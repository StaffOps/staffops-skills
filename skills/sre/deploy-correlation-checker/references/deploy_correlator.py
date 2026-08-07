#!/usr/bin/env python3
"""Cross-reference deploy timestamps with metric anomaly windows.

Given a list of recent deploys (from ArgoCD) and metric anomaly timestamps,
determines which deploy most likely caused the degradation.

Usage:
    python3 deploy_correlator.py --data-file /tmp/deploy_data.json [--window 30]

Input format:
{
  "deploys": [
    {"service": "service-a", "timestamp": "2026-08-06T14:00:00Z", "image_tag": "v2.3.1", "namespace": "default"},
    {"service": "service-b", "timestamp": "2026-08-06T13:45:00Z", "image_tag": "v1.8.0", "namespace": "default"}
  ],
  "anomalies": [
    {"metric": "http_error_rate", "started_at": "2026-08-06T14:03:00Z", "value": 0.12},
    {"metric": "latency_p99", "started_at": "2026-08-06T14:05:00Z", "value": 2.8}
  ]
}
"""
import argparse
import json
import sys
from datetime import datetime, timezone


def parse_ts(ts_str):
    """Parse ISO timestamp to datetime."""
    ts = ts_str.replace("Z", "+00:00")
    return datetime.fromisoformat(ts)


def correlate(deploys, anomalies, max_window_minutes=30):
    """Find deploys that precede anomalies within the correlation window."""
    results = []

    for anomaly in anomalies:
        anomaly_time = parse_ts(anomaly["started_at"])
        candidates = []

        for deploy in deploys:
            deploy_time = parse_ts(deploy["timestamp"])
            delta = (anomaly_time - deploy_time).total_seconds()

            # Deploy must be BEFORE the anomaly, within window
            if 0 < delta <= max_window_minutes * 60:
                candidates.append({
                    "service": deploy["service"],
                    "image_tag": deploy.get("image_tag", "unknown"),
                    "namespace": deploy.get("namespace", "unknown"),
                    "deployed_at": deploy["timestamp"],
                    "delta_seconds": int(delta),
                    "delta_human": f"{int(delta // 60)}m{int(delta % 60)}s",
                    "correlation_strength": round(1 - (delta / (max_window_minutes * 60)), 2),
                })

        # Sort by closest to anomaly (strongest correlation)
        candidates.sort(key=lambda x: x["delta_seconds"])

        results.append({
            "anomaly_metric": anomaly["metric"],
            "anomaly_started": anomaly["started_at"],
            "anomaly_value": anomaly.get("value"),
            "candidate_deploys": candidates,
            "most_likely": candidates[0] if candidates else None,
        })

    return results


def main():
    parser = argparse.ArgumentParser(description="Deploy ↔ anomaly correlation")
    parser.add_argument("--data-file", required=True, help="Path to JSON input file")
    parser.add_argument("--window", type=int, default=30,
                        help="Max minutes between deploy and anomaly (default: 30)")
    args = parser.parse_args()

    try:
        with open(args.data_file) as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(1)

    deploys = data.get("deploys", [])
    anomalies = data.get("anomalies", [])

    if not deploys:
        print(json.dumps({"error": "No deploys in data file",
                          "hint": "Check ArgoCD via gitops_apps_list"}))
        sys.exit(1)
    if not anomalies:
        print(json.dumps({"error": "No anomalies in data file",
                          "hint": "Run metric-correlation-analysis first"}))
        sys.exit(1)

    correlations = correlate(deploys, anomalies, args.window)

    # Summary
    all_candidates = set()
    for c in correlations:
        if c["most_likely"]:
            all_candidates.add(c["most_likely"]["service"])

    # Check if same deploy correlates with ALL anomalies
    common_cause = None
    if len(correlations) > 1:
        first_candidates = {c["most_likely"]["service"] for c in correlations if c["most_likely"]}
        if len(first_candidates) == 1:
            common_cause = first_candidates.pop()

    report = {
        "analysis": "deploy-correlation",
        "params": {
            "window_minutes": args.window,
            "deploys_checked": len(deploys),
            "anomalies_checked": len(anomalies),
        },
        "correlations": correlations,
        "conclusion": {
            "deploys_in_window": len(all_candidates),
            "common_cause_deploy": common_cause,
            "verdict": (
                f"STRONG: All {len(correlations)} anomalies correlate with deploy of "
                f"{common_cause}. Rollback candidate."
                if common_cause else
                f"{len(all_candidates)} different deploys in the anomaly window — "
                f"no single common cause."
                if all_candidates else
                "No deploys found within the correlation window. "
                "Cause is NOT a recent deploy."
            ),
            "action": (
                f"⚠️ RECOMMENDATION ONLY: Consider rollback of {common_cause} via ArgoCD."
                if common_cause else
                "Investigate non-deploy causes (traffic spike, dependency failure, "
                "infrastructure)."
            ),
        },
    }
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
