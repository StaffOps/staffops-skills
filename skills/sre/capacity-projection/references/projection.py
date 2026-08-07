#!/usr/bin/env python3
"""Project resource exhaustion dates using linear regression on time-series data.

Given metric data over a time window (7d-30d), fits a linear trend and projects
when the value will breach a threshold (e.g., disk full, memory exhausted).

Usage:
    python3 projection.py --data-file /tmp/capacity_data.json

Input format:
{
  "dimensions": [
    {
      "name": "VictoriaMetrics storage (vmstorage-0)",
      "current_value": 850,
      "unit": "GB",
      "threshold": 1000,
      "values": [[timestamp, value], ...]
    }
  ]
}
"""
import argparse
import json
import sys
from datetime import datetime, timedelta

import numpy as np


def linear_regression(timestamps, values):
    """Simple linear regression returning slope, intercept, r_squared."""
    n = len(timestamps)
    if n < 3:
        return None
    x = np.array(timestamps, dtype=float)
    y = np.array(values, dtype=float)
    # Normalize x to hours from start for numerical stability
    x_start = x[0]
    x_norm = (x - x_start) / 3600  # hours

    x_mean, y_mean = x_norm.mean(), y.mean()
    ss_xx = ((x_norm - x_mean) ** 2).sum()
    ss_xy = ((x_norm - x_mean) * (y - y_mean)).sum()

    if ss_xx == 0:
        return None

    slope = ss_xy / ss_xx  # units per hour
    intercept = y_mean - slope * x_mean

    # R-squared
    y_pred = slope * x_norm + intercept
    ss_res = ((y - y_pred) ** 2).sum()
    ss_tot = ((y - y_mean) ** 2).sum()
    r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0

    return {
        "slope_per_hour": slope,
        "slope_per_day": slope * 24,
        "intercept": intercept,
        "r_squared": round(r_squared, 4),
        "x_start": x_start,
    }


def project_exhaustion(regression, current_value, threshold, unit):
    """Project when the value will reach the threshold."""
    if regression is None:
        return {"projectable": False, "reason": "Insufficient data for regression"}

    slope_per_hour = regression["slope_per_hour"]

    if slope_per_hour <= 0:
        return {
            "projectable": True,
            "trend": "DECREASING" if slope_per_hour < 0 else "FLAT",
            "exhaustion": "NEVER (at current trend)",
            "days_to_exhaustion": None,
            "headroom_pct": round((threshold - current_value) / threshold * 100, 1),
        }

    remaining = threshold - current_value
    if remaining <= 0:
        return {
            "projectable": True,
            "trend": "ALREADY_BREACHED",
            "exhaustion": "NOW",
            "days_to_exhaustion": 0,
            "headroom_pct": 0,
        }

    hours_to_exhaustion = remaining / slope_per_hour
    days = hours_to_exhaustion / 24
    exhaust_date = datetime.now() + timedelta(hours=hours_to_exhaustion)

    return {
        "projectable": True,
        "trend": "INCREASING",
        "growth_per_day": round(slope_per_hour * 24, 2),
        "growth_per_day_unit": f"{unit}/day",
        "days_to_exhaustion": round(days, 1),
        "exhaustion_date": exhaust_date.strftime("%Y-%m-%d"),
        "headroom_pct": round(remaining / threshold * 100, 1),
        "confidence": "HIGH" if regression["r_squared"] > 0.8 else "MEDIUM" if regression["r_squared"] > 0.5 else "LOW",
        "r_squared": regression["r_squared"],
    }


def classify_urgency(days_to_exhaustion):
    """Classify how urgent action is."""
    if days_to_exhaustion is None:
        return "NONE"
    if days_to_exhaustion <= 0:
        return "CRITICAL_NOW"
    if days_to_exhaustion <= 7:
        return "CRITICAL"
    if days_to_exhaustion <= 30:
        return "WARNING"
    if days_to_exhaustion <= 90:
        return "WATCH"
    return "HEALTHY"


def main():
    parser = argparse.ArgumentParser(description="Capacity exhaustion projection")
    parser.add_argument("--data-file", required=True, help="Path to JSON input file")
    args = parser.parse_args()

    try:
        with open(args.data_file) as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(1)

    dimensions = data.get("dimensions", [])
    if not dimensions:
        print(json.dumps({"error": "No dimensions in data file"}))
        sys.exit(1)

    results = []
    worst_urgency = "HEALTHY"
    urgency_order = ["HEALTHY", "WATCH", "WARNING", "CRITICAL", "CRITICAL_NOW"]

    for dim in dimensions:
        name = dim.get("name", "unknown")
        current = dim.get("current_value", 0)
        unit = dim.get("unit", "")
        threshold = dim.get("threshold", 0)
        values = dim.get("values", [])

        timestamps = [v[0] for v in values]
        vals = [float(v[1]) for v in values]

        regression = linear_regression(timestamps, vals)
        projection = project_exhaustion(regression, current, threshold, unit)
        urgency = classify_urgency(projection.get("days_to_exhaustion"))

        if urgency_order.index(urgency) > urgency_order.index(worst_urgency):
            worst_urgency = urgency

        results.append({
            "dimension": name,
            "current": f"{current} {unit}",
            "threshold": f"{threshold} {unit}",
            "utilization_pct": round(current / threshold * 100, 1) if threshold > 0 else 0,
            "projection": projection,
            "urgency": urgency,
        })

    report = {
        "analysis": "capacity-projection",
        "dimensions_analyzed": len(results),
        "results": results,
        "overall": {
            "worst_urgency": worst_urgency,
            "action": {
                "HEALTHY": "No action needed. All dimensions have >90 days headroom.",
                "WATCH": "Plan capacity expansion within the quarter.",
                "WARNING": "Capacity expansion needed within 30 days. Create ticket.",
                "CRITICAL": "Capacity exhausts within 7 days. Immediate action required.",
                "CRITICAL_NOW": "Threshold already breached. Investigate immediately.",
            }.get(worst_urgency, "Unknown"),
        },
    }
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
