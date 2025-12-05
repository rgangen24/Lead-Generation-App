## Start the Admin Web
- Use the provided commands to launch the server:
  - `cd "C:\Users\rgang\Documents\trae_projects\Lead Generation App"`
  - `set SECRET_KEY=test-secret-key-for-local-testing-12345` (PowerShell: `$env:SECRET_KEY = "test-secret-key-for-local-testing-12345"`)
  - `set PORT=5000` (PowerShell: `$env:PORT = 5000`)
  - `python -m lead_generation_app.admin_web`
- The app binds to port from `PORT`/`ADMIN_PORT`; with `PORT=5000` it serves at `http://localhost:5000/`.

## Quick Health Check
- Open `http://localhost:5000/admin/health` and confirm JSON `{"status":"healthy"}` with 200.
- This endpoint is not behind Basic Auth; other `/admin/*` routes are.

## Access Admin Pages
- Visit `http://localhost:5000/admin/clients`.
- When prompted for Basic Auth, use default credentials unless overridden: `admin` / `admin`.

## Visual CSRF Verification
- On `Clients` page (`clients.html`):
  - Confirm hidden `csrf_token` in these forms: bulk soft delete, bulk restore, bulk permanent delete, bulk selection (`id="bulk-form"`).
- On per-client list (`clients_body.html`):
  - Deleted view: confirm `csrf_token` on `restore` and `permanent-delete` forms.
  - Active view: confirm `csrf_token` on `soft-delete` form.
- On `Client Detail` (`client_detail.html`):
  - Confirm `csrf_token` on `update_plan`, `restore`, `permanent-delete`, `soft-delete` forms.
- Use the browser devtools Elements panel to inspect each form and verify the hidden input exists: `input[name="csrf_token"]`.

## CSRF Enforcement (Negative Test)
- Attempt a POST without a token to ensure protection triggers 400:
  - Example (Basic Auth): `curl -i -u admin:admin -X POST http://localhost:5000/admin/clients/1/soft-delete`
  - Expect a 400 CSRF failure response.

## Functional Form Tests (Positive)
- With normal form submissions in the UI (which include the token), verify expected behavior:
  - `Update Plan`: change plan, see redirect back to detail and updated `Plan:` value.
  - `Soft Delete`: mark a client deleted, then see it move to `Deleted Clients` view.
  - `Restore`: bring a deleted client back to active.
  - `Permanent Delete`: remove a client, confirm it no longer appears.
  - Bulk actions: select multiple clients via checkboxes and submit; confirm redirect and state changes.

## Wrap Up
- Check logs for `admin_web_start` and `admin_web_bind` messages.
- Stop the server when done.
