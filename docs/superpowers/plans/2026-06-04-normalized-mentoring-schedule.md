# Normalized Mentoring Schedule Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Store trainee-to-mentoring registrations as normalized data, use that data as the source of truth for team schedule calculations, and keep vector/RAG only as a recommendation aid.

**Architecture:** SQLite becomes the authoritative store for teams, mentoring events, participants, sync runs, and embedding docs. ChromaDB stores semantic documents built from normalized mentoring events. LangChain tools choose deterministic DB paths for schedule questions and RAG/reranking paths for recommendation questions.

**Tech Stack:** FastAPI, SQLite, LangChain/LangGraph, ChromaDB, React Chrome extension, TypeScript.

---

### Task 1: Normalize Backend Storage

**Files:**
- Modify: `backend/database.py`
- Test: `backend/test_normalized_schedule.py`

- [ ] Add tests proving `save_mentorings()` writes `mentoring_participants`, `sync_item_results`, and queryable registration rows.
- [ ] Add tables: `teams`, `team_members`, `trainees`, `mentoring_participants`, `mentoring_embedding_docs`, `sync_runs`, `sync_item_results`.
- [ ] Keep legacy `mentorings` and `team_info` reads working while new query methods use normalized tables.
- [ ] Make `clear_all_portal_data()` clear all normalized tables.

### Task 2: Move Schedule Tools to Normalized DB

**Files:**
- Modify: `backend/tools.py`
- Test: `backend/test_normalized_schedule.py`

- [ ] Make participant registration lookup use `db.load_participant_registrations()` instead of scanning `raw_json`.
- [ ] Make team free-slot calculation use team members and participant registration events.
- [ ] Keep schedule visual blocks with hover details that explain the exact blocked reason.
- [ ] Add a vector search tool wrapper for recommendation flows.

### Task 3: Sync and Vector Observability

**Files:**
- Modify: `backend/main.py`
- Modify: `backend/vector_store.py`

- [ ] Return sync run stats: list count, detail success/fail count, participant links, vector document count.
- [ ] Store embedding doc metadata for every vectorized mentoring event.
- [ ] Ensure vector sync failure does not block normalized DB writes.

### Task 4: Agent Policy and Cycle Guardrails

**Files:**
- Modify: `backend/agent.py`
- Modify: `backend/agent_prompts.py`

- [ ] Team schedule questions must call team info and free slots, then finalize.
- [ ] Simple team-info questions must not render a calendar.
- [ ] Recommendation questions must combine DB exclusion, vector search, and reranking.
- [ ] Keep repeated tool-call protection and avoid exposing raw tool tokens.

### Task 5: Extension Sync Process UX

**Files:**
- Modify: `extension/src/components/ChatPanel.tsx`
- Modify: `extension/src/styles.css`

- [ ] Show a scrollable sync/process step list.
- [ ] Separate portal sync stages from question-processing stages.
- [ ] Display list/detail/participant/vector counts separately.
- [ ] Keep browser personal schedule as optional or hidden, not required.

### Verification

- [ ] `rtk backend/venv/bin/python -m pytest backend/test_normalized_schedule.py -q`
- [ ] `rtk backend/venv/bin/python -m py_compile backend/database.py backend/tools.py backend/main.py backend/agent.py backend/agent_prompts.py backend/vector_store.py`
- [ ] `rtk npm run build` from `extension`
