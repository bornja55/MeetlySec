import datetime
import json
import logging
import mimetypes
import os
import secrets
import shutil
from typing import Literal

import archive
import config
import docx_generation
import email_service
import magic_link
import pdf_generation
from audio_native import AudioNativeError, transcribe_meeting_audio
from auth import require_role, require_role_for_audio_stream, verify_azure_ad_token
from db import get_db, init_db
from docx_generation import DocxGenerationError
from email_service import EmailSendError
from fastapi import BackgroundTasks, Depends, FastAPI, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from magic_link import MagicLinkError
from minutes_generation import MinutesGenerationError, generate_minutes
from models import Meeting, MeetingAgendaItem, MeetingApprovalLog, MeetingAttendee
from pdf_generation import PdfGenerationError
from pydantic import BaseModel
from rag import RAGWorkerError, rag_pipeline, trigger_confidential_index_rebuild
from sqlalchemy.orm import Session

# ⚠️ พบบั๊กจริง (2026-08-05): `getLogger()` เฉยๆไม่พอ — Python root logger ดีฟอลต์ level เป็น
# WARNING ไม่มี handler ผูกไว้เลย ทำให้ log.info(...) ที่ใช้ทั่วทั้งไฟล์นี้ (upload/poll progress ใน
# audio_native.py ที่รับ callable นี้เข้าไป, "[TRANSCRIBE-DONE]" summary) ถูกตัดทิ้งเงียบๆมาตลอด
# ไม่เคยโชว์ในเทอร์มินอลเลยสักบรรทัด — ผู้ใช้เห็นแต่ "INFO: 127.0.0.1:... GET ..." ซึ่งเป็นของ
# uvicorn's access logger เอง (คนละ logger ที่ config มาให้แล้ว) ไม่ใช่ log ของแอปนี้ — แก้โดย
# ผูก StreamHandler + ตั้ง level=INFO ให้ logger นี้โดยตรง (ไม่พึ่ง logging.basicConfig() ที่อาจเป็น
# no-op เงียบๆถ้า uvicorn ผูก handler ให้ root loggerไปก่อนแล้วตามลำดับ import) ปิด propagate กัน
# log ซ้ำ 2 บรรทัดถ้า root logger มี handler อยู่แล้วเหมือนกัน
log = logging.getLogger("com_sec.main")
log.setLevel(logging.INFO)
if not log.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    log.addHandler(_handler)
    log.propagate = False

app = FastAPI(
    title="Company Secretary AI System - API",
    description="Backend for the Com Sec Meeting & RAG Assistant",
    version="1.0.0"
)

# สร้างตาราง DB ตอน import โมดูลนี้ (แทน startup event — โปรเจกต์นี้รันแบบ script ตรงๆผ่าน
# uvicorn main:app เดียว ไม่มีหลาย entrypoint ให้ต้องแยก event hook) ดู db.py's docstring
# เรื่อง Alembic migration ที่ยังไม่ทำ (MVP เท่านั้น)
init_db()


def _recover_stuck_processing_meetings() -> None:
    """⚠️ พบบั๊กจริง (2026-08-05): meeting ที่ `status="processing"` ตอน backend เพิ่งเริ่มโปรเซสใหม่
    **เป็นไปไม่ได้ที่จะยังประมวลผลอยู่จริง** เพราะ background task ที่ถืองานนั้นผูกกับ process เดิมที่
    ตายไปแล้ว (FastAPI `BackgroundTasks` ไม่ persist ข้าม restart — ทั้ง Gemini native audio ตอนนี้
    และ `audio_worker` เดิมมีช่องโหว่นี้เหมือนกัน) ผู้ใช้เจอเคสจริง: restart backend ระหว่างมี meeting
    กำลังประมวลผลอยู่ → ค้าง "processing" ตลอดกาล → `app.js`'s `actionCellHtml()` ไม่โชว์ปุ่ม
    Upload/Re-upload ให้เลย (โชว์เฉพาะสถานะ `draft`/`failed`) → อัปโหลดไฟล์ใหม่เข้า meeting นั้นไม่ได้
    อีกเลยจนกว่าจะแก้ DB เอง — ตรงกับ `/scrutinize` finding เดิมที่บันทึกไว้แล้วใน task.md ("ไม่มี
    timeout/watchdog ถ้า diarization/ASR ค้าง") เรียกครั้งเดียวตอน startup (หลัง `init_db()`) —
    auto-mark meeting ที่ค้างเป็น "failed" พร้อมข้อความอธิบายชัดเจน ให้ปุ่ม Re-upload กลับมาทันที
    โดยไม่ต้องแก้ DB เอง — ไม่ใช่ watchdog เต็มรูปแบบ (ยังไม่จับกรณี backend ไม่ได้ restart แต่
    background task ค้างจริงๆ เช่น Gemini ไม่ตอบเลย — ยังต้องพึ่ง GEMINI_TRANSCRIPTION_TIMEOUT_MS
    เดิมสำหรับกรณีนั้น) แค่ปิดช่องโหว่เฉพาะกรณี "ค้างเพราะ restart" ที่เจอจริงรอบนี้

    ⚠️ ขยายเพิ่ม (2026-08-05, พบระหว่าง /scrutinize รอบนี้เอง — ยังไม่มีผู้ใช้รายงานจริง แต่ตรรกะ
    เดียวกันทุกประการ): `status="uploaded"` ก็ค้างตลอดกาลได้ด้วยเหตุผลเดียวกัน — ถ้า backend
    restart/reload ในช่วงสั้นๆ ระหว่าง `upload_meeting_audio()` commit สถานะ "uploaded" กับตอนที่
    `BackgroundTasks` เพิ่ง dispatch งานจริง (Starlette รันหลังส่ง response แล้ว) ตัว background
    task จะไม่มีวันเริ่มทำงานเลย และ `app.js` ก็ไม่มีปุ่ม re-upload ให้ตอน "uploaded" เช่นกัน
    (`meeting-detail.html`'s reuploadBtn โชว์เฉพาะ transcribed/failed — ดู app.js:1017) ทำให้ค้างที่
    placeholder "อัปโหลดไฟล์แล้ว รอเริ่มประมวลผล..." ตลอดกาลเหมือนกัน ตรรกะการ recover เหมือนกันทุก
    ประการกับ "processing": ตอน backend เพิ่ง start ใหม่ เป็นไปไม่ได้ที่ background task จะยังไม่ถูก
    dispatch จริงๆ (ไม่มี request ใดๆเข้ามาได้ก่อนบรรทัดนี้รันเสร็จ) จึงปลอดภัยที่จะรวมไว้ด้วยกัน"""
    from db import SessionLocal

    db = SessionLocal()
    try:
        stuck = (
            db.query(Meeting)
            .filter(Meeting.status.in_(["processing", "uploaded"]))
            .all()
        )
        for meeting in stuck:
            meeting.status = "failed"
            meeting.processing_error = (
                "ประมวลผลถูกขัดจังหวะเพราะ backend restart กลางทาง — background task ที่ถืองานนี้"
                "ถูกฆ่าไปพร้อม process เดิม ไม่เกี่ยวกับไฟล์เสียงเสียหรือ Gemini error ใดๆ "
                "กด Re-upload ได้เลย"
            )
        if stuck:
            db.commit()
            log.warning(
                f"พบ {len(stuck)} meeting ค้างสถานะ 'processing'/'uploaded' จาก backend รอบก่อน "
                f"(ids: {[m.id for m in stuck]}) — ตั้งเป็น 'failed' อัตโนมัติแล้ว ให้ผู้ใช้ "
                f"re-upload ใหม่ได้"
            )
    finally:
        db.close()


_recover_stuck_processing_meetings()

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
    # session 3.37 — เฉพาะ /api/rag/query_confidential เท่านั้นที่ใช้ (ทั่วไปไม่มี concept การประชุม)
    # ไม่ระบุ/None = ค้นหาทุกเอกสารลับเหมือนเดิม (backward compatible กับ frontend เก่าที่ยังไม่ส่ง)
    meeting_id: str | int | None = None


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
            meeting_id=body.meeting_id,
        )
    except RAGWorkerError as e:
        raise HTTPException(status_code=503, detail=str(e))
    return {"query": body.query, "user": user, **result}

# ────────────────────────────────────────────────────────────────────────────────────────
# Module 2: Meeting entity + upload — สร้าง "การประชุม" ก่อนอัปโหลดไฟล์เสียงเสมอ (ตัดสินใจ
# `/grill-me` รอบ 3, ดู task.md Module 2) ประมวลผลเสียงเรียก Gemini native audio ตรงจากโปรเซสนี้เอง
# ผ่าน `audio_native.transcribe_meeting_audio()` (เดิมเรียก `audio_worker` โปรเซสแยกผ่าน `audio.py`
# — แทนที่แล้วตามการตัดสินใจ `/grill-me` 2026-08-04, ดู `audio_native.py`'s docstring สำหรับเหตุผล
# สถาปัตยกรรมเต็ม + task.md บรรทัด 164-191) ผ่าน FastAPI BackgroundTasks เพื่อให้ HTTP response ของ
# /upload ไม่ต้องรอจนประมวลผลเสร็จ (อาจนานหลายสิบวินาทีถึงหลายนาทีสำหรับประชุมยาว) — client poll
# สถานะผ่าน GET /api/meetings/{id} แทน
# ────────────────────────────────────────────────────────────────────────────────────────


class AttendeeIn(BaseModel):
    name: str
    position: str | None = None
    # Module 4-5 (2026-08-03): กรอกเองต่อการประชุม — attendee ที่มี email จะได้รับ Magic Link หลัง
    # Checker Approve (ดู models.py's MeetingAttendee.email docstring สำหรับที่มาการตัดสินใจ)
    email: str | None = None


class AgendaItemIn(BaseModel):
    # เลขวาระที่โชว์จริงในเอกสาร (2026-08-07, ผู้ใช้ขอ — ดู models.py's MeetingAgendaItem.label
    # docstring) ปล่อยว่าง/ไม่ส่งมา = ให้ backend เติม "วาระที่ {ลำดับ}" อัตโนมัติ (ดูจุดที่ใช้ค่านี้ใน
    # create_meeting()/update_meeting_agenda_items() ด้านล่าง) พิมพ์เองได้เต็มที่ไม่จำกัดรูปแบบ (เช่น
    # "วาระที่ 3.1", "เรื่องที่ 5") — ไม่ validate รูปแบบใดๆ เป็น free text ล้วน
    label: str | None = None
    description: str


class MeetingCreateBody(BaseModel):
    meeting_number: str  # เช่น "15/2569" ตรงกับชื่อไฟล์ template
    meeting_date: datetime.date
    attendees: list[AttendeeIn] = []
    agenda_items: list[AgendaItemIn] = []
    # Multi-template (2026-08-03) — ชื่อ key ใน docx_generation.TEMPLATE_REGISTRY เลือกตอนสร้าง
    # การประชุม (ดู GET /api/templates ด้านล่างสำหรับรายการที่ frontend ใช้ populate dropdown)
    template_name: str = docx_generation.DEFAULT_TEMPLATE_NAME


def _build_agenda_items(items_in: list[AgendaItemIn]) -> list[MeetingAgendaItem]:
    """แปลง `AgendaItemIn` (จาก request body) เป็น `MeetingAgendaItem` ORM object พร้อม default
    `label` ถ้าผู้ใช้ไม่กรอก — ใช้ร่วมกันทั้ง `create_meeting()`/`update_meeting_agenda_items()` กัน
    ตรรกะ default diverge กัน (เคยเจอปัญหานี้มาแล้วกับ `_is_speaker_mapping_complete()`)"""
    result = []
    for i, item in enumerate(items_in):
        label = item.label.strip() if item.label and item.label.strip() else f"วาระที่ {i + 1}"
        result.append(MeetingAgendaItem(order=i, label=label, description=item.description))
    return result


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
        # ชื่อโมเดล Gemini ที่ transcribe สำเร็จจริงรอบล่าสุด (primary "gemini-3.6-flash" หรือ
        # fallback "gemini-3.5-flash") — None ถ้ายังไม่เคยประมวลผลสำเร็จ ดู models.py's
        # transcription_model_used docstring (2026-08-05, ผู้ใช้ขอให้บันทึก/แสดงทุกที่)
        "transcription_model_used": meeting.transcription_model_used,
        "attendees": [
            {"name": a.name, "position": a.position, "email": a.email} for a in meeting.attendees
        ],
        "agenda_items": [
            {"label": a.label, "description": a.description} for a in meeting.agenda_items
        ],
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
        agenda_items=_build_agenda_items(body.agenda_items),
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


class AttendeesBody(BaseModel):
    attendees: list[AttendeeIn] = []


class AgendaItemsBody(BaseModel):
    agenda_items: list[AgendaItemIn] = []


def _reject_if_approved(meeting: Meeting, what: str) -> None:
    """เดิม `attendees`/`agenda_items` ตั้งได้แค่ตอน `POST /api/meetings` (สร้างประชุม) เท่านั้น ไม่มี
    ทางแก้ย้อนหลังเลย (ผู้ใช้เจอจริง 2026-08-07: สร้างประชุม "test" โดยลืมกรอกทั้ง 2 อย่าง แล้ว
    Generate Minutes reject ด้วย "ไม่มีวาระการประชุมเลย" กู้ไม่ได้ต้องสร้างใหม่ทั้งใบ) — เพิ่ม endpoint
    แก้ไขย้อนหลัง 2 อันด้านล่าง (เขียนทับทั้ง array เสมอ ตรงกับ pattern
    `update_transcript_segments`/`set_speaker_mapping` ทุกประการ) **กันแก้หลัง `approval_status`
    เป็น "Approved" แล้วเท่านั้น** (สถานะสุดท้ายของ compliance flow นี้ — แก้ผู้เข้าร่วม/วาระของ
    การประชุมที่บอร์ดอนุมัติเอกสารไปแล้วจะทำให้ข้อมูลไม่ตรงกับสิ่งที่อนุมัติจริงแบบเงียบๆ) ไม่ได้บล็อก
    สถานะอื่นเลย (Draft/Pending_Review/Needs_Revision แก้ได้ปกติ) — ⚠️ หมายเหตุ: ถ้าแก้หลังจาก
    Generate Minutes ไปแล้ว (แต่ยังไม่ Approve) `minutes_json` เดิมจะไม่ sync กับ agenda ใหม่โดย
    อัตโนมัติ ต้องกด Generate Minutes ซ้ำเอง — ตรงกับปรัชญา "เขียนทับ ไม่มี versioning" ของทั้งระบบ"""
    if meeting.approval_status == "Approved":
        raise HTTPException(
            status_code=400,
            detail=f"การประชุมนี้อนุมัติเอกสารไปแล้ว (Approved) แก้ไข{what}ย้อนหลังไม่ได้อีก",
        )


@app.put("/api/meetings/{meeting_id}/attendees")
def update_meeting_attendees(
    meeting_id: int,
    body: AttendeesBody,
    db: Session = Depends(get_db),
    user: dict = Depends(require_role(MEETING_MANAGE_ROLES)),
):
    """แก้ไขรายชื่อผู้เข้าร่วมย้อนหลังได้ (2026-08-07, ผู้ใช้ขอ) — เขียนทับทั้ง array เสมอ (ให้ caller
    ส่ง attendee ทั้งหมดที่ต้องการมาทุกครั้ง ตรงกับ pattern `set_speaker_mapping` ด้านล่าง) ใช้
    `AttendeeIn` schema เดียวกับตอนสร้างประชุม (`MeetingCreateBody.attendees`) — cascade
    `delete-orphan` ใน models.py จัดการลบแถวเก่า/เพิ่มแถวใหม่ให้เองตอน reassign `meeting.attendees`"""
    meeting = db.get(Meeting, meeting_id)
    if meeting is None:
        raise HTTPException(status_code=404, detail="ไม่พบการประชุมนี้")
    _reject_if_approved(meeting, "รายชื่อผู้เข้าร่วม")

    meeting.attendees = [
        MeetingAttendee(name=a.name, position=a.position, email=a.email) for a in body.attendees
    ]
    db.commit()
    return _meeting_to_dict(meeting)


@app.put("/api/meetings/{meeting_id}/agenda_items")
def update_meeting_agenda_items(
    meeting_id: int,
    body: AgendaItemsBody,
    db: Session = Depends(get_db),
    user: dict = Depends(require_role(MEETING_MANAGE_ROLES)),
):
    """แก้ไขวาระการประชุมย้อนหลังได้ (2026-08-07, ผู้ใช้ขอ) — เขียนทับทั้ง array เสมอเหมือน
    `update_meeting_attendees` ด้านบน `order` คำนวณจากลำดับ index ใน list ที่ส่งมาเสมอ (ตรงกับตอน
    สร้างประชุมใน `create_meeting`) ไม่รับ `order` จาก client ตรงๆ กันส่งลำดับไม่ต่อเนื่อง/ซ้ำมาเอง —
    `label` รับตรงจาก client ได้ (ตรงกับ `AgendaItemIn`, ดู `_build_agenda_items()`) เพราะเป็น free
    text ที่ผู้ใช้ตั้งใจกำหนดเอง (เช่น "วาระที่ 3.1") ไม่ใช่ค่าที่ derive จากลำดับเหมือน `order`"""
    meeting = db.get(Meeting, meeting_id)
    if meeting is None:
        raise HTTPException(status_code=404, detail="ไม่พบการประชุมนี้")
    _reject_if_approved(meeting, "วาระการประชุม")

    meeting.agenda_items = _build_agenda_items(body.agenda_items)
    db.commit()
    return _meeting_to_dict(meeting)


def _process_meeting_audio_background(
    meeting_id: int, filename: str, model_override: str | None = None,
) -> None:
    """รันใน FastAPI BackgroundTask — เปิด DB session ใหม่ของตัวเอง (session ของ request เดิม
    ปิดไปแล้วตอน response ส่งกลับ ใช้ต่อไม่ได้) เรียก Gemini native audio ตรงจากโปรเซสนี้เอง (ไม่ใช่
    audio_worker โปรเซสแยกอีกต่อไป — ดู audio_native.py's docstring) แบบ synchronous (บล็อกอยู่ใน
    background task เท่านั้น ไม่บล็อก HTTP response ที่ตอบ client ไปแล้ว) — ไม่มี concept "worker
    กำลังยุ่ง" อีกแล้ว (Gemini เป็น cloud call รองรับ concurrent request ได้ ไม่ผูกกับทรัพยากร GPU
    เครื่องเดียวเหมือน audio_worker เดิม) เหลือ except เดียว (AudioNativeError) แทน 2 เดิม

    model_override (2026-08-05): ส่งต่อจาก `upload_meeting_audio()`'s form field `model` (ผู้ใช้
    เลือกเองผ่าน dropdown บน frontend) ตรงไปยัง `transcribe_meeting_audio()` เฉยๆ — validate ค่านี้
    ไปแล้วตั้งแต่ endpoint ก่อนหน้า (เทียบกับ `config.GEMINI_TRANSCRIPTION_MODEL_CHOICES`) ที่นี่แค่
    ส่งผ่าน"""
    from db import SessionLocal

    db = SessionLocal()
    try:
        meeting = db.get(Meeting, meeting_id)
        if meeting is None:
            return  # ถูกลบไปแล้วระหว่างรอคิว — ไม่มีอะไรให้อัปเดต

        meeting.status = "processing"
        db.commit()

        audio_path = os.path.join(UPLOAD_DIR, filename)
        try:
            # checkpoint_key=str(meeting_id) (2026-08-05, session 3.32) — ให้ retry/re-upload ไฟล์
            # เดิมไปยัง meeting เดิมข้าม chunk ที่ transcribe สำเร็จไปแล้วได้ ไม่ต้องเรียก Gemini ซ้ำ
            # ทั้งไฟล์ถ้า chunk กลางไฟล์ fail (เจอจริง: 503 ชนพอดีกับ backend restart กลาง 11-chunk job
            # — ดู handoff.md session 3.31/3.32) ปลอดภัยเพราะ audio_chunking.load_checkpoint() เช็ค
            # plan (offset/duration ต่อ chunk) ตรงกับไฟล์เสียงปัจจุบันก่อนใช้เสมอ — ไฟล์เสียงคนละไฟล์
            # ทับของเดิม (re-upload ไฟล์ใหม่) จะไม่ตรง plan เดิม ถูกทิ้งอัตโนมัติ ไม่เสี่ยง merge ผิดชุด
            result = transcribe_meeting_audio(
                audio_path, log=log.info, model_override=model_override,
                checkpoint_key=str(meeting_id),
            )
        except AudioNativeError as e:
            meeting.status = "failed"
            meeting.processing_error = str(e)
            db.commit()
            return

        meeting.status = "transcribed"
        meeting.transcript_segments_json = json.dumps(result.get("transcript_segments"))
        # บันทึกไว้ทุกที่ (ผู้ใช้ขอ 2026-08-05 — เดิมรู้ได้แค่จาก backend terminal log ของ
        # run_with_fallback เท่านั้น ไม่มีที่เก็บถาวรต่อ meeting เลย) ดู models.py's
        # transcription_model_used docstring — log บรรทัดสรุปชัดเจนแยกจาก log ระดับ upload/poll ของ
        # audio_native.py เอง (หาง่ายกว่าด้วย grep "[TRANSCRIBE-DONE]")
        model_used = result.get("model_used")
        meeting.transcription_model_used = model_used
        db.commit()
        log.info(
            f"[TRANSCRIBE-DONE] meeting {meeting_id} transcribed ด้วยโมเดล={model_used} "
            f"ใน {result.get('elapsed_seconds'):.1f}s ({len(result.get('transcript_segments') or [])} "
            f"segments)"
        )
    finally:
        db.close()


@app.get("/api/transcription_models")
def list_transcription_models(user: dict = Depends(verify_azure_ad_token)):
    """เลือกโมเดล Gemini เองตอน upload/re-upload (2026-08-05, ผู้ใช้ขอ — ดู config.py's
    `GEMINI_TRANSCRIPTION_MODEL_CHOICES` สำหรับที่มา) คืนรายการให้ frontend populate dropdown —
    mirror pattern เดียวกับ `GET /api/templates`/`docx_generation.list_templates()` ทุกประการ
    (metadata ล้วนๆ ไม่มีข้อมูลลับ อนุญาตทุก authenticated user เรียกได้) `default` คือโมเดล primary
    ปัจจุบันจาก `config.GEMINI_MODEL_TRANSCRIPTION` — frontend ใช้ pre-select ตัวนี้เป็นค่าเริ่มต้น"""
    return {
        "models": [
            {"value": value, "label": label}
            for value, label in config.GEMINI_TRANSCRIPTION_MODEL_CHOICES
        ],
        "default": config.GEMINI_MODEL_TRANSCRIPTION,
    }


@app.post("/api/meetings/{meeting_id}/upload")
def upload_meeting_audio(
    meeting_id: int,
    background_tasks: BackgroundTasks,
    file: UploadFile,
    model: str | None = Form(None),
    db: Session = Depends(get_db),
    user: dict = Depends(require_role(MEETING_MANAGE_ROLES)),
):
    meeting = db.get(Meeting, meeting_id)
    if meeting is None:
        raise HTTPException(status_code=404, detail="ไม่พบการประชุมนี้")

    # เลือกโมเดลเอง (2026-08-05, ผู้ใช้ขอ — ดู list_transcription_models() ด้านบน) — validate ค่า
    # ที่ frontend ส่งมาเทียบกับ whitelist จริงเสมอ (ไม่เชื่อ dropdown ฝั่ง client เฉยๆ กัน request
    # ปลอมส่งชื่อโมเดล/ค่าอื่นที่ไม่ใช่ตัวเลือกจริงเข้ามาตรงๆ) ค่าว่าง/ไม่ส่งมา = ใช้ fallback chain
    # ปกติจาก config.py เหมือนเดิมทุกประการ (ไม่ระบุ = ไม่เปลี่ยนพฤติกรรมเดิม)
    model_override = model or None
    if model_override is not None:
        valid_models = {value for value, _label in config.GEMINI_TRANSCRIPTION_MODEL_CHOICES}
        if model_override not in valid_models:
            raise HTTPException(status_code=400, detail=f"โมเดล '{model_override}' ไม่อยู่ในรายการที่เลือกได้")

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

    background_tasks.add_task(
        _process_meeting_audio_background, meeting_id, safe_filename, model_override,
    )

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
    # โครงเดียวกับที่ audio_native._adapt_segments() คืนมา ({start, end, speaker, text}) — เดิมมาจาก
    # audio_worker/asr.py::transcribe_segments ก่อนเปลี่ยนมาเรียก Gemini native audio (2026-08-05,
    # ดู audio_native.py) — schema key เดิมไม่เปลี่ยนเลยตามการตัดสินใจ /grill-me ข้อ 3 — ฟอร์มแก้ไข
    # transcript (ไม่บังคับ, ตามแผน Module 2)
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

    # ส่ง label ไปด้วย (2026-08-07 — ดู models.py's MeetingAgendaItem.label) ให้ merge กลับเข้า
    # minutes_json ได้ตรงๆ ไม่ต้อง query DB ซ้ำตอน render docx ทีหลัง — label ไม่ส่งเข้า Gemini prompt
    # เลย (ดู minutes_generation.py's build_minutes_user_prompt: ใช้แค่ description) เพราะเป็นเรื่อง
    # การแสดงผลล้วนๆ ไม่เกี่ยวกับเนื้อหาที่ต้องสรุป
    agenda_items_in = [
        {"label": a.label or f"วาระที่ {i + 1}", "description": a.description}
        for i, a in enumerate(meeting.agenda_items)
    ]

    try:
        minutes = generate_minutes(
            company_name=config.COMPANY_NAME,
            meeting_number=meeting.meeting_number,
            meeting_date_iso=meeting.meeting_date.isoformat(),
            attendees=[{"name": a.name, "position": a.position} for a in meeting.attendees],
            agenda_items=agenda_items_in,
            transcript_segments=transcript_segments,
            speaker_mapping=speaker_mapping,
        )
    except MinutesGenerationError as e:
        # ปฏิเสธด้วย 400 ถ้าไม่มีวาระ (ผู้ใช้แก้ได้เอง — เพิ่มวาระ) ที่เหลือ (Gemini ล้มเหลว/schema
        # ไม่ตรง/API key ไม่มี) เป็น 503 (ปัญหาระบบ ไม่ใช่ input ผิดของผู้ใช้) — ดู
        # backend/rag.py's RAGWorkerError สำหรับ pattern การแยก error code เดียวกัน
        status_code = 400 if not agenda_items_in else 503
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

        # ── ต่อสาย Approve → Confidential RAG index (2026-08-07) ────────────────────────
        # ตัดสินใจจากผู้ใช้ผ่าน AskUserQuestion: "Auto: index อัตโนมัติทันทีที่ Approve" — copy
        # final_docx_full เข้า confidential_corpus/ แล้วสั่ง worker rebuild ดัชนีทั้งก้อนทันที (ไม่
        # incremental — ผู้ใช้ยอมรับ tradeoff นี้แล้วเพราะ corpus เล็ก/ไม่บ่อย) แยก try/except ของ
        # ตัวเอง เหมือนขั้นตอนอื่นทั้งหมดในฟังก์ชันนี้ — index ไม่สำเร็จต้องไม่ทำให้ approve
        # (ที่สมบูรณ์ไปแล้ว: PDF+email+archive) ถูกมองว่าล้มเหลว แค่ log ไว้ใน audit trail
        try:
            os.makedirs(config.RAG_WORKER_CONFIDENTIAL_CORPUS_DIR, exist_ok=True)
            corpus_dest = os.path.join(
                config.RAG_WORKER_CONFIDENTIAL_CORPUS_DIR, f"meeting_{meeting_id}_final.docx"
            )
            shutil.copy2(final_docx_full, corpus_dest)
            rebuild_result = trigger_confidential_index_rebuild()
            if rebuild_result.get("success"):
                log.info(f"[meeting {meeting_id}] {rebuild_result.get('message')}")
            else:
                log.warning(
                    f"[meeting {meeting_id}] rebuild confidential RAG index ไม่สำเร็จ: "
                    f"{rebuild_result.get('message')}"
                )
                db.add(MeetingApprovalLog(
                    meeting_id=meeting_id, action="rag_index_failed", from_status="Approved",
                    to_status="Approved", comment=str(rebuild_result.get("message", ""))[:500],
                    user_id="system",
                ))
                db.commit()
        except OSError as e:
            log.warning(f"[meeting {meeting_id}] copy เอกสารเข้า confidential_corpus ไม่สำเร็จ: {e}")
            db.add(MeetingApprovalLog(
                meeting_id=meeting_id, action="rag_index_failed", from_status="Approved",
                to_status="Approved", comment=str(e)[:500], user_id="system",
            ))
            db.commit()
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
    # reload=False (2026-08-05, session 3.32 — เปลี่ยนจาก True ถาวรตามที่ผู้ใช้ยืนยัน) เดิมเป็น
    # CRITICAL ที่พบตั้งแต่ session 3.20 (auto-reload ฆ่า background task กลางคันถ้ามีไฟล์ .py ใน
    # backend/ ถูกแก้ระหว่าง transcription กำลังรันอยู่) ตอนนั้นผู้ใช้เลือกยอมรับความเสี่ยงไว้ก่อนเพื่อ
    # ความสะดวกตอน dev — จนมาเจอจริงใน session 3.31/3.32: 11-chunk transcription job ตายกลางทางที่
    # chunk 7 (503 ชนพอดีกับ process restart) เสียเควตา chunk 1-6 ไปฟรี (ตอนนั้นยังไม่มี
    # checkpoint/resume) ยืนยันว่าความเสี่ยงนี้ไม่ใช่แค่ทฤษฎี ตอนนี้ต้อง restart backend เอง
    # (Ctrl+C แล้วรันคำสั่งนี้ใหม่) ทุกครั้งที่แก้โค้ด .py — แลกความสะดวกตอน dev กับความน่าเชื่อถือของ
    # job ที่กินเวลานาน (transcription ไฟล์ยาวใช้เวลาหลายนาทีถึงหลักชั่วโมง)
    #
    # host="0.0.0.0" (2026-08-07, ผู้ใช้ขอ — ComSec ตัวจริงเข้า http://192.168.214.98:8000/dashboard/
    # จากเครื่องอื่นในวง LAN ไม่ได้เลยตอน bind "127.0.0.1" เพราะ loopback ไม่ฟัง LAN NIC เลยไม่ว่า IP
    # จะถูกแค่ไหน) ⚠️ เพิ่ม attack surface จริง: (1) /dashboard เป็น StaticFiles mount ไม่มี auth คุม
    # เลย (auth เช็คแค่ตอนเรียก /api/* ผ่าน Depends(...)) ใครก็ตามในวง LAN/WiFi เดียวกันเปิดหน้าเว็บได้
    # แม้ยังต้อง login ผ่าน Azure AD ถึงจะดึงข้อมูลจริงได้ (2) ยังเป็น HTTP เปล่า ไม่มี TLS — token/
    # credential วิ่ง plaintext ในเครือข่ายนั้น ผู้ใช้ยืนยันรับความเสี่ยงนี้แล้ว (2026-08-07, ผ่าน
    # AskUserQuestion) เพื่อให้ ComSec ตัวจริงช่วยตรวจสอบได้ — ควรใช้แค่บนเครือข่ายบริษัทที่เชื่อถือได้
    # เท่านั้น ไม่ใช่ WiFi สาธารณะ ถ้าจะใช้ต่อเนื่องระยะยาวควรพิจารณา TLS/VPN แทนการเปิด 0.0.0.0 ตรงๆ
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
