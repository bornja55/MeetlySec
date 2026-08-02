@echo off
title Com Sec - Backend API (port 8000)
cd /d "D:\Com Sec\backend"

if not exist ".env" (
    echo [WARNING] .env not found in D:\Com Sec\backend
    echo Copy .env.example to .env before running.
    pause
    exit /b 1
)

echo Starting Backend API (Com Sec) on port 8000...
echo Using global python (all packages already installed there).
echo NOTE: Start the RAG Worker (port 8766) first, or /api/rag/query will error.
echo.

python main.py

echo.
echo Backend stopped.
pause
