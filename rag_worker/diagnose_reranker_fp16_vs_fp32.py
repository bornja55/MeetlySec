"""
diagnose_reranker_fp16_vs_fp32.py — โหลด BGE-reranker-v2-m3 3 รอบ (fp16 vs fp32 vs fp64) แล้ว
rerank 60 คู่เดียวกันทุกรอบ เทียบเวลาตรงๆ — ยืนยัน/ล้มสมมติฐานว่า torch_dtype=float16 บน CPU คือ
ตัวการที่ทำให้ rerank ใช้เวลา 859s (จาก diagnose_pipeline_stages.py) พร้อมเช็คว่า fp64 (double
precision) เข้ากับ CPU ดีกว่า/เร็วกว่าจริงไหม (ทฤษฎี: ไม่น่าเร็วกว่า fp32 — fp64 กินพื้นที่ 2 เท่า
และ SIMD instruction ประมวลผลได้น้อยกว่าต่อรอบ แต่วัดจริงชัวร์กว่าเดา)

รัน:
    cd "D:\\Com Sec\\rag_worker"
    python diagnose_reranker_fp16_vs_fp32.py
"""
import sys
import time

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import faiss  # noqa: E402,F401
import torch  # noqa: E402
import worker_config as config  # noqa: E402
from sentence_transformers import CrossEncoder  # noqa: E402

# จำลอง 60 คู่ query-document ใกล้เคียงของจริง (ความยาวประมาณ chunk_size=400 token/ชิ้น)
_filler = (
    "ระเบียบข้อบังคับเกี่ยวกับการทำงานฉบับนี้กำหนดหลักเกณฑ์และเงื่อนไขต่างๆ ที่เกี่ยวข้องกับการจ้างงาน "
    "สวัสดิการ วันหยุด วันลา และแนวปฏิบัติของพนักงานทุกระดับภายในองค์กร โดยมีวัตถุประสงค์เพื่อสร้าง "
    "ความเข้าใจที่ตรงกันระหว่างนายจ้างและลูกจ้าง ลดข้อขัดแย้งที่อาจเกิดขึ้นจากการตีความกฎระเบียบที่ "
    "แตกต่างกัน และเพื่อให้การบริหารทรัพยากรบุคคลเป็นไปอย่างมีประสิทธิภาพและเป็นธรรมต่อทุกฝ่าย "
)
query = "นโยบายการลาพักร้อนคืออะไร"
pairs = [[query, f"[เอกสาร {i}] {_filler}"] for i in range(60)]

# ── เช็ค torch version/CUDA ก่อนทดสอบเสมอ — ครั้งก่อน fp16 บน CPU ใช้ 553s, รอบนี้ 0.39s
# ต่างกันขนาดนี้ระหว่าง 2 รันไม่ใช่เรื่องบังเอิญ ต้องดูว่า torch เวอร์ชัน/build เปลี่ยนไปหรือยัง
# (ดู task.md 2026-08-02: Local RAG's venv ใช้ 2.5.1+cu121 "ไม่เคยช้า" ส่วน global เดิมใช้ 2.13.0)
print("=" * 60)
print(f"[ENV] torch version: {torch.__version__}")
print(f"[ENV] torch.cuda.is_available(): {torch.cuda.is_available()}")
if torch.cuda.is_available():
    print(f"[ENV] GPU: {torch.cuda.get_device_name(0)}")
print("=" * 60)


def run_test(label: str, torch_dtype, device: str = "cpu") -> float:
    print("=" * 60)
    print(f"[TEST] {label} (device={device})")
    kwargs = {"use_safetensors": True}
    if torch_dtype is not None:
        kwargs["torch_dtype"] = torch_dtype

    t0 = time.time()
    model = CrossEncoder(config.RERANKER_PATH, device=device, model_kwargs=kwargs)
    print(f"  โหลดโมเดล: {time.time() - t0:.2f}s")

    t0 = time.time()
    model.predict([["warmup", "test"]])
    print(f"  warmup (1 คู่): {time.time() - t0:.2f}s")

    t0 = time.time()
    model.predict(pairs)  # ผลลัพธ์ไม่ได้ใช้ต่อ — สคริปต์นี้วัดแค่เวลา ไม่ได้เช็คความถูกต้องของ score
    elapsed = time.time() - t0
    print(f"  >>> rerank 60 คู่: {elapsed:.2f}s <<<")
    del model
    if device == "cuda":
        torch.cuda.empty_cache()
    return elapsed


results = {}
results["CPU fp16"] = run_test("torch_dtype=torch.float16", torch.float16, "cpu")
results["CPU fp32"] = run_test("torch_dtype=ไม่ระบุ (default fp32)", None, "cpu")
results["CPU fp64"] = run_test("torch_dtype=torch.float64 (double precision)", torch.float64, "cpu")

if torch.cuda.is_available():
    results["GPU fp32"] = run_test("torch_dtype=ไม่ระบุ (default fp32)", None, "cuda")
    results["GPU fp16"] = run_test("torch_dtype=torch.float16", torch.float16, "cuda")
else:
    print("=" * 60)
    print("[ข้าม GPU test] torch.cuda.is_available() == False — ไม่มี GPU ให้ทดสอบตอนนี้")

print("=" * 60)
print("สรุปทั้งหมด:")
for label, t in results.items():
    print(f"  {label}: {t:.2f}s")
fastest_label = min(results, key=results.get)
print(f">>> เร็วที่สุด: {fastest_label} ({results[fastest_label]:.2f}s) <<<")
