"""
email_service.py — Module 5: ส่ง Automated Secure Email (Magic Link) ให้ Board_Member หลัง Checker
Approve (2026-08-03)

ใช้ `smtplib`/`email` มาตรฐานของ Python (ไม่เพิ่ม dependency ใหม่) แทน Microsoft Graph API ตามที่
implementation_plan.md เสนอไว้เดิม ("Microsoft Graph API/SMTP") — เลือก SMTP เพราะ Azure AD ยังไม่
เชื่อมต่อจริงในระบบนี้เลย (ดู auth.py, ยัง mock token ทั้งหมด) จะสลับไปใช้ Graph API ได้ในอนาคตถ้า
เชื่อม Azure AD จริงแล้วโดยไม่กระทบ caller (endpoint เรียกผ่านฟังก์ชัน `send_magic_link_email()` นี้
เท่านั้น ไม่ผูกกับ smtplib โดยตรง)

⚠️ **ยังไม่เคยส่งอีเมลจริงเลยสักครั้ง** (sandbox ไม่มี SMTP server จริงให้ทดสอบ, `.env.example` ยังเป็น
ค่าตัวอย่าง `smtp.example.com`) — verify ได้แค่ py_compile/pyflakes เหมือน docx2pdf ผู้ใช้ต้องตั้งค่า
SMTP จริง (Gmail/Office365/SMTP relay ภายในองค์กร) แล้ว live test เองก่อนถือว่าใช้งานได้จริง
"""
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import config

log = logging.getLogger("com_sec.email_service")


class EmailSendError(Exception):
    """ส่งอีเมลไม่สำเร็จ — caller (main.py background task) จับแล้ว log ต่อไม่ crash ทั้ง flow
    approve (การส่งอีเมลไม่สำเร็จไม่ควรทำให้ PDF ที่ generate ไปแล้ว/archive ที่ทำไปแล้วเสียหาย —
    แค่บันทึกว่าอีเมลฉบับนี้ส่งไม่สำเร็จ ผู้ใช้ต้องส่งซ้ำเอง/ทางอื่นแทน)"""


def is_configured() -> bool:
    """เช็คว่าตั้งค่า SMTP ไว้หรือยัง (ค่า default ใน config.py เป็นค่าว่าง) — ใช้ก่อนพยายามส่งจริง
    กันโยน exception ที่คาดเดาได้อยู่แล้วเปล่าๆ ถ้ายังไม่ได้ตั้งค่า"""
    return bool(config.SMTP_HOST and config.SMTP_FROM_EMAIL)


def send_magic_link_email(
    to_email: str, meeting_number: str, meeting_date_thai: str, magic_link_url: str, pdf_password: str
) -> None:
    """ส่งอีเมลแจ้ง Board_Member ว่ารายงานการประชุมได้รับการอนุมัติแล้ว พร้อม Magic Link (ใช้ได้ครั้ง
    เดียว หมดอายุตาม `config.MAGIC_LINK_EXPIRY_HOURS`) และรหัสผ่านเปิดไฟล์ PDF — ส่งรหัสผ่านในอีเมล
    เดียวกับลิงก์ (ไม่ได้แยกช่องทางส่ง เช่น SMS) **ยอมรับความเสี่ยงนี้ใน MVP** (ดู models.py's
    `final_pdf_password` docstring) เพราะยังไม่มีช่องทางสื่อสารอื่นที่ยืนยันตัวตนได้ในระบบตอนนี้"""
    if not is_configured():
        raise EmailSendError(
            "ยังไม่ได้ตั้งค่า SMTP (SMTP_HOST/SMTP_FROM_EMAIL ว่างอยู่ใน backend/.env) — "
            "ตั้งค่าก่อนแล้วลอง Approve ใหม่ (PDF/archive ที่ทำไปแล้วยังอยู่ ไม่ต้องสร้างซ้ำ)"
        )

    subject = f"[Com Sec] รายงานการประชุมคณะกรรมการบริษัท ครั้งที่ {meeting_number} ได้รับการอนุมัติแล้ว"
    body = (
        f"เรียน กรรมการบริษัท\n\n"
        f"รายงานการประชุมคณะกรรมการบริษัท ครั้งที่ {meeting_number} "
        f"(ประชุมเมื่อวันที่ {meeting_date_thai}) ได้รับการอนุมัติจาก Company Secretary Checker แล้ว\n\n"
        f"กรุณาเปิดเอกสารผ่านลิงก์ด้านล่างนี้ (ใช้ได้ครั้งเดียว หมดอายุภายใน "
        f"{config.MAGIC_LINK_EXPIRY_HOURS} ชั่วโมง):\n{magic_link_url}\n\n"
        f"รหัสผ่านสำหรับเปิดไฟล์ PDF: {pdf_password}\n\n"
        f"หากลิงก์หมดอายุหรือใช้งานไม่ได้ กรุณาติดต่อเลขานุการบริษัทเพื่อขอลิงก์ใหม่\n\n"
        f"อีเมลนี้ส่งโดยระบบอัตโนมัติ Com Sec AI System"
    )

    msg = MIMEMultipart()
    msg["From"] = config.SMTP_FROM_EMAIL
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain", "utf-8"))

    try:
        with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=30) as server:
            if config.SMTP_USE_TLS:
                server.starttls()
            if config.SMTP_USERNAME:
                server.login(config.SMTP_USERNAME, config.SMTP_PASSWORD)
            server.sendmail(config.SMTP_FROM_EMAIL, [to_email], msg.as_string())
    except Exception as e:  # smtplib มี exception หลายชนิด (SMTPException ลูกๆ) ห่อรวมเป็นของเราเอง
        raise EmailSendError(f"ส่งอีเมลไปยัง {to_email} ไม่สำเร็จ: {e}") from e

    log.info(f"ส่ง Magic Link ไปยัง {to_email} สำเร็จ (meeting_number={meeting_number})")
