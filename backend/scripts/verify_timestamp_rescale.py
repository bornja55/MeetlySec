"""verify_timestamp_rescale.py — วัดผลจริงของ `audio_chunking.rescale_chunk_segments()` (เพิ่ม
2026-08-05, session 3.31 — ดู handoff.md/task.md) โดย **replay ผลลัพธ์ Gemini ที่เก็บไว้แล้วจริง** ใน
`model_comparison_results/<clip>/<model>.json` (จาก session 3.26-3.29) เทียบกับความยาวไฟล์จริงที่วัด
ด้วย ffprobe — ไม่เรียก Gemini ใหม่เลย ไม่เปลืองเควตา ไม่ต้องรอเน็ตออก Google

เหตุผลที่เขียนสคริปต์นี้แทนแค่เชื่อคณิตศาสตร์เฉยๆ: ธรรมเนียมโปรเจกต์นี้ (mantra 3) คือ falsify ด้วย
ข้อมูลจริงก่อนเชื่อว่าอะไรใช้ได้ — ข้อมูล Gemini จริงจาก batch test เดิม (session 3.28-3.29) ที่มีอยู่
แล้วบนดิสก์เพียงพอสำหรับพิสูจน์ก่อน/หลัง rescale โดยไม่ต้องทดสอบใหม่บนเครื่องจริงก่อน — ยัง**ไม่ทดแทน**
การทดสอบจริงผ่าน `transcribe_meeting_audio()` เต็ม flow บนเครื่องจริง (สคริปต์นี้ทดสอบแค่ตรรกะ rescale
เดียว ไม่ทดสอบ ffmpeg chunking/Gemini call จริงของ production path)

Usage:
    python scripts/verify_timestamp_rescale.py
    python scripts/verify_timestamp_rescale.py --results-dir model_comparison_results --audio-dir test_audio
"""
import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # ให้ import audio_chunking ได้
# ไม่ว่าจะรันจาก backend/ หรือ backend/scripts/ ก็ตาม (pattern เดียวกับ compare_transcription_models.py)

import audio_chunking  # noqa: E402


def _iter_result_files(results_dir: str):
    """หา (clip_name, model_name, json_path) ทุกคู่ที่เป็นผลลัพธ์ batch test จริง — เฉพาะไฟล์ที่อยู่ใน
    subfolder ของ clip (ข้ามไฟล์ระดับ root ของ results_dir ซึ่งเป็นผลรันเดี่ยวคนละ session ไม่มี
    subfolder คู่กันชัดเจน)"""
    for clip_name in sorted(os.listdir(results_dir)):
        clip_dir = os.path.join(results_dir, clip_name)
        if not os.path.isdir(clip_dir):
            continue
        for fname in sorted(os.listdir(clip_dir)):
            if fname.endswith(".json"):
                yield clip_name, fname[: -len(".json")], os.path.join(clip_dir, fname)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-dir", default="model_comparison_results")
    parser.add_argument("--audio-dir", default="test_audio")
    parser.add_argument(
        "--overshoot-threshold", type=float, default=1.15,
        help="ต้องตรงกับค่าดีฟอลต์ใน audio_chunking.rescale_chunk_segments (1.15 = ต้องเกิน 15%%)",
    )
    args = parser.parse_args()

    rows = []
    for clip_name, model_name, json_path in _iter_result_files(args.results_dir):
        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)
        if not data.get("success") or not data.get("segments"):
            continue

        audio_path = os.path.join(args.audio_dir, f"{clip_name}.wav")
        if not os.path.exists(audio_path):
            print(f"⚠️  ข้าม {clip_name}/{model_name}: ไม่พบไฟล์เสียงต้นฉบับ {audio_path}")
            continue
        actual_duration = audio_chunking.get_duration_seconds(audio_path)

        segments = data["segments"]
        before_max_end = max(seg["end"] for seg in segments)
        before_drift = before_max_end / actual_duration if actual_duration > 0 else None

        rescaled, scale = audio_chunking.rescale_chunk_segments(
            segments, actual_duration, overshoot_threshold=args.overshoot_threshold
        )
        after_max_end = max(seg["end"] for seg in rescaled) if rescaled else 0.0
        after_drift = after_max_end / actual_duration if actual_duration > 0 else None

        rows.append({
            "clip": clip_name,
            "model": model_name,
            "actual_duration": actual_duration,
            "before_drift": before_drift,
            "after_drift": after_drift,
            "rescaled": scale is not None,
            "scale": scale,
        })

    print(f"{'clip':<22}{'model':<24}{'duration':>10}{'drift ก่อน':>12}{'drift หลัง':>12}  แก้แล้ว?")
    print("-" * 92)
    for r in rows:
        before_str = f"{r['before_drift']:.3f}" if r["before_drift"] is not None else "-"
        after_str = f"{r['after_drift']:.3f}" if r["after_drift"] is not None else "-"
        flag = "✅ rescale" if r["rescaled"] else "—"
        print(
            f"{r['clip']:<22}{r['model']:<24}{r['actual_duration']:>10.1f}"
            f"{before_str:>12}{after_str:>12}  {flag}"
        )

    rescaled_rows = [r for r in rows if r["rescaled"]]
    if rescaled_rows:
        before_vals = [r["before_drift"] for r in rescaled_rows]
        after_vals = [r["after_drift"] for r in rescaled_rows]
        print()
        print(
            f"สรุป: {len(rescaled_rows)}/{len(rows)} รายการเข้าเงื่อนไข rescale — drift เฉลี่ยก่อนแก้ "
            f"{sum(before_vals) / len(before_vals):.3f} → หลังแก้ {sum(after_vals) / len(after_vals):.3f} "
            f"(1.0 = ตรงเป๊ะ)"
        )
    else:
        print("\nไม่มีรายการไหนเข้าเงื่อนไข rescale เลย (ทุกอันอยู่ในช่วง threshold หรือ undershoot)")


if __name__ == "__main__":
    main()
