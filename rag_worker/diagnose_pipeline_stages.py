"""
diagnose_pipeline_stages.py — โหลด embed model + reranker + FAISS index เหมือน worker จริง
แล้วรัน query เดียวผ่านทีละสเตจ พร้อมจับเวลาแยกแต่ละสเตจ (ไม่ผ่าน chat_engine/condense เลย
เพื่อตัดตัวแปรนั้นออก) — เป้าหมาย: หาว่าเวลาหลักร้อยวินาทีไปกองอยู่ที่สเตจไหนจริงๆ
    1. Embed query (BGE-M3)
    2. FAISS retrieve (similarity_top_k=60)
    3. Rerank (BGE-reranker-v2-m3 cross-encoder, 60 คู่)
    4. Generate คำตอบสุดท้าย (Gemini, ใช้ context ที่ rerank แล้ว)

รัน (ใช้เวลาโหลดโมเดล ~1-2 นาทีเหมือน worker ตอนเริ่ม แล้ว query จะรันทันที):
    cd "D:\\Com Sec\\rag_worker"
    python diagnose_pipeline_stages.py
"""
import os
import sys
import time

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import worker_config as config  # noqa: E402 (โหลด .env + ตั้ง OMP/HF env vars ก่อนเสมอ)

if "GOOGLE_API_KEY" not in os.environ:
    print("[ERROR] ไม่พบ GOOGLE_API_KEY ใน .env")
    raise SystemExit(1)

import faiss  # noqa: E402,F401  (ต้อง import ก่อน torch เสมอ)

QUERY = "นโยบายการลาพักร้อนคืออะไร"


def timed(label):
    t0 = time.time()

    class _Ctx:
        def __enter__(self):
            print(f"[เริ่ม] {label}...")
            return self

        def __exit__(self, *a):
            print(f"[จบ] {label}: {time.time() - t0:.2f}s")

    return _Ctx()


print("=" * 60)
with timed("โหลด embedding model (BGE-M3)"):
    import torch
    from llama_index.core import Settings
    from llama_index.embeddings.huggingface import HuggingFaceEmbedding

    embed_model = HuggingFaceEmbedding(
        model_name=config.BGE_M3_PATH,
        model_kwargs={"torch_dtype": torch.float16, "use_safetensors": True},
    )
    embed_model.get_text_embedding("warmup")
    Settings.embed_model = embed_model
    Settings.context_window = 1048576
    Settings.chunk_size = 400
    Settings.chunk_overlap = 40

with timed("โหลด reranker (BGE-reranker-v2-m3)"):
    from sentence_transformers import CrossEncoder

    reranker_model = CrossEncoder(
        config.RERANKER_PATH,
        model_kwargs={"torch_dtype": torch.float16, "use_safetensors": True},
    )
    reranker_model.predict([["warmup", "test"]])

with timed(f"โหลด FAISS index จาก {config.STORAGE_DIR}"):
    from llama_index.core import StorageContext, load_index_from_storage
    from llama_index.vector_stores.faiss import FaissVectorStore

    vector_store = FaissVectorStore.from_persist_dir(config.STORAGE_DIR)
    storage_context = StorageContext.from_defaults(
        vector_store=vector_store, persist_dir=config.STORAGE_DIR
    )
    index = load_index_from_storage(storage_context)

print("=" * 60)
print(f"[QUERY] {QUERY!r}")
print("=" * 60)

with timed("สร้าง retriever + embed คำถาม + FAISS search (similarity_top_k=60)"):
    retriever = index.as_retriever(similarity_top_k=60)
    nodes = retriever.retrieve(QUERY)
print(f"    -> ได้ {len(nodes)} nodes")

with timed(f"Rerank {len(nodes)} nodes ผ่าน cross-encoder (predict ทีละคู่)"):
    from llama_index.core.schema import QueryBundle

    query_bundle = QueryBundle(query_str=QUERY)
    pairs = [[QUERY, n.node.get_content()] for n in nodes]
    scores = reranker_model.predict(pairs)
top20 = sorted(zip(nodes, scores), key=lambda x: x[1], reverse=True)[:20]
print(f"    -> เหลือ {len(top20)} nodes หลัง rerank")

context_text = "\n\n".join(n.node.get_content() for n, _ in top20)
full_prompt = (
    f"ตอบคำถามจาก context นี้:\n\n{context_text}\n\nคำถาม: {QUERY}"
)
print(f"    -> ขนาด prompt สุดท้าย: {len(full_prompt)} ตัวอักษร (~{len(full_prompt)//4} token)")

with timed("เรียก Gemini generate_content ด้วย context ที่ rerank แล้ว"):
    from google import genai

    client = genai.Client(api_key=os.environ["GOOGLE_API_KEY"])
    model = os.environ.get("GEMINI_MODEL_CHAT", "gemini-3.1-flash-lite")
    response = client.models.generate_content(model=model, contents=full_prompt)

print("=" * 60)
print(f"[คำตอบ 200 ตัวอักษรแรก] {response.text[:200]!r}")
print("=" * 60)
print("สรุป: ดูเวลาแต่ละ [จบ] ด้านบน — สเตจไหนกินเวลามากที่สุดคือคำตอบ")
