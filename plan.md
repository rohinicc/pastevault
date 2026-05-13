# PasteVault — Project Plan

## Vision
A zero-trust, encrypted code snippet vault with burn-after-read and time-expiry.
No accounts needed. Share once, vanish forever.

---

## Phase 1 — Core Backend (Week 1)

### Day 1–2: Project Setup
- [x] FastAPI skeleton with lifespan
- [x] PostgreSQL + SQLAlchemy async models
- [x] Redis client (aioredis)
- [x] Alembic migrations
- [x] Docker Compose (api + db + redis)

### Day 3–4: Crypto + Storage
- [x] Fernet server-side encryption layer
- [x] PBKDF2 password-derived key (layer 2)
- [x] Slug generator with collision detection
- [x] Redis-only path for TTL ≤ 24h
- [x] PostgreSQL path for long-lived / permanent pastes

### Day 5: API Endpoints
- [x] POST /pastes/ — create with full options
- [x] GET  /pastes/{slug} — read + burn logic
- [x] DELETE /pastes/{slug} — token-based delete
- [x] GET /pastes/{slug}/meta — stats, no content

---

## Phase 2 — Frontend (Week 1–2)

### Day 6–7: UI
- [x] Antigravity dark theme (Space Mono, floating card, neon glow)
- [x] index.html — create paste form
- [x] view.html  — read paste + burn warning
- [x] style.css  — full antigravity design system
- [x] app.js     — API calls, clipboard, UI state

---

## Phase 3 — Polish (Week 2)

### Hardening
- [ ] Rate limiting middleware (Redis counter per IP)
- [ ] Max paste size enforcement (500KB)
- [ ] Input sanitisation on content
- [ ] CORS lock to production domain

### Ops
- [ ] Background cleanup task (hourly purge of expired DB rows)
- [ ] Prometheus metrics endpoint (/metrics)
- [ ] Grafana dashboard (paste count, burn rate, error rate)
- [ ] Healthcheck endpoint (/health)

---

## Phase 4 — Deployment (Week 2)

- [ ] EC2 t2.micro (Free Tier)
- [ ] Nginx reverse proxy + SSL (Certbot)
- [ ] GitHub Actions CI → Docker build → SSH deploy
- [ ] ENV secrets via AWS Parameter Store

---

## Tech Decisions

| Decision | Choice | Why |
|----------|--------|-----|
| Encryption | Fernet (symmetric) | Simple, fast, auditable |
| Short TTL storage | Redis only | Avoid DB write for ephemeral data |
| Long TTL storage | PostgreSQL | Persistence, queryable |
| Slug length | 8 chars (62^8 = 218T combos) | Collision-safe at scale |
| Key derivation | PBKDF2 + SHA256, 390k iters | OWASP recommended |
| Frontend | Vanilla HTML/CSS/JS | Zero build step, fast |

---

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| Redis crash loses short pastes | Acceptable — TTL pastes are ephemeral by design |
| Brute-force slug guessing | Rate limit + long slugs |
| Key compromise exposes all pastes | Rotate ENCRYPTION_KEY + re-encrypt on startup |
| DB bloat from old pastes | Hourly cleanup task |
