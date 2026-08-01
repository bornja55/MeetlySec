# confidential_corpus/

โฟลเดอร์นี้เก็บ BOD Minutes ที่ผ่านการ Approve แล้วเท่านั้น (.docx/.md) — Module 5 (Approval +
Archive) จะ copy ไฟล์มาลงที่นี่หลัง Checker กด Approve (ยังไม่ได้ implement — ดู task.md Module 5)

หลังมีไฟล์ในนี้แล้ว รัน `venv\Scripts\python.exe build_confidential_index.py` เพื่อสร้างดัชนี
FAISS แยก (`confidential_storage/`) ที่ `/query_confidential` endpoint ใช้ค้นหา

**ห้าม commit ไฟล์ในโฟลเดอร์นี้ขึ้น git** (เนื้อหาลับระดับบอร์ด) — เพิ่ม `confidential_corpus/*`
และ `confidential_storage/` ลง .gitignore ถ้า D:\Com Sec ถูก init เป็น git repo ในอนาคต
