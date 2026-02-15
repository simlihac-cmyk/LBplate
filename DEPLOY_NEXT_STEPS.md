# Deployment Next Steps (mac mini + Tailscale)

## Current assumptions
- Dev workspace: `/Users/sg_mac/lbplate_dev`
- Production workspace: `/Users/sg_mac/lbplate`
- Domain: `https://monosaccharide180.com`
- Django app port: `4000`
- WordPress port: `4080`
- Runtime in production: `tmux` session

## 1) One-time setup in `lbplate`
```bash
cd /Users/sg_mac/lbplate

# Pull latest deploy branch
git pull --ff-only origin main

# Create production env once
cp .env.production.example .env.production

# Generate and set secure secret key
python3 -c "import secrets; print(secrets.token_urlsafe(64))"
# paste into DJANGO_SECRET_KEY in .env.production
```

Production `.env.production` must include:
- `DJANGO_DEV_MODE=false`
- `DJANGO_DEBUG=false`
- `DJANGO_ALLOWED_HOSTS=monosaccharide180.com,www.monosaccharide180.com`
- `DJANGO_CSRF_TRUSTED_ORIGINS=https://monosaccharide180.com,https://www.monosaccharide180.com`
- `WP_BASE_URL=http://127.0.0.1:4080/wp-json/wp/v2`

## 2) Daily workflow (Dev -> Git -> Deploy)

### A. Develop and push from `lbplate_dev`
```bash
cd /Users/sg_mac/lbplate_dev
source /Users/sg_mac/lbplate_dev/venv/bin/activate

python manage.py check
python manage.py test core.tests -v 2

git add .
git commit -m "feat: describe change"
git push origin main
```

### B. Deploy from `lbplate`
```bash
cd /Users/sg_mac/lbplate

# If local file edits block pull, stash first
git stash push -m "temp before deploy" config/settings.py || true

git pull --ff-only origin main

source /Users/sg_mac/lbplate/venv/bin/activate
set -a && source .env.production && set +a

pip install -r requirements.txt
python manage.py check
python manage.py test core.tests -v 2
python manage.py collectstatic --noinput
```

### C. One-command deploy in `lbplate` (recommended)
`deploy.sh` is included in the repo root and automates:
- `git pull --ff-only`
- `pip install -r requirements.txt`
- `python manage.py check`
- `python manage.py test core.tests -v 2`
- `python manage.py collectstatic --noinput`
- tmux app restart (`lbplate` session)

```bash
cd /Users/sg_mac/lbplate
./deploy.sh
```

Useful options:
```bash
# skip tests
RUN_TESTS=0 ./deploy.sh

# skip pip install
PIP_INSTALL=0 ./deploy.sh

# disable auto-stash for config/settings.py
AUTO_STASH_SETTINGS=0 ./deploy.sh
```

## 3) Restart app in tmux (current operation mode)
Example if running Django in a tmux session:
```bash
tmux ls
tmux attach -t lbplate
# stop old process: Ctrl+C
cd /Users/sg_mac/lbplate
source /Users/sg_mac/lbplate/venv/bin/activate
set -a && source .env.production && set +a
python manage.py runserver 127.0.0.1:4000
```

Detach without stopping process:
```bash
Ctrl+b, then d
```

## 4) Reverse proxy check (HTTPS + security)
Nginx/Caddy should forward `X-Forwarded-Proto` to Django.

Nginx example:
```nginx
proxy_set_header X-Forwarded-Proto $scheme;
```

Quick validation points:
- `https://monosaccharide180.com` opens without redirect loop.
- Django app receives HTTPS context correctly.

## 5) Recommended next upgrades
- Replace `runserver` with `gunicorn` + process manager (`systemd` or `supervisor`).
- Move production DB from sqlite to PostgreSQL/MariaDB.
- Add error monitoring (Sentry) and structured logging.
