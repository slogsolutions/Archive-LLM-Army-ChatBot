```
root/
├── Archive/
│   ├── backend/
│   │   ├── app/
│   │   │   ├── api/          # FastAPI route files
│   │   │   ├── core/         # config, security, RBAC engine
│   │   │   ├── models/       # SQLAlchemy models
│   │   │   ├── schemas/      # Pydantic schemas
│   │   │   ├── services/     # OCR, classifier, metadata
│   │   │   └── workers/      # Celery tasks
│   │   ├── alembic/          # DB migrations
│   │   ├── Dockerfile
│   │   └── requirements.txt
│   ├── frontend/
│   │   ├── src/
│   │   │   ├── pages/        # Login, Dashboard, Search, Viewer
│   │   │   ├── components/   # RBAC-aware components
│   │   │   └── hooks/        # Auth, WebSocket hooks
│   │   ├── Dockerfile
│   │   └── package.json
│   └── data-migration/
│       ├── scripts/          # Bulk import, re-index tools
│       └── Dockerfile
├── LLM/                      # Phase 2 — empty for now
└── docker-compose.yml        # Single compose for all services
```