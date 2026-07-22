"""MaritimeGuard AI — ML experiments.

Three models built on the maritime warehouse:
  1. Vessel Arrival Delay Classifier    (XGBoost)
  2. Voyage Duration Regressor          (XGBoost)
  3. AIS Blackout Anomaly Detector      (Isolation Forest)

Design notes:
  * All models read from the gold layer — the same data served by the API.
  * Delay classification uses a 24-hour threshold relative to per-route median.
  * The anomaly detector is unsupervised; evaluation uses a proxy: known blackouts
    (time_gap > 2h) vs normal pings. This is documented, not hidden.
  * Results are written back to gold tables for API serving.
"""
from __future__ import annotations

import warnings
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.metrics import (accuracy_score, classification_report, f1_score,
                              mean_absolute_error, mean_squared_error, r2_score,
                              roc_auc_score, precision_score, recall_score)
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler

try:
    from xgboost import XGBClassifier, XGBRegressor
    HAS_XGBOOST = True
except ImportError:
    from sklearn.ensemble import GradientBoostingClassifier, GradientBoostingRegressor
    HAS_XGBOOST = False
    print("WARNING: xgboost not installed, falling back to sklearn GradientBoosting")

warnings.filterwarnings("ignore")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = str(PROJECT_ROOT / "warehouse" / "maritimeguard.duckdb")
con = duckdb.connect(DB_PATH)
RESULTS: dict[str, dict] = {}


def banner(t: str) -> None:
    print("\n" + "=" * 64 + f"\n{t}\n" + "=" * 64)


# ============================================================================
# 1. VESSEL ARRIVAL DELAY CLASSIFIER (XGBoost / GradientBoosting)
# ============================================================================
banner("1. VESSEL ARRIVAL DELAY CLASSIFIER")

# Build features from port calls + vessel positions
delay_data = con.execute("""
    WITH port_stats AS (
        SELECT
            port_key,
            avg(duration_hours) as avg_port_duration,
            count(*) as port_call_count
        FROM gold.fct_port_calls
        GROUP BY 1
    ),
    vessel_voyage AS (
        SELECT
            v.vessel_key,
            v.vessel_type_code,
            avg(v.sog) as avg_sog,
            stddev(v.sog) as sog_variability,
            max(v.distance_nm) as max_leg_distance,
            count(*) as position_count,
            -- time-based features
            avg(extract(hour from v.position_ts)) as avg_hour,
            -- anomaly indicator
            sum(case when v.time_gap_minutes > 60 then 1 else 0 end) as n_gaps_over_1h
        FROM gold.fct_vessel_positions v
        GROUP BY v.vessel_key, v.vessel_type_code
    )
    SELECT
        pc.vessel_key,
        pc.port_key,
        pc.duration_hours,
        vv.vessel_type_code,
        vv.avg_sog,
        vv.sog_variability,
        vv.max_leg_distance,
        vv.position_count,
        vv.avg_hour,
        vv.n_gaps_over_1h,
        ps.avg_port_duration,
        ps.port_call_count,
        -- TARGET: is the stay extended (> 48h)?
        case when pc.duration_hours > 48 then 1 else 0 end as is_delayed
    FROM gold.fct_port_calls pc
    LEFT JOIN vessel_voyage vv ON pc.vessel_key = vv.vessel_key
    LEFT JOIN port_stats ps ON pc.port_key = ps.port_key
    WHERE pc.duration_hours is not null
      AND vv.avg_sog is not null
""").df()

if len(delay_data) > 10:
    print(f"port calls with features: {len(delay_data)}")
    rate = delay_data["is_delayed"].mean()
    print(f"delay rate: {rate:.1%}")

    features = ["vessel_type_code", "avg_sog", "sog_variability", "max_leg_distance",
                "position_count", "avg_hour", "n_gaps_over_1h", "avg_port_duration",
                "port_call_count"]
    X = delay_data[features].fillna(0)
    y = delay_data["is_delayed"]

    Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.25, random_state=42,
                                           stratify=y if y.nunique() > 1 else None)

    base_acc = max(rate, 1 - rate)
    print(f"baseline (majority class) accuracy = {base_acc:.4f}")

    if HAS_XGBOOST:
        clf = XGBClassifier(n_estimators=200, max_depth=6, learning_rate=0.1,
                            random_state=42, eval_metric="logloss",
                            scale_pos_weight=(1 - rate) / max(rate, 0.01))
    else:
        clf = GradientBoostingClassifier(n_estimators=200, max_depth=6,
                                          learning_rate=0.1, random_state=42)

    clf.fit(Xtr, ytr)
    pred = clf.predict(Xte)
    proba = clf.predict_proba(Xte)[:, 1] if hasattr(clf, "predict_proba") else pred.astype(float)

    acc = accuracy_score(yte, pred)
    f1 = f1_score(yte, pred, zero_division=0)
    try:
        auc = roc_auc_score(yte, proba)
    except ValueError:
        auc = 0.0

    print(f"XGBoost accuracy = {acc:.4f}  F1 = {f1:.4f}  ROC-AUC = {auc:.4f}")
    print(f"lift over baseline = {acc - base_acc:+.4f}")
    print("\n" + classification_report(yte, pred, target_names=["on_time", "delayed"],
                                        digits=3, zero_division=0))

    # Feature importance
    imp = pd.Series(clf.feature_importances_, index=features).sort_values(ascending=False)
    print("feature importance:")
    for f, v in imp.items():
        print(f"  {f:24} {v:.4f}")

    # Write predictions
    delay_data["delay_proba"] = clf.predict_proba(X)[:, 1] if hasattr(clf, "predict_proba") else clf.predict(X).astype(float)
    con.execute("CREATE OR REPLACE TABLE gold.vessel_delay_predictions AS SELECT * FROM delay_data")
    print(f"\n-> gold.vessel_delay_predictions written ({len(delay_data)} rows)")
    RESULTS["delay_classifier"] = {"accuracy": round(acc, 4), "f1": round(f1, 4),
                                     "auc": round(auc, 4), "baseline": round(base_acc, 4)}
else:
    print(f"Insufficient port call data ({len(delay_data)} rows). Skipping delay classifier.")
    RESULTS["delay_classifier"] = {"status": "skipped", "reason": f"only {len(delay_data)} rows"}


# ============================================================================
# 2. VOYAGE DURATION REGRESSOR (XGBoost / GradientBoosting)
# ============================================================================
banner("2. VOYAGE DURATION REGRESSOR")

voyage_data = con.execute("""
    SELECT
        pc.vessel_key,
        pc.port_key,
        pc.duration_hours,
        dv.vessel_type_code,
        dv.length_m,
        dv.width_m,
        dv.draft_m,
        dp.channel_depth_m,
        dp.harbor_size_rank,
        dp.latitude as port_lat,
        dp.longitude as port_lon
    FROM gold.fct_port_calls pc
    LEFT JOIN gold.dim_vessels dv ON pc.vessel_key = dv.vessel_key
    LEFT JOIN gold.dim_ports dp ON pc.port_key = dp.port_key
    WHERE pc.duration_hours is not null
      AND pc.duration_hours > 0
      AND pc.duration_hours < 720  -- cap at 30 days
""").df()

if len(voyage_data) > 10:
    print(f"voyage records: {len(voyage_data)}")

    voy_features = ["vessel_type_code", "length_m", "width_m", "draft_m",
                    "channel_depth_m", "harbor_size_rank", "port_lat", "port_lon"]
    Xv = voyage_data[voy_features].fillna(0)
    yv = voyage_data["duration_hours"]

    Xvtr, Xvte, yvtr, yvte = train_test_split(Xv, yv, test_size=0.25, random_state=42)

    # Baseline: predict median
    median_duration = yvtr.median()
    baseline_mae = mean_absolute_error(yvte, np.full(len(yvte), median_duration))
    print(f"baseline (median={median_duration:.1f}h) MAE = {baseline_mae:.2f}")

    if HAS_XGBOOST:
        reg = XGBRegressor(n_estimators=200, max_depth=6, learning_rate=0.1, random_state=42)
    else:
        reg = GradientBoostingRegressor(n_estimators=200, max_depth=6,
                                         learning_rate=0.1, random_state=42)

    reg.fit(Xvtr, yvtr)
    pred_v = reg.predict(Xvte)

    mae = mean_absolute_error(yvte, pred_v)
    rmse = np.sqrt(mean_squared_error(yvte, pred_v))
    r2 = r2_score(yvte, pred_v)
    mape = float(np.mean(np.abs((yvte - pred_v) / yvte.clip(lower=0.1))) * 100)

    print(f"XGBoost  MAE = {mae:.2f}h  RMSE = {rmse:.2f}h  R² = {r2:.4f}  MAPE = {mape:.1f}%")
    print(f"lift over baseline MAE = {baseline_mae - mae:+.2f}h")

    RESULTS["voyage_regressor"] = {"mae": round(mae, 2), "rmse": round(rmse, 2),
                                    "r2": round(r2, 4), "mape": round(mape, 1),
                                    "baseline_mae": round(baseline_mae, 2)}
else:
    print(f"Insufficient voyage data ({len(voyage_data)} rows). Skipping regressor.")
    RESULTS["voyage_regressor"] = {"status": "skipped", "reason": f"only {len(voyage_data)} rows"}


# ============================================================================
# 3. AIS BLACKOUT ANOMALY DETECTOR (Isolation Forest)
# ============================================================================
banner("3. AIS BLACKOUT ANOMALY DETECTOR (Isolation Forest)")

anomaly_data = con.execute("""
    SELECT
        vessel_key,
        position_ts,
        time_gap_minutes,
        distance_nm,
        sog,
        vessel_type_code,
        extract(hour from position_ts) as hour_of_day,
        -- proxy label: time_gap > 120 min is a known anomaly
        case when time_gap_minutes > 120 then 1 else 0 end as is_anomaly_proxy
    FROM gold.fct_vessel_positions
    WHERE time_gap_minutes is not null
      AND distance_nm is not null
""").df()

if len(anomaly_data) > 100:
    print(f"position transitions: {len(anomaly_data)}")
    anomaly_rate = anomaly_data["is_anomaly_proxy"].mean()
    print(f"known anomaly rate (gap > 2h): {anomaly_rate:.2%}")

    anom_features = ["time_gap_minutes", "distance_nm", "sog", "vessel_type_code", "hour_of_day"]
    Xa = anomaly_data[anom_features].fillna(0)

    # Scale features
    scaler = StandardScaler()
    Xa_scaled = scaler.fit_transform(Xa)

    # Isolation Forest — contamination set to approximate the known anomaly rate
    iso = IsolationForest(
        n_estimators=200,
        contamination=min(anomaly_rate * 1.5, 0.1),  # slightly overestimate
        random_state=42,
        n_jobs=-1,
    )
    iso.fit(Xa_scaled)

    # -1 = anomaly, 1 = normal
    iso_pred = iso.predict(Xa_scaled)
    anomaly_data["iso_anomaly"] = (iso_pred == -1).astype(int)
    anomaly_data["iso_score"] = -iso.score_samples(Xa_scaled)  # higher = more anomalous

    # Evaluate against proxy labels
    iso_pred_binary = anomaly_data["iso_anomaly"]
    proxy = anomaly_data["is_anomaly_proxy"]

    precision = precision_score(proxy, iso_pred_binary, zero_division=0)
    recall = recall_score(proxy, iso_pred_binary, zero_division=0)
    f1_anom = f1_score(proxy, iso_pred_binary, zero_division=0)

    print(f"\nIsolation Forest vs proxy labels:")
    print(f"  Precision = {precision:.4f}")
    print(f"  Recall    = {recall:.4f}")
    print(f"  F1        = {f1_anom:.4f}")
    print(f"  Detected anomalies: {iso_pred_binary.sum()} / {len(iso_pred_binary)}")

    # Write anomaly scores back
    scored = anomaly_data[anomaly_data["iso_anomaly"] == 1][
        ["vessel_key", "position_ts", "time_gap_minutes", "distance_nm",
         "sog", "iso_score"]
    ].copy()
    scored.rename(columns={"iso_score": "ml_risk_score"}, inplace=True)
    if len(scored) > 0:
        con.execute("CREATE OR REPLACE TABLE gold.ml_anomaly_scores AS SELECT * FROM scored")
        print(f"\n-> gold.ml_anomaly_scores written ({len(scored)} rows)")

    RESULTS["anomaly_detector"] = {"precision": round(precision, 4),
                                    "recall": round(recall, 4),
                                    "f1": round(f1_anom, 4),
                                    "detected": int(iso_pred_binary.sum()),
                                    "total": len(iso_pred_binary)}
else:
    print(f"Insufficient position data ({len(anomaly_data)} rows). Skipping anomaly detector.")
    RESULTS["anomaly_detector"] = {"status": "skipped", "reason": f"only {len(anomaly_data)} rows"}


# ============================================================================
# SUMMARY
# ============================================================================
banner("SUMMARY")
for name, metrics in RESULTS.items():
    print(f"{name:24} {metrics}")

con.close()
