"""
tune_diarization.py — ค้นหา hyperparameter ของ SpeakerDiarization pipeline เทียบ ground truth จริง
(2026-08-03, สร้างขึ้นหลัง /scrutinize พบว่า manual probing ทีละค่า (threshold 0.7→1.0→0.85) ถึง
เพดานแล้ว — คู่ประธาน(เสียงชาย)+เลขา(เสียงหญิง) ยังถูกรวมเป็น speaker เดียวกันอยู่ทุกค่าที่ลอง ในขณะ
ที่ speaker อื่นๆ over/under-segment สลับกันไปมา สรุปว่าต้อง joint-tune หลายพารามิเตอร์พร้อมกันแทนการ
ขยับทีละตัวด้วยมือ)

ใช้ `pyannote.pipeline.Optimizer` (Optuna ข้างใต้) ค้นหาพร้อมกันทั้ง 5 ค่า ซึ่งประกาศเป็น tunable
`Parameter` อยู่แล้วในซอร์สจริงของ pyannote.audio 3.3.2 (ตรวจสอบแล้วโดยดาวน์โหลด wheel มาอ่านตรงๆ
ไม่ได้เดา — ดู `pyannote/audio/pipelines/speaker_diarization.py` + `clustering.py`):
    - segmentation.threshold        (0.1 - 0.9)
    - segmentation.min_duration_off (0.0 - 1.0)
    - clustering.threshold          (0.0 - 2.0)
    - clustering.method             (categorical: centroid/median/ward/single/complete/average/weighted)
    - clustering.min_cluster_size   (1 - 20 จำนวนเต็ม)

metric ที่ optimize คือ Diarization Error Rate (DER) จาก `SpeakerDiarization.get_metric()` ที่มีอยู่
แล้วในตัว pipeline เอง (`GreedyDiarizationErrorRate` จาก `pyannote.metrics` — เป็น dependency ของ
pyannote.audio อยู่แล้ว ไม่ต้องติดตั้งเพิ่ม) — ยิ่ง DER ต่ำยิ่งดี (0 = สมบูรณ์แบบ)

=== วิธีใช้ ===
(ไฟล์ตัวอย่าง/artifact ของการ tune ทั้งหมด — `tuning_ground_truth.example.csv`/`tuning_clip.wav`/
ผลลัพธ์การทดลอง — ย้ายมารวมไว้ที่ `D:\Com Sec\experiments\` แล้ว 2026-08-04 (ดู /scrutinize session
นั้น — เดิมกระจัดกระจายอยู่ใน audio_worker/ ปนกับ source code) ยกเว้น `tuned_diarization_params.yaml`
ผลลัพธ์จริงที่ต้อง**อยู่ใน audio_worker/ เท่านั้น** เพราะ `diarization.py` โหลดจาก path นี้ตรงๆ)
1. เตรียม ground-truth CSV (ดู `../experiments/tuning_ground_truth.example.csv` เป็นตัวอย่างฟอร์แมต)
   โดยฟังไฟล์เสียงที่ผ่าน ffmpeg แล้ว (`audio_worker/processed/<job_id>.wav` — mono 16k ตัวเดียวกับที่
   diarization จริงใช้) ช่วงสั้นๆ (แนะนำ 5-10 นาทีที่มีคนพูดสลับกันหลายคนจริง ไม่ต้องทั้งไฟล์) แล้วจดว่า
   ใครพูดช่วงไหนจริงๆ (ใช้ชื่อเรียกเองได้ เช่น "ประธาน", "เลขา", "กรรมการ1" — ไม่ต้องตรงกับ SPEAKER_XX
   ที่ระบบเดาไว้)
2. ตัด clip เสียงช่วงเดียวกันนั้นออกมาเป็นไฟล์แยก (ให้ตรงกับเวลาที่ใช้ในข้อ 1 เป๊ะ เริ่มที่ 0 วินาที)
   เช่นด้วย ffmpeg: `ffmpeg -i processed/<job_id>.wav -ss 0 -t 600 ../experiments/tuning_clip.wav`
3. รัน: `python tune_diarization.py --audio ../experiments/tuning_clip.wav --ground-truth
   ../experiments/my_ground_truth.csv --iterations 30`
   (ใช้เวลานานพอสมควร แต่ละรอบรัน diarization เต็มรูปแบบ 1 ครั้งบน clip — ยิ่ง clip สั้น ยิ่งเร็ว)
4. ผลลัพธ์ (hyperparameter ที่ดีที่สุด) จะถูกบันทึกอัตโนมัติที่ `tuned_diarization_params.yaml` ทุก
   ครั้งที่เจอค่าที่ดีขึ้น (กันหายถ้า process ถูกขัดจังหวะกลางคัน กด Ctrl+C ได้เลยไม่เสียของ) —
   `diarization.py`'s `load_pipeline()` จะโหลดไฟล์นี้ทับค่า env ทั้งหมดโดยอัตโนมัติถ้ามีไฟล์นี้อยู่
   ไม่ต้องแก้ .env อีก แค่ restart audio_worker แล้ว reprocess ไฟล์เดิม
"""
import argparse
import csv
import os
import sys
from pathlib import Path

import torch
import yaml
from diarization import build_pipeline
from pyannote.core import Annotation, Segment, Timeline
from pyannote.pipeline import Optimizer
from worker_config import BASE_DIR


def _load_ground_truth_csv(path: str) -> tuple[Annotation, float]:
    """อ่าน CSV คอลัมน์ start_sec,end_sec,speaker_label (มี header หรือไม่มีก็ได้ — เดาจากว่า
    ค่าคอลัมน์แรกของแถวแรกแปลงเป็นตัวเลขได้ไหม) คืน (Annotation, duration รวม)"""
    annotation = Annotation()
    max_end = 0.0
    with open(path, encoding="utf-8-sig") as f:
        rows = list(csv.reader(f))
    if not rows:
        raise ValueError(f"ไฟล์ ground truth ว่างเปล่า: {path}")

    start_idx = 0
    try:
        float(rows[0][0])
    except (ValueError, IndexError):
        start_idx = 1  # แถวแรกเป็น header ข้ามไป

    for row_num, row in enumerate(rows[start_idx:], start=start_idx + 1):
        row = [c.strip() for c in row if c.strip() != ""]
        if not row:
            continue  # ข้ามบรรทัดว่าง
        if len(row) < 3:
            raise ValueError(f"บรรทัดที่ {row_num} ผิดฟอร์แมต (ต้องมี 3 คอลัมน์: start,end,speaker): {row}")
        try:
            start, end = float(row[0]), float(row[1])
        except ValueError:
            raise ValueError(f"บรรทัดที่ {row_num}: start/end ต้องเป็นตัวเลข (วินาที): {row}")
        speaker = row[2]
        if end <= start:
            raise ValueError(f"บรรทัดที่ {row_num}: end ({end}) ต้องมากกว่า start ({start})")
        annotation[Segment(start, end)] = speaker
        max_end = max(max_end, end)

    if len(annotation) == 0:
        raise ValueError(f"ไม่พบข้อมูลที่ใช้ได้ใน ground-truth CSV: {path}")
    return annotation, max_end


def main() -> None:
    parser = argparse.ArgumentParser(
        description="ค้นหา hyperparameter diarization ที่ดีที่สุดเทียบ ground truth จริง "
        "(ดู docstring หัวไฟล์นี้สำหรับขั้นตอนเต็ม)"
    )
    parser.add_argument("--audio", required=True, help="path ไปยัง wav clip ที่ตรงกับ ground-truth CSV เป๊ะ (เริ่มที่ 0 วินาที)")
    parser.add_argument("--ground-truth", required=True, help="path ไปยัง CSV: start_sec,end_sec,speaker_label")
    parser.add_argument("--iterations", type=int, default=30, help="จำนวนรอบค้นหา (default 30 — ยิ่งเยอะยิ่งแม่นแต่ยิ่งนาน)")
    parser.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    parser.add_argument(
        "--output", default=os.path.join(BASE_DIR, "tuned_diarization_params.yaml"),
        help="ไฟล์ output ที่ diarization.py's load_pipeline() จะโหลดอัตโนมัติถ้ามีอยู่",
    )
    args = parser.parse_args()

    if not os.path.exists(args.audio):
        sys.exit(f"[tune] ไม่พบไฟล์เสียง: {args.audio}")
    if not os.path.exists(args.ground_truth):
        sys.exit(f"[tune] ไม่พบไฟล์ ground truth: {args.ground_truth}")

    print(f"[tune] โหลด ground truth จาก {args.ground_truth} ...")
    annotation, duration = _load_ground_truth_csv(args.ground_truth)
    annotation.uri = "tuning_clip"
    annotated = Timeline([Segment(0, duration)], uri="tuning_clip")
    print(f"[tune] พบ {len(annotation.labels())} speaker จริงใน ground truth, ครอบคลุมช่วง 0-{duration:.1f} วินาที")

    print(f"[tune] โหลด pipeline (checkpoint เดียวกับที่ใช้งานจริง) บน device={args.device} ...")
    pipeline = build_pipeline(args.device)

    input_file = {
        "uri": "tuning_clip",
        "audio": args.audio,
        "annotation": annotation,
        "annotated": annotated,
    }

    optimizer = Optimizer(pipeline)
    output_path = Path(args.output)
    print(f"[tune] เริ่มค้นหา hyperparameter ({args.iterations} รอบ) — แต่ละรอบรัน diarization เต็ม")
    print("[tune] รูปแบบ 1 ครั้งบน clip นี้ อาจใช้เวลานานพอสมควร กด Ctrl+C ได้ทุกเมื่อ (ค่าที่ดีที่สุด")
    print(f"[tune] ล่าสุดถูกบันทึกไว้ที่ {output_path} เสมอหลังทุกรอบที่ดีขึ้น)")

    best = None
    try:
        for i, result in enumerate(optimizer.tune_iter([input_file], show_progress=False), start=1):
            improved = best is None or result["loss"] < best["loss"]
            best = result
            marker = " (ดีขึ้น)" if improved else ""
            print(f"[tune] รอบ {i}/{args.iterations}: DER ดีที่สุดตอนนี้ = {result['loss']:.4f}{marker}")
            if improved:
                pipeline.dump_params(output_path, params=result["params"], loss=result["loss"])
            if i >= args.iterations:
                break
    except KeyboardInterrupt:
        print("\n[tune] ถูกยกเลิกกลางคัน — ค่าที่ดีที่สุดล่าสุดถูกบันทึกไว้แล้ว")

    if best is None:
        sys.exit("[tune] ไม่มีผลลัพธ์เลย (0 รอบสำเร็จ) — เช็ค error ด้านบน")

    print()
    print(f"[tune] เสร็จแล้ว — DER ดีที่สุด = {best['loss']:.4f} (ยิ่งต่ำยิ่งดี, 0 = สมบูรณ์แบบ)")
    print(f"[tune] บันทึก hyperparameter ที่ดีที่สุดไว้ที่: {output_path}")
    print("[tune] ค่าที่ดีที่สุด:")
    print(yaml.dump(best["params"], default_flow_style=False, allow_unicode=True))
    print(
        "[tune] diarization.py's load_pipeline() จะโหลดไฟล์นี้อัตโนมัติถ้ามีอยู่ (ไม่ต้องแก้ .env "
        "อีก) — restart audio_worker แล้ว reprocess ไฟล์เดิมได้เลย"
    )


if __name__ == "__main__":
    main()
