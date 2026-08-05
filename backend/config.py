"""
config.py — โหลด `.env` + env var config กลางของ backend (ใหม่ทั้งไฟล์, 2026-08-03, Module 3)

พบบั๊กจริงระหว่างเขียน Module 3 (mantra 4, cross-reference กับ requirements.txt): `python-dotenv`
อยู่ใน requirements.txt มาตั้งแต่ Module 1 (ดู requirements.txt) แต่ไม่มีจุดไหนในโค้ด backend เรียก
`load_dotenv()` เลยสักครั้ง — `backend/.env` ที่มีอยู่จริงบนเครื่องผู้ใช้ (สร้างไว้ตั้งแต่ 2026-08-01,
มี `GOOGLE_API_KEY` อยู่แล้ว) จึงไม่เคยถูกโหลดเข้า `os.environ` จริงๆ เลย — ไม่กระทบอะไรมาก่อนหน้านี้
เพราะยังไม่มีโค้ดจุดไหนของ backend อ่าน env var ที่มาจาก `.env` (Azure AD/`auth.py` ยัง mock อยู่)
Module 3 นี้เป็นจุดแรกที่ backend ต้องอ่าน `GOOGLE_API_KEY` จริง — เพิ่ม `load_dotenv()` ที่นี่
(ตำแหน่งเดียว รวมศูนย์ ตาม pattern เดียวกับ `rag_worker/worker_config.py`'s `_load_dotenv`) แล้วให้
ทุกโมดูลที่ต้องใช้ env var import โมดูลนี้แทนอ่าน `os.environ` ตรงๆ
"""
import os

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

COMPANY_NAME = os.environ.get("COMPANY_NAME", "ออริจิ้น โกลบอล เอ็มไพร์")

GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY", "")

# ── Module 3: Minutes Generation ────────────────────────────────────────────────────────
# โมเดลแยกจาก rag_worker's GEMINI_MODEL_CHAT/DRAFT (คนละ .env/คนละโปรเซส) แต่ตั้งใจใช้ค่าเริ่มต้น
# เดียวกับ GEMINI_MODEL_DRAFT ของ rag_worker (งานแบบ one-shot generation เหมือนกัน ไม่ใช่ chat)
GEMINI_MODEL_MINUTES = os.environ.get("GEMINI_MODEL_MINUTES", "gemini-3.5-flash")


def _parse_model_chain(env_value: str) -> list[str]:
    """เหมือน rag_worker/worker_config.py's _parse_model_chain — comma-separated fallback chain"""
    return [m.strip() for m in env_value.split(",") if m.strip()]


GEMINI_MODEL_MINUTES_FALLBACK = _parse_model_chain(
    os.environ.get("GEMINI_MODEL_MINUTES_FALLBACK", "")
)

# ยังไม่มีตัวเลข latency จริงของ Module 3 (ต้อง live test บนเครื่องผู้ใช้ก่อน — ดู handoff.md) ตั้ง
# ค่าดีฟอลต์เท่ากับ rag_worker's GEMINI_REQUEST_TIMEOUT_MS ไปก่อน (5 นาทีต่อการเรียก 1 ครั้ง) ปรับ
# ขึ้นได้ผ่าน env ถ้าพบว่าสั้นเกินไปเหมือนที่เคยเจอกับ Module 1 (ดู backend/rag.py's หมายเหตุ
# RAG_WORKER_TIMEOUT_SECONDS สำหรับบั๊ก class เดียวกันที่เคยเกิด)
GEMINI_MINUTES_TIMEOUT_MS = int(os.environ.get("GEMINI_MINUTES_TIMEOUT_MS", str(5 * 60 * 1000)))

# ── Experiment (2026-08-04): Gemini native audio transcription+diarization ─────────────
# ทดลองแทน pipeline pyannote+typhoon-asr แยกส่วนเดิม (audio_worker) ด้วยการส่งไฟล์เสียงเข้า Gemini
# ตรงๆ ให้ทำ diarization+transcription จบในโมเดลเดียว — ต้นเหตุคือผู้ใช้ลองโยนไฟล์เดียวกันเข้า
# NotebookLM (ใช้ Gemini audio understanding ข้างใน) ได้ผล diarization แม่นกว่า pipeline เราเองมาก
# (ดู handoff.md 3.13, `backend/audio_transcription_experiment.py`) — โมเดลแยกจาก
# GEMINI_MODEL_MINUTES เพราะงาน audio understanding อาจต้องการรุ่นที่ต่างกัน (ทดลองปรับแยกได้)
#
# ดีฟอลต์ primary=gemini-3.6-flash (ไม่ใช่ 3.5-flash เหมือน GEMINI_MODEL_MINUTES) — ตัดสินใจจากการ
# ทดลองจริงบนไฟล์ประชุมเต็ม 55 นาที (2026-08-04): gemini-3.5-flash โดน free-tier rate limit หนักมาก
# (ผู้ใช้ retry เกือบ 1 ชม.ถึงสำเร็จ) ส่วน gemini-3.6-flash รันผ่านรอบเดียวใน 154s แถมพบบั๊กจริงใน
# ผลลัพธ์ 3.5-flash ด้วย: speaker_label ไม่สม่ำเสมอ ("Speaker  3"/"Speaker  4" เว้นวรรคซ้ำ ปนกับ
# "Speaker 3"/"Speaker 4" เว้นวรรคเดียวที่ไม่โผล่มาเลย) ทำให้นับ speaker คลาดเคลื่อน (428 segment
# นับได้ 6 speaker ทั้งที่จริงมีแค่ ~4-5 คน) — ยืนยันว่า 3.6-flash เสถียรกว่าทั้ง rate-limit และความ
# สม่ำเสมอของ label ให้ fallback ไป 3.5-flash เฉพาะตอน 3.6-flash เต็มโควต้าเท่านั้น
GEMINI_MODEL_TRANSCRIPTION = os.environ.get("GEMINI_MODEL_TRANSCRIPTION", "gemini-3.6-flash")
GEMINI_MODEL_TRANSCRIPTION_FALLBACK = _parse_model_chain(
    os.environ.get("GEMINI_MODEL_TRANSCRIPTION_FALLBACK", "gemini-3.5-flash")
)
# ไฟล์เสียงยาวกว่า text มาก ต้อง timeout นานกว่า GEMINI_MINUTES_TIMEOUT_MS — ตั้ง 15 นาทีไปก่อน
# (ยังไม่มีตัวเลข latency จริง ต้องวัดจากการทดลองจริงก่อน)
GEMINI_TRANSCRIPTION_TIMEOUT_MS = int(
    os.environ.get("GEMINI_TRANSCRIPTION_TIMEOUT_MS", str(15 * 60 * 1000))
)

# ── Module 4: Word Template Mapping ─────────────────────────────────────────────────────
# ที่อยู่บริษัทที่จะโชว์ในเอกสาร .docx ที่ AI ร่าง (ดู docx_generation.py) — ไม่มีใน minutes_json
# (Module 3's schema ไม่เก็บ) ปล่อยว่างได้ถ้าไม่ตั้ง (Maker เติมเองใน Word ทีหลัง ไม่ error)
COMPANY_ADDRESS = os.environ.get("COMPANY_ADDRESS", "")

# ── Module 5: Finalization & Secure Delivery ────────────────────────────────────────────
# SMTP ธรรมดา (`smtplib` มาตรฐาน ไม่เพิ่ม dependency ใหม่) — เลือกแทน Microsoft Graph API เพราะ
# Azure AD ยังไม่เชื่อมต่อจริงในระบบนี้เลย (ดู auth.py, ยัง mock token อยู่ทั้งหมด) จะสลับไปใช้ Graph
# API ได้ในอนาคตถ้าเชื่อม Azure AD จริงแล้ว — ไม่ได้ hardcode ไว้ตายตัว
SMTP_HOST = os.environ.get("SMTP_HOST", "")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USERNAME = os.environ.get("SMTP_USERNAME", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
SMTP_USE_TLS = os.environ.get("SMTP_USE_TLS", "true").strip().lower() != "false"
SMTP_FROM_EMAIL = os.environ.get("SMTP_FROM_EMAIL", SMTP_USERNAME)

# Magic Link (ดู magic_link.py) — ตัดสินใจจาก `/scrutinize`: ต้องมี expiration + single-use ตั้งแต่
# ตอนออกแบบ (ดู task.md Module 4-5) MAGIC_LINK_BASE_URL ต้องชี้ไปที่เครื่องที่ Board_Member เข้าถึงได้
# จริง (ไม่ใช่ 127.0.0.1 ถ้าต้องเปิดจากเครื่องอื่น — ผู้ใช้ต้องตั้งเองตอน deploy จริง)
MAGIC_LINK_BASE_URL = os.environ.get("MAGIC_LINK_BASE_URL", "http://127.0.0.1:8000")
MAGIC_LINK_EXPIRY_HOURS = int(os.environ.get("MAGIC_LINK_EXPIRY_HOURS", "168"))  # ดีฟอลต์ 7 วัน

# Archive ปลายทางแยก 2 ประเภท (ตัดสินใจจาก `/grill-me` รอบ 2, ดู implementation_plan.md/task.md
# Module 4-5) — ค่าว่างหมายถึง "ยังไม่ตั้งค่า" ข้ามการ archive แต่ไม่ crash ทั้ง flow approve (log
# warning เฉยๆ เพราะการ archive ไม่ใช่เงื่อนไขที่ทำให้ approve ล้มเหลว — ผู้ใช้ต้องตั้ง UNC path จริง
# เองก่อนขึ้นใช้งานจริง ตอนนี้ยังไม่มีค่าให้ทดสอบ)
ARCHIVE_DOCUMENTS_DESTINATION = os.environ.get("ARCHIVE_DOCUMENTS_DESTINATION", "")
ARCHIVE_RECORDINGS_DESTINATION = os.environ.get("ARCHIVE_RECORDINGS_DESTINATION", "")
