"""
pdf_generation.py — Module 5: แปลง .docx (final, ที่ Maker แก้ไข/เพิ่มตารางธุรกรรมแล้ว) เป็น PDF
แบบใส่รหัสผ่าน (2026-08-03)

**เครื่องมือที่เลือก (ถามผู้ใช้ก่อนผ่าน `AskUserQuestion`)**: เครื่อง Windows ที่รันระบบนี้มี
Microsoft Word ติดตั้งอยู่จริง → ใช้ `docx2pdf` (COM automation ผ่าน Word เอง) แปลง .docx→PDF ได้
คุณภาพสูงสุด ตรงกับต้นฉบับ 100% (ต่างจาก LibreOffice headless ที่บาง formatting อาจเพี้ยนเล็กน้อย)
— **ข้อจำกัดที่รู้อยู่แล้ว**: `docx2pdf` ทำงานได้เฉพาะ Windows + ต้องมี Word ติดตั้งจริงเท่านั้น (ใช้
`win32com` COM automation ข้างใต้) **sandbox นี้ไม่มีทั้ง Windows และ Word ให้รันจริง** — verify ได้
แค่ `py_compile`/`pyflakes` เหมือนโค้ดที่พึ่ง GPU/เบราว์เซอร์ทุกครั้งก่อนหน้านี้ในโปรเจกต์นี้ ผู้ใช้ต้อง
live test บนเครื่องจริงก่อนถือว่าใช้งานได้ (ดู handoff.md "How to resume")

**Password protection**: ใช้ `pypdf` (pure Python, ไม่ต้องพึ่ง qpdf binary ภายนอกเหมือน `pikepdf`)
`user_password` (รหัสที่ต้องกรอกตอนเปิดไฟล์) กับ `owner_password` (คุมสิทธิ์แก้ไข/พิมพ์) ตั้งเป็นค่า
เดียวกันเพื่อความง่ายใน MVP นี้ (ไม่มี concept "เปิดอ่านได้แต่แก้ไม่ได้" แยกจาก "เปิดอ่านไม่ได้เลย" —
ยอมรับความเรียบง่ายนี้เพราะ MVP เน้นแค่กันคนนอกเปิดไฟล์ที่หลุดออกไปโดยไม่ตั้งใจ ไม่ได้เน้น DRM ระดับ
enterprise)

**สถาปัตยกรรม**: ไม่แยกโปรเซส (ต่างจาก rag_worker/audio_worker) เพราะ `docx2pdf`/`pypdf` ไม่มี
native library (torch/faiss) ที่จะชน Windows WINHTTP.dll เหมือนเหตุผลเดิมที่ Module 3 ก็เรียก Gemini
ตรงจากโปรเซส backend เอง — แต่ COM automation ของ Word **บล็อก thread ที่เรียกมันอยู่จนกว่าจะเสร็จ**
(เปิด Word จริงในเบื้องหลัง ไม่ใช่ async) จึงต้องเรียกจาก FastAPI BackgroundTask เท่านั้น (ห้ามเรียกตรง
ใน request handler เหมือนที่ audio processing/minutes generation ทำอยู่แล้ว — ดู main.py's
`_process_meeting_audio_background` สำหรับ pattern เดียวกัน)
"""
import logging
import os

log = logging.getLogger("com_sec.pdf_generation")

GENERATED_DOCS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "generated_docs")


class PdfGenerationError(Exception):
    """ปัญหาระหว่างแปลง docx→PDF หรือใส่รหัสผ่าน — caller (main.py background task) จับแล้วบันทึก
    ลง MeetingApprovalLog/processing_error แทนที่จะปล่อยให้ background task ล้มทั้งก้อนแบบเงียบๆ"""


def convert_docx_to_pdf(docx_path: str, meeting_id: int) -> str:
    """แปลง .docx เป็น PDF (ยังไม่ใส่รหัสผ่าน) ผ่าน Microsoft Word (`docx2pdf`) — ต้องรันบน Windows
    ที่มี Word ติดตั้งจริงเท่านั้น import แบบ lazy (ในฟังก์ชัน ไม่ใช่หัวไฟล์) เพื่อให้ไฟล์นี้ยัง
    `import` ได้บน sandbox/Linux ที่ไม่มี `docx2pdf`/`pywin32` ติดตั้ง (แค่เรียกฟังก์ชันนี้จริงถึงจะ
    fail — สอดคล้องกับที่ requirements.txt marker `sys_platform == "win32"` ไม่ติดตั้ง docx2pdf บน
    Linux อยู่แล้ว)"""
    try:
        from docx2pdf import convert
    except ImportError as e:
        raise PdfGenerationError(
            "ไม่พบ docx2pdf/pywin32 — ฟีเจอร์นี้ต้องรันบน Windows ที่มี Microsoft Word ติดตั้งจริง "
            f"เท่านั้น ({e})"
        ) from e

    os.makedirs(GENERATED_DOCS_DIR, exist_ok=True)
    pdf_path = os.path.join(GENERATED_DOCS_DIR, f"meeting_{meeting_id}_unprotected.pdf")
    try:
        convert(docx_path, pdf_path)
    except Exception as e:  # docx2pdf/win32com ไม่มี exception class เฉพาะทางที่ import ได้ง่ายๆ
        raise PdfGenerationError(f"แปลง .docx เป็น PDF ไม่สำเร็จ (Word COM automation): {e}") from e

    if not os.path.exists(pdf_path):
        raise PdfGenerationError("docx2pdf ไม่ได้ error แต่ไม่พบไฟล์ PDF ผลลัพธ์ — ไม่ทราบสาเหตุ")
    return pdf_path


def protect_pdf(unprotected_pdf_path: str, password: str, meeting_id: int) -> str:
    """ใส่รหัสผ่านลง PDF ด้วย `pypdf` แล้วลบไฟล์ที่ยังไม่ใส่รหัสผ่านทิ้ง (กันไฟล์ไม่มีรหัสผ่านหลงเหลือ
    อยู่ใน generated_docs/ โดยไม่ตั้งใจ) คืน path ของไฟล์ที่ใส่รหัสผ่านแล้ว"""
    from pypdf import PdfReader, PdfWriter

    try:
        reader = PdfReader(unprotected_pdf_path)
        writer = PdfWriter()
        for page in reader.pages:
            writer.add_page(page)
        writer.encrypt(user_password=password, owner_password=password, use_128bit=True)

        protected_path = os.path.join(GENERATED_DOCS_DIR, f"meeting_{meeting_id}_final.pdf")
        with open(protected_path, "wb") as f:
            writer.write(f)
    except Exception as e:
        raise PdfGenerationError(f"ใส่รหัสผ่าน PDF ไม่สำเร็จ: {e}") from e

    try:
        os.remove(unprotected_pdf_path)
    except OSError as e:
        # ไม่ใช่ error ร้ายแรง (ไฟล์ protected สร้างสำเร็จแล้ว) แค่ log เตือนว่ามีไฟล์ไม่มีรหัสผ่าน
        # ค้างอยู่ ต้องลบมือ
        log.warning(f"ลบไฟล์ PDF ที่ยังไม่ใส่รหัสผ่าน ({unprotected_pdf_path}) ไม่สำเร็จ: {e}")

    return protected_path
