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
RAG_WORKER_TIMEOUT_SECONDS = float(os.environ.get("RAG_WORKER_TIMEOUT_SECONDS", "60"))


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
    ) -> dict:
        """เรียก worker `/query` (search_scope="general") หรือ `/query_confidential`
        (search_scope="confidential") คืน dict {"response", "sources", "tokens", ...} ตรงจาก
        worker — raise RAGWorkerError ถ้า worker ไม่ตอบ/ตอบ error (เช่น 503 = ยังโหลดโมเดลไม่เสร็จ,
        403 = role ไม่มีสิทธิ์)

        session key ที่ worker ใช้คือ user_id ที่ส่งมานี้ตรงๆ (ไม่ใช่ browser-tab session_id แบบ
        Local RAG เดิม — ตัดสินใจจาก handoff.md ข้อ 3.0.2 "เปลี่ยน session model... เป็นผูกกับ
        authenticated user_id จริง")"""
        if not user_id:
            raise RAGWorkerError("ไม่พบ user_id — ต้อง authenticate ก่อนเรียก RAG query")

        if search_scope == "confidential":
            path = "/query_confidential"
            body = {"user_id": user_id, "role": role or "", "prompt": user_query}
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
