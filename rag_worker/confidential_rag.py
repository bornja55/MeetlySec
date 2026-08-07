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
import re
import threading

import llm_fallback
import worker_config as config
from worker_state import SessionStore, log

# ชื่อไฟล์ที่ backend/main.py's _archive_and_notify_background() ใช้เขียนเข้า CONFIDENTIAL_CORPUS_DIR
# เสมอคือ f"meeting_{meeting_id}_final.docx" (ดู session 3.36) — ใช้ pattern เดียวกันแกะ meeting_id
# กลับออกมาตอน index เพื่อ tag เป็น metadata ต่อ chunk (session 3.37, ผู้ใช้ขอ filter ค้นหาเฉพาะ
# การประชุมที่เลือกได้ — ดู handoff.md) ไฟล์ไหนไม่ตรง pattern (เช่นถูกใส่มือ) จะไม่มี meeting_id
# metadata เลย — ยังค้นหาได้ปกติ แค่ไม่โผล่ตอน filter ตาม meeting_id เจาะจง
_FILENAME_MEETING_ID_RE = re.compile(r"^meeting_(\d+)_final\.")

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


def rebuild_index_from_corpus() -> dict:
    """สร้างดัชนี FAISS จาก `CONFIDENTIAL_CORPUS_DIR` ใหม่ทั้งหมด (2026-08-07, ผู้ใช้ขอต่อสาย
    Approve → RAG อัตโนมัติ — ดู handoff.md session 3.36) — ก่อนหน้านี้มีแค่
    `build_confidential_index.py` (สคริปต์ CLI แยกต่างหาก ต้องรันมือ ไม่เคยถูกเรียกจากที่ไหนเลย
    ทั้งระบบ) ย้าย logic หลักมาไว้ที่นี่แทน ให้เรียกได้ 2 ทาง: (1) `build_confidential_index.py`
    (CLI แบบเดิม, เหลือไว้เป็น thin wrapper) (2) `POST /admin/rebuild_confidential_index` ตอน
    `rag_worker` กำลังรันอยู่แล้ว (เรียกจาก `backend/main.py` หลัง Checker Approve)

    **Full rebuild เสมอ ไม่ใช่ incremental** (ตัดสินใจ 2026-08-07 ผ่าน `AskUserQuestion` — ผู้ใช้
    เลือกความง่าย/ถูกต้องแน่นอน เหนือ optimization เพราะสเกลเอกสารบอร์ดของบริษัทเดียวไม่มากพอที่จะ
    คุ้มความซับซ้อนของ incremental index) ทุกครั้งที่เรียกจะอ่านทุกไฟล์ใน corpus ใหม่หมด embed ใหม่
    ทั้งชุด แล้วเขียนทับ storage เดิม

    **reuse `Settings.embed_model`** ถ้ามีอยู่แล้ว (เคสเรียกจาก endpoint ตอน worker รันอยู่ — โหลด
    ไว้แล้วตั้งแต่ `main.py::_load_everything()` ตอน startup) กัน VRAM โดนใช้ซ้ำซ้อน 2 ชุดพร้อมกัน —
    โหลดใหม่เองแค่ตอนเรียกแบบ standalone CLI (`Settings.embed_model` ยังเป็น `None` เพราะไม่มี worker
    process ไหนโหลดไว้ก่อน)

    **สำคัญ**: reset `_index`/`_reranker`/`_load_attempted`/`_load_error` ทันทีหลัง build สำเร็จ —
    ปิด gap เดิมที่ `ensure_loaded()` เคย "พยายามโหลดครั้งเดียวต่อการรัน process" (ถ้าไม่ reset
    ตรงนี้ ดัชนีใหม่ที่เพิ่งสร้างจะไม่ถูกโหลดจนกว่าจะ restart worker เอง — คำเตือนเดิมใน
    `build_confidential_index.py`) คืน `{"success": bool, "message": str, "document_count": int}`"""
    global _index, _reranker, _load_attempted, _load_error

    if not os.path.exists(config.CONFIDENTIAL_CORPUS_DIR):
        os.makedirs(config.CONFIDENTIAL_CORPUS_DIR, exist_ok=True)
        return {
            "success": False,
            "message": f"{config.CONFIDENTIAL_CORPUS_DIR} ว่างเปล่า (สร้างโฟลเดอร์ให้แล้ว) — ยังไม่มีเอกสารลับให้ index",
            "document_count": 0,
        }

    # ไม่นับ README.md (ไฟล์คำอธิบายโฟลเดอร์เดิม ไม่ใช่เอกสารลับจริง — ดู confidential_corpus/README.md)
    # เป็น "เอกสารที่มีอยู่" กันตัดสินใจผิดว่ามีเอกสารพร้อม index ทั้งที่ยังไม่มีจริง
    real_files = [
        f for f in os.listdir(config.CONFIDENTIAL_CORPUS_DIR)
        if os.path.isfile(os.path.join(config.CONFIDENTIAL_CORPUS_DIR, f)) and f != "README.md"
    ]
    if not real_files:
        return {
            "success": False,
            "message": f"{config.CONFIDENTIAL_CORPUS_DIR} ยังไม่มีเอกสารลับจริง (มีแค่ README.md หรือว่างเปล่า)",
            "document_count": 0,
        }

    import faiss
    from llama_index.core import Settings, SimpleDirectoryReader, StorageContext, VectorStoreIndex
    from llama_index.vector_stores.faiss import FaissVectorStore

    # เช็คว่ามี embed_model ตั้งไว้แล้วจริงหรือยัง — **ห้ามอ่าน `Settings.embed_model` ตรงๆ เพื่อเช็ค
    # ค่า** เพราะเป็น property ที่ auto-resolve เป็นค่า default ของ llama_index (OpenAI embeddings)
    # ทันทีถ้ายังไม่เคยตั้งค่าไว้เลย ซึ่งไปเรียก `resolve_embed_model("default")` แล้ว raise
    # ImportError ก่อนจะรู้ผล "is None" ด้วยซ้ำ (โปรเจกต์นี้ไม่ได้ติดตั้ง
    # llama-index-embeddings-openai เพราะใช้ BGE-M3 ผ่าน HuggingFace เท่านั้น — เจอบั๊กนี้จริงตอนรัน
    # build_confidential_index.py แบบ standalone ครั้งแรก 2026-08-07 ดู handoff.md session 3.38)
    # อ่าน internal attribute `_embed_model` ตรงๆ แทนเพื่อเลี่ยง auto-resolve นี้
    if getattr(Settings, "_embed_model", None) is None:
        # โหมด CLI standalone (build_confidential_index.py เรียกตรง ไม่มี rag_worker process ไหน
        # โหลด embed_model ไว้ก่อนเลย) — โหลดเองสดๆ เหมือน build_confidential_index.py เดิมทุกประการ
        import torch
        from llama_index.embeddings.huggingface import HuggingFaceEmbedding

        _device = "cuda" if torch.cuda.is_available() else "cpu"
        _dtype = torch.float16 if _device == "cuda" else torch.float32
        log(f"[CONFIDENTIAL-REBUILD] ไม่มี Settings.embed_model โหลดไว้ก่อน (โหมด standalone) — "
            f"โหลดใหม่ device={_device}, dtype={_dtype}")
        Settings.embed_model = HuggingFaceEmbedding(
            model_name=config.BGE_M3_PATH, device=_device,
            model_kwargs={"torch_dtype": _dtype, "use_safetensors": True},
        )
    Settings.chunk_size = 400
    Settings.chunk_overlap = 40
    Settings.llm = None

    documents = SimpleDirectoryReader(
        config.CONFIDENTIAL_CORPUS_DIR, exclude=["README.md"]
    ).load_data()
    if not documents:
        return {
            "success": False,
            "message": "พบไฟล์ในโฟลเดอร์แต่อ่านเป็นเอกสารไม่ได้เลย (เช็คฟอร์แมต — รองรับ .docx/.md/.txt/.pdf)",
            "document_count": 0,
        }

    # แท็ก meeting_id ให้แต่ละ Document ก่อนสร้างดัชนี (session 3.37) — ใช้ filter ตอนค้นหาให้จำกัด
    # เฉพาะการประชุมที่ผู้ใช้เลือกได้ (ดู handle_confidential_query) exclude ออกจาก
    # embed/llm text เพราะเป็นแค่ id เชิงโครงสร้าง ไม่ใช่เนื้อหาที่ควรมีผลต่อ semantic search
    for doc in documents:
        file_name = doc.metadata.get("file_name", "")
        m = _FILENAME_MEETING_ID_RE.match(file_name)
        if m:
            doc.metadata["meeting_id"] = m.group(1)
            doc.excluded_embed_metadata_keys.append("meeting_id")
            doc.excluded_llm_metadata_keys.append("meeting_id")

    faiss_index = faiss.IndexFlatIP(1024)
    vector_store = FaissVectorStore(faiss_index=faiss_index)
    storage_context = StorageContext.from_defaults(vector_store=vector_store)
    log(f"[CONFIDENTIAL-REBUILD] กำลังสร้างดัชนีจาก {len(documents)} เอกสาร...")
    index = VectorStoreIndex.from_documents(documents, storage_context=storage_context)

    os.makedirs(config.CONFIDENTIAL_STORAGE_DIR, exist_ok=True)
    index.storage_context.persist(persist_dir=config.CONFIDENTIAL_STORAGE_DIR)

    with _lock:
        _index = None
        _reranker = None
        _load_attempted = False
        _load_error = None

    log(f"[CONFIDENTIAL-REBUILD] สร้างดัชนีใหม่สำเร็จ ({len(documents)} เอกสาร) — จะโหลดอัตโนมัติ"
        f"ในคำถามถัดไป (ไม่ต้อง restart worker)")
    return {
        "success": True,
        "message": f"rebuild ดัชนีเอกสารลับสำเร็จ ({len(documents)} เอกสาร)",
        "document_count": len(documents),
    }


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


def handle_confidential_query(user_id: str, prompt: str, meeting_id: str | int | None = None) -> dict:
    """Q&A บนเอกสารลับ (BOD minutes) — role check ทำที่ main.py /query_confidential แล้วก่อนเรียก
    มาถึงนี่ (worker นี้ไม่รู้จัก role โดยตรง ไว้ใจ header ที่ backend หลักส่งมาหลัง require_role()
    ผ่านแล้วเท่านั้น) session key คือ user_id จริงเสมอ ไม่ใช่ session_id ที่ client เลือกเอง

    `meeting_id` (session 3.37, ผู้ใช้ขอผ่าน `/grill-me`-style AskUserQuestion): ถ้าระบุมา จะจำกัด
    ผลลัพธ์ให้อยู่แค่ chunk ที่มาจากการประชุมนั้นเท่านั้น — **filter ทำเองใน Python หลัง retrieve
    ไม่ใช้ llama_index's MetadataFilters ที่ระดับ vector store** เพราะ `FaissVectorStore` (raw FAISS
    index) **ไม่รองรับ metadata filter แบบ native** (FAISS เป็นแค่ similarity search โครงสร้างล้วนๆ
    ไม่มี concept ของ metadata เลย) วิธีนี้เพิ่ม `similarity_top_k` ให้กว้างขึ้นตอนมี filter (80 แทน
    40) กันเคสที่ chunk ของการประชุมที่เลือกไม่ติด top-k เพราะแข่งกับการประชุมอื่นที่เนื้อหาใกล้เคียง
    คำถามมากกว่า — เพียงพอสำหรับสเกล MVP (เอกสารบอร์ดบริษัทเดียว ไม่ใช่ corpus ขนาดใหญ่)"""
    if not ensure_loaded():
        return {
            "response": _load_error or "เอกสารลับยังไม่พร้อมใช้งาน",
            "sources": [],
            "tokens": 0,
            "confidential_index_ready": False,
        }

    from llama_index.core.schema import QueryBundle

    retrieve_top_k = 80 if meeting_id else 40
    retriever = _index.as_retriever(similarity_top_k=retrieve_top_k)
    nodes = retriever.retrieve(prompt)

    if meeting_id is not None and str(meeting_id).strip():
        meeting_id_str = str(meeting_id).strip()
        nodes = [n for n in nodes if str(n.node.metadata.get("meeting_id", "")) == meeting_id_str]
        if not nodes:
            # ไม่เจอ chunk ของการประชุมนี้เลยใน top-k ที่ดึงมา — ตอบตรงๆ ไม่ต้องเสีย Gemini call
            # เปล่าๆ (ต่างจากเคส "ไม่ระบุ meeting_id" ที่ปล่อยให้ LLM เห็น context ว่างแล้วตอบเอง
            # เพราะเคสนั้นเกิดยากกว่ามาก — ดัชนีทั้งก้อนว่างจริงๆ)
            return {
                "response": "ไม่พบเนื้อหาที่เกี่ยวข้องกับคำถามนี้ในเอกสารการประชุมที่เลือก "
                            "ลองเปลี่ยนคำถามหรือเลือก \"ทุกการประชุม\" เพื่อค้นหาในทุกเอกสาร",
                "sources": [],
                "tokens": 0,
                "confidential_index_ready": True,
            }

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
