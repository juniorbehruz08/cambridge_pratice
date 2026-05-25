# Deployment

This Django project is ready for a normal WSGI deployment using Gunicorn and WhiteNoise.

## Required Environment Variables

Copy `.env.example` and set real production values:

```text
DJANGO_SECRET_KEY=your-long-random-secret
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=your-domain.com,www.your-domain.com
DJANGO_CSRF_TRUSTED_ORIGINS=https://your-domain.com,https://www.your-domain.com
```

Use `DATABASE_URL` if the host provides Postgres. If `DATABASE_URL` is empty, Django uses `db.sqlite3`; only do that on a host with persistent disk.

## Build Commands

Run these during deployment:

```bash
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_answer_keys
python manage.py collectstatic --noinput
```

Make sure the deployment environment already has `DJANGO_DEBUG=False` before `collectstatic` runs. The production static build keeps only hashed files and skips compression for audio, so the generated bundle is smaller.

## Start Command

```bash
gunicorn project.wsgi:application --bind 0.0.0.0:$PORT
```

## Notes

Do not deploy `private_books/`, `tmp_*/`, `.env`, or `db.sqlite3`. The app should be deployed from templates, static assets, migrations, and `cambridge_practice/data/answer_keys.json`.

The production static bundle is large because it includes listening audio for all tests. The latest local `collectstatic` build is about 2.23 GB, so choose a host with enough disk/slug space or move audio to object storage/CDN later.
