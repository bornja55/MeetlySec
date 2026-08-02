"""
diagnose_reranker_via_localrag_venv.py — ทดสอบ rerank เดียวกันเป๊ะ (60 คู่, reranker ตัวเดียวกัน)
แต่รันผ่าน **Local RAG's venv python โดยตรง** (ไม่ใช่ global python ที่ Com Sec ใช้อยู่) —
ตอบคำถามตรงๆ ว่า venv ที่ Local RAG ใช้จริง (torch 2.5.1+cu121) รันแล้วเสถียร/เร็วจริงหรือไม่
หรือจะเจอความไม่นิ่งแบบเดียวกับที่เจอใน global env

ไม่ import worker_config (กันปัญหา path เวลารันข้าม environment) — ชี้ path ตรงๆ แทน เพราะ
โมเดล/index เป็นของที่ใช้ร่วมกันระหว่าง Local RAG กับ Com Sec อยู่แล้ว

รัน (ต้องใช้ python ของ Local RAG's venv ตรงๆ ไม่ใช่ global):
    cd "D:\\Com Sec\\rag_worker"
    "D:\\Review Policy\\Local  RAG\\venv\\Scripts\\python.exe" diagnose_reranker_via_localrag_venv.py

แนะนำให้รัน 2-3 รอบติดกัน (เรียกสคริปต์ใหม่ทุกครั้ง ไม่ใช่รันซ้ำใน process เดียว) เพื่อดูว่าเวลา
นิ่งจริงไหม หรือแกว่งแบบที่เจอใน global env ก่อนหน้านี้
"""
import sys
import time

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

RERANKER_PATH = r"D:\Review Policy\Local  RAG\models\bge-reranker-v2-m3"

import torch  # noqa: E402
from sentence_transformers import CrossEncoder  # noqa: E402

print("=" * 60)
print(f"[ENV] python executable: {sys.executable}")
print(f"[ENV] torch version: {torch.__version__}")
print(f"[ENV] torch.cuda.is_available(): {torch.cuda.is_available()}")
print("=" * 60)

_filler = (
    "ระเบียบข้อบังคับเกี่ยวกับการทำงานฉบับนี้กำหนดหลักเกณฑ์และเงื่อนไขต่างๆ ที่เกี่ยวข้องกับการจ้างงาน "
    "สวัสดิการ วันหยุด วันลา และแนวปฏิบัติของพนักงานทุกระดับภายในองค์กร โดยมีวัตถุประสงค์เพื่อสร้าง "
    "ความเข้าใจที่ตรงกันระหว่างนายจ้างและลูกจ้าง ลดข้อขัดแย้งที่อาจเกิดขึ้นจากการตีความกฎระเบียบที่ "
    "แตกต่างกัน และเพื่อให้การบริหารทรัพยากรบุคคลเป็นไปอย่างมีประสิทธิภาพและเป็นธรรมต่อทุกฝ่าย "
)
query = "นโยบายการลาพักร้อนคืออะไร"
pairs = [[query, f"[เอกสาร {i}] {_filler}"] for i in range(60)]

print("[TEST] torch_dtype=torch.float16, device=cpu (ค่าเดียวกับที่ต้นฉบับ Local RAG ใช้จริง)")
t0 = time.time()
model = CrossEncoder(
    RERANKER_PATH, device="cpu",
    model_kwargs={"torch_dtype": torch.float16, "use_safetensors": True},
)
print(f"  โหลดโมเดล: {time.time() - t0:.2f}s")

t0 = time.time()
model.predict([["warmup", "test"]])
print(f"  warmup (1 คู่): {time.time() - t0:.2f}s")

t0 = time.time()
scores = model.predict(pairs)
elapsed = time.time() - t0
print(f"  >>> rerank 60 คู่: {elapsed:.2f}s <<<")
print("=" * 60)
print("รันสคริปต์นี้ซ้ำอีก 2-3 รอบ (เรียกใหม่ทุกครั้ง) แล้วเทียบตัวเลข — ถ้านิ่ง (ใกล้เคียงกันทุกรอบ)")
print("แปลว่า Local RAG's venv เสถียรจริง ถ้าแกว่งเหมือนกัน แปลว่าปัญหาไม่ได้ขึ้นกับ environment เลย")
