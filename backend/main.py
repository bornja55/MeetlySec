from auth import require_role, verify_azure_ad_token
from fastapi import Depends, FastAPI, HTTPException
from rag import RAGWorkerError, rag_pipeline

app = FastAPI(
    title="Company Secretary AI System - API",
    description="Backend for the Com Sec Meeting & RAG Assistant",
    version="1.0.0"
)


@app.get("/")
def read_root():
    return {"message": "Welcome to Com Sec AI Backend API"}


# Module 1: Local-RAG Endpoints — rag_pipeline เป็น HTTP client ไปหา RAG worker โปรเซสแยก
# (D:\Com Sec\rag_worker\main.py, ดู backend/rag.py) ไม่ใช่ stub คืนค่า hardcoded อีกต่อไป
# (แก้จาก /scrutinize 2026-08-01 — ดู handoff.md ข้อ 3.0)
@app.post("/api/rag/query")
def query_policy(query: str, user: dict = Depends(verify_azure_ad_token)):
    try:
        result = rag_pipeline.query(
            query, user_id=user["user_id"], search_scope="general",
        )
    except RAGWorkerError as e:
        raise HTTPException(status_code=503, detail=str(e))
    return {"query": query, "user": user, **result}


@app.post("/api/rag/query_confidential")
def query_confidential(
    query: str,
    user: dict = Depends(require_role(["Com_Sec_Maker", "Com_Sec_Checker", "Board_Member"])),
):
    # Only Com Sec team, Board Member, and Global Admin can access this — เช็คซ้ำอีกชั้นที่ worker
    # เอง (defense in depth ดู rag_worker/main.py's /query_confidential)
    try:
        result = rag_pipeline.query(
            query, user_id=user["user_id"], search_scope="confidential", role=user["role"],
        )
    except RAGWorkerError as e:
        raise HTTPException(status_code=503, detail=str(e))
    return {"query": query, "user": user, **result}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
