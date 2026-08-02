@echo off
title Com Sec - RAG Worker (port 8766)
cd /d "D:\Com Sec\rag_worker"

if not exist ".env" (
    echo [WARNING] .env not found in D:\Com Sec\rag_worker
    echo Copy .env.example to .env and set GOOGLE_API_KEY before running.
    pause
    exit /b 1
)

echo Starting RAG Worker (Com Sec) on port 8766...
echo Loading models (BGE-M3 + reranker + FAISS index) takes about 1-2 minutes.
echo Wait for the "ready" status in the log below before testing.
echo.

python -m uvicorn main:app --host 127.0.0.1 --port 8766

echo.
echo Worker stopped.
pause
