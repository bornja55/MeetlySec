# 🏛️ Com Sec AI System (ระบบผู้ช่วย AI งานเลขานุการบริษัท)

![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-backend-009688?style=for-the-badge&logo=fastapi&logoColor=white)
![SQLite](https://img.shields.io/badge/SQLite-SQLAlchemy-003B57?style=for-the-badge&logo=sqlite&logoColor=white)
![Status](https://img.shields.io/badge/Status-MVP%20กำลังพัฒนา-yellow?style=for-the-badge)
![License](https://img.shields.io/badge/License-Private%20%2F%20Internal-lightgrey?style=for-the-badge)

ระบบผู้ช่วยอัตโนมัติสำหรับทีมเลขานุการบริษัท (Company Secretary) ที่เดิมต้องทำงานทุกขั้นตอนด้วยมือ — อัดเสียงประชุม ถอดเทปเอง แยกว่าใครพูดตรงไหนเอง ร่างรายงานการประชุมเอง ค้นนโยบายบริษัทเอง แล้ววนขออนุมัติผ่านอีเมล ระบบนี้เอา AI มาช่วยตั้งแต่ **แปลงเสียงประชุมเป็น transcript แยกผู้พูด**, **ร่างรายงานการประชุมอัตโนมัติ**, ไปจนถึง **ค้นหานโยบายบริษัทแบบแยกชั้นความลับ** — ออกแบบมาให้ข้อมูลระดับบอร์ดไม่มีทางหลุดไปปนกับระบบค้นนโยบายทั่วไปที่ทีมอื่นก็เข้าถึงได้!

---

## 📢 อัปเดตล่าสุด (Recent Updates)

- **🎙️ ตัดถอดเสียงใหม่ทีละคำพูด (Per-Segment ASR):** เดิมระบบตัดไฟล์เสียงเป็นชิ้นละ 1 ชั่วโมงตายตัวก่อนถอดเทป ทำให้บางทีตัดกลางประโยคพอดี ปรับใหม่ให้ตัดตาม "ช่วงที่แต่ละคนพูด" จริงๆ (diarization segment) แม่นยำขึ้นมาก แลกกับใช้เวลาถอดเทปมากขึ้นเล็กน้อย
- **🗣️ หน้าจอจับคู่ผู้พูด (Speaker Mapping):** หลังระบบแยกเสียงได้ว่า "คนที่ 1", "คนที่ 2" พูดตรงไหน ผู้ใช้จับคู่ชื่อจริงได้ก่อนส่งไปร่างรายงาน กันชื่อผิดคน
- **✏️ แก้ไข Transcript ได้เอง:** ถอดเทปผิดตรงไหน แก้คำได้เองก่อนส่งต่อ ไม่ต้องเชื่อ AI 100%
- **🖥️ หน้าเว็บใช้งานจริงแล้ว:** สร้างประชุม → อัปโหลดไฟล์เสียง → ระบบประมวลผลอัตโนมัติ → จับคู่ผู้พูด → ดู/แก้ไข transcript → export ไฟล์ .txt ได้ครบวงจรผ่านเบราว์เซอร์
- **⚡ แก้บั๊กความช้าผิดปกติของระบบค้นนโยบาย:** ค้นนโยบายเคยช้าถึง 15+ นาทีต่อคำถาม ตามล่าจนเจอสาเหตุจริง (ไม่ใช่ network, ไม่ใช่ SDK) แก้แล้วเหลือ 1-2 วินาที (ดูหัวข้อ Troubleshooting)

> 💡 สถานะปัจจุบัน: **MVP กำลังพัฒนา** — Module ถอดเสียง+แยกผู้พูด+ค้นนโยบายใช้งานได้จริงแล้ว ส่วนร่างรายงานการประชุมอัตโนมัติและระบบอนุมัติยังไม่เริ่ม (ดู [🎯 Roadmap](#-roadmap))

---

## 🔥 ไฮไลท์ฟีเจอร์เด่น (Key Features)

### 🎙️ 1. ถอดเสียงประชุมแยกผู้พูดอัตโนมัติ (Audio Transcription + Speaker Diarization)

อัปโหลดไฟล์เสียง/วิดีโอประชุม (จาก Google Meet, MS Teams หรือเครื่องบันทึกเสียง) ระบบจะฟังทั้งไฟล์แล้วบอกว่า "ใครพูดตอนไหน" ก่อน (**Diarization**) แล้วค่อยถอดเป็นข้อความทีละช่วงคำพูด (**ASR ภาษาไทยด้วย Typhoon ASR**) ได้ผลลัพธ์เป็น transcript ที่มีทั้งเวลาเริ่ม-จบและชื่อผู้พูดกำกับทุกประโยค — ไม่ต้องนั่งฟังซ้ำแล้วพิมพ์เองอีกต่อไป

- ✅ รองรับไฟล์เสียง/วิดีโอแทบทุกฟอร์แมต (ผ่าน `ffmpeg`)
- ✅ ประมวลผลอัตโนมัติในพื้นหลัง ไม่ต้องรอหน้าจอค้าง
- ✅ ใช้การ์ดจอ (GPU) แค่ตอนจำเป็น แล้วคืนหน่วยความจำทันทีให้โมเดลตัวถัดไปใช้ต่อ (รองรับเครื่องการ์ดจอเล็ก 4GB ได้)

### 🗣️ 2. จับคู่ชื่อผู้พูด (Speaker Mapping)

ระบบรู้แค่ว่า "คนที่ 1 / คนที่ 2" พูดตรงไหน แต่ไม่รู้ชื่อจริง — หน้าจอนี้ให้ผู้ใช้พิมพ์ชื่อจริงจับคู่เข้าไปทีเดียว (มี autocomplete จากรายชื่อผู้เข้าประชุมที่กรอกไว้ตอนสร้างนัดหมาย) ก่อนจะไปขั้นตอนร่างรายงานการประชุมได้

### ✏️ 3. แก้ไข Transcript ก่อนใช้งานจริง

AI ถอดเสียงไม่มีทางแม่น 100% หน้าจอนี้ให้แก้คำผิดทีละประโยคได้ก่อนส่งต่อ ข้ามได้ถ้ามั่นใจว่าถูกแล้ว

### 🔍 4. ค้นหานโยบายบริษัท แยกชั้นความลับ (Secure Policy RAG)

ถามคำถามเกี่ยวกับนโยบายบริษัทเป็นภาษาพูดธรรมดา ระบบค้นเอกสารที่เกี่ยวข้องแล้วสรุปคำตอบให้ — แบ่งเป็น **2 ชั้น** ตามความลับ:

- 📖 **ค้นนโยบายทั่วไป**: ทุกคนที่ล็อกอินเข้าใช้ได้
- 🔒 **ค้นเอกสารประชุมบอร์ดที่อนุมัติแล้ว**: จำกัดเฉพาะทีม Com Sec + กรรมการบอร์ดเท่านั้น เก็บแยกฐานข้อมูลกันคนละก้อนจากระบบค้นนโยบายทั่วไป **เพื่อไม่ให้ข้อมูลลับหลุดไปโผล่ในผลค้นหาของคนทั่วไปโดยไม่ตั้งใจ**

### 🖥️ 5. แดชบอร์ดใช้งานผ่านเบราว์เซอร์

หน้าเว็บ 3 หน้า (รายการประชุม / สร้างนัดหมายใหม่ / รายละเอียดประชุม) ออกแบบตามอัตลักษณ์องค์กร EMPIRE CI ใช้งานผ่านเบราว์เซอร์ได้เลยไม่ต้องติดตั้งอะไรเพิ่ม

---

## 🛠️ Tech Stack

### Backend

- **FastAPI** — REST API หลัก (port 8000)
- **SQLAlchemy + SQLite** — เก็บข้อมูลการประชุม/ผู้เข้าร่วม/วาระ/transcript
- **Azure AD (mock อยู่ตอนนี้)** — ระบบยืนยันตัวตน + สิทธิ์การใช้งาน

### AI / ML Workers (แยกโปรเซสจาก backend หลักเสมอ — ดู [Architecture](#-สถาปัตยกรรม-architecture))

- **RAG Worker** (port 8766): LlamaIndex + FAISS + BGE-M3 (embedding) + BGE-reranker-v2-m3 + Gemini (พร้อม fallback chain)
- **Audio Worker** (port 8767): `pyannote.audio` 3.3.2 (diarization, fine-tuned checkpoint ภาษาไทย) + Typhoon ASR (`nemo-toolkit`)

### Frontend

- **Static HTML/CSS/JS** — ไม่มี build step ให้ยุ่งยาก, FastAPI serve ตรงจาก `/dashboard`

### DevOps

- **GitHub Actions** — lint + syntax check ทุก push (`ruff`, `py_compile`, `node --check`)
- **pre-commit** — `detect-secrets` (กัน API key หลุด) + `ruff` (auto-fix ตอน commit)

---

## 🏗️ สถาปัตยกรรม (Architecture)

> 💡 **ทำไมต้องแยกเป็น 3 โปรเซส?** เพราะ `torch`/`faiss` (ที่ AI worker ทั้งสองตัวใช้) รวมเข้าโปรเซสเดียวกับ FastAPI web layer บน Windows แล้วเจอปัญหา crash จริง (`WINHTTP.dll` access violation) — แยกเป็นคนละโปรเซสตัดปัญหานี้ทั้งหมด แลกกับต้องคุยกันผ่าน HTTP ภายในเครื่องเดียวกัน

```
┌─────────────────┐      HTTP       ┌──────────────────┐
│   Backend API    │ ───────────────▶│    RAG Worker     │  port 8766
│   (port 8000)     │                 │  (ค้นนโยบาย/Gemini) │
│                   │      HTTP       └──────────────────┘
│  SQLite + Auth    │ ───────────────▶┌──────────────────┐
│  serves /dashboard │                 │   Audio Worker     │  port 8767
└─────────────────┘                 │ (ถอดเสียง+แยกผู้พูด) │
                                      └──────────────────┘
```

การ์ดจอ (GPU) ถูกแชร์ระหว่าง 3 ระบบด้วยการ**โหลดทีละตัว → ใช้งาน → คืนหน่วยความจำ → โหลดตัวถัดไป** ไม่ปล่อยให้สองโมเดลแย่ง VRAM พร้อมกัน (สำคัญมากบนเครื่องการ์ดจอเล็ก เช่น 4GB)

---

## 🛠 สิ่งที่ต้องมีในเครื่อง (Prerequisites)

- **Python 3.10+**
- **ffmpeg** (ต้องอยู่ใน PATH)
- **การ์ดจอ NVIDIA + CUDA** (แนะนำ — รันได้บน CPU แต่ช้ากว่ามาก มี fallback อัตโนมัติ)
- **Google Gemini API key** (สำหรับ RAG Worker)
- Hugging Face account ที่ accept terms ของ `pyannote/segmentation` แล้ว (โมเดล diarization เป็น gated model)

---

## 🚀 วิธีการเริ่มต้นใช้งาน (Quick Start)

### 1. ติดตั้ง dependencies ของแต่ละ process แยกกัน

```powershell
# Backend
cd backend
pip install -r requirements.txt

# RAG Worker — ⚠️ ต้องติดตั้ง torch แบบ CUDA เอง ไม่ใช่ pip install torch เฉยๆ (ได้ CPU-only wheel เงียบๆ)
cd ..\rag_worker
pip install -r requirements.txt
pip install torch==2.5.1 --index-url https://download.pytorch.org/whl/cu121

# Audio Worker — ⚠️ เหมือนกัน ต้องระบุ index-url ของ CUDA build
cd ..\audio_worker
pip install -r requirements.txt
pip install torch==2.8.0 torchaudio==2.8.0 torchvision==0.23.0 --index-url https://download.pytorch.org/whl/cu126
```

### 2. ตั้งค่า environment variables

คัดลอก `.env.example` → `.env` ในแต่ละโฟลเดอร์ (`backend/`, `rag_worker/`, `audio_worker/`) แล้วใส่ค่าจริง (เช่น `GOOGLE_API_KEY`)

### 3. รันทั้งระบบ

```powershell
# รันทีเดียวครบ (เปิดหน้าต่างแยกให้อัตโนมัติ)
start_all.bat

# หรือรันทีละตัวก็ได้ (สำหรับ debug)
rag_worker\start_worker.bat
audio_worker\start_worker.bat
backend\start_backend.bat
```

👉 เปิดใช้งานที่ `http://127.0.0.1:8000/dashboard/`

> 💡 RAG Worker ใช้เวลาโหลดโมเดลประมาณ 1-2 นาที รอจนขึ้นสถานะ "ready" ก่อนค่อยทดสอบ

---

## 📁 ตำแหน่งการจัดเก็บไฟล์

- 📂 `backend/` — REST API หลัก, ตาราง Meeting/ผู้เข้าร่วม/วาระ, ระบบยืนยันตัวตน
- 📂 `rag_worker/` — ค้นหานโยบายบริษัท (แยกดัชนีทั่วไป vs. ดัชนีลับระดับบอร์ด)
- 📂 `audio_worker/` — ถอดเสียงประชุม + แยกผู้พูด
- 📂 `ComSecAI_Dashboard/` — หน้าเว็บ (static HTML/CSS/JS)
- 📄 `handoff.md` — บันทึกความคืบหน้าโปรเจกต์แบบละเอียดทุกเซสชัน (สำหรับคนที่มาสานต่องาน)
- 📄 `task.md` — เช็กลิสต์ความคืบหน้ารายโมดูล
- 📄 `PRD.md` — เอกสารความต้องการโปรเจกต์ฉบับเต็ม

*💡 ไฟล์เสียง/วิดีโอต้นฉบับ, model checkpoint, และไฟล์ `.env` ทั้งหมด**ไม่ถูก commit เข้า git** (กันข้อมูลลับ/ไฟล์ใหญ่หลุด — ดู `.gitignore`)*

---

## 🎯 Roadmap

- ✅ **Module 0-1: โครงสร้างพื้นฐาน + ค้นหานโยบาย (RAG)** — DONE (ยกเว้น Azure AD จริง ยังเป็น mock auth)
- ✅ **Module 2: ถอดเสียงประชุม + แยกผู้พูด + จับคู่ชื่อ + แก้ไข transcript** — DONE (ยังไม่ tune diarization hyperparameter จริง, ยังไม่มีนโยบายเก็บรักษาไฟล์เสียง)
- 📋 **Module 3: ร่างรายงานการประชุมอัตโนมัติด้วย Gemini** — ยังไม่เริ่ม (ขั้นต่อไป)
- 📋 **Module 4-5: แมปข้อมูลลง Word Template + ระบบอนุมัติ Maker/Checker + ส่งอีเมลปลอดภัย** — ยังไม่เริ่ม
- 🚧 **Module 6: หน้าเว็บ (Frontend)** — เชื่อมกับ backend จริงครบ 3 หน้าแล้ว เหลือ Synced Audio/Video Player (ดูวิดีโอพร้อม transcript เลื่อนตามเวลา)

ดูรายละเอียดเช็กลิสต์แบบเต็มที่ [`task.md`](task.md)

---

## ⚠️ ความปลอดภัยและสิ่งที่ควรทราบ (Security & Privacy)

- 🔒 **ระบบยืนยันตัวตนยังเป็น mock** — `auth.py` ยังไม่ได้ต่อกับ Azure AD จริง (รอ tenant ID/client ID) **ห้ามใช้กับข้อมูลจริงจนกว่าจะเชื่อมต่อเสร็จ**
- 🛡️ **เอกสารลับแยกฐานข้อมูลจริง ไม่ใช่แค่แท็ก** — ป้องกันข้อมูลบอร์ดหลุดไปโผล่ในผลค้นหาของระบบนโยบายทั่วไป
- 👻 **ยังไม่มีนโยบายเก็บรักษาไฟล์เสียง/วิดีโอต้นฉบับ** (ระยะเวลาเก็บ, การเข้ารหัส, สิทธิ์เข้าถึงระดับไฟล์) — ต้องกำหนดก่อนใช้งานกับข้อมูลประชุมจริง
- 🔑 ไม่มี API key/secret ใดๆ ถูก commit เข้า git — มี `detect-secrets` scan ทุกครั้งที่ commit + ทุก push (CI)

---

## 🛠️ Troubleshooting

### ค้นหานโยบายช้ามาก (700-1000+ วินาทีต่อคำถาม)

**Status:** ✅ แก้แล้ว
**Impact:** ค้นนโยบายใช้เวลานานผิดปกติ ผู้ใช้รอไม่ไหว
**What broke:** โมเดล reranker auto-detect หาการ์ดจอไม่เจอ (เพราะเครื่องติดตั้ง `torch` แบบ CPU-only wheel เงียบๆ) เลยตกไปรันบน CPU + `float16` ซึ่ง CPU ส่วนใหญ่ไม่รองรับ fp16 จริง ต้องจำลองการคำนวณ ช้ากว่าปกติมาก
**Workaround/Fix:**
```powershell
# ต้องติดตั้ง torch แบบ CUDA build ชัดเจน ไม่ใช่ pip install torch เฉยๆ
pip install torch==2.5.1 --index-url https://download.pytorch.org/whl/cu121
python -c "import torch; print(torch.cuda.is_available())"  # ต้องได้ True
```

### `pip install torch` ได้ CPU-only wheel ทั้งที่มีการ์ดจอ

**Status:** ✅ รู้สาเหตุแล้ว มีคำเตือนในโค้ด
**Impact:** worker รันได้แต่ช้ากว่าที่ควรมาก โดยไม่มี error ให้เห็นเลย
**What broke:** PyPI ให้ CPU-only wheel เป็นค่าเริ่มต้นเงียบๆ ถ้าไม่ระบุ `--index-url` ของ CUDA build ชัดเจน
**Workaround:** ดูคำสั่งติดตั้งที่ระบุไว้ใน `rag_worker/requirements.txt` และ `audio_worker/requirements.txt` (มี comment อธิบายละเอียด) ตรวจสอบเสมอด้วย `torch.cuda.is_available()`

### Audio Worker error ว่าโหลดโมเดล diarization ไม่ได้

**Status:** ✅ รู้สาเหตุแล้ว
**What broke:** `pyannote/segmentation` เป็น gated model บน Hugging Face ต้อง accept terms ก่อน
**Workaround:**
```bash
huggingface-cli login
# แล้วไปกด Accept terms ที่ https://huggingface.co/pyannote/segmentation
```

---

## 🤝 เครดิตและขอขอบคุณ (Credits & Special Thanks)

- **[Local RAG / Policy RAG Assistant](../../../Review%20Policy/Local%20%20RAG)** — ฐานสถาปัตยกรรม RAG Worker (LlamaIndex + FAISS + BGE-M3 + reranker + Gemini fallback chain) ที่ผ่านการทดสอบจริงมาแล้ว
- **[typhoon-asr](https://github.com/scb-10x/typhoon-asr)** by **@scb-10x** — โมเดล ASR ภาษาไทยหลักที่ใช้ถอดเสียงประชุม
- **[Diarization_ThaiSpeech_2022](https://github.com/Gyoowai/Diarization_ThaiSpeech_2022)** by **@Gyoowai** — checkpoint diarization ที่ fine-tune สำหรับเสียงพูดภาษาไทย
- **[meetily](https://github.com/Zackriya-Solutions/meetily)** by **Zackriya Solutions** — อ้างอิงแพทเทิร์น Synced Audio/Video Player (`AudioPlayer.tsx`/`TranscriptView.tsx`) สำหรับ Module 6

---

## 📄 License

Private / Internal use only — ไม่เปิดสาธารณะ

## 📞 Support

พบปัญหาหรือมีคำถาม เปิด Issue ใน repo นี้ หรือติดต่อทีมเลขานุการบริษัทโดยตรง

## 👨‍💻 Maintainer

**Siraphob** — [siraphob.an@gmail.com](mailto:siraphob.an@gmail.com)

---

<p align="center">รายละเอียดความคืบหน้าแบบเต็ม อ่านได้ที่ <a href="handoff.md">handoff.md</a> และ <a href="task.md">task.md</a></p>
