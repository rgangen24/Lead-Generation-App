# Troubleshooting

- DB connection fails: check `.env` DB_* values and that Postgres is reachable.
- Provider errors: ensure SendGrid/Twilio keys are set; dry-run mode simulates sends.
- Empty metrics: metrics are in-memory; query the same process or use DB aggregates.
- Caps unexpected: verify plan and industry tier; check delivered_leads counts for the month.
