"""
gpu_utils.py — ปล่อย VRAM คืนจริง (แก้บั๊ก CRITICAL ที่พบจาก /scrutinize, 2026-08-02)

**บั๊กเดิม**: `diarization.py`/`asr.py` เคยมี `unload_pipeline(pipeline)`/`unload_model(model)` ที่
เรียก `del pipeline`/`del model` ข้างในฟังก์ชันตัวเอง — แต่ `del` แบบนี้ลบแค่ local binding ของ
พารามิเตอร์ในสโคปของฟังก์ชันนั้นเท่านั้น ตัวแปรของฝั่งเรียก (เช่น `pipe` ใน `pipeline.py`) ยังอ้างถึง
object เดิมอยู่ต่อไป refcount ไม่ตกเป็น 0 จริง → `torch.cuda.empty_cache()` เลยไม่มีอะไรให้ปล่อยคืน
จริงๆ (รันได้ไม่ error แต่ VRAM ไม่ได้ถูกปล่อยตามที่ตั้งใจ) — ทำให้ GPU lock ที่ออกแบบไว้ทั้งหมด
(ห้ามมี diarization+ASR ค้างบน VRAM พร้อมกัน) ใช้ไม่ได้จริงแบบเงียบๆ

**แก้ถูกต้อง**: การ `del`/ตัด reference สุดท้ายต้องเกิดที่**สโคปของฝั่งเรียก** (ที่ตัวแปรจริงอาศัยอยู่)
ก่อนเรียกฟังก์ชันนี้ — ดูวิธีใช้ที่ `pipeline.py` (`del pipe` / `del model` ในสโคปตัวเองก่อน แล้วค่อย
เรียก `release_gpu_memory()`)
"""
import gc
import logging

import torch

log = logging.getLogger("audio_worker.gpu")


def release_gpu_memory() -> None:
    """เรียกหลังจากฝั่งเรียก `del`/ตัด reference สุดท้ายของโมเดลในสโคปตัวเองแล้วเท่านั้น —
    ถ้ายังมี reference ค้างอยู่ที่ไหนสักที่ (แม้แต่ในสโคปฟังก์ชันนี้เอง) VRAM จะไม่ถูกปล่อยจริง"""
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()


def log_vram(label: str) -> None:
    """log VRAM ที่ใช้อยู่จริง ณ จุดนี้ — เพิ่มจาก /debug-mantra (2026-08-02) เพื่อ**พิสูจน์**ว่า
    การแก้บั๊ก unload (ดู `pipeline.py`) ปล่อย VRAM คืนจริงหรือไม่ ไม่ใช่แค่เชื่อว่าโค้ดถูก — เทียบ
    ตัวเลขที่ log นี้ ก่อน/หลัง diarization ควรเห็น allocated ตกลงมาใกล้ 0 ก่อนโหลด ASR ถ้าไม่ตก
    แปลว่า release ยังไม่ได้ผลจริง ต้องสืบต่อ"""
    if not torch.cuda.is_available():
        log.info(f"[VRAM] {label}: ไม่มี GPU (CPU mode)")
        return
    allocated = torch.cuda.memory_allocated() / (1024 * 1024)
    reserved = torch.cuda.memory_reserved() / (1024 * 1024)
    log.info(f"[VRAM] {label}: allocated={allocated:.0f}MiB reserved={reserved:.0f}MiB")
