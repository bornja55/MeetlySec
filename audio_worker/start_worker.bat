@echo off
title Com Sec - Audio Worker (port 8767)
cd /d "D:\Com Sec\audio_worker"

echo Starting Audio Worker (Com Sec) on port 8767...
echo Requires: ffmpeg in PATH, CUDA-build torch installed, and one-time
echo   "huggingface-cli login" done already (pyannote/segmentation is gated).
echo See .env.example if this is the first run.
echo.

python -m uvicorn main:app --host 127.0.0.1 --port 8767

echo.
echo Worker stopped.
pause
