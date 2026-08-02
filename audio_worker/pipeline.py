"""
pipeline.py — orchestrate การประมวลผลไฟล์เสียง 1 ไฟล์: ffmpeg extract → diarization (เต็มไฟล์) →
ปล่อย VRAM → ASR ทีละ diarization segment → ปล่อย VRAM → คืน `transcript_segments` ชุดเดียว

**Redesign 2026-08-02 (ดู handoff.md 3.3)**: เดิมตัด ASR เป็นชิ้นละ 1 ชม. (chunk-level, หยาบ) แยก
จาก diarization segment (fine-grained) แล้วทิ้ง TODO ไว้ว่ายังไม่ได้ merge เข้าด้วยกัน — ตัดสินใจ
แล้ว (ผู้ใช้เลือกเอง ไม่ใช่ heuristic proportional-matching) ให้ตัด ASR ใหม่ทีละ segment ของ
diarization ตรงๆ แม่นยำสุดเพราะทุก segment ผูก speaker อยู่แล้วในตัว ไม่ต้อง align ทีหลังอีกเลย —
แลกกับ transcribe เยอะครั้งขึ้นมาก (segment สั้นๆหลักวินาที แทนที่จะเป็นชิ้นละ 1 ชม.) `asr.py`'s
`transcribe_segments()` รับ diarization segments ตรงๆ แล้วคืน `{start, end, speaker, text}` ต่อ
segment (sub-split เพิ่มถ้า segment ไหนยาวเกิน `ASR_MAX_SEGMENT_SECONDS`) — ผลลัพธ์จึง**เป็น**
`transcript_segments` อยู่แล้วโดยไม่ต้อง merge ขั้นตอนเพิ่มอีก
"""
import os
import threading
import time

import asr
import diarization
import ffmpeg_utils
import gpu_utils
import torch
from worker_config import CPU_FALLBACK_ON_OOM, PROCESSED_DIR

# ล็อกเดียวทั้งโปรเซส — บังคับประมวลผลทีละไฟล์ queue เดียว (ตัดสินใจ Module 2) กันไม่ให้ diarization
# กับ ASR ของงานคนละไฟล์มาแย่ง VRAM กันเองถ้ามี request ซ้อนเข้ามาโดยไม่ได้ตั้งใจ
_pipeline_lock = threading.Lock()
_status_lock = threading.Lock()
_status = {"state": "idle", "current_job": None}


class WorkerBusyError(RuntimeError):
    """worker กำลังประมวลผลไฟล์อื่นอยู่ — แยก exception type ต่างหาก (แก้จาก /scrutinize:
    เดิม main.py เช็คด้วยการ string-match ข้อความไทยใน RuntimeError ธรรมดา ถ้ามีใครแก้ข้อความ
    วันหลังโดยไม่รู้ตัว จะพัง HTTP status code จาก 409 กลายเป็น 500 เงียบๆ)"""


def get_status() -> dict:
    with _status_lock:
        return dict(_status)


def _set_status(state: str, current_job: str | None = None) -> None:
    with _status_lock:
        _status["state"] = state
        _status["current_job"] = current_job


def _pick_device() -> str:
    return "cuda" if torch.cuda.is_available() else "cpu"


def _is_cuda_oom(exc: Exception) -> bool:
    """เช็คแบบกันเหนียว 2 ชั้น: `torch.cuda.OutOfMemoryError` (class จริงตั้งแต่ torch 2.0) +
    เช็คข้อความ fallback เผื่อบาง build/เวอร์ชันคืน RuntimeError ธรรมดาแทน"""
    oom_cls = getattr(torch.cuda, "OutOfMemoryError", None)
    if oom_cls is not None and isinstance(exc, oom_cls):
        return True
    return isinstance(exc, RuntimeError) and "out of memory" in str(exc).lower()


def _run_diarization_stage(wav_path: str) -> list[dict]:
    # หมายเหตุ (แก้บั๊ก CRITICAL จาก /scrutinize, 2026-08-02): ต้อง `del pipe` ใน**สโคปนี้**
    # (ที่ตัวแปร `pipe` อาศัยอยู่จริง) ก่อนเรียก gpu_utils.release_gpu_memory() เท่านั้น VRAM ถึงจะ
    # ถูกปล่อยจริง — เดิมเคยเรียก diarization.unload_pipeline(pipe) ซึ่ง `del` แค่ local parameter
    # ในฟังก์ชันนั้น ไม่ช่วยอะไรเพราะ `pipe` ตัวนี้ยังอ้างถึง object เดิมอยู่ต่อไป
    device = _pick_device()
    try:
        pipe = diarization.load_pipeline(device)
        gpu_utils.log_vram("หลังโหลด diarization")
        try:
            return diarization.run_diarization(pipe, wav_path)
        finally:
            del pipe
            gpu_utils.release_gpu_memory()
            gpu_utils.log_vram("หลังปล่อย diarization")
    except RuntimeError as e:
        if device == "cpu" or not CPU_FALLBACK_ON_OOM or not _is_cuda_oom(e):
            raise
        # ตัดสินใจ Module 2: ถ้า VRAM ไม่พอ ให้ตกไปใช้ CPU อัตโนมัติเป็นตัวเลือกสุดท้าย
        pipe = diarization.load_pipeline("cpu")
        try:
            return diarization.run_diarization(pipe, wav_path)
        finally:
            del pipe
            gpu_utils.release_gpu_memory()


def _run_asr_stage(wav_path: str, segments: list[dict]) -> list[dict]:
    # เหตุผลเดียวกับ _run_diarization_stage ด้านบน — `del model` ต้องอยู่ในสโคปนี้ รับ
    # `segments` (ผลจาก _run_diarization_stage) เข้ามาตรงๆ แทนการตัดชิ้นตายตัวเป็นเวลา — ดู
    # asr.py's transcribe_segments()
    device = _pick_device()
    try:
        model = asr.load_model(device)
        gpu_utils.log_vram("หลังโหลด ASR")
        try:
            return asr.transcribe_segments(model, wav_path, segments)
        finally:
            del model
            gpu_utils.release_gpu_memory()
            gpu_utils.log_vram("หลังปล่อย ASR")
    except RuntimeError as e:
        if device == "cpu" or not CPU_FALLBACK_ON_OOM or not _is_cuda_oom(e):
            raise
        model = asr.load_model("cpu")
        try:
            return asr.transcribe_segments(model, wav_path, segments)
        finally:
            del model
            gpu_utils.release_gpu_memory()


def process_audio_file(job_id: str, input_path: str) -> dict:
    """จุดเข้าหลักที่ main.py's /process endpoint เรียก — ประมวลผลไฟล์เดียวจบตั้งแต่ต้นจนจบ
    (synchronous, บล็อกจนเสร็จ) คืน dict พร้อม `transcript_segments` ชุดเดียว (แทน
    diarization_segments/asr_chunks แยกกันแบบเดิม — ดู module docstring ด้านบน)"""
    if not _pipeline_lock.acquire(blocking=False):
        raise WorkerBusyError(
            "worker กำลังประมวลผลไฟล์อื่นอยู่ — ตามการตัดสินใจ Module 2 (queue เดียว "
            "ไม่ขนาน) ต้องรอให้งานปัจจุบันเสร็จก่อน"
        )
    try:
        _set_status("processing", job_id)
        t0 = time.time()

        os.makedirs(PROCESSED_DIR, exist_ok=True)
        wav_path = os.path.join(PROCESSED_DIR, f"{job_id}.wav")
        ffmpeg_utils.extract_mono_16k_wav(input_path, wav_path)

        # 1) Diarization บนไฟล์เต็มความยาวก่อนเสมอ (ห้ามตัดชิ้น — กัน Speaker ID ไม่ตรงกันข้ามชิ้น)
        diarization_segments = _run_diarization_stage(wav_path)

        # 2) ASR ทีละ diarization segment ตรงๆ — โหลดหลังจาก diarization ปล่อย VRAM คืนแล้วเท่านั้น
        #    ผลลัพธ์คือ transcript_segments ({start, end, speaker, text}) ชุดสุดท้ายเลย ไม่ต้อง
        #    merge เพิ่มอีกขั้น (ดู module docstring)
        transcript_segments = _run_asr_stage(wav_path, diarization_segments)

        elapsed = time.time() - t0
        return {
            "job_id": job_id,
            "elapsed_seconds": elapsed,
            "transcript_segments": transcript_segments,
        }
    finally:
        _set_status("idle", None)
        _pipeline_lock.release()
