---
name: anomaly-detection-deep
description: "Choose detection algorithms and tune false positives."
version: 1.0.0
author: Carlos Felipe Gomes
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [anomaly, detection, deep, development]
    category: development
    related_skills: []
---
# Anomaly Detection Deep Dive

Comprehensive reference for detection algorithms, tuning strategies, and <org>-specific implementation patterns.

## When to Use

Use when designing anomaly detection rules, choosing detection algorithms, tuning false positive rates, or correlating signals across metrics/logs/events. Covers static thresholds, EWMA, Z-Score, Modified Z-Score, seasonal decomposition, multivariate methods, <org> anomaly-detection-controller patterns.

## Detection Algorithm Reference Card

### 1. Static Thresholds

Simplest approach — fixed upper/lower bounds.

| Aspect | Detail |
|--------|--------|
| When | Known SLOs, capacity limits, binary health |
| Pros | Zero warm-up, deterministic, easy to explain |
| Cons | No adaptation, seasonal blindness, manual tuning |
| Example | CPU ratio > 0.9, restarts > 3 in 5m |

```yaml
# <org> config.yaml
- name: high_cpu_ratio
  type: static
  query: 'max(rate(container_cpu_usage_seconds_total{...}[5m]) / on(pod) container_spec_cpu_quota{...}) by (pod)'
  threshold: 0.9
  operator: ">"
  severity: warning
```

### 2. Adaptive Baselines (EWMA + Percentiles)

Exponentially Weighted Moving Average tracks a smoothed baseline that adapts to gradual drift.

| Aspect | Detail |
|--------|--------|
| When | Metrics with gradual trends, no strong seasonality |
| Pros | Self-tuning, handles drift, low memory |
| Cons | Lags behind sudden shifts, alpha tuning needed |
| Formula | `baseline = α * current + (1-α) * previous` |

Alpha selection:
- `α = 0.1` — slow adaptation (stable services, 10+ data points to converge)
- `α = 0.3` — moderate (default in <org> controller)
- `α = 0.5` — fast adaptation (volatile metrics)

### 3. Z-Score (Standard Score)

Measures how many standard deviations a value is from the mean.

| Aspect | Detail |
|--------|--------|
| When | Normally distributed metrics, sufficient history |
| Pros | Statistical rigor, configurable sensitivity |
| Cons | Assumes normality, sensitive to outliers in training |
| Formula | `z = (x - μ) / σ` |
| Alert threshold | `|z| > 3` (99.7% confidence) |

```go
// Welford's online algorithm (<org> controller uses this)
func (b *Baseline) Update(value float64) {
    b.Count++
    delta := value - b.Mean
    b.Mean += delta / float64(b.Count)
    delta2 := value - b.Mean
    b.M2 += delta * delta2
}

func (b *Baseline) StdDev() float64 {
    if b.Count < 2 {
        return 0
    }
    return math.Sqrt(b.M2 / float64(b.Count-1))
}
```

### 4. Modified Z-Score (Median + MAD)

Robust alternative using median and Median Absolute Deviation — resistant to outliers.

| Aspect | Detail |
|--------|--------|
| When | Skewed distributions, outlier-contaminated history |
| Pros | Robust to outliers, works on non-normal data |
| Cons | Requires storing window of values (memory), slower |
| Formula | `modified_z = 0.6745 * (x - median) / MAD` |
| Alert threshold | `|modified_z| > 3.5` (Iglewicz & Hoaglin) |

```python
import numpy as np

def modified_z_score(values: np.ndarray) -> np.ndarray:
    median = np.median(values)
    mad = np.median(np.abs(values - median))
    if mad == 0:
        return np.zeros_like(values)
    return 0.6745 * (values - median) / mad
```

### 5. Seasonal Decomposition (STL, Holt-Winters)

Decomposes time series into trend + seasonal + residual components.

| Aspect | Detail |
|--------|--------|
| When | Strong daily/weekly patterns (traffic, batch jobs) |
| Pros | Handles periodicity, separates trend from noise |
| Cons | Needs 2+ full cycles of history, computationally expensive |
| Alert on | Residual component exceeding threshold |

<org> controller uses simplified seasonal profiles:
```
seasonal:{metric}:{hash}:{dow}:{hour} → {mean, stddev, count}
```

### 6. Forecasting + Residuals (Prophet)

Forecast expected value, alert when actual deviates significantly from prediction.

| Aspect | Detail |
|--------|--------|
| When | Complex seasonality, holidays, external regressors |
| Pros | Handles missing data, multiple seasonalities, interpretable |
| Cons | Slow training (seconds-minutes), univariate only |
| Alert on | `|actual - forecast| > N * uncertainty_interval` |

See skill `prophet-isolation-forest-patterns` for implementation details.

### 7. Multivariate (Isolation Forest, Mahalanobis)

Detect anomalies across multiple correlated metrics simultaneously.

| Aspect | Detail |
|--------|--------|
| When | Correlated metrics (CPU+memory+latency), complex failure modes |
| Pros | Catches multi-dimensional anomalies invisible to univariate |
| Cons | Feature engineering critical, harder to explain |
| Isolation Forest | Tree-based isolation — anomalies have shorter path lengths |
| Mahalanobis | Distance from centroid accounting for covariance |

### 8. ML-based (Autoencoders, LSTM)

Deep learning for complex temporal patterns.

| Aspect | Detail |
|--------|--------|
| When | Very complex patterns, large training data available |
| Pros | Learns arbitrary patterns, no manual feature engineering |
| Cons | Black box, expensive training, needs GPU, overfitting risk |
| Autoencoder | High reconstruction error = anomaly |
| LSTM | Prediction error on next-step forecast |

**<org> stance**: not in scope for Fase 3. Prophet + Isolation Forest cover 95% of use cases.

## Decision Tree: Which Method When

```
Is there a known hard limit (SLO, capacity)?
├── YES → Static threshold
└── NO
    ├── Is the metric seasonal (daily/weekly pattern)?
    │   ├── YES → Strong seasonality?
    │   │   ├── YES → Prophet (univariate) or Seasonal profiles (lightweight)
    │   │   └── NO → EWMA with seasonal adjustment
    │   └── NO
    │       ├── Single metric?
    │       │   ├── YES → Z-Score (normal) or Modified Z-Score (skewed)
    │       │   └── NO → Isolation Forest (5+ features) or Mahalanobis (2-4 features)
    └── Is the distribution heavily skewed or outlier-contaminated?
        ├── YES → Modified Z-Score
        └── NO → Standard Z-Score
```

**Rule of thumb**: start with static + Z-Score. Add seasonal/ML only when false positives demand it.

## <org> anomaly-detection-controller Implementation

### Architecture

```
Controller (Go, 2 replicas)
  ├── Config loader (hot-reload via fsnotify)
  ├── Job batch builder (groups rules by query type)
  ├── gRPC fan-out (round_robin to workers)
  └── Correlator (groups anomalies by workload, dedup, escalation)

Workers (Go, 3+ replicas, stateless)
  ├── Rate limiter (token bucket: 100/s VM, 50/s Loki)
  ├── Query executor (PromQL → VictoriaMetrics, LogQL → Loki)
  ├── Detection engine (static | adaptive | pattern)
  ├── Baseline updater (Redis EWMA + seasonal)
  └── Result reporter (gRPC back to controller)
```

### Detection types in production

| Type | Implementation | Redis key pattern |
|------|---------------|-------------------|
| Static | Direct threshold comparison | None (stateless) |
| Adaptive | Welford's online Z-Score | `baseline:{metric}:{labels_hash}` |
| Log rate | Rate spike detection via LogQL | `baseline:lograte:{ns}:{hash}` |
| K8s events | Regex pattern matching | None (event-driven) |
| Seasonal | Per-hour/per-dow profile lookup | `seasonal:{metric}:{hash}:{dow}:{hour}` |

### Redis baseline structure

```
baseline:{metric}:{hash} = {
  "mean": 0.45,
  "m2": 0.023,        // Welford's M2 (variance accumulator)
  "count": 1450,
  "last_update": "2026-05-28T23:00:00Z"
}

seasonal:{metric}:{hash}:{dow}:{hour} = {
  "mean": 0.62,
  "stddev": 0.08,
  "count": 168         // ~1 week of hourly samples
}
```

### Worker gRPC interface

```protobuf
// proto/worker.proto
service WorkerService {
  rpc ExecuteJob(JobRequest) returns (JobResult);
  rpc HealthCheck(Empty) returns (HealthResponse);
}

message JobRequest {
  string rule_name = 1;
  string query = 2;
  string detection_type = 3;  // "static" | "adaptive" | "log_rate" | "event"
  double threshold = 4;
  string operator = 5;
  string severity = 6;
}
```

## False Positive Control

### Alert deduplication (1h window)

```
alert:dedup:{fingerprint} → TTL 1h
```

Fingerprint = hash of (rule_name + labels). Same anomaly won't re-alert within 1 hour.

### Multi-metric correlation

Controller groups anomalies by workload before alerting:

```go
// Correlator groups anomalies arriving within 30s window
type Correlation struct {
    Workload   string        // e.g., "dpm-people-api"
    Anomalies  []Anomaly     // CPU + memory + latency together
    FirstSeen  time.Time
    Severity   string        // escalates if multiple signals
}
```

Single-metric anomaly → `warning`. Multi-metric (2+) → `critical`.

### Multi-window confirmation

Before alerting, confirm anomaly persists across windows:

| Window | Purpose |
|--------|---------|
| 5m (instant) | Detect the spike |
| 30m | Confirm it's not a transient blip |
| 24h (seasonal) | Compare to same time yesterday |

Only alert if 5m anomaly AND (30m confirms OR 24h seasonal deviation).

## Code Examples

### Go: Adaptive Z-Score detection (simplified)

```go
func (d *AdaptiveDetector) Detect(value float64, baseline *Baseline) *Anomaly {
    if baseline.Count < 30 {
        // Warm-up: learn, don't alert
        baseline.Update(value)
        return nil
    }

    stddev := baseline.StdDev()
    if stddev == 0 {
        stddev = 0.001 // avoid division by zero
    }

    zScore := (value - baseline.Mean) / stddev

    // Update baseline AFTER detection (avoid self-suppression)
    baseline.Update(value)

    if math.Abs(zScore) > 3.0 {
        return &Anomaly{
            Score:    zScore,
            Expected: baseline.Mean,
            Actual:   value,
            StdDev:   stddev,
        }
    }
    return nil
}
```

### Python: Prophet residual detection

```python
from prophet import Prophet
import pandas as pd
import numpy as np

def detect_prophet_anomalies(df: pd.DataFrame, threshold_sigma: float = 3.0):
    """
    df must have columns: ds (datetime), y (metric value)
    Returns DataFrame with anomaly column.
    """
    model = Prophet(
        changepoint_prior_scale=0.05,
        seasonality_mode='multiplicative',
        daily_seasonality=True,
        weekly_seasonality=True,
    )
    model.fit(df)

    forecast = model.predict(df)
    residuals = df['y'].values - forecast['yhat'].values
    residual_std = np.std(residuals)

    df['anomaly'] = np.abs(residuals) > (threshold_sigma * residual_std)
    df['residual'] = residuals
    df['expected'] = forecast['yhat'].values
    return df
```

## Anti-patterns

- ❌ **Alerting on raw Z-Score without warm-up** — first 30 samples are unreliable (high variance in Welford's)
- ❌ **Single-metric anomalies as critical** — one metric spiking is often noise; require correlation
- ❌ **No time-of-day awareness** — batch jobs at 2am look anomalous without seasonal profiles
- ❌ **Static thresholds on volatile metrics** — use adaptive for request_rate, latency
- ❌ **Training on anomalous data** — baseline contamination makes future anomalies invisible
- ❌ **Alerting without dedup** — same anomaly fires every eval cycle (alert storm)
- ❌ **Z-Score on non-normal distributions** — use Modified Z-Score for skewed metrics
- ❌ **ML in critical alerting path without fallback** — if ML service is down, alerts stop entirely
- ❌ **Ignoring warm-up period** — new deployments have no baseline; suppress alerts for N cycles
- ❌ **High-cardinality detection labels** — adding `pod_name` to anomaly metrics creates cardinality explosion

## Reference

- <org> controller: `<workspace>/06-STAFFOPS/anomaly-detection-controller/`
- <org> ML service: `<workspace>/06-STAFFOPS/anomaly-detection-ml/`
- Welford's algorithm: https://en.wikipedia.org/wiki/Algorithms_for_calculating_variance#Welford's_online_algorithm
- EWMA: https://en.wikipedia.org/wiki/Exponential_smoothing
- Related skills: `prophet-isolation-forest-patterns`, `go-patterns`, `vmalert-configuration`, `alertmanager-slack-config`
