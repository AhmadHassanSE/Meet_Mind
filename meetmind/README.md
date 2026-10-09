# MeetMind — Iteration 1

Fresh implementation. The sibling `meeting-transcription-agent` directory is reference only.

## Run locally (two PowerShell terminals)

Prerequisites: Node.js, uv, Ollama running with `llama3.2:latest` installed.

Backend:
```powershell
cd meetmind/backend
uv sync --group dev
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Frontend:
```powershell
cd meetmind/frontend
npm.cmd install
npm.cmd run dev
```

Open the localhost URL printed by Vite. Development requests proxy to the local backend. API documentation: http://127.0.0.1:8000/docs

Configuration: backend environment variables `OLLAMA_URL`, `OLLAMA_MODEL`, `MEETMIND_DB`. Defaults: localhost:11434, llama3.2:latest, backend/meetmind.db. No hosted AI provider or API key is used. Installing dependencies/models requires internet; model inference uses the configured local Ollama service.

## Current scope

TXT/basic VTT ingestion, SQLite persistence, source-linked structured Ollama extraction, meeting library/detail, health status and explicit errors. Extraction suggestions all require review. Source references are validated, but semantic accuracy and hallucinations are not guaranteed. Re-extraction replaces previous results. Owner/deadline editing, robust VTT cue handling, spaCy, baseline evaluation, confidence module and AMI dataset work are pending. No external actions execute.

Ollama is the local LLM backend, not evidence of BERT fine-tuning. The proposal's BERT milestone remains distinct unless the supervisor accepts a documented method change. SQLite is a temporary local foundation; PostgreSQL remains the proposed relational target. No authentication or production deployment is included.

## Checks
```powershell
cd backend
uv run pytest
cd ..\frontend
npm.cmd run build
```

AI-assisted code must be reviewed and understood by its owners; disclose assistance in the evaluation report. No research performance results are claimed yet.
