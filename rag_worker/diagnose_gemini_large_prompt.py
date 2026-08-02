"""
diagnose_gemini_large_prompt.py — เหมือน diagnose_gemini_latency.py แต่ยิง prompt ขนาดใหญ่
ใกล้เคียงของจริง (context ~8000-10000 token + ขอคำตอบยาว) ยังคงเป็น raw API ตรงๆ ผ่าน
google-genai SDK เปล่า ไม่ผ่าน llama_index/chat_engine/retrieval/reranker เลย

เป้าหมาย: แยกว่าความช้า ~700-1000s มาจาก "ขนาด payload ใหญ่" (context เข้า + คำตอบยาวออก)
ล้วนๆ หรือมาจากสิ่งที่ chat_engine/condense_plus_context ทำเพิ่ม (เช่น 2 LLM call ต่อเทิร์น)

รัน:
    cd "D:\\Com Sec\\rag_worker"
    python diagnose_gemini_large_prompt.py
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

# จำลอง context ขนาดใกล้เคียงของจริง: reranker top_n=20 x chunk_size~400 token ≈ 8000 token
# ใช้ข้อความ filler ภาษาไทยซ้ำๆ (ไม่ใช่เนื้อหาจริง แค่ทดสอบขนาด payload ไม่ใช่เนื้อหา)
_filler_chunk = (
    "ระเบียบข้อบังคับเกี่ยวกับการทำงานฉบับนี้กำหนดหลักเกณฑ์และเงื่อนไขต่างๆ ที่เกี่ยวข้องกับการจ้างงาน "
    "สวัสดิการ วันหยุด วันลา และแนวปฏิบัติของพนักงานทุกระดับภายในองค์กร โดยมีวัตถุประสงค์เพื่อสร้าง "
    "ความเข้าใจที่ตรงกันระหว่างนายจ้างและลูกจ้าง ลดข้อขัดแย้งที่อาจเกิดขึ้นจากการตีความกฎระเบียบที่ "
    "แตกต่างกัน และเพื่อให้การบริหารทรัพยากรบุคคลเป็นไปอย่างมีประสิทธิภาพและเป็นธรรมต่อทุกฝ่าย ทั้งนี้ "
    "พนักงานทุกคนมีหน้าที่ต้องศึกษาและปฏิบัติตามระเบียบนี้อย่างเคร่งครัด "
)
context_text = "\n\n".join(f"[เอกสาร {i}]\n{_filler_chunk}" for i in range(20))  # ~20 chunks

sys_prompt = (
    "คุณเป็นผู้ช่วยตอบคำถามนโยบายบริษัท ใช้ข้อมูลจาก context ด้านล่างนี้ตอบคำถามอย่างละเอียด "
    "แยกเป็นหัวข้อย่อยชัดเจน อ้างอิงเอกสารที่เกี่ยวข้องด้วย\n\n--- Context ---\n" + context_text
)
user_msg = "นโยบายการลาพักร้อนคืออะไร กรุณาอธิบายละเอียดพร้อมยกตัวอย่างประกอบ"
full_prompt = sys_prompt + "\n\n" + user_msg

approx_tokens = len(full_prompt) // 4
print(f"[INFO] จะเรียกโมเดล: {model}")
print(f"[INFO] ขนาด prompt: {len(full_prompt)} ตัวอักษร (~{approx_tokens} token โดยประมาณ)")
print("[INFO] เริ่มจับเวลา...")

from google import genai  # noqa: E402

client = genai.Client(api_key=api_key)

t0 = time.time()
try:
    response = client.models.generate_content(model=model, contents=full_prompt)
    elapsed = time.time() - t0
    print(f"\n[สำเร็จ] ใช้เวลา {elapsed:.2f}s")
    print(f"[ความยาวคำตอบ] {len(response.text)} ตัวอักษร")
    print(f"[คำตอบ (200 ตัวอักษรแรก)] {response.text[:200]!r}")
except Exception as e:
    elapsed = time.time() - t0
    print(f"\n[ERROR หลังผ่านไป {elapsed:.2f}s] {type(e).__name__}: {e}")
