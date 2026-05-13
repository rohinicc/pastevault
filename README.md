# PasteVault

**Encrypted. Ephemeral. Antigravity.**

A zero-trust, end-to-end encrypted paste-sharing platform. Create a paste, share the link, and it vanishes — after reading, after expiry, or on demand.

---

## System Architecture

```
                         ┌─────────────────────────────────┐
                         │         CLIENT BROWSER           │
                         │   index.html  |  view.html       │
                         │      (Vanilla HTML/CSS/JS)       │
                         └──────────────┬──────────────────┘
                                        │ HTTP REST
                         ┌──────────────▼──────────────────┐
                         │         FASTAPI (uvicorn)        │
                         │                                  │
                         │  ┌──────────┐  ┌─────────────┐  │
                         │  │  /pastes │  │   /health   │  │
                         │  │  router  │  │   /docs     │  │
                         │  └────┬─────┘  └─────────────┘  │
                         │       │                          │
                         │  ┌────▼──────────────────────┐  │
                         │  │      paste_service         │  │
                         │  │  ┌──────────┐ ┌────────┐  │  │
                         │  │  │  crypto  │ │  slug  │  │  │
                         │  │  │ _service │ │_service│  │  │
                         │  │  └──────────┘ └────────┘  │  │
                         │  └────┬───────────────┬──────┘  │
                         └───────┼───────────────┼─────────┘
                                 │               │
                ┌────────────────▼──┐     ┌──────▼───────────────┐
                │   POSTGRESQL 16   │     │      REDIS 7          │
                │   (long-lived)    │     │   (short-lived)       │
                │                   │     │                        │
                │  ┌─────────────┐  │     │  paste:short:{slug}   │
                │  │slug (PK)    │  │     │  burn:{slug}          │
                │  │encrypted_   │  │     │  views:{slug}         │
                │  │  content    │  │     │  rate:{ip}            │
                │  │language     │  │     │                        │
                │  │burn_after_  │  │     │  TTL → Redis SETEX     │
                │  │  read       │  │     └────────────────────────┘
                │  │password_salt│  │
                │  │delete_token │  │
                │  │  _hash      │  │
                │  │view_count   │  │
                │  │expires_at   │  │
                │  │is_burned    │  │
                │  │created_at   │  │
                │  └─────────────┘  │
                └───────────────────┘
```

---

## Request Flows

### Create Paste

```
Browser ──POST /pastes/──► FastAPI
                              │
                    ┌─────────▼──────────┐
                    │  Rate Limiter Check │
                    │  (Redis INCR ip,    │
                    │   100 req/min)      │
                    └─────────┬──────────┘
                              │
                    ┌─────────▼──────────┐
                    │  Pydantic Validate │
                    │  PasteCreate       │
                    └─────────┬──────────┘
                              │
                    ┌─────────▼──────────┐
                    │  generate_slug()   │
                    │  (8-char random,   │
                    │  check Redis + DB  │
                    │  for collision)    │
                    └─────────┬──────────┘
                              │
                    ┌─────────▼──────────┐
                    │  uuid4()           │
                    │  → delete_token    │
                    └─────────┬──────────┘
                              │
                    ┌─────────▼──────────┐
                    │  encrypt(content,  │
                    │    password, slug) │
                    │  → ciphertext +    │
                    │    password_salt   │
                    └─────────┬──────────┘
                              │
                    ┌─────────▼──────────┐
                    │  TTL ≤ 24 hours?   │
                    └─────────┬──────────┘
                         YES │              NO
                    ┌─────────▼──┐   ┌──────▼──────────┐
                    │  Redis     │   │  PostgreSQL      │
                    │  SETEX     │   │  INSERT paste    │
                    │  paste:    │   │  row             │
                    │  short:    │   └──────┬──────────┘
                    │  {slug}    │          │
                    └──────┬─────┘   ┌──────▼──────────┐
                           │         │  if burn_after  │
                    ┌──────▼─────┐   │  _read → Redis  │
                    │  if burn   │   │  SET burn:{slug}│
                    │  _after_   │   └─────────────────┘
                    │  read →    │
                    │  Redis     │         BOTH PATHS
                    │  SETEX     │            │
                    │  burn:     │    ┌───────▼──────────┐
                    │  {slug}    │    │  Return response │
                    └────────────┘    │  { slug, url,    │
                                      │   delete_token,  │
                                      │   expires_at }   │
                                      └──────────────────┘
```

### Read Paste

```
Browser ──GET /pastes/{slug}──► FastAPI
                                  │
                    ┌─────────────▼─────────────┐
                    │  Check burn:{slug} in Redis│
                    │  + paste:short:{slug}      │
                    └─────────────┬─────────────┘
                                  │
              ┌───────────────────┼───────────────────┐
              │                   │                   │
     burn EXISTS +          short EXISTS        neither EXISTS
     short MISSING           → Redis HIT        → fall through
              │                   │                   │
    ┌─────────▼────────┐  ┌──────▼───────┐   ┌───────▼────────┐
    │ Check DB for     │  │ Atomic Lua   │   │ SELECT FROM DB │
    │ is_burned        │  │ Script:      │   │ + FOR UPDATE   │
    │  → 410 if burned │  │ GET content  │   │                │
    └──────────────────┘  │ INCR views   │   │  Not found→404 │
                          │ DEL if burn  │   │  is_burned→410 │
                          └──────┬───────┘   │  expired →410 │
                                 │           └───────┬────────┘
                                 │                   │
                          ┌──────▼───────────────────▼──────┐
                          │  decrypt(ciphertext, password,  │
                          │    slug, password_salt)          │
                          └──────┬───────────────────┬──────┘
                                 │                   │
                          ┌──────▼───────┐   ┌───────▼────────┐
                          │  if burn_    │   │  Increment     │
                          │  after_read  │   │  view_count    │
                          │  → DELETE    │   │                │
                          │    keys +    │   │  Return {      │
                          │    set       │   │   content,     │
                          │    is_burned │   │   language,    │
                          │    = True    │   │   view_count } │
                          └──────────────┘   └────────────────┘
```

---

## Storage Decision Tree

```
POST /pastes/ received
        │
        ├── TTL ≤ 24 hours (86,400s)?
        │        │
        │       YES ──► Redis SETEX only (no DB write)
        │        │      Store: paste:short:{slug}
        │        │      Burn flag: burn:{slug} (same TTL)
        │        │
        │        NO
        │        │
        │        ├── TTL > 24h ──► PostgreSQL INSERT
        │        │                 Burn flag: Redis SET burn:{slug}
        │        │
        │        └── No TTL (permanent) ──► PostgreSQL INSERT only
```

---

## Encryption Architecture

```
 User Input (plaintext)
        │
        ▼
┌─────────────────────────────────────────────┐
│  Layer 1: Fernet(SERVER_KEY)                │
│  Algorithm: AES-128-CBC + HMAC-SHA256       │
│  Always applied — server-side key           │
│  encrypt(plaintext) → ciphertext_L1         │
└─────────────────────┬───────────────────────┘
                      │
            password provided?
                      │
          ┌───────────┼───────────┐
         YES           │          NO
          │            │           │
          ▼            │           ▼
┌─────────────────────▼┐   ┌──────▼──────────────┐
│  Layer 2: Fernet(    │   │  Store ciphertext_L1 │
│   PBKDF2(password +  │   │  directly            │
│   random 32-byte     │   └─────────────────────┘
│   salt, 390K iters)) │
│                      │
│  encrypt(ciphertext_ │
│   L1) → final        │
│  ciphertext          │
└──────────────────────┘

 Decryption (reverse order):
  1. If password set: Fernet(PBKDF2(password + salt)).decrypt()
  2. Fernet(SERVER_KEY).decrypt() → plaintext
```

---

## Features

- **End-to-end encryption** — Fernet AES-128-CBC + HMAC-SHA256 on the server, with optional PBKDF2-SHA256 password layer (390,000 iterations, random 32-byte salt per paste)
- **Burn after reading** — paste is destroyed immediately after first view (atomic Redis Lua script prevents race conditions)
- **Time-based expiry** — pastes auto-delete after 1 hour up to 30 days (or never)
- **Password protection** — second encryption layer derived from your password + unique random salt
- **Delete tokens** — each paste gets a unique UUID, SHA-256 hashed before storage
- **Dual storage** — short-TTL pastes stay in Redis only (no DB write); long-lived pastes go to PostgreSQL
- **Rate limiting** — 100 requests/minute per IP via Redis counter
- **Async architecture** — FastAPI + asyncpg + aioredis + SQLAlchemy async
- **No accounts, no logs** — anonymous usage, zero PII collected

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| API | FastAPI (Python 3.12) |
| Database | PostgreSQL 16 (via asyncpg) |
| Cache | Redis 7 (via redis-py async) |
| ORM | SQLAlchemy 2.0 (async) |
| Migrations | Alembic |
| Encryption | Fernet + PBKDF2 (cryptography) |
| Frontend | Vanilla HTML / CSS / JS |
| Containerization | Docker + Docker Compose |

---

## Project Structure

```
pastevault/
├── app/
│   ├── main.py              # FastAPI app, lifespan, rate limiter, mount
│   ├── config.py            # Pydantic Settings from .env
│   ├── database.py          # Async SQLAlchemy engine + session
│   ├── redis_client.py      # Redis async client + atomic Lua scripts
│   ├── models/
│   │   └── paste.py         # SQLAlchemy ORM (Paste model)
│   ├── schemas/
│   │   └── paste.py         # Pydantic request/response schemas
│   ├── routers/
│   │   └── paste.py         # FastAPI route definitions
│   ├── services/
│   │   ├── crypto_service.py   # Fernet + PBKDF2 encryption
│   │   ├── paste_service.py    # Core business logic
│   │   └── slug_service.py     # Unique slug generation
│   └── tasks/
│       └── cleanup.py       # Background expired-paste purge
├── frontend/
│   ├── index.html           # Create paste UI
│   ├── view.html            # View paste UI
│   ├── app.js               # Frontend logic
│   └── style.css            # Antigravity design system
├── alembic/                 # Database migrations
├── Dockerfile
├── docker-compose.yml
├── .env.example
├── requirements.txt
└── README.md
```

---

## Quick Start

### Prerequisites

- Docker & Docker Compose

### Run

```bash
git clone https://github.com/yourusername/pastevault.git
cd pastevault

# Copy environment file
cp .env.example .env

# Generate a Fernet encryption key
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# Edit .env — paste the generated key as ENCRYPTION_KEY

# Build and start all services
docker compose up --build -d
```

### Access

| Service | URL |
|---------|-----|
| Create paste | http://localhost:8000 |
| View paste | http://localhost:8000/view.html |
| API docs (Swagger) | http://localhost:8000/api/docs |
| API docs (ReDoc) | http://localhost:8000/api/redoc |

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `postgresql+asyncpg://postgres:password@db:5432/pastevault` | PostgreSQL async connection string |
| `REDIS_URL` | `redis://redis:6379/0` | Redis connection string |
| `ENCRYPTION_KEY` | — | Fernet key (required — generate via `Fernet.generate_key().decode()`) |
| `BASE_URL` | `http://localhost:8000` | Public URL for generated paste links |
| `LOG_LEVEL` | `INFO` | Python logging level |
| `DB_POOL_SIZE` | `10` | SQLAlchemy async connection pool size |
| `DB_MAX_OVERFLOW` | `20` | Max overflow connections for the pool |
| `RATE_LIMIT_PER_MINUTE` | `100` | Max requests per IP per minute (sliding window via Redis) |
| `CLEANUP_INTERVAL_SECONDS` | `3600` | Interval for background expired-paste purge task |
| `POSTGRES_PASSWORD` | `password` | PostgreSQL password |

---

## API Endpoints

### `POST /pastes/` — Create a paste

Request body:
```json
{
  "content": "your text here",
  "language": "python",
  "burn_after_read": false,
  "ttl_seconds": 3600,
  "password": null
}
```

Response `201`:
```json
{
  "slug": "AbC123Xy",
  "url": "http://localhost:8000/view.html?slug=AbC123Xy",
  "delete_token": "550e8400-e29b-41d4-a716-446655440000",
  "expires_at": "2026-05-13T10:00:00+00:00",
  "burn_after_read": false,
  "language": "python"
}
```

### `GET /pastes/{slug}` — Read a paste (no password)

Returns `200` with content, language, view count, expiry info.

### `POST /pastes/{slug}/read` — Read a password-protected paste

Request body:
```json
{ "password": "your-password" }
```

### `GET /pastes/{slug}/meta` — Get paste metadata

Returns slug, language, password protection status, view count, expiry — **without** the decrypted content.

### `DELETE /pastes/{slug}?token=...` — Delete a paste

Requires the delete token returned at creation. Returns `204` on success.

---

## Security

| Property | Implementation |
|----------|---------------|
| Encryption at rest | Fernet AES-128-CBC + HMAC-SHA256 |
| Password protection | PBKDF2-SHA256, 390,000 iterations, random 32-byte salt per paste |
| Delete tokens | SHA-256 hashed before storage (raw token shown once at creation) |
| Burn after read | Atomic Redis Lua script — no race condition between concurrent readers |
| Rate limiting | Per-IP Redis counter with expiry |
| Slug collision | 62^8 ≈ 218 trillion combinations, checked against Redis + DB |
| Container security | Runs as non-root `pastevault` user |
| No PII collected | Anonymous pastes — no accounts, no cookies, no logs of content |

---

## License

MIT
