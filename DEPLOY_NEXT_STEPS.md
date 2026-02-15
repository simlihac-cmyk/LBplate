# Deployment Next Steps (mac mini + Tailscale)

## Current assumptions
- Dev workspace: `/Users/sg_mac/lbplate_dev`
- Production workspace: `/Users/sg_mac/lbplate`
- Domain: `https://monosaccharide180.com`
- Django app port: `4000`
- WordPress port: `4080`
- Current runtime: `tmux` session (`lbplate`)
- Next runtime target: `gunicorn` (`systemd` optional)

## 1) One-time setup in `lbplate`
```bash
cd /Users/sg_mac/lbplate

git pull --ff-only origin main

# Create production env once
cp .env.production.example .env.production

# Generate a secure key
python3 -c "import secrets; print(secrets.token_urlsafe(64))"
# paste into DJANGO_SECRET_KEY in .env.production
```

Required values in `.env.production`:
- `DJANGO_DEV_MODE=false`
- `DJANGO_DEBUG=false`
- `DJANGO_ALLOWED_HOSTS=monosaccharide180.com,www.monosaccharide180.com`
- `DJANGO_CSRF_TRUSTED_ORIGINS=https://monosaccharide180.com,https://www.monosaccharide180.com`
- `WP_BASE_URL=http://127.0.0.1:4080/wp-json/wp/v2`
- `WP_CACHE_TIMEOUT=300`
- `WP_SITEMAP_CACHE_TIMEOUT=3600`
- `DJANGO_USE_X_FORWARDED_PROTO=true`
- `GA4_MEASUREMENT_ID=G-XXXXXXXXXX`  # 사용하지 않으면 비워도 됨

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

### B. Deploy in `lbplate` (recommended: one command)
```bash
cd /Users/sg_mac/lbplate
./deploy.sh
```

`deploy.sh` does:
- `git pull --ff-only`
- `pip install -r requirements.txt`
- `python manage.py check`
- `python manage.py test core.tests -v 2`
- `python manage.py collectstatic --noinput`
- restart app in tmux session `lbplate`

Useful options:
```bash
# dry-run (no actual changes)
DRY_RUN=1 ./deploy.sh

# skip tests
RUN_TESTS=0 ./deploy.sh

# skip pip install
PIP_INSTALL=0 ./deploy.sh

# disable config/settings.py auto-stash
AUTO_STASH_SETTINGS=0 ./deploy.sh

# run tests with production flags 그대로 사용
TEST_FORCE_DEV_MODE=0 ./deploy.sh

# rollback on failure (dangerous if local uncommitted changes exist)
AUTO_ROLLBACK=1 ./deploy.sh
```

## 3) Runtime mode choices

### Option A. Keep tmux (current)
`deploy.sh` already supports this. Keep using `tmux` if stable for your ops.

Check/attach:
```bash
tmux ls
tmux attach -t lbplate
```

Detach:
```bash
Ctrl+b, then d
```

### Option B. Move to systemd + gunicorn (Linux host only)
Files already included:
- `gunicorn.conf.py`
- `deploy/systemd/lbplate.service`
- `deploy/systemd/README.md`

Apply:
```bash
sudo cp /Users/sg_mac/lbplate/deploy/systemd/lbplate.service /etc/systemd/system/lbplate.service
sudo systemctl daemon-reload
sudo systemctl enable lbplate
sudo systemctl restart lbplate
sudo systemctl status lbplate --no-pager
```

## 4) Reverse proxy check (HTTPS + security)
Nginx/Caddy should pass `X-Forwarded-Proto`.

Nginx example:
```nginx
proxy_set_header X-Forwarded-Proto $scheme;
```

Validation:
- `https://monosaccharide180.com` opens without redirect loop
- Django receives HTTPS context correctly

## 5) Tailscale impact
- These changes do not change Tailscale tunnel topology.
- As long as app bind remains local (`127.0.0.1:4000`) and reverse proxy is on the same host, Tailscale remote IDE workflow is unaffected.
- If you need direct tailnet access in production, add tailnet host/IP to `DJANGO_ALLOWED_HOSTS`.

## 6) Next recommended upgrades
- Move production DB from SQLite to PostgreSQL
- Add monitoring/alerts (Sentry + webhook)
- Add backup/restore script and weekly restore drill
