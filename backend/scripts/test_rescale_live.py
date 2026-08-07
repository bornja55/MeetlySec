"""test_rescale_live.py — ทดสอบ `audio_chunking.rescale_chunk_segments()` แบบ end-to-end จริงผ่าน
Gemini จริง (เรียก `audio_native.transcribe_meeting_audio()` ตรงๆ — ฟังก์ชันเดียวกับที่
`backend/main.py`'s background task ใช้จริงทุกประการ ไม่ใช่ path ทดลองแยก) เพิ่ม 2026-08-05, session
3.31 (ดู handoff.md/task.md สำหรับที่มาเต็ม)

ต่างจาก `scripts/verify_timestamp_rescale.py` (session 3.31 เดียวกัน) ที่ replay ผลลัพธ์ Gemini เก่าที่
เก็บไว้แล้วโดยไม่เรียก Gemini ใหม่เลย — สคริปต์นี้**เรียก Gemini จริง เปลืองเควตาจริงทุกครั้งที่รัน**
ใช้เพื่อ verify ว่าโค้ด production เต็ม flow (ffmpeg chunking + Gemini call + rescale + merge) ทำงาน
ถูกต้องร่วมกันจริง ไม่ใช่แค่ตรรกะ rescale เดี่ยวๆที่ verify ไปแล้วด้วยข้อมูลเก่า

**รันบนเครื่องจริงเท่านั้น** (ต้องมี venv + ffmpeg ใน PATH + `GOOGLE_API_KEY` จริงใน `backend/.env` —
sandbox เรียก Gemini ไม่ได้เลย ดู handoff.md สำหรับข้อจำกัดนี้)

แนะนำ: ทดสอบไฟล์สั้น (~10 นาที, chunk เดียว) ก่อนเสมอ เพราะเปลืองเควตาแค่ 1 call — ค่อยขยับไปทดสอบไฟล์
ยาวจริง (หลาย chunk) ทีหลังถ้าไฟล์สั้นผ่านแล้ว

Usage:
    venv\\Scripts\\python.exe scripts\\test_rescale_live.py test_audio\\meeting_1_last10min.wav
    venv\\Scripts\\python.exe scripts\\test_rescale_live.py uploads\\meeting_1.m4a --model gemini-3.6-flash
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # ให้ import audio_chunking/audio_native ได้
# ไม่ว่าจะรันจาก backend/ หรือ backend/scripts/ ก็ตาม (pattern เดียวกับ compare_transcription_models.py)

import audio_chunking  # noqa: E402
import audio_native  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("audio_path", help="path ไฟล์เสียงที่จะทดสอบ")
    parser.add_argument(
        "--model", default=None,
        help="ระบุโมเดลเดียว (ไม่งั้นใช้ fallback chain ปกติจาก config.py's GEMINI_MODEL_TRANSCRIPTION)",
    )
    args = parser.parse_args()

    actual_duration = audio_chunking.get_duration_seconds(args.audio_path)
    print(f"ความยาวไฟล์จริง (ffprobe): {actual_duration:.1f}s ({actual_duration / 60:.1f} นาที)")
    if actual_duration > audio_native.config.AUDIO_CHUNK_SECONDS:
        n_chunks = len(audio_chunking.plan_chunks(actual_duration))
        print(f"⚠️  ไฟล์นี้จะถูกตัดเป็น {n_chunks} chunk → เรียก Gemini {n_chunks} ครั้ง (เปลืองเควตาตามนั้น)")
    else:
        print("ไฟล์นี้สั้นกว่า 1 chunk — เรียก Gemini แค่ 1 ครั้ง")
    print("กำลังเรียก transcribe_meeting_audio() จริง (เปลืองเควตา Gemini จริง) ...\n")

    result = audio_native.transcribe_meeting_audio(
        args.audio_path, log=print, model_override=args.model
    )
    segments = result["transcript_segments"]
    max_end = max((seg["end"] for seg in segments), default=0.0)
    drift = max_end / actual_duration if actual_duration > 0 else None

    print()
    print(f"model_used: {result['model_used']}")
    print(f"elapsed: {result['elapsed_seconds']:.1f}s")
    print(f"segment count: {len(segments)}")
    print(f"segment สุดท้าย end={max_end:.1f}s เทียบความยาวไฟล์จริง {actual_duration:.1f}s")
    print(f"drift ratio: {drift:.4f}  (1.0 = ตรงเป๊ะ — ก่อนแก้ session 3.31 เจอสูงถึง 1.6-1.67 ในไฟล์เดียวกันคลาส)")
    if drift is not None and 0.97 <= drift <= 1.05:
        print("✅ อยู่ในช่วงที่ยอมรับได้ — rescale ทำงานถูกต้องกับ Gemini จริง")
    else:
        print(
            "⚠️  ยังคลาดเกินคาด — เช็ค log ด้านบนว่า rescale ทำงานที่ chunk ไหนบ้าง "
            "(บรรทัด '[transcribe] ... แก้ proportional timestamp drift') "
            "ถ้า drift < 1.0 มาก อาจเป็น undershoot (ถอดเสียงไม่ครบ) ซึ่งเป็นปัญหาคนละ class ที่ยังไม่ได้แก้"
        )


if __name__ == "__main__":
    main()
