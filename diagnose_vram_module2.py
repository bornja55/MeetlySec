"""
diagnose_vram_module2.py — วัด VRAM จริงของ typhoon-asr และ Diarization_ThaiSpeech_2022 บนเครื่อง
Windows จริง (ต้องรันบนเครื่องที่มี GPU เท่านั้น — sandbox ของ AI ไม่มี GPU วัดให้ไม่ได้)

เหตุผล: handoff.md ข้อ 4 "[Immediate]" ต้องออกแบบ GPU Lock ให้ครอบคลุม RAG worker (ใช้ VRAM ค้างอยู่
แล้ว ~2-3GB โดยประมาณ ยังไม่วัดจริง) + Module 2 (Diarization+ASR) บนเครื่อง 4GB — ก่อนออกแบบ lock
policy (RAG worker resident vs. เข้าคิว unload) ต้องมีตัวเลขจริงก่อนตาม /debug-mantra มะตรา 1
(Reproduce First — ห้ามเดา ต้องวัดจริง)

วิธีใช้ (ทำตามลำดับ):
1. เช็ค VRAM ที่ RAG worker ใช้อยู่ตอนนี้ก่อน (worker ต้องรันอยู่แล้ว, ยิง query ทดสอบ 1 ครั้งให้ warm
   up โมเดลเสร็จก่อน) เปิด terminal อีกอันแล้วรัน:
       nvidia-smi
   จด "Memory-Usage" ของ process python ที่เป็น rag_worker ไว้ (คอลัมน์ MiB) — นี่คือ baseline

2. ติดตั้ง dependency ที่ยังไม่มี (เท่าที่ต้องใช้เฉพาะสคริปต์นี้):
       pip install -r typhoon-asr/requirements.txt
       pip install pyannote.audio speechbrain

3. รันสคริปต์นี้ (จาก D:\\Com Sec):
       python diagnose_vram_module2.py

   สคริปต์จะโหลด/รัน/ปล่อย VRAM ทีละตัว (ไม่พร้อมกัน) แล้ว print peak VRAM (MiB) ของแต่ละตัว
   ให้เทียบกับ baseline ของ RAG worker จากข้อ 1 เอง (สคริปต์นี้ตั้งใจไม่แตะ RAG worker process)

4. ส่งผล print กลับมาให้ AI ออกแบบ GPU Lock policy ต่อ (resident vs. unload-on-idle) ด้วยตัวเลขจริง
   แทนการประมาณ
"""
import gc
import os
import time

os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
os.environ.setdefault("TQDM_DISABLE", "1")

import torch  # noqa: E402


def _reset_and_measure(label: str, fn):
    """รันฟังก์ชันที่โหลด+inference 1 ตัว วัด peak VRAM เดี่ยวๆ แล้วปล่อยคืนก่อนตัวถัดไป"""
    if not torch.cuda.is_available():
        print(f"[{label}] ไม่พบ GPU (torch.cuda.is_available() == False) — ข้าม")
        return None

    torch.cuda.empty_cache()
    torch.cuda.reset_peak_memory_stats()
    print(f"\n=== {label}: เริ่มโหลด+รัน ===")
    t0 = time.time()
    try:
        fn()
    except Exception as e:  # noqa: BLE001 — สคริปต์วัดค่า ไม่ใช่ production code ต้องไม่ล้มทั้งกระบวนการ
        print(f"[{label}] ล้มเหลว: {type(e).__name__}: {e}")
        return None
    elapsed = time.time() - t0
    peak_mb = torch.cuda.max_memory_allocated() / (1024 * 1024)
    reserved_mb = torch.cuda.max_memory_reserved() / (1024 * 1024)
    print(f"[{label}] เสร็จใน {elapsed:.1f}s — peak allocated={peak_mb:.0f}MiB, "
          f"peak reserved(รวม CUDA overhead)={reserved_mb:.0f}MiB")

    gc.collect()
    torch.cuda.empty_cache()
    return peak_mb, reserved_mb


def measure_typhoon_asr():
    import nemo.collections.asr as nemo_asr

    sample = os.path.join("typhoon-asr", "examples", "cv_test.wav")
    model = nemo_asr.models.ASRModel.from_pretrained(model_name="scb10x/typhoon-asr-realtime")
    model = model.to("cuda")
    model.eval()
    with torch.no_grad():
        _ = model.transcribe([sample])
    del model


def measure_diarization():
    from pyannote.audio import Model
    from pyannote.audio.pipelines import SpeakerDiarization

    ckpt_dir = os.path.join("Diarization_ThaiSpeech_2022", "checkpoints")
    ckpts = [f for f in os.listdir(ckpt_dir) if f.endswith(".ckpt")]
    if not ckpts:
        raise FileNotFoundError(f"ไม่พบไฟล์ .ckpt ใน {ckpt_dir}")
    ckpt_path = os.path.join(ckpt_dir, ckpts[0])

    # หมายเหตุ (2026-08-02, พบจาก /debug-mantra ตอนวัด VRAM จริง): โค้ดต้นฉบับใน
    # Evaluate_Diarization.ipynb (pytorch-lightning ~1.5.x, ปี 2022) เรียก
    # `pretrained_instance.load_from_checkpoint(...)` เป็น instance method ได้ — pytorch-lightning
    # 2.x (ที่ pip ติดตั้งมาให้ตอนนี้) เปลี่ยนให้เป็น classmethod ล้วนๆ ต้องเรียกผ่าน class type
    # เท่านั้น ไม่ใช่ instance เดิม (ล้ม deepcopy(pretrained) ไปเลย ไม่จำเป็นแล้ว)
    pretrained = Model.from_pretrained("pyannote/segmentation")
    finetuned = type(pretrained).load_from_checkpoint(
        ckpt_path,
        map_location="cuda" if torch.cuda.is_available() else "cpu",
    )

    # หมายเหตุ 2: hyperparameter dict เดิมจาก notebook ("segmentation_onset"/"clustering.
    # single_cluster_detection"/... ) เป็น API ของ pyannote.audio **2.x** — เช็คซอร์สของ
    # pyannote.audio==3.3.2 ที่ติดตั้งจริงแล้ว (pip download --no-deps มาอ่าน เพราะ sandbox
    # ของ AI ไม่มี GPU รันไม่ได้แต่อ่านซอร์สได้) พบว่า SpeakerDiarization รุ่น 3.x เปลี่ยน schema
    # ทั้งหมด: `instantiate()` ต้องการ {"segmentation": {"threshold", "min_duration_off"},
    # "clustering": {"threshold", "method", "min_cluster_size"}} แทน — ค่าด้านล่างเป็นค่ากลางๆ
    # ที่ใช้ได้กับทุกโมเดล (ไม่ใช่ค่าที่ผ่านการ tune จริงแบบใน notebook เดิม เพราะ tune ไว้กับ
    # pipeline คนละเวอร์ชัน/อัลกอริทึมกันโดยสิ้นเชิง เอามาใช้ตรงๆไม่ได้) **จุดประสงค์สคริปต์นี้คือ
    # วัด VRAM เท่านั้น ไม่ได้วัดความถูกต้องของ diarization** — ถ้าจะใช้งานจริงใน Module 2 ต้อง
    # ทำ hyperparameter search ใหม่ (`pipeline.parameters(instantiated=False)` + Optuna เหมือนที่
    # โปรเจกต์ต้นฉบับทำไว้ตอน tune ครั้งแรก)
    pipeline = SpeakerDiarization(
        segmentation=finetuned,
        embedding="speechbrain/spkrec-ecapa-voxceleb",
    )
    pipeline.instantiate({
        "segmentation": {"threshold": 0.5, "min_duration_off": 0.0},
        "clustering": {"threshold": 0.7, "method": "average", "min_cluster_size": 1},
    })
    pipeline.to(torch.device("cuda"))

    # ใช้ไฟล์ตัวอย่างสั้นสุดที่มีอยู่แล้วใน repo (Parliament_1m ~1 นาที)
    sample_dir = os.path.join("Diarization_ThaiSpeech_2022", "tests", "Parliament_1m")
    wavs = [f for f in os.listdir(sample_dir) if f.endswith(".wav")]
    if not wavs:
        raise FileNotFoundError(f"ไม่พบไฟล์ .wav ใน {sample_dir}")
    sample = os.path.join(sample_dir, wavs[0])

    _ = pipeline(sample)
    del pipeline


if __name__ == "__main__":
    print("torch:", torch.__version__, "| cuda available:", torch.cuda.is_available())
    if torch.cuda.is_available():
        print("GPU:", torch.cuda.get_device_name(0))
        total_mb = torch.cuda.get_device_properties(0).total_memory / (1024 * 1024)
        print(f"VRAM รวมของการ์ด: {total_mb:.0f}MiB")

    results = {}
    results["typhoon-asr"] = _reset_and_measure("typhoon-asr", measure_typhoon_asr)
    results["diarization"] = _reset_and_measure("Diarization_ThaiSpeech_2022", measure_diarization)

    print("\n=== สรุป (peak allocated MiB) ===")
    for label, r in results.items():
        print(f"{label}: {r[0]:.0f}MiB" if r else f"{label}: วัดไม่ได้")
    print("\nหมายเหตุ: ตัวเลขนี้คือแต่ละโมเดล*เดี่ยวๆ* (ไม่พร้อมกัน) — บวกกับ VRAM ของ RAG worker ที่จด")
    print("ไว้จาก nvidia-smi ในข้อ 1 เพื่อดูว่ารวมกันเกิน VRAM การ์ด (ข้อ \"VRAM รวมของการ์ด\" ด้านบน)")
    print("หรือไม่ ถ้าเกิน = ต้องมี GPU Lock policy ที่ยอมให้บางตัว unload ก่อน")
