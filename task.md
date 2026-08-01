# Project Tasks: Company Secretary AI System

> ⚠️ **อัปเดต 2026-08-01 (รอบ 2 — หลังเซสชัน `/grill-me` เรื่องการรวม repo ภายนอก):** พบโปรเจกต์ RAG ที่ทำงานจริงอยู่แล้วที่
> `D:\Review Policy\Local  RAG` (39 unit test + 11 E2E test ผ่านหมด) — เปลี่ยนกลยุทธ์ Module 1 จาก "เขียนใหม่" เป็น
> "reuse ของเดิม" ทั้งหมด พร้อมตัดสินใจสำคัญอีกหลายข้อเรื่องฮาร์ดแวร์/กฎหมาย/สถาปัตยกรรม — ดูรายละเอียดเหตุผลแต่ละ
> ข้อใน `implementation_plan.md` ส่วน "Decisions from /grill-me session (2026-08-01)"

## Module 0: ข้อจำกัดฮาร์ดแวร์ & กฎหมาย (ตัดสินใจแล้ว)

- `[x]` ยืนยันใช้ `typhoon-asr` เป็น ASR หลัก (FastConformer, รันได้ทั้ง CPU/GPU) — **ไม่ใช้ `typhoon2-audio`** (โมเดล 8B parameters ต้องการ VRAM ~16GB+ เกินเครื่องที่มี 4GB ไปมาก) เก็บ `typhoon2-audio` ไว้เป็น**ตัวเลือกสำหรับ production บน cloud GPU ในอนาคตเท่านั้น** ไม่ใช่แผนตอนนี้
- `[x]` ยืนยันความเสี่ยงด้านกฎหมายของ `Diarization_ThaiSpeech_2022` (ไม่มีไฟล์ LICENSE = all rights reserved โดยปริยาย) — ยอมรับความเสี่ยงนี้เพราะใช้ภายในองค์กรเท่านั้น ข้อมูลเป็นความลับ ไม่มีการขาย/แจกจ่ายต่อ **ต้องกลับมาทบทวนใหม่ถ้าจะเปลี่ยนขอบเขตการใช้งาน** (เช่น แจกจ่ายให้บริษัทอื่น)
- `[x]` ยืนยันว่า RAG stack (BGE-M3 + reranker) รันบน **CPU เท่านั้น** เสมอ (ตามที่ Local RAG เดิมออกแบบและพิสูจน์แล้วว่าไม่ต้องการ GPU) — สงวน VRAM 4GB ทั้งหมดไว้ให้ Module 2 (Diarization + ASR) เท่านั้น ห้ามติดตั้ง torch แบบ CUDA ให้ RAG worker โดยเด็ดขาด

## Module 1: Secure Local-RAG (ผู้ช่วยนโยบายบริษัท)

- `[x]` **พบและ reuse โปรเจกต์ที่ทำงานจริงแล้ว**: `D:\Review Policy\Local  RAG` — Streamlit + `rag_worker.py` แยกโปรเซส, LlamaIndex + FAISS + BGE-M3 + BGE-reranker-v2-m3 + Gemini (พร้อม auto-fallback chain), ผ่าน unit test 39 + E2E test 11 บนเครื่องจริงแล้ว
- `[x]` **ตัดสินใจสถาปัตยกรรมสุดท้าย (แก้จาก `/grill-me` รอบ 2, 2026-08-01):** คง RAG worker เป็น**โปรเซสแยกต่อไป** (ตาม HANDOFF.md เดิมเตือนไว้ ไม่เสี่ยง Windows crash) แต่**เขียนชั้น HTTP/routing ใหม่เป็น FastAPI** (แทน `http.server`/`BaseHTTPRequestHandler` เดิมที่เป็นคนละ stack กับ Com Sec) ส่วน RBAC แก้ด้วยการส่ง role/JWT ผ่าน HTTP header ให้ worker เช็คเอง ไม่ต้องรวมโปรเซส
- `[x]` **สร้าง FastAPI worker process ใหม่** (`D:\Com Sec\rag_worker\`, แยกโปรเซสจาก backend หลัก) — เขียนชั้น HTTP ใหม่เป็น FastAPI (`rag_worker/main.py`) แทน `http.server` เดิม ส่วนชั้น logic copy มาจาก Local RAG **ไม่แก้เลยแม้แต่บรรทัดเดียว**: `llm_fallback.py`, `worker_state.py`, `worker_prompts.py`, `worker_parsing.py`, `worker_retrieval.py`, `worker_handlers.py` — เพิ่ม `worker_config.py` เวอร์ชันปรับ path ให้ชี้ไปที่ `storage/`/`models/`/corpus ของ Local RAG โดยตรง (ไม่ copy) ⚠️ **เขียนโค้ดเสร็จแล้ว verify แค่ `py_compile`/`pyflakes` ใน sandbox (ไม่มี torch/faiss/BGE-M3 ให้รันจริง) — ยังไม่เคยรันจริงบนเครื่อง Windows เลยสักครั้ง** ต้องรัน `pip install -r rag_worker/requirements.txt` แล้ว `python -m uvicorn main:app --port 8766` บนเครื่องจริงก่อนเชื่อถือว่าใช้งานได้ (ดู handoff.md ข้อ 4 สำหรับคำสั่งเต็ม)
- `[x]` **`backend/rag.py` เป็น HTTP client เรียกไปหา RAG worker process ใหม่แล้ว** (เดิมเป็น stub คืนค่า hardcoded string) ใช้ `httpx` ยิงไป `http://127.0.0.1:8766` ส่ง `user_id`/`role` ต่อจาก `auth.py` — จับ `ConnectError`/`TimeoutException`/503/403 แปลงเป็น `RAGWorkerError` ให้ `main.py` คืน HTTP 503 ที่มีความหมายแทน error ดิบ ⚠️ **ยังไม่เคยทดสอบยิงจริงระหว่าง 2 โปรเซส** (ต้องมี worker รันอยู่ก่อน)
- `[x]` **เปลี่ยน session model แล้ว**: worker ใหม่ใช้ `user_id` (จาก JWT/mock token ผ่าน `X-User-Id` header + body) เป็น session key ตรงๆ แทน browser-tab session_id ของ Local RAG เดิม — ครอบคลุมทั้ง general query (`worker_state.sessions`) และ confidential query (`confidential_rag.confidential_sessions`, SessionStore แยกต่างหาก)
- `[x]` **เช็ค corpus หาชื่อบริษัทเก่าตกค้างแล้ว (2026-08-01)** — grep `"ทเวนตี้ โฟร์ คอน แอนด์ ซัพพลาย"` ทั้ง corpus พบ **65 ไฟล์** ยังมีชื่อเก่าอยู่ (Policies 28/49, Procedures 11/11, Manuals 7/11, Forms 19/142) และคำว่า `"24CS"` (รหัสบริษัทเก่า) ปรากฏใน **166 ไฟล์** — ⚠️ **นี่คือรายงานผลการค้นหาเท่านั้น ยังไม่ได้แก้ไขเนื้อหาเอกสารใดๆ** การแก้ไขเนื้อหานโยบาย/กฎหมายเป็นการตัดสินใจของเจ้าของนโยบาย ไม่ใช่สิ่งที่ AI ควรแก้เองโดยพลการ — ต้องตัดสินใจร่วมกับผู้ใช้ก่อนว่าจะ (ก) ปล่อยไว้ตามเดิม (Local RAG's Prefill provenance rule ก็ยึดหลักโชว์วันที่เอกสารให้มนุษย์ตัดสินความ staleness เองอยู่แล้ว) หรือ (ข) ไล่แก้ทีละไฟล์
- `[x]` **Streamlit app เดิม (Local RAG) ไม่ retire — เป็นคนละวัตถุประสงค์กับ Com Sec (ชี้แจงจาก `/grill-me` รอบ 3)**: Local RAG ใช้สำหรับสอบถามนโยบายเชิงลึก (deep policy research) ส่วน Module 1 ของ Com Sec เป็นแค่ RAG Q&A แบบเร็วที่ฝังอยู่ใน workflow เลขาบริษัท (เตรียมประชุม/อนุมัติ) — ทั้งสองระบบอยู่คู่กันถาวร คนละกลุ่มผู้ใช้/คนละ use case **แต่ต้องชี้ไปที่ FAISS index/`storage/` โฟลเดอร์เดียวกัน** (ไม่ copy corpus แยก) ป้องกันไม่ให้ข้อมูลสองระบบ drift กัน
- `[ ]` **ติดตั้ง dependencies และรัน backend+worker ให้ขึ้นจริงอย่างน้อย 1 ครั้งบนเครื่อง Windows จริง** — sandbox agent ทำเองไม่ได้ (ไม่มี torch/faiss/BGE-M3/venv จริง) คำสั่งที่ต้องรัน:
  1. `cd "D:\Com Sec\rag_worker" && pip install -r requirements.txt && copy .env.example .env` (ใส่ `GOOGLE_API_KEY` จริง) แล้ว `python -m uvicorn main:app --host 127.0.0.1 --port 8766`
  2. `cd "D:\Com Sec\backend" && pip install -r requirements.txt` แล้ว `python main.py` (คนละ terminal จาก worker)
  3. ทดสอบ: `curl -X POST http://127.0.0.1:8000/api/rag/query?query=... -H "Authorization: Bearer mock_admin_token"`
- `[ ]` เชื่อมต่อ Authentication (Azure AD) จริง — ปัจจุบัน `auth.py` เป็น mock token string ล้วนๆ ไม่มีการ decode JWT/เรียก Azure AD จริง (ยังไม่แตะรอบนี้ — ต้องมี Azure AD tenant ID/client ID จากผู้ใช้ก่อน)
- `[x]` **เพิ่มระบบแยกสิทธิ์เอกสารลับแล้ว (สถาปัตยกรรม)** — ตัดสินใจ**แยกดัชนี**แทนแท็ก metadata ในดัชนีเดียวกับ Local RAG (ดู `rag_worker/confidential_rag.py` docstring สำหรับเหตุผล: Local RAG ไม่มี RBAC เลย ถ้าใส่ BOD minutes ลงดัชนีร่วมจะเสี่ยงข้อมูลลับหลุดไปโผล่ในผลค้นหาของ Local RAG) `rag_worker/main.py`'s `/query_confidential` เช็ค role เทียบ `CONFIDENTIAL_ALLOWED_ROLES` ก่อนเข้าดัชนีลับเสมอ ⚠️ **ยังไม่เคย end-to-end test เพราะยังไม่มีเอกสารลับจริงในระบบเลย** (Module 3 สร้าง minutes / Module 5 approve+archive ยังไม่ถูกสร้าง — ดัชนีลับจะว่างจนกว่าจะมีเอกสารจริงแล้วรัน `build_confidential_index.py`)
- `[x]` **`/api/rag/query` (ทั่วไป) และ `/api/rag/query_confidential` (จำกัดเฉพาะ Com_Sec_Maker/Checker/Board_Member/Global_Admin) ต่อกับ role จริงแล้ว** — `backend/main.py` ส่ง `user["role"]`/`user["user_id"]` จาก `require_role()`/`verify_azure_ad_token()` ต่อไปให้ worker ⚠️ role/user ที่ใช้ตอนนี้ยังมาจาก **mock auth** (ดูรายการด้านบน — Azure AD จริงยังไม่เชื่อม)
- `[x]` ~~โคลนและประยุกต์ใช้ `book-to-skill`~~ — **ตัดออกจากแผนแล้ว และลบโฟลเดอร์ทิ้งแล้ว (`/scrutinize` cleanup 2026-08-01)** ซ้ำซ้อนกับเครื่องมือที่ Local RAG มีอยู่แล้ว (`extract_forms.py`/`convert_forms_to_txt.py`/`dump_raw_forms.py` + Gemini แกะทุกตัวอักษร) ซึ่งรักษาความสมบูรณ์ของเนื้อหา 100% ส่วน `book-to-skill` เป็นเครื่องมือ**กลั่น/สรุป**เนื้อหา (ลด token 24-51 เท่า) ไม่เหมาะกับเอกสารนโยบาย/กฎหมายที่ต้องอ้างอิงคำต่อคำ

## Module 2: Audio Processing & Transcription

- `[ ]` **รองรับไฟล์เสียง/วิดีโอต้นทาง 3 แหล่ง แบบ manual upload เหมือนกันหมด (ตัดสินใจจาก `/grill-me` รอบ 3)**: Google Meet, MS Teams, เครื่องบันทึกเสียง/มือถือ (ออฟไลน์) — ไม่ทำ auto-fetch ผ่าน Google Drive/Graph API ใน MVP, ใช้ `ffmpeg` รองรับทุกฟอร์แมตที่รู้จัก (mp4/wav/mp3/m4a/mov ฯลฯ) ไม่จำกัดชนิดไฟล์ล่วงหน้า
- `[ ]` **สร้าง "การประชุม" (Meeting) เป็น entity แยกต่างหาก ก่อนอัปโหลดไฟล์เสียง (ตัดสินใจจาก `/grill-me` รอบ 3)** — ฟอร์มกรอกล่วงหน้า: วันที่ประชุม, เลขที่การประชุม (ตรงกับชื่อไฟล์ template เช่น "15/2569"), รายชื่อผู้เข้าร่วม+ตำแหน่ง, วาระการประชุม — อัปโหลดไฟล์เสียงทีหลังโดยผูกเข้ากับ meeting ที่สร้างไว้แล้ว
- `[ ]` สร้างฟังก์ชันรับไฟล์เสียง/วิดีโออัปโหลดผ่าน FastAPI (Async Background Task, **ประมวลผลทีละไฟล์ queue เดียว ไม่ขนาน** ตามการตัดสินใจเรื่อง VRAM ด้านล่าง)
- `[x]` โคลนโปรเจกต์ `meetily`, `typhoon-asr`, `typhoon2-audio`, `Diarization_ThaiSpeech_2022` (ยืนยันแล้วว่าโคลนจริง มีไฟล์ครบ)
- `[ ]` ติดตั้งและปรับใช้ `ffmpeg` สำหรับสกัดเสียงเป็น 16kHz Mono WAV
- `[ ]` **เพิ่ม GPU Lock ตัวเดียวทั้งระบบ**: Diarization และ Typhoon ASR ต้องแย่ง lock เดียวกันก่อนขึ้น GPU — โหลดโมเดล → รัน → `torch.cuda.empty_cache()` ปล่อย VRAM คืน → ค่อยโหลดโมเดลถัดไป ห้ามมี 2 โมเดลอยู่บน VRAM พร้อมกันเด็ดขาด (ยอมแลกเวลาโหลดซ้ำ 10-30s/โมเดล เพื่อความปลอดภัยของ VRAM 4GB)
- `[ ]` CPU fallback: ถ้า VRAM ไม่พอ (`torch.cuda.OutOfMemoryError`) ให้ตกไปใช้ `--device cpu` อัตโนมัติ (ทั้ง `typhoon-asr` และ `pyannote.audio` รองรับอยู่แล้ว) — เป็นตัวเลือกสุดท้ายเสมอตามที่ตัดสินใจไว้
- `[ ]` **รัน Diarization บนไฟล์เต็มความยาวก่อน (ไม่ตัดชิ้น) แล้วตัดเฉพาะ ASR เป็นชิ้นละ 1 ชม. (ตัดสินใจจาก `/grill-me` รอบ 3)** — ป้องกันปัญหา Speaker ID ไม่ตรงกันข้ามชิ้น (diarization model ตั้ง label ใหม่อิสระต่อกันถ้าประมวลผลแยกชิ้น) ทำให้ speaker mapping ที่ Maker ทำไว้ใช้ได้ตลอดทั้งการประชุม ไม่ต้องจับคู่ใหม่ทุกชั่วโมง
- `[ ]` รวมระบบ Typhoon ASR + Diarization_ThaiSpeech_2022 **พร้อมเก็บ timestamp เริ่ม/จบของแต่ละท่อนพูดไว้ด้วย** (ไม่ใช่แค่ข้อความ) — จำเป็นสำหรับฟีเจอร์ transcript-sync player ใน Module 6
- `[ ]` เก็บไฟล์เสียง/วิดีโอต้นฉบับไว้ให้ FastAPI serve กลับมาเล่นย้อนหลังได้ (requirement ใหม่จากฟีเจอร์ transcript-sync)
- `[ ]` ⚠️ **นโยบายเก็บรักษาไฟล์เสียง/วิดีโอต้นฉบับ (ยังไม่ตัดสินใจ, พบจาก `/scrutinize`)**: ต้องกำหนด retention period (เช่น ลบอัตโนมัติ N วันหลัง Approve), encryption at rest, และสิทธิ์เข้าถึงระดับไฟล์ (ไม่ใช่แค่ metadata) ก่อนเริ่มเก็บไฟล์จริง — องค์กรมี HR_PDPA_Policy/Data_Breach_Policy ใช้บังคับจริงอยู่แล้ว การเก็บเสียงประชุมบอร์ดโดยไม่มีนโยบายชัดเจนเสี่ยงขัด policy ตัวเอง
- `[ ]` ⚠️ **verify VRAM จริงของ `typhoon-asr`** — ที่ผ่านมาเช็คแค่ `typhoon2-audio` (8B, ~16GB, ตัดออกแล้ว) ส่วน `typhoon-asr` มีแค่คำว่า "Hardware Flexible" ยังไม่มีตัวเลขจริงยืนยันว่าพอกับ VRAM 4GB จริง ต้องรันวัดจริงก่อนพึ่งพา
- `[ ]` ออกแบบ UX คิวสำหรับ user ที่อัปโหลดพร้อมกัน (queue เดียว ประมวลผลทีละไฟล์ — ต้องมีหน้าจอแจ้งสถานะ/แจ้งเตือนเมื่อเสร็จใน Module 6)
- `[ ]` **หน้าจอ Speaker Mapping (บังคับ, ตัดสินใจจาก `/grill-me` รอบ 3)** — หลัง Diarization เสร็จ ต้องจับคู่ `Speaker_00/01/02...` กับชื่อจริงจาก attendee list ที่กรอกไว้ตอนสร้าง meeting ก่อนกด "สรุปเป็น Minutes" ได้ (Module 3 บล็อกถ้ายังจับคู่ไม่ครบ) — มีปุ่มเล่นตัวอย่างเสียงสั้นๆ ต่อ speaker ช่วยจำเสียง
- `[ ]` **หน้าจอแก้ไข Transcript (ไม่บังคับ)** — ใช้ UI เดียวกับ transcript-sync player ให้ Com_Sec_Maker แก้คำถอดเสียงผิดได้ก่อนส่งเข้า Module 3 แต่ข้ามได้ถ้าเชื่อว่าถูกต้องแล้ว
- `[x]` บันทึกความเสี่ยงกฎหมายเรื่อง license ของ `Diarization_ThaiSpeech_2022` ไว้แล้ว (ดู Module 0)
- `[ ]` `typhoon2-audio`: ไม่ integrate ตอนนี้ เก็บไว้เป็นเอกสารอ้างอิงสำหรับตัวเลือก production บน cloud GPU เท่านั้น

## Module 3: Meeting Minutes Generation

- `[ ]` ใช้ Gemini ผ่าน `google-genai` SDK เดียวกับ Local RAG (ไม่ใช่ Claude) — reuse `llm_fallback.py`'s `run_with_fallback()` (retry+backoff+auto-fallback ที่ผ่าน test มาแล้ว) แทนการเขียน retry logic ใหม่
- `[ ]` ใช้ **native structured output ของ Gemini** (`response_schema` + `response_mime_type="application/json"`) แทนการเพิ่ม library `Instructor` ตามแผนเดิม — ลด dependency ที่ไม่จำเป็น
- `[ ]` ออกแบบ Pydantic schema สำหรับ Minutes of Meeting (ต้องคุยร่วมกับ Module 4 เรื่อง mapping ไปยัง Word template)
- `[ ]` เขียน prompt ใหม่: transcript (พร้อม speaker+timestamp) → JSON โครงสร้าง
- `[ ]` **ใช้ Gemini API แบบเปิด billing (paid tier) ตั้งแต่ทดสอบด้วยเนื้อหาจริงครั้งแรก** ไม่รอถึง production — เพราะเนื้อหาประชุมบอร์ดเป็นความลับสูง และ paid tier ยืนยันแล้วว่าไม่นำ prompt/response ไปเทรนโมเดล (Google Cloud DPA) ต่างจาก free tier ที่มนุษย์อาจ review ได้ (ทดสอบด้วยข้อมูลสมมติบน free tier ได้ปกติ)

## Module 4 & 5: Word Template Mapping & Secure Delivery

- `[ ]` วิเคราะห์ไฟล์เทมเพลต `260628 Draft_EMPIRE - BOD Minutes 15-2569 v.5.docx`
- `[ ]` เขียนสคริปต์ `python-docx` แมปตัวแปร JSON ลงเอกสาร
- `[ ]` เขียนระบบจัดการ Approval Flow (Maker/Checker) — **มีสถานะ "ตีกลับแก้ไข" อย่างเป็นทางการ (ตัดสินใจจาก `/grill-me` รอบ 3)**: อย่างน้อย 4 สถานะ `Draft` → `Pending_Review` → `Needs_Revision` (Checker reject พร้อมคอมเมนต์เหตุผล, กลับไปให้ Maker แก้) หรือ `Approved` → ส่งต่อ Board_Member — เก็บ audit trail ครบทุกรอบตีกลับเพื่อ compliance
- `[ ]` สร้างฟังก์ชันดึงรายชื่ออีเมลจากระบบ แล้วส่ง Automated Secure Email (Magic Link) ถึง Board_Member หลัง Approve — **ต้องกำหนด token expiration + single-use ตั้งแต่ตอนออกแบบ** (พบจาก `/scrutinize` ว่ายังไม่ระบุ)
- `[ ]` **ระบบ Archive ไฟล์แบบเลือกปลายทางได้ (พบจาก `/grill-me` รอบ 2)** — ตั้งค่าระดับระบบ (config path, ไม่ใช่ folder-picker ต่อครั้ง) แยก **2 ปลายทางตามประเภทไฟล์**:
  1. `documents_destination` — รายงานการประชุมฉบับสมบูรณ์ (.docx/PDF) copy ไป mapped drive/UNC path ที่แชร์กับผู้บริหาร (Board_Member) หลัง Approve
  2. `recordings_destination` — ไฟล์เสียง/วิดีโอต้นฉบับ + ข้อมูล transcript-sync แยกคนละที่เก็บ **เข้าถึงได้เฉพาะทีม Com Sec เท่านั้น** (Com_Sec_Maker/Checker/Global_Admin) ตามนโยบายชั้นความลับข้อมูล — **Board_Member ไม่มีสิทธิ์เข้าถึงจุดนี้**
  - Implementation: `shutil.copy`/`shutil.copytree` ไป UNC path ตรงๆ (ไม่ต้องพึ่ง SharePoint Graph API ก็ได้ ปรับปลายทางได้ผ่าน config ภายหลัง) — ไม่มี version history อัตโนมัติแบบ SharePoint ต้อง log การ approve/copy เองใน DB
- `[ ]` **ปรับ RBAC ของฟีเจอร์ transcript-sync player**: จำกัดเฉพาะ Com_Sec_Maker/Checker/Global_Admin เท่านั้น (แคบกว่า `/api/rag/query_confidential` เดิมที่รวม Board_Member ด้วย) — เพราะไฟล์เสียงดิบเป็นคนละชั้นความลับกับรายงานฉบับสมบูรณ์ที่ส่งให้บอร์ด

## Module 6: Front-End UI Integration (Stitch MCP + CI)

- `[ ]` อ่านไฟล์ `EMPIRE CI(1).png` เพื่อสร้าง Design System (รหัสสี, ฟอนต์)
- `[ ]` ใช้ Stitch MCP Generate หน้า UI แดชบอร์ดตาม CI ของบริษัท
- `[ ]` นำ UI มาเชื่อมกับ FastAPI (CORS, API Routes)
- `[ ]` **ฟีเจอร์ใหม่: Synced Audio/Video Player + Transcript Panel** (แบบดูวิดีโออบรมออนไลน์ที่มี script ด้านขวา) — อ้างอิงแพทเทิร์นจาก `meetily/frontend` (`AudioPlayer.tsx`/`useAudioPlayer.ts`/`TranscriptView.tsx`) แต่เขียนใหม่ด้วย HTML5 `<audio>`/`<video>` + `ontimeupdate` แทน Tauri-specific `invoke('read_audio_file')` ที่เอามาใช้ในเว็บตรงๆ ไม่ได้ ต้องอาศัย timestamp per-segment จาก Module 2
