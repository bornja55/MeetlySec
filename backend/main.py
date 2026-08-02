import datetime
import json
import logging
import os

from audio import AudioWorkerBusyError, AudioWorkerError, audio_pipeline
from auth import require_role, verify_azure_ad_token
from db import get_db, init_db
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, UploadFile
from fastapi.staticfiles import StaticFiles
from models import Meeting, MeetingAgendaItem, MeetingAttendee
from pydantic import BaseModel
from rag import RAGWorkerError, rag_pipeline
from sqlalchemy.orm import Session

log = logging.getLogger("com_sec.main")

app = FastAPI(
    title="Company Secretary AI System - API",
    description="Backend for the Com Sec Meeting & RAG Assistant",
    version="1.0.0"
)

# สร้างตาราง DB ตอน import โมดูลนี้ (แทน startup event — โปรเจกต์นี้รันแบบ script ตรงๆผ่าน
# uvicorn main:app เดียว ไม่มีหลาย entrypoint ให้ต้องแยก event hook) ดู db.py's docstring
# เรื่อง Alembic migration ที่ยังไม่ทำ (MVP เท่านั้น)
init_db()

# role ที่มีสิทธิ์สร้าง/อัปโหลดไฟล์เสียงการประชุม — ใช้ชุดเดียวกับ /api/rag/query_confidential
# (Com_Sec_Maker/Checker คือคนทำงานจริง, Global_Admin ได้สิทธิ์ทุก role อยู่แล้วจาก require_role())
MEETING_MANAGE_ROLES = ["Com_Sec_Maker", "Com_Sec_Checker"]

UPLOAD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploads")

# Module 6 (Front-End): dashboard ที่ออกแบบจาก Google Stitch (Antigravity) แล้ว wire เข้ากับ API
# จริงในเซสชันนี้ (ดู handoff.md) — serve เป็น static files ตรงๆจาก FastAPI เดียวกัน (same-origin
# กับ /api/* ทั้งหมด) เลือกทางนี้แทนแยก dev server ต่างหาก เพราะไม่ต้องตั้งค่า CORS เลย — ใช้ path
# prefix "/dashboard" (ไม่ใช่ "/") กัน conflict กับ endpoint "/" (read_root) เดิม
DASHBOARD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "ComSecAI_Dashboard")
if os.path.isdir(DASHBOARD_DIR):
    app.mount("/dashboard", StaticFiles(directory=DASHBOARD_DIR, html=True), name="dashboard")
else:
    # ไม่ crash ทั้ง backend แค่เพราะโฟลเดอร์ frontend หาย (เช่น clone repo ใหม่ยังไม่มีโฟลเดอร์นี้)
    # — API endpoints อื่นทั้งหมดต้องยังใช้งานได้ปกติ
    log.warning(f"ไม่พบโฟลเดอร์ dashboard ที่ {DASHBOARD_DIR} — ข้าม mount /dashboard")


class QueryBody(BaseModel):
    query: str


@app.get("/")
def read_root():
    return {"message": "Welcome to Com Sec AI Backend API"}


# Module 1: Local-RAG Endpoints — rag_pipeline เป็น HTTP client ไปหา RAG worker โปรเซสแยก
# (D:\Com Sec\rag_worker\main.py, ดู backend/rag.py) ไม่ใช่ stub คืนค่า hardcoded อีกต่อไป
# (แก้จาก /scrutinize 2026-08-01 — ดู handoff.md ข้อ 3.0)
#
# หมายเหตุ (2026-08-01): `query` เดิมเป็น query parameter (`?query=...`) — ใช้ได้กับ ASCII
# เท่านั้น พอส่งข้อความภาษาไทยดิบๆ ใน URL (ไม่ผ่าน percent-encoding) จะได้ HTTP request line ที่ผิด
# กฎ RFC 7230 (request-target ต้องเป็น VCHAR/ASCII visible เท่านั้น) ทำให้ uvicorn ปฏิเสธ request
# ทั้งก้อนตั้งแต่ชั้น parser เลย (ก่อนถึง FastAPI ด้วยซ้ำ) — เปลี่ยนเป็นรับผ่าน JSON body แทน (มาตรฐาน
# ของ FastAPI สำหรับ endpoint ที่รับข้อความยาว/ไม่ใช่ ASCII) ผ่าน UTF-8 ได้ตรงๆ ไม่ต้อง encode เอง
@app.post("/api/rag/query")
def query_policy(body: QueryBody, user: dict = Depends(verify_azure_ad_token)):
    try:
        result = rag_pipeline.query(
            body.query, user_id=user["user_id"], search_scope="general",
        )
    except RAGWorkerError as e:
        raise HTTPException(status_code=503, detail=str(e))
    return {"query": body.query, "user": user, **result}


@app.post("/api/rag/query_confidential")
def query_confidential(
    body: QueryBody,
    user: dict = Depends(require_role(["Com_Sec_Maker", "Com_Sec_Checker", "Board_Member"])),
):
    # Only Com Sec team, Board Member, and Global Admin can access this — เช็คซ้ำอีกชั้นที่ worker
    # เอง (defense in depth ดู rag_worker/main.py's /query_confidential)
    try:
        result = rag_pipeline.query(
            body.query, user_id=user["user_id"], search_scope="confidential", role=user["role"],
        )
    except RAGWorkerError as e:
        raise HTTPException(status_code=503, detail=str(e))
    return {"query": body.query, "user": user, **result}

# ────────────────────────────────────────────────────────────────────────────────────────
# Module 2: Meeting entity + upload — สร้าง "การประชุม" ก่อนอัปโหลดไฟล์เสียงเสมอ (ตัดสินใจ
# `/grill-me` รอบ 3, ดู task.md Module 2) ประมวลผลเสียงเรียก audio_worker (โปรเซสแยก, ดู audio.py)
# ผ่าน FastAPI BackgroundTasks — คนละเรื่องกับ "audio_worker เป็นโปรเซสแยก" (นั่นคือที่ๆ งานหนัก
# GPU รันจริง) ส่วน BackgroundTasks ที่นี่แค่ทำให้ HTTP response ของ /upload ไม่ต้องรอจนประมวลผล
# เสร็จ (อาจนานหลายสิบนาทีถึงชั่วโมงสำหรับประชุมยาว) — client poll สถานะผ่าน GET /api/meetings/{id}
# แทน
# ────────────────────────────────────────────────────────────────────────────────────────


class AttendeeIn(BaseModel):
    name: str
    position: str | None = None


class MeetingCreateBody(BaseModel):
    meeting_number: str  # เช่น "15/2569" ตรงกับชื่อไฟล์ template
    meeting_date: datetime.date
    attendees: list[AttendeeIn] = []
    agenda_items: list[str] = []


def _extract_speaker_labels(transcript_segments: list[dict] | None) -> list[str]:
    """รายชื่อ speaker label ที่ต่างกันทั้งหมด (เช่น `SPEAKER_00`/`SPEAKER_01`) เรียงตามลำดับที่
    ปรากฏครั้งแรกใน transcript — ใช้เช็คว่า Speaker Mapping ครบหรือยัง (ตัดสินใจจาก `/grill-me`
    รอบ 3: ทุก label ต้องมีชื่อจริงจับคู่ก่อนถึงจะสรุปเป็น Minutes ได้ใน Module 3)"""
    if not transcript_segments:
        return []
    seen: list[str] = []
    for seg in transcript_segments:
        speaker = seg.get("speaker")
        if speaker and speaker not in seen:
            seen.append(speaker)
    return seen


def _meeting_to_dict(meeting: Meeting) -> dict:
    transcript_segments = (
        json.loads(meeting.transcript_segments_json)
        if meeting.transcript_segments_json else None
    )
    speaker_labels = _extract_speaker_labels(transcript_segments)
    speaker_mapping: dict[str, str] = (
        json.loads(meeting.speaker_mapping_json) if meeting.speaker_mapping_json else {}
    )
    return {
        "id": meeting.id,
        "meeting_number": meeting.meeting_number,
        "meeting_date": meeting.meeting_date.isoformat(),
        "status": meeting.status,
        "audio_filename": meeting.audio_filename,
        "processing_error": meeting.processing_error,
        "attendees": [
            {"name": a.name, "position": a.position} for a in meeting.attendees
        ],
        "agenda_items": [a.description for a in meeting.agenda_items],
        # Redesign 2026-08-02 (ดู handoff.md 3.3): field เดียวแทน diarization_segments/asr_chunks
        # เดิม — audio_worker ตัด ASR ทีละ diarization segment แล้วคืน {start, end, speaker, text}
        # ต่อ segment ตรงๆ
        "transcript_segments": transcript_segments,
        # Speaker Mapping (บังคับ, ดู handoff.md session นี้): speaker_labels คือ label ทั้งหมดที่
        # เจอจริงใน transcript (ground truth มาจากข้อมูลจริง ไม่ใช่เดาว่ามีกี่คน), speaker_mapping
        # คือสิ่งที่จับคู่ไว้แล้ว (อาจไม่ครบ — ตั้งผ่าน POST .../speaker_mapping),
        # speaker_mapping_complete = true ก็ต่อเมื่อมี label อย่างน้อย 1 ตัวและทุกตัวถูกจับคู่กับชื่อ
        # ที่ไม่ว่างเปล่าแล้วเท่านั้น (Module 3 ต้องเช็คค่านี้ก่อนอนุญาตสรุปเป็น Minutes)
        "speaker_labels": speaker_labels,
        "speaker_mapping": speaker_mapping,
        "speaker_mapping_complete": bool(speaker_labels) and all(
            speaker_mapping.get(label, "").strip() for label in speaker_labels
        ),
    }


@app.post("/api/meetings")
def create_meeting(
    body: MeetingCreateBody,
    db: Session = Depends(get_db),
    user: dict = Depends(require_role(MEETING_MANAGE_ROLES)),
):
    meeting = Meeting(
        meeting_number=body.meeting_number,
        meeting_date=datetime.datetime.combine(body.meeting_date, datetime.time.min),
        created_by_user_id=user["user_id"],
        status="draft",
        attendees=[MeetingAttendee(name=a.name, position=a.position) for a in body.attendees],
        agenda_items=[
            MeetingAgendaItem(order=i, description=desc)
            for i, desc in enumerate(body.agenda_items)
        ],
    )
    db.add(meeting)
    db.commit()
    db.refresh(meeting)
    return _meeting_to_dict(meeting)


@app.get("/api/meetings")
def list_meetings(db: Session = Depends(get_db), user: dict = Depends(verify_azure_ad_token)):
    # ⚠️ ยังไม่ได้ออกแบบ RBAC เฉพาะสำหรับดู Meeting list (ต่างจาก MEETING_MANAGE_ROLES ที่คุมแค่
    # สร้าง/อัปโหลด) — ตอนนี้อนุญาตทุก authenticated user เห็นได้หมดก่อน ต้องทบทวนก่อน production
    meetings = db.query(Meeting).order_by(Meeting.created_at.desc()).all()
    return [_meeting_to_dict(m) for m in meetings]


@app.get("/api/meetings/{meeting_id}")
def get_meeting(
    meeting_id: int, db: Session = Depends(get_db), user: dict = Depends(verify_azure_ad_token)
):
    meeting = db.get(Meeting, meeting_id)
    if meeting is None:
        raise HTTPException(status_code=404, detail="ไม่พบการประชุมนี้")
    return _meeting_to_dict(meeting)


def _process_meeting_audio_background(meeting_id: int, filename: str) -> None:
    """รันใน FastAPI BackgroundTask — เปิด DB session ใหม่ของตัวเอง (session ของ request เดิม
    ปิดไปแล้วตอน response ส่งกลับ ใช้ต่อไม่ได้) เรียก audio_worker (โปรเซสแยก) แบบ synchronous
    (บล็อกอยู่ใน background task เท่านั้น ไม่บล็อก HTTP response ที่ตอบ client ไปแล้ว)"""
    from db import SessionLocal

    db = SessionLocal()
    try:
        meeting = db.get(Meeting, meeting_id)
        if meeting is None:
            return  # ถูกลบไปแล้วระหว่างรอคิว — ไม่มีอะไรให้อัปเดต

        meeting.status = "processing"
        db.commit()

        try:
            result = audio_pipeline.process(str(meeting_id), filename)
        except AudioWorkerBusyError as e:
            # ⚠️ ยังไม่มีระบบ retry/คิวจริง (ดู task.md Module 2 "ออกแบบ UX คิว" ที่ยังไม่ได้ทำ) —
            # ตอนนี้แค่บันทึกว่าล้มเหลวเพราะ worker ยุ่ง ผู้ใช้ต้องอัปโหลดซ้ำเอง
            meeting.status = "failed"
            meeting.processing_error = f"worker กำลังยุ่งอยู่ ลองอัปโหลดใหม่อีกครั้ง: {e}"
            db.commit()
            return
        except AudioWorkerError as e:
            meeting.status = "failed"
            meeting.processing_error = str(e)
            db.commit()
            return

        meeting.status = "transcribed"
        meeting.transcript_segments_json = json.dumps(result.get("transcript_segments"))
        db.commit()
    finally:
        db.close()


@app.post("/api/meetings/{meeting_id}/upload")
def upload_meeting_audio(
    meeting_id: int,
    background_tasks: BackgroundTasks,
    file: UploadFile,
    db: Session = Depends(get_db),
    user: dict = Depends(require_role(MEETING_MANAGE_ROLES)),
):
    meeting = db.get(Meeting, meeting_id)
    if meeting is None:
        raise HTTPException(status_code=404, detail="ไม่พบการประชุมนี้")

    # ตั้งชื่อไฟล์เองจาก meeting_id + นามสกุลต้นฉบับเท่านั้น (ไม่ใช้ชื่อไฟล์ที่ผู้ใช้ส่งมาตรงๆ —
    # กัน path traversal ที่ต้นทาง แทนที่จะพึ่ง _reject_path_traversal ฝั่ง audio_worker เพียงอย่าง
    # เดียว, ดู audio_worker/main.py สำหรับ defense-in-depth อีกชั้น)
    ext = os.path.splitext(file.filename or "")[1] or ".bin"
    safe_filename = f"meeting_{meeting_id}{ext}"

    os.makedirs(UPLOAD_DIR, exist_ok=True)
    dest_path = os.path.join(UPLOAD_DIR, safe_filename)
    with open(dest_path, "wb") as f:
        f.write(file.file.read())

    meeting.audio_filename = safe_filename
    meeting.status = "uploaded"
    meeting.processing_error = None
    # ล้าง speaker mapping เก่าทิ้งเสมอตอนอัปโหลดไฟล์ใหม่ (เช่น อัปโหลดซ้ำแก้ไฟล์ผิด) — diarization
    # clustering ID (SPEAKER_00/01/...) ไม่ stable ข้าม run มี label เดิมไม่ได้แปลว่าเป็นคนเดิม
    # เก็บ mapping เก่าไว้จะทำให้จับคู่ผิดคนแบบเงียบๆ ปลอดภัยกว่าให้ผู้ใช้จับคู่ใหม่ทุกครั้งที่มี
    # transcript ชุดใหม่
    meeting.speaker_mapping_json = None
    db.commit()

    background_tasks.add_task(_process_meeting_audio_background, meeting_id, safe_filename)

    return {"message": "อัปโหลดสำเร็จ กำลังประมวลผลเบื้องหลัง", **_meeting_to_dict(meeting)}


class TranscriptSegmentIn(BaseModel):
    # โครงเดียวกับที่ audio_worker คืนมา ({start, end, speaker, text}) — ดู
    # audio_worker/asr.py::transcribe_segments — ฟอร์มแก้ไข transcript (ไม่บังคับ, ตามแผน Module 2)
    # ส่ง start/end/speaker เดิมกลับมาด้วยเสมอ (ไม่ให้ผู้ใช้แก้ผ่าน UI นี้ แก้ได้แค่ text) แต่ backend
    # รับ start/end/speaker เป็น field ที่แก้ไขได้ในตัว schema ไว้ก่อน เผื่ออนาคตต้องการ reassign
    # speaker ต่อ segment (ยังไม่ทำ UI ส่วนนั้นตอนนี้)
    start: float
    end: float
    speaker: str | None = None
    text: str


class TranscriptSegmentsBody(BaseModel):
    transcript_segments: list[TranscriptSegmentIn]


@app.put("/api/meetings/{meeting_id}/transcript_segments")
def update_transcript_segments(
    meeting_id: int,
    body: TranscriptSegmentsBody,
    db: Session = Depends(get_db),
    user: dict = Depends(require_role(MEETING_MANAGE_ROLES)),
):
    """แก้ไขข้อความ transcript (ไม่บังคับ, ตามแผน Module 2 — ใช้ UI เดียวกับที่จะกลายเป็น
    transcript-sync player ใน Module 6 ทีหลัง) — เขียนทับทั้ง array เสมอ (pattern เดียวกับ
    `set_speaker_mapping` ด้านบน: ให้ caller ส่ง state ปัจจุบันทั้งหมดมาทุกครั้ง ตรงไปตรงมากว่า
    partial-update ทีละ segment)"""
    meeting = db.get(Meeting, meeting_id)
    if meeting is None:
        raise HTTPException(status_code=404, detail="ไม่พบการประชุมนี้")
    if not meeting.transcript_segments_json:
        raise HTTPException(
            status_code=400,
            detail="ยังไม่มี transcript ให้แก้ไข — ต้องรอสถานะ 'transcribed' ก่อน",
        )

    meeting.transcript_segments_json = json.dumps(
        [seg.model_dump() for seg in body.transcript_segments]
    )
    db.commit()
    return _meeting_to_dict(meeting)


class SpeakerMappingBody(BaseModel):
    # {"SPEAKER_00": "สมชาย ใจดี", "SPEAKER_01": "..."} — key ต้องตรงกับ label จริงจาก diarization
    # (ดู GET .../{id}'s "speaker_labels" สำหรับ label ทั้งหมดที่ต้องจับคู่) ไม่บังคับว่า value ต้อง
    # ตรงกับชื่อใน meeting.attendees เป๊ะ (เผื่อมีคนพูดที่ไม่ได้อยู่ใน attendee list ที่กรอกไว้ล่วงหน้า
    # เช่น ผู้บรรยายรับเชิญ) — validation เรื่องนี้ปล่อยเป็นหน้าที่ UI ชั้น frontend (Module 6)
    mapping: dict[str, str]


@app.post("/api/meetings/{meeting_id}/speaker_mapping")
def set_speaker_mapping(
    meeting_id: int,
    body: SpeakerMappingBody,
    db: Session = Depends(get_db),
    user: dict = Depends(require_role(MEETING_MANAGE_ROLES)),
):
    """บันทึกการจับคู่ Speaker_00/01/... กับชื่อจริง (บังคับก่อนสรุปเป็น Minutes ได้ใน Module 3,
    ตัดสินใจจาก `/grill-me` รอบ 3) — เขียนทับทั้ง dict เสมอในคราวเดียว (ไม่ merge ทีละ key) ให้
    caller ส่ง mapping ทั้งหมดที่ต้องการมาทุกครั้ง ตรงไปตรงมากว่า partial-update ที่อาจทำให้ mapping
    เก่า/ใหม่ปนกันโดยไม่ตั้งใจถ้ามีการแก้ไขพร้อมกันจากหลายที่"""
    meeting = db.get(Meeting, meeting_id)
    if meeting is None:
        raise HTTPException(status_code=404, detail="ไม่พบการประชุมนี้")
    if not meeting.transcript_segments_json:
        raise HTTPException(
            status_code=400,
            detail="ยังไม่มี transcript ให้จับคู่ผู้พูด — ต้องรอสถานะ 'transcribed' ก่อน",
        )

    meeting.speaker_mapping_json = json.dumps(body.mapping)
    db.commit()
    return _meeting_to_dict(meeting)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
