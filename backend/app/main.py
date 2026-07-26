"""SwiftGate — AI model gateway with cost intelligence.

'See the cost before you pay it.'
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import init_db
from app.routers import admin, agents, analytics, apikeys, cost, gateway, quality
from app.services.pricing import seed_database


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: create tables + seed pricing data."""
    await init_db()

    # Seed the pricing database
    from app.database import async_session
    async with async_session() as db:
        result = await seed_database(db)
        await db.commit()
        print(f"[SwiftGate] Database seeded: {result}")

    yield


app = FastAPI(
    title="SwiftGate",
    description="AI model gateway with cost intelligence. See the cost before you pay it.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Health ────────────────────────────────────────────────────────────

@app.get("/health", tags=["health"])
async def health():
    return {"status": "ok", "service": "swiftgate", "version": "1.0.0"}


@app.get("/health/ready", tags=["health"])
async def health_ready():
    try:
        from app.database import engine
        from sqlalchemy import text

        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return {"status": "ready", "database": "connected"}
    except Exception as e:
        from fastapi import HTTPException
        raise HTTPException(503, f"Database not ready: {e}")


# ─── Routers ───────────────────────────────────────────────────────────

app.include_router(cost.router)        # /v1/predict, /v1/compare, /v1/models, /v1/pareto
app.include_router(gateway.router)     # /v1/chat/completions (OpenAI-compatible proxy)
app.include_router(analytics.router)   # /v1/usage, /v1/usage/daily, /v1/stats
app.include_router(admin.router)       # /admin/providers, /admin/models (CRUD)
app.include_router(apikeys.router)     # /v1/keys (create, list, revoke)
app.include_router(agents.router)      # /v1/agents (budget orchestration)
app.include_router(quality.router)     # /v1/quality, /v1/routing (quality-aware routing)


# ─── Root ──────────────────────────────────────────────────────────────

@app.get("/", tags=["root"])
async def root():
    return {
        "name": "SwiftGate",
        "tagline": "See the cost before you pay it",
        "docs": "/docs",
        "endpoints": {
            "predict": "POST /v1/predict",
            "compare": "POST /v1/compare",
            "models": "GET /v1/models",
            "pareto": "GET /v1/pareto",
            "chat": "POST /v1/chat/completions",
            "usage": "GET /v1/usage",
            "stats": "GET /v1/stats",
            "admin": "GET /admin/providers, /admin/models",
        },
    }
