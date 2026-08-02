"""
asr.py — โหลด+รัน typhoon-asr แบบตัดใหม่ทีละ diarization segment (redesign 2026-08-02, ดู
handoff.md 3.3)

ตัดสินใจ: transcribe ทีละ diarization segment ตรงๆ (แม่นยำสุด เพราะไม่ต้อง merge/align ข้อความเข้ากับ
speaker segment ทีหลังอีก — audio_worker คืน `transcript_segments` ชุดเดียวจบ) แลกกับ transcribe เยอะ
ครั้งขึ้นมาก (segment สั้นๆหลักวินาทีต่อครั้ง แทนที่จะเป็นชิ้นละ 1 ชม.) — ตัดทางเลือก
proportional-matching heuristic ทิ้งแล้ว (ผู้ใช้ตัดสินใจเอง ดู handoff.md)

**การกรอง segment ที่ผลลัพธ์ว่างเปล่า (2026-08-02, ดู handoff.md 3.4)**: เดิมลองกรองล่วงหน้าด้วย
duration-heuristic (`ASR_MIN_SEGMENT_SECONDS` สูงๆ ทำนายว่า segment สั้นน่าจะว่าง) — live test พิสูจน์
ว่าใช้ไม่ได้จริง (duration ไม่ correlate กับคุณภาพผลลัพธ์แม่นยำพอ) เปลี่ยนมา**กรองจากผลจริงหลัง
transcribe แล้วแทน** (`transcribe_segments()` drop entry ที่ text ว่างเปล่าหลังโมเดลตอบมา) แม่นยำ
100% เพราะไม่ใช่การเดา — `ASR_MIN_SEGMENT_SECONDS` กลับไปทำหน้าที่แค่กันขอบเขตทางเทคนิค (ffmpeg/model
เจอ input สั้นผิดปกติ) เท่านั้น

⚠️ **หมายเหตุสำคัญที่ยังใช้ได้เหมือนเดิม**: ฟีเจอร์ "timestamp ต่อคำ" ของ
`typhoon-asr/typhoon_asr_inference.py` (ต้นฉบับที่ port มา) **ไม่ใช่ timestamp จริงจากโมเดล** — เป็น
แค่การประมาณเส้นตรง (`audio_duration / จำนวนคำ`) สมมติว่าทุกคำใช้เวลาพูดเท่ากัน โมดูลนี้จึงตั้งใจ
**ไม่ใช้ฟีเจอร์นั้น** และใช้ start/end ของ segment เอง (จาก diarization หรือจาก sub-split คำนวณตรงๆ)
เป็น timestamp แทน ซึ่งแม่นยำกว่า เพราะมาจากการตัดไฟล์เองตามเวลาจริง ไม่ใช่ประมาณ
"""
import logging
import math
import os
import tempfile

import ffmpeg_utils
import torch
from worker_config import ASR_MAX_SEGMENT_SECONDS, ASR_MIN_SEGMENT_SECONDS, TYPHOON_ASR_MODEL_NAME

log = logging.getLogger("audio_worker.asr")


def load_model(device: str):
    """โหลด typhoon-asr (เรียกครั้งเดียวต่อ 1 งาน แล้ว release ด้วย gpu_utils.release_gpu_memory()
    ที่ฝั่งเรียก — ห้ามค้างบน VRAM พร้อมกับ diarization pipeline)"""
    import nemo.collections.asr as nemo_asr

    model = nemo_asr.models.ASRModel.from_pretrained(
        model_name=TYPHOON_ASR_MODEL_NAME,
        map_location=torch.device(device),
    )
    model.eval()
    return model


def _transcribe_wav(model, wav_path: str) -> str:
    with torch.no_grad():
        transcriptions = model.transcribe(audio=[wav_path])
    text = transcriptions[0] if transcriptions else ""
    # NeMo บางเวอร์ชันคืน Hypothesis object แทน str ตรงๆ — กันไว้เผื่อ
    if hasattr(text, "text"):
        text = text.text
    return text


def _split_range(start: float, end: float, max_seconds: int) -> list[tuple[float, float]]:
    """แบ่งช่วง [start, end] เป็นช่วงย่อยยาวเท่าๆกัน ไม่เกิน `max_seconds` ต่อชิ้น (ไม่ใช่ตัดเดินหน้า
    ทีละ max_seconds ตรงๆ ซึ่งจะทำให้ชิ้นสุดท้ายอาจสั้นเกินไปจนความแม่นยำโมเดลตกได้) คืน
    `[(start, end)]` เฉยๆถ้าไม่เกินเพดานอยู่แล้ว"""
    duration = end - start
    if duration <= max_seconds:
        return [(start, end)]

    num_parts = math.ceil(duration / max_seconds)
    part_len = duration / num_parts
    return [(start + k * part_len, start + (k + 1) * part_len) for k in range(num_parts)]


def transcribe_segments(
    model,
    wav_path: str,
    segments: list[dict],
    max_segment_seconds: int = ASR_MAX_SEGMENT_SECONDS,
) -> list[dict]:
    """วนทุก diarization segment (`{start, end, speaker}`) ตัดเสียงเฉพาะช่วงนั้นด้วย
    `ffmpeg_utils.extract_chunk` แล้ว transcribe ต่อชิ้น — ถ้า segment ไหนยาวเกิน
    `max_segment_seconds` (คนพูดยาวต่อเนื่องไม่มีใครขัด) จะถูก `_split_range` แบ่งเป็นหลายชิ้นย่อย
    ก่อน (คง speaker เดิม แบ่งเวลาเท่าๆกัน) แล้ว transcribe แต่ละชิ้นแยกกัน คืน list ของ
    `{start, end, speaker, text}` เรียงตามเวลา — จำนวน entry ที่คืนอาจ**น้อยกว่า**หรือมากกว่า
    `segments` ที่ส่งเข้ามาก็ได้: มากกว่าถ้ามี sub-split เกิดขึ้น, น้อยกว่าถ้า segment ไหนโมเดล
    ตอบข้อความว่างเปล่ากลับมาจริงๆ (drop ทิ้ง ไม่ส่งต่อให้ downstream เห็น entry ที่ไม่มีเนื้อหา)"""
    results = []
    skipped_too_short = 0
    dropped_empty = 0
    with tempfile.TemporaryDirectory(prefix="asr_segments_") as tmp_dir:
        for i, seg in enumerate(segments):
            start = seg["start"]
            end = seg["end"]
            speaker = seg.get("speaker")
            # เกณฑ์ทางเทคนิคเท่านั้น (กัน ffmpeg/model เจอ input สั้นผิดปกติ) — ไม่ใช่ตัวกรองคุณภาพ
            # แล้ว ดู module docstring เรื่องเหตุผลที่เปลี่ยนมากรองจากผลจริงแทน
            if end - start < ASR_MIN_SEGMENT_SECONDS:
                skipped_too_short += 1
                continue

            for j, (sub_start, sub_end) in enumerate(_split_range(start, end, max_segment_seconds)):
                chunk_path = os.path.join(tmp_dir, f"seg_{i:05d}_{j:03d}.wav")
                ffmpeg_utils.extract_chunk(wav_path, chunk_path, sub_start, sub_end - sub_start)
                text = _transcribe_wav(model, chunk_path)
                if not text or not text.strip():
                    # โมเดลไม่ได้ยินคำพูดชัดเจนพอ (มักเป็น artifact จาก diarization clustering
                    # hyperparameter ที่ยังไม่ tune, ดู diarization.py's warning) — drop แทนที่จะคืน
                    # entry ว่างเปล่าที่ไม่มีประโยชน์กับ downstream (Speaker Mapping UI/Module 3)
                    dropped_empty += 1
                    continue
                results.append({
                    "start": sub_start,
                    "end": sub_end,
                    "speaker": speaker,
                    "text": text,
                })

    # log สรุปจำนวนที่ถูกกรอง — เอาไว้เทียบตอนตัดสินใจ tune diarization hyperparameter จริง (ยิ่ง
    # dropped_empty สูงเทียบกับ len(segments) ยิ่งบ่งชี้ว่า clustering ปล่อย segment ขยะออกมาเยอะ)
    log.info(
        f"transcribe_segments: input={len(segments)} segments, output={len(results)} entries, "
        f"skipped_too_short={skipped_too_short}, dropped_empty_text={dropped_empty}"
    )
    return results


# หมายเหตุ: unload ทำผ่าน `del model` ในสโคปของฝั่งเรียก (pipeline.py) แล้วเรียก
# gpu_utils.release_gpu_memory() — ดูคำอธิบายเดียวกันใน diarization.py/gpu_utils.py (แก้บั๊ก
# CRITICAL จาก /scrutinize ไปแล้ว — ไฟล์นี้ไม่มี unload_model() ของตัวเองตั้งแต่ต้น)
