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

# Everthing used

```
Phase 1 tech stack
LayerTechnologyWhyOCR pre-processOpenCV (Python)Deskew, denoise, binarise scanned docsOCR enginePaddleOCRBest Hindi+Roman accuracy on poor scansDoc classifierscikit-learn / lightweight transformerTag doc type offlineTask queueCelery + RedisParallel processing, job trackingObject storageMinIOS3-compatible, runs fully offlineMetadata DBPostgreSQLRBAC-scoped structured searchFull-text searchElasticsearchAny phrase search across OCR outputAuth directoryOpenLDAPCentral user/role managementAuth tokensJWT (python-jose)Stateless, per-request RBAC enforcementAPI serverFastAPIAsync, WebSocket, fastFrontendReact + ViteRole-aware UI, real-time updatesAudit logPostgreSQL (separate table)Every action logged with user + timestampReverse proxyNginxSingle entry point, static file serving
```

# RBAC


```
SuperAdmin
   ↓
HeadQuarter (2STC, 3STC...)
   ↓
Unit (3TTR, 5TTR...)
   ↓
Branch (A, Q, G, M...)
   ↓
Users:
   - Unit Admin
   - Branch Officer
   - Clerk
   - Trainee
```