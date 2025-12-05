## Goal
Safely allow `/admin/health` to be accessible without authentication while keeping all other `/admin/*` routes protected. Verify locally and prepare for deploy.

## Verify Current State
- Read `lead_generation_app/admin_web.py` to confirm:
  - Bulk routes and `/admin/health` are placed before `def main()`
  - Basic Auth guard line currently broken across two lines
- Confirm `jsonify` is imported and `/admin/health` returns `jsonify(status, timestamp)`.

## Implement Safe Fix
- Create a backup: copy `lead_generation_app/admin_web.py` to `admin_web.safe.bak.py`.
- Update Basic Auth middleware line to a single-line condition:
  - Replace:
    - `if request.path.startswith('/admin') and not\n request.path.startswith('/admin/health'):`
  - With:
    - `if request.path.startswith('/admin') and not request.path.startswith('/admin/health'):`
- Do not change any other logic.

## Local Testing
- Start locally: `python -m lead_generation_app.admin_web`.
- Test endpoints:
  - Without auth: `curl -i http://127.0.0.1:5000/admin/health` → 200 JSON
  - With auth: `curl -i -u admin:admin http://127.0.0.1:5000/admin/health` → 200 JSON
  - Dashboard without auth: `curl -i http://127.0.0.1:5000/admin/` → 401
  - Dashboard with auth: `curl -i -u admin:admin http://127.0.0.1:5000/admin/` → 200
  - Spot check `/admin/clients` requires auth.

## Prepare Deployment
- Commit changes to `main`: concise message: "fix(admin): make health auth guard single-line and exclude /admin/health".
- Push to `origin/main`.
- On Render:
  - Ensure Web Service tracks `main` and Auto‑Deploy is ON.
  - Trigger “Clear build cache & deploy”.

## Production Verification
- Verify on Render:
  - `curl -i https://YOUR_URL/admin/health` → 200 JSON
  - `curl -i -u ADMIN_USER:ADMIN_PASS https://YOUR_URL/admin/` → 200
  - `curl -i https://YOUR_URL/admin/` without auth → 401
- Confirm route map loads without errors in logs.

## Rollback
- Restore `admin_web.safe.bak.py` if needed and redeploy.
- Alternatively revert the commit in Git and redeploy.

## Notes
- Change is minimal and isolated to the auth guard condition.
- No dependency, template, or route logic changes beyond the guard fix.
