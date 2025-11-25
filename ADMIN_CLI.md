# Admin CLI

List clients:
- `python -m lead_generation_app.admin_cli clients list`

Update plan:
- `python -m lead_generation_app.admin_cli clients update <client_id> <plan_name>`

Show metrics:
- `python -m lead_generation_app.admin_cli metrics show`

Opt-outs:
- List: `python -m lead_generation_app.admin_cli optout list email|whatsapp`
- Add: `python -m lead_generation_app.admin_cli optout add email|whatsapp <value>`
