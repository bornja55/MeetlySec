import datetime
import json
import logging
import mimetypes
import os
import secrets
from typing import Literal

import archive
import config
import docx_generation
import email_service
import magic_link
import pdf_generation
from audio import AudioWorkerBusyError, AudioWorkerError, audio_pipeline
from auth import require_role, require_role_for_audio_stream, verify_azure_ad_token
from db import get_db, init_db
from docx_generation import DocxGenerationError
from email_service import EmailSendError
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from magic_link import MagicLinkError
from minutes_generation import MinutesGenerationError, generate_minutes
from models import Meeting, MeetingAgendaItem, MeetingApprovalLog, MeetingAttendee
from pdf_generation import PdfGenerationError
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
    # Module 4-5 (2026-08-03): กรอกเองต่อการประชุม — attendee ที่มี email จะได้รับ Magic Link หลัง
    # Checker Approve (ดู models.py's MeetingAttendee.email docstring สำหรับที่มาการตัดสินใจ)
    email: str | None = None


class MeetingCreateBody(BaseModel):
    meeting_number: str  # เช่น "15/2569" ตรงกับชื่อไฟล์ template
    meeting_date: datetime.date
    attendees: list[AttendeeIn] = []
    agenda_items: list[str] = []
    # Multi-template (2026-08-03) — ชื่อ key ใน docx_generation.TEMPLATE_REGISTRY เลือกตอนสร้าง
    # การประชุม (ดู GET /api/templates ด้านล่างสำหรับรายการที่ frontend ใช้ populate dropdown)
    template_name: str = docx_generation.DEFAULT_TEMPLATE_NAME


@app.get("/api/templates")
def list_meeting_templates(user: dict = Depends(verify_azure_ad_token)):
    """Multi-template (2026-08-03) — คืนรายการ template ที่มีให้เลือกตอนสร้างการประชุม (ใช้
    populate dropdown ใน create-meeting.html) — ไม่ใช่ endpoint จัดการ role พิเศษ (แค่ metadata
    ไม่มีข้อมูลลับ) เลยอนุญาตทุก authenticated user เรียกได้เหมือน GET /api/meetings"""
    return docx_generation.list_templates()


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


def _is_speaker_mapping_complete(speaker_labels: list[str], speaker_mapping: dict[str, str]) -> bool:
    """แยกออกมาจาก _meeting_to_dict() (2026-08-03, Module 3) เพราะตอนนี้มี 2 จุดที่ต้องเช็คเงื่อนไข
    เดียวกัน — ตัวนี้ (แสดงผลใน API response) กับ endpoint สร้าง Minutes ด้านล่างที่ต้อง**บังคับ**
    เงื่อนไขนี้ก่อนอนุญาตเรียก Gemini (ตัดสินใจจาก `/grill-me` รอบ 3, ดู task.md Module 2/3) —
    เขียนตรรกะซ้ำ 2 ที่เสี่ยง diverge กันถ้าแก้จุดใดจุดหนึ่งแล้วลืมอีกจุด"""
    return bool(speaker_labels) and all(
        speaker_mapping.get(label, "").strip() for label in speaker_labels
    )


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
            {"name": a.name, "position": a.position, "email": a.email} for a in meeting.attendees
        ],
        "agenda_items": [a.description for a in meeting.agenda_items],
        # Multi-template (2026-08-03) — เลือกไว้ตอนสร้างการประชุม แก้ทีหลังไม่ได้ผ่าน API นี้
        "template_name": meeting.template_name,
        "template_label": docx_generation.TEMPLATE_REGISTRY.get(
            meeting.template_name, docx_generation.TEMPLATE_REGISTRY[docx_generation.DEFAULT_TEMPLATE_NAME]
        )["label"],
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
        "speaker_mapping_complete": _is_speaker_mapping_complete(speaker_labels, speaker_mapping),
        # Module 3 (Minutes Generation, ดู minutes_generation.py) — None จนกว่าจะสร้างสำเร็จครั้งแรก
        "minutes": json.loads(meeting.minutes_json) if meeting.minutes_json else None,
        "minutes_generated_at": (
            meeting.minutes_generated_at.isoformat() if meeting.minutes_generated_at else None
        ),
        # Module 4-5 (2026-08-03, Word Template Mapping & Approval Workflow) — ดู models.py's
        # docstring หัวข้อ Module 4-5 สำหรับที่มาการตัดสินใจแต่ละ field ⚠️ ไม่ใส่
        # `final_pdf_password` ในนี้โดยตั้งใจ — endpoint นี้ให้ authenticated user ทุก role อ่านได้
        # (ดู get_meeting ด้านล่าง) รหัสผ่าน PDF ต้องส่งผ่านอีเมลเท่านั้น ไม่ผ่าน API ทั่วไป
        "approval_status": meeting.approval_status,
        "has_draft_docx": bool(meeting.minutes_docx_path),
        "has_final_docx": bool(meeting.final_docx_path),
        "has_final_pdf": bool(meeting.final_pdf_path),
    }


@app.post("/api/meetings")
def create_meeting(
    body: MeetingCreateBody,
    db: Session = Depends(get_db),
    user: dict = Depends(require_role(MEETING_MANAGE_ROLES)),
):
    # Multi-template: ชื่อไม่รู้จัก → fallback เป็น default เงียบๆ (เหมือน docx_generation's
    # _resolve_template_path) แทนที่จะ 400 ปฏิเสธการสร้างประชุมทั้งใบเพราะ dropdown ฝั่ง client
    # ส่งค่าผิด/เก่ามา — ไม่ใช่ input ที่ user พิมพ์เองอิสระ (มาจาก dropdown เท่านั้น) ความเสี่ยงต่ำ
    template_name = (
        body.template_name
        if body.template_name in docx_generation.TEMPLATE_REGISTRY
        else docx_generation.DEFAULT_TEMPLATE_NAME
    )
    meeting = Meeting(
        meeting_number=body.meeting_number,
        meeting_date=datetime.datetime.combine(body.meeting_date, datetime.time.min),
        created_by_user_id=user["user_id"],
        status="draft",
        template_name=template_name,
        attendees=[
            MeetingAttendee(name=a.name, position=a.position, email=a.email)
            for a in body.attendees
        ],
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


# mimetypes.guess_type() เดามาผิด/ไม่ตรงมาตรฐานสำหรับบางนามสกุลที่โปรเจกต์นี้เจอจริง (เช่น .wav ได้
# "audio/x-wav" ซึ่งบาง browser ไม่รู้จัก) — ทับด้วยค่าที่ตรงมาตรฐาน HTML5 <audio>/<video> ก่อน แล้ว
# ค่อย fallback ไปที่ mimetypes สำหรับนามสกุลอื่นที่ไม่อยู่ใน list นี้
AUDIO_VIDEO_MEDIA_TYPES = {
    ".wav": "audio/wav",
    ".mp3": "audio/mpeg",
    ".m4a": "audio/mp4",
    ".aac": "audio/aac",
    ".ogg": "audio/ogg",
    ".flac": "audio/flac",
    ".mp4": "video/mp4",
    ".mov": "video/quicktime",
    ".webm": "video/webm",
}


@app.get("/api/meetings/{meeting_id}/audio")
def get_meeting_audio(
    meeting_id: int,
    db: Session = Depends(get_db),
    user: dict = Depends(require_role_for_audio_stream(MEETING_MANAGE_ROLES)),
):
    """ให้ HTML5 <audio> element ของ Synced Playback panel (ดู ComSecAI_Dashboard) stream ไฟล์เสียง/
    วิดีโอต้นฉบับกลับมาเล่นย้อนหลัง (feature ที่ task.md Module 6 ทิ้งไว้ว่ายังไม่ได้ทำ) — ใช้
    require_role_for_audio_stream (รับ token ผ่าน query string แทน header เพราะ <audio src=...> แนบ
    Authorization header เองไม่ได้ ดู auth.py) ผูก role ชุดเดียวกับ MEETING_MANAGE_ROLES ตรงกับ
    การตัดสินใจที่บันทึกไว้ใน handoff.md 3.0: "ไฟล์เสียง/วิดีโอ → เฉพาะทีม Com Sec เท่านั้น
    (Board_Member เข้าไม่ได้)" — นี่คือ RBAC ของ transcript-sync player ที่ task.md ทิ้งค้างไว้เป็น
    TODO มาหลาย session

    ใช้ FileResponse ตรงๆ (ไม่ใส่ filename= กัน browser บังคับดาวน์โหลดแทนเล่น inline) — Starlette's
    FileResponse รองรับ HTTP Range request (206 Partial Content) ในตัวอยู่แล้ว ทำให้ seek/scrub
    ตำแหน่งเล่นได้โดยไม่ต้องโหลดทั้งไฟล์ก่อน (สำคัญมากสำหรับไฟล์ประชุมยาวเป็นชม.)"""
    meeting = db.get(Meeting, meeting_id)
    if meeting is None:
        raise HTTPException(status_code=404, detail="ไม่พบการประชุมนี้")
    if not meeting.audio_filename:
        raise HTTPException(status_code=404, detail="การประชุมนี้ยังไม่มีไฟล์เสียง/วิดีโอ")

    file_path = os.path.join(UPLOAD_DIR, meeting.audio_filename)
    if not os.path.isfile(file_path):
        raise HTTPException(status_code=404, detail="ไม่พบไฟล์บนเซิร์ฟเวอร์ (อาจถูกลบไปแล้ว)")

    ext = os.path.splitext(meeting.audio_filename)[1].lower()
    media_type = AUDIO_VIDEO_MEDIA_TYPES.get(ext) or mimetypes.guess_type(file_path)[0] or "application/octet-stream"
    return FileResponse(file_path, media_type=media_type)


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


# ────────────────────────────────────────────────────────────────────────────────────────
# Module 3: Minutes Generation — เรียก Gemini ตรงๆ จากโปรเซสนี้ (ไม่แยกโปรเซสแบบ rag_worker/
# audio_worker เพราะ google-genai ไม่มี native library ที่จะชน Windows WINHTTP.dll — ดู
# minutes_generation.py หัวไฟล์สำหรับเหตุผลเต็ม)
# ────────────────────────────────────────────────────────────────────────────────────────


@app.post("/api/meetings/{meeting_id}/generate_minutes")
def generate_meeting_minutes(
    meeting_id: int,
    db: Session = Depends(get_db),
    user: dict = Depends(require_role(MEETING_MANAGE_ROLES)),
):
    """สร้าง Minutes of Meeting ผ่าน Gemini (Module 3) — บังคับ Speaker Mapping ครบ 100% ก่อนเสมอ
    (ตัดสินใจจาก `/grill-me` รอบ 3: "Module 3 บล็อกถ้ายังจับคู่ไม่ครบ" ดู task.md Module 2) เขียนทับ
    `minutes_json` เดิมทั้งก้อนถ้าเรียกซ้ำ (ยังไม่มี versioning — สอดคล้องกับ pattern JSON blob อื่นๆ
    ในโปรเจกต์นี้ เช่น speaker_mapping/transcript_segments)"""
    meeting = db.get(Meeting, meeting_id)
    if meeting is None:
        raise HTTPException(status_code=404, detail="ไม่พบการประชุมนี้")
    if not meeting.transcript_segments_json:
        raise HTTPException(
            status_code=400, detail="ยังไม่มี transcript — ต้องรอสถานะ 'transcribed' ก่อน"
        )

    transcript_segments = json.loads(meeting.transcript_segments_json)
    speaker_labels = _extract_speaker_labels(transcript_segments)
    speaker_mapping: dict[str, str] = (
        json.loads(meeting.speaker_mapping_json) if meeting.speaker_mapping_json else {}
    )
    if not _is_speaker_mapping_complete(speaker_labels, speaker_mapping):
        raise HTTPException(
            status_code=400,
            detail="ต้องจับคู่ผู้พูด (Speaker Mapping) ให้ครบทุกคนก่อนสรุปเป็น Minutes ได้",
        )

    agenda_descriptions = [a.description for a in meeting.agenda_items]

    try:
        minutes = generate_minutes(
            company_name=config.COMPANY_NAME,
            meeting_number=meeting.meeting_number,
            meeting_date_iso=meeting.meeting_date.isoformat(),
            attendees=[{"name": a.name, "position": a.position} for a in meeting.attendees],
            agenda_descriptions=agenda_descriptions,
            transcript_segments=transcript_segments,
            speaker_mapping=speaker_mapping,
        )
    except MinutesGenerationError as e:
        # ปฏิเสธด้วย 400 ถ้าไม่มีวาระ (ผู้ใช้แก้ได้เอง — เพิ่มวาระ) ที่เหลือ (Gemini ล้มเหลว/schema
        # ไม่ตรง/API key ไม่มี) เป็น 503 (ปัญหาระบบ ไม่ใช่ input ผิดของผู้ใช้) — ดู
        # backend/rag.py's RAGWorkerError สำหรับ pattern การแยก error code เดียวกัน
        status_code = 400 if not agenda_descriptions else 503
        raise HTTPException(status_code=status_code, detail=str(e))

    meeting.minutes_json = json.dumps(minutes)
    meeting.minutes_generated_at = datetime.datetime.utcnow()
    db.commit()
    return _meeting_to_dict(meeting)


# ────────────────────────────────────────────────────────────────────────────────────────
# Module 4-5: Word Template Mapping & Finalization/Secure Delivery (2026-08-03) — ดู
# models.py's docstring หัวข้อ Module 4-5 สำหรับที่มาการตัดสินใจทั้งหมด (docxtpl template ใหม่,
# Maker แก้ตารางธุรกรรมเองใน Word, docx2pdf ผ่าน MS Word, SMTP แทน Graph API, attendee.email
# กรอกเอง) — flow เต็ม: generate_docx (Maker/Checker) → download → แก้ใน Word → upload_final_docx
# (Maker, เข้าสถานะ Pending_Review) → review (Checker, approve/reject) → approve trigger
# background task แปลง PDF + ใส่รหัสผ่าน + ส่ง Magic Link + archive
# ────────────────────────────────────────────────────────────────────────────────────────

GENERATABLE_STATUSES = ("Draft", "Needs_Revision")  # สร้าง/regenerate ร่าง .docx ได้เฉพาะสถานะนี้


@app.post("/api/meetings/{meeting_id}/generate_docx")
def generate_meeting_docx(
    meeting_id: int,
    db: Session = Depends(get_db),
    user: dict = Depends(require_role(MEETING_MANAGE_ROLES)),
):
    """สร้าง/regenerate ร่าง .docx จาก minutes_json ผ่าน docxtpl (Module 4) — เขียนทับ
    minutes_docx_path เดิมเสมอถ้าเรียกซ้ำ ตรงกับ pattern JSON blob อื่นๆของโปรเจกต์นี้ ปิดกั้นถ้า
    approval_status ไม่ใช่ Draft/Needs_Revision (กันสร้างร่างใหม่ทับระหว่างรอ Checker ตรวจอยู่)"""
    meeting = db.get(Meeting, meeting_id)
    if meeting is None:
        raise HTTPException(status_code=404, detail="ไม่พบการประชุมนี้")
    if not meeting.minutes_json:
        raise HTTPException(status_code=400, detail="ยังไม่มี Minutes — ต้องกด Generate Minutes ก่อน")
    if meeting.approval_status not in GENERATABLE_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"ไม่สามารถสร้างร่างเอกสารใหม่ได้ในสถานะปัจจุบัน ({meeting.approval_status})",
        )

    try:
        docx_path = docx_generation.render_minutes_docx(
            meeting_id, json.loads(meeting.minutes_json), meeting.template_name
        )
    except DocxGenerationError as e:
        raise HTTPException(status_code=503, detail=str(e))

    meeting.minutes_docx_path = os.path.basename(docx_path)
    db.commit()
    return _meeting_to_dict(meeting)


@app.get("/api/meetings/{meeting_id}/download_docx")
def download_meeting_docx(
    meeting_id: int,
    variant: Literal["draft", "final"] = "draft",
    db: Session = Depends(get_db),
    user: dict = Depends(require_role(MEETING_MANAGE_ROLES)),
):
    """ดาวน์โหลด .docx — variant=draft คือร่างที่ AI สร้าง (สำหรับ Maker เอาไปแก้ต่อใน Word),
    variant=final คือฉบับที่ Maker อัปโหลดกลับมาแล้ว (สำหรับ Checker ตรวจก่อน Approve)"""
    meeting = db.get(Meeting, meeting_id)
    if meeting is None:
        raise HTTPException(status_code=404, detail="ไม่พบการประชุมนี้")

    filename = meeting.minutes_docx_path if variant == "draft" else meeting.final_docx_path
    if not filename:
        raise HTTPException(status_code=404, detail=f"ยังไม่มีไฟล์ {variant} ให้ดาวน์โหลด")

    full_path = os.path.join(docx_generation.GENERATED_DOCS_DIR, filename)
    if not os.path.exists(full_path):
        raise HTTPException(status_code=404, detail="ไม่พบไฟล์บนเซิร์ฟเวอร์ (อาจถูกลบไปแล้ว)")

    download_name = f"minutes_{meeting.meeting_number.replace('/', '-')}_{variant}.docx"
    return FileResponse(
        full_path,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=download_name,
    )


@app.post("/api/meetings/{meeting_id}/upload_final_docx")
def upload_meeting_final_docx(
    meeting_id: int,
    file: UploadFile,
    db: Session = Depends(get_db),
    user: dict = Depends(require_role(MEETING_MANAGE_ROLES)),
):
    """Maker อัปโหลดไฟล์ .docx ฉบับที่แก้/เพิ่มตารางธุรกรรมด้วย Word เองแล้วกลับเข้าระบบ (Module 4-5,
    ตัดสินใจจาก AskUserQuestion — ไม่สร้าง table editor ในระบบ) — เข้าสถานะ Pending_Review ทันที
    เพื่อรอ Checker ตรวจ"""
    meeting = db.get(Meeting, meeting_id)
    if meeting is None:
        raise HTTPException(status_code=404, detail="ไม่พบการประชุมนี้")
    if not meeting.minutes_docx_path:
        raise HTTPException(
            status_code=400, detail="ต้องสร้างร่างเอกสาร (Generate Docx) ก่อนอัปโหลดฉบับสมบูรณ์"
        )
    if meeting.approval_status not in GENERATABLE_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"ไม่สามารถอัปโหลดฉบับสมบูรณ์ใหม่ได้ในสถานะปัจจุบัน ({meeting.approval_status})",
        )
    if not (file.filename or "").lower().endswith(".docx"):
        raise HTTPException(status_code=400, detail="ต้องเป็นไฟล์ .docx เท่านั้น")

    os.makedirs(docx_generation.GENERATED_DOCS_DIR, exist_ok=True)
    # ตั้งชื่อไฟล์เองเสมอ (กัน path traversal ที่ต้นทาง เหมือน upload_meeting_audio ด้านบน — ไม่ใช้
    # ชื่อไฟล์จากผู้ใช้ตรงๆ)
    safe_filename = f"meeting_{meeting_id}_final.docx"
    dest_path = os.path.join(docx_generation.GENERATED_DOCS_DIR, safe_filename)
    with open(dest_path, "wb") as f:
        f.write(file.file.read())

    from_status = meeting.approval_status
    meeting.final_docx_path = safe_filename
    meeting.approval_status = "Pending_Review"
    db.add(MeetingApprovalLog(
        meeting_id=meeting_id, action="submit_for_review", from_status=from_status,
        to_status="Pending_Review", user_id=user["user_id"],
    ))
    db.commit()
    return {"message": "อัปโหลดฉบับสมบูรณ์สำเร็จ ส่งให้ Checker ตรวจสอบแล้ว", **_meeting_to_dict(meeting)}


class ReviewBody(BaseModel):
    action: Literal["approve", "reject"]
    comment: str | None = None


def _archive_and_notify_background(meeting_id: int) -> None:
    """รันใน FastAPI BackgroundTask หลัง Checker กด Approve (ดู pattern เดียวกับ
    `_process_meeting_audio_background`) — แปลง final_docx → PDF (docx2pdf ผ่าน MS Word) → ใส่
    รหัสผ่าน (pypdf) → สร้าง Magic Link token ต่อ attendee ที่มี email → ส่งอีเมล → archive ไฟล์ —
    **แต่ละขั้นตอนแยก try/except ของตัวเอง** ไม่ให้ขั้นตอนหลังพังเพราะขั้นตอนก่อนหน้า error (เช่น
    ถ้าส่งอีเมลไม่สำเร็จ ไฟล์ PDF/archive ที่ทำไปแล้วต้องไม่เสียหาย) — บันทึกทุก error ลง
    MeetingApprovalLog (action="delivery_failed"/"email_failed") ให้เห็นใน audit trail แทนที่จะ
    หายเงียบๆ (approval_status ยังคงเป็น "Approved" เสมอ เพราะการตัดสินใจของ Checker สมบูรณ์แล้ว —
    ปัญหาที่เหลือเป็นเรื่อง operational ไม่ใช่การตัดสินใจ approve ผิด)"""
    from db import SessionLocal

    db = SessionLocal()
    try:
        meeting = db.get(Meeting, meeting_id)
        if meeting is None or not meeting.final_docx_path:
            return

        final_docx_full = os.path.join(docx_generation.GENERATED_DOCS_DIR, meeting.final_docx_path)

        try:
            unprotected_pdf = pdf_generation.convert_docx_to_pdf(final_docx_full, meeting_id)
            password = secrets.token_urlsafe(9)
            protected_pdf = pdf_generation.protect_pdf(unprotected_pdf, password, meeting_id)
            meeting.final_pdf_path = os.path.basename(protected_pdf)
            meeting.final_pdf_password = password
            db.commit()
        except PdfGenerationError as e:
            log.error(f"[meeting {meeting_id}] แปลง/ใส่รหัสผ่าน PDF ไม่สำเร็จ: {e}")
            db.add(MeetingApprovalLog(
                meeting_id=meeting_id, action="delivery_failed", from_status="Approved",
                to_status="Approved", comment=f"PDF generation: {e}", user_id="system",
            ))
            db.commit()
            return  # ไม่มี PDF ก็ส่งอีเมล/archive ต่อไม่ได้ หยุดที่นี่

        try:
            tokens = magic_link.create_tokens_for_meeting(db, meeting_id, list(meeting.attendees))
            db.commit()
            meeting_date_thai = docx_generation.thai_date(meeting.meeting_date.isoformat())
            for token_row in tokens:
                try:
                    email_service.send_magic_link_email(
                        to_email=token_row.attendee_email,
                        meeting_number=meeting.meeting_number,
                        meeting_date_thai=meeting_date_thai,
                        magic_link_url=magic_link.build_magic_link_url(token_row.token),
                        pdf_password=meeting.final_pdf_password,
                    )
                except EmailSendError as e:
                    log.warning(f"[meeting {meeting_id}] {e}")
                    db.add(MeetingApprovalLog(
                        meeting_id=meeting_id, action="email_failed", from_status="Approved",
                        to_status="Approved", comment=f"{token_row.attendee_email}: {e}",
                        user_id="system",
                    ))
            db.commit()
        except Exception as e:  # ไม่คาดคิด (เช่น DB error ระหว่างสร้าง token) — log แล้วไปต่อที่ archive
            log.error(f"[meeting {meeting_id}] สร้าง/ส่ง Magic Link ล้มเหลวทั้งชุด: {e}")

        recordings_paths = []
        if meeting.audio_filename:
            recordings_paths.append(os.path.join(UPLOAD_DIR, meeting.audio_filename))
        archive.archive_documents(meeting_id, [final_docx_full, protected_pdf])
        archive.archive_recordings(meeting_id, recordings_paths)
    finally:
        db.close()


@app.post("/api/meetings/{meeting_id}/review")
def review_meeting_minutes(
    meeting_id: int,
    body: ReviewBody,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user: dict = Depends(require_role(["Com_Sec_Checker"])),
):
    """Checker อนุมัติ/ตีกลับเอกสาร (Module 5) — **เฉพาะ Com_Sec_Checker เท่านั้น** (ต่างจาก
    endpoint อื่นของ Module 2-4 ที่ Maker ทำได้ด้วย เพราะสิทธิ์กด Approve เป็นของ Checker โดยเฉพาะ
    ตาม implementation_plan.md's RBAC) ตีกลับ (reject) ต้องมี comment เสมอ (ตัดสินใจจาก `/grill-me`
    รอบ 3 — เก็บเหตุผลไว้ compliance) Approve แล้วจะ trigger background task แปลง PDF/ส่ง Magic
    Link/archive ทันที (ดู `_archive_and_notify_background`)"""
    meeting = db.get(Meeting, meeting_id)
    if meeting is None:
        raise HTTPException(status_code=404, detail="ไม่พบการประชุมนี้")
    if meeting.approval_status != "Pending_Review":
        raise HTTPException(
            status_code=400,
            detail=f"ต้องอยู่ในสถานะ Pending_Review เท่านั้นถึงจะ approve/reject ได้ "
            f"(ปัจจุบัน: {meeting.approval_status})",
        )

    if body.action == "reject":
        if not (body.comment or "").strip():
            raise HTTPException(status_code=400, detail="ต้องระบุเหตุผลที่ตีกลับ (comment) เสมอ")
        meeting.approval_status = "Needs_Revision"
        db.add(MeetingApprovalLog(
            meeting_id=meeting_id, action="reject", from_status="Pending_Review",
            to_status="Needs_Revision", comment=body.comment, user_id=user["user_id"],
        ))
        db.commit()
        return _meeting_to_dict(meeting)

    # action == "approve"
    if not meeting.final_docx_path:
        raise HTTPException(status_code=400, detail="ไม่พบเอกสารฉบับสมบูรณ์ — ไม่สามารถ Approve ได้")

    meeting.approval_status = "Approved"
    db.add(MeetingApprovalLog(
        meeting_id=meeting_id, action="approve", from_status="Pending_Review",
        to_status="Approved", comment=body.comment, user_id=user["user_id"],
    ))
    db.commit()
    background_tasks.add_task(_archive_and_notify_background, meeting_id)
    return {
        "message": "อนุมัติสำเร็จ กำลังสร้าง PDF/ส่ง Magic Link/archive เบื้องหลัง",
        **_meeting_to_dict(meeting),
    }


@app.get("/api/meetings/{meeting_id}/approval_log")
def get_meeting_approval_log(
    meeting_id: int,
    db: Session = Depends(get_db),
    user: dict = Depends(require_role(MEETING_MANAGE_ROLES)),
):
    meeting = db.get(Meeting, meeting_id)
    if meeting is None:
        raise HTTPException(status_code=404, detail="ไม่พบการประชุมนี้")
    return [
        {
            "action": log_entry.action,
            "from_status": log_entry.from_status,
            "to_status": log_entry.to_status,
            "comment": log_entry.comment,
            "user_id": log_entry.user_id,
            "created_at": log_entry.created_at.isoformat(),
        }
        for log_entry in meeting.approval_logs
    ]


@app.get("/api/magic_link/{token}")
def open_magic_link(token: str, db: Session = Depends(get_db)):
    """Public endpoint — Board_Member เปิดจากลิงก์ในอีเมลโดยตรง ไม่มี session login ปกติ (ไม่ผ่าน
    `verify_azure_ad_token`/`require_role` เหมือน endpoint อื่น) ความปลอดภัยมาจาก token เอง
    (256-bit random, single-use, หมดอายุตาม config.MAGIC_LINK_EXPIRY_HOURS — ดู magic_link.py)"""
    try:
        token_row = magic_link.verify_and_consume_token(db, token)
    except MagicLinkError as e:
        raise HTTPException(status_code=400, detail=str(e))

    meeting = db.get(Meeting, token_row.meeting_id)
    if meeting is None or not meeting.final_pdf_path:
        raise HTTPException(status_code=404, detail="ไม่พบเอกสารสำหรับลิงก์นี้")

    full_path = os.path.join(docx_generation.GENERATED_DOCS_DIR, meeting.final_pdf_path)
    if not os.path.exists(full_path):
        raise HTTPException(status_code=404, detail="ไม่พบไฟล์ PDF บนเซิร์ฟเวอร์")

    return FileResponse(
        full_path,
        media_type="application/pdf",
        filename=f"BOD_Minutes_{meeting.meeting_number.replace('/', '-')}.pdf",
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
