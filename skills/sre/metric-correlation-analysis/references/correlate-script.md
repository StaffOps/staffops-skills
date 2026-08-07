# Metric Correlation Script

The agent copies this to a `.py` file in the sandbox and runs it.

```python
#!/usr/bin/env python3
"""Correlate metric data points to find co-occurring anomalies."""
import argparse
import json
import sys
from datetime import datetime
import numpy as np
import pandas as pd

def detect_anomalies(values, threshold=2.0):
    if len(values) < 5:
        return []
    df = pd.DataFrame(values, columns=["timestamp", "value"])
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    df = df.dropna()
    if df.empty or df["value"].std() == 0:
        return []
    mean, std = df["value"].mean(), df["value"].std()
    df["zscore"] = (df["value"] - mean) / std
    anomalies = df[df["zscore"].abs() > threshold]
    return [{"timestamp": r["timestamp"], "value": round(r["value"], 4),
             "zscore": round(r["zscore"], 2),
             "time": datetime.fromtimestamp(r["timestamp"]).isoformat()}
            for _, r in anomalies.iterrows()]

def find_correlations(all_anomalies, window=300):
    correlations = []
    metrics = list(all_anomalies.keys())
    for i, m1 in enumerate(metrics):
        for m2 in metrics[i+1:]:
            for a1 in all_anomalies[m1]:
                for a2 in all_anomalies[m2]:
                    delta = abs(a1["timestamp"] - a2["timestamp"])
                    if delta <= window:
                        correlations.append({"metric_a": m1, "metric_b": m2,
                            "time_a": a1["time"], "time_b": a2["time"],
                            "delta_seconds": delta,
                            "zscore_a": a1["zscore"], "zscore_b": a2["zscore"]})
    seen = set()
    unique = []
    for c in sorted(correlations, key=lambda x: abs(x["zscore_a"])+abs(x["zscore_b"]), reverse=True):
        key = (c["metric_a"], c["metric_b"], c["time_a"])
        if key not in seen:
            seen.add(key)
            unique.append(c)
    return unique[:20]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-file", required=True)
    parser.add_argument("--threshold", type=float, default=2.0)
    parser.add_argument("--window", type=int, default=300)
    args = parser.parse_args()
    try:
        with open(args.data_file) as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(1)
    metrics = data.get("metrics", [])
    if not metrics:
        print(json.dumps({"error": "No metrics in data file"}))
        sys.exit(1)
    all_anomalies = {}
    summaries = []
    for m in metrics:
        name = m.get("name", "unknown")
        labels = m.get("labels", {})
        values = m.get("values", [])
        label_str = ",".join(f'{k}="{v}"' for k, v in labels.items())
        full_name = f"{name}{{{label_str}}}" if labels else name
        anomalies = detect_anomalies(values, args.threshold)
        all_anomalies[full_name] = anomalies
        summaries.append({"metric": full_name, "data_points": len(values),
                          "anomalies_found": len(anomalies),
                          "anomaly_times": [a["time"] for a in anomalies[:5]]})
    correlations = find_correlations(all_anomalies, args.window)
    report = {"analysis": "metric-correlation",
              "params": {"threshold": args.threshold, "window_seconds": args.window, "metrics_count": len(metrics)},
              "per_metric": summaries, "correlations": correlations,
              "conclusion": {"correlated_pairs": len(correlations),
                             "strongest": correlations[0] if correlations else None,
                             "summary": f"{len(correlations)} pairs with co-occurring anomalies within {args.window}s." if correlations else "No temporal correlation found."}}
    print(json.dumps(report, indent=2))

if __name__ == "__main__":
    main()
```
