#!/usr/bin/env python3
"""SwiftGate SDK demo — shows all features in one script."""

import asyncio
from swiftgate import SwiftGateClient


async def main():
    client = SwiftGateClient(base_url="http://localhost:8000")

    # 1. List models
    models = await client.list_models()
    print(f"Available models: {len(models['models'])}")

    # 2. Predict cost
    pred = await client.predict(
        model="gpt-4o",
        messages=[{"role": "user", "content": "Write a REST API in Python"}],
        max_tokens=2000,
    )
    print(f"\nPredicted cost: {pred['formatted']['estimated_total']}")
    print(f"  Input tokens: {pred['input_tokens']}")
    print(f"  Task type: {pred['task_type']}")

    # 3. Quality-per-dollar routing
    route = await client.quality_route(
        messages=[{"role": "user", "content": "Write a REST API in Python"}],
        max_budget_cents=50,
    )
    print(f"\nQuality-per-dollar routing ({route['count']} models):")
    for m in route["models"][:3]:
        star = "★" if m.get("pareto_optimal") else " "
        print(f"  {star} {m['display_name']:25s} Q={m['quality_score']:.1f} QPD={m['qpd_score']}")

    # 4. Quality leaderboard
    lb = await client.quality_leaderboard(task_type="code")
    print(f"\nCode leaderboard ({len(lb['leaderboard'])} models):")
    for entry in lb["leaderboard"][:5]:
        print(f"  {entry['model_id']:25s} score={entry['empirical_score']:.1f}")

    # 5. PII detection
    pii = await client.pii_detect(text="Contact me at john@example.com or 555-123-4567")
    print(f"\nPII detected: {pii['total_found']} entities: {pii['types_found']}")

    # 6. Cache stats
    cache = await client.cache_stats()
    print(f"\nCache: {cache['active_entries']} entries, {cache['total_hits']} hits")

    # 7. Agent management
    agents = await client.list_agents()
    print(f"\nAgents: {agents['count']} registered")

    await client.close()
    print("\n✅ All SDK features working!")


if __name__ == "__main__":
    asyncio.run(main())
