# PRD: Company Secretary AI System (Com Sec)

**Status**: Draft
**Author**: Siraphob
**Date**: 2026-08-01

---

## Problem

The Company Secretary team currently handles board/committee meetings manually end-to-end: recording, transcribing, drafting Minutes of Meeting, searching company policy documents for reference, and routing final documents through approval before sending to the Board. There is no tooling support for any of these steps, and no access-control system for confidential board content — the only existing RAG tool (Local RAG / Policy RAG Assistant) has no RBAC at all and is meant for a different audience (deep policy research), so board minutes cannot safely be added to its shared index. Hardware is also constrained (4GB VRAM), and one candidate reference model (`Diarization_ThaiSpeech_2022`) carries legal risk (no LICENSE file).

## Goals

- Automate Thai meeting audio/video into a speaker-labeled, timestamped transcript
- Automate Minutes of Meeting drafting from that transcript into the official Word template, via structured LLM output
- Provide a Maker → Checker → (Needs_Revision) → Approved workflow with full audit trail before secure delivery to the Board
- Provide fast, RBAC-gated policy Q&A embedded in the secretary workflow, reusing the proven Local RAG stack rather than rebuilding it
- Enforce the EMPIRE company CI across the frontend
- ~~Keep the RAG worker CPU-only at all times~~ — **reversed 2026-08-02**: live testing found CPU + `torch.float16` reranking took 553-1000s per query (17x slower than CPU + fp32, per direct measurement); user chose to run the RAG worker on GPU when available (falls back to CPU + fp32, never fp16-on-CPU) rather than accept the CPU-only latency. This reopens VRAM sharing with Module 2 (Diarization/ASR) — the GPU Lock design must now cover the RAG worker too, not just Diarization+ASR (see task.md 2026-08-02 entry)

## Non-goals

- Retiring or replacing Local RAG (Streamlit) — it stays as a separate, permanent product for deep policy research; both point at the same FAISS index/storage to avoid corpus drift
- Using `typhoon2-audio` (8B params, ~16GB VRAM) in the current MVP — kept only as a documented option for a future cloud-GPU production deployment
- ~~GPU-opportunistic scheduling for the RAG worker~~ — **reversed 2026-08-02** (see Goals above): the RAG worker now uses GPU when available; the Module 2 GPU Lock design must be extended to cover it, not treated as out of scope anymore
- Auto-fetching meeting recordings via Google Drive/MS Graph API — manual upload only for the three known sources (Google Meet, MS Teams, local recorder/phone)
- Using the `Instructor` library for structured LLM output — using Gemini's native `response_schema` instead
- Using SharePoint Graph API for archive delivery — plain UNC-path copy (`shutil.copy`), destination configurable
- Tracking the cloned reference repos (`meetily`, `typhoon-asr`, `typhoon2-audio`, `Diarization_ThaiSpeech_2022`) inside the Com Sec git repo — they keep their own `.git` history and are gitignored from the main repo

## Users

- **Com_Sec_Maker** — uploads meeting audio, maps speakers, generates and lightly edits the draft minutes
- **Com_Sec_Checker** — head of Company Secretary; approves or rejects (with comments) the final draft
- **Board_Member** — reads and e-signs the approved document; does **not** get access to raw recordings or the transcript-sync player (narrower RBAC than document access)
- **Global_Admin** — full access across every role and endpoint

## Requirements

### Must have (P0)

- RAG worker runs as a separate OS process from the main FastAPI backend, never merged into it (avoids a documented Windows WINHTTP.dll access-violation crash from combining torch/faiss with the web layer in one process)
- `backend/rag.py` is a real HTTP client to the worker (not a stub returning hardcoded strings)
- Worker session state is keyed by authenticated `user_id`, not a browser-tab session id
- Confidential BOD-minutes retrieval uses a FAISS index kept **physically separate** from the general policy index shared with Local RAG, because Local RAG's Streamlit UI has no RBAC and would otherwise be able to surface confidential content
- `/api/rag/query` (general policy Q&A, any authenticated role) and `/api/rag/query_confidential` (restricted to Com_Sec_Maker/Checker/Board_Member/Global_Admin) with role enforced at both the backend and the worker
- Manual upload support for audio/video from 3 sources (Google Meet, MS Teams, local recorder), via `ffmpeg`, with no upfront format restriction
- A "Meeting" entity (date, meeting number, attendee list + titles, agenda) must be created before an audio file can be uploaded against it
- Diarization runs on the full-length audio file first (not chunked); only ASR is chunked afterward (1-hour segments) — preserves consistent speaker IDs across the whole meeting
- A single GPU Lock shared only between Diarization and ASR (load → run → `torch.cuda.empty_cache()` → next model); never two models on VRAM simultaneously
- CPU fallback (`--device cpu`) if VRAM allocation fails, always as a last resort
- A mandatory Speaker Mapping screen (map `Speaker_00/01/...` to real names from the attendee list) blocks minutes generation until complete
- Per-segment start/end timestamps are stored for every transcribed utterance (needed for the transcript-sync player)
- Minutes generation uses Gemini via `google-genai`, native structured output (`response_schema` + `response_mime_type="application/json"`), reusing `llm_fallback.run_with_fallback()` for retry/fallback
- Gemini **paid tier** is used from the first real-content test onward (not just at production), because board content is highly confidential and paid tier is confirmed not to train on prompts/responses
- Generated JSON is mapped into the official Word template (`260628 Draft_EMPIRE - BOD Minutes 15-2569 v.5.docx`) via `python-docx`
- Approval workflow has at least 4 states: `Draft` → `Pending_Review` → `Needs_Revision` (Checker rejects with a comment, returns to Maker) or `Approved` → sent to Board_Member; every state transition is logged for audit
- After approval: automated secure email with a Magic Link to the Board_Member, with the link designed for **single-use and token expiration**
- Two separate, config-driven archive destinations by file type: completed documents (shared with executives) vs. original recordings + transcript-sync data (Com Sec team only — Global_Admin/Maker/Checker; Board_Member explicitly excluded)
- Frontend built against an EMPIRE-CI-derived design system (colors/fonts extracted from `EMPIRE CI(1).png`)
- Synced audio/video player + transcript panel, built with HTML5 `<audio>`/`<video>` + `ontimeupdate` (the `meetily/frontend` Tauri implementation cannot be used directly in a web app)
- Git version control for the Com Sec codebase on GitHub (private repo, code only — `github.com/bornja55/MeetlySec`), with `.gitignore` excluding secrets, media files, model weights, the confidential corpus, and the cloned reference repos
- Pre-commit hooks (`detect-secrets` + `ruff`) and a GitHub Actions lint workflow, so no API keys/secrets can be committed and lint runs on every push

### Should have (P1)

- Real Azure AD authentication — currently `auth.py` is entirely mock token strings; blocked on the user providing a tenant ID / client ID
- Measured (not assumed) VRAM usage of `typhoon-asr` on the actual 4GB machine
- UX for the upload queue/status when multiple users upload concurrently (single queue, one file processed at a time — screen not yet designed)
- A decision and remediation plan for the 65 (of 213 scanned) corpus files that still contain the old company name "ทเวนตี้ โฟร์ คอน แอนด์ ซัพพลาย" (and 166 containing the old company code "24CS") — found and reported this session, not yet acted on
- A retention policy for original audio/video recordings (retention period, encryption at rest, file-level access control) — flagged as an unresolved compliance gap against the org's own HR_PDPA_Policy / Data_Breach_Policy

### Nice to have (P2)

- Automatic re-indexing of the confidential corpus on every Module 5 approval, instead of manually running `build_confidential_index.py` — undecided, deferred until Module 5 is scoped

## Success metrics

Not discussed in concrete, measurable terms anywhere in this conversation — no baseline, target, or timeframe was given for any metric (e.g., transcription accuracy, turnaround time from upload to approved minutes, Q&A latency). **Missing — needs follow-up with the user before this section can be filled in.**

| Metric | Baseline | Target | Timeframe |
|--------|---------|--------|-----------|
| _(none defined yet)_ | — | — | — |

## Open questions

- Should the confidential-corpus FAISS index be re-built automatically on every Module 5 approval, or manually via script? (explicitly left open in `build_confidential_index.py`)
- What is the retention/encryption/access policy for original meeting recordings? (flagged as a real compliance risk, not yet decided)
- What should happen to the 65 corpus files still containing the old company name — leave as-is (relying on the existing Prefill provenance/date-based staleness rule) or correct them?
- When (if ever) should the Gemini fallback models be turned on in production? (old open item inherited from Local RAG, never resolved)
- Should recordings ever be auto-fetched from Google Meet/MS Teams APIs in a later phase, or is manual upload permanent?

## Out of scope

- Retiring Local RAG (Streamlit) — stays as a separate, permanent product
- `typhoon2-audio` integration — kept only as a reference for a possible future cloud-GPU deployment
- `book-to-skill` — removed from the plan entirely (duplicated Local RAG's own document-conversion tooling)
- ~~GPU-opportunistic scheduling for the RAG worker~~ — reversed 2026-08-02, now in scope (see Goals)
- Auto-fetching recordings from Google Meet/MS Teams APIs — manual upload only for the MVP
