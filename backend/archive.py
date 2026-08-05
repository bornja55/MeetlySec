"""
archive.py — Module 5: copy ไฟล์ไปยังปลายทาง archive แยก 2 ประเภทตามชั้นความลับ (2026-08-03)

**ตัดสินใจจาก `/grill-me` รอบ 2** (ดู implementation_plan.md/task.md Module 4-5): แยก 2 ปลายทางตาม
ประเภทไฟล์ — (1) `documents_destination`: รายงานฉบับสมบูรณ์ (.docx/PDF) ที่แชร์กับผู้บริหารได้
(2) `recordings_destination`: ไฟล์เสียงต้นฉบับ+transcript **เฉพาะทีม Com Sec เท่านั้น** (Board_Member
เข้าไม่ได้) — ใช้ `shutil.copy2` ไป UNC path/mapped drive ตรงๆ ไม่พึ่ง SharePoint Graph API (ปรับ
ปลายทางได้ผ่าน config ภายหลังโดยไม่ต้องแก้โค้ด)

**ตัดสินใจ (ไม่ได้คุยกับผู้ใช้แยก — execution-only decision)**: ถ้ายังไม่ได้ตั้งค่า
`ARCHIVE_*_DESTINATION` (ค่าว่างเป็นดีฟอลต์ใน config.py) หรือ copy ไม่สำเร็จ (เช่น UNC path ไม่ reachable)
→ **แค่ log warning ไม่ raise exception** เพราะการ archive ไม่ควรเป็นเงื่อนไขที่ทำให้ทั้ง flow Approve
(PDF สร้างสำเร็จ + อีเมลส่งสำเร็จแล้ว) ถูก mark ว่าล้มเหลวไปด้วย — การ archive คือ "nice to have"
เพิ่มเติมจาก compliance ไม่ใช่ transactional กับ approve เอง"""
import logging
import os
import shutil

import config

log = logging.getLogger("com_sec.archive")


def _copy_files(dest_root: str, meeting_id: int, file_paths: list[str], label: str) -> None:
    if not dest_root:
        log.warning(f"{label} ยังไม่ได้ตั้งค่าใน .env — ข้ามการ archive ({label})")
        return

    dest_dir = os.path.join(dest_root, f"meeting_{meeting_id}")
    try:
        os.makedirs(dest_dir, exist_ok=True)
        for path in file_paths:
            if path and os.path.exists(path):
                shutil.copy2(path, dest_dir)
                log.info(f"archive {label}: copy {path} → {dest_dir}")
    except OSError as e:
        # ไม่ raise — UNC path ที่ unreachable ชั่วคราว (VPN หลุด/เครื่องปลายทางปิด) ไม่ควรทำให้
        # ทั้ง flow Approve ล้มเหลว (ดู docstring หัวไฟล์)
        log.warning(f"archive {label} ไป {dest_dir} ไม่สำเร็จ: {e}")


def archive_documents(meeting_id: int, file_paths: list[str]) -> None:
    """รายงานฉบับสมบูรณ์ (.docx/PDF) — ปลายทางที่แชร์กับผู้บริหารได้"""
    _copy_files(config.ARCHIVE_DOCUMENTS_DESTINATION, meeting_id, file_paths, "documents_destination")


def archive_recordings(meeting_id: int, file_paths: list[str]) -> None:
    """ไฟล์เสียง/วิดีโอต้นฉบับ + transcript — ปลายทางที่เข้าถึงได้เฉพาะทีม Com Sec เท่านั้น"""
    _copy_files(config.ARCHIVE_RECORDINGS_DESTINATION, meeting_id, file_paths, "recordings_destination")
