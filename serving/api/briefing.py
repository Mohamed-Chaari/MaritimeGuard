"""MaritimeGuard AI — AI-powered supply chain risk briefing.

Uses an LLM to generate executive summaries from warehouse KPIs.
Secured by the same read-only connection pattern as ask_data.py.
"""
from __future__ import annotations

import os

import duckdb


DEFAULT_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")


def generate_briefing(context: str, db_path: str,
                       api_key: str | None = None,
                       model: str = DEFAULT_MODEL) -> dict:
    """Generate an executive supply chain risk briefing."""
    from anthropic import Anthropic

    con = duckdb.connect(db_path, read_only=True)
    try:
        # Gather KPIs
        kpis = {}
        kpis["total_vessels"] = con.execute(
            "SELECT count(*) FROM gold.dim_vessels").fetchone()[0]
        kpis["total_positions"] = con.execute(
            "SELECT count(*) FROM gold.fct_vessel_positions").fetchone()[0]
        kpis["port_calls"] = con.execute(
            "SELECT count(*) FROM gold.fct_port_calls").fetchone()[0]
        kpis["anomalies"] = con.execute(
            "SELECT count(*) FROM gold.fct_ais_anomalies").fetchone()[0]

        # Top anomalies
        top_anom = con.execute("""
            SELECT anomaly_type, count(*) n, round(avg(risk_score),1) avg_risk
            FROM gold.fct_ais_anomalies GROUP BY 1 ORDER BY n DESC LIMIT 5
        """).fetchall()

        # Top ports
        top_ports = con.execute("""
            SELECT dp.port_name, dp.country, count(*) calls
            FROM gold.fct_port_calls pc
            JOIN gold.dim_ports dp ON pc.port_key = dp.port_key
            GROUP BY 1, 2 ORDER BY calls DESC LIMIT 5
        """).fetchall()

        data_summary = f"""
Maritime Intelligence KPIs:
- Vessels tracked: {kpis['total_vessels']}
- Total AIS positions: {kpis['total_positions']}
- Port calls recorded: {kpis['port_calls']}
- AIS anomalies flagged: {kpis['anomalies']}

Top anomaly types:
{chr(10).join(f'  - {t}: {n} events, avg risk {r}' for t, n, r in top_anom)}

Top ports by traffic:
{chr(10).join(f'  - {p} ({c}): {n} calls' for p, c, n in top_ports)}

Context requested: {context}
"""

        client = Anthropic(api_key=api_key)
        resp = client.messages.create(
            model=model,
            max_tokens=1000,
            system="""You are a maritime intelligence analyst. Generate a concise
executive briefing (3-5 paragraphs) summarizing the supply chain risk posture
based on the provided KPIs. Highlight any AIS anomalies, congestion risks,
and operational concerns. Use professional maritime terminology. Format as markdown.""",
            messages=[{"role": "user", "content": data_summary}],
        )
        briefing_text = "".join(b.text for b in resp.content if b.type == "text")

        return {
            "context": context,
            "kpis": kpis,
            "briefing": briefing_text,
        }
    finally:
        con.close()
