"""
magic_link.py — Module 5: สร้าง/ตรวจสอบ Magic Link token ที่ส่งให้ Board_Member ทางอีเมลหลัง
Checker Approve (2026-08-03)

**ตัดสินใจจาก `/scrutinize`** (ดู task.md Module 4-5): ต้องกำหนด token expiration + single-use
ตั้งแต่ตอนออกแบบ — เก็บเป็นตาราง `MagicLinkToken` แยกต่างหาก (ไม่ใช่ JWT ที่ decode ได้เองโดยไม่ query
DB) เพราะ **single-use ต้องเช็คสถานะจาก DB เสมอ** (JWT ธรรมดา revoke ก่อนหมดอายุไม่ได้ ถ้าไม่มี
denylist แยกอยู่ดี — เก็บ state ใน DB ตรงๆ ง่ายกว่าและตรงไปตรงมากว่าสำหรับ MVP นี้)

**ขอบเขต**: token ผูกกับ (meeting_id, attendee_email) คู่หนึ่งต่อ 1 การ approve — endpoint
`GET /api/magic_link/{token}` (public, ไม่ผ่าน `require_role`/`verify_azure_ad_token` เพราะ
Board_Member เปิดจากอีเมลโดยตรง ไม่มี session login ปกติ) ใช้ `verify_and_consume_token()` ตรวจสอบ
ก่อน serve PDF ทุกครั้ง
"""
import datetime
import secrets

import config
from models import MagicLinkToken, MeetingAttendee
from sqlalchemy.orm import Session

TOKEN_BYTES = 32  # secrets.token_urlsafe(32) ให้ entropy ~256 bit เดายากเกินจะ brute-force ไหว


class MagicLinkError(Exception):
    """token ไม่ถูกต้อง/หมดอายุ/ถูกใช้ไปแล้ว — caller (main.py) แปลงเป็น HTTP 4xx ที่มีความหมาย"""


def create_tokens_for_meeting(db: Session, meeting_id: int, attendees: list[MeetingAttendee]) -> list[MagicLinkToken]:
    """สร้าง token ใหม่ 1 อันต่อ attendee ที่มี email ไม่ว่างเปล่า (attendee ที่ไม่กรอก email ถูกข้าม
    เฉยๆ ไม่ error — ตัดสินใจจาก AskUserQuestion, ดู models.py's MeetingAttendee.email docstring)
    เรียกครั้งเดียวต่อ 1 รอบ Approve (ไม่ reuse token เก่าข้ามรอบ ถ้า approve ซ้ำหลายรอบในอนาคตจะได้
    token ชุดใหม่ทุกครั้ง)"""
    now = datetime.datetime.utcnow()
    expires_at = now + datetime.timedelta(hours=config.MAGIC_LINK_EXPIRY_HOURS)

    tokens: list[MagicLinkToken] = []
    for attendee in attendees:
        email = (attendee.email or "").strip()
        if not email:
            continue
        token_row = MagicLinkToken(
            meeting_id=meeting_id,
            attendee_email=email,
            token=secrets.token_urlsafe(TOKEN_BYTES),
            expires_at=expires_at,
        )
        db.add(token_row)
        tokens.append(token_row)

    db.flush()  # ให้ token_row.id/token พร้อมใช้ก่อน commit จริงที่ caller (ส่งอีเมลต่อ)
    return tokens


def build_magic_link_url(token: str) -> str:
    return f"{config.MAGIC_LINK_BASE_URL.rstrip('/')}/api/magic_link/{token}"


def verify_and_consume_token(db: Session, token: str) -> MagicLinkToken:
    """ตรวจสอบ token แล้ว **mark เป็นใช้แล้วทันที** (single-use) ก่อน caller จะ serve PDF — เรียก
    ครั้งเดียวพอ ไม่ต้องเรียกซ้ำเพื่อเช็คก่อน serve จริงอีกที (ฟังก์ชันนี้ทำทั้งสองอย่างพร้อมกันเพื่อกัน
    race condition ที่อาจเปิดลิงก์ 2 ครั้งพร้อมกันแล้วผ่านทั้งคู่ถ้าแยกเช็ค/mark เป็นคนละขั้นตอน)"""
    token_row = db.query(MagicLinkToken).filter(MagicLinkToken.token == token).first()
    if token_row is None:
        raise MagicLinkError("ลิงก์นี้ไม่ถูกต้อง")
    if token_row.used_at is not None:
        raise MagicLinkError("ลิงก์นี้ถูกใช้ไปแล้ว (ใช้ได้ครั้งเดียวเท่านั้น)")
    if token_row.expires_at < datetime.datetime.utcnow():
        raise MagicLinkError("ลิงก์นี้หมดอายุแล้ว กรุณาติดต่อเลขานุการบริษัทเพื่อขอลิงก์ใหม่")

    token_row.used_at = datetime.datetime.utcnow()
    db.commit()
    return token_row
