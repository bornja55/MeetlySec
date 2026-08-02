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
- 📌 **Task Tracker:** [task.md](task.md) — เช็กลิสต์ความคืบหน้าที่ตรงกับสถานะจริงของโค้ด (ตรวจสอบแล้วผ่าน `/scrutinize` หลายรอบตลอดโปรเจกต์ — ดูหัวข้อ 5 ด้านล่างสำหรับรายการ finding ที่พบแต่ละรอบ)
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
3. **Hardware**: ใช้ `typhoon-asr` เป็น ASR หลัก (ไม่ใช่ `typhoon2-audio` ซึ่งเป็นโมเดล 8B ต้องการ VRAM ~16GB+ เกิน 4GB ที่มีมาก — เก็บไว้เป็นตัวเลือก production บน cloud GPU ในอนาคต), ~~RAG stack รัน CPU-only เสมอ~~ **(กลับคำตัดสินใจแล้ว 2026-08-02 — ดู task.md Module 0 "กลับคำตัดสินใจ RAG stack CPU-only เสมอ เป็น ใช้ GPU ถ้ามี": พบ latency bug 700-1000s/query จริงจาก CPU+fp16 auto-detect ตกไปทาง CPU ตอนไม่มี CUDA build ของ torch แก้แล้วด้วยการติดตั้ง torch CUDA จริง + explicit `device=` detection ปัจจุบัน RAG worker ใช้ GPU resident ตลอด query เหลือ 1-2s)**, ภายใน Module 2 ใช้ GPU Lock ตัวเดียวให้ Diarization/ASR สลับกันขึ้น VRAM ทีละตัว (คนละโปรเซสจาก RAG worker — ไม่ต้อง lock ร่วม ดู Module 0/3.2 สำหรับตัวเลข VRAM headroom เต็ม)
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

**อัปเดต (2026-08-01 ต่อ — หลัง live test จริงบนเครื่อง Windows)**: ผู้ใช้รัน worker + backend
จริงสำเร็จแล้ว, `/api/rag/query` ตอบ JSON คำตอบจริงกลับมา 2 ครั้ง (ไม่ error) — **Module 1 ใช้งาน
ได้จริงเป็นครั้งแรกแล้ว** ระหว่างเทสเจอบั๊กจริง 3 จุด แก้ครบแล้ว: (1) `query` เดิมเป็น URL query
parameter → ข้อความไทยดิบทำผิด HTTP/1.1 request-line grammar → เปลี่ยนเป็น JSON body, (2)
`RAG_WORKER_TIMEOUT_SECONDS` เดิม 60s สั้นเกินไป (ของจริงใช้เวลา ~1000s/query) → ปรับเป็น 1800s
ชั่วคราว, (3) secret หลุดผิดไฟล์ (Google API key จริงอยู่ใน `backend/.env.example` แทน `.env`) →
แก้แล้ว ยืนยันไม่เคย commit/push จึงไม่รั่วจริง — ดู task.md Module 1 สำหรับรายละเอียดเต็ม

**ยังไม่ได้ทำ / ทำไม่ได้ในเซสชันนี้ (ต้องทำต่อ)**:
- ⚠️ **latency ผิดปกติที่ยังไม่ทราบสาเหตุแท้จริง** — query สำเร็จที่ primary model เอง
  (`gemini-3.1-flash-lite`) แต่ใช้เวลา 1005s/987s ต่อครั้ง สูงผิดปกติมาก ทดสอบ raw network latency
  ไปยัง Google API แล้วพบว่าเร็วปกติ (0.286s) ตัดประเด็น proxy/VPN ออกได้ — ตั้งสมมติฐานว่าเป็น
  retry ภายใน `google-genai` SDK เอง (เช่น free-tier rate limit) ที่อยู่นอกเหนือ logging ของเรา
  ยังไม่ยืนยันสาเหตุแท้จริง ต้องตรวจสอบก่อนขึ้น production
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

## 3.2 Session 2026-08-02 (ต่อ) — `/debug-mantra`: ปิดเรื่อง GPU Lock ด้วยตัวเลขจริง

**Goal**: ทำตาม "[Immediate]" ของ handoff ฉบับก่อน — ออกแบบ GPU Lock ให้ครอบคลุม RAG worker
ด้วย ไม่ใช่แค่ Module 2 (Diarization+ASR) ก่อนเริ่มสร้าง Module 2 จริง

**สิ่งที่ทำเสร็จแล้ว**:
1. **Mantra 4 (cross-reference) พบจุดไม่ตรงกันใน `task.md`**: Module 1 ยังมี entry latency bug
   เดิมเป็น `[ ]` พร้อม hypothesis เก่า (SDK retry) ทั้งที่ Module 0 มี root cause จริงที่ยืนยันแล้ว
   (auto-detect ตกไป CPU+fp16) — แก้ entry ให้ตรงกับ Module 0 แล้ว
2. **เช็คโค้ด `rag_worker/main.py`/`worker_config.py`/`build_confidential_index.py`**: ยืนยันว่า
   ไม่มี GPU lock อยู่เลยในระบบตอนนี้ — RAG worker โหลด BGE-M3+reranker ครั้งเดียวตอน startup แล้ว
   ค้างบน VRAM ตลอด ไม่เคยเรียก `torch.cuda.empty_cache()`
3. **ถามผู้ใช้ (AskUserQuestion)** ว่า RAG worker ควร resident เสมอ หรือเข้าคิวร่วม lock (unload
   เมื่อ idle) — ผู้ใช้เลือก **"รอวัด VRAM จริงก่อนตัดสินใจ"** (มะตรา 1: ห้ามเดา ต้อง reproduce)
4. **เขียน `D:\Com Sec\diagnose_vram_module2.py`** (สคริปต์ throwaway, ไม่ใช่ production code) —
   โหลด+รัน `typhoon-asr` และ `Diarization_ThaiSpeech_2022` ทีละตัวบน GPU จริง วัด
   `torch.cuda.max_memory_allocated()`/`reserved()` — verify ใน sandbox ได้แค่ `py_compile`/
   `pyflakes` (sandbox ไม่มี GPU) แล้วให้ผู้ใช้รันจริงบนเครื่อง Windows ไล่แก้บั๊กจริงหลายจุดจนผ่าน:
   - dependency (`nemo`, `pyannote`) ไม่เคยติดตั้งเลย — ต้องสร้าง venv ใหม่
   - `typhoon-asr/requirements.txt` pin `torch==2.8.0` แบบไม่มี `--index-url` → ได้ CPU-only wheel
     เงียบๆ (บั๊กสายพันธุ์เดียวกับที่เคยเจอตอน RAG worker) → ต้องติดตั้งซ้ำด้วย
     `--index-url https://download.pytorch.org/whl/cu126` (cu121/cu124 ไม่มี wheel 2.8.0 — เช็ค
     จาก pip error จริงของผู้ใช้เอง หลังข้อมูล search ครั้งแรกผิด)
   - `pyannote/segmentation` เป็น gated model บน Hugging Face — ต้อง accept terms +
     `huggingface-cli login`
   - โค้ดต้นฉบับใน `Evaluate_Diarization.ipynb` (pytorch-lightning ~1.5.x, ปี 2022) เรียก
     `instance.load_from_checkpoint(...)` ได้ — พัง บน pytorch-lightning 2.5.3 (เป็น classmethod
     ล้วนๆแล้ว) แก้เป็น `type(pretrained).load_from_checkpoint(ckpt_path, map_location=...)`
   - hyperparameter dict เดิมของ notebook (`segmentation_onset`, `clustering.
     single_cluster_detection`) เป็น API ของ `pyannote.audio` **2.x** ใช้กับ 3.3.2 ที่ติดตั้งจริง
     ไม่ได้เลย — ดาวน์โหลดซอร์ส 3.3.2 มาอ่านจริงในนี้ (`pip download --no-deps` เพราะ sandbox
     ไม่มี GPU รันไม่ได้ แต่อ่านซอร์สได้) แล้วเขียนใหม่เป็น
     `{"segmentation": {"threshold","min_duration_off"}, "clustering":
     {"threshold","method","min_cluster_size"}}` (ค่ากลางๆ พอสำหรับวัด VRAM เท่านั้น **ไม่ใช่ค่า
     tune จริง** ถ้าจะใช้งานจริงใน Module 2 ต้อง tune ใหม่)
   - ลองแก้ด้วยการ downgrade `pyannote.audio` เป็น `2.1.1` (ให้ตรง notebook เป๊ะ) — **ล้มเหลว**
     เพราะ dependency `torchaudio<1.0` ชนกับ torch/torchaudio 2.8.0+cu126 ที่ต้องใช้ (ยืนยันแล้วว่า
     pip ไม่ทันได้ install อะไรก่อน error เลย environment เดิมไม่เสียหาย) — ปิดทางเลือกนี้ไปเลย
5. **ผลวัดจริงบนเครื่อง** (RTX 3050 Laptop, VRAM รวม 4096MiB):
   - RAG worker resident (รวม Windows desktop overhead): **3060MiB**
   - `typhoon-asr` (โปรเซสแยก, peak reserved): **564MiB**
   - `Diarization_ThaiSpeech_2022` (โปรเซสแยก, peak reserved): **242MiB**
   - headroom เหลือหลัง RAG worker: **1036MiB**
6. **ตัดสินใจสุดท้าย (บันทึกเต็มใน `task.md` Module 0)**: **RAG worker คง resident ตลอดไป ไม่ต้อง
   unload/เข้าคิวร่วม lock** — โมเดล Module 2 ที่หนักสุด (ASR, 564MiB) ยังพอดีใน headroom 1036MiB
   เหลือ margin ~472MiB ไม่ต้องแลกความเร็ว query (1-2s) กับ unload-on-idle ที่ซับซ้อนกว่า **GPU
   Lock ที่ต้องสร้างจริงจึงเหลือแค่ระหว่าง Diarization↔ASR เท่านั้น** (ตามแผนเดิมของ Module 2 ก่อน
   พบปัญหานี้เลย) เพราะทั้งสองรันในโปรเซสเดียวกับ backend (async background task, queue เดียว
   ไม่ขนาน) ไม่ใช่คนละโปรเซสกับ RAG worker — ไม่ต้องมี cross-process lock ครอบคลุม 3 ระบบ แค่
   โหลด→รัน→`del`+`gc.collect()`+`torch.cuda.empty_cache()`→โหลดตัวถัดไปตามลำดับในโปรเซสเดียวพอ
   + เก็บ CPU fallback (`torch.cuda.OutOfMemoryError`→CPU) ที่ตัดสินใจไว้แล้วเป็น safety net
7. **ผู้ใช้ลบ `diagnose_venv` แล้วติดตั้ง dependency ชุดเดียวกัน (torch 2.8.0+cu126, nemo-toolkit,
   pyannote.audio 3.3.2, speechbrain) ลง global Python แทน** (ทางเลือกของผู้ใช้เอง ไม่ใช่คำแนะนำ
   ของ AI) — แจ้งเตือนแล้วว่า global env นี้เป็นตัวเดียวกับที่เคยมี torch 2.13.0 CPU-only จนเป็น
   ต้นเหตุบั๊ก latency ตัวแรกของ RAG worker (ดู 3.1 ด้านบน) ~~**คำสั่ง verify สุดท้ายที่ให้ผู้ใช้รัน
   (`python -c "import torch; print(torch.__version__, torch.cuda.is_available())"`) ยังไม่ได้
   รับผลยืนยันกลับมาก่อนตัด session — ต้องขอผลนี้ก่อนเขียนโค้ด Module 2 จริงที่พึ่ง GPU**~~ **แก้แล้ว
   (ดู 3.4 ด้านล่าง)**: ผลยืนยันกลับมาว่า global Python มี `torch 2.8.0+cu126` ใช้งานได้จริง Module 2
   เขียนโค้ดต่อและ live test สำเร็จบน GPU จริงแล้ว (ปิดจบเรื่องนี้แล้ว)

**Key Files ของเซสชันนี้**: `D:\Com Sec\diagnose_vram_module2.py` (ใหม่ทั้งไฟล์ — throwaway
diagnostic script แต่มี reference implementation ของการโหลด custom pyannote checkpoint บน API
3.x ที่ port มาจาก notebook เก่าแล้ว เก็บไว้ reuse ได้), `task.md` (ปิด item Module 0 GPU VRAM +
แก้ stale entry Module 1)

---

## 3.3 Session 2026-08-02 (ต่อ) — `/handoff`: ASR redesign per-segment (งานค้างกลางทาง)

**Status**: กำลังกลางทางการ redesign ASR ให้ transcribe ทีละ diarization segment แทนการตัดชิ้นละ
1 ชม. — **ยังไม่ได้แก้โค้ดสักไฟล์เดียวในรอบนี้** (แค่ Read `worker_config.py`/`backend/main.py`/
`backend/models.py`/`backend/db.py` เพื่อเตรียมแก้)

**Goal**: ผู้ใช้เลือกวิธี "ตัด ASR ใหม่ทีละ segment ของ diarization (แม่นยำสุด แต่ transcribe เยอะ
ครั้งขึ้นมาก — segment สั้นๆหลักวินาที)" แทน heuristic proportional-matching — ต้องการให้ audio
pipeline คืนค่า unified `transcript_segments` (start/end/speaker/text) ตรงๆจาก pipeline โดยไม่ต้อง
merge ทีหลัง

**What's done** (จาก session ก่อนๆ, ไม่ใช่รอบนี้): Module 2 ทำงาน end-to-end แล้วบนเครื่องจริง
(Meeting entity + SQLite/SQLAlchemy, upload → background task → audio_worker แยกโปรเซส port 8767 →
diarization เต็มไฟล์ → ASR ชิ้นละ 1 ชม. → บันทึก `diarization_segments_json`/`asr_chunks_json`
แยกกัน), GPU VRAM release bug แก้+verify แล้วด้วย log จริง, `WorkerBusyError` + path traversal
guard แก้แล้ว (จาก `/scrutinize`) — task tool มี Task #4 "Redesign ASR to transcribe per
diarization segment" สร้างไว้แล้ว status `in_progress`

**What's next** (ลำดับที่ต้องทำ ยังไม่เริ่มสักขั้น):
1. แก้ `audio_worker/worker_config.py` บรรทัด 64-67: เปลี่ยน `ASR_CHUNK_SECONDS` (ปัจจุบันคือ
   `int(os.environ.get("ASR_CHUNK_SECONDS", str(60 * 60)))`) → `ASR_MAX_SEGMENT_SECONDS` (เสนอ
   default 30s อ้างอิง typhoon-asr training `max_duration: 30.0` — **ยังไม่ verify ว่าโมเดล
   "realtime" ทนอินพุตยาวกว่านั้นได้ไหม**) ใช้เป็นเพดานตัด segment ที่ยาวเกิน ไม่ใช่ขนาด chunk คงที่
2. แก้/เขียนใหม่ `audio_worker/asr.py`: ลบ `transcribe_in_chunks` ออก เพิ่ม
   `transcribe_segments(model, wav_path, segments) -> list[dict]` — วนทุก diarization segment,
   ใช้ `ffmpeg_utils.extract_chunk` ตัดเสียงเฉพาะช่วง, sub-split ถ้ายาวเกิน
   `ASR_MAX_SEGMENT_SECONDS`, transcribe ต่อชิ้น, คืน list ของ `{start, end, speaker, text}`
3. แก้ `audio_worker/pipeline.py`: `_run_asr_stage` รับ `segments` (ผลจาก `_run_diarization_stage`)
   เป็นพารามิเตอร์, `process_audio_file` ส่ง diarization segments เข้า ASR stage แล้วคืน field
   เดียว `transcript_segments` (เลิกใช้ `diarization_segments`/`asr_chunks` แยกกัน) — ระวังบั๊ก
   `del` ซ้ำแบบที่เคยเจอ (การ `del` ใน scope ของ callee ไม่ล้าง reference ของ caller)
4. แก้ `backend/models.py`: รวม `diarization_segments_json` + `asr_chunks_json` เป็นคอลัมน์เดียว
   `transcript_segments_json` (Text, nullable)
5. แก้ `backend/main.py`: `_meeting_to_dict()` (บรรทัด 99-118) คืน `transcript_segments` แทน 2
   field เดิม, `_process_meeting_audio_background()` (บรรทัด 192-194) เก็บ
   `result.get("transcript_segments")` ลง `meeting.transcript_segments_json`
6. แก้ `audio_worker/.env.example` ให้ตรงชื่อ env var ใหม่
7. verify ทุกไฟล์ด้วย `py_compile`+`pyflakes` ใน sandbox (ไม่มี GPU — ต้องให้ผู้ใช้รันจริงบน
   Windows อีกที)
8. อัปเดต `task.md` (Module 2 section) ให้ตรงกับ redesign นี้
9. **แจ้งผู้ใช้ก่อนรันจริง**: ต้องลบ `D:\Com Sec\backend\com_sec.db` ทิ้งก่อน restart backend
   รอบหน้า เพราะ SQLAlchemy's `create_all()` สร้างแค่ตารางที่ยังไม่มี ไม่ ALTER ตารางเดิม — ไม่มี
   Alembic migration ระบบ แต่เป็น MVP/test data ล้วนๆ ลบทิ้งได้ปลอดภัย

**Key decisions**: เลือก per-segment ASR แบบ explicit (ผู้ใช้ตัดสินใจเอง ไม่ใช่ AI แนะนำ) —
ตัดทางเลือก proportional-matching heuristic ทิ้งแล้ว

**Files ที่ต้องแก้ในรอบนี้**: `audio_worker/worker_config.py`, `audio_worker/asr.py`,
`audio_worker/pipeline.py`, `backend/models.py`, `backend/main.py`, `audio_worker/.env.example`,
`task.md` — ไฟล์ที่ **ไม่ต้องแก้** (พร้อมใช้กับ redesign นี้อยู่แล้ว): `audio_worker/diarization.py`
(คืน `list[{start,end,speaker}]` ตรงกับ input ที่ `transcribe_segments` ต้องการพอดี),
`audio_worker/ffmpeg_utils.py` (มี `extract_chunk()` พร้อมใช้), `audio_worker/gpu_utils.py`,
`audio_worker/main.py`

**How to resume**: เปิด `audio_worker/worker_config.py` แก้บรรทัด 64-67 ตามข้อ 1 ด้านบนก่อน
จากนั้นไล่ทำข้อ 2-9 ตามลำดับ

---

## 3.4 Session 2026-08-02 (ต่อ) — `/debug-mantra`: ASR redesign per-segment เขียนโค้ดเสร็จแล้ว

**Goal**: ทำข้อ 1-9 ของ 3.3 ให้จบ — เปลี่ยน ASR จากตัดชิ้นละ 1 ชม. เป็นตัดใหม่ทีละ diarization
segment ตรงๆ

**Mantra 1+4 ก่อนแก้โค้ด**: อ่านไฟล์ที่เกี่ยวข้องทั้งหมด (`worker_config.py`/`asr.py`/
`pipeline.py`/`diarization.py`/`ffmpeg_utils.py`/`gpu_utils.py`/`main.py`/`backend/models.py`/
`backend/main.py`/`backend/audio.py`/`backend/db.py`) ยืนยันตรงกับที่ 3.3 อธิบายไว้ทุกจุด — พบ
breadcrumb ไม่ตรงกัน 1 จุด: handoff เดิมอ้าง typhoon-asr training `max_duration: 30.0` แต่ grep
ซอร์สจริงที่โคลนมา (`typhoon-asr/examples/finetune.py` บรรทัด 187/193) เจอ `max_duration = 20`
ไม่ใช่ 30 — ใช้ **20s** เป็น default ของ `ASR_MAX_SEGMENT_SECONDS` แทน (เลขที่ verify จากซอร์สจริง
ไม่ใช่จากความจำ)

**สิ่งที่ทำเสร็จแล้ว (เขียนโค้ดจริงครบทั้ง 9 ข้อของแผน 3.3)**:
1. `audio_worker/worker_config.py` — `ASR_CHUNK_SECONDS` (60*60) → `ASR_MAX_SEGMENT_SECONDS`
   (default 20, override ผ่าน env) เป็นเพดานความยาวต่อ segment ไม่ใช่ขนาด chunk คงที่แล้ว
2. `audio_worker/asr.py` — ลบ `transcribe_in_chunks` ออก เขียนใหม่เป็น
   `transcribe_segments(model, wav_path, segments)`: วนทุก diarization segment, ข้าม segment
   สั้นกว่า `MIN_SEGMENT_SECONDS=0.1` (กัน artifact จาก clustering ที่ยังไม่ tune), sub-split ด้วย
   `_split_range()` (แบ่งเท่าๆกัน ไม่ใช่เดินหน้าทีละก้อนคงที่ กันชิ้นสุดท้ายสั้นเกินไป) ถ้ายาวเกิน
   เพดาน, ตัด+transcribe ต่อชิ้นด้วย `ffmpeg_utils.extract_chunk`, คืน `{start, end, speaker, text}`
   ต่อ entry (จำนวนอาจมากกว่า diarization segments เดิมถ้ามี sub-split)
3. `audio_worker/pipeline.py` — `_run_asr_stage(wav_path, segments)` รับ segments จาก
   `_run_diarization_stage` ส่งต่อ `asr.transcribe_segments`, `process_audio_file` คืน field เดียว
   `transcript_segments` (เลิก `diarization_segments`/`asr_chunks` แยกกัน) — คง pattern `del`
   ในสโคปฝั่งเรียก + `gpu_utils.release_gpu_memory()` เดิมไว้ทั้งหมด ไม่แตะ GPU lock logic
4. `backend/models.py` — รวม `diarization_segments_json`+`asr_chunks_json` เป็นคอลัมน์เดียว
   `transcript_segments_json`
5. `backend/main.py` — `_meeting_to_dict()` คืน `transcript_segments`, background task เก็บ
   `result.get("transcript_segments")` ลง `meeting.transcript_segments_json`
6. `audio_worker/.env.example` — เปลี่ยนชื่อ env var + comment อธิบาย semantic ใหม่ (เพดาน ไม่ใช่
   ขนาด chunk คงที่)
7. `backend/audio.py` — แก้ docstring ที่อ้าง field name เก่า (`diarization_segments`/`asr_chunks`)
   ให้ตรงกับ response จริงตอนนี้ (ไม่ใช่โค้ด logic เพราะไฟล์นี้แค่ pass-through `resp.json()`)
8. Verify: `py_compile` ผ่านทุกไฟล์ (audio_worker ทั้งหมด + backend ที่แก้) ✅, `pyflakes` สะอาด
   ทุกไฟล์ที่แก้ ไม่มี unused import/variable ✅ (sandbox ไม่มี GPU — **ยังไม่เคยรันจริงบนเครื่อง
   Windows รอบนี้เลย**)
9. `task.md` (Module 2) — อัปเดต 3 entry ให้ตรงกับ redesign: chunk-based ASR item, merge TODO
   item (ปิดแล้ว — วิธีแก้คือเปลี่ยนวิธีตัด ไม่ใช่ merge ทีหลัง), multi-chunk test finding (ตอกย้ำ
   เหตุผลที่เลือก redesign นี้)

**ยังไม่ได้ทำ / ทำไม่ได้ในเซสชันนี้**:
- ✅ **แก้แล้ว (ดู "อัปเดต" ด้านบน) — รันจริงบนเครื่อง Windows สำเร็จแล้ว** ด้วยเสียงไทยจริง 60s
  ผ่านครบ end-to-end, sub-split + GPU release verify ด้วยเลขจริงแล้วทั้งคู่
- ⚠️ **ต้องลบ `D:\Com Sec\backend\com_sec.db` ก่อน restart backend รอบหน้า** — schema เปลี่ยน
  (`diarization_segments_json`+`asr_chunks_json` → `transcript_segments_json`) SQLAlchemy's
  `create_all()` ไม่ ALTER ตารางเดิม ไม่มี Alembic migration (MVP/test data ล้วนๆ ลบทิ้งได้ปลอดภัย)
- `MIN_SEGMENT_SECONDS=0.1` และวิธี sub-split แบบแบ่งเท่าๆกันใน `_split_range()` เป็นค่า/วิธีที่
  เลือกเอง (ไม่ใช่การตัดสินใจร่วมกับผู้ใช้) — ยังไม่ verify ด้วยข้อมูลจริงว่าเหมาะสม ต้องดูผลลัพธ์
  จริงหลังรันบน Windows ก่อน

**Key Files ของเซสชันนี้**: `audio_worker/worker_config.py`, `audio_worker/asr.py`,
`audio_worker/pipeline.py`, `backend/models.py`, `backend/main.py`, `audio_worker/.env.example`,
`backend/audio.py`, `task.md`

**อัปเดต (2026-08-02 ต่อ — verify จริงบน Windows สำเร็จ)**: ผู้ใช้ลบ `com_sec.db`, เปิด 3 process
(RAG worker/backend/audio worker), สร้าง meeting → อัปโหลด `Diarization_ThaiSpeech_2022/tests/
Parliament_1m/Parliament_1m.wav` (เสียงไทยจริง 60s, รัฐสภา) → poll จน `status="transcribed"` สำเร็จ
ใน 63.2s **redesign ทำงานได้จริงเป็นครั้งแรก**:
- ✅ **sub-split ยืนยันถูกต้องด้วยเลขจริง**: diarization segment 1.85s-31.49s (29.64s ยาวเกิน 20s)
  ถูกแบ่งเป็น 2 ชิ้น 14.82s เท่ากันเป๊ะ (1.85-16.67, 16.67-31.49) ตรงสูตร `ceil(29.64/20)=2` parts
  ของ `_split_range()` พอดี — อีกจุด (33.27-59.97, 26.7s) ก็แบ่ง 2 ชิ้น 13.35s เท่ากันเช่นกัน
- ✅ **GPU release ยัง regression-safe**: log VRAM เหมือนเดิมทุกประการ (560MiB→115MiB หลังปล่อย ASR)
  ไม่ได้พังจากการแก้รอบนี้
- ⚠️ **พบ (ไม่ใช่บั๊กจากรอบนี้ เป็นผลจาก diarization hyperparameter ที่ยังไม่ tune อยู่แล้ว — ดู
  `diarization.py` warning เดิม)**: มี segment สั้นมาก (0.3-0.5s) ของ `SPEAKER_00` คืน `text=""`
  (ว่างเปล่า) 3 จาก 4 ครั้ง — ผ่าน `MIN_SEGMENT_SECONDS=0.1` เกณฑ์เลยส่งเข้าโมเดลแต่โมเดลไม่ได้ยินคำ
  พูดชัดเจนพอ น่าจะเป็น clustering artifact จาก `min_cluster_size=1` (ค่ากลางๆยังไม่ tune) มากกว่า
  ปัญหาโค้ด

**ตัดสินใจรอบแรก (ผู้ใช้เลือก)**: ขยับเกณฑ์ขั้นต่ำขึ้น — ย้าย `MIN_SEGMENT_SECONDS` จาก `asr.py`
ไปไว้ `worker_config.py` (เปลี่ยนชื่อเป็น `ASR_MIN_SEGMENT_SECONDS` ให้สอดคล้องกับ tunable อื่นๆ)
ปรับ default 0.1s → 0.5s `py_compile`/`pyflakes` ผ่านสะอาดหลังแก้

**Live test รอบ 2 (verify บนเครื่องจริงด้วยไฟล์เดิม `Parliament_1m.wav`)**: ผลตรงกับที่คาด+เตือนไว้
พอดี — **falsify แล้ว ไม่ใช่แค่ทฤษฎี**:
- ✅ กรองได้ 3/4: segment 0.37s/0.32s/0.41s หายไปหมด (ไม่ถูกส่งเข้าโมเดลอีกต่อไป)
- ❌ **segment 0.54s ("28.82-29.36") ยังหลุดผ่านเกณฑ์ 0.5s ได้ (ยาวกว่า) แต่ยังคืน text ว่างเปล่า
  เหมือนเดิม** — พิสูจน์ชัดว่าความยาว segment ไม่ใช่ตัวชี้วัดคุณภาพที่แม่นยำ (แค่ correlate หลวมๆ)
- ⚠️ **ผลข้างเคียงที่เสียไป**: segment 0.37s ที่เคยให้คำจริง ("วันนี้") โดนกรองทิ้งไปด้วย เพราะสั้น
  กว่าเกณฑ์ — heuristic ตาม duration แลกความแม่นยำกับ recall ไม่ได้

**ตัดสินใจรอบ 2 (ผู้ใช้เลือก, 2026-08-02 ต่อ)**: เปลี่ยนวิธีจาก duration-heuristic (ทำนายล่วงหน้าว่า
segment ไหนน่าจะว่าง) เป็น **filter จากผลจริงหลัง transcribe แล้ว** (แม่นยำกับผลจริงของโมเดล ไม่ใช่
การเดาจาก duration อีกต่อไป — ไม่ได้แปลว่าคุณภาพ transcription สมบูรณ์แบบ 100%)

**โค้ดที่แก้**:
- `audio_worker/asr.py`'s `transcribe_segments()` — หลัง transcribe แต่ละ (sub-)segment แล้ว ถ้า
  `text` ว่างเปล่า/whitespace ล้วน → `continue` ไม่ append เข้า `results` (ไม่ส่ง entry ว่างเปล่าให้
  downstream เห็นอีกต่อไป)
- `worker_config.py`'s `ASR_MIN_SEGMENT_SECONDS` — กลับ default 0.5s → **0.1s** เปลี่ยนบทบาทกลับเป็น
  แค่กันขอบเขตทางเทคนิค (ffmpeg/model เจอ input สั้นผิดปกติ) ไม่ใช่ตัวกรองคุณภาพแล้ว
- เพิ่ม logging (`transcribe_segments` log สรุป `skipped_too_short`/`dropped_empty_text` ต่อไฟล์) —
  ไว้เทียบสัดส่วนตอนตัดสินใจ tune diarization hyperparameter จริงในอนาคต (ยิ่ง dropped_empty สูงเทียบ
  input segments ยิ่งบ่งชี้ปัญหาที่ clustering hyperparameter ชัดเจน)

**`/scrutinize` บนการแก้นี้**: พบ 1 จุดที่ต้องแก้จริง (ไม่ใช่แค่ทฤษฎี) — `audio_worker/.env.example`
ยังมี `ASR_MIN_SEGMENT_SECONDS=0.5` ค้างจากการตัดสินใจรอบแรก ถ้าใครสร้าง `.env` จริงจากไฟล์นี้ตอนนี้
จะได้ค่าเก่าที่พิสูจน์แล้วว่าใช้ไม่ได้ผลกลับมาซ่อนอยู่ (env var ทับ code default) — **แก้แล้ว** กลับเป็น
0.1 พร้อมอธิบายเหตุผลอัปเดต — เช็คแล้วว่า `audio_worker/.env` จริงบนเครื่องยังไม่มีไฟล์ (ยังไม่เคยสร้าง)
เลยไม่กระทบ live test ที่ผ่านมา verdict: **APPROVE พร้อมแก้ที่พบแล้ว**

**Live test รอบ 3 (verify การแก้ด้วยไฟล์เดิม `Parliament_1m.wav` ซ้ำอีกครั้ง หลัง restart worker)**:
✅ **ตรงกับที่คาดไว้ทุกจุด** — `transcript_segments` มี 6 entry เท่ากับรอบ 2 แต่:
- segment `28.82-29.36` (0.54s, เคยว่างเปล่า) **หายไปแล้ว** — กรองถูกจากผลจริง ไม่ใช่ทำนายผิดแบบ
  duration-heuristic เดิม
- segment `21.97-22.34` ("วันนี้", เคยถูกกรองทิ้งเพราะสั้นกว่า 0.5s ในรอบ duration-heuristic)
  **กลับมาแล้ว** เพราะตอนนี้กรองจากผลจริงหลัง transcribe ไม่ใช่ duration
- **ไม่มี entry ข้อความว่างเปล่าเหลืออยู่เลยทั้ง 6 entry** — วิธีใหม่ไม่มี false negative (ไม่เสียคำ
  จริง) และไม่มี false positive (ไม่มี entry ว่างหลุดผ่าน) เท่าที่เทสนี้แสดง — **ปิดประเด็นนี้ได้**

---

## 3.5 Session 2026-08-02 (ต่อ) — `/debug-mantra`: Speaker Mapping (backend เท่านั้น)

**Goal**: ทำงานถัดไปตามแผน (Speaker Mapping, บังคับก่อน Module 3) — แต่ mantra 1 (reproduce/เข้าใจ
ก่อนลงมือ) เจอว่า Module 6 (Front-End) ทั้งหมดยัง `[ ]` ไม่ได้เริ่มเลย ไม่มีโฟลเดอร์ frontend ของ
Com Sec เอง (มีแค่ `meetily/frontend` ที่เป็น repo อ้างอิง) — ถามผู้ใช้ผ่าน `AskUserQuestion` ก่อนว่า
จะเริ่มจากไหน ผู้ใช้เลือก **"Backend ก่อน"** (แยกจาก UI framework decision ที่ยังไม่ต้องตัดสินตอนนี้)

**สิ่งที่ทำเสร็จแล้ว**:
1. `backend/models.py` — เพิ่ม `Meeting.speaker_mapping_json` (Text, nullable) เก็บ JSON
   `{"SPEAKER_00": "ชื่อจริง", ...}` แบบเดียวกับ `transcript_segments_json` (MVP, ยังไม่ normalize)
2. `backend/main.py`:
   - `_extract_speaker_labels(transcript_segments)` — ดึง label ที่ต่างกันทั้งหมดจาก transcript
     จริง (ground truth จากข้อมูล ไม่ใช่เดา) เรียงตามลำดับที่ปรากฏครั้งแรก
   - `_meeting_to_dict()` เพิ่ม 3 field: `speaker_labels` (label ทั้งหมดที่ต้องจับคู่),
     `speaker_mapping` (ที่จับคู่ไว้แล้ว, อาจไม่ครบ), `speaker_mapping_complete` (bool — true ก็ต่อเมื่อ
     มี label อย่างน้อย 1 ตัวและทุกตัวจับคู่กับชื่อไม่ว่างเปล่าแล้ว)
   - `POST /api/meetings/{id}/speaker_mapping` — role `Com_Sec_Maker`/`Checker` (เหมือน
     `MEETING_MANAGE_ROLES` อื่น) รับ `{"mapping": {...}}` เขียนทับทั้ง dict เสมอ (ไม่ merge ทีละ
     key — ตรงไปตรงมากว่า) ปฏิเสธด้วย 400 ถ้ายังไม่มี transcript (`transcript_segments_json` เป็น
     null)
3. **แก้ edge case ที่พบระหว่างเขียน (mantra 2, trace fail path จริง ไม่ใช่แค่ทฤษฎี)**: สังเกตว่า
   flow "อัปโหลดไฟล์ใหม่ทับ meeting เดิม" ใช้งานได้จริงอยู่แล้ว (ทดสอบไปแล้วหลายรอบใน session ก่อน
   หน้า) — แต่ diarization clustering ID (`SPEAKER_00`/`01`) ไม่ stable ข้าม run ถ้าไม่ล้าง
   `speaker_mapping_json` ทิ้งตอนอัปโหลดใหม่ mapping เก่าจะผูกกับคนละคนแบบเงียบๆ (label ตรงกันแต่คน
   ไม่ตรง) — เพิ่มโค้ดล้างทิ้งใน `upload_meeting_audio` ให้แล้ว

**Verify**: `py_compile`/`pyflakes` ผ่านสะอาดทั้ง `models.py`/`main.py`

**ยังไม่ได้ทำ**:
- ⚠️ **ยังไม่มี UI เลย** (ตามที่ตัดสินใจ — Module 6 ยังไม่เริ่ม) endpoint นี้ทดสอบได้แค่ผ่าน
  curl/Postman เหมือน Module 2 ตอนที่ยังไม่มี frontend
- ไม่ validate ว่าชื่อที่จับคู่ตรงกับ `meeting.attendees` ที่กรอกไว้ล่วงหน้า — ตั้งใจปล่อยยืดหยุ่น
  (เผื่อมีคนพูดที่ไม่ได้อยู่ใน attendee list เช่นผู้บรรยายรับเชิญ) ไม่ใช่ bug ที่ลืมทำ
- ✅ **การล้าง `speaker_mapping_json` ตอนอัปโหลดไฟล์ใหม่ — verify แล้ว** (ดู "Edge case" ด้านล่าง)

**อัปเดต (2026-08-02 ต่อ — verify จริงบน Windows สำเร็จ)**: ลบ `com_sec.db` → สร้าง meeting ใหม่ →
อัปโหลด `Parliament_1m.wav` → รอ `transcribed` → เห็น `speaker_labels: ["SPEAKER_01","SPEAKER_00"]`
ถูกต้อง → `POST .../speaker_mapping` ส่ง `{"SPEAKER_01":"ท่านประธาน","SPEAKER_00":"สมาชิกสภา ก"}` →
`speaker_mapping_complete` เปลี่ยนจาก `false` → `true` ทันที และ persist อยู่หลัง `GET` ซ้ำ —
**flow หลักทำงานถูกต้องครบ**

**Edge case (re-upload ล้าง mapping) — verify แล้ว**: อัปโหลดไฟล์เดิมซ้ำเข้า meeting ที่มี mapping
ไว้แล้ว → `speaker_mapping` กลับเป็น `{}` ทันทีตั้งแต่ response ของ `/upload` เอง (ก่อน background
task ประมวลผลเสร็จด้วยซ้ำ) และยังว่างอยู่หลัง transcribe รอบใหม่เสร็จ — **ปิดประเด็นนี้ได้สมบูรณ์
ไม่มี mapping เก่าหลุดค้างข้าม diarization run**

**Key Files ของเซสชันนี้**: `backend/models.py`, `backend/main.py`, `task.md`

---

## 4. Next Steps (สิ่งที่ต้องทำต่อไป)

> ⚠️ **หัวข้อนี้เขียนไว้หลังเซสชัน 3.5 (ก่อน Module 6 frontend + transcript edit จะเสร็จ) —
> ล้าสมัยไปแล้ว คงไว้เป็น breadcrumb ประวัติเท่านั้น สถานะจริงล่าสุดอยู่ท้าย 3.8 ด้านล่าง**

**สถานะล่าสุด (2026-08-02, หลังจบ 3.8)**: Module 2 เสร็จสมบูรณ์ทั้งบังคับ+ไม่บังคับ (ASR redesign,
Speaker Mapping ทั้ง backend+frontend, transcript edit ทั้ง backend+frontend) — เหลือแค่รอผู้ใช้
verify transcript edit จริงในเบราว์เซอร์ (ยังไม่เคยทดสอบ) ก่อนถือว่าปิด Module 2 ได้แบบเต็มร้อย
Module 6 เชื่อมกับ backend จริงครบ 3 หน้าแล้ว (dashboard/create-meeting/meeting-detail) เหลือแค่ฟีเจอร์
Synced Audio/Video Player (ยังไม่เริ่ม) — **ขั้นต่อไปที่เสนอไว้คือเริ่ม Module 3 (Minutes Generation
ผ่าน Gemini)** ดู task.md สำหรับ checklist เต็มทุก module

---

## 3.6 Session 2026-08-02 (ต่อ) — เริ่ม Module 6 frontend แล้วหยุดกลางทาง (รอผลจาก Stitch)

**สิ่งที่เกิดขึ้น**: mantra 4 (cross-reference) เจอว่า "Stitch MCP" ที่ระบุใน `task.md` Module 6 **ไม่มี
อยู่จริง** ในระบบ (เช็ค MCP registry แล้วไม่มี connector ชื่อ Stitch เลย มีแค่ Figma ที่ยังไม่เชื่อมต่อ
กับ Canva ที่เชื่อมต่ออยู่แต่เป็นเครื่องมือกราฟิก/เอกสาร ไม่เหมาะกับ dashboard ที่ต้องเรียก API จริง) —
ถาม AskUserQuestion เรื่อง frontend stack ผู้ใช้เลือก **Plain HTML/CSS/JS** (ไม่ต้องมี Node.js/npm/
build step, ให้ FastAPI serve ตรงๆ) เริ่มอ่าน `EMPIRE CI(1).png` ดึงสี/โทนจริง (ไม่ได้เดา) แล้วเขียน
`frontend/style.css` เสร็จ 1 ไฟล์ — **ระหว่างนั้นผู้ใช้แจ้งว่ามี Google Stitch ติดตั้งอยู่ที่ Antigravity
(เครื่องมืออื่น) จะไปออกแบบเองแล้วส่งผลกลับมาให้ทีหลัง** — **หยุดงาน frontend ตรงนี้ทันที** ไม่เขียน
`index.html`/`app.js`/ต่อกับ backend ต่อ รอผู้ใช้ส่งผลออกแบบจาก Stitch กลับมาก่อน

**สีที่อ่านได้จาก `EMPIRE CI(1).png` (บันทึกไว้เผื่อใช้อ้างอิงตอน import ผลจาก Stitch)**:
- Gold-Light `#F3DE8F`, Global Gold (primary accent) `#D9B168`, Gold-Deep `#AA843D`
- Deep Empire Teal (core background) `#0F282A`, Teal-Mid `#1C3936`, Teal-Darker `#0A1416`
- Origin Cyan-Teal (brand connection) `#ACD8D9`, Cyan-Teal-Deep `#123B3A`
- Core White `#FFFFFF`
- Gradient: Gold `#F3DE8F→#D9B168→#AA843D`, Teal `#0A1416→#1C3936→#0F282A`, Cyan-Teal
  `#ACD8D9→#123B3A`
- แบรนด์: "ORIGIN GLOBAL EMPIRE" โลโก้ teal/gold gradient text — ไม่มีชื่อฟอนต์ระบุในภาพ
  `frontend/style.css` เลยเลือกใช้ system font stack แทน Google Fonts CDN โดยตั้งใจ (ไม่อยากมี
  network dependency ภายนอกสำหรับแอปที่จัดการข้อมูลบอร์ด/เอกสารลับ — ตรงกับแนวทาง PDPA ของระบบนี้)

**Key Files ของเซสชันนี้**: `frontend/style.css` (ใหม่, ยังไม่ได้ใช้งานจริงเพราะ `index.html` ยังไม่มี)

**How to resume**: รอผู้ใช้ส่งผลออกแบบจาก Stitch (Antigravity) กลับมาก่อน — น่าจะเป็น mockup/HTML/
screenshot ที่ต้องมาแปลงเป็น `frontend/index.html`+`app.js` จริง ต่อกับ endpoint ที่มีอยู่แล้ว
(`GET/POST /api/meetings`, `POST /api/meetings/{id}/upload`, `POST /api/meetings/{id}/speaker_mapping`)
ยังไม่ต้องตัดสินใจเรื่อง static file serving ใน `backend/main.py` จนกว่าจะรู้โครงสร้างไฟล์จริงจาก
Stitch ก่อน

---

## 3.7 Session 2026-08-02 (ต่อ) — `/debug-mantra`: ต่อผล Stitch เข้ากับ backend จริงครบ 3 หน้า

**Goal**: ผู้ใช้ส่งผลออกแบบจาก Stitch กลับมาที่ `D:\Com Sec\ComSecAI_Dashboard\` (4 ไฟล์:
`index.html`/`create-meeting.html`/`meeting-detail.html`/`style.css` — static mockup, สีตรงกับ
EMPIRE CI ที่ brief ไปเป๊ะ, ใช้ฟอนต์ Inter/Montserrat จาก Google Fonts CDN, ทุกอย่างยังเป็น
hardcoded demo data ไม่มี JS ต่อ backend เลย) — ต้องเขียน JS ต่อเข้ากับ endpoint จริงให้ครบ

**สิ่งที่ทำเสร็จแล้ว**:
1. **`ComSecAI_Dashboard/app.js` (ใหม่ทั้งไฟล์)** — ไฟล์เดียวใช้ร่วมกันทั้ง 3 หน้า (`initX()`
   แยกตาม DOM element ที่มีจริงในแต่ละหน้า): `apiFetch()` helper (แนบ Bearer token, auto JSON
   stringify/parse, throw `Error` พร้อมข้อความจาก backend's `detail`), role picker ผูกกับ
   `localStorage` (mock auth token 4 แบบ), `formatDate()`/`formatSeconds()`, dashboard
   table render+poll ทุก 5s, create-meeting form (dynamic add/remove participant/agenda row ผ่าน
   event delegation — แถวเริ่มต้นจาก Stitch mockup กับแถวที่เพิ่มทีหลังใช้ handler เดียวกัน),
   meeting-detail (อ่าน `?id=` จาก URL, render summary/speaker mapping/transcript, poll เฉพาะตอน
   `uploaded`/`processing` แล้วหยุดทันทีที่ `transcribed`/`failed` กันเขียนทับ input ที่ผู้ใช้กำลัง
   พิมพ์ในฟอร์ม Speaker Mapping อยู่), export transcript เป็น `.txt` ฝั่ง client (ไม่มี backend
   endpoint ใหม่ — Blob + object URL ล้วนๆ)
2. **แก้ 3 index.html/create-meeting.html/meeting-detail.html** — ลบ hardcoded demo data ออก,
   ใส่ id ให้ element ที่ `app.js` ต้องอ้างถึง, เพิ่ม `<script src="app.js">`, เพิ่ม role-select
   ในหัวหน้า `create-meeting.html`/`meeting-detail.html` ที่ Stitch ไม่ได้ใส่มาให้ (มีแค่ใน
   `index.html`)
3. **`backend/main.py`** — mount `ComSecAI_Dashboard/` เป็น static files ที่ path `/dashboard`
   (`StaticFiles(html=True)`) — same-origin กับ `/api/*` ทั้งหมดเลยไม่ต้องตั้ง CORS ใดๆ (คนละเรื่อง
   กับที่ task.md เดิมกลัวว่าต้องตั้ง CORS เพราะคิดว่า frontend จะรันคนละ dev server) — กัน
   backend crash ทั้งระบบถ้าโฟลเดอร์นี้หายด้วย (`if os.path.isdir(...)` ก่อน mount, log warning
   เฉยๆถ้าไม่เจอ แทนที่จะปล่อยให้ `StaticFiles()` raise ตอน import)
4. **ลบ `frontend/style.css`** ที่เคยเขียนไว้ก่อนผู้ใช้แจ้งเรื่อง Stitch (ดู 3.6) — ค้างเป็น draft
   ที่ไม่ได้ใช้แล้ว กัน frontend 2 โฟลเดอร์ปนกัน — ต้องขอสิทธิ์ลบผ่าน
   `mcp__cowork__allow_cowork_file_delete` ก่อน (bash `rm` ธรรมดาโดน permission block)

**บั๊กที่พบระหว่าง trace เองก่อนส่งให้ทดสอบ (mantra 2, ยังไม่ทันได้ผู้ใช้รายงาน)**:
- `renderMainContent()` เดิมไม่ซ่อน `#status-placeholder` ตอน transition จาก `processing` →
  `transcribed` ระหว่าง poll (ซ่อนแค่ตอน initial load เพราะมี `display:none` ใน HTML อยู่แล้ว) —
  ผลคือถ้าเปิดหน้า meeting-detail ค้างไว้ระหว่างรอผลประมวลผล จะเห็น placeholder เก่าซ้อนกับ
  panel ใหม่ — แก้แล้ว (ซ่อน placeholder ทุกครั้งที่ status เป็น transcribed ไม่ใช่แค่ initial)
- `triggerUpload()` เดิมเรียก `.click()` บน `<input type="file">` ที่ไม่เคย attach เข้า DOM —
  ใช้ได้บาง browser แต่ไม่ reliable ทุกตัว — แก้เป็น attach เข้า `document.body` (ซ่อนด้วย
  `display:none`) ก่อน click แล้วลบทิ้งหลังใช้เสร็จทุก path (สำเร็จ/error)

**Verify**: `node --check app.js` ผ่าน (syntax เท่านั้น ไม่มี runtime test จริงเพราะไม่มี browser
ในเซสชันนี้) — **ยังไม่เคยเปิดจริงในเบราว์เซอร์เลย** ต้องให้ผู้ใช้เปิด
`http://127.0.0.1:8000/dashboard/` ทดสอบเองก่อนถือว่าใช้งานได้จริง

**ยังไม่ได้ทำ**:
- ⚠️ **ยังไม่เคยรันจริงในเบราว์เซอร์** — เขียนจาก static analysis + trace มือล้วนๆ อาจมีบั๊กที่
  เห็นได้แค่ตอนคลิกจริง (เช่น CSS layout ผิดที่, event listener ชนกัน)
- Stitch ใส่ Google Fonts CDN (`fonts.googleapis.com`) มาด้วย — แอปนี้จัดการข้อมูลบอร์ด/เอกสารลับ
  ตามที่เคยตั้งข้อสังเกตไว้ตอนเขียน draft style.css เอง (ดู 3.6) แต่รอบนี้เป็นไฟล์ที่ผู้ใช้เลือก
  ออกแบบเองผ่าน Stitch โดยตรง **ไม่ได้ตัดออกให้เอง** เพราะเป็นการตัดสินใจของผู้ใช้ — แค่บันทึกไว้
  เป็นข้อสังเกตเผื่อต้องพิจารณาก่อนขึ้น production จริง (ต้องมี internet ให้เครื่องที่รัน backend
  ถึงจะโหลดฟอนต์ได้ ถ้าเน็ตล่มจะ fallback เป็น browser default font เฉยๆไม่ error)
- Speaker Mapping input ใช้ `<datalist>` (autocomplete) ตามที่ brief ขอไว้ แต่ Stitch mockup เดิม
  ไม่มี — เพิ่มเข้าไปเองตอน wire (ไม่กระทบ visual จนกว่าจะพิมพ์)
- หน้าจอแก้ไข transcript (ไม่บังคับ ตามแผนเดิม Module 2) — Stitch ไม่ได้ออกแบบมาให้ด้วย ทำเสร็จแล้ว
  ในเซสชันถัดมา ดู 3.8 ด้านล่าง

**Key Files ของเซสชันนี้**: `ComSecAI_Dashboard/app.js` (ใหม่), `ComSecAI_Dashboard/index.html`,
`ComSecAI_Dashboard/create-meeting.html`, `ComSecAI_Dashboard/meeting-detail.html`,
`ComSecAI_Dashboard/style.css` (เพิ่มแค่ `.text-muted` utility class), `backend/main.py`

**How to resume**: เปิด `http://127.0.0.1:8000/dashboard/` (restart backend ก่อนถ้ายังไม่เคย mount)
ทดสอบ flow เต็ม: สร้างประชุม → อัปโหลดไฟล์ → รอ poll เปลี่ยนเป็น transcribed อัตโนมัติ → จับคู่ผู้พูด
→ ดู transcript → export .txt — รายงานบั๊กที่เจอกลับมา (คาดว่าน่าจะมีเรื่อง CSS/layout เล็กๆน้อยๆ
เพราะยังไม่เคยเห็นจริงในเบราว์เซอร์)

**อัปเดต (2026-08-02 ต่อ — verify จริงในเบราว์เซอร์สำเร็จครั้งแรก)**: ผู้ใช้เปิด `/dashboard/` จริง
แล้วทดสอบ export transcript — ได้ไฟล์ `transcript_5566.txt` กลับมา ตรวจแล้วถูกต้องทุกจุด: format
`[MM:SS] ชื่อที่จับคู่: ข้อความ` ตรงตามที่ `exportTranscriptText()` ออกแบบไว้, timestamp ตรงกับข้อมูล
จริงที่เคย verify ผ่าน curl มาก่อนหน้า (00:00/00:02/00:17/00:22 ตรงกับ `Parliament_1m.wav` เป๊ะ),
ชื่อผู้พูดที่จับคู่ไว้ ("ชาวบ้าน1"/"ชาวบ้าน2") แสดงถูกต้อง — **ยืนยันว่า flow เต็มทำงานจริงใน
เบราว์เซอร์แล้ว**: สร้างประชุม → อัปโหลด → poll จน transcribed → จับคู่ผู้พูด (input+datalist ใช้ได้
จริง) → export .txt สำเร็จ — ยังไม่มีรายงานบั๊ก UI/layout ใดๆกลับมา

**เรื่อง GPU Lock/torch install ปิดจบแล้ว** (ดู 3.2 ด้านบน + `task.md` Module 0): global Python
ยืนยันแล้วว่ามี torch 2.8.0+cu126 ใช้งานได้จริง (verify ผ่านการรัน `diagnose_vram_module2.py`
สำเร็จ), RAG worker resident เสมอ, Diarization↔ASR ใช้ lock ในโปรเซสเดียวกับ backend ตามแผนเดิม
ไม่ต้องออกแบบอะไรเพิ่มอีกแล้ว

**งานถัดไปหลัง ASR redesign เสร็จ**: Speaker Mapping UI (บังคับ) → transcript edit UI (ไม่บังคับ)
→ เริ่ม Module 3 (Minutes Generation ผ่าน Gemini) ซึ่งรอ `transcript_segments` ที่ merge เสร็จแล้ว
เป็น input

**งานที่เป็น execution ล้วนๆ ไม่ต้องตัดสินใจอะไรเพิ่ม (ทำได้เลย):**
- ตัดสินใจเรื่องชื่อบริษัทเก่าตกค้าง 65 ไฟล์ (เช็คแล้วในหัวข้อ 3.1 — รอผู้ใช้ตัดสินใจว่าจะแก้/ปล่อยไว้)
- ออกแบบ UX คิว/สถานะสำหรับ user ที่อัปโหลดพร้อมกัน
- นโยบายเก็บรักษาไฟล์เสียง/วิดีโอต้นฉบับ (retention/encryption/access) — พบจาก `/scrutinize`
  ก่อนหน้านี้ ยังไม่ตัดสินใจ ต้องทำก่อนเริ่มเก็บไฟล์เสียงจริงใน Module 2

**ทางเลือกที่ต้องตัดสินใจร่วมกับผู้ใช้**: Azure AD จริง (ต้องมี tenant ID/client ID) — ตอนนี้ยังเป็น
mock auth ทั้งหมด

ดู `task.md` สำหรับรายละเอียด checklist แบบเต็มของทุก module

---

## 3.8 Session 2026-08-02 (ต่อ) — หน้าจอแก้ไข Transcript (ไม่บังคับ, Module 2)

**Goal**: เพิ่มความสามารถแก้ไขข้อความ transcript ต่อ segment ได้ (แก้คำผิดจาก ASR) — ตามแผนเดิม
Module 2 ที่ระบุว่า "ไม่บังคับ" แต่ Stitch ไม่ได้ออกแบบ UI ให้ไว้ ต้องเพิ่มเองทั้งหมด

**Backend** (`backend/main.py`): เพิ่ม `TranscriptSegmentIn`/`TranscriptSegmentsBody` (Pydantic) +
`PUT /api/meetings/{meeting_id}/transcript_segments` — validate ว่า meeting มีอยู่จริงและมี
`transcript_segments_json` อยู่แล้ว (ห้ามแก้ก่อนมี transcript) แล้วเขียนทับทั้ง array ด้วย
`json.dumps([seg.model_dump() for seg in body.transcript_segments])` — ใช้ pattern เดียวกับ
speaker_mapping คือ **เขียนทับทั้งก้อนเสมอ ไม่ patch บางส่วน** (ตรงกับ MVP JSON-blob convention ทั้ง
โปรเจกต์)

**Frontend** (`ComSecAI_Dashboard/`):
- `meeting-detail.html`: เพิ่มปุ่ม `#edit-transcript-btn` ใน panel header ของ Transcript (เปลี่ยน
  class `panel-header` → `panel-header flex-between` เพื่อจัดปุ่มชิดขวา)
- `style.css`: เพิ่ม `textarea` เข้า selector styling ร่วมกับ `input[type=text/date]` เดิม + คลาสใหม่
  `.transcript-edit-row`/`.edit-meta`/`.edit-meta .speaker-name` (ไม่มีใน mockup เดิมจาก Stitch
  เพิ่มเองให้เข้าธีมเดียวกัน ใช้ตัวแปร `:root` ของ Stitch เอง เช่น `--secondary-cyan-deep`,
  `--status-failed`)
- `app.js`: เพิ่ม `speakerDisplayName()` (ดึง logic แสดงชื่อผู้พูดออกมาจาก `renderTranscript()` เดิม
  ให้ใช้ร่วมกับฟังก์ชันใหม่ได้), `renderTranscriptEditable(meeting, container)` (render แต่ละ
  segment เป็น meta line (อ่านอย่างเดียว) + `<textarea>` ที่ prefill ด้วย `seg.text`, ปุ่ม Save/
  Cancel ท้ายสุด), `exitTranscriptEditMode()` (กลับไป `renderTranscript()` ปกติ + คืนปุ่ม Edit ให้
  แสดง) — คลิก Save แล้วส่ง `PUT .../transcript_segments` ทีเดียวทั้ง array (ไม่ใช่ทีละ segment)
  โดย **คง `start`/`end`/`speaker` ของแต่ละ segment ไว้เดิมทุกประการ แก้แค่ `text`** จับคู่ด้วย
  `data-index` บน `<textarea>` ที่ตรงกับ index เดิมใน array (ไม่ใช่เรียงใหม่ระหว่างแก้ไข) — ปุ่ม
  Cancel แค่ re-render จาก `meeting` เดิมในหน่วยความจำ ไม่ยิง API เลย. Event listener ของปุ่ม
  `#edit-transcript-btn` อยู่ใน `initMeetingDetailPage()` เช็คก่อนว่ามี `transcript_segments` จริง
  ถึงจะเปิดโหมดแก้ไขได้ (กันกดตอนยังไม่มี transcript)
- polling ของหน้า detail หยุดเองแล้วตั้งแต่ status เปลี่ยนเป็น `transcribed` (ดู 3.7) จึงไม่มีความเสี่ยง
  ที่ poll จะเขียนทับฟอร์มที่กำลังแก้ไขอยู่ — ไม่ต้องเพิ่ม guard อะไรเพิ่ม

**Verify**: `node --check app.js` ผ่าน, `py_compile`+`pyflakes` บน `backend/main.py` ผ่าน — **ยังไม่ได้
ทดสอบจริงในเบราว์เซอร์** (เหมือนงาน frontend ก่อนหน้านี้ทั้งหมดในเซสชันนี้ sandbox ไม่มีเบราว์เซอร์จริงให้
รัน) — ผู้ใช้ต้องเปิด `/dashboard/` เข้าหน้า meeting ที่ transcribed แล้วกด "Edit" ทดสอบ: แก้ข้อความ →
Save → เช็คว่า transcript อัปเดตถูกต้องและ `start`/`end`/`speaker` ไม่เปลี่ยน, ลอง Cancel ด้วยว่าคืนค่า
เดิมถูกต้อง

**Key Files ของเซสชันนี้**: `backend/main.py`, `ComSecAI_Dashboard/meeting-detail.html`,
`ComSecAI_Dashboard/style.css`, `ComSecAI_Dashboard/app.js`

**How to resume**: รอผลทดสอบจริงจากผู้ใช้ก่อน ถ้าผ่านครบ Module 2 จะถือว่าสมบูรณ์ทั้งหมด (บังคับ+ไม่บังคับ)
ขั้นต่อไปที่เสนอไว้คือเริ่ม Module 3 (Minutes Generation ผ่าน Gemini) ซึ่งรอ `transcript_segments`
เป็น input โดยตรง

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
- `/scrutinize`: หากมีการปรับเปลี่ยนสถาปัตยกรรมใหญ่ๆ ให้ใช้สกิลนี้ตรวจสอบช่องโหว่อีกครั้ง (เพราะระบบนี้เน้น Compliance หนักมาก) — ใช้ไปแล้วหลายรอบตลอดโปรเจกต์ พบ finding จริงทุกครั้ง: (1) Module 1 mock ทั้งหมด + ความเสี่ยง Windows WINHTTP.dll crash จากการรวมโปรเซส (2026-08-01), (2) CRITICAL GPU cleanup bug ใน `pipeline.py` — `del` ผิดสโคปทำให้ VRAM ไม่ถูกปล่อยจริง (ดู task.md Module 2 "GPU Lock"), (3) `.env.example` ค้างค่า `ASR_MIN_SEGMENT_SECONDS=0.5` เก่าหลังเปลี่ยนมาใช้ post-hoc filtering (session 3.4), (4) `WorkerBusyError`+path traversal guard ที่ยังไม่มี (audio_worker เปิดเป็น HTTP service ไม่มี auth — ดู task.md Module 2 รายการ scrutinize findings)
- `/grill-me`: หากทีมพัฒนาต้องการทดสอบไอเดีย หรือเช็กความพร้อมก่อนเขียนโค้ด — ใช้ไปแล้ว 3 รอบ ครอบคลุมทุกมิติของ Module 1-6 แล้ว
- `qwenchance`: เมื่อเริ่มเขียนโค้ดระบบ Audio Processing หรือ RAG ที่ลอจิกยาวและซับซ้อน ป้องกัน AI ติดลูป
