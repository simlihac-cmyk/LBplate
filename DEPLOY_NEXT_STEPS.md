# Deployment Next Steps (mac mini + Tailscale)

## Current assumptions
- Dev workspace: `/Users/sg_mac/lbplate_dev`
- Production workspace: `/Users/sg_mac/lbplate`
- Domain: `https://monosaccharide180.com`
- Django app port: `4000`
- WordPress port: `4080`

## 1. Separate env files by purpose
- Dev: keep `.env` in `lbplate_dev` with `DJANGO_DEBUG=true`.
- Prod: keep `.env.production` in `lbplate` with `DJANGO_DEBUG=false`, `DJANGO_DEV_MODE=false`.
- Verify in prod:
  - `DJANGO_ALLOWED_HOSTS=monosaccharide180.com,www.monosaccharide180.com`
  - `DJANGO_CSRF_TRUSTED_ORIGINS=https://monosaccharide180.com,https://www.monosaccharide180.com`
  - `WP_BASE_URL=http://127.0.0.1:4080/wp-json/wp/v2`

## 2. Build a repeatable deploy flow (dev -> prod)
- Keep deployment as pull/sync from `lbplate_dev` to `lbplate`.
- Recommended sequence in `lbplate`:
  1. `git pull`
  2. `source venv/bin/activate`
  3. `set -a && source .env.production && set +a`
  4. `python manage.py check`
  5. `python manage.py test core.tests -v 2`
  6. `python manage.py collectstatic --noinput`
  7. restart app process (systemd/supervisor)

## 3. Process management on port 4000
- Run Django via WSGI app server (gunicorn/uwsgi), not `runserver`.
- Example target: bind app to `127.0.0.1:4000` and reverse proxy from nginx/caddy.

## 4. Reverse proxy hardening
- TLS terminate at nginx/caddy.
- Route `monosaccharide180.com` -> `127.0.0.1:4000`.
- Keep `X-Forwarded-Proto` header so Django secure settings behave correctly.

## 5. Backup and rollback
- Before deploy:
  - DB backup (`db.sqlite3` if still using sqlite)
  - snapshot of `.env.production`
- Keep previous app revision available for quick rollback.

## 6. Remote operations via Tailscale
- Restrict admin/SSH by Tailscale ACL where possible.
- If direct Tailscale host access is needed in production, explicitly add tailnet host/IP to `DJANGO_ALLOWED_HOSTS`.

## 7. Next recommended upgrade
- Move production DB from sqlite to PostgreSQL or MariaDB for reliability under concurrent traffic.
- Add centralized error monitoring (Sentry) and structured logging.
