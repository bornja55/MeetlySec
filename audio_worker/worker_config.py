"""
worker_config.py — config/env loading ของ Com Sec Audio Worker (Module 2: Diarization + ASR)

ตัดสินใจสถาปัตยกรรม (2026-08-02, ต่อจาก /debug-mantra session ที่วัด VRAM จริง): audio_worker
เป็น**โปรเซสแยกต่างหาก**จาก backend หลัก เหมือน `rag_worker/` — เหตุผลเดียวกันเป๊ะกับที่ RAG worker
ต้องแยก: rag_worker/main.py's docstring เตือนว่า Windows เกิด WINHTTP.dll access-violation crash
ถ้ารวม torch/faiss เข้าโปรเซสเดียวกับ web layer — audio_worker ใช้ torch (ผ่าน nemo-toolkit +
pyannote.audio + speechbrain) หนักไม่ต่างจาก rag_worker เลย จึงเสี่ยงบั๊กสายพันธุ์เดียวกัน แม้ว่า
task.md ฉบับเดิม (เขียนก่อนพบปัญหานี้) จะระบุว่าให้รันผ่าน "FastAPI Async Background Task" ในโปรเซส
เดียวกับ backend ก็ตาม — แก้ไขแผนเป็นแยกโปรเซสแล้ว (ผู้ใช้ยืนยันการตัดสินใจนี้)

หมายเหตุ VRAM (ดู task.md Module 0 สำหรับตัวเลขเต็ม): วัดจริงบนเครื่อง RTX 3050 Laptop (4096MiB)
ว่า RAG worker resident ใช้ 3060MiB, typhoon-asr peak 564MiB, diarization peak 242MiB — audio
worker นี้ **ไม่โหลดทั้งสองโมเดลพร้อมกัน** (ดู pipeline.py's GPU lock sequencing) จึงต้องการ VRAM
สูงสุดแค่ ~564MiB ในแต่ละช่วงเวลา พอดีกับ headroom ~1036MiB ที่เหลือ
"""
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)


def _load_dotenv(path: str) -> None:
    """โหลด KEY=VALUE จาก .env แบบง่ายๆ เหมือน rag_worker/worker_config.py ไม่ทับค่าที่ set
    ไว้แล้วใน environment จริง"""
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

# พอร์ตแยกจาก backend หลัก (8000) และ RAG worker (8766)
PORT = int(os.environ.get("AUDIO_WORKER_PORT", "8767"))

# ── Path ไปยังโมเดล/checkpoint — ชี้ไปที่ repo ที่โคลนไว้แล้วที่ project root โดยตรง ─────────
# (เหมือนแนวทาง rag_worker ที่ชี้ไป Local RAG โดยตรง ไม่ copy — override ผ่าน .env ได้ถ้าย้ายที่)
TYPHOON_ASR_MODEL_NAME = os.environ.get("TYPHOON_ASR_MODEL_NAME", "scb10x/typhoon-asr-realtime")

DIARIZATION_CHECKPOINT_DIR = os.environ.get(
    "DIARIZATION_CHECKPOINT_DIR",
    os.path.join(PROJECT_ROOT, "Diarization_ThaiSpeech_2022", "checkpoints"),
)

# ── งานประมวลผล — ไฟล์เสียงต้นฉบับที่ backend บันทึกไว้แล้วก่อนเรียก worker นี้ ──────────────
# ตั้งใจใช้ shared filesystem path (worker กับ backend รันบนเครื่องเดียวกัน) แทนการอัปโหลดไฟล์
# เสียง/วิดีโอซ้ำผ่าน HTTP body (ไฟล์ประชุมอาจยาวหลายชั่วโมง ส่งซ้ำสองรอบไม่คุ้ม) — backend ส่งแค่
# path มาที่นี่
UPLOAD_DIR = os.environ.get(
    "AUDIO_UPLOAD_DIR",
    os.path.join(PROJECT_ROOT, "backend", "uploads"),
)
PROCESSED_DIR = os.environ.get(
    "AUDIO_PROCESSED_DIR",
    os.path.join(BASE_DIR, "processed"),
)

# ── ASR per-segment (redesign 2026-08-02, ดู handoff.md 3.3) ─────────────────────────────
# เปลี่ยนจาก "ตัด ASR เป็นชิ้นละ 1 ชม." เป็น "ตัด ASR ใหม่ทีละ segment ของ diarization" (แม่นยำสุด
# เพราะ speaker segment ผูกกับข้อความตรงๆไม่ต้อง merge/align ทีหลัง แต่ transcribe เยอะครั้งขึ้นมาก
# — segment สั้นๆหลักวินาที) diarization ยังรันบนไฟล์เต็มความยาวเหมือนเดิมเสมอ (ห้ามตัดชิ้น กัน
# Speaker ID ไม่ตรงกันข้ามชิ้น) — ค่านี้ไม่ใช่ขนาด chunk คงที่แล้ว แต่เป็น**เพดาน**ความยาวต่อ segment
# ที่ยอมส่งเข้าโมเดลทีเดียว ถ้า diarization segment ไหนยาวเกิน (คนพูดยาวต่อเนื่องไม่มีใครขัด) จะถูก
# sub-split เพิ่มใน asr.py's transcribe_segments()
#
# ⚠️ ค่า default: 20s — cross-check กับ `typhoon-asr/examples/finetune.py` บรรทัด
# `asr_model.cfg.train_ds.max_duration = 20` (ของจริงในซอร์สที่โคลนมา, ตรวจแล้ว 2026-08-02) ไม่ใช่
# 30s ที่เคยเขียนไว้ในฉบับร่างของ handoff (อ้างอิงจากความจำ ไม่ได้ grep ซอร์สจริงตอนนั้น) — ยังไม่
# verify ว่าโมเดล "realtime" (`scb10x/typhoon-asr-realtime`) ทนอินพุตยาวกว่า train_ds.max_duration
# ได้แค่ไหนจริง (README ไม่มีข้อมูลเรื่องนี้) เพดานนี้จึงยังเป็นค่าอนุรักษ์นิยม ปรับได้ผ่าน env var
ASR_MAX_SEGMENT_SECONDS = int(os.environ.get("ASR_MAX_SEGMENT_SECONDS", "20"))

# segment สั้นกว่านี้ (วินาที) ข้ามไปเลย ไม่ส่งเข้าโมเดล — วัตถุประสงค์เดียวตอนนี้คือกันขอบเขต
# ทางเทคนิค (ffmpeg extract ไฟล์แทบว่าง/model เจอ input สั้นผิดปกติ) เท่านั้น **ไม่ใช่ตัวกรอง
# คุณภาพอีกต่อไป**
#
# ประวัติการปรับ (ดู handoff.md 3.4 สำหรับรายละเอียดเต็ม): เคยลองขยับ 0.1s → 0.5s เป็น
# duration-heuristic เพื่อกรอง segment ที่มักคืน text ว่างเปล่า — **live test พิสูจน์ว่าใช้ไม่ได้
# จริง**: segment 0.54s (ผ่านเกณฑ์) ยังว่างเปล่าอยู่ดี ขณะที่ segment 0.37s (ไม่ผ่านเกณฑ์) กลับมีคำ
# จริง ("วันนี้") — ความยาว segment ไม่ correlate กับคุณภาพผลลัพธ์แม่นยำพอจะใช้เป็นตัวกรอง — **เปลี่ยน
# วิธีแทน**: กรองจากผลจริงหลัง transcribe แล้ว (`asr.py`'s `transcribe_segments()` drop entry ที่
# text ว่างเปล่าหลังโมเดลตอบมา แม่นยำ 100% เพราะไม่ใช่การเดา) ค่านี้จึงกลับไปเป็นค่าอนุรักษ์นิยมเล็กๆ
# เหมือนเดิมพอ
ASR_MIN_SEGMENT_SECONDS = float(os.environ.get("ASR_MIN_SEGMENT_SECONDS", "0.1"))

# ── GPU lock / fallback ──────────────────────────────────────────────────────────────
# ห้ามมี diarization model กับ ASR model อยู่บน VRAM พร้อมกันเด็ดขาด (ตัดสินใจ Module 2 เดิม) —
# โหลด→รัน→ปล่อย ทีละตัวตามลำดับใน pipeline.py เท่านั้น ค่านี้คือ fallback ถ้า VRAM ไม่พอจริง
# (torch.cuda.OutOfMemoryError) ให้ตกไปใช้ CPU แทนแบบอัตโนมัติ
CPU_FALLBACK_ON_OOM = os.environ.get("CPU_FALLBACK_ON_OOM", "true").lower() != "false"

LOG_FILE = os.path.join(BASE_DIR, "audio_worker.log")
