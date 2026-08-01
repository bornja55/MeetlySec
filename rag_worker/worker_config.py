"""
worker_config.py — config/env loading ของ Com Sec RAG worker

พอร์ตมาจาก D:\\Review Policy\\Local  RAG\\worker_config.py (Policy RAG Assistant) ตามการตัดสินใจ
Module 1 (`/grill-me` รอบ 2, 2026-08-01): คง RAG worker เป็นโปรเซสแยกต่อไป ไม่รวมเข้า FastAPI หลัก
ของ Com Sec — เขียนชั้น HTTP ใหม่เป็น FastAPI (ดู main.py) ส่วนโมดูล logic (worker_state.py,
worker_prompts.py, worker_parsing.py, worker_retrieval.py, worker_handlers.py, llm_fallback.py)
copy มาจากต้นฉบับ**ไม่แก้แม้แต่บรรทัดเดียว** เพื่อคง behaviour ที่ผ่านการทดสอบมาแล้ว (39 unit test +
11 E2E test) — ไฟล์นี้เป็นไฟล์เดียวที่ปรับต่างจากต้นฉบับ เพราะต้องชี้ path ไปที่ corpus/storage/models
เดียวกับ Local RAG (ไม่ copy corpus แยก ป้องกัน FAISS index สอง product drift กัน — ดู
handoff.md ข้อ 3.0 การตัดสินใจข้อ 1)

สำคัญ: โมดูลนี้ต้อง import ได้โดย**ไม่ต้องมี GOOGLE_API_KEY** เหมือนต้นฉบับ (การเช็ค API key อยู่ที่
main.py entrypoint แทน) และต้องถูก import ก่อน faiss/torch เสมอ
"""
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ── ชี้ไปที่ corpus/storage/models ของ Local RAG โดยตรง (ไม่ copy) ──────────────────────
# ตัดสินใจ (handoff.md ข้อ 3.0.2): Local RAG (Streamlit, deep policy research) กับ Module 1 ของ
# Com Sec (RAG Q&A เร็วๆ ฝังใน workflow เลขาบริษัท) อยู่คู่กันถาวร คนละ use case แต่ต้องชี้ไปที่
# FAISS index/storage เดียวกัน ป้องกันข้อมูล 2 ระบบ drift กัน — override ผ่าน .env
# (SHARED_RAG_DIR=...) ถ้าย้ายที่เก็บในอนาคต
SHARED_RAG_DIR = os.environ.get(
    "SHARED_RAG_DIR",
    r"D:\Review Policy\Local  RAG",
)
BGE_M3_PATH = os.path.join(SHARED_RAG_DIR, "models", "bge-m3")
RERANKER_PATH = os.path.join(SHARED_RAG_DIR, "models", "bge-reranker-v2-m3")
STORAGE_DIR = os.path.join(SHARED_RAG_DIR, "storage")
DATA_DIRS = [
    os.path.join(SHARED_RAG_DIR, "Policies"),
    os.path.join(SHARED_RAG_DIR, "Procedures"),
    os.path.join(SHARED_RAG_DIR, "Manuals"),
    os.path.join(SHARED_RAG_DIR, "Forms"),
]

# ── Corpus ลับเฉพาะ Com Sec (BOD Minutes ที่ Approve แล้ว) — index แยกต่างหาก ────────────
# ตั้งใจ**ไม่ใส่ในดัชนีเดียวกับ Local RAG ด้านบน** เพราะ Local RAG ไม่มีระบบ RBAC เลย (ใครก็ใช้
# Streamlit app ได้) ถ้าใส่ BOD minutes ลงดัชนีที่ใช้ร่วมกันจะเสี่ยงข้อมูลลับหลุดไปโผล่ในผลค้นหาของ
# Local RAG ทันที — ดัชนีนี้จึงเก็บแยกไว้เฉพาะใน Com Sec เอง เข้าถึงได้ผ่าน /query_confidential
# เท่านั้น (RBAC เช็คทั้งที่ backend หลักและซ้ำอีกชั้นที่ worker นี้) ปัจจุบันยังไม่มีเอกสารจริง
# (Module 3-5 ยังไม่เสร็จ — ยังไม่มี BOD minutes ที่ approve แล้วให้ index) โฟลเดอร์/ดัชนีนี้จะว่าง
# จนกว่าจะรัน build_confidential_index.py หลังมีเอกสารจริง
CONFIDENTIAL_CORPUS_DIR = os.path.join(BASE_DIR, "confidential_corpus")
CONFIDENTIAL_STORAGE_DIR = os.path.join(BASE_DIR, "confidential_storage")

LOG_FILE = os.path.join(BASE_DIR, "rag_worker_com_sec.log")

# พอร์ตแยกจาก Local RAG worker (8765) เพื่อให้รันพร้อมกันบนเครื่องเดียวกันได้โดยไม่ชนกัน
PORT = int(os.environ.get("COM_SEC_RAG_WORKER_PORT", "8766"))


def _load_dotenv(path: str) -> None:
    """โหลด KEY=VALUE จาก .env แบบง่ายๆ เหมือนต้นฉบับ ไม่ทับค่าที่ set ไว้แล้วใน environment จริง"""
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())


_load_dotenv(os.path.join(BASE_DIR, ".env"))

# ── Env setup (เหมือนต้นฉบับทุกประการ) ──────────────────────────────────────────────
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"
os.environ["TQDM_DISABLE"] = "1"
os.environ["TOKENIZERS_PARALLELISM"] = "false"
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"

COMPANY_NAME = os.environ.get("COMPANY_NAME", "ออริจิ้น โกลบอล เอ็มไพร์")

GEMINI_MODEL_CHAT = os.environ.get("GEMINI_MODEL_CHAT", "gemini-3.1-flash-lite")
GEMINI_MODEL_DRAFT = os.environ.get("GEMINI_MODEL_DRAFT", "gemini-3.5-flash")


def _parse_model_chain(env_value: str) -> list[str]:
    """เหมือนต้นฉบับ — comma-separated model fallback chain"""
    return [m.strip() for m in env_value.split(",") if m.strip()]


GEMINI_MODEL_CHAT_FALLBACK = _parse_model_chain(os.environ.get("GEMINI_MODEL_CHAT_FALLBACK", ""))
GEMINI_MODEL_DRAFT_FALLBACK = _parse_model_chain(os.environ.get("GEMINI_MODEL_DRAFT_FALLBACK", ""))

# หมดอายุ session ที่ไม่ได้ใช้งานนาน — เหมือนต้นฉบับ แต่ session key ที่ Com Sec ใช้คือ
# authenticated user_id จริง (ไม่ใช่ browser-tab session_id แบบ Local RAG เดิม — ดู main.py)
SESSION_IDLE_TIMEOUT_SECONDS = int(os.environ.get("SESSION_IDLE_TIMEOUT_SECONDS", str(8 * 60 * 60)))

GEMINI_REQUEST_TIMEOUT_MS = int(os.environ.get("GEMINI_REQUEST_TIMEOUT_MS", str(5 * 60 * 1000)))

# Role ที่มีสิทธิ์เรียก /query_confidential (เช็คซ้ำอีกชั้นที่ worker นี้ นอกจาก backend หลัก) —
# ตาม main.py stub เดิมของ Com Sec backend: Com_Sec_Maker/Checker/Board_Member (+ Global_Admin
# ที่ได้สิทธิ์ทุก role อยู่แล้วจาก require_role() ใน backend/auth.py)
CONFIDENTIAL_ALLOWED_ROLES = {
    "Global_Admin", "Com_Sec_Maker", "Com_Sec_Checker", "Board_Member",
}
