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
> ล้าสมัยไปแล้ว คงไว้เป็น breadcrumb ประวัติเท่านั้น สถานะจริงล่าสุดอยู่ที่ session 3.17 (ท้ายไฟล์นี้
> ก่อนหัวข้อ "5. Suggested Skills")**

**อัปเดตล่าสุด (2026-08-04, หลังจบ 3.14)**: ตัดสินใจทิศทางสถาปัตยกรรมสุดท้ายแล้วผ่าน `/grill-me`
(ดู 3.14 เต็ม + `task.md`) — **แทนที่ `audio_worker` (pyannote+typhoon-asr) ทั้งชุดด้วย Gemini native
audio** (`gemini-3.6-flash` primary, `gemini-3.5-flash` fallback), ย้าย call เข้า `backend/` โดยตรง,
ลบ `audio_worker/` ทั้งโฟลเดอร์เมื่อถึงเวลาตัดจริง — **แต่ยังไม่ตัดขาดจริง**: (a) ยังไม่ได้เขียนโค้ด
adapter/wiring จริงเข้า `main.py` (schema `start_seconds`→`start` ฯลฯ), (b) ทดสอบจริงมีแค่ไฟล์ประชุม
เดียว ต้องทดสอบเพิ่มอย่างน้อย 1-2 ไฟล์ประชุมอื่นก่อนลบ `audio_worker/` จริง — `tune_diarization.py`
(3.12, pyannote joint-tuning) **เลิกทำแล้ว** ตามผลตัดสินใจนี้ ไม่ต้องรอ ground-truth CSV จากผู้ใช้อีก

**สถานะล่าสุด (2026-08-03, หลังจบ 3.11)**: Module 2/3 ยังรอผู้ใช้ live test จริงบนเครื่อง Windows
เหมือนเดิม (ไม่มีอะไรเปลี่ยนจากที่เขียนไว้ตอนจบ 3.9) — **Module 4 & 5 (Word Template Mapping &
Secure Delivery) เขียนโค้ดจบครบ backend+frontend รอบแรกแล้วระหว่างรอไฟล์เสียงจริงมาเทส Module 3**
(ดู 3.10) ครอบคลุมทุก item ใน task.md ยกเว้น RBAC ของ transcript-sync player (ผูกกับ Module 6 ที่ยัง
ไม่เริ่ม) + **เพิ่ม Multi-template ทันทีต่อกัน** (ดู 3.11 — เลือก template ตอนสร้างประชุมได้จาก
dropdown, เพิ่ม template ใหม่ทีหลังได้โดยไม่ต้องแก้โค้ด) — **verify ด้วย end-to-end test จริงผ่าน
FastAPI TestClient สำเร็จทุกจุดทั้ง 2 เซสชัน** (mock แค่ 2 จุดที่ sandbox ทำไม่ได้จริง: Word COM
automation/SMTP) — **ขั้นต่อไปคือรอผู้ใช้ live test บนเครื่อง Windows จริง**: (1) Module 3 ต้องมีไฟล์
เสียงประชุมจริง+ทดสอบปุ่ม Generate Minutes ก่อน (ค้างมาจาก 3.9), (2) Module 4-5 ต้อง live test เต็ม
flow (generate docx → แก้ Word → upload final → Checker approve → เช็คว่า Word COM automation แปลง
PDF ได้จริง + ตั้งค่า SMTP จริงแล้วอีเมลส่งถึงจริง) ดู task.md สำหรับ checklist เต็มทุก module

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

## 3.9 Session 2026-08-03 — `/debug-mantra`: Module 3 (Minutes Generation) เขียนโค้ดจบรอบแรก

**Goal**: ทำตาม "ขั้นต่อไป" ของ handoff ฉบับก่อน — เริ่ม Module 3 (Minutes Generation ผ่าน Gemini)

**Mantra 1 ก่อนเขียนโค้ด**: อ่าน `task.md`/`implementation_plan.md` Module 3 ก่อน พบว่าต้อง "คุยร่วมกับ
Module 4 เรื่อง mapping ไปยัง Word template" — เปิดไฟล์ template จริง
`260628 Draft_EMPIRE - BOD Minutes 15-2569 v.5.docx` ด้วย python-docx (พบว่าเป็นรายงานการประชุมจริง
ที่เขียนเสร็จแล้ว ไม่ใช่ template ที่มี placeholder — มีตารางย่อยรายละเอียดธุรกรรม/ตัวเลข/สัดส่วนหุ้น
ซับซ้อนมาก) — ถาม `AskUserQuestion` 2 ข้อก่อนเขียนโค้ดจริง:
1. Schema ของ Minutes ควรครอบคลุมแค่ไหน (เสี่ยง AI หลอนตัวเลขถ้าพยายาม map ตารางธุรกรรมตรงๆ) — ผู้ใช้
   เลือก **แบบยืดหยุ่น (Recommended)**: ต่อวาระมีแค่ discussion_summary/resolution_status/
   resolution_text เป็น free text (ดูเหตุผลเต็มที่ `minutes_schema.py` หัวไฟล์)
2. ทำแค่ backend หรือ backend+frontend รอบนี้เลย — ผู้ใช้เลือก **ทำทั้งคู่**

**Mantra 4 (cross-reference) ก่อนเขียนโค้ดจริง**: เปิด `rag_worker/llm_fallback.py` ดูของจริงว่า
"reuse `run_with_fallback()`" ตามที่ task.md เขียนไว้ทำได้จริงไหม — พบว่า `build_llm()`/
`complete_with_fallback()` ผูกกับ `llama-index-llms-google-genai` wrapper ที่ `.complete()` ไม่รองรับ
`response_schema` ตรงๆ แต่ `run_with_fallback()` เองรับ `factory`/`call` เป็น callable ทั่วไป (ไม่ผูก
llama_index) — เขียน factory/call ใหม่เรียก raw `google-genai` `Client.models.generate_content()`
แทน ยังใช้ `run_with_fallback()` เดิมได้ตรงตามแผน — ยืนยันจากซอร์สจริงของ package (`pip install
google-genai` ใน sandbox แล้วเช็ค `GenerateContentConfig.response_schema`/
`GenerateContentResponse.parsed` ด้วย `inspect`) ว่า `response.parsed` คืน Pydantic instance ให้ตรงๆ
ถ้าส่ง `response_schema=PydanticModelClass` — ไม่ใช่การเดา

**พบบั๊กจริงจาก mantra 4 อีกจุด**: `backend/requirements.txt` มี `python-dotenv` มาตั้งแต่ Module 1
แต่ grep ทั้ง backend ไม่เจอจุดไหนเรียก `load_dotenv()` เลย — `backend/.env` (มีอยู่จริงตั้งแต่
2026-08-01) ไม่เคยถูกโหลดเข้า `os.environ` จริง (ไม่กระทบอะไรมาก่อนหน้านี้เพราะยังไม่มีโค้ดอ่าน env
var จาก `.env` — Azure AD/auth.py ยัง mock อยู่) — แก้ด้วยการเพิ่ม `backend/config.py` ใหม่ทั้งไฟล์
(เรียก `load_dotenv()` รวมศูนย์ที่เดียว, pattern เดียวกับ `rag_worker/worker_config.py`)

**สิ่งที่ทำเสร็จแล้ว (เขียนโค้ดจริงครบ backend+frontend)**:
1. **`backend/llm_fallback.py`** (ใหม่) — copy จาก `rag_worker/llm_fallback.py` ตรงๆ ไม่แก้แม้แต่
   บรรทัดเดียว (verify ด้วย `diff` ว่า byte-identical) — reuse แค่ `run_with_fallback()`
   (`build_llm`/`complete_with_fallback` เป็น llama_index-specific ไม่ได้ใช้ที่นี่ แต่เก็บไว้ทั้งไฟล์
   ตาม convention เดียวกับที่ rag_worker copy จาก Local RAG)
2. **`backend/config.py`** (ใหม่) — โหลด `.env` รวมศูนย์ (แก้บั๊กที่พบข้างบน) + `COMPANY_NAME`/
   `GOOGLE_API_KEY`/`GEMINI_MODEL_MINUTES`/`GEMINI_MODEL_MINUTES_FALLBACK`/`GEMINI_MINUTES_TIMEOUT_MS`
3. **`backend/minutes_schema.py`** (ใหม่) — `AgendaItemMinutes`/`MinutesGenerationResult` (ส่งเป็น
   `response_schema` ให้ Gemini) + `MinutesOfMeeting` (โครงสร้างเต็มที่เก็บจริงใน DB หลัง merge)
4. **`backend/minutes_prompts.py`** (ใหม่) — system prompt เน้นกฎห้ามหลอนตัวเลข/ห้ามเพิ่มวาระใหม่/
   ห้ามแต่งเนื้อหาเกินกว่า transcript, แปลง transcript+speaker_mapping เป็นข้อความ `[MM:SS] ชื่อ: ...`
5. **`backend/minutes_generation.py`** (ใหม่) — `generate_minutes()`: เรียก Gemini ผ่าน
   `run_with_fallback()` (factory คืน model string เฉยๆ เพราะ raw genai Client ไม่ต้อง bind model
   ตอนสร้าง), validate จำนวน/ลำดับ agenda_items ที่ตอบกลับตรงกับที่ส่งไปเป๊ะ (raise
   `MinutesGenerationError` ถ้าไม่ตรง กันข้อมูลผิดวาระหลุดเข้า DB แบบเงียบๆ), merge กับ field ที่เป็น
   ground truth จาก DB (company_name/meeting_number/meeting_date/attendees/agenda description จริง —
   ไม่ใช้ที่ Gemini อาจ paraphrase มา) — **สถาปัตยกรรม**: เรียก Gemini ตรงจากโปรเซส backend เอง ไม่
   สร้างโปรเซสที่ 3 (ต่างจาก rag_worker/audio_worker) เพราะ `google-genai` ไม่มี native library
   (torch/faiss) ที่จะชน Windows WINHTTP.dll — เหตุผลเดิมที่ต้องแยกโปรเซสไม่เกี่ยวข้องกับที่นี่เลย
6. **`backend/models.py`** — เพิ่ม `Meeting.minutes_json`/`minutes_generated_at` (แยกจาก `status`/
   Approval workflow ของ Module 4-5 ตามที่ docstring เดิมเตือนไว้)
7. **`backend/main.py`** — เพิ่ม `POST /api/meetings/{id}/generate_minutes` (role Maker/Checker/
   Global_Admin) บังคับ Speaker Mapping ครบ 100% ก่อนเสมอ (ตัดสินใจ `/grill-me` รอบ 3 ที่ค้างไว้) —
   แยก helper `_is_speaker_mapping_complete()` ออกจาก `_meeting_to_dict()` ใช้ร่วมกัน 2 จุด กันตรรกะ
   diverge — `_meeting_to_dict()` เพิ่ม field `minutes`/`minutes_generated_at`
8. **`backend/requirements.txt`/`.env.example`** — เพิ่ม `google-genai` + `GEMINI_MODEL_MINUTES*`/
   `GEMINI_MINUTES_TIMEOUT_MS`, บันทึกบั๊ก dotenv ที่พบไว้ทั้งสองไฟล์
9. **Frontend** (`ComSecAI_Dashboard/`) — Minutes Panel ใหม่ใน `meeting-detail.html` (ปุ่ม
   `#generate-minutes-btn` disable ถ้า speaker mapping ยังไม่ครบ), `app.js`:
   `renderMinutesPanel()` (แสดงต่อวาระ: คำอธิบาย+สรุปอภิปราย+badge สถานะมติ+ข้อความมติ, ประธานในที่
   ประชุม, เรื่องอื่นๆ, timestamp+ชื่อโมเดลที่สร้าง, คำเตือน "ต้องตรวจสอบก่อนใช้จริง"), click handler
   เรียก endpoint ใหม่ (ปุ่มโชว์ "กำลังสร้าง... อาจใช้เวลาสักครู่" ระหว่างรอ กันกดซ้ำ), `style.css`
   เพิ่ม `.minutes-agenda-item` เข้าธีมเดิม

**Verify ที่ทำแล้ว**: `py_compile`/`pyflakes` สะอาดทุกไฟล์ที่แก้/สร้างใหม่ (ยกเว้น finding เดิมที่รู้อยู่
แล้วไม่ใช่บั๊กใน `auth.py`/`db.py` — เหมือนเดิมทุกเซสชันก่อนหน้า), `node --check app.js` ผ่าน, HTML
parse ผ่าน — **เพิ่มเติมจากที่เคยทำใน session อื่น**: เขียน mock unit test ชั่วคราวใน sandbox (mock
`google.genai.Client` ทั้งก้อน ไม่ต้องมี API key จริง/เครือข่ายจริง) ยืนยัน 5 เคสด้วยการรันจริง (mantra
3 falsify ไม่ใช่แค่ทฤษฎี): happy path (primary model สำเร็จ), fallback ไปโมเดลสำรองสำเร็จ, ปฏิเสธ
ผลลัพธ์ถูกต้องถ้าจำนวนวาระที่ Gemini ตอบไม่ตรงกับที่ส่งไป, error message ชัดเจนถ้าไม่มี
`GOOGLE_API_KEY`, error message ชัดเจนถ้าการประชุมไม่มีวาระเลย — ทั้ง 5 เคสผ่านตามที่ออกแบบไว้

**ยังไม่ได้ทำ / ทำไม่ได้ในเซสชันนี้ (ต้องทำต่อ)**:
- ⚠️ **ยังไม่เคยเรียก Gemini จริงเลยสักครั้ง** (sandbox ไม่มี `GOOGLE_API_KEY` จริง/ไม่มีเครือข่ายไปยัง
  Google) — ยังไม่ทราบ latency จริง (ตั้ง `GEMINI_MINUTES_TIMEOUT_MS` เท่ากับ rag_worker's ค่าเดิม 5
  นาทีไปก่อน เผื่อเจอบั๊ก latency ผิดปกติแบบเดียวกับที่ Module 1 เคยเจอตอนแรก), ยังไม่ทราบว่า Gemini
  จะตอบตรง schema/จำนวนวาระถูกต้องกับ transcript ภาษาไทยจริงหรือไม่ (mock test ยืนยันแค่ logic การ
  merge/validate ของโค้ดเราเอง ไม่ได้ยืนยันคุณภาพผลลัพธ์จาก Gemini จริง)
- ⚠️ **ยังไม่เคยกดปุ่ม Generate Minutes ในเบราว์เซอร์จริงเลย** (เหมือนงาน frontend ทุกเซสชันก่อนหน้า
  — sandbox ไม่มีเบราว์เซอร์ให้ทดสอบ) — ผู้ใช้ต้องเปิด `/dashboard/` เข้า meeting ที่ transcribed +
  speaker mapping ครบแล้ว กด Generate Minutes ทดสอบเอง (restart backend ก่อนถ้ายังไม่เคย — DB schema
  เปลี่ยน (`minutes_json`/`minutes_generated_at` เพิ่มใหม่) SQLAlchemy's `create_all()` **ALTER
  ตารางเดิมไม่ได้** — ⚠️ **ต้องลบ `D:\Com Sec\backend\com_sec.db` ก่อน restart รอบหน้าเหมือนทุกครั้งที่
  schema เปลี่ยน** ไม่มี Alembic migration (MVP/test data ล้วนๆ ลบทิ้งได้ปลอดภัย))
- versioning/ประวัติการสร้าง Minutes ซ้ำ (สร้างซ้ำแล้วเขียนทับของเก่าหายไปเลยตอนนี้ — พอสำหรับ MVP
  ตามที่ตัดสินใจไว้ ไม่ใช่ bug ที่ลืมทำ)
- การแมปไปยัง Word template จริง (ตาราง/ตัวเลขธุรกรรมละเอียด) เป็นขอบเขตของ Module 4 ที่ยังไม่เริ่ม —
  Minutes ที่สร้างได้ตอนนี้เป็น JSON เก็บใน DB เท่านั้น ยังไม่มีการ generate เอกสาร .docx จริง

**Key Files ของเซสชันนี้**: `backend/llm_fallback.py` (ใหม่, copy), `backend/config.py` (ใหม่),
`backend/minutes_schema.py` (ใหม่), `backend/minutes_prompts.py` (ใหม่),
`backend/minutes_generation.py` (ใหม่), `backend/models.py`, `backend/main.py`,
`backend/requirements.txt`, `backend/.env.example`, `ComSecAI_Dashboard/meeting-detail.html`,
`ComSecAI_Dashboard/app.js`, `ComSecAI_Dashboard/style.css`, `task.md`

**How to resume**: ลบ `com_sec.db` → รัน backend (ต้องมี `GOOGLE_API_KEY` paid tier จริงใน
`backend/.env` — เพิ่งจะมีผลจริงเป็นครั้งแรกเพราะบั๊ก dotenv ที่แก้ไปแล้ว) → เปิด `/dashboard/` เข้า
meeting ที่ transcribed แล้ว → จับคู่ผู้พูดให้ครบ (ถ้ายังไม่ครบ) → กด "Generate Minutes" → รายงานผล/
บั๊กที่เจอกลับมา (โดยเฉพาะคุณภาพเนื้อหาที่ Gemini สรุปมา เทียบกับ transcript จริง และเวลาที่ใช้จริง)
— ถ้าผ่าน ขั้นต่อไปคือเริ่ม Module 4 (วิเคราะห์ไฟล์เทมเพลต `.docx` จริง + เขียนสคริปต์ `python-docx`
แมปตัวแปร JSON ลงเอกสาร)

---

## 3.10 Session 2026-08-03 (ต่อ) — `/debug-mantra`: Module 4 & 5 (Word Template Mapping & Secure Delivery) เขียนโค้ดจบรอบแรก

**Goal**: ผู้ใช้ขอให้เริ่ม Module 4 & 5 ระหว่างรอไฟล์เสียงประชุมจริงมาทดสอบ Module 3 (ไฟล์
`Parliament_1m.wav` ที่ใช้เทส Module 2 เป็นเสียงรัฐสภา ไม่ใช่เนื้อหาประชุมบอร์ดจริงที่เหมาะทดสอบ
Minutes Generation) — สั่งให้เริ่มด้วย `/debug-mantra` และถามก่อนถ้าไม่แน่ใจ

**Mantra 1 ก่อนเขียนโค้ด**: อ่าน handoff.md/task.md/implementation_plan.md ทั้งหมด + เปิดไฟล์ template
จริง `260628 Draft_EMPIRE - BOD Minutes 15-2569 v.5.docx` ด้วย python-docx ซ้ำอีกรอบ (ยืนยันสิ่งที่
Module 3 เคยพบแล้ว: ไม่มี placeholder เลย มีตาราง 3 ตารางที่เป็นรายละเอียดธุรกรรม) + อ่านโค้ดที่มีอยู่
จริง (`backend/models.py`/`main.py`/`auth.py`/`config.py`) พบว่า auth ทั้งระบบยัง mock 4 token คงที่
ไม่มีตาราง user/email จริงเลยสักตาราง — เจอจุดที่ต้องตัดสินใจสำคัญ 4 จุดที่ handoff/task.md เดิมไม่ได้
ระบุไว้ชัด ถาม `AskUserQuestion` ก่อนเขียนโค้ดจริง (ทั้งหมดเลือกตัวเลือก Recommended):
1. **วิธีสร้างเอกสาร**: ไฟล์จริงไม่มี placeholder ไม่ generic พอจะใช้ตรงๆ → **สร้าง template ใหม่ด้วย
   `docxtpl`** เลียนแบบ layout/ฟอนต์จากไฟล์จริง
2. **ตาราง/ตัวเลขธุรกรรมที่ Module 3 ไม่สร้างให้ (กันหลอน)**: → **ให้ Maker ดาวน์โหลดร่าง .docx → แก้/
   เพิ่มด้วย Microsoft Word เอง → อัปโหลดกลับเป็นฉบับสมบูรณ์** (ไม่สร้าง table editor ในระบบ)
3. **เครื่องมือแปลง .docx→PDF**: ถามผู้ใช้ว่าเครื่อง Windows มีอะไรติดตั้งอยู่ → **มี Microsoft Word** →
   ใช้ `docx2pdf` (COM automation)
4. **ที่มาอีเมล Board_Member สำหรับ Magic Link**: ไม่มีตาราง user/email จริง, Azure AD ยังไม่เชื่อม →
   **เพิ่ม `MeetingAttendee.email` ให้ Maker กรอกเองต่อการประชุม**

**สิ่งที่ทำเสร็จแล้ว (เขียนโค้ดจริงครบ backend+frontend, verify ด้วย unit test จริงในเซสชันนี้)**:

1. **`backend/models.py`**: เพิ่ม `MeetingAttendee.email` (nullable), `Meeting.approval_status`
   (`Draft`/`Pending_Review`/`Needs_Revision`/`Approved`, คนละ field จาก `status`/`minutes_json` โดย
   ตั้งใจ — ดู docstring หัวไฟล์), `minutes_docx_path`/`final_docx_path`/`final_pdf_path`/
   `final_pdf_password` (plaintext ใน DB — ยอมรับความเสี่ยงนี้ใน MVP เพราะต้องส่งรหัสจริงกลับทางอีเมล),
   ตารางใหม่ `MeetingApprovalLog` (append-only audit trail) และ `MagicLinkToken`
   (256-bit random token, `expires_at`/`used_at` แยกกัน)
2. **`backend/build_minutes_template.py`** (ใหม่) — สคริปต์สร้าง `templates/minutes_template.docx`
   ด้วย python-docx (รันครั้งเดียว, commit ไฟล์ผลลัพธ์ไว้ แก้ layout ทีหลังต้องแก้สคริปต์นี้แล้วรันใหม่)
   ดึงค่า font/margin จริงจากไฟล์ต้นฉบับ (TH SarabunPSK 15pt, A4, margin 1"/0.886") — **ตั้งใจไม่ใส่สี
   EMPIRE CI** (เอกสารกฎหมาย/compliance ควรคงเป็นขาว-ดำเหมือนต้นฉบับ ต่างจาก dashboard ที่บังคับ CI)
3. **`backend/docx_generation.py`** (ใหม่) — `render_minutes_docx()`: แปลง `minutes_json` เป็น context
   ของ `docxtpl`, แปลงวันที่ ISO เป็นข้อความไทย พ.ศ. เอง (`thai_date()`, ไม่พึ่ง locale ระบบ), แปล
   `resolution_status` enum เป็น label ไทย (มี `assert` กันลืมแก้ถ้าเพิ่ม status ใหม่)
4. **`backend/pdf_generation.py`** (ใหม่) — `convert_docx_to_pdf()` (`docx2pdf`, lazy import กัน
   sandbox/Linux import พังเพราะไม่มี `pywin32`), `protect_pdf()` (`pypdf`, pure Python)
5. **`backend/magic_link.py`**/**`backend/email_service.py`** (ใหม่) — token สร้าง/verify (single-use,
   mark ใช้แล้วทันทีตอน verify กัน race condition), ส่งอีเมลผ่าน `smtplib` (ไม่ใช่ Graph API — Azure AD
   ยังไม่เชื่อม)
6. **`backend/archive.py`** (ใหม่) — copy ไฟล์ไป `ARCHIVE_DOCUMENTS_DESTINATION`/
   `ARCHIVE_RECORDINGS_DESTINATION` ตามที่ `/grill-me` รอบ 2 ตัดสินใจไว้ — ค่าว่าง/copy ไม่สำเร็จ = log
   warning เฉยๆ ไม่ทำให้ approve ล้มเหลว (execution-only decision ของเซสชันนี้ ไม่ได้คุยกับผู้ใช้แยก)
7. **`backend/config.py`/`.env.example`/`requirements.txt`** — เพิ่ม `COMPANY_ADDRESS`/`SMTP_*`/
   `MAGIC_LINK_*`/`ARCHIVE_*_DESTINATION` + `docxtpl`/`pypdf`/`docx2pdf` (marker
   `sys_platform == "win32"` กัน pip ติดตั้งบน Linux)
8. **`backend/main.py`** — endpoint ใหม่ครบ: `POST .../generate_docx`, `GET .../download_docx?variant=`,
   `POST .../upload_final_docx`, `POST .../review` (เฉพาะ `Com_Sec_Checker`), `GET .../approval_log`,
   `GET /api/magic_link/{token}` (public, ไม่ผ่าน auth ปกติ) — `_archive_and_notify_background()` รัน
   เป็น FastAPI BackgroundTask หลัง approve (แปลง PDF→ใส่รหัสผ่าน→สร้าง token→ส่งอีเมล→archive แต่ละ
   ขั้นแยก try/except ไม่ให้ล้มพร้อมกันหมด, บันทึก error ลง `MeetingApprovalLog` แทนหายเงียบๆ)
9. **Frontend** (`ComSecAI_Dashboard/`) — Documents & Approval panel ใหม่ใน `meeting-detail.html`
   (ปุ่ม generate/download draft-final, upload final input, Checker approve/reject+comment, ปุ่มดู
   approval log), `create-meeting.html` เพิ่มช่อง email ต่อผู้เข้าร่วม, `app.js`:
   `renderDocumentsPanel()`/`downloadAuthenticatedFile()` (fetch+Blob เพราะต้องแนบ Bearer token, ต่าง
   จาก `<a href>` ธรรมดา), `style.css` เพิ่ม `input[type=email]`/`input[type=file]` เข้า selector

**Verify ที่ทำแล้ว (มากกว่าแค่ py_compile/pyflakes ทุกไฟล์ที่แก้/สร้างใหม่ — สะอาดหมด ยกเว้น 2 finding
เดิมที่รู้อยู่แล้วไม่ใช่บั๊กใน `auth.py`/`db.py`)**:
- Render `docxtpl` จริงด้วยข้อมูลตัวอย่าง (2 วาระ 2 ผู้เข้าร่วม) — ยืนยัน `{{ }}`/`{%p for/endfor %}`
  ทำงานถูกต้อง ไม่เหลือบรรทัดว่างจาก tag
- Encrypt/decrypt PDF จริงด้วย `pypdf` (สร้าง PDF จริง → ใส่รหัสผ่าน → ถอดรหัสสำเร็จ) — ยืนยันว่า
  `protect_pdf()` ทำงานถูกต้องจริง ไม่ใช่แค่ทฤษฎี
- **เขียน end-to-end test เต็ม flow ด้วย FastAPI `TestClient`** (mock แค่ `pdf_generation.convert_docx_to_pdf`/
  `email_service.send_magic_link_email` เพราะ sandbox ไม่มี Word/SMTP จริง ส่วนที่เหลือรันจริงไม่ mock
  รวมถึง DB/docxtpl render/pypdf encryption/magic link token): สร้างประชุม (attendee 1 คนมี email 1 คน
  ไม่มี) → inject minutes_json → generate_docx → download draft → upload final → **Maker ถูกบล็อกจาก
  `/review` (403 ถูกต้อง)** → **reject ไม่มี comment ถูกบล็อก (400)** → reject มี comment →
  `Needs_Revision` → อัปโหลดใหม่ → `Pending_Review` → approve → **PDF ถูกสร้าง+ใส่รหัสผ่านจริง (ถอดรหัส
  สำเร็จด้วยรหัสที่เก็บใน DB)** → **Magic Link ส่งเฉพาะ attendee ที่มี email (1 ใน 2 คนถูกต้อง)** →
  เปิดลิงก์สำเร็จ → **เปิดซ้ำถูกปฏิเสธ (single-use ทำงานถูกต้อง)** → approval log มีครบ 4 entry ตาม
  ลำดับที่ถูกต้อง (`submit_for_review`→`reject`→`submit_for_review`→`approve`) — **ทุก assertion ผ่าน
  หมด** (พบ+แก้ 1 misunderstanding ระหว่างเทส: response body ของ `/review` (approve) สร้างจากข้อมูล
  ก่อน background task รัน — `has_final_pdf` ยังเป็น `false` ในตัว response เอง ต้อง GET ซ้ำถึงจะเห็นผล
  ของ background task ครบ ไม่ใช่บั๊ก แต่เป็นพฤติกรรมปกติของ FastAPI `BackgroundTasks`)
- ทำความสะอาดไฟล์ทดสอบที่หลุดเข้า `D:\Com Sec\backend\generated_docs\` จริงระหว่างเทส (`.docx`/`.pdf`
  ทดสอบ 5 ไฟล์) ผ่าน `allow_cowork_file_delete` แล้วลบทิ้งหมดก่อนจบเซสชัน — ไม่มีไฟล์ทดสอบตกค้าง
- `node --check app.js` ผ่าน, HTML parse ผ่านทั้ง `meeting-detail.html`/`create-meeting.html`

**ยังไม่ได้ทำ / ทำไม่ได้ในเซสชันนี้ (ต้องทำต่อ)**:
- ⚠️ **`docx2pdf`/Word COM automation ยังไม่เคยรันจริงเลยสักครั้ง** (sandbox ไม่มี Windows/Word) —
  verify ได้แค่ py_compile/pyflakes เหมือนโค้ดที่พึ่ง GPU/เบราว์เซอร์ทุกครั้งก่อนหน้านี้ในโปรเจกต์นี้
- ⚠️ **SMTP ยังไม่เคยตั้งค่า/ส่งอีเมลจริงเลยสักครั้ง** (`.env.example` ยังเป็นค่าตัวอย่าง
  `smtp.example.com`) — ต้องกรอกค่าจริง (Gmail/Office365/SMTP relay องค์กร) แล้ว live test เอง
- ⚠️ **ยังไม่เคยเปิด Documents & Approval panel ใหม่ในเบราว์เซอร์จริงเลย** (เหมือนงาน frontend ทุก
  เซสชันก่อนหน้าของโปรเจกต์นี้ — sandbox ไม่มีเบราว์เซอร์จริง) เขียนจาก static analysis + `node --check`
  ล้วนๆ อาจมีบั๊ก CSS layout/event listener ที่เห็นได้แค่ตอนคลิกจริง
- **ยังไม่ได้ตั้งค่า `ARCHIVE_*_DESTINATION` จริง** — ยังไม่มี UNC path/mapped drive ให้ทดสอบตอนนี้ โค้ด
  รองรับค่าว่าง (ข้าม+log warning) แล้วแต่ยังไม่เคย copy ไฟล์ไปปลายทางจริงสักครั้ง
- **DB schema เปลี่ยนอีกรอบ** (เพิ่มคอลัมน์ใหม่ใน `meetings` + ตารางใหม่ 2 ตาราง) — ⚠️ **ต้องลบ
  `D:\Com Sec\backend\com_sec.db` ก่อน restart backend รอบหน้าเหมือนทุกครั้งที่ schema เปลี่ยน**
  (SQLAlchemy's `create_all()` ไม่ ALTER ตารางเดิม ไม่มี Alembic migration — MVP/test data ล้วนๆ ลบทิ้ง
  ได้ปลอดภัย)
- versioning ของรอบ approve ที่ >1 (เก็บแค่ path/password ล่าสุดเสมอ เขียนทับของเก่า — ตรงกับ pattern
  JSON blob อื่นของโปรเจกต์นี้ ไม่ใช่การลืมทำ)
- transcript JSON dump ยังไม่ถูก archive ไปพร้อม audio ต้นฉบับใน `recordings_destination` (archive
  แค่ไฟล์เสียงต้นฉบับตอนนี้ — ตัดขอบเขตไว้ก่อนเพื่อจำกัดสโคปของเซสชันนี้)
- **RBAC ของ transcript-sync player** (ข้อสุดท้ายใน task.md Module 4-5) — ยังไม่ได้ทำ เพราะผูกกับ
  transcript-sync player ของ Module 6 ที่ยังไม่เริ่มสร้างเลย

**Key decisions ทั้งหมดยืนยันผ่าน `AskUserQuestion` ก่อนเขียนโค้ด** (ดู Mantra 1 ด้านบนสำหรับรายละเอียด
เต็มทั้ง 4 ข้อ) — ไม่มีการเดา/ตัดสินใจสถาปัตยกรรมสำคัญเองโดยไม่ถามก่อนสักจุดเดียว

**Key Files ของเซสชันนี้**: `backend/models.py`, `backend/build_minutes_template.py` (ใหม่),
`backend/templates/minutes_template.docx` (ใหม่, binary), `backend/docx_generation.py` (ใหม่),
`backend/pdf_generation.py` (ใหม่), `backend/magic_link.py` (ใหม่), `backend/email_service.py` (ใหม่),
`backend/archive.py` (ใหม่), `backend/config.py`, `backend/.env.example`, `backend/requirements.txt`,
`backend/main.py`, `ComSecAI_Dashboard/meeting-detail.html`, `ComSecAI_Dashboard/create-meeting.html`,
`ComSecAI_Dashboard/app.js`, `ComSecAI_Dashboard/style.css`, `task.md`

**How to resume**: ลบ `com_sec.db` → ตั้งค่า `backend/.env` เพิ่ม (`COMPANY_ADDRESS`/`SMTP_*`/
`MAGIC_LINK_BASE_URL`/`ARCHIVE_*_DESTINATION` ถ้ามีค่าจริงแล้ว — ไม่ตั้งก็รันได้ แค่ข้ามฟีเจอร์นั้น) →
รัน backend → เปิด `/dashboard/` เข้า meeting ที่มี Minutes แล้ว (Module 3) → ทดสอบ flow เต็ม: Generate
เอกสาร Word → ดาวน์โหลด → (ลองแก้ในตาราง/ตัวเลขด้วย Word จริง) → อัปโหลดฉบับสมบูรณ์กลับ → สลับ role เป็น
Com Sec Checker → Approve/Reject → ถ้า Approve แล้วเช็คว่า PDF ถูกสร้างจริง (`docx2pdf`) + ได้รับอีเมล
จริงถ้าตั้ง SMTP ไว้แล้ว — รายงานบั๊กที่เจอกลับมา โดยเฉพาะจุดที่ sandbox ทดสอบไม่ได้ (Word COM
automation คุณภาพการแปลง PDF, SMTP ส่งจริง, UI คลิกจริงในเบราว์เซอร์)

---

## 3.11 Session 2026-08-03 (ต่อทันทีจาก 3.10) — Multi-template: เลือก template ตอนสร้างประชุมได้

**Goal**: ผู้ใช้ถามหลังเห็น template แรกของ Module 4 (ขอดูไฟล์ผ่าน `present_files`) ว่าจะดู/แก้
template ตอนนี้และในอนาคตยังไงถ้าต้องมีการประชุมที่ต้องใช้ form/template อื่น — ถามกลับด้วย
`AskUserQuestion` ว่าจะแค่อธิบายวิธีแก้ template เดียวที่มี หรือสร้างระบบรองรับหลาย template เลย —
ผู้ใช้เลือก **"สร้างเลย — เพิ่ม dropdown เลือก template ตอนสร้างการประชุม"**

**สิ่งที่ทำเสร็จแล้ว**:
1. `backend/models.py` — เพิ่ม `Meeting.template_name` (String, default `"bod_minutes"`) เก็บ key
   ของ template ที่เลือกไว้ตอนสร้าง — เลือกได้ครั้งเดียวตอนสร้าง แก้ทีหลังไม่ได้ผ่าน API (ตั้งใจ กัน
   สับสนถ้าเปลี่ยน template กลางทางหลังมี minutes ไปแล้ว)
2. `backend/docx_generation.py` — เพิ่ม `TEMPLATE_REGISTRY` (dict `{name: {filename, label}}`),
   `list_templates()`, `_resolve_template_path()` (fallback เป็น default เงียบๆถ้าชื่อไม่รู้จัก แทน
   error ทันที) — `render_minutes_docx()` รับพารามิเตอร์ `template_name` เพิ่ม
3. `backend/build_minutes_template.py` — refactor แยก `_build_document(doc_title_prefix)` เป็นแกน
   กลางที่ทุก template ใช้ร่วมกัน (layout/ฟอนต์/Jinja tag เหมือนกันหมด ต่างแค่ข้อความหัวเรื่อง) แล้ว
   สร้าง template ตัวอย่างที่ 2 (`subcommittee` — "รายงานการประชุมคณะกรรมการชุดย่อย/อนุกรรมการ") พิสูจน์
   ว่ากลไกทำงานได้จริง — **บันทึกไว้ในคอมเมนต์หัวไฟล์ชัดเจนว่าผู้ใช้เพิ่ม template ใหม่เองได้ในอนาคตโดย
   ไม่ต้องแตะโค้ด Python เลย**: ก็อปปี้ไฟล์ `.docx` ที่มีอยู่ไปชื่อใหม่ → แก้ด้วย Word ตรงๆ → เพิ่ม 1
   entry ใน `TEMPLATE_REGISTRY`
4. `backend/main.py` — เพิ่ม `GET /api/templates` (คืนรายการสำหรับ dropdown), `MeetingCreateBody`
   เพิ่ม `template_name` (ชื่อไม่รู้จัก → fallback เงียบๆ ไม่ 400 เพราะมาจาก dropdown เท่านั้นไม่ใช่
   user พิมพ์อิสระ), `_meeting_to_dict()` เพิ่ม `template_name`/`template_label`,
   `generate_meeting_docx()` ส่ง `meeting.template_name` เข้า `render_minutes_docx()`
5. Frontend — dropdown "Document Template" ใหม่ใน `create-meeting.html` (โหลดรายการจาก
   `GET /api/templates` ไม่ hardcode — เพิ่ม template ใหม่ที่ backend แล้วโผล่ในนี้อัตโนมัติ),
   `meeting-detail.html`/`app.js` โชว์ template label ที่เลือกไว้ (informational, header ของหน้า)

**บั๊กเล็กที่เจอระหว่างรัน build script (ไม่ใช่บั๊กโค้ด)**: พยายามเขียนทับ `minutes_template.docx` เดิม
ตรงๆตอน refactor แต่เจอ `PermissionError` — ตรวจแล้วพบว่าผู้ใช้เปิดไฟล์นี้อยู่ใน Microsoft Word จริง
ระหว่างดูไฟล์ที่ผมส่งให้ (มี lock file `~$nutes_template.docx` ยืนยัน) — เนื้อหาของ `bod_minutes`
template ไม่ได้เปลี่ยนจากการ refactor เลย (แค่ย้ายเข้าไปอยู่ใน `_build_document()` ที่ใช้ร่วมกัน) จึง
ข้ามการเขียนทับไปสร้างแค่ไฟล์ `subcommittee` ใหม่แทน (ไม่ต้องแตะไฟล์ที่ผู้ใช้เปิดอยู่เลย)

**สิ่งที่สังเกตได้ตอนจบเซสชัน (ยืนยันว่า workflow ที่แนะนำผู้ใช้ใช้ได้จริง)**: ไฟล์
`minutes_template.docx` มีขนาด/เวลาแก้ไขเปลี่ยนไปเอง (lock file หายไปด้วย) — แปลว่าผู้ใช้เปิด+ปิด (และ
อาจแก้ไข) ไฟล์ด้วย Microsoft Word จริงระหว่างเซสชันนี้ — **verify ซ้ำว่า `docxtpl` ยัง render ไฟล์นี้
ได้ปกติหลัง Word แก้ไข/เซฟทับ** (เปิดไฟล์เช็คเนื้อหา + render ทดสอบสำเร็จ) — ยืนยันว่าการแก้ template
ด้วย Word ตรงๆตามที่แนะนำไม่ทำให้ระบบพัง

**Verify ที่ทำแล้ว**: `py_compile`/`pyflakes` สะอาดทุกไฟล์ (เหมือนเดิม 2 finding เก่าที่รู้อยู่แล้ว),
เขียน end-to-end test ผ่าน FastAPI `TestClient`: `GET /api/templates` คืนทั้ง 2 template →
สร้างประชุมเลือก `subcommittee` → `generate_docx` → ดาวน์โหลด → เปิดเช็คเนื้อหาจริงว่าหัวเรื่องตรงกับ
template ที่เลือก (ไม่ใช่ default) → สร้างประชุมอีกใบไม่ระบุ `template_name` → ยืนยัน fallback เป็น
`bod_minutes` ถูกต้อง — **ทุก assertion ผ่านหมด**, `node --check app.js` ผ่าน, HTML parse ผ่านทั้ง 2
หน้าที่แก้

**ยังไม่ได้ทำ**: ยังไม่เคยเปิด dropdown ใหม่ในเบราว์เซอร์จริง (เหมือนงาน frontend อื่นทุกครั้ง),
ยังไม่มี UI แก้/ลบ template จาก dashboard (ต้องแก้ไฟล์ + `TEMPLATE_REGISTRY` เองผ่าน code เท่านั้น
ตามที่ตั้งใจไว้ — ไม่ใช่ฟีเจอร์ที่ตัดสินใจสร้างรอบนี้)

**Key Files ของเซสชันนี้**: `backend/models.py`, `backend/build_minutes_template.py`,
`backend/templates/minutes_template_subcommittee.docx` (ใหม่), `backend/docx_generation.py`,
`backend/main.py`, `ComSecAI_Dashboard/create-meeting.html`, `ComSecAI_Dashboard/meeting-detail.html`,
`ComSecAI_Dashboard/app.js`, `task.md`

**How to resume**: ลบ `com_sec.db` (schema เปลี่ยนอีกรอบ — เพิ่มคอลัมน์ `template_name`) → รัน backend
→ เปิดหน้า Create Meeting → เช็คว่า dropdown "Document Template" โชว์ทั้ง 2 ตัวเลือกจริง → สร้างประชุม
ทดสอบด้วย template `subcommittee` → generate docx → ดาวน์โหลดมาเปิดดูว่าหัวเรื่องถูกต้อง

---

## 3.12 Session 2026-08-03 (ต่อ) — `/scrutinize`: ไล่ debug "คำพูดมันแปลกๆ" → เจอ export bug จริง +
diarization tuning ถึงเพดาน manual probing → เขียนเครื่องมือ Optuna tuning

**Goal**: ผู้ใช้ทดสอบ Module 3 จริง เจอ diarization ให้ speaker 38 คนจากคนพูดจริงไม่กี่คน แล้วบ่นว่า
"คำพูดมันแปลกๆ" พร้อมแนบ transcript จริง + invoke `/scrutinize`

**Diagnosis รอบแรก (ตรวจ transcript จริง ไม่เดา)**: นับ speaker label + คำซ้ำใน `transcript_555.txt`
จริงด้วย `grep`/`wc` (ไม่ได้อ่านผ่านสายตาเดา) พบ 2 ปัญหาแยกกัน: (1) over-segmentation รุนแรง (33 label
ไม่ซ้ำ, 25 ตัวมีแค่ 1-2 บรรทัด, ประโยคเดียวถูกตัดเป็นท่อนคำเดียวกระจายข้าม speaker ปลอมหลายตัว — สาเหตุ
คำร้องเรียน "แปลกๆ" หลัก), (2) ASR repetition-loop artifact 1 จุด ("ตั้งแต่"ซ้ำ 11 ครั้งติด, [27:26])
แยกเป็นคนละปัญหาจาก diarization

**ไล่ tune `clustering.threshold` ทีละค่า (คำแนะนำจากเซสชันก่อนที่ค้างไว้)**: 0.7(เดิม)→1.0→0.85 — ทุก
ครั้งตรวจจากไฟล์ transcript จริงที่ผู้ใช้อัปโหลดมา (นับ speaker label ด้วย `grep -c`, นับคำลงท้ายชาย
"ครับ/ฮะ"เทียบหญิง"ค่ะ/คะ" ต่อ speaker เพื่อจับว่าคนละคนถูกรวมกันไหม — เทคนิคนี้แม่นยำเพราะภาษาไทยคำ
ลงท้ายบ่งเพศชัดเจน) — **ผลตรงข้ามคาด**: 1.0 ลด speaker เหลือ 2 จริง แต่รวมประธาน(ชาย)กับเลขา(หญิง)เป็น
คนเดียว (62 ครั้ง"ครับ/ฮะ"ปน 99 ครั้ง"ค่ะ/คะ"ใน label เดียว) — 0.85 (ค่ากลาง) ไม่ได้อยู่ตรงกลางจริงในแง่
คุณภาพ: ได้ 15 speaker แต่คู่ประธาน+เลขา**ยังรวมกันอยู่เป๊ะ** (57/97 ครั้ง แทบเท่าตอน 1.0) พร้อม
over-segment กลับมาเพิ่มอีก ~13 speaker ปลอม — **สรุปว่า manual probing ถึงเพดานแล้ว** threshold ตัว
เดียวแก้ไม่ได้ทั้งคู่พร้อมกัน

**บั๊กที่เจอกลางทาง (คนละเรื่องกับ diarization)**: ผู้ใช้ยืนยันหนักแน่นว่า export ได้ transcript "2
speaker" ทั้งที่หน้าจอ Speaker Mapping โชว์ "15" ชัดเจน ตอนแรกสงสัยว่าเป็นไฟล์เก่าค้าง (ตรวจ
mtime/byte-size ไฟล์ที่แนบมาหลายรอบพบว่าใช่จริงในบางรอบ) แต่ผู้ใช้ยืนยันว่าไม่ใช่ — เทรซโค้ดจริงพบ
สาเหตุ: `app.js`'s ปุ่ม Export Transcript เดิมใช้ `_detailMeeting` (state ค้างใน memory ของหน้าเว็บ)
ตรงๆ ไม่ fetch ใหม่ก่อน export — ถ้า tab เปิดค้างจากก่อน reprocess รอบล่าสุด (polling หยุดเองตอน status
เป็น "transcribed" แล้ว ไม่มีทางรู้ว่ามี reprocess รอบใหม่เกิดขึ้นจาก tab/session อื่น) จะ export ข้อมูล
เก่าออกมาโดยไม่มีสัญญาณเตือนใดๆ — **แก้แล้ว**: ปุ่ม Export เรียก `loadMeetingDetail()` (fetch จาก
server ใหม่) ก่อนสร้างไฟล์เสมอ ไม่พึ่ง state ค้างอีกต่อไป (กันปัญหาได้ทุกกรณี ไม่ใช่แค่กรณี stale tab
ที่เจอ) — verify ด้วย `node --check` ผ่าน + ผู้ใช้ทดสอบซ้ำแล้วยืนยันไฟล์ export ตรงกับหน้าจอแล้ว

**ตัดสินใจก้าวต่อไป (ผ่าน `AskUserQuestion`)**: เสนอ 3 ทาง (ปล่อยผ่านไป Module 3 ใช้ Speaker Mapping
แก้มือ / ลองอีก 1-2 ค่าต่อแบบเดิม / ลงทุน tune จริงแบบ joint-optimize เทียบ ground truth) — ผู้ใช้เลือก
**ลงทุน tune แบบจริงจัง**

**เครื่องมือที่สร้างเสร็จ (ดูรายละเอียดเต็มใน `task.md` Module 2)**:
1. `audio_worker/diarization.py` — แยก `build_pipeline(device)` (pipeline ที่ยังไม่ instantiate
   hyperparameter) ออกจาก `load_pipeline()` (ยังพฤติกรรมเดิมทุกอย่าง + เพิ่มการโหลด
   `tuned_diarization_params.yaml` อัตโนมัติถ้ามีไฟล์นี้อยู่ ทับค่า env ทั้งหมด)
2. `audio_worker/tune_diarization.py` (ใหม่) — ใช้ `pyannote.pipeline.Optimizer` (Optuna) ค้นหา 5
   พารามิเตอร์พร้อมกัน (`segmentation.threshold`, `segmentation.min_duration_off`,
   `clustering.threshold`, `clustering.method`, `clustering.min_cluster_size` — ยืนยันจากการดาวน์โหลด
   `pyannote.audio==3.3.2`+`pyannote.pipeline==4.0.0` wheel มาอ่านซอร์สจริงในนี้ ไม่ได้เดา API) เทียบ
   Diarization Error Rate จริง (`SpeakerDiarization.get_metric()` มี `GreedyDiarizationErrorRate` ใน
   ตัวอยู่แล้ว) ใช้ `tune_iter()` เซฟผลดีที่สุดทุกรอบกัน progress หายถ้า Ctrl+C กลางคัน
3. `audio_worker/tuning_ground_truth.example.csv` (ใหม่) — ตัวอย่างฟอร์แมต ground truth ให้ผู้ใช้ทำเอง
4. `audio_worker/requirements.txt` — เพิ่ม `pyannote.pipeline==4.0.0`, `optuna` (`pyannote.metrics` เป็น
   dependency ของ `pyannote.audio` อยู่แล้ว ตรวจจากซอร์สแล้วไม่ต้องเพิ่มเอง)

**Verify ที่ทำแล้ว**: `py_compile`/`ast.parse` สะอาดทั้ง `diarization.py`/`tune_diarization.py`,
`node --check app.js` ผ่านหลังแก้ export bug — **ยังไม่เคยรันจริง** (ไม่มี GPU/checkpoint/ground-truth
จริงใน sandbox ให้ทดสอบ pyannote.pipeline.Optimizer end-to-end)

**ยังไม่ได้ทำ (งานถัดไปที่ต้องทำโดยผู้ใช้ ทำแทนไม่ได้)**:
1. ฟังไฟล์ `audio_worker/processed/<job_id>.wav` ช่วงสั้นๆ (5-10 นาที) จริง แล้วเตรียม ground-truth
   CSV เอง (ดู `tuning_ground_truth.example.csv`) — ไม่มีทางลัด ต้องมีคนฟังจริง
2. ตัด audio clip ช่วงเดียวกันด้วย ffmpeg แล้วรัน `python tune_diarization.py --audio ...
   --ground-truth ... --iterations 30` บนเครื่อง Windows ที่มี GPU จริง (ดู docstring หัวไฟล์)
3. หลังได้ `tuned_diarization_params.yaml` แล้ว restart audio_worker + reprocess ไฟล์เดิม verify DER/
   speaker count ใหม่ก่อนกลับไปทดสอบ Module 3 (Generate Minutes) ต่อ — เป้าหมายเดิมของการ live test
   รอบนี้ที่ถูกขัดจังหวะด้วยปัญหา diarization ตั้งแต่ต้น

**Key Files ของเซสชันนี้**: `audio_worker/diarization.py`, `audio_worker/worker_config.py`,
`audio_worker/.env.example`, `audio_worker/tune_diarization.py` (ใหม่),
`audio_worker/tuning_ground_truth.example.csv` (ใหม่), `audio_worker/requirements.txt`,
`ComSecAI_Dashboard/app.js`, `task.md`

**How to resume**: อ่านหัวข้อ "ยังไม่ได้ทำ" ด้านบน — ผู้ใช้ต้องเตรียม ground truth ก่อน ถ้าเปิดเซสชันใหม่
มาแล้วยังไม่มี `tuned_diarization_params.yaml` แปลว่ายังไม่ได้ทำขั้นตอนนี้ ให้ถามผู้ใช้ตรงๆว่าเตรียม
ground truth ไปถึงไหนแล้วก่อนเสนอขั้นตอนต่อไป

---

## 3.13 Session 2026-08-04 (ต่อ) — ประเมิน NotebookLM เทียบ pipeline เอง → เขียนสคริปต์ทดลอง
Gemini native audio transcription คู่ขนานกับการ tune pyannote

**Goal**: ผู้ใช้ลองโยนไฟล์เสียงประชุมเดียวกันเข้า NotebookLM ได้รายงานสรุปที่ diarization แม่นกว่า
pipeline เราเองมาก (ระบุประธาน/CEO/เลขา/กรรมการถูกคนตลอดทั้งไฟล์ ตัวเลขครบ ไม่มีปัญหาประโยคขาดเป็น
ท่อนสั้นๆแบบที่เจอใน 3.12) ถามว่าจะใช้ "mcp notebooklm" แทนการ tune pyannode ต่อได้ไหม

**Research ก่อนตอบ (ไม่เดา)**: เว็บค้นแล้วพบ 2 ประเด็นสำคัญ:
1. **ไม่มี official NotebookLM API/MCP จาก Google เลย** — MCP ทั้งหมดที่เจอเป็นโปรเจกต์ community ที่
   reverse-engineer internal `batchexecute` RPC หรือใช้ browser automation ปลอมตัวเป็น user จริง —
   แหล่งข่าวเองระบุตรงๆว่า "ไม่เป็นทางการ" และ "อยู่ในเขตเทาของ Google ToS" (มีแค่ NotebookLM
   Enterprise เท่านั้นที่มี API compliant จริง)
2. **Data privacy ผูกกับ tier** — NotebookLM tier paid/Enterprise (มี VPC-SC) ไม่เอาข้อมูลไปเทรนโมเดล
   จริง แต่การป้องกันนี้ผูกกับสัญญา/tier องค์กรที่ถูกต้อง ไม่ชัดว่าบัญชีที่ผู้ใช้ลองใช้อยู่ tier ไหน

**สรุปกับผู้ใช้**: ไม่แนะนำใช้ NotebookLM (ผ่าน MCP ไม่เป็นทางการ) แทนในระบบจริง ด้วย 3 เหตุผล (ToS
gray area, data governance tier ไม่ชัด, output เป็น markdown อิสระไม่เข้ากับ JSON schema/Word
template/approval pipeline ที่มีอยู่) — แต่ตั้งข้อสังเกตว่าคุณภาพที่ดีกว่าน่าจะมาจาก **Gemini รุ่นใหม่
อ่านไฟล์เสียงตรงๆได้** (native audio understanding, diarization+ASR จบในโมเดลเดียว) ต่างจาก pipeline
เราที่แยก pyannote (diarization) + typhoon-asr (ASR ต่อ segment แยก ไม่เห็นบริบทข้ามประโยค) — เสนอ
ทดลองส่งไฟล์เสียงเข้า Gemini API ของเราเองตรงๆ (คีย์เดียวกับที่ใช้อยู่แล้ว ควบคุมได้ อยู่ใน compliance
posture เดิม) แทน — ผู้ใช้เลือกทางนี้ผ่าน `AskUserQuestion` (ตัวเลือกอื่นที่ไม่เลือก: เดินหน้า tune
pyannote ต่อตามแผนเดิม / ใช้ NotebookLM แบบ manual ทั้งที่มีความเสี่ยง)

**เขียนสคริปต์ทดลอง**: `backend/audio_transcription_experiment.py` (ใหม่) — ส่งไฟล์เสียงเข้า Gemini
ผ่าน Files API (`client.files.upload()` + poll `PROCESSING`→`ACTIVE`) แล้วขอ structured output
(`AudioTranscriptResult` — list ของ `{start_seconds, end_seconds, speaker_label, text}`) ผ่าน prompt
ที่เน้นกฎ diarization ชัดเจน (label เดียวกันตลอดทั้งไฟล์คนเดียวกัน, ห้ามแต่งเติมคำ, ตัด segment ตาม
เปลี่ยนผู้พูดจริงไม่ใช่ตามประโยค) — **⚠️ ตรวจจากซอร์สจริงของ `google-genai==2.16.0` (ติดตั้งอยู่ใน
sandbox พอดี ตรวจได้ตรงๆไม่ต้องเดา) พบข้อผิดพลาดที่เกือบเขียนพลาด**: เอกสาร web ที่ค้นมาบอกว่าต้องใช้
`GenerateContentConfig(audio_timestamp=True)` เพื่อให้ได้ timestamp แม่นแต่ **parameter นี้โยน
`ValueError` ทันทีถ้าใช้ผ่าน Gemini Developer API mode** (`genai.Client(api_key=...)` — โหมดที่
โปรเจกต์นี้ใช้อยู่ทั้ง Module 1/3) รองรับเฉพาะ Vertex AI "Gemini Enterprise Agent Platform" mode
เท่านั้น (`google/genai/models.py`'s `_GenerateContentConfig_to_mldev()` เช็คแล้ว raise ตรงๆ) — แก้
โดยขอ timestamp ผ่าน prompt text + Pydantic schema field แทน ไม่ใช้ parameter นี้เลย — reuse
`llm_fallback.py::run_with_fallback()` เหมือน Module 3, เพิ่ม config ใหม่ (`GEMINI_MODEL_
TRANSCRIPTION`/`_FALLBACK`/`GEMINI_TRANSCRIPTION_TIMEOUT_MS`) ใน `config.py`/`.env.example`

**Verify**: เขียน mock test 4 เคสในเซสชันนี้ (mock `genai.Client` เพราะ sandbox ไม่มี API key จริงจะ
ใช้เพื่อยิง audio call — เหมือน pattern Module 3): happy path (upload ACTIVE ทันที → parse สำเร็จ →
ลบไฟล์ที่อัปโหลดทิ้งหลังใช้เสร็จ), polling `PROCESSING`→`ACTIVE` ทำงานถูกต้อง, error ชัดเจนถ้าไม่มี
API key, error ชัดเจนถ้าไม่พบไฟล์เสียง — **ทุกเคสผ่านหมด**, `py_compile`/`pyflakes` สะอาด

**เตรียมไฟล์ทดลองให้แล้ว**: ตัด clip 10 นาทีแรกจากไฟล์เสียงจริง (`audio_worker/processed/
1_3d05c249.wav` — รอบ threshold=0.85/15 speaker) ด้วย ffmpeg ไว้ที่ `audio_worker/tuning_clip.wav`
แล้ว (ใช้ร่วมกับทั้ง 2 การทดลอง — ground truth สำหรับ tune pyannote และ input สำหรับสคริปต์นี้ได้)

**ยังไม่ได้ทำ (ต้องให้ผู้ใช้รันเอง — ทำแทนไม่ได้)**: **ยังไม่เคยเรียก Gemini จริงด้วยไฟล์เสียงจริง**
(sandbox ไม่มี `GOOGLE_API_KEY` จริงให้ยิง และมีค่าใช้จ่ายจริงต่อการรันที่ไม่ควรทำแทนโดยไม่ถามก่อน) —
ผู้ใช้ต้องรัน `python audio_transcription_experiment.py --audio ../audio_worker/tuning_clip.wav
--output transcription_experiment_result.txt` บนเครื่อง Windows เอง แล้วเทียบผลกับ `transcript_555
(2).txt` เดิม (จำนวน speaker สมเหตุสมผลไหม ประโยคขาดเป็นท่อนสั้นๆเหมือนเดิมไหม) — **ยังไม่ตัดสินใจว่า
จะแทนที่ `audio_worker`'s pipeline ทั้งชุดหรือไม่** จนกว่าจะมีผลจริงมาเทียบกับทาง tune pyannote (3.12)

**อัปเดต (2026-08-04 ต่อ)**: รันจริงกับ clip 10 นาทีแรกสำเร็จแล้ว (71.81s, model=gemini-3.5-flash) —
**ผลดีมาก**: 4 speaker (สมเหตุสมผลจริง เทียบกับ 33/2/15 ของ pyannote), ประโยคไม่ขาดเป็นท่อนสั้นๆอีกแล้ว
(ต่างจาก pyannote pipeline ที่ตัดกลางประโยคตลอด), ตัวเลข/ชื่อบริษัทตรงกับไฟล์อ้างอิง NotebookLM แทบ
ทุกจุด ("เมดิก้า แอสเซท" สะกดถูก, ตัวเลขกำไร/ขาดทุนตรงกัน) — ยืนยันสมมติฐานว่า Gemini native audio
ดีกว่า pipeline แยกส่วนจริง

⚠️ **พบปัญหา compliance ระหว่างรัน**: ผู้ใช้รันด้วย **free tier API key** (ยืนยันจาก screenshot quota
ของ Google AI Studio) — ขัดกับการตัดสินใจเดิมของโปรเจกต์ (task.md Module 3: ต้องใช้ paid tier เสมอกับ
เนื้อหาบอร์ดจริง เพราะ free tier data อาจถูก Google นำไปใช้พัฒนาโมเดล ตามนโยบายที่เช็คแล้ว) — **ผู้ใช้
ชี้แจงว่าไฟล์ทดสอบนี้ (ประชุมครั้งที่ 16) เนื้อหาไม่ลับแล้ว เพราะแจ้ง/ประกาศผ่าน SET ไปแล้ว** ยอมรับ
ความเสี่ยงสำหรับไฟล์นี้โดยเฉพาะ — **ข้อควรระวังสำหรับอนาคต**: การยกเว้นนี้ใช้ได้เฉพาะไฟล์นี้เท่านั้น
(SET เปิดเผยมักเป็นแค่รายการ/มติสาระสำคัญ ไม่ใช่เนื้อหาการประชุมทั้งหมดคำต่อคำ) — **ประชุมจริงในอนาคต
ที่ยังไม่แจ้ง SET ต้องเปิด billing/ใช้ paid tier ก่อนส่งเข้า `audio_transcription_experiment.py` หรือ
pipeline จริงเสมอ** (เปิด billing ที่ Google AI Studio/Cloud project ผูกกับ API key — ไม่ต้องเปลี่ยน
โมเดล Flash models ใช้ได้ทั้ง 2 tier เหมือนกัน ต่างกันแค่ billing status)

**Key Files ของเซสชันนี้**: `backend/audio_transcription_experiment.py` (ใหม่), `backend/config.py`,
`backend/.env.example`, `audio_worker/tuning_clip.wav` (ใหม่),
`backend/transcription_experiment_result.txt` (ใหม่, ผลทดสอบจริง 10 นาทีแรก), `task.md`

**How to resume**: เช็คว่าผู้ใช้รัน `audio_transcription_experiment.py` กับไฟล์จริงแล้วหรือยัง (ถามตรงๆ
ถ้าไม่แน่ใจ) ถ้ารันแล้วให้เทียบผลกับ transcript เดิม+ผลจาก `tune_diarization.py` (3.12) ก่อนตัดสินใจ
ทิศทางสถาปัตยกรรมสุดท้ายของ diarization/transcription ว่าจะใช้ pyannote+typhoon-asr ที่ tune แล้ว
หรือเปลี่ยนไปใช้ Gemini native audio ทั้งหมด (ถ้าเปลี่ยน จะกระทบ `audio_worker` ทั้งโมดูล — ต้องคุย
กับผู้ใช้ก่อนลงมือ ไม่ใช่ตัดสินใจเอง)

---

## 3.14 Session 2026-08-04 (ต่อ) — full-file 3.6-flash vs 3.5-flash เทียบกัน + `/grill-me` ตัดสินใจสถาปัตยกรรมสุดท้าย

**ผลทดสอบเพิ่ม**: รันไฟล์เต็ม 55 นาทีจริง 2 รอบ —
- `gemini-3.6-flash`: 154.64s, 121 segment, 7 speaker คงที่ตลอดไฟล์ ไม่มี drift/fragmentation ตัวเลข/
  ชื่อส่วนใหญ่ตรงกับ NotebookLM reference — เจอ 2 จุดที่ยังไม่แม่น 100%: ชื่อเล่น CEO ไม่ตรงกับรอบ
  10 นาทีก่อนหน้า ("กุ้ง" ในรอบนี้ vs "ปุ้ม" ในรอบ 3.5-flash/NotebookLM) และตัวเลขหนี้สิน 24.90 ล้านบาท
  ผูกกับบริษัทคนละบริษัท ("TI" ในรอบนี้ vs "24 CSX" ใน NotebookLM)
- `gemini-3.5-flash`: 552.17s (เกือบ 1 ชม.รวมเวลา retry เพราะโดน free-tier rate limit หนักมาก) — สำเร็จ
  ในที่สุดได้ 428 segment/6 speaker แต่ **เจอบั๊กจริงในผลลัพธ์**: speaker_label เว้นวรรคไม่สม่ำเสมอ
  ("Speaker  3"/"Speaker  4" เว้นวรรคซ้ำ ปนกับ "Speaker 4" เว้นวรรคเดียว โดยไม่มี "Speaker 3" เว้นวรรค
  เดียวเลย) ทำให้นับ speaker บวมเกินจริง (จริงๆน่าจะ ~4-5 คน ไม่ใช่ 6)

**สรุป**: `gemini-3.6-flash` เสถียรกว่าทั้ง rate-limit และความสม่ำเสมอของ label — ตั้งเป็น primary,
`gemini-3.5-flash` เป็น fallback เท่านั้น (แก้ `config.py`'s `GEMINI_MODEL_TRANSCRIPTION`/
`GEMINI_MODEL_TRANSCRIPTION_FALLBACK` + `.env.example` แล้ว)

**`/grill-me` เต็มรอบ (คำถาม 7 ข้อ ไล่ทีละ dependency)** — เพราะ handoff เดิมทิ้ง "ยังไม่ตัดสินใจ
ทิศทางสุดท้าย" ค้างไว้ ผู้ใช้เรียก `/grill-me` เพื่อปิดทุกแขนงของการตัดสินใจนี้ **ผลสรุปทั้งหมด (เขียน
รายละเอียดเต็มไว้ที่ `task.md` แล้ว)**:

1. **แทนที่ `audio_worker` ทั้งชุด** — ตรวจ `implementation_plan.md` แล้วพบว่า local pipeline เดิม
   เลือกเพราะข้อจำกัดฮาร์ดแวร์ (GPU 4GB/6GB) ล้วนๆ ไม่มีเหตุผล compliance ใดๆ บังคับให้ต้องรัน local —
   เก็บ pyannote ไว้เป็นทางเลือกสำรองมีต้นทุนบำรุงรักษาสูงกว่าประโยชน์ (ยังมีปัญหา diarization ที่ tune
   ไม่จบด้วย)
2. **ย้าย Gemini call เข้า `backend/` โดยตรง** ไม่ใช่ worker process แยก (ไม่มี torch/GPU แล้ว ปัญหา
   WINHTTP.dll crash เดิมไม่เกี่ยวข้องอีกต่อไป)
3. **Adapter แปลง schema** `start_seconds`/`end_seconds`/`speaker_label` → `start`/`end`/`speaker` ที่
   จุดเดียวตอนรับผล ไม่แตะ downstream code เลย
4. **Paid-tier gate = documentation เท่านั้น** เหมือน Module 3 (ไม่มีทาง enforce ด้วยโค้ดจริง)
5. **Error handling ใช้ pattern เดิม** — ไม่ใส่ `--model` override ให้ใช้ fallback chain 3.6→3.5 ที่มี
   retry-with-backoff อยู่แล้ว พังหมดทุกโมเดล → `status="failed"` เหมือน `audio_worker` เดิม
6. **ลบ `audio_worker/` ทั้งโฟลเดอร์ทิ้ง** (รวม `backend/audio.py`, `start_worker.bat`) — ไม่เก็บ archive
   แยก อาศัย git history
7. **⚠️ ยังไม่ตัดขาดจริง** — ทดสอบมีแค่ไฟล์ประชุมเดียว (2-3 รอบ/โมเดล) ยังไม่พอมั่นใจว่าคุณภาพสม่ำเสมอกับ
   ประชุมอื่น (คนพูดเยอะกว่า/เสียงแย่กว่า) — **ต้องทดสอบเพิ่มอย่างน้อย 1-2 ไฟล์ประชุมอื่นก่อน** ค่อยลบ
   `audio_worker/`/ตัด production path จริง เขียนโค้ด adapter/wiring (ข้อ 2-3) เตรียมไว้ได้เลย แต่ garbage-
   collect `audio_worker/` ต้องรอผ่านด่านนี้ก่อน

**Key Files ของเซสชันนี้**: `backend/config.py`, `backend/.env.example` (primary/fallback model สลับ),
`task.md` (บันทึกผลตัดสินใจเต็ม)

**How to resume**: ยังไม่ได้เขียนโค้ด wiring จริง (ข้อ 2-3 ด้านบน) — ขั้นต่อไปคือ (a) รอไฟล์ประชุมอื่นจาก
ผู้ใช้เพื่อทดสอบเพิ่ม (ข้อ 7) หรือ (b) เริ่มเขียน adapter/wiring code ควบคู่ไปได้เลยถ้าผู้ใช้อยากลงมือ
ก่อน (ยังไม่ลบ `audio_worker/` จนกว่าจะผ่านข้อ 7) — **ห้ามลบ `audio_worker/` เองโดยไม่ถามผู้ใช้ก่อน**
แม้ตัดสินใจสถาปัตยกรรมจะจบแล้วก็ตาม เพราะเงื่อนไขข้อ 7 (ทดสอบเพิ่ม) ยังไม่ผ่าน

---

## 3.15 Session 2026-08-04 (ต่อ) — `/debug-mantra`: ฟีเจอร์ preview ฟังไฟล์เสียงย้อนหลัง (Synced
Audio Playback + Transcript Panel)

**Goal**: ผู้ใช้ขอให้เริ่มทำฟีเจอร์ "preview ฟังไฟล์เสียงย้อนหลัง" — ตรงกับ task.md Module 6 ข้อ
"Synced Audio/Video Player + Transcript Panel" ที่ทิ้งค้างไว้เป็น `[ ]` มาหลาย session (อ้างอิงจาก
`meetily/frontend`) ไม่ใช่งานใหม่ที่ไม่มีในแผน

**Mantra 1 (เข้าใจก่อนลงมือ) + Mantra 4 (cross-reference)**: อ่าน `handoff.md` เต็มไฟล์ +
grep `task.md` หา "RBAC"/"transcript-sync" พบ 2 checklist item ที่ผูกกับฟีเจอร์นี้โดยตรง (task.md
Module 2 บรรทัด "เก็บไฟล์เสียง/วิดีโอต้นฉบับไว้ให้ FastAPI serve กลับมาเล่นย้อนหลังได้" และ Module 4-5
"ปรับ RBAC ของฟีเจอร์ transcript-sync player") — ตรวจโค้ดจริง (`backend/main.py`/`models.py`/
`auth.py`, `ComSecAI_Dashboard/*`) ยืนยันว่าไฟล์ต้นฉบับถูกเก็บไว้ที่ `backend/uploads/` อยู่แล้วตั้งแต่
Module 1 (ไม่เคยลบ) แต่ไม่มี endpoint serve กลับเลย, และ `meetily/frontend/src/components/
AudioPlayer.tsx` เป็นไฟล์ว่างเปล่าจริง (ใช้ได้แค่ `useAudioPlayer.ts` เป็นแนวทาง pattern
seek/timeupdate ส่วน UI ต้องออกแบบเอง) — ตรวจ Starlette source จริงในนี้ (ติดตั้งเวอร์ชันปัจจุบันใน
sandbox ตรวจ ไม่ได้เดา) ยืนยันว่า `FileResponse` รองรับ HTTP Range/206 Partial Content ในตัวอยู่แล้ว
(เพิ่ม `accept-ranges: bytes` เสมอ + parse `Range` header จริง) ไม่ต้องเขียน chunking เอง

**สิ่งที่ทำเสร็จแล้ว (เขียนโค้ดจริง)**:
1. **`backend/auth.py`** — แยก `_resolve_mock_token()` ออกจาก `verify_azure_ad_token()` เดิม (ไม่แก้
   behavior เดิมเลย) เพิ่ม `verify_audio_stream_token()` (รับ token ผ่าน query string แทน
   Authorization header เพราะ `<audio src=...>` element แนบ header เองไม่ได้) + `_build_role_checker()`
   factory กลาง สร้างทั้ง `require_role` (เดิม, header-based) และ `require_role_for_audio_stream`
   (ใหม่, query-token-based) จาก dependency คนละแบบ ไม่ก็อปตรรกะเช็ค role 2 ที่
2. **`backend/main.py`** — เพิ่ม `GET /api/meetings/{id}/audio`: ผูก
   `require_role_for_audio_stream(MEETING_MANAGE_ROLES)` (Com_Sec_Maker/Checker/Global_Admin เท่านั้น
   — Board_Member โดน 403 ตรงกับการตัดสินใจที่บันทึกไว้ตั้งแต่ 3.0 "ไฟล์เสียง/วิดีโอ → เฉพาะทีม
   Com Sec เท่านั้น") 404 ถ้าไม่มี meeting/audio_filename/ไฟล์บนดิสก์ คืน `FileResponse` แบบไม่ใส่
   `filename=` (กัน browser บังคับดาวน์โหลดแทนเล่น inline) พร้อม media type map เอง
   (`AUDIO_VIDEO_MEDIA_TYPES`) ทับ `mimetypes.guess_type()` สำหรับนามสกุลที่เดาผิดมาตรฐาน (เช่น .wav
   เดาเป็น "audio/x-wav" ที่บาง browser ไม่รู้จัก → บังคับ "audio/wav" แทน)
3. **`ComSecAI_Dashboard/meeting-detail.html`** — เพิ่ม Playback panel (`<audio controls
   preload="metadata">`) วางไว้**นอก** `main-content-grid` ตั้งใจ (โชว์ได้ตั้งแต่ status=uploaded ไม่
   ต้องรอ transcribed เหมือน panel อื่น เพราะไฟล์ต้นฉบับมีอยู่แล้วตั้งแต่ upload)
4. **`ComSecAI_Dashboard/app.js`**:
   - `renderTranscript()` — เพิ่ม `data-start="${seg.start}"` ให้แต่ละ `.transcript-line`
   - `meetingAudioUrl()` — สร้าง URL พร้อม mock token แนบผ่าน query string
   - `setupAudioPlayer()` — ตั้ง `<audio src>` เฉพาะตอน meeting.id เปลี่ยน (กัน polling ทุก 5s ระหว่าง
     processing รีเซ็ตตำแหน่งเล่นที่กำลังฟังอยู่) เช็คสิทธิ์ด้วย `fetch(Range: bytes=0-0)` ก่อนเสมอ
     (ไม่ปล่อยให้ `<audio src>` เจอ 403/404 ตรงๆ เพราะ `MediaError` ทั่วไปไม่บอก HTTP status จริง
     — ต้องการข้อความที่มีความหมายให้ผู้ใช้ เช่น Board Member ต้องรู้ว่าโดนกันสิทธิ์ ไม่ใช่ไฟล์เสีย)
   - `highlightActiveTranscriptSegment()` — หา `.transcript-line` ล่าสุดที่ `start <= currentTime`
     (segments เรียงตามเวลาอยู่แล้ว ไม่ต้อง sort ซ้ำ) เพิ่ม class `active` + auto-scroll ถ้ายังไม่อยู่ใน
     มุมมอง
   - `initMeetingDetailPage()` — ผูก `timeupdate` กับ `<audio>` element ตรงๆ (element ไม่เคยถูกสร้าง
     ใหม่ แค่ src เปลี่ยน) และผูก `click` แบบ event delegation ที่ `#transcript-container` (กันต้อง
     re-bind ทุกครั้งที่ transcript ถูก re-render ทับ innerHTML ใหม่) — click บรรทัด → seek + play
5. **`ComSecAI_Dashboard/style.css`** — เพิ่ม `.transcript-line:hover`/`.transcript-line.active` (ใช้
   `--secondary-cyan-deep`/`--primary-gold` ตาม EMPIRE CI เดิม ไม่เพิ่มสีใหม่)
6. **`task.md`** — ปิด 3 checklist item ที่ผูกกับฟีเจอร์นี้ (Module 2 "เก็บไฟล์เสียง/วิดีโอต้นฉบับ",
   Module 4-5 "RBAC ของ transcript-sync player", Module 6 "Synced Audio/Video Player") พร้อมบันทึก
   สโคปที่ตัดออกตั้งใจไว้ในนั้น

**สโคปที่ตัดออกตั้งใจ (ไม่ใช่ MVP รอบนี้ — ผู้ใช้ขอ "ฟังไฟล์เสียงย้อนหลัง" ไม่ใช่ดูวิดีโอ)**: ไม่มี
`<video>` element แยก (ไฟล์วิดีโอต้นฉบับ เช่น Google Meet/Teams recording ยังเล่นเสียงได้ผ่าน
`<audio>` เอง แค่ไม่เห็นภาพ), ไม่มี custom scrubber/theme (ใช้ native `<audio controls>` ตาม pattern
เดิมของโปรเจกต์ที่ปล่อย browser-native element ไปเมื่อ theme เต็มไม่คุ้ม เช่น `input[type=file]`)

**Verify ที่ทำแล้ว**: `py_compile`/`pyflakes` สะอาดทั้ง `auth.py`/`main.py` (2 finding เดิมที่รู้อยู่แล้ว
จาก mock auth — `os`/`jwt` unused — ไม่ใช่ของใหม่จากรอบนี้), `node --check app.js` ผ่าน — **⚠️ ยังไม่
เคยเปิดจริงในเบราว์เซอร์เลย** (เขียนจาก static analysis เหมือนงาน frontend อื่นๆของโปรเจกต์นี้ทุกครั้ง)

**ยังไม่ได้ทำ / ต้องให้ผู้ใช้ verify บนเครื่องจริง**:
1. เปิด meeting ที่มี audio_filename จริงในเบราว์เซอร์ เช็คว่า Playback panel โชว์ + เล่นได้จริง
2. คลิกบรรทัด transcript แล้ว seek ไปตำแหน่งที่คลิกตรงไหม + เล่นต่ออัตโนมัติไหม
3. ฟังเพลงค้างไว้ระหว่าง status="processing" (poll ทุก 5s) แล้วเช็คว่าตำแหน่งเล่น**ไม่**รีเซ็ต/กระตุก
4. สลับ role dropdown เป็น "Board Member" แล้วเช็คว่าเห็นข้อความ "เล่นไฟล์เสียงไม่ได้: Permission
   denied..." (403) ไม่ใช่ player พังเงียบๆ
5. ทดสอบกับไฟล์ .m4a/.wav จริงที่มีอยู่แล้วใน `backend/uploads/` (`meeting_1.m4a`/`meeting_1.wav`/
   `meeting_2.wav`) เช็ค media type ที่ browser เล่นได้ถูกต้องทั้งคู่
6. **ยังไม่ได้ตัดสินใจ**: จะเพิ่ม `<video>` element แยกสำหรับไฟล์ต้นฉบับที่เป็นวิดีโอในอนาคตไหม (ตอนนี้
   เล่นได้แค่เสียง) — รอผู้ใช้ยืนยันว่าจำเป็นจริงก่อน (ไม่ใช่ AI ตัดสินใจขยายสโคปเอง)

**Key Files ของเซสชันนี้**: `backend/auth.py`, `backend/main.py`, `ComSecAI_Dashboard/meeting-detail.html`,
`ComSecAI_Dashboard/app.js`, `ComSecAI_Dashboard/style.css`, `task.md`

**How to resume**: ทำตามข้อ 1-6 ใน "ยังไม่ได้ทำ" ด้านบนบนเครื่อง Windows จริงก่อน (ต้องมี backend +
audio ที่มี `audio_filename` อยู่แล้วในระบบ — ใช้ meeting ที่ผ่าน Module 2 มาแล้วจากไฟล์ตัวอย่างใน
`backend/uploads/` ได้เลย ไม่ต้องอัปโหลดใหม่) — ไม่เกี่ยวข้อง/ไม่กระทบการตัดสินใจสถาปัตยกรรม
transcription (3.14, audio_worker vs Gemini native audio) เลย เพราะ endpoint นี้อ่านจาก
`backend/uploads/` ตรงๆ ไม่ผ่าน pipeline transcription ใดๆ ทำคู่ขนานกันได้

---

## 3.16 Session 2026-08-04 (ต่อ) — หน้า Policy & Board Document Search (Module 1 RAG ไม่เคยมี UI มา
ก่อนเลย) — brief ไป Stitch แล้วต่อผลลัพธ์เข้ากับ backend จริง

**Goal**: ผู้ใช้ถามว่า frontend มีครบทุกฟีเจอร์ตามที่ออกแบบหรือยัง — ตรวจแล้วพบว่า Module 1 RAG
(`/api/rag/query`/`/api/rag/query_confidential`) เป็น P0 requirement ใน `PRD.md` แต่ **ไม่เคยมีหน้า
UI เลยตั้งแต่เขียน backend เสร็จ (session 3.1)** ทดสอบได้แค่ผ่าน curl/Postman มาตลอด — ผู้ใช้ให้เขียน
brief ส่งไป Google Stitch (Antigravity) เอง (คนละ session/เครื่องมือ ไม่มี Stitch MCP ในระบบ เช็คซ้ำ
แล้วยังไม่มีเหมือน session 3.6)

**สิ่งที่ทำเสร็จแล้ว**:
1. **`stitch_brief_rag_search.md`** (ใหม่, root ของโปรเจกต์) — brief พร้อมวางใน Stitch ตรงๆ ระบุ
   layout (scope selector ทั่วไป/ลับ, chat-style Q&A, sources card, loading state ที่ต้องรองรับคำตอบ
   ช้าเป็นนาที), สี EMPIRE CI ครบ, โครงสร้าง response จริงจาก backend (`{response, sources, tokens}`)
   ให้ Stitch ออกแบบ UI ที่ map กับข้อมูลจริงได้พอดี — ผู้ใช้เอาไปวางใน Stitch เอง ได้ `search.html`
   กลับมาที่ `ComSecAI_Dashboard/`
2. **ต่อผลลัพธ์เข้ากับ backend จริง** — Stitch ส่งมาเป็น Tailwind CDN + Material Symbols (คนละ tech
   stack จาก 3 หน้าเดิมที่ใช้ plain CSS ล้วน — ตัดสินใจปล่อยไว้แบบนี้ ไม่ rewrite เป็น plain CSS เพราะ
   แยกไฟล์กันอยู่แล้วไม่ชนกัน คุ้มกว่าเขียนใหม่) แก้ `search.html`:
   - ตัด chrome ที่ Stitch ใส่มาเกินสโคปของ brief ทิ้ง: sidebar เดิมมี nav "Confidential Vault"/
     "Templates"/"Help Center"/"Logout" + notifications/settings icon + avatar image (placeholder จาก
     Google demo asset host) — ทั้งหมดเป็น dead link/ฟีเจอร์ที่ไม่มีหน้า/backend รองรับเลย ตัดทิ้งแทน
     ปล่อยให้กดแล้วไม่มีอะไรเกิดขึ้น (ตรงกับหลักที่ยึดมาตลอดโปรเจกต์: ไม่ปล่อย UI ที่ดูใช้ได้แต่พังเงียบๆ)
   - เพิ่ม role-select (สำคัญมาก — ไม่มีอยู่ในมockup เดิมเลย ทั้งที่เป็นกลไก mock-auth หลักของทั้งระบบ)
     ทั้ง mobile header + desktop sidebar — 2 ตัวพร้อมกันในหน้าเดียว
   - Scope selector มี 2 ชุดซ้อนกันจาก Stitch (pill กลางจอ + sidebar link) — ไม่ตัดออกอันไหน แต่ทำให้
     sync กันผ่าน `updateScopeUI()`/`setSearchScope()` แทน (pill ใช้ได้ทั้ง mobile/desktop เพราะ sidebar
     ซ่อนบน mobile, sidebar ให้ความรู้สึก app-like บน desktop)
   - "New Search" — wire ให้ reset บทสนทนาจริง (เดิมเป็นปุ่มเปล่า)
3. **`app.js`**:
   - `initRoleSelect()` — เดิมใช้ `querySelector` (ตัวเดียว) แก้เป็น `querySelectorAll` + sync ทุกตัวที่
     เจอ เพราะหน้านี้มี `.role-select` 2 ตัวพร้อมกันเป็นครั้งแรก (หน้าอื่นมีแค่ตัวเดียว)
   - เพิ่ม `initSearchPage()`/`submitSearchQuery()`/`appendSearchUserBubble()`/`appendSearchAiBubble()`/
     `showSearchLoading()`/`hideSearchLoading()`/`resetSearchConversation()` — ต่อ `POST /api/rag/query`
     (scope=general)/`POST /api/rag/query_confidential` (scope=confidential) ผ่าน `apiFetch()` เดิม
     ไม่ต้องเขียน HTTP client ใหม่ — loading state มี elapsed-time counter (นับวินาทีเพิ่มทุก 1s) เพราะ
     query ช้าได้ถึง ~30 นาที (`backend/rag.py`'s `RAG_WORKER_TIMEOUT_SECONDS=1800`) ไม่ใช่ 2-3 วิ
     แบบ search ทั่วไป — คำตอบ AI escape เป็น HTML เสมอก่อน render (กัน prompt injection ที่หลุดมาใน
     คำตอบกลายเป็น HTML จริงในหน้า) — copy-to-clipboard ผูกผ่าน closure จับ answer text ตรงๆ ไม่ผ่าน
     data-attribute (กัน escape/unescape ผิดรอบ)
4. **เพิ่ม nav link "Policy Search"** ในหัวของ `index.html`/`create-meeting.html`/`meeting-detail.html`
   ทั้ง 3 หน้า — เดิมไม่มีทางเข้าหน้านี้จากที่ไหนในแอปเลย

**Verify ที่ทำแล้ว**: `node --check app.js` ผ่าน, เขียนสคริปต์เทียบ id ที่ JS เรียก `getElementById`
ทุกตัวกับ id ที่มีจริงใน `search.html` (ครบทุกตัว), เขียน HTML tag-balance checker เอง (sandbox ไม่มี
HTML validator สำเร็จรูป) ผ่านสะอาด — **⚠️ ยังไม่เคยเปิดจริงในเบราว์เซอร์เลย** เหมือนงาน frontend
อื่นๆของโปรเจกต์นี้ทุกครั้ง

**ยังไม่ได้ทำ / ต้องให้ผู้ใช้ verify บนเครื่องจริง**:
1. เปิด `search.html` จริง เช็ค layout ไม่พัง (Tailwind CDN โหลดสำเร็จ, สี/ฟอนต์ตรงตามที่ตั้งใจ)
2. ถามคำถามจริงทั้ง scope ทั่วไป/ลับ เช็คว่าได้คำตอบ+sources กลับมาถูกต้อง (ดัชนีลับตอนนี้ยังว่างอยู่ —
   ยังไม่มี BOD minutes จริงให้ index ดู task.md Module 1)
3. สลับ role dropdown แล้วเช็คว่า mobile/desktop select sync กันจริง (ไม่ต้องรีเฟรชหน้า)
4. กด "New Search" แล้วเช็คว่า state เคลียร์จริง กลับไป empty state
5. ปล่อยคำถามค้างไว้นานๆ (จำลอง query ช้า) เช็คว่า elapsed-time counter เดินจริง ไม่ใช่ค้าง

**Key Files ของเซสชันนี้**: `stitch_brief_rag_search.md` (ใหม่), `ComSecAI_Dashboard/search.html`
(ใหม่ — จาก Stitch แล้วแก้ต่อ), `ComSecAI_Dashboard/app.js`, `ComSecAI_Dashboard/index.html`,
`ComSecAI_Dashboard/create-meeting.html`, `ComSecAI_Dashboard/meeting-detail.html`, `task.md`

**How to resume**: ทำตามข้อ 1-5 ใน "ยังไม่ได้ทำ" ด้านบนบนเครื่อง Windows จริง — ไม่เกี่ยวข้อง/ไม่กระทบ
งานอื่นที่ค้างอยู่ (audio_worker vs Gemini native audio, diarization tuning) เลย เพราะ Module 1 RAG
เป็นคนละระบบจาก Module 2-3 ทั้งหมด ทำคู่ขนานกันได้

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

## 3.17 Session 2026-08-05 — `/debug-mantra`: เขียน adapter/wiring Gemini native audio เข้า
`backend/main.py` แทน `audio_worker` จริง (ค้างมาจาก `/grill-me` 3.14 ข้อ 2-3)

**Goal**: ทำตาม "How to resume" ของ 3.14 ข้อ (b) — เขียนโค้ด adapter/wiring จริง (ยังไม่ลบ
`audio_worker/` เพราะข้อ 7 ของ `/grill-me` ยังไม่ผ่าน — ต้องทดสอบไฟล์ประชุมอื่นก่อน)

**Mantra 1 ก่อนเขียนโค้ด**: อ่าน handoff.md เต็มไฟล์ (1274 บรรทัด) + task.md's checklist ที่ยังไม่ปิด
(grep `[ ]`) ยืนยันว่านี่คืองานเขียนโค้ดจุดเดียวที่ยังไม่เริ่มและไม่ติดบล็อกจากงานที่ต้องรอผู้ใช้
(งานอื่นที่ค้างล้วนรอ live test บนเครื่อง Windows จริงหรือรอผู้ใช้เตรียมข้อมูล) — ถาม
`AskUserQuestion` ยืนยันกับผู้ใช้ก่อนเริ่ม (ตามธรรมเนียมโปรเจกต์นี้) — ผู้ใช้เลือกงานนี้ — อ่าน
`backend/audio_transcription_experiment.py` (โค้ดทดลองที่ verify แล้วว่าได้ผลดีจริง 2 รอบ),
`backend/audio.py` (client เดิมที่จะแทนที่), `backend/main.py` (จุดเรียก + `_meeting_to_dict()`),
`backend/config.py` (ยืนยันว่า `GEMINI_MODEL_TRANSCRIPTION`/`_FALLBACK`/
`GEMINI_TRANSCRIPTION_TIMEOUT_MS` ตั้งไว้แล้วจาก session 3.13), `backend/llm_fallback.py`
(`run_with_fallback()` signature), `backend/models.py` (ยืนยัน schema `Meeting.status`/
`processing_error`/`transcript_segments_json` ไม่ต้องแก้), `TranscriptSegmentIn` ใน `main.py`
(ยืนยัน key `start`/`end`/`speaker`/`text` ที่ downstream ทั้งหมดพึ่งอยู่)

**สิ่งที่ทำเสร็จแล้ว (เขียนโค้ดจริง)**:
1. **`backend/audio_native.py`** (ใหม่ทั้งไฟล์) — ย้าย logic หลักจาก
   `audio_transcription_experiment.py` มาไว้ที่นี่ (Pydantic schema/system prompt/upload+poll ผ่าน
   Files API/fallback chain ผ่าน `run_with_fallback()` เดิม — ไม่แก้ตรรกะเลย แค่ย้ายที่ + เพิ่ม
   `log` parameter รับ callable แทน hardcode `print` เพราะเรียกจาก background task ไม่มี stdout ให้
   ผู้ใช้ดู) เพิ่ม `AudioNativeError` (exception เดียว แทน `AudioWorkerError`+`AudioWorkerBusyError`
   เดิม 2 ตัว — ไม่มี concept "worker ยุ่ง" อีกต่อไปเพราะ Gemini เป็น cloud call รองรับ concurrent
   request ได้ ไม่ผูกกับทรัพยากร GPU เครื่องเดียว), `_adapt_segments()` (จุดแปลง schema เดียวของ
   ระบบ: `start_seconds`/`end_seconds`/`speaker_label` → `start`/`end`/`speaker` ตาม decision ข้อ 3
   ของ `/grill-me`), `transcribe_meeting_audio(audio_path)` (จุดเรียกหลักจาก `main.py`)
2. **`backend/audio_transcription_experiment.py`** — refactor เป็น CLI wrapper บางๆ import จาก
   `audio_native.py` แทน (เดิมมี logic ซ้ำเต็มไฟล์) กันโค้ด production path กับสคริปต์ทดลอง diverge
   กัน — พฤติกรรม CLI เดิมทุกอย่างเหมือนเดิม (`--audio`/`--output`/`--model` เดิมทั้งหมด)
3. **`backend/main.py`**:
   - แก้ import บรรทัด 15: `from audio_native import AudioNativeError, transcribe_meeting_audio`
     (ลบ `from audio import AudioWorkerBusyError, AudioWorkerError, audio_pipeline` — **ไม่ได้ลบไฟล์
     `audio.py`/โฟลเดอร์ `audio_worker/`** แค่เลิกเรียกใช้จาก `main.py` เท่านั้น ตามเงื่อนไขข้อ 7 ของ
     `/grill-me` ที่ยังไม่ผ่าน)
   - `_process_meeting_audio_background()`: เรียก `transcribe_meeting_audio(audio_path, log=log.info)`
     แทน `audio_pipeline.process(str(meeting_id), filename)` — เหลือ `except AudioNativeError`
     ตัวเดียว (ลบ `except AudioWorkerBusyError` เดิม เพราะไม่มี concept worker ยุ่งแล้ว)
   - อัปเดตคอมเมนต์หัว section Module 2 + docstring ของฟังก์ชันนี้ + comment ของ `TranscriptSegmentIn`
     ให้ตรงกับสถาปัตยกรรมใหม่ (ไม่แก้ comment ประวัติที่อธิบาย redesign เดิมของ session 3.3/3.4 —
     ยังถูกต้องในแง่ประวัติ)

**Verify ที่ทำแล้ว**: `py_compile`/`pyflakes` สะอาดทั้ง 3 ไฟล์ที่แก้/สร้างใหม่ (`audio_native.py`,
`audio_transcription_experiment.py`, `main.py`) — เขียน mock unit test ชั่วคราวใน sandbox (mock
`audio_native.genai.Client` ทั้งก้อน ไม่ต้องมี API key จริง/เครือข่ายจริง เหมือน pattern เดียวกับที่
เคยทำใน Module 3/3.13) ยืนยัน 5 เคสด้วยการรันจริง (mantra 3 falsify ไม่ใช่แค่ทฤษฎี): happy path
(schema แปลงถูกต้อง `start_seconds`→`start` ฯลฯ, ลบไฟล์ที่อัปโหลดทิ้งหลังใช้เสร็จ), fallback ไป
โมเดลสำรองสำเร็จ (`GEMINI_MODEL_TRANSCRIPTION_FALLBACK[0]` ถูกเรียกจริงตอน primary error), error
ชัดเจนถ้าไม่มี `GOOGLE_API_KEY`, error ชัดเจนถ้าไม่พบไฟล์เสียง, error ชัดเจนถ้าทุกโมเดลล้มเหลว —
**ทั้ง 5 เคสผ่านตามที่ออกแบบไว้**

**ยังไม่ได้ทำ / ทำไม่ได้ในเซสชันนี้ (ต้องทำต่อ)**:
- ⚠️ **ยังไม่เคยเรียก Gemini จริงผ่าน endpoint `/upload` เลยสักครั้ง** (sandbox ไม่มี `GOOGLE_API_KEY`
  จริง/ไม่มีเครือข่ายไปยัง Google) — mock test ยืนยันแค่ตรรกะ wiring/schema adapter ของเราเอง ไม่ได้
  ยืนยันว่า flow เต็มทำงานถูกต้องจริงบน Windows (upload → background task → Gemini → DB → poll →
  frontend)
- ⚠️ **เงื่อนไขข้อ 7 ของ `/grill-me` (ทดสอบไฟล์ประชุมอื่นอย่างน้อย 1-2 ไฟล์) ยังไม่ผ่าน** — ยังไม่ควร
  ลบ `audio_worker/`/`backend/audio.py`/`start_worker.bat` จนกว่าจะทดสอบเพิ่ม (ห้าม AI ตัดสินใจลบเอง)
- `backend/audio.py` ยังอยู่ในโค้ดแต่ไม่มีใครเรียกใช้แล้ว (dead code ชั่วคราว ตั้งใจเก็บไว้เผื่อ
  ต้อง rollback ด่วนถ้า Gemini native audio มีปัญหาจริงกับไฟล์อื่น) — จะลบพร้อม `audio_worker/`
  ตอนผ่านข้อ 7 แล้วเท่านั้น
- ยังไม่ได้ตัดสินใจว่าจะปรับ `AUDIO_WORKER_TIMEOUT_SECONDS`/`AUDIO_WORKER_BASE_URL` (ยังอยู่ใน
  `audio.py`) ทิ้งเมื่อไหร่ — รอพร้อมกับการลบทั้งไฟล์

**Key Files ของเซสชันนี้**: `backend/audio_native.py` (ใหม่), `backend/audio_transcription_experiment.py`,
`backend/main.py`, `task.md`

**อัปเดต (2026-08-05 ต่อ) — บั๊กจริงที่ผู้ใช้รายงาน + แก้แล้ว**: หลังจบเซสชันด้านบน ผู้ใช้ทดสอบอัปโหลด
ไฟล์จริงแล้วรายงานว่า backend terminal "นิ่ง" ไม่มี log อะไรขึ้นหลังอัปโหลด — mantra 2 (trace fail
path จริง) พบว่า `_upload_and_wait()` ใน `audio_native.py` **ไม่เคยรับ/เรียก `log` เลยตั้งแต่ refactor
จาก `audio_transcription_experiment.py` เดิม** (ต้นฉบับมี `print()` ทุกรอบ poll `PROCESSING`→`ACTIVE`
แต่ตอนย้าย logic มาไฟล์ใหม่ ไม่ได้ส่ง `log` เข้าไปในฟังก์ชันนี้ด้วย) — ระหว่าง `client.files.upload()`
(อาจช้าถ้าไฟล์ใหญ่) และ poll loop จึงไม่มี log ออกมาเลยสักบรรทัด ดูเหมือนค้างทั้งที่จริงทำงานปกติอยู่
**ไม่เกี่ยวกับที่ผู้ใช้แก้ไฟล์การประชุมเดิม** — **แก้แล้ว**: `_upload_and_wait()` รับ `log` เพิ่ม log
3 จุด (เริ่มส่งไฟล์, อัปโหลดไบต์เสร็จ+เริ่มรอประมวลผล, ทุกรอบ poll พร้อมเลข poll count/เวลาโดยประมาณ) —
verify ด้วย mock test เพิ่ม 1 เคส (falsify ตรงจุด: จำลอง state `PROCESSING`→`ACTIVE` แล้วยืนยันว่า log
ถูกเรียกจริงทั้ง 3 จุด ไม่ใช่แค่ก่อน/หลังทั้งก้อน) ผ่านแล้ว, `py_compile`/`pyflakes` สะอาด — **ยังไม่ได้
verify จริงบนเครื่อง Windows ว่า log ที่เพิ่มแก้ปัญหา "ดูเหมือนค้าง" ได้จริง** (ผู้ใช้ต้องอัปโหลดซ้ำแล้ว
ดู backend terminal ว่าเห็น log ระหว่างรอ Gemini ประมวลผลไฟล์แล้ว)

**อัปเดต (2026-08-05 ต่ออีกรอบ) — บั๊กจริงที่ 2: meeting ค้าง "processing" ตลอดกาลหลัง backend
restart**: ผู้ใช้ restart backend (เพื่อโหลดโค้ดแก้ log ด้านบน) แล้วพบว่าหน้าเว็บค้างที่สถานะ
processing อัปโหลดไฟล์ใหม่ไม่ได้ — เช็ค `com_sec.db` ตรงๆ (ผ่าน sqlite3 ใน sandbox) ยืนยันว่า meeting
#1 ค้าง `status="processing"` จริง — **root cause**: FastAPI `BackgroundTasks` ผูกกับ process เดิม
ไม่ persist ข้าม restart พอ backend ถูกฆ่ากลางทางที่มี background task กำลังประมวลผลอยู่ status
ก็ค้างตลอดกาล (ไม่มีทางรู้ว่า "ค้างจริง" หรือ "restart กลางทาง") และ `app.js`'s `actionCellHtml()`
ไม่โชว์ปุ่ม Upload/Re-upload ให้เลยตอน status="processing" (โชว์เฉพาะ `draft`/`failed`) — ตรงกับ
`/scrutinize` finding เดิมที่บันทึกไว้แล้ว ("ไม่มี timeout/watchdog") แค่เพิ่งโดนจริงเป็นครั้งแรก —
**ไม่ใช่บั๊กจากที่แก้ log ก่อนหน้า**

**ลองแก้ตรง DB ผ่าน sandbox ก่อน (ผู้ใช้เลือกทางนี้ผ่าน `AskUserQuestion`) — ล้มเหลว**: `UPDATE` ตรงๆ
ผ่าน `sqlite3` ใน sandbox เจอ `disk I/O error` (ตรวจแล้ว `PRAGMA integrity_check` ผ่าน — ไฟล์ไม่เสีย
แค่เขียนไม่ได้ น่าจะเป็นข้อจำกัดของ mounted/network filesystem ที่ sandbox ใช้เข้าถึง `D:\Com Sec`
กับ SQLite's file locking) — **เปลี่ยนทางแก้**: เขียนฟังก์ชัน `_recover_stuck_processing_meetings()`
ใน `backend/main.py` (เรียกครั้งเดียวตอน import module หลัง `init_db()`) — meeting ใดก็ตามที่
`status="processing"` ตอน backend เพิ่งเริ่มโปรเซสใหม่เป็นไปไม่ได้ที่จะยังประมวลผลอยู่จริง auto-mark
เป็น `"failed"` พร้อม `processing_error` อธิบายเหตุผลชัดเจน (ให้ปุ่ม Re-upload กลับมาทันที) —
**ข้อจำกัด**: ยังไม่ใช่ watchdog เต็มรูปแบบ ไม่จับกรณี background task ค้างจริงระหว่างที่ backend ยัง
รันอยู่ (กรณีนั้นยังพึ่ง `GEMINI_TRANSCRIPTION_TIMEOUT_MS` เดิม) ปิดแค่ช่องโหว่ "ค้างเพราะ restart"
ที่เจอจริงรอบนี้เท่านั้น

**Verify**: เขียน integration test จริงใน sandbox (ไม่ mock) — สร้าง SQLite DB แยกต่างหาก (env var
`COM_SEC_DB_PATH` override), insert meeting ด้วย `status="processing"` ตรงๆผ่าน `sqlite3` ดิบ (จำลอง
state ค้างจาก process ก่อน) แล้ว `import main` (เหมือน `uvicorn main:app` เริ่มโปรเซสใหม่จริง) ยืนยัน
ว่า status เปลี่ยนเป็น `"failed"` พร้อม `processing_error` ที่มีคำอธิบายจริงหลัง import เสร็จ — **ผ่าน
สำเร็จ** `py_compile`/`pyflakes` สะอาด

**ยังไม่ได้ทำ**: ยังไม่ได้ verify บนเครื่อง Windows จริงว่า restart แล้ว meeting #1 จริงของผู้ใช้กลับมา
เป็น `failed` + กด Re-upload ได้จริง (verify แล้วแค่ logic เดียวกันในสภาพแวดล้อม sandbox)

**How to resume**: ตั้งค่า `GOOGLE_API_KEY` (paid tier) ใน `backend/.env` ให้พร้อม → รัน backend (ไม่
ต้องรัน `audio_worker`/`start_worker.bat` อีกต่อไปสำหรับ flow นี้ — เหลือรันแค่ `rag_worker` + backend
2 โปรเซส) → เปิด `/dashboard/` สร้างการประชุมใหม่ → อัปโหลดไฟล์เสียงประชุม **อื่น** (ไม่ใช่ไฟล์เดิมที่
เคยทดสอบใน 3.13-3.14 — ตามเงื่อนไขข้อ 7 ที่ต้องทดสอบไฟล์ใหม่) → poll จน `status="transcribed"` →
ตรวจคุณภาพ (speaker count สมเหตุสมผลไหม, ข้อความตรงกับเสียงจริงไหม) เทียบกับที่เคยได้จาก
`audio_worker` เดิม (ถ้ามี) → รายงานผลกลับมา — **ถ้าคุณภาพดีสม่ำเสมอกับไฟล์แรกที่เคยทดสอบ** ค่อยถาม
ผู้ใช้เรื่องลบ `audio_worker/`/`backend/audio.py`/`start_worker.bat` (ข้อ 6 ของ `/grill-me`) — **ห้าม
ลบเองโดยไม่ถามก่อน**

---

## 3.18 Session 2026-08-05 (ต่อ) — `/debug-mantra`: บันทึก+แสดงโมเดล transcription ทุกที่ (log/DB/web)

**Goal**: ผู้ใช้ขอ "บันทึกและแสดงทุกที่ทั้งใน log, db, web" ต่อจากที่คุยกันเรื่องอยากรู้ว่ารอบไหนใช้
โมเดลไหนสำเร็จ (log มีอยู่แล้วจาก `run_with_fallback()` แต่ DB/web ยังไม่มี)

**สิ่งที่ทำเสร็จแล้ว**:
1. **`backend/models.py`** — เพิ่ม `Meeting.transcription_model_used` (String, nullable) เก็บชื่อ
   โมเดลที่สำเร็จจริงรอบล่าสุด (primary/fallback) เขียนทับด้วยค่าล่าสุดเสมอถ้า reprocess ซ้ำ (ตรงกับ
   pattern field อื่นของโปรเจกต์นี้)
2. **`backend/main.py`**:
   - `_process_meeting_audio_background()` — เก็บ `result.get("model_used")` ลงคอลัมน์ใหม่ + เพิ่ม
     log บรรทัดสรุปแยกต่างหาก `[TRANSCRIBE-DONE] meeting {id} transcribed ด้วยโมเดล=... ใน Xs (N
     segments)` (แยกจาก log ระดับ upload/poll ของ `audio_native.py` เอง — grep หาง่ายกว่า)
   - `_meeting_to_dict()` — คืน field `transcription_model_used` เพิ่ม
3. **Frontend** (`ComSecAI_Dashboard/`) — `meeting-detail.html` เพิ่ม `<p id="transcript-model-used">`
   ใต้หัวข้อ "Meeting Transcript" (ห่อ h3 ด้วย div เพื่อไม่ให้ชนกับปุ่ม Edit ใน `flex-between`
   layout), `app.js`'s `renderTranscriptionModelUsed()` (เรียกจาก `renderMainContent()` คู่กับ
   `renderTranscript()`) — ซ่อนเงียบๆถ้า field เป็น null (meeting เก่า/ยังไม่เคยสำเร็จ) ไม่โชว์ข้อความ
   ว่างเปล่า

**Verify**: เขียน integration test จริงใน sandbox (ไม่ mock DB) — สร้าง SQLite DB แยกผ่าน
`COM_SEC_DB_PATH` override, ยืนยัน `PRAGMA table_info` เห็นคอลัมน์ใหม่จริงหลัง `init_db()`, insert
meeting, `import main` (โหลดโค้ดจริงรวม `_recover_stuck_processing_meetings()`), จำลอง background
task set `transcription_model_used` แล้วเรียก `main._meeting_to_dict()` จริง ยืนยันว่า field ไหลจาก
DB ออกมาถูกต้อง — **ผ่านสำเร็จ**, `py_compile`/`pyflakes`/`node --check app.js`/HTML parse
(`html.parser`, เช็ค tag balance) สะอาดหมด

**ยังไม่ได้ทำ**: ยังไม่เคย verify จริงในเบราว์เซอร์/บนเครื่อง Windows (เหมือนงาน frontend อื่นๆของ
โปรเจกต์นี้ทุกครั้ง) — ⚠️ **DB schema เปลี่ยนอีกรอบ ต้องลบ `com_sec.db` ก่อน restart backend** เหมือน
ทุกครั้งที่ schema เปลี่ยน (ไม่มี Alembic — MVP เท่านั้น) — การลบ DB รอบนี้จะล้าง meeting ทดสอบเดิม
ทั้งหมดไปด้วย (รวม meeting ที่กำลังทดสอบปัญหาข้อความหาย 13:46-16:48 ใน 3.17 — ถ้ายังไม่เก็บผลลัพธ์/
สังเกตอะไรไว้ ให้บันทึกก่อนลบ)

**Key Files ของเซสชันนี้**: `backend/models.py`, `backend/main.py`, `ComSecAI_Dashboard/meeting-detail.html`,
`ComSecAI_Dashboard/app.js`, `task.md`

**How to resume**: บันทึกผลทดสอบ "ลองอัปโหลดไฟล์เดิมซ้ำ" ของ 3.17 ไว้ก่อนถ้ายังไม่ได้บันทึก → ลบ
`com_sec.db` → รัน backend → อัปโหลดไฟล์เสียงทดสอบ → หลัง transcribed เช็คว่า Transcript panel โชว์
บรรทัด "ถอดเสียงด้วยโมเดล: gemini-3.6-flash" (หรือ 3.5-flash ถ้า fallback) ใต้หัวข้อถูกต้อง + เช็ค log
backend terminal เห็นบรรทัด `[TRANSCRIBE-DONE]` ด้วย

**อัปเดต (2026-08-05 ต่ออีกรอบ) — บั๊กจริงที่ 3 (ใหญ่กว่าที่คิด): `log.info(...)` ไม่เคยโชว์ในเทอร์มินอล
เลยตั้งแต่แรก**: ผู้ใช้เรียก `/debug-mantra` รายงานว่า log ระหว่างเปิดหน้า meeting-detail มีแค่
access log ของ uvicorn เฉยๆ (`INFO: 127.0.0.1:... GET ...`) ไม่มี log อะไรจากแอปเราเลย แม้จะเพิ่ม
`log.info(...)` calls ไปหลายจุดในเซสชันก่อนๆ (แก้บั๊ก "นิ่ง" ของ `_upload_and_wait`, เพิ่ม
`[TRANSCRIBE-DONE]` summary) — **mantra 2 (trace) + mantra 4 (cross-reference กับ uvicorn's access
log ที่โชว์ปกติ) พบ root cause จริง**: `log = logging.getLogger("com_sec.main")` ใน `backend/main.py`
ไม่เคยถูก config เลย (ไม่มี `basicConfig()`/handler/level) — Python root logger ดีฟอลต์ level เป็น
`WARNING` ไม่มี handler ผูกไว้ ทำให้ `log.info(...)` ทุกจุดถูกตัดทิ้งเงียบๆมาตลอด (below threshold) —
**ไม่ใช่บั๊กใหม่จากเซสชันไหนโดยเฉพาะ เป็น gap ที่ซ่อนอยู่ตั้งแต่ `main.py` ถูกสร้างครั้งแรก** เพิ่งโดน
จริงเพราะเพิ่งมาพึ่ง `log.info()` เป็นทางเดียวในการสื่อสารกับผู้ใช้ (audio_worker เดิมใช้ `print()`
ตรงๆซึ่งไม่มีปัญหานี้) — **สำคัญ**: log ที่เพิ่มไปในเซสชันก่อนหน้า (3.17's `_upload_and_wait` fix,
3.18's `[TRANSCRIBE-DONE]`) **โค้ดถูกต้องแล้วทั้งหมด แค่ไม่เคยแสดงผลได้จริง** จนกว่าจะแก้จุดนี้

**แก้แล้ว**: เพิ่มการ config logger นี้โดยตรงหลัง `logging.getLogger("com_sec.main")` — `setLevel(logging.INFO)`
+ ผูก `StreamHandler` (ไม่พึ่ง `logging.basicConfig()` เพราะอาจเป็น no-op เงียบๆถ้า root logger มี
handler อยู่แล้วจาก uvicorn ตามลำดับ import) + `propagate = False` กัน log ซ้ำ 2 บรรทัดถ้า root
logger ดันมี handler ของตัวเองด้วย — **Verify**: รัน `import main` จริงใน sandbox (ไม่ mock) เรียก
`main.log.info(...)`/`main.log.warning(...)` ตรงๆ ยืนยันว่าออกมาจริงที่ stderr (format
`timestamp LEVEL logger_name: message`) — ผ่านสำเร็จ, `py_compile`/`pyflakes` สะอาด

**ยังไม่ได้ทำ**: ยังไม่เคย verify จริงบนเครื่อง Windows ว่า log โชว์ในเทอร์มินอลจริงหลัง restart (ผล
ทดสอบใน sandbox ยืนยันแค่ logic การ config เท่านั้น) — ผู้ใช้ต้อง restart backend อีกครั้งแล้วลอง
อัปโหลด/ดูว่าเห็น log `[transcribe] ...`/`[TRANSCRIBE-DONE]` จริงในเทอร์มินอลหรือไม่

**Key Files ของเซสชันนี้**: `backend/main.py`

---

## 3.19 Session 2026-08-05 (ต่อ) — วิเคราะห์บั๊ก "timestamp ไม่ตรง" ด้วยข้อมูลจริง พบ drift ตาม
สัดส่วนคงที่ตลอดไฟล์ (ปัญหาคุณภาพร้ายแรงกว่า omission ที่เจอก่อนหน้า)

**Goal**: ผู้ใช้รายงานว่า timestamp ใน transcript ไม่ตรงกับเสียงจริง (เสียงจริง 06:19 แต่ข้อความที่
ถูกต้องติด timestamp 10:14) พร้อมเดาสาเหตุว่าอาจเป็นเพราะไม่ได้ลบช่วงที่ไม่ได้ถอดออกมา — ต้องวินิจฉัย
ก่อนสรุปว่าใช่/ไม่ใช่

**Mantra 3 (falsify ด้วยข้อมูลจริง ไม่เดา)**: query `com_sec.db` ตรงๆ (sandbox มีสิทธิ์อ่านผ่าน mount)
ดึง `transcript_segments_json` ของ meeting #1 (263 segment, model=`gemini-3.6-flash`) + วัดความยาว
ไฟล์เสียงต้นฉบับจริงด้วย `ffprobe` (`backend/uploads/meeting_1.m4a` = 55:42 / 3342.7s) — เขียนสคริปต์
เช็ค gap ระหว่างทุกคู่ segment ที่ติดกัน (262 คู่) และเทียบ `end` ของ segment สุดท้ายกับความยาวไฟล์จริง

**ผลลัพธ์**:
- **สมมติฐาน "ไม่ลบช่วงที่ไม่ได้ถอด" ถูก falsify แล้ว**: gap ใหญ่สุดระหว่าง segment ที่ติดกันทั้งหมด
  แค่ 0.7s — แทบไม่มีช่องว่างเลย ไม่ใช่สาเหตุ
- **สาเหตุจริง**: `end` ของ segment สุดท้ายที่ Gemini รายงาน = **93:20** (5600s) ทั้งที่ไฟล์จริงยาวแค่
  **55:42** (3342.7s, ยืนยันจาก ffprobe) → อัตราส่วน **1.675x**
- เทียบกับจุดที่ผู้ใช้เจอเอง (06:19 จริง ↔ 10:14 ที่รายงาน) → อัตราส่วน **1.620x**
- **สองอัตราส่วนนี้ใกล้กันมาก แม้วัดกันคนละจุดของไฟล์ (นาทีที่ 6 vs นาทีที่ 55)** — บ่งชี้ชัดว่าเป็น
  การประมาณเวลาผิดแบบ**สัดส่วนคงที่ตลอดไฟล์** ไม่ใช่ drift สะสมจากช่วงที่หายเป็นก้อนๆแบบที่ผู้ใช้เดา —
  ตรงกับความเสี่ยงที่บันทึกไว้แล้วตั้งแต่ session 3.13: Gemini Developer API mode (ที่โปรเจกต์นี้ใช้
  อยู่) ใช้ `GenerateContentConfig(audio_timestamp=True)` (native, แม่นระดับเฟรมเสียง) ไม่ได้ —
  รองรับเฉพาะ Vertex AI Enterprise mode เท่านั้น — เราเลยต้องขอ timestamp ผ่าน prompt+schema ให้
  โมเดลประมาณเอาเอง (สมมติฐานที่สมเหตุสมผลที่สุด: โมเดลอิงจังหวะพูด/จำนวนคำสะสมโดยประมาณ ไม่ใช่ตำแหน่ง
  จริงในไฟล์เสียง — ยังไม่ได้ verify กลไกภายในจริงเพราะเป็น black box)

**ตรวจโค้ดฝั่งเราแล้วไม่พบบั๊ก**: `audio_native.py`'s `_adapt_segments()` — map `start_seconds`/
`end_seconds` → `start`/`end` ตรงๆ ไม่มีการคำนวณ/แปลงหน่วยใดๆเลย, `app.js`'s `formatSeconds()` —
เลขคณิต `Math.floor(total/60)`/`total%60` ถูกต้อง ไม่มี off-by-one — **ยืนยันว่าเป็นข้อจำกัดจริงของ
Gemini เองล้วนๆ ไม่ใช่บั๊กใน adapter/frontend ของโปรเจกต์นี้เลย**

**ผลกระทบ**: ยิ่งไฟล์ยาวยิ่งคลาดสะสมมาก (ไฟล์ 55 นาทีนี้ ท้ายไฟล์คลาดไปเกือบ 38 นาที) — กระทบฟีเจอร์
click-to-seek/highlight (session 3.15) โดยตรง: ใช้งานได้จริงแค่ช่วงต้นไฟล์สั้นๆเท่านั้น สำหรับไฟล์
ประชุมยาวเป็นชั่วโมง timestamp จะคลาดเคลื่อนจนฟีเจอร์นี้ใช้งานจริงไม่ได้ — **ไม่กระทบเนื้อหา/ข้อความ
transcript เอง** (แค่ metadata เวลากำกับผิด เนื้อหายังถูกต้องตามที่เคย verify คุณภาพไปแล้วก่อนหน้า) —
**ไม่กระทบ Minutes Generation (Module 3)** เพราะ prompt ของ `minutes_prompts.py` ใช้ timestamp แค่
ประกอบบริบทให้ Gemini อ่าน ไม่ได้เอาไปคำนวณ/แสดงผลอะไรที่ต้องแม่นระดับวินาที

**ยังไม่ได้ตัดสินใจทิศทางต่อ** — ตัวเลือกที่ยังไม่ได้คุยกับผู้ใช้ (รอ `/grill-me` หรือคุยกันก่อนตัดสินใจ
ตามธรรมเนียมโปรเจกต์นี้):
1. ใช้ Gemini native audio ต่อสำหรับเนื้อหา/Minutes (คุณภาพดีกว่า pyannote+typhoon-asr จริงตามที่
   verify ไปแล้วใน 3.13-3.14) แต่ยอมรับว่าฟีเจอร์ timestamp-dependent (click-to-seek/highlight) ใช้
   ไม่ได้จริงสำหรับไฟล์ยาว — อาจต้องปิดฟีเจอร์นี้หรือเตือนผู้ใช้ชัดเจนว่า timestamp เป็นแค่ "โดยประมาณ"
2. สำรวจว่า Vertex AI Enterprise mode (รองรับ `audio_timestamp=True` จริง, แม่นระดับเฟรม) เป็นไปได้
   ไหมสำหรับโปรเจกต์นี้ (ต้องเปลี่ยนวิธี auth/billing จาก Developer API key ธรรมดา — ยังไม่ได้ศึกษา
   รายละเอียด/ค่าใช้จ่ายเพิ่มเติม)
3. กลับไปใช้ `audio_worker` (pyannote+typhoon-asr) เฉพาะสำหรับความแม่นของเวลา แม้ diarization
   coherence จะแย่กว่า (over-segmentation ที่เจอใน session 3.12) — ทางนี้ต้องดีไซน์ hybrid ถ้าจะเอา
   ข้อดีทั้งคู่ (เนื้อหา/diarization coherence จาก Gemini + timestamp แม่นจาก local pipeline) ซึ่งซับซ้อน
   ขึ้นมาก

**ผลกระทบต่อเกณฑ์ข้อ 7 (`/grill-me` 3.14)**: นี่คือ finding ที่ 2 ที่กระทบเกณฑ์นี้โดยตรง (ต่อจาก
omission 13:46-16:48 ใน 3.17 ที่ยังไม่มีผลอัปโหลดซ้ำกลับมาเช็ค deterministic/random) — **ยิ่งมีน้ำหนัก
มากขึ้นว่า "แทนที่ audio_worker ทั้งชุด" อาจไม่ใช่คำตอบที่ถูกต้องอีกต่อไป โดยเฉพาะถ้าฟีเจอร์
timestamp-dependent สำคัญกับผู้ใช้จริง** — ต้องคุยกับผู้ใช้ก่อนตัดสินใจทิศทางสุดท้าย ไม่ใช่ AI ตัดสินใจ
เอง

**Key Files ของเซสชันนี้**: ไม่มีไฟล์โค้ดที่แก้ (เป็นเซสชันวิเคราะห์/วินิจฉัยล้วนๆ), `task.md`

**How to resume**: คุยกับผู้ใช้ว่าจะเลือกทางไหนใน 3 ตัวเลือกด้านบน (หรือทางอื่น) ก่อนเขียนโค้ดต่อ —
ถ้ายังไม่ตัดสินใจ ให้ถือว่า `audio_worker/`/`backend/audio.py` **ยังห้ามลบ** เหมือนเดิม (เงื่อนไขข้อ 7
เดิมยิ่งไม่ผ่านชัดเจนขึ้นจาก finding นี้)

---

### Session 3.20 — `/scrutinize` การเปลี่ยน Gemini native audio ทั้งชุด + ค้นข้อมูลเพิ่มเรื่อง timestamp drift (2026-08-05)

ผู้ใช้เรียก `/scrutinize` พร้อมขอให้ "วิเคราะห์และหาข้อมูลเพิ่มสำหรับปัญหานี้หน่อย" — ตีความว่าครอบคลุม
ทั้ง (a) รีวิวโค้ดที่แก้ทั้งหมดของ session ก่อนหน้า (3.17-3.19: `audio_native.py`, `main.py`'s logging
config + `_recover_stuck_processing_meetings()`, `models.py`, frontend 3 ไฟล์) และ (b) ค้นข้อมูลเพิ่ม
เรื่อง timestamp drift ที่เจอใน 3.19

**งานวิจัยที่ทำ (ไม่มีการเปลี่ยนโค้ดจากส่วนนี้)**:
- ยืนยันผ่านกระทู้ Google AI Developer Forum ว่า progressive/proportional timestamp drift ในการถอด
  เสียงของ Gemini เป็นบั๊กที่รู้จักแพร่หลาย เปิดมาตั้งแต่มีนาคม 2026 ยังไม่มี fix อย่างเป็นทางการ
- ยืนยันผ่าน GitHub issue `googleapis/java-genai#774` ตรงกับที่เราเจอเองใน session 3.13:
  `audioTimestamp(true)` throw error บน Gemini Developer API (รองรับเฉพาะ Vertex AI)
- **พบ lead ใหม่ที่ actionable**: benchmark จากบุคคลที่สามรายงานว่าโมเดล "Flash Lite" แม่นกว่ามาก
  (sub-second, ไม่มี progressive drift) เทียบกับ "Pro"/"Flash" ตัวเต็มที่คลาดสะสมได้ถึง 157s ในกรณี
  แย่สุด — ยังไม่ได้ทดสอบจริงกับไฟล์ของเรา
- พบว่า Google อัปเดตเอกสาร (2026-07-30) แนะนำ API ใหม่ `client.interactions.create()` แทน
  `client.models.generate_content()` ("Legacy") — `google-genai==2.16.0` ที่ติดตั้งอยู่รองรับ API ใหม่
  นี้แล้ว แต่การย้ายไม่น่าจะแก้ drift ได้ (ข้อจำกัดระดับโมเดล ไม่ใช่ API surface) — เก็บไว้อ้างอิงเฉยๆ

**การรีวิวโค้ด — พบ 1 CRITICAL (ยังไม่แก้ รอผู้ใช้ตัดสินใจ) + 1 WARNING (แก้แล้ว)**:

1. **CRITICAL — `main.py`'s `uvicorn.run(..., reload=True)`**: ตรวจพบว่า auto-reload ยังเปิดอยู่จริง
   (บรรทัด 891) หมายความว่าทุกครั้งที่ไฟล์ `.py` ในโฟลเดอร์ backend ถูกแก้ (รวมถึงตอนที่ผมแก้โค้ดให้
   ผู้ใช้ตลอด session นี้เอง) uvicorn จะ kill+restart worker process ทันที ถ้าจังหวะนั้นมี meeting
   กำลัง transcribe จริงอยู่ background task จะถูกฆ่ากลางทางแบบเงียบๆ แล้วพอ
   `_recover_stuck_processing_meetings()` (เขียนเองใน 3.17) รันตอน restart จะ mark เป็น "failed" ทั้ง
   ที่ผู้ใช้ไม่ได้ตั้งใจ restart เลย — **นี่อาจอธิบายส่วนหนึ่งของเคส "processing ค้าง" ที่เจอเองใน
   session ก่อนหน้าด้วย** เพราะมีการแก้ไฟล์ backend หลายรอบระหว่างทดสอบจริงพร้อมกัน — **ยังไม่แก้**
   เพราะกระทบ dev workflow (ปิด reload ต้อง restart เองทุกครั้งที่แก้โค้ด) ต้องถามผู้ใช้ก่อนว่าจะ (a)
   ปิดถาวร (b) ปิดเฉพาะตอนทดสอบ audio จริง หรือ (c) ยอมรับความเสี่ยงไว้ก่อน (อย่างน้อยตอนนี้ fail แบบ
   เห็นชัดแล้ว ไม่ค้างเงียบแบบเดิม) — **ถามแล้ว ผู้ใช้เลือก (c) ยอมรับความเสี่ยงไว้ก่อน** ไม่แก้โค้ด
   คง `reload=True` ไว้ตามเดิม

2. **WARNING → แก้แล้ว — `_recover_stuck_processing_meetings()` ไม่ครอบคลุม `status="uploaded"`**:
   ตรรกะเดิมกรองแค่ `status="processing"` แต่ `status="uploaded"` ค้างตลอดกาลได้ด้วยเหตุผลเดียวกันทุก
   ประการ (FastAPI `BackgroundTasks` dispatch หลังส่ง response แล้ว ถ้า restart ในช่วงสั้นๆ ระหว่างนั้น
   background task จะไม่มีวันเริ่ม) และ `app.js`'s `reuploadBtn` ก็ไม่โชว์ตอน "uploaded" เหมือนกัน (โชว์
   เฉพาะ transcribed/failed) — **แก้แล้ว**: เปลี่ยน filter เป็น
   `Meeting.status.in_(["processing", "uploaded"])` verify ด้วย `py_compile` ผ่าน (ยังไม่ได้ integration
   test ซ้ำแบบ 3.17 เพราะเป็นการขยาย filter ตรงไปตรงมา ไม่ใช่ logic ใหม่)

3. NITPICK — `_recover_stuck_processing_meetings()` ไม่มี try/except รอบ `db.commit()` ถ้า commit fail
   (เช่น disk เต็ม) exception จะ propagate ขึ้นไปทำให้ backend ทั้งตัว crash ตอน startup แทนที่จะแค่ log
   warning แล้วรันต่อ — ตรงกับ pattern เดิมของ `init_db()` ที่ก็ไม่มี defensive handling เหมือนกัน (ไม่ใช่
   pattern ใหม่ที่ผมเพิ่งนำเข้ามา) ยอมรับความเสี่ยงนี้ไว้ก่อนตาม convention เดิมของโปรเจกต์

4. ส่วนอื่นของโค้ด (`audio_native.py` ทั้งไฟล์, `models.py`'s column เพิ่ม, frontend 3 ไฟล์) ตรวจแล้ว
   ไม่พบปัญหาเพิ่มเติม — schema translation จุดเดียว (`_adapt_segments`), error handling ครบ (ทั้ง
   `AudioNativeError`/timeout/fallback), CSS/frontend เป็น additive ล้วนๆไม่กระทบ path เดิม

**VERDICT: NEEDS DISCUSSION** — โค้ดที่แก้ทั้งหมด (adapter, logging fix, model_used tracking, CSS fix)
ผ่านการรีวิวไม่มีปัญหาเชิง correctness เพิ่มเติมนอกจาก `uploaded` gap ที่แก้ไปแล้ว แต่ CRITICAL
`reload=True` ต้องคุยกับผู้ใช้ก่อนตัดสินใจ (ไม่ใช่ AI เลือกปิดเอง) — และเรื่อง timestamp drift ยังคง
เป็นข้อจำกัดของ Gemini เองที่ไม่มีทางแก้ในโค้ดฝั่งเรา มีแค่ lead ใหม่ (ลอง Flash Lite variant) ที่ยัง
ไม่ได้ทดสอบ

**Key Files ของเซสชันนี้**: `backend/main.py` (ขยาย filter ใน `_recover_stuck_processing_meetings()`
เท่านั้น — ไม่แตะไฟล์อื่น), `task.md`, `handoff.md`

**How to resume**: `reload=True` ตัดสินใจแล้ว (ยอมรับความเสี่ยงไว้ก่อน ไม่แก้โค้ด) — งานที่เหลือคือรอ
ผลอัปโหลดไฟล์เดิมซ้ำเรื่อง omission (3.17) และการตัดสินใจทิศทาง Gemini native vs audio_worker (3.19)
เหมือนเดิม — `audio_worker/`/`backend/audio.py` **ยังห้ามลบ**

---

### Session 3.21 — เขียน audio chunking แก้ timestamp drift จริง (2026-08-05)

ผู้ใช้ขอให้ค้นว่าคนอื่นแก้ปัญหา timestamp drift (session 3.19) ยังไง และบอกว่า "พร้อมถึงขั้นเปลี่ยน
วิธี" — ค้นเว็บเจอหลายแหล่งอิสระที่แก้ปัญหาเดียวกันด้วยวิธีเดียวกันตรงกันหมด:

- **Towards Data Science** — บทความทีมที่สร้าง production interview-transcription pipeline ด้วย
  Gemini จริง (2025) รายงานตรงกับที่เราเจอเป๊ะ: "timestamp คลาดเกิน 10 นาทีในไฟล์ 1 ชม.ถ้าส่งทีเดียว"
  แก้ด้วยการตัดไฟล์เป็น chunk 10 นาที overlap 30 วิ ลดคลาดเหลือแค่ 5-10 วิตลอดทั้งชั่วโมง
- **GitHub `jianchang512/pyvideotrans` issue #624** — โค้ดจริงที่ตัด audio ตาม silence detection
  แล้วคำนวณ timestamp เองจาก segment duration แทนที่จะเชื่อ Gemini เลย
- **`madeyexz/youtube2transcripts`** — ตัดไฟล์เป็น chunk 20 นาทีเพราะ token limit เหมือนกัน

สรุปที่มาแบบเต็มอยู่ใน task.md (บรรทัดใกล้ finding เดิมของ session 3.19) — ผู้ใช้เลือก "เริ่มเขียนเลย"
ผ่าน AskUserQuestion (defaults: chunk 10 นาที + overlap 30 วิ)

**เขียนเสร็จแล้ว**:

1. **`backend/audio_chunking.py`** (ไฟล์ใหม่) — `get_duration_seconds()` (ffprobe subprocess, pattern
   เดียวกับ `audio_worker/ffmpeg_utils.py`), `plan_chunks()` (คำนวณ offset/duration ล้วนๆ ไม่พึ่ง
   ffmpeg จริง — unit test ได้ในสภาพแวดล้อมไม่มี ffmpeg), `split_into_chunks()` (ตัดจริงผ่าน ffmpeg
   subprocess, re-encode เป็น 16kHz mono WAV ทุกชิ้น **ไม่ใช้ `-c copy`** เพราะไฟล์ต้นฉบับส่วนใหญ่เป็น
   container บีบอัด ตัดแบบ copy ตรงๆไม่ตรง keyframe ทำให้ไฟล์เพี้ยนได้), `merge_chunk_segments()`
   (ตัดซ้ำที่รอย overlap ด้วย **midpoint cut** — เลือกทางนี้แทน LLM merge แบบที่ TDS ใช้ เพราะง่ายกว่า
   มากและไม่เพิ่มความเสี่ยง hallucination ใหม่ ⚠️ ยอมรับความเสี่ยงตัดกลางประโยคตรงรอย chunk ไว้ตรงๆ —
   เป็น risk class เดียวกับที่โปรเจกต์นี้เคยเจอตอนตัด ASR ด้วยเวลาตายตัวใน audio_worker Module 2 มาก่อน
   แล้ว แต่ยอมรับเพราะเกิดได้แค่ทุก ~9.5 นาทีเท่านั้น ไม่ใช่ทุก segment เหมือนตอนนั้น)

2. **`config.py`** — เพิ่ม `AUDIO_CHUNK_SECONDS=600` (10 นาที, อ้างอิงจาก TDS ที่พบคุณภาพเริ่มเสื่อม
   ราวนาทีที่ 15-20 ของการส่งทีเดียว), `AUDIO_CHUNK_OVERLAP_SECONDS=30`

3. **`audio_native.py`** — แยก `_transcribe_one_file()` ออกมาจาก `transcribe_audio_native()` เดิม
   (แกนกลาง upload+poll+call-with-fallback+cleanup ใช้ร่วมกันได้) `transcribe_audio_native()` **ไม่
   เปลี่ยนพฤติกรรม** (ยังส่งทีเดียวทั้งไฟล์ ใช้โดย `audio_transcription_experiment.py --model` สำหรับ
   เทียบโมเดลเท่านั้น) — `transcribe_meeting_audio()` (production path ที่ `main.py` เรียกจริง) ถูก
   rewrite ให้ orchestrate chunking เต็มรูปแบบ: หาความยาวไฟล์ → ถ้าสั้นกว่า 1 chunk เรียกแบบเดิมตรงๆ
   ไม่ผ่าน ffmpeg เลย (ไม่มี regression/overhead สำหรับประชุมสั้น) → ถ้ายาวกว่า ตัด chunk ผ่าน
   `audio_chunking.split_into_chunks()` แล้ววนเรียก Gemini ทีละ chunk บวก `chunk.offset_seconds` เข้า
   timestamp ที่ได้ก่อน merge — เพิ่ม `_speaker_context_prompt()` ส่ง label ผู้พูดที่เจอมาก่อนหน้าเข้า
   prompt ของ chunk ถัดไป (soft mitigation กัน label สลับข้าม chunk — **ไม่รับประกัน 100%** ไม่มี
   แหล่งไหนที่ค้นมาแก้ปัญหานี้สมบูรณ์แบบเลยแม้แต่ TDS ที่ต้องทำ LLM merge step แยกทั้งอัน) ถ้า chunk
   ไหนล้มเหลวหมดทุก model ถือว่าทั้งการถอดเสียงล้มเหลว (raise ทันที ไม่คืนผลลัพธ์บางส่วนแบบเงียบๆ)

4. **`requirements.txt`** — ไม่มี Python package ใหม่ (เรียก ffmpeg ผ่าน subprocess ตรงๆ) แต่เพิ่ม
   หมายเหตุว่า **backend process ต้องมี ffmpeg ใน PATH แล้วตอนนี้ด้วย** (เดิมมีแค่ audio_worker ที่
   ต้องใช้ — เครื่องที่เคยรัน audio_worker ได้ปกติมี ffmpeg อยู่แล้ว ไม่ต้องติดตั้งเพิ่ม)

**Verify**: `py_compile`/`pyflakes` ผ่านหมดทุกไฟล์ที่แก้ (`audio_chunking.py`, `audio_native.py`,
`config.py`, `main.py`, `audio_transcription_experiment.py` ยังคง import ได้ปกติ) + unit test จริงใน
sandbox (mock ffmpeg/Gemini ทั้งหมด เพราะ sandbox ไม่มี ffmpeg/network ออก Google):
- `plan_chunks()`: ไฟล์สั้นกว่า chunk ไม่ตัดเลย, ไฟล์เท่ากับ chunk พอดีไม่ตัด, ไฟล์ยาวจริง
  `meeting_1.m4a` (3342.7s/55:42) แบ่งได้ 6 chunks ถูกต้อง (offset ห่างกัน step=570s ตามสูตร,
  chunk สุดท้ายสั้นกว่าจบพอดีที่ปลายไฟล์)
- `merge_chunk_segments()`: synthetic 2-chunk overlap scenario — segment ก่อน/หลัง midpoint ถูกเก็บ/
  ตัดถูกต้องทุกกรณี ไม่มี segment ปรากฏซ้ำ
- `transcribe_meeting_audio()` เต็ม flow (mock `_transcribe_one_file`/`audio_chunking.*`): ไฟล์สั้น
  ไม่เรียก `split_into_chunks` เลย, ไฟล์ยาว 2 chunk — offset ถูกบวกเข้า timestamp ถูกต้อง
  (relative 20s + offset 570s = absolute 590s ตรงตามคาด), speaker context ส่งเฉพาะ chunk ที่ 2 เป็น
  ต้นไป, model_used aggregate ถูกต้อง (`"gemini-3.6-flash+gemini-3.5-flash"` ตอนโมเดลต่างกันข้าม
  chunk)

⚠️ **ยังไม่เคย verify กับ Gemini API จริง/ffmpeg จริงบนเครื่อง** (sandbox ไม่มี network ออก Google
ไม่มี ffmpeg ติดตั้ง) — รอผู้ใช้ทดสอบไฟล์ประชุมจริงบนเครื่อง โดยเฉพาะไฟล์ 55 นาทีเดิม
(`backend/uploads/meeting_1.m4a`) เพื่อเทียบ timestamp accuracy กับผลลัพธ์เดิมที่คลาด ~38 นาทีตอนท้าย
ไฟล์ (session 3.19) — **คาดว่า overlap 30 วิจะช่วยลดปัญหา omission (13:46-16:48, session 3.17) ไป
พร้อมกันด้วย** เพราะรอยตัดแบบเดิม (ไม่มี overlap) คือจุดที่เนื้อหาหายง่ายที่สุด แต่ยังไม่ได้ยืนยันจริง

**Key Files ของเซสชันนี้**: `backend/audio_chunking.py` (ใหม่), `backend/audio_native.py` (rewrite
`transcribe_meeting_audio()`+แยก `_transcribe_one_file()`), `backend/config.py` (เพิ่ม config 2 ตัว),
`backend/requirements.txt` (หมายเหตุ ffmpeg), `task.md`, `handoff.md`

**How to resume**: รอผู้ใช้ทดสอบไฟล์จริงบนเครื่อง (ต้องมี ffmpeg ใน PATH ก่อน) เทียบ timestamp
accuracy + เช็คว่า omission หายไปด้วยไหม — ถ้าผลดี น่าจะช่วยเปิดทางให้ตัดสินใจข้อ 7 ของ `/grill-me`
ได้ง่ายขึ้น (เก็บ Gemini native audio ต่อแทนที่ audio_worker ทั้งชุด) แต่ยังต้องรอผลจริงก่อน —
`audio_worker/`/`backend/audio.py` **ยังห้ามลบ**

---

### Session 3.22 — บั๊ก "นาทีที่ 1-10 หายไปเลย" หลัง chunking รอบแรก (2026-08-05)

ผู้ใช้ทดสอบ chunking จริงเป็นครั้งแรกกับไฟล์ประชุมจริงยาว 1:38:45 (screenshot: `model_used =
"gemini-3.6-flash+gemini-3.5-flash"` ยืนยันว่า chunking ทำงาน) รายงานบั๊กใหม่: **"นาทีที่ 1-10
หายไปเลย"** ระหว่างเล่นเสียง/ดู transcript

**วินิจฉัย (mantra 3 — verify ด้วยข้อมูลจริง แทนเดา)**: ดึง `transcript_segments_json` ของ meeting
id=2 จริงจาก `com_sec.db` มาวิเคราะห์ พบว่า **เนื้อหาไม่ได้หายจริง — segment ยังอยู่ครบ 299 อัน แค่
timestamp ผิด**: ลำดับ segment ในช่วงนาทีที่ ~1-9:40 ของไฟล์จริง Gemini คืน `start_seconds`/
`end_seconds` เป็น **หน่วยนาที** (เช่น `1.1`, `9.6`) ไม่ใช่วินาทีตาม schema — segment ก่อน/หลังช่วงนั้น
(0.0-52.4, 52.4-55.4) ยังเป็นวินาทีปกติถูกต้อง คือ Gemini สลับหน่วยกลางคันภายในการตอบครั้งเดียว (คนละ
อาการกับ proportional drift ที่เจอใน session 3.19 แต่ต้นเหตุเดียวกัน: self-reported timestamp ของ
Gemini ไม่น่าเชื่อถือ)

**ต้นเหตุจริงที่ทำให้ "หายไปเลย" คือบั๊กที่ผมเพิ่งใส่เองท้าย session 3.21**: เพิ่ม
`merged.sort(key=lambda seg: seg["start"])` เป็น "safety net" ท้าย `merge_chunk_segments()` (คอมเมนต์
เดิม: "Gemini ควรคืนเรียงอยู่แล้ว") โดยสมมติว่าค่า timestamp เชื่อถือได้เสมอ — พอ Gemini คืนค่าผิดหน่วย
(`1.1` แทนที่จะเป็น `66.0`) sort ก็เอา segment เหล่านั้นไปเรียงแทรกไว้ใกล้ต้นไฟล์ (ระหว่าง `start=0.0`
กับ `start=52.4`) ทำให้เนื้อหาที่ควรอยู่นาทีที่ 1-10 ของไฟล์จริงถูกย้ายไปแสดง timestamp ~0:01-0:09
ทั้งหมด (`formatSeconds()` คิดตามตัวเลขที่มันเป็นตรงๆ) — ผลคือตอน seek เสียงไปนาทีที่ 1-10 จริง ไม่มี
segment ไหนอ้างว่าเริ่มในช่วงนั้นเลย ทำให้ transcript panel ว่างเปล่า ดูเหมือนเนื้อหาหายไปทั้งที่จริง
ข้อความยังอยู่ครบ แค่ label เวลาผิดกลุ่มไปกองอยู่ต้นไฟล์

**แก้แล้ว**: ตัด `.sort()` ออกจาก `merge_chunk_segments()` ทั้งหมด — เหตุผล: ลำดับที่ Gemini คืนมาใน
array (ลำดับการ generate จริง) น่าเชื่อถือกว่าค่าตัวเลข `start_seconds`/`end_seconds` เอง เพราะโมเดล
transcribe ไปตามลำดับเวลาจริงในไฟล์เสมอ ต่อให้บางครั้งใส่หน่วยตัวเลขผิด ลำดับที่ส่งออกมาก็ยังถูกต้อง —
ไม่ sort เลยจึงคง reading order ที่ถูกต้องไว้ได้แม้ timestamp ตัวเลขของ segment ที่โดนบั๊กจะยังผิดอยู่

**Verify**: `py_compile`/`pyflakes` ผ่าน + unit test ใหม่ 2 ตัวใน `audio_chunking.py`: (1) regression
test เดิม (2-chunk overlap ปกติ) ยังผ่านหลังตัด sort ออก (2) test ใหม่จำลองเคส "buggy-minutes" เหมือน
ที่เจอจริง (segment ที่มีค่า start ผิดหน่วยแทรกอยู่กลาง array) ยืนยันว่าลำดับผลลัพธ์คง generation order
เดิมไว้ ไม่ scramble

⚠️ **ยังไม่แก้ (บันทึกไว้ตรงๆ)**: ค่า timestamp ตัวเลขของ segment ที่โดนบั๊กนี้ยังผิดอยู่ (ป้าย MM:SS
ที่โชว์ในหน้า transcript จะยังคลาดเคลื่อนสำหรับ segment ช่วงนั้น แม้เนื้อหา/ลำดับการอ่านจะถูกต้องแล้ว —
click-to-seek/highlight (session 3.15) จะยังไม่ sync ถูกสำหรับ segment เหล่านั้นโดยเฉพาะ) ยังไม่ได้ทำ
unit-detection heuristic (เช่น เจอค่า start กระโดดถอยหลังกะทันหันแล้วลองคูณ 60 ดูว่าใกล้เคียงตำแหน่งที่
ควรจะเป็นไหม แล้ว auto-correct) เพราะเพิ่มความซับซ้อน/ความเสี่ยงเดาผิดเพิ่มเข้าไปอีกชั้น — ยังไม่ได้
คุยกับผู้ใช้ว่าคุ้มจะทำเพิ่มไหม รอดูว่าเกิดถี่แค่ไหนจากการใช้งานจริงต่อไปก่อน

**Key Files**: `backend/audio_chunking.py` (ตัด `.sort()` ออก + เพิ่ม unit test 2 ตัว), `task.md`,
`handoff.md`

**How to resume**: ให้ผู้ใช้ทดสอบซ้ำกับไฟล์เดิม (1:38:45) ดูว่า reading order ถูกต้องแล้วไหม (เนื้อหา
นาทีที่ 1-10 ควรกลับมาแสดงในตำแหน่งที่ถูกต้องของ transcript panel แล้ว แม้ timestamp badge ที่โชว์คู่
กันอาจยังผิดสำหรับบาง segment) — ถ้ายังเจอปัญหา timestamp ผิดหน่วยบ่อยจากการใช้งานจริง ค่อยกลับมาคุย
เรื่อง unit-detection heuristic เพิ่ม

---

### Session 3.23 — ทดลองกู้ข้อมูล scramble ด้วย heuristic (ไม่พอ) → เขียน reset_meeting.py แทน (2026-08-05)

ผู้ใช้ขอ script แก้ DB ตรง แทนที่จะ re-upload ใหม่ — เหตุผล: `gemini-3.6-flash` ใกล้ RPD (requests
per day) limit ของฟรีเทียร์แล้ว (16/20 ตามที่ผู้ใช้ screenshot จาก Google AI Studio) เพราะ chunking
(session 3.21) ทำให้ 1 meeting ยาวเรียก Gemini หลายรอบ (1 call/chunk) แทนที่จะเป็น 1 call/meeting
เหมือนก่อนหน้า — re-upload ไฟล์ 1:38:45 ซ้ำ (~10 chunks) เสี่ยงชน RPD limit กลางทาง

**ทดลอง heuristic กู้ข้อมูลเดิม (meeting id=2) ที่ scramble จาก session 3.22 ก่อน**: เขียน Python
script วิเคราะห์ตรงจาก `com_sec.db` (read-only ใน sandbox) เดา unit ผิด (นาที vs วินาที) จาก
"ความเร็วพูดที่สมเหตุสมผล" (นับตัวอักษรไทย/duration):
- เวอร์ชันหลวม (rate_as_sec > 15 chars/s = flag): จับได้ 52/299 segment **แต่มี false positive** —
  จับ segment ท้ายไฟล์ที่ถูกต้องอยู่แล้ว (เช่น `start=5571.2` ของจริง ถูกจับผิดว่าควรคูณ 60) ถ้ารันจริง
  จะทำข้อมูลที่ถูกอยู่แล้วพังเพิ่ม — **ปฏิเสธเวอร์ชันนี้ทันที**
- เวอร์ชันเข้ม (เพิ่มเงื่อนไข `start×60 ≤ ความยาวไฟล์จริง×1.05` เป็น hard gate กัน false positive):
  ปลอดภัยขึ้น ไม่จับของถูกมาพังซ้ำแล้ว **แต่จับได้แค่ 16/52** segment ที่เสียจริง (segment สั้นๆ 1-3
  คำอย่าง "ได้ค่ะ" มี duration เล็กมาก คำนวณ rate แกว่งสูง เดาหน่วยแม่นๆไม่ได้จากความยาวข้อความอย่าง
  เดียว)

**สรุป: กู้ข้อมูลที่ scramble แล้วให้ถูก 100% เป็นไปไม่ได้จริง** — ต้นเหตุคือลำดับ array ดั้งเดิมจาก
Gemini (ซึ่งถูกต้องเสมอตามลำดับการ generate จริง ต่อให้ตัวเลข timestamp บางอันผิดหน่วย) ถูกเขียนทับ
หายไปแล้วตอน `.sort()` (บั๊กที่แก้ไปแล้วใน session 3.22) — ข้อมูลที่จำเป็นต่อการกู้คืนแม่นยำไม่มีเหลือ
อยู่แล้ว รายงานให้ผู้ใช้ทราบตรงๆ พร้อมตัวเลขชัดเจน (ไม่เสนอ heuristic ที่ไม่น่าเชื่อถือพอเป็นทางแก้จริง)

**ถามผู้ใช้ผ่าน AskUserQuestion** ว่าจะจัดการ meeting นี้ (test data) ยังไง — 3 ทางเลือก: (a) รีเซ็ต
ทิ้ง (ไม่เปลืองเควตา, ข้อมูลถูก 100% หลัง re-upload ใหม่ทีหลัง) (b) แพตช์บางส่วนด้วย heuristic เข้ม
(16/52 ที่มั่นใจสูง เหลือ transcript ไม่สมบูรณ์) (c) re-upload เลยตอนนี้ยอมเสี่ยง quota — **ผู้ใช้เลือก
(a) รีเซ็ตทิ้ง**

**เขียนเสร็จแล้ว**: `backend/scripts/reset_meeting.py` — สคริปต์ maintenance แบบ CLI
(`python scripts/reset_meeting.py <meeting_id> [--yes]`) ให้ผู้ใช้รันเองบนเครื่องจริง (**ไม่ใช่จาก
sandbox** — เขียน DB ตรงจาก sandbox เจอ "disk I/O error" มาก่อนแล้วในเซสชันก่อนหน้า) ใช้
`db.SessionLocal`/`models.Meeting` ตัวเดียวกับที่ `main.py` ใช้จริง (ไม่ใช่ raw SQL ที่เสี่ยง schema
mismatch) แสดงสรุป meeting ก่อนเขียนจริง + ถามยืนยัน (ข้าม prompt ได้ด้วย `--yes`) — set
`status="failed"` + `processing_error` อธิบายเหตุผลชัดเจน + ล้าง `transcript_segments_json`/
`transcription_model_used`/`speaker_mapping_json` เป็น `None` **แต่ไม่ลบ `audio_filename`** (ไฟล์เสียง
ต้นฉบับยังอยู่ใน `uploads/` ไม่ต้องหาไฟล์ใหม่ กด Re-upload เลือกไฟล์เดิมซ้ำได้เลย) — **ไม่เรียก Gemini
เลย ไม่เปลืองเควตา**

**Verify**: `py_compile`/`pyflakes` ผ่าน + รันจริงกับ throwaway temp SQLite DB ในแซนด์บ็อกซ์ (สร้าง
meeting ปลอมด้วย schema เดียวกัน รันสคริปต์ `--yes` แล้ว query กลับมาดูผลลัพธ์) ยืนยันว่า
status/processing_error/clear-fields ทำงานถูกต้องครบ **ไม่ได้รันกับ `com_sec.db` จริงเลย** (ตาม
เหตุผลข้างต้นเรื่อง sandbox เขียน DB ไม่ได้) — ผู้ใช้ต้องรันเองบนเครื่องจริงตาม Usage ในหัวไฟล์สคริปต์

**Key Files**: `backend/scripts/reset_meeting.py` (ใหม่), `task.md`, `handoff.md`

**How to resume**: รอผู้ใช้รัน `python scripts/reset_meeting.py 2` บนเครื่องจริง แล้ว re-upload ไฟล์
1:38:45 ใหม่ (รอ quota ฟื้นถ้าจำเป็น) เพื่อยืนยันว่า sort-scramble bug (3.22) หายจริงกับข้อมูลจริงรอบ
ใหม่ — ยังมีความเสี่ยงที่ Gemini จะใส่หน่วย timestamp ผิดสำหรับบาง segment อีก (ข้อจำกัดที่ยังไม่ได้
แก้ ดู task.md) แต่อย่างน้อยจะไม่ scramble ลำดับการอ่านอีกต่อไป

---

### Session 3.24 — เพิ่มปุ่มเลือกโมเดล Gemini เองตอน upload/re-upload (2026-08-05)

ระหว่างรอทดสอบ reset script ผู้ใช้ส่ง screenshot Google AI Studio rate-limit dashboard เห็นว่า
`gemini-3.6-flash` ใกล้เต็ม RPD ฟรีเทียร์ (16/20) ขณะที่โมเดลอื่น (2.5/3.1 Flash, Flash-Lite ทุกรุ่น)
แทบไม่ได้ใช้เลย (0/20, 0/500) — ขอปุ่มเลือกโมเดลเองตอน upload/re-upload พร้อมลำดับที่ต้องการชัดเจน:
3.6 Flash → 3.5 Flash → 3.5 Flash-Lite → 3.1 Flash → 3.1 Flash-Lite → 2.5 Flash → 2.5 Flash-Lite

**เขียนเสร็จแล้ว — mirror pattern เดียวกับ multi-template ทุกจุด** (`docx_generation.TEMPLATE_REGISTRY`/
`GET /api/templates`/`loadTemplateOptions()`):

1. **`config.py`** — เพิ่ม `GEMINI_TRANSCRIPTION_MODEL_CHOICES` เป็น ordered list ของ
   `(model_id, label)` ตามลำดับที่ผู้ใช้ระบุเป๊ะ (ไม่ใช่ลำดับ version number) — หมายเหตุกำกับไว้ว่า
   โมเดลที่ทดสอบยิงจริงแล้วมีแค่ `gemini-3.6-flash`/`gemini-3.5-flash` (session 3.13-3.14) ตัวอื่นตาม
   naming convention เดียวกันแต่ยังไม่เคยยิงจริง

2. **`main.py`** — เพิ่ม `GET /api/transcription_models` คืน `{models: [{value, label}], default}`
   (mirror `list_templates()` เป๊ะ) — `POST /api/meetings/{id}/upload` เพิ่ม param `model: str | None
   = Form(None)` validate เทียบ whitelist จริงเสมอ (400 ถ้าไม่ตรง ไม่เชื่อ dropdown ฝั่ง client เฉยๆ)
   thread ผ่าน `_process_meeting_audio_background()` (เพิ่ม param `model_override`) →
   `transcribe_meeting_audio(..., model_override=...)`

3. **`audio_native.py`** — `transcribe_meeting_audio()` เพิ่ม `model_override: str | None = None`
   thread ผ่านทั้ง 2 call site ของ `_transcribe_one_file()` (short-file path ที่ไม่ chunk และ
   chunked loop) — ถ้าระบุ **ไม่มี fallback chain เลยสำหรับทุก chunk** (ใช้ semantics เดิมของ
   `_transcribe_one_file()`'s `model_override` อยู่แล้ว) ตั้งใจแบบนี้เพราะจุดประสงค์คือหลบโมเดลที่
   โควต้าใกล้เต็ม — silent fallback กลับไปโมเดลที่กำลังหลบอยู่จะขัดจุดประสงค์ ไม่ระบุ = พฤติกรรมเดิม
   ทุกประการ (ไม่กระทบ path เดิมเลยถ้าไม่ใช้ฟีเจอร์นี้)

4. **`app.js`** — เพิ่ม `getModelOptionsHtml()` (fetch+cache module-level ครั้งเดียว เพราะ dashboard
   เรียกใช้ต่อแถว หลาย meeting พร้อมกัน ต่างจาก `loadTemplateOptions()` ที่มีจุดเดียวไม่ต้อง cache)
   เพิ่ม `<select class="model-select">` ข้างปุ่ม Upload/Re-upload ใน `actionCellHtml()` (dashboard,
   populate async หลัง DOM สร้างเสร็จใน `renderMeetingsTable()` เพราะ `actionCellHtml()` เป็น sync)
   `triggerUpload()` อ่านค่าจาก sibling `.model-select` (ผ่าน `btn.parentElement`) ใส่ลง FormData
   field `model` ถ้าเลือกไว้ — เพิ่ม `#reupload-model-select` ใน `meeting-detail.html` (แสดง/ซ่อน
   พร้อม `reupload-audio-btn` เสมอใน `loadMeetingDetail()`, populate ครั้งเดียวเช็ค `.innerHTML` ว่าง
   ก่อนกัน re-fetch ทุกรอบ poll) `triggerReuploadOnDetailPage()` อ่านค่าใส่ FormData เหมือนกัน

**Verify**: `py_compile`/`pyflakes` ผ่านทุกไฟล์ backend + **FastAPI TestClient integration test เต็ม**
(mock `transcribe_meeting_audio` กัน Gemini/ffmpeg จริง, ใช้ throwaway temp SQLite DB): (1)
`GET /api/transcription_models` คืนลำดับ 7 โมเดลตรงตามที่ผู้ใช้ระบุ + `default="gemini-3.6-flash"`
ถูกต้อง (2) upload ไม่ระบุ `model` field เลย ยังทำงานได้ปกติ (regression check — ไม่กระทบ path เดิม)
(3) upload ระบุ `model="gemini-2.5-flash-lite"` thread ผ่านจนบันทึกลง `transcription_model_used`
ถูกต้องตรงกับที่เลือก (4) upload ระบุ model ปลอม (`"gpt-4o-not-a-real-gemini-model"`) ได้ 400 ตามคาด
— frontend: `node --check` ผ่าน `app.js`, `HTMLParser` ผ่าน `meeting-detail.html` (ไม่มี malformed
tag) **ยังไม่เคย verify จริงในเบราว์เซอร์** (sandbox ไม่มีเบราว์เซอร์ให้ทดสอบ UI จริง)

**Key Files**: `backend/config.py` (เพิ่ม `GEMINI_TRANSCRIPTION_MODEL_CHOICES`), `backend/main.py`
(เพิ่ม endpoint + upload param + background task param), `backend/audio_native.py` (เพิ่ม
`model_override` param), `ComSecAI_Dashboard/app.js` (เพิ่ม `getModelOptionsHtml()`/dropdown 2 จุด),
`ComSecAI_Dashboard/meeting-detail.html` (เพิ่ม `#reupload-model-select`), `task.md`, `handoff.md`

**How to resume**: ผู้ใช้บอกว่าจะ re-upload ไฟล์ใหม่ทดสอบเองแล้ว (ไม่ต้องรัน `reset_meeting.py` ก็ได้
ถ้าเลือก re-upload ตรงๆ — ทับ meeting id=2 เดิมได้เลยผ่าน `POST .../upload` ปกติ ไม่ต้อง reset ก่อนก็
ได้เพราะ endpoint นี้ทับข้อมูลเก่าอยู่แล้ว) — ให้ทดสอบทั้ง 2 เรื่องพร้อมกันในรอบเดียว: (1)
sort-scramble bug (3.22) หายจริงไหม (2) เลือกโมเดลใหม่ (เช่น Flash-Lite ที่ยังไม่เคยทดสอบจริง — ตาม
research session 3.20 มีรายงานว่า timestamp แม่นกว่า Pro/Flash ตัวเต็มด้วย) ทำงานถูกต้องจริงในเบราว์เซอร์
ไหม ยังไม่เคย verify UI จริงเลยสักจุดของฟีเจอร์นี้

---

### 3.25 — เขียนสคริปต์เปรียบเทียบ 7 โมเดล Gemini พร้อมกัน (2026-08-05)

ผู้ใช้ขอ: "ช่วยทำทดสอบเพื่อนำมาเปรียบเทียบหน่อยสิระหว่างแต่ละโมเดลที่เราจะเอามาใช้งานจริง ... ทำสคริปทดสอบ
ส่งไฟล์เดียวกัน 10 นาที ไปทุกโมเดลและเอาผลลัพธ์ออกมาเทียบดูหน่อย เพราะถ้ารับได้อาจจะรันแบบคู่ขนานได้"
— ต่อยอดจาก session 3.20 ที่พบ lead ว่า "Flash Lite" อาจแม่นกว่า "Pro"/"Flash" ตัวเต็มเรื่อง timestamp
drift แต่ยังไม่เคยทดสอบจริง

**เขียนเสร็จแล้ว**: `backend/scripts/compare_transcription_models.py` (ไฟล์ใหม่)
- `--audio` (required, ไฟล์เดียว แนะนำ ~10 นาที), `--models` (comma-separated, default = ทุกตัวใน
  `config.GEMINI_TRANSCRIPTION_MODEL_CHOICES` — 7 ตัวตามลำดับที่ผู้ใช้ระบุไว้ session 3.24), `--parallel`
  (flag เปิดโหมดยิงพร้อมกันด้วย `ThreadPoolExecutor`), `--output-dir` (default
  `model_comparison_results/`)
- เรียก `transcribe_audio_native(audio_path, model_override=model_id, log=log)` ตรงๆต่อโมเดล **ไม่ผ่าน
  `transcribe_meeting_audio()`** (ไม่ chunk เพราะไฟล์ 10 นาทีสั้นกว่า `AUDIO_CHUNK_SECONDS` (600s)
  อยู่แล้วพอดี ไม่ถูกตัดอยู่แล้วแม้จะใช้ทางนั้น — เลือกฟังก์ชันตรงกว่า/ง่ายกว่าแทน) **ไม่มี fallback
  chain** ต่อโมเดล (เหมือน production path ที่เลือกโมเดลเอง — ต้องการวัดผลแต่ละโมเดลจริงๆ ไม่อยากให้
  fallback ไปโมเดลอื่นแล้ววัดผิดตัว)
- `_run_one_model()` ครอบ `try/except AudioNativeError` + `except Exception` กว้างรอบนอกอีกชั้น — ตั้งใจ
  กว้างเพื่อกันโมเดลหนึ่ง fail (โควต้าเต็มพอดี/model id ไม่มีจริง) แล้วทำให้ future อื่นที่กำลังรันขนาน
  อยู่ใน `ThreadPoolExecutor` พังตามหรือถูกยกเลิกไปด้วย — คืน dict ที่มี `success: False` +
  `error` message แทนแทนที่จะ raise ออกไป
- `run_comparison()` แยก orchestration logic ออกจาก `main()`/argparse เพื่อ unit test ได้ — คืน
  `(results, total_elapsed)`; parallel mode ใช้ `concurrent.futures.as_completed()` แล้ว **sort กลับ
  ตามลำดับ `model_ids` เดิมเสมอ** ก่อน return (ThreadPoolExecutor คืนผลไม่เรียงตามเวลาที่ยิงจริง —
  ถ้าไม่ sort กลับ ตารางสรุป/ไฟล์ผลลัพธ์จะสลับลำดับไปมาตามความเร็วของแต่ละโมเดล อ่านเทียบยาก)
- เก็บต่อโมเดล: เวลาที่ใช้, จำนวน segment, จำนวนตัวอักษรรวม, จำนวน+รายชื่อ speaker ที่เจอ, segment เต็ม
  ทั้งหมด (start/end/speaker/text) → เขียนเป็น JSON แยกไฟล์ต่อโมเดล (`write_results()`) + พิมพ์ตารางสรุป
  เชิงปริมาณ (`print_summary_table()`) — **หมายเหตุกำกับไว้ในสคริปต์เอง**: ตัวเลขเชิงปริมาณ
  (segment/ตัวอักษร/speaker count) ไม่ได้บอกคุณภาพเนื้อหา ยังต้องเปิด JSON อ่านเทียบข้อความ/timestamp/
  speaker label ด้วยตาเองว่าโมเดลไหนถอดผิด/ตกหล่นน้อยกว่ากัน

**ต้องรันบนเครื่องจริงของผู้ใช้เท่านั้น** (sandbox ไม่มี network ออก Google เลย)

**Verify**: `py_compile`/`pyflakes` ผ่าน + เขียน mock-based orchestration test เต็ม (mock
`transcribe_audio_native` ให้ `gemini-3.1-flash` throw `AudioNativeError` จำลอง และ
`gemini-3.1-flash-lite` throw `RuntimeError` จำลอง ตัวอื่นสำเร็จปกติด้วย fake segment data):
(1) sequential mode คืนผลตามลำดับ `model_ids` ที่ส่งเข้ามาเป๊ะ, ทั้ง 2 โมเดลที่ fail ถูก isolate ไม่กระทบ
โมเดลอื่น (2) parallel mode เรียกครบทุกโมเดลจริง (เช็คจาก call log) แล้ว sort กลับมาเรียงลำดับเดิม
เหมือน sequential ทุกประการแม้จะเสร็จไม่ตามลำดับจริง (3) `write_results()` เขียนไฟล์ JSON ครบทุกโมเดล
เนื้อหาถูกต้อง (4) `print_summary_table()` พิมพ์ตารางไม่ error ครอบคลุมทั้งเคสสำเร็จและ fail — **ทุก
assertion ผ่านหมด** — **ยังไม่เคยยิง Gemini จริงสักครั้ง** (ทั้งการเทียบผลลัพธ์เชิงคุณภาพและการทดสอบว่า
รันขนานจริงชนกันไหมในระดับ API ต้องรอผู้ใช้รันเองบนเครื่องจริง)

**Key Files**: `backend/scripts/compare_transcription_models.py` (ใหม่ทั้งไฟล์), `task.md`,
`handoff.md`

**How to resume**: ผู้ใช้ต้องเตรียมไฟล์เสียงทดสอบ ~10 นาที แล้วรัน:
```
cd backend
python scripts/compare_transcription_models.py --audio path/to/10min_test.wav --parallel
```
ดูตารางสรุป + เปิด `model_comparison_results/<model>.json` แต่ละไฟล์เทียบเนื้อหาเอง แนะนำให้สังเกตเป็น
พิเศษว่า Flash Lite variant (`gemini-3.5-flash-lite`/`gemini-3.1-flash-lite`/`gemini-2.5-flash-lite`)
มี timestamp แม่นกว่าจริงไหมตาม lead จาก session 3.20 — ถ้าพบว่าใช่ อาจพิจารณาเปลี่ยน
`config.GEMINI_MODEL_TRANSCRIPTION` (default model) เป็น Flash Lite แทน Flash เต็มตัว และประเมินด้วยว่า
`--parallel` ยิง 7 โมเดลพร้อมกันจาก API key เดียวติด rate limit (429) ไหม — ถ้าไม่ติดเลยอาจเปลี่ยนมาใช้
แนวทางรัน 2-3 โมเดลพร้อมกันจริงในโปรดักชันแล้วให้ผู้ใช้เลือกผลที่ดีที่สุดเอง (ผู้ใช้พูดถึงไอเดียนี้ตอนขอ
feature — "เพราะถ้ารับได้อาจจะรันแบบคู่ขนานได้") แต่ยังไม่ได้ตัดสินใจ/ออกแบบส่วนนั้นจริง เป็นแค่แนวคิดที่
รอผลทดสอบนี้ก่อน

### 3.26 — เพิ่ม `--delay` + ตารางเทียบทีละวินาที + `/scrutinize` (2026-08-05)

ผู้ใช้ขอไฟล์ทดสอบก่อน ("ไฟล์เสียง 10min อยู่ไหน?") → ตัดคลิป 10 นาทีสุดท้ายจาก `meeting_2.m4a`
(duration จริง 5925.6s) ด้วย `ffmpeg -sseof -600 -t 600 -ar 16000 -ac 1` (re-encode ไม่ใช้ `-c copy`
ตามธรรมเนียมเดียวกับ `audio_chunking.py::split_into_chunks()` — กันปัญหาตัด container บีบอัดที่ไม่ตรง
keyframe) → `backend/test_audio/meeting_2_last10min.wav`

จากนั้นผู้ใช้ขอ 3 อย่างพร้อมกัน: "แก้ไขอีกครั้งเพิ่ม delay เข้าไปหน่อย แล้วจะรันทดสอบอีกครั้ง" +
"ได้ผลลัพธ์แล้วทำเป็นตารางเทียบต่อวินาทีออกมาหน่อย" + `/scrutinize`

**1) `--delay` (ใหม่)**: หน่วงก่อนเริ่มงานของโมเดลที่ 2 เป็นต้นไป (ไม่หน่วงก่อนตัวแรก) ดีฟอลต์ 0.0 = ไม่
กระทบพฤติกรรมเดิมเลย — sequential mode หน่วงจริงระหว่างรอผลก่อนยิงตัวถัดไป, parallel mode หน่วงแค่
จังหวะ `submit()` ให้แต่ละงานเริ่มเหลื่อมกัน (ยังคงขนานกันจริงในเธรดของมันเอง ไม่ได้กลายเป็น sequential)
— เหตุผล: โควต้า Gemini free tier มักมีทั้ง RPD (เจอแล้วจาก session 3.23) และ RPM แยกกัน ยิง 7 โมเดล
พร้อมกันในเสี้ยววินาทีเดียวอาจชน RPM burst ได้ทั้งที่ RPD ยังไม่เต็ม — `run_comparison()` เพิ่ม
`delay_seconds`/`_sleep` (dependency injection ของ `time.sleep` เพื่อ unit test จังหวะ delay ได้โดยไม่
ต้องรอเวลาจริง)

**2) ตารางเทียบทีละวินาที (ใหม่)**: `_determine_total_seconds()` (ใช้ `audio_chunking.get_duration_seconds()`
เป็นหลัก, fallback เป็นค่า `end` มากสุดจาก segment ถ้า ffprobe ใช้ไม่ได้) → `build_second_by_second_table()`
(แต่ละแถว=1วินาที, แต่ละคอลัมน์=1โมเดล, ค่า=`[speaker] ข้อความ` ของ segment ที่ครอบคลุมวินาทีนั้น ตัด
สั้นถ้ายาวเกิน, ว่างถ้าไม่มี segment ไหนครอบคลุม — **ไม่ sort segment ซ้ำ ใช้ลำดับที่ Gemini คืนมาตรงๆ**
บทเรียนจาก sort-scramble bug session 3.22) → `write_second_by_second_csv()` เขียนเป็น
`comparison_by_second.csv` ด้วย `utf-8-sig` (มี BOM กัน Excel เปิดอักษรไทยเพี้ยน) เปิดดูใน Excel เทียบ
แนวนอนได้ทันทีว่าแต่ละโมเดล transcribe ตรงกันไหมที่วินาทีเดียวกัน

**3) `/scrutinize` — พบ 2 WARNING จริง แก้ทั้งคู่**:
- **CSV/formula injection** (เชิงป้องกัน): Excel ตีความเซลล์ที่ขึ้นต้นด้วย `= + - @` เป็นสูตรแทนข้อความ
  ธรรมดา — ถ้าคำที่ Gemini transcribe ออกมาขึ้นต้นด้วยเครื่องหมายพวกนี้พอดี (หรือ speaker label ผิดปกติ)
  อาจทำให้ Excel error/พยายามรันเป็นสูตร — เพิ่ม `_csv_safe()` เติม `'` นำหน้าถ้าขึ้นต้นด้วยอักขระเสี่ยง
  **ตรวจแล้วว่าปัจจุบันยังไม่ใช่ช่องโหว่จริง** เพราะ cell format คือ `f"[{speaker}] {text}"` ขึ้นต้นด้วย
  `[` เสมออยู่แล้ว — ใส่ `_csv_safe()` ไว้เป็น defense-in-depth เผื่อ format เปลี่ยนในอนาคต (ยืนยันด้วย
  unit test ว่า cell ยังขึ้นต้นด้วย `[` เหมือนเดิม)
- **`--models ""` + `--parallel` crash**: ถ้าทุก token ว่างหมดหลัง `.strip()` จะได้ `model_ids = []` แล้ว
  `ThreadPoolExecutor(max_workers=0)` raise `ValueError` ที่อ่านไม่รู้เรื่อง — เพิ่ม guard เช็ค
  `model_ids` ว่างใน `main()` แล้ว exit พร้อมข้อความอธิบายก่อนถึงจุดนั้น

**Verdict จาก scrutinize**: APPROVE (หลังแก้ 2 WARNING ข้างต้นแล้ว) — จุดอื่นที่ตรวจแล้วไม่พบปัญหา: การวัด
เวลาต่อโมเดล (`elapsed_seconds` ใน `_run_one_model()`) ไม่ปนกับเวลา delay เพราะ sleep เกิดนอก timer
window, `_determine_total_seconds()` catch เฉพาะ `audio_chunking.FFmpegError` ถูกต้องครบ (ตรวจ
`get_duration_seconds()`/`_run_ffmpeg()` แล้วว่า wrap `FileNotFoundError` เป็น `FFmpegError` เสมอ ไม่มี
exception หลุดออกมาแบบดิบ), delay=0 ไม่มีพฤติกรรมเปลี่ยนจากเดิมเลย (regression-tested) — ข้อจำกัดที่รู้
อยู่แล้วไม่ใช่บั๊ก (บันทึกไว้ในโค้ด): ถ้า segment ของโมเดลเดียวกันคาบเกี่ยวกันเอง (เช่น พูดแทรก) ตาราง
แสดงได้แค่ speaker เดียวต่อวินาทีต่อโมเดล (segment แรกที่เจอ "ชนะ")

**Verify**: `py_compile`/`pyflakes` ผ่าน + mock unit test เต็มทั้งฟีเจอร์ใหม่และ fix จาก scrutinize
(delay stagger sequential/parallel ทั้งค่า >0 และ =0, `build_second_by_second_table` ครอบคลุม
gap/truncate/failed-model, `write_second_by_second_csv` BOM+เนื้อหาถูกต้อง, `_determine_total_seconds`
ทั้ง happy path และ fallback, `_csv_safe` ทุกอักขระเสี่ยง, empty-models guard) — **ยังไม่เคยยิง Gemini
จริงสักครั้ง** เช่นเดิม (sandbox ไม่มี network ออก Google)

**Key Files**: `backend/scripts/compare_transcription_models.py` (แก้เพิ่ม), `backend/test_audio/`
(ใหม่ — ไฟล์ทดสอบ), `task.md`, `handoff.md`

**How to resume**: ผู้ใช้รัน
`python scripts/compare_transcription_models.py --audio test_audio/meeting_2_last10min.wav --parallel --delay <n>`
เอง (ต้องเลือกค่า delay เอง ยังไม่มีค่าที่ทดสอบแล้วว่าพอดี — แนะนำเริ่มจาก 1-2 วินาทีแล้วดูว่ายังชน 429
ไหม) ดูตาราง `comparison_by_second.csv` เทียบใน Excel + `model_comparison_results/<model>.json` เทียบ
เนื้อหาเต็ม

**ผลทดสอบจริงรอบแรก (2026-08-05, ผู้ใช้รันจริงแล้ว)** — ไฟล์ `meeting_2_last10min.wav` (600s):

| โมเดล | สถานะ | เวลา(s) | Segments | Chars | Speakers | Drift (last-end vs 600s จริง) |
|---|---|---|---|---|---|---|
| gemini-3.6-flash | ✅ | 82.9 | 87 | 6057 | 4 | +26.5% (759s) — **น้อยสุดในกลุ่มที่สำเร็จ** |
| gemini-3.5-flash | ✅ | 95.7 | 64 | 5000 | 4 | +38.7% (832s) |
| gemini-3.5-flash-lite | ✅ | 43.6 | 123 | 10984 | 2 ⚠️ | +66.3% (998s) — **แย่สุด** |
| gemini-3.1-flash-lite | ✅ | 28.9 | 84 | 6953 | 2 ⚠️ | +48.4% (891s) |
| gemini-2.5-flash | ✅ | 107.9 | 164 | 7133 | 8 ⚠️ | +59.9% (959s) |
| gemini-2.5-flash-lite | ❌ 503 UNAVAILABLE (server โหลดสูงชั่วคราว) | 190.7 | - | - | - | - |
| gemini-3.1-flash | ❌ 404 NOT_FOUND (**model ID นี้ไม่มีอยู่จริงใน Gemini API**) | 7.3 | - | - | - | - |

**Key findings**:
1. **ขัดแย้งกับ research รอบก่อน (session 3.20)** ที่รายงานว่า "Flash Lite" ตระกูล drift น้อยกว่า — ผล
   จริงกลับตรงข้าม: `3.5-flash-lite`/`3.1-flash-lite` drift แย่กว่า `3.6-flash`/`3.5-flash` ตัวเต็ม
   ชัดเจน (ตัวอย่าง n=1 ไฟล์เดียว ยังสรุปเป็น universal claim ไม่ได้ แต่หักล้าง assumption เดิมพอสมควร)
2. **`gemini-3.1-flash` ไม่มีอยู่จริง** (404) — ชื่อที่เดาไว้ตาม naming convention ใน
   `config.GEMINI_TRANSCRIPTION_MODEL_CHOICES` ผิด ต้องลบออกหรือหาชื่อจริงมาแทน (ยังไม่ได้แก้ — รอ
   ผู้ใช้ยืนยัน)
3. **`speaker_count` แกว่งมาก (2-8 คน) กับไฟล์เดียวกัน** — `3.5-flash-lite`/`3.1-flash-lite` น่าจะ
   under-diarize (รวมคนพูดหลายคนเป็น 2 label), `2.5-flash` น่าจะ over-diarize/hallucinate (8 label) —
   `3.6-flash`/`3.5-flash` เจอ 4 คนตรงกัน น่าเชื่อถือกว่า (cross-validate กันเอง)
4. `gemini-2.5-flash-lite` ล้มเหลวเพราะ Google server โหลดสูงชั่วคราว (503) ไม่ใช่ปัญหาโค้ด/config —
   ต้องลองแยกใหม่ก่อนตัดสินว่าใช้ได้จริงไหม
5. ยังไม่ได้ฟังไฟล์เสียงจริงเทียบความถูกต้องของเนื้อหา (ตัวเลขข้างบนเป็น proxy เชิงปริมาณ ไม่ใช่ accuracy
   จริง) — ยังต้องอ่าน/ฟังเทียบเองเพื่อตัดสินใจสุดท้าย

### 3.27 — แก้ `gemini-3.1-flash` → `gemini-3-flash` (2026-08-05)

ผู้ใช้ยืนยัน: "3.1-flash — ไม่มีโมเดลนี้อยู่จริง ต้องเป็น 3 Flash" (ตรงกับผลทดสอบ 404 NOT_FOUND ใน 3.26)
— แก้ `config.GEMINI_TRANSCRIPTION_MODEL_CHOICES` เปลี่ยน `("gemini-3.1-flash", "Gemini 3.1 Flash")`
เป็น `("gemini-3-flash", "Gemini 3 Flash")` ตำแหน่งเดิมในลิสต์ (ไม่กระทบลำดับที่ผู้ใช้ระบุไว้) —
`gemini-3.1-flash-lite` **ไม่แตะ** เพราะทดสอบจริงแล้วว่าเรียกได้ (success ใน 3.26) ไม่ใช่ปัญหาเดียวกัน —
อัปเดตคอมเมนต์เหนือลิสต์ให้ตรงกับสถานะ verify จริงล่าสุด (5/7 โมเดลยืนยันเรียกได้จริงแล้ว, 1 โมเดล
เปลี่ยนชื่อยังไม่เคย verify ซ้ำ, 1 โมเดลเจอ 503 ชั่วคราวยังสรุปไม่ได้)

**Verify**: `py_compile`/`pyflakes` ผ่าน + เช็คด้วย python จริงว่า `GEMINI_TRANSCRIPTION_MODEL_CHOICES`
มี `gemini-3-flash` และไม่มี `gemini-3.1-flash` หลงเหลืออยู่, ยังมีครบ 7 รายการ — **ยังไม่เคยยิง
`gemini-3-flash` ตัวใหม่ผ่าน Gemini จริง** ผู้ใช้ต้องรัน `compare_transcription_models.py` ซ้ำอีกรอบ
(หรือ upload/re-upload เลือกโมเดลนี้ตรงๆ) เพื่อยืนยันว่าชื่อใหม่ถูกจริง

**Key Files**: `backend/config.py`, `task.md`, `handoff.md`

**How to resume**: รัน `compare_transcription_models.py` ซ้ำ (มี `--models gemini-3-flash` เจาะจงตัวเดียว
ก็ได้ ไม่ต้องรันครบ 7 ตัวใหม่ทั้งหมด) เพื่อยืนยันว่า `gemini-3-flash` เรียกได้จริง + ลองแยก
`gemini-2.5-flash-lite` อีกรอบดูว่า 503 เดิมเป็นแค่ transient หรือมีปัญหาอื่นจริง

### 3.28 — เพิ่ม sample size: ตัดไฟล์ทดสอบอีก 2 ไฟล์ + `compare_transcription_models_batch.py` (2026-08-05)

ผู้ใช้ถามว่า research เดิม (เรื่อง Flash Lite แม่นกว่า) อาจล้าสมัยหรือเงื่อนไขต่างกัน — ตอบไปว่าข้อมูลเรา
เอง (n=1 ไฟล์) น่าเชื่อกว่าสำหรับเงื่อนไขงานจริง แต่ n=1 ยังไม่พอฟันธง — ผู้ใช้ตอบ "เขียนสคลิปทดสอบได้เลย
เริ่มจาก ตัดไฟล์เพิ่มอีก 2 ไฟล์ก่อน"

**ตัดไฟล์ทดสอบเพิ่ม 2 ไฟล์** (16kHz mono WAV, re-encode ไม่ใช้ `-c copy` เหมือนเดิม) จาก `meeting_1.m4a`
(ยังไม่เคยใช้มาก่อน — คนละไฟล์กับ `meeting_2` ที่ใช้ตัด clip แรก เพิ่มความหลากหลายของ sample จริงๆ ไม่ใช่
แค่สุ่ม timestamp ต่างกันในไฟล์เดิม):
- `test_audio/meeting_1_first10min.wav` (0:00-10:00, ช่วงเปิดประชุม)
- `test_audio/meeting_1_last10min.wav` (10 นาทีสุดท้าย, ช่วงปิดประชุม — mirror กับที่ตัด `meeting_2` ไว้)

รวมกับ `meeting_2_last10min.wav` เดิม = 3 clip ครอบคลุมทั้งช่วงเปิด/ปิดประชุม จาก 2 ไฟล์ต้นฉบับที่ต่างกัน

**`backend/scripts/compare_transcription_models_batch.py`** (ไฟล์ใหม่) — รันเปรียบเทียบโมเดลข้ามหลาย
ไฟล์รวดเดียว แล้วรวม **drift ratio** (`max(segment end)/ความยาวไฟล์จริง` — 1.0=ไม่ drift, ยิ่งมากยิ่ง
คลาดสะสม) ของแต่ละโมเดลเป็นตารางเดียวข้ามไฟล์ (mean/min/max) — **reuse ฟังก์ชันจาก
`compare_transcription_models.py` ตรงๆ** (`import scripts.compare_transcription_models as single` แล้ว
เรียก `single.run_comparison()`/`write_results()`/`build_second_by_second_table()`/
`write_second_by_second_csv()` เดิมทุกอย่างต่อไฟล์ ไม่ copy logic ซ้ำ) — รันไฟล์ทีละไฟล์ (ไม่ขนานข้าม
ไฟล์ — เจตนา: `--parallel`/`--delay` คุมแค่ความขนานระหว่างโมเดลภายใน 1 ไฟล์ ยิงหลายไฟล์พร้อมกันจะเพิ่ม
ความเสี่ยง rate limit ซ้อนกันแบบคาดเดาไม่ได้) ผลลัพธ์แต่ละไฟล์แยกโฟลเดอร์ย่อย
(`model_comparison_results/<ชื่อไฟล์>/...`) + สรุปรวม `batch_drift_summary.csv`

**Verify**: `py_compile`/`pyflakes` ผ่าน + mock test เต็ม (จำลอง 2 ไฟล์ × 3 โมเดล — `m_good` drift 10%,
`m_bad` drift 60%, `m_fail` fail ทุกไฟล์): `run_batch()` คืนโครงสร้างถูกต้อง, โมเดล fail ถูก isolate
(`drift_ratio=None` ไม่ใช่ 0 หรือ crash), สร้างโฟลเดอร์ย่อยต่อไฟล์ครบ (JSON+CSV), `build_aggregate_table()`
คำนวณ mean/min/max ถูกต้อง (รวมถึงกรณีโมเดล fail หมดได้ `None` ไม่ใช่ error), `write_aggregate_csv()`
เขียน BOM ถูกต้อง, `print_aggregate_table()` ไม่ crash เวลาเจอค่า `None` — **ยังไม่เคยยิง Gemini จริง**
เช่นเดิม

**Key Files**: `backend/scripts/compare_transcription_models_batch.py` (ใหม่), `backend/test_audio/`
(เพิ่ม 2 ไฟล์), `task.md`, `handoff.md`

**How to resume**: ผู้ใช้รัน
```
cd backend
python scripts/compare_transcription_models_batch.py --audio test_audio/meeting_2_last10min.wav test_audio/meeting_1_first10min.wav test_audio/meeting_1_last10min.wav --parallel --delay 1.5
```
ดู `model_comparison_results/batch_drift_summary.csv` — ถ้า `gemini-3.6-flash` ยัง drift น้อยสุดตรงกัน
ทั้ง 3 ไฟล์ (ไม่ใช่แค่ไฟล์เดียวเหมือนรอบก่อน) จะเริ่มมั่นใจได้มากขึ้นว่าไม่ใช่ความบังเอิญของไฟล์เดียว —
ถ้าผลสลับกันไปมาระหว่างไฟล์ แปลว่ายังต้องมี sample เพิ่มอีกก่อนตัดสินใจเลือกโมเดล production จริง

⚠️ **บั๊กจริงที่พบตอนผู้ใช้รันจริง (2026-08-05)**: `ModuleNotFoundError: No module named
'scripts.compare_transcription_models'` — โค้ดเดิม `import scripts.compare_transcription_models as
single` (namespace package import) รันผ่านปกติใน sandbox (Linux) ตอน verify แต่พังจริงบน Windows
(เครื่องผู้ใช้) — sandbox verify ไม่จับบั๊กนี้เพราะ mock test เดิมรัน logic ผ่านการ `import` แบบ manual
ใน `python3 -` heredoc (ตั้ง sys.path เอง) ไม่ใช่การรันไฟล์สคริปต์ตรงๆแบบผู้ใช้จริง — **แก้โดยเปลี่ยนเป็น
`import compare_transcription_models as single`** (sibling import ตรงๆ ไม่มี `scripts.` prefix เลย —
ใช้ประโยชน์จากที่ Python ใส่โฟลเดอร์ของสคริปต์หลักลง `sys.path[0]` ให้อัตโนมัติเวลารันตรงๆอยู่แล้ว เหมือน
ที่ `compare_transcription_models.py` เอง import `audio_native` แบบไม่มี prefix) — verify ซ้ำด้วยการรัน
**subprocess จริง** (`python3 scripts/compare_transcription_models_batch.py --help` และอีก 2 เคส:
ไม่มี API key / ไฟล์ไม่มีจริง) แทนการ mock import ให้ตรงกับวิธีที่ผู้ใช้รันจริงมากขึ้น — บทเรียน: การ
verify script แบบ standalone (`python scripts/xxx.py`) ต้องทดสอบด้วยการรัน subprocess จริงอย่างน้อย 1
ครั้งเสมอ ไม่ใช่แค่ import module ภายใน process เดียวกันแล้วเชื่อว่าเหมือนกัน (สอง path ต่างกันจริงเรื่อง
sys.path[0]/namespace package resolution โดยเฉพาะข้าม OS)

### 3.29 — ผลจริงจาก batch (3 ไฟล์) — ไม่มีผู้ชนะชัดเจน, พบบั๊กซ้ำที่ `gemini-3-flash` (2026-08-05)

**ผลสรุป (`batch_drift_summary.csv`, 3 ไฟล์: meeting_1_first10min/meeting_1_last10min/meeting_2_last10min)**:

| โมเดล | สำเร็จ | Drift เฉลี่ย/ต่ำ/สูง | หมายเหตุ |
|---|---|---|---|
| gemini-3.6-flash | 2/3 (1 FAIL 503) | 1.63 / 1.60 / 1.67 | overshoot สูงเมื่อสำเร็จ |
| gemini-3.5-flash | 3/3 | 0.83 / **0.09** / 1.38 | **0.09 ไม่ใช่ดี — คือ transcribe ไม่จบ (แค่ 54s จาก 600s)** |
| gemini-3.5-flash-lite | 2/3 (1 FAIL 503) | 1.37 / 1.08 / 1.67 | overshoot สูงเมื่อสำเร็จ |
| gemini-3-flash | **0/3 (404 ทุกไฟล์)** | - | **ชื่อที่แก้ไปยังผิดอยู่ดี** |
| gemini-3.1-flash-lite | 3/3 | 0.77 / 0.70 / 0.84 | **undershoot สม่ำเสมอทุกไฟล์** (จบก่อนท้ายไฟล์จริงเสมอ) + speaker=2 คงที่ทุกไฟล์ (ต้องสงสัย under-diarize) |
| gemini-2.5-flash | 3/3 | 1.42 / 1.07 / 1.60 | speaker count แกว่ง 3/6/8 คน ไฟล์หนึ่งเริ่มตั้งชื่อคนพูดเอง ("CEO Poom", "Watcharin" ฯลฯ แทน "Speaker N") |
| gemini-2.5-flash-lite | 1/3 | - | fail คนละแบบทุกครั้ง (503, 503, "ไม่คืน structured output") — ดูไม่เสถียรจริง ไม่ใช่แค่โชคร้าย |

**Key findings**:
1. **`gemini-3-flash` (ที่เพิ่งแก้จาก `gemini-3.1-flash` ใน session 3.27) ยังคง 404 ทุกไฟล์** — ชื่อที่
   ผู้ใช้ยืนยันว่า "ต้องเป็น 3 Flash" ก็ยังไม่ใช่ชื่อจริงใน API — ต้องหาทางยืนยันชื่อจริงแบบเชื่อถือได้กว่า
   การเดา (เช่น เรียก `client.models.list()` ของ google-genai SDK จริงเพื่อดึงรายชื่อโมเดลที่ใช้ได้จริง
   ทั้งหมด แทนการเดาตาม naming convention) — **ยังไม่ได้แก้ รอผู้ใช้ตัดสินใจ**
2. **ไม่มีโมเดลไหน "ชนะ" ชัดเจนข้าม 3 ไฟล์** — reliability (success rate) สำคัญพอๆกับ drift:
   `gemini-3.5-flash`/`gemini-3.1-flash-lite` เท่านั้นที่ 3/3 ไฟล์ แต่ทั้งคู่มีปัญหาเชิงคุณภาพของตัวเอง
   (3.5-flash: transcribe ไม่จบในไฟล์หนึ่ง, 3.1-flash-lite: undershoot สม่ำเสมอ+speaker คงที่ 2 คนน่า
   สงสัย)
3. **drift ratio ไม่คงที่แม้เป็นโมเดล+ไฟล์เดียวกัน**: `gemini-3.6-flash` รอบก่อน (session 3.26, ไฟล์
   `meeting_2_last10min`) สำเร็จด้วย drift 1.265 แต่รอบนี้ไฟล์เดียวกันโมเดลเดียวกัน **fail ด้วย 503**
   แทน — ยืนยันว่าตัวเลข drift จากการรันครั้งเดียวไม่ใช่ค่าคงที่ที่เชื่อถือได้ 100% มี variance จาก
   ฝั่ง Google เองด้วย (ไม่ใช่แค่ความแตกต่างของโมเดล)
4. **`gemini-2.5-flash` เริ่มตั้งชื่อคนพูดเองในบางไฟล์** (ไม่ใช่แค่ "Speaker N" — ใช้ "CEO Poom",
   "Watcharin" ฯลฯ ในไฟล์ `meeting_1_last10min`) — พฤติกรรมไม่คงที่ระหว่างไฟล์ (ไฟล์อื่นใช้ "Speaker N"
   ปกติ) — ความเสี่ยง hallucination ชื่อจริงที่ไม่ได้ตรวจสอบ สำหรับระบบที่จัดการข้อมูลลับบอร์ดบริษัทควร
   ระวังเป็นพิเศษ

**ยังไม่ได้ทำ**: ฟังไฟล์เสียงจริงเทียบความถูกต้องของเนื้อหา (ทุกอย่างข้างบนเป็น proxy เชิงปริมาณ) —
ตัวเลขพวกนี้ชี้ปัญหาได้ (transcribe ไม่จบ/undershoot/speaker ไม่เสถียร) แต่ยังสรุปเป็น "โมเดลไหนดีที่สุด"
แบบมั่นใจไม่ได้จากข้อมูลนี้อย่างเดียว

**Key Files**: `backend/model_comparison_results/batch_drift_summary.csv` (ผลจริง, ไม่ commit เข้า
repo — เป็นผลลัพธ์รันจริงของผู้ใช้), `task.md`, `handoff.md`

### 3.30 — สำรวจ Gemini Live API (real-time) — พบ 2 hard blocker ก่อนเขียน spike ด้วยซ้ำ (2026-08-05)

ผู้ใช้ถาม "เรามีโมเดลที่ถอดเสียงแบบ real-time ไหม? กำลังคิดนอกกรอบ /scrutinize" + ส่ง screenshot
Google AI Studio แสดง Live API models มี free tier ("Gemini 2.5 Flash Native Audio Dialog",
"Gemini 3 Flash Live", "Gemini 3.5 Live Translate") — ตอบ AskUserQuestion เลือก "เริ่ม spike test เลย"

**ค้นเอกสารทางการ (`ai.google.dev/gemini-api/docs/live-api/*`, อัปเดตล่าสุด 2026-07-08/2026-08-04 —
สดกว่า research รอบก่อนๆทั้งหมดในเซสชันนี้) ก่อนเขียนโค้ด แทนเดาชื่อโมเดลต่อ (บทเรียนจาก 2 รอบก่อนที่
เดาผิดทั้ง `gemini-3.1-flash`/`gemini-3-flash`)**:

1. **ยืนยัน endpoint string จริงจากตาราง official models page**: `gemini-3.1-flash-live-preview`
   (Live dialogue รุ่นล่าสุด), `gemini-2.5-flash-native-audio-preview-12-2025` (Live รุ่นเก่ากว่า) —
   หมายเหตุ: ชื่อในหน้า Rate limits ของ AI Studio ("Gemini 3 Flash Live") **ไม่ตรงกับชื่อในตาราง
   official docs เป๊ะ** ("Gemini 3.1 Flash Live") — ยืนยันอีกครั้งว่า UI display name ≠ ชื่อจริงที่ใช้
   เรียก API เสมอ (ต้องเช็คตาราง endpoint จริงทุกครั้ง ไม่เดาจาก label ที่เห็นในหน้าเว็บ)
2. **🚫 พบ 2 ข้อจำกัดที่น่าจะเป็น dealbreaker สำหรับ use case นี้ ก่อนเขียน spike ด้วยซ้ำ**:
   - **ไม่มีคำว่า "speaker"/"diarization" ปรากฏที่ไหนเลยในเอกสาร Live API capabilities ทั้งหน้า** —
     `input_audio_transcription` (config ที่ต้องเปิดเพื่อรับ transcript ของเสียงที่เราส่งเข้าไป)
     ดูจากตัวอย่างโค้ดแล้วให้ text stream เดียวรวมกัน ไม่มี field ระบุผู้พูดเลย — Live API ออกแบบมาเพื่อ
     "ผู้ใช้ 1 คนคุยกับ Gemini" ไม่ใช่ "คนหลายคนคุยกันเองในห้องประชุม" ตรงกับที่ scrutinize รอบก่อนกังวล
     ไว้ (CRITICAL #1) — มีความเป็นไปได้สูงว่า diarization จะใช้ไม่ได้เลยกับ use case นี้
   - **Session duration จำกัด 15 นาทีสำหรับ audio-only session** (audio+video จำกัดแค่ 2 นาที) ต้องพึ่ง
     "session management techniques" (session resumption/compaction) เพิ่มถึงจะยืดได้ — ตรงกับที่
     scrutinize รอบก่อนกังวลไว้ (CRITICAL #2, เรื่องสโคปงานใหญ่) ยืนยันแล้วว่าเป็นข้อจำกัดจริงมีตัวเลข
     ชัดเจน ไม่ใช่แค่คาดเดา

**สรุป**: หลักฐานจากเอกสารทางการชี้ว่า Live API **ไม่น่าจะเหมาะกับ use case นี้เลย** (multi-speaker
meeting diarization) ก่อนจะลงทุนเขียน WebSocket spike client ด้วยซ้ำ — ยังไม่ได้เขียน spike จริง รอ
ผู้ใช้ตัดสินใจว่าจะทดสอบยืนยันเชิงประจักษ์ต่อไหม (เผื่อเอกสารไม่ครบ/diarization ทำได้ผ่าน prompting
แบบอื่น) หรือพอแค่นี้แล้วกลับไปโฟกัส batch model comparison ของ pipeline เดิม (async, ที่มีอยู่แล้ว)

**Key Files**: `handoff.md` (บันทึกผลค้นแล้ว, ยังไม่มีโค้ดใหม่)

**How to resume**: ถ้าจะทดสอบยืนยันต่อ ต้องเขียน spike client (Python `google-genai` SDK,
`client.aio.live.connect(model="gemini-3.1-flash-live-preview", config={"response_modalities":
["AUDIO"], "input_audio_transcription": {}})`, ส่ง raw PCM 16-bit/16kHz จากคลิปทดสอบสั้นๆ 2 คนพูด
สลับกัน แล้วดูว่า `input_transcription.text` แยกคนพูดได้ไหม) — ถ้าไม่สนใจแล้วกลับไปที่งานค้าง: หา
model ID จริงของ "3 Flash" (async, `gemini-3-flash-preview` — พบพร้อมกันตอนค้นรอบนี้ ดูหมายเหตุด้านล่าง)
แทน `gemini-3.1-flash`/`gemini-3-flash` ที่ผิดทั้งคู่, ตัด `gemini-2.5-flash-lite` ออกถ้ายัง fail ต่อเนื่อง

⚠️ **พบเพิ่มระหว่างค้น (บังเอิญเจอ ไม่ได้ตั้งใจหา)**: ชื่อโมเดล async "Gemini 3 Flash" (ที่เราพยายามแก้
มา 2 รอบใน session 3.27/3.28 ด้วย `gemini-3.1-flash`→`gemini-3-flash`, ทั้งคู่ 404) ชื่อ endpoint จริง
ตามตาราง official docs คือ **`gemini-3-flash-preview`** (เป็น *Preview* model ต้องมี suffix
`-preview` เสมอ ไม่ใช่ Stable — สาเหตุที่เราเดาผิดมาตลอด 2 รอบเพราะไม่ได้ใส่ `-preview`) — **ยังไม่ได้
แก้ใน `config.py` เพราะกำลังอยู่ระหว่างสำรวจเรื่อง Live API ตามที่ผู้ใช้ขอ** รอกลับมาแก้ทีหลัง

**How to resume**: (1) หาชื่อโมเดล "3 Flash"/"3.x Flash (non-lite)" ที่ถูกต้องจริง — แนะนำเขียนสคริปต์
เล็กๆเรียก `client.models.list()` แทนเดาชื่อต่อ (2) พิจารณาตัด `gemini-2.5-flash-lite` ออกจาก
`GEMINI_TRANSCRIPTION_MODEL_CHOICES` ถ้า fail ต่อเนื่องแบบนี้อีก (3) ฟังไฟล์เทียบเนื้อหาจริงอย่างน้อย
1-2 จุดที่มีปัญหาเห็นชัด (เช่น `gemini-3.5-flash` ที่ transcribe ไม่จบใน `meeting_2_last10min`)

---

### Session 3.31 — `/scrutinize`: แก้ proportional timestamp drift ที่ยังเหลือแม้ตัด chunk 10 นาทีแล้ว
(2026-08-05)

**Goal**: ผู้ใช้ตัดสินใจพอกับการหาโมเดลที่ดีที่สุดแล้ว (ใช้ `gemini-3.6-flash` ดีฟอลต์ตามคำแนะนำ) แต่ขอ
ให้กลับมาแก้ปัญหา **timestamp drift ที่ยังต่างกันแบบมีนัยยะ แม้ตัดไฟล์เป็น chunk 10 นาทีแล้วก็ตาม**
พร้อม `/scrutinize`

**วินิจฉัย (mantra 3 — ข้อมูลจริง ไม่เดา)**: `batch_drift_summary.csv` (session 3.28-3.29) วัด drift
บนไฟล์ทดสอบยาว ~10 นาทีพอดี (เท่ากับ `AUDIO_CHUNK_SECONDS` — ไม่ถูกตัดซ้ำเลยระหว่างทดสอบ) แต่ยังโชว์
drift ratio คลาดมาก: `gemini-3.6-flash` เฉลี่ย 1.633 (คลาด 63%), สูงสุด 1.667 — **สรุปว่าการตัด chunk
เป็น 10 นาทีแก้ได้แค่ "ขนาดความเสียหายสูงสุดต่อไฟล์" (absolute — ไฟล์ 55 นาทีเดิมคลาดสูงสุด 38 นาที ตอน
นี้คลาดสูงสุดแค่ ~ระดับนาทีต่อ chunk) แต่ไม่ได้แก้ "สัดส่วนที่คลาดต่อ chunk" เลย (relative)** — บั๊ก
proportional drift เดิมที่เจอในไฟล์ยาว (session 3.19) จริงๆแล้วเกิดซ้ำเท่าๆกันในทุก chunk ไม่ว่าจะสั้น
แค่ไหน ไม่ใช่ปรากฏการณ์ที่ผูกกับความยาวไฟล์รวมแบบที่คิดไว้ตอนออกแบบ chunking ครั้งแรก (session 3.21)

**แก้แล้ว**: เพิ่ม `audio_chunking.rescale_chunk_segments(segments, known_duration_seconds, *,
overshoot_threshold=1.15)` — ใช้ความยาว chunk จริงที่รู้แน่นอน 100% (จาก ffmpeg `-t` ตอนตัด/ffprobe
ตอนไม่ตัด — **ไม่ใช่ค่าที่ Gemini ประมาณ**) เป็น ground truth rescale timestamp ทุก segment ในสัดส่วน
เดียวกัน (`scale = known_duration / observed_max_end`) หลักฐานที่สนับสนุนว่า linear rescale ใช้ได้จริง:
session 3.19 พิสูจน์แล้วว่า drift เป็น**สัดส่วนคงที่**ตลอดช่วงที่วัด (นาทีที่ 6 vs นาทีที่ 55 ของไฟล์
เดียวกัน ratio ใกล้กันมาก: 1.62 vs 1.675) — แก้เฉพาะกรณี **overshoot** (เกินความยาวจริง >15%)
**ไม่แก้ undershoot** เพราะเป็นปัญหาคนละ class (undershoot ส่วนใหญ่ = ถอดเสียงไม่ครบจริง ไม่ใช่แค่ประมาณ
เวลาผิดสัดส่วน — เช่น `gemini-3.1-flash-lite` undershoot สม่ำเสมอทุกไฟล์ที่เจอใน session 3.29 น่าจะเป็น
เพราะโมเดลนี้จบเร็วกว่าไฟล์จริงเสมอ ไม่ใช่นับเวลาผิด — rescale กรณีนี้จะยืดเนื้อหาที่ถูกอยู่แล้วให้
timestamp ผิดเพิ่มแทน) — เพิ่ม field `AudioChunk.duration_seconds` เก็บความยาวจริงต่อ chunk ต่อสายเข้า
`audio_native.py::transcribe_meeting_audio()` ทั้ง 2 branch (ไฟล์สั้นไม่ตัด chunk ก็ apply เหมือนกัน
ใช้ `total_duration`, ไฟล์ยาวตัด chunk แล้ว apply ต่อ chunk ก่อนบวก `offset_seconds`) log ทุกครั้งที่มี
การ rescale จริง (เห็นได้จาก backend log ว่าเกิดถี่แค่ไหนจากการใช้งานจริง)

**Verify ด้วยข้อมูลจริง (mantra 3, ไม่ใช่แค่ mock)**: sandbox นี้มี ffmpeg/ffprobe ติดตั้งจริง (ต่างจาก
session ก่อนๆที่บันทึกไว้ว่าไม่มี — เช็คซ้ำแล้วพบว่ามี) ใช้ทดสอบ `plan_chunks()`/`split_into_chunks()`
กับไฟล์เสียงจริงในเครื่อง (`test_audio/meeting_1_last10min.wav`) ยืนยัน `duration_seconds` ต่อ chunk
ตรงกับความยาวไฟล์ chunk จริงที่ตัดออกมา 100% แล้วเขียน **`scripts/verify_timestamp_rescale.py`**
(เครื่องมือใหม่ถาวร) replay ผลลัพธ์ Gemini จริงที่เก็บไว้แล้วจาก batch test เดิม (session 3.28-3.29 —
14 ไฟล์ผลลัพธ์ที่มีอยู่แล้วใน `model_comparison_results/*/`, **ไม่เรียก Gemini ใหม่เลย ไม่เปลืองเควตา**)
เทียบกับความยาวไฟล์จริงที่วัดด้วย ffprobe จริง — **ผลลัพธ์**: 6/14 รายการเข้าเงื่อนไข rescale, drift
เฉลี่ยของรายการที่ rescale ลดจาก **1.585 → 1.000 พอดี** ทุกรายการ (รวม `gemini-3.6-flash` ดีฟอลต์ตัวหลัก
ทั้ง 2 ไฟล์ที่มีข้อมูล: 1.667/1.598 → 1.000 ทั้งคู่) ส่วนรายการ undershoot (`gemini-3.1-flash-lite`,
`gemini-2.5-flash-lite`, `gemini-3.5-flash` บางไฟล์) ไม่ถูกแตะตามที่ออกแบบไว้ ตรงตามเงื่อนไขทุกกรณี —
`py_compile`/`pyflakes` ผ่านทุกไฟล์ที่แก้

⚠️ **ยังไม่เคย verify ผ่าน `transcribe_meeting_audio()` เต็ม flow จริงบนเครื่องผู้ใช้** — สคริปต์
verify ทดสอบแค่ตรรกะ rescale เดียวกับข้อมูล Gemini จริงที่มีอยู่แล้ว ไม่ได้ทดสอบ ffmpeg
chunking/Gemini call จริงของ production path เอง (แม้จะ verify แยกส่วนทั้งคู่แล้วก็ตาม) — ผู้ใช้ควร
อัปโหลด/re-upload ไฟล์ประชุมจริงอีกครั้งเพื่อยืนยัน click-to-seek/highlight (session 3.15) แม่นขึ้นจริง
ในเบราว์เซอร์

**Key Files ของเซสชันนี้**: `backend/audio_chunking.py` (เพิ่ม `rescale_chunk_segments()` + field
`AudioChunk.duration_seconds`), `backend/audio_native.py` (เรียก rescale ทั้ง 2 branch ใน
`transcribe_meeting_audio()`), `backend/scripts/verify_timestamp_rescale.py` (ใหม่ — เครื่องมือ replay
ข้อมูลจริงถาวร ใช้ซ้ำได้ทุกครั้งที่มีผลทดสอบโมเดลใหม่ ไม่ต้องเรียก Gemini ใหม่), `task.md`, `handoff.md`

**How to resume**: รอผู้ใช้ทดสอบไฟล์ประชุมจริงบนเครื่อง (สั้น+ยาว) ยืนยันว่า timestamp badge ที่โชว์ตรง
กับเสียงจริงมากขึ้นจริง (โดยเฉพาะช่วงท้ายไฟล์/chunk) — ถ้าผลดี ควรช่วยเปิดทางให้ตัดสินใจข้อ 7 ของ
`/grill-me` (3.14) ได้ง่ายขึ้น (เก็บ Gemini native audio ต่อแทนที่ `audio_worker` ทั้งชุด เพราะข้อกังวล
เรื่อง timestamp-dependent feature ใช้ไม่ได้ลดลงมาก) แต่ยังต้องรอผลจริงก่อนตัดสินใจข้อนั้น —
`audio_worker/`/`backend/audio.py` **ยังห้ามลบ** เหมือนเดิม — ถ้ายังเจอ drift หลังแก้นี้ ให้ลองปรับ
`overshoot_threshold` ให้ต่ำลง (เข้มขึ้น) หรือพิจารณาว่า undershoot cases (`gemini-3.1-flash-lite` ที่
undershoot สม่ำเสมอทุกไฟล์) อาจต้องมี mitigation แยกต่างหาก (เช่น เตือนผู้ใช้ว่าโมเดลนี้มักถอดไม่ครบ
ไม่ใช่แค่ timestamp ผิด)

---

### Session 3.32 — ทดสอบจริงเจอ 11-chunk job ตายกลางทาง + เพิ่ม checkpoint/resume ต่อ chunk (2026-08-05)

**เกิดอะไรขึ้น**: ผู้ใช้รัน `test_rescale_live.py`/upload จริงผ่านแอปกับไฟล์ยาว (~66+ นาที, ตัดได้ 11
chunk) — log จริง: chunk 1-6 สำเร็จ (ใช้ `gemini-3.6-flash`), chunk 7 เจอ `503 UNAVAILABLE` ("high
demand", ข้อความบอกชัดว่าเป็นแค่ transient) แล้ว log ตัดจบทันทีด้วย uvicorn shutdown/restart
sequence เต็มรูปแบบ (`Waiting for application shutdown` → `Started server process` ใหม่)

**วินิจฉัย**: อ่านโค้ด `llm_fallback.run_with_fallback()` แล้วยืนยันว่าตรรกะ retry/fallback ทำงานถูกต้อง
ตามดีไซน์ — 503 ไม่ใช่ quota error (`is_quota_error()`=False) จึงไม่ retry primary model ซ้ำ (breaks
ทันทีหลัง attempt เดียว) แต่ **ตรง `is_fallback_worthy_error()`** (แมตช์ `\b(503|504)\b`) ควรจะสลับไป
`gemini-3.5-flash` (fallback เดียวที่ตั้งไว้ใน `.env` ปัจจุบัน — ไม่ override
`GEMINI_MODEL_TRANSCRIPTION_FALLBACK` เลย ใช้ดีฟอลต์ `config.py` ตรงๆ) — แต่ log ไม่มีบรรทัด "กำลังลอง
โมเดลสำรอง" เลยก่อนที่ process จะ restart **แปลว่า process ถูกฆ่ากลางคันก่อนโค้ด fallback จะได้รันจบ
ไม่ใช่ fallback ทำงานผิด** — สาเหตุที่เป็นไปได้สูงสุด: `uvicorn.run(..., reload=True)` (main.py:941,
CRITICAL ที่พบตั้งแต่ session 3.20 ผู้ใช้เคยเลือก "(c) ยอมรับความเสี่ยงไว้ก่อน" ไม่ปิด) — **ยังไม่ยืนยัน
100% กับผู้ใช้ว่าเป็นสาเหตุจริง** (ไม่รู้ว่ามีการแก้ไฟล์ในโฟลเดอร์ backend ระหว่าง run นั้นหรือไม่ หรือ
ผู้ใช้ restart เอง) — ถามผู้ใช้แล้วรอคำตอบ

**ปัญหาที่แท้จริงที่ต้องแก้ไม่ว่าสาเหตุ restart จะเป็นอะไร**: `transcribe_meeting_audio()` เดิมเก็บ
`all_chunk_segments` แค่ใน local variable ของฟังก์ชัน — chunk ไหนก็ตามที่ fail (ไม่ว่าจาก fallback
หมดจริง หรือ process ถูกฆ่ากลางคัน) ทำให้ progress ของทุก chunk ก่อนหน้าที่**เรียก Gemini จริงสำเร็จ
แล้ว**หายไปทั้งหมด ต้องเริ่มไฟล์ใหม่ทั้งไฟล์ถ้า retry (เปลืองเควตา/เวลาซ้ำ — กรณีนี้เควตาที่ใช้ไปกับ
chunk 1-6 หายฟรี)

**แก้แล้ว — เพิ่ม checkpoint/resume ต่อ chunk**: `audio_chunking.py` เพิ่ม `save_checkpoint()`/
`load_checkpoint()`/`clear_checkpoint()` เขียนความคืบหน้าลง `backend/checkpoints/<key>.json` แบบ
atomic (`.tmp` + `os.replace`) ทุกครั้งที่ 1 chunk สำเร็จ — `load_checkpoint()` เช็ค `plan` (offset/
duration ต่อ chunk) ตรงกับไฟล์เสียงปัจจุบันก่อนใช้เสมอ (tolerance ±0.5s กันคลาดจุดทศนิยม ffprobe) ไม่
ตรง = ทิ้ง checkpoint ปลอดภัยกว่าเสี่ยง merge ผิดชุด (เช่น re-upload ไฟล์เสียงคนละไฟล์ทับของเดิม) —
`audio_native.transcribe_meeting_audio()` รับ `checkpoint_key: str | None` ใหม่ โหลด checkpoint ก่อน
เริ่ม loop (ข้าม chunk ที่ทำสำเร็จแล้ว), save หลังทุก chunk สำเร็จ, clear ตอนจบครบทุก chunก — `main.py`
ส่ง `checkpoint_key=str(meeting_id)` เข้ามา (filename `meeting_{id}.ext` deterministic ต่อ meeting
อยู่แล้ว — re-upload ไฟล์เดิมไปยัง meeting เดิมได้ checkpoint key เดียวกันเป๊ะ)

**Verify**: `py_compile`/`pyflakes` ผ่านทุกไฟล์ + เขียน mock test เต็ม (stub `google.genai` ทั้งโมดูล
เพราะ sandbox ไม่มี dependency จริง) จำลอง 4-chunk job ที่ chunk index 2 fail เสมอรอบแรก: attempt 1
เรียก Gemini (mock) ที่ chunk 0,1,2 แล้ว raise ตามคาด, checkpoint มี 2 chunk ที่สำเร็จ (0,1) ถูกต้อง —
attempt 2 (จำลอง 503 หายแล้ว) **เรียก mock Gemini แค่ chunk 2,3 เท่านั้น ไม่เรียก 0,1 ซ้ำ** ยืนยันว่า
resume ทำงานถูกต้อง ประหยัดเควตาจริงตามดีไซน์ — checkpoint ถูกลบอัตโนมัติหลังสำเร็จครบ

⚠️ **ไม่ช่วย run ที่พังไปแล้วรอบนี้**: chunk 1-6 ที่ transcribe สำเร็จไปแล้วในการทดสอบจริงของผู้ใช้
**สูญเสียไปแล้ว** เพราะ feature checkpoint นี้ยังไม่มีตอนนั้น (เพิ่งเขียนหลังเหตุการณ์) — ต้อง re-upload
ไฟล์เดิมใหม่ทั้งไฟล์อีกครั้งหนึ่ง (รอบนี้จะเสียเควตาเต็มอีกรอบ แต่ถ้า fail กลางทางอีกรอบถัดไปจะ resume ได้)

⚠️ **ยังไม่ได้ตัดสินใจกับผู้ใช้**: (1) จะปิด `reload=True` ถาวร/ชั่วคราวตอนรัน transcription จริงไหม
(ผู้ใช้เคยเลือกยอมรับความเสี่ยงไว้ก่อนใน session 3.20 แต่ตอนนี้เพิ่งทำให้เสียเควตาจริงแล้ว ควรถามซ้ำ)
(2) จะขยาย `GEMINI_MODEL_TRANSCRIPTION_FALLBACK` จาก 1 โมเดล (`gemini-3.5-flash` ดีฟอลต์) เป็นหลาย
โมเดลไหม (ลด risk ที่ primary+fallback เดียวพังพร้อมกันช่วง Google มีปัญหา capacity — คนละประเด็นกับ
"โมเดลไหนดีที่สุด" ที่ปิดเรื่องไปแล้ว นี่เป็นเรื่อง redundancy)

**Key Files**: `backend/audio_chunking.py` (เพิ่ม checkpoint functions), `backend/audio_native.py`
(เพิ่ม param `checkpoint_key` + wiring), `backend/main.py` (ส่ง `checkpoint_key=str(meeting_id)`),
`task.md`, `handoff.md`

**How to resume**: รอคำตอบผู้ใช้เรื่อง reload=True + fallback chain width แล้ว re-upload ไฟล์เดิมใหม่
ทั้งไฟล์อีกครั้ง (ครั้งนี้ถ้า fail กลางทางอีก ลอง re-upload ซ้ำไฟล์เดิมไปที่ meeting เดิม ควรเห็น log
"พบ checkpoint เดิม — ข้าม N chunk ที่สำเร็จแล้ว" ถ้า mechanism ทำงานถูกต้องจริงกับ Gemini จริง)

**อัปเดตต่อทันที (2026-08-05, ยังใน session 3.32) — ผู้ใช้ตอบคำถามทั้ง 2 ข้อแล้ว + ขอเพิ่ม**:

1. **`reload=True` → `reload=False` ถาวร** (`main.py` บรรทัดท้ายไฟล์) ตามที่ผู้ใช้ยืนยัน "ปิดถาวรตอนนี้
   เลย" — ต้อง restart backend เอง (Ctrl+C + รันคำสั่งใหม่) ทุกครั้งที่แก้โค้ด `.py` จากนี้ไป
2. **ขยาย `GEMINI_MODEL_TRANSCRIPTION_FALLBACK`** จาก 1 โมเดล (`gemini-3.5-flash`) เป็น 3 โมเดล
   (`gemini-3.5-flash,gemini-3.5-flash-lite,gemini-2.5-flash`) ใน `config.py`/`.env.example` — ผู้ใช้
   ถามก่อนอนุมัติว่า speaker label ส่งต่อข้าม chunk ยังทำงานไหมถ้าโมเดลเปลี่ยนกลางไฟล์ (fallback) —
   ตอบด้วยการอ่านโค้ดจริง (`_speaker_context_prompt()` ใน audio_native.py) ไม่เดา: กลไกนี้เป็น**prompt
   ข้อความล้วนๆ**ส่งให้ทุก chunk ถัดไปเหมือนกันไม่ว่าจะใช้โมเดลเดิมหรือโมเดลสำรอง (ไม่มีช่องทางพิเศษที่
   หลุดเฉพาะตอนสลับโมเดล — ไม่เคยส่งบริบทเสียงจริงข้าม chunk ตั้งแต่แรกอยู่แล้ว) ความเสี่ยง label ไม่
   ตรงกันมีอยู่แล้วเท่าเดิมไม่ว่า fallback มี 1 หรือ 3 ตัว (แค่โอกาสเจอบ่อยขึ้นเพราะมี fallback ให้สลับ
   มากขึ้น ไม่ใช่ความเสี่ยง class ใหม่) — ผู้ใช้ยืนยันให้ทำ ("ไม่กระทบเรื่องการส่งต่อ speaker จริงก็ทำ
   ได้เลย ไม่เอาคาดเดานะ") ตั้งใจไม่ใส่ `gemini-3.1-flash-lite` (undershoot สม่ำเสมอ) และ
   `gemini-2.5-flash-lite` (fail ไม่เสถียร) ตามผลจริงจาก batch test (session 3.28-3.29)
3. **เพิ่ม `scripts/split_audio.py`** (ใหม่) — ผู้ใช้ขอสคริปต์แยกต่างหาก "มีไฟล์ยาวไฟล์เดียว อยากได้
   สคริปต์ตัดเองเป็นไฟล์ย่อยๆ 10 นาทีก่อน" (ถามชัดผ่าน AskUserQuestion ก่อนเขียนว่าหมายถึงตัดไฟล์เดียว
   เป็นไฟล์ย่อยถาวร ไม่ใช่รวมไฟล์ที่แยกอยู่แล้วเป็น 1 meeting) — reuse
   `audio_chunking.plan_chunks()`/`split_into_chunks()` เดียวกับ production เป๊ะ (ไม่มีโค้ดตัดใหม่ที่
   ต้องดูแลแยก) ต่างแค่เขียนไฟล์ลงโฟลเดอร์ถาวรที่เลือกได้แทน `tempfile.TemporaryDirectory()` ที่ลบทิ้ง
   อัตโนมัติ — รองรับ `--chunk-seconds`/`--overlap-seconds` override ชั่วคราว (override ค่า `config`
   ใน process ของสคริปต์เองเท่านั้น ไม่กระทบ backend ที่รันอยู่จริง) **Verify ด้วยไฟล์จริง**: รันจริงกับ
   `uploads/meeting_1.m4a` (55.7 นาทีจริง) ผ่าน ffmpeg จริงในนี้ (sandbox นี้มี ffmpeg ติดตั้งอยู่) ได้
   6 chunk ตรงตาม plan เป๊ะ, เช็ค ffprobe จริงของทุกไฟล์ chunk ที่ตัดออกมา (5 ไฟล์ 600.0s พอดี +
   ไฟล์สุดท้าย 492.7s) ตรงกับตัวเลขที่สคริปต์พิมพ์ทุกไฟล์

**Key Files เพิ่มจากอัปเดตนี้**: `backend/main.py` (`reload=False`), `backend/config.py`/
`backend/.env.example` (fallback chain 3 โมเดล), `backend/scripts/split_audio.py` (ใหม่)

---

### Session 3.33 — `/debug-mantra`: fallback chain (session 3.32) ใช้งานจริงไม่ได้เลยเพราะ dropdown
ปิดทิ้งเงียบๆ ทุกครั้ง — แก้แล้ว + verify กับ Gemini จริงครบ flow (2026-08-07)

**เกิดอะไรขึ้น**: ผู้ใช้ re-upload ไฟล์ยาว (3343s, 6 chunk) ไฟล์เดิมเข้า meeting เดิม (id=3) หลัง fix
checkpoint/resume ของ session 3.32 — checkpoint resume ทำงานถูกต้อง (skip 4 chunk ที่สำเร็จแล้ว) แต่
chunk 5 พัง `503 UNAVAILABLE` อีกครั้งแล้ว **fail ทันทีไม่มี log พยายามลองโมเดลสำรองเลยสักบรรทัด**
ทั้งที่เพิ่งขยาย `GEMINI_MODEL_TRANSCRIPTION_FALLBACK` เป็น 3 โมเดลไปเมื่อ session ก่อน — ต่างจากเคส
เดิมที่ backend restart กลางทาง (session 3.32) รอบนี้ backend **ไม่ได้ restart เลย** (`GET
/api/meetings` วิ่งต่อเนื่องปกติไม่มี shutdown/restart sequence ใน log)

**วินิจฉัย (mantra 1-4 เต็มรูปแบบ)**: ไล่โค้ด `audio_native.py:172`
(`fallback_models = [] if model_override else config.GEMINI_MODEL_TRANSCRIPTION_FALLBACK`) →
`model_override` มาจาก FormData field `model` ที่ dashboard ส่งมา (`main.py:439`) → ไล่ต่อไปที่
`app.js`'s `getModelOptionsHtml()` (ฟังก์ชันเดียวที่ populate ทั้ง dropdown ในตาราง (`.model-select`)
และ dropdown หน้า detail (`#reupload-model-select`)) พบว่า **ไม่เคยมี option ค่าว่างเลยตั้งแต่เขียน
ฟีเจอร์นี้ครั้งแรก (session 3.24)** — options ทุกตัว map จาก `data.models` (ชื่อโมเดลจริงล้วนๆ) แล้ว
pre-select โมเดล primary (`data.default`) ไว้เป็นดีฟอลต์เสมอ → `<select>` มี option `selected` เสมอ →
`.value` ไม่เคยว่างจริงเลยสักครั้ง → `triggerUpload()`/`triggerReuploadOnDetailPage()`'s
`if (modelSelect.value) form.append("model", ...)` ส่ง field `model` มาเสมอ 100% ทุกครั้งที่ upload/
re-upload จากหน้านี้ **แม้ผู้ใช้ไม่ได้ตั้งใจเลือกอะไรเองเลย** — cross-reference กับ comment เดิมที่
เขียนไว้แล้วทั้ง 2 จุด (`app.js:218-220`, `main.py:437-438`) ยืนยันว่า "ค่าว่าง = ใช้ fallback chain"
คือ**เจตนาดีไซน์เดิมที่ implement ไม่ครบตั้งแต่แรก** ไม่ใช่พฤติกรรมที่ตั้งใจปิด — สรุป: fallback chain
3 โมเดลที่เพิ่งเขียนใน session 3.32 **ใช้งานจริงไม่ได้แม้แต่ครั้งเดียวนับตั้งแต่เขียน** เพราะ UI ปิดทาง
เข้าถึงไว้เงียบๆ

**แก้แล้ว (frontend เท่านั้น ไม่แตะ backend เลย — ตรงตามเจตนาเดิม)**: `getModelOptionsHtml()` เพิ่ม
option ค่าว่าง `"ค่าเริ่มต้น (ลองโมเดลสำรองอัตโนมัติถ้าโมเดลหลักพัง)"` เป็นตัวแรกและ `selected` แทนการ
pre-select โมเดล primary ตรงๆ (โมเดล primary ยังเลือกได้ในรายการ มีป้าย "(หลัก)" กำกับ) + เพิ่ม `title`
tooltip บน `<select>` ทั้ง 2 จุด (`modelSelectHtml()` ในตาราง, `#reupload-model-select` ใน
`meeting-detail.html`) เตือนชัดว่า "เลือกโมเดลเจาะจง = ปิดการสลับโมเดลสำรองอัตโนมัติทั้งหมด" กันคนอื่น
เจอปัญหาเดิมซ้ำโดยไม่รู้ตัว

**Verify (mantra ครบ + ยืนยันจริงกับ Gemini production ไม่ใช่แค่ mock)**: `node --check app.js` ผ่าน +
จำลอง logic จริงด้วย node ยืนยัน option ค่าว่างเป็น `selected` เริ่มต้น ไม่มีโมเดลไหนถูก pre-select
และ gate เดิมจะไม่ append field `model` เมื่อผู้ใช้ไม่แตะ dropdown — จากนั้นผู้ใช้ re-upload ไฟล์เดิม
(3343s/6 chunk) เข้า meeting 3 ซ้ำอีกครั้งโดยไม่แตะ dropdown เลย **log จริงยืนยันครบทุกจุดที่แก้**:
1. Checkpoint resume: `พบ checkpoint เดิม (key=3) — ข้าม 4 chunk ที่สำเร็จแล้ว เริ่มต่อจาก chunk 5/6`
2. Fallback chain ทำงานจริงครั้งแรก: chunk 5 พัง `503` บน `gemini-3.6-flash` →
   `โมเดล gemini-3.6-flash ใช้ไม่ได้ (ServerError) กำลังลองโมเดลสำรอง gemini-3.5-flash...` → สำเร็จใน
   50.49s ด้วยโมเดลสำรอง
3. Rescale timestamp ทำงานต่อเนื่องปกติทั้ง chunk 5-6 (`scale=0.600`, `scale=0.604`)
4. จบครบ 6 chunk: `[TRANSCRIBE-DONE] meeting 3 transcribed ด้วยโมเดล=gemini-3.6-flash+gemini-3.5-flash
   ใน 133.4s (231 segments)`

**Key Files**: `ComSecAI_Dashboard/app.js` (`getModelOptionsHtml()`, `modelSelectHtml()`),
`ComSecAI_Dashboard/meeting-detail.html` (`#reupload-model-select` tooltip)

**สถานะ**: ปิดเคสนี้ — checkpoint/resume (session 3.32) + fallback chain (session 3.32 เขียน,
session 3.33 แก้ให้ใช้งานได้จริง) verify ครบ end-to-end กับ Gemini production แล้วทั้งคู่พร้อมกัน
ในไฟล์เดียวกัน ไม่มีงานค้างในเรื่องนี้อีก

---

### Session 3.34 — เพิ่มแก้ไข Participants/Agenda ย้อนหลังได้ + แก้ host bind ให้ ComSec ตัวจริง
เข้าผ่าน LAN ได้ (2026-08-07)

**บริบท**: ผู้ใช้กด Generate Minutes บน meeting "test" แล้วเจอ error "การประชุมนี้ไม่มีวาระการประชุม
เลย" — ไล่โค้ดพบว่า `POST /api/meetings`'s `agenda_items`/`attendees` เป็น `list = []` ดีฟอลต์ ไม่บังคับ
กรอกตอนสร้างประชุมเลย และ **ไม่มีทางแก้ไขย้อนหลังได้เลยสักทาง** (ตั้งได้แค่ตอนสร้างครั้งเดียว) —
meeting นั้นกู้ไม่ได้ต้องสร้างใหม่ทั้งใบ ผู้ใช้ขอให้เพิ่มการแก้ไข 2 หัวข้อนี้ย้อนหลังได้

**แก้แล้ว**: เพิ่ม `PUT /api/meetings/{id}/attendees` + `PUT /api/meetings/{id}/agenda_items`
(`backend/main.py`, ใหม่ทั้งคู่) เขียนทับทั้ง array เสมอเหมือน pattern `update_transcript_segments`/
`set_speaker_mapping` เดิมทุกประการ — เพิ่ม `_reject_if_approved()` กันแก้ไขหลัง
`approval_status="Approved"` แล้ว (สถานะสุดท้ายของ compliance flow — แก้ผู้เข้าร่วม/วาระของเอกสารที่
บอร์ดอนุมัติไปแล้วจะทำให้ข้อมูลไม่ตรงกับที่อนุมัติจริงแบบเงียบๆ) ไม่บล็อกสถานะอื่น (Draft/
Pending_Review/Needs_Revision แก้ได้ปกติ) ⚠️ หมายเหตุที่ตั้งใจไม่แก้เพิ่ม: ถ้าแก้ agenda หลัง Generate
Minutes ไปแล้ว (แต่ยังไม่ Approve) `minutes_json` เดิมจะไม่ sync อัตโนมัติ ต้องกด Generate Minutes ซ้ำ
เอง — ตรงกับปรัชญา "เขียนทับ ไม่มี versioning" ของทั้งระบบ

**Frontend**: `meeting-detail.html` เพิ่มปุ่ม Edit ข้างหัวข้อ Participants/Agenda (ซ่อนถ้า Approved
แล้ว) — `app.js` เพิ่ม `renderParticipantsView/Edit()`/`renderAgendaView/Edit()` (input rows + "+
เพิ่ม" + ปุ่มลบต่อแถว + Save/Cancel, pattern เดียวกับ `renderSpeakerMapping`/
`renderTranscriptEditable` เดิมทุกประการ) Save แก้ attendees แล้ว re-render Speaker Mapping panel
ต่อด้วยถ้ามี transcript แล้ว (autocomplete datalist ของ mapping ใช้ attendees เป็นแหล่งชื่อ)

**Verify (แน่นกว่าปกติ เพราะ endpoint นี้ไม่พึ่ง Gemini/Word — รันจริงได้เต็มใน sandbox ไม่ต้อง mock
เลย)**: ติดตั้ง dependency ที่ขาด (`fastapi`/`sqlalchemy`/`google-genai`/ฯลฯ) ใน sandbox แล้ว
`import main` ผ่านจริง — เขียน FastAPI `TestClient` test ยิง flow เต็มด้วย throwaway SQLite
(`COM_SEC_DB_PATH` env override กัน touch `com_sec.db` จริง): สร้าง meeting ว่าง (ไม่มี
attendees/agenda เหมือนเคสจริงที่เจอ) → `PUT attendees` (2 คน, ตรวจ `position=null` ไม่พังด้วย) →
`PUT agenda_items` (2 วาระ, ตรวจลำดับ) → GET ซ้ำยืนยัน persist จริงใน DB ไม่ใช่แค่ response →
`generate_minutes` ไม่ reject "ไม่มีวาระการประชุมเลย" อีกต่อไป (พังที่ step อื่นแทนเพราะไม่มี
API key/transcript จริงในแซนด์บ็อกซ์ ตามคาด) → overwrite attendees ด้วย list สั้นกว่าเดิม (1 คน)
ยืนยันว่า **แทนที่ทั้งหมด ไม่ merge** (cascade `delete-orphan` ทำงานถูกต้อง) → list ว่างเปล่ายอมรับได้
(ลบผู้เข้าร่วมทั้งหมด) → 404 กรณี meeting ไม่มีจริง → 403 กรณี role `Board_Member` → 400 ทั้ง 2
endpoint หลัง set `approval_status="Approved"` ตรงๆใน DB — **ทุก assertion ผ่านหมด (18 เคส)** —
`node --check app.js` ผ่าน + เช็ค id ที่ JS อ้างอิงครบทุกตัวจริงใน HTML (สคริปต์เทียบ id set แบบเดียว
กับที่เคยทำใน session ก่อนๆ) ⚠️ **ยังไม่เคยเปิดจริงในเบราว์เซอร์** (เขียน UI จาก static analysis
เหมือนงาน frontend อื่นๆของโปรเจกต์นี้ทุกครั้ง) ต้องให้ผู้ใช้ทดสอบจริง: กด Edit → แก้/เพิ่ม/ลบแถว →
Save → เช็คว่า list ฝั่ง view mode อัปเดตถูกต้อง, Cancel ไม่ยิง API, ปุ่ม Edit หายไปจริงถ้า meeting
Approved แล้ว

**เพิ่มในเซสชันเดียวกัน (ก่อนหน้านี้)**: `host="127.0.0.1"` → `host="0.0.0.0"` ใน
`backend/main.py`'s `uvicorn.run()` — ComSec ตัวจริงเข้า `http://192.168.214.98:8000/dashboard/`
จากเครื่องอื่นในวง LAN ไม่ได้เลยเพราะ loopback ไม่ฟัง LAN NIC (ผู้ใช้ยืนยันรับความเสี่ยง attack
surface ที่เพิ่มขึ้นแล้วผ่าน AskUserQuestion — `/dashboard` ยังไม่มี auth คุมที่ static file mount,
ยังเป็น HTTP เปล่าไม่มี TLS) — ผู้ใช้ยืนยันแล้วว่าใช้งานได้จริงหลัง restart backend + เปิด Windows
Firewall

**Key Files**: `backend/main.py` (`AttendeesBody`/`AgendaItemsBody`/`_reject_if_approved()`/
2 endpoint ใหม่, `host="0.0.0.0"`), `ComSecAI_Dashboard/meeting-detail.html` (ปุ่ม Edit),
`ComSecAI_Dashboard/app.js` (render*View/Edit functions ใหม่ 6 ตัว), `task.md`, `handoff.md`

---

### Session 3.35 — เพิ่มเลขวาระแบบกำหนดเอง (3.1/3.2/เลขข้าม) หลังผู้ใช้ถามทำไม export ได้วาระเดียว
(2026-08-07)

**บริบท**: ผู้ใช้ upload ไฟล์ `minutes_test_draft.docx` (ผลลัพธ์จริงจาก Generate Docx) ถามว่าทำไมมีแค่
วาระเดียว — ไล่โค้ดยืนยันว่า export pipeline ไม่มีบั๊ก (`{%p for item in agenda_items %}` วนถูกต้อง,
`len(result.agenda_items) == len(agenda_descriptions)` บังคับเสมอ) **สาเหตุจริงคือ meeting นั้นมี
agenda item ใน DB แค่ 1 รายการจริงๆ** (description = "BOD 16/2569" หน้าตาเหมือนชื่อประชุมมากกว่าหัวข้อ
วาระ) — Gemini เลยต้องยัดทุกเรื่องที่คุยในที่ประชุมลงวาระเดียว แนะนำให้แยกวาระผ่านปุ่ม Edit Agenda
(session 3.34) ผู้ใช้ถามต่อว่าวาระจริงเป็นเลขแบบ "3.1/3.2" (วาระย่อย) จะทำยังไง — เดิมระบบ auto-number
จาก index (0,1,2,...) เรียงต่อเนื่องเท่านั้น ไม่รองรับ

**ถาม `AskUserQuestion`** ระหว่าง 2 แนวทาง (1: เพิ่มช่อง label แยกกรอกเอง vs 2: พิมพ์เลขวาระเองในช่อง
description เลย ตัด prefix "วาระที่" อัตโนมัติออกจาก template) — **ผู้ใช้เลือกทั้ง 2 ข้อ** ตีความ/สร้าง
เป็นทางออกผสม: เพิ่ม field `label` แยกต่างหาก (structured, มี UI ของตัวเอง) **แต่** template ไม่เติม
prefix "วาระที่" ให้เองอีกต่อไป พิมพ์ `{{ item.label }}` ตรงๆ (ดีฟอลต์ auto-fill "วาระที่ {ลำดับ}" ถ้า
ไม่กรอก — หน้าตาเหมือนเดิมทุกประการถ้าไม่ตั้งใจแก้ ได้ทั้งความง่าย(1)และความยืดหยุ่นเต็มที่(2)พร้อมกัน)

**แก้แล้วทั้งสาย**:
- `models.py`: `MeetingAgendaItem.label` คอลัมน์ใหม่ (nullable, free text) แยกจาก `order` เดิม (ยังคุม
  ลำดับจริง/จับคู่ผล Gemini เหมือนเดิมทุกประการ ไม่แตะ)
- `db.py`: เพิ่ม `_migrate_add_missing_columns()` — **สำคัญ**: `Base.metadata.create_all()` ไม่เพิ่ม
  คอลัมน์ใหม่ให้ตารางที่มีอยู่แล้ว (SQLAlchemy ปกติ) ถ้าไม่มี migration ตรงนี้ DB จริงที่มีข้อมูลอยู่แล้ว
  (`com_sec.db` มี meeting จริงหลายอันแล้ว) จะ error ทันทีว่าไม่มีคอลัมน์ `label` — เขียน
  `ALTER TABLE ... ADD COLUMN` เบาที่สุด เช็ค `PRAGMA table_info` ก่อนกัน error ซ้ำถ้ารันหลายรอบ
  (โปรเจกต์นี้ยังไม่มี Alembic — MVP เท่านั้น)
- `main.py`: `AgendaItemIn` schema ใหม่ (`{label, description}`) แทน `list[str]` เดิม — ใช้ทั้ง
  `MeetingCreateBody`/`AgendaItemsBody` (endpoint แก้ไขย้อนหลังจาก session 3.34) — `_build_agenda_items()`
  helper กลาง เติมดีฟอลต์ `"วาระที่ {ลำดับ}"` ถ้าไม่กรอก `label` มา — `_meeting_to_dict()`/
  `generate_meeting_minutes()` ส่ง label ผ่านไปด้วยทุกจุด
- `minutes_generation.py`: `generate_minutes(agenda_descriptions: list[str], ...)` →
  `agenda_items: list[dict], ...` — **label ไม่เข้า Gemini prompt เลย** (`build_minutes_user_prompt`
  ยังรับแค่ description string เหมือนเดิม) merge กลับเข้า `minutes_json` จาก DB ตรงๆ 100% (เหมือน
  `description` ที่เป็น ground truth อยู่แล้ว — label ก็เป็น ground truth เพิ่มอีกฟิลด์)
- `docx_generation.py`: context ส่ง `"label"` เข้า Jinja พร้อม fallback `"วาระที่ {order+1}"` สำหรับ
  `minutes_json` เก่าที่สร้างไว้ก่อนมี field นี้ (กัน KeyError)
- `build_minutes_template.py`: ตัด hardcode `"วาระที่ {{ item.agenda_order }}"` ออก เหลือแค่
  `"{{ item.label }}"` — **ต้องรัน `python build_minutes_template.py` ใหม่จริงในเซสชันนี้** เพื่อ
  regenerate ไฟล์ binary `.docx` ทั้ง 2 ไฟล์ (template เป็น artifact ที่ build ไว้ล่วงหน้า ไม่ได้อ่าน
  จาก .py ตรงๆตอน runtime) — ยืนยันด้วย `python-docx` เปิดไฟล์ที่ regenerate แล้วเช็ค tag จริง
- Frontend: `create-meeting.html`/`app.js`'s `addAgendaRow()` เพิ่มช่อง `.agenda-label` คู่กับ
  `.agenda-item` เดิม, `meeting-detail.html`'s `renderAgendaView()`/`_buildAgendaRow()`/
  `renderAgendaEdit()` เพิ่ม label เช่นกัน (agenda_items เปลี่ยนจาก `list[str]` เป็น
  `list[{label, description}]` — breaking change ของ shape ที่ต้องแก้ทุกจุดที่ใช้), `renderMinutesPanel()`
  เปลี่ยนจาก hardcode `วาระที่ ${agenda_order+1}` เป็นใช้ `item.label` (fallback เดิมถ้าไม่มี)

**Verify (ไม่ mock — เรียก `render_minutes_docx()` จริง)**: `py_compile`/`node --check` ผ่านทุกไฟล์ +
รัน `build_minutes_template.py` จริง regenerate template แล้ว TestClient test เต็ม flow: สร้าง meeting
พร้อม label "3.1"/"3.2" ปนกับไม่กรอก label เลย → ยืนยัน default `"วาระที่ 3"` ถูกต้อง → GET ซ้ำ persist
จริง → PUT แก้ไขเป็นเลขข้ามไม่เรียงต่อเนื่อง "5"/"5.2.1" (ซ้อน 3 ชั้น) → เขียน `minutes_json` จำลองตรงๆ
(ไม่เรียก Gemini จริง) → เรียก `render_minutes_docx()` ตรงๆ → เปิดไฟล์ `.docx` ผลลัพธ์ด้วย `python-docx`
ยืนยัน text มี `"5\tวาระใหญ่"`/`"5.2.1\tวาระย่อยซ้อนหลายชั้น"` จริง และ**ไม่มี** `"วาระที่ 0"`/
`"วาระที่ 1"` แบบเดิมหลงเหลือเลย — **ทุก assertion ผ่านหมด (12 เคส)**

⚠️ **เหตุการณ์ระหว่าง verify (บันทึกไว้กันพลาดซ้ำ)**: สคริปต์ทดสอบแรกเขียนไฟล์ `.docx` ทดสอบลง
`backend/generated_docs/` จริงของโปรเจกต์ (คนละพาธกับ `COM_SEC_DB_PATH` ที่ override ผ่าน env ได้ —
`docx_generation.GENERATED_DOCS_DIR` ไม่มี env override) กลายเป็นไฟล์หลุดเข้า `D:\Com Sec` จริง ลบตรงๆ
ไม่ได้ (permission denied) ต้องขอสิทธิ์ผ่าน `allow_cowork_file_delete` ก่อน — เช็คแล้วว่า**ไม่ได้เขียน
ทับไฟล์จริงของ meeting ไหนเลย** (query DB จริงยืนยัน meeting id ที่ชนกันมี `minutes_docx_path=None`
อยู่แล้ว ไม่เคยมีไฟล์มาก่อน) ลบไฟล์ทดสอบทิ้งเรียบร้อย — **บทเรียนสำหรับครั้งหน้า**: ถ้าต้อง verify
`render_minutes_docx()`/`docx_generation.py` ตรงๆอีก ควร monkeypatch `GENERATED_DOCS_DIR` ไปที่ temp
dir ก่อนเสมอ (เหมือนที่ทำกับ `COM_SEC_DB_PATH` อยู่แล้ว) กันเขียนลงโฟลเดอร์จริงของผู้ใช้อีก

✅ **live test จริงในเบราว์เซอร์ผ่านแล้ว (2026-08-07, ยืนยันโดยผู้ใช้)** — "เรียบร้อยใช้งานได้ครบถ้วน"
ครอบคลุมทั้ง label แบบกำหนดเอง + แก้ไข Participants/Agenda ย้อนหลัง (session 3.34) พร้อมกัน — ปิดเคส
นี้ ไม่มีงานค้างอีก

**Key Files**: `backend/models.py` (`MeetingAgendaItem.label`), `backend/db.py`
(`_migrate_add_missing_columns()`), `backend/main.py` (`AgendaItemIn`/`_build_agenda_items()`),
`backend/minutes_generation.py`, `backend/docx_generation.py`, `backend/build_minutes_template.py`
(+ regenerate `templates/*.docx` จริง), `ComSecAI_Dashboard/create-meeting.html`/`app.js`/
`meeting-detail.html`, `task.md`, `handoff.md`

---

### Session 3.36 — ต่อสาย Approve → Confidential RAG index อัตโนมัติ (Policy Search เอกสารลับ) (2026-08-07)

**บริบท**: ผู้ใช้ขอให้เช็ค logic ว่าเอกสารรายงานการประชุมที่ Approve แล้วต่อเข้า Local RAG (feature
"Policy Search") ยังไงบ้าง — ไล่โค้ดจริง (`archive.py`, `rag_worker/main.py`, `confidential_rag.py`,
`build_confidential_index.py`) พบว่า**ไม่มีการเชื่อมต่อกันเลยสักจุดเดียว**: (1) `archive_documents()`
copy ไฟล์ไป UNC path ภายนอกเท่านั้น ไม่เคย copy เข้า `confidential_corpus/`, (2) ไม่มีจุดไหนเรียก
`build_confidential_index.py` เลย (เป็นสคริปต์ CLI แยกที่ต้องรันมือ), (3) แม้รันมือแล้วก็ต้อง restart
`rag_worker` process ใหม่ถึงจะโหลดดัชนีที่ rebuild แล้ว (module-level cache `_index`/`_load_attempted`
ไม่เคยถูก reset) — สรุปคือ Module 5 (Approval) เขียนเสร็จสมบูรณ์แล้ว แต่**ไม่เคยต่อสายเข้า RAG เลยตั้งแต่ต้น**

**ถาม `AskUserQuestion`**: ผู้ใช้เลือก **"Auto: index อัตโนมัติทันทีที่ Approve"** (ยอมรับ tradeoff
เป็น full rebuild ทุกครั้ง ไม่ใช่ incremental — เหตุผล: corpus เอกสารบอร์ดของบริษัทเดียวไม่โตเร็วพอที่จะ
คุ้มความซับซ้อนของ incremental index)

**แก้แล้วทั้งสาย**:
- `rag_worker/confidential_rag.py`: เพิ่ม `rebuild_index_from_corpus()` — ฟังก์ชันกลางฟังก์ชันเดียวที่
  ทำ full rebuild จาก `CONFIDENTIAL_CORPUS_DIR` ทั้งหมด (exclude `README.md`), **reuse
  `Settings.embed_model`** ถ้ามีโหลดอยู่แล้ว (เคส `rag_worker` process กำลังรันอยู่ — กัน VRAM โดนใช้ซ้ำ
  2 ชุด) หรือโหลดเองถ้าเป็นการเรียกแบบ standalone CLI, และที่สำคัญที่สุด — **reset module state
  (`_index`/`_reranker`/`_load_attempted`/`_load_error`) หลัง rebuild เสร็จ** แก้ limitation เดิมที่
  ต้อง restart worker ถึงจะเห็นดัชนีใหม่ (ตอนนี้ query ถัดไปหลัง rebuild โหลดดัชนีใหม่อัตโนมัติทันที)
- `rag_worker/build_confidential_index.py`: ลด logic เดิมทั้งหมดออก เหลือเป็น thin CLI wrapper เรียก
  `confidential_rag.rebuild_index_from_corpus()` แทน (ก่อนหน้านี้มี logic ซ้ำกันเต็มๆ 2 ที่)
- `rag_worker/main.py`: เพิ่ม `POST /admin/rebuild_confidential_index` — เป็น sync `def` (ไม่ใช่
  `async def`) ตั้งใจให้ FastAPI รันใน threadpool อัตโนมัติ ไม่บล็อก event loop หลักระหว่าง rebuild
  (endpoint `/health`/`/query` ยังตอบได้ปกติระหว่างนั้น) ไม่มี auth เพิ่มที่นี่ — เชื่อ network
  isolation เดียวกับ endpoint อื่น (worker ฟัง `127.0.0.1` เท่านั้น)
- `backend/config.py`: เพิ่ม `RAG_WORKER_CONFIDENTIAL_CORPUS_DIR` ชี้ไปที่
  `rag_worker/confidential_corpus/` (ต้องตรงกับ `worker_config.py`'s `CONFIDENTIAL_CORPUS_DIR` เสมอ —
  override ผ่าน `.env` ได้ถ้าโครงสร้างโฟลเดอร์เปลี่ยน)
- `backend/rag.py`: เพิ่ม `trigger_confidential_index_rebuild()` — HTTP client เรียก worker endpoint
  ใหม่ (timeout แยกจาก query — `RAG_WORKER_REBUILD_TIMEOUT_SECONDS` default 600s) **ไม่ raise
  exception เลยแม้แต่กรณีเดียว** คืน dict `{"success": bool, "message": str}` เสมอ
- `backend/main.py`: `_archive_and_notify_background()` เพิ่มขั้นตอนสุดท้าย (หลัง archive) — copy
  `final_docx_full` เข้า `RAG_WORKER_CONFIDENTIAL_CORPUS_DIR` เป็น `meeting_{id}_final.docx` แล้วเรียก
  `trigger_confidential_index_rebuild()` — แยก try/except ของตัวเอง เหมือนทุกขั้นตอนอื่นในฟังก์ชันนี้
  (PDF/email/archive) — **rebuild ล้มเหลวไม่ทำให้ approve ถูกมองว่าล้มเหลว** แค่บันทึก
  `MeetingApprovalLog(action="rag_index_failed", ...)` ไว้ให้เห็นใน audit trail (pattern เดียวกับ
  `delivery_failed`/`email_failed` ที่มีอยู่แล้ว)

**Verify**: sandbox ไม่มี torch/faiss/GPU (rag_worker ต้องใช้ venv จริงบน Windows เท่านั้น — ข้อจำกัด
เดียวกับทุกฟีเจอร์ RAG ก่อนหน้านี้) จึงแบ่ง verify เป็น 2 ชั้น:
1. **`confidential_rag.rebuild_index_from_corpus()` edge cases** (ไม่ต้องพึ่ง torch/faiss เพราะ import
   เหล่านั้นอยู่ใน branch ที่มีเอกสารจริงเท่านั้น — deferred import ตั้งใจ): ทดสอบ 3 เคส (โฟลเดอร์ไม่มี
   อยู่เลย → สร้างให้+คืน success=False, โฟลเดอร์ว่างเปล่า → success=False, มีแค่ README.md →
   success=False) **ผ่านหมดทั้ง 3 เคส** ยืนยันด้วยว่า heavy import ไม่ถูกเรียกจริงในเคสเหล่านี้ (ไม่มี
   `ImportError` แม้ sandbox ไม่มี torch/faiss ติดตั้งเลย)
2. **backend wiring แบบเต็ม flow**: เขียน fake HTTP server (built-in `http.server`, ไม่ใช้ mock
   library) จำลอง `/admin/rebuild_confidential_index` ของ worker คืนค่าได้ 4 แบบ (success, success=False,
   HTTP 500, connection refused) แล้วรัน `main._archive_and_notify_background()` จริง (monkeypatch
   `pdf_generation.convert_docx_to_pdf`/`protect_pdf` เพราะ sandbox ไม่มี MS Word/`docx2pdf`, ใช้
   `COM_SEC_DB_PATH`+`GENERATED_DOCS_DIR`+`RAG_WORKER_CONFIDENTIAL_CORPUS_DIR` override ทั้งหมดไปที่
   temp dir กันไฟล์หลุดเข้าโปรเจกต์จริงซ้ำแบบ session 3.35) — **ทุกเคสถูกต้อง**: ไฟล์ docx ถูก copy
   เข้า corpus เสมอ (แม้ worker error/ปิดอยู่ — เพื่อให้ retry/manual rebuild ทีหลังเจอไฟล์), เคส
   success ไม่มี log ผิดพลาด, เคส failure ทั้ง 3 แบบ (success=False/500/connection refused) ถูกบันทึก
   `rag_index_failed` log ถูกต้องครบ พร้อม comment ที่มีรายละเอียด error จริง — ตรวจแล้วว่าไม่มีไฟล์
   ทดสอบหลุดเข้า `D:\Com Sec` จริงเลย (`find ... -newer` เช็คว่าง)

⚠️ **ยังไม่ live test บนเครื่องจริง** (ต้องมี `rag_worker` รันจริงด้วย venv ที่มี torch/faiss/GPU +
meeting ที่ approve จริงอย่างน้อย 1 อัน) — ขั้นต่อไปเมื่อผู้ใช้ทดสอบจริง: approve เอกสารสักฉบับ → เช็ค
`rag_worker_com_sec.log` มีบรรทัด `[CONFIDENTIAL-REBUILD] สร้างดัชนีใหม่สำเร็จ` → ไปหน้า Policy Search
เลือก scope "เอกสารลับ" ถามคำถามที่เกี่ยวกับเนื้อหาในเอกสารที่เพิ่ง approve → ต้องเจอคำตอบจากเอกสารนั้น
โดยไม่ต้อง restart `rag_worker` เลย

**Key Files**: `rag_worker/confidential_rag.py` (`rebuild_index_from_corpus()`),
`rag_worker/build_confidential_index.py` (thin wrapper), `rag_worker/main.py`
(`POST /admin/rebuild_confidential_index`), `backend/config.py`
(`RAG_WORKER_CONFIDENTIAL_CORPUS_DIR`), `backend/rag.py` (`trigger_confidential_index_rebuild()`),
`backend/main.py` (`_archive_and_notify_background()`), `task.md`, `handoff.md`

---

### Session 3.37 — Live test แรกเจอ 2 ปัญหา: docx อ่านเป็น garbled text + อยากกรองผลตามการประชุม (2026-08-07)

**บริบท**: ผู้ใช้ live test session 3.36 จริง (approve meeting 3) ส่ง screenshot มา — Policy Search
หน้าเอกสารบอร์ด (ลับ) ตอบว่า "ไม่พบข้อมูลที่เกี่ยวข้อง เนื้อหาที่ให้มาเป็นข้อมูลที่อ่านไม่ออก
(Garbled text/Binary code)" พร้อม sources การ์ดที่มีแต่ตัวอักษรมั่ว (`meeting_3_final.docx` ×8) —
พิสูจน์ว่า pipeline การ index ต่อสายสำเร็จจริง (เห็นชื่อไฟล์+เนื้อหาถูกดึงมา) แต่**เนื้อหาที่ index ผิด**
ผู้ใช้ยังถามต่อว่า "ตามแผนต้องเลือกเอกสารการประชุมได้สิ" — เช็ค `stitch_brief_rag_search.md` (สเปกดีไซน์
ต้นฉบับของหน้านี้) แล้วไม่มีสเปกนี้อยู่จริง (มีแค่ scope toggle นโยบายทั่วไป/เอกสารบอร์ดลับ) — เป็นฟีเจอร์
ใหม่ที่ผู้ใช้ขอเพิ่มตอนนี้ ไม่ใช่ของที่หายไปจากแผนเดิม

**ปัญหาที่ 1 — root cause (ไม่ต้องรันโค้ดเลย พบจาก cross-reference comment เดิม)**:
`rag_worker/requirements.txt` มี comment บอกไว้ชัดว่า **`docx2txt` ถูกตัดออกจาก requirements ตั้งใจ**
ตอนพอร์ต Local RAG มา เพราะตอนนั้น (ก่อน session 3.36) `rag_worker` process ไม่เคยอ่านไฟล์ `.docx`
ตรงๆ เลยสักครั้ง (โหลดแต่ FAISS index ที่ build ไว้ล่วงหน้า, Local RAG เองก็ pre-convert เป็น `.txt`
ก่อนด้วยสคริปต์แยกต่างหาก) — พอ session 3.36 เพิ่ม `rebuild_index_from_corpus()` ที่ยื่น `.docx` เข้า
`SimpleDirectoryReader` ตรงๆ เป็นครั้งแรกในโปรเจกต์ **โดยไม่มี `docx2txt`** llama_index หา `DocxReader`
ไม่เจอ ตกไปใช้ default text reader อ่านไฟล์ `.docx` (ซึ่งเป็น zip binary จริงๆ) เป็น UTF-8 ดิบ — ตรงกับ
อาการในภาพเป๊ะ (fragment ตัวอักษรอ่านออกปนกับขยะ = ลักษณะเฉพาะของการอ่าน zip เป็น text)

**แก้**: เพิ่ม `docx2txt` กลับเข้า `rag_worker/requirements.txt` พร้อม comment อธิบาย root cause เต็ม
กันคนในอนาคตตัดออกซ้ำโดยไม่รู้เหตุผล — **ผู้ใช้ต้องทำเองบนเครื่องจริง**: `pip install docx2txt` ในเวอร์ชวล
เอนไวรอนเมนต์ของ `rag_worker` แล้ว **rebuild ดัชนีลับใหม่** (ดัชนีปัจจุบันที่มีอยู่ garbled ทั้งก้อน ต้อง
รันซ้ำ ไม่ใช่แค่ติดตั้ง dependency เฉยๆ) — วิธีที่ง่ายที่สุดคือ approve เอกสารอีกฉบับ (trigger rebuild
อัตโนมัติ) หรือรัน `build_confidential_index.py` มือก็ได้ (thin wrapper เรียกฟังก์ชันเดียวกัน)

**ปัญหาที่ 2 — ฟีเจอร์ใหม่ "กรองผลตามการประชุม"**: ถาม `AskUserQuestion` ผู้ใช้เลือกระหว่าง 2 แนวทาง
(dropdown filter ก่อนถาม vs แยกเป็นห้องแชทต่างหาก) — แนะนำ**ทางแรก** เพราะ session model ปัจจุบันผูก
`user_id` เดียว (ไม่ใช่ per-document) การแยกห้องแชทจริงต้องรื้อ session architecture ทั้งชุด ในขณะที่
ปัญหาจริง ("คำตอบปนกันข้ามการประชุม") แก้ได้ด้วย filter ธรรมดา ไม่ต้องเปลี่ยน UX/flow เดิมเลย — ผู้ใช้
เห็นด้วย ("ทำเลย")

**แก้แล้วทั้งสาย**:
- `rag_worker/confidential_rag.py`: `rebuild_index_from_corpus()` แท็ก `metadata["meeting_id"]` ให้
  แต่ละ `Document` โดยแกะจากชื่อไฟล์ (`meeting_{id}_final.docx` — pattern เดียวกับที่
  `_archive_and_notify_background()` ใช้เขียนไฟล์เข้า corpus เสมอ) `exclude` metadata นี้ออกจาก
  embed/llm text (เป็นแค่ id เชิงโครงสร้าง ไม่ควรมีผลต่อ semantic search) — `handle_confidential_query()`
  รับ `meeting_id` เพิ่ม (optional) **filter เองใน Python หลัง retrieve** ไม่ใช้ llama_index's
  `MetadataFilters` ที่ระดับ vector store เพราะ **`FaissVectorStore` ไม่รองรับ metadata filter แบบ
  native** (FAISS เป็นแค่ similarity search โครงสร้างล้วนๆ) — เพิ่ม `similarity_top_k` เป็น 80 (จาก 40)
  ตอนมี filter กันเคส chunk ของการประชุมที่เลือกไม่ติด top-k เพราะแข่งกับการประชุมอื่น — ไม่เจอ chunk
  ของการประชุมที่เลือกเลย → ตอบข้อความแจ้งตรงๆ ไม่เสีย Gemini call เปล่าๆ
- `rag_worker/main.py`: `ConfidentialQueryBody` เพิ่ม field `meeting_id` (optional, backward
  compatible — ไม่ส่งมา = ค้นหาทุกเอกสารเหมือนเดิม)
- `backend/rag.py`/`backend/main.py`: `RAGPipeline.query()`/`QueryBody`/`/api/rag/query_confidential`
  รับ-ส่ง `meeting_id` ผ่านทั้งสาย
- `ComSecAI_Dashboard/search.html`/`app.js`: เพิ่ม dropdown `#search-meeting-select` (โชว์เฉพาะ
  scope="confidential") ดึงรายชื่อจาก `GET /api/meetings` กรอง `approval_status === "Approved"` ฝั่ง
  client (ไม่เพิ่ม backend endpoint ใหม่ — ยังไม่คุ้ม) ตัวเลือกดีฟอลต์ "ทุกการประชุม" = ไม่ส่ง
  `meeting_id` เลย (พฤติกรรมเดิมทุกประการ)

**Verify**: sandbox ไม่มี torch/faiss เหมือนเดิม แบ่งเป็น 3 ชั้น — (1) regex แกะ `meeting_id` จากชื่อไฟล์
6 เคส (ตรง/pdf/ไม่ตรง pattern หลายแบบ) ผ่านหมด (2) mock `_index`/`_reranker`/`llm_fallback` ใน
`confidential_rag.py` ตรงๆ (ไม่ต้องพึ่ง torch/faiss เพราะ mock object เอง) ทดสอบ 4 เคส: ไม่ filter
(เห็นทุก node), filter meeting_id="1" (เหลือ 2 จาก 4), filter meeting_id=2 แบบ int (เหลือ 1), filter
meeting_id ที่ไม่มีอยู่จริง (ตอบ "ไม่พบ" โดยไม่เรียก LLM) — ผ่านหมด ยืนยัน `similarity_top_k` สลับ
40→80 ถูกต้องตามที่ filter หรือไม่ (3) TestClient จริงยิง `/api/rag/query_confidential` ผ่าน
`Com_Sec_Checker` token เช็คว่า `meeting_id` จาก request body ไหลไปถึง `rag_pipeline.query()` จริง
(ทั้งเคสส่งมาและไม่ส่งมา) — ผ่านหมด `node --check app.js` + `py_compile` ทุกไฟล์ backend/rag_worker
ผ่าน

⚠️ **ยังไม่ live test บนเครื่องจริง** — ต้องรอผู้ใช้: (1) `pip install docx2txt`, (2) rebuild ดัชนีลับ
ใหม่ (ดัชนีเดิม garbled ต้องทำใหม่), (3) restart ทั้ง `rag_worker`+`backend` (แก้ `main.py`
ทั้งสองฝั่ง), (4) เปิดหน้า Policy Search → เลือกสโคป "เอกสารบอร์ด (ลับ)" → ต้องเห็น dropdown เลือก
การประชุมโผล่มา → ลองเลือกการประชุมเจาะจงแล้วถามคำถาม → sources ที่ได้ต้องเป็นข้อความไทยอ่านออก
(ไม่ใช่ตัวอักษรมั่วเหมือนเดิม)

**Key Files**: `rag_worker/requirements.txt` (`docx2txt`), `rag_worker/confidential_rag.py`
(`meeting_id` metadata + filter), `rag_worker/main.py` (`ConfidentialQueryBody.meeting_id`),
`backend/rag.py`/`backend/main.py` (`meeting_id` passthrough), `ComSecAI_Dashboard/search.html`/
`app.js` (dropdown), `task.md`, `handoff.md`

---

### Session 3.38 — Live test รอบ 2: garbled text ไม่หายเพราะ process ไม่ restart + บั๊กใหม่ standalone CLI crash (2026-08-07)

**บริบท**: ผู้ใช้ทำตาม session 3.37 ต่อ — revert meeting 3 กลับ `Needs_Revision` ด้วยสคริปต์ SQL มือ
(`backend/revert_approval.py`, สร้างให้แบบ ad-hoc ไม่ใช่ไฟล์ถาวรของระบบ), `pip install docx2txt`,
แก้เอกสารแล้ว approve ใหม่ — แต่ Policy Search หน้าเอกสารลับยังตอบ garbled text เหมือนเดิมทุกตัวอักษร

**ปัญหาที่ 1 — root cause: ไม่ได้ restart `rag_worker` หลังติดตั้ง docx2txt**: llama_index ตรวจว่ามี
`docx2txt` ให้ใช้หรือไม่แค่ครั้งเดียวตอน import module reader ครั้งแรกในแต่ละ process (ไม่เช็คซ้ำ) —
`rag_worker` process ที่รันอยู่ตอนนั้นเปิดค้างมาตั้งแต่ก่อนติดตั้ง docx2txt (import ไปแล้วว่า "ไม่มี"
ตอนยังไม่ได้ลง) ติดตั้ง package ใหม่ระหว่าง process รันอยู่ไม่มีผลจนกว่าจะ restart — ผู้ใช้ trigger
rebuild ผ่าน endpoint `/admin/rebuild_confidential_index` (ตอน approve) ซึ่งรันใน process เดิมที่ยัง
จำ state เก่าอยู่ ได้ดัชนี garbled เหมือนเดิมทั้งที่ pip install สำเร็จแล้วจริง **แก้**: บอกผู้ใช้ปิด
`rag_worker` (หน้าต่าง `start_worker.bat`) แล้วเปิดใหม่ก่อนเสมอหลังลง dependency ใหม่ใดๆ

**ปัญหาที่ 2 — บั๊กจริงเจอจากการรัน standalone CLI ครั้งแรก (ไม่เคยถูกทดสอบเส้นทางนี้มาก่อน)**:
`build_confidential_index.py` (standalone, ไม่ผ่าน `rag_worker` process ที่รันอยู่) crash ด้วย
`ImportError: llama-index-embeddings-openai package not found` ที่บรรทัด
`confidential_rag.py`'s `if Settings.embed_model is None:` — สาเหตุ: `Settings.embed_model` ของ
llama_index เป็น **property ที่ auto-resolve เป็นค่า default (OpenAI embeddings) ทันทีถ้ายังไม่เคย
ตั้งค่าไว้เลย** ไม่ใช่แค่คืน `None` เฉยๆ ตามที่ชื่อโค้ดเดิมสันนิษฐานไว้ (ตอนเขียน session 3.36 ไม่เคย
ทดสอบเส้นทาง standalone จริงเลย เทสแค่ 3 เคส edge case ที่ deferred import ไม่ถูกเรียกถึง — ดู
"Verify" ของ session 3.36) เคสที่เคยใช้งานได้ (ผ่าน endpoint ตอน `rag_worker` รันอยู่) รอดเพราะ
`main.py::_load_everything()` ตั้ง `Settings.embed_model` เป็น HuggingFace ไว้ก่อนแล้วตั้งแต่
startup — property เลยคืนค่าที่ตั้งไว้ตรงๆ ไม่ไป auto-resolve **แก้**: เปลี่ยนไปเช็ค internal
attribute `Settings._embed_model` ตรงๆ แทน (เลี่ยง property getter ที่มี side effect) — ทดสอบซ้ำแล้ว
ว่า standalone CLI รันผ่านได้จริงในเชิง logic (sandbox ไม่มี torch/faiss ยืนยันแค่ว่า exception เดิม
ไม่เกิดซ้ำจาก code path เดียวกัน ยังไม่ live test บนเครื่องจริง)

⚠️ **ยังไม่ live test บนเครื่องจริง** — ขั้นต่อไปที่ผู้ใช้ต้องทำ: (1) restart `rag_worker` (จำเป็นสำหรับ
ปัญหาที่ 1 ด้วย), (2) รัน `python build_confidential_index.py` standalone อีกครั้งให้ผ่านจริง (ยืนยัน
ปัญหาที่ 2 หายจริง), (3) เปิด Policy Search ถามคำถามเดิม ต้องได้ sources เป็นข้อความไทยอ่านออก

**Key Files**: `rag_worker/confidential_rag.py` (`rebuild_index_from_corpus()`'s embed_model check),
`backend/revert_approval.py` (สคริปต์ ad-hoc สำหรับ manual revert — ไม่ใช่ของถาวรของระบบ ลบทิ้งได้
หลังใช้เสร็จ), `handoff.md`

---

### Session 3.39 — วินิจฉัยผิดตัวใน session 3.37: ไม่ใช่ docx2txt แต่ขาด `llama-index-readers-file` ทั้ง package (2026-08-07)

**บริบท**: ผู้ใช้ทำตาม session 3.37-3.38 ครบ (`pip install docx2txt`, restart worker, rebuild ดัชนี)
แต่ garbled text ยังไม่หาย แม้ยืนยันแล้วว่า `docx2txt` ติดตั้งถูก environment จริง
(`python -m pip show docx2txt` เจอปกติ) — ใช้ `/debug-mantra` ไล่ตาม Mantra 3 (falsify hypothesis
เดิม แทนที่จะเชื่อทันที) เขียนสคริปต์ diagnostic เทียบ (1) `docx2txt.process()` เรียกตรงๆ กับ (2)
`llama_index.core.SimpleDirectoryReader` บนไฟล์เดียวกัน

**ผลที่พบ (Mantra 2 — trace the fail path จริง ไม่เดา)**: `docx2txt.process()` อ่านออกเป็นภาษาไทยปกติ
สมบูรณ์ (3408 ตัวอักษร) แต่ `SimpleDirectoryReader.load_data()` บนไฟล์เดียวกันคืนค่า
`PK\x03\x04\x14\x00...` — **byte header ของไฟล์ ZIP ดิบๆ** (.docx คือ ZIP อยู่แล้วภายใน) พิสูจน์ชัดว่า
llama_index **ไม่เคยเรียก `DocxReader` เลยแม้แต่น้อย** ทั้งที่ `docx2txt` มีอยู่จริงในเครื่อง — สมมติฐาน
เดิมของ session 3.37 ("ขาดแค่ docx2txt") **ผิด**

**Root cause จริง (Mantra 4 — cross-reference กับ requirements.txt จริง)**: เช็ค
`rag_worker/requirements.txt` พบว่ามีแค่ `llama-index-core`/`llama-index-embeddings-huggingface`/
`llama-index-vector-stores-faiss`/`llama-index-llms-google-genai` — **ไม่มี
`llama-index-readers-file` เลย** ตั้งแต่แรก ตั้งแต่ llama_index แยก package เป็นโมดูลย่อยจำนวนมาก
(v0.10+) ตัวคลาส `DocxReader` (และ reader เฉพาะทางไฟล์ประเภทอื่นๆ) ถูกย้ายออกจาก
`llama-index-core` ไปอยู่ package แยก `llama-index-readers-file` โดยเฉพาะ — ไม่มี package นี้ =
`SimpleDirectoryReader` ไม่มี `.docx` reader ให้เลือกใช้เลยตั้งแต่ต้น ตกไปอ่านเป็น raw bytes ทันที
ไม่ว่าจะมี `docx2txt` อยู่ในเครื่องหรือไม่ก็ตาม (`docx2txt` เป็นแค่ dependency ที่ `DocxReader`
เรียกใช้ *ถ้ามันถูกโหลดขึ้นมาได้ก่อน* — ไม่มีตัว `DocxReader` เองเลยก็ไม่มีความหมาย)

**แก้**: เพิ่ม `llama-index-readers-file` เข้า `rag_worker/requirements.txt` พร้อมคอมเมนต์แก้ไข
diagnosis เดิมของ session 3.37 ให้ถูกต้อง (กันคนในอนาคตเข้าใจผิดซ้ำว่าขาดแค่ docx2txt)

⚠️ **ยังไม่ live test บนเครื่องจริง** — ขั้นต่อไปที่ผู้ใช้ต้องทำ: (1) `pip install llama-index-readers-file`
(หรือ `pip install -r requirements.txt` ให้ครบทุกอย่าง), (2) รัน `diagnose_docx_read.py` ซ้ำ
(สคริปต์ ad-hoc ที่สร้างไว้ช่วยวินิจฉัย) ยืนยันว่าส่วนที่ 2 (SimpleDirectoryReader) อ่านออกเป็นภาษาไทย
แล้วจริง ไม่ใช่ raw bytes อีกต่อไป, (3) รัน `build_confidential_index.py` ใหม่, (4) restart
`rag_worker` (เหตุผลเดิมจาก session 3.38 — in-memory cache ของ process เดิมไม่รู้ว่าดิสก์เปลี่ยน),
(5) ทดสอบ Policy Search ถามคำถามจริงอีกครั้ง

**Key Files**: `rag_worker/requirements.txt` (`llama-index-readers-file`),
`rag_worker/diagnose_docx_read.py` (สคริปต์ ad-hoc ช่วย diagnose — ลบทิ้งได้หลังยืนยันเสร็จ),
`handoff.md`

---

## 5. Suggested Skills (สกิล AI ที่แนะนำให้เปิดใช้งานตอนสานต่อ)
หากผู้รับช่วงต่อเป็น AI แนะนำให้เรียกใช้สกิลต่อไปนี้ตามสถานการณ์:
- `/scrutinize`: หากมีการปรับเปลี่ยนสถาปัตยกรรมใหญ่ๆ ให้ใช้สกิลนี้ตรวจสอบช่องโหว่อีกครั้ง (เพราะระบบนี้เน้น Compliance หนักมาก) — ใช้ไปแล้วหลายรอบตลอดโปรเจกต์ พบ finding จริงทุกครั้ง: (1) Module 1 mock ทั้งหมด + ความเสี่ยง Windows WINHTTP.dll crash จากการรวมโปรเซส (2026-08-01), (2) CRITICAL GPU cleanup bug ใน `pipeline.py` — `del` ผิดสโคปทำให้ VRAM ไม่ถูกปล่อยจริง (ดู task.md Module 2 "GPU Lock"), (3) `.env.example` ค้างค่า `ASR_MIN_SEGMENT_SECONDS=0.5` เก่าหลังเปลี่ยนมาใช้ post-hoc filtering (session 3.4), (4) `WorkerBusyError`+path traversal guard ที่ยังไม่มี (audio_worker เปิดเป็น HTTP service ไม่มี auth — ดู task.md Module 2 รายการ scrutinize findings)
- `/grill-me`: หากทีมพัฒนาต้องการทดสอบไอเดีย หรือเช็กความพร้อมก่อนเขียนโค้ด — ใช้ไปแล้ว 3 รอบ ครอบคลุมทุกมิติของ Module 1-6 แล้ว
- `qwenchance`: เมื่อเริ่มเขียนโค้ดระบบ Audio Processing หรือ RAG ที่ลอจิกยาวและซับซ้อน ป้องกัน AI ติดลูป
