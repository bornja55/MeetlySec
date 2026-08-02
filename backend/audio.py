"""
audio.py — HTTP client เรียกไปหา Com Sec Audio Worker (โปรเซสแยกต่างหาก,
`D:\\Com Sec\\audio_worker\\main.py`)

ตัดสินใจสถาปัตยกรรม (2026-08-02, ต่อจาก /debug-mantra session ที่วัด VRAM จริง): audio worker
เป็นโปรเซสแยก ไม่รวมเข้า FastAPI หลักนี้ — เหตุผลเดียวกับ `rag.py`/`rag_worker` เป๊ะ (กัน Windows
WINHTTP.dll crash จากรวม torch เข้าโปรเซสเดียวกับ web layer) ไฟล์นี้จึงเป็นแค่ HTTP client บางๆ
ไม่มี torch/nemo/pyannote อยู่ในโปรเซสนี้เลย เหมือน `rag.py` ไม่มี torch/faiss

⚠️ **ยังไม่มีจุดเรียกใช้จริง (caller)**: Meeting entity + upload endpoint (ที่จะเป็นคนเรียก
`audio_pipeline.process()` นี้) ยังไม่ได้ออกแบบ — ต้องตัดสินใจเรื่อง persistence layer ก่อน
(SQLite/SQLAlchemy? JSON file? ยังไม่มี DB ใดๆในโปรเจกต์นี้เลยตอนนี้) ไฟล์นี้เตรียมไว้ให้พร้อมเรียก
ได้ทันทีที่ upload endpoint ถูกออกแบบแล้ว
"""
import os

import httpx

AUDIO_WORKER_BASE_URL = os.environ.get("AUDIO_WORKER_BASE_URL", "http://127.0.0.1:8767")

# ประมวลผลเสียงประชุมอาจใช้เวลานาน (diarization เต็มไฟล์ + ASR หลายชิ้นละ 1 ชม. สำหรับประชุมยาว
# หลายชั่วโมง) — ตั้ง timeout กว้างไว้ก่อนเหมือน rag.py (ปรับตามจริงหลัง live test แรกเหมือนที่
# RAG_WORKER_TIMEOUT_SECONDS เคยต้องปรับมาแล้ว 2 รอบ)
AUDIO_WORKER_TIMEOUT_SECONDS = float(os.environ.get("AUDIO_WORKER_TIMEOUT_SECONDS", "3600"))


class AudioWorkerError(Exception):
    """Worker ไม่พร้อมใช้งาน / ตอบ error / เชื่อมต่อไม่ได้ — main.py จับแล้วแปลงเป็น HTTPException
    ไม่ปล่อยให้ traceback ดิบหลุดไปถึง client"""


class AudioWorkerBusyError(AudioWorkerError):
    """worker กำลังประมวลผลไฟล์อื่นอยู่ (queue เดียว ไม่ขนาน ตามการตัดสินใจ Module 2) —
    แยก exception type ต่างหากเพื่อให้ caller เลือก retry-with-backoff ได้แทนที่จะ error ทันที"""


class AudioPipeline:
    """Thin HTTP client ไป Com Sec Audio Worker — ไม่ถือ state/โมเดลใดๆ ในโปรเซสนี้เลย
    (state/โมเดลทั้งหมดอยู่ที่ worker คนละโปรเซส)"""

    def process(self, meeting_id: str, filename: str) -> dict:
        """เรียก worker `/process` — `filename` ต้องเป็นชื่อไฟล์ที่ backend บันทึกไว้แล้วใน
        `audio_worker`'s UPLOAD_DIR (shared filesystem path บนเครื่องเดียวกัน ไม่ส่งไฟล์ซ้ำผ่าน
        HTTP body — ดู audio_worker/worker_config.py's docstring) คืน dict
        {"job_id", "elapsed_seconds", "transcript_segments"} ตรงจาก worker (field เดียว
        `transcript_segments` แทน diarization_segments/asr_chunks เดิม — redesign 2026-08-02,
        ดู handoff.md 3.3)"""
        try:
            resp = httpx.post(
                f"{AUDIO_WORKER_BASE_URL}/process",
                json={"meeting_id": meeting_id, "filename": filename},
                timeout=AUDIO_WORKER_TIMEOUT_SECONDS,
            )
        except httpx.ConnectError as e:
            raise AudioWorkerError(
                f"เชื่อมต่อ Audio worker ไม่ได้ที่ {AUDIO_WORKER_BASE_URL} — worker รันอยู่หรือไม่? "
                f"(D:\\Com Sec\\audio_worker\\start_worker.bat)"
            ) from e
        except httpx.TimeoutException as e:
            raise AudioWorkerError(
                f"Audio worker ตอบช้าเกิน {AUDIO_WORKER_TIMEOUT_SECONDS}s"
            ) from e

        if resp.status_code == 409:
            raise AudioWorkerBusyError(_safe_detail(resp) or "worker กำลังยุ่งอยู่")
        if resp.status_code == 404:
            raise AudioWorkerError(_safe_detail(resp) or "ไม่พบไฟล์เสียงที่ระบุ")
        if resp.status_code >= 400:
            detail = _safe_detail(resp)
            raise AudioWorkerError(f"Audio worker error ({resp.status_code}): {detail}")

        return resp.json()

    def health(self) -> dict:
        try:
            resp = httpx.get(f"{AUDIO_WORKER_BASE_URL}/health", timeout=5.0)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as e:
            raise AudioWorkerError(f"เชื่อมต่อ Audio worker ไม่ได้: {e}") from e


def _safe_detail(resp: httpx.Response) -> str:
    try:
        payload = resp.json()
        return payload.get("detail") or payload.get("error") or str(payload)
    except ValueError:
        return resp.text


# Singleton instance — ตั้งชื่อให้สอดคล้องกับ rag_pipeline ใน rag.py
audio_pipeline = AudioPipeline()
