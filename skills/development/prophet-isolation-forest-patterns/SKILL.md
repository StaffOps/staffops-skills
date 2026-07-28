---
name: prophet-isolation-forest-patterns
description: "Forecast and detect outliers with Prophet."
version: 1.0.0
author: Carlos Felipe Gomes
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [prophet, isolation, forest, patterns, development]
    category: development
    related_skills: []
---
# Prophet & Isolation Forest Patterns

ML-based anomaly detection patterns for the <org> anomaly-detection pipeline. Prophet handles univariate time-series with seasonality; Isolation Forest handles multivariate detection without distribution assumptions.

## When to Use

Use when designing ML-based anomaly detection with Prophet (univariate forecasting) or Isolation Forest (multivariate detection), or building hybrid pipelines. Covers Prophet seasonality/changepoints, Isolation Forest contamination tuning, feature engineering, gRPC ML service integration.

## Prophet (Facebook/Meta)

### Overview

Additive regression model: `y(t) = trend(t) + seasonality(t) + holidays(t) + error(t)`

| Aspect | Detail |
|--------|--------|
| Type | Univariate time-series forecasting |
| Input | DataFrame with `ds` (datetime) and `y` (value) columns |
| Output | Forecast with uncertainty intervals (`yhat`, `yhat_lower`, `yhat_upper`) |
| Anomaly signal | `|actual - yhat| > N * (yhat_upper - yhat_lower)` |

### Pros & Cons

| Pros | Cons |
|------|------|
| Handles missing data gracefully | Slow training (1-30s per series) |
| Multiple seasonalities (daily + weekly + yearly) | Univariate only |
| Interpretable components (decomposition plot) | Sensitive to `changepoint_prior_scale` |
| Built-in uncertainty quantification | Requires 2+ full seasonal cycles |
| Robust to outliers in training data | Not real-time (batch retraining) |

### Key Parameters

| Parameter | Default | Tuning guidance |
|-----------|---------|-----------------|
| `changepoint_prior_scale` | 0.05 | Lower = smoother trend. Higher = more reactive. <org>: 0.01-0.1 |
| `seasonality_prior_scale` | 10 | Lower = dampen seasonality. Rarely needs tuning |
| `seasonality_mode` | `additive` | Use `multiplicative` when seasonal amplitude scales with trend |
| `daily_seasonality` | auto | Force `True` for infra metrics (clear daily pattern) |
| `weekly_seasonality` | auto | Force `True` for business metrics (weekday/weekend) |
| `yearly_seasonality` | auto | Usually `False` for infra (not enough history) |
| `interval_width` | 0.8 | Uncertainty interval width. 0.95 = fewer false positives |

### Training Pattern

```python
from prophet import Prophet
import pandas as pd

def train_prophet_model(
    history: pd.DataFrame,
    changepoint_prior: float = 0.05,
    seasonality_mode: str = 'multiplicative',
) -> Prophet:
    """
    history: DataFrame with 'ds' and 'y' columns.
    Minimum: 14 days for daily+weekly seasonality.
    """
    model = Prophet(
        changepoint_prior_scale=changepoint_prior,
        seasonality_mode=seasonality_mode,
        daily_seasonality=True,
        weekly_seasonality=True,
        yearly_seasonality=False,
        interval_width=0.95,
    )
    model.fit(history)
    return model
```

### Anomaly Detection Pattern

```python
import numpy as np

def detect_anomalies_prophet(
    model: Prophet,
    recent: pd.DataFrame,
    sigma_multiplier: float = 1.5,
) -> pd.DataFrame:
    """
    recent: last N hours of data (ds, y).
    Returns DataFrame with 'is_anomaly' and 'score' columns.
    """
    forecast = model.predict(recent[['ds']])
    merged = recent.merge(forecast[['ds', 'yhat', 'yhat_lower', 'yhat_upper']], on='ds')

    # Residual-based scoring
    residual = merged['y'] - merged['yhat']
    interval_width = merged['yhat_upper'] - merged['yhat_lower']

    # Normalize residual by interval width
    merged['score'] = np.abs(residual) / (interval_width / 2)
    merged['is_anomaly'] = merged['score'] > sigma_multiplier

    return merged[['ds', 'y', 'yhat', 'score', 'is_anomaly']]
```

### External Regressors

Add correlated signals to improve forecast accuracy:

```python
# Add deploy events as regressor
model.add_regressor('deploy_happened', mode='additive')

# Add day-of-month (batch jobs run on 1st/15th)
model.add_regressor('is_batch_day', mode='multiplicative')
```

## Isolation Forest (scikit-learn)

### Overview

Unsupervised tree-based anomaly detection. Isolates anomalies by random partitioning — anomalies require fewer splits to isolate.

| Aspect | Detail |
|--------|--------|
| Type | Multivariate unsupervised |
| Input | Feature matrix (N samples × M features) |
| Output | Anomaly score (-1 = anomaly, 1 = normal) or raw score |
| Key insight | Anomalies are few and different → short isolation paths |

### Pros & Cons

| Pros | Cons |
|------|------|
| Scales to high dimensions (100+ features) | No seasonality awareness |
| No normality assumption | `contamination` param sensitive |
| Fast training and inference | Needs feature engineering for temporal data |
| Works with mixed feature types | Hard to explain individual predictions |
| Low memory footprint | Retraining needed when patterns shift |

### Key Parameters

| Parameter | Default | Tuning guidance |
|-----------|---------|-----------------|
| `n_estimators` | 100 | 100-300 sufficient. More = stable but slower |
| `contamination` | `auto` | Expected anomaly ratio. <org>: 0.01-0.05 |
| `max_samples` | `auto` | Subsample size. 256 is often optimal |
| `max_features` | 1.0 | Feature subsample ratio. 0.5-1.0 |
| `random_state` | None | Set for reproducibility |

### Feature Engineering (Critical)

Raw metrics are insufficient. Transform into features that capture temporal behavior:

```python
import pandas as pd
import numpy as np

def engineer_features(df: pd.DataFrame, metric_cols: list[str]) -> pd.DataFrame:
    """
    Transform raw time-series into features suitable for Isolation Forest.
    df: DataFrame with timestamp index and metric columns.
    """
    features = pd.DataFrame(index=df.index)

    for col in metric_cols:
        # Current value (normalized)
        features[f'{col}_current'] = (df[col] - df[col].mean()) / df[col].std()

        # Rate of change
        features[f'{col}_diff'] = df[col].diff()

        # Rolling statistics (5m window)
        features[f'{col}_rolling_mean'] = df[col].rolling(5).mean()
        features[f'{col}_rolling_std'] = df[col].rolling(5).std()

        # Lag features
        features[f'{col}_lag_1'] = df[col].shift(1)
        features[f'{col}_lag_5'] = df[col].shift(5)

        # Ratio to rolling mean (spike detection)
        rolling = df[col].rolling(10).mean()
        features[f'{col}_ratio'] = df[col] / rolling.replace(0, np.nan)

    return features.dropna()
```

### Detection Pattern

```python
from sklearn.ensemble import IsolationForest
import numpy as np

def train_isolation_forest(
    features: np.ndarray,
    contamination: float = 0.02,
) -> IsolationForest:
    """
    features: 2D array (samples × engineered features).
    contamination: expected fraction of anomalies (0.01-0.05 for infra).
    """
    model = IsolationForest(
        n_estimators=200,
        contamination=contamination,
        max_samples=min(256, len(features)),
        random_state=42,
        n_jobs=-1,
    )
    model.fit(features)
    return model


def detect_anomalies_iforest(
    model: IsolationForest,
    features: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Returns (labels, scores).
    labels: -1 = anomaly, 1 = normal.
    scores: lower = more anomalous (negative = anomaly).
    """
    labels = model.predict(features)
    scores = model.decision_function(features)
    return labels, scores
```

## Decision Matrix: When to Use Which

| Scenario | Method | Why |
|----------|--------|-----|
| Single metric + strong daily/weekly pattern | Prophet | Captures seasonality, interpretable |
| Single metric + no seasonality | Z-Score / EWMA | Simpler, faster, sufficient |
| 5+ correlated metrics | Isolation Forest | Multivariate, catches complex failures |
| 2-4 correlated metrics | Mahalanobis distance | Simpler multivariate, interpretable |
| Complex seasonality + external events | Prophet + regressors | Handles holidays, deploys |
| Need real-time (<1s latency) | NOT Prophet (too slow) | Use Z-Score or pre-trained IF |
| Unknown failure modes | Isolation Forest | Unsupervised, finds novel anomalies |

### Ensemble (both)

```
Prophet (per-metric) → residuals → Isolation Forest (multi-metric residuals)
```

Prophet removes expected seasonality. IF detects multivariate anomalies in the residuals. Best of both worlds but highest complexity.

## <org> Integration

### anomaly-detection-ml Service (Fase 3)

**Path**: `<workspace>/06-STAFFOPS/anomaly-detection-ml/`

**Status**: scaffold created, NOT functional yet.

```
anomaly-detection-ml/
├── proto/ml.proto           # gRPC interface definition
├── src/
│   ├── server.py            # gRPC server (:50051)
│   ├── prophet_detector.py  # Prophet wrapper
│   ├── iforest_detector.py  # Isolation Forest wrapper
│   └── feature_store.py     # Feature engineering pipeline
├── models/                  # Serialized trained models
├── Dockerfile
├── pyproject.toml
└── tests/
```

### gRPC Interface

```protobuf
// proto/ml.proto
service MLService {
  rpc DetectAnomaly(DetectRequest) returns (DetectResponse);
  rpc TrainModel(TrainRequest) returns (TrainResponse);
  rpc HealthCheck(Empty) returns (HealthResponse);
}

message DetectRequest {
  string metric_name = 1;
  repeated MetricPoint points = 2;  // recent window
  string model_type = 3;            // "prophet" | "isolation_forest"
}

message DetectResponse {
  bool is_anomaly = 1;
  double score = 2;
  double expected = 3;
  double actual = 4;
  string explanation = 5;
}
```

### Controller → ML Integration Flow

```
Controller builds job batch
  → Worker queries VictoriaMetrics (PromQL)
  → Worker calls ML service via gRPC (DetectAnomaly)
  → ML service returns score + is_anomaly
  → Worker reports result to Controller
  → Controller correlates + dedup + alert
```

### Ports & Services

| Service | Port | Protocol |
|---------|------|----------|
| ML gRPC | 50051 | gRPC (HTTP/2) |
| ML metrics | 8082 | HTTP (Prometheus) |
| Worker (caller) | 50052 | gRPC |

## Operational Patterns

### Model Training Cadence

| Model | Training frequency | Data window | Duration |
|-------|-------------------|-------------|----------|
| Prophet | Every 6h (cron) | Last 14 days | 5-30s per metric |
| Isolation Forest | Every 1h | Last 24h | 1-5s per feature set |

Training runs as background task — detection uses last trained model.

### Feature Store / Data Pipeline

```
VictoriaMetrics (raw metrics)
  → Query last 14d (Prophet) or 24h (IF)
  → Feature engineering (lags, rolling stats, ratios)
  → Train model
  → Serialize to disk (joblib/pickle)
  → Serve via gRPC
```

### Fallback: ML Service Down

**Critical**: ML service failure MUST NOT stop anomaly detection.

```go
// In worker: ML call with timeout + fallback
func (w *Worker) detectWithML(ctx context.Context, req *pb.DetectRequest) (*pb.DetectResponse, error) {
    ctx, cancel := context.WithTimeout(ctx, 2*time.Second)
    defer cancel()

    resp, err := w.mlClient.DetectAnomaly(ctx, req)
    if err != nil {
        // Fallback to static/adaptive detection
        log.Warn("ML service unavailable, using fallback", "error", err)
        return w.fallbackDetect(req)
    }
    return resp, nil
}
```

Fallback hierarchy:
1. ML service (Prophet/IF) — preferred
2. Adaptive Z-Score — always available (Redis baselines)
3. Static thresholds — last resort (no state needed)

### Model Versioning

```
models/
├── prophet_cpu_by_workload_v3.pkl
├── prophet_cpu_by_workload_v2.pkl  # previous (rollback)
├── iforest_multivariate_v1.pkl
└── metadata.json                   # active versions, training timestamps
```

## Anti-patterns

- ❌ **Prophet on multivariate data** — it's univariate only; use one model per metric or switch to IF
- ❌ **Isolation Forest without feature engineering** — raw metric values miss temporal patterns (lags, rates)
- ❌ **ML in critical alerting path without fallback** — if ML pod crashes, all detection stops
- ❌ **Training on anomalous periods** — model learns anomalies as normal; filter training data
- ❌ **`contamination=0.5`** — means 50% of data is anomalous; realistic range is 0.01-0.05
- ❌ **Prophet with <7 days of data** — can't learn weekly seasonality without full cycle
- ❌ **Retraining on every request** — Prophet takes seconds; train on schedule, serve cached model
- ❌ **Ignoring model staleness** — model trained 7 days ago may not reflect recent pattern shifts
- ❌ **No explanation in alerts** — "anomaly detected" is useless; include expected vs actual, score, which features
- ❌ **Synchronous training in request path** — training blocks detection; use background jobs
- ❌ **Single contamination value for all metrics** — CPU (stable) needs 0.01, request_rate (volatile) needs 0.05

## Reference

- <org> ML service: `<workspace>/06-STAFFOPS/anomaly-detection-ml/`
- <org> controller: `<workspace>/06-STAFFOPS/anomaly-detection-controller/`
- Prophet docs: https://facebook.github.io/prophet/
- Isolation Forest: https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.IsolationForest.html
- Related skills: `anomaly-detection-deep`, `python-otel-patterns`, `go-patterns`
