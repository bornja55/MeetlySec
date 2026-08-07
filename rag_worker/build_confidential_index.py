"""
build_confidential_index.py — สร้าง/อัปเดตดัชนี FAISS ของเอกสารลับ (BOD Minutes ที่ Approve แล้ว)

พอร์ตแพทเทิร์นจาก D:\\Review Policy\\Local  RAG\\build_index.py แต่ชี้ไปที่
confidential_corpus/ → confidential_storage/ แยกต่างหาก (ไม่ใช่ storage/ ที่ใช้ร่วมกับ Local RAG
— ดู confidential_rag.py สำหรับเหตุผลที่แยกดัชนี)

**อัปเดต (2026-08-07)**: เดิมไฟล์นี้มี logic เต็มอยู่ในตัวเอง เป็นสคริปต์ standalone ที่ต้องรันมือ
เท่านั้น ไม่เคยถูกเรียกจากที่ไหนในระบบเลย (`archive.py` หลัง Approve ก็ไม่เคยเรียก) ผู้ใช้ขอให้ต่อสาย
Approve → RAG index อัตโนมัติ — ย้าย logic ทั้งหมดไปไว้ที่ `confidential_rag.py::rebuild_index_from_corpus()`
แทน (ให้ `rag_worker/main.py`'s `POST /admin/rebuild_confidential_index` เรียกใช้ร่วมกันได้ ไม่ต้อง
ก็อปโค้ดซ้ำ 2 ที่) ไฟล์นี้เหลือไว้เป็น thin wrapper สำหรับรันมือแบบเดิมเท่านั้น (เผื่อกรณีต้อง
force-rebuild เองโดยไม่ผ่าน backend เช่น debug/แก้ปัญหา)

รันแบบ standalone (เหมือนเดิมทุกประการ):
    venv\\Scripts\\python.exe build_confidential_index.py
"""
import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

import confidential_rag  # noqa: E402


def main() -> None:
    result = confidential_rag.rebuild_index_from_corpus()
    print(result["message"])


if __name__ == "__main__":
    main()
