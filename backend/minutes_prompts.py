"""
minutes_prompts.py — prompt builder สำหรับ Module 3 (Minutes Generation) แยกออกมาจาก
minutes_generation.py ตาม convention เดียวกับ rag_worker/worker_prompts.py (รวม prompt string
template ไว้ที่เดียว ไม่มี dependency กับ Gemini client ใดๆ — pure string formatting ล้วน
ทำให้ทดสอบ/แก้ถ้อยคำได้โดยไม่ต้องมี API key)
"""


def format_transcript_for_prompt(
    transcript_segments: list[dict], speaker_mapping: dict[str, str]
) -> str:
    """แปลง transcript_segments ({start,end,speaker,text}) เป็นข้อความอ่านง่าย พร้อมชื่อผู้พูดจริง
    (จาก speaker_mapping ที่ต้องครบ 100% แล้วก่อนเรียกฟังก์ชันนี้ — เช็คที่ main.py's endpoint)
    แทน label ดิบ (SPEAKER_00) กัน Gemini สับสนว่าใครพูดอะไร"""
    lines = []
    for seg in transcript_segments:
        speaker_label = seg.get("speaker") or "ไม่ทราบผู้พูด"
        speaker_name = speaker_mapping.get(speaker_label, speaker_label)
        start = seg.get("start", 0)
        mm, ss = divmod(int(start), 60)
        lines.append(f"[{mm:02d}:{ss:02d}] {speaker_name}: {seg.get('text', '')}")
    return "\n".join(lines)


def format_agenda_items_for_prompt(agenda_descriptions: list[str]) -> str:
    """agenda_descriptions คือ list เรียงตาม order จาก MeetingAgendaItem.description (index ใน
    list = agenda_order ตรงตัว ดู models.py — agenda_items ผูก order ตาม index ตอนสร้างใน
    main.py::create_meeting) — เบอร์ลำดับที่ใส่ในนี้ต้องตรงกับ agenda_order ที่ขอให้ Gemini ตอบกลับ"""
    return "\n".join(
        f"{i}. {desc}" for i, desc in enumerate(agenda_descriptions)
    )


def build_minutes_system_prompt(company_name: str) -> str:
    return (
        f"คุณคือผู้ช่วยสรุปรายงานการประชุมคณะกรรมการบริษัทให้กับ {company_name} "
        "หน้าที่ของคุณคือวิเคราะห์บทถอดเสียงการประชุม (transcript) ที่แนบมา แล้วสรุปเนื้อหาการอภิปราย "
        "และมติที่ประชุมของแต่ละวาระที่ระบุไว้ล่วงหน้าเท่านั้น\n\n"
        "กติกาที่สำคัญมาก (ห้ามฝ่าฝืน เพราะเอกสารนี้จะใช้เป็นรายงานการประชุมบอร์ดที่มีผลทางกฎหมาย):\n"
        "1. ห้ามสร้างวาระใหม่ที่ไม่มีในรายการวาระที่ให้มา — ต้องตอบครบทุกวาระที่ให้มาตามลำดับ agenda_order "
        "เป๊ะ ไม่ขาดไม่เกิน\n"
        "2. ห้ามอ้างตัวเลข มูลค่าเงิน สัดส่วนร้อยละ หรือข้อเท็จจริงใดๆ ที่ transcript ไม่ได้พูดถึงอย่าง "
        "ชัดเจน — ถ้า transcript พูดตัวเลขไม่ครบถ้วนหรือไม่ชัดเจน ให้สรุปแบบกว้างๆ โดยไม่ระบุตัวเลขที่ไม่แน่ใจ "
        "แทนการเดา/ประมาณเอง\n"
        "3. ถ้าวาระใดไม่มีการอภิปรายถึงเลยใน transcript ให้ระบุ discussion_summary ว่า "
        "'ไม่มีการอภิปรายเพิ่มเติม' และ resolution_status เป็น 'no_resolution'\n"
        "4. เขียนเป็นภาษาไทยทางการ สำนวนรายงานการประชุม (เช่น 'ที่ประชุมพิจารณาแล้ว มีมติ...') "
        "ไม่ใช้ภาษาพูด/สรุปแบบย่อเกินไป\n"
        "5. เนื้อหานี้เป็นความลับระดับกรรมการบริษัท ห้ามสรุปหรือแต่งเติมเกินกว่าที่ transcript ระบุไว้จริง "
        "โดยเด็ดขาด — เอกสารที่ได้จะต้องผ่านการตรวจสอบจากเลขานุการบริษัท (Maker/Checker) ก่อนใช้จริงเสมอ "
        "ไม่ใช่เอกสารฉบับสมบูรณ์ที่ใช้ได้ทันที\n"
    )


def build_minutes_user_prompt(
    agenda_descriptions: list[str], transcript_segments: list[dict], speaker_mapping: dict[str, str]
) -> str:
    agenda_text = format_agenda_items_for_prompt(agenda_descriptions)
    transcript_text = format_transcript_for_prompt(transcript_segments, speaker_mapping)
    return (
        f"--- รายการวาระการประชุม (agenda_order เริ่มจาก 0 ตามลำดับด้านล่าง) ---\n{agenda_text}\n\n"
        f"--- บทถอดเสียงการประชุมเต็ม (พร้อมชื่อผู้พูดจริงและเวลา) ---\n{transcript_text}\n\n"
        "กรุณาสรุปเนื้อหาการอภิปรายและมติที่ประชุมของแต่ละวาระข้างต้นตามรูปแบบ JSON ที่กำหนด"
    )
