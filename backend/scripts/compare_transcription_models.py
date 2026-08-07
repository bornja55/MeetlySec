"""
compare_transcription_models.py — ส่งไฟล์เสียงเดียวกัน (แนะนำ ~10 นาที) ไปถอดเสียงด้วยทุกโมเดลใน
`config.GEMINI_TRANSCRIPTION_MODEL_CHOICES` (หรือเลือกบางตัวผ่าน `--models`) แล้วเปรียบเทียบผลลัพธ์
เคียงกัน — ผู้ใช้ขอ (2026-08-05) เพื่อตัดสินใจว่าจะใช้โมเดลไหนจริงในโปรดักชัน และทดสอบว่า **รันหลาย
โมเดลพร้อมกัน (concurrent request จาก API key เดียวกัน) ได้จริงไม่ชนกันไหม** (ถ้ารันขนานได้จริง จะช่วย
ลดเวลารอทดสอบเทียบโมเดลได้มาก — ปกติทีละตัวรวมกัน 7 โมเดลอาจรอนานหลายนาที)

ใช้ `transcribe_audio_native()` (ไม่ chunk — ตรงตามที่ผู้ใช้ขอ "ไฟล์เดียวกัน 10 นาที" ซึ่งสั้นกว่า
`AUDIO_CHUNK_SECONDS` อยู่แล้วเป๊ะๆพอดี ไม่ถูกตัดเป็นชิ้นโดย `transcribe_meeting_audio()` แม้จะใช้ทาง
นั้นก็ตาม — เลือกใช้ฟังก์ชันที่ตรงและง่ายกว่าแทน) เรียกทีละโมเดล **ไม่มี fallback chain** (เหมือน
production path ที่เลือกโมเดลเอง — ต้องการดูผลของแต่ละโมเดลจริงๆ ไม่อยากให้ fallback ไปโมเดลอื่นแล้ว
วัดผลผิดตัว)

**ต้องรันบนเครื่องจริงของผู้ใช้** (sandbox นี้ไม่มี network ออก Google เลย — เขียน/verify ได้แค่ logic
การจัดลำดับ/รวมผล/เขียนไฟล์ ผ่าน mock เท่านั้น ไม่เคยยิง Gemini จริงสักครั้ง)

**อัปเดต (2026-08-05, session 3.26) — เพิ่ม `--delay` + ตารางเทียบทีละวินาที** ผู้ใช้ขอเพิ่ม delay ก่อน
รันซ้ำอีกรอบ (เหตุผลสันนิษฐาน: กัน rate limit ตอน `--parallel` — โควต้า Gemini free tier มักมีทั้ง
RPD (เจอแล้วจาก session 3.23 — 16/20) และ RPM (requests-per-minute) แยกกัน ยิง 7 โมเดลพร้อมกันในเสี้ยว
วินาทีเดียวอาจชน RPM burst ได้ทั้งที่ RPD ยังไม่เต็ม) — เพิ่ม `--delay` (ดีฟอลต์ 0.0 = พฤติกรรมเดิม
ทุกประการ ไม่กระทบถ้าไม่ระบุ) หน่วงเวลาก่อน submit คำขอของแต่ละโมเดลถัดไป (sequential: หน่วงจริงระหว่าง
รอผลก่อนยิงตัวถัดไป, parallel: หน่วงแค่จังหวะ "เริ่ม" งานแต่ละ future ให้เหลื่อมกันแทนที่จะยิงพร้อมกันหมด
ในเสี้ยววินาทีเดียว — ยังคงขนานกันอยู่จริง แค่ stagger จุดเริ่ม ไม่ได้กลายเป็น sequential)

เพิ่มตารางเปรียบเทียบผลลัพธ์ทีละวินาที (`comparison_by_second.csv`) — user ขอ "ทำเป็นตารางเทียบต่อวินาที"
หลังได้ผลลัพธ์จริง: แต่ละแถว = 1 วินาทีของไฟล์เสียง, แต่ละคอลัมน์ = 1 โมเดล, ค่าในช่อง = `[speaker]
ข้อความ` ของ segment ที่ครอบคลุมวินาทีนั้น (ตัดสั้นถ้ายาวเกิน) หรือว่างถ้าไม่มี segment ไหนครอบคลุม —
เปิดใน Excel เทียบแนวนอนได้ทันทีว่าแต่ละโมเดล transcribe ตรงกันไหมที่วินาทีเดียวกัน ช่วยเห็น
gap/duplicate/timestamp drift ได้ตรงจุดกว่าดู JSON แยกไฟล์

Usage:
    cd backend
    python scripts/compare_transcription_models.py --audio path/to/10min_test.wav
    python scripts/compare_transcription_models.py --audio path/to/10min_test.wav --parallel
    python scripts/compare_transcription_models.py --audio path/to/10min_test.wav --parallel --delay 1.5
    python scripts/compare_transcription_models.py --audio path/to/10min_test.wav \
        --models gemini-3.6-flash,gemini-2.5-flash-lite
"""
import argparse
import concurrent.futures
import csv
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import audio_chunking  # noqa: E402
import config  # noqa: E402
from audio_native import AudioNativeError, transcribe_audio_native  # noqa: E402


def _run_one_model(audio_path: str, model_id: str) -> dict:
    """ยิงโมเดลเดียว คืน dict สรุปผล+ข้อมูลเต็ม — ไม่ raise ออกไปเด็ดขาด (ทั้ง `AudioNativeError` ที่
    รู้จักอยู่แล้ว และ exception อื่นที่ไม่คาดคิด) เพราะเรียกจาก `ThreadPoolExecutor` ตอน `--parallel`
    — ถ้าโมเดลหนึ่งพัง (เช่น โควต้าเต็มพอดี/ไม่มีโมเดลนี้จริง) ต้องไม่ทำให้ future อื่นๆที่กำลังรันขนาน
    อยู่พังตามหรือถูกยกเลิกไปด้วย"""
    t0 = time.time()

    def log(msg):
        pass  # เงียบไว้ (progress log ของ _upload_and_wait ไม่ต้องโชว์ตอนรันเทียบหลายโมเดลพร้อมกัน
        # จะปนกันอ่านไม่ออก — ดู stdout print แยกต่อโมเดลด้านล่างแทน)

    try:
        result, model_used = transcribe_audio_native(audio_path, model_override=model_id, log=log)
        elapsed = time.time() - t0
        segments = result.segments
        total_chars = sum(len(s.text) for s in segments)
        speakers = sorted(set(s.speaker_label for s in segments))
        return {
            "model": model_id,
            "model_used_confirmed": model_used,  # ควรตรงกับ model_id เสมอ (ไม่มี fallback) — เก็บไว้
            # เผื่อพบว่าไม่ตรงกันจะได้รู้ทันทีว่ามีอะไรผิดปกติ
            "success": True,
            "elapsed_seconds": round(elapsed, 1),
            "segment_count": len(segments),
            "total_chars": total_chars,
            "speaker_count": len(speakers),
            "speakers": speakers,
            "segments": [
                {
                    "start": seg.start_seconds, "end": seg.end_seconds,
                    "speaker": seg.speaker_label, "text": seg.text,
                }
                for seg in segments
            ],
            "error": None,
        }
    except AudioNativeError as e:
        return {
            "model": model_id, "model_used_confirmed": None, "success": False,
            "elapsed_seconds": round(time.time() - t0, 1), "segment_count": 0, "total_chars": 0,
            "speaker_count": 0, "speakers": [], "segments": [], "error": str(e),
        }
    except Exception as e:  # noqa: BLE001 — ตั้งใจกว้าง กันโมเดลอื่นพังตามถ้าตัวนี้ throw อะไรที่ไม่คาดคิด
        return {
            "model": model_id, "model_used_confirmed": None, "success": False,
            "elapsed_seconds": round(time.time() - t0, 1), "segment_count": 0, "total_chars": 0,
            "speaker_count": 0, "speakers": [], "segments": [],
            "error": f"{type(e).__name__}: {e}",
        }


def run_comparison(
    audio_path: str, model_ids: list[str], *, parallel: bool = False, delay_seconds: float = 0.0,
    progress=print, _sleep=time.sleep,
) -> tuple[list[dict], float]:
    """แยก orchestration logic ออกจาก `main()`/CLI parsing เพื่อ unit test ได้โดยไม่ต้องพึ่ง argparse
    — คืน (results เรียงตามลำดับ model_ids เดิม, total_elapsed_seconds) `progress` callback รับ string
    เดียว (ดีฟอลต์ `print` ปกติ, ส่ง no-op เข้ามาแทนได้เวลา test)

    `delay_seconds` (ดีฟอลต์ 0.0 = พฤติกรรมเดิมทุกประการ ไม่หน่วงเลย): หน่วงก่อนเริ่มงานของโมเดลที่ 2
    เป็นต้นไป (ไม่หน่วงก่อนตัวแรก) กันชน rate limit แบบ RPM/burst เวลายิงหลายโมเดลติดกัน —
    sequential mode หน่วง "จริง" ระหว่างรอผลก่อนยิงตัวถัดไป, parallel mode หน่วงแค่จังหวะ `submit()`
    ให้แต่ละงาน "เริ่ม" เหลื่อมกัน (staggered start) ไม่ใช่ยิงพร้อมกันทั้งหมดในเสี้ยววินาทีเดียว — งานที่
    submit ไปแล้วยังคงรันขนานกันจริงในเธรดของมันเอง ไม่ได้กลายเป็น sequential แค่ช้าลง

    `_sleep` รับ sleep function แทนได้ (ดีฟอลต์ `time.sleep` จริง) เพื่อให้ unit test ตรวจจังหวะ delay ได้
    โดยไม่ต้องรอเวลาจริง"""
    t_start = time.time()
    results: list[dict] = []

    if parallel:
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(model_ids)) as ex:
            futures = {}
            for i, m in enumerate(model_ids):
                if i > 0 and delay_seconds > 0:
                    _sleep(delay_seconds)
                futures[ex.submit(_run_one_model, audio_path, m)] = m
            for fut in concurrent.futures.as_completed(futures):
                r = fut.result()
                status = "OK" if r["success"] else f"FAIL: {r['error']}"
                progress(f"[{r['model']}] เสร็จใน {r['elapsed_seconds']}s — {status}")
                results.append(r)
    else:
        for i, m in enumerate(model_ids):
            if i > 0 and delay_seconds > 0:
                _sleep(delay_seconds)
            progress(f"กำลังทดสอบ {m} ...")
            r = _run_one_model(audio_path, m)
            status = "OK" if r["success"] else f"FAIL: {r['error']}"
            progress(f"  เสร็จใน {r['elapsed_seconds']}s — {status}")
            results.append(r)

    total_elapsed = time.time() - t_start
    # ThreadPoolExecutor คืนผลไม่เรียงลำดับ (as_completed ตามเวลาที่เสร็จจริง) — เรียงกลับตามลำดับ
    # model_ids เดิมเสมอ ให้ตารางสรุป/ไฟล์ผลลัพธ์อ่านง่าย ไม่สลับไปมาตามความเร็วของแต่ละโมเดล
    order = {m: i for i, m in enumerate(model_ids)}
    results.sort(key=lambda r: order.get(r["model"], 999))
    return results, total_elapsed


def print_summary_table(results: list[dict], total_elapsed: float) -> None:
    print(f"\n{'=' * 100}")
    print(f"สรุปผล (รวมเวลาทั้งหมด: {total_elapsed:.1f}s)")
    print(f"{'=' * 100}")
    header = f"{'Model':<26} {'สถานะ':<8} {'เวลา(s)':<10} {'Segments':<10} {'ตัวอักษร':<10} {'Speakers':<10}"
    print(header)
    print("-" * len(header))
    for r in results:
        status = "OK" if r["success"] else "FAIL"
        print(
            f"{r['model']:<26} {status:<8} {r['elapsed_seconds']:<10} "
            f"{r['segment_count']:<10} {r['total_chars']:<10} {r['speaker_count']:<10}"
        )
        if not r["success"]:
            print(f"    └─ error: {r['error']}")


def write_results(results: list[dict], output_dir: str) -> None:
    os.makedirs(output_dir, exist_ok=True)
    for r in results:
        safe_name = r["model"].replace("/", "_")
        with open(os.path.join(output_dir, f"{safe_name}.json"), "w", encoding="utf-8") as f:
            json.dump(r, f, ensure_ascii=False, indent=2)


def _determine_total_seconds(audio_path: str, results: list[dict], *, progress=print) -> int:
    """หาความยาวไฟล์ทั้งหมด (วินาที, ปัดขึ้น) เพื่อกำหนดจำนวนแถวของตารางเทียบทีละวินาที — ใช้ ffprobe
    ผ่าน `audio_chunking.get_duration_seconds()` เป็นหลัก (แม่นสุด ตรงกับไฟล์จริง ไม่ขึ้นกับว่าโมเดลไหน
    transcribe ครอบคลุมกี่วินาที) — ถ้า ffprobe ใช้ไม่ได้ (เช่น เครื่องผู้ใช้ไม่มี ffmpeg ใน PATH) fallback
    เป็นค่า `end` ที่มากที่สุดในบรรดา segment ที่ transcribe สำเร็จทั้งหมด (อาจสั้นกว่าไฟล์จริงถ้าโมเดล
    ทุกตัวตัดจบก่อนท้ายไฟล์พอดี แต่ยังดีกว่าไม่มีตารางเลย)"""
    try:
        return int(audio_chunking.get_duration_seconds(audio_path)) + 1
    except audio_chunking.FFmpegError as e:
        progress(f"⚠️ หาความยาวไฟล์ด้วย ffprobe ไม่ได้ ({e}) — ใช้ค่า end ที่มากสุดจาก segment แทน")
        max_end = 0.0
        for r in results:
            for seg in r.get("segments", []):
                max_end = max(max_end, seg["end"])
        return int(max_end) + 1


def _csv_safe(text: str) -> str:
    """กันปัญหา "CSV/formula injection": ถ้าเนื้อหาขึ้นต้นด้วย `= + - @` (หรือ tab/CR) Excel อาจตีความ
    เป็นสูตรแทนที่จะเป็นข้อความธรรมดา (เช่น ผู้พูดพูดคำที่ transcribe ออกมาขึ้นต้นด้วยเครื่องหมายลบ/บวก
    พอดี) — เติม `'` (apostrophe) นำหน้าให้ Excel แสดงเป็น text เสมอ ไม่ error/ไม่ถูกรันเป็นสูตร (มาตรฐาน
    เดียวกับที่ OWASP แนะนำสำหรับ CSV injection — ความเสี่ยงต่ำเพราะเนื้อหามาจากเสียงประชุมของผู้ใช้เอง
    ไม่ใช่ input จากภายนอกที่ไม่น่าเชื่อถือ แต่ระบบนี้จัดการข้อมูลลับของบอร์ดบริษัท ป้องกันไว้ก่อนดีกว่า)"""
    if text and text[0] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + text
    return text


def build_second_by_second_table(
    results: list[dict], total_seconds: int, *, text_maxlen: int = 40,
) -> tuple[list[dict], list[str]]:
    """สร้างตารางเทียบผลลัพธ์ทีละวินาทีระหว่างโมเดล — แต่ละแถวคือ 1 วินาทีของไฟล์เสียง คอลัมน์คือแต่ละ
    โมเดล ค่าคือ `[speaker] ข้อความ` ของ segment ที่ครอบคลุมวินาทีนั้น (`seg["start"] <= t <
    seg["end"]`, ตัดข้อความยาวเกิน text_maxlen) หรือว่างถ้าไม่มี segment ไหนครอบคลุมวินาทีนั้นเลย (ช่วง
    เงียบ/โมเดลข้าม/gap) — โมเดลที่ล้มเหลว (`success=False`) ได้คอลัมน์ว่างทั้งแถว ไม่ error

    ⚠️ ใช้ลำดับ segment ตามที่ `_run_one_model()`/`transcribe_audio_native()` คืนมาตรงๆ **ไม่ sort ซ้ำ**
    — บทเรียนจาก session 3.22 (บั๊ก sort-scramble ใน `audio_chunking.merge_chunk_segments()`): sort ตาม
    ค่าตัวเลข `start` ไม่ปลอดภัยถ้า Gemini คืนหน่วยผิดบางจุด ลำดับ array ดั้งเดิมน่าเชื่อถือกว่าเสมอ"""
    rows: list[dict] = []
    model_ids = [r["model"] for r in results]
    for t in range(total_seconds):
        row: dict = {"second": t, "mm_ss": f"{t // 60}:{t % 60:02d}"}
        for r in results:
            cell = ""
            if r["success"]:
                for seg in r["segments"]:
                    if seg["start"] <= t < seg["end"]:
                        text = seg["text"]
                        if len(text) > text_maxlen:
                            text = text[: text_maxlen - 1] + "…"
                        cell = f"[{seg['speaker']}] {text}"
                        break
            row[r["model"]] = _csv_safe(cell)
        rows.append(row)
    return rows, model_ids


def write_second_by_second_csv(rows: list[dict], model_ids: list[str], output_dir: str) -> str:
    os.makedirs(output_dir, exist_ok=True)
    path = os.path.join(output_dir, "comparison_by_second.csv")
    # utf-8-sig (มี BOM) กัน Excel เปิดไฟล์ CSV ที่มีอักษรไทยแล้วเพี้ยนเป็น mojibake — ปัญหาที่พบบ่อยมาก
    # เวลาเปิด UTF-8 ธรรมดาใน Excel บน Windows (ผู้ใช้ project นี้ทั้งหมดอยู่บน Windows)
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=["second", "mm_ss", *model_ids])
        writer.writeheader()
        writer.writerows(rows)
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--audio", required=True, help="path ไฟล์เสียงทดสอบ (แนะนำ ~10 นาที)")
    parser.add_argument(
        "--models", default=None,
        help="comma-separated model id (ดีฟอลต์ = ทุกตัวใน config.GEMINI_TRANSCRIPTION_MODEL_CHOICES)",
    )
    parser.add_argument("--parallel", action="store_true", help="ยิงทุกโมเดลพร้อมกัน (ดีฟอลต์ = ทีละตัว)")
    parser.add_argument(
        "--delay", type=float, default=0.0, dest="delay_seconds",
        help="หน่วงกี่วินาทีก่อนเริ่มงานของโมเดลถัดไป (กัน rate limit burst) ดีฟอลต์ 0 = ไม่หน่วง",
    )
    parser.add_argument(
        "--output-dir", default="model_comparison_results",
        help="โฟลเดอร์เก็บผลลัพธ์เต็มต่อโมเดล (JSON) — ดีฟอลต์: backend/model_comparison_results/",
    )
    args = parser.parse_args()

    if not config.GOOGLE_API_KEY:
        print("ไม่มี GOOGLE_API_KEY ใน backend/.env — ตั้งค่าก่อนใช้งาน")
        sys.exit(1)
    if not os.path.exists(args.audio):
        print(f"ไม่พบไฟล์: {args.audio}")
        sys.exit(1)

    if args.models:
        model_ids = [m.strip() for m in args.models.split(",") if m.strip()]
    else:
        model_ids = [m for m, _label in config.GEMINI_TRANSCRIPTION_MODEL_CHOICES]

    if not model_ids:
        # กัน `--models ""` หรือ `--models ","` (ทุก token ว่างหมดหลัง strip) — ไม่งั้น `--parallel` จะไป
        # เจอ `ThreadPoolExecutor(max_workers=0)` ซึ่ง raise ValueError อ่านไม่รู้เรื่องแทน (พบจาก
        # /scrutinize 2026-08-05, session 3.26)
        print("ไม่มีโมเดลให้ทดสอบเลย (เช็ค --models ว่าใส่ค่าถูกไหม)")
        sys.exit(1)

    print(f"ทดสอบ {len(model_ids)} โมเดล กับไฟล์ {args.audio} ({'ขนาน' if args.parallel else 'ทีละตัว'})")
    if args.delay_seconds > 0:
        print(f"หน่วง {args.delay_seconds}s ก่อนเริ่มงานของแต่ละโมเดลถัดไป")
    print(f"โมเดล: {', '.join(model_ids)}\n")

    results, total_elapsed = run_comparison(
        args.audio, model_ids, parallel=args.parallel, delay_seconds=args.delay_seconds,
    )

    write_results(results, args.output_dir)
    print_summary_table(results, total_elapsed)

    total_seconds = _determine_total_seconds(args.audio, results)
    rows, model_ids_out = build_second_by_second_table(results, total_seconds)
    csv_path = write_second_by_second_csv(rows, model_ids_out, args.output_dir)

    print(f"\nผลลัพธ์เต็มต่อโมเดล (segment/text ทั้งหมด) บันทึกไว้ที่ {args.output_dir}/<model>.json")
    print(f"ตารางเปรียบเทียบทีละวินาที (เปิดใน Excel ได้เลย): {csv_path}")
    print("แนะนำ: เปิด JSON ของแต่ละโมเดลเทียบข้อความ/timestamp/speaker label ด้วยตาเพื่อประเมินคุณภาพจริง")
    print("(สคริปต์นี้เทียบแค่ตัวเลขเชิงปริมาณ — จำนวน segment/ตัวอักษร/speaker — ไม่ได้ตัดสินคุณภาพ")
    print("เนื้อหาให้อัตโนมัติ ยังต้องอ่านเทียบเองว่าโมเดลไหนถอดผิด/ตกหล่นน้อยกว่ากัน)")


if __name__ == "__main__":
    main()
