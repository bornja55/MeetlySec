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
**Module 3 (2026-08-03)**: เพิ่ม `minutes_json`/`minutes_generated_at` เก็บผล Minutes Generation
(`minutes_generation.py::generate_minutes()`) — ยังคง**แยกจาก `status`** เหมือนเดิม (status นี้คุม
แค่ pipeline เสียง) และยังไม่ใช่สถานะ Approval workflow ของ Module 4-5 (Draft/Pending_Review/
Needs_Revision/Approved) ซึ่งเป็นคนละ field ที่ต้องเพิ่มทีหลังตอนสร้าง Module 4-5 จริง — ตอนนี้
"มี minutes_json หรือยัง" คือสถานะเดียวที่มีสำหรับ Module 3 (ยังไม่มี concept ของ "draft minutes"
กับ "final minutes" แยกกัน — สร้างซ้ำแล้วเขียนทับทั้งก้อนเสมอ ตรงกับ pattern ของ
speaker_mapping_json/transcript_segments_json)

**Multi-template (2026-08-03, ต่อจาก Module 4-5 ทันที — ผู้ใช้ถามหลังเห็น template แรกว่าจะรองรับ
การประชุมที่ต้องใช้ form/template อื่นได้อย่างไร)**: เพิ่ม `Meeting.template_name` เก็บว่าการประชุมนี้
เลือกใช้ template ไฟล์ไหนตอนสร้าง (เลือกได้จาก dropdown ตอนสร้างการประชุม, ดู
`docx_generation.TEMPLATE_REGISTRY`) — **ข้อจำกัดที่ตั้งใจไว้**: ทุก template ต้องใช้ context/ตัวแปร
Jinja ชุดเดียวกัน (มาจาก `minutes_json`/Module 3's schema ที่ไม่เปลี่ยน) เปลี่ยนได้แค่ layout/ถ้อยคำ/
หัวเรื่อง ไม่ใช่ชุดข้อมูล — ถ้าต้องการการประชุมที่มีชุดข้อมูลต่างไปจริงๆ (เช่น มติผู้ถือหุ้นที่มี field
ต่างจาก BOD) ต้องขยาย schema/prompt ของ Module 3 เพิ่มด้วย ไม่ใช่แค่เพิ่ม template ไฟล์ใหม่เฉยๆ — เก็บ
`template_name` แยกจาก `approval_status` (คนละเรื่องกันชัดเจน)

**Module 4-5 (2026-08-03, ดู handoff.md session ล่าสุด)**: เพิ่ม approval workflow จริงตามที่ตัดสินใจ
ไว้ใน task.md/implementation_plan.md — สถามคุยกับผู้ใช้ก่อนเขียนโค้ด (`AskUserQuestion`) ได้ข้อสรุป:
1. เปิดไฟล์ template จริงแล้วยืนยันว่าไม่มี placeholder เลย (เป็นรายงานที่เขียนเสร็จสมบูรณ์ มีตาราง
   ธุรกรรม/ตัวเลขซับซ้อน 3 ตาราง) — เลือกสร้าง **template ใหม่ด้วย `docxtpl`** (Jinja tag ในไฟล์
   .docx) เลียนแบบ layout/หัวกระดาษจากไฟล์จริง แทนที่จะพยายาม parse/reuse ไฟล์เดิมตรงๆ (ดู
   `build_minutes_template.py`)
2. Module 3 สร้างแค่ free text ต่อวาระ (`discussion_summary`/`resolution_status`/`resolution_text`)
   ไม่มีตารางตัวเลขธุรกรรม — ผู้ใช้เลือกให้ **Maker ดาวน์โหลด `.docx` ร่างที่ AI สร้าง → แก้ไข/เพิ่ม
   ตาราง-ตัวเลขด้วย Microsoft Word เอง → อัปโหลดกลับเข้าระบบเป็น "final" ก่อนส่ง Checker** (ไม่สร้าง
   table editor ในระบบ) — จึงต้องมี "draft" (`minutes_docx_path`, AI generate) กับ "final"
   (`final_docx_path`, Maker อัปโหลดกลับ) แยกกันชัดเจน คนละไฟล์คนละคอลัมน์
3. เครื่อง Windows มี Microsoft Word ติดตั้งอยู่ → ใช้ `docx2pdf` (COM automation ผ่าน Word) แปลง
   `final_docx_path` เป็น PDF ตอน Checker กด Approve (ดู `pdf_generation.py`) — **sandbox นี้ไม่มี
   Windows/Word ให้รันจริง verify ได้แค่ py_compile/pyflakes เหมือนโค้ดที่พึ่ง GPU/browser ก่อนหน้านี้
   ทุกครั้ง**
4. ยังไม่มีตาราง user/email จริงในระบบ (auth ทั้งหมดยัง mock 4 token คงที่, Azure AD ยังไม่เชื่อม) —
   ผู้ใช้เลือก **เพิ่ม `MeetingAttendee.email` ให้ Maker กรอกเองต่อการประชุม** แทนที่จะรอ Azure AD จริง
   หรือ hardcode อีเมลผ่าน .env — Board Member ที่จะได้รับ Magic Link คือ attendee ที่กรอก email ไว้
   เท่านั้น (attendee ที่ไม่กรอก email จะไม่ได้รับอีเมล ไม่ error)

`approval_status` (Draft/Pending_Review/Needs_Revision/Approved) เป็นคนละ field จาก `status` (audio
pipeline) และคนละ field จาก "มี minutes_json หรือยัง" (Module 3) โดยตั้งใจ — 3 สถานะนี้คุมคนละเรื่อง
กัน ไม่ผสมกันเป็น field เดียวเพื่อกันตรรกะพันกัน (เช่น audio ประมวลผลเสร็จแล้ว (`status=transcribed`)
ไม่ได้แปลว่ามี minutes, มี minutes แล้วไม่ได้แปลว่าเริ่ม approval workflow แล้ว)

**ยังไม่ทำ (บันทึกไว้ตอนสร้าง Module 4-5 นี้)**: versioning ของ approval รอบที่ >1 ใช้
`MeetingApprovalLog` เก็บประวัติทุกรอบ (Draft→Pending_Review→Needs_Revision→Pending_Review→Approved
ได้หลายรอบ) แต่ `final_docx_path`/`final_pdf_path` ยังเป็น "เขียนทับล่าสุดเสมอ" เหมือนไฟล์อื่นๆของ
โปรเจกต์ (ไม่เก็บไฟล์ทุก revision แยก path) — ตรงกับ pattern MVP ของ JSON blob อื่นๆ, `final_pdf_password`
เก็บเป็น plaintext ใน DB (ไม่ hash) เพราะต้องส่งรหัสผ่านจริงกลับให้ Board Member ผ่านอีเมล — ยอมรับความ
เสี่ยงนี้ใน MVP (DB ไฟล์เดียวในเครื่อง ไม่ expose เป็น API ใดๆ) ต้องทบทวนก่อน production จริง
"""
import datetime

from db import Base
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

# สถานะ pipeline การประมวลผลเสียงของการประชุม (คนละเรื่องกับสถานะเอกสาร Minutes ของ Module 4-5)
MEETING_STATUSES = ("draft", "uploaded", "processing", "transcribed", "failed")

# สถานะ Approval workflow ของเอกสาร Minutes (Module 4-5, ตัดสินใจจาก `/grill-me` รอบ 3 — ดู
# handoff.md/task.md) — คนละ field จาก Meeting.status ด้านบนโดยตั้งใจ (ดู docstring หัวไฟล์)
APPROVAL_STATUSES = ("Draft", "Pending_Review", "Needs_Revision", "Approved")


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

    # Minutes Generation (Module 3, ดู minutes_generation.py) — โครงสร้างตรงกับ
    # minutes_schema.py::MinutesOfMeeting เก็บเป็น JSON blob เขียนทับทั้งก้อนเสมอเวลาสร้างใหม่/
    # สร้างซ้ำ (ยังไม่มี versioning/ประวัติการสร้างซ้ำ — MVP เท่านั้น) minutes_generated_at เป็น
    # None จนกว่าจะสร้างสำเร็จครั้งแรก ใช้แสดงผลฝั่ง frontend ว่า "สร้างล่าสุดเมื่อไหร่"
    minutes_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    minutes_generated_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)

    # Multi-template (2026-08-03) — ชื่อ key ใน docx_generation.TEMPLATE_REGISTRY ไม่ใช่ path/filename
    # ตรงๆ (เปลี่ยน filename เบื้องหลังได้โดยไม่กระทบ meeting เก่า) เลือกตอนสร้างการประชุม แก้ทีหลัง
    # ไม่ได้ผ่าน API ตอนนี้ (ตั้งใจ — เปลี่ยน template กลางทางหลังมี minutes ไปแล้วเสี่ยงสับสน)
    template_name: Mapped[str] = mapped_column(String, nullable=False, default="bod_minutes")

    # ── Module 4-5: Word Template Mapping & Approval Workflow (2026-08-03) ──────────────────
    # ดู docstring หัวไฟล์สำหรับที่มาการตัดสินใจแต่ละ field
    approval_status: Mapped[str] = mapped_column(String, nullable=False, default="Draft")
    # path (relative to backend/generated_docs/) ของ .docx ที่ AI ร่างจาก minutes_json ผ่าน
    # docx_generation.py — regenerate ได้เรื่อยๆ ระหว่างยังไม่ submit (เขียนทับของเก่าเสมอ)
    minutes_docx_path: Mapped[str | None] = mapped_column(String, nullable=True)
    # path ของ .docx ฉบับที่ Maker แก้ไข/เพิ่มตารางธุรกรรมด้วย Word แล้วอัปโหลดกลับ — ต้องมีไฟล์นี้
    # ก่อน Checker จึงจะกด Approve ได้ (บังคับใน endpoint)
    final_docx_path: Mapped[str | None] = mapped_column(String, nullable=True)
    # path ของ PDF ที่แปลงจาก final_docx_path ตอน Checker กด Approve (docx2pdf ผ่าน MS Word บน
    # เครื่อง Windows จริง — ดู pdf_generation.py) — ใส่รหัสผ่านด้วย pypdf ก่อนเก็บ
    final_pdf_path: Mapped[str | None] = mapped_column(String, nullable=True)
    # รหัสผ่านเปิด PDF แบบ plaintext (ดู docstring หัวไฟล์ — ยอมรับความเสี่ยงนี้ใน MVP เพราะต้องส่ง
    # รหัสจริงกลับให้ Board Member ทางอีเมล) สร้างครั้งเดียวตอน Approve ต่อ 1 รอบการ approve
    final_pdf_password: Mapped[str | None] = mapped_column(String, nullable=True)

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
    approval_logs: Mapped[list["MeetingApprovalLog"]] = relationship(
        back_populates="meeting", cascade="all, delete-orphan", order_by="MeetingApprovalLog.created_at"
    )
    magic_link_tokens: Mapped[list["MagicLinkToken"]] = relationship(
        back_populates="meeting", cascade="all, delete-orphan"
    )


class MeetingAttendee(Base):
    __tablename__ = "meeting_attendees"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    meeting_id: Mapped[int] = mapped_column(ForeignKey("meetings.id"), nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    position: Mapped[str | None] = mapped_column(String, nullable=True)
    # Module 4-5 (2026-08-03): กรอกเองต่อการประชุม (ตัดสินใจจาก AskUserQuestion — ยังไม่มี
    # ตาราง user/email จริงในระบบ, Azure AD ยังไม่เชื่อม) — attendee ที่มี email จะได้รับ Magic Link
    # หลัง Checker Approve, ที่ไม่กรอกจะถูกข้ามเฉยๆ ไม่ error (ไม่บังคับทุกคนต้องมี email)
    email: Mapped[str | None] = mapped_column(String, nullable=True)

    meeting: Mapped["Meeting"] = relationship(back_populates="attendees")


class MeetingAgendaItem(Base):
    __tablename__ = "meeting_agenda_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    meeting_id: Mapped[int] = mapped_column(ForeignKey("meetings.id"), nullable=False)
    order: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)

    meeting: Mapped["Meeting"] = relationship(back_populates="agenda_items")


class MeetingApprovalLog(Base):
    """Audit trail ของทุกการเปลี่ยนสถานะ approval (Module 4-5) — เก็บทุกรอบตีกลับ/อนุมัติเพื่อ
    compliance (ตัดสินใจจาก `/grill-me` รอบ 3, ดู task.md "เก็บ audit trail ครบทุกรอบตีกลับ") ต่างจาก
    field อื่นๆของโปรเจกต์ที่เขียนทับทั้งก้อนเสมอ — ตารางนี้ **append-only** ไม่มีการแก้/ลบ record เดิม"""

    __tablename__ = "meeting_approval_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    meeting_id: Mapped[int] = mapped_column(ForeignKey("meetings.id"), nullable=False)
    action: Mapped[str] = mapped_column(String, nullable=False)  # "submit_for_review"/"approve"/"reject"
    from_status: Mapped[str] = mapped_column(String, nullable=False)
    to_status: Mapped[str] = mapped_column(String, nullable=False)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)  # บังคับกรอกตอน reject เท่านั้น
    user_id: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=datetime.datetime.utcnow
    )

    meeting: Mapped["Meeting"] = relationship(back_populates="approval_logs")


class MagicLinkToken(Base):
    """Token สำหรับ Magic Link ที่ส่งให้ Board_Member ทางอีเมลหลัง Checker Approve (Module 5) —
    **ตัดสินใจจาก `/scrutinize`** (ดู task.md): ต้องมี expiration + single-use ตั้งแต่ตอนออกแบบ เลย
    มี `expires_at`/`used_at` แยกกันชัดเจน (ดู magic_link.py::verify_and_consume_token()) ต่อ
    attendee 1 คนต่อ 1 รอบ approve คือ 1 token (สร้างใหม่ทุกครั้งที่ approve ซ้ำ ไม่ reuse token เก่า
    ข้ามรอบ)"""

    __tablename__ = "magic_link_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    meeting_id: Mapped[int] = mapped_column(ForeignKey("meetings.id"), nullable=False)
    attendee_email: Mapped[str] = mapped_column(String, nullable=False)
    token: Mapped[str] = mapped_column(String, nullable=False, unique=True, index=True)
    expires_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False)
    used_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=datetime.datetime.utcnow
    )

    meeting: Mapped["Meeting"] = relationship(back_populates="magic_link_tokens")
