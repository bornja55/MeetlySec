"""
reset_meeting.py — เครื่องมือ maintenance: รีเซ็ต meeting กลับเป็น "failed" (พร้อม re-upload ใหม่)
ล้าง transcript/speaker-mapping/minutes ทิ้ง โดย**ไม่เรียก Gemini เลย** (ไม่เปลืองเควตา)

**ต้องรันบนเครื่องจริงของผู้ใช้ (ไม่ใช่ sandbox)** — เขียนไฟล์ตรงผ่าน SQLite ต้องมี lock/write access
ปกติของเครื่อง Windows ที่ backend รันอยู่จริง (sandbox ที่ mount โฟลเดอร์เข้ามาเจอ "disk I/O error"
เวลาลองเขียนตรงมาก่อนแล้ว — ดู handoff.md session ที่เจอปัญหานี้)

ที่มา (2026-08-05, ดู handoff.md 3.22): meeting ที่ transcribe ผ่าน audio chunking (session 3.21) แล้ว
เจอบั๊ก sort scramble timestamp (แก้โค้ดแล้ว) — segment array เดิมที่บันทึกไว้ก่อนแก้โค้ดมีลำดับผิด
กู้กลับมาให้ถูก 100% ไม่ได้ (ลำดับ generate จริงจาก Gemini ถูกเขียนทับไปแล้วตอน sort) ทดลอง heuristic
กู้คืนด้วยการเดาหน่วย timestamp จาก text length แล้ว — **ไม่น่าเชื่อถือพอ** (แบบหลวมจับของถูกมาพังซ้ำ,
แบบเข้มจับได้แค่ ~30% ของที่เสียจริง) เลยเลือกรีเซ็ตทิ้งแทนตามที่ผู้ใช้ยืนยัน (meeting เป็น test data
ตามธรรมเนียมโปรเจกต์นี้ — ไม่มี Alembic migration, MVP ล้วนๆ ปลอดภัยที่จะรีเซ็ต/ลบ)

**ไม่ลบ audio_filename**: ไฟล์เสียงต้นฉบับยังอยู่ใน uploads/ เหมือนเดิม กด "Re-upload" ใหม่ (เลือกไฟล์
เดิมซ้ำได้เลยจาก uploads/ ถ้าจำชื่อไฟล์ได้ หรือไฟล์ต้นฉบับที่มีอยู่ในเครื่อง) เพื่อ transcribe ใหม่ด้วย
โค้ดที่แก้ sort bug แล้ว — ครั้งนี้จะไม่เจอปัญหา "นาทีหาย" อีก (แต่ยังมีโอกาสเจอ Gemini ใส่หน่วย
timestamp ผิดสำหรับบาง segment เหมือนเดิม เป็นข้อจำกัดที่ยังไม่ได้แก้ ดู task.md)

Usage:
    cd backend
    python scripts/reset_meeting.py <meeting_id>
    python scripts/reset_meeting.py <meeting_id> --yes   # ข้าม confirm prompt
"""
import argparse
import sys
from pathlib import Path

# ให้ import db/models ได้เหมือนรันจาก backend/ ตรงๆ (ปกติรัน `python scripts/reset_meeting.py`
# จาก backend/ อยู่แล้ว แต่กันเผื่อรันจาก path อื่น)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db import SessionLocal  # noqa: E402
from models import Meeting  # noqa: E402

RESET_ERROR_MESSAGE = (
    "รีเซ็ตด้วย scripts/reset_meeting.py (2026-08-05) — transcript เดิมมีลำดับ segment ผิด "
    "(sort scramble bug ใน audio_chunking.py, แก้โค้ดแล้วแต่กู้ข้อมูลเดิมคืนไม่ได้ 100%) "
    "กด Re-upload เพื่อ transcribe ใหม่ด้วยโค้ดที่แก้แล้ว"
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("meeting_id", type=int, help="ID ของ meeting ที่จะรีเซ็ต")
    parser.add_argument(
        "--yes", action="store_true", help="ข้ามการถามยืนยันก่อนเขียน DB จริง"
    )
    args = parser.parse_args()

    db = SessionLocal()
    try:
        meeting = db.get(Meeting, args.meeting_id)
        if meeting is None:
            print(f"ไม่พบ meeting id={args.meeting_id}")
            sys.exit(1)

        print("พบ meeting ที่จะรีเซ็ต:")
        print(f"  id              = {meeting.id}")
        print(f"  meeting_number  = {meeting.meeting_number}")
        print(f"  status ปัจจุบัน   = {meeting.status}")
        print(f"  audio_filename  = {meeting.audio_filename}  (จะไม่ถูกลบ)")
        segs_len = len(meeting.transcript_segments_json or "")
        print(f"  transcript_segments_json ปัจจุบัน = {segs_len} bytes  (จะถูกล้างทิ้ง)")

        if not args.yes:
            answer = input("\nยืนยันรีเซ็ต meeting นี้เป็น 'failed' (ล้าง transcript ทิ้ง)? [y/N] ")
            if answer.strip().lower() != "y":
                print("ยกเลิก ไม่มีการเปลี่ยนแปลงใดๆ")
                return

        meeting.status = "failed"
        meeting.processing_error = RESET_ERROR_MESSAGE
        meeting.transcript_segments_json = None
        meeting.transcription_model_used = None
        meeting.speaker_mapping_json = None
        db.commit()

        print(f"\nรีเซ็ต meeting id={args.meeting_id} เป็น 'failed' เรียบร้อยแล้ว")
        print("ไปที่หน้า dashboard/detail แล้วกด 'Re-upload' เพื่อ transcribe ใหม่ได้เลย")
    finally:
        db.close()


if __name__ == "__main__":
    main()
