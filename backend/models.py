"""
models.py — SQLAlchemy ORM models สำหรับ Meeting entity (Module 2)

ขอบเขตตอนนี้: แค่ metadata ของการประชุม + สถานะ pipeline การประมวลผลเสียง (Diarization+ASR) —
**ยังไม่รวม** Minutes ที่สร้างจาก Module 3, สถานะ Approval workflow ของ Module 4-5 (Draft/
Pending_Review/Needs_Revision/Approved) ซึ่งเป็นคนละสถานะกับ `Meeting.status` ด้านล่าง (status นี้
คุมแค่ pipeline เสียง ไม่ใช่สถานะเอกสาร) — ตั้งใจแยกกันชัดเจน กัน field เดียวทำหน้าที่ 2 อย่างพร้อมกัน

⚠️ **ยังไม่ได้ทำ**: การเก็บผล transcript ตอนนี้เก็บเป็น JSON ดิบ (`transcript_segments_json`) ตรงจาก
`audio_worker` โดยไม่แปลงเป็นตารางแยก (เช่น `TranscriptSegment` ที่มี speaker+text+timestamp ผูกกัน
เป็น row จริง) — เพียงพอสำหรับ MVP ตอนนี้ ค่อย normalize เป็นตารางจริงถ้าต้อง query/แก้ไขราย segment
บ่อยขึ้นใน Module 3+ (Speaker Mapping UI/transcript edit UI)

**Redesign 2026-08-02 (ดู handoff.md 3.3)**: เดิมเก็บ `diarization_segments_json` +
`asr_chunks_json` แยกกัน 2 คอลัมน์ (เพราะยังไม่ได้ merge ASR chunk-level เข้ากับ speaker segment) —
ตอนนี้ `audio_worker` ตัด ASR ทีละ diarization segment ตรงๆแล้ว (ดู `audio_worker/pipeline.py`)
ผลลัพธ์จึงเป็น `{start, end, speaker, text}` ต่อ segment อยู่แล้ว ไม่ต้องเก็บแยก 2 ชุดอีกต่อไป
"""
import datetime

from db import Base
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

# สถานะ pipeline การประมวลผลเสียงของการประชุม (คนละเรื่องกับสถานะเอกสาร Minutes ของ Module 4-5)
MEETING_STATUSES = ("draft", "uploaded", "processing", "transcribed", "failed")


class Meeting(Base):
    __tablename__ = "meetings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # เลขที่การประชุม ตรงกับชื่อไฟล์ template เช่น "15/2569" (ตัดสินใจ Module 2, `/grill-me` รอบ 3)
    meeting_number: Mapped[str] = mapped_column(String, nullable=False)
    meeting_date: Mapped[datetime.date] = mapped_column(DateTime, nullable=False)
    created_by_user_id: Mapped[str] = mapped_column(String, nullable=False)

    status: Mapped[str] = mapped_column(String, nullable=False, default="draft")
    audio_filename: Mapped[str | None] = mapped_column(String, nullable=True)
    processing_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ผลดิบจาก audio_worker — list ของ {start, end, speaker, text} ต่อ segment (JSON) — ดู warning
    # ที่หัวไฟล์เรื่องยังไม่ normalize เป็นตารางแยก
    transcript_segments_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Speaker Mapping (บังคับ, ตัดสินใจจาก `/grill-me` รอบ 3, ดู handoff.md) — dict JSON
    # {"SPEAKER_00": "ชื่อจริง", ...} จับคู่ speaker label จาก diarization เข้ากับชื่อคน ก่อนอนุญาต
    # สรุปเป็น Minutes ได้ใน Module 3 — เก็บเป็น JSON เหมือน transcript (MVP, ยังไม่ normalize)
    speaker_mapping_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=datetime.datetime.utcnow
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow
    )

    attendees: Mapped[list["MeetingAttendee"]] = relationship(
        back_populates="meeting", cascade="all, delete-orphan"
    )
    agenda_items: Mapped[list["MeetingAgendaItem"]] = relationship(
        back_populates="meeting", cascade="all, delete-orphan", order_by="MeetingAgendaItem.order"
    )


class MeetingAttendee(Base):
    __tablename__ = "meeting_attendees"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    meeting_id: Mapped[int] = mapped_column(ForeignKey("meetings.id"), nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    position: Mapped[str | None] = mapped_column(String, nullable=True)

    meeting: Mapped["Meeting"] = relationship(back_populates="attendees")


class MeetingAgendaItem(Base):
    __tablename__ = "meeting_agenda_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    meeting_id: Mapped[int] = mapped_column(ForeignKey("meetings.id"), nullable=False)
    order: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)

    meeting: Mapped["Meeting"] = relationship(back_populates="agenda_items")
