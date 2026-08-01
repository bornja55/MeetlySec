"""
confidential_rag.py — ดัชนี RAG ลับเฉพาะ Com Sec (BOD Minutes ที่ Approve แล้ว)

ไฟล์นี้เป็นโค้ดใหม่ทั้งหมด **ไม่มีอยู่ในต้นฉบับ Local RAG** เพราะ Local RAG ไม่มีระบบแยกสิทธิ์เอกสารลับ
เลย (task.md Module 1: "เพิ่มระบบแยกสิทธิ์เอกสารลับ... Local RAG เดิมไม่มีกลไกนี้เลย ต้องเขียนใหม่
ทั้งหมด")

ออกแบบให้ดัชนีนี้**แยกจากดัชนีทั่วไป**ของ worker_state.py โดยสิ้นเชิง (คนละ FAISS index, คนละ
storage folder) แทนที่จะแท็ก metadata ระดับความลับลงในดัชนีเดียวกับที่ Local RAG ใช้ร่วมด้วย
เหตุผล: Local RAG (Streamlit) ไม่มี RBAC เลย — ถ้าใส่เอกสารลับ (BOD minutes) ลงดัชนีที่สองระบบชี้
ร่วมกัน จะเสี่ยงให้ผู้ใช้ Local RAG ทั่วไปเห็นเนื้อหาลับผ่านผลค้นหาได้ทันที การแยกดัชนีตัดความเสี่ยงนี้
ทั้งหมดโดยไม่ต้องแก้ FaissVectorStore หรือ build_index.py ของ Local RAG เลย (ดู worker_config.py
ส่วน CONFIDENTIAL_* สำหรับรายละเอียด path)

สถานะปัจจุบัน (2026-08-01): ยังไม่มีเอกสารลับจริงให้ index เพราะ Module 3 (Minutes Generation) และ
Module 5 (Approval + Archive) ยังไม่ถูกสร้าง — ฟังก์ชันในไฟล์นี้ออกแบบให้ทำงานได้แม้ดัชนียังไม่มีอยู่
(คืนข้อความแจ้งเตือนแทนการ crash) รอ build_confidential_index.py ถูกรันครั้งแรกหลังมี BOD minutes
ที่ approve แล้วเก็บอยู่ใน confidential_corpus/
"""
import os
import threading

import llm_fallback
import worker_config as config
from worker_state import SessionStore, log

_lock = threading.Lock()
_index = None
_reranker = None
_load_attempted = False
_load_error: str | None = None

# session key คือ authenticated user_id จริง (ไม่ใช่ browser-tab session_id แบบ Local RAG เดิม) —
# ตัดสินใจจาก handoff.md ข้อ 3.0.2 "เปลี่ยน session model จากผูก browser tab เป็นผูกกับ
# authenticated user_id จริง"
confidential_sessions = SessionStore()


def index_available() -> bool:
    return os.path.exists(config.CONFIDENTIAL_STORAGE_DIR) and bool(
        os.listdir(config.CONFIDENTIAL_STORAGE_DIR)
    )


def ensure_loaded() -> bool:
    """โหลดดัชนีลับแบบ lazy (โหลดตอนมี query แรกเข้ามาเท่านั้น ไม่บล็อก worker startup เหมือน
    ดัชนีทั่วไป เพราะดัชนีนี้อาจไม่มีอยู่เลยในช่วงแรกของโปรเจกต์) คืน True ถ้าพร้อมใช้งาน
    thread-safe, พยายามโหลดครั้งเดียว (ถ้าล้มเหลวจะไม่ retry ทุก request — ต้อง restart worker
    หลังแก้ปัญหาแล้วค่อยลองใหม่)"""
    global _index, _reranker, _load_attempted, _load_error
    with _lock:
        if _index is not None:
            return True
        if _load_attempted:
            return False
        _load_attempted = True
        if not index_available():
            _load_error = "ยังไม่มีเอกสารลับในระบบ (ยังไม่มี BOD Minutes ที่ Approve แล้ว — รอ Module 3-5)"
            log(f"[CONFIDENTIAL] {_load_error}")
            return False
        try:
            import torch
            from llama_index.core import StorageContext, load_index_from_storage
            from llama_index.core.postprocessor.types import BaseNodePostprocessor
            from llama_index.vector_stores.faiss import FaissVectorStore
            from pydantic import Field, PrivateAttr
            from sentence_transformers import CrossEncoder

            # ใช้ Settings.embed_model เดียวกับที่ main.py โหลดไว้แล้วตอน startup (global ของ
            # llama_index) — ดัชนีทั่วไปต้องโหลดเสร็จก่อนเสมอ (main.py บังคับลำดับนี้อยู่แล้ว)
            vector_store = FaissVectorStore.from_persist_dir(config.CONFIDENTIAL_STORAGE_DIR)
            storage_context = StorageContext.from_defaults(
                vector_store=vector_store, persist_dir=config.CONFIDENTIAL_STORAGE_DIR
            )
            index = load_index_from_storage(storage_context)

            class _ConfidentialReranker(BaseNodePostprocessor):
                top_n: int = Field(default=10)
                model_name: str = Field(default=config.RERANKER_PATH)
                _model = PrivateAttr()

                def __init__(self, **kwargs):
                    super().__init__(**kwargs)
                    self._model = CrossEncoder(
                        self.model_name,
                        model_kwargs={"torch_dtype": torch.float16, "use_safetensors": True},
                    )

                @classmethod
                def class_name(cls):
                    return "ConfidentialReranker"

                def _postprocess_nodes(self, nodes, query_bundle=None):
                    if not query_bundle or not nodes:
                        return nodes
                    pairs = [[query_bundle.query_str, n.node.get_content()] for n in nodes]
                    scores = self._model.predict(pairs)
                    for node, score in zip(nodes, scores):
                        node.score = float(score)
                    return sorted(nodes, key=lambda x: x.score or 0.0, reverse=True)[: self.top_n]

            _index = index
            _reranker = _ConfidentialReranker()
            log("[CONFIDENTIAL] ดัชนีเอกสารลับพร้อมใช้งานแล้ว")
            return True
        except Exception as e:
            _load_error = f"{type(e).__name__}: {e}"
            log(f"[CONFIDENTIAL] โหลดดัชนีล้มเหลว: {_load_error}")
            return False


def handle_confidential_query(user_id: str, prompt: str) -> dict:
    """Q&A บนเอกสารลับ (BOD minutes) — role check ทำที่ main.py /query_confidential แล้วก่อนเรียก
    มาถึงนี่ (worker นี้ไม่รู้จัก role โดยตรง ไว้ใจ header ที่ backend หลักส่งมาหลัง require_role()
    ผ่านแล้วเท่านั้น) session key คือ user_id จริงเสมอ ไม่ใช่ session_id ที่ client เลือกเอง"""
    if not ensure_loaded():
        return {
            "response": _load_error or "เอกสารลับยังไม่พร้อมใช้งาน",
            "sources": [],
            "tokens": 0,
            "confidential_index_ready": False,
        }

    from llama_index.core.schema import QueryBundle

    retriever = _index.as_retriever(similarity_top_k=40)
    nodes = retriever.retrieve(prompt)
    nodes = _reranker._postprocess_nodes(nodes, QueryBundle(query_str=prompt))

    context_text = "\n\n".join(
        f"[{n.node.metadata.get('file_name', 'Unknown')}]\n{n.node.get_content()}" for n in nodes
    )
    sources = [
        {
            "file_name": n.node.metadata.get("file_name", "Unknown"),
            "content": n.node.get_content()[:200],
        }
        for n in nodes
    ]

    sys_prompt = (
        "คุณเป็นผู้ช่วยค้นหารายงานการประชุมคณะกรรมการบริษัท (BOD Minutes) ที่เป็นความลับ "
        "ตอบจากเนื้อหาที่ให้มาเท่านั้น ห้ามเดาหรือแต่งเติมข้อมูล ถ้าไม่พบข้อมูลที่เกี่ยวข้องให้บอกตรงๆ ว่าไม่พบ"
    )
    full_prompt = f"{sys_prompt}\n\n=== เนื้อหาที่เกี่ยวข้อง ===\n{context_text}\n\n=== คำถาม ===\n{prompt}"

    log_prefix = f"[CONFIDENTIAL-CHAT user={user_id[:12]}]"
    response_text, error = llm_fallback.complete_with_fallback(
        config.GEMINI_MODEL_CHAT, config.GEMINI_MODEL_CHAT_FALLBACK, full_prompt, log_prefix,
        timeout_ms=config.GEMINI_REQUEST_TIMEOUT_MS, log=log,
    )
    if response_text is None:
        return {"error": str(error) if error else "unknown error"}

    return {
        "response": response_text,
        "sources": sources,
        "tokens": (len(full_prompt) + len(response_text)) // 4,
        "confidential_index_ready": True,
    }
