## Update requirements.txt
- Add the following lines exactly:
  - `Flask-Login==0.6.3`
  - `werkzeug==3.0.3`
- Ensure they are added to the project requirements file used by Render.

## Add Flask-Login User Model
- Open `lead_generation_app/database/models.py`.
- Keep the existing SQLAlchemy `User` table class intact.
- Add imports:
  - `from flask_login import UserMixin`
  - `from werkzeug.security import generate_password_hash, check_password_hash`
  - `import os`
- Add a non-SQLAlchemy wrapper class to avoid name collision:
  - Define `class LoginUser(UserMixin):`
    - `__init__(self, id, username, password_hash)`
    - `check_password(self, password)` using `check_password_hash`
    - `@staticmethod def get(user_id)` returning a `LoginUser` built from `ADMIN_USER`/`ADMIN_PASS` env vars (hashed with `generate_password_hash`), or `None` if not set.

## Notes
- This preserves the existing database schema while enabling Flask-Login integration without breaking current models.
- Subsequent steps (routes and session management) can use `LoginUser.get()` and standard Flask-Login loaders.
