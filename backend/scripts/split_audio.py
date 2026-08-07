"""split_audio.py — ตัดไฟล์เสียงยาว 1 ไฟล์เป็นไฟล์ย่อยๆ (ดีฟอลต์ 10 นาที + overlap 30 วิ ตรงกับ
production `AUDIO_CHUNK_SECONDS`/`AUDIO_CHUNK_OVERLAP_SECONDS`) เก็บเป็นไฟล์ .wav ถาวรในโฟลเดอร์ที่
เลือกได้ — **ไม่ผ่าน DB/meeting ใดๆทั้งสิ้น** ต่างจาก production path
(`audio_native.transcribe_meeting_audio()`) ที่ตัด chunk ลง `tempfile.TemporaryDirectory()` แล้วลบทิ้ง
อัตโนมัติหลังใช้เสร็จ เพิ่ม 2026-08-05 (session 3.32) ตามที่ผู้ใช้ขอ — มีไว้เพื่อตรวจ/ทดสอบทีละชิ้นเอง
(เช่น ฟังเทียบเนื้อหา, ยิงเข้า `test_rescale_live.py`/`compare_transcription_models.py` ทีละไฟล์)

reuse logic การตัด chunk เดียวกับ production เป๊ะ (`audio_chunking.plan_chunks()`/
`split_into_chunks()`) ไม่มีโค้ดใหม่ที่ต้องดูแลแยกต่างหาก — ต่างกันแค่ปลายทางที่เขียนไฟล์ (ถาวร ไม่ใช่
temp dir ที่ลบทิ้งเอง)

Usage:
    venv\\Scripts\\python.exe scripts\\split_audio.py uploads\\meeting_1.m4a
    venv\\Scripts\\python.exe scripts\\split_audio.py uploads\\meeting_1.m4a --output-dir split_out
    venv\\Scripts\\python.exe scripts\\split_audio.py uploads\\meeting_1.m4a --chunk-seconds 300 --overlap-seconds 15
"""
import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # ให้ import audio_chunking/config ได้
# ไม่ว่าจะรันจาก backend/ หรือ backend/scripts/ ก็ตาม (pattern เดียวกับ compare_transcription_models.py)

import audio_chunking  # noqa: E402
import config  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("audio_path", help="path ไฟล์เสียงยาวที่จะตัด")
    parser.add_argument(
        "--output-dir", default=None,
        help="โฟลเดอร์เก็บไฟล์ที่ตัดแล้ว (ดีฟอลต์: <ชื่อไฟล์ต้นฉบับ>_chunks/ อยู่โฟลเดอร์เดียวกับไฟล์ต้นฉบับ)",
    )
    parser.add_argument(
        "--chunk-seconds", type=int, default=None,
        help=f"ความยาวต่อ chunk วินาที (ดีฟอลต์ตาม config.py = {config.AUDIO_CHUNK_SECONDS}s)",
    )
    parser.add_argument(
        "--overlap-seconds", type=int, default=None,
        help=f"overlap ระหว่าง chunk ที่ติดกัน วินาที (ดีฟอลต์ตาม config.py = {config.AUDIO_CHUNK_OVERLAP_SECONDS}s)",
    )
    args = parser.parse_args()

    # override ค่า config ชั่วคราวถ้าผู้ใช้ระบุมาเอง (สคริปต์นี้รันแยก process จาก backend จริง
    # ไม่กระทบ backend ที่รันอยู่ — ปลอดภัย)
    if args.chunk_seconds is not None:
        config.AUDIO_CHUNK_SECONDS = args.chunk_seconds
    if args.overlap_seconds is not None:
        config.AUDIO_CHUNK_OVERLAP_SECONDS = args.overlap_seconds

    input_path = Path(args.audio_path)
    if not input_path.exists():
        print(f"❌ ไม่พบไฟล์: {input_path}")
        sys.exit(1)

    output_dir = Path(args.output_dir) if args.output_dir else input_path.with_name(f"{input_path.stem}_chunks")
    output_dir.mkdir(parents=True, exist_ok=True)

    duration = audio_chunking.get_duration_seconds(str(input_path))
    plan = audio_chunking.plan_chunks(duration)
    print(f"ไฟล์ต้นฉบับ: {input_path} ({duration:.1f}s / {duration / 60:.1f} นาที)")
    print(
        f"ตัดเป็น {len(plan)} chunk (chunk={config.AUDIO_CHUNK_SECONDS}s, "
        f"overlap={config.AUDIO_CHUNK_OVERLAP_SECONDS}s) → {output_dir}/\n"
    )

    if len(plan) == 1:
        print("⚠️  ไฟล์นี้สั้นกว่า 1 chunk อยู่แล้ว — ไม่ตัดเลย (เหมือนพฤติกรรม production ที่ไม่ chunk ไฟล์สั้น)")
        return

    chunks = audio_chunking.split_into_chunks(str(input_path), str(output_dir))

    print(f"{'#':<4}{'offset':>10}{'duration':>10}  file")
    print("-" * 60)
    for c in chunks:
        print(f"{c.index + 1:<4}{c.offset_seconds:>10.1f}{c.duration_seconds:>10.1f}  {os.path.basename(c.path)}")

    print(f"\nเสร็จแล้ว — {len(chunks)} ไฟล์ที่ {output_dir}/ (ตั้งใจไม่ลบเอง ต่างจาก production ที่ใช้ temp dir)")


if __name__ == "__main__":
    main()
