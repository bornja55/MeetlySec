"""
minutes_schema.py — Pydantic schema สำหรับ Module 3 (Minutes Generation ผ่าน Gemini native
structured output)

ตัดสินใจสำคัญ (2026-08-03, คุยกับผู้ใช้ก่อนเริ่มเขียนโค้ด): เปิดไฟล์ template จริง
`260628 Draft_EMPIRE - BOD Minutes 15-2569 v.5.docx` (ของจริง ไม่ใช่ template ที่มี placeholder —
เป็นตัวอย่างรายงานการประชุมที่เขียนเสร็จแล้ว) พบว่ามีตารางย่อยรายละเอียดธุรกรรม/ตัวเลข/สัดส่วนหุ้น
ที่ซับซ้อนมาก (เช่น มูลค่าธุรกรรม, ร้อยละการถือหุ้นก่อน/หลังทำรายการ, อัตราดอกเบี้ย) — ถามผู้ใช้ผ่าน
`AskUserQuestion` ว่าจะให้ schema พยายาม map ตัวเลข/ตารางเหล่านี้ตรงๆ จาก transcript หรือไม่ (เสี่ยง
AI สร้างตัวเลขผิด/หลอนถ้า transcript พูดตัวเลขไม่ครบ/ไม่ชัด) — **ผู้ใช้เลือกแบบยืดหยุ่น (Recommended)**:
Gemini สร้างแค่ `discussion_summary`/`resolution_status`/`resolution_text` เป็น free text ต่อวาระ
ไม่พยายามแยก field ตัวเลข/ตารางธุรกรรมโดยเฉพาะ — ลดความเสี่ยงหลอนตัวเลข ผู้ใช้ตรวจ/แก้ไขเองตอน
Maker/Checker review ก่อน Approve (ดู task.md Module 4 "Approval Flow") — ถ้าต้องการความละเอียด
ระดับตารางธุรกรรมจริงต้องพิมพ์/แก้ไขเพิ่มเองใน resolution_text หรือรอ Module 4-5 ที่มนุษย์ตรวจทาน

หลักการลดความเสี่ยงหลอนอีกชั้น (ไม่ใช่แค่ schema flexible): agenda_items ที่ส่งเข้า Gemini มาจาก
`MeetingAgendaItem` ที่กรอกไว้ล่วงหน้าก่อนประชุมจริง (ground truth จาก DB) — ให้ Gemini สรุปเนื้อหา/มติ
ของแต่ละวาระที่มีอยู่แล้วเท่านั้น (จับคู่ด้วย agenda_order) ไม่ให้เพิ่มวาระใหม่ขึ้นมาเอง (ป้องกันหลอน
วาระที่ไม่มีจริง) ส่วนข้อมูลที่เป็น ground truth อยู่แล้วจาก DB (ชื่อบริษัท, เลขที่ประชุม, วันที่, รายชื่อ
ผู้เข้าร่วม) **ไม่ให้ Gemini สร้างเลย** — merge เข้าไปทีหลังใน `minutes_generation.py` (ดูฟังก์ชัน
`generate_minutes()`) ตรงจาก DB เสมอ

`chairperson_name` เป็นข้อยกเว้นที่ยอมให้ Gemini ระบุจาก transcript ได้ (ไม่ใช่ตัวเลข/ข้อเท็จจริงทาง
กฎหมาย แค่ระบุว่าใครทำหน้าที่ประธานจากบทสนทนา ซึ่งมักพูดชัดเจนในการเปิดประชุม — ความเสี่ยงหลอนต่ำกว่า
ตัวเลขทางการเงินมาก)
"""
from typing import Literal

from pydantic import BaseModel, Field

RESOLUTION_STATUSES = ("approved", "rejected", "deferred", "acknowledged", "no_resolution")


class AgendaItemMinutes(BaseModel):
    """ผลสรุป 1 วาระ — Gemini กรอกเฉพาะ field เหล่านี้ ไม่สร้าง agenda_order ใหม่เอง (ต้องตรงกับ
    agenda_order ของ MeetingAgendaItem ที่ส่งไปใน prompt เท่านั้น — เช็คใน minutes_generation.py)"""

    agenda_order: int = Field(
        description="ลำดับวาระ ต้องตรงกับเลขลำดับวาระที่ให้มาในรายการวาระการประชุมเท่านั้น "
        "ห้ามสร้างวาระใหม่ที่ไม่มีในรายการ"
    )
    discussion_summary: str = Field(
        description="สรุปเนื้อหาการอภิปรายของวาระนี้จาก transcript เป็นภาษาไทยทางการ "
        "(สำนวนรายงานการประชุม) ห้ามอ้างตัวเลข/มูลค่า/สัดส่วนที่ transcript ไม่ได้พูดถึงชัดเจน "
        "ถ้าไม่มีการอภิปรายในวาระนี้เลย ให้ระบุว่า 'ไม่มีการอภิปรายเพิ่มเติม'"
    )
    resolution_status: Literal[
        "approved", "rejected", "deferred", "acknowledged", "no_resolution"
    ] = Field(
        description="สถานะมติของวาระนี้: approved (อนุมัติ), rejected (ไม่อนุมัติ), "
        "deferred (เลื่อน/ยังไม่ตัดสิน เช่น รอข้อมูลเพิ่มเติม), acknowledged (รับทราบ ไม่ต้องมีมติอนุมัติ "
        "เช่น วาระแจ้งเพื่อทราบ), no_resolution (ไม่มีข้อมูลมติชัดเจนใน transcript)"
    )
    resolution_text: str = Field(
        description="ข้อความมติที่ประชุมแบบเต็ม (ถ้ามี) ตามสำนวนที่ transcript ระบุ เช่น "
        "'ที่ประชุมพิจารณาแล้ว มีมติเป็นเอกฉันท์อนุมัติ...' ถ้าไม่มีมติชัดเจนให้ระบุว่า "
        "'ไม่มีข้อมูลมติที่ชัดเจนจากการประชุม ต้องตรวจสอบเพิ่มเติมก่อนอนุมัติเอกสาร'"
    )


class MinutesGenerationResult(BaseModel):
    """โครงสร้าง JSON ที่ Gemini ต้องตอบกลับ (ผ่าน response_schema) — เฉพาะส่วนที่ต้องมาจากการ
    วิเคราะห์เนื้อหา transcript เท่านั้น ไม่รวมข้อมูล metadata ที่มีอยู่แล้วใน DB (merge ทีหลัง)"""

    chairperson_name: str = Field(
        description="ชื่อผู้ทำหน้าที่ประธานในที่ประชุมนี้ ตามที่ระบุ/อนุมานได้จาก transcript เท่านั้น "
        "ถ้าไม่สามารถระบุได้ชัดเจนให้ตอบว่า '(ไม่สามารถระบุได้จาก transcript)'"
    )
    agenda_items: list[AgendaItemMinutes] = Field(
        description="ผลสรุปของทุกวาระที่ให้มาในรายการวาระการประชุม เรียงตาม agenda_order "
        "ต้องมีจำนวน entry เท่ากับจำนวนวาระที่ให้มาเป๊ะ ห้ามขาดห้ามเกิน"
    )
    other_business_notes: str = Field(
        description="เนื้อหาสำคัญอื่นๆ ที่พบใน transcript ซึ่งไม่ตรงกับวาระใดในรายการที่ให้มาเลย "
        "(เช่น เรื่องอื่นๆ ที่หยิบยกขึ้นมาหารือกลางที่ประชุม) ถ้าไม่มีให้ตอบว่า '(ไม่มี)'"
    )


class MinutesOfMeeting(BaseModel):
    """โครงสร้างเต็มที่เก็บลง `Meeting.minutes_json` — รวม field ที่มาจาก DB ตรงๆ (ground truth,
    ไม่ผ่าน Gemini) เข้ากับผลจาก MinutesGenerationResult (ดู minutes_generation.py::generate_minutes)
    ใช้ schema นี้แค่เพื่อความชัดเจนของโครงสร้าง — เก็บจริงเป็น dict ผ่าน model_dump() ไม่ผูก ORM"""

    company_name: str
    meeting_number: str
    meeting_date: str  # ISO date string จาก DB ตรงๆ
    attendees: list[dict]  # [{"name", "position"}] จาก DB ตรงๆ
    chairperson_name: str  # จาก Gemini (ดู docstring ข้างบน — ยอมรับความเสี่ยงต่ำนี้)
    agenda_items: list[dict]  # [{"agenda_order","description" (จาก DB), "discussion_summary",
    # "resolution_status","resolution_text" (จาก Gemini)}]
    other_business_notes: str
    generated_by_model: str  # ชื่อโมเดล Gemini ที่ตอบสำเร็จจริง (primary หรือ fallback ตัวไหน)
