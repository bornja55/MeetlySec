"""
audio_native.py — เรียก Gemini native audio understanding โดยตรงจากโปรเซส backend เพื่อถอดเสียง +
speaker diarization ของไฟล์ประชุม แทน `audio_worker` (โปรเซสแยก pyannote+typhoon-asr เดิม)

**ตัดสินใจสถาปัตยกรรม (2026-08-04, `/grill-me` เต็มรอบ 7 ข้อ — ดู handoff.md 3.14, task.md บรรทัด
164-191 สำหรับรายละเอียดเต็ม)**:
1. **แทนที่ `audio_worker` ทั้งชุด** — ตรวจ `implementation_plan.md`/`task.md` แล้วไม่มีเหตุผล
   compliance ใดๆบังคับให้ diarization/ASR ต้องรัน local เลย เหตุผลเดิมคือข้อจำกัดฮาร์ดแวร์ (GPU
   4GB/6GB) ล้วนๆ ไม่ใช่การตัดสินใจเชิงนโยบาย — ทดลองจริง 2 รอบ (10 นาที + ไฟล์เต็ม 55 นาที, ดู
   handoff.md 3.13-3.14) ยืนยันว่า Gemini native audio ให้ผลดีกว่า pyannote+typhoon-asr มาก
   (speaker count สมเหตุสมผล ไม่มี fragmentation, เร็วกว่า 3-4 เท่า)
2. **เรียก Gemini ตรงจากโปรเซส backend เอง ไม่ใช่ worker process แยกอีกต่อไป** — เหตุผลเดิมที่ต้อง
   แยกโปรเซส (กัน Windows WINHTTP.dll crash จากรวม torch เข้าโปรเซสเดียวกับ web layer, ดู `rag.py`/
   `audio.py`) ไม่เกี่ยวข้องแล้วเพราะ `google-genai` ไม่มี native library (torch/faiss) ที่จะชนกัน
3. **แปลง schema ที่จุดเดียวในไฟล์นี้** (`_adapt_segments()`): Gemini คืน `start_seconds`/
   `end_seconds`/`speaker_label` → แปลงเป็น `start`/`end`/`speaker` ให้ตรงกับ
   `transcript_segments_json` เดิมทันทีตอนรับผล ไม่ต้องแก้ `_extract_speaker_labels()`/speaker
   mapping endpoint/`minutes_generation.py`/`app.js` เลยสักจุด (ทั้งหมดยังอ่าน key เดิม)
4. **Paid-tier gate = documentation เท่านั้น** เหมือน Module 3 (`minutes_generation.py`) — ไม่มีทาง
   enforce ด้วยโค้ดจริงเพราะ Gemini API ไม่มีทางเช็คได้ว่า key เป็น free/paid tier — ⚠️ **เนื้อหา
   ประชุมบอร์ดจริงต้องเปิด billing ก่อนเสมอ** (ข้อยกเว้นเฉพาะไฟล์ที่ SET เปิดเผยแล้วเท่านั้น ดู
   handoff.md 3.13 สำหรับรายละเอียดข้อยกเว้นนี้)
5. **Error handling ใช้ pattern เดิมทั้งหมด** — ไม่ override model ปล่อยให้ fallback chain
   (`GEMINI_MODEL_TRANSCRIPTION` → `GEMINI_MODEL_TRANSCRIPTION_FALLBACK`, ดู `config.py`) ที่มี
   retry-with-backoff อยู่แล้วจาก `llm_fallback.run_with_fallback()` จัดการ ถ้าพังหมดทุกโมเดล raise
   `AudioNativeError` เดียว ให้ `main.py` แปลงเป็น `status="failed"` + `processing_error` เหมือน
   `AudioWorkerError` เดิมทุกประการ
6. **ไม่มี concept "worker กำลังยุ่ง" อีกต่อไป** (เดิม `audio_worker` มี queue เดียวกันการชน GPU
   เครื่องเดียว — ดู `AudioWorkerBusyError` ใน `audio.py`) — Gemini API เป็น cloud call รองรับ
   concurrent request ได้ (ผูกกับ rate limit ของ API key เอง ไม่ใช่ทรัพยากรเครื่อง) หลาย background
   task ประมวลผลพร้อมกันได้โดยไม่ต้อง lock ระดับโปรเซสอีกต่อไป
7. **ตัดไฟล์เป็น chunk ก่อนส่ง Gemini (เพิ่ม 2026-08-05, ดู handoff.md 3.19/3.21)** — พบว่า timestamp
   ที่ Gemini รายงานเองคลาดสะสมตามสัดส่วนความยาวไฟล์ (ไฟล์ 55 นาทีที่ทดสอบจริงคลาดท้ายไฟล์เกือบ 38
   นาที) ค้นข้อมูลแล้วยืนยันว่าหลายทีมอิสระเจอปัญหาเดียวกัน (Towards Data Science's production
   pipeline, pyvideotrans issue #624, madeyexz/youtube2transcripts) และแก้ด้วยวิธีเดียวกันตรงกันหมด:
   ตัดไฟล์เป็นชิ้นสั้นๆ (ดีฟอลต์ 10 นาที + overlap 30 วิ, ดู `config.py`/`audio_chunking.py`) ก่อนส่ง
   Gemini ทีละชิ้น แล้วคำนวณ timestamp จริงเองจาก `chunk_offset + timestamp_สัมพัทธ์ที่ Gemini
   รายงานภายใน chunk` แทนที่จะเชื่อ timestamp สัมบูรณ์ที่ Gemini ประมาณเองสำหรับไฟล์ยาวทั้งไฟล์ —
   `transcribe_audio_native()` (ใช้โดย `audio_transcription_experiment.py` สำหรับเทียบโมเดลไฟล์เดียว)
   **ไม่เปลี่ยนพฤติกรรม ไม่ chunk** ยังคงส่งทีเดียวทั้งไฟล์เหมือนเดิมเป๊ะ — chunking อยู่ที่
   `transcribe_meeting_audio()` (production path ที่ `main.py` เรียกจริง) เท่านั้น

⚠️ **ยังไม่ตัดขาด `audio_worker/` จริง** (ข้อ 7 ของ `/grill-me`): ทดสอบจริงมีแค่ไฟล์ประชุมเดียว (2-3
รอบ/โมเดล) ยังไม่พอมั่นใจว่าคุณภาพสม่ำเสมอกับประชุมอื่น (คนพูดเยอะกว่า/เสียงคุณภาพแย่กว่า) — ไฟล์นี้
เตรียม wiring ไว้ให้ `backend/main.py` สลับมาเรียกได้แล้ว (ดู session ที่เขียนไฟล์นี้ใน handoff.md)
แต่ **ห้ามลบ `audio_worker/`/`backend/audio.py` เองโดยไม่ถามผู้ใช้ก่อน** จนกว่าจะทดสอบเพิ่มผ่านด่านนี้

Logic หลัก (Pydantic schema/system prompt/upload+poll ผ่าน Files API) copy มาจาก
`backend/audio_transcription_experiment.py` ที่ทดลองแล้วยืนยันผลดีจริง 2 รอบ (ดู handoff.md
3.13-3.14) — ไฟล์ experiment เดิมแก้ให้ import จากที่นี่แทนแล้ว กันโค้ด diverge ระหว่าง production
path กับสคริปต์ทดลอง
"""
import mimetypes
import tempfile
import time
from pathlib import Path

import audio_chunking
import config
from google import genai
from google.genai import types
from llm_fallback import run_with_fallback
from pydantic import BaseModel, Field


class AudioNativeError(Exception):
    """เรียก Gemini native audio ไม่สำเร็จ (ไม่มี API key / ไม่พบไฟล์ / อัปโหลดล้มเหลว / ทุกโมเดลใน
    fallback chain ล้มเหลว) — `main.py` จับแล้วตั้ง `meeting.status = "failed"` เหมือน
    `AudioWorkerError` เดิม ไม่ปล่อยให้ traceback ดิบหลุดไปถึง background task"""


class AudioTranscriptSegment(BaseModel):
    start_seconds: float = Field(..., description="เวลาเริ่มพูดของ segment นี้ นับจากต้นไฟล์ (วินาที)")
    end_seconds: float = Field(..., description="เวลาจบพูดของ segment นี้ (วินาที)")
    speaker_label: str = Field(
        ...,
        description=(
            'ป้ายชื่อผู้พูด ตั้งเองให้สอดคล้องกันตลอดทั้งไฟล์ เช่น "Speaker 1" — '
            "คนเดียวกันต้องใช้ label เดียวกันเสมอ"
        ),
    )
    text: str = Field(..., description="คำพูดจริงในช่วงนี้ ห้ามแต่งเติมหรือสรุปเอง ต้องเป็นคำที่ได้ยินจริง")


class AudioTranscriptResult(BaseModel):
    segments: list[AudioTranscriptSegment] = Field(
        ..., description="รายการ segment เรียงตามเวลา ครอบคลุมทั้งไฟล์"
    )


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


def _upload_and_wait(client: genai.Client, audio_path: Path, log) -> types.File:
    """⚠️ พบบั๊กจริง (2026-08-05, ผู้ใช้รายงานว่า backend terminal "นิ่ง" หลังอัปโหลด — mantra 2
    trace path จริงพบว่าฟังก์ชันนี้ไม่เคยรับ/เรียก `log` เลยตั้งแต่ refactor จาก
    `audio_transcription_experiment.py` เดิม (ที่มี `print()` ทุกรอบ poll) ทำให้ระหว่าง
    `client.files.upload()` (อาจช้าถ้าไฟล์ใหญ่) และ poll loop `PROCESSING`→`ACTIVE` ไม่มี log
    ออกมาเลยสักบรรทัด — ดูเหมือนค้างทั้งที่จริงกำลังทำงานปกติอยู่ — แก้แล้วด้วยการรับ `log` เข้ามา
    และ log ทุกจุดที่อาจใช้เวลานาน"""
    mime_type, _ = mimetypes.guess_type(str(audio_path))
    log(f"[transcribe] กำลังส่งไฟล์ {audio_path} (mime={mime_type or 'ไม่ทราบ, ให้ SDK เดา'}) "
        f"ไปยัง Gemini Files API ...")
    uploaded = client.files.upload(file=str(audio_path))
    log(f"[transcribe] อัปโหลดไบต์เสร็จแล้ว (name={uploaded.name}, state={uploaded.state}) "
        f"กำลังรอ Gemini ประมวลผลไฟล์...")
    # Files API เป็น async สำหรับไฟล์ใหญ่ — poll จนกว่าจะ ACTIVE
    poll_count = 0
    while uploaded.state == types.FileState.PROCESSING:
        poll_count += 1
        log(f"[transcribe] Gemini กำลังประมวลผลไฟล์ที่อัปโหลด รอ... (poll #{poll_count}, "
            f"~{poll_count * 3}s)")
        time.sleep(3)
        uploaded = client.files.get(name=uploaded.name)
    if uploaded.state == types.FileState.FAILED:
        raise AudioNativeError(f"อัปโหลดไฟล์เข้า Gemini ล้มเหลว: {uploaded.error}")
    return uploaded


def _transcribe_one_file(
    client: genai.Client,
    path: Path,
    log,
    *,
    model_override: str | None = None,
    extra_prompt_context: str = "",
) -> tuple[AudioTranscriptResult, str]:
    """แกนกลางจริงของการเรียก Gemini 1 ครั้งต่อไฟล์ 1 ไฟล์ (อัปโหลด+poll+call-with-fallback+cleanup)
    — ทั้ง `transcribe_audio_native()` (เดิม ไม่ chunk สำหรับ CLI experiment) และ
    `transcribe_meeting_audio()` (production path ที่ chunk แล้วเรียกทางนี้ทีละ chunk) ใช้ฟังก์ชันนี้
    ร่วมกัน — แยกออกมาตอนเพิ่ม chunking (2026-08-05) กันโค้ด upload/fallback/cleanup ซ้ำกัน 2 ที่

    extra_prompt_context: ข้อความเสริมต่อท้าย system prompt เฉพาะตอนเรียกจาก chunk ที่ไม่ใช่ชิ้นแรก
    (ให้บริบทผู้พูดที่เคยเจอมาก่อนหน้า กัน speaker label สลับข้าม chunk — ดู
    `transcribe_meeting_audio()`) ปล่อยว่างเมื่อไม่ได้ chunk (พฤติกรรมเดิมเป๊ะ)"""
    uploaded_file = _upload_and_wait(client, path, log)
    log(f"[transcribe] ไฟล์พร้อมใช้งานแล้ว: {uploaded_file.name} ({uploaded_file.size_bytes} bytes)")

    succeeded_model = {"name": None}
    prompt = _TRANSCRIPTION_SYSTEM_PROMPT + extra_prompt_context

    def factory(model: str) -> str:
        return model

    def call(model: str) -> AudioTranscriptResult:
        log(f"[transcribe] เรียก Gemini model={model} ...")
        response = client.models.generate_content(
            model=model,
            contents=[uploaded_file, prompt],
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
        primary_model, fallback_models, factory, call, "[TRANSCRIBE]", log=log,
    )

    try:
        client.files.delete(name=uploaded_file.name)
    except Exception as cleanup_err:  # ไม่ critical — แค่เก็บกวาดไฟล์ที่อัปโหลดไว้ชั่วคราวบน Google
        log(f"[transcribe] เก็บกวาดไฟล์ที่อัปโหลดไม่สำเร็จ (ไม่ critical): {cleanup_err}")

    if result is None:
        raise AudioNativeError(f"เรียก Gemini ไม่สำเร็จทุก model: {error}")

    return result, succeeded_model["name"]


def transcribe_audio_native(
    audio_path: str, *, model_override: str | None = None, log=lambda *_a, **_kw: None,
) -> tuple[AudioTranscriptResult, str]:
    """ส่งไฟล์เสียงเข้า Gemini ตรงๆ ทีเดียวทั้งไฟล์ (ไม่ chunk) คืน (ผลลัพธ์, ชื่อโมเดลที่สำเร็จจริง)
    — raise `AudioNativeError` ถ้าไม่มี API key / ไม่พบไฟล์ / อัปโหลดล้มเหลว / ทุกโมเดลใน fallback
    chain ล้มเหลว **ใช้จาก `audio_transcription_experiment.py` สำหรับทดลองเทียบโมเดลเท่านั้น —
    production path (`main.py`) เรียก `transcribe_meeting_audio()` ที่ chunk ให้อัตโนมัติแทน**

    model_override: ถ้าระบุ จะใช้โมเดลนี้ตัวเดียว (ไม่มี fallback chain) — สำหรับทดลองเทียบโมเดล
    เฉพาะกิจผ่าน `audio_transcription_experiment.py --model` **ต้องเป็นโมเดลหมวด "Text-out models"
    ที่รองรับ `generate_content()` + audio input เท่านั้น** โมเดลหมวด "Live API" ใช้ผ่านทางนี้ไม่ได้
    เพราะเป็นคนละ WebSocket streaming session (ดู handoff.md 3.13)

    log: callable(str) สำหรับ progress log — ดีฟอลต์เงียบ (ใช้จาก background task ใน `main.py` ที่
    ไม่มี stdout ให้ผู้ใช้ดู) ส่ง `print` เข้ามาเองถ้ารันจาก CLI (ดู
    `audio_transcription_experiment.py`)"""
    if not config.GOOGLE_API_KEY:
        raise AudioNativeError("ไม่มี GOOGLE_API_KEY ใน backend/.env — ตั้งค่าก่อนใช้งาน")

    path = Path(audio_path)
    if not path.exists():
        raise AudioNativeError(f"ไม่พบไฟล์เสียง: {audio_path}")

    client = genai.Client(api_key=config.GOOGLE_API_KEY)
    return _transcribe_one_file(client, path, log, model_override=model_override)


def _adapt_segments(result: AudioTranscriptResult) -> list[dict]:
    """แปลง schema ของ Gemini (`start_seconds`/`end_seconds`/`speaker_label`) เป็น
    `{start, end, speaker, text}` — ตรงกับ `transcript_segments_json` เดิมที่ `audio_worker` เคย
    คืนมา (ดู decision ข้อ 3 ในหัวไฟล์) จุดแปลง schema เดียวของทั้งระบบ"""
    return [
        {
            "start": seg.start_seconds,
            "end": seg.end_seconds,
            "speaker": seg.speaker_label,
            "text": seg.text,
        }
        for seg in result.segments
    ]


def _speaker_context_prompt(labels_seen: list[str]) -> str:
    """สร้างข้อความเสริม prompt บอก Gemini ว่าเจอผู้พูดคนไหนมาแล้วในไฟล์เดียวกัน (chunk ก่อนหน้า) —
    ⚠️ เป็นแค่ mitigation แบบ soft ไม่รับประกัน 100% ว่า label จะตรงกันข้าม chunk เสมอ (Gemini อาจ
    ยังตั้ง label ใหม่ให้คนเดิมถ้าน้ำเสียงในช่วงนั้นต่างจากช่วงก่อน เช่น พูดเบา/มีเสียงรบกวน) — ไม่มี
    แหล่งอ้างอิงไหนที่ค้นมา (ดู handoff.md 3.21) แก้ปัญหานี้ได้สมบูรณ์แบบ แม้แต่ TDS's production
    pipeline ก็ต้องใช้ LLM merge step แยกต่างหากทั้งอัน ซึ่งซับซ้อนเกินไปสำหรับตอนนี้ — ถ้าพบว่า label
    สลับข้าม chunk บ่อยจากการใช้งานจริง ค่อยพิจารณา merge step เพิ่มทีหลัง"""
    if not labels_seen:
        return ""
    labels_text = ", ".join(labels_seen)
    return (
        "\n\nหมายเหตุสำคัญ: ไฟล์เสียงนี้ถูกตัดเป็นช่วงๆแล้วส่งเข้ามาทีละช่วง ช่วงก่อนหน้านี้ในไฟล์"
        f"เดียวกันมีผู้พูดที่เคยระบุ label ไว้แล้วคือ: {labels_text} — ถ้าเสียงในช่วงนี้เป็นคนเดิม "
        "(น้ำเสียง/ลักษณะการพูดตรงกัน) ให้ใช้ label เดิมต่อ ห้ามตั้ง label ใหม่ให้คนที่เคยมี label "
        "แล้ว แต่ถ้าเป็นคนใหม่ที่ยังไม่เคยเจอ ตั้ง label ใหม่ตามปกติได้"
    )


def transcribe_meeting_audio(
    audio_path: str, *, log=lambda *_a, **_kw: None, model_override: str | None = None,
    checkpoint_key: str | None = None,
) -> dict:
    """จุดเรียกหลักจาก `backend/main.py`'s `_process_meeting_audio_background()` — แทนที่
    `audio.AudioPipeline.process()` เดิม (เรียก `audio_worker` ผ่าน HTTP) คืน dict
    `{"transcript_segments", "model_used", "elapsed_seconds"}` (field แรกใช้ schema เดียวกับที่
    `audio_worker` เคยคืน ส่วนอีก 2 field ใหม่ไว้ log/debug เพิ่มเติม — ไม่มี "job_id" อีกต่อไปเพราะ
    ไม่มี worker process แยกให้ track job) raise `AudioNativeError` ถ้าล้มเหลว

    **Chunking (2026-08-05, ดู handoff.md 3.19/3.21)**: ไฟล์ที่สั้นกว่า `AUDIO_CHUNK_SECONDS` ไม่ถูก
    ตัดเลย (ทางเดียวกับก่อนมี feature นี้เป๊ะๆ — ประชุมส่วนใหญ่ไม่ยาวเกิน 10 นาทีอยู่แล้ว) ไฟล์ที่ยาว
    กว่าถูกตัดเป็นชิ้น + overlap ผ่าน `audio_chunking.py` แล้วเรียก Gemini ทีละชิ้น timestamp ที่ได้
    ต่อ chunk ถูกปรับเป็นเวลาจริงในไฟล์ต้นฉบับก่อน merge (บวก `chunk.offset_seconds`) — ถ้า chunk
    ไหนล้มเหลวหมดทุก model ในระหว่างนั้น ทั้งการถอดเสียงไฟล์นี้ถือว่าล้มเหลว (raise ทันที ไม่คืนผลลัพธ์
    บางส่วนแบบเงียบๆ — สอดคล้องกับ error semantics เดิมของทั้งระบบที่ status="failed" ต้องชัดเจน)

    model_override (2026-08-05, ผู้ใช้เลือกเองตอน upload — ดู `config.py`'s
    `GEMINI_TRANSCRIPTION_MODEL_CHOICES`/`main.py`'s `GET /api/transcription_models`): ถ้าระบุ ใช้
    โมเดลนี้ตัวเดียวสำหรับ**ทุก chunk** (ไม่มี fallback chain เลย — ตรงกับ semantics เดิมของ
    `_transcribe_one_file()`'s `model_override` param อยู่แล้ว ตั้งใจไม่ fallback เพราะผู้ใช้เลือกเอง
    ก็มักจะเป็นเพราะโมเดลอื่นในลิสต์ fallback โควต้าใกล้เต็มพอดี — silent fallback กลับไปโมเดลที่กำลัง
    หลบอยู่จะขัดจุดประสงค์ที่เลือกเอง) ปล่อยว่าง (`None`) ใช้ fallback chain ปกติจาก config.py
    เหมือนเดิมทุกประการ (ไม่กระทบพฤติกรรมเดิมถ้าไม่ระบุ)

    checkpoint_key (2026-08-05, session 3.32 — ดู handoff.md): ถ้าระบุ (ปกติ `main.py` ส่ง
    `str(meeting_id)` มา) บันทึกความคืบหน้าทุกครั้งที่ 1 chunk สำเร็จลง
    `audio_chunking._CHECKPOINT_DIR` — เรียกฟังก์ชันนี้ซ้ำด้วย checkpoint_key เดิม (เช่น re-upload
    ไฟล์เดิมไปยัง meeting เดิมหลัง chunk กลางไฟล์ fail) จะข้าม chunk ที่สำเร็จแล้วไปเลย ไม่เรียก Gemini
    ซ้ำ (ที่มา: เจอ 11-chunk job ตายที่ chunk 7 เพราะ 503 ชนพอดีกับ backend restart — chunk 1-6 ที่
    เพิ่งเปลืองเควตาไปฟรีถ้าไม่มี feature นี้) — เฉพาะ multi-chunk path เท่านั้น (ไฟล์สั้นไม่ตัด chunk
    ไม่ต้อง checkpoint แค่ 1 call เดียว) ปล่อยว่าง (`None`) = ไม่ checkpoint เลย (พฤติกรรมเดิมเป๊ะ —
    ใช้จาก `audio_transcription_experiment.py`/CLI script ที่ไม่มี concept "meeting" ผูกอยู่)"""
    t0 = time.time()

    if not config.GOOGLE_API_KEY:
        raise AudioNativeError("ไม่มี GOOGLE_API_KEY ใน backend/.env — ตั้งค่าก่อนใช้งาน")
    path = Path(audio_path)
    if not path.exists():
        raise AudioNativeError(f"ไม่พบไฟล์เสียง: {audio_path}")

    try:
        total_duration = audio_chunking.get_duration_seconds(str(path))
    except audio_chunking.FFmpegError as e:
        raise AudioNativeError(f"หาความยาวไฟล์เสียงไม่ได้ (ffprobe): {e}") from e

    plan = audio_chunking.plan_chunks(total_duration)
    client = genai.Client(api_key=config.GOOGLE_API_KEY)

    if len(plan) == 1:
        # ไฟล์สั้นกว่า 1 chunk — ไม่ต้องผ่าน ffmpeg เลย เรียกตรงเหมือนก่อนมี chunking feature นี้
        log(f"[transcribe] ไฟล์ยาว {total_duration:.0f}s สั้นกว่า chunk เดียว ({config.AUDIO_CHUNK_SECONDS}s) — ไม่ตัด")
        result, model_used = _transcribe_one_file(client, path, log, model_override=model_override)
        adapted, scale = audio_chunking.rescale_chunk_segments(_adapt_segments(result), total_duration)
        if scale is not None:
            log(
                f"[transcribe] แก้ proportional timestamp drift: Gemini รายงาน end เกินความยาวไฟล์จริง "
                f"— ปรับสัดส่วนด้วย scale={scale:.3f} (ดู handoff.md session 3.19/3.29 สำหรับที่มา)"
            )
        return {
            "transcript_segments": adapted,
            "model_used": model_used,
            "elapsed_seconds": time.time() - t0,
        }

    log(
        f"[transcribe] ไฟล์ยาว {total_duration:.0f}s ตัดเป็น {len(plan)} chunk "
        f"(chunk={config.AUDIO_CHUNK_SECONDS}s, overlap={config.AUDIO_CHUNK_OVERLAP_SECONDS}s) "
        f"เพื่อกัน timestamp drift"
    )

    with tempfile.TemporaryDirectory(prefix="com_sec_audio_chunks_") as tmp_dir:
        try:
            chunks = audio_chunking.split_into_chunks(str(path), tmp_dir)
        except audio_chunking.FFmpegError as e:
            raise AudioNativeError(f"ตัดไฟล์เสียงเป็น chunk ไม่สำเร็จ (ffmpeg): {e}") from e

        all_chunk_segments: list[list[dict]] = []
        models_used: list[str] = []
        labels_seen: list[str] = []
        start_index = 0

        if checkpoint_key:
            checkpoint = audio_chunking.load_checkpoint(checkpoint_key, plan)
            if checkpoint is not None:
                all_chunk_segments = checkpoint["all_chunk_segments"]
                models_used = checkpoint["models_used"]
                labels_seen = checkpoint["labels_seen"]
                start_index = len(all_chunk_segments)
                log(
                    f"[transcribe] พบ checkpoint เดิม (key={checkpoint_key}) — ข้าม {start_index} "
                    f"chunk ที่สำเร็จแล้ว เริ่มต่อจาก chunk {start_index + 1}/{len(chunks)}"
                )

        for chunk in chunks[start_index:]:
            log(f"[transcribe] chunk {chunk.index + 1}/{len(chunks)} (offset={chunk.offset_seconds:.0f}s) ...")
            extra_prompt = _speaker_context_prompt(labels_seen)
            result, model_used = _transcribe_one_file(
                client, Path(chunk.path), log,
                model_override=model_override, extra_prompt_context=extra_prompt,
            )
            adapted, scale = audio_chunking.rescale_chunk_segments(
                _adapt_segments(result), chunk.duration_seconds
            )
            if scale is not None:
                log(
                    f"[transcribe] chunk {chunk.index + 1}: แก้ proportional timestamp drift "
                    f"scale={scale:.3f} (Gemini รายงาน end เกินความยาว chunk จริง)"
                )
            for seg in adapted:
                seg["start"] += chunk.offset_seconds
                seg["end"] += chunk.offset_seconds
                if seg["speaker"] not in labels_seen:
                    labels_seen.append(seg["speaker"])
            all_chunk_segments.append(adapted)
            models_used.append(model_used)
            if checkpoint_key:
                audio_chunking.save_checkpoint(
                    checkpoint_key, plan, all_chunk_segments, models_used, labels_seen
                )

    merged_segments = audio_chunking.merge_chunk_segments(all_chunk_segments, plan)
    unique_models = list(dict.fromkeys(models_used))  # คง order, ตัดซ้ำ
    model_used_summary = unique_models[0] if len(unique_models) == 1 else "+".join(unique_models)

    if checkpoint_key:
        audio_chunking.clear_checkpoint(checkpoint_key)  # สำเร็จครบทุก chunk แล้ว ไม่ต้อง resume อีก

    return {
        "transcript_segments": merged_segments,
        "model_used": model_used_summary,
        "elapsed_seconds": time.time() - t0,
    }
