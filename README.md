# E-Drug-Lab

E-Drug-Lab is a prototype platform for target-focused virtual screening workflows.
It currently includes:

- a FastAPI backend (API routes, tool integration skeletons, SDF parsing/sync, ranking),
- a Next.js frontend (workflow pages and basic UI),
- SQL schema and project docs.

## Repository Layout

```text
backend/     FastAPI application and services
frontend/    Next.js + TypeScript frontend
database/    SQL initialization scripts
docs/        Project documentation
molecules/   Local molecule data (not tracked by git in current policy)
outputs/     Local outputs (not tracked by git)
deliverables/ Local package artifacts (partially excluded from git)
```

## Quick Start

## 1) Backend

Requirements:

- Python 3.10+
- pip

Run:

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Health checks:

- `GET http://localhost:8000/health`
- `GET http://localhost:8000/ready`

## 2) Frontend

Requirements:

- Node.js 18+
- npm

Run:

```bash
cd frontend
npm install
npm run dev
```

Default URL: `http://localhost:3000`

## Environment

Backend environment sample file:

- `backend/.env.example`

Copy it to `.env` and adjust database/tool/API settings as needed.

## Git Upload Policy (Current)

This repository is configured to upload code and Markdown only by default.
Large files, build outputs, dependency directories, and selected local artifacts are excluded via `.gitignore`.

Also excluded from tracking:

- `deliverables/target-driven-vs-package/`

## Status

This project is in active prototype stage.
Some routes and integrations are skeleton implementations and need further business logic completion.
