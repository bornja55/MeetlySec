"""
main.py — Com Sec Audio Worker (Module 2: Diarization + ASR), entrypoint

ตัดสินใจสถาปัตยกรรม (2026-08-02): โปรเซสแยกจาก backend หลักเหมือน `rag_worker/` — เหตุผลเต็มอยู่ที่
`worker_config.py`'s docstring (สรุปสั้นๆ: กัน Windows WINHTTP.dll access-violation crash จากการรวม
torch เข้าโปรเซสเดียวกับ web layer เหมือนที่เคยพบตอนสร้าง RAG worker)

รัน: `venv\\Scripts\\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8767`
(ดู start_worker.bat)
"""
import logging
import os
import uuid

import pipeline
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from worker_config import LOG_FILE, PORT, UPLOAD_DIR

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler(LOG_FILE, encoding="utf-8"), logging.StreamHandler()],
)
log = logging.getLogger("audio_worker")

app = FastAPI(title="Com Sec Audio Worker", version="1.0.0")


class ProcessBody(BaseModel):
    meeting_id: str
    # path สัมพัทธ์กับ UPLOAD_DIR (backend เป็นคนบันทึกไฟล์จริงไว้ก่อนเรียก endpoint นี้ — ดู
    # worker_config.py's docstring เรื่อง shared filesystem path แทนอัปโหลดซ้ำผ่าน HTTP body)
    filename: str


@app.get("/health")
def health():
    return {"status": "ready", **pipeline.get_status()}


def _reject_path_traversal(name: str, field: str) -> None:
    """กันกรณี meeting_id/filename มี `..`/separator แอบพาออกนอก UPLOAD_DIR/PROCESSED_DIR —
    พบจาก /scrutinize: worker นี้เป็น HTTP service เปิดอยู่บน localhost ไม่มี auth เลย ถ้า
    caller (ตอนนี้ยังไม่มีใครเรียกจริงนอกจาก dev เอง) ส่งค่าที่มี path traversal เข้ามาจะเปิดไฟล์
    นอก UPLOAD_DIR ได้ตรงๆ — เช็คกันไว้ก่อนแม้ความเสี่ยงตอนนี้จะต่ำ (localhost-only)"""
    if any(sep in name for sep in ("..", "/", "\\")):
        raise HTTPException(status_code=400, detail=f"{field} มีอักขระที่ไม่อนุญาต: {name!r}")


@app.post("/process")
def process(body: ProcessBody):
    _reject_path_traversal(body.filename, "filename")
    _reject_path_traversal(body.meeting_id, "meeting_id")

    input_path = os.path.join(UPLOAD_DIR, body.filename)
    if not os.path.isfile(input_path):
        raise HTTPException(status_code=404, detail=f"ไม่พบไฟล์: {input_path}")

    job_id = f"{body.meeting_id}_{uuid.uuid4().hex[:8]}"
    log.info(f"เริ่มประมวลผล job_id={job_id} input={input_path}")
    try:
        result = pipeline.process_audio_file(job_id, input_path)
    except pipeline.WorkerBusyError as e:
        log.warning(f"job_id={job_id} ถูกปฏิเสธ: worker ยุ่งอยู่")
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        log.error(f"job_id={job_id} ล้มเหลว: {type(e).__name__}: {e}")
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")

    log.info(f"job_id={job_id} เสร็จใน {result['elapsed_seconds']:.1f}s")
    return result


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=PORT, reload=False)
