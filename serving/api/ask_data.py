"""MaritimeGuard AI — update ask_data system prompt for maritime schema.

The core validation logic (4 defense layers) is unchanged from InsightFlow.
Only the system prompt and default model are updated to reflect the maritime
gold schema.
"""
from __future__ import annotations

import json
import os
import re
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout

import duckdb

DEFAULT_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")
ROW_LIMIT = 200
QUERY_TIMEOUT_S = 8

_EXECUTOR = ThreadPoolExecutor(max_workers=4)

# Keywords/functions that must never appear, even inside an otherwise valid
# SELECT: DDL/DML, session/config changes, and file- or network-access table
# functions that would let a "SELECT" read outside the warehouse.
_FORBIDDEN = {
    "INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE", "TRUNCATE",
    "REPLACE", "MERGE", "GRANT", "REVOKE", "ATTACH", "DETACH", "COPY",
    "EXPORT", "IMPORT", "PRAGMA", "SET", "RESET", "CALL", "VACUUM",
    "INSTALL", "LOAD", "READ_CSV", "READ_CSV_AUTO", "READ_JSON",
    "READ_JSON_AUTO", "READ_PARQUET", "READ_NDJSON", "GLOB",
    "SQLITE_SCAN", "POSTGRES_SCAN", "MYSQL_SCAN", "HTTPFS",
}
_TABLE_TOKEN_RE = re.compile(r"\b(?:FROM|JOIN)\s+([a-zA-Z_][a-zA-Z0-9_\.]*)", re.IGNORECASE)
_SQL_BLOCK_RE = re.compile(r"```(?:sql)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)


class UnsafeSQLError(ValueError):
    """Raised when generated SQL fails a safety check. Never executed."""


def get_gold_schema_context(con: duckdb.DuckDBPyConnection) -> tuple[str, set[str]]:
    """Introspect the live gold schema. Returns (prompt text, allowed table names).

    Read from the database itself, not hardcoded, so the prompt and the
    allowlist can never drift from what actually exists.
    """
    rows = con.execute("""
        SELECT table_name, column_name, data_type
        FROM information_schema.columns
        WHERE table_schema = 'gold'
        ORDER BY table_name, ordinal_position
    """).fetchall()

    by_table: dict[str, list[str]] = {}
    for table, col, dtype in rows:
        by_table.setdefault(table, []).append(f"{col} ({dtype})")

    lines = []
    allowed = set()
    for table, cols in sorted(by_table.items()):
        lines.append(f"- gold.{table}: " + ", ".join(cols))
        allowed.add(table.lower())
        allowed.add(f"gold.{table}".lower())

    return "\n".join(lines), allowed


def validate_sql(sql: str, allowed_tables: set[str]) -> str:
    """Raise UnsafeSQLError on anything that fails any layer. Returns clean SQL."""
    s = sql.strip()
    if s.endswith(";"):
        s = s[:-1].strip()
    if ";" in s:
        raise UnsafeSQLError("multiple statements are not allowed")

    first_word = s.split(None, 1)[0].upper() if s else ""
    if first_word not in ("SELECT", "WITH"):
        raise UnsafeSQLError("only SELECT / WITH queries are allowed")

    upper = s.upper()
    for kw in _FORBIDDEN:
        if re.search(rf"\b{re.escape(kw)}\b", upper):
            raise UnsafeSQLError(f"forbidden keyword or function: {kw}")

    referenced = {m.group(1).lower() for m in _TABLE_TOKEN_RE.finditer(s)}
    cte_names = {m.group(1).lower() for m in re.finditer(r"\b(\w+)\s+AS\s*\(", upper)}
    for tbl in referenced:
        # allow a bare CTE name referenced later in the same query
        if tbl in allowed_tables or tbl in cte_names:
            continue
        raise UnsafeSQLError(f"query references a table outside the gold schema: {tbl}")

    if " LIMIT " not in f" {upper} ":
        s = f"{s}\nLIMIT {ROW_LIMIT}"
    return s


def _extract_sql(text: str) -> tuple[str, str]:
    """Parse the model's reply. Prefer strict JSON, fall back to a code block."""
    try:
        parsed = json.loads(text)
        return parsed["sql"], parsed.get("explanation", "")
    except (json.JSONDecodeError, KeyError, TypeError):
        pass
    m = _SQL_BLOCK_RE.search(text)
    if m:
        return m.group(1).strip(), ""
    raise UnsafeSQLError("could not parse a SQL statement from the model response")


def _run_with_timeout(con: duckdb.DuckDBPyConnection, sql: str):
    fut = _EXECUTOR.submit(lambda: con.execute(sql).fetch_df())
    try:
        return fut.result(timeout=QUERY_TIMEOUT_S)
    except FutureTimeout:
        con.interrupt()  # best-effort cancellation
        raise TimeoutError(f"query exceeded {QUERY_TIMEOUT_S}s and was interrupted")


SYSTEM_TEMPLATE = """You are a SQL analyst for the MaritimeGuard AI warehouse (DuckDB dialect).
This is a maritime intelligence platform tracking global vessel movements,
port operations, and AIS anomalies.

Only these tables exist. Use ONLY these, qualified as gold.<table>:
{schema}

Domain knowledge:
- MMSI is the vessel identifier (Maritime Mobile Service Identity)
- SOG = Speed Over Ground (knots), COG = Course Over Ground (degrees)
- AIS anomalies include blackouts (transponder shutoffs) and impossible speed jumps
- risk_score ranges from 0-100 (higher = more suspicious)
- Port calls track vessel arrivals, departures, and stay durations
- Weather zones cover major maritime chokepoints (Suez, Gibraltar, etc.)

Rules:
- Output ONLY one SELECT (or WITH ... SELECT) statement, DuckDB SQL syntax.
- Never write INSERT, UPDATE, DELETE, DROP, ALTER, or any DDL/DML.
- Never call file- or network-access functions (read_csv, read_json, glob, etc).
- Add a LIMIT unless the question asks for a single aggregate value.
- Respond with ONLY a JSON object, no other text: {{"sql": "...", "explanation": "one short sentence, same language as the question"}}
"""


def ask(question: str, db_path: str, api_key: str | None = None,
        model: str = DEFAULT_MODEL) -> dict:
    """Answer a natural-language question against the gold layer.

    Opens its OWN read-only connection — layer 4 of the defense — independent
    of whatever connection the caller (e.g. the FastAPI app) otherwise uses.
    """
    from anthropic import Anthropic  # imported lazily: not needed to run tests

    con = duckdb.connect(db_path, read_only=True)
    try:
        schema_text, allowed = get_gold_schema_context(con)

        client = Anthropic(api_key=api_key)  # falls back to ANTHROPIC_API_KEY env
        resp = client.messages.create(
            model=model,
            max_tokens=500,
            system=SYSTEM_TEMPLATE.format(schema=schema_text),
            messages=[{"role": "user", "content": question}],
        )
        raw_text = "".join(b.text for b in resp.content if b.type == "text")
        raw_sql, explanation = _extract_sql(raw_text)
        safe_sql = validate_sql(raw_sql, allowed)

        df = _run_with_timeout(con, safe_sql)
        return {
            "question": question,
            "sql": safe_sql,
            "explanation": explanation,
            "columns": list(df.columns),
            "rows": df.head(ROW_LIMIT).values.tolist(),
            "row_count": len(df),
        }
    finally:
        con.close()
