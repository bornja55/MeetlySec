# Company Secretary AI System (Comprehensive MVP - Final)

เป้าหมายคือการสร้างระบบผู้ช่วยอัตโนมัติสำหรับเลขาบริษัท (Company Secretary) แบบครบวงจร ครอบคลุมการถอดเสียง บันทึกการประชุม (Minutes of Meeting) ค้นหากฎระเบียบ (RAG) พร้อมระบบรักษาความปลอดภัยระดับ Enterprise โปรเจกต์ทั้งหมดจะถูกเก็บไว้ที่ `D:\Com Sec`

## User Review Required

> [!IMPORTANT]
> นี่คือแผนการพัฒนาฉบับไฟนอลที่อุดช่องโหว่ทั้งหมดจากการทำ /scrutinize เรียบร้อยแล้ว หากคุณพร้อมให้ผมเริ่มลงมือเขียนโค้ด กด **"Proceed"** หรือพิมพ์บอกผมได้เลยครับ ผมจะสร้างไฟล์ Task List และเริ่มลงมือเขียน **Module 1** ให้คุณทันที!

---

## 🏗️ โครงสร้างสถาปัตยกรรมภาพรวม (Architecture)
- **Directory หลัก:** `D:\Com Sec`
- **Front-end:** สร้างด้วย **MCP Google Stitch** (React/Next.js) 
- **Back-end:** Python FastAPI
- **Hardware Constraint:** ทำงานบน GPU 2 ใบ (4GB + 6GB)

---

## 🔍 Decisions from `/grill-me` session (2026-08-01)

ระหว่างเซสชัน `/grill-me` เรื่อง "repo ภายนอกที่โคลนมาจะรวมกับระบบได้จริงไหม" พบข้อเท็จจริงสำคัญและตัดสินใจหลายข้อที่เปลี่ยนแผนเดิม สรุปไว้ที่นี่ (รายละเอียดเหตุผลแต่ละข้ออยู่ใน `task.md` ส่วน Module ที่เกี่ยวข้อง):

1. **พบโปรเจกต์ RAG ที่ทำงานจริงแล้วที่ `D:\Review Policy\Local  RAG`** (Streamlit + `rag_worker.py` แยกโปรเซส, LlamaIndex+FAISS+BGE-M3+BGE-reranker-v2-m3+Gemini fallback chain, ผ่าน unit test 39 + E2E test 11 บนเครื่องจริง) — Module 1 เปลี่ยนจาก "เขียนใหม่ทั้งหมด" เป็น **reuse logic module จาก `rag_worker.py`** แล้วเขียนชั้น HTTP ใหม่เป็น FastAPI worker แยกโปรเซส — **Local RAG (Streamlit) เป็นคนละผลิตภัณฑ์ ไม่ retire**: ใช้สอบถามนโยบายเชิงลึก (deep research) ต่างจาก Module 1 ของ Com Sec ที่เป็น RAG Q&A เร็วๆ ฝังใน workflow เลขาบริษัท — ทั้งสองอยู่คู่กันถาวร แต่ต้องชี้ไปที่ FAISS index/`storage/` เดียวกันเพื่อไม่ให้ corpus drift
2. ~~สถาปัตยกรรม Module 1 = FastAPI เดียว (monolith)~~ **แก้ไขสุดท้าย (`/grill-me` รอบ 2, 2026-08-01):** `HANDOFF.md` ของ Local RAG ระบุชัดว่า two-process split มีไว้แก้ Windows WINHTTP.dll crash จาก native-library conflict โดยเฉพาะ ("never recombine into one process") — **คง RAG worker เป็นโปรเซสแยกต่อไป ไม่รวมเข้า FastAPI หลัก** แต่เขียนชั้น HTTP/routing ใหม่เป็น **FastAPI** (แทน `http.server`/`BaseHTTPRequestHandler` เดิมที่เป็นคนละ stack) — ส่วนชั้น logic ภายใน (`llm_fallback.py`, `worker_retrieval.py`, `worker_parsing.py`, `worker_prompts.py`, `worker_config.py`) ไม่มี dependency กับ `http.server`/Streamlit เลย นำมา reuse ได้ตรงๆ ไม่ต้องเขียนใหม่ (ของเดิมผ่านการแก้บั๊ก timeout/fallback-chain/sleep-monkeypatch มาแล้วหลายรอบ) RBAC แก้ด้วยการส่ง role/JWT ผ่าน HTTP header ให้ worker เช็คเอง
3. **`typhoon-asr` เป็น ASR หลัก ไม่ใช่ `typhoon2-audio`** — `typhoon2-audio` คือโมเดล 8B parameters ต้องการ VRAM ~16GB+ (fp16) เกินเครื่องที่มี 4GB ไปมาก เก็บไว้เป็นตัวเลือก production บน cloud GPU ในอนาคตเท่านั้น
4. **`Diarization_ThaiSpeech_2022` ไม่มีไฟล์ LICENSE** (all rights reserved โดยปริยาย) — ยอมรับความเสี่ยงนี้เพราะใช้ภายในองค์กรเท่านั้น ข้อมูลลับ ไม่ redistribute ต้องทบทวนใหม่ถ้าเปลี่ยนขอบเขต
5. **RAG stack (BGE-M3+reranker) รัน CPU-only เสมอ** สงวน VRAM 4GB ทั้งหมดให้ Module 2 — ภายใน Module 2 ใช้ **GPU Lock ตัวเดียว** ให้ Diarization/ASR สลับกันขึ้น VRAM ทีละตัว (โหลด→รัน→`torch.cuda.empty_cache()`→โหลดตัวถัดไป) ไม่มีทางขึ้นพร้อมกัน ยอมแลกเวลาโหลดซ้ำเพื่อความปลอดภัยของ VRAM, CPU fallback เป็นตัวเลือกสุดท้ายเสมอ
6. **ตัด `book-to-skill` ออกจากแผน Module 1** — ซ้ำซ้อนกับเครื่องมือแปลงเอกสารที่ Local RAG มีอยู่แล้ว (`extract_forms.py`/`convert_forms_to_txt.py` + Gemini แกะทุกตัวอักษร รักษาความสมบูรณ์ 100%) ส่วน `book-to-skill` เป็นเครื่องมือกลั่น/สรุปเนื้อหา (ลด token 24-51 เท่า) ไม่เหมาะกับเอกสารที่ต้องอ้างอิงคำต่อคำ
7. **Module 3 ใช้ Gemini (ไม่ใช่ Claude) ผ่าน `google-genai`** เดียวกับ Local RAG, reuse `llm_fallback.py`'s `run_with_fallback()`, ใช้ **native structured output ของ Gemini** (`response_schema`) แทน library `Instructor`, และ**ใช้ Gemini API แบบเปิด billing (paid tier) ตั้งแต่ทดสอบด้วยเนื้อหาจริงครั้งแรก** ไม่รอถึง production เพราะเนื้อหาประชุมบอร์ดเป็นความลับสูง (paid tier ไม่นำ prompt/response ไปเทรนโมเดล ตาม Google Cloud DPA)
8. **`meetily` ใช้เป็นแค่ architecture/UX reference** (เป็น Tauri desktop app, Rust+Next.js — ไม่สามารถเอาโค้ดมาใช้ตรงๆ ในเว็บแอปได้) — ฟีเจอร์ที่จะหยิบมาปรับใช้: **Synced Audio/Video Player + Transcript Panel** (`AudioPlayer.tsx`/`useAudioPlayer.ts`/`TranscriptView.tsx`) เขียนใหม่ด้วย HTML5 `<audio>`/`<video>`+`ontimeupdate` แทน Tauri-specific `invoke()` — เพิ่ม requirement ใหม่ให้ Module 2 ต้องเก็บ timestamp ต่อท่อนพูด และเก็บไฟล์เสียง/วิดีโอต้นฉบับไว้ serve กลับมาเล่นได้

---

## 📋 แผนการพัฒนาทีละโมดูล (Phased Implementation)

### 🟢 Module 1: Secure Local-RAG (ผู้ช่วยนโยบายบริษัท)
- **Security Update:** เชื่อมต่อระบบ Authentication ระดับ **Global Admin (Azure AD / Google Workspace)** ควบคุมสิทธิ์การเข้าถึงข้อมูลตาม Role แบบ 100% Enterprise Security
- **การทำงาน:** Port logic จริงจาก `D:\Review Policy\Local  RAG\rag_worker.py` (FAISS+BGE-M3+BGE-reranker-v2-m3+Gemini fallback) เข้า FastAPI ของ Com Sec เป็น monolith เดียว — เพิ่มระบบแยกสิทธิ์เอกสารลับ (metadata ระดับความลับ + filter ตาม role จริง) ที่ของเดิมไม่มี

### 🟢 Module 2: Audio Processing & Transcription (Thai Optimized + Diarization)
- **หน้าที่:** จัดการไฟล์เสียง/วิดีโอจากห้องประชุม ถอดเสียงสนทนาภาษาไทย และแยกแยะผู้พูด
- **Hardware constraint (VRAM 4GB):** ประมวลผลทีละไฟล์ (queue เดียว ไม่ขนาน) ใช้ **GPU Lock ตัวเดียวทั้งระบบ** ให้ Diarization กับ ASR สลับกันขึ้น VRAM ทีละตัว (โหลด→รัน→ปล่อย VRAM คืน→โหลดตัวถัดไป) ไม่มีทาง 2 โมเดลขึ้นพร้อมกัน ยอมแลกเวลาโหลดซ้ำ (10-30s/โมเดล) เพื่อความปลอดภัยของ VRAM — CPU fallback (`--device cpu`) เป็นตัวเลือกสุดท้ายเสมอถ้า VRAM ไม่พอ
- **การทำงาน:** 
  1. ใช้ `ffmpeg` สกัดไฟล์เสียง (รองรับไฟล์ขนาดใหญ่ผ่าน **Async Background Task** เพื่อป้องกันเว็บ Timeout)
  2. ใช้โมเดล **`Diarization_ThaiSpeech_2022`** ในการสแกนไฟล์เสียงเพื่อจับเวลาว่า "ใครพูดช่วงไหน" (Speaker Diarization) — **หมายเหตุ:** repo นี้ไม่มีไฟล์ LICENSE (all rights reserved โดยปริยาย) ยอมรับความเสี่ยงนี้เพราะใช้ภายในองค์กรเท่านั้น ข้อมูลลับ ไม่ redistribute
  3. รัน **Typhoon ASR (SCB 10X)** แบบ Local เพื่อแปลงเสียงเป็นข้อความที่ตัดคำถูกต้อง — **ใช้ `typhoon-asr` เป็นตัวหลัก ไม่ใช้ `Typhoon2-Audio`** (โมเดล 8B parameters ต้องการ VRAM ~16GB+ เกินเครื่องนี้ไปมาก) เก็บ Typhoon2-Audio ไว้เป็นตัวเลือก production บน cloud GPU ในอนาคตเท่านั้น
  4. นำผลลัพธ์จากข้อ 2 และ 3 มารวมกัน เพื่อให้ได้ Transcript ในรูปแบบ `[Speaker A]: สวัสดีครับ...` **พร้อมเก็บ timestamp เริ่ม/จบของแต่ละท่อนพูดไว้ด้วย** (จำเป็นสำหรับฟีเจอร์ transcript-sync player ใน Module 6) ที่พร้อมที่สุดสำหรับ AI
  5. เก็บไฟล์เสียง/วิดีโอต้นฉบับไว้ให้ FastAPI serve กลับมาเล่นย้อนหลังได้ (ใช้กับฟีเจอร์ transcript-sync player)

### 🟢 Module 3: Meeting Minutes Generation (Strict JSON)
- **หน้าที่:** สรุปเนื้อหาการประชุมลงตัวแปร
- **Model:** ใช้ **Gemini ผ่าน `google-genai` SDK** เดียวกับ Local RAG (ไม่ใช่ Claude/Instructor) — reuse `llm_fallback.py`'s `run_with_fallback()` (retry+backoff+auto-fallback ที่ผ่าน unit test 39 เทสมาแล้ว) แทนการเขียน retry logic ใหม่
- **การทำงาน:** ใช้ **Native Structured Outputs ของ Gemini เอง** (`response_schema` + `response_mime_type="application/json"`) บังคับให้ LLM คืนค่าโครงสร้างข้อมูลเป็น JSON เท่านั้น — เลือกใช้ feature ในตัวของ Google แทนการเพิ่ม library `Instructor` เพื่อลด dependency ที่ไม่จำเป็น (Instructor เน้นรองรับ OpenAI-style function calling เป็นหลัก ส่วนรองรับ Gemini ยังไม่ mature เท่า native feature)
- **นโยบายข้อมูล (Data Privacy):** เนื้อหาประชุมบอร์ด (BOD Minutes) เป็นความลับระดับสูง — **ใช้ Gemini API แบบเปิด billing (paid tier) ตั้งแต่ทดสอบด้วยเนื้อหาจริงครั้งแรก ไม่รอถึง production** (ทดสอบด้วยข้อมูลสมมติบน free tier ได้ปกติ) เพราะ paid tier ยืนยันแล้วว่าไม่นำ prompt/response ไปเทรนโมเดลหรือปรับปรุงผลิตภัณฑ์ ประมวลผลภายใต้ Google Cloud Data Processing Addendum (DPA) — ต่างจาก free tier ที่มนุษย์อาจ review เนื้อหาได้ ไม่ต้องรอ migrate ไป Enterprise API Token (Azure OpenAI/Vertex AI) เพื่อเรื่องนี้โดยเฉพาะ เพราะ paid tier ธรรมดาก็ได้มาตรฐานเดียวกันแล้ว

### 🟢 Module 4: Word Template Mapping
- **หน้าที่:** นำ JSON มาหยอดลง Template
- **การทำงาน:** 
  1. ใช้ Template `260628 Draft_EMPIRE - BOD Minutes 15-2569 v.5.docx` (หรือผูกกับ Google Docs API) แมปตัวแปรจาก JSON ลงช่องว่างต่างๆ โดยตรง

### 🟢 Module 5: Finalization & Secure Delivery (Maker-Checker Workflow)
- **หน้าที่:** ปิดจบกระบวนการทำงานและส่งเอกสารให้บอร์ดบริหาร
- **RBAC (Role-Based Access Control):** กำหนด Role ชัดเจนเพื่อความปลอดภัย
  1. `Com_Sec_Maker`: ผู้ทำหน้าที่อัปโหลดไฟล์เสียง สร้างดราฟต์ด้วย AI และตรวจสอบความเรียบร้อยเบื้องต้น
  2. `Com_Sec_Checker`: หัวหน้าเลขาบริษัท ผู้มีสิทธิ์กดปุ่ม **"Approve"** เอกสารขั้นสุดท้าย
  3. `Board_Member`: ผู้มีสิทธิ์เปิดอ่านเอกสารและเซ็นอนุมัติ
- **กระบวนการ:** เมื่อ `Com_Sec_Checker` กด Approve ระบบจะแปลงไฟล์เป็น PDF (Password-Protected) และส่ง **Automated Secure Email (ผ่าน Microsoft Graph API/SMTP)** แนบ Magic Link ไปยัง `Board_Member` เพื่อรอการ E-Signature ทันที
- **Archive ปลายทางที่เลือกได้ (ตัดสินใจจาก `/grill-me` รอบ 2, 2026-08-01):** ตั้งค่าระดับระบบ แยก 2 ปลายทางตามประเภทไฟล์ — (1) `documents_destination`: รายงานประชุมฉบับสมบูรณ์ copy ไป mapped drive/UNC path ที่แชร์กับผู้บริหาร หลัง Approve (2) `recordings_destination`: ไฟล์เสียง/วิดีโอต้นฉบับ+transcript-sync data แยกที่เก็บต่างหาก **เข้าถึงเฉพาะทีม Com Sec เท่านั้น ไม่รวม Board_Member** ตามนโยบายชั้นความลับ — ไม่ hardcode SharePoint Graph API เพื่อให้ปรับปลายทางได้ในอนาคต

### 🟢 Module 6: Front-End UI Integration (Stitch MCP + EMPIRE CI)
- **หน้าที่:** สร้าง UI ที่มีอัตลักษณ์ขององค์กร (EMPIRE) แบบ 100%
- **การทำงาน:** 
  1. วิเคราะห์และสกัดข้อมูลจากภาพ `EMPIRE CI(1).png` (เช่น รหัสสี HEX, ฟอนต์)
  2. ป้อนข้อมูลเป็น Design System ลงในคำสั่ง `create_design_system` ของ **Stitch MCP**
  3. สั่ง Generate หน้าเว็บทั้งหมด โดย Stitch จะบังคับใช้ Brand CI ของ EMPIRE ทุกหน้าโดยอัตโนมัติ
- **ฟีเจอร์ใหม่ — Synced Audio/Video Player + Transcript Panel:** แบบดูวิดีโออบรมออนไลน์ที่มี script อยู่ด้านขวามือ เล่นเสียง/วิดีโอแล้วไฮไลต์/เลื่อนไปยังบรรทัด transcript ที่ตรงกับเวลาปัจจุบันอัตโนมัติ (คลิก transcript แล้วกระโดดเสียงไปจุดนั้นได้ด้วย) — อ้างอิงแพทเทิร์นจาก `meetily/frontend` (`AudioPlayer.tsx`/`useAudioPlayer.ts`/`TranscriptView.tsx`) แต่เขียนใหม่ด้วย HTML5 `<audio>`/`<video>` + `ontimeupdate` แทน Tauri-specific `invoke('read_audio_file')` ที่ใช้ในเว็บไม่ได้ ต้องพึ่ง timestamp ต่อท่อนพูดจาก Module 2
