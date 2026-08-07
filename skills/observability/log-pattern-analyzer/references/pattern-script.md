# Log Pattern Analyzer Script

The agent extracts this code and runs it in the sandbox.

```python
#!/usr/bin/env python3
"""Analyze log lines for frequency patterns and anomalies.

Given a file with log lines (one per line, or JSON array), identifies:
1. Most frequent patterns (template extraction)
2. Anomalous patterns (rare but potentially important)
3. Error clustering (group errors by similarity)
4. Time-based frequency changes (if timestamps present)

Usage:
    python3 /tmp/log_analyzer.py --data-file /tmp/logs.json [--top 20] [--min-count 2]

Input format (JSON array of log lines):
{
  "lines": [
    {"timestamp": "2026-08-06T14:02:00Z", "message": "Connection refused to redis:6379", "level": "ERROR"},
    {"timestamp": "2026-08-06T14:02:01Z", "message": "Connection refused to redis:6379", "level": "ERROR"},
    {"timestamp": "2026-08-06T14:02:02Z", "message": "Request completed in 150ms", "level": "INFO"},
    ...
  ]
}

Or plain text (one message per line):
{
  "lines": ["Connection refused to redis:6379", "Request completed in 150ms", ...]
}
"""
import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime

import pandas as pd


def normalize_message(msg):
    """Extract a pattern template by replacing variable parts."""
    # Replace IPs
    pattern = re.sub(r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}(:\d+)?', '<IP>', msg)
    # Replace UUIDs
    pattern = re.sub(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', '<UUID>', pattern)
    # Replace hex strings (trace IDs, span IDs)
    pattern = re.sub(r'\b[0-9a-f]{16,64}\b', '<HEX>', pattern)
    # Replace numbers (but keep short ones that might be status codes)
    pattern = re.sub(r'\b\d{5,}\b', '<NUM>', pattern)
    # Replace timestamps
    pattern = re.sub(r'\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}[.\d]*Z?', '<TS>', pattern)
    # Replace durations
    pattern = re.sub(r'\d+(\.\d+)?(ms|s|m|h)', '<DUR>', pattern)
    # Replace paths with IDs
    pattern = re.sub(r'/[0-9a-f-]{20,}', '/<ID>', pattern)
    return pattern.strip()


def analyze_patterns(lines, top_n=20, min_count=2):
    """Group log lines by normalized pattern and count."""
    patterns = Counter()
    examples = {}
    
    for line in lines:
        msg = line.get("message", line) if isinstance(line, dict) else str(line)
        pattern = normalize_message(msg)
        patterns[pattern] += 1
        if pattern not in examples:
            examples[pattern] = msg  # Keep first example

    results = []
    for pattern, count in patterns.most_common(top_n):
        if count >= min_count:
            results.append({
                "pattern": pattern,
                "count": count,
                "percentage": round(count / len(lines) * 100, 2),
                "example": examples[pattern][:200],
            })
    return results


def analyze_errors(lines):
    """Separate and cluster error-level messages."""
    errors = []
    for line in lines:
        if isinstance(line, dict):
            level = line.get("level", "").upper()
            if level in ("ERROR", "FATAL", "CRITICAL", "WARN", "WARNING"):
                errors.append(line)
        else:
            msg = str(line).lower()
            if any(k in msg for k in ["error", "exception", "fatal", "failed", "timeout"]):
                errors.append({"message": str(line), "level": "ERROR"})

    error_patterns = Counter()
    for e in errors:
        msg = e.get("message", str(e))
        pattern = normalize_message(msg)
        error_patterns[pattern] += 1

    return {
        "total_errors": len(errors),
        "error_rate_pct": round(len(errors) / max(len(lines), 1) * 100, 2),
        "top_error_patterns": [
            {"pattern": p, "count": c, "pct_of_errors": round(c / max(len(errors), 1) * 100, 1)}
            for p, c in error_patterns.most_common(10)
        ],
    }


def analyze_time_distribution(lines):
    """Check if errors cluster in specific time windows."""
    timestamps = []
    for line in lines:
        if isinstance(line, dict) and "timestamp" in line:
            try:
                ts = line["timestamp"]
                if isinstance(ts, str):
                    ts = ts.replace("Z", "+00:00")
                    dt = datetime.fromisoformat(ts)
                    timestamps.append(dt)
            except (ValueError, TypeError):
                continue

    if len(timestamps) < 10:
        return {"has_timestamps": False, "note": "Insufficient timestamps for time analysis"}

    df = pd.DataFrame({"ts": timestamps})
    df["minute"] = df["ts"].dt.floor("min")
    per_minute = df.groupby("minute").size()

    return {
        "has_timestamps": True,
        "time_range": {
            "start": per_minute.index.min().isoformat(),
            "end": per_minute.index.max().isoformat(),
            "duration_minutes": len(per_minute),
        },
        "rate": {
            "mean_per_minute": round(per_minute.mean(), 1),
            "max_per_minute": int(per_minute.max()),
            "max_at": per_minute.idxmax().isoformat(),
            "stddev": round(per_minute.std(), 1),
        },
        "spike_detected": bool(per_minute.max() > per_minute.mean() + 2 * per_minute.std()),
    }


def main():
    parser = argparse.ArgumentParser(description="Log pattern frequency analyzer")
    parser.add_argument("--data-file", required=True)
    parser.add_argument("--top", type=int, default=20, help="Top N patterns to show")
    parser.add_argument("--min-count", type=int, default=2, help="Minimum count to report")
    args = parser.parse_args()

    try:
        with open(args.data_file) as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(1)

    lines = data.get("lines", [])
    if not lines:
        print(json.dumps({"error": "No log lines in data file"}))
        sys.exit(1)

    report = {
        "analysis": "log-pattern",
        "total_lines": len(lines),
        "unique_patterns": len(set(
            normalize_message(l.get("message", str(l)) if isinstance(l, dict) else str(l))
            for l in lines
        )),
        "top_patterns": analyze_patterns(lines, args.top, args.min_count),
        "error_analysis": analyze_errors(lines),
        "time_analysis": analyze_time_distribution(lines),
        "interpretation": {},
    }

    # Auto-interpret
    error_rate = report["error_analysis"]["error_rate_pct"]
    unique_ratio = report["unique_patterns"] / max(len(lines), 1)

    if error_rate > 20:
        report["interpretation"]["severity"] = "HIGH — >20% of lines are errors"
    elif error_rate > 5:
        report["interpretation"]["severity"] = "MEDIUM — 5-20% error rate"
    else:
        report["interpretation"]["severity"] = "LOW — <5% error rate"

    if unique_ratio > 0.8:
        report["interpretation"]["pattern_diversity"] = "HIGH — logs are mostly unique (possible high-cardinality issue)"
    elif unique_ratio < 0.1:
        report["interpretation"]["pattern_diversity"] = "LOW — few patterns dominate (normal, healthy structure)"
    else:
        report["interpretation"]["pattern_diversity"] = "MEDIUM — moderate pattern variety"

    time_info = report["time_analysis"]
    if time_info.get("spike_detected"):
        report["interpretation"]["temporal"] = f"SPIKE DETECTED at {time_info['rate']['max_at']} ({time_info['rate']['max_per_minute']} lines/min vs mean {time_info['rate']['mean_per_minute']})"

    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
```
