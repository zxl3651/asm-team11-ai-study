# Data Quality And Agent Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add canonical RDBMS fields, validation status, and explicit agent workflow branching for SoMa Mate.

**Architecture:** Keep the extension collection flow unchanged. Normalize and validate portal data when the backend saves it, use validated canonical fields for tools, keep Chroma as a secondary candidate source, and add LangGraph nodes for intent classification and data readiness before tool execution.

**Tech Stack:** Python, SQLite, FastAPI, LangGraph, LangChain, ChromaDB.

---

### Task 1: Data validation layer
- [ ] Create `backend/data_validation.py` with date/time parsing and quality status helpers.
- [ ] Apply validation in `backend/database.py` save methods.

### Task 2: Validated search tools
- [ ] Update `backend/tools.py` to prefer canonical fields and avoid invalid records for schedule-sensitive answers.
- [ ] Keep vector search as a secondary boost only.

### Task 3: Explicit agent workflow branching
- [ ] Add intent classification and data readiness nodes to `backend/agent.py`.
- [ ] Update Mermaid generation to show selected intent, readiness, retrieval, validation, and answer path.

### Task 4: Verification
- [ ] Compile backend files.
- [ ] Run extension build if UI-facing types changed.

