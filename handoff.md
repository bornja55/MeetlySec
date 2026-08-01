# Project Handoff: Company Secretary AI System (MVP)

## 1. Project Overview
ระบบผู้ช่วยอัตโนมัติสำหรับเลขาบริษัท (Company Secretary) แบบครบวงจร ครอบคลุมตั้งแต่:
- **Audio Processing**: การถอดเสียงประชุมและแยกผู้พูด (Speaker Diarization) โดยเน้นภาษาไทยด้วย Typhoon ASR
- **Minutes Generation**: การส่งสคริปต์ที่ถอดเสียงแล้วไปยัง Cloud LLM (Gemini) เพื่อจัดรูปแบบออกเป็น JSON ที่มีโครงสร้างเป๊ะ (Structured Outputs) และหยอดลงใน Word Template ของบริษัท
- **Secure Local-RAG**: การทำระบบค้นหานโยบายและรายงานการประชุมย้อนหลัง (แยกสิทธิ์การค้นหาเอกสารลับผ่าน Azure AD)
- **Approval Workflow**: ระบบ Maker/Checker ที่ต้องอนุมัติก่อนส่ง PDF (Password-protected) แจ้งเตือนบอร์ดผ่าน Magic Link อีเมล พร้อม archive ไปยัง mapped drive/UNC path ที่เลือกได้
- **Frontend CI Enforcement**: บังคับใช้อัตลักษณ์ขององค์กร (EMPIRE CI) ทุกส่วนในแดชบอร์ด

---

## 2. Important Artifacts (เอกสารอ้างอิงหลัก)
กรุณาอ่านไฟล์เหล่านี้ก่อนเริ่มทำงานต่อ ห้ามเขียนแผนใหม่ซ้ำซ้อน:
- 📌 **Implementation Plan (Final):** [implementation_plan.md](implementation_plan.md) — พิมพ์เขียวสถาปัตยกรรม 6 โมดูล + ส่วน "Decisions from `/grill-me` session (2026-08-01)" ที่สรุปการตัดสินใจสำคัญทั้งหมด
- 📌 **Task Tracker:** [task.md](task.md) — เช็กลิสต์ความคืบหน้าที่ตรงกับสถานะจริงของโค้ด (ตรวจสอบแล้วผ่าน `/scrutinize` 2 รอบ)
- 📌 **โปรเจกต์อ้างอิงที่ reuse จริง:** `D:\Review Policy\Local  RAG` — Policy RAG Assistant ที่ทำงานจริงแล้ว (39 unit test + 11 E2E test ผ่านหมด) ใช้เป็นฐานของ Module 1 — **อ่าน `HANDOFF.md`/`ADR.md`/`CONTEXT.md` ของโปรเจกต์นั้นก่อน** ถ้าจะแตะ Module 1 เพราะมี constraint สำคัญเรื่องสถาปัตยกรรม (ห้ามรวม torch/faiss เข้า process เดียวกับ web layer บน Windows — ดูข้อ 3.1 ด้านล่าง)

---

## 3. Current Progress (สิ่งที่ทำไปแล้ว)
ทำงานกันอยู่ใน Directory: `D:\Com Sec`

### 3.0 Session สำคัญ 2026-08-01: `/scrutinize` พบ backend เดิมเป็น mock ทั้งหมด + ค้นพบ Local RAG ที่ใช้ได้จริง + `/grill-me` 3 รอบ

**สิ่งที่พบ:**
- ตรวจโค้ดจริงพบว่า checklist เดิมของ Module 1 เช็ก ✅ ไว้เกินจริงทั้งหมด — `auth.py` เป็น mock token string ล้วนๆ, `rag.py` เป็น stub คืนค่า hardcoded string, ไม่มี Vector DB จริง, venv ไม่เคยติดตั้ง dependency เลย, backend ไม่เคยถูกรัน
- พบโปรเจกต์ `D:\Review Policy\Local  RAG` ที่เป็น Policy RAG Assistant ทำงานจริงแล้ว (Streamlit + `rag_worker.py` แยกโปรเซส, LlamaIndex+FAISS+BGE-M3+BGE-reranker-v2-m3+Gemini fallback chain) — **แต่เป็นคนละวัตถุประสงค์กับ Com Sec** (ใช้สอบถามนโยบายเชิงลึก ไม่ใช่ workflow เลขาบริษัท) ทั้งสองจะอยู่คู่กันถาวร ไม่ retire ตัวไหน แต่ต้องแชร์ FAISS index เดียวกันไม่ให้ corpus drift

**การตัดสินใจสำคัญทั้งหมด (รายละเอียดเต็มอยู่ใน `implementation_plan.md` ส่วน Decisions + `task.md` แต่ละ module):**

1. **Module 1 สถาปัตยกรรม**: คง RAG worker เป็น**โปรเซสแยกต่อไป** (ไม่รวมเข้า FastAPI หลัก) เพราะ HANDOFF.md ของ Local RAG เตือนไว้ชัดเจนว่ารวมโปรเซสจะชน Windows WINHTTP.dll crash — เขียนใหม่แค่ชั้น HTTP (เป็น FastAPI แทน `http.server` เดิม) ส่วน logic module (`llm_fallback.py`, `worker_retrieval.py`, `worker_parsing.py`, `worker_prompts.py`, `worker_config.py`) reuse ได้ตรงๆ ไม่มี Streamlit dependency เลย
2. **RBAC**: ส่ง role/JWT ผ่าน HTTP header ให้ worker เช็คเอง (ไม่ต้องรวมโปรเซส), เปลี่ยน session model จากผูก browser tab เป็นผูกกับ authenticated user_id จริง
3. **Hardware**: ใช้ `typhoon-asr` เป็น ASR หลัก (ไม่ใช่ `typhoon2-audio` ซึ่งเป็นโมเดล 8B ต้องการ VRAM ~16GB+ เกิน 4GB ที่มีมาก — เก็บไว้เป็นตัวเลือก production บน cloud GPU ในอนาคต), RAG stack รัน CPU-only เสมอ, ภายใน Module 2 ใช้ GPU Lock ตัวเดียวให้ Diarization/ASR สลับกันขึ้น VRAM ทีละตัว
4. **Legal**: ยอมรับความเสี่ยง `Diarization_ThaiSpeech_2022` ไม่มี LICENSE (ใช้ภายในองค์กรเท่านั้น ไม่ redistribute)
5. **Module 3 (Minutes Generation)**: ใช้ Gemini ผ่าน `google-genai` (ไม่ใช่ Claude/Instructor), native structured output (`response_schema`), ใช้ Gemini API paid tier ตั้งแต่ทดสอบด้วยเนื้อหาจริงครั้งแรก (ไม่รอ production) เพราะเนื้อหาบอร์ดเป็นความลับสูง
6. **Workflow ใหม่ที่เพิ่มเข้ามา (ไม่มีในแผนเดิมเลย)**:
   - สร้าง "การประชุม" (Meeting) พร้อมผู้เข้าร่วม+วาระ **ก่อน**อัปโหลดไฟล์เสียง
   - หน้าจอ Speaker Mapping (บังคับ) จับคู่ `Speaker_00/01/02` กับชื่อจริงก่อนสรุปเป็น Minutes ได้
   - หน้าจอแก้ไข transcript (ไม่บังคับ) ใช้ UI เดียวกับ transcript-sync player
   - Approval flow เพิ่มสถานะ `Needs_Revision` (ตีกลับแก้ไข) ไม่ใช่แค่ Draft/Approved
   - รัน Diarization บนไฟล์เต็มความยาวก่อน (ไม่ตัดชิ้น) แล้วค่อยตัด ASR เป็นชิ้นละ 1 ชม. (กัน Speaker ID ไม่ตรงกันข้ามชิ้น)
   - รองรับไฟล์เสียง/วิดีโอ 3 แหล่ง (Google Meet, MS Teams, เครื่องบันทึก/มือถือ) แบบ manual upload เหมือนกันหมด ไม่ auto-fetch
   - Archive แยก 2 ปลายทางตามประเภทไฟล์: เอกสารรายงาน → ที่แชร์กับผู้บริหาร, ไฟล์เสียง/วิดีโอ → เฉพาะทีม Com Sec เท่านั้น (Board_Member เข้าไม่ได้)
7. **Module 6**: เพิ่มฟีเจอร์ Synced Audio/Video Player + Transcript Panel (อ้างอิงจาก `meetily/frontend`)

**สถานะ Module 1 (Backend Initialization & Auth) — แก้ไขจากเดิม:**
- มีแค่โครง FastAPI (`main.py`/`auth.py`/`rag.py`) ที่เป็น stub/mock ทั้งหมด ยังไม่มี logic ทำงานจริง — ของจริงที่จะ port เข้ามาคือ logic module จาก `D:\Review Policy\Local  RAG`

**Module 2 (Audio Processing Prep) — เสร็จแค่การโคลนโปรเจกต์:**
- โคลน Git Repositories ที่จำเป็นลงมาไว้แล้ว: `typhoon-asr`/`typhoon2-audio`, `Diarization_ThaiSpeech_2022`, `meetily` — ยืนยันแล้วว่าโคลนจริง มีไฟล์ครบ, license เช็คแล้ว (Apache 2.0 / MIT / ไม่มี license)
- `book-to-skill` ตัดออกจากแผนแล้ว (ซ้ำซ้อนกับเครื่องมือแปลงเอกสารที่ Local RAG มีอยู่แล้ว)

---

## 3.1 Session 2026-08-01 (ต่อจาก 3.0 วันเดียวกัน) — เริ่มเขียนโค้ด Module 1 จริง

**Goal**: ทำตาม "[Immediate Task ที่แนะนำ]" เดิมของ handoff ฉบับนี้ — สร้าง FastAPI RAG worker
process ใหม่ port logic จาก `D:\Review Policy\Local  RAG` แล้วต่อ RBAC/session ตาม user login

**สิ่งที่ทำเสร็จแล้ว (เขียนโค้ดจริง, verify ด้วย `py_compile`/`pyflakes` ใน sandbox เท่านั้น —
⚠️ ยังไม่เคยรันจริงบนเครื่อง Windows สักครั้ง เพราะ sandbox ไม่มี torch/faiss/BGE-M3/venv จริง)**:

1. **`D:\Com Sec\rag_worker\`** — worker process ใหม่ (FastAPI, พอร์ต 8766 แยกจาก Local RAG's
   8765):
   - `main.py` — entrypoint ใหม่ทั้งหมด (FastAPI แทน `http.server`), port `_load_everything()`
     จาก `rag_worker.py` เดิมมาปรับให้โหลด storage จาก `worker_config.STORAGE_DIR` (ชี้ Local RAG)
   - `worker_config.py` — ไฟล์เดียวที่ปรับจากต้นฉบับ (path เท่านั้น) ชี้ `BGE_M3_PATH`/
     `RERANKER_PATH`/`STORAGE_DIR`/`DATA_DIRS` ไปที่ `D:\Review Policy\Local  RAG` ตรงๆ (override
     ผ่าน `SHARED_RAG_DIR` env var) — **ไม่ copy corpus** ตามการตัดสินใจ
   - `worker_state.py`/`worker_prompts.py`/`worker_parsing.py`/`worker_retrieval.py`/
     `worker_handlers.py`/`llm_fallback.py` — copy จากต้นฉบับ **ไม่แก้แม้แต่บรรทัดเดียว**
   - `confidential_rag.py` (ไฟล์ใหม่ทั้งหมด) — ดัชนี FAISS **แยกต่างหาก** สำหรับ BOD Minutes ลับ
     (ไม่ใช่แท็ก metadata ในดัชนีเดียวกับ Local RAG) **เหตุผลสำคัญที่ต้องรู้**: Local RAG
     (Streamlit) ไม่มี RBAC เลย ถ้าใส่เอกสารลับลงดัชนีที่สองระบบชี้ร่วมกันจะเสี่ยงข้อมูลลับหลุดไป
     โผล่ในผลค้นหาของผู้ใช้ Local RAG ทั่วไปทันที — แยกดัชนีตัดความเสี่ยงนี้ทั้งหมด โหลดแบบ lazy
     (ไม่ block worker startup) เพราะยังไม่มีเอกสารลับจริงให้ index (Module 3/5 ยังไม่สร้าง)
   - `build_confidential_index.py` — สคริปต์ build ดัชนีลับ (โครงไว้ล่วงหน้า รอมี BOD minutes จริง)
   - `requirements.txt`/`.env.example` ของ worker นี้เอง (แยกจาก backend หลัก)
2. **`backend/rag.py`** — เขียนใหม่ทั้งหมดจาก stub (hardcoded string) เป็น `httpx` HTTP client
   เรียก `rag_worker` ที่ `127.0.0.1:8766` ส่ง `user_id`/`role` ต่อ จับ error (worker ไม่พร้อม/
   403/timeout) เป็น `RAGWorkerError` แปลงเป็น HTTP 503 ที่มีความหมายให้ frontend
3. **`backend/main.py`** — ต่อ `/api/rag/query`/`/api/rag/query_confidential` เข้ากับ
   `rag_pipeline.query()` ใหม่จริง ส่ง `user_id`/`role` จาก `Depends(verify_azure_ad_token)`/
   `Depends(require_role(...))` (ยังเป็น mock auth เดิม — ดูข้อ 4)
4. **`backend/requirements.txt`** — ตัด `instructor`/`sentence-transformers` ออก (ไม่ใช้/ย้ายไป
   worker), เพิ่ม `httpx`/`pyjwt`
5. **Grep เช็ค corpus หาชื่อบริษัทเก่าตกค้างแล้ว** — พบ **65/213 ไฟล์** ยังมี
   "ทเวนตี้ โฟร์ คอน แอนด์ ซัพพลาย" และ **166 ไฟล์** มีคำว่า "24CS" — **นี่คือรายงานผลเท่านั้น
   ยังไม่ได้แก้เนื้อหาเอกสารใดๆ** (การแก้เนื้อหานโยบาย/กฎหมายต้องให้เจ้าของนโยบาย/ผู้ใช้ตัดสินใจ
   ก่อน ไม่ใช่ AI แก้เองโดยพลการ) — ดู task.md Module 1 สำหรับรายละเอียดแยกตามโฟลเดอร์

**ยังไม่ได้ทำ / ทำไม่ได้ในเซสชันนี้ (ต้องทำต่อ)**:
- **รันจริงบนเครื่อง Windows** — ยังไม่เคยรันแม้แต่ครั้งเดียว (sandbox ไม่มี venv/torch/faiss/
  BGE-M3/API key จริง) ดูคำสั่งที่ต้องรันใน task.md Module 1 บรรทัดแรก
- **Azure AD จริง** — ยังไม่แตะ `auth.py` เลย ยังเป็น mock token string เดิมทั้งหมด (ต้องมี
  tenant ID/client ID จากผู้ใช้ก่อนถึงจะเริ่มได้)
- **ตัดสินใจเรื่องชื่อบริษัทเก่าตกค้าง 65 ไฟล์** — รอผู้ใช้ตัดสินใจว่าจะแก้หรือปล่อยไว้
- **เอกสารลับจริงยังไม่มี** — `confidential_rag.py`/`build_confidential_index.py` เป็นโครงที่
  พร้อมใช้ทันทีที่มี BOD minutes ที่ approve แล้ว (Module 3-5) แต่ตอนนี้ยัง end-to-end test ไม่ได้
  เพราะไม่มีข้อมูลจริงให้ทดสอบ

**Verification ที่ทำแล้ว**: `py_compile` ผ่านทุกไฟล์ที่แก้/สร้างใหม่ (backend + rag_worker),
`pyflakes` สะอาด ยกเว้น 2 จุดที่รู้อยู่แล้วว่าไม่ใช่บั๊ก: (1) `rag_worker/main.py`'s `import faiss`
unused — ตั้งใจ (ต้อง import ก่อน torch เสมอกันปัญหา DLL order เหมือนต้นฉบับ Local RAG ที่มี
finding เดียวกันนี้อยู่แล้ว) (2) `backend/auth.py`'s `os`/`jwt` imports unused — ค้างจาก mock auth
เดิม (ยังไม่แตะไฟล์นี้ รอ Azure AD จริง)

**Key Files ของเซสชันนี้**: `rag_worker/main.py`, `rag_worker/worker_config.py`,
`rag_worker/confidential_rag.py`, `backend/rag.py`, `backend/main.py`

---

## 4. Next Steps (สิ่งที่ต้องทำต่อไป)

**[Immediate — ต้องทำก่อนอย่างอื่น]**: รัน Module 1 ที่เขียนเสร็จแล้วให้ขึ้นจริงบนเครื่อง Windows
เป็นครั้งแรก (ดูคำสั่งเต็มในหัวข้อ 3.1 ด้านบน หรือ task.md Module 1) — ยังไม่เคยยืนยันว่ารันได้จริง
เลยสักครั้ง ควรยืนยันจุดนี้ก่อนต่อยอด Module 2

**งานที่เป็น execution ล้วนๆ ไม่ต้องตัดสินใจอะไรเพิ่ม (ทำได้เลย):**
- Verify VRAM จริงของ `typhoon-asr` บนเครื่อง 4GB
- ตัดสินใจเรื่องชื่อบริษัทเก่าตกค้าง 65 ไฟล์ (เช็คแล้วในหัวข้อ 3.1 — รอผู้ใช้ตัดสินใจว่าจะแก้/ปล่อยไว้)
- ออกแบบ UX คิว/สถานะสำหรับ user ที่อัปโหลดพร้อมกัน

**ทางเลือกที่ต้องตัดสินใจร่วมกับผู้ใช้**: Azure AD จริง (ต้องมี tenant ID/client ID) — ตอนนี้ยังเป็น
mock auth ทั้งหมด

**ทางเลือกอื่น**: ขึ้นโครง Module 2 (สร้าง Meeting entity + upload endpoint + ffmpeg extraction +
GPU-lock sequencing) — ควรทำหลัง Module 1 verify รันจริงแล้ว เพราะ Module 2 ต้องอิง user/role
เดียวกัน

ดู `task.md` สำหรับรายละเอียด checklist แบบเต็มของทุก module

---

## 4.5 Provenance ของ repo อ้างอิงที่ถูกลบ `.git`/asset ที่ไม่จำเป็นออกแล้ว (`/scrutinize` cleanup, 2026-08-01)

เพื่อประหยัดพื้นที่ ลบ `.git` history + asset ที่ไม่เกี่ยวกับการใช้งานจริงออกจาก repo อ้างอิงบางตัวแล้ว บันทึก commit ต้นทางไว้ที่นี่เผื่อต้องอ้างอิงย้อนหลัง (สำคัญกับ `Diarization_ThaiSpeech_2022` เพราะมีความเสี่ยงเรื่อง license ที่บันทึกไว้แล้ว):

| Repo | Remote | Commit ล่าสุดตอนโคลน | สิ่งที่ลบออกไปแล้ว |
|---|---|---|---|
| `meetily` | https://github.com/Zackriya-Solutions/meetily.git | `0281737d87d26352fb0adc78c8c0975f691b23d1` (2026-06-05) | `.git` (46M), `docs/` (34M, demo GIF/screenshot ล้วนๆ), `backend/` (876K, Rust/Python core ไม่ใช้), `llama-helper/` (28K) — เหลือแค่ `frontend/` (12M) ไว้อ้างอิง `AudioPlayer.tsx`/`useAudioPlayer.ts`/`TranscriptView.tsx` |
| `Diarization_ThaiSpeech_2022` | https://github.com/Gyoowai/Diarization_ThaiSpeech_2022.git | `ccc9ca5f77fdfa29e30b2ea4d0ecd06baf7ccb13` (2022-10-19) | `logs/` (48M), `cv02_metadata.csv` (11M), `.git` (262M, ลบเพิ่มหลัง confirm กับผู้ใช้) — เก็บ `checkpoints/` (โมเดลจริง) และ `tests/` (sample audio+ground truth สำหรับ smoke test) ไว้ |
| `book-to-skill` | https://github.com/virgiliojr94/book-to-skill.git | `efda3b2212ce1b2c052126e85e14de40a32442e8` (2026-07-30) | **ลบทั้งโฟลเดอร์แล้ว** (confirm จากผู้ใช้ — ตัดออกจากแผน product ทั้งหมด) |
| `typhoon2-audio` | https://github.com/scb-10x/typhoon2-audio.git | `6cd4d6063b944a1c27ae5a5f5e3616098a1bbba3` (2026-02-14) | ไม่ลบ — เก็บไว้เป็นเอกสารอ้างอิงสำหรับ production ในอนาคตตามแผน |
| `typhoon-asr` | https://github.com/scb-10x/typhoon-asr.git | `9859f19b0d523341c7be6e60b57ff2ec782cc52e` (2025-11-28) | ไม่ลบ — ใช้งานจริง |

---

## 5. Suggested Skills (สกิล AI ที่แนะนำให้เปิดใช้งานตอนสานต่อ)
หากผู้รับช่วงต่อเป็น AI แนะนำให้เรียกใช้สกิลต่อไปนี้ตามสถานการณ์:
- `/scrutinize`: หากมีการปรับเปลี่ยนสถาปัตยกรรมใหญ่ๆ ให้ใช้สกิลนี้ตรวจสอบช่องโหว่อีกครั้ง (เพราะระบบนี้เน้น Compliance หนักมาก) — ใช้ไปแล้ว 2 รอบ พบ CRITICAL finding สำคัญทั้งคู่ (Module 1 mock จริง, ความเสี่ยง Windows crash จากการรวมโปรเซส)
- `/grill-me`: หากทีมพัฒนาต้องการทดสอบไอเดีย หรือเช็กความพร้อมก่อนเขียนโค้ด — ใช้ไปแล้ว 3 รอบ ครอบคลุมทุกมิติของ Module 1-6 แล้ว
- `qwenchance`: เมื่อเริ่มเขียนโค้ดระบบ Audio Processing หรือ RAG ที่ลอจิกยาวและซับซ้อน ป้องกัน AI ติดลูป
