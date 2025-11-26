# Lead Generation App

Features: Postgres-backed lead pipeline, pricing and caps, trials, WhatsApp and Email delivery, live scraping, metrics endpoint, admin CLI, lightweight job workers.

Quick start:
- Copy `.env.template` → `.env` and fill values
- Run `docker compose up -d`
- Visit `http://localhost:8000/metrics`
- Admin CLI: `docker compose exec app python -m lead_generation_app.admin_cli clients list`
