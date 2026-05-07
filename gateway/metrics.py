"""CloudWatch Embedded Metric Format (EMF) module.

Emits metrics via structured logs that CloudWatch automatically
extracts as custom metrics. No put_metric_data API calls needed.
"""

import json
import logging
import time

logger = logging.getLogger(__name__)

NAMESPACE = "Gateway"
LOG_GROUP = "/ecs/gateway"


def _emit_emf(metrics: dict, dimensions: list[dict], properties: dict | None = None) -> None:
    """Emit a CloudWatch EMF structured log entry.

    Args:
        metrics: dict of metric_name -> value
        dimensions: list of dimension dicts [{name: value}]
        properties: additional non-metric fields to include in the log
    """
    metric_definitions = []
    for name, value in metrics.items():
        unit = "Milliseconds" if "latency" in name.lower() else "None"
        if "count" in name.lower() or "request" in name.lower():
            unit = "Count"
        if "rate" in name.lower() or "score" in name.lower():
            unit = "None"
        metric_definitions.append({"Name": name, "Unit": unit})

    dimension_sets = [[d["Name"] for d in dim_group] for dim_group in [dimensions]]

    emf_log = {
        "_aws": {
            "Timestamp": int(time.time() * 1000),
            "CloudWatchMetrics": [
                {
                    "Namespace": NAMESPACE,
                    "Dimensions": dimension_sets,
                    "Metrics": metric_definitions,
                }
            ],
        },
    }

    # Add dimensions as top-level fields
    for dim in dimensions:
        emf_log[dim["Name"]] = dim["Value"]

    # Add metric values as top-level fields
    for name, value in metrics.items():
        emf_log[name] = value

    # Add extra properties
    if properties:
        emf_log.update(properties)

    # EMF logs must go to stdout (not through Python logging hierarchy)
    print(json.dumps(emf_log), flush=True)


def emit_routing_decision(
    selected: str,
    reason: str,
    bedrock_score: float,
    openai_score: float,
    bedrock_healthy: bool,
    openai_healthy: bool,
    bedrock_error_rate: float,
    openai_error_rate: float,
    bedrock_avg_latency_ms: float,
    openai_avg_latency_ms: float,
) -> None:
    """Emit routing decision metrics via EMF."""
    # Metric for provider selection (1 = selected)
    _emit_emf(
        metrics={
            "ProviderSelected": 1,
            "HealthScore": bedrock_score if selected == "bedrock" else openai_score,
        },
        dimensions=[
            {"Name": "Provider", "Value": selected},
            {"Name": "Reason", "Value": reason},
        ],
        properties={
            "event": "routing_decision",
            "bedrock_score": round(bedrock_score, 2),
            "openai_score": round(openai_score, 2),
            "bedrock_healthy": bedrock_healthy,
            "openai_healthy": openai_healthy,
            "bedrock_error_rate": round(bedrock_error_rate, 4),
            "openai_error_rate": round(openai_error_rate, 4),
            "bedrock_avg_latency_ms": round(bedrock_avg_latency_ms, 2),
            "openai_avg_latency_ms": round(openai_avg_latency_ms, 2),
        },
    )

    # Emit per-provider health metrics (both providers every decision)
    _emit_emf(
        metrics={
            "AvgLatency": bedrock_avg_latency_ms,
            "ErrorRate": bedrock_error_rate,
            "HealthScore": bedrock_score,
        },
        dimensions=[{"Name": "Provider", "Value": "bedrock"}],
    )
    _emit_emf(
        metrics={
            "AvgLatency": openai_avg_latency_ms,
            "ErrorRate": openai_error_rate,
            "HealthScore": openai_score,
        },
        dimensions=[{"Name": "Provider", "Value": "openai"}],
    )


def emit_request_metrics(
    provider: str,
    latency_ms: float,
    status_code: int,
    is_fallback: bool = False,
) -> None:
    """Emit per-request metrics via EMF."""
    metrics = {
        "RequestLatency": round(latency_ms, 2),
        "RequestCount": 1,
    }

    if status_code >= 500:
        metrics["ErrorCount"] = 1
    else:
        metrics["ErrorCount"] = 0

    if is_fallback:
        metrics["FailoverCount"] = 1
    else:
        metrics["FailoverCount"] = 0

    _emit_emf(
        metrics=metrics,
        dimensions=[{"Name": "Provider", "Value": provider}],
        properties={
            "status_code": status_code,
            "is_fallback": is_fallback,
        },
    )
