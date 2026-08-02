"""
diarization.py — โหลด+รัน Diarization_ThaiSpeech_2022 (fine-tuned pyannote segmentation model)

⚠️ **หมายเหตุสำคัญ (2026-08-02)**: hyperparameter ของ `SpeakerDiarization.instantiate()` ด้านล่าง
เป็น**ค่ากลางๆที่ยังไม่ผ่านการ tune** — ตอนวัด VRAM จริง (`diagnose_vram_module2.py`) พบว่า
hyperparameter ที่ tune ไว้เดิมใน `Evaluate_Diarization.ipynb` (ปี 2022, DER ~3.9% ตามที่ README
ของ repo อ้างถึง) ผูกกับ `pyannote.audio` **2.x** API/อัลกอริทึมคนละเวอร์ชันกับที่ติดตั้งจริงตอนนี้
(3.3.2) เอามาใช้ตรงๆไม่ได้ (schema ของ `instantiate()` เปลี่ยนทั้งหมด — ดู comment ในโค้ดด้านล่าง)
**ก่อนใช้งานจริงกับข้อมูลประชุมจริง ต้อง tune hyperparameter ใหม่** (`pipeline.parameters
(instantiated=False)` + optimize ด้วย `pyannote.pipeline`/Optuna เทียบกับ ground truth เหมือนที่
repo ต้นฉบับเคยทำ) ไม่งั้นความแม่นยำ diarization ไม่มีอะไรการันตี — ตอนนี้แค่ทำให้ pipeline รันได้
จริงโดยไม่ error เท่านั้น
"""
import os

import torch
from worker_config import DIARIZATION_CHECKPOINT_DIR


def _find_checkpoint() -> str:
    if not os.path.isdir(DIARIZATION_CHECKPOINT_DIR):
        raise FileNotFoundError(f"ไม่พบโฟลเดอร์ checkpoint: {DIARIZATION_CHECKPOINT_DIR}")
    ckpts = [f for f in os.listdir(DIARIZATION_CHECKPOINT_DIR) if f.endswith(".ckpt")]
    if not ckpts:
        raise FileNotFoundError(f"ไม่พบไฟล์ .ckpt ใน {DIARIZATION_CHECKPOINT_DIR}")
    return os.path.join(DIARIZATION_CHECKPOINT_DIR, ckpts[0])


def load_pipeline(device: str):
    """โหลด fine-tuned segmentation model + ประกอบเป็น SpeakerDiarization pipeline บน device
    ที่ระบุ (เรียกครั้งเดียวต่อ 1 งาน แล้ว release ด้วย unload_pipeline() ก่อนโหลด ASR ต่อ — ห้าม
    มี diarization+ASR ค้างบน VRAM พร้อมกัน ดู pipeline.py)"""
    from pyannote.audio import Model
    from pyannote.audio.pipelines import SpeakerDiarization

    ckpt_path = _find_checkpoint()

    # หมายเหตุ (พบจาก /debug-mantra ตอนวัด VRAM): โค้ดต้นฉบับปี 2022 เรียก
    # `pretrained_instance.load_from_checkpoint(...)` เป็น instance method ได้ — pytorch-lightning
    # 2.x บังคับให้เป็น classmethod เท่านั้นแล้ว ต้องเรียกผ่าน class type
    pretrained = Model.from_pretrained("pyannote/segmentation")
    finetuned = type(pretrained).load_from_checkpoint(ckpt_path, map_location=device)

    pipeline = SpeakerDiarization(
        segmentation=finetuned,
        embedding="speechbrain/spkrec-ecapa-voxceleb",
    )
    # ค่ากลางๆ ยังไม่ tune — ดู warning ที่หัวไฟล์
    pipeline.instantiate({
        "segmentation": {"threshold": 0.5, "min_duration_off": 0.0},
        "clustering": {"threshold": 0.7, "method": "average", "min_cluster_size": 1},
    })
    pipeline.to(torch.device(device))
    return pipeline


def run_diarization(pipeline, wav_path: str) -> list[dict]:
    """รัน diarization บนไฟล์เต็มความยาว (ห้ามตัดชิ้นก่อน — กัน Speaker ID ไม่ตรงกันข้ามชิ้น
    ตามการตัดสินใจ Module 2) คืน list ของ {start, end, speaker} เรียงตามเวลา"""
    annotation = pipeline(wav_path)
    segments = []
    for segment, _track, speaker in annotation.itertracks(yield_label=True):
        segments.append({
            "start": segment.start,
            "end": segment.end,
            "speaker": speaker,  # เช่น "SPEAKER_00" — ยังไม่ผูกกับชื่อจริง รอหน้าจอ Speaker Mapping
        })
    return segments


# หมายเหตุ: เคยมี unload_pipeline(pipeline) ที่ทำ `del pipeline` ในนี้ — ลบไปแล้ว (แก้บั๊ก
# CRITICAL จาก /scrutinize: `del` พารามิเตอร์ในฟังก์ชันนี้ไม่ช่วยอะไร เพราะฝั่งเรียกยังถือ
# reference ของตัวเองอยู่ต่อไป VRAM ไม่ถูกปล่อยจริง) — ฝั่งเรียกต้อง `del` ตัวแปรของตัวเองในสโคป
# ตัวเอง แล้วเรียก gpu_utils.release_gpu_memory() แทน ดู pipeline.py
