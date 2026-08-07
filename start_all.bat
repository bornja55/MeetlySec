@echo off
title Com Sec - Start All
cd /d "D:\Com Sec"

echo Opening RAG Worker, Audio Worker, and Backend in separate windows...
echo (Workers take ~1-2 minutes to load models. Wait for "ready" before testing.)
echo.

start "Com Sec - RAG Worker" "D:\Com Sec\rag_worker\start_worker.bat"
timeout /t 3 /nobreak >nul
start "Com Sec - Audio Worker" "D:\Com Sec\audio_worker\start_worker.bat"
timeout /t 3 /nobreak >nul
start "Com Sec - Backend" "D:\Com Sec\backend\start_backend.bat"

echo All three windows opened (RAG Worker + Audio Worker + Backend). You can close this window now.
pause
