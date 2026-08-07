/*
  app.js — เชื่อม static mockup ที่ออกแบบจาก Google Stitch (Antigravity) เข้ากับ backend จริง
  (D:\Com Sec\backend\main.py) ไฟล์เดียวใช้ร่วมกันทั้ง 3 หน้า (index/create-meeting/meeting-detail)
  — แต่ละหน้าเรียก initX() ของตัวเองตาม DOM element ที่มีอยู่จริงในหน้านั้น (ดูท้ายไฟล์)

  Auth: ระบบยังเป็น mock auth (ดู backend/auth.py — ยังไม่ได้ต่อ Azure AD จริง) เลือก role ผ่าน
  dropdown แล้ว map เป็น mock token คงที่ ส่งเป็น Bearer token ทุก request — เก็บ role ที่เลือกไว้ใน
  localStorage กันต้องเลือกใหม่ทุกครั้งที่รีเฟรช (ไฟล์นี้รันในเบราว์เซอร์บนเครื่องผู้ใช้เอง ไม่ใช่
  Claude artifact ที่ห้ามใช้ localStorage)
*/

const ROLE_TOKENS = {
  "Com Sec Maker": "mock_maker_token",
  "Com Sec Checker": "mock_checker_token",
  "Board Member": "mock_board_token",
  "Admin": "mock_admin_token",
};
const ROLE_STORAGE_KEY = "comsec_role";

function getCurrentRole() {
  return localStorage.getItem(ROLE_STORAGE_KEY) || "Com Sec Maker";
}

function getCurrentToken() {
  return ROLE_TOKENS[getCurrentRole()] || ROLE_TOKENS["Com Sec Maker"];
}

/** ผูก <select class="role-select"> ทุกตัวในหน้าเข้ากับ localStorage — เรียกครั้งเดียวตอนโหลดหน้า
 * ใช้ querySelectorAll (ไม่ใช่ querySelector ตัวเดียวแบบเดิม) เพราะ search.html (ใหม่ 2026-08-04) มี
 * .role-select 2 ตัว (mobile header + desktop sidebar) พร้อมกัน — เปลี่ยนตัวไหนต้อง sync อีกตัวด้วย
 * ไม่งั้นจะโชว์ role คนละอันกันจนกว่าจะรีเฟรชหน้า (ค่าจริงที่ apiFetch ใช้อ่านจาก localStorage เสมอ
 * ถูกต้องอยู่แล้ว แต่ UI ที่ไม่ sync กันจะดูเหมือนบั๊ก) */
function initRoleSelect() {
  const selects = document.querySelectorAll(".role-select");
  if (!selects.length) return;
  selects.forEach((select) => { select.value = getCurrentRole(); });
  selects.forEach((select) => {
    select.addEventListener("change", () => {
      localStorage.setItem(ROLE_STORAGE_KEY, select.value);
      selects.forEach((other) => { if (other !== select) other.value = select.value; });
    });
  });
}

/**
 * apiFetch — เรียก backend API (same-origin เพราะ dashboard นี้ถูก FastAPI serve เอง ไม่ต้องมี
 * CORS) แนบ Authorization header เสมอ, ถ้า body เป็น plain object จะ JSON.stringify ให้อัตโนมัติ
 * (FormData ปล่อยผ่านตรงๆ สำหรับ multipart upload) — throw Error ที่มีข้อความจาก backend's
 * `detail` field ถ้า response ไม่ใช่ 2xx ให้ caller catch ไปแสดงผลเอง
 */
async function apiFetch(path, options = {}) {
  const headers = Object.assign({ Authorization: `Bearer ${getCurrentToken()}` }, options.headers || {});
  let body = options.body;
  if (body && !(body instanceof FormData) && typeof body === "object") {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(body);
  }

  const resp = await fetch(path, Object.assign({}, options, { headers, body }));
  let payload = null;
  try {
    payload = await resp.json();
  } catch {
    // response ไม่มี JSON body (เช่น 204) — ปล่อยเป็น null
  }
  if (!resp.ok) {
    const detail = (payload && (payload.detail || payload.message)) || `HTTP ${resp.status}`;
    throw new Error(detail);
  }
  return payload;
}

/** "2026-08-12T00:00:00" → "12 Aug 2026" (ตรงกับ format ที่ mockup เดิมของ Stitch ใช้) */
function formatDate(isoString) {
  if (!isoString) return "-";
  const d = new Date(isoString);
  if (Number.isNaN(d.getTime())) return isoString;
  return d.toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" });
}

/** วินาที (float, จาก audio_worker ตรงๆ) → "MM:SS" */
function formatSeconds(seconds) {
  const total = Math.max(0, Math.round(seconds || 0));
  const mm = Math.floor(total / 60);
  const ss = total % 60;
  return `${String(mm).padStart(2, "0")}:${String(ss).padStart(2, "0")}`;
}

/** map สถานะ (จาก Meeting.status) → { badgeClass, label } ให้ตรงกับ badge-* class ที่มีอยู่แล้วใน
 * style.css ของ Stitch เป๊ะ ไม่ต้องเพิ่ม CSS class ใหม่ */
const STATUS_META = {
  draft: { cls: "badge-draft", label: "Draft" },
  uploaded: { cls: "badge-uploaded", label: "Uploaded" },
  processing: { cls: "badge-processing", label: "Processing ⏳" },
  transcribed: { cls: "badge-transcribed", label: "Transcribed" },
  failed: { cls: "badge-failed", label: "Failed" },
};

function statusBadgeHtml(status) {
  const meta = STATUS_META[status] || { cls: "badge-draft", label: status };
  return `<span class="badge ${meta.cls}">${meta.label}</span>`;
}

/** map resolution_status (จาก Module 3 Minutes Generation) → badge — reuse badge-* class เดิม
 * (ไม่เพิ่ม CSS ใหม่ เหมือน STATUS_META ด้านบน) */
const RESOLUTION_STATUS_META = {
  approved: { cls: "badge-success", label: "อนุมัติ" },
  rejected: { cls: "badge-failed", label: "ไม่อนุมัติ" },
  deferred: { cls: "badge-warning", label: "เลื่อน" },
  acknowledged: { cls: "badge-transcribed", label: "รับทราบ" },
  no_resolution: { cls: "badge-draft", label: "ไม่มีข้อมูลมติ" },
};

function resolutionStatusBadgeHtml(status) {
  const meta = RESOLUTION_STATUS_META[status] || { cls: "badge-draft", label: status };
  return `<span class="badge ${meta.cls}">${meta.label}</span>`;
}

function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

// ─────────────────────────────────────────────────────────────────────────
// index.html — Dashboard (ตาราง Board Meetings)
// ─────────────────────────────────────────────────────────────────────────

let _dashboardPollTimer = null;

function speakerMatchingCellHtml(meeting) {
  if (meeting.status !== "transcribed" || !meeting.speaker_labels || meeting.speaker_labels.length === 0) {
    return "-";
  }
  const mapped = meeting.speaker_labels.filter(
    (label) => (meeting.speaker_mapping[label] || "").trim()
  ).length;
  if (meeting.speaker_mapping_complete) {
    return '<span class="badge badge-success">Complete ✓</span>';
  }
  return `<span class="badge badge-warning">Incomplete (${mapped}/${meeting.speaker_labels.length})</span>`;
}

// เลือกโมเดล Gemini เองตอน upload/re-upload (2026-08-05) — <select> ว่างไว้ก่อน (populate จริงใน
// renderMeetingsTable() หลัง DOM สร้างเสร็จ เพราะ getModelOptionsHtml() เป็น async แต่ actionCellHtml
// เป็น sync — ต้อง data-id ตรงกับปุ่มเพื่อ query ทีหลังได้)
function modelSelectHtml(meeting) {
  const title = "เลือกโมเดลเจาะจง = ปิดการสลับโมเดลสำรองอัตโนมัติทั้งหมด (ใช้โมเดลนั้นตัวเดียว)";
  return `<select class="model-select" data-id="${meeting.id}" title="${title}" style="font-size: 0.8rem; padding: 0.3rem; margin-right: 0.5rem;"></select>`;
}

function actionCellHtml(meeting) {
  // draft: ยังไม่มีไฟล์เสียง → ปุ่มอัปโหลดอย่างเดียว (ไม่มีอะไรให้ดูใน detail page)
  // failed: อัปโหลดไปแล้วแต่ประมวลผลพัง → ปุ่ม re-upload (โชว์ processing_error เป็น title
  // tooltip กันต้องเปิดหน้าอื่นแค่เพื่อดู error สั้นๆ)
  // uploaded/processing/transcribed: มีอะไรให้ดูแล้ว → View ไปหน้า detail
  if (meeting.status === "draft") {
    return `${modelSelectHtml(meeting)}<button class="btn btn-secondary upload-btn" data-id="${meeting.id}">Upload Audio</button>`;
  }
  if (meeting.status === "failed") {
    const title = meeting.processing_error ? ` title="${escapeHtml(meeting.processing_error)}"` : "";
    return `${modelSelectHtml(meeting)}<button class="btn btn-secondary upload-btn" data-id="${meeting.id}"${title}>Re-upload</button>`;
  }
  return `<a href="meeting-detail.html?id=${meeting.id}" class="btn btn-secondary">View</a>`;
}

function renderMeetingsTable(meetings) {
  const tbody = document.getElementById("meetings-tbody");
  if (!tbody) return;

  if (meetings.length === 0) {
    tbody.innerHTML = `<tr><td colspan="5" class="text-muted">ยังไม่มีการประชุม — กด "+ Create New Meeting" เพื่อเริ่ม</td></tr>`;
    return;
  }

  tbody.innerHTML = meetings.map((m) => `
    <tr>
      <td>${escapeHtml(m.meeting_number)}</td>
      <td>${formatDate(m.meeting_date)}</td>
      <td>${statusBadgeHtml(m.status)}</td>
      <td>${speakerMatchingCellHtml(m)}</td>
      <td>${actionCellHtml(m)}</td>
    </tr>
  `).join("");

  // ปุ่ม upload/re-upload — สร้าง <input type="file"> ที่มองไม่เห็นต่อปุ่ม กด browse ไฟล์แล้ว
  // อัปโหลดทันที (ไม่มี modal เพิ่ม ตรงกับ interaction เดิมของปุ่มใน mockup ที่ยังไม่ทำงานจริง)
  tbody.querySelectorAll(".upload-btn").forEach((btn) => {
    btn.addEventListener("click", () => triggerUpload(Number(btn.dataset.id), btn));
  });

  // populate model-select ทุกแถวพร้อมกัน (async แยกจาก sync render ด้านบน — ดู modelSelectHtml())
  getModelOptionsHtml().then((html) => {
    tbody.querySelectorAll(".model-select").forEach((sel) => { sel.innerHTML = html; });
  });
}

function triggerUpload(meetingId, btn) {
  // ต่อ input เข้า DOM จริง (แค่ซ่อนไว้) ก่อนเรียก .click() — บาง browser ไม่เปิด file picker
  // ให้ถ้า element ยังไม่ถูก attach เข้า document เลย (ไม่ reliable ทุก browser ถ้าเรียก .click()
  // บน element ลอยๆ) แล้วลบทิ้งหลังใช้งานเสร็จทุกกรณี (สำเร็จ/ล้มเหลว)
  const input = document.createElement("input");
  input.type = "file";
  input.accept = "audio/*,video/*";
  input.style.display = "none";
  document.body.appendChild(input);

  input.onchange = async () => {
    if (!input.files || input.files.length === 0) {
      input.remove();
      return;
    }
    const originalText = btn.textContent;
    btn.disabled = true;
    btn.textContent = "กำลังอัปโหลด...";
    try {
      const form = new FormData();
      form.append("file", input.files[0]);
      // เลือกโมเดลเอง (2026-08-05) — <select class="model-select"> อยู่ข้างปุ่มเดียวกันเสมอ (ดู
      // actionCellHtml()) ค่าว่าง = ใช้ fallback chain ปกติจาก backend (ไม่ส่ง field นี้เลยถ้าไม่ได้
      // เลือกอะไร กัน backend ต้องแยกแยะ "" กับไม่ส่งมา)
      const modelSelect = btn.parentElement?.querySelector(".model-select");
      if (modelSelect && modelSelect.value) form.append("model", modelSelect.value);
      await apiFetch(`/api/meetings/${meetingId}/upload`, { method: "POST", body: form });
      await loadMeetings();
    } catch (err) {
      alert(`อัปโหลดไม่สำเร็จ: ${err.message}`);
      btn.disabled = false;
      btn.textContent = originalText;
    } finally {
      input.remove();
    }
  };
  input.click();
}

async function loadMeetings() {
  try {
    const meetings = await apiFetch("/api/meetings");
    renderMeetingsTable(meetings);
  } catch (err) {
    const tbody = document.getElementById("meetings-tbody");
    if (tbody) {
      tbody.innerHTML = `<tr><td colspan="5" class="text-muted">โหลดรายการประชุมไม่สำเร็จ: ${escapeHtml(err.message)}</td></tr>`;
    }
  }
}

function initDashboardPage() {
  const tbody = document.getElementById("meetings-tbody");
  if (!tbody) return; // ไม่ใช่หน้านี้

  loadMeetings();
  // poll ทุก 5 วิ ให้เห็นสถานะ processing → transcribed โดยไม่ต้องกดรีเฟรชเอง (เหมือนที่ทดสอบผ่าน
  // curl ตอน Module 2 ที่ต้อง poll GET ซ้ำๆ) — เขียนทับทั้งตารางทุกครั้งได้เพราะหน้านี้ไม่มี input
  // ให้ผู้ใช้พิมพ์ค้างอยู่ (ต่างจาก meeting-detail's speaker mapping panel ที่ต้องระวังเรื่องนี้)
  _dashboardPollTimer = setInterval(loadMeetings, 5000);
}

// ─────────────────────────────────────────────────────────────────────────
// create-meeting.html — ฟอร์มสร้างการประชุมใหม่
// ─────────────────────────────────────────────────────────────────────────

function addParticipantRow(container) {
  const row = document.createElement("div");
  row.className = "grid-2 mb-4 participant-row";
  row.innerHTML = `
    <input type="text" class="participant-name" placeholder="Name">
    <div style="display: flex; gap: 1rem;">
      <input type="text" class="participant-position" placeholder="Position" style="flex: 1;">
      <input type="email" class="participant-email" placeholder="Email (สำหรับ Magic Link)" style="flex: 1;">
      <button type="button" class="btn btn-secondary remove-row-btn" style="color: var(--status-failed); border-color: var(--status-failed);">Remove</button>
    </div>
  `;
  container.appendChild(row);
}

function addAgendaRow(container) {
  const row = document.createElement("div");
  row.className = "agenda-row";
  row.style.cssText = "display: flex; gap: 1rem; margin-bottom: 1rem;";
  row.innerHTML = `
    <input type="text" class="agenda-label" placeholder="เลขวาระ (ไม่บังคับ)" style="width: 160px;">
    <input type="text" class="agenda-item" placeholder="Agenda item" style="flex: 1;">
    <button type="button" class="btn btn-secondary remove-row-btn" style="color: var(--status-failed); border-color: var(--status-failed);">Remove</button>
  `;
  container.appendChild(row);
}

/** Multi-template (2026-08-03) — โหลดรายการ template จาก backend มาใส่ dropdown ตอนสร้างประชุม
 * (แทนที่จะ hardcode ในหน้า HTML — เพิ่ม template ใหม่ที่ backend แล้วจะโผล่ที่นี่อัตโนมัติ ไม่ต้อง
 * แก้ frontend เลย) */
async function loadTemplateOptions(selectEl) {
  try {
    const templates = await apiFetch("/api/templates");
    selectEl.innerHTML = templates.map((t) => `<option value="${escapeHtml(t.name)}">${escapeHtml(t.label)}</option>`).join("");
  } catch (err) {
    selectEl.innerHTML = '<option value="bod_minutes">รายงานการประชุมคณะกรรมการบริษัท (BOD Minutes)</option>';
  }
}

/** เลือกโมเดล Gemini เองตอน upload/re-upload (2026-08-05, ผู้ใช้ขอ — ดู backend's
 * GET /api/transcription_models/config.py's GEMINI_TRANSCRIPTION_MODEL_CHOICES) — cache ผลไว้
 * module-level เพราะ dashboard เรียกใช้ต่อแถว (หลาย meeting พร้อมกัน) ไม่อยาก fetch ซ้ำทุกแถว
 * ต่างจาก loadTemplateOptions() ที่มีแค่จุดเดียว (create-meeting.html) เลย fetch ตรงได้เลยไม่ต้อง
 * cache */
let _modelOptionsHtmlCache = null;

async function getModelOptionsHtml() {
  if (_modelOptionsHtmlCache) return _modelOptionsHtmlCache;
  try {
    const data = await apiFetch("/api/transcription_models");
    // ⚠️ บั๊กที่แก้ตรงนี้ (พบจาก log จริง 2026-08-07, /debug-mantra): เดิม options ทุกตัว map จาก
    // data.models ล้วนๆ (ไม่มีค่าว่างเลย) แล้ว pre-select โมเดล primary (data.default) ไว้เสมอ —
    // triggerUpload()/triggerReuploadOnDetailPage() เช็คแค่ `if (modelSelect.value)` ก่อน append
    // field "model" (ดู comment เดิมบรรทัดนั้น: "ค่าว่าง = ใช้ fallback chain ปกติจาก backend")
    // แต่เพราะ <select> มี option ที่ selected อยู่เสมอ .value จึงไม่เคยว่างจริงเลยสักครั้ง — ทุก
    // upload/re-upload จากหน้านี้เลยส่ง model override มาเสมอ 100% โดยผู้ใช้ไม่รู้ตัว ทำให้
    // audio_native.py's `fallback_models = [] if model_override else config.FALLBACK` (บรรทัด 172)
    // ปิด fallback chain ทั้ง 3 โมเดลทิ้งไปเงียบๆทุกครั้ง — เจอจริง: chunk พัง 503 ครั้งเดียวแล้ว fail
    // ทันที ไม่มี log พยายามลองโมเดลสำรองเลยสักบรรทัด — เพิ่ม option ค่าว่างกลับมาเป็นดีฟอลต์ (ตรงกับ
    // เจตนาเดิมที่ comment ไว้แล้วทั้ง 2 จุด ไม่ใช่การเปลี่ยน design ใหม่) โมเดลเจาะจงยังเลือกได้เหมือน
    // เดิมทุกประการ แค่ไม่ใช่ค่าเริ่มต้นอีกต่อไป
    const defaultOption =
      '<option value="" selected>ค่าเริ่มต้น (ลองโมเดลสำรองอัตโนมัติถ้าโมเดลหลักพัง)</option>';
    const modelOptions = data.models
      .map((m) => `<option value="${escapeHtml(m.value)}">${escapeHtml(m.label)}${m.value === data.default ? " (หลัก)" : ""}</option>`)
      .join("");
    _modelOptionsHtmlCache = defaultOption + modelOptions;
  } catch (err) {
    // fallback แบบเดียวกับ loadTemplateOptions() — เผื่อ backend ยังไม่ทันมี endpoint นี้/เรียกไม่ได้
    _modelOptionsHtmlCache = '<option value="" selected>ค่าเริ่มต้น (ใช้ fallback chain อัตโนมัติ)</option>';
  }
  return _modelOptionsHtmlCache;
}

function initCreateMeetingPage() {
  const form = document.getElementById("create-meeting-form");
  if (!form) return; // ไม่ใช่หน้านี้

  const participantsContainer = document.getElementById("participants-container");
  const agendaContainer = document.getElementById("agenda-container");
  const templateSelect = document.getElementById("meeting-template-select");
  if (templateSelect) loadTemplateOptions(templateSelect);

  document.getElementById("add-participant-btn").addEventListener("click", () => {
    addParticipantRow(participantsContainer);
  });
  document.getElementById("add-agenda-btn").addEventListener("click", () => {
    addAgendaRow(agendaContainer);
  });

  // Event delegation แทนการผูก listener ต่อแถว — ครอบคลุมทั้งแถวเริ่มต้นที่มีอยู่แล้วใน HTML
  // (จาก Stitch mockup เดิม) และแถวที่เพิ่มทีหลังผ่าน addParticipantRow/addAgendaRow ด้วยตัวมันเอง
  participantsContainer.addEventListener("click", (ev) => {
    const btn = ev.target.closest(".remove-row-btn");
    if (btn) btn.closest(".participant-row").remove();
  });
  agendaContainer.addEventListener("click", (ev) => {
    const btn = ev.target.closest(".remove-row-btn");
    if (btn) btn.closest(".agenda-row").remove();
  });

  form.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const errorBox = document.getElementById("form-error");
    errorBox.textContent = "";

    const meetingNumber = document.getElementById("meeting-number").value.trim();
    const meetingDate = document.getElementById("meeting-date").value;
    if (!meetingNumber || !meetingDate) {
      errorBox.textContent = "กรุณากรอกเลขที่ประชุมและวันที่ประชุม";
      return;
    }

    // Module 4-5 (2026-08-03): email ไม่บังคับ — ผู้เข้าร่วมที่ไม่กรอกจะไม่ได้รับ Magic Link ตอน
    // อนุมัติเอกสาร (ดู backend/models.py's MeetingAttendee.email docstring)
    const attendees = Array.from(participantsContainer.querySelectorAll(".participant-row"))
      .map((row) => ({
        name: row.querySelector(".participant-name").value.trim(),
        position: row.querySelector(".participant-position").value.trim() || null,
        email: row.querySelector(".participant-email").value.trim() || null,
      }))
      .filter((a) => a.name);

    // เลขวาระ (2026-08-07, ผู้ใช้ขอ) — ส่งเป็น {label, description} คู่กัน ตัดแถวที่ไม่กรอก
    // description ทิ้ง (label ปล่อยว่างได้ — backend เติม "วาระที่ N" ให้อัตโนมัติ)
    const agendaItems = Array.from(agendaContainer.querySelectorAll(".agenda-row"))
      .map((row) => ({
        label: row.querySelector(".agenda-label").value.trim() || null,
        description: row.querySelector(".agenda-item").value.trim(),
      }))
      .filter((a) => a.description);

    const submitBtn = form.querySelector('button[type="submit"]');
    submitBtn.disabled = true;
    try {
      await apiFetch("/api/meetings", {
        method: "POST",
        body: {
          meeting_number: meetingNumber, meeting_date: meetingDate, attendees, agenda_items: agendaItems,
          template_name: templateSelect ? templateSelect.value : "bod_minutes",
        },
      });
      window.location.href = "index.html";
    } catch (err) {
      errorBox.textContent = `บันทึกไม่สำเร็จ: ${err.message}`;
      submitBtn.disabled = false;
    }
  });
}

// ─────────────────────────────────────────────────────────────────────────
// meeting-detail.html — รายละเอียดการประชุม + Speaker Mapping + Transcript
// ─────────────────────────────────────────────────────────────────────────

function getMeetingIdFromUrl() {
  const params = new URLSearchParams(window.location.search);
  const id = params.get("id");
  return id ? Number(id) : null;
}

function renderSpeakerMapping(meeting, container) {
  if (!meeting.speaker_labels || meeting.speaker_labels.length === 0) {
    container.innerHTML = '<p class="text-muted">ยังไม่พบผู้พูดใน transcript</p>';
    return;
  }

  const attendeeNames = meeting.attendees.map((a) => a.name);
  const datalistHtml = attendeeNames.length
    ? `<datalist id="attendee-list">${attendeeNames.map((n) => `<option value="${escapeHtml(n)}">`).join("")}</datalist>`
    : "";

  const rowsHtml = meeting.speaker_labels.map((label) => `
    <div class="form-group">
      <label>${escapeHtml(label)}</label>
      <input type="text" class="mapping-input" data-label="${escapeHtml(label)}"
             list="attendee-list" placeholder="พิมพ์ชื่อผู้เข้าร่วม..."
             value="${escapeHtml(meeting.speaker_mapping[label] || "")}">
    </div>
  `).join("");

  const mappedCount = meeting.speaker_labels.filter(
    (label) => (meeting.speaker_mapping[label] || "").trim()
  ).length;
  const totalCount = meeting.speaker_labels.length;
  const statusHtml = meeting.speaker_mapping_complete
    ? '<span class="badge badge-success">Complete ✓</span>'
    : `<span class="badge badge-warning">${mappedCount}/${totalCount} matched</span>`;

  container.innerHTML = `
    ${datalistHtml}
    ${rowsHtml}
    <div class="flex-between mt-4" style="border-top: 1px solid var(--secondary-cyan-deep); padding-top: 1rem;">
      <span id="mapping-status-badge">${statusHtml}</span>
      <button id="save-mapping-btn" class="btn btn-primary">Save Mapping</button>
    </div>
    <p id="mapping-error" class="text-muted" style="color: var(--status-failed);"></p>
  `;

  document.getElementById("save-mapping-btn").addEventListener("click", async () => {
    const btn = document.getElementById("save-mapping-btn");
    const errorBox = document.getElementById("mapping-error");
    errorBox.textContent = "";
    const mapping = {};
    container.querySelectorAll(".mapping-input").forEach((input) => {
      const value = input.value.trim();
      if (value) mapping[input.dataset.label] = value;
    });

    btn.disabled = true;
    btn.textContent = "กำลังบันทึก...";
    try {
      const updated = await apiFetch(`/api/meetings/${meeting.id}/speaker_mapping`, {
        method: "POST",
        body: { mapping },
      });
      // เขียนทับ meeting ในหน่วยความจำแล้ว re-render เฉพาะ badge + transcript (ไม่ re-render
      // input ทั้งหมด กัน cursor/focus กระโดดระหว่างพิมพ์ต่อ ถ้าจะพิมพ์เพิ่มหลัง save)
      Object.assign(meeting, updated);
      const mapped2 = meeting.speaker_labels.filter((l) => (meeting.speaker_mapping[l] || "").trim()).length;
      document.getElementById("mapping-status-badge").innerHTML = meeting.speaker_mapping_complete
        ? '<span class="badge badge-success">Complete ✓</span>'
        : `<span class="badge badge-warning">${mapped2}/${totalCount} matched</span>`;
      renderTranscript(meeting, document.getElementById("transcript-container"));
    } catch (err) {
      errorBox.textContent = `บันทึกไม่สำเร็จ: ${err.message}`;
    } finally {
      btn.disabled = false;
      btn.textContent = "Save Mapping";
    }
  });
}

function speakerDisplayName(meeting, speaker) {
  const mappedName = meeting.speaker_mapping[speaker];
  return mappedName ? `${escapeHtml(mappedName)} (${escapeHtml(speaker)})` : escapeHtml(speaker || "-");
}

/** โชว์ชื่อโมเดล Gemini ที่ transcribe สำเร็จจริง (2026-08-05, ผู้ใช้ขอให้บันทึก/แสดงทุกที่ — ดู
 * backend/models.py's Meeting.transcription_model_used) — ซ่อนเงียบๆถ้าเป็น null (meeting เก่า
 * ก่อนมี field นี้ หรือประมวลผลไม่สำเร็จ) ไม่ error/ไม่โชว์ข้อความว่างๆ */
function renderTranscriptionModelUsed(meeting) {
  const el = document.getElementById("transcript-model-used");
  if (!el) return;
  if (meeting.transcription_model_used) {
    el.textContent = `ถอดเสียงด้วยโมเดล: ${meeting.transcription_model_used}`;
    el.style.display = "";
  } else {
    el.style.display = "none";
  }
}

function renderTranscript(meeting, container) {
  const segments = meeting.transcript_segments || [];
  if (segments.length === 0) {
    container.innerHTML = '<p class="text-muted">ยังไม่มี transcript</p>';
    return;
  }
  // data-start (ใหม่, ดู setupAudioPlayer/highlightActiveTranscriptSegment) — ให้ click
  // seek ไปยังเวลานั้นใน <audio> player ได้ + ใช้เทียบกับ currentTime ตอนไฮไลต์บรรทัดที่กำลังเล่นอยู่
  container.innerHTML = segments.map((seg) => `
      <div class="transcript-line" data-start="${seg.start}">
        <span class="speaker-name">${speakerDisplayName(meeting, seg.speaker)}</span>
        <span class="speaker-time">${formatSeconds(seg.start)}</span>
        <p>${escapeHtml(seg.text)}</p>
      </div>
    `).join("");
}

/**
 * Audio Playback Sync — "preview ฟังไฟล์เสียงย้อนหลัง" (ใหม่ 2026-08-04, ดู task.md Module 6
 * "Synced Audio/Video Player + Transcript Panel") อ้างอิงแพทเทิร์นจาก meetily/frontend
 * (useAudioPlayer.ts/TranscriptView.tsx) แต่เขียนใหม่ด้วย HTML5 <audio> ธรรมดา + ontimeupdate แทน
 * AudioContext/Tauri invoke('read_audio_file') เดิม (เว็บ same-origin ไม่มีข้อจำกัดแบบ Tauri app
 * ให้ต้องอ้อม — <audio src="..."> ตรงๆ ก็ seek/stream ได้อยู่แล้วโดยธรรมชาติ)
 */

/** URL สำหรับ <audio src=...> — แนบ mock token ผ่าน query string เพราะ <audio> element เรียก src
 * ตรงๆ ไม่มีทางแนบ Authorization header เองได้ (ต่างจาก apiFetch/downloadAuthenticatedFile ที่ใช้
 * fetch() สั่งเอง) ดู backend/auth.py's verify_audio_stream_token() ฝั่ง backend + คำเตือนเรื่อง
 * ความเสี่ยง token ใน query string (ยอมรับได้ตอนนี้เพราะเป็น mock token คงที่ ไม่ใช่ของจริง) */
function meetingAudioUrl(meetingId) {
  return `/api/meetings/${meetingId}/audio?token=${encodeURIComponent(getCurrentToken())}`;
}

/** เพิ่ม class "active" ให้ .transcript-line ที่ตรงกับเวลาปัจจุบันของ player (segment สุดท้ายที่
 * start <= currentTime — segments เรียงตามเวลาอยู่แล้วเสมอ ไม่ต้อง sort ซ้ำ) เอาออกจากตัวอื่นทั้งหมด
 * ก่อนเสมอ แล้วเลื่อนจอตามถ้าบรรทัดนั้นยังไม่อยู่ในมุมมอง — เรียกทุกครั้งที่ <audio> ยิง "timeupdate" */
function highlightActiveTranscriptSegment(currentTime) {
  const container = document.getElementById("transcript-container");
  if (!container) return;
  const lines = container.querySelectorAll(".transcript-line[data-start]");
  let activeEl = null;
  lines.forEach((el) => {
    const start = parseFloat(el.dataset.start);
    if (!Number.isNaN(start) && start <= currentTime) activeEl = el;
  });
  lines.forEach((el) => el.classList.toggle("active", el === activeEl));
  if (activeEl) {
    const rect = activeEl.getBoundingClientRect();
    const containerRect = container.getBoundingClientRect();
    const isVisible = rect.top >= containerRect.top && rect.bottom <= containerRect.bottom;
    if (!isVisible) activeEl.scrollIntoView({ block: "center", behavior: "smooth" });
  }
}

/**
 * ตั้งค่า <audio> element ของ Playback panel — เรียกทุกครั้งที่ loadMeetingDetail แต่ตั้ง src ซ้ำ
 * เฉพาะตอน meeting.id เปลี่ยน (เช็คผ่าน player.dataset.meetingId) กันเพลงที่กำลังเล่นอยู่รีเซ็ต
 * ตำแหน่ง/กระตุกทุกครั้งที่ startDetailPolling() fetch ข้อมูลใหม่ทุก 5 วินาทีระหว่าง processing
 *
 * เช็คสิทธิ์เข้าถึงไฟล์ด้วย fetch(Range: bytes=0-0) ก่อนตั้ง src จริงเสมอ — ถ้าปล่อยให้ <audio
 * src=...> ชี้ URL ที่ 403/404 ตรงๆ จะได้แค่ MediaError ทั่วไป (ไม่บอก HTTP status) ทำให้โชว์
 * ข้อความที่มีความหมายให้ผู้ใช้ไม่ได้ (เช่น Board Member ต้องรู้ว่าโดนกันสิทธิ์ ไม่ใช่ไฟล์เสีย)
 */
async function setupAudioPlayer(meeting) {
  const panel = document.getElementById("audio-player-panel");
  const player = document.getElementById("meeting-audio-player");
  const errorBox = document.getElementById("audio-player-error");
  if (!panel || !player) return;

  if (!meeting.audio_filename) {
    panel.style.display = "none";
    return;
  }
  panel.style.display = "";

  if (player.dataset.meetingId === String(meeting.id)) return; // ตั้งไปแล้ว ไม่ต้องซ้ำ
  player.dataset.meetingId = String(meeting.id);
  if (errorBox) errorBox.textContent = "";

  const url = meetingAudioUrl(meeting.id);
  try {
    const resp = await fetch(url, { headers: { Range: "bytes=0-0" } });
    if (!resp.ok) {
      let detail = `HTTP ${resp.status}`;
      try {
        const payload = await resp.json();
        detail = payload.detail || detail;
      } catch {
        // ไม่มี JSON body — ใช้ HTTP status เฉยๆ
      }
      if (errorBox) errorBox.textContent = `เล่นไฟล์เสียงไม่ได้: ${detail}`;
      player.removeAttribute("src");
      return;
    }
    player.src = url;
  } catch (err) {
    if (errorBox) errorBox.textContent = `เล่นไฟล์เสียงไม่ได้: ${err.message}`;
  }
}

/**
 * Edit Transcript (ไม่บังคับ, ตามแผน Module 2 — ไม่มีใน Stitch mockup เดิม เพิ่มเข้ามาเอง) —
 * แก้ได้แค่ text ต่อ segment เท่านั้น (start/end/speaker คงค่าเดิมเสมอ ส่งกลับไปพร้อม text ที่แก้
 * แล้วเพราะ backend's PUT .../transcript_segments เขียนทับทั้ง array) กด Save แล้วยิงทีเดียวทั้งชุด
 * ไม่ใช่ทีละ segment (ตรงกับ pattern เดียวกับ Save Mapping)
 */
function renderTranscriptEditable(meeting, container) {
  const segments = meeting.transcript_segments || [];
  container.innerHTML = segments.map((seg, i) => `
      <div class="transcript-edit-row">
        <div class="edit-meta">
          <span class="speaker-name">${speakerDisplayName(meeting, seg.speaker)}</span>
          <span class="speaker-time">${formatSeconds(seg.start)}</span>
        </div>
        <textarea class="transcript-edit-input" data-index="${i}" rows="2">${escapeHtml(seg.text)}</textarea>
      </div>
    `).join("") + `
    <div class="flex-between mt-4" style="border-top: 1px solid var(--secondary-cyan-deep); padding-top: 1rem;">
      <button id="cancel-transcript-btn" type="button" class="btn btn-secondary">Cancel</button>
      <button id="save-transcript-btn" type="button" class="btn btn-primary">Save Transcript</button>
    </div>
    <p id="transcript-edit-error" style="color: var(--status-failed);"></p>
  `;

  document.getElementById("cancel-transcript-btn").addEventListener("click", () => {
    exitTranscriptEditMode(meeting, container);
  });

  document.getElementById("save-transcript-btn").addEventListener("click", async () => {
    const btn = document.getElementById("save-transcript-btn");
    const errorBox = document.getElementById("transcript-edit-error");
    errorBox.textContent = "";

    // คง start/end/speaker เดิมของแต่ละ segment ไว้ทั้งหมด แก้แค่ text จาก textarea ที่ index
    // ตรงกัน (data-index อ้างอิง index ใน array เดิมตรงๆ ไม่ได้เรียงใหม่ระหว่างแก้ไข)
    const updatedSegments = segments.map((seg, i) => {
      const textarea = container.querySelector(`.transcript-edit-input[data-index="${i}"]`);
      return { start: seg.start, end: seg.end, speaker: seg.speaker, text: textarea.value };
    });

    btn.disabled = true;
    btn.textContent = "กำลังบันทึก...";
    try {
      const updated = await apiFetch(`/api/meetings/${meeting.id}/transcript_segments`, {
        method: "PUT",
        body: { transcript_segments: updatedSegments },
      });
      Object.assign(meeting, updated);
      exitTranscriptEditMode(meeting, container);
    } catch (err) {
      errorBox.textContent = `บันทึกไม่สำเร็จ: ${err.message}`;
      btn.disabled = false;
      btn.textContent = "Save Transcript";
    }
  });
}

function exitTranscriptEditMode(meeting, container) {
  renderTranscript(meeting, container);
  const editBtn = document.getElementById("edit-transcript-btn");
  if (editBtn) editBtn.style.display = "";
}

function exportTranscriptText(meeting) {
  const segments = meeting.transcript_segments || [];
  const lines = segments.map((seg) => {
    const mappedName = meeting.speaker_mapping[seg.speaker] || seg.speaker || "-";
    return `[${formatSeconds(seg.start)}] ${mappedName}: ${seg.text}`;
  });
  const blob = new Blob([lines.join("\n")], { type: "text/plain;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `transcript_${meeting.meeting_number.replace(/[\/\\]/g, "-")}.txt`;
  a.click();
  URL.revokeObjectURL(url);
}

function renderMeetingSummary(meeting) {
  document.getElementById("meeting-title").textContent = `Meeting ${meeting.meeting_number}`;
  document.getElementById("meeting-date").textContent = `| ${formatDate(meeting.meeting_date)}`;
  document.getElementById("meeting-status-badge").innerHTML = statusBadgeHtml(meeting.status);

  // Multi-template (2026-08-03) — โชว์ label ของ template ที่เลือกไว้ตอนสร้างประชุม (informational
  // เท่านั้น เปลี่ยนทีหลังไม่ได้ผ่าน UI นี้)
  const templateLabelEl = document.getElementById("meeting-template-label");
  if (templateLabelEl) templateLabelEl.textContent = `Template: ${meeting.template_label}`;

  renderParticipantsView(meeting);
  renderAgendaView(meeting);

  // แก้ไขย้อนหลังไม่ได้อีกหลัง Approved (ดู backend's _reject_if_approved()) — ซ่อนปุ่ม Edit ทั้งคู่
  // กันกดแล้วเจอ 400 error แบบงงๆ ตอน Save
  const isApproved = meeting.approval_status === "Approved";
  const editParticipantsBtn = document.getElementById("edit-participants-btn");
  const editAgendaBtn = document.getElementById("edit-agenda-btn");
  if (editParticipantsBtn) editParticipantsBtn.style.display = isApproved ? "none" : "";
  if (editAgendaBtn) editAgendaBtn.style.display = isApproved ? "none" : "";
}

function renderParticipantsView(meeting) {
  const container = document.getElementById("participants-container");
  container.innerHTML = meeting.attendees.length
    ? `<ul style="color: var(--text-muted); padding-left: 1.2rem; margin: 0;">${meeting.attendees.map((a) => {
        const emailHtml = a.email ? ` <span class="text-muted">(${escapeHtml(a.email)})</span>` : "";
        return `<li>${escapeHtml(a.name)}${a.position ? " - " + escapeHtml(a.position) : ""}${emailHtml}</li>`;
      }).join("")}</ul>`
    : '<p class="text-muted">ไม่มีรายชื่อผู้เข้าร่วม</p>';
}

function renderAgendaView(meeting) {
  const container = document.getElementById("agenda-container");
  // agenda_items เป็น {label, description} ต่อรายการ (2026-08-07, ผู้ใช้ขอรองรับเลขวาระแบบ 3.1/3.2
  // — ดู backend's models.py MeetingAgendaItem.label) เดิมเป็น string ล้วน
  container.innerHTML = meeting.agenda_items.length
    ? `<ul style="color: var(--text-muted); padding-left: 1.2rem; margin: 0;">${meeting.agenda_items.map((item) => `<li><strong>${escapeHtml(item.label || "")}</strong> ${escapeHtml(item.description)}</li>`).join("")}</ul>`
    : '<p class="text-muted">ไม่มีวาระการประชุม</p>';
}

/** สร้าง 1 แถว input ของ attendee (ใช้ทั้งตอน render ครั้งแรกและตอนกด "+ เพิ่มผู้เข้าร่วม") — คืน
 * DOM element ที่ผูก listener ปุ่มลบให้เรียบร้อยแล้ว ไม่ต้องมา query ใหม่ทีหลัง */
function _buildAttendeeRow(a) {
  const row = document.createElement("div");
  row.className = "attendee-edit-row";
  row.style.cssText = "display: flex; gap: 0.4rem; margin-bottom: 0.4rem;";
  row.innerHTML = `
    <input type="text" class="attendee-name" placeholder="ชื่อ" value="${escapeHtml(a.name || "")}" style="flex: 2; min-width: 0;">
    <input type="text" class="attendee-position" placeholder="ตำแหน่ง" value="${escapeHtml(a.position || "")}" style="flex: 2; min-width: 0;">
    <input type="email" class="attendee-email" placeholder="อีเมล (ไม่บังคับ)" value="${escapeHtml(a.email || "")}" style="flex: 2; min-width: 0;">
    <button class="btn btn-secondary remove-row-btn" type="button" style="flex: 0 0 auto;">&times;</button>
  `;
  row.querySelector(".remove-row-btn").addEventListener("click", () => row.remove());
  return row;
}

/** แก้ไขรายชื่อผู้เข้าร่วมย้อนหลังได้ (2026-08-07, ผู้ใช้ขอ — เดิมกรอกได้แค่ตอนสร้างประชุมเท่านั้น) —
 * pattern เดียวกับ renderSpeakerMapping/renderTranscriptEditable ทุกประการ: สลับ container เป็น
 * input rows, กด Save ยิง PUT ทีเดียวทั้ง array (เขียนทับหมด ไม่ partial-update), กด Cancel
 * re-render จาก meeting object เดิมใน memory ไม่ยิง API */
function renderParticipantsEdit(meeting) {
  const container = document.getElementById("participants-container");
  container.innerHTML = `
    <div id="attendee-rows"></div>
    <button id="add-attendee-row" class="btn btn-secondary" type="button" style="font-size: 0.8rem; margin: 0.4rem 0;">+ เพิ่มผู้เข้าร่วม</button>
    <div class="flex-between">
      <button id="save-attendees-btn" class="btn btn-primary">Save</button>
      <button id="cancel-attendees-btn" class="btn btn-secondary">Cancel</button>
    </div>
    <p id="attendees-edit-error" class="text-muted" style="color: var(--status-failed); margin-bottom: 0;"></p>
  `;

  const rowsContainer = document.getElementById("attendee-rows");
  const initialRows = meeting.attendees.length ? meeting.attendees : [{ name: "", position: "", email: "" }];
  initialRows.forEach((a) => rowsContainer.appendChild(_buildAttendeeRow(a)));

  document.getElementById("add-attendee-row").addEventListener("click", () => {
    rowsContainer.appendChild(_buildAttendeeRow({ name: "", position: "", email: "" }));
  });

  document.getElementById("cancel-attendees-btn").addEventListener("click", () => {
    renderParticipantsView(meeting);
  });

  document.getElementById("save-attendees-btn").addEventListener("click", async () => {
    const btn = document.getElementById("save-attendees-btn");
    const errorBox = document.getElementById("attendees-edit-error");
    errorBox.textContent = "";
    // แถวที่ไม่กรอกชื่อเลยตัดทิ้งเงียบๆ (เช่น กด "+ เพิ่ม" ไว้เฉยๆแล้วไม่ได้กรอก) — position/email
    // ว่าง = null ตรงกับ AttendeeIn ฝั่ง backend (ไม่บังคับ)
    const attendees = [...rowsContainer.querySelectorAll(".attendee-edit-row")]
      .map((row) => ({
        name: row.querySelector(".attendee-name").value.trim(),
        position: row.querySelector(".attendee-position").value.trim() || null,
        email: row.querySelector(".attendee-email").value.trim() || null,
      }))
      .filter((a) => a.name);

    btn.disabled = true;
    btn.textContent = "กำลังบันทึก...";
    try {
      const updated = await apiFetch(`/api/meetings/${meeting.id}/attendees`, {
        method: "PUT",
        body: { attendees },
      });
      Object.assign(meeting, updated);
      renderParticipantsView(meeting);
      // Speaker Mapping panel ใช้ attendees เป็น autocomplete datalist (ดู renderSpeakerMapping) —
      // re-render ถ้ามี transcript แล้วกันชื่อใหม่ไม่โผล่ใน suggestion จนกว่าจะ refresh หน้าเอง
      if (meeting.transcript_segments && meeting.transcript_segments.length) {
        renderSpeakerMapping(meeting, document.getElementById("mapping-container"));
      }
    } catch (err) {
      errorBox.textContent = `บันทึกไม่สำเร็จ: ${err.message}`;
      btn.disabled = false;
      btn.textContent = "Save";
    }
  });
}

/** เลขวาระ (2026-08-07, ผู้ใช้ขอรองรับ 3.1/3.2/เลขข้ามได้ — ดู backend's
 * models.py MeetingAgendaItem.label docstring) — รับ {label, description} แทน string ล้วนแบบเดิม
 * label ปล่อยว่างได้ (backend เติม "วาระที่ N" ให้อัตโนมัติตอน save ถ้าไม่กรอก) */
function _buildAgendaRow(item) {
  const label = (item && item.label) || "";
  const description = (item && item.description) || "";
  const row = document.createElement("div");
  row.className = "agenda-edit-row";
  row.style.cssText = "display: flex; gap: 0.4rem; margin-bottom: 0.4rem;";
  row.innerHTML = `
    <input type="text" class="agenda-label" placeholder="เลขวาระ (ไม่บังคับ)" value="${escapeHtml(label)}" style="flex: 0 0 160px;">
    <input type="text" class="agenda-desc" placeholder="วาระการประชุม" value="${escapeHtml(description)}" style="flex: 1; min-width: 0;">
    <button class="btn btn-secondary remove-row-btn" type="button" style="flex: 0 0 auto;">&times;</button>
  `;
  row.querySelector(".remove-row-btn").addEventListener("click", () => row.remove());
  return row;
}

/** แก้ไขวาระการประชุมย้อนหลังได้ (2026-08-07, ผู้ใช้ขอ) — pattern เดียวกับ
 * renderParticipantsEdit() ด้านบนทุกประการ ลำดับ (order) คำนวณจาก index ตอน save เสมอ (ไม่ให้ผู้ใช้
 * ลากจัดลำดับเอง — ยังไม่ทำในรอบนี้ กันสโคปบาน) label เป็น free text แยกต่างหาก รองรับเลขวาระย่อย
 * แบบ 3.1/3.2 หรือเลขข้ามที่ไม่เรียงต่อเนื่องตามธรรมเนียมบอร์ดจริง */
function renderAgendaEdit(meeting) {
  const container = document.getElementById("agenda-container");
  container.innerHTML = `
    <div id="agenda-rows"></div>
    <button id="add-agenda-row" class="btn btn-secondary" type="button" style="font-size: 0.8rem; margin: 0.4rem 0;">+ เพิ่มวาระ</button>
    <div class="flex-between">
      <button id="save-agenda-btn" class="btn btn-primary">Save</button>
      <button id="cancel-agenda-btn" class="btn btn-secondary">Cancel</button>
    </div>
    <p id="agenda-edit-error" class="text-muted" style="color: var(--status-failed); margin-bottom: 0;"></p>
  `;

  const rowsContainer = document.getElementById("agenda-rows");
  const initialRows = meeting.agenda_items.length ? meeting.agenda_items : [{ label: "", description: "" }];
  initialRows.forEach((item) => rowsContainer.appendChild(_buildAgendaRow(item)));

  document.getElementById("add-agenda-row").addEventListener("click", () => {
    rowsContainer.appendChild(_buildAgendaRow({ label: "", description: "" }));
  });

  document.getElementById("cancel-agenda-btn").addEventListener("click", () => {
    renderAgendaView(meeting);
  });

  document.getElementById("save-agenda-btn").addEventListener("click", async () => {
    const btn = document.getElementById("save-agenda-btn");
    const errorBox = document.getElementById("agenda-edit-error");
    errorBox.textContent = "";
    const agenda_items = [...rowsContainer.querySelectorAll(".agenda-edit-row")]
      .map((row) => ({
        label: row.querySelector(".agenda-label").value.trim() || null,
        description: row.querySelector(".agenda-desc").value.trim(),
      }))
      .filter((a) => a.description); // แถวที่ไม่กรอก description ตัดทิ้งเงียบๆ เหมือน attendees

    btn.disabled = true;
    btn.textContent = "กำลังบันทึก...";
    try {
      const updated = await apiFetch(`/api/meetings/${meeting.id}/agenda_items`, {
        method: "PUT",
        body: { agenda_items },
      });
      Object.assign(meeting, updated);
      renderAgendaView(meeting);
    } catch (err) {
      errorBox.textContent = `บันทึกไม่สำเร็จ: ${err.message}`;
      btn.disabled = false;
      btn.textContent = "Save";
    }
  });
}

/** "2026-08-03T10:15:00" (UTC naive จาก datetime.utcnow().isoformat() ฝั่ง backend) → แสดงเป็น
 * local time ของเบราว์เซอร์ — ต้องเติม "Z" เองก่อนส่งให้ Date() ตีความ ไม่งั้น JS จะเข้าใจผิดว่าเป็น
 * local time อยู่แล้ว (เพี้ยนตาม timezone offset ของเครื่องผู้ใช้) */
function formatDateTime(isoString) {
  if (!isoString) return "-";
  const withZ = isoString.endsWith("Z") ? isoString : `${isoString}Z`;
  const d = new Date(withZ);
  if (Number.isNaN(d.getTime())) return isoString;
  return d.toLocaleString("en-GB", {
    day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit",
  });
}

/**
 * Minutes Panel (Module 3, ใหม่ — ไม่มีใน Stitch mockup เดิม) — ปุ่ม Generate ถูก disable ถ้า
 * speaker_mapping ยังไม่ครบ (ตัดสินใจจาก `/grill-me` รอบ 3: "Module 3 บล็อกถ้ายังจับคู่ไม่ครบ" —
 * backend เช็คซ้ำอีกชั้นอยู่แล้วที่ endpoint ฝั่งนี้แค่กันกดผิดจังหวะ ไม่ใช่ security boundary)
 */
function renderMinutesPanel(meeting) {
  const btn = document.getElementById("generate-minutes-btn");
  const container = document.getElementById("minutes-container");
  if (!btn || !container) return;

  btn.textContent = meeting.minutes ? "Regenerate Minutes" : "Generate Minutes";
  btn.disabled = !meeting.speaker_mapping_complete;
  btn.title = meeting.speaker_mapping_complete
    ? ""
    : "ต้องจับคู่ผู้พูด (Speaker Mapping) ให้ครบทุกคนก่อนสร้าง Minutes ได้";

  if (!meeting.minutes) {
    container.innerHTML = `
      <p class="text-muted">ยังไม่ได้สร้าง Minutes — กด "Generate Minutes" ด้านบน
        ${meeting.speaker_mapping_complete ? "" : "(ต้องจับคู่ผู้พูดให้ครบก่อน)"}</p>
      <p id="minutes-error" style="color: var(--status-failed);"></p>
    `;
    return;
  }

  const m = meeting.minutes;
  const agendaItemsHtml = m.agenda_items.map((item) => `
    <div class="minutes-agenda-item">
      <p>
        <strong>${escapeHtml(item.label || `วาระที่ ${item.agenda_order + 1}`)}: ${escapeHtml(item.description)}</strong>
        ${resolutionStatusBadgeHtml(item.resolution_status)}
      </p>
      <p class="text-muted">${escapeHtml(item.discussion_summary)}</p>
      <p><em>${escapeHtml(item.resolution_text)}</em></p>
    </div>
  `).join("");
  const otherBusinessHtml = (m.other_business_notes && m.other_business_notes !== "(ไม่มี)")
    ? `<p><strong>เรื่องอื่นๆ:</strong> ${escapeHtml(m.other_business_notes)}</p>`
    : "";

  container.innerHTML = `
    <p class="text-muted">สร้างล่าสุด: ${formatDateTime(meeting.minutes_generated_at)}
      (โมเดล: ${escapeHtml(m.generated_by_model || "-")})</p>
    <p><strong>ประธานในที่ประชุม:</strong> ${escapeHtml(m.chairperson_name)}</p>
    ${agendaItemsHtml}
    ${otherBusinessHtml}
    <p class="text-muted mt-4" style="border-top: 1px solid var(--secondary-cyan-deep); padding-top: 1rem;">
      ⚠️ เอกสารนี้เป็นร่างที่สร้างโดย AI จาก transcript ต้องผ่านการตรวจสอบและแก้ไขโดยเลขานุการบริษัท
      (Maker/Checker) ก่อนใช้จริงเสมอ
    </p>
    <p id="minutes-error" style="color: var(--status-failed);"></p>
  `;
}

/** map approval_status (Module 4-5) → badge — reuse badge-* class เดิม (ไม่เพิ่ม CSS ใหม่) */
const APPROVAL_STATUS_META = {
  Draft: { cls: "badge-draft", label: "Draft" },
  Pending_Review: { cls: "badge-processing", label: "Pending Review" },
  Needs_Revision: { cls: "badge-failed", label: "Needs Revision" },
  Approved: { cls: "badge-success", label: "Approved" },
};

function approvalStatusBadgeHtml(status) {
  const meta = APPROVAL_STATUS_META[status] || { cls: "badge-draft", label: status };
  return `<span class="badge ${meta.cls}">${meta.label}</span>`;
}

/** ดาวน์โหลดไฟล์จาก endpoint ที่ต้องแนบ Bearer token (ต่างจาก exportTranscriptText ที่สร้าง Blob
 * ฝั่ง client ล้วนๆ — ไฟล์นี้มาจาก server จริง ต้อง fetch ด้วย header เองแทนใช้ <a href> ตรงๆ เพราะ
 * browser's normal navigation ไม่แนบ Authorization header ให้) */
async function downloadAuthenticatedFile(path, filename) {
  const resp = await fetch(path, { headers: { Authorization: `Bearer ${getCurrentToken()}` } });
  if (!resp.ok) {
    let detail = `HTTP ${resp.status}`;
    try {
      const payload = await resp.json();
      detail = payload.detail || detail;
    } catch {
      // ไม่มี JSON body — ใช้ HTTP status เฉยๆ
    }
    throw new Error(detail);
  }
  const blob = await resp.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

/**
 * Documents & Approval Panel (Module 4-5, ใหม่ — ไม่มีใน Stitch mockup เดิม) — flow เต็ม:
 * Generate ร่าง .docx → ดาวน์โหลดไปแก้/เพิ่มตารางธุรกรรมด้วย Word เอง → อัปโหลดฉบับสมบูรณ์กลับ
 * (เข้า Pending_Review) → Checker Approve/Reject (ตีกลับต้องมี comment) → Approve แล้ว backend
 * จะสร้าง PDF+ส่ง Magic Link ให้อัตโนมัติเบื้องหลัง (ไม่มีอะไรให้กดเพิ่มในหน้านี้หลัง Approve)
 *
 * ไม่เช็ค role ฝั่ง client ก่อนแสดงปุ่ม (ต่างจากที่อาจคาดหวัง) — ตั้งใจให้เหมือนปุ่มอื่นๆที่มีอยู่แล้ว
 * ในหน้านี้ (Speaker Mapping/Generate Minutes) ที่ปล่อยให้ backend เป็นคนบังคับสิทธิ์จริง (403) แล้ว
 * โชว์ error message กลับมาเฉยๆ ถ้า role ไม่ตรง — ลดความซับซ้อนของ client, backend คือ source of
 * truth ของ RBAC อยู่แล้ว
 */
function renderDocumentsPanel(meeting) {
  const badge = document.getElementById("approval-status-badge");
  const container = document.getElementById("documents-container");
  if (!badge || !container) return;

  badge.innerHTML = approvalStatusBadgeHtml(meeting.approval_status);

  if (!meeting.minutes) {
    container.innerHTML = '<p class="text-muted">ต้องสร้าง Minutes ก่อน (panel ด้านบน) ถึงจะสร้างเอกสาร Word ได้</p>';
    return;
  }

  const canGenerateOrUpload = meeting.approval_status === "Draft" || meeting.approval_status === "Needs_Revision";

  const draftRowHtml = `
    <div class="flex-between mb-4">
      <button id="generate-docx-btn" class="btn btn-secondary" ${canGenerateOrUpload ? "" : "disabled"}>
        ${meeting.has_draft_docx ? "อัปเดตร่างเอกสาร Word" : "สร้างร่างเอกสาร Word"}
      </button>
      ${meeting.has_draft_docx ? '<button id="download-draft-btn" class="btn btn-secondary">ดาวน์โหลดร่าง (.docx)</button>' : ""}
    </div>
  `;

  const uploadFinalHtml = (meeting.has_draft_docx && canGenerateOrUpload) ? `
    <div class="form-group mb-4">
      <label>อัปโหลดฉบับสมบูรณ์ (หลังแก้/เพิ่มตารางธุรกรรมด้วย Word เองแล้ว)</label>
      <input type="file" id="upload-final-input" accept=".docx">
    </div>
  ` : "";

  const downloadFinalHtml = meeting.has_final_docx
    ? '<div class="mb-4"><button id="download-final-btn" class="btn btn-secondary">ดาวน์โหลดฉบับสมบูรณ์ (.docx)</button></div>'
    : "";

  const reviewHtml = meeting.approval_status === "Pending_Review" ? `
    <div class="form-group mb-4" style="border-top: 1px solid var(--secondary-cyan-deep); padding-top: 1rem;">
      <label>ความเห็น Checker (บังคับถ้ากด "ตีกลับ")</label>
      <textarea id="review-comment" rows="2" placeholder="เช่น กรุณาเพิ่มตารางรายละเอียดธุรกรรมในวาระที่ 2"></textarea>
      <div class="flex-between mt-4">
        <button id="reject-btn" class="btn btn-secondary" style="color: var(--status-failed); border-color: var(--status-failed);">ตีกลับ (Reject)</button>
        <button id="approve-btn" class="btn btn-primary">Approve</button>
      </div>
    </div>
  ` : "";

  const approvedHtml = meeting.approval_status === "Approved" ? `
    <p class="text-muted" style="border-top: 1px solid var(--secondary-cyan-deep); padding-top: 1rem;">
      ✓ อนุมัติแล้ว — ระบบกำลัง/ได้สร้าง PDF (ใส่รหัสผ่าน) และส่ง Magic Link ให้ผู้เข้าร่วมที่กรอก
      อีเมลไว้แล้วโดยอัตโนมัติเบื้องหลัง (ดูผลการส่งได้ที่ "ดูประวัติการอนุมัติ" ด้านล่าง)
    </p>
  ` : "";

  container.innerHTML = `
    ${draftRowHtml}
    ${uploadFinalHtml}
    ${downloadFinalHtml}
    ${reviewHtml}
    ${approvedHtml}
    <div class="mt-4">
      <button id="view-approval-log-btn" class="btn btn-secondary">ดูประวัติการอนุมัติ</button>
      <div id="approval-log-container" style="display: none; margin-top: 1rem;"></div>
    </div>
    <p id="documents-error" style="color: var(--status-failed);"></p>
  `;

  const errorBox = document.getElementById("documents-error");
  const setError = (msg) => { if (errorBox) errorBox.textContent = msg; };

  const generateBtn = document.getElementById("generate-docx-btn");
  if (generateBtn) {
    generateBtn.addEventListener("click", async () => {
      setError("");
      generateBtn.disabled = true;
      const originalText = generateBtn.textContent;
      generateBtn.textContent = "กำลังสร้าง...";
      try {
        const updated = await apiFetch(`/api/meetings/${meeting.id}/generate_docx`, { method: "POST" });
        Object.assign(meeting, updated);
        renderDocumentsPanel(meeting);
      } catch (err) {
        setError(`สร้างร่างเอกสารไม่สำเร็จ: ${err.message}`);
        generateBtn.disabled = false;
        generateBtn.textContent = originalText;
      }
    });
  }

  const downloadDraftBtn = document.getElementById("download-draft-btn");
  if (downloadDraftBtn) {
    downloadDraftBtn.addEventListener("click", async () => {
      setError("");
      try {
        await downloadAuthenticatedFile(
          `/api/meetings/${meeting.id}/download_docx?variant=draft`,
          `minutes_${meeting.meeting_number.replace(/[\/\\]/g, "-")}_draft.docx`,
        );
      } catch (err) {
        setError(`ดาวน์โหลดไม่สำเร็จ: ${err.message}`);
      }
    });
  }

  const downloadFinalBtn = document.getElementById("download-final-btn");
  if (downloadFinalBtn) {
    downloadFinalBtn.addEventListener("click", async () => {
      setError("");
      try {
        await downloadAuthenticatedFile(
          `/api/meetings/${meeting.id}/download_docx?variant=final`,
          `minutes_${meeting.meeting_number.replace(/[\/\\]/g, "-")}_final.docx`,
        );
      } catch (err) {
        setError(`ดาวน์โหลดไม่สำเร็จ: ${err.message}`);
      }
    });
  }

  const uploadFinalInput = document.getElementById("upload-final-input");
  if (uploadFinalInput) {
    uploadFinalInput.addEventListener("change", async () => {
      if (!uploadFinalInput.files || uploadFinalInput.files.length === 0) return;
      setError("");
      try {
        const form = new FormData();
        form.append("file", uploadFinalInput.files[0]);
        const updated = await apiFetch(`/api/meetings/${meeting.id}/upload_final_docx`, {
          method: "POST", body: form,
        });
        Object.assign(meeting, updated);
        renderDocumentsPanel(meeting);
      } catch (err) {
        setError(`อัปโหลดไม่สำเร็จ: ${err.message}`);
      }
    });
  }

  const approveBtn = document.getElementById("approve-btn");
  const rejectBtn = document.getElementById("reject-btn");
  const doReview = async (action) => {
    setError("");
    const comment = document.getElementById("review-comment").value.trim();
    if (action === "reject" && !comment) {
      setError("ต้องระบุเหตุผลที่ตีกลับก่อน");
      return;
    }
    [approveBtn, rejectBtn].forEach((b) => { if (b) b.disabled = true; });
    try {
      const updated = await apiFetch(`/api/meetings/${meeting.id}/review`, {
        method: "POST", body: { action, comment: comment || null },
      });
      Object.assign(meeting, updated);
      renderDocumentsPanel(meeting);
    } catch (err) {
      setError(`${action === "approve" ? "Approve" : "Reject"} ไม่สำเร็จ: ${err.message}`);
      [approveBtn, rejectBtn].forEach((b) => { if (b) b.disabled = false; });
    }
  };
  if (approveBtn) approveBtn.addEventListener("click", () => doReview("approve"));
  if (rejectBtn) rejectBtn.addEventListener("click", () => doReview("reject"));

  const viewLogBtn = document.getElementById("view-approval-log-btn");
  if (viewLogBtn) {
    viewLogBtn.addEventListener("click", async () => {
      const logContainer = document.getElementById("approval-log-container");
      const isHidden = logContainer.style.display === "none";
      if (!isHidden) {
        logContainer.style.display = "none";
        return;
      }
      logContainer.style.display = "";
      logContainer.innerHTML = '<p class="text-muted">กำลังโหลด...</p>';
      try {
        const entries = await apiFetch(`/api/meetings/${meeting.id}/approval_log`);
        logContainer.innerHTML = entries.length
          ? entries.map((e) => `
              <p class="text-muted">
                <strong>${escapeHtml(e.action)}</strong>
                (${escapeHtml(e.from_status)} → ${escapeHtml(e.to_status)}) โดย ${escapeHtml(e.user_id)}
                — ${formatDateTime(e.created_at)}
                ${e.comment ? `<br>ความเห็น: ${escapeHtml(e.comment)}` : ""}
              </p>
            `).join("")
          : '<p class="text-muted">ยังไม่มีประวัติ</p>';
      } catch (err) {
        logContainer.innerHTML = `<p style="color: var(--status-failed);">โหลดประวัติไม่สำเร็จ: ${escapeHtml(err.message)}</p>`;
      }
    });
  }
}

function renderMainContent(meeting) {
  const mainContent = document.getElementById("main-content-grid");
  const placeholder = document.getElementById("status-placeholder");
  const minutesPanel = document.getElementById("minutes-panel");
  const documentsPanel = document.getElementById("documents-panel");
  if (meeting.status === "transcribed") {
    // ต้องซ่อน placeholder เองด้วย เผื่อ transition มาจาก processing→transcribed ระหว่าง poll
    // (ไม่ใช่แค่ตอน initial load ที่ placeholder ซ่อนอยู่แล้วจาก inline style เริ่มต้นใน HTML)
    placeholder.style.display = "none";
    mainContent.style.display = "";
    if (minutesPanel) minutesPanel.style.display = "";
    if (documentsPanel) documentsPanel.style.display = "";
    renderSpeakerMapping(meeting, document.getElementById("mapping-container"));
    renderTranscript(meeting, document.getElementById("transcript-container"));
    renderTranscriptionModelUsed(meeting);
    renderMinutesPanel(meeting);
    renderDocumentsPanel(meeting);
  } else {
    // ยังไม่มี transcript ให้แสดง (uploaded/processing/failed/draft) — โชว์ placeholder แทนทุก
    // panel หลัก (รวม Minutes) ไม่ใช่ปล่อยว่างเปล่าเงียบๆ
    mainContent.style.display = "none";
    if (minutesPanel) minutesPanel.style.display = "none";
    if (documentsPanel) documentsPanel.style.display = "none";
    placeholder.style.display = "";
    if (meeting.status === "processing") {
      placeholder.textContent = "กำลังถอดเสียง+แยกผู้พูดอยู่ — หน้านี้จะอัปเดตอัตโนมัติเมื่อเสร็จ";
    } else if (meeting.status === "failed") {
      placeholder.textContent = `ประมวลผลไม่สำเร็จ: ${meeting.processing_error || "ไม่ทราบสาเหตุ"} — กลับไปหน้ารายการเพื่ออัปโหลดไฟล์ใหม่`;
    } else if (meeting.status === "uploaded") {
      placeholder.textContent = "อัปโหลดไฟล์แล้ว รอเริ่มประมวลผล...";
    } else {
      placeholder.textContent = "ยังไม่ได้อัปโหลดไฟล์เสียง — กลับไปหน้ารายการเพื่ออัปโหลด";
    }
  }
}

let _detailMeeting = null;
let _detailPollTimer = null;

async function loadMeetingDetail(meetingId) {
  const meeting = await apiFetch(`/api/meetings/${meetingId}`);
  _detailMeeting = meeting;
  renderMeetingSummary(meeting);
  renderMainContent(meeting);
  setupAudioPlayer(meeting); // async แต่ไม่ await — ไม่บล็อก render ส่วนอื่น, ตั้ง src เองเมื่อพร้อม
  const exportBtn = document.getElementById("export-transcript-btn");
  if (exportBtn) {
    // ปิดปุ่มไว้ก่อนถ้ายังไม่มี transcript ให้ export — กันกดแล้วไม่มีอะไรเกิดขึ้นแบบงงๆ
    exportBtn.disabled = !(meeting.transcript_segments && meeting.transcript_segments.length);
  }
  const reuploadBtn = document.getElementById("reupload-audio-btn");
  const reuploadModelSelect = document.getElementById("reupload-model-select");
  if (reuploadBtn) {
    // แสดงเฉพาะตอน transcribed/failed (มีผลลัพธ์ให้แทนที่แล้ว หรือประมวลผลพังต้องลองใหม่) — ซ่อนตอน
    // draft (ยังไม่มีไฟล์ ใช้ปุ่มปกติจากหน้า dashboard แทน)/uploaded/processing (มีงานค้างอยู่แล้ว
    // กันกดซ้อนจนสับสนว่า process ไหนคือของจริง)
    const showReupload = meeting.status === "transcribed" || meeting.status === "failed";
    reuploadBtn.style.display = showReupload ? "" : "none";
    // เลือกโมเดลเอง (2026-08-05) — แสดง/ซ่อนพร้อมปุ่ม reupload เสมอ, populate ครั้งเดียวพอ (เช็ค
    // .innerHTML ว่างก่อน กัน re-fetch ทุกครั้งที่ loadMeetingDetail() รันซ้ำระหว่าง poll)
    if (reuploadModelSelect) {
      reuploadModelSelect.style.display = showReupload ? "" : "none";
      if (showReupload && !reuploadModelSelect.innerHTML) {
        getModelOptionsHtml().then((html) => { reuploadModelSelect.innerHTML = html; });
      }
    }
  }
  return meeting;
}

/** แยกออกมาจาก initMeetingDetailPage() (2026-08-03) เพื่อให้ triggerReuploadOnDetailPage() เรียก
 * ซ้ำได้หลัง re-upload สำเร็จ — timer เดิมถูก clearInterval ไปแล้วตั้งแต่รอบแรกที่ transcribed
 * (ดู callback ด้านใน) ต้องเริ่มใหม่เองไม่งั้นหน้าจะไม่ auto-update ตอน reprocess เสร็จรอบที่ 2 */
function startDetailPolling(meetingId) {
  if (_detailPollTimer) clearInterval(_detailPollTimer); // กันมี timer ซ้อนกันถ้าเผลอเรียก 2 ครั้ง
  _detailPollTimer = setInterval(async () => {
    if (_detailMeeting && _detailMeeting.status !== "processing" && _detailMeeting.status !== "uploaded") {
      clearInterval(_detailPollTimer);
      return;
    }
    try {
      await loadMeetingDetail(meetingId);
    } catch {
      // เงียบไว้ระหว่าง poll — error หลักแสดงไปแล้วตอน initial load
    }
  }, 5000);
}

/**
 * Re-upload/reprocess ไฟล์เสียงจากหน้า meeting-detail ตรงๆ (ใหม่ 2026-08-03) — เดิมทำได้แค่จาก
 * dashboard's actionCellHtml() ตอน status="failed" เท่านั้น ไม่มีทางแก้ไฟล์/reprocess ซ้ำได้เลย
 * หลัง transcribed แล้ว (เช่น อยากลองรัน diarization ใหม่หลังปรับ hyperparameter) — ใช้ pattern
 * เดียวกับ triggerUpload() แต่ callback ต่างกัน: ต้อง reload meeting-detail + restart polling
 * ไม่ใช่ loadMeetings() ของหน้า dashboard ที่ element ไม่มีอยู่ในหน้านี้
 */
function triggerReuploadOnDetailPage(meetingId, btn) {
  const input = document.createElement("input");
  input.type = "file";
  input.accept = "audio/*,video/*";
  input.style.display = "none";
  document.body.appendChild(input);

  input.onchange = async () => {
    if (!input.files || input.files.length === 0) {
      input.remove();
      return;
    }
    const originalText = btn.textContent;
    btn.disabled = true;
    btn.textContent = "กำลังอัปโหลด...";
    try {
      const form = new FormData();
      form.append("file", input.files[0]);
      // เลือกโมเดลเอง (2026-08-05) — ดู meeting-detail.html's #reupload-model-select
      const modelSelect = document.getElementById("reupload-model-select");
      if (modelSelect && modelSelect.value) form.append("model", modelSelect.value);
      await apiFetch(`/api/meetings/${meetingId}/upload`, { method: "POST", body: form });
      // โหลดสถานะใหม่ทันที (จะเห็น "uploaded" ก่อน background task ประมวลผลเสร็จด้วยซ้ำ — ตรงกับ
      // ที่ renderMainContent ซ่อน panel หลักทั้งหมดรอจนกว่าจะ transcribed ใหม่) แล้วเริ่ม poll ใหม่
      await loadMeetingDetail(meetingId);
      startDetailPolling(meetingId);
    } catch (err) {
      alert(`อัปโหลดไม่สำเร็จ: ${err.message}`);
    } finally {
      btn.disabled = false;
      btn.textContent = originalText;
      input.remove();
    }
  };
  input.click();
}

function initMeetingDetailPage() {
  const titleEl = document.getElementById("meeting-title");
  if (!titleEl) return; // ไม่ใช่หน้านี้

  const meetingId = getMeetingIdFromUrl();
  if (!meetingId) {
    titleEl.textContent = "ไม่พบการประชุมที่ระบุ (ไม่มี ?id= ใน URL)";
    return;
  }

  loadMeetingDetail(meetingId).catch((err) => {
    titleEl.textContent = `โหลดข้อมูลไม่สำเร็จ: ${err.message}`;
  });

  // Audio Playback Sync — ผูก listener ครั้งเดียวตอนโหลดหน้า (ไม่ใช่ทุกครั้งที่ renderTranscript
  // เขียนทับ #transcript-container's innerHTML ใหม่) "timeupdate" ผูกกับ <audio> element ตรงๆ (ตัว
  // element เองไม่เคยถูกสร้างใหม่ มีแค่ src ที่เปลี่ยน) ส่วน click ผูกกับ container (ยังอยู่ตัวเดิม
  // เสมอ แค่ innerHTML ข้างในเปลี่ยน) ใช้ event delegation อ่าน .transcript-line ที่ถูกคลิกจาก
  // e.target.closest() กันต้อง re-bind listener ทุกครั้งที่ transcript re-render
  const audioPlayerEl = document.getElementById("meeting-audio-player");
  if (audioPlayerEl) {
    audioPlayerEl.addEventListener("timeupdate", () => {
      highlightActiveTranscriptSegment(audioPlayerEl.currentTime);
    });
  }
  const transcriptContainerEl = document.getElementById("transcript-container");
  if (transcriptContainerEl) {
    transcriptContainerEl.addEventListener("click", (e) => {
      const line = e.target.closest(".transcript-line[data-start]");
      if (!line || !audioPlayerEl || !audioPlayerEl.src) return;
      audioPlayerEl.currentTime = parseFloat(line.dataset.start);
      audioPlayerEl.play().catch(() => {
        // autoplay อาจโดน browser policy บล็อกถ้ายังไม่เคย interact กับ <audio> นี้เลย — เงียบไว้
        // ผู้ใช้กดปุ่ม play ของ controls เองต่อได้ปกติ (currentTime ถูกตั้งไปแล้ว)
      });
    });
  }

  const exportBtn = document.getElementById("export-transcript-btn");
  if (exportBtn) {
    // บั๊กที่พบ (2026-08-03, ผู้ใช้รายงาน): กด Export แล้วได้ transcript คนละอันกับที่หน้าจอโชว์อยู่
    // ตอนนั้น (เช่น mapping panel บอก 15 speaker แต่ export ออกมาแค่ 2) — สาเหตุคือ exportBtn เดิม
    // ใช้ตัวแปร `_detailMeeting` ที่ค้างอยู่ใน memory ตรงๆ โดยไม่ fetch ใหม่ก่อน ถ้า tab นี้เปิดค้างไว้
    // ตั้งแต่ก่อน reprocess รอบล่าสุด (หรือ reprocess ผ่าน tab/session อื่น) `_detailMeeting` จะไม่มี
    // ทางอัปเดตเอง เพราะ startDetailPolling() หยุด poll ทันทีที่ status เป็น "transcribed" แล้ว (ดู
    // comment ของฟังก์ชันนั้น) — แก้โดยให้ Export fetch ข้อมูลล่าสุดจาก backend ก่อนสร้างไฟล์เสมอ
    // แทนที่จะเชื่อ state ใน memory เฉยๆ (กันปัญหาข้อมูลเก่าค้างได้ทุกกรณี ไม่ใช่แค่กรณี stale tab)
    exportBtn.addEventListener("click", async () => {
      const originalLabel = exportBtn.textContent;
      exportBtn.disabled = true;
      exportBtn.textContent = "กำลังโหลดข้อมูลล่าสุด...";
      try {
        const freshMeeting = await loadMeetingDetail(meetingId);
        if (freshMeeting && freshMeeting.transcript_segments && freshMeeting.transcript_segments.length) {
          exportTranscriptText(freshMeeting);
        }
      } catch (err) {
        alert(`โหลดข้อมูลล่าสุดไม่สำเร็จ ไม่ export: ${err.message}`);
      } finally {
        exportBtn.disabled = false;
        exportBtn.textContent = originalLabel;
      }
    });
  }

  const editBtn = document.getElementById("edit-transcript-btn");
  if (editBtn) {
    editBtn.addEventListener("click", () => {
      if (!_detailMeeting || !_detailMeeting.transcript_segments || !_detailMeeting.transcript_segments.length) return;
      editBtn.style.display = "none"; // exitTranscriptEditMode คืนค่าให้ตอน Save/Cancel
      renderTranscriptEditable(_detailMeeting, document.getElementById("transcript-container"));
    });
  }

  const reuploadBtn = document.getElementById("reupload-audio-btn");
  if (reuploadBtn) {
    reuploadBtn.addEventListener("click", () => triggerReuploadOnDetailPage(meetingId, reuploadBtn));
  }

  // แก้ไข Participants/Agenda ย้อนหลัง (2026-08-07, ผู้ใช้ขอ) — pattern เดียวกับ edit-transcript-btn
  // ด้านบน: อ่านจาก _detailMeeting ที่โหลดล่าสุดเสมอ ไม่ผูกกับ closure ตอน initial load
  const editParticipantsBtn = document.getElementById("edit-participants-btn");
  if (editParticipantsBtn) {
    editParticipantsBtn.addEventListener("click", () => {
      if (!_detailMeeting) return;
      renderParticipantsEdit(_detailMeeting);
    });
  }

  const editAgendaBtn = document.getElementById("edit-agenda-btn");
  if (editAgendaBtn) {
    editAgendaBtn.addEventListener("click", () => {
      if (!_detailMeeting) return;
      renderAgendaEdit(_detailMeeting);
    });
  }

  // Module 3: Generate Minutes — เรียก Gemini ฝั่ง backend อาจใช้เวลาสักครู่ (ไม่ทราบตัวเลขจริง
  // ยังไม่เคย live test — ดู handoff.md) แสดง label บนปุ่มระหว่างรอ กันผู้ใช้กดซ้ำ/คิดว่าค้าง
  const generateMinutesBtn = document.getElementById("generate-minutes-btn");
  if (generateMinutesBtn) {
    generateMinutesBtn.addEventListener("click", async () => {
      const originalText = generateMinutesBtn.textContent;
      generateMinutesBtn.disabled = true;
      generateMinutesBtn.textContent = "กำลังสร้าง Minutes... (อาจใช้เวลาสักครู่)";
      const errorBox = document.getElementById("minutes-error");
      if (errorBox) errorBox.textContent = "";
      try {
        const updated = await apiFetch(`/api/meetings/${meetingId}/generate_minutes`, { method: "POST" });
        Object.assign(_detailMeeting, updated);
        renderMinutesPanel(_detailMeeting); // re-render ทับ error box เดิม + คืนปุ่มให้ถูก label
      } catch (err) {
        generateMinutesBtn.disabled = false;
        generateMinutesBtn.textContent = originalText;
        const box = document.getElementById("minutes-error");
        if (box) box.textContent = `สร้าง Minutes ไม่สำเร็จ: ${err.message}`;
      }
    });
  }

  // poll เฉพาะตอนยังไม่ transcribed (รอผลประมวลผล) — หยุด poll ทันทีที่ transcribed แล้ว กัน
  // เขียนทับ input ที่ผู้ใช้กำลังพิมพ์ในฟอร์ม Speaker Mapping อยู่ (ต่างจาก dashboard ที่ poll
  // ตลอดได้เพราะไม่มี input ค้าง) — แยกเป็น startDetailPolling() เพื่อให้ re-upload เรียกซ้ำได้
  startDetailPolling(meetingId);
}

// ─────────────────────────────────────────────────────────────────────────
// search.html — Policy & Board Document Search (Module 1 RAG, ใหม่ 2026-08-04) — mockup มาจาก
// Google Stitch (ดู stitch_brief_rag_search.md) ตัดสิ่งที่ไม่ได้ผูกกับฟีเจอร์จริงออก (sidebar เดิมมี
// nav "Confidential Vault"/"Templates"/"Help Center"/"Logout"/notifications/settings/avatar —
// ไม่มีหน้า/backend รองรับสักอย่าง เป็น dead link ทั้งหมด ตัดออกแทนที่จะปล่อยให้กดแล้วไม่มีอะไรเกิดขึ้น)
// เหลือแค่ role-select (ผูกกับ .role-select เดิม), scope selector (sync 2 ชุด: pill บนสุด +
// sidebar link), New Search (reset ในหน่วยความจำ ไม่มี persist), และ Q&A จริงที่ผูกกับ
// POST /api/rag/query / /api/rag/query_confidential
// ─────────────────────────────────────────────────────────────────────────

let _searchScope = "general"; // "general" | "confidential" — ตรงกับ search_scope ฝั่ง backend/rag.py
let _searchBusy = false; // กันยิงซ้ำระหว่างรอคำตอบ (query อาจใช้เวลาถึงหลายนาที ไม่ใช่ 2-3 วิ)
let _searchElapsedTimer = null;
let _searchMeetingOptionsLoaded = false; // โหลด dropdown รายชื่อการประชุมแค่ครั้งแรกที่สลับมา confidential (ไม่โหลดซ้ำทุกครั้ง)

/** อัปเดต active state ของ scope control ทั้ง 2 ชุด (pill กลางจอ ใช้ได้ทั้ง mobile/desktop, sidebar
 * link ใช้ได้เฉพาะ desktop ที่ sidebar โชว์) ให้ตรงกับ _searchScope เสมอ — เขียนแยก class ของ pill/nav
 * เพราะ Stitch ออกแบบ active state ของ 2 แบบนี้ไม่เหมือนกัน (nav link ใช้พื้นหลังทึบ, pill ใช้แค่สี
 * ตัวอักษร+พื้นหลังอ่อนกว่า) */
function updateScopeUI() {
  const pillGeneral = document.getElementById("scope-pill-general");
  const pillConfidential = document.getElementById("scope-pill-confidential");
  const navGeneral = document.getElementById("scope-nav-general");
  const navConfidential = document.getElementById("scope-nav-confidential");

  [pillGeneral, pillConfidential].forEach((el) => {
    if (!el) return;
    el.classList.remove("bg-secondary-container", "text-primary", "shadow-sm", "text-on-surface-variant");
  });
  const activePill = _searchScope === "general" ? pillGeneral : pillConfidential;
  const inactivePill = _searchScope === "general" ? pillConfidential : pillGeneral;
  if (activePill) activePill.classList.add("bg-secondary-container", "text-primary", "shadow-sm");
  if (inactivePill) inactivePill.classList.add("text-on-surface-variant");

  [navGeneral, navConfidential].forEach((el) => {
    if (!el) return;
    el.classList.remove("bg-secondary-container", "text-primary", "shadow-sm", "text-on-surface-variant");
  });
  const activeNav = _searchScope === "general" ? navGeneral : navConfidential;
  const inactiveNav = _searchScope === "general" ? navConfidential : navGeneral;
  if (activeNav) activeNav.classList.add("bg-secondary-container", "text-primary", "shadow-sm");
  if (inactiveNav) inactiveNav.classList.add("text-on-surface-variant");
}

/** โชว์/ซ่อน dropdown เลือกการประชุม — เฉพาะ scope="confidential" เท่านั้น (scope="general" ไม่มี
 * concept "การประชุม" เลย) โหลดตัวเลือกครั้งแรกที่สลับมา confidential เท่านั้น (ไม่โหลดซ้ำทุกครั้ง
 * ที่สลับ scope ไปมา — รายชื่อการประชุมที่ approve แล้วไม่ได้เปลี่ยนบ่อยระหว่างอยู่หน้านี้) */
function updateMeetingFilterVisibility() {
  const wrap = document.getElementById("search-meeting-filter-wrap");
  if (!wrap) return;
  wrap.style.display = _searchScope === "confidential" ? "" : "none";
  if (_searchScope === "confidential" && !_searchMeetingOptionsLoaded) {
    loadConfidentialMeetingOptions();
  }
}

/** ดึงรายชื่อการประชุมที่ Approve แล้ว (มีเอกสารลับ index ไว้จริง — ดู
 * backend/main.py's _archive_and_notify_background) มาใส่ dropdown ให้เลือก filter — กรองฝั่ง
 * client เอา (ไม่มี backend endpoint แยกสำหรับ "Approved only" ยังไม่คุ้มเพิ่ม endpoint ใหม่แค่นี้
 * GET /api/meetings คืนทุกการประชุมอยู่แล้ว) ล้มเหลวก็แค่ dropdown เหลือแค่ "ทุกการประชุม" เหมือนเดิม
 * ไม่ block การใช้งานหน้านี้ */
async function loadConfidentialMeetingOptions() {
  const select = document.getElementById("search-meeting-select");
  if (!select) return;
  _searchMeetingOptionsLoaded = true; // ตั้งก่อนเรียกเสมอ กัน retry ถี่ๆ ถ้า fail (ผู้ใช้ refresh เองได้)
  try {
    const meetings = await apiFetch("/api/meetings");
    const approved = (meetings || []).filter((m) => m.approval_status === "Approved");
    approved.forEach((m) => {
      const opt = document.createElement("option");
      opt.value = m.id;
      opt.textContent = `${m.meeting_number} (${formatDate(m.meeting_date)})`;
      select.appendChild(opt);
    });
  } catch {
    // เงียบไว้ — dropdown เหลือแค่ "ทุกการประชุม" ผู้ใช้ยังค้นหาแบบเดิมได้ปกติ
  }
}

function setSearchScope(scope) {
  _searchScope = scope;
  updateScopeUI();
  updateMeetingFilterVisibility();
}

function appendSearchUserBubble(query) {
  const area = document.getElementById("search-conversation");
  const emptyState = document.getElementById("search-empty-state");
  if (emptyState) emptyState.style.display = "none";

  const userDiv = document.createElement("div");
  userDiv.className = "flex justify-end";
  userDiv.innerHTML = `
    <div class="max-w-[85%] md:max-w-[75%] bg-[#1C3936] rounded-2xl rounded-tr-sm px-5 py-4 border border-secondary/10 shadow-sm">
      <p class="font-body-lg text-body-lg text-on-surface">${escapeHtml(query)}</p>
    </div>`;
  area.insertBefore(userDiv, document.getElementById("search-loading"));
  area.scrollTop = area.scrollHeight;
}

/** ต่อท้าย AI bubble — resultOrErrorMessage คือ dict `{response, sources, tokens}` จาก backend ตอน
 * สำเร็จ (โครงตรงกับ rag_worker/worker_handlers.py's _handle_chat) หรือ string ข้อความ error ตอน
 * ล้มเหลว (isError=true, ข้อความมาจาก apiFetch's err.message ซึ่งดึงจาก backend's `detail` field) */
function appendSearchAiBubble(resultOrErrorMessage, isError) {
  const area = document.getElementById("search-conversation");
  const loadingEl = document.getElementById("search-loading");
  const aiDiv = document.createElement("div");
  aiDiv.className = "flex justify-start";

  if (isError) {
    aiDiv.innerHTML = `
      <div class="bg-error-container/20 border border-error/30 rounded-lg px-4 py-3 flex items-start gap-3 text-error max-w-[95%] md:max-w-[85%]">
        <span class="material-symbols-outlined text-[20px] mt-0.5">error</span>
        <div class="font-label-md text-label-md">
          <strong class="block mb-1">ค้นหาไม่สำเร็จ</strong>
          <p class="text-error/80 text-sm">${escapeHtml(resultOrErrorMessage)}</p>
        </div>
      </div>`;
    area.insertBefore(aiDiv, loadingEl);
    area.scrollTop = area.scrollHeight;
    return;
  }

  const answerText = resultOrErrorMessage.response || "";
  // ตัดย่อหน้าจาก \n\n (backend คืน plain text ไม่ใช่ markdown/HTML) — escapeHtml ทุกย่อหน้าเสมอ
  // กัน prompt injection ที่หลุดมาจากคำตอบ AI render เป็น HTML จริงในหน้าเว็บ
  const paragraphsHtml = answerText
    .split(/\n{2,}/)
    .map((p) => `<p>${escapeHtml(p)}</p>`)
    .join("");
  const sources = resultOrErrorMessage.sources || [];
  const sourcesHtml = sources.length ? `
      <div class="mt-2">
        <h4 class="font-label-md text-label-md text-on-surface-variant/70 mb-3 flex items-center gap-2 uppercase tracking-wider text-xs">
          <span class="material-symbols-outlined text-[14px]">find_in_page</span>
          Sources
        </h4>
        <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
          ${sources.map((s) => `
            <div class="bg-[#1C3936] border border-secondary/15 rounded-lg p-3 flex flex-col gap-2">
              <div class="flex items-center gap-2 overflow-hidden">
                <span class="material-symbols-outlined text-secondary text-[18px] shrink-0">description</span>
                <span class="font-label-md text-label-md text-on-surface truncate font-medium">${escapeHtml(s.file_name || "Unknown")}</span>
              </div>
              <p class="text-xs text-on-surface-variant line-clamp-2 leading-snug">${escapeHtml(s.content || "")}</p>
            </div>
          `).join("")}
        </div>
      </div>` : "";

  aiDiv.innerHTML = `
    <div class="max-w-[95%] md:max-w-[85%] bg-transparent flex gap-4">
      <div class="w-8 h-8 rounded-full bg-primary-container flex items-center justify-center shrink-0 mt-1 shadow-sm">
        <span class="material-symbols-outlined text-on-primary-container text-[18px]">smart_toy</span>
      </div>
      <div class="flex flex-col gap-4">
        <div class="prose prose-invert max-w-none font-body-lg text-body-lg text-on-surface-variant leading-relaxed">${paragraphsHtml}</div>
        ${sourcesHtml}
        <div class="flex items-center gap-3 mt-1">
          <button class="copy-answer-btn text-on-surface-variant hover:text-primary transition-colors p-1" title="Copy to clipboard" type="button">
            <span class="material-symbols-outlined text-[18px]">content_copy</span>
          </button>
        </div>
      </div>
    </div>`;
  area.insertBefore(aiDiv, loadingEl);

  // ผูก copy หลังต่อเข้า DOM แล้ว (ใช้ closure จับ answerText ตรงๆ แทนการยัดข้อความลง data-attribute
  // แล้วอ่านกลับ — กัน escape/unescape ผิดรอบ)
  const copyBtn = aiDiv.querySelector(".copy-answer-btn");
  if (copyBtn) {
    copyBtn.addEventListener("click", () => {
      navigator.clipboard.writeText(answerText).catch(() => {
        // เบราว์เซอร์บล็อก clipboard API (เช่นไม่ใช่ HTTPS/localhost) — ไม่มี fallback ให้ผู้ใช้เอง
        // copy จากหน้าจอตรงๆ
      });
    });
  }

  area.scrollTop = area.scrollHeight;
}

/** โชว์ loading indicator ที่มีอยู่แล้วใน DOM ตัวเดียว (ไม่ clone) — ย้ายไปต่อท้ายบทสนทนาเสมอก่อน
 * แสดง เริ่มนับเวลาที่ผ่านไปด้วย เพราะ query นี้ตอบช้าผิดปกติได้ (ดูคำเตือนใน backend/rag.py) ผู้ใช้
 * ต้องรู้ว่ายังไม่ค้าง ไม่ใช่แค่เห็น spinner เฉยๆ */
function showSearchLoading() {
  const el = document.getElementById("search-loading");
  const area = document.getElementById("search-conversation");
  if (!el || !area) return;
  area.appendChild(el); // ย้าย node เดิม (ไม่ใช่ clone) ไปต่อท้ายสุด
  el.style.display = "";
  area.scrollTop = area.scrollHeight;

  let seconds = 0;
  const label = document.getElementById("search-elapsed");
  if (label) label.textContent = "";
  _searchElapsedTimer = setInterval(() => {
    seconds += 1;
    if (label) label.textContent = ` (${seconds}s)`;
  }, 1000);
}

function hideSearchLoading() {
  const el = document.getElementById("search-loading");
  if (el) el.style.display = "none";
  if (_searchElapsedTimer) {
    clearInterval(_searchElapsedTimer);
    _searchElapsedTimer = null;
  }
}

/** "New Search" — ล้างบทสนทนาในหน่วยความจำ/DOM เท่านั้น (ไม่มี backend session ให้ล้างจริง — ทุก
 * query ที่ยิงไปแล้วจบไปแล้ว ไม่มี state ค้างฝั่ง server ให้ต้องเคลียร์คู่กัน) */
function resetSearchConversation() {
  const area = document.getElementById("search-conversation");
  if (!area) return;
  Array.from(area.children).forEach((child) => {
    if (child.id !== "search-empty-state" && child.id !== "search-loading") child.remove();
  });
  const emptyState = document.getElementById("search-empty-state");
  if (emptyState) emptyState.style.display = "";
  const input = document.getElementById("search-input");
  if (input) input.value = "";
}

async function submitSearchQuery() {
  if (_searchBusy) return;
  const input = document.getElementById("search-input");
  const submitBtn = document.getElementById("search-submit-btn");
  if (!input) return;
  const query = (input.value || "").trim();
  if (!query) return;

  input.value = "";
  appendSearchUserBubble(query);
  _searchBusy = true;
  if (submitBtn) submitBtn.disabled = true;
  input.disabled = true;
  showSearchLoading();

  const endpoint = _searchScope === "confidential" ? "/api/rag/query_confidential" : "/api/rag/query";
  const body = { query };
  if (_searchScope === "confidential") {
    const meetingSelect = document.getElementById("search-meeting-select");
    const selected = meetingSelect ? meetingSelect.value : "";
    if (selected) body.meeting_id = selected; // "" (ทุกการประชุม) = ไม่ส่ง field นี้เลย ค้นหาทุกเอกสาร
  }
  try {
    const result = await apiFetch(endpoint, { method: "POST", body });
    hideSearchLoading();
    appendSearchAiBubble(result, false);
  } catch (err) {
    hideSearchLoading();
    appendSearchAiBubble(err.message, true);
  } finally {
    _searchBusy = false;
    if (submitBtn) submitBtn.disabled = false;
    input.disabled = false;
    input.focus();
  }
}

function initSearchPage() {
  const area = document.getElementById("search-conversation");
  if (!area) return; // ไม่ใช่หน้านี้

  updateScopeUI();
  updateMeetingFilterVisibility();

  document.querySelectorAll("[data-scope]").forEach((el) => {
    el.addEventListener("click", (e) => {
      e.preventDefault();
      setSearchScope(el.dataset.scope);
    });
  });

  const submitBtn = document.getElementById("search-submit-btn");
  if (submitBtn) submitBtn.addEventListener("click", submitSearchQuery);

  const input = document.getElementById("search-input");
  if (input) {
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
        e.preventDefault();
        submitSearchQuery();
      }
    });
  }

  const newSearchBtn = document.getElementById("new-search-btn");
  if (newSearchBtn) newSearchBtn.addEventListener("click", resetSearchConversation);
}

// ─────────────────────────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
  initRoleSelect();
  initDashboardPage();
  initCreateMeetingPage();
  initMeetingDetailPage();
  initSearchPage();
});
