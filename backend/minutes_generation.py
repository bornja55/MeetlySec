"""
minutes_generation.py — เรียก Gemini native structured output (`response_schema`) เพื่อสร้าง
Minutes of Meeting จาก transcript ที่ถอดเสียง+จับคู่ผู้พูดครบแล้ว (Module 3)

สถาปัตยกรรม (ตัดสินใจ 2026-08-03): เรียก Gemini ตรงๆ จากโปรเซส backend เอง ไม่สร้างโปรเซสแยกที่ 3
เพิ่ม (ต่างจาก Module 1/2 ที่แยก rag_worker/audio_worker ออกไป) เพราะเหตุผลที่ต้องแยกโปรเซสเดิม
(กัน Windows WINHTTP.dll crash จาก native library conflict ของ torch/faiss) ไม่เกี่ยวข้องกับที่นี่เลย
— `google-genai` เป็นแค่ REST client บางๆ (httpx ข้างใน) ไม่มี native extension ที่จะชนกัน ใช้
`run_with_fallback()` จาก `llm_fallback.py` (copy จาก `rag_worker/llm_fallback.py` ตรงๆ ไม่แก้ —
ดูหัวไฟล์นั้น) สำหรับ retry+fallback logic ที่ผ่าน unit test มาแล้ว ตามที่ task.md Module 3 ระบุไว้

**ความเสี่ยงหลอนตัวเลข/ข้อมูลที่ไม่มีมูล**: ดู `minutes_schema.py` หัวไฟล์สำหรับการตัดสินใจเต็มเรื่อง
scope ของ schema (คุยกับผู้ใช้ก่อนเขียนโค้ด — เลือกแบบยืดหยุ่น ไม่พยายาม map ตัวเลข/ตารางธุรกรรม
ละเอียดจาก template จริงที่ซับซ้อนมาก)
"""
import logging

import config
from google import genai
from google.genai import types as genai_types
from llm_fallback import run_with_fallback
from minutes_prompts import build_minutes_system_prompt, build_minutes_user_prompt
from minutes_schema import MinutesGenerationResult

log = logging.getLogger("com_sec.minutes_generation")


class MinutesGenerationError(Exception):
    """Gemini เรียกไม่สำเร็จ (ทุกโมเดล primary+fallback ล้มเหลว) หรือตอบกลับไม่ตรง schema/จำนวนวาระ
    ไม่ครบ — main.py จับแล้วแปลงเป็น HTTP 503 ที่มีความหมายให้ frontend (pattern เดียวกับ
    backend/rag.py's RAGWorkerError และ backend/audio.py's AudioWorkerError)"""


def generate_minutes(
    *,
    company_name: str,
    meeting_number: str,
    meeting_date_iso: str,
    attendees: list[dict],
    agenda_items: list[dict],
    transcript_segments: list[dict],
    speaker_mapping: dict[str, str],
) -> dict:
    """เรียก Gemini สรุปเนื้อหา+มติของแต่ละวาระจาก transcript แล้ว merge กับ field ที่เป็น ground
    truth จาก DB (company_name/meeting_number/meeting_date/attendees/agenda descriptions) เข้า
    ด้วยกัน คืน dict พร้อมเก็บลง `Meeting.minutes_json` ตรงๆ (โครงสร้างตรงกับ
    `minutes_schema.py::MinutesOfMeeting`) — raise MinutesGenerationError ถ้า Gemini ล้มเหลวทุก
    โมเดล, ตอบกลับไม่ตรง schema, หรือจำนวน/ลำดับ agenda_items ไม่ตรงกับที่ส่งไป (ป้องกันข้อมูลไม่
    ครบ/ผิดวาระหลุดเข้า DB แบบเงียบๆ)

    agenda_items (2026-08-07, เปลี่ยนจาก `agenda_descriptions: list[str]` เดิม — ดู models.py's
    MeetingAgendaItem.label docstring): list ของ `{label, description}` — **`label` ใช้แค่ตอน merge
    ผลลัพธ์กลับเข้า `minutes_json` เท่านั้น ไม่ส่งเข้า Gemini prompt เลย** (ดู
    `build_minutes_user_prompt` ด้านล่าง: รับแค่ description ล้วน) เพราะเป็นเรื่องการแสดงผล/เลขวาระ
    ที่มนุษย์กำหนดเอง ไม่ใช่เนื้อหาที่ต้องให้ Gemini อ่าน/สรุป"""
    if not config.GOOGLE_API_KEY:
        raise MinutesGenerationError(
            "ไม่พบ GOOGLE_API_KEY ใน backend/.env — ต้องตั้งค่า API key (paid tier ตามที่ตัดสินใจไว้ "
            "เพราะเนื้อหาบอร์ดเป็นความลับสูง ดู .env.example) ก่อนใช้ฟีเจอร์นี้"
        )
    if not agenda_items:
        raise MinutesGenerationError("การประชุมนี้ไม่มีวาระการประชุมเลย ไม่สามารถสรุป Minutes ได้")

    agenda_descriptions = [item["description"] for item in agenda_items]
    system_prompt = build_minutes_system_prompt(company_name)
    user_prompt = build_minutes_user_prompt(agenda_descriptions, transcript_segments, speaker_mapping)

    client = genai.Client(api_key=config.GOOGLE_API_KEY)
    # เก็บชื่อโมเดลที่สำเร็จจริงไว้ (primary หรือ fallback ตัวไหนก็ได้) — run_with_fallback ไม่คืนค่านี้
    # ให้ตรงๆ (คืนแค่ (result, error)) เซ็ตผ่าน closure ตรงจุดที่ call() สำเร็จเท่านั้น
    succeeded_model: dict[str, str | None] = {"name": None}

    def factory(model: str) -> str:
        # ไม่มี state ให้ cache ต่อโมเดล (ต่างจาก llama_index's GoogleGenAI ใน llm_fallback.build_llm
        # ที่ต้อง bind model ตอนสร้าง object) — ส่ง model string ผ่านตรงๆ ให้ call() ใช้เอง
        return model

    def call(model: str) -> MinutesGenerationResult:
        response = client.models.generate_content(
            model=model,
            contents=[system_prompt, user_prompt],
            config=genai_types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=MinutesGenerationResult,
                http_options=genai_types.HttpOptions(timeout=config.GEMINI_MINUTES_TIMEOUT_MS),
            ),
        )
        if response.parsed is None:
            # เกิดได้ถ้า Gemini ตอบ JSON ที่ SDK parse เข้า schema ไม่ได้เป๊ะ (rare — response_schema
            # ควรบังคับรูปแบบให้แล้ว แต่ไม่รับประกัน 100%) raise ต่อให้ run_with_fallback ตัดสินใจ
            # ลองโมเดลถัดไปแทนที่จะคืนผลลัพธ์ที่ใช้ไม่ได้แบบเงียบๆ
            raise MinutesGenerationError(f"Gemini (model={model}) ตอบกลับไม่ตรง schema ที่กำหนด")
        succeeded_model["name"] = model
        return response.parsed

    result, error = run_with_fallback(
        config.GEMINI_MODEL_MINUTES, config.GEMINI_MODEL_MINUTES_FALLBACK,
        factory, call, "[MINUTES]", log=log.info,
    )
    if result is None:
        raise MinutesGenerationError(f"สร้าง Minutes ไม่สำเร็จ (ลองครบทุกโมเดลแล้ว): {error}")

    if len(result.agenda_items) != len(agenda_items):
        raise MinutesGenerationError(
            f"Gemini ตอบจำนวนวาระไม่ตรงกับที่ส่งไป (ส่งไป {len(agenda_items)} วาระ "
            f"ได้ผลกลับมา {len(result.agenda_items)} วาระ) — ปฏิเสธผลลัพธ์นี้กันข้อมูลไม่ครบ/ผิดวาระ"
        )

    # merge ผลจาก Gemini (สรุป+มติต่อวาระ) เข้ากับ description/label ต้นฉบับจาก DB (ground truth) —
    # ใช้ข้อความวาระของจริงจาก DB เสมอ ไม่ใช้ข้อความที่ Gemini อาจ paraphrase มาแทน (label ไม่เคยส่งเข้า
    # Gemini เลยด้วยซ้ำ — ผ่านมาจาก DB ตรงๆ 100%)
    agenda_by_order = {item.agenda_order: item for item in result.agenda_items}
    merged_agenda_items = []
    for order, agenda_item_in in enumerate(agenda_items):
        item = agenda_by_order.get(order)
        if item is None:
            raise MinutesGenerationError(
                f"Gemini ไม่ได้ตอบผลของวาระลำดับที่ {order} "
                f"('{agenda_item_in['description']}') กลับมา"
            )
        merged_agenda_items.append({
            "agenda_order": order,
            "label": agenda_item_in.get("label") or f"วาระที่ {order + 1}",
            "description": agenda_item_in["description"],
            "discussion_summary": item.discussion_summary,
            "resolution_status": item.resolution_status,
            "resolution_text": item.resolution_text,
        })

    return {
        "company_name": company_name,
        "meeting_number": meeting_number,
        "meeting_date": meeting_date_iso,
        "attendees": attendees,
        "chairperson_name": result.chairperson_name,
        "agenda_items": merged_agenda_items,
        "other_business_notes": result.other_business_notes,
        "generated_by_model": succeeded_model["name"],
    }
