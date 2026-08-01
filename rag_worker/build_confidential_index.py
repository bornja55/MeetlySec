"""
build_confidential_index.py — สร้าง/อัปเดตดัชนี FAISS ของเอกสารลับ (BOD Minutes ที่ Approve แล้ว)

พอร์ตแพทเทิร์นจาก D:\\Review Policy\\Local  RAG\\build_index.py แต่ชี้ไปที่
confidential_corpus/ → confidential_storage/ แยกต่างหาก (ไม่ใช่ storage/ ที่ใช้ร่วมกับ Local RAG
— ดู confidential_rag.py สำหรับเหตุผลที่แยกดัชนี)

**สถานะปัจจุบัน (2026-08-01): ยังไม่มีเอกสารจริงให้รัน** — Module 5 (Approval + Archive) ยังไม่ถูก
สร้าง จึงยังไม่มี BOD minutes ที่ approve แล้วให้ index สคริปต์นี้เตรียมไว้ล่วงหน้าเป็นโครง รอวันที่
Module 5 เริ่มเขียนไฟล์ .docx/.md ของรายงานที่ approve แล้วลงใน confidential_corpus/ จริง — ตอนนั้น
ค่อยรันสคริปต์นี้ (หรือเรียกจาก Module 5's archive step โดยตรงเพื่อ auto re-index หลัง approve ทุกครั้ง
— ยังไม่ตัดสินใจว่าจะ auto หรือ manual รอ scope Module 5)

รันแบบ standalone:
    venv\\Scripts\\python.exe build_confidential_index.py
"""
import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

import worker_config as config  # noqa: E402


def main() -> None:
    if not os.path.exists(config.CONFIDENTIAL_CORPUS_DIR):
        os.makedirs(config.CONFIDENTIAL_CORPUS_DIR, exist_ok=True)
        print(
            f"สร้างโฟลเดอร์ {config.CONFIDENTIAL_CORPUS_DIR} แล้ว (ว่างเปล่า) — ยังไม่มีเอกสารลับ "
            f"ให้ index กรุณาใส่ไฟล์ BOD Minutes ที่ Approve แล้ว (.docx/.md) ลงในโฟลเดอร์นี้ก่อนรัน "
            f"สคริปต์นี้อีกครั้ง"
        )
        return

    documents_present = any(
        os.path.isfile(os.path.join(config.CONFIDENTIAL_CORPUS_DIR, f))
        for f in os.listdir(config.CONFIDENTIAL_CORPUS_DIR)
    )
    if not documents_present:
        print(
            f"{config.CONFIDENTIAL_CORPUS_DIR} ว่างเปล่า — ยังไม่มีเอกสารลับให้ index "
            f"(ปกติถ้า Module 5 ยังไม่เริ่ม archive รายงานที่ approve แล้ว)"
        )
        return

    import faiss
    import torch
    from llama_index.core import (
        Settings,
        SimpleDirectoryReader,
        StorageContext,
        VectorStoreIndex,
    )
    from llama_index.embeddings.huggingface import HuggingFaceEmbedding
    from llama_index.vector_stores.faiss import FaissVectorStore

    print("กำลังโหลด Embedding Model (BAAI/bge-m3)...")
    embed_model = HuggingFaceEmbedding(
        model_name=config.BGE_M3_PATH,
        model_kwargs={"torch_dtype": torch.float16, "use_safetensors": True},
    )
    Settings.embed_model = embed_model
    Settings.chunk_size = 400
    Settings.chunk_overlap = 40
    Settings.llm = None

    print(f"กำลังอ่านเอกสารลับจาก {config.CONFIDENTIAL_CORPUS_DIR} ...")
    documents = SimpleDirectoryReader(config.CONFIDENTIAL_CORPUS_DIR).load_data()
    if not documents:
        print("ไม่พบเอกสารที่อ่านได้ (ตรวจสอบฟอร์แมตไฟล์ — รองรับ .docx/.md/.txt/.pdf)")
        return
    print(f"อ่านไฟล์สำเร็จ รวมทั้งหมด {len(documents)} ชิ้น")

    faiss_index = faiss.IndexFlatIP(1024)
    vector_store = FaissVectorStore(faiss_index=faiss_index)
    storage_context = StorageContext.from_defaults(vector_store=vector_store)

    print("กำลังสร้าง Vector Store Index สำหรับเอกสารลับ...")
    index = VectorStoreIndex.from_documents(
        documents, storage_context=storage_context, show_progress=True
    )

    os.makedirs(config.CONFIDENTIAL_STORAGE_DIR, exist_ok=True)
    index.storage_context.persist(persist_dir=config.CONFIDENTIAL_STORAGE_DIR)
    print(f"สร้างดัชนีเอกสารลับสำเร็จ บันทึกไว้ที่ {config.CONFIDENTIAL_STORAGE_DIR}")
    print("รีสตาร์ท rag_worker (main.py) เพื่อให้โหลดดัชนีใหม่นี้ (โหลดแบบ lazy ตอน query แรก)")


if __name__ == "__main__":
    main()
