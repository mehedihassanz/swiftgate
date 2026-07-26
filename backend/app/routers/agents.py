"""Agent management router — budget orchestration for multi-agent workflows.

Endpoints:
  POST   /v1/agents                    — register/create an agent
  GET    /v1/agents                    — list all agents
  GET    /v1/agents/{agent_id}         — get agent details + spend
  PUT    /v1/agents/{agent_id}         — update agent (budget, name)
  POST   /v1/agents/{agent_id}/kill    — kill-switch (block all future requests)
  POST   /v1/agents/{agent_id}/pause   — temporarily pause
  POST   /v1/agents/{agent_id}/resume  — resume a paused agent
  POST   /v1/agents/{agent_id}/reset   — reset spend counter
  GET    /v1/agents/{agent_id}/trace   — get execution trace (events)
  POST   /v1/agents/{agent_id}/events  — record an agent event
"""
from __future__ import annotations

import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Agent, AgentEvent, UsageRecord
from app.auth import require_admin

router = APIRouter(prefix="/v1/agents", tags=["agents"])


# ─── Schemas ───────────────────────────────────────────────────────────

class AgentCreate(BaseModel):
    agent_id: str = Field(..., description="Unique agent identifier")
    name: str = "unnamed-agent"
    budget_cents: int | None = Field(None, description="Total budget in cents")
    alert_thresholds: str = "50,80,100"


class AgentUpdate(BaseModel):
    name: str | None = None
    budget_cents: int | None = None
    status: str | None = Field(None, pattern="^(active|paused|killed|budget_exceeded)$")
    alert_thresholds: str | None = None


class AgentEventCreate(BaseModel):
    event_type: str = Field(..., description="llm_call, tool_call, tool_result, handoff, error")
    model: str | None = None
    cost_cents: int = 0
    parent_agent_id: str | None = None
    trace_id: str | None = None
    message: str | None = None
    metadata: dict | None = None
    duration_ms: int = 0


# ─── Endpoints ─────────────────────────────────────────────────────────

@router.post("", status_code=201)
async def create_agent(body: AgentCreate, db: AsyncSession = Depends(get_db)):
    """Register a new agent for budget tracking."""
    existing = await db.execute(select(Agent).where(Agent.agent_id == body.agent_id))
    if existing.scalar_one_or_none():
        raise HTTPException(409, f"Agent '{body.agent_id}' already exists")

    agent = Agent(
        agent_id=body.agent_id,
        name=body.name,
        budget_cents=body.budget_cents,
        alert_thresholds=body.alert_thresholds,
    )
    db.add(agent)
    await db.commit()
    await db.refresh(agent)
    return _agent_to_dict(agent)


@router.get("")
async def list_agents(
    status_filter: str | None = Query(None, alias="status"),
    db: AsyncSession = Depends(get_db),
):
    """List all agents with spend summary."""
    stmt = select(Agent).order_by(desc(Agent.created_at))
    if status_filter:
        stmt = stmt.where(Agent.status == status_filter)

    result = await db.execute(stmt)
    agents = result.scalars().all()
    return {
        "agents": [_agent_to_dict(a) for a in agents],
        "count": len(agents),
    }


@router.get("/{agent_id}")
async def get_agent(agent_id: str, db: AsyncSession = Depends(get_db)):
    """Get agent details including recent usage."""
    result = await db.execute(select(Agent).where(Agent.agent_id == agent_id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(404, f"Agent '{agent_id}' not found")

    data = _agent_to_dict(agent)

    # Get recent usage
    usage_result = await db.execute(
        select(UsageRecord)
        .where(UsageRecord.agent_id == agent_id)
        .order_by(desc(UsageRecord.created_at))
        .limit(20)
    )
    data["recent_usage"] = [
        {
            "model": r.model_served,
            "prompt_tokens": r.prompt_tokens,
            "completion_tokens": r.completion_tokens,
            "cost_cents": r.total_cost_cents,
            "latency_ms": r.latency_ms,
            "status": r.status,
            "task_type": r.task_type,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in usage_result.scalars().all()
    ]

    return data


@router.put("/{agent_id}")
async def update_agent(agent_id: str, body: AgentUpdate, db: AsyncSession = Depends(get_db), _admin: bool = Depends(require_admin)):
    """Update agent settings."""
    result = await db.execute(select(Agent).where(Agent.agent_id == agent_id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(404, f"Agent '{agent_id}' not found")

    for field, val in body.model_dump(exclude_unset=True).items():
        setattr(agent, field, val)

    await db.commit()
    return {"updated": True, "agent_id": agent_id}


@router.post("/{agent_id}/kill")
async def kill_agent(agent_id: str, db: AsyncSession = Depends(get_db), _admin: bool = Depends(require_admin)):
    """Kill-switch — immediately blocks all future requests from this agent."""
    result = await db.execute(select(Agent).where(Agent.agent_id == agent_id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(404, f"Agent '{agent_id}' not found")

    agent.status = "killed"
    agent.killed_at = datetime.utcnow()
    await db.commit()
    return {"killed": True, "agent_id": agent_id, "killed_at": agent.killed_at.isoformat()}


@router.post("/{agent_id}/pause")
async def pause_agent(agent_id: str, db: AsyncSession = Depends(get_db), _admin: bool = Depends(require_admin)):
    """Temporarily pause an agent. Requests will be blocked until resumed."""
    result = await db.execute(select(Agent).where(Agent.agent_id == agent_id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(404, f"Agent '{agent_id}' not found")

    agent.status = "paused"
    await db.commit()
    return {"paused": True, "agent_id": agent_id}


@router.post("/{agent_id}/resume")
async def resume_agent(agent_id: str, db: AsyncSession = Depends(get_db), _admin: bool = Depends(require_admin)):
    """Resume a paused agent."""
    result = await db.execute(select(Agent).where(Agent.agent_id == agent_id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(404, f"Agent '{agent_id}' not found")

    if agent.status == "killed":
        agent.killed_reason = None
        agent.killed_at = None

    agent.status = "active"
    await db.commit()
    return {"resumed": True, "agent_id": agent_id}


@router.post("/{agent_id}/reset")
async def reset_agent_budget(agent_id: str, db: AsyncSession = Depends(get_db), _admin: bool = Depends(require_admin)):
    """Reset spend counter for a new billing cycle."""
    result = await db.execute(select(Agent).where(Agent.agent_id == agent_id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(404, f"Agent '{agent_id}' not found")

    agent.spend_cents = 0
    agent.request_count = 0
    agent.budget_reset_at = datetime.utcnow()
    if agent.status == "budget_exceeded":
        agent.status = "active"
    await db.commit()
    return {"reset": True, "agent_id": agent_id}


@router.get("/{agent_id}/trace")
async def get_agent_trace(
    agent_id: str,
    limit: int = Query(50, ge=1, le=500),
    trace_id: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """Get the execution trace (event log) for an agent."""
    stmt = (
        select(AgentEvent)
        .where(AgentEvent.agent_id == agent_id)
        .order_by(desc(AgentEvent.created_at))
        .limit(limit)
    )
    if trace_id:
        stmt = stmt.where(AgentEvent.trace_id == trace_id)

    result = await db.execute(stmt)
    events = result.scalars().all()
    return {
        "agent_id": agent_id,
        "events": [_event_to_dict(e) for e in reversed(events)],  # chronological order
        "count": len(events),
    }


@router.post("/{agent_id}/events", status_code=201)
async def record_event(
    agent_id: str,
    body: AgentEventCreate,
    db: AsyncSession = Depends(get_db),
):
    """Record an event in the agent's execution trace."""
    # Verify agent exists
    result = await db.execute(select(Agent).where(Agent.agent_id == agent_id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(404, f"Agent '{agent_id}' not found")

    event = AgentEvent(
        agent_id=agent_id,
        event_type=body.event_type,
        model=body.model,
        cost_cents=body.cost_cents,
        parent_agent_id=body.parent_agent_id,
        trace_id=body.trace_id,
        message=body.message,
        metadata_json=json.dumps(body.metadata) if body.metadata else None,
        duration_ms=body.duration_ms,
    )
    db.add(event)

    # Update agent spend
    agent.spend_cents += body.cost_cents
    agent.last_active = datetime.utcnow()

    # Check budget
    if agent.budget_cents and agent.spend_cents >= agent.budget_cents:
        agent.status = "budget_exceeded"

    await db.commit()
    return {"recorded": True, "event_id": event.id}


# ─── Helpers ───────────────────────────────────────────────────────────

def _agent_to_dict(a: Agent) -> dict:
    budget_used_pct = None
    if a.budget_cents and a.budget_cents > 0:
        budget_used_pct = round((a.spend_cents / a.budget_cents) * 100, 1)

    return {
        "id": a.id,
        "agent_id": a.agent_id,
        "name": a.name,
        "status": a.status,
        "budget_cents": a.budget_cents,
        "spend_cents": a.spend_cents,
        "budget_used_pct": budget_used_pct,
        "request_count": a.request_count,
        "killed_reason": a.killed_reason,
        "killed_at": a.killed_at.isoformat() if a.killed_at else None,
        "alert_thresholds": a.alert_thresholds,
        "created_at": a.created_at.isoformat() if a.created_at else None,
        "last_active": a.last_active.isoformat() if a.last_active else None,
    }


def _event_to_dict(e: AgentEvent) -> dict:
    return {
        "id": e.id,
        "event_type": e.event_type,
        "model": e.model,
        "cost_cents": e.cost_cents,
        "parent_agent_id": e.parent_agent_id,
        "trace_id": e.trace_id,
        "message": e.message,
        "metadata": json.loads(e.metadata_json) if e.metadata_json else None,
        "duration_ms": e.duration_ms,
        "created_at": e.created_at.isoformat() if e.created_at else None,
    }
