# Architecture

Components:
- Database: SQLAlchemy models and Postgres
- Config: pricing and tiers
- Delivery: WhatsApp/Email modules with caps, discounts, trials
- Scrapers: Google Maps
- Observability: structured logging, in-memory metrics `/metrics`
- Admin CLI: client management, metrics, opt-outs
- Jobs: lightweight worker with retry/backoff and dead-letter

Data Flow:
- Scrape → Raw leads → Validate/Qualify/Enrich → Qualified leads → Deliver → delivered_leads + metrics
