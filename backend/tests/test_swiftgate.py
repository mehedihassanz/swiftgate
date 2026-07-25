"""SwiftGate test suite — comprehensive backend tests.

Run: pytest -v
"""
import asyncio
import hashlib
import json
import os
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

# Set test environment BEFORE importing app
os.environ["ENV"] = "testing"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./test_swiftgate.db"

from app.database import Base, async_session, engine, init_db
from app.main import app
from app.services.pricing import seed_database


@pytest_asyncio.fixture(scope="function")
async def db_session():
    """Fresh database for each test."""
    await init_db()
    async with async_session() as db:
        await seed_database(db)
        await db.commit()
        yield db
        await db.rollback()


@pytest_asyncio.fixture(scope="function")
async def client():
    """HTTP test client."""
    await init_db()
    async with async_session() as db:
        await seed_database(db)
        await db.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# ─── Health ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_health(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["service"] == "swiftgate"


@pytest.mark.asyncio
async def test_root(client):
    resp = await client.get("/")
    assert resp.status_code == 200
    data = resp.json()
    assert "endpoints" in data


# ─── Tokenizer ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_token_count_gpt4o():
    from app.services.tokenizer import get_token_count
    tokens = get_token_count(
        [{"role": "user", "content": "Hello, how are you?"}],
        "gpt-4o",
    )
    assert tokens > 0
    assert tokens < 100  # short prompt


@pytest.mark.asyncio
async def test_token_count_claude():
    from app.services.tokenizer import get_token_count
    tokens = get_token_count(
        [{"role": "user", "content": "Write a Python function"}],
        "claude-opus-5",
    )
    assert tokens > 0


@pytest.mark.asyncio
async def test_classify_task():
    from app.services.tokenizer import classify_task
    assert classify_task([{"role": "user", "content": "write a function"}]) == "code"
    assert classify_task([{"role": "user", "content": "explain step by step"}]) == "reasoning"
    assert classify_task([{"role": "user", "content": "hello"}]) == "chat"


@pytest.mark.asyncio
async def test_estimate_output():
    from app.services.tokenizer import estimate_output_tokens
    est = estimate_output_tokens("gpt-4o", "chat", 1000)
    assert est > 0
    assert est <= 1000  # capped at max_tokens


# ─── Cost Prediction ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_predict_cost(db_session):
    from app.services.cost_engine import predict_cost
    result = await predict_cost(
        db_session,
        "gpt-4o",
        [{"role": "user", "content": "Write a Python function"}],
        max_tokens=1000,
    )
    assert "costs" in result
    assert result["input_tokens"] > 0
    assert result["estimated_output_tokens"] > 0
    assert result["costs"]["estimated_total_cents"] >= 0
    assert result["task_type"] in ("chat", "code", "reasoning", "vision", "tool_use")


@pytest.mark.asyncio
async def test_predict_cost_unknown_model(db_session):
    from app.services.cost_engine import predict_cost
    result = await predict_cost(
        db_session,
        "nonexistent-model",
        [{"role": "user", "content": "test"}],
    )
    assert "error" in result


@pytest.mark.asyncio
async def test_compare_models(db_session):
    from app.services.cost_engine import compare_models
    result = await compare_models(
        db_session,
        [{"role": "user", "content": "Write code"}],
        max_tokens=1000,
        optimize_for="cheapest",
    )
    assert len(result) > 0
    # Cheapest should be first
    assert result[0]["total_cost_cents"] <= result[-1]["total_cost_cents"]
    # At least one should be Pareto optimal
    assert any(m["pareto_optimal"] for m in result)


@pytest.mark.asyncio
async def test_pareto_optimal_marking(db_session):
    from app.services.cost_engine import compare_models
    result = await compare_models(
        db_session,
        [{"role": "user", "content": "Hello"}],
        max_tokens=100,
    )
    pareto = [m for m in result if m["pareto_optimal"]]
    # Pareto-optimal models should not be dominated
    for m in pareto:
        for other in result:
            if other["model_id"] == m["model_id"]:
                continue
            # No other model should be both cheaper AND higher quality
            dominated = (
                other["total_cost_cents"] < m["total_cost_cents"]
                and other["quality_score"] >= m["quality_score"]
            )
            assert not dominated, f"{m['model_id']} is dominated by {other['model_id']}"


# ─── API Keys ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_api_key(client):
    resp = await client.post("/v1/keys", json={"name": "test-key"})
    assert resp.status_code == 201
    data = resp.json()
    assert "key" in data
    assert data["key"].startswith("sg-")
    assert data["key_prefix"].startswith("sg-")
    assert data["name"] == "test-key"


@pytest.mark.asyncio
async def test_list_keys(client):
    # Create a key first
    await client.post("/v1/keys", json={"name": "key1"})
    await client.post("/v1/keys", json={"name": "key2"})
    resp = await client.get("/v1/keys")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] >= 2


@pytest.mark.asyncio
async def test_delete_key(client):
    create_resp = await client.post("/v1/keys", json={"name": "to-delete"})
    key_id = create_resp.json()["id"]
    del_resp = await client.delete(f"/v1/keys/{key_id}")
    assert del_resp.status_code == 200
    # Verify it's gone
    get_resp = await client.get(f"/v1/keys/{key_id}")
    assert get_resp.status_code == 404


@pytest.mark.asyncio
async def test_update_key_budget(client):
    create_resp = await client.post("/v1/keys", json={"name": "budget-key"})
    key_id = create_resp.json()["id"]
    update_resp = await client.put(
        f"/v1/keys/{key_id}",
        json={"monthly_budget_cents": 5000},
    )
    assert update_resp.status_code == 200
    # Verify
    get_resp = await client.get(f"/v1/keys/{key_id}")
    assert get_resp.json()["monthly_budget_cents"] == 5000


@pytest.mark.asyncio
async def test_reset_spend(client):
    create_resp = await client.post("/v1/keys", json={"name": "reset-key"})
    key_id = create_resp.json()["id"]
    reset_resp = await client.post(f"/v1/keys/{key_id}/reset")
    assert reset_resp.status_code == 200


# ─── Models ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_models(client):
    resp = await client.get("/v1/models")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] >= 30  # we have 34+ models
    assert all("model_id" in m for m in data["models"])


@pytest.mark.asyncio
async def test_list_models_by_category(client):
    resp = await client.get("/v1/models?category=frontier")
    assert resp.status_code == 200
    data = resp.json()
    assert all(m["category"] == "frontier" for m in data["models"])


# ─── Predict/Compare API ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_predict_endpoint(client):
    resp = await client.post("/v1/predict", json={
        "model": "gpt-4o",
        "messages": [{"role": "user", "content": "Hello"}],
        "max_tokens": 500,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "input_tokens" in data
    assert "costs" in data


@pytest.mark.asyncio
async def test_compare_endpoint(client):
    resp = await client.post("/v1/compare", json={
        "messages": [{"role": "user", "content": "Write code"}],
        "max_tokens": 500,
        "optimize_for": "cheapest",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] > 0


# ─── Admin ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_admin_list_providers(client):
    resp = await client.get("/admin/providers")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] >= 18  # 18 seeded providers


@pytest.mark.asyncio
async def test_admin_list_models(client):
    resp = await client.get("/admin/models")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] >= 30


@pytest.mark.asyncio
async def test_admin_create_provider(client):
    resp = await client.post("/admin/providers", json={
        "name": "test-provider",
        "display_name": "Test Provider",
        "base_url": "https://api.test.com/v1",
        "api_key_env": "TEST_API_KEY",
        "priority": 50,
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "test-provider"


@pytest.mark.asyncio
async def test_admin_create_model(client):
    # First get a provider ID
    providers_resp = await client.get("/admin/providers")
    provider_id = providers_resp.json()["providers"][0]["id"]

    resp = await client.post("/admin/models", json={
        "model_id": "test-model-v1",
        "display_name": "Test Model",
        "provider_id": provider_id,
        "prompt_price": "0.000001",
        "completion_price": "0.000003",
        "context_window": 32000,
        "max_output": 4096,
        "quality_score": 7.0,
        "category": "general",
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["model_id"] == "test-model-v1"


@pytest.mark.asyncio
async def test_admin_stats(client):
    resp = await client.get("/admin/stats")
    assert resp.status_code == 200
    data = resp.json()
    assert "providers" in data
    assert "models" in data
    assert data["providers"] >= 18


# ─── Rate Limiter ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_rate_limiter_basic():
    from app.services.rate_limiter import rate_limiter
    # Reset state
    rate_limiter._windows.clear()
    # Should allow first request
    allowed, count, _ = rate_limiter.check(1, 5)
    assert allowed
    assert count == 1
    # Fill up to limit
    for _ in range(4):
        rate_limiter.check(1, 5)
    allowed, count, _ = rate_limiter.check(1, 5)
    assert not allowed  # 6th request should be blocked


@pytest.mark.asyncio
async def test_rate_limiter_per_key():
    from app.services.rate_limiter import rate_limiter
    rate_limiter._windows.clear()
    # Key 1 uses 3 requests
    for _ in range(3):
        rate_limiter.check(1, 5)
    # Key 2 should have separate window
    allowed, count, _ = rate_limiter.check(2, 5)
    assert allowed
    assert count == 1


# ─── Streaming Usage ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_streaming_tracker():
    from app.services.streaming import StreamingUsageTracker
    tracker = StreamingUsageTracker()

    # Simulate SSE chunks
    tracker.process_chunk('{"model":"gpt-4o","choices":[{"delta":{"content":"Hello"}}]}')
    tracker.process_chunk('{"choices":[{"delta":{"content":" world"}}]}')
    tracker.process_chunk('{"choices":[{"finish_reason":"stop"}],"usage":{"prompt_tokens":10,"completion_tokens":2}}')

    usage = tracker.get_usage()
    assert usage["prompt_tokens"] == 10
    assert usage["completion_tokens"] == 2
    assert usage["finish_reason"] == "stop"
    assert usage["estimated"] is False


@pytest.mark.asyncio
async def test_streaming_tracker_estimated():
    from app.services.streaming import StreamingUsageTracker
    tracker = StreamingUsageTracker()
    # Chunks without usage info
    for i in range(10):
        tracker.process_chunk(f'{{"choices":[{{"delta":{{"content":"chunk {i}"}}}}]}}')

    usage = tracker.get_usage()
    assert usage["completion_tokens"] > 0  # estimated from content chunks
    assert usage["estimated"] is True


# ─── Provider Router ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_should_retry():
    from app.services.provider_router import should_retry
    assert should_retry(429, 0) is True
    assert should_retry(503, 0) is True
    assert should_retry(400, 0) is False  # client error, don't retry
    assert should_retry(429, 2) is False  # max retries reached


# ─── Pricing ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_pricing_seeded(db_session):
    from app.services.pricing import MODELS, PROVIDERS
    assert len(PROVIDERS) >= 18
    assert len(MODELS) >= 30
    # Verify no duplicate model IDs
    model_ids = [m["model_id"] for m in MODELS]
    assert len(model_ids) == len(set(model_ids)), "Duplicate model IDs found"
