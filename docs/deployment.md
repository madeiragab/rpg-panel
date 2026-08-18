> 🇧🇷 [Português](deployment.pt-BR.md) · 🇬🇧 **English**

# Deployment

The panel runs anywhere that can serve a WSGI app. It is currently deployed
on PythonAnywhere (`galibinja.pythonanywhere.com`), and the `Procfile` also
supports platforms that read it (Railway, Render, Heroku-likes).

## Environment variables

| Variable | Required | Purpose |
|---|---|---|
| `DJANGO_SECRET_KEY` | **Yes in production** | Django secret key. The app refuses to boot without it when `DEBUG` is off. |
| `DEBUG` | No | `True` enables debug mode and a development-only secret key fallback. Defaults to `False`. |
| `EMAIL_HOST_USER` | For password reset | Gmail account used to send reset e-mails. |
| `EMAIL_HOST_PASSWORD` | For password reset | Gmail **app password** (not the account password). |

Generate a secret key with:

```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

> **Security note:** the secret key used to be hardcoded in
> `settings.py` and is therefore present in this repository's git history.
> Any deployment must use a **newly generated** key via
> `DJANGO_SECRET_KEY` — never the old one. Rotating the key invalidates
> existing sessions and password-reset tokens, which is the desired
> outcome here.

## HTTPS hardening

With `DEBUG` off, `settings.py` turns on HTTPS-only session and CSRF cookies, the redirect to HTTPS, and a one-year HSTS. `SECURE_PROXY_SSL_HEADER` goes with them: the host's proxy is what terminates TLS, and without that setting Django sees the request as plain text and enters a redirect loop.

None of it turns on in development — the site runs on `http://127.0.0.1`, where a cookie marked `secure` would simply never arrive.

CI runs `manage.py check --deploy --fail-level WARNING`, so this set cannot quietly disappear from `settings.py`.

## Allowed hosts

`ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS` are hardcoded in
`rpg_panel/settings.py`. Add your domain there before deploying to a new
host, otherwise Django rejects every request with a 400.

## Deploy steps

```bash
pip install -r requirements.txt
python manage.py migrate
python manage.py collectstatic --noinput
gunicorn rpg_panel.wsgi:application
```

The `Procfile` chains the last two commands, so platforms that read it need
no extra configuration.

## Static and media files

- **Static** (`/static/`) — collected into `staticfiles/` and served by
  **WhiteNoise** with compressed, hashed filenames. `collectstatic` is
  mandatory on every deploy; skipping it breaks all CSS/JS because the
  manifest storage refuses to serve unhashed names.
- **Media** (`/media/`) — user uploads (avatars, banners, character and item
  images) are written to `media/` on local disk.

> ⚠️ **Ephemeral filesystems:** on platforms that reset the disk between
> deploys (Railway, Render free tiers, Heroku), uploaded images are lost on
> every redeploy. For a permanent setup, point media at object storage (S3
> or similar) via `django-storages`, or use a host with a persistent volume.

## Database

Development and the current deployment both use **SQLite**
(`db.sqlite3`, untracked). For a multi-user production setup, switch
`DATABASES` to PostgreSQL and run the migrations again — no model changes
are required.

## Migration branches

The migration history contains parallel branches from concurrent feature
work (two `0007_*`, `0008_*`, `0009_*` and `0010_*` migrations). Django
resolves them through their declared dependencies, so `migrate` runs
cleanly. If you add a migration and Django complains about multiple leaf
nodes, merge them with:

```bash
python manage.py makemigrations --merge
```
