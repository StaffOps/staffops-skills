# Cardinality Explosion Finder Script

The agent extracts this code and runs it in the sandbox.

```python
#!/usr/bin/env python3
"""Analyze TSDB status data to find the source of a cardinality explosion.

Given TSDB status from VictoriaMetrics (top series by metric, label, label-value pair),
identifies the most likely explosion source and suggests remediation.

Usage:
    python3 /tmp/cardinality.py --data-file /tmp/tsdb_status.json

Input format (from VictoriaMetrics /api/v1/status/tsdb):
{
  "seriesCountByMetricName": [
    {"name": "http_server_request_duration_seconds_bucket", "value": 45000},
    {"name": "istio_requests_total", "value": 32000},
    ...
  ],
  "seriesCountByLabelName": [
    {"name": "pod", "value": 180000},
    {"name": "instance", "value": 95000},
    ...
  ],
  "seriesCountByLabelValuePair": [
    {"name": "job=kubernetes-pods", "value": 120000},
    {"name": "namespace=dpm", "value": 45000},
    ...
  ],
  "totalSeries": 2500000,
  "totalLabelValuePairs": 850000
}
"""
import argparse
import json
import sys


# Known-safe high-cardinality labels (expected to be high, not actionable)
EXPECTED_HIGH_CARDINALITY = {"pod", "instance", "node", "container_id", "uid", "pod_ip"}

# Histogram suffixes that multiply series count
HISTOGRAM_SUFFIXES = ("_bucket", "_sum", "_count")

# Known problematic patterns
EXPLOSION_PATTERNS = [
    {"pattern": "user_id", "reason": "Unbounded user identifier as label", "fix": "Remove from labels, use logs/traces for per-user data"},
    {"pattern": "request_id", "reason": "Per-request identifier", "fix": "Remove immediately — every request creates a new series"},
    {"pattern": "trace_id", "reason": "Trace ID as metric label", "fix": "Use exemplars instead of labels for trace correlation"},
    {"pattern": "url", "reason": "Raw URL path with IDs", "fix": "Use http.route template instead of raw path"},
    {"pattern": "error_message", "reason": "Unique error text as label", "fix": "Use error.type enum instead"},
    {"pattern": "timestamp", "reason": "Time as label value", "fix": "Remove — time is the X axis, not a label"},
    {"pattern": "ip_address", "reason": "Client IP as label", "fix": "Remove from metrics, use logs for per-IP analysis"},
    {"pattern": "email", "reason": "PII as label", "fix": "Remove immediately — PII should never be in metrics"},
]


def analyze_metrics(data):
    """Identify metrics contributing most to cardinality."""
    metrics = data.get("seriesCountByMetricName", [])
    total = data.get("totalSeries", 1)
    
    results = []
    for m in metrics[:20]:
        name = m["name"]
        count = m["value"]
        pct = round(count / total * 100, 2)
        
        is_histogram = any(name.endswith(s) for s in HISTOGRAM_SUFFIXES)
        # Histograms naturally have high series count (N labels × M buckets)
        # Flag only if disproportionately large
        flagged = pct > 5 or (not is_histogram and count > 10000)
        
        results.append({
            "metric": name,
            "series_count": count,
            "pct_of_total": pct,
            "is_histogram": is_histogram,
            "flagged": flagged,
            "note": "Histogram — high count expected but check bucket count" if is_histogram and flagged else None,
        })
    return results


def analyze_labels(data):
    """Identify labels driving cardinality."""
    labels = data.get("seriesCountByLabelName", [])
    total = data.get("totalSeries", 1)
    
    results = []
    for l in labels[:20]:
        name = l["name"]
        count = l["value"]
        pct = round(count / total * 100, 2)
        
        is_expected = name in EXPECTED_HIGH_CARDINALITY or name.startswith("__")
        is_problematic = any(p["pattern"] in name.lower() for p in EXPLOSION_PATTERNS)
        problem = next((p for p in EXPLOSION_PATTERNS if p["pattern"] in name.lower()), None)
        
        results.append({
            "label": name,
            "series_count": count,
            "pct_of_total": pct,
            "expected_high": is_expected,
            "problematic": is_problematic,
            "reason": problem["reason"] if problem else None,
            "fix": problem["fix"] if problem else None,
        })
    return results


def analyze_pairs(data):
    """Identify label=value pairs with highest series count."""
    pairs = data.get("seriesCountByLabelValuePair", [])
    total = data.get("totalSeries", 1)
    
    results = []
    for p in pairs[:20]:
        name = p["name"]
        count = p["value"]
        pct = round(count / total * 100, 2)
        
        results.append({
            "pair": name,
            "series_count": count,
            "pct_of_total": pct,
        })
    return results


def generate_recommendations(metrics_analysis, labels_analysis):
    """Generate actionable recommendations."""
    recs = []
    
    # Check for problematic labels
    for l in labels_analysis:
        if l["problematic"]:
            recs.append({
                "priority": "CRITICAL",
                "label": l["label"],
                "reason": l["reason"],
                "fix": l["fix"],
                "impact_series": l["series_count"],
            })
    
    # Check for disproportionate histograms
    for m in metrics_analysis:
        if m["flagged"] and m["is_histogram"] and m["pct_of_total"] > 10:
            recs.append({
                "priority": "HIGH",
                "metric": m["metric"],
                "reason": f"Histogram consuming {m['pct_of_total']}% of total series",
                "fix": "Reduce bucket count, or use streaming aggregation to pre-aggregate",
                "impact_series": m["series_count"],
            })
    
    # Check for unexpected non-histogram metrics with >5% share
    for m in metrics_analysis:
        if m["flagged"] and not m["is_histogram"] and m["pct_of_total"] > 5:
            recs.append({
                "priority": "HIGH",
                "metric": m["metric"],
                "reason": f"Non-histogram metric with {m['pct_of_total']}% of total — likely has a high-cardinality label",
                "fix": "Inspect label set with label_values() — find the unbounded one",
                "impact_series": m["series_count"],
            })
    
    recs.sort(key=lambda x: {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2}.get(x["priority"], 3))
    return recs


def main():
    parser = argparse.ArgumentParser(description="Cardinality explosion source finder")
    parser.add_argument("--data-file", required=True)
    args = parser.parse_args()

    try:
        with open(args.data_file) as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(1)

    total = data.get("totalSeries", 0)
    if total == 0:
        print(json.dumps({"error": "No totalSeries in data", "hint": "Query /api/v1/status/tsdb from VictoriaMetrics"}))
        sys.exit(1)

    metrics_analysis = analyze_metrics(data)
    labels_analysis = analyze_labels(data)
    pairs_analysis = analyze_pairs(data)
    recommendations = generate_recommendations(metrics_analysis, labels_analysis)

    report = {
        "analysis": "cardinality-explosion",
        "total_series": total,
        "total_label_value_pairs": data.get("totalLabelValuePairs", 0),
        "top_metrics": metrics_analysis[:10],
        "top_labels": labels_analysis[:10],
        "top_pairs": pairs_analysis[:10],
        "recommendations": recommendations,
        "conclusion": {
            "critical_issues": len([r for r in recommendations if r["priority"] == "CRITICAL"]),
            "high_issues": len([r for r in recommendations if r["priority"] == "HIGH"]),
            "top_offender": recommendations[0] if recommendations else None,
            "summary": (
                f"Found {len(recommendations)} cardinality issues. "
                f"Top offender: {recommendations[0]['label'] if 'label' in recommendations[0] else recommendations[0].get('metric', 'unknown')} "
                f"({recommendations[0]['impact_series']} series)."
                if recommendations else
                "No obvious cardinality explosion source found. Series distribution looks healthy."
            ),
        },
    }
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
```
