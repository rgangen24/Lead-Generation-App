## Change

* Open `lead_generation_app/admin_web.py` and add a decorator to exempt CSRF checks on the soft-delete endpoint:

  * Place `@csrf.exempt` on the `soft_delete_client` view.

## Commit & Push

* `git add .`

* `git commit -m "Fix CSRF error for soft-delete endpoint"`

* `git push origin main`

## Deploy

* Wait for Render to auto-deploy from GitHub.

## Test

* Run: `curl -i -u myadmin:mysecretpass -X POST https://lead-generation-app-934w.onrender.com/admin/clients/1/soft-delete`

* Expect `200 OK` (not `400 Bad Request`).

