#!/usr/bin/env bash
set -Eeuo pipefail

APP_DIR="${APP_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
REMOTE="${REMOTE:-origin}"
BRANCH="${BRANCH:-main}"
ENV_FILE="${ENV_FILE:-$APP_DIR/.env.production}"
VENV_ACTIVATE="${VENV_ACTIVATE:-$APP_DIR/venv/bin/activate}"
VENV_PYTHON="${VENV_PYTHON:-$APP_DIR/venv/bin/python}"
TMUX_SESSION="${TMUX_SESSION:-lbplate}"
APP_START_CMD="${APP_START_CMD:-$VENV_PYTHON -m gunicorn config.wsgi:application --config $APP_DIR/gunicorn.conf.py}"

RUN_TESTS="${RUN_TESTS:-1}"
PIP_INSTALL="${PIP_INSTALL:-1}"
AUTO_STASH_SETTINGS="${AUTO_STASH_SETTINGS:-1}"
AUTO_ROLLBACK="${AUTO_ROLLBACK:-0}"
DRY_RUN="${DRY_RUN:-0}"
TEST_FORCE_DEV_MODE="${TEST_FORCE_DEV_MODE:-1}"
NOTIFY_WEBHOOK_URL="${NOTIFY_WEBHOOK_URL:-}"

ROLLBACK_COMMIT=""

log() {
  printf '[deploy] %s\n' "$1"
}

die() {
  printf '[deploy][error] %s\n' "$1" >&2
  exit 1
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "Required command not found: $1"
}

run_cmd() {
  if [[ "$DRY_RUN" == "1" ]]; then
    printf '[deploy][dry-run] %s\n' "$*"
    return 0
  fi
  "$@"
}

notify() {
  local level="$1"
  local message="$2"

  if [[ -z "$NOTIFY_WEBHOOK_URL" ]]; then
    return 0
  fi

  if ! command -v curl >/dev/null 2>&1; then
    log "curl is not installed; skipping webhook notification"
    return 0
  fi

  if [[ "$DRY_RUN" == "1" ]]; then
    printf '[deploy][dry-run] webhook(%s): %s\n' "$level" "$message"
    return 0
  fi

  curl -sS -X POST "$NOTIFY_WEBHOOK_URL" \
    -H "Content-Type: application/json" \
    -d "{\"text\":\"[$level] $message\"}" >/dev/null || true
}

restart_in_tmux() {
  local restart_cmd
  restart_cmd="cd $APP_DIR && source $VENV_ACTIVATE && set -a && source $ENV_FILE && set +a && $APP_START_CMD"

  if [[ "$DRY_RUN" == "1" ]]; then
    printf '[deploy][dry-run] restart tmux session %s with: %s\n' "$TMUX_SESSION" "$restart_cmd"
    return 0
  fi

  if tmux has-session -t "$TMUX_SESSION" 2>/dev/null; then
    log "Restarting existing tmux session: $TMUX_SESSION"
    tmux send-keys -t "$TMUX_SESSION" C-c
    sleep 1
    tmux send-keys -t "$TMUX_SESSION" "$restart_cmd" C-m
  else
    log "Creating tmux session: $TMUX_SESSION"
    tmux new-session -d -s "$TMUX_SESSION" "bash -lc '$restart_cmd'"
  fi
}

on_error() {
  local exit_code="$1"
  local line_no="$2"

  log "Deployment failed at line ${line_no} (exit=${exit_code})"

  if [[ "$AUTO_ROLLBACK" == "1" && -n "$ROLLBACK_COMMIT" ]]; then
    log "Rolling back to commit: $ROLLBACK_COMMIT"
    if [[ "$DRY_RUN" == "1" ]]; then
      printf '[deploy][dry-run] git reset --hard %s\n' "$ROLLBACK_COMMIT"
    else
      git reset --hard "$ROLLBACK_COMMIT"
      restart_in_tmux
    fi
  fi

  notify "ERROR" "Deploy failed on $(hostname) at line ${line_no}."
  exit "$exit_code"
}

trap 'on_error $? $LINENO' ERR

require_cmd git
require_cmd tmux

cd "$APP_DIR"

[[ -f "$ENV_FILE" ]] || die "Missing env file: $ENV_FILE"
[[ -f "$VENV_ACTIVATE" ]] || die "Missing venv activate file: $VENV_ACTIVATE"
[[ -x "$VENV_PYTHON" ]] || die "Missing venv python executable: $VENV_PYTHON"
[[ -f "$APP_DIR/manage.py" ]] || die "manage.py not found in APP_DIR: $APP_DIR"

if [[ "$AUTO_STASH_SETTINGS" == "1" ]] && ! git diff --quiet -- config/settings.py; then
  log "Auto-stashing local changes in config/settings.py"
  run_cmd git stash push -m "auto-stash: deploy config/settings.py" config/settings.py
fi

ROLLBACK_COMMIT="$(git rev-parse HEAD)"
log "Rollback point: $ROLLBACK_COMMIT"

log "Pulling latest code from $REMOTE/$BRANCH"
run_cmd git pull --ff-only "$REMOTE" "$BRANCH"

if [[ "$DRY_RUN" != "1" ]]; then
  # shellcheck disable=SC1090
  source "$VENV_ACTIVATE"
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
fi

if [[ "$PIP_INSTALL" == "1" ]]; then
  log "Installing requirements"
  run_cmd "$VENV_PYTHON" -m pip install -r requirements.txt
fi

log "Running django checks"
run_cmd "$VENV_PYTHON" manage.py check

if [[ "$RUN_TESTS" == "1" ]]; then
  log "Running tests"
  if [[ "$TEST_FORCE_DEV_MODE" == "1" ]]; then
    # Keep prod HTTPS/security flags from causing 301 redirects in Django test client.
    run_cmd env DJANGO_DEV_MODE=true DJANGO_DEBUG=true DJANGO_SECURE_SSL_REDIRECT=false DJANGO_SESSION_COOKIE_SECURE=false DJANGO_CSRF_COOKIE_SECURE=false "$VENV_PYTHON" manage.py test core.tests -v 2
  else
    run_cmd "$VENV_PYTHON" manage.py test core.tests -v 2
  fi
fi

log "Collecting static files"
run_cmd "$VENV_PYTHON" manage.py collectstatic --noinput

restart_in_tmux

notify "OK" "Deploy succeeded on $(hostname) for ${BRANCH}."
log "Deployment complete."
log "tmux attach -t $TMUX_SESSION"
