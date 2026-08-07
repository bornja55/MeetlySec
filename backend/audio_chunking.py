"""
audio_chunking.py — ตัดไฟล์เสียงยาวเป็นชิ้นสั้นๆ (chunk) ก่อนส่งเข้า Gemini native audio
transcription เพื่อแก้ปัญหา timestamp drift ตามสัดส่วน (ดู handoff.md session 3.19/3.21, config.py's
AUDIO_CHUNK_SECONDS/AUDIO_CHUNK_OVERLAP_SECONDS สำหรับที่มาแบบเต็ม)

หลักการ (ยืนยันจากหลายแหล่งอิสระที่แก้ปัญหาเดียวกันด้วยวิธีเดียวกัน — Towards Data Science's
production interview-transcription pipeline, pyvideotrans issue #624,
madeyexz/youtube2transcripts): Gemini ประมาณ timestamp ของ segment ที่อยู่ใกล้ต้นไฟล์ได้แม่น แต่ยิ่ง
ไกลจากต้นไฟล์ (เมื่อส่งไฟล์ยาวทีเดียวทั้งไฟล์) ยิ่งคลาดสะสม — ตัดไฟล์เป็นชิ้นสั้นพอ (ดีฟอลต์ 10 นาที)
แล้วให้ Gemini รายงาน timestamp แค่ "สัมพัทธ์ภายใน chunk นั้น" (ซึ่งแม่นเพราะ chunk สั้น) จากนั้นฝั่งเรา
คำนวณ timestamp จริงในไฟล์ต้นฉบับเอง = chunk_offset_seconds + timestamp_สัมพัทธ์ — ไม่พึ่ง Gemini
ประมาณตำแหน่งสัมบูรณ์ในไฟล์ยาวอีกต่อไป

Pattern การเรียก ffmpeg copy มาจาก `audio_worker/ffmpeg_utils.py` (subprocess, ต้องมี ffmpeg ใน PATH
— เครื่องผู้ใช้มีอยู่แล้วเพราะ audio_worker ใช้เหมือนกัน) แต่แยกไฟล์ต่างหากอยู่ใน backend/ เอง ไม่
import ข้ามโปรเซสจาก audio_worker/ เพราะ backend ไม่ควรพึ่งโค้ดที่อาจถูกลบทิ้งในอนาคต (ดู /grill-me
ข้อ 7 ที่ยังไม่ตัดสินใจ — audio_worker/ ยังไม่ถูกลบตอนนี้ แต่ก็ไม่ควรผูกกันไว้โดยไม่จำเป็น)
"""
import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

import config

# ── Checkpoint/resume ต่อ chunk (เพิ่ม 2026-08-05, session 3.32) ────────────────────────────
# ที่มา: ผู้ใช้ทดสอบไฟล์ยาวจริง (11 chunk) เจอ chunk 7 fail (Gemini 503 "high demand" ชั่วคราว)
# พอดีจังหวะเดียวกับ backend process restart (uvicorn `reload=True` — ดู task.md Module 3 หมายเหตุ
# session 3.20 เรื่องความเสี่ยงนี้ที่ผู้ใช้เคยยอมรับไว้ก่อน) ทำให้ 6 chunk แรกที่ transcribe สำเร็จแล้ว
# (เรียก Gemini จริง เปลืองเควตาไปแล้ว) หายไปหมด ต้องเริ่มใหม่ทั้งไฟล์ถ้า retry — ก่อนหน้านี้ไม่มีที่เก็บ
# ความคืบหน้าเลย (`all_chunk_segments` อยู่ในตัวแปร local ของ `transcribe_meeting_audio()` เท่านั้น)
# แก้ด้วยการเขียน checkpoint ลงดิสก์ทุกครั้งที่ 1 chunk สำเร็จ คีย์ด้วย `checkpoint_key` (ฝั่งเรียก
# ส่ง `str(meeting_id)` มา — ดู `main.py::_process_meeting_audio_background`) ให้ retry ครั้งถัดไป
# ข้าม chunk ที่ทำสำเร็จแล้วได้ ไม่ต้องเรียก Gemini ซ้ำ (ประหยัดทั้งเวลาและเควตา)
_CHECKPOINT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "checkpoints")


def _checkpoint_path(checkpoint_key: str) -> str:
    # sanitize กันอักขระแปลกๆ (meeting_id ปกติเป็นเลขล้วนอยู่แล้ว แต่กันไว้เผื่อฝั่งเรียกส่ง key แบบอื่น)
    safe_key = "".join(c for c in str(checkpoint_key) if c.isalnum() or c in "-_") or "_"
    return os.path.join(_CHECKPOINT_DIR, f"{safe_key}.json")


def load_checkpoint(checkpoint_key: str, plan: list[tuple[float, float]]) -> dict | None:
    """โหลด checkpoint เดิมของ `checkpoint_key` นี้ — คืน `None` ถ้าไม่มี, อ่านไม่ได้ (ไฟล์เสีย/ครึ่งๆ
    กลางๆจาก process ถูกฆ่ากลางคันตอนเขียนพอดี — ดู save_checkpoint's atomic write ที่ป้องกันเคสนี้
    อยู่แล้วเป็นส่วนใหญ่ แต่กันเผื่อไว้อีกชั้น) **หรือ `plan` ที่คำนวณใหม่จากไฟล์เสียงตอนนี้ไม่ตรงกับ
    plan ที่บันทึกไว้ตอนนั้น** (เช่น อัปโหลดไฟล์เสียงคนละไฟล์ทับของเดิม หรือปรับ
    `AUDIO_CHUNK_SECONDS`/`AUDIO_CHUNK_OVERLAP_SECONDS` ระหว่างทาง) — plan ไม่ตรงถือว่า checkpoint
    ใช้ไม่ได้เลย ปลอดภัยกว่าเสี่ยง merge segment ผิดชุดกัน (ทน error ±0.5s กันความคลาดจุดทศนิยมของ
    ffprobe เท่านั้น ไม่ใช่ tolerance สำหรับไฟล์ที่ต่างกันจริง)"""
    path = _checkpoint_path(checkpoint_key)
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None
    saved_plan = data.get("plan")
    if not isinstance(saved_plan, list) or len(saved_plan) != len(plan):
        return None
    for saved, current in zip(saved_plan, plan):
        if len(saved) != 2 or abs(saved[0] - current[0]) > 0.5 or abs(saved[1] - current[1]) > 0.5:
            return None
    return data


def save_checkpoint(
    checkpoint_key: str,
    plan: list[tuple[float, float]],
    all_chunk_segments: list[list[dict]],
    models_used: list[str],
    labels_seen: list[str],
) -> None:
    """บันทึกความคืบหน้าหลัง**แต่ละ chunk สำเร็จ** — เขียนแบบ atomic (เขียนไฟล์ `.tmp` ก่อนแล้ว
    `os.replace` เข้าชื่อจริง) กัน checkpoint เสียครึ่งๆกลางๆถ้า process ถูกฆ่าพอดีตอนกำลังเขียน (เคส
    เดียวกับที่ทำให้ต้องมี feature นี้ตั้งแต่แรก — ดูหัวไฟล์)"""
    os.makedirs(_CHECKPOINT_DIR, exist_ok=True)
    path = _checkpoint_path(checkpoint_key)
    tmp_path = path + ".tmp"
    data = {
        "plan": [list(p) for p in plan],
        "all_chunk_segments": all_chunk_segments,
        "models_used": models_used,
        "labels_seen": labels_seen,
    }
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    os.replace(tmp_path, path)


def clear_checkpoint(checkpoint_key: str) -> None:
    """ลบ checkpoint หลังงานสำเร็จครบทุก chunk แล้ว (transcribe เสร็จสมบูรณ์ ไม่ต้อง resume อีกต่อไป)
    — เงียบถ้าไฟล์ไม่มีอยู่แล้ว (ไม่เคย checkpoint เลย เช่นไฟล์สั้นไม่ผ่าน branch นี้)"""
    try:
        os.remove(_checkpoint_path(checkpoint_key))
    except FileNotFoundError:
        pass


class FFmpegError(Exception):
    """ffmpeg/ffprobe คืนค่า non-zero exit code หรือหาไฟล์ไม่เจอใน PATH"""


def _run_ffmpeg(args: list[str]) -> None:
    try:
        result = subprocess.run(
            ["ffmpeg", "-y", *args],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError as e:
        raise FFmpegError(
            "ไม่พบ ffmpeg ใน PATH — ต้องติดตั้งก่อน (เครื่องนี้ควรมีอยู่แล้วถ้าเคยใช้ audio_worker "
            "เดิม — เช็คด้วย `ffmpeg -version` ใน terminal)"
        ) from e
    if result.returncode != 0:
        # ffmpeg พิมพ์รายละเอียด error ไปที่ stderr เสมอ — ตัดมาแค่บรรทัดท้ายๆ กันข้อความยาวเกินไป
        tail = "\n".join(result.stderr.strip().splitlines()[-15:])
        raise FFmpegError(f"ffmpeg exit code {result.returncode}:\n{tail}")


def get_duration_seconds(input_path: str) -> float:
    """เรียก ffprobe หาความยาวไฟล์ต้นฉบับ (วินาที) — ใช้ตัดสินว่าต้อง chunk หรือไม่ (ไฟล์สั้นกว่า
    1 chunk ไม่ต้องตัดเลย คงพฤติกรรมเดิมก่อนมี feature นี้เป๊ะๆ)"""
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                input_path,
            ],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError as e:
        raise FFmpegError("ไม่พบ ffprobe ใน PATH — มากับ ffmpeg ปกติ เช็คการติดตั้งอีกที") from e
    if result.returncode != 0 or not result.stdout.strip():
        raise FFmpegError(f"ffprobe อ่านความยาวไฟล์ไม่ได้: {result.stderr.strip()}")
    return float(result.stdout.strip())


@dataclass
class AudioChunk:
    path: str  # ไฟล์ WAV ชั่วคราวของ chunk นี้ (16kHz mono, re-encode ใหม่ — ดู split_into_chunks)
    offset_seconds: float  # ตำแหน่งเริ่มของ chunk นี้ในไฟล์ต้นฉบับ (ไม่ใช่ 0 เสมอไปหลัง chunk แรก)
    duration_seconds: float  # ความยาวจริงของ chunk นี้ (มาจาก ffmpeg -t ตรงๆ ไม่ใช่ที่ Gemini ประมาณ)
    # — ใช้เป็น ground truth แก้ proportional timestamp drift ใน rescale_chunk_segments()
    index: int  # ลำดับ chunk (0-based) — ใช้ log/บอกความคืบหน้า


def plan_chunks(total_duration_seconds: float) -> list[tuple[float, float]]:
    """คำนวณรายการ (offset_seconds, duration_seconds) ของแต่ละ chunk ตาม
    AUDIO_CHUNK_SECONDS/AUDIO_CHUNK_OVERLAP_SECONDS — แยกออกมาจาก split_into_chunks() ไม่พึ่ง ffmpeg
    จริง เพื่อ unit test ได้ในสภาพแวดล้อมที่ไม่มี ffmpeg (เช่น sandbox ตอน verify โค้ดนี้)

    step = chunk_seconds - overlap_seconds คือระยะห่างระหว่าง offset ของ chunk ที่ติดกัน (ไม่ใช่ความ
    ยาว chunk เอง) เพื่อให้แต่ละ chunk คาบเกี่ยวกับ chunk ก่อนหน้าเป็นเวลา overlap_seconds วินาทีเสมอ
    ไฟล์ที่สั้นกว่า/เท่ากับ 1 chunk คืน chunk เดียวครอบคลุมทั้งไฟล์ (ไม่มี overlap เพราะไม่มี chunk
    ที่สอง)"""
    chunk_seconds = config.AUDIO_CHUNK_SECONDS
    overlap_seconds = config.AUDIO_CHUNK_OVERLAP_SECONDS
    if total_duration_seconds <= chunk_seconds:
        return [(0.0, total_duration_seconds)]

    step = chunk_seconds - overlap_seconds
    plan: list[tuple[float, float]] = []
    offset = 0.0
    while offset < total_duration_seconds:
        duration = min(chunk_seconds, total_duration_seconds - offset)
        plan.append((offset, duration))
        if offset + duration >= total_duration_seconds:
            break
        offset += step
    return plan


def split_into_chunks(audio_path: str, tmp_dir: str) -> list[AudioChunk]:
    """ตัดไฟล์เสียงต้นฉบับ (ฟอร์แมตอะไรก็ได้ที่ ffmpeg เปิดได้) เป็นชิ้นตาม plan_chunks() — re-encode
    เป็น 16kHz mono WAV ทุกชิ้น (**ไม่ใช้ `-c copy`**) เพราะไฟล์ต้นฉบับส่วนใหญ่เป็น container บีบอัด
    (m4a/mp3 เป็นต้น) — ตัดแบบ copy stream ตรงๆ ที่ไม่ตรง keyframe ทำให้ไฟล์ผลลัพธ์เพี้ยน/เปิดไม่ได้
    บางครั้ง (ต่างจาก `audio_worker/ffmpeg_utils.py::extract_chunk()` ที่ใช้ `-c copy` ได้เพราะ input
    เป็น WAV PCM ที่ extract ไว้แล้วเสมอ) — re-encode ช้ากว่าเล็กน้อยแต่ปลอดภัยกว่าแน่นอน (chunk ละ
    ~10 นาที ไม่ได้ช้ามาก) ใช้ `-ss` ก่อน `-i` (input seeking) เพื่อความเร็ว ไม่ต้อง decode ทั้งไฟล์
    ก่อนตัดทุกครั้ง

    หมายเหตุ: ฟังก์ชันนี้ถูกเรียกเฉพาะตอน `plan_chunks()` คืนมากกว่า 1 chunk เท่านั้น (ไฟล์สั้นกว่า
    1 chunk ฝั่งเรียก — `audio_native.py::transcribe_meeting_audio()` — ข้ามการเรียกฟังก์ชันนี้ไปเลย
    ใช้ไฟล์ต้นฉบับตรงๆ กัน re-encode ที่ไม่จำเป็น)"""
    total_duration = get_duration_seconds(audio_path)
    plan = plan_chunks(total_duration)

    chunks = []
    for i, (offset, duration) in enumerate(plan):
        chunk_path = str(Path(tmp_dir) / f"chunk_{i:03d}.wav")
        _run_ffmpeg([
            "-ss", str(offset),
            "-i", audio_path,
            "-t", str(duration),
            "-ar", "16000",
            "-ac", "1",
            "-vn",
            chunk_path,
        ])
        chunks.append(
            AudioChunk(path=chunk_path, offset_seconds=offset, duration_seconds=duration, index=i)
        )
    return chunks


def rescale_chunk_segments(
    segments: list[dict], known_duration_seconds: float, *, overshoot_threshold: float = 1.15
) -> tuple[list[dict], float | None]:
    """แก้ **proportional timestamp drift** (handoff.md session 3.19: Gemini self-report timestamp
    คลาดตามสัดส่วนคงที่ตลอดไฟล์ที่ส่งเข้าไป 1 ครั้ง — ยืนยันจาก batch test จริงข้าม 3 ไฟล์ session
    3.28-3.29 ว่ายังเกิดแม้ในคลิปสั้นแค่ ~10 นาที ไม่ใช่แค่ไฟล์ยาวเป็นชั่วโมง: drift ratio เฉลี่ยของ
    `gemini-3.6-flash` = 1.633, สูงสุด 1.667 — แปลว่าแค่ตัด chunk เป็น 10 นาทีอย่างเดียว **ลดได้แค่
    ขนาดความเสียหายสูงสุดต่อไฟล์ (absolute) ไม่ได้ลดสัดส่วนที่คลาดต่อ chunk เลย (relative)** — บั๊กนี้
    เกิดซ้ำในทุก chunk เท่าๆกัน ไม่ใช่แค่ไฟล์ยาวทั้งไฟล์แบบที่คิดไว้ตอนออกแบบ chunking ครั้งแรก)

    หลักการ: เรารู้ความยาวจริงของ chunk แน่นอน 100% อยู่แล้ว (มาจาก ffmpeg `-t` ตอนตัด/ffprobe ตอนไม่
    ตัด ไม่ใช่ค่าที่ Gemini ประมาณ) ใช้เป็น ground truth ปรับ timestamp ของทุก segment ในสัดส่วน
    เดียวกัน (`ratio = known_duration / observed_max_end`) — สมเหตุสมผลเพราะ session 3.19 พิสูจน์แล้ว
    ว่า drift เป็น**สัดส่วนคงที่ตลอดช่วงที่วัด** (จุดที่นาทีที่ 6 กับนาทีที่ 55 ของไฟล์เดียวกัน ให้ค่า
    ratio ใกล้กันมาก: 1.62 vs 1.675) การ rescale ด้วยตัวคูณเดียวจึงแก้ได้ทั้ง chunk ไม่ใช่แค่ segment
    สุดท้าย

    เงื่อนไข: แก้เฉพาะกรณี **overshoot** (Gemini รายงาน end เกินความยาวจริงมาก ตาม overshoot_threshold
    ดีฟอลต์ 1.15 = เกิน 15%) เท่านั้น — **ไม่แก้กรณี undershoot** (จบก่อนความยาวจริง เช่น
    `gemini-3.1-flash-lite`/`gemini-3.5-flash` บางไฟล์ในผล batch test) เพราะเป็นปัญหาคนละ class:
    undershoot ส่วนใหญ่แปลว่าโมเดลถอดเสียงไม่ครบ (transcription ขาดหายจริง จบก่อนไฟล์จบจริง — ไม่ใช่แค่
    ประมาณเวลาผิดสัดส่วน) การ rescale กรณีนี้จะไปยืดเนื้อหาที่ถอดถูกต้องอยู่แล้วให้ timestamp ผิดเพิ่ม
    แทนที่จะช่วย ไม่แก้ปัญหาเนื้อหาขาดหายที่เป็นต้นเหตุจริงเลย

    คืน `(segments ใหม่ที่ rescale แล้ว — list ใหม่ ไม่แก้ของเดิม, scale_factor ที่ใช้ — None ถ้าไม่ได้
    rescale)` ให้ฝั่งเรียก log ได้ว่าเกิดการแก้ไขจริงหรือไม่ (สำหรับติดตามว่าเกิดถี่แค่ไหนจากการใช้งาน
    จริง — ยังไม่เคย verify กับ Gemini เรียกจริงรอบใหม่ mock/replay ด้วยผลลัพธ์จริงเดิมที่เก็บไว้แล้วใน
    `model_comparison_results/` เท่านั้น ดู `scripts/verify_timestamp_rescale.py`)"""
    if not segments:
        return segments, None
    observed_max_end = max(seg["end"] for seg in segments)
    if observed_max_end <= 0 or observed_max_end <= known_duration_seconds * overshoot_threshold:
        return segments, None
    scale = known_duration_seconds / observed_max_end
    rescaled = [{**seg, "start": seg["start"] * scale, "end": seg["end"] * scale} for seg in segments]
    return rescaled, scale


def merge_chunk_segments(
    all_chunk_segments: list[list[dict]], plan: list[tuple[float, float]]
) -> list[dict]:
    """รวม segment (ปรับเป็น absolute timestamp แล้วโดยฝั่งเรียก — ดู
    `audio_native.py::transcribe_meeting_audio()`) จากแต่ละ chunk เป็น transcript เดียว ตัดซ้ำที่รอย
    overlap ด้วย **midpoint cut** แทนการทำ LLM merge แบบที่ TDS's pipeline ใช้ (ต้องเรียก LLM เพิ่ม
    อีกรอบมา merge ข้อความ ซับซ้อนกว่ามาก + เสี่ยง hallucination ของตัวเอง) — วิธีนี้ง่ายกว่า:
    สำหรับ chunk คู่ที่ติดกัน จุดกึ่งกลางของช่วง overlap (`midpoint`) ให้ chunk ก่อนหน้าเก็บเฉพาะ
    segment ที่เริ่มก่อน midpoint และ chunk ถัดไปเก็บเฉพาะ segment ที่เริ่มตั้งแต่ midpoint เป็นต้นไป
    — รับประกันว่า segment แต่ละอันปรากฏในผลลัพธ์สุดท้ายครั้งเดียว ไม่ต้อง dedup ข้อความซ้ำ

    ⚠️ ข้อจำกัดที่รู้อยู่แล้ว (บันทึกไว้ตรงๆ ไม่ปิดบัง): การตัดตรง midpoint แบบตายตัวเสี่ยงตัดกลาง
    ประโยคได้ถ้าจังหวะพูดคาบเกี่ยวจุดนั้นพอดี — เป็นความเสี่ยง class เดียวกับที่โปรเจกต์นี้เคยเจอมาแล้ว
    ตอนตัด ASR ด้วยเวลาตายตัวใน audio_worker (ดู task.md Module 2 — ตอนนั้น redesign เป็นตัดตาม
    diarization segment แทนเพราะเจอปัญหานี้จริง) ที่นี่ยอมรับความเสี่ยงนี้ไว้ก่อนเพราะ: (1) เกิดได้แค่
    ที่รอย chunk เท่านั้น (ทุก ~9.5 นาที ไม่ใช่ทุก segment เหมือนตอนนั้น) (2) การทำ LLM merge เต็ม
    รูปแบบเพิ่ม complexity/ต้นทุน/ความเสี่ยง hallucination ใหม่มากกว่าที่ประหยัดได้ — ถ้าพบว่าเป็น
    ปัญหาจริงจากการใช้งาน ค่อยพิจารณาขยาย overlap หรือทำ merge step เพิ่มทีหลัง"""
    overlap = config.AUDIO_CHUNK_OVERLAP_SECONDS
    n = len(plan)
    merged: list[dict] = []
    for i, segments in enumerate(all_chunk_segments):
        lower_bound = plan[i][0] + overlap / 2 if i > 0 else None
        upper_bound = plan[i + 1][0] + overlap / 2 if i < n - 1 else None
        for seg in segments:
            if lower_bound is not None and seg["start"] < lower_bound:
                continue
            if upper_bound is not None and seg["start"] >= upper_bound:
                continue
            merged.append(seg)
    # ⚠️ พบบั๊กจริง (2026-08-05, ผู้ใช้รายงาน "นาทีที่ 1-10 หายไปเลย" หลังใช้ chunking รอบแรก —
    # mantra 3 verify ด้วยข้อมูลจริงจาก com_sec.db พบว่า Gemini คืน start_seconds/end_seconds ของ
    # segment ช่วงกลางไฟล์บาง chunk เป็น **หน่วยนาที** (เช่น 1.1, 9.6) แทนที่จะเป็นวินาทีตาม schema
    # (สลับหน่วยกลางคันในการตอบครั้งเดียวกัน — segment ก่อน/หลังช่วงนั้นยังเป็นวินาทีปกติ) เป็นรูปแบบ
    # ใหม่ของบั๊ก timestamp ที่ไม่แม่นของ Gemini เอง (ดู handoff.md 3.19 — คนละอาการกับ proportional
    # drift เดิม แต่ต้นเหตุเดียวกันคือ self-reported timestamp ไม่น่าเชื่อถือ) ตอนแรกใส่ `.sort()`
    # ท้ายนี้เป็น "safety net" (คอมเมนต์เดิม: "Gemini ควรคืนเรียงอยู่แล้ว") — กลับกลายเป็นตัวขยายบั๊ก
    # ให้แย่ลงกว่าเดิมมาก: เพราะ sort เชื่อค่าตัวเลข start ที่ผิดหน่วย (1.1) ไปเรียงแทรกไว้ใกล้ต้นไฟล์
    # (หลัง 0.0 ก่อน 52.4) ทำให้เนื้อหาที่ควรอยู่นาทีที่ ~1-10 ถูกย้ายไปแสดงเป็น timestamp ~0:01-0:09
    # ทั้งหมด (formatSeconds คิดเป็นวินาทีตามที่มันเป็นตัวเลข) กลายเป็นว่า UI มองไม่เห็นเนื้อหาช่วงนั้น
    # เวลา seek เสียงไปนาทีที่ 1-10 จริง (ดูเหมือน "หายไปเลย" ทั้งที่จริงข้อความยังอยู่ครบ แค่ label เวลา
    # ผิด) — **แก้โดยตัด `.sort()` ออกทั้งหมด**: ลำดับที่ Gemini คืนมาใน array (ลำดับการ generate จริง)
    # น่าเชื่อถือกว่าค่าตัวเลข start_seconds/end_seconds เอง เพราะโมเดล transcribe ไปตามลำดับเวลาจริง
    # ในไฟล์เสมอ ต่อให้บางครั้งใส่หน่วยตัวเลขผิด ลำดับที่ส่งออกมาก็ยังถูกต้อง — ไม่ sort เลยจึงคง
    # ลำดับการอ่าน (reading order) ที่ถูกต้องไว้ได้ แม้ค่า timestamp ตัวเลขสำหรับ segment ที่โดนบั๊กนี้
    # จะยังผิดอยู่ (ป้าย MM:SS ที่โชว์จะยังคลาดเคลื่อนสำหรับ segment เหล่านั้น — เป็นข้อจำกัดที่ยังไม่ได้
    # แก้ ดู task.md/handoff.md สำหรับการตัดสินใจว่าจะทำ unit-detection heuristic เพิ่มหรือไม่)
    return merged
