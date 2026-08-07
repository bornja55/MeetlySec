"""
rag.py — HTTP client เรียกไปหา Com Sec RAG Worker (โปรเซสแยกต่างหาก, `D:\\Com Sec\\rag_worker\\main.py`)

ตัดสินใจสถาปัตยกรรม (handoff.md ข้อ 3.0.1, `/grill-me` รอบ 2 2026-08-01): RAG worker คงเป็น
โปรเซสแยก ไม่รวมเข้า FastAPI หลักนี้ (กัน Windows WINHTTP.dll crash จาก native-library conflict
ระหว่าง faiss/torch — ดู rag_worker/main.py docstring กับ Local RAG's HANDOFF.md) ไฟล์นี้จึงเป็น
แค่ HTTP client บางๆ — ไม่มี torch/faiss/llama_index/sentence-transformers อยู่ในโปรเซสนี้เลย

เดิม (ก่อนแก้ไข 2026-08-01): เป็น stub `RAGPipeline.query()` คืนค่า hardcoded string, ไม่มี
Vector DB จริง, ไม่เคย import sentence-transformers จริง — พบจาก `/scrutinize` (ดู handoff.md
ข้อ 3.0 "สิ่งที่พบ")
"""
import os

import httpx

RAG_WORKER_BASE_URL = os.environ.get("RAG_WORKER_BASE_URL", "http://127.0.0.1:8766")

# บั๊กจริงที่พบ 2026-08-01 (live test ครั้งแรก): เดิม default 60s สั้นเกินไป — worker เจอ
# {"detail":"RAG worker ตอบช้าเกิน 60.0s"} ทั้งที่ worker เองยัง process อยู่ (ดู log
# "[CHAT session=...] ถาม: ..." ที่ยังทำงานต่อหลัง client ตัดการเชื่อมต่อไปแล้ว)
#
# นี่คือบั๊ก class เดียวกับที่ Local RAG's HANDOFF.md (ADR-003) เคยพบและแก้มาก่อนแล้ว: client
# timeout ต้องคำนวณจาก worst-case ของทั้ง retry+fallback chain ฝั่ง worker ไม่ใช่เดาตัวเลขสั้นๆ
# worker เอง (worker_config.py) มี GEMINI_REQUEST_TIMEOUT_MS default 300000ms (5 นาที) ต่อการเรียก
# 1 ครั้ง, primary model retry ได้ถึง 3 ครั้ง (มี backoff 10s/20s ระหว่างรอบ), แล้วยังมี fallback
# model ต่อได้อีกหลายตัว (ดู .env.example: GEMINI_MODEL_CHAT_FALLBACK)
#
# อัปเดต (2026-08-01, หลัง live test จริงครั้งที่ 2): 600s (ตัวเลขแรกที่ตั้งไว้) ยังสั้นไป —
# log จริงจาก worker แสดง "สำเร็จใน 1005.03s (โมเดล: gemini-3.1-flash-lite)" คือสำเร็จที่ primary
# model เองเลย (ไม่ใช่ fallback) แปลว่า 1 รอบ retry loop (สูงสุด 3 attempt บนโมเดลเดียวกัน + backoff
# 10s/20s ถ้าเป็น quota error) ใช้เวลารวมเกิน 1000s จริง — ตั้ง default กว้างขึ้นอีกเป็น 1800s (30
# นาที) กันไว้ก่อน แต่ตัวเลข ~1000s ต่อ query เดียวสูงผิดปกติสำหรับโมเดล "lite" ควรตรวจสอบ network
# path ไปยัง generativelanguage.googleapis.com ต่อ (proxy/VPN/firewall การันตี DPI ที่อาจหน่วง
# TLS handshake) แยกต่างหาก ไม่ใช่แค่ยืดเวลา timeout ไปเรื่อยๆ
RAG_WORKER_TIMEOUT_SECONDS = float(os.environ.get("RAG_WORKER_TIMEOUT_SECONDS", "1800"))


class RAGWorkerError(Exception):
    """Worker ไม่พร้อมใช้งาน / ตอบ error / เชื่อมต่อไม่ได้ — main.py จับแล้วแปลงเป็น HTTPException
    (502/503 แล้วแต่กรณี) ไม่ปล่อยให้ traceback ดิบหลุดไปถึง client"""


class RAGPipeline:
    """Thin HTTP client ไป Com Sec RAG Worker — ไม่ถือ state/โมเดลใดๆ ในโปรเซสนี้เลย
    (state/โมเดลทั้งหมดอยู่ที่ worker คนละโปรเซส) เก็บชื่อ class/singleton เดิมไว้
    (`rag_pipeline`) เพื่อไม่ต้องแก้ import ใน main.py"""

    def query(
        self,
        user_query: str,
        user_id: str,
        search_scope: str = "general",
        role: str | None = None,
        meeting_id: str | int | None = None,
    ) -> dict:
        """เรียก worker `/query` (search_scope="general") หรือ `/query_confidential`
        (search_scope="confidential") คืน dict {"response", "sources", "tokens", ...} ตรงจาก
        worker — raise RAGWorkerError ถ้า worker ไม่ตอบ/ตอบ error (เช่น 503 = ยังโหลดโมเดลไม่เสร็จ,
        403 = role ไม่มีสิทธิ์)

        session key ที่ worker ใช้คือ user_id ที่ส่งมานี้ตรงๆ (ไม่ใช่ browser-tab session_id แบบ
        Local RAG เดิม — ตัดสินใจจาก handoff.md ข้อ 3.0.2 "เปลี่ยน session model... เป็นผูกกับ
        authenticated user_id จริง")

        `meeting_id` (session 3.37) — ใช้เฉพาะ `search_scope="confidential"` เท่านั้น จำกัดผลลัพธ์
        ให้อยู่แค่การประชุมที่เลือก ไม่ระบุ = ค้นหาทุกเอกสารลับเหมือนเดิม"""
        if not user_id:
            raise RAGWorkerError("ไม่พบ user_id — ต้อง authenticate ก่อนเรียก RAG query")

        if search_scope == "confidential":
            path = "/query_confidential"
            body = {"user_id": user_id, "role": role or "", "prompt": user_query, "meeting_id": meeting_id}
        else:
            path = "/query"
            body = {"user_id": user_id, "prompt": user_query}

        try:
            resp = httpx.post(
                f"{RAG_WORKER_BASE_URL}{path}",
                json=body,
                headers={"X-User-Id": user_id},
                timeout=RAG_WORKER_TIMEOUT_SECONDS,
            )
        except httpx.ConnectError as e:
            raise RAGWorkerError(
                f"เชื่อมต่อ RAG worker ไม่ได้ที่ {RAG_WORKER_BASE_URL} — worker รันอยู่หรือไม่? "
                f"(venv\\Scripts\\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8766 "
                f"ใน D:\\Com Sec\\rag_worker\\)"
            ) from e
        except httpx.TimeoutException as e:
            raise RAGWorkerError(f"RAG worker ตอบช้าเกิน {RAG_WORKER_TIMEOUT_SECONDS}s") from e

        if resp.status_code == 503:
            raise RAGWorkerError("RAG worker ยังโหลดโมเดลไม่เสร็จ กรุณาลองใหม่อีกครั้งในอีกสักครู่")
        if resp.status_code == 403:
            detail = _safe_detail(resp)
            raise RAGWorkerError(detail or "ไม่มีสิทธิ์เข้าถึงเอกสารลับ")
        if resp.status_code >= 400:
            detail = _safe_detail(resp)
            raise RAGWorkerError(f"RAG worker error ({resp.status_code}): {detail}")

        return resp.json()


def _safe_detail(resp: httpx.Response) -> str:
    try:
        payload = resp.json()
        return payload.get("detail") or payload.get("error") or str(payload)
    except ValueError:
        return resp.text


# Singleton instance — เก็บชื่อเดิมจาก stub เพื่อไม่ต้องแก้ import ที่อื่น
rag_pipeline = RAGPipeline()


# ── ต่อสาย Approve → Confidential RAG index (2026-08-07) ───────────────────────────────
# Timeout สั้นกว่า RAG_WORKER_TIMEOUT_SECONDS มาก (rebuild ดัชนีเอกสารลับไม่กี่ไฟล์ใช้เวลาไม่กี่
# วินาทีถึงไม่กี่นาที ต่างจาก query ที่รอ Gemini ตอบได้นานถึง 30 นาที) แยก env var ของตัวเองเผื่อ
# corpus โตขึ้นมากในอนาคตแล้วต้องปรับ
RAG_WORKER_REBUILD_TIMEOUT_SECONDS = float(
    os.environ.get("RAG_WORKER_REBUILD_TIMEOUT_SECONDS", "600")
)


def trigger_confidential_index_rebuild() -> dict:
    """เรียก worker `POST /admin/rebuild_confidential_index` — ใช้จาก
    `main.py::_archive_and_notify_background()` หลัง Checker approve เอกสารแล้ว **ไม่ raise
    exception เลยแม้แต่กรณีเดียว** (คืน dict {"success": False, "message": "..."} แทน) เพราะการ
    index เข้า RAG เป็น "nice to have" เหมือน archive.py (ดู docstring หัวไฟล์นั้น) — ต้องไม่ทำให้
    ทั้ง flow Approve (PDF สร้างสำเร็จ + อีเมลส่งสำเร็จแล้ว) ถูก mark ว่าล้มเหลวไปด้วยแค่เพราะ worker
    ปิดอยู่หรือ rebuild ล้มเหลว"""
    try:
        resp = httpx.post(
            f"{RAG_WORKER_BASE_URL}/admin/rebuild_confidential_index",
            timeout=RAG_WORKER_REBUILD_TIMEOUT_SECONDS,
        )
    except httpx.ConnectError as e:
        return {"success": False, "message": f"เชื่อมต่อ RAG worker ไม่ได้ที่ {RAG_WORKER_BASE_URL}: {e}"}
    except httpx.TimeoutException as e:
        return {"success": False, "message": f"RAG worker rebuild ตอบช้าเกิน {RAG_WORKER_REBUILD_TIMEOUT_SECONDS}s: {e}"}

    if resp.status_code >= 400:
        return {"success": False, "message": f"RAG worker rebuild error ({resp.status_code}): {_safe_detail(resp)}"}

    try:
        return resp.json()
    except ValueError:
        return {"success": False, "message": f"RAG worker rebuild ตอบไม่ใช่ JSON: {resp.text}"}
