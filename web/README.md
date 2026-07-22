# Web platform (Next.js)

Consumes the FastAPI serving layer and the Cube.dev semantic layer to render
interactive dashboards (KPIs, drill-down charts, maps).

Scaffold once the API endpoints return real data:
    npx create-next-app@latest . --ts --tailwind --app

Planned pages:
- /            overview KPIs (from /kpis)
- /explore     drill-down / slice-dice via Cube.dev
- /predict     ML predictions form (from /predict)
