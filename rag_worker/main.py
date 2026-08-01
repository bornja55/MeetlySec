"""
main.py — Com Sec RAG Worker (FastAPI) — โปรเซสแยกต่างหากที่โหลด torch/faiss/embedding/reranker/LLM

ตัดสินใจสถาปัตยกรรม (handoff.md ข้อ 3.0.1, `/grill-me` รอบ 2, 2026-08-01): คง RAG worker เป็น
โปรเซสแยกต่อไป (ไม่รวมเข้า FastAPI หลักของ Com Sec ที่ backend/main.py) เพราะ HANDOFF.md ของ
Local RAG (`D:\\Review Policy\\Local  RAG\\HANDOFF.md`) เตือนไว้ชัดเจนว่า Windows เกิด
WINHTTP.dll access-violation crash ถ้ารวม torch/faiss เข้าโปรเซสเดียวกับ web layer — เขียนใหม่แค่
ชั้น HTTP นี้เป็น FastAPI (แทน `http.server`/`BaseHTTPRequestHandler` เดิม) ส่วน logic module
(worker_state.py, worker_prompts.py, worker_parsing.py, worker_retrieval.py, worker_handlers.py,
llm_fallback.py) copy มาจากต้นฉบับ**ไม่แก้เลย** เพื่อคง behaviour ที่ผ่านการทดสอบมาแล้ว
(39 unit test + 11 E2E test บน Local RAG เดิม)

ขอบเขตที่ตัดออกโดยตั้งใจ: ต้นฉบับ Local RAG มี endpoint /draft, /draft/questions, /review/* ด้วย
(โหมดร่างเอกสารนโยบาย+รีวิวเอกสาร) — Com Sec Module 1 ต้องการแค่ Q&A (backend/main.py stub เดิมมี
แค่ /api/rag/query กับ /api/rag/query_confidential) จึงไม่ port endpoint เหล่านั้นมาที่นี่ (ไม่ใช้
= ไม่เพิ่มพื้นที่โค้ดที่ไม่มีใครเรียก) ถ้าต้องการโหมดร่าง/รีวิวเอกสารในอนาคต ใช้ Local RAG
(Streamlit) ตรงๆ ได้เลย — เป็นคนละผลิตภัณฑ์ที่ตั้งใจให้อยู่คู่กัน (ดู handoff.md)

RBAC: worker นี้**ไม่ตรวจสอบ JWT เอง** — เชื่อ header X-User-Id / X-User-Role ที่ backend หลักของ
Com Sec (backend/main.py ผ่าน auth.py) ตรวจสอบสิทธิ์แล้วส่งต่อมาให้ (worker ฟังที่
127.0.0.1 เท่านั้น ไม่เปิดสู่เครือข่ายภายนอก — ดู .env.example) endpoint /query_confidential เช็ค
role ซ้ำอีกชั้นที่นี่ (defense in depth) เทียบกับ CONFIDENTIAL_ALLOWED_ROLES ใน worker_config.py

Endpoints:
    GET  /health              -> {"status": "loading"|"ready"|"error", "detail": "...",
                                   "confidential_index_ready": bool}
    POST /query                body {"user_id": "...", "prompt": "..."}
                               -> {"response": "...", "sources": [...], "tokens": N}
                               ค้นนโยบายทั่วไป (ดัชนีเดียวกับ Local RAG) — ทุก authenticated role
    POST /query_confidential   body {"user_id": "...", "role": "...", "prompt": "..."}
                               -> {"response": "...", "sources": [...], "tokens": N,
                                   "confidential_index_ready": bool}
                               ค้น BOD Minutes ที่ลับ — จำกัดเฉพาะ role ใน
                               CONFIDENTIAL_ALLOWED_ROLES เท่านั้น (403 ถ้าไม่ใช่)

รันแบบ standalone:
    venv\\Scripts\\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8766
"""
import os
import sys
import threading
import traceback

# worker_config มี side effect ตอน import (โหลด .env + ตั้ง OMP/HF env vars) — ต้องมาก่อน
# faiss/torch เสมอ เหมือนต้นฉบับทุกประการ
import worker_config as config
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

if "GOOGLE_API_KEY" not in os.environ:
    raise RuntimeError(
        "ไม่พบ GOOGLE_API_KEY — สร้างไฟล์ .env ใน D:\\Com Sec\\rag_worker\\ (ดู .env.example) "
        "แล้วใส่ GOOGLE_API_KEY=<คีย์จริงของคุณ>"
    )

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# import faiss ก่อน torch เสมอ กันปัญหา OpenMP DLL โหลดผิดลำดับ (เหมือนต้นฉบับ)
import confidential_rag  # noqa: E402
import faiss  # noqa: E402,F401
import worker_handlers as handlers  # noqa: E402
import worker_state as state  # noqa: E402
from worker_prompts import _build_sys_prompt  # noqa: E402

log = state.log

app = FastAPI(title="Com Sec RAG Worker", version="1.0.0")


def _load_everything() -> None:
    """โหลดโมเดล/ดัชนีทั่วไปทั้งหมด (บล็อกประมาณ 4 นาทีรอบแรก) รันใน background thread —
    พอร์ตมาจาก rag_worker.py เดิมของ Local RAG ตรงๆ ไม่แก้ logic แค่ต่างจุดที่โหลด storage
    (ชี้ผ่าน worker_config.STORAGE_DIR ที่ตอนนี้ชี้ไปที่ Local RAG's storage/ แทน)"""
    try:
        log("เริ่มโหลด embedding model (BGE-M3)...")
        import torch
        from llama_index.core import Settings
        from llama_index.embeddings.huggingface import HuggingFaceEmbedding

        embed_model = HuggingFaceEmbedding(
            model_name=config.BGE_M3_PATH,
            model_kwargs={"torch_dtype": torch.float16, "use_safetensors": True},
        )
        embed_model.get_text_embedding("warmup")
        log("Embedding model พร้อมแล้ว")

        Settings.embed_model = embed_model
        Settings.context_window = 1048576
        Settings.chunk_size = 400
        Settings.chunk_overlap = 40

        log("เริ่มโหลด reranker (BGE-reranker-v2-m3)...")
        from llama_index.core.postprocessor.types import BaseNodePostprocessor
        from pydantic import Field, PrivateAttr
        from sentence_transformers import CrossEncoder

        class _Reranker(BaseNodePostprocessor):
            top_n: int = Field(default=20)
            model_name: str = Field(default=config.RERANKER_PATH)
            _model = PrivateAttr()

            def __init__(self, **kwargs):
                super().__init__(**kwargs)
                self._model = CrossEncoder(
                    self.model_name,
                    model_kwargs={"torch_dtype": torch.float16, "use_safetensors": True},
                )
                self._model.predict([["warmup", "test"]])

            @classmethod
            def class_name(cls):
                return "Reranker"

            def _postprocess_nodes(self, nodes, query_bundle=None):
                if not query_bundle or not nodes:
                    return nodes
                pairs = [[query_bundle.query_str, n.node.get_content()] for n in nodes]
                scores = self._model.predict(pairs)
                for node, score in zip(nodes, scores):
                    node.score = float(score)
                return sorted(nodes, key=lambda x: x.score or 0.0, reverse=True)[: self.top_n]

        reranker = _Reranker()
        log("Reranker พร้อมแล้ว")

        log(f"เริ่มโหลด FAISS index จาก {config.STORAGE_DIR} (ใช้ร่วมกับ Local RAG)...")
        from llama_index.core import StorageContext, load_index_from_storage
        from llama_index.vector_stores.faiss import FaissVectorStore

        if not os.path.exists(config.STORAGE_DIR):
            raise RuntimeError(
                f"ไม่พบดัชนี Local RAG ที่ {config.STORAGE_DIR} — ต้อง build_index.py ที่ "
                f"'{config.SHARED_RAG_DIR}' ก่อน (โปรเจกต์นั้นทำไปแล้ว ถ้าเห็น error นี้แปลว่า "
                f"SHARED_RAG_DIR ใน worker_config.py/.env ชี้ผิด path)"
            )
        vector_store = FaissVectorStore.from_persist_dir(config.STORAGE_DIR)
        storage_context = StorageContext.from_defaults(
            vector_store=vector_store, persist_dir=config.STORAGE_DIR
        )
        index = load_index_from_storage(storage_context)
        log("FAISS index พร้อมแล้ว")

        with state._state_lock:
            state._index = index
            state._reranker = reranker
            state._sys_prompt = _build_sys_prompt()
            state._status["status"] = "ready"
            state._status["detail"] = "พร้อมใช้งาน"
        log("Worker พร้อมรับคำถามแล้ว")

    except Exception as e:
        log(f"โหลดล้มเหลว: {type(e).__name__} - {e}\n{traceback.format_exc()}")
        with state._state_lock:
            state._status["status"] = "error"
            state._status["detail"] = f"{type(e).__name__}: {e}"


def _cleanup_idle_sessions() -> None:
    """ลบ session (ทั้ง general + confidential) ที่ idle เกิน SESSION_IDLE_TIMEOUT_SECONDS —
    เหมือนต้นฉบับ แต่ลบทั้งสอง SessionStore เพราะ Com Sec มีดัชนีลับแยกที่มี session ของตัวเอง"""
    import time
    while True:
        time.sleep(600)
        expired = state.sessions.cleanup_idle(config.SESSION_IDLE_TIMEOUT_SECONDS)
        expired_confidential = confidential_rag.confidential_sessions.cleanup_idle(
            config.SESSION_IDLE_TIMEOUT_SECONDS
        )
        if expired:
            log(f"[CLEANUP] ลบ {len(expired)} session (ทั่วไป) ที่ idle เกิน "
                f"{config.SESSION_IDLE_TIMEOUT_SECONDS}s")
        if expired_confidential:
            log(f"[CLEANUP] ลบ {len(expired_confidential)} session (ลับ) ที่ idle เกิน "
                f"{config.SESSION_IDLE_TIMEOUT_SECONDS}s")


@app.on_event("startup")
def _startup() -> None:
    log("=" * 50)
    log("Com Sec RAG worker กำลังเริ่มทำงาน (FastAPI)...")
    threading.Thread(target=_load_everything, daemon=True).start()
    threading.Thread(target=_cleanup_idle_sessions, daemon=True).start()


def _require_ready() -> None:
    with state._state_lock:
        ready = state._status["status"] == "ready"
        detail = dict(state._status)
    if not ready:
        raise HTTPException(status_code=503, detail=detail)


class QueryBody(BaseModel):
    user_id: str
    prompt: str


class ConfidentialQueryBody(BaseModel):
    user_id: str
    role: str
    prompt: str


@app.get("/health")
def health():
    with state._state_lock:
        payload = dict(state._status)
    payload["confidential_index_ready"] = confidential_rag.index_available()
    return payload


@app.post("/query")
def query(body: QueryBody, x_user_id: str | None = Header(default=None)):
    """Q&A นโยบายทั่วไป (ดัชนีเดียวกับ Local RAG) — ทุก authenticated user เรียกได้
    (สิทธิ์เช็คที่ backend หลักผ่าน verify_azure_ad_token แล้วก่อนถึงนี่) session key คือ
    user_id จริง (จาก body หรือ header X-User-Id ถ้ามี — ใช้ตัวใดตัวหนึ่ง ต้องไม่ว่าง)"""
    _require_ready()
    user_id = (x_user_id or body.user_id or "").strip()
    if not user_id:
        raise HTTPException(status_code=400, detail="missing user_id")
    try:
        result = handlers._handle_chat(user_id, body.prompt)
    except Exception as e:
        log(f"POST /query error: {type(e).__name__} - {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))
    if "error" in result:
        return JSONResponse(status_code=502, content=result)
    return result


@app.post("/query_confidential")
def query_confidential(body: ConfidentialQueryBody, x_user_id: str | None = Header(default=None)):
    """Q&A บน BOD Minutes ที่ลับ — เช็ค role ซ้ำอีกชั้นที่นี่ (defense in depth นอกเหนือจาก
    require_role() ที่ backend หลักเช็คไปแล้วรอบหนึ่ง) เทียบกับ CONFIDENTIAL_ALLOWED_ROLES"""
    _require_ready()
    if body.role not in config.CONFIDENTIAL_ALLOWED_ROLES:
        raise HTTPException(
            status_code=403,
            detail=f"role '{body.role}' ไม่มีสิทธิ์เข้าถึงเอกสารลับ "
                   f"(ต้องเป็นหนึ่งใน {sorted(config.CONFIDENTIAL_ALLOWED_ROLES)})",
        )
    user_id = (x_user_id or body.user_id or "").strip()
    if not user_id:
        raise HTTPException(status_code=400, detail="missing user_id")
    try:
        result = confidential_rag.handle_confidential_query(user_id, body.prompt)
    except Exception as e:
        log(f"POST /query_confidential error: {type(e).__name__} - {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))
    if "error" in result:
        return JSONResponse(status_code=502, content=result)
    return result


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=config.PORT, reload=False)
