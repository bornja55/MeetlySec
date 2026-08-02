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

/** ผูก <select class="role-select"> ในแต่ละหน้าเข้ากับ localStorage — เรียกครั้งเดียวตอนโหลดหน้า */
function initRoleSelect() {
  const select = document.querySelector(".role-select");
  if (!select) return;
  select.value = getCurrentRole();
  select.addEventListener("change", () => {
    localStorage.setItem(ROLE_STORAGE_KEY, select.value);
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

function actionCellHtml(meeting) {
  // draft: ยังไม่มีไฟล์เสียง → ปุ่มอัปโหลดอย่างเดียว (ไม่มีอะไรให้ดูใน detail page)
  // failed: อัปโหลดไปแล้วแต่ประมวลผลพัง → ปุ่ม re-upload (โชว์ processing_error เป็น title
  // tooltip กันต้องเปิดหน้าอื่นแค่เพื่อดู error สั้นๆ)
  // uploaded/processing/transcribed: มีอะไรให้ดูแล้ว → View ไปหน้า detail
  if (meeting.status === "draft") {
    return `<button class="btn btn-secondary upload-btn" data-id="${meeting.id}">Upload Audio</button>`;
  }
  if (meeting.status === "failed") {
    const title = meeting.processing_error ? ` title="${escapeHtml(meeting.processing_error)}"` : "";
    return `<button class="btn btn-secondary upload-btn" data-id="${meeting.id}"${title}>Re-upload</button>`;
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
    <input type="text" class="agenda-item" placeholder="Agenda item" style="flex: 1;">
    <button type="button" class="btn btn-secondary remove-row-btn" style="color: var(--status-failed); border-color: var(--status-failed);">Remove</button>
  `;
  container.appendChild(row);
}

function initCreateMeetingPage() {
  const form = document.getElementById("create-meeting-form");
  if (!form) return; // ไม่ใช่หน้านี้

  const participantsContainer = document.getElementById("participants-container");
  const agendaContainer = document.getElementById("agenda-container");

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

    const attendees = Array.from(participantsContainer.querySelectorAll(".participant-row"))
      .map((row) => ({
        name: row.querySelector(".participant-name").value.trim(),
        position: row.querySelector(".participant-position").value.trim() || null,
      }))
      .filter((a) => a.name);

    const agendaItems = Array.from(agendaContainer.querySelectorAll(".agenda-item"))
      .map((input) => input.value.trim())
      .filter((text) => text);

    const submitBtn = form.querySelector('button[type="submit"]');
    submitBtn.disabled = true;
    try {
      await apiFetch("/api/meetings", {
        method: "POST",
        body: { meeting_number: meetingNumber, meeting_date: meetingDate, attendees, agenda_items: agendaItems },
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

function renderTranscript(meeting, container) {
  const segments = meeting.transcript_segments || [];
  if (segments.length === 0) {
    container.innerHTML = '<p class="text-muted">ยังไม่มี transcript</p>';
    return;
  }
  container.innerHTML = segments.map((seg) => `
      <div class="transcript-line">
        <span class="speaker-name">${speakerDisplayName(meeting, seg.speaker)}</span>
        <span class="speaker-time">${formatSeconds(seg.start)}</span>
        <p>${escapeHtml(seg.text)}</p>
      </div>
    `).join("");
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

  const participantsList = document.getElementById("participants-list");
  participantsList.innerHTML = meeting.attendees.length
    ? meeting.attendees.map((a) => `<li>${escapeHtml(a.name)}${a.position ? " - " + escapeHtml(a.position) : ""}</li>`).join("")
    : '<li class="text-muted">ไม่มีรายชื่อผู้เข้าร่วม</li>';

  const agendaList = document.getElementById("agenda-list");
  agendaList.innerHTML = meeting.agenda_items.length
    ? meeting.agenda_items.map((item) => `<li>${escapeHtml(item)}</li>`).join("")
    : '<li class="text-muted">ไม่มีวาระการประชุม</li>';
}

function renderMainContent(meeting) {
  const mainContent = document.getElementById("main-content-grid");
  const placeholder = document.getElementById("status-placeholder");
  if (meeting.status === "transcribed") {
    // ต้องซ่อน placeholder เองด้วย เผื่อ transition มาจาก processing→transcribed ระหว่าง poll
    // (ไม่ใช่แค่ตอน initial load ที่ placeholder ซ่อนอยู่แล้วจาก inline style เริ่มต้นใน HTML)
    placeholder.style.display = "none";
    mainContent.style.display = "";
    renderSpeakerMapping(meeting, document.getElementById("mapping-container"));
    renderTranscript(meeting, document.getElementById("transcript-container"));
  } else {
    // ยังไม่มี transcript ให้แสดง (uploaded/processing/failed/draft) — โชว์ placeholder แทน 2
    // panel หลัก ไม่ใช่ปล่อยว่างเปล่าเงียบๆ
    mainContent.style.display = "none";
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
  const exportBtn = document.getElementById("export-transcript-btn");
  if (exportBtn) {
    // ปิดปุ่มไว้ก่อนถ้ายังไม่มี transcript ให้ export — กันกดแล้วไม่มีอะไรเกิดขึ้นแบบงงๆ
    exportBtn.disabled = !(meeting.transcript_segments && meeting.transcript_segments.length);
  }
  return meeting;
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

  const exportBtn = document.getElementById("export-transcript-btn");
  if (exportBtn) {
    exportBtn.addEventListener("click", () => {
      if (_detailMeeting && _detailMeeting.transcript_segments) {
        exportTranscriptText(_detailMeeting);
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

  // poll เฉพาะตอนยังไม่ transcribed (รอผลประมวลผล) — หยุด poll ทันทีที่ transcribed แล้ว กัน
  // เขียนทับ input ที่ผู้ใช้กำลังพิมพ์ในฟอร์ม Speaker Mapping อยู่ (ต่างจาก dashboard ที่ poll
  // ตลอดได้เพราะไม่มี input ค้าง)
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

// ─────────────────────────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
  initRoleSelect();
  initDashboardPage();
  initCreateMeetingPage();
  initMeetingDetailPage();
});
