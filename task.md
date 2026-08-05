# Project Tasks: Company Secretary AI System

> ⚠️ **อัปเดต 2026-08-01 (รอบ 2 — หลังเซสชัน `/grill-me` เรื่องการรวม repo ภายนอก):** พบโปรเจกต์ RAG ที่ทำงานจริงอยู่แล้วที่
> `D:\Review Policy\Local  RAG` (39 unit test + 11 E2E test ผ่านหมด) — เปลี่ยนกลยุทธ์ Module 1 จาก "เขียนใหม่" เป็น
> "reuse ของเดิม" ทั้งหมด พร้อมตัดสินใจสำคัญอีกหลายข้อเรื่องฮาร์ดแวร์/กฎหมาย/สถาปัตยกรรม — ดูรายละเอียดเหตุผลแต่ละ
> ข้อใน `implementation_plan.md` ส่วน "Decisions from /grill-me session (2026-08-01)"

## Module 0: ข้อจำกัดฮาร์ดแวร์ & กฎหมาย (ตัดสินใจแล้ว)

- `[x]` ยืนยันใช้ `typhoon-asr` เป็น ASR หลัก (FastConformer, รันได้ทั้ง CPU/GPU) — **ไม่ใช้ `typhoon2-audio`** (โมเดล 8B parameters ต้องการ VRAM ~16GB+ เกินเครื่องที่มี 4GB ไปมาก) เก็บ `typhoon2-audio` ไว้เป็น**ตัวเลือกสำหรับ production บน cloud GPU ในอนาคตเท่านั้น** ไม่ใช่แผนตอนนี้
- `[x]` ยืนยันความเสี่ยงด้านกฎหมายของ `Diarization_ThaiSpeech_2022` (ไม่มีไฟล์ LICENSE = all rights reserved โดยปริยาย) — ยอมรับความเสี่ยงนี้เพราะใช้ภายในองค์กรเท่านั้น ข้อมูลเป็นความลับ ไม่มีการขาย/แจกจ่ายต่อ **ต้องกลับมาทบทวนใหม่ถ้าจะเปลี่ยนขอบเขตการใช้งาน** (เช่น แจกจ่ายให้บริษัทอื่น)
- `[x]` ~~ยืนยันว่า RAG stack (BGE-M3 + reranker) รันบน CPU เท่านั้นเสมอ~~ — **กลับคำตัดสินใจแล้ว (2026-08-02)** ดูรายการถัดไป

### ⚠️ อัปเดต 2026-08-02: กลับคำตัดสินใจ "RAG stack CPU-only เสมอ" เป็น "ใช้ GPU ถ้ามี"

**สาเหตุ**: live test จริงพบว่า `/api/rag/query` ใช้เวลา 700-1000s ต่อคำขอ — ไล่หาสาเหตุด้วย
`/debug-mantra` + `/scrutinize` หลายรอบ (เดาผิดไป 3 รอบ: SDK retry ภายใน, CPU contention จาก
Local RAG's worker ที่ยังรันค้าง, ขนาด payload ใหญ่ — ทุกอันตัดออกด้วยการทดสอบจริง) จนแยกเวลา
ทีละสเตจได้ (`diagnose_pipeline_stages.py`): **rerank 60 candidate ใช้เวลา 859s เดี่ยวๆ** (ส่วน
retrieval 0.61s, generate 5.2s เร็วปกติ) เทียบ fp16 vs fp32 บน CPU เครื่องเดียวกัน
(`diagnose_reranker_fp16_vs_fp32.py`): **fp16 = 553s, fp32 = 32s** (เร็วขึ้น 17 เท่า) — สาเหตุคือ
`torch_dtype=torch.float16` (จากโค้ดต้นฉบับ Local RAG ที่ copy มาไม่แก้) รันบน CPU ที่ส่วนใหญ่ไม่มี
native fp16 support จริง ต้อง emulate ช้ามาก ยืนยันเพิ่มว่า Local RAG's venv ใช้ torch 2.5.1+cu121
(build เก่ากว่า) ส่วน Com Sec's global env ใช้ torch 2.13.0 (CPU-only build ใหม่กว่า) — คนละ
build กัน จึงเจอ regression นี้ไม่เท่ากัน (อธิบายว่าทำไม Local RAG "ไม่เคยช้า" ในการใช้งานจริง)

**ทางเลือกที่มี**: (ก) ใช้ fp32 บน CPU (พิสูจน์แล้วว่าได้ 32s ไม่ต้องแตะ GPU/VRAM เลย) หรือ
(ข) ย้ายไป GPU จริง (เร็วกว่าอีก) — **ผู้ใช้เลือกข้อ (ข) เอง** (2026-08-02) หลังเห็นตัวเลขครบถ้วน
พร้อมรับทราบผลที่ตามมาเรื่อง VRAM

**หมายเหตุแก้ไข (2026-08-02, หลังทดสอบเพิ่ม)**: สมมติฐาน "fp16 บน CPU ช้าเพราะ emulate" ยังไม่ใช่
คำตอบที่สมบูรณ์ — ทดสอบซ้ำพบว่าผลไม่นิ่ง (fp16 บน CPU: 553s → 0.39s → ค้าง 10+ นาทีอีกครั้ง คนละรัน
กัน โดยไม่ได้แก้อะไรระหว่างนั้น) แปลว่าเป็น **thread contention แบบสุ่ม** (`KMP_DUPLICATE_LIB_OK=TRUE`
ที่ปล่อยให้ faiss กับ torch มี OpenMP runtime ซ้อนกันในโปรเซสเดียว — ดูโค้ด comment ใน
worker_config.py) ไม่ใช่ dtype ที่ช้าตายตัว — ยิ่งสนับสนุนการย้ายไป GPU เพราะ compute ย้ายไปรันบน
GPU เลี่ยง CPU thread contention นี้ได้ทั้งหมด (ไม่ใช่แค่เร็วกว่า แต่เสถียรกว่าด้วย)

**ข้อสรุปสุดท้าย (2026-08-02, ยืนยัน root cause จริง)**: ทดสอบ fp16-CPU rerank ผ่าน Local RAG's
venv โดยตรง (`diagnose_reranker_via_localrag_venv.py`, บังคับ `device="cpu"`) ก็เจอค้าง 10+ นาที
เหมือนกัน — ล้มทฤษฎี "torch version ต่างกันจึงเจอไม่เท่ากัน" ไปเลย เพราะ environment เดียวกันเป๊ะก็
พังได้ ตรวจ Task Manager ระหว่างค้าง: process ใช้ CPU 6.1% (=1/16 core เต็ม 100%, memory ปกติ,
เครื่องรวม CPU แค่ 17%) → **ไม่ใช่ deadlock ไม่ใช่เครื่องรวน กำลังคำนวณจริงแค่ช้าเพราะ single-thread
fp16-on-CPU** แล้วไปตรวจซอร์ส `sentence_transformers/cross_encoder/model.py` (บรรทัด 50-51) พบว่า
`device` param default เป็น `None` = "checks if a GPU can be used" (auto-detect) — และ Local RAG's
`rag_worker.py` **ไม่เคยระบุ `device=` เลย** (โค้ดต้นฉบับปล่อย auto-detect) เพราะ venv ของ Local RAG
มี `torch==2.5.1+cu121` (CUDA build) อยู่แล้วบนเครื่องที่มี RTX 3050 จริง มันจึง **auto-select GPU
มาตลอดในการใช้งานจริง** ไม่เคยตกไป CPU-fp16 path เลย — fp16 บน GPU เร็ว/เสถียร (มี tensor core
รองรับจริง) ส่วน Com Sec เจอบั๊กเพราะ global env เดิมมี `torch==2.13.0` (CPU-only build ไม่มี CUDA
compiled เข้ามา) → auto-detect เจอ `cuda.is_available()==False` → ตกไป CPU+fp16 ที่ช้า/ไม่เสถียร
**สรุป: Local RAG ไม่มีความเสี่ยงแฝงใดๆ ปมทั้งหมดอยู่ที่ Com Sec's global env ขาด CUDA build ของ
torch เพียงอย่างเดียว ซึ่งแก้แล้ว** (ติดตั้ง `torch==2.5.1+cu121` แทน + เพิ่ม explicit `device=`
detection ในโค้ดของ Com Sec เองเพื่อไม่ต้องพึ่ง auto-detect แบบเงียบๆ อีกต่อไป)

- `[x]` แก้ `rag_worker/main.py`'s `_load_everything()` และ `build_confidential_index.py` ให้
  detect GPU อัตโนมัติ (`torch.cuda.is_available()`) — มี GPU ใช้ `device="cuda"` + `fp16`
  (เหมาะกับ GPU tensor core จริง), ไม่มี GPU fallback เป็น `device="cpu"` + **fp32** (ไม่ใช้ fp16
  บน CPU อีกต่อไป กัน regression เดิมถ้าใครรันบนเครื่องไม่มี GPU)
- `[x]` **ติดตั้ง torch แบบ CUDA สำเร็จแล้ว + ยืนยันด้วย live test จริง (2026-08-02)** —
  `pip install torch==2.5.1 --index-url https://download.pytorch.org/whl/cu121` ยืนยัน
  `torch.cuda.is_available()==True` (GPU: NVIDIA GeForce RTX 3050 Laptop GPU), worker log ขึ้น
  `device=cuda, dtype=torch.float16` จริง โหลดโมเดลเสร็จใน ~21s (เร็วกว่า CPU เดิมด้วย) —
  **query จริงหลังแก้: 1-2 วินาที** (จากเดิม 700-1000+ วินาที) ✅ Module 1 ใช้งานได้จริงและเร็วแล้ว
  ว่าติดตั้งแล้วรันบน GPU จริงสำเร็จ (แค่แก้โค้ด+ตัดสินใจ ยังไม่ได้ live test รอบใหม่)
- `[x]` ⚠️→✅ **ผลที่ตามมา — วัด VRAM จริงแล้ว ตัดสินใจ GPU Lock policy แล้ว (2026-08-02)**:
  วัดจริงบนเครื่อง (RTX 3050 Laptop, VRAM รวม 4096MiB) ด้วย `diagnose_vram_module2.py` +
  `nvidia-smi`:
  - RAG worker (resident, รวม Windows desktop overhead แล้ว): **3060MiB**
  - `typhoon-asr` (โหลด+รัน 1 ครั้งในโปรเซสแยก, peak reserved): **564MiB**
  - `Diarization_ThaiSpeech_2022` (โหลด+รัน 1 ครั้งในโปรเซสแยก, peak reserved): **242MiB**
  - เหลือ headroom หลัง RAG worker: 4096 − 3060 = **1036MiB**

  **สรุปตัดสินใจ**: **RAG worker คง resident ต่อไป (ไม่ต้อง unload/เข้าคิวร่วม lock)** — ตัวเดียว
  (typhoon-asr, ตัวที่หนักกว่า) ใช้ 564MiB จาก headroom 1036MiB ที่มี เหลือ margin ~472MiB สบายๆ
  ไม่ต้องแลกความเร็ว RAG query (1-2s) กับการออกแบบ unload-on-idle ที่ซับซ้อนกว่าตามที่กังวลไว้ตอนแรก
  — **GPU Lock ที่ต้องสร้างจริงจึงเป็นแค่ระหว่าง Diarization กับ ASR เท่านั้น** (ตามแผนเดิมของ
  Module 2 ก่อนพบปัญหานี้เลย ไม่ต้องขยายให้ครอบคลุม RAG worker) เพราะทั้งสองรันอยู่ใน**คนละโปรเซส
  จาก RAG worker อยู่แล้ว** (Diarization/ASR รันใน backend's async background task ตาม Module 2 บรรทัด
  "ประมวลผลทีละไฟล์ queue เดียว ไม่ขนาน" — ไม่ต้องมี cross-process lock ซับซ้อน แค่เขียนโค้ดให้
  โหลด Diarization → รัน → `del`+`gc.collect()`+`torch.cuda.empty_cache()` → โหลด ASR → รัน →
  cleanup เหมือนกัน ตามลำดับในโปรเซสเดียวก็พอ) — **CPU fallback ที่ตัดสินใจไว้แล้ว (ดูรายการถัดไป
  ในไฟล์นี้) ยังคงไว้เป็น safety net** เผื่อ margin ~472MiB ถูกกินจาก fragmentation/แอปอื่นที่ใช้ GPU
  พร้อมกัน (เช่นเปิดวิดีโอ hardware-accelerated) — ไม่ได้แก้โค้ด RAG worker ใดๆในหัวข้อนี้ ทิ้ง
  `diagnose_vram_module2.py`/`diagnose_venv` ไว้เป็นเครื่องมือ reuse ได้ถ้าต้องวัดซ้ำ (เช่น
  เปลี่ยนขนาดโมเดลในอนาคต)

## Module 1: Secure Local-RAG (ผู้ช่วยนโยบายบริษัท)

- `[x]` **พบและ reuse โปรเจกต์ที่ทำงานจริงแล้ว**: `D:\Review Policy\Local  RAG` — Streamlit + `rag_worker.py` แยกโปรเซส, LlamaIndex + FAISS + BGE-M3 + BGE-reranker-v2-m3 + Gemini (พร้อม auto-fallback chain), ผ่าน unit test 39 + E2E test 11 บนเครื่องจริงแล้ว
- `[x]` **ตัดสินใจสถาปัตยกรรมสุดท้าย (แก้จาก `/grill-me` รอบ 2, 2026-08-01):** คง RAG worker เป็น**โปรเซสแยกต่อไป** (ตาม HANDOFF.md เดิมเตือนไว้ ไม่เสี่ยง Windows crash) แต่**เขียนชั้น HTTP/routing ใหม่เป็น FastAPI** (แทน `http.server`/`BaseHTTPRequestHandler` เดิมที่เป็นคนละ stack กับ Com Sec) ส่วน RBAC แก้ด้วยการส่ง role/JWT ผ่าน HTTP header ให้ worker เช็คเอง ไม่ต้องรวมโปรเซส
- `[x]` **สร้าง FastAPI worker process ใหม่** (`D:\Com Sec\rag_worker\`, แยกโปรเซสจาก backend หลัก) — เขียนชั้น HTTP ใหม่เป็น FastAPI (`rag_worker/main.py`) แทน `http.server` เดิม ส่วนชั้น logic copy มาจาก Local RAG **ไม่แก้เลยแม้แต่บรรทัดเดียว**: `llm_fallback.py`, `worker_state.py`, `worker_prompts.py`, `worker_parsing.py`, `worker_retrieval.py`, `worker_handlers.py` — เพิ่ม `worker_config.py` เวอร์ชันปรับ path ให้ชี้ไปที่ `storage/`/`models/`/corpus ของ Local RAG โดยตรง (ไม่ copy) ✅ **ยืนยันรันจริงสำเร็จบนเครื่อง Windows แล้ว (2026-08-01)** — โหลด BGE-M3 + reranker + FAISS index จาก Local RAG's `storage/` สำเร็จ ขึ้นสถานะ "ready" และตอบ chat query จริงได้
- `[x]` **`backend/rag.py` เป็น HTTP client เรียกไปหา RAG worker process ใหม่แล้ว** (เดิมเป็น stub คืนค่า hardcoded string) ใช้ `httpx` ยิงไป `http://127.0.0.1:8766` ส่ง `user_id`/`role` ต่อจาก `auth.py` — จับ `ConnectError`/`TimeoutException`/503/403 แปลงเป็น `RAGWorkerError` ให้ `main.py` คืน HTTP 503 ที่มีความหมายแทน error ดิบ ✅ **ทดสอบยิงจริงระหว่าง 2 โปรเซสสำเร็จแล้ว (2026-08-01)** — `/api/rag/query` ตอบ JSON กลับมาจริง (ไม่ error) หลังแก้บั๊ก 2 จุดที่เจอระหว่างเทส (ดูรายการ ⚠️→✅ ด้านล่าง)
- `[x]` **เปลี่ยน session model แล้ว**: worker ใหม่ใช้ `user_id` (จาก JWT/mock token ผ่าน `X-User-Id` header + body) เป็น session key ตรงๆ แทน browser-tab session_id ของ Local RAG เดิม — ครอบคลุมทั้ง general query (`worker_state.sessions`) และ confidential query (`confidential_rag.confidential_sessions`, SessionStore แยกต่างหาก)
- `[x]` **เช็ค corpus หาชื่อบริษัทเก่าตกค้างแล้ว (2026-08-01)** — grep `"ทเวนตี้ โฟร์ คอน แอนด์ ซัพพลาย"` ทั้ง corpus พบ **65 ไฟล์** ยังมีชื่อเก่าอยู่ (Policies 28/49, Procedures 11/11, Manuals 7/11, Forms 19/142) และคำว่า `"24CS"` (รหัสบริษัทเก่า) ปรากฏใน **166 ไฟล์** — ⚠️ **นี่คือรายงานผลการค้นหาเท่านั้น ยังไม่ได้แก้ไขเนื้อหาเอกสารใดๆ** การแก้ไขเนื้อหานโยบาย/กฎหมายเป็นการตัดสินใจของเจ้าของนโยบาย ไม่ใช่สิ่งที่ AI ควรแก้เองโดยพลการ — ต้องตัดสินใจร่วมกับผู้ใช้ก่อนว่าจะ (ก) ปล่อยไว้ตามเดิม (Local RAG's Prefill provenance rule ก็ยึดหลักโชว์วันที่เอกสารให้มนุษย์ตัดสินความ staleness เองอยู่แล้ว) หรือ (ข) ไล่แก้ทีละไฟล์
- `[x]` **Streamlit app เดิม (Local RAG) ไม่ retire — เป็นคนละวัตถุประสงค์กับ Com Sec (ชี้แจงจาก `/grill-me` รอบ 3)**: Local RAG ใช้สำหรับสอบถามนโยบายเชิงลึก (deep policy research) ส่วน Module 1 ของ Com Sec เป็นแค่ RAG Q&A แบบเร็วที่ฝังอยู่ใน workflow เลขาบริษัท (เตรียมประชุม/อนุมัติ) — ทั้งสองระบบอยู่คู่กันถาวร คนละกลุ่มผู้ใช้/คนละ use case **แต่ต้องชี้ไปที่ FAISS index/`storage/` โฟลเดอร์เดียวกัน** (ไม่ copy corpus แยก) ป้องกันไม่ให้ข้อมูลสองระบบ drift กัน
- `[x]` **ติดตั้ง dependencies และรัน backend+worker ขึ้นจริงบนเครื่อง Windows สำเร็จแล้ว (2026-08-01)** — ผู้ใช้รันเองบนเครื่องจริง ทั้ง worker และ backend ขึ้นครบ, `/api/rag/query` ตอบ JSON จริงกลับมา 2 ครั้งติดต่อกัน (ใช้ mock_admin_token) — ระหว่างเทสเจอบั๊กจริง 3 จุด แก้ครบแล้ว:
  1. **`query` เดิมเป็น URL query parameter** → ส่งข้อความไทยดิบใน URL ทำให้ผิด HTTP/1.1 request-line grammar (RFC 7230), uvicorn ปฏิเสธ request ทั้งก้อน ("Invalid HTTP request received.") — แก้เป็นรับผ่าน JSON body (`QueryBody` Pydantic model) แทน
  2. **`RAG_WORKER_TIMEOUT_SECONDS` เดิม default 60s สั้นเกินไป** — worker ใช้เวลาจริง ~1000s ต่อ query แรกๆ (ดู ⚠️ ด้านล่าง) ปรับ default เป็น 1800s ชั่วคราว
  3. **secret หลุดผิดไฟล์**: พบ Google API key จริง + ชื่อบริษัทจริงถูกพิมพ์ลงใน `backend/.env.example` (ไฟล์ template ที่ git track) แทน `backend/.env` (ไฟล์จริงที่ gitignore) — ยืนยันด้วย `git diff` ว่ายังไม่เคย commit/push จึงไม่รั่วจริง สลับค่ากลับเรียบร้อย
- `[x]` ⚠️→✅ **latency ผิดปกติ — ยืนยันสาเหตุแท้จริงแล้ว (แก้จาก stale entry นี้ด้วย `/debug-mantra`, 2026-08-02)**: entry นี้เขียนไว้ตอนที่ยังตั้งสมมติฐานว่าเป็น retry ภายใน `google-genai` SDK — สมมติฐานนั้นถูก**ล้มแล้ว** (falsified) ด้วยการวัดจริงแยกทีละสเตจ พบว่าตัวการจริงคือ **`sentence-transformers` CrossEncoder auto-detect ตกไปที่ CPU+fp16** (ไม่ใช่ SDK หรือ network) — รายละเอียดสาเหตุ+การแก้ครบถ้วนอยู่ที่ Module 0 ด้านบน (บรรทัด "ข้อสรุปสุดท้าย (2026-08-02, ยืนยัน root cause จริง)") ไม่ซ้ำเขียนที่นี่ — คงไว้เป็น breadcrumb ว่าทฤษฎีตั้งต้นคืออะไรและทำไมถึงตัดออก
- `[ ]` เชื่อมต่อ Authentication (Azure AD) จริง — ปัจจุบัน `auth.py` เป็น mock token string ล้วนๆ ไม่มีการ decode JWT/เรียก Azure AD จริง (ยังไม่แตะรอบนี้ — ต้องมี Azure AD tenant ID/client ID จากผู้ใช้ก่อน)
- `[x]` **เพิ่มระบบแยกสิทธิ์เอกสารลับแล้ว (สถาปัตยกรรม)** — ตัดสินใจ**แยกดัชนี**แทนแท็ก metadata ในดัชนีเดียวกับ Local RAG (ดู `rag_worker/confidential_rag.py` docstring สำหรับเหตุผล: Local RAG ไม่มี RBAC เลย ถ้าใส่ BOD minutes ลงดัชนีร่วมจะเสี่ยงข้อมูลลับหลุดไปโผล่ในผลค้นหาของ Local RAG) `rag_worker/main.py`'s `/query_confidential` เช็ค role เทียบ `CONFIDENTIAL_ALLOWED_ROLES` ก่อนเข้าดัชนีลับเสมอ ⚠️ **ยังไม่เคย end-to-end test เพราะยังไม่มีเอกสารลับจริงในระบบเลย** (Module 3 สร้าง minutes / Module 5 approve+archive ยังไม่ถูกสร้าง — ดัชนีลับจะว่างจนกว่าจะมีเอกสารจริงแล้วรัน `build_confidential_index.py`)
- `[x]` **`/api/rag/query` (ทั่วไป) และ `/api/rag/query_confidential` (จำกัดเฉพาะ Com_Sec_Maker/Checker/Board_Member/Global_Admin) ต่อกับ role จริงแล้ว** — `backend/main.py` ส่ง `user["role"]`/`user["user_id"]` จาก `require_role()`/`verify_azure_ad_token()` ต่อไปให้ worker ⚠️ role/user ที่ใช้ตอนนี้ยังมาจาก **mock auth** (ดูรายการด้านบน — Azure AD จริงยังไม่เชื่อม)
- `[x]` ~~โคลนและประยุกต์ใช้ `book-to-skill`~~ — **ตัดออกจากแผนแล้ว และลบโฟลเดอร์ทิ้งแล้ว (`/scrutinize` cleanup 2026-08-01)** ซ้ำซ้อนกับเครื่องมือที่ Local RAG มีอยู่แล้ว (`extract_forms.py`/`convert_forms_to_txt.py`/`dump_raw_forms.py` + Gemini แกะทุกตัวอักษร) ซึ่งรักษาความสมบูรณ์ของเนื้อหา 100% ส่วน `book-to-skill` เป็นเครื่องมือ**กลั่น/สรุป**เนื้อหา (ลด token 24-51 เท่า) ไม่เหมาะกับเอกสารนโยบาย/กฎหมายที่ต้องอ้างอิงคำต่อคำ

## Module 2: Audio Processing & Transcription

- `[x]` ✅ **รองรับไฟล์เสียง/วิดีโอต้นทาง 3 แหล่ง แบบ manual upload เหมือนกันหมด (ตัดสินใจจาก `/grill-me` รอบ 3)**: Google Meet, MS Teams, เครื่องบันทึกเสียง/มือถือ (ออฟไลน์) — ไม่ทำ auto-fetch ผ่าน Google Drive/Graph API ใน MVP, ใช้ `ffmpeg` รองรับทุกฟอร์แมตที่รู้จัก (mp4/wav/mp3/m4a/mov ฯลฯ) ไม่จำกัดชนิดไฟล์ล่วงหน้า — ชั้น extraction เขียนแล้ว (`audio_worker/ffmpeg_utils.py::extract_mono_16k_wav`, ไม่เช็คนามสกุลไฟล์ ปล่อยให้ ffmpeg ตัดสินเอง) **ต่อกับ upload endpoint จริงแล้ว** (`audio_worker/pipeline.py` บรรทัด 130 เรียก `ffmpeg_utils.extract_mono_16k_wav` เป็นสเตจแรกของ `process_audio_file`, ยืนยันรันจริงผ่าน end-to-end test ของ Meeting entity ด้านล่างซ้ำหลายรอบแล้ว — ไม่มีงานค้าง)
- `[x]` **สถาปัตยกรรมเปลี่ยนจากแผนเดิม (2026-08-02, ต่อจาก `/debug-mantra` ที่วัด VRAM จริง)**: เดิมรายการถัดไป (สร้างฟังก์ชันอัปโหลด) ระบุว่ารันผ่าน "FastAPI Async Background Task" ในโปรเซสเดียวกับ backend หลัก — **แก้เป็นแยกเป็นโปรเซสต่างหาก (`D:\Com Sec\audio_worker\`) เหมือน `rag_worker/` แล้ว** เพราะ Diarization+ASR ใช้ torch หนักไม่ต่างจาก RAG worker เลย เสี่ยง Windows WINHTTP.dll crash บั๊กสายพันธุ์เดียวกันถ้ารวมโปรเซส (ผู้ใช้ยืนยันการตัดสินใจนี้ผ่าน AskUserQuestion) — เขียนโครงเสร็จแล้ว: `audio_worker/main.py` (FastAPI, พอร์ต 8767, endpoint `/health` + `/process`), `audio_worker/pipeline.py` (orchestration), `backend/audio.py` (HTTP client เหมือน `backend/rag.py`) ✅ **ยืนยันรันจริงสำเร็จบนเครื่อง Windows แล้ว (2026-08-02)** — `python -m uvicorn main:app --host 127.0.0.1 --port 8767` ขึ้นไม่มี error, `/health` ตอบ `{"status":"ready","state":"idle"}`, ยิง `/process` ด้วยไฟล์ทดสอบ (`typhoon-asr/examples/cv_test.wav`) ผ่าน pipeline เต็มสาย (ffmpeg→diarization→ASR) สำเร็จใน 8.4s ได้ `diarization_segments`+`asr_chunks` กลับมาจริง (ข้อความ ASR ผิดเพี้ยนเพราะไฟล์ทดสอบเป็นภาษาอังกฤษ ไม่ตรงโดเมนโมเดลไทย — ไม่ใช่บั๊ก ยังไม่เคยทดสอบกับเสียงประชุมภาษาไทยจริง)
- `[x]` **สร้าง "การประชุม" (Meeting) เป็น entity แยกต่างหาก ก่อนอัปโหลดไฟล์เสียง (ตัดสินใจจาก `/grill-me` รอบ 3)** — ฟอร์มกรอกล่วงหน้า: วันที่ประชุม, เลขที่การประชุม, รายชื่อผู้เข้าร่วม+ตำแหน่ง, วาระการประชุม — อัปโหลดไฟล์เสียงทีหลังโดยผูกเข้ากับ meeting ที่สร้างไว้แล้ว ✅ **เขียนเสร็จแล้ว (2026-08-02)**: ตัดสินใจ persistence layer ร่วมกับผู้ใช้ = **SQLite + SQLAlchemy ORM** (เทียบ sqlite3 ดิบ/JSON file แล้ว — เลือกเพราะต้องมี FK จริงข้าม Meeting/attendees/agenda และจะขยายอีกใน Module 3-5) — ไฟล์ใหม่: `backend/db.py` (engine/session, `init_db()` เรียกตอน import โมดูล, DB path `backend/com_sec.db`), `backend/models.py` (`Meeting`/`MeetingAttendee`/`MeetingAgendaItem`) — endpoint ใหม่ใน `backend/main.py`: `POST /api/meetings` (สร้าง, role `Com_Sec_Maker`/`Checker`/`Global_Admin`), `POST /api/meetings/{id}/upload` (multipart, sanitize ชื่อไฟล์เป็น `meeting_{id}{ext}` เอง ไม่ใช้ชื่อที่ client ส่งมาตรงๆ กัน path traversal ที่ต้นทาง, เรียก `_process_meeting_audio_background` ผ่าน `BackgroundTasks` ไม่บล็อก HTTP response), `GET /api/meetings`/`GET /api/meetings/{id}` (poll สถานะ) — ✅ **ยืนยันรันจริงสำเร็จบนเครื่อง Windows ครบสาย end-to-end แล้ว (2026-08-02)**: สร้างการประชุม (`POST /api/meetings`) → อัปโหลดไฟล์ทดสอบ (`POST /api/meetings/2/upload`) → background task เรียก audio_worker สำเร็จ → poll `GET /api/meetings/2` เห็น `status="transcribed"` พร้อม `diarization_segments`/`asr_chunks` กลับมาจริงครบ (ทดสอบ error path ด้วยเช่นกัน: ครั้งแรกที่ audio_worker ยังไม่รัน ได้ `status="failed"` + `processing_error` ที่มีความหมายชัดเจนตามที่ออกแบบไว้ ไม่ crash) ⚠️ **ยังไม่ได้ทำ**: RBAC ของ `GET /api/meetings` (ตอนนี้ authenticated user ใดก็เห็นได้หมด), ระบบ retry/คิวจริงถ้า audio_worker ยุ่ง (แค่บันทึก `status="failed"` ให้ผู้ใช้อัปโหลดซ้ำเอง), Alembic migration (ใช้ `create_all()` ตรงๆ พอสำหรับ MVP)
- `[x]` สร้างฟังก์ชันประมวลผลไฟล์เสียง/วิดีโอ (**แยกโปรเซสแล้ว ไม่ใช่ Background Task ในโปรเซสเดียวกับ backend** — ดูรายการด้านบน) **ประมวลผลทีละไฟล์ queue เดียว ไม่ขนาน**: บังคับด้วย `threading.Lock` ใน `audio_worker/pipeline.py` (คืน HTTP 409 ถ้ามีงานค้างอยู่แล้ว)
- `[x]` โคลนโปรเจกต์ `meetily`, `typhoon-asr`, `typhoon2-audio`, `Diarization_ThaiSpeech_2022` (ยืนยันแล้วว่าโคลนจริง มีไฟล์ครบ)
- `[x]` ติดตั้งและปรับใช้ `ffmpeg` สำหรับสกัดเสียงเป็น 16kHz Mono WAV — เขียนโค้ดแล้ว (`audio_worker/ffmpeg_utils.py::extract_mono_16k_wav`) ⚠️ ยังไม่ได้ทดสอบรันจริง (ต้องมี ffmpeg ใน PATH ของเครื่อง — ยังไม่ยืนยันว่าติดตั้งแล้ว)
- `[x]→🐛→✅` **เพิ่ม GPU Lock ตัวเดียวทั้งระบบ**: เขียนแล้วใน `audio_worker/pipeline.py` — โหลด diarization → รัน → cleanup → โหลด ASR → รัน → cleanup ตามลำดับในโปรเซสเดียว (ไม่ต้องมี cross-process lock ครอบคลุม RAG worker ด้วย — ดู Module 0 ด้านบนสำหรับเหตุผล/ตัวเลข VRAM เต็ม) — **`/scrutinize` (2026-08-02) พบบั๊ก CRITICAL**: cleanup เดิม (`diarization.unload_pipeline(pipe)`/`asr.unload_model(model)`) ทำ `del` พารามิเตอร์ **ข้างในฟังก์ชันที่ถูกเรียก** ซึ่งไม่ช่วยอะไรเลย เพราะตัวแปรฝั่งเรียก (`pipe`/`model` ใน `pipeline.py`) ยังอ้างถึง object เดิมอยู่ต่อไป refcount ไม่ตกเป็น 0 จริง `torch.cuda.empty_cache()` เลยไม่ได้ปล่อย VRAM คืนจริงตามที่ตั้งใจ (รันผ่านไม่ error แต่ทำงานผิดเงียบๆ) — **แก้แล้ว**: ย้าย `del`/`gc.collect()`/`empty_cache()` ไปทำในสโคปของฝั่งเรียกเอง (`pipeline.py`'s `_run_diarization_stage`/`_run_asr_stage`) ผ่าน `gpu_utils.release_gpu_memory()` ตัวใหม่ — ✅ **verify ด้วยการวัดจริงแล้ว (2026-08-02, `/debug-mantra`)**: เพิ่ม `gpu_utils.log_vram()` log ทุกจุดโหลด/ปล่อย พบว่า "หลังปล่อย diarization" เหลือ allocated 98MiB (ใกล้ 0, ลดจาก 90MiB ตอนโหลด) แล้ว "หลังโหลด ASR" ขึ้นไป 560MiB ตรงกับตัวเลข ASR เดี่ยวๆที่เคยวัดได้ก่อนหน้า (ไม่ใช่ผลรวมสองโมเดลซ้อนกัน) ยืนยันว่าปล่อย VRAM คืนจริงก่อนโหลดตัวถัดไป ไม่ใช่แค่รันผ่านไม่ error เหมือนบั๊กเดิม
- `[x]` CPU fallback: เขียนแล้ว (`audio_worker/pipeline.py::_run_diarization_stage`/`_run_asr_stage` จับ `torch.cuda.OutOfMemoryError` ตกไป `device="cpu"` อัตโนมัติ) ⚠️ ยังไม่เคย trigger จริง (ต้องมี VRAM ไม่พอจริงถึงจะทดสอบ path นี้ได้)
- `[x]` ✅ **รัน Diarization บนไฟล์เต็มความยาวก่อน (ไม่ตัดชิ้น) แล้วตัด ASR ใหม่ทีละ diarization segment (redesign 2026-08-02, ดู handoff.md 3.3-3.4)** — เดิมตัด ASR เป็นชิ้นละ 1 ชม. คงตายตัว (`transcribe_in_chunks`) แก้เป็นตัดตาม diarization segment ตรงๆแล้ว (`audio_worker/diarization.py::run_diarization` รับไฟล์เต็มเหมือนเดิมไม่เปลี่ยน, `audio_worker/asr.py::transcribe_segments` วนทุก segment ตัดด้วย `ffmpeg_utils.extract_chunk`, sub-split ถ้ายาวเกิน `ASR_MAX_SEGMENT_SECONDS` ค่า default 20s อ้างอิง `typhoon-asr/examples/finetune.py`'s `train_ds.max_duration`) — ✅ **verify จริงบนเครื่อง Windows แล้ว**: อัปโหลด `Diarization_ThaiSpeech_2022/tests/Parliament_1m/Parliament_1m.wav` (เสียงไทยจริง 60s) ผ่านครบ end-to-end ใน 63.2s, sub-split ถูกต้องตามสูตร (segment 29.64s → 2×14.82s เป๊ะ), GPU release VRAM pattern ไม่เปลี่ยน (560MiB→115MiB หลังปล่อย ASR) — - `[x]` ✅ **แก้เสร็จสมบูรณ์แล้ว (ยืนยันด้วย live test 3 รอบ)**: segment สั้นมาก (0.3-0.5s) บางอันเคยคืน `text=""` ว่างเปล่า — **รอบ 1**: ขยับ `MIN_SEGMENT_SECONDS` (ย้ายไป `worker_config.py` เปลี่ยนชื่อเป็น `ASR_MIN_SEGMENT_SECONDS`) จาก 0.1s → 0.5s เป็น duration-heuristic — **live test ยืนยัน**: กรองได้ 3/4 แต่ segment 0.54s (ยาวกว่าเกณฑ์) ยังว่างเปล่าอยู่ดี + เสีย segment 0.37s ที่มีคำจริง ("วันนี้") ไปด้วย — พิสูจน์ว่า duration ไม่ใช่ตัวชี้วัดคุณภาพที่แม่นยำ — **รอบ 2 (ตัดสินใจสุดท้าย, ผ่าน `/scrutinize` แล้ว — APPROVE พร้อมแก้ 1 จุดที่พบ: `.env.example` ค้างค่าเก่า 0.5 แก้กลับเป็น 0.1 แล้ว)**: เปลี่ยนเป็น **filter จากผลจริงหลัง transcribe** (`asr.py`'s `transcribe_segments()` drop entry ที่ text ว่างเปล่าหลังโมเดลตอบมาแล้ว) แทน duration-heuristic — `ASR_MIN_SEGMENT_SECONDS` กลับไปเป็นแค่เกณฑ์ทางเทคนิค (0.1s) + เพิ่ม log สรุป `skipped_too_short`/`dropped_empty_text` ต่อไฟล์ไว้เทียบตอน tune hyperparameter จริง — **รอบ 3 (verify การแก้)**: อัปโหลดไฟล์เดิมซ้ำ ผลตรงตามคาด segment 0.54s ที่เคยว่างเปล่าหายไปแล้ว, segment 0.37s ("วันนี้") ที่เคยเสียไปกลับมาแล้ว, ไม่มี entry ว่างเปล่าเหลือเลยทั้ง 6 entry — **ปิดประเด็นนี้ได้** — ⚠️ **ยังไม่ได้ tune diarization hyperparameter จริง** (ต้นเหตุที่ทำให้มี segment ขยะเกิดขึ้นตั้งแต่ต้น ยังเป็น TODO แยกต่างหาก ไม่ใช่ปัญหาเร่งด่วนแล้วเพราะกรองผลปลายทางได้เรียบร้อยแล้ว) (ต้นเหตุแท้จริงที่ทำให้มี segment ขยะเกิดขึ้นตั้งแต่ต้น ยังเป็น TODO แยกต่างหาก) — ⚠️ **hyperparameter ของ diarization pipeline (`instantiate()`) เป็นค่ากลางๆที่ยังไม่ tune** (เหมือนเดิม ไม่เกี่ยวกับ redesign รอบนี้) — ค่า tune จริงจาก notebook เดิม (DER ~3.9%) ผูกกับ `pyannote.audio` 2.x API ที่ใช้กับเวอร์ชัน 3.3.2 ที่ติดตั้งจริงไม่ได้ **ต้อง tune ใหม่ก่อนใช้กับข้อมูลประชุมจริง**
- `[x]` ✅ **แก้แล้ว (redesign 2026-08-02) — merge ASR เข้ากับ diarization segment เสร็จแล้ว**: เดิมทิ้ง TODO ไว้ว่า diarization ให้ timestamp แม่นยำระดับ segment ผู้พูดแต่ ASR ให้แค่ timestamp ระดับ chunk หยาบๆ (1 ชม./ชิ้น) ต้อง forced-alignment/heuristic มา merge ทีหลัง — **เปลี่ยนวิธีแทน**: ตัด ASR ใหม่ทีละ diarization segment ตรงๆ (segment สั้นๆหลักวินาที) ทำให้ output เป็น `{start, end, speaker, text}` ต่อ segment อยู่แล้วในตัว ไม่ต้อง align/merge อีกขั้นเลย (ผู้ใช้เลือกวิธีนี้เอง ตัดทางเลือก proportional-matching heuristic ทิ้ง) — แลกกับ transcribe เยอะครั้งขึ้นมาก — ⚠️ **สำคัญ**: `typhoon-asr/typhoon_asr_inference.py`'s ฟีเจอร์ "timestamp ต่อคำ" **ไม่ใช่ของจริงจากโมเดล** เป็นแค่ประมาณเส้นตรง (`duration/จำนวนคำ`) ยังไม่ใช้เหมือนเดิม (ดู `audio_worker/asr.py` docstring)
- `[ ]` ⚠️ **Diarization hyperparameter ยังไม่ tune จริง — manual probing ทีละค่าแตะเพดานแล้ว
  (2026-08-03, พบผ่าน `/scrutinize` ตอนไล่ debug คำร้องเรียน "คำพูดมันแปลกๆ" ของผู้ใช้)**: ไล่ขยับค่า
  เดียวทีละตัวด้วยมือ 3 รอบ (`clustering.threshold`: 0.7→1.0→0.85) ได้ผลตรวจสอบจากไฟล์ transcript จริง
  ทุกรอบ (นับ speaker label + คำลงท้ายชาย"ครับ/ฮะ"เทียบหญิง"ค่ะ/คะ" ต่อ speaker ตรงๆจากไฟล์ ไม่เดา):
  0.7→38/33 speaker (over-segment รุนแรง), 1.0→2 speaker (under-segment: ประธาน(ชาย)+เลขา(หญิง) รวม
  เป็นคนเดียวกัน ยืนยันจากคำลงท้าย 62 ครั้ง"ครับ/ฮะ"ปน 99 ครั้ง"ค่ะ/คะ"ใน speaker เดียว), 0.85→15
  speaker (ปัญหาทั้งสองฝั่งพร้อมกัน: คู่ประธาน+เลขายังรวมกันอยู่เป๊ะ 57/97 ครั้ง เกือบเท่ากับตอน 1.0
  เป๊ะ + มี speaker ปลอมเพิ่มอีก ~13 ตัวจาก over-segment กลับมา) — **สรุป**: threshold ตัวเดียวแก้ไม่ได้
  ทั้งคู่พร้อมกัน ต้อง joint-tune หลายพารามิเตอร์เทียบ ground truth จริงแทน manual probing — ผู้ใช้เลือก
  ทางนี้ผ่าน `AskUserQuestion` (ตัวเลือกอื่นที่ไม่เลือก: ปล่อยผ่านไป Module 3 ใช้ Speaker Mapping แก้มือ
  ตอน review / ลองอีก 1-2 ค่าในช่วง 0.85-1.0 ต่อแบบเดิม) — **เขียนเครื่องมือ tuning เสร็จแล้ว**:
  1. `diarization.py`'s `load_pipeline()` แยกส่วนโหลด checkpoint ออกเป็น `build_pipeline(device)`
     (คืน pipeline **ที่ยังไม่ instantiate hyperparameter**) — `load_pipeline()` เดิมยังพฤติกรรมเหมือน
     เดิมทุกอย่าง (เรียก `build_pipeline()` แล้ว instantiate จาก env ต่อ) แค่เพิ่มการเช็คว่ามีไฟล์
     `tuned_diarization_params.yaml` อยู่ไหม ถ้ามีจะโหลดค่านั้นมาทับ env ทั้งหมดอัตโนมัติ
  2. `tune_diarization.py` (ใหม่ทั้งไฟล์) — ใช้ `pyannote.pipeline.Optimizer` (Optuna ข้างใน) ค้นหา
     พร้อมกันทั้ง 5 พารามิเตอร์ที่ประกาศเป็น tunable `Parameter` อยู่แล้วในซอร์สจริงของ pyannote.audio
     3.3.2 (ตรวจสอบจากการดาวน์โหลด wheel มาอ่านจริง ไม่เดา): `segmentation.threshold` (0.1-0.9),
     `segmentation.min_duration_off` (0.0-1.0), `clustering.threshold` (0.0-2.0), `clustering.method`
     (categorical), `clustering.min_cluster_size` (1-20) — optimize เทียบ Diarization Error Rate
     (`SpeakerDiarization.get_metric()` มี `GreedyDiarizationErrorRate` จาก `pyannote.metrics` ในตัว
     อยู่แล้ว เป็น dependency ของ pyannote.audio เอง ไม่ต้องติดตั้งเพิ่ม — เพิ่มแค่ `pyannote.pipeline`
     + `optuna` ใน `requirements.txt`) — ใช้ `tune_iter()` (ไม่ใช่ `tune()`) บันทึกค่าที่ดีที่สุดลง
     `tuned_diarization_params.yaml` ทุกครั้งที่ดีขึ้น กัน progress หายถ้า Ctrl+C กลางคัน
  3. `tuning_ground_truth.example.csv` (ใหม่) — ตัวอย่างฟอร์แมต ground truth ที่ผู้ใช้ต้องเตรียมเอง
     (`start_sec,end_sec,speaker` — ฟังไฟล์ `audio_worker/processed/<job_id>.wav` ที่มีอยู่แล้วจริงช่วง
     สั้นๆ 5-10 นาทีแล้วจดว่าใครพูดช่วงไหนจริง)
  ⚠️ **ยังไม่ได้รันจริง** — สคริปต์ผ่านแค่ `py_compile`/`ast.parse` ในนี้ (ไม่มี GPU/checkpoint/
  ground-truth จริงให้ทดสอบ) **ผู้ใช้ต้องเตรียม ground-truth CSV เองก่อน** (ต้องฟังเสียงจริง — ทำแทนไม่
  ได้) แล้วรัน `python tune_diarization.py --audio ... --ground-truth ... --iterations 30` บนเครื่อง
  Windows ที่มี GPU จริง — ดู docstring หัวไฟล์ `tune_diarization.py` สำหรับขั้นตอนเต็ม
- `[ ]` ⚠️ **ทางเลือกใหม่ที่กำลังทดลองคู่ขนาน (2026-08-04)**: ผู้ใช้ลองโยนไฟล์เสียงเดียวกันเข้า
  NotebookLM ได้ diarization/transcription แม่นกว่า pipeline เราเองมาก — ค้นแล้วพบว่า "MCP
  notebooklm" ที่มีอยู่ทั้งหมดเป็นของ community ไม่เป็นทางการ (reverse-engineer internal API/browser
  automation, อยู่ในเขตเทา ToS ของ Google) **ไม่แนะนำใช้ในระบบจริง** แต่ตั้งสมมติฐานว่าคุณภาพที่ดีกว่า
  มาจาก Gemini ทำ diarization+ASR ในโมเดลเดียวจบ (audio understanding ตรงๆ) — **เขียนสคริปต์ทดลอง
  แยกต่างหาก**: `backend/audio_transcription_experiment.py` ส่งไฟล์เสียงเข้า Gemini ตรงๆ (Files API +
  structured output ขอ `start_seconds`/`end_seconds`/`speaker_label`/`text` ต่อ segment) — **ตรวจ
  จากซอร์สจริงของ `google-genai==2.16.0` แล้วพบว่าห้ามใช้ `GenerateContentConfig(audio_timestamp=
  True)`** (โยน `ValueError` ทันทีถ้าใช้ผ่าน Gemini Developer API mode ที่โปรเจกต์นี้ใช้อยู่ — รองรับ
  เฉพาะ Vertex AI Enterprise mode เท่านั้น) ใช้วิธีขอ timestamp ผ่าน prompt+schema แทน — เพิ่ม
  `GEMINI_MODEL_TRANSCRIPTION`/`_FALLBACK`/`GEMINI_TRANSCRIPTION_TIMEOUT_MS` ใน `config.py`/
  `.env.example` — **Verify**: เขียน mock test 4 เคสในเซสชันนี้ (happy path, polling PROCESSING→
  ACTIVE, ไม่มี API key, ไม่พบไฟล์) ผ่านหมด, `py_compile`/`pyflakes` สะอาด **ยังไม่เคยเรียก Gemini
  จริงด้วยไฟล์เสียงจริง** (มีค่าใช้จ่ายจริงต่อการรัน ต้องให้ผู้ใช้รันเองบนเครื่องจริง) — ถ้าผลดีจริง
  (diarization แม่นกว่า, ไม่ต้อง tune pyannote อีกเลย) จะพิจารณาแทนที่ `audio_worker`'s diarization+
  ASR pipeline ทั้งชุด แต่**ยังไม่ตัดสินใจ** จนกว่าจะมีผลทดลองจริงเทียบกัน
- `[x]` ✅ **ตัดสินใจสถาปัตยกรรมสุดท้ายจาก `/grill-me` (2026-08-04)**: ทดลองจริง 2 รอบ (10 นาที + ไฟล์
  เต็ม 55 นาที ด้วย `gemini-3.5-flash` และ `gemini-3.6-flash`) ยืนยันว่า Gemini native audio ดีกว่า
  pyannote+typhoon-asr มาก (speaker count สมเหตุสมผล ไม่มี fragmentation เร็วกว่า 3-4 เท่า) — grill
  เจาะประเด็นจนครบทุกแขนงแล้ว **สรุปทิศทาง**:
  1. **แทนที่ `audio_worker` ทั้งชุด** (ตัวเลือก A จาก 3 ตัวเลือก: แทนที่/เก็บคู่ขนาน/hybrid fallback)
     — ตรวจ `implementation_plan.md`/`task.md` แล้วพบว่า **ไม่มีเหตุผล compliance ใดๆ** ที่บังคับให้
     diarization/ASR ต้องรัน local เลย เหตุผลเดิมคือข้อจำกัดฮาร์ดแวร์ (GPU 4GB/6GB) ล้วนๆ ไม่ใช่การ
     ตัดสินใจเชิงนโยบาย เก็บ pyannote ไว้เป็นทางเลือกสำรองมีต้นทุนบำรุงรักษาสูงกว่าที่เห็น (CUDA/torch/
     nemo-toolkit/pyannote ทั้งชุด + ปัญหา diarization ที่ยังไม่จบ) จึงตัดสินใจตัดทิ้งทั้งหมด
  2. **ย้าย Gemini call เข้า `backend/` โดยตรง** (ไม่ใช่ worker process แยก) — เพราะไม่มี torch/GPU แล้ว
     ปัญหา WINHTTP.dll crash เดิม (สาเหตุที่ต้องแยก process) ไม่เกี่ยวข้องอีกต่อไป
  3. **แปลง schema ที่ตัว adapter** — Gemini คืน `start_seconds`/`end_seconds`/`speaker_label` ต้อง
     rename เป็น `start`/`end`/`speaker` ให้ตรงกับ `transcript_segments_json` เดิมทันทีตอนรับผล เพื่อไม่
     ต้องแก้ `_extract_speaker_labels()`/speaker mapping endpoint/minutes generation/`app.js` เลย
  4. **Paid-tier gate = documentation เท่านั้น** เหมือน Module 3 เดิม (ไม่มี code enforcement เพราะ
     Gemini API ไม่มีทางเช็คได้ว่า key เป็น free/paid tier จริง) — สอดคล้อง pattern เดิม ไม่สร้างมาตรฐาน
     สองระดับระหว่าง audio กับ text
  5. **Error handling ใช้ pattern เดิมทั้งหมด** — เรียก `transcribe_audio_native()` แบบไม่ใส่ `--model`
     override ให้ใช้ fallback chain `gemini-3.6-flash`→`gemini-3.5-flash` ที่ตั้งไว้แล้วใน `config.py`
     (มี retry-with-backoff อัตโนมัติจาก `llm_fallback.py` อยู่แล้ว) ถ้าพังหมดทุกโมเดล → `status="failed"`
     + `processing_error` เหมือน `audio_worker` เดิม ไม่มี auto-retry queue ใหม่ ผู้ใช้ reprocess เอง
  6. **ลบ `audio_worker/` ทั้งโฟลเดอร์ทิ้ง** (รวม `backend/audio.py` HTTP client, `start_worker.bat`)
     เมื่อถึงเวลาตัดจริง — git history เก็บโค้ดไว้ให้กู้คืนได้ถ้าจำเป็น ไม่เก็บเป็น archive/ แยก
  7. **⚠️ ยังไม่ตัดขาดจริง — รอทดสอบเพิ่มก่อน**: ทดลองจริงมีแค่ไฟล์ประชุมเดียว (คนละรอบ/โมเดล) ยังไม่พอ
     ที่จะมั่นใจว่าคุณภาพดีสม่ำเสมอกับประชุมอื่น (คนพูดเยอะกว่า/เสียงคุณภาพแย่กว่า) — **ต้องทดสอบกับ
     ไฟล์ประชุมอื่นอย่างน้อย 1-2 ไฟล์ก่อน** ค่อยลบ `audio_worker/` และตัด production path จริง เขียนโค้ด
     adapter/wiring (ข้อ 2-3) เตรียมไว้ได้เลยตอนนี้ แต่การ garbage-collect `audio_worker/` ต้องรอผ่าน
     ด่านนี้ก่อน — ดู handoff.md สำหรับ session ที่บันทึกการ grill นี้
- `[ ]` ⚠️ **พบจาก `/scrutinize` (2026-08-02), ยังไม่ได้แก้ — ต้องทำก่อนใช้งานจริง**:
  1. `[x]→🔄` **เดิม: แก้แล้ว — ทดสอบ multi-chunk path จริงแล้ว (2026-08-02, ก่อน redesign)**: ลด `ASR_CHUNK_SECONDS=2` ชั่วคราวแล้วยิงไฟล์ทดสอบเดิมซ้ำ พบว่าการตัดตามเวลาตายตัวตัดกลางประโยคได้จริง — **นี่คือสาเหตุที่เลือก redesign เป็นตัด ASR ทีละ diarization segment แทน** (ดูรายการด้านบน) แทนที่จะพยายาม merge chunk-level เข้ากับ speaker segment ทีหลัง — ⚠️ ข้อจำกัดใหม่ที่ยังไม่ได้ทดสอบจริง: การ **sub-split** segment ที่ยาวเกิน `ASR_MAX_SEGMENT_SECONDS` (คนพูดยาวต่อเนื่องไม่มีใครขัด) ยังตัดกลางประโยคได้เหมือนกัน แค่เกิดถี่น้อยกว่าเดิมมาก (เฉพาะ segment ยาว ไม่ใช่ทุกชิ้น)
  2. **`audio_worker/processed/*.wav` ไม่เคยถูกลบ** — ทุกไฟล์ที่ประมวลผลจะเก็บสำเนา 16kHz mono WAV ไว้ถาวรไม่มีวันลบเอง ดิสก์จะโตไม่มีที่สิ้นสุดถ้าใช้งานสม่ำเสมอ (คนละเรื่องกับ retention policy ของไฟล์ต้นฉบับด้านล่าง แต่เป็นปัญหาคลาสเดียวกัน)
  3. **ไม่มี timeout/watchdog ถ้า diarization หรือ ASR ค้าง** — โปรเจกต์นี้เคยเจอ process ค้าง 10+ นาทีมาแล้วจริงๆ (ดู Module 0 root cause เดิม) ถ้าเกิดซ้ำใน audio_worker จะถือ `_pipeline_lock` ค้างตลอดไป ทำให้ worker รับงานใหม่ไม่ได้อีกเลยจนกว่าจะ restart process เอง
  4. **`meeting_id`/`filename` เพิ่ง validate กัน path traversal พื้นฐานแล้ว** (เช็ค `..`/`/`/`\\`) แต่ worker ยังเป็น HTTP service เปิดบน localhost ไม่มี auth ใดๆเลย — ยอมรับได้ตอนนี้ (เรียกจาก backend เท่านั้น) แต่ต้องทบทวนถ้าจะเปิดให้เรียกจากที่อื่น
- `[x]` เก็บไฟล์เสียง/วิดีโอต้นฉบับไว้ให้ FastAPI serve กลับมาเล่นย้อนหลังได้ (requirement ใหม่จากฟีเจอร์ transcript-sync) — **ทำแล้ว (2026-08-04)**: ไฟล์ต้นฉบับถูกเก็บไว้ที่ `backend/uploads/` อยู่แล้วตั้งแต่ Module 1 (ไม่เคยลบทิ้ง) เพิ่ม `GET /api/meetings/{id}/audio` ให้ stream กลับผ่าน `FileResponse` (รองรับ HTTP Range/206 สำหรับ seek ในตัวจาก Starlette เอง ไม่ต้องเขียน chunking เอง) ดู task.md Module 6
- `[ ]` ⚠️ **นโยบายเก็บรักษาไฟล์เสียง/วิดีโอต้นฉบับ (ยังไม่ตัดสินใจ, พบจาก `/scrutinize`)**: ต้องกำหนด retention period (เช่น ลบอัตโนมัติ N วันหลัง Approve), encryption at rest, และสิทธิ์เข้าถึงระดับไฟล์ (ไม่ใช่แค่ metadata) ก่อนเริ่มเก็บไฟล์จริง — องค์กรมี HR_PDPA_Policy/Data_Breach_Policy ใช้บังคับจริงอยู่แล้ว การเก็บเสียงประชุมบอร์ดโดยไม่มีนโยบายชัดเจนเสี่ยงขัด policy ตัวเอง
- `[x]` ⚠️→✅ **verify VRAM จริงของ `typhoon-asr`** — วัดจริงแล้ว (2026-08-02, ดู Module 0 ด้านบนสำหรับตัวเลขเต็ม): peak reserved 564MiB บน RTX 3050 Laptop (4096MiB) พอกับ VRAM 4GB จริง
- `[ ]` ออกแบบ UX คิวสำหรับ user ที่อัปโหลดพร้อมกัน (queue เดียว ประมวลผลทีละไฟล์ — ต้องมีหน้าจอแจ้งสถานะ/แจ้งเตือนเมื่อเสร็จใน Module 6) — `audio_worker`'s `/health` คืนสถานะ `idle`/`processing` แล้ว (`pipeline.get_status()`) พร้อมให้ frontend poll ได้ แต่ UI ยังไม่ได้ออกแบบ
- `[x]` ✅ **Speaker Mapping (บังคับ, ตัดสินใจจาก `/grill-me` รอบ 3)** — หลัง Diarization เสร็จ ต้องจับคู่ `Speaker_00/01/02...` กับชื่อจริงก่อนกด "สรุปเป็น Minutes" ได้ (Module 3 บล็อกถ้ายังจับคู่ไม่ครบ) — **ตัดสินใจ 2026-08-02 (ผู้ใช้เลือกผ่าน AskUserQuestion)**: ยังไม่มี frontend project ของ Com Sec เองเลย (Module 6 ทั้งหมดยัง `[ ]` ตอนนั้น) เลยทำ **backend ก่อน** แยกจาก UI จริง — **เขียนเสร็จแล้ว**: `backend/models.py` เพิ่ม `Meeting.speaker_mapping_json` (JSON `{label: ชื่อจริง}`), `backend/main.py` เพิ่ม `POST /api/meetings/{id}/speaker_mapping` (role Maker/Checker, ปฏิเสธถ้ายังไม่มี transcript) + `_meeting_to_dict()` คืน `speaker_labels` (label จริงที่เจอใน transcript), `speaker_mapping` (ที่จับคู่ไว้แล้ว), `speaker_mapping_complete` (bool เช็คครบทุก label) — **แก้ edge case ที่พบระหว่างเขียน (mantra 2 trace fail path)**: อัปโหลดไฟล์ใหม่ทับของเดิมได้ (test flow ที่ใช้จริงอยู่แล้ว) แต่ diarization clustering ID ไม่ stable ข้าม run — เพิ่มโค้ดล้าง `speaker_mapping_json` ทิ้งทุกครั้งที่มีการอัปโหลดใหม่ใน `upload_meeting_audio` กัน mapping เก่าผูกกับคนละคนแบบเงียบๆ — ⚠️ **ยังไม่มีปุ่มเล่นตัวอย่างเสียงต่อ speaker** (เป็นงาน UI เพิ่มเติม ยังไม่ทำ — ไม่บล็อกอะไร), **ยังไม่ validate ว่าชื่อที่จับคู่ตรงกับ attendee list ที่กรอกไว้** (ตั้งใจปล่อยให้ยืดหยุ่น เผื่อมีคนพูดที่ไม่ได้อยู่ใน attendee list เช่นผู้บรรยายรับเชิญ) — ✅ **verify ครบทั้ง flow หลักและ edge case จริงบน Windows แล้ว (2026-08-02)**: สร้าง meeting → อัปโหลด `Parliament_1m.wav` → `speaker_labels` ตรง → `POST .../speaker_mapping` → `speaker_mapping_complete` เปลี่ยน `false`→`true` ถูกต้อง persist ผ่าน GET ซ้ำ; re-upload ไฟล์เดิมทับ meeting ที่มี mapping แล้ว → `speaker_mapping` กลับเป็น `{}` ทันที ไม่มีมapping เก่าหลุดค้างข้าม diarization run — **✅ Module 6 (frontend) ต่อ UI จริงแล้วด้วย (ดู handoff.md 3.7)**: `renderSpeakerMapping()` ใน `app.js` + `#mapping-container` ใน `meeting-detail.html`, `<datalist>` autocomplete, ปุ่ม Save Mapping ยิง `POST .../speaker_mapping` จริง verify แล้วในเบราว์เซอร์จริง — **ไม่มีงานค้างทั้ง backend และ frontend แล้ว**
- `[x]` ✅ **หน้าจอแก้ไข Transcript (ไม่บังคับ) — เขียนเสร็จแล้ว (2026-08-02, ดู handoff.md 3.8)**: ให้ Com_Sec_Maker แก้คำถอดเสียงผิดได้ก่อนส่งเข้า Module 3 แต่ข้ามได้ถ้าเชื่อว่าถูกต้องแล้ว — Backend: `PUT /api/meetings/{id}/transcript_segments` เขียนทับทั้ง array (คง `start`/`end`/`speaker` เดิม แก้แค่ `text`) ตรงกับ pattern เดียวกับ speaker_mapping — Frontend: ปุ่ม `#edit-transcript-btn` ใน `meeting-detail.html`, `renderTranscriptEditable()`/`exitTranscriptEditMode()` ใน `app.js` (textarea ต่อ segment, Save ยิงทีเดียวทั้งชุด, Cancel re-render จาก memory ไม่ยิง API) — `node --check`/`py_compile`/`pyflakes` ผ่านหมด ⚠️ **ยังไม่ได้ทดสอบจริงในเบราว์เซอร์** รอผู้ใช้เปิด `/dashboard/` ทดสอบ Edit → Save/Cancel
- `[x]` บันทึกความเสี่ยงกฎหมายเรื่อง license ของ `Diarization_ThaiSpeech_2022` ไว้แล้ว (ดู Module 0)
- `[ ]` `typhoon2-audio`: ไม่ integrate ตอนนี้ เก็บไว้เป็นเอกสารอ้างอิงสำหรับตัวเลือก production บน cloud GPU เท่านั้น

## Module 3: Meeting Minutes Generation

- `[x]` ✅ **ใช้ Gemini ผ่าน `google-genai` SDK ตรงๆ (ไม่ใช่ Claude, ไม่ผ่าน llama_index) — เขียนเสร็จแล้ว
  (2026-08-03, `/debug-mantra`)**: เดิม task นี้เขียนไว้ว่า "SDK เดียวกับ Local RAG" ซึ่งของจริงคือ Local
  RAG's `llm_fallback.py::build_llm()` ห่อด้วย `llama-index-llms-google-genai` (ไม่รองรับ
  `response_schema` ตรงๆ ผ่าน `.complete()`) — ใช้ raw `google-genai` `Client.models.generate_content()`
  แทน (ยืนยันจากซอร์สจริงของ package ว่า `GenerateContentConfig.response_schema` + `response.parsed`
  คืน Pydantic instance ให้ตรงๆ ไม่ต้อง parse เอง) **reuse `llm_fallback.py`'s `run_with_fallback()`
  ได้ตรงตามแผนเดิม** เพราะมันรับ `factory`/`call` เป็น callable ทั่วไป ไม่ผูกกับ llama_index — copy
  `rag_worker/llm_fallback.py` ไป `backend/llm_fallback.py` ตรงๆ ไม่แก้ (ตาม convention เดียวกับที่
  rag_worker copy จาก Local RAG) — **สถาปัตยกรรม**: เรียก Gemini ตรงจากโปรเซส backend เอง ไม่สร้าง
  โปรเซสที่ 3 เพิ่ม (ต่างจาก rag_worker/audio_worker) เพราะ `google-genai` ไม่มี native library
  (torch/faiss) ที่จะชน Windows WINHTTP.dll — เหตุผลเดิมที่ต้องแยกโปรเซสไม่เกี่ยวข้องกับกรณีนี้
- `[x]` ✅ **ใช้ native structured output ของ Gemini (`response_schema`+`response_mime_type`) แทน
  Instructor — เขียนเสร็จแล้ว**: `backend/minutes_schema.py::MinutesGenerationResult` ส่งตรงเป็น
  `response_schema` ผ่าน `backend/minutes_generation.py`
- `[x]` ✅ **ออกแบบ Pydantic schema เสร็จแล้ว (คุยกับผู้ใช้ผ่าน `AskUserQuestion` ก่อนเขียนโค้ด)**:
  เปิดไฟล์ template จริง `260628 Draft_EMPIRE - BOD Minutes 15-2569 v.5.docx` ดูก่อน (ของจริงที่เขียน
  เสร็จแล้ว ไม่ใช่ template ที่มี placeholder — มีตารางย่อยรายละเอียดธุรกรรม/ตัวเลข/สัดส่วนหุ้นซับซ้อน
  มาก) — ผู้ใช้เลือก **schema แบบยืดหยุ่น (Recommended)**: ต่อวาระมีแค่ `discussion_summary`/
  `resolution_status`/`resolution_text` เป็น free text ไม่พยายามแยก field ตัวเลข/ตารางธุรกรรมจาก
  template ตรงๆ (ลดความเสี่ยง AI หลอนตัวเลขถ้า transcript พูดไม่ครบ) — เรื่องแมปไปยัง Word template
  ละเอียด (ตาราง/ตัวเลข) ต้องรอ Module 4 ที่มนุษย์ (Maker/Checker) กรอก/ตรวจเพิ่มเอง ยังไม่ทำตอนนี้ —
  **การลดความเสี่ยงหลอนอีกชั้น**: agenda_items ที่ส่งเข้า Gemini มาจาก `MeetingAgendaItem` ของจริงใน
  DB เท่านั้น (ห้ามเพิ่มวาระใหม่เอง, เช็คจำนวน/agenda_order ตรงกันเป๊ะก่อนยอมรับผลลัพธ์ — ดู
  `minutes_generation.py::generate_minutes()` validation), field ที่เป็น ground truth จาก DB อยู่แล้ว
  (ชื่อบริษัท/เลขที่ประชุม/วันที่/รายชื่อผู้เข้าร่วม) **ไม่ให้ Gemini สร้างเลย** — merge เข้าไปทีหลัง
- `[x]` ✅ **เขียน prompt ใหม่เสร็จแล้ว**: `backend/minutes_prompts.py` — transcript แปลงเป็นข้อความ
  พร้อมชื่อผู้พูดจริง (ผ่าน speaker_mapping ที่บังคับครบ 100% แล้ว) + timestamp `[MM:SS]`, system
  prompt เน้นกฎห้ามหลอนตัวเลข/ห้ามเพิ่มวาระใหม่/ห้ามแต่งเนื้อหาเกินกว่า transcript ระบุจริง
- `[x]` ✅ **ใช้ Gemini API แบบเปิด billing (paid tier) — ตั้งค่าไว้แล้ว**: ใช้ `GOOGLE_API_KEY` เดียวกับ
  ที่ Module 1 ยืนยันแล้วว่าเป็น paid tier ใน `backend/.env` (ไฟล์เดียวกับ rag_worker ใช้ค่าคนละตัวแปร
  environment คนละไฟล์ .env — ดู `backend/.env.example`) — ⚠️ **พบบั๊กจริงระหว่างเขียน (mantra 4,
  cross-reference กับ requirements.txt)**: `python-dotenv` อยู่ใน requirements.txt มาตั้งแต่ Module 1
  แต่ไม่มีจุดไหนในโค้ด backend เรียก `load_dotenv()` เลยสักครั้ง — `backend/.env` ไม่เคยถูกโหลดเข้า
  `os.environ` จริง (ไม่กระทบอะไรมาก่อนเพราะยังไม่มีโค้ดอ่าน env var จาก `.env` มาก่อน Module 3) —
  แก้แล้วด้วย `backend/config.py` (ใหม่ทั้งไฟล์ เรียก `load_dotenv()` รวมศูนย์ที่เดียว)
- `[x]` เขียน endpoint `POST /api/meetings/{id}/generate_minutes` (role Maker/Checker/Global_Admin
  เหมือน `MEETING_MANAGE_ROLES` อื่น) — **บังคับ Speaker Mapping ครบ 100% ก่อนเสมอ** (ตัดสินใจจาก
  `/grill-me` รอบ 3 ที่ค้างไว้ตั้งแต่เดิม) แยก helper `_is_speaker_mapping_complete()` ออกมาใช้ร่วมกับ
  `_meeting_to_dict()` กันตรรกะ diverge — เขียนทับ `Meeting.minutes_json`/`minutes_generated_at`
  ทั้งก้อนเสมอถ้าเรียกซ้ำ (ยังไม่มี versioning — ตรงกับ pattern JSON blob อื่นของโปรเจกต์นี้)
- `[x]` **Verify ที่ทำแล้วในเซสชันนี้**: `py_compile`/`pyflakes` สะอาดทุกไฟล์ที่แก้/สร้างใหม่, เขียน
  unit test ชั่วคราวใน sandbox (mock `google.genai.Client`, ไม่ต้องมี API key จริง) ยืนยัน 5 เคส:
  happy path (primary model), fallback ทำงานถูกต้อง, ปฏิเสธผลลัพธ์ถ้าจำนวนวาระไม่ตรง, error ชัดเจนถ้า
  ไม่มี API key, error ชัดเจนถ้าไม่มีวาระเลย — **ยังไม่เคยเรียก Gemini จริง** (sandbox ไม่มี API key จริง)
  และ **ยังไม่เคยทดสอบปุ่ม Generate Minutes ในเบราว์เซอร์จริง** (`node --check` ผ่านเท่านั้น) — ผู้ใช้
  ต้องเปิด `/dashboard/` กด Generate Minutes บน meeting ที่ speaker mapping ครบแล้วทดสอบเอง
- `[ ]` ⚠️ **ยังไม่ได้ทำ**: วัด latency จริงของการเรียก Gemini structured output (ไม่มีตัวเลขอ้างอิง
  — ตั้ง `GEMINI_MINUTES_TIMEOUT_MS` เท่ากับ rag_worker's `GEMINI_REQUEST_TIMEOUT_MS` (5 นาที) ไปก่อน
  เผื่อเจอบั๊ก latency ผิดปกติแบบเดียวกับที่ Module 1 เคยเจอ), versioning/ประวัติการสร้าง Minutes ซ้ำ
  (สร้างซ้ำแล้วเขียนทับของเก่าหายไปเลยตอนนี้ — พอสำหรับ MVP), การแมปไปยัง Word template จริงเป็นของ
  Module 4

## Module 4 & 5: Word Template Mapping & Secure Delivery

- `[x]` ✅ **Multi-template (2026-08-03, เพิ่มทันทีหลังจบ session แรกของ Module 4-5 — ผู้ใช้ถามว่าจะดู/
  แก้ template ตอนนี้และในอนาคตยังไงถ้าต้องมีประชุมที่ใช้ form อื่น)**: เพิ่ม `Meeting.template_name` +
  `docx_generation.TEMPLATE_REGISTRY` (dict ชื่อ→{filename, label}) — dropdown "Document Template"
  ใหม่ในหน้า Create Meeting (โหลดรายการจาก `GET /api/templates` ใหม่ ไม่ hardcode ใน frontend) เลือก
  ได้ตอนสร้างประชุมเท่านั้น (แก้ทีหลังไม่ได้ผ่าน UI ตอนนี้ — ตั้งใจ กันสับสนหลังมี minutes ไปแล้ว) —
  **ข้อจำกัดที่ตั้งใจ**: ทุก template ต้องใช้ Jinja context ชุดเดียวกัน (ต่างได้แค่ layout/ถ้อยคำ ไม่ใช่
  ชุดข้อมูล) สร้าง `subcommittee` เป็นตัวอย่าง template ที่ 2 (ต่างจาก `bod_minutes` แค่คำในหัวเรื่อง)
  พิสูจน์ว่ากลไกทำงานได้จริงด้วย unit test เต็ม flow (list templates → สร้างประชุมเลือก
  `subcommittee` → generate_docx → เปิดไฟล์ผลลัพธ์เช็คว่าใช้หัวเรื่องที่ถูกต้อง → เทียบกับ meeting อีก
  ใบที่ไม่ระบุ template_name แล้ว fallback เป็น `bod_minutes` ถูกต้อง) — **ทุก assertion ผ่านหมด**
  **วิธีเพิ่ม template ใหม่ในอนาคต (ไม่ต้องแตะโค้ด Python เลยก็ได้)**: ก็อปปี้ไฟล์ `.docx` ที่มีอยู่ไป
  ชื่อใหม่ในโฟลเดอร์ `backend/templates/` → เปิดแก้ layout/ถ้อยคำด้วย Microsoft Word ตรงๆ (ห้ามลบ/พิมพ์
  ผิด Jinja tag เดิม) → เพิ่ม 1 entry ใน `docx_generation.TEMPLATE_REGISTRY` ชี้ไปที่ไฟล์ใหม่ — ยืนยัน
  แล้วว่าเปิด/แก้/เซฟด้วย Word จริงไม่ทำให้ template พัง (ผู้ใช้เปิดไฟล์ `minutes_template.docx` ดูเอง
  ระหว่างเซสชันนี้ ไฟล์ขนาดเปลี่ยนจาก Word resave แต่ยัง render ผ่าน `docxtpl` ได้ปกติทุกจุด — verify
  ซ้ำแล้ว)

- `[x]` ✅ **วิเคราะห์ไฟล์เทมเพลต `260628 Draft_EMPIRE - BOD Minutes 15-2569 v.5.docx` แล้ว** (ซ้ำกับที่
  Module 3 เคยเปิดดูแล้ว แต่รอบนี้ดูละเอียดถึงระดับ font/margin/alignment ด้วย python-docx) ยืนยันอีกครั้ง
  ว่าเป็นรายงานที่เขียนเสร็จสมบูรณ์แล้ว **ไม่มี placeholder เลยสักจุด** — ฟอนต์ TH SarabunPSK 15pt, A4,
  margin ซ้าย/ขวา/บน 1 นิ้ว ล่าง 0.886 นิ้ว, หัวเอกสารจัดกึ่งกลาง, เนื้อหาจัด Thai-Justify — ดึงค่าพวกนี้
  มาใช้ตรงๆใน template ใหม่ (ดูข้อถัดไป)
- `[x]` ✅ **สร้าง template ใหม่ด้วย `docxtpl` แทนการพยายามใช้ไฟล์จริงเป็น template** (ตัดสินใจจาก
  `AskUserQuestion` ก่อนเขียนโค้ด — ไฟล์จริงมีตารางธุรกรรม/ตัวเลข/สัดส่วนหุ้น 3 ตารางที่ผูกกับการประชุม
  ครั้งนั้นเฉพาะ ไม่ generic พอ): `backend/build_minutes_template.py` (สคริปต์สร้าง, รันครั้งเดียว) →
  `backend/templates/minutes_template.docx` (ไฟล์ผลลัพธ์ที่ commit เก็บไว้) ใช้ Jinja tag ของ `docxtpl`
  (`{{ }}` ธรรมดา + `{%p for/endfor %}` สำหรับ loop attendees/agenda_items ที่ลบพารากราฟ tag ทิ้งเอง
  หลัง render ไม่เหลือบรรทัดว่าง) — **verify ด้วยการ render จริงในเซสชันนี้** (ไม่ใช่แค่ทฤษฎี): ยืนยันว่า
  loop/{{ }}/`{%p %}` ทำงานถูกต้องครบทุกจุดด้วยข้อมูลตัวอย่าง 2 วาระ 2 ผู้เข้าร่วม
- `[x]` ✅ **เขียนโค้ด render minutes_json ลง template**: `backend/docx_generation.py`'s
  `render_minutes_docx()` — แปลง `minutes_json` (โครงสร้างจาก Module 3's `MinutesOfMeeting`) เป็น
  context ของ Jinja tag, แปลงวันที่ ISO (ค.ศ.) เป็นข้อความไทย พ.ศ. เอง (`thai_date()`, ไม่พึ่ง
  `locale.setlocale("th_TH")` ที่อาจไม่มีบนเครื่อง Windows), แปล `resolution_status` enum ภาษาอังกฤษเป็น
  label ไทย (มี `assert` กันลืมแก้ถ้ามีสถานะใหม่เพิ่มใน `minutes_schema.py` ในอนาคต) — เขียนทับไฟล์
  `generated_docs/meeting_{id}_draft.docx` เดิมเสมอถ้า regenerate ซ้ำ
- `[x]` ✅ **ตกลงกับผู้ใช้แล้วว่ารายละเอียดตาราง/ตัวเลขธุรกรรม (ที่ Module 3 ไม่สร้างให้ กันหลอน) ให้ Maker
  เพิ่มเองด้วย Microsoft Word หลังดาวน์โหลดร่าง** (ตัดสินใจจาก `AskUserQuestion`, ไม่สร้าง table editor
  ในระบบ) — flow จริง: `POST .../generate_docx` (สร้าง/regenerate ร่าง) → `GET .../download_docx?variant=draft`
  → แก้ด้วย Word เอง → `POST .../upload_final_docx` (อัปโหลดกลับ, เข้าสถานะ `Pending_Review` ทันที) —
  เก็บ path ร่าง (`minutes_docx_path`) กับฉบับสมบูรณ์ (`final_docx_path`) แยกกันคนละคอลัมน์ใน `Meeting`
- `[x]` ✅ **เขียนระบบจัดการ Approval Flow (Maker/Checker) เสร็จแล้ว ครบ 4 สถานะตามแผน** —
  `Meeting.approval_status`: `Draft` → (อัปโหลดฉบับสมบูรณ์) → `Pending_Review` → Checker
  `POST .../review` (`action: "approve"|"reject"`) → `Needs_Revision` (บังคับมี `comment` เสมอ, กลับไป
  ให้ Maker แก้แล้วอัปโหลดใหม่ได้) หรือ `Approved` (ต้องมี `final_docx_path` แล้วเท่านั้น) — **เฉพาะ
  `Com_Sec_Checker` เท่านั้นที่เรียก `/review` ได้** (role อื่นได้ 403 — verify แล้วด้วย unit test จริง
  ในเซสชันนี้) — audit trail เก็บที่ตาราง `MeetingApprovalLog` ใหม่ (append-only, บันทึกทุก
  submit_for_review/reject/approve/delivery_failed/email_failed พร้อม user_id+timestamp+comment)
- `[x]` ✅ **สร้างฟังก์ชันส่ง Automated Secure Email (Magic Link) ถึงผู้เข้าร่วมที่กรอกอีเมลไว้ หลัง
  Checker Approve** — **ใช้ SMTP ธรรมดา (`smtplib`) แทน Microsoft Graph API** (ตัดสินใจจาก
  `AskUserQuestion`: Azure AD ยังไม่เชื่อมต่อจริงในระบบเลย ดู `auth.py`) — **เพิ่ม
  `MeetingAttendee.email` ให้ Maker กรอกเองต่อการประชุม** แทนที่จะรอ Azure AD จริงหรือ hardcode ผ่าน
  `.env` (ตัดสินใจจาก `AskUserQuestion` เช่นกัน — ยังไม่มีตาราง user/email จริงในระบบเลยสักตาราง)
  attendee ที่ไม่กรอก email จะไม่ได้รับอีเมล ไม่ error — **ต้องกำหนด token expiration + single-use
  ตั้งแต่ตอนออกแบบ (พบจาก `/scrutinize`) — ทำแล้ว**: ตาราง `MagicLinkToken` ใหม่ (256-bit random token,
  `expires_at`/`used_at` แยกกันชัดเจน, `verify_and_consume_token()` mark ใช้แล้วทันทีกันเปิดซ้ำ) —
  **verify single-use + expiry จริงด้วย unit test ในเซสชันนี้** (เปิดลิงก์ครั้งที่ 2 ได้ 400 ถูกต้อง)
- `[x]` ✅ **แปลง .docx → PDF (Password-Protected)**: ถามผู้ใช้แล้วเครื่อง Windows มี Microsoft Word
  ติดตั้งอยู่ → ใช้ `docx2pdf` (COM automation ผ่าน Word) ใน `backend/pdf_generation.py`, ใส่รหัสผ่านด้วย
  `pypdf` (pure Python ไม่ต้องพึ่ง qpdf binary ภายนอกเหมือน `pikepdf`) — **verify การเข้ารหัส/ถอดรหัส
  PDF จริงด้วย `pypdf` ในเซสชันนี้แล้ว** (สร้าง PDF ทดสอบ → ใส่รหัสผ่าน → ถอดรหัสด้วยรหัสผ่านที่เก็บใน DB
  จริง → อ่านเนื้อหาได้ถูกต้อง) — **⚠️ ส่วน `docx2pdf`/Word COM automation เองยังไม่เคยรันจริงสักครั้ง**
  (sandbox ไม่มี Windows/Word) verify ได้แค่ `py_compile`/`pyflakes` เหมือนโค้ดที่พึ่ง GPU/เบราว์เซอร์ทุก
  ครั้งก่อนหน้านี้ — ผู้ใช้ต้อง live test บนเครื่องจริงก่อนถือว่าใช้งานได้ (ดู handoff.md "How to resume")
- `[x]` ✅ **ระบบ Archive ไฟล์แบบเลือกปลายทางได้ (พบจาก `/grill-me` รอบ 2)** — `backend/archive.py`
  ใหม่ทั้งไฟล์ แยก 2 ปลายทางตามประเภทไฟล์ตามแผนเป๊ะ:
  1. `documents_destination` (`config.ARCHIVE_DOCUMENTS_DESTINATION`) — final `.docx`+PDF หลัง Approve
  2. `recordings_destination` (`config.ARCHIVE_RECORDINGS_DESTINATION`) — ไฟล์เสียงต้นฉบับ (จาก
     `UPLOAD_DIR`) — **ยังไม่ได้รวม transcript JSON dump เป็นไฟล์แยกไปด้วย** (ขอบเขตที่ตัดไว้รอบนี้
     เพื่อจำกัดสโคป — แค่ archive ไฟล์เสียงต้นฉบับพอสำหรับตอนนี้)
  - Implementation: `shutil.copy2` ไป UNC path ตรงๆตามแผน ไม่พึ่ง SharePoint Graph API — **ค่าว่าง (ยัง
    ไม่ตั้ง .env) = ข้าม + log warning เฉยๆ ไม่ทำให้ทั้ง flow Approve ล้มเหลว** (ตัดสินใจเอง, ไม่ใช่คุย
    กับผู้ใช้แยก — เหตุผล: archive เป็นเรื่อง operational ไม่ควร block การตัดสินใจ approve ที่สมบูรณ์แล้ว)
    ยังไม่มี UNC path จริงให้ทดสอบตอนนี้ (ผู้ใช้ต้องตั้งค่าเองก่อนใช้งานจริง)
- `[x]` **ปรับ RBAC ของฟีเจอร์ transcript-sync player**: จำกัดเฉพาะ Com_Sec_Maker/Checker/Global_Admin เท่านั้น (แคบกว่า `/api/rag/query_confidential` เดิมที่รวม Board_Member ด้วย) — เพราะไฟล์เสียงดิบเป็นคนละชั้นความลับกับรายงานฉบับสมบูรณ์ที่ส่งให้บอร์ด — **ทำแล้ว (2026-08-04)**: `GET /api/meetings/{id}/audio` (backend/main.py) ผูก `require_role_for_audio_stream(MEETING_MANAGE_ROLES)` เดียวกับ upload/speaker_mapping — Board_Member โดน 403 จริง ดู task.md Module 6 + handoff.md session ล่าสุดสำหรับรายละเอียดเต็ม (⚠️ ยังไม่เคย live test จริงในเบราว์เซอร์กับทุก role — ตรวจแค่ตรรกะ/`py_compile`/`pyflakes`)
- `[x]` **Verify ที่ทำแล้วในเซสชันนี้ (มากกว่าแค่ py_compile/pyflakes)**: เขียน end-to-end test จริงด้วย
  FastAPI `TestClient` (mock `pdf_generation.convert_docx_to_pdf`/`email_service.send_magic_link_email`
  เพราะ sandbox ไม่มี Word/SMTP จริง — ส่วนที่เหลือทั้งหมดรันจริงไม่ mock) ครอบคลุม: สร้าง draft docx →
  ดาวน์โหลด → อัปโหลด final → Maker ถูกบล็อกจาก `/review` (403) → reject ไม่มี comment ถูกบล็อก (400) →
  reject มี comment → `Needs_Revision` → อัปโหลดใหม่ → `Pending_Review` → approve → PDF ถูกสร้าง+ใส่
  รหัสผ่านจริง (ถอดรหัสสำเร็จด้วยรหัสที่เก็บใน DB) → Magic Link ส่งเฉพาะ attendee ที่มี email (1 ใน 2
  คน) → เปิดลิงก์สำเร็จ → เปิดซ้ำถูกปฏิเสธ (single-use) → approval log มีครบ 4 entry ตามลำดับที่ถูกต้อง
  — **ทุก assertion ผ่านหมด** (ไฟล์ทดสอบเป็น throwaway ใน `/tmp`, ลบไฟล์ที่หลุดเข้า `generated_docs/`
  จริงหลังเทสเสร็จแล้วผ่าน `allow_cowork_file_delete`)
- `[ ]` **ยังไม่ได้ทำ**: live test จริงบนเครื่อง Windows (Word COM automation/SMTP จริง/UNC path
  จริง — ดู handoff.md "How to resume"), versioning ของรอบ approve ที่ >1 (เก็บแค่ path ล่าสุดเสมอ
  เหมือนไฟล์อื่นของโปรเจกต์ ไม่เก็บทุก revision แยก), Module 6 frontend panel ยังไม่เคยเปิดจริงใน
  เบราว์เซอร์เลย (เขียนจาก static analysis เหมือนงาน frontend อื่นๆของโปรเจกต์นี้ทุกครั้ง)

## Module 6: Front-End UI Integration

- `[x]` ✅ **อ่านไฟล์ `EMPIRE CI(1).png` แล้ว** ดึงสี/โทนจริง (ไม่ใช่เดา — ดู handoff.md 3.6 สำหรับ hex code เต็ม)
- `[x]` ~~ใช้ Stitch MCP Generate~~ — **"Stitch MCP" ไม่มีอยู่จริงในระบบ** (เช็ค MCP registry แล้วไม่พบ, ดู handoff.md 3.6) ผู้ใช้ใช้ **Google Stitch ผ่าน Antigravity แทน** (เครื่องมือคนละตัว, ออกแบบเองนอกเซสชันนี้) ได้ผลลัพธ์เป็น static HTML/CSS 4 ไฟล์ที่ `D:\Com Sec\ComSecAI_Dashboard\`
- `[x]` ✅ **นำ UI มาเชื่อมกับ FastAPI แล้ว (2026-08-02)** — mount เป็น static files ที่ `/dashboard` ผ่าน `StaticFiles(html=True)` ใน `backend/main.py` — **ไม่ต้องตั้ง CORS เลย** (ต่างจากที่ item เดิมกลัวไว้ เพราะ serve same-origin กับ `/api/*` จาก FastAPI เดียวกัน ไม่ใช่ dev server แยก) เขียน `ComSecAI_Dashboard/app.js` ต่อทั้ง 3 หน้า (dashboard/create-meeting/meeting-detail) เข้ากับ endpoint จริงครบ (`GET/POST /api/meetings`, upload, speaker_mapping) — ✅ **verify จริงในเบราว์เซอร์สำเร็จแล้ว (2026-08-02)** — ทดสอบ flow เต็ม: สร้างประชุม → อัปโหลด → poll จน transcribed → จับคู่ผู้พูด → export transcript (.txt) สำเร็จ ตรวจไฟล์ที่ export ออกมาแล้วถูกต้องทุกจุด (timestamp/ชื่อที่จับคู่/ข้อความตรงกับข้อมูลจริง) — **ไม่มีรายงานบั๊ก UI/layout กลับมา**
- `[x]` ⚠️→✅ **ฟีเจอร์ใหม่: Synced Audio/Video Player + Transcript Panel** (แบบดูวิดีโออบรมออนไลน์ที่มี script ด้านขวา) — อ้างอิงแพทเทิร์นจาก `meetily/frontend` (`AudioPlayer.tsx`/`useAudioPlayer.ts`/`TranscriptView.tsx`, ตรวจซอร์สจริงแล้ว `AudioPlayer.tsx` เป็นไฟล์ว่างเปล่า ใช้แค่ `useAudioPlayer.ts`+`TranscriptView.tsx` เป็นแนวทาง) เขียนใหม่ด้วย HTML5 `<audio>` + `ontimeupdate` แทน Tauri-specific AudioContext/`invoke('read_audio_file')` เดิม (เว็บ same-origin ไม่มีข้อจำกัดแบบ Tauri ให้ต้องอ้อม) — **ทำแล้ว (2026-08-04)**: Playback panel ใหม่ใน `meeting-detail.html` (นอก `main-content-grid` ตั้งใจ — โชว์ได้ตั้งแต่ status=uploaded ไม่ต้องรอ transcribed) ผูกกับ `transcript-container` เดิม 2 ทาง: (1) click บรรทัด transcript → seek `<audio>` ไปเวลานั้น+เล่นต่อ (2) `timeupdate` → ไฮไลต์บรรทัดที่กำลังเล่นอยู่ (`.transcript-line.active`, auto-scroll ถ้ายังไม่อยู่ในมุมมอง) ดู `app.js`'s `setupAudioPlayer`/`highlightActiveTranscriptSegment`/`meetingAudioUrl`
  - **สโคปที่ตัดออกตั้งใจ (ไม่ใช่ MVP นี้)**: video-only ไม่มี custom scrubber/theme (ใช้ native `<audio controls>` เหมือน pattern `input[type=file]` เดิมของโปรเจกต์ที่ปล่อย browser-native ไป), ไม่มี `<video>` element แยก (ไฟล์ต้นฉบับที่เป็นวิดีโอ เช่น Google Meet/Teams recording ยังเล่นได้ผ่าน `<audio>` เอง แค่ไม่เห็นภาพ — พอสำหรับ "ฟังย้อนหลัง" ตามที่ผู้ใช้ขอรอบนี้)
  - **RBAC**: `GET /api/meetings/{id}/audio` ผูก role เดียวกับ `MEETING_MANAGE_ROLES` (Com_Sec_Maker/Checker/Global_Admin) ผ่าน `require_role_for_audio_stream` ใหม่ใน `auth.py` (รับ token ผ่าน query string เพราะ `<audio src=...>` แนบ header เองไม่ได้ — ดู docstring เต็มใน `auth.py`/`main.py` สำหรับความเสี่ยงที่รู้อยู่แล้วเรื่อง token ใน query string ของ mock auth)
  - **Verify ที่ทำแล้ว**: `py_compile`/`pyflakes` สะอาด (backend), `node --check app.js` ผ่าน — **⚠️ ยังไม่เคยเปิดจริงในเบราว์เซอร์เลย** (เขียนจาก static analysis เหมือนงาน frontend อื่นๆของโปรเจกต์นี้ทุกครั้ง ต้องให้ผู้ใช้ทดสอบบนเครื่อง Windows จริง: เล่น/pause/seek ทำงานถูกไหม, click transcript แล้ว seek ตรงไหม, ไฮไลต์ตามเวลาจริงไหม, Board_Member โดน 403 จริงไหม)
- `[x]` ✅ หน้าจอแก้ไข Transcript (ไม่บังคับ, ตามแผน Module 2) — **เขียนเสร็จแล้ว** (ดู Module 2 รายการด้านบนสำหรับรายละเอียดเต็ม + handoff.md 3.8) — Stitch ไม่ได้ออกแบบมาด้วยแต่เพิ่มเข้าไปเองจนครบ ⚠️ ยังไม่ได้ทดสอบจริงในเบราว์เซอร์ (รอผู้ใช้ verify)
- `[x]` ✅ **หน้าใหม่: Policy & Board Document Search (Module 1 RAG — ไม่เคยมี UI มาก่อนเลยตั้งแต่เขียน backend เสร็จ, session 3.1)** — ผู้ใช้ส่ง brief (`stitch_brief_rag_search.md`) ไปออกแบบผ่าน Google Stitch (Antigravity) เอง ได้ `search.html` กลับมา (Tailwind CDN + Material Symbols — คนละ tech stack จาก 3 หน้าเดิมที่ใช้ plain CSS แต่แยกไฟล์กันเลยไม่ชนกัน) — **ทำแล้ว (2026-08-04)**: ต่อเข้ากับ `POST /api/rag/query`/`POST /api/rag/query_confidential` จริงผ่าน `app.js`'s `initSearchPage()`/`submitSearchQuery()`/`appendSearchAiBubble()` ตัดส่วนที่ Stitch ใส่มาเกินสโคป (sidebar เดิมมี "Confidential Vault"/"Templates"/"Help Center"/"Logout"/notifications/settings/avatar — ไม่มีหน้า/backend รองรับสักอย่าง เป็น dead link ทั้งหมด) เหลือแค่สิ่งที่ผูกกับฟีเจอร์จริง: role-select (แก้ `initRoleSelect()` ให้รองรับหลาย `.role-select` ในหน้าเดียว sync กันเอง — หน้านี้มี 2 ตัว mobile+desktop), scope selector 2 ชุด sync กัน (pill กลางจอ + sidebar link), "New Search" (reset ในหน่วยความจำ), loading state ที่มี elapsed-time counter (สำคัญเพราะ query ช้าได้ถึง ~30 นาที ดู `backend/rag.py`'s `RAG_WORKER_TIMEOUT_SECONDS`), sources card render จาก response จริง (`{response, sources:[{file_name, content}], tokens}`) — เพิ่ม nav link "Policy Search" ในหัวอีก 3 หน้าเดิมด้วย (เดิมไม่มีทางเข้าหน้านี้จากที่ไหนเลย)
  - **Verify ที่ทำแล้ว**: `node --check app.js` ผ่าน, เช็ค id ที่ JS อ้างอิงครบทุกตัวจริงใน HTML (สคริปต์เทียบ id set), HTML tag balance ผ่าน (เขียน checker เอง — sandbox ไม่มี HTML validator สำเร็จรูป) — **⚠️ ยังไม่เคยเปิดจริงในเบราว์เซอร์เลย** เหมือนงาน frontend อื่นๆของโปรเจกต์นี้ทุกครั้ง ต้องให้ผู้ใช้ทดสอบบนเครื่อง Windows จริง: ถามคำถามจริงทั้ง 2 scope, สลับ role แล้วเช็คว่า sync ระหว่าง mobile/desktop select ถูกไหม, กด New Search แล้ว state เคลียร์จริงไหม, sources card แสดงถูกไหมเมื่อมีเอกสารลับจริงใน confidential index (ตอนนี้ดัชนีลับยังว่างอยู่ — ดู Module 1 รายการด้านบน)
