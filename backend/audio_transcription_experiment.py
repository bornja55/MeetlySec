"""
audio_transcription_experiment.py — ทดลองส่งไฟล์เสียงเข้า Gemini native audio understanding
โดยตรง (diarization + transcription จบในโมเดลเดียว) แทน pipeline pyannote+typhoon-asr แยกส่วนเดิม
ของ `audio_worker/` (2026-08-04)

**เหตุผล**: ผู้ใช้ลองโยนไฟล์เสียงประชุมเดียวกันเข้า NotebookLM (ซึ่งใช้ Gemini audio understanding
ข้างใน) ได้ผล diarization/transcription แม่นกว่า pipeline ของเราเองมาก (ระบุคนพูดถูก ตัวเลขครบ
ประโยคไม่ขาดเป็นท่อนสั้นๆแบบที่ `audio_worker` เจอหลัง tune `clustering.threshold` หลายรอบแล้วยังแก้
ไม่ได้ — ดู handoff.md 3.12) — ตั้งสมมติฐานว่าสาเหตุคือ Gemini ทำ diarization+ASR **ในโมเดลเดียวจบ**
(เห็น audio ตรงๆ) ต่างจากเราที่แยก pyannote (diarization บน embedding เสียง) + typhoon-asr (ASR ต่อ
segment แยก, ไม่เห็นบริบทข้ามประโยค) — สคริปต์นี้ทดลองยืนยันสมมติฐานด้วยการยิง API ตรงๆ

⚠️ **นี่คือสคริปต์ทดลองเท่านั้น** ยังไม่เชื่อมเข้า `main.py`/`pipeline.py` จริง — เจตนาให้รันแยกเทียบผล
กับ transcript ที่มีอยู่แล้ว (`transcript_555*.txt`) ก่อนตัดสินใจว่าจะแทนที่ audio_worker's
diarization+ASR pipeline ทั้งชุดหรือไม่ (ถ้าผลดีจริง จะลดความซับซ้อนของระบบได้มาก — ไม่ต้อง tune
pyannote hyperparameter อีกเลย ไม่ต้องมี audio_worker แยกโปรเซสสำหรับ diarization+ASR อีกต่อไป)

⚠️ **มีค่าใช้จ่ายจริง** — ไฟล์เสียงประชุม 55 นาทีส่งเข้า Gemini ทั้งไฟล์ ไม่ใช่ทดลองฟรี รันด้วยความ
ระมัดระวัง (แนะนำให้ทดลองกับ clip สั้นๆก่อน เช่น `experiments/tuning_clip.wav` 10 นาทีที่มีอยู่แล้ว —
ไฟล์ทดลอง/output ทั้งหมดของสคริปต์นี้ย้ายมารวมไว้ที่ `experiments/` แล้ว 2026-08-04 ดู /scrutinize
session นั้น เดิมกระจัดกระจายอยู่ใน backend/ ปนกับ source code + ไม่เคยถูก .gitignore)

**หมายเหตุสำคัญที่ตรวจจากซอร์สจริงของ `google-genai==2.16.0` แล้ว (ไม่ได้เดาจาก doc):**
❌ **ห้ามใช้ `GenerateContentConfig(audio_timestamp=True)`** — parameter นี้โยน `ValueError` ทันทีถ้า
ใช้ผ่าน **Gemini Developer API mode** (`genai.Client(api_key=...)` — โหมดที่โปรเจกต์นี้ใช้อยู่ทั้ง
Module 1/3) รองรับเฉพาะ Vertex AI "Gemini Enterprise Agent Platform" mode เท่านั้น (ดู
`google/genai/models.py`'s `_GenerateContentConfig_to_mldev()`) — ใช้วิธีขอ timestamp ผ่าน prompt
text + structured output schema แทน (ให้โมเดลใส่ `start_seconds`/`end_seconds` เป็น field ในทุก
segment เอง)

**วิธีใช้**:
    python audio_transcription_experiment.py --audio ../experiments/tuning_clip.wav \\
        --output ../experiments/transcription_experiment_result.txt
เทียบผลลัพธ์ที่ได้กับ `transcript_555 (2).txt` (ผลจาก pyannote+typhoon-asr รอบ threshold=0.85) —
ดูว่าจำนวน speaker สมเหตุสมผลไหม ประโยคขาดเป็นท่อนสั้นๆเหมือนเดิมไหม
"""
import argparse
import mimetypes
import sys
import time
from pathlib import Path

import config
from google import genai
from google.genai import types
from llm_fallback import run_with_fallback
from pydantic import BaseModel, Field


class AudioTranscriptSegment(BaseModel):
    start_seconds: float = Field(..., description="เวลาเริ่มพูดของ segment นี้ นับจากต้นไฟล์ (วินาที)")
    end_seconds: float = Field(..., description="เวลาจบพูดของ segment นี้ (วินาที)")
    speaker_label: str = Field(
        ..., description='ป้ายชื่อผู้พูด ตั้งเองให้สอดคล้องกันตลอดทั้งไฟล์ เช่น "Speaker 1" — คนเดียวกันต้องใช้ label เดียวกันเสมอ'
    )
    text: str = Field(..., description="คำพูดจริงในช่วงนี้ ห้ามแต่งเติมหรือสรุปเอง ต้องเป็นคำที่ได้ยินจริง")


class AudioTranscriptResult(BaseModel):
    segments: list[AudioTranscriptSegment] = Field(..., description="รายการ segment เรียงตามเวลา ครอบคลุมทั้งไฟล์")


_TRANSCRIPTION_SYSTEM_PROMPT = """คุณเป็นระบบถอดเสียงประชุมภาษาไทยที่ต้องแม่นยำสูงสุด งานของคุณคือ
ถอดเสียงไฟล์ที่แนบมาเป็นข้อความภาษาไทยทั้งหมด พร้อมแบ่งช่วงพูดตามผู้พูดจริง (speaker diarization)

กฎที่ต้องทำตามเคร่งครัด:
1. ถอดให้ครบทุกคำที่ได้ยินจริงในไฟล์ ห้ามข้ามช่วงไหน ห้ามสรุปย่อ ห้ามแต่งเติมคำที่ไม่ได้ยิน
2. แบ่ง segment ตามการเปลี่ยนผู้พูดจริง (ไม่ใช่ตามประโยค) — ผู้พูดคนเดียวกันพูดต่อเนื่องยาวๆ ให้อยู่
   segment เดียวกัน ไม่ต้องตัดย่อยโดยไม่จำเป็น
3. ตั้ง speaker_label เอง (เช่น "Speaker 1", "Speaker 2") — ผู้พูดคนเดียวกันต้องใช้ label เดียวกัน
   สม่ำเสมอตลอดทั้งไฟล์ ห้ามสลับ label ให้คนเดียวกันเป็นคนละ label หรือรวมคนละคนไว้ label เดียวกัน
4. start_seconds/end_seconds ต้องตรงกับเวลาจริงในไฟล์ (นับจาก 0 ที่ต้นไฟล์)
5. ถ้าฟังไม่ชัดหรือไม่แน่ใจ ให้ถอดตามที่ได้ยินใกล้เคียงที่สุด ไม่ต้องเดาเติมคำที่ไม่มั่นใจ"""


def _upload_and_wait(client: genai.Client, audio_path: Path) -> types.File:
    mime_type, _ = mimetypes.guess_type(str(audio_path))
    print(f"[transcribe] กำลังอัปโหลด {audio_path} (mime={mime_type or 'ไม่ทราบ, ให้ SDK เดา'}) ...")
    uploaded = client.files.upload(file=str(audio_path))
    # Files API เป็น async สำหรับไฟล์ใหญ่ — poll จนกว่าจะ ACTIVE
    while uploaded.state == types.FileState.PROCESSING:
        print("[transcribe] Gemini กำลังประมวลผลไฟล์ที่อัปโหลด รอ...")
        time.sleep(3)
        uploaded = client.files.get(name=uploaded.name)
    if uploaded.state == types.FileState.FAILED:
        raise RuntimeError(f"อัปโหลดไฟล์ล้มเหลว: {uploaded.error}")
    print(f"[transcribe] อัปโหลดสำเร็จ: {uploaded.name} ({uploaded.size_bytes} bytes)")
    return uploaded


def transcribe_audio_native(
    audio_path: str, *, model_override: str | None = None,
) -> tuple[AudioTranscriptResult, str]:
    """ส่งไฟล์เสียงเข้า Gemini ตรงๆ คืน (ผลลัพธ์, ชื่อโมเดลที่สำเร็จจริง)

    model_override: ถ้าระบุ จะใช้โมเดลนี้ตัวเดียว (ไม่มี fallback chain) — สำหรับทดลองเทียบโมเดล
    เฉพาะกิจผ่าน `--model` โดยไม่ต้องแก้ `.env` (ดู main()) — **ต้องเป็นโมเดลหมวด "Text-out models"
    ที่รองรับ `generate_content()` + audio input เท่านั้น** โมเดลหมวด "Live API" (เช่น
    "...-native-audio-dialog", "...-live-translate") ใช้ผ่านทางนี้ไม่ได้เลย เพราะเป็นคนละ
    WebSocket streaming session ไม่ใช่ request/response ธรรมดา (ตรวจสอบจากเอกสารจริงแล้ว
    2026-08-04, ดู handoff.md 3.13)"""
    if not config.GOOGLE_API_KEY:
        raise RuntimeError("ไม่มี GOOGLE_API_KEY ใน backend/.env — ตั้งค่าก่อนรันสคริปต์นี้")

    path = Path(audio_path)
    if not path.exists():
        raise FileNotFoundError(f"ไม่พบไฟล์เสียง: {audio_path}")

    client = genai.Client(api_key=config.GOOGLE_API_KEY)
    uploaded_file = _upload_and_wait(client, path)

    succeeded_model = {"name": None}

    def factory(model: str) -> str:
        return model

    def call(model: str) -> AudioTranscriptResult:
        print(f"[transcribe] เรียก Gemini model={model} ...")
        response = client.models.generate_content(
            model=model,
            contents=[uploaded_file, _TRANSCRIPTION_SYSTEM_PROMPT],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=AudioTranscriptResult,
                http_options=types.HttpOptions(timeout=config.GEMINI_TRANSCRIPTION_TIMEOUT_MS),
            ),
        )
        if response.parsed is None:
            raise RuntimeError(f"Gemini (model={model}) ไม่คืน structured output ที่ parse ได้")
        succeeded_model["name"] = model
        return response.parsed

    primary_model = model_override or config.GEMINI_MODEL_TRANSCRIPTION
    fallback_models = [] if model_override else config.GEMINI_MODEL_TRANSCRIPTION_FALLBACK
    result, error = run_with_fallback(
        primary_model,
        fallback_models,
        factory,
        call,
        "[TRANSCRIBE]",
        log=print,
    )

    try:
        client.files.delete(name=uploaded_file.name)
    except Exception as cleanup_err:  # ไม่ critical — แค่เก็บกวาดไฟล์ที่อัปโหลดไว้ชั่วคราวบน Google
        print(f"[transcribe] เก็บกวาดไฟล์ที่อัปโหลดไม่สำเร็จ (ไม่ critical): {cleanup_err}")

    if result is None:
        raise RuntimeError(f"เรียก Gemini ไม่สำเร็จทุก model: {error}")

    return result, succeeded_model["name"]


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
        "../experiments/transcription_experiment_result.txt — สมมติรันจาก backend/ ตามตัวอย่างด้านบน; "
        "ไฟล์ทดลองทั้งหมดของสคริปต์นี้รวมไว้ที่ experiments/ ตั้งแต่ 2026-08-04)",
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
        result, model_used = transcribe_audio_native(args.audio, model_override=args.model)
    except Exception as e:
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
