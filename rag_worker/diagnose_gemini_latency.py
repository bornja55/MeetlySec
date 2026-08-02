"""
diagnose_gemini_latency.py — เรียก Gemini API ตรงๆ ผ่าน google-genai SDK เปล่าๆ (ไม่ผ่าน
llama_index/worker/retry logic เลย) วัดเวลาที่ใช้จริงต่อ 1 คำขอ เพื่อแยกว่าความช้า ~1000s ที่เจอ
มาจาก (ก) ตัว Gemini API/SDK เอง หรือ (ข) โค้ดฝั่งเราที่ห่อไว้อีกที (retry loop, llama_index wrapper)

รัน (คนละ terminal จาก worker/backend ที่กำลังรันอยู่ก็ได้ ไม่ชนกัน):
    cd "D:\\Com Sec\\rag_worker"
    python diagnose_gemini_latency.py
"""
import os
import time

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def _load_dotenv(path: str) -> None:
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())


_load_dotenv(os.path.join(BASE_DIR, ".env"))

api_key = os.environ.get("GOOGLE_API_KEY")
if not api_key:
    print("[ERROR] ไม่พบ GOOGLE_API_KEY ใน .env — ตรวจสอบก่อนรัน")
    raise SystemExit(1)

model = os.environ.get("GEMINI_MODEL_CHAT", "gemini-3.1-flash-lite")
prompt = "ตอบสั้นๆ คำเดียวพอ: 1+1 เท่ากับเท่าไร"

print(f"[INFO] จะเรียกโมเดล: {model}")
print(f"[INFO] prompt: {prompt!r}")
print("[INFO] เริ่มจับเวลา...")

from google import genai  # noqa: E402

client = genai.Client(api_key=api_key)

t0 = time.time()
try:
    response = client.models.generate_content(model=model, contents=prompt)
    elapsed = time.time() - t0
    print(f"\n[สำเร็จ] ใช้เวลา {elapsed:.2f}s")
    print(f"[คำตอบ] {response.text!r}")
except Exception as e:
    elapsed = time.time() - t0
    print(f"\n[ERROR หลังผ่านไป {elapsed:.2f}s] {type(e).__name__}: {e}")
