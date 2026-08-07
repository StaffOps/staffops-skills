#!/usr/bin/env python3
"""Multi-window SLO burn rate calculator.

Given error/total request counts over a time range, calculates burn rates
at multiple windows (1h, 6h, 24h, 72h) and determines if an SLO is at risk.

Implements Google SRE Workbook multi-window alerting:
- Fast burn (1h window, 14.4x budget): pages immediately
- Medium burn (6h window, 6x budget): warns within shift
- Slow burn (24h-72h window, 1-3x budget): ticket/review

Usage:
    python3 burn_rate.py --data-file /tmp/slo_data.json [--budget-days 30] [--target 0.999]

Input format:
{
  "service": "DataPlatform.People",
  "slo_target": 0.999,
  "budget_period_days": 30,
  "windows": {
    "1h":  {"errors": 12, "total": 8500},
    "6h":  {"errors": 45, "total": 51000},
    "24h": {"errors": 120, "total": 204000},
    "72h": {"errors": 290, "total": 612000}
  }
}
"""
import argparse
import json
import sys


def calculate_burn_rate(errors, total, slo_target, budget_period_days, window_hours):
    """Calculate burn rate for a single window.

    burn_rate = (error_rate / error_budget_rate)
    where error_budget_rate = (1 - slo_target)

    A burn_rate of 1.0 means consuming budget at exactly the sustainable rate.
    A burn_rate of 14.4 means exhausting a 30-day budget in ~50 hours.
    """
    if total == 0:
        return {"burn_rate": 0, "error_rate": 0, "status": "no_data"}

    error_rate = errors / total
    error_budget = 1 - slo_target  # e.g., 0.001 for 99.9%

    if error_budget == 0:
        return {"burn_rate": float("inf"), "error_rate": error_rate,
                "status": "impossible_target"}

    burn_rate = error_rate / error_budget

    # Time to exhaust budget at this rate
    budget_hours = budget_period_days * 24
    hours_to_exhaustion = budget_hours / burn_rate if burn_rate > 0 else float("inf")

    # Remaining budget percentage (assuming this rate started at period begin)
    budget_consumed_pct = min((burn_rate * window_hours / budget_hours) * 100, 100)

    return {
        "burn_rate": round(burn_rate, 2),
        "error_rate": round(error_rate, 6),
        "error_rate_pct": round(error_rate * 100, 4),
        "hours_to_exhaustion": round(hours_to_exhaustion, 1),
        "budget_consumed_in_window_pct": round(budget_consumed_pct, 2),
        "status": classify_burn(burn_rate, window_hours),
    }


def classify_burn(burn_rate, window_hours):
    """Classify severity per Google SRE multi-window model."""
    if window_hours <= 1:
        if burn_rate >= 14.4:
            return "CRITICAL_PAGE"
        elif burn_rate >= 6:
            return "WARNING"
        return "ok"
    elif window_hours <= 6:
        if burn_rate >= 6:
            return "CRITICAL_PAGE"
        elif burn_rate >= 3:
            return "WARNING"
        return "ok"
    elif window_hours <= 24:
        if burn_rate >= 3:
            return "WARNING_TICKET"
        elif burn_rate >= 1:
            return "WATCH"
        return "ok"
    else:  # 72h+
        if burn_rate >= 1:
            return "SLOW_BURN_TICKET"
        return "ok"


def get_action(status):
    """Return recommended action for a given burn status."""
    actions = {
        "ok": "No action needed. Budget is healthy.",
        "WATCH": "Monitor — burn rate elevated but sustainable.",
        "SLOW_BURN_TICKET": "Create ticket. Budget will exhaust before period end at this rate.",
        "WARNING": "Investigate now. Budget consuming faster than shift allows.",
        "WARNING_TICKET": "Create P2 ticket. Sustained elevated burn.",
        "CRITICAL_PAGE": "PAGE. Budget exhausts within hours at this rate. Immediate action required.",
    }
    return actions.get(status, "Unknown status")


def main():
    parser = argparse.ArgumentParser(description="SLO burn rate calculator")
    parser.add_argument("--data-file", required=True, help="Path to JSON input file")
    parser.add_argument("--budget-days", type=int, default=30,
                        help="Budget period in days (default: 30)")
    parser.add_argument("--target", type=float, default=None,
                        help="SLO target (e.g., 0.999). Overrides value in data file.")
    args = parser.parse_args()

    try:
        with open(args.data_file) as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(1)

    slo_target = args.target or data.get("slo_target", 0.999)
    budget_days = args.budget_days or data.get("budget_period_days", 30)
    service = data.get("service", "unknown")
    windows = data.get("windows", {})

    if not windows:
        print(json.dumps({"error": "No window data provided"}))
        sys.exit(1)

    # Calculate per window
    results = {}
    worst_status = "ok"
    worst_window = None
    severity_order = ["ok", "WATCH", "SLOW_BURN_TICKET", "WARNING",
                      "WARNING_TICKET", "CRITICAL_PAGE"]

    for window_label, counts in windows.items():
        # Parse window hours from label
        hours = float(window_label.replace("h", "").replace("d", ""))
        if "d" in window_label:
            hours *= 24

        result = calculate_burn_rate(
            errors=counts.get("errors", 0),
            total=counts.get("total", 0),
            slo_target=slo_target,
            budget_period_days=budget_days,
            window_hours=hours,
        )
        results[window_label] = result

        # Track worst
        if severity_order.index(result["status"]) > severity_order.index(worst_status):
            worst_status = result["status"]
            worst_window = window_label

    # Budget math
    longest_window = max(
        windows.keys(),
        key=lambda w: float(w.replace("h", "").replace("d", "")) * (24 if "d" in w else 1),
    )
    longest_data = windows[longest_window]
    current_error_rate = (
        longest_data["errors"] / longest_data["total"]
        if longest_data["total"] > 0 else 0
    )

    report = {
        "service": service,
        "slo_target": slo_target,
        "slo_target_pct": f"{slo_target * 100:.3f}%",
        "error_budget": f"{(1 - slo_target) * 100:.3f}%",
        "budget_period_days": budget_days,
        "windows": results,
        "overall": {
            "worst_status": worst_status,
            "worst_window": worst_window,
            "action": get_action(worst_status),
            "current_error_rate_pct": round(current_error_rate * 100, 4),
        },
    }
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
