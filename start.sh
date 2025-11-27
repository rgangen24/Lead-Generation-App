#!/bin/sh
set -eu
python3 -c "from lead_generation_app.database.database import init_db; init_db()"
exec gunicorn --bind 0.0.0.0: --timeout 120 lead_generation_app.admin_web:app
