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
> ล้าสมัยไปแล้ว คงไว้เป็น breadcrumb ประวัติเท่านั้น สถานะจริงล่าสุดอยู่ท้าย 3.12 ด้านล่าง**

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

## 5. Suggested Skills (สกิล AI ที่แนะนำให้เปิดใช้งานตอนสานต่อ)
หากผู้รับช่วงต่อเป็น AI แนะนำให้เรียกใช้สกิลต่อไปนี้ตามสถานการณ์:
- `/scrutinize`: หากมีการปรับเปลี่ยนสถาปัตยกรรมใหญ่ๆ ให้ใช้สกิลนี้ตรวจสอบช่องโหว่อีกครั้ง (เพราะระบบนี้เน้น Compliance หนักมาก) — ใช้ไปแล้วหลายรอบตลอดโปรเจกต์ พบ finding จริงทุกครั้ง: (1) Module 1 mock ทั้งหมด + ความเสี่ยง Windows WINHTTP.dll crash จากการรวมโปรเซส (2026-08-01), (2) CRITICAL GPU cleanup bug ใน `pipeline.py` — `del` ผิดสโคปทำให้ VRAM ไม่ถูกปล่อยจริง (ดู task.md Module 2 "GPU Lock"), (3) `.env.example` ค้างค่า `ASR_MIN_SEGMENT_SECONDS=0.5` เก่าหลังเปลี่ยนมาใช้ post-hoc filtering (session 3.4), (4) `WorkerBusyError`+path traversal guard ที่ยังไม่มี (audio_worker เปิดเป็น HTTP service ไม่มี auth — ดู task.md Module 2 รายการ scrutinize findings)
- `/grill-me`: หากทีมพัฒนาต้องการทดสอบไอเดีย หรือเช็กความพร้อมก่อนเขียนโค้ด — ใช้ไปแล้ว 3 รอบ ครอบคลุมทุกมิติของ Module 1-6 แล้ว
- `qwenchance`: เมื่อเริ่มเขียนโค้ดระบบ Audio Processing หรือ RAG ที่ลอจิกยาวและซับซ้อน ป้องกัน AI ติดลูป
