"""
audio_transcription_experiment.py — CLI ทดลองส่งไฟล์เสียงเข้า Gemini native audio understanding
โดยตรง (diarization + transcription จบในโมเดลเดียว) เทียบผลกับ transcript เดิม

**อัปเดต (2026-08-05, wiring จริงเข้า `main.py` — ดู `/grill-me` 3.14, task.md บรรทัด 164-191)**:
logic หลักทั้งหมด (Pydantic schema/system prompt/upload+poll ผ่าน Files API/fallback chain) ย้ายไป
`audio_native.py` แล้ว เพราะ `backend/main.py` ต้องเรียกใช้ตัวเดียวกันในโปรเซสจริง (ไม่ใช่แค่ CLI
ทดลองอีกต่อไป) — ไฟล์นี้เหลือแค่ CLI wrapper บางๆสำหรับทดลองเทียบโมเดล/ไฟล์แบบ ad-hoc เท่านั้น
**ไม่ import ซ้ำ/ก็อปปี้ logic เดิมมาเขียนใหม่** กันโค้ด production path กับสคริปต์ทดลอง diverge กัน
(ดูประวัติเต็มของการทดลองนี้ที่ handoff.md 3.13-3.14 — 2 รอบทดสอบจริงที่ยืนยันผลดีของแนวทางนี้)

⚠️ **มีค่าใช้จ่ายจริง** — ไฟล์เสียงประชุมยาวส่งเข้า Gemini ทั้งไฟล์ ไม่ใช่ทดลองฟรี รันด้วยความ
ระมัดระวัง (แนะนำให้ทดลองกับ clip สั้นๆก่อน เช่น `experiments/tuning_clip.wav` — ไฟล์ทดลอง/output
ทั้งหมดของสคริปต์นี้รวมไว้ที่ `experiments/` ตั้งแต่ 2026-08-04)

**วิธีใช้**:
    python audio_transcription_experiment.py --audio ../experiments/tuning_clip.wav \\
        --output ../experiments/transcription_experiment_result.txt
"""
import argparse
import sys
from pathlib import Path

from audio_native import AudioNativeError, AudioTranscriptResult, transcribe_audio_native


def _format_as_transcript_txt(result: AudioTranscriptResult) -> str:
    """แปลงเป็นฟอร์แมตเดียวกับ exportTranscriptText() ใน app.js เพื่อเทียบกับไฟล์เก่าได้ตรงๆ"""
    lines = []
    for seg in result.segments:
        mm = int(seg.start_seconds // 60)
        ss = int(seg.start_seconds % 60)
        lines.append(f"[{mm:02d}:{ss:02d}] {seg.speaker_label}: {seg.text}")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audio", required=True, help="path ไปยังไฟล์เสียง (wav/m4a/mp3 ฯลฯ)")
    parser.add_argument(
        "--output", default="../experiments/transcription_experiment_result.txt",
        help="ไฟล์ output รูปแบบเดียวกับ Export Transcript เดิม (default: "
        "../experiments/transcription_experiment_result.txt — สมมติรันจาก backend/ ตามตัวอย่างด้านบน)",
    )
    parser.add_argument(
        "--model", default=None,
        help='เทสโมเดลเฉพาะกิจ ข้าม config.py/.env (เช่น "gemini-3.6-flash") — '
        'ต้องเป็นโมเดลหมวด "Text-out models" ที่รองรับ generate_content()+audio เท่านั้น '
        'ห้ามใช้โมเดลหมวด "Live API" (เช่น ...-native-audio-dialog, ...-live-translate) '
        "จะ error ทันทีเพราะเป็นคนละ API",
    )
    args = parser.parse_args()

    try:
        result, model_used = transcribe_audio_native(
            args.audio, model_override=args.model, log=print,
        )
    except AudioNativeError as e:
        sys.exit(f"[transcribe] ล้มเหลว: {e}")

    unique_speakers = sorted({seg.speaker_label for seg in result.segments})
    print()
    print(f"[transcribe] สำเร็จด้วย model={model_used}")
    print(f"[transcribe] จำนวน segment: {len(result.segments)}, จำนวน speaker: {len(unique_speakers)}")
    print(f"[transcribe] speaker labels: {unique_speakers}")

    output_path = Path(args.output)
    output_path.write_text(_format_as_transcript_txt(result), encoding="utf-8")
    print(f"[transcribe] บันทึกผลลัพธ์ (รูปแบบเดียวกับ Export Transcript เดิม) ที่: {output_path}")
    print("[transcribe] เทียบกับ transcript_555*.txt เดิมได้เลย — เช็คว่า speaker สมเหตุสมผลไหม, "
          "ประโยคขาดเป็นท่อนสั้นๆเหมือนเดิมไหม")


if __name__ == "__main__":
    main()
