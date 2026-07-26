# SwiftGate Railway Deployment Guide

Railway deploys each service (backend, web, landing) as a separate container.
This guide covers both the Railway UI and CLI workflows.

---

## Architecture on Railway

```
┌──────────────────────────────────────────────────┐
│  Railway Project                                  │
│                                                   │
│  ┌─────────────┐    ┌──────────┐  ┌──────────┐  │
│  │  PostgreSQL │    │  Backend │  │  Redis   │  │
│  │  (plugin)   │───▶│  (Docker)│◀─│ (plugin) │  │
│  └─────────────┘    └────┬─────┘  └──────────┘  │
│                          │                        │
│                    ┌─────▼─────┐                  │
│                    │    Web    │                  │
│                    │  (nginx)  │                  │
│                    └───────────┘                  │
└──────────────────────────────────────────────────┘
```

## Quick Start (CLI)

### 1. Install Railway CLI
```bash
npm install -g @railway/cli
railway login
```

### 2. Create project and services
```bash
cd swiftgate
railway init  # Create new project

# Add PostgreSQL and Redis (Railway plugins)
railway add --plugin postgresql
railway add --plugin redis

# Deploy backend
railway up --service backend --detach
# Railway detects backend/Dockerfile + backend/railway.json

# Deploy web dashboard
railway up --service web --detach
# Railway detects web/Dockerfile + web/railway.json

# Deploy landing page
railway up --service landing --detach
```

### 3. Set environment variables

Go to the Railway dashboard → Backend service → Variables tab:

**Required:**
```
ENV=production
ADMIN_KEY=<generate a strong random string>
CORS_ORIGINS=https://<your-web-domain>.up.railway.app,https://<your-landing-domain>.up.railway.app
```

**Database (auto-set by PostgreSQL plugin):**
```
DATABASE_URL=${{Postgres.DATABASE_URL}}
REDIS_URL=${{Redis.REDIS_URL}}
```
Railway auto-injects these when you use the plugin reference syntax.

**Provider API keys (set at least one):**
```
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
DEEPINFRA_API_KEY=...
GOOGLE_API_KEY=...
```

**Web service variables:**
```
BACKEND_URL=https://<your-backend-domain>.up.railway.app
```

### 4. Generate domains

In Railway dashboard, for each service:
- Settings → Networking → Generate Domain

---

## Service Configuration

### Backend (`backend/railway.json`)
- **Builder:** Dockerfile (root context)
- **Start command:** `alembic upgrade head && uvicorn ... --port $PORT`
- **Healthcheck:** `GET /health`
- Railway injects `PORT` (typically 7437 or similar — never hardcode)

### Web (`web/railway.json`)
- **Builder:** Dockerfile (multi-stage: Node build → nginx serve)
- **Healthcheck:** `GET /` (serves index.html)
- Proxies `/v1/`, `/admin/`, `/health` to `$BACKEND_URL`

### Landing (`landing/railway.json`)
- Static nginx, no proxy needed

---

## Environment Variables Reference

### Backend Service
| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DATABASE_URL` | ✅ | SQLite | Postgres connection string (auto-set by plugin) |
| `REDIS_URL` | ✅ | localhost | Redis connection string (auto-set by plugin) |
| `ENV` | ✅ | `development` | Set to `production` |
| `ADMIN_KEY` | ✅ | `""` | Admin authentication key |
| `CORS_ORIGINS` | ✅ | `*` | Comma-separated allowed origins |
| `OPENAI_API_KEY` | Optional | `""` | OpenAI API key |
| `ANTHROPIC_API_KEY` | Optional | `""` | Anthropic API key |
| `DEEPINFRA_API_KEY` | Optional | `""` | DeepInfra API key |
| `GOOGLE_API_KEY` | Optional | `""` | Google AI key |
| `TOKEN_MARGIN` | Optional | `0.01` | Markup on token costs (1%) |
| `CACHE_ENABLED` | Optional | `true` | Enable semantic cache |
| `PII_REDACTION_ENABLED` | Optional | `false` | Strip PII before provider calls |

### Web Service
| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `BACKEND_URL` | ✅ | internal | URL of backend service on Railway |

---

## Postgres vs SQLite

Railway containers have **ephemeral filesystems** — SQLite data is lost on redeploy.

**Use the PostgreSQL plugin** (free tier: 500MB, 1 connection):
- Railway auto-creates `DATABASE_URL` with the connection string
- Alembic migrations run automatically on startup (`alembic upgrade head`)
- Connection pool config is already in `database.py`:
  ```python
  pool_size=10, max_overflow=20, pool_pre_ping=True, pool_recycle=3600
  ```

---

## CLI Cheatsheet

```bash
railway link              # Link to existing project
railway status            # View deployment status
railway logs              # Stream logs
railway variables         # View env vars
railway open              # Open in browser
railway up --detach       # Deploy without blocking
railway down              # Tear down deployment
```

---

## Troubleshooting

### Backend won't start
- Check logs: `railway logs --service backend`
- Common cause: `ADMIN_KEY` not set in production → admin endpoints return 503
- Common cause: Alembic migration fails → check `DATABASE_URL` format

### Web can't reach backend
- Verify `BACKEND_URL` is set to the full Railway domain (not localhost)
- Must include `https://` prefix
- Check that backend healthcheck passes: `curl https://<backend-domain>.up.railway.app/health`

### CORS errors
- Set `CORS_ORIGINS` to your exact web domain(s)
- Don't use `*` in production (credentials are rejected with wildcard)

### Streaming/SSE not working
- nginx config already has `proxy_buffering off` + `proxy_http_version 1.1`
- If still broken, check Railway's proxy timeout (Railway supports SSE)
