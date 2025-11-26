# Deployment Guide

Prereqs: Docker, Docker Compose.

Steps:
1. Copy `.env.template` → `.env`, set DB and provider keys
2. `docker compose build`
3. `docker compose up -d`
4. Verify:
   - DB: `docker compose exec db psql -U $POSTGRES_USER -d $POSTGRES_DB -c "\dt"`
   - Metrics: `curl http://localhost:8000/metrics`
   - CLI: `docker compose exec app python -m lead_generation_app.admin_cli clients list`
