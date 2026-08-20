# Runs the same Django app as local dev (manage.py runserver), just behind a
# real WSGI server (gunicorn) instead — see requirements.txt's comment on
# why gunicorn/whitenoise are only actually used here. Single stage: this
# project has no compiled dependencies (Django/requests/gunicorn/whitenoise/
# python-dotenv are all pure Python), so a multi-stage build wouldn't save
# anything meaningful — it would just add complexity for no real image-size
# win.
FROM python:3.12-slim

# Prevents .pyc files (irrelevant/wasted in a container that's rebuilt from
# source every time, not restarted-in-place) and forces stdout/stderr to be
# unbuffered so `docker logs` shows output immediately instead of batched.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Needs SOME value present for settings.py to import cleanly (it doesn't
# need to be cryptographically real — collectstatic never touches the
# database or does any signing) — the real SECRET_KEY is supplied at
# container *run* time via docker-compose's env_file/environment, not baked
# into the image.
RUN SECRET_KEY=build-time-placeholder python manage.py collectstatic --noinput

EXPOSE 8000

COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh
ENTRYPOINT ["/docker-entrypoint.sh"]
