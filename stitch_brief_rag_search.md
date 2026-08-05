# Stitch Design Brief — หน้า "ค้นหานโยบาย/เอกสารประชุมย้อนหลัง" (Policy & Board Document Search)

> วิธีใช้: copy เนื้อหาทั้งหมดด้านล่างนี้ (ตั้งแต่ "## Prompt สำหรับวาง Stitch" ลงไป) ไปวางเป็น prompt
> ใน Google Stitch (ผ่าน Antigravity) ได้เลย — เขียนไว้ให้ครบทุกอย่างที่ Stitch ต้องรู้ในก้อนเดียว
> ไม่ต้องแก้อะไรเพิ่ม เสร็จแล้วส่งผลลัพธ์ (HTML/CSS หรือภาพ mockup) กลับมา ผมจะต่อเข้ากับ backend จริง
> ให้เหมือนที่ทำกับ 3 หน้าเดิม (Dashboard/Create Meeting/Meeting Detail)

---

## Prompt สำหรับวาง Stitch

ออกแบบหน้าเว็บใหม่ 1 หน้า ชื่อ **"Policy & Board Document Search"** สำหรับระบบผู้ช่วยเลขานุการบริษัท
(Company Secretary AI System) — เป็นหน้าที่ 4 ต่อจาก Dashboard/Create Meeting/Meeting Detail ที่มีอยู่
แล้ว ต้องใช้ดีไซน์ระบบเดียวกันเป๊ะ (ดู Design System ด้านล่าง) ไม่ใช่สร้างธีมใหม่

### บริบทของฟีเจอร์

หน้านี้เป็น **AI Q&A search** ให้พนักงานถามคำถามเป็นภาษาธรรมชาติ (ภาษาไทยเป็นหลัก) แล้วได้คำตอบที่สรุป
มาจากเอกสารนโยบายบริษัท/รายงานการประชุมย้อนหลังจริง พร้อมอ้างอิงแหล่งที่มา (RAG — Retrieval-Augmented
Generation) ไม่ใช่แค่ full-text search ธรรมดา

### โครงหน้า (Layout)

1. **Header เดิม** — โลโก้ "Com Sec AI" ซ้าย, role dropdown (Com Sec Maker / Com Sec Checker / Board
   Member / Admin) + nav กลับ Dashboard ขวา (เหมือน 3 หน้าเดิมทุกอย่าง)
2. **Scope Selector** (ใต้ header) — toggle/tab 2 ตัวเลือกให้ผู้ใช้เลือกก่อนถาม:
   - **"นโยบายทั่วไป" (General Policy)** — ค้นในคลังเอกสารนโยบายบริษัททั่วไป
   - **"เอกสารบอร์ด (ลับ)" (Board Documents — Confidential)** — ค้นเฉพาะรายงานการประชุมบอร์ด/มติที่
     อนุมัติแล้ว ใส่ไอคอนกุญแจ/โล่เล็กๆ กำกับให้ดูออกว่าเป็นข้อมูลชั้นสูงกว่า (ไม่ต้องมี logic
     ซับซ้อน แค่ให้ต่างจาก tab แรกด้วยสายตา)
3. **Search Box** — input ข้อความยาวได้หลายบรรทัด (ผู้ใช้อาจพิมพ์คำถามยาว) + ปุ่ม "ค้นหา" (Search)
   วางแบบ chat input (คล้าย ChatGPT/Gemini) ไม่ใช่ search bar สั้นๆแบบ Google
4. **Conversation/History Area** — พื้นที่หลักตรงกลาง แสดงประวัติคำถาม-คำตอบในเซสชันนี้แบบเรียงจากบนลง
   ล่าง (คำถามของผู้ใช้ชิดขวาแบบ chat bubble, คำตอบ AI ชิดซ้าย) — แต่ละคำตอบต้องมี:
   - เนื้อหาคำตอบ (ข้อความยาวได้หลายย่อหน้า)
   - **กล่องแหล่งอ้างอิง (Sources)** ต่อท้ายคำตอบเสมอ — แสดงเป็น badge/card เล็กๆ ต่อไฟล์ที่ AI อ้างอิง
     (ชื่อไฟล์ + ตัวอย่างข้อความสั้นๆ 1-2 บรรทัดจากไฟล์นั้น) คลิกขยายดู snippet เต็มได้ (accordion หรือ
     tooltip ก็ได้)
5. **Loading State ที่สำคัญมาก** — คำถามนี้อาจใช้เวลาตอบ **นานถึงหลายนาที** (ไม่ใช่ 2-3 วินาทีแบบ
   search ทั่วไป) ต้องออกแบบ loading state ที่บอกผู้ใช้ชัดเจนว่ากำลังประมวลผลอยู่ ไม่ใช่ค้าง/พัง — เช่น
   ข้อความ "กำลังค้นหาและสรุปคำตอบ... อาจใช้เวลาถึงหลายนาที" พร้อม animated indicator (ไม่ใช่ progress
   bar ที่ผูกเวลาแน่นอน เพราะไม่รู้เวลาจริงล่วงหน้า) — ปุ่ม Search ต้อง disable ระหว่างรอ
6. **Empty State** — ตอนยังไม่เคยถามอะไรเลย โชว์ placeholder แนะนำตัวอย่างคำถาม 2-3 ข้อ (เช่น
   "นโยบายการลาป่วยเป็นอย่างไร", "มติที่ประชุมบอร์ดครั้งล่าสุดเรื่องงบลงทุนคืออะไร")
7. **Error State** — เช่น ระบบค้นหายังไม่พร้อม (โหลดโมเดลอยู่)/หมดเวลา/ไม่มีสิทธิ์ — แสดงเป็นข้อความ
   error สีแดงในตำแหน่งเดียวกับที่คำตอบควรจะอยู่ ไม่ใช่ popup/alert

### Design System (ต้องใช้ตรงตามนี้ — ห้ามเปลี่ยนสี/ฟอนต์)

- พื้นหลังหลัก (Deep Empire Teal): `#0F282A`
- พื้นผิว panel/card (Teal-Mid): `#1C3936`
- เส้นขอบ/แถบรอง (Cyan-Teal-Deep): `#123B3A`
- สีทองหลัก/ปุ่ม primary (Global Gold): `#D9B168` (hover: `#F3DE8F`, deep: `#AA843D`)
- สีฟ้าอมเขียว รอง/ลิงก์ (Origin Cyan-Teal): `#ACD8D9`
- ตัวอักษรหลัก: ขาว `#FFFFFF`, ตัวอักษรรอง/มืดกว่า: `#A0B0B0`
- สี status: แดง (error) `#dc3545`, เขียว (success) `#28a745`, เหลือง (warning) `#ffc107`
- Font: หัวข้อใช้ Montserrat (600/700), เนื้อหาใช้ Inter (400/600)
- มุมโค้ง (border-radius) 8px ทุกจุด (การ์ด/ปุ่ม/input)
- โทนรวม: dark theme หรูหรา แบบองค์กร ไม่ใช่ playful/casual

### สิ่งที่ไม่ต้องออกแบบมาให้ (ทำต่อเองภายหลัง)

- ไม่ต้องมี logic จริง (นี่คือ static mockup)
- ไม่ต้องกังวลเรื่อง responsive/mobile (ระบบนี้ใช้บนคอมพิวเตอร์ทำงานเท่านั้น)
- ไม่ต้องใส่ font จาก Google Fonts CDN ถ้าเลี่ยงได้ (ระบบนี้จัดการข้อมูลลับ พยายามลด external
  dependency — แต่ถ้า Stitch ใส่มาเป็นค่า default ก็รับได้ ไม่ใช่ตัวบล็อก)

### Output ที่ต้องการ

HTML/CSS แบบ static file (เหมือน 3 หน้าเดิม — `index.html`/`create-meeting.html`/
`meeting-detail.html` ที่มีอยู่แล้วใน `D:\Com Sec\ComSecAI_Dashboard\`) ไม่ต้องมี JavaScript framework
ใดๆ (React/Vue ฯลฯ) — Plain HTML/CSS พอ

---

## หมายเหตุสำหรับตอนเอาผลลัพธ์กลับมา (ไม่ต้องส่งให้ Stitch ส่วนนี้)

- บันทึกไฟล์ที่ได้ไว้ที่ `D:\Com Sec\ComSecAI_Dashboard\` (เช่น `search.html`) แล้วบอกผม ผมจะ:
  1. ต่อเข้ากับ `POST /api/rag/query` (scope ทั่วไป) และ `POST /api/rag/query_confidential` (scope
     เอกสารบอร์ด) ที่มีอยู่แล้วจริงใน backend
  2. เพิ่ม nav link ไปหน้านี้ในหัวของอีก 3 หน้าเดิม (ตอนนี้ยังไม่มีทางเข้าหน้านี้จากที่ไหนเลย)
  3. Response ที่ backend ส่งกลับมาจริงมีโครงสร้าง `{"response": "ข้อความคำตอบ", "sources": [{"file_name": "...", "content": "..."}], "tokens": n}` — ตรงกับ Sources card ที่ระบุไว้ใน brief ข้างบนพอดี
  4. คำเตือน timeout จริง: query อาจใช้เวลาถึง ~30 นาทีในกรณีเลวร้ายสุด (ดู `backend/rag.py`'s
     `RAG_WORKER_TIMEOUT_SECONDS`) — loading state ที่ขอให้ Stitch ออกแบบมาสำคัญจริง ไม่ใช่ขอเผื่อเฉยๆ
