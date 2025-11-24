"""
Cost Monitoring API Endpoints

Provides endpoints for tracking and analyzing LLM costs over time.
"""

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from datetime import datetime, timedelta
from typing import Literal, List, Dict, Any
from collections import defaultdict
import csv
from io import StringIO

from app.services.interfaces.memory_store import IMemoryStore
from app.api.dependencies import get_memory_store


router = APIRouter(prefix="/costs")


@router.get("/stats")
async def get_cost_stats(
    persona_id: str = Query(..., description="Persona ID to get cost stats for"),
    period: Literal["7d", "30d", "90d", "all"] = Query(
        "30d", description="Time period for stats"
    ),
    memory_store: IMemoryStore = Depends(get_memory_store)
):
    """
    Get cost statistics for a persona over a time period.

    Returns aggregated cost data including:
    - Total cost and interaction count
    - Average cost per interaction
    - Daily cost breakdown
    - Cost breakdown by model
    - Token usage statistics
    - Projected monthly cost

    Args:
        persona_id: UUID of the persona
        period: Time period (7d, 30d, 90d, or all)
        memory_store: Memory store dependency

    Returns:
        Dictionary with cost statistics and breakdowns
    """
    # Calculate date range
    if period == "all":
        since = None
    else:
        days = int(period[:-1])
        since = datetime.utcnow() - timedelta(days=days)

    # Query interactions with cost data
    interactions = await memory_store.get_interactions_with_cost(
        persona_id=persona_id,
        since=since
    )

    # If no interactions, return empty stats
    if not interactions:
        return {
            "total_cost": 0.0,
            "total_interactions": 0,
            "avg_cost_per_interaction": 0.0,
            "total_tokens_in": 0,
            "total_tokens_out": 0,
            "projected_monthly_cost": 0.0,
            "daily_costs": [],
            "model_breakdown": []
        }

    # Aggregate by date and model
    daily_costs = aggregate_by_date(interactions)
    model_breakdown = aggregate_by_model(interactions)

    # Calculate metrics
    total_cost = sum(i.get_metadata().get("cost", 0) for i in interactions)
    total_tokens_in = sum(i.get_metadata().get("tokens_in", 0) for i in interactions)
    total_tokens_out = sum(i.get_metadata().get("tokens_out", 0) for i in interactions)
    avg_cost_per_interaction = total_cost / len(interactions) if interactions else 0

    # Project monthly cost (extrapolate from current data)
    if since:
        days_in_period = (datetime.utcnow() - since).days
        days_in_period = max(1, days_in_period)  # Avoid division by zero
    else:
        # For "all" period, calculate days since first interaction
        first_interaction_date = min(i.created_at for i in interactions)
        days_in_period = (datetime.utcnow() - first_interaction_date).days
        days_in_period = max(1, days_in_period)

    daily_avg = total_cost / days_in_period if days_in_period > 0 else 0
    projected_monthly = daily_avg * 30

    return {
        "total_cost": round(total_cost, 4),
        "total_interactions": len(interactions),
        "avg_cost_per_interaction": round(avg_cost_per_interaction, 6),
        "total_tokens_in": total_tokens_in,
        "total_tokens_out": total_tokens_out,
        "projected_monthly_cost": round(projected_monthly, 2),
        "daily_costs": daily_costs,
        "model_breakdown": model_breakdown
    }


@router.get("/export")
async def export_costs_csv(
    persona_id: str = Query(..., description="Persona ID to export costs for"),
    period: Literal["7d", "30d", "90d", "all"] = Query(
        "30d", description="Time period for export"
    ),
    memory_store: IMemoryStore = Depends(get_memory_store)
):
    """
    Export cost data as CSV file.

    Args:
        persona_id: UUID of the persona
        period: Time period (7d, 30d, 90d, or all)
        memory_store: Memory store dependency

    Returns:
        CSV file with cost data
    """
    # Calculate date range
    if period == "all":
        since = None
    else:
        days = int(period[:-1])
        since = datetime.utcnow() - timedelta(days=days)

    # Query interactions with cost data
    interactions = await memory_store.get_interactions_with_cost(
        persona_id=persona_id,
        since=since
    )

    # Generate CSV
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Date",
        "Reddit ID",
        "Subreddit",
        "Interaction Type",
        "Model",
        "Tokens In",
        "Tokens Out",
        "Cost"
    ])

    for i in interactions:
        metadata = i.get_metadata()
        writer.writerow([
            i.created_at.isoformat() if hasattr(i.created_at, "isoformat") else str(i.created_at),
            i.reddit_id,
            i.subreddit,
            i.interaction_type,
            metadata.get("model", "unknown"),
            metadata.get("tokens_in", 0),
            metadata.get("tokens_out", 0),
            metadata.get("cost", 0)
        ])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename=costs_{persona_id}_{period}.csv"
        }
    )


def aggregate_by_date(interactions: List) -> List[Dict[str, Any]]:
    """
    Group interactions by date and sum costs.

    Args:
        interactions: List of Interaction objects

    Returns:
        List of daily cost aggregations
    """
    daily = defaultdict(lambda: {"cost": 0.0, "interactions": 0, "tokens": 0})

    for interaction in interactions:
        # Extract date from created_at
        if hasattr(interaction.created_at, "date"):
            date = interaction.created_at.date().isoformat()
        else:
            # If created_at is already a string, parse it
            try:
                date_obj = datetime.fromisoformat(str(interaction.created_at))
                date = date_obj.date().isoformat()
            except (ValueError, AttributeError):
                date = str(interaction.created_at)[:10]  # Take first 10 chars (YYYY-MM-DD)

        metadata = interaction.get_metadata()
        daily[date]["cost"] += metadata.get("cost", 0)
        daily[date]["interactions"] += 1
        daily[date]["tokens"] += (
            metadata.get("tokens_in", 0) + metadata.get("tokens_out", 0)
        )

    # Convert to list and sort by date
    result = [
        {
            "date": date,
            "cost": round(stats["cost"], 4),
            "interactions": stats["interactions"],
            "tokens": stats["tokens"]
        }
        for date, stats in sorted(daily.items())
    ]

    return result


def aggregate_by_model(interactions: List) -> List[Dict[str, Any]]:
    """
    Group interactions by model and sum costs.

    Args:
        interactions: List of Interaction objects

    Returns:
        List of model cost aggregations
    """
    models = defaultdict(lambda: {"cost": 0.0, "count": 0})

    for interaction in interactions:
        metadata = interaction.get_metadata()
        model = metadata.get("model", "unknown")
        models[model]["cost"] += metadata.get("cost", 0)
        models[model]["count"] += 1

    # Calculate total for percentages
    total_cost = sum(m["cost"] for m in models.values())

    # Convert to list and sort by cost (highest first)
    result = [
        {
            "model": model,
            "cost": round(stats["cost"], 4),
            "count": stats["count"],
            "percentage": round(
                (stats["cost"] / total_cost * 100) if total_cost > 0 else 0, 1
            )
        }
        for model, stats in sorted(
            models.items(), key=lambda x: x[1]["cost"], reverse=True
        )
    ]

    return result
