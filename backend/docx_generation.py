"""
docx_generation.py — Module 4: render `Meeting.minutes_json` ลง template ผ่าน `docxtpl` (2026-08-03)

**Multi-template (2026-08-03, ต่อจาก Module 4-5 ทันที)**: `TEMPLATE_REGISTRY` ด้านล่างคือรายการ
template ทั้งหมดที่ระบบรู้จัก (key ตรงกับ `Meeting.template_name`) — เพิ่ม template ใหม่โดยเพิ่ม 1
entry ในนี้ชี้ไปยังไฟล์ `.docx` ใน `templates/` (ดู `build_minutes_template.py` หัวไฟล์สำหรับวิธีสร้าง
ไฟล์ template ใหม่) **ทุก template ต้องใช้ context/Jinja tag ชุดเดียวกัน** (มาจาก `minutes_json` ที่
ไม่เปลี่ยนตาม template) — เปลี่ยนได้แค่ layout/ถ้อยคำ ไม่ใช่ชุดข้อมูล

**ต่อจาก Module 3**: `minutes_json` มีโครงสร้างตรงกับ `minutes_schema.py::MinutesOfMeeting`
(company_name/meeting_number/meeting_date/attendees/chairperson_name/agenda_items/
other_business_notes/generated_by_model) — ฟังก์ชันนี้แปลง dict นั้นเป็น context ที่ตรงกับ Jinja tag
ใน `templates/minutes_template.docx` (ดู `build_minutes_template.py` หัวไฟล์สำหรับรายการ tag เต็ม)
แล้วเซฟเป็นไฟล์ .docx จริงใน `generated_docs/`

**สิ่งที่ไม่ได้มาจาก `minutes_json` ตรงๆ ต้องแปลง/เติมเพิ่มที่นี่**:
- `company_address`: ไม่มีใน `minutes_json` เลย (Module 3's schema ไม่เก็บ) — ใช้ `config.COMPANY_ADDRESS`
  (ค่าว่างได้ถ้าไม่ตั้ง — เอกสารจะแสดงที่อยู่ว่างเปล่า ไม่ error ให้ Maker เติมเองใน Word ทีหลัง)
- `meeting_date_thai`: แปลง ISO date string (ค.ศ.) เป็นข้อความไทยแบบ พ.ศ. (เช่น "29 มิถุนายน 2569")
  ผ่าน `thai_date()` ด้านล่าง — ไม่ใช้ locale ของระบบ (ไม่พึ่ง `locale.setlocale("th_TH")` ที่อาจไม่มี
  ติดตั้งบนเครื่อง Windows ของผู้ใช้) เขียนตาราง mapping เดือนเอง ควบคุมผลลัพธ์ได้แน่นอน
- `agenda_items[].resolution_status_label`: แปล `resolution_status` (enum ภาษาอังกฤษจาก
  `minutes_schema.RESOLUTION_STATUSES`) เป็นข้อความไทยที่อ่านแล้วเป็นธรรมชาติในเอกสารทางการ
- `generated_at_thai`: เวลาที่ generate เอกสาร .docx นี้ (คนละเวลากับ `minutes_generated_at` ของ
  Module 3 ที่เป็นเวลาที่ Gemini สรุปเนื้อหาเสร็จ — ที่นี่คือเวลาที่แปลงเป็น .docx ซึ่งอาจ regenerate
  หลายรอบกว่า minutes_json เดิม)

**ยังไม่ได้ทำ**: ไม่ escape เนื้อหาที่ Gemini สร้างเพื่อกัน Jinja injection (เช่นถ้า transcript มี
ข้อความที่บังเอิญมีรูปแบบคล้าย `{{ }}` หลุดเข้าไปใน `discussion_summary`) — ความเสี่ยงต่ำมากเพราะ
input เป็น free text ภาษาไทยจาก LLM ไม่ใช่ user-controlled template string โดยตรง แต่ `docxtpl`
render เนื้อหาที่ใส่เข้าไปเป็น**ค่า** ไม่ใช่ template ซ้อน template (`{{ item.discussion_summary }}`
คือตัวแปรที่ถูกแทนที่ด้วยค่าตรงๆ ไม่ใช่การ re-parse เนื้อหานั้นเป็น Jinja syntax อีกชั้น) จึงไม่มีช่อง
โหว่ injection จริงอยู่แล้วโดยธรรมชาติของวิธีที่ docxtpl ทำงาน — บันทึกไว้เผื่อมีคนสงสัยทีหลัง
"""
import datetime
import os

import config
from docxtpl import DocxTemplate
from minutes_schema import RESOLUTION_STATUSES

TEMPLATE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates")
GENERATED_DOCS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "generated_docs")

# Multi-template registry — key คือ `Meeting.template_name` ที่เลือกตอนสร้างการประชุม (ดู main.py's
# GET /api/templates ที่ frontend ใช้ populate dropdown) เพิ่ม template ใหม่แค่เพิ่ม entry ตรงนี้
DEFAULT_TEMPLATE_NAME = "bod_minutes"
TEMPLATE_REGISTRY = {
    "bod_minutes": {
        "filename": "minutes_template.docx",
        "label": "รายงานการประชุมคณะกรรมการบริษัท (BOD Minutes)",
    },
    "subcommittee": {
        "filename": "minutes_template_subcommittee.docx",
        "label": "รายงานการประชุมคณะกรรมการชุดย่อย/อนุกรรมการ",
    },
}


def list_templates() -> list[dict]:
    """คืนรายการ template ทั้งหมดสำหรับ frontend dropdown — {name, label} เท่านั้น (ไม่ต้องรู้
    filename ฝั่ง client)"""
    return [{"name": name, "label": meta["label"]} for name, meta in TEMPLATE_REGISTRY.items()]


def _resolve_template_path(template_name: str) -> str:
    meta = TEMPLATE_REGISTRY.get(template_name)
    if meta is None:
        # ชื่อไม่รู้จัก (เช่น meeting เก่าที่ตั้ง template_name ไว้ก่อนจะลบ entry นั้นออกจาก registry
        # ทีหลัง) — fallback เป็น default แทนที่จะ error ทันที ให้ยังสร้างเอกสารได้อยู่
        meta = TEMPLATE_REGISTRY[DEFAULT_TEMPLATE_NAME]
    return os.path.join(TEMPLATE_DIR, meta["filename"])

_THAI_MONTHS = [
    "", "มกราคม", "กุมภาพันธ์", "มีนาคม", "เมษายน", "พฤษภาคม", "มิถุนายน",
    "กรกฎาคม", "สิงหาคม", "กันยายน", "ตุลาคม", "พฤศจิกายน", "ธันวาคม",
]

_RESOLUTION_STATUS_LABELS_TH = {
    "approved": "อนุมัติ",
    "rejected": "ไม่อนุมัติ",
    "deferred": "เลื่อนการพิจารณา",
    "acknowledged": "รับทราบ",
    "no_resolution": "ไม่มีมติที่ชัดเจน — ต้องตรวจสอบเพิ่มเติม",
}
assert set(_RESOLUTION_STATUS_LABELS_TH) == set(RESOLUTION_STATUSES), (
    "resolution_status label ไม่ครบ/ไม่ตรงกับ minutes_schema.RESOLUTION_STATUSES — "
    "ต้องแก้ทั้งสองที่พร้อมกันถ้ามีสถานะใหม่เพิ่มเข้ามา"
)


class DocxGenerationError(Exception):
    """ปัญหาที่เกิดระหว่างการ render/เซฟไฟล์ .docx — caller (main.py) แปลงเป็น HTTP error ต่อ"""


def thai_date(iso_date_str: str) -> str:
    """แปลง ISO date/datetime string (ปี ค.ศ.) เป็นข้อความไทยแบบปี พ.ศ. เช่น '29 มิถุนายน 2569' —
    ไม่พึ่ง locale ของระบบปฏิบัติการ (เขียน mapping เดือนเอง กันปัญหา locale th_TH ไม่ได้ติดตั้งบน
    เครื่อง Windows บางเครื่อง)"""
    date_part = iso_date_str.split("T")[0]
    d = datetime.date.fromisoformat(date_part)
    buddhist_year = d.year + 543
    return f"{d.day} {_THAI_MONTHS[d.month]} {buddhist_year}"


def thai_datetime_now() -> str:
    now = datetime.datetime.now()
    date_text = thai_date(now.date().isoformat())
    return f"{date_text} {now.strftime('%H:%M')} น."


def render_minutes_docx(meeting_id: int, minutes: dict, template_name: str = DEFAULT_TEMPLATE_NAME) -> str:
    """Render `minutes` dict (จาก `json.loads(meeting.minutes_json)`) ลง template ที่เลือกไว้ตอน
    สร้างการประชุม (`Meeting.template_name`) แล้วเซฟเป็นไฟล์ .docx จริง คืนค่า path เต็ม — เขียนทับ
    ไฟล์เดิมของ meeting นี้เสมอถ้าเรียกซ้ำ (regenerate ระหว่างยังไม่ submit ให้ Checker ได้เรื่อยๆ
    ตรงกับ pattern JSON blob อื่นของโปรเจกต์นี้)"""
    template_path = _resolve_template_path(template_name)
    if not os.path.exists(template_path):
        raise DocxGenerationError(
            f"ไม่พบไฟล์ template ที่ {template_path} — ต้องรัน "
            "`python build_minutes_template.py` ก่อนสร้างเอกสารครั้งแรก"
        )

    context = {
        "company_name": minutes.get("company_name", ""),
        "company_address": config.COMPANY_ADDRESS,
        "meeting_number": minutes.get("meeting_number", ""),
        "meeting_date_thai": thai_date(minutes["meeting_date"]),
        "attendees": minutes.get("attendees", []),
        "chairperson_name": minutes.get("chairperson_name", "(ไม่สามารถระบุได้จาก transcript)"),
        "agenda_items": [
            {
                "agenda_order": item["agenda_order"],
                "description": item["description"],
                "discussion_summary": item["discussion_summary"],
                "resolution_status_label": _RESOLUTION_STATUS_LABELS_TH.get(
                    item["resolution_status"], item["resolution_status"]
                ),
                "resolution_text": item["resolution_text"],
            }
            for item in minutes.get("agenda_items", [])
        ],
        "other_business_notes": minutes.get("other_business_notes", "(ไม่มี)"),
        "generated_by_model": minutes.get("generated_by_model", "unknown"),
        "generated_at_thai": thai_datetime_now(),
    }

    try:
        tpl = DocxTemplate(template_path)
        tpl.render(context)
    except Exception as e:  # docxtpl ไม่มี exception class เฉพาะทาง — ห่อเป็น error ของเราเอง
        raise DocxGenerationError(f"Render เอกสารไม่สำเร็จ: {e}") from e

    os.makedirs(GENERATED_DOCS_DIR, exist_ok=True)
    dest_path = os.path.join(GENERATED_DOCS_DIR, f"meeting_{meeting_id}_draft.docx")
    tpl.save(dest_path)
    return dest_path
