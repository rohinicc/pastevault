# PasteVault — Architecture

## System Overview

```
                        ┌─────────────────────────────────┐
                        │          CLIENT BROWSER          │
                        │   index.html   |   view.html     │
                        └──────────────┬──────────────────┘
                                       │ HTTP/REST
                        ┌──────────────▼──────────────────┐
                        │         FASTAPI (uvicorn)        │
                        │                                  │
                        │  ┌──────────┐  ┌─────────────┐  │
                        │  │  /pastes │  │   /health   │  │
                        │  │  router  │  │   /metrics  │  │
                        │  └────┬─────┘  └─────────────┘  │
                        │       │                          │
                        │  ┌────▼──────────────────────┐  │
                        │  │       paste_service        │  │
                        │  │  ┌──────────┐ ┌────────┐  │  │
                        │  │  │  crypto  │ │  slug  │  │  │
                        │  │  │ _service │ │_service│  │  │
                        │  │  └──────────┘ └────────┘  │  │
                        │  └────┬───────────────┬──────┘  │
                        └───────┼───────────────┼─────────┘
                                │               │
               ┌────────────────▼──┐     ┌──────▼───────────────┐
               │   POSTGRESQL 16   │     │      REDIS 7          │
               │                   │     │                        │
               │  pastes table     │     │  paste:short:{slug}   │
               │  ┌─────────────┐  │     │  burn:{slug}          │
               │  │slug (PK)    │  │     │  views:{slug}         │
               │  │encrypted_   │  │     │  rate:{ip}            │
               │  │  content    │  │     │                        │
               │  │language     │  │     │  TTL managed natively  │
               │  │burn_after_  │  │     │  by Redis SETEX        │
               │  │  read       │  │     └────────────────────────┘
               │  │is_password_ │  │
               │  │  protected  │  │
               │  │delete_token │  │
               │  │view_count   │  │
               │  │expires_at   │  │
               │  │is_burned    │  │
               │  │created_at   │  │
               │  └─────────────┘  │
               └───────────────────┘
```

---

## Storage Decision Tree

```
POST /pastes/ received
        │
        ├── TTL ≤ 24 hours?
        │        │
        │       YES ──► Redis SETEX only (no DB write)
        │        │      burn flag → Redis burn:{slug}
        │        │
        │        NO
        │        │
        │        ├── TTL > 24h ──► PostgreSQL INSERT
        │        │                 + Redis read cache (5min TTL)
        │        │
        │        └── Permanent ──► PostgreSQL INSERT only
```

---

## Encryption Architecture

```
 User Input (plaintext)
        │
        ▼
 ┌──────────────────────────────────────────┐
 │  Layer 1: Fernet(SERVER_KEY)             │  ← always applied
 │  encrypt(plaintext) → ciphertext_L1      │
 └──────────────────────┬───────────────────┘
                        │
              password provided?
                        │
            YES ─────────────────────────────────────────┐
                        │                                 ▼
                        │          ┌────────────────────────────────────┐
                        │          │  Layer 2: Fernet(PBKDF2(pwd+slug)) │
                        │          │  encrypt(ciphertext_L1) → final    │
                        │          └────────────────────────────────────┘
                        │
            NO ──► store ciphertext_L1 directly

 Decryption reverses layers (L2 first if password set, then L1)
```

---

## Request Flow — Create Paste

```
POST /pastes/
  Body: { content, language, burn_after_read, ttl_seconds, password }

  1. Pydantic validation
  2. generate_slug() → check Redis + DB for collision
  3. uuid4() → delete_token
  4. encrypt(content, password, slug)
  5. TTL decision → Redis or PostgreSQL
  6. Set burn:{slug} in Redis if burn_after_read
  7. Return { slug, url, delete_token, expires_at }
```

## Request Flow — Read Paste

```
GET /pastes/{slug}?password=...

  1. Check burn:{slug} in Redis
     └── exists AND paste:short:{slug} missing → 410 Gone (already burned)

  2. Try Redis short-store (paste:short:{slug})
     └── HIT → decrypt → increment views → burn if flagged → return

  3. Try PostgreSQL
     └── NOT FOUND → 404
     └── expires_at < now → 410
     └── is_burned = true → 410
     └── decrypt → view_count++ → burn if flagged → return
```

---

## Directory Structure

```
pastevault/
├── app/
│   ├── main.py              # FastAPI app, lifespan, mounts
│   ├── config.py            # Pydantic Settings from .env
│   ├── database.py          # Async SQLAlchemy engine + session
│   ├── redis_client.py      # aioredis connection + helpers
│   ├── models/
│   │   └── paste.py         # SQLAlchemy ORM model
│   ├── schemas/
│   │   └── paste.py         # Pydantic request/response models
│   ├── routers/
│   │   └── paste.py         # FastAPI routes
│   ├── services/
│   │   ├── crypto_service.py   # Fernet + PBKDF2 encryption
│   │   ├── paste_service.py    # Core create/read logic
│   │   └── slug_service.py     # Unique slug generation
│   └── tasks/
│       └── cleanup.py       # Background expired-paste purge
├── frontend/
│   ├── index.html           # Create paste UI
│   ├── view.html            # View paste UI
│   ├── style.css            # Antigravity design system
│   └── app.js               # API calls + UI logic
├── alembic/                 # DB migrations
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── .env.example
├── architecture.md
└── plan.md
```

---

## Environment Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `DATABASE_URL` | Async PostgreSQL DSN | `postgresql+asyncpg://...` |
| `REDIS_URL` | Redis connection URL | `redis://redis:6379/0` |
| `ENCRYPTION_KEY` | Fernet key (32-byte base64) | `run Fernet.generate_key()` |
| `BASE_URL` | Public URL for paste links | `https://pastevault.io` |

---

## Security Properties

| Property | Implementation |
|----------|---------------|
| Encryption at rest | Fernet AES-128-CBC + HMAC-SHA256 |
| Password protection | PBKDF2-SHA256, 390,000 iterations |
| Burn-after-read | Atomic Redis delete before response return |
| Delete token | UUID4, never stored in URL |
| Rate limiting | Redis counter per IP, 100 req/min |
| No auth required | Anonymous pastes — no PII collected |
