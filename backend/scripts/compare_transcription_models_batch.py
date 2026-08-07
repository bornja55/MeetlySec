"""
compare_transcription_models_batch.py — รันเปรียบเทียบโมเดล (เหมือน compare_transcription_models.py
เป๊ะ ต่อไฟล์) กับไฟล์เสียงหลายไฟล์รวดเดียว แล้วรวมผล **timestamp drift ratio** ของแต่ละโมเดลข้ามทุกไฟล์
เป็นตารางสรุปเดียว — ผู้ใช้ขอ (2026-08-05, session 3.28) หลังผลทดสอบรอบแรก (n=1 ไฟล์, ดู handoff.md
3.26-3.27) ขัดกับ research รอบก่อนเรื่อง "Flash Lite แม่นกว่า" — n=1 ไฟล์ยังฟันธงเป็นข้อสรุปทั่วไปไม่ได้
เลยต้องการ sample size มากกว่านี้ก่อนเลือกโมเดล production จริง

**reuse โค้ดจาก compare_transcription_models.py ตรงๆ** (import เป็น module ไม่ copy logic ซ้ำ) —
เรียก `run_comparison()`/`write_results()`/`build_second_by_second_table()`/`write_second_by_second_csv()`
เดิมทุกอย่างต่อไฟล์ แค่วนหลายไฟล์ + เพิ่มขั้นสุดท้ายคำนวณ **drift ratio** (`max(segment end) /
ความยาวไฟล์จริงจาก ffprobe`) ต่อโมเดลต่อไฟล์ แล้วรวมเป็นค่าเฉลี่ย/ต่ำสุด/สูงสุดข้ามไฟล์ทั้งหมด

ผลลัพธ์แต่ละไฟล์แยกโฟลเดอร์ย่อยของตัวเอง (`<output-dir>/<audio_basename>/...` — มี JSON ต่อโมเดล +
`comparison_by_second.csv` เหมือนสคริปต์เดี่ยวทุกประการ) บวกไฟล์สรุปข้ามไฟล์เพิ่มอีก 1 ไฟล์
(`<output-dir>/batch_drift_summary.csv`)

**ต้องรันบนเครื่องจริงของผู้ใช้เท่านั้น** (sandbox ไม่มี network ออก Google เลย — เขียน/verify ได้แค่
logic การรวมผล/คำนวณ drift ratio ผ่าน mock เท่านั้น ไม่เคยยิง Gemini จริงสักครั้ง)

Usage:
    cd backend
    python scripts/compare_transcription_models_batch.py \
        --audio test_audio/meeting_2_last10min.wav test_audio/meeting_1_first10min.wav test_audio/meeting_1_last10min.wav \
        --parallel --delay 1.5
    python scripts/compare_transcription_models_batch.py \
        --audio test_audio/*.wav --models gemini-3.6-flash,gemini-3.5-flash-lite
"""
import argparse
import csv
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import audio_chunking  # noqa: E402
import config  # noqa: E402
import compare_transcription_models as single  # noqa: E402
# ⚠️ import แบบ `compare_transcription_models` ตรงๆ (ไม่ใช่ `scripts.compare_transcription_models`)
# ตั้งใจ — เดิมใช้ `import scripts.compare_transcription_models` (namespace package) รันได้ปกติใน
# sandbox (Linux) แต่พังจริงบนเครื่องผู้ใช้ (Windows): `ModuleNotFoundError: No module named
# 'scripts.compare_transcription_models'` — สาเหตุน่าจะมาจาก Windows filesystem case-insensitive
# ชน namespace package resolution กับโฟลเดอร์อื่นที่ชื่อคล้ายกัน (เช่น venv's `Scripts\` ที่มีอยู่แล้ว
# ทุก virtualenv บน Windows) ทำให้ Python หา submodule ไม่เจอ — เพราะสองไฟล์นี้อยู่โฟลเดอร์เดียวกัน
# (`backend/scripts/`) และ Python ใส่โฟลเดอร์ของสคริปต์หลักลง sys.path[0] ให้อัตโนมัติอยู่แล้วเวลารัน
# ตรงๆ (`python scripts/xxx.py`) จึง import แบบ sibling module ตรงๆได้เลยโดยไม่ต้องพึ่ง namespace
# package เลย — เหมือน `compare_transcription_models.py` เอง import `audio_native` ตรงๆ ไม่มี prefix


def _drift_ratio(result: dict, actual_duration: float) -> float | None:
    """คำนวณ drift ratio ของโมเดลหนึ่งสำหรับไฟล์หนึ่ง — `max(segment end ทั้งหมด) / ความยาวไฟล์จริง`
    ยิ่งเกิน 1.0 มาก ยิ่งแปลว่า timestamp คลาดเคลื่อนสะสมมาก (ค่า 1.0 = ไม่ drift เลย, 1.5 = คลาดไป 50%
    ของความยาวไฟล์จริง) คืน `None` ถ้าโมเดล fail หรือไม่มี segment เลย (คำนวณไม่ได้ ไม่ใช่ 0)"""
    if not result["success"] or not result["segments"]:
        return None
    if actual_duration <= 0:
        return None
    max_end = max(seg["end"] for seg in result["segments"])
    return max_end / actual_duration


def run_batch(
    audio_paths: list[str], model_ids: list[str], *, parallel: bool = False, delay_seconds: float = 0.0,
    output_dir: str = "model_comparison_results", progress=print,
) -> dict[str, list[dict]]:
    """รัน `single.run_comparison()` ต่อไฟล์ (เรียงทีละไฟล์ ไม่ใช่ขนานข้ามไฟล์ — เจตนา: `--parallel`/
    `--delay` ควบคุมแค่ความขนานระหว่างโมเดลภายใน 1 ไฟล์เท่านั้น การยิงหลายไฟล์พร้อมกันจะยิ่งเพิ่มความ
    เสี่ยง rate limit ซ้อนกันแบบคาดเดาไม่ได้ ไม่คุ้มกับเวลาที่ประหยัดได้) เขียนผลลัพธ์เต็มของแต่ละไฟล์ลง
    โฟลเดอร์ย่อยของตัวเอง (mirror `single.main()` เป๊ะ) แล้วคืน dict `{model_id: [{"file", "success",
    "drift_ratio", "elapsed_seconds"}, ...]}` ไว้ให้ `build_aggregate_table()` สรุปต่อ

    หมายเหตุ: ใช้ `audio_chunking.get_duration_seconds()` หาความยาวไฟล์จริงต่อไฟล์ (ไม่ใช้ fallback แบบ
    `single._determine_total_seconds()` เพราะที่นี่ต้องการความยาว "จริง" ล้วนๆ มาคำนวณ drift ratio ไม่ใช่
    แค่จำนวนแถวของตาราง — ถ้า ffprobe ใช้ไม่ได้เลย ข้ามไฟล์นั้นไปทั้งไฟล์ ไม่เดาความยาว)"""
    per_model: dict[str, list[dict]] = {m: [] for m in model_ids}

    for audio_path in audio_paths:
        stem = Path(audio_path).stem
        progress(f"\n{'#' * 80}\n# ไฟล์: {audio_path}\n{'#' * 80}")

        try:
            actual_duration = audio_chunking.get_duration_seconds(audio_path)
        except audio_chunking.FFmpegError as e:
            progress(f"⚠️ ข้ามไฟล์นี้ทั้งไฟล์ — หาความยาวจริงด้วย ffprobe ไม่ได้: {e}")
            continue

        file_output_dir = os.path.join(output_dir, stem)
        results, total_elapsed = single.run_comparison(
            audio_path, model_ids, parallel=parallel, delay_seconds=delay_seconds, progress=progress,
        )
        single.write_results(results, file_output_dir)
        single.print_summary_table(results, total_elapsed)

        total_seconds = int(actual_duration) + 1
        rows, model_ids_out = single.build_second_by_second_table(results, total_seconds)
        single.write_second_by_second_csv(rows, model_ids_out, file_output_dir)

        for r in results:
            per_model[r["model"]].append({
                "file": audio_path,
                "success": r["success"],
                "elapsed_seconds": r["elapsed_seconds"],
                "drift_ratio": _drift_ratio(r, actual_duration),
                "error": r["error"],
            })

    return per_model


def build_aggregate_table(per_model: dict[str, list[dict]]) -> list[dict]:
    """สรุปข้ามไฟล์ต่อโมเดล — จำนวนไฟล์ที่สำเร็จ/ทั้งหมด, drift ratio เฉลี่ย/ต่ำสุด/สูงสุด (เฉพาะไฟล์ที่
    สำเร็จและคำนวณ drift ratio ได้เท่านั้น — โมเดลที่ fail ทุกไฟล์จะได้ mean/min/max เป็น `None`)"""
    rows = []
    for model, runs in per_model.items():
        n_total = len(runs)
        n_success = sum(1 for r in runs if r["success"])
        drifts = [r["drift_ratio"] for r in runs if r["drift_ratio"] is not None]
        rows.append({
            "model": model,
            "success_count": n_success,
            "total_files": n_total,
            "drift_mean": round(sum(drifts) / len(drifts), 3) if drifts else None,
            "drift_min": round(min(drifts), 3) if drifts else None,
            "drift_max": round(max(drifts), 3) if drifts else None,
            "elapsed_mean": round(
                sum(r["elapsed_seconds"] for r in runs if r["success"]) / n_success, 1
            ) if n_success else None,
        })
    return rows


def print_aggregate_table(rows: list[dict]) -> None:
    print(f"\n{'=' * 100}")
    print("สรุป drift ratio ข้ามไฟล์ทั้งหมด (1.0 = ไม่ drift เลย, ยิ่งมากยิ่ง timestamp คลาดเคลื่อนสะสม)")
    print(f"{'=' * 100}")
    header = (
        f"{'Model':<26} {'สำเร็จ':<10} {'Drift เฉลี่ย':<14} {'Drift ต่ำสุด':<14} "
        f"{'Drift สูงสุด':<14} {'เวลาเฉลี่ย(s)':<14}"
    )
    print(header)
    print("-" * len(header))
    for r in rows:
        success_str = f"{r['success_count']}/{r['total_files']}"
        mean_str = f"{r['drift_mean']}" if r["drift_mean"] is not None else "-"
        min_str = f"{r['drift_min']}" if r["drift_min"] is not None else "-"
        max_str = f"{r['drift_max']}" if r["drift_max"] is not None else "-"
        elapsed_str = f"{r['elapsed_mean']}" if r["elapsed_mean"] is not None else "-"
        print(
            f"{r['model']:<26} {success_str:<10} {mean_str:<14} {min_str:<14} "
            f"{max_str:<14} {elapsed_str:<14}"
        )


def write_aggregate_csv(rows: list[dict], output_dir: str) -> str:
    os.makedirs(output_dir, exist_ok=True)
    path = os.path.join(output_dir, "batch_drift_summary.csv")
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "model", "success_count", "total_files", "drift_mean", "drift_min", "drift_max",
            "elapsed_mean",
        ])
        writer.writeheader()
        writer.writerows(rows)
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--audio", required=True, nargs="+",
        help="path ไฟล์เสียงทดสอบ ระบุได้หลายไฟล์ (เว้นวรรคคั่น หรือ glob เช่น test_audio/*.wav)",
    )
    parser.add_argument(
        "--models", default=None,
        help="comma-separated model id (ดีฟอลต์ = ทุกตัวใน config.GEMINI_TRANSCRIPTION_MODEL_CHOICES)",
    )
    parser.add_argument("--parallel", action="store_true", help="ยิงทุกโมเดลพร้อมกัน (ต่อไฟล์)")
    parser.add_argument(
        "--delay", type=float, default=0.0, dest="delay_seconds",
        help="หน่วงกี่วินาทีก่อนเริ่มงานของโมเดลถัดไป (ต่อไฟล์) ดีฟอลต์ 0 = ไม่หน่วง",
    )
    parser.add_argument(
        "--output-dir", default="model_comparison_results",
        help="โฟลเดอร์เก็บผลลัพธ์ — แต่ละไฟล์ได้โฟลเดอร์ย่อยของตัวเอง + สรุปรวม batch_drift_summary.csv",
    )
    args = parser.parse_args()

    if not config.GOOGLE_API_KEY:
        print("ไม่มี GOOGLE_API_KEY ใน backend/.env — ตั้งค่าก่อนใช้งาน")
        sys.exit(1)

    missing = [a for a in args.audio if not os.path.exists(a)]
    if missing:
        print(f"ไม่พบไฟล์: {', '.join(missing)}")
        sys.exit(1)

    if args.models:
        model_ids = [m.strip() for m in args.models.split(",") if m.strip()]
    else:
        model_ids = [m for m, _label in config.GEMINI_TRANSCRIPTION_MODEL_CHOICES]

    if not model_ids:
        print("ไม่มีโมเดลให้ทดสอบเลย (เช็ค --models ว่าใส่ค่าถูกไหม)")
        sys.exit(1)

    print(f"ทดสอบ {len(model_ids)} โมเดล กับ {len(args.audio)} ไฟล์: {', '.join(args.audio)}")
    print(f"โมเดล: {', '.join(model_ids)}")

    per_model = run_batch(
        args.audio, model_ids, parallel=args.parallel, delay_seconds=args.delay_seconds,
        output_dir=args.output_dir,
    )

    aggregate_rows = build_aggregate_table(per_model)
    csv_path = write_aggregate_csv(aggregate_rows, args.output_dir)
    print_aggregate_table(aggregate_rows)

    print(f"\nผลลัพธ์เต็มต่อไฟล์อยู่ที่ {args.output_dir}/<ชื่อไฟล์>/ (JSON ต่อโมเดล + comparison_by_second.csv)")
    print(f"สรุป drift ratio ข้ามไฟล์: {csv_path}")
    print("หมายเหตุ: drift ratio เป็นตัวเลขเชิงปริมาณจาก timestamp ท้าย segment เทียบความยาวไฟล์จริงเท่านั้น")
    print("ไม่ได้วัดความถูกต้องของเนื้อหา (คำผิด/speaker สลับ) ยังต้องอ่าน/ฟัง JSON เทียบเองอยู่ดี")


if __name__ == "__main__":
    main()
