#!/bin/sh
set -e

# Runs on every container start, not just the first — cheap/idempotent
# either way (Django tracks which migrations already applied), and means a
# `docker compose up` after pulling a change with a new migration just
# works without a separate manual step.
python manage.py migrate --noinput

exec gunicorn jobtracker_server.wsgi:application \
    --bind 0.0.0.0:8000 \
    --workers 3
