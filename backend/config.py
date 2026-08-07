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
# ⚠️ ขยายจาก 1 โมเดล (`gemini-3.5-flash` เดิม) เป็น 3 โมเดล (2026-08-05, session 3.32) — ที่มา:
# ผู้ใช้ทดสอบจริงเจอ primary (`gemini-3.6-flash`) โดน 503 "high demand" ชั่วคราวกลางไฟล์ยาว 11 chunk —
# fallback เดียวไม่พอถ้า Google มีปัญหา capacity ชั่วคราวกระทบหลายโมเดลพร้อมกัน (คนละประเด็นกับ "โมเดล
# ไหนดีที่สุด" ที่ปิดเรื่องไปแล้วใน session 3.30 — นี่คือเรื่อง redundancy ล้วนๆ) เลือก 2 ตัวเพิ่ม
# (`gemini-3.5-flash-lite`, `gemini-2.5-flash`) จากผลจริงใน `model_comparison_results/batch_drift_summary.csv`
# (session 3.28-3.29): ทั้งคู่เรียกได้จริงสำเร็จ 2/3 และ 3/3 ไฟล์ทดสอบตามลำดับ — **ตั้งใจไม่ใส่
# `gemini-3.1-flash-lite`** (undershoot สม่ำเสมอทุกไฟล์ที่ทดสอบ + speaker count คงที่ 2 คนน่าสงสัยว่า
# under-diarize) และ **ไม่ใส่ `gemini-2.5-flash-lite`** (fail คนละแบบทุกครั้งในผลจริง 3 ไฟล์ — 503 x2,
# "ไม่คืน structured output" x1 — ไม่เสถียรพอจะเป็น fallback)
#
# ผลกระทบต่อ speaker label consistency ข้าม chunk (ผู้ใช้ถามตรงๆ ก่อนอนุมัติ — ตอบด้วยข้อมูลจริงจากโค้ด
# ไม่เดา): `_speaker_context_prompt()` ใน audio_native.py ส่ง label ที่เจอมาก่อนหน้าเป็น **prompt
# ข้อความล้วนๆ** ให้ chunk ถัดไป ไม่ว่า chunk ถัดไปจะใช้โมเดลเดิมหรือโมเดลสำรองที่ fallback มาก็ได้ hint
# เดียวกันเป๊ะ (ไม่มีช่องทางพิเศษที่จะขาดหายเฉพาะตอนสลับโมเดล — กลไกนี้ไม่เคยส่งบริบทเสียงจริงข้าม chunk
# อยู่แล้วตั้งแต่ก่อนมี fallback หลายตัว มีแค่ text hint นี้เท่านั้น ดู docstring เดิมของฟังก์ชันนั้น) —
# ความเสี่ยง "โมเดลจำเสียงคนเดิมไม่ได้" มีอยู่แล้วเท่ากันไม่ว่าจะมี fallback 1 หรือ 3 ตัว (แค่โอกาสเจอ
# มากขึ้นเพราะมี fallback ให้สลับได้บ่อยขึ้นเท่านั้น ไม่ใช่ความเสี่ยง class ใหม่ที่ขยายนี้สร้างขึ้น)
GEMINI_MODEL_TRANSCRIPTION_FALLBACK = _parse_model_chain(
    os.environ.get(
        "GEMINI_MODEL_TRANSCRIPTION_FALLBACK",
        "gemini-3.5-flash,gemini-3.5-flash-lite,gemini-2.5-flash",
    )
)
# ไฟล์เสียงยาวกว่า text มาก ต้อง timeout นานกว่า GEMINI_MINUTES_TIMEOUT_MS — ตั้ง 15 นาทีไปก่อน
# (ยังไม่มีตัวเลข latency จริง ต้องวัดจากการทดลองจริงก่อน)
GEMINI_TRANSCRIPTION_TIMEOUT_MS = int(
    os.environ.get("GEMINI_TRANSCRIPTION_TIMEOUT_MS", str(15 * 60 * 1000))
)

# ── เลือกโมเดล Gemini เองตอน upload/re-upload (2026-08-05, ผู้ใช้ขอ) ────────────────────────
# ที่มา: audio chunking (ดูด้านบน) ทำให้ 1 meeting ยาวเรียก Gemini หลาย request (1 ต่อ chunk) แทนที่
# จะเป็น 1 request/meeting เหมือนก่อนหน้า — ผู้ใช้เจอ RPD (requests/day) ของ `gemini-3.6-flash` บน
# ฟรีเทียร์ใกล้เต็ม (16/20 จาก screenshot Google AI Studio) ขณะที่โมเดลอื่นแทบไม่ได้ใช้เลย (0/20,
# 0/500 เป็นต้น) — เปิดให้เลือกโมเดลเองตอน upload/re-upload แทนที่จะพึ่ง
# GEMINI_MODEL_TRANSCRIPTION+FALLBACK อย่างเดียว **ลำดับตามที่ผู้ใช้ระบุเอง** (ไม่ใช่ลำดับ version
# number ตรงๆ — เรียงจากที่อยากให้เป็นตัวเลือกแรกสุดไปหลังสุด) ดู `GET /api/transcription_models`
# (main.py) สำหรับ endpoint ที่ frontend ใช้ populate dropdown (mirror pattern เดียวกับ
# `docx_generation.TEMPLATE_REGISTRY`/`list_templates()`) — ค่า key ต้องตรงกับชื่อโมเดลจริงของ
# Gemini API เป๊ะ
#
# ⚠️ **อัปเดต (2026-08-05, session 3.27)**: รัน `scripts/compare_transcription_models.py` จริงกับไฟล์
# ทดสอบ 10 นาที (ดู handoff.md 3.26 สำหรับผลเต็ม) ยืนยันสถานะจริงแล้ว: `gemini-3.6-flash`/
# `gemini-3.5-flash`/`gemini-3.5-flash-lite`/`gemini-3.1-flash-lite`/`gemini-2.5-flash` เรียกได้จริง
# ทั้งหมด — **`gemini-3.1-flash` ไม่มีอยู่จริง** (API คืน 404 NOT_FOUND) ลองแก้เป็น `gemini-3-flash`
# ตามที่ผู้ใช้บอก (session 3.27) — **ก็ยังคง 404 อยู่ดี** (ยืนยันจากผลทดสอบ batch จริง session 3.28)
# ⚠️ **แก้จริงแล้ว (2026-08-05, session 3.30)**: ค้นตาราง endpoint จริงจาก official docs
# (ai.google.dev/gemini-api/docs/models, อัปเดต 2026-08-04) พบว่า "Gemini 3 Flash" เป็น **Preview**
# model (ไม่ใช่ Stable เหมือน 3.6/3.5 Flash) ต้องมี suffix `-preview` เสมอ — ชื่อที่ถูกต้องจริงคือ
# `gemini-3-flash-preview` — **ยังไม่เคย verify เรียกได้จริงผ่าน google-genai SDK อีกรอบ** (แก้ตาม
# เอกสารทางการ ยังไม่ได้ทดสอบยิงจริง) `gemini-2.5-flash-lite` เจอ fail ต่อเนื่องหลายแบบ (503 x2,
# "ไม่คืน structured output" x1) ใน batch test จริง — ดูไม่เสถียร ควรพิจารณาตัดออกถ้ายัง fail ต่อ —
# ถ้าชื่อผิด/โมเดลไม่มีจริง `run_with_fallback`/`_transcribe_one_file` จะ raise error ชัดเจน ไม่ silent
# fail
GEMINI_TRANSCRIPTION_MODEL_CHOICES = [
    ("gemini-3.6-flash", "Gemini 3.6 Flash"),
    ("gemini-3.5-flash", "Gemini 3.5 Flash"),
    ("gemini-3.5-flash-lite", "Gemini 3.5 Flash-Lite"),
    ("gemini-3-flash-preview", "Gemini 3 Flash"),
    ("gemini-3.1-flash-lite", "Gemini 3.1 Flash-Lite"),
    ("gemini-2.5-flash", "Gemini 2.5 Flash"),
    ("gemini-2.5-flash-lite", "Gemini 2.5 Flash-Lite"),
]

# ── Audio chunking (2026-08-05, แก้ปัญหา timestamp drift ตามสัดส่วน — ดู handoff.md 3.19/3.21) ──
# พบว่ายิ่งไฟล์เสียงยาวเท่าไหร่ ยิ่งส่งทีเดียวทั้งไฟล์ Gemini ยิ่งประมาณ timestamp คลาดสะสมมาก (ไฟล์
# 55 นาทีที่ทดสอบจริงคลาดท้ายไฟล์เกือบ 38 นาที) — ค้นข้อมูลแล้วพบว่าเป็น pattern ที่หลายทีมอิสระเจอ
# ตรงกัน (Towards Data Science's production pipeline, pyvideotrans issue #624,
# madeyexz/youtube2transcripts เป็นต้น) วิธีแก้ที่ตรงกันทุกแหล่ง: ตัดไฟล์เป็นชิ้นสั้นๆก่อนส่ง Gemini
# แล้วคำนวณ timestamp จริงเองจาก offset ของ chunk ในไฟล์ต้นฉบับ (ไม่เชื่อ timestamp สัมบูรณ์ที่ Gemini
# รายงานเองสำหรับไฟล์ยาว — เชื่อได้แค่ timestamp สัมพัทธ์ภายใน chunk สั้นๆ) ดู audio_chunking.py
#
# ขนาด chunk: TDS's production pipeline พบว่าคุณภาพ/timestamp เริ่มเสื่อมชัดราวนาทีที่ 15-20 ของการส่ง
# ทีเดียว เลือก 10 นาทีให้มีระยะเผื่อ (ตรงกับที่ TDS ใช้จริงเช่นกัน) ไฟล์สั้นกว่า chunk เดียวไม่ต้องตัด
# เลย (คงพฤติกรรมเดิม ไม่มี overhead เพิ่ม)
AUDIO_CHUNK_SECONDS = int(os.environ.get("AUDIO_CHUNK_SECONDS", str(10 * 60)))
# overlap กันเนื้อหาขาดหายตรงรอยตัด (เจอปัญหานี้แยกต่างหากมาก่อนแล้วใน session 3.17 — omission
# 13:46-16:48 — overlap นี้น่าจะช่วยลดความเสี่ยงเดียวกันนี้ด้วย แม้จะแก้คนละปัญหากันโดยตรง) TDS ใช้ 30
# วินาทีแล้วพบว่าพอสำหรับให้ LLM merge จับประโยคเต็มได้ (เราไม่ได้ทำ LLM merge แต่ใช้ midpoint cut
# แทน — ดู audio_chunking.py's merge_chunk_segments() สำหรับเหตุผลที่เลือกทางง่ายกว่า)
AUDIO_CHUNK_OVERLAP_SECONDS = int(os.environ.get("AUDIO_CHUNK_OVERLAP_SECONDS", "30"))

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

# ── ต่อสาย Approve → Confidential RAG index (2026-08-07) ───────────────────────────────
# ดีฟอลต์ชี้ไปที่ rag_worker/confidential_corpus/ ข้างๆ backend/ นี้ (../rag_worker/confidential_corpus
# — เหมือน worker_config.py's CONFIDENTIAL_CORPUS_DIR = BASE_DIR/confidential_corpus ที่ BASE_DIR
# คือ rag_worker/) backend เขียนไฟล์ .docx ที่ Approve แล้วลงตรงนี้เอง (ไม่ผ่าน worker) แล้วค่อยยิง
# HTTP ไปสั่ง worker rebuild ดัชนีจากโฟลเดอร์นี้อีกที (ดู _archive_and_notify_background) — override
# ผ่าน .env ได้ถ้าโครงสร้างโฟลเดอร์เปลี่ยนในอนาคต ต้องตรงกับ rag_worker's worker_config.py เสมอ
RAG_WORKER_CONFIDENTIAL_CORPUS_DIR = os.environ.get(
    "RAG_WORKER_CONFIDENTIAL_CORPUS_DIR",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "rag_worker", "confidential_corpus"),
)
