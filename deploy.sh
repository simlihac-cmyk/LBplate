#!/usr/bin/env bash
set -Eeuo pipefail

APP_DIR="${APP_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
REMOTE="${REMOTE:-origin}"
BRANCH="${BRANCH:-main}"
ENV_FILE="${ENV_FILE:-$APP_DIR/.env.production}"
VENV_ACTIVATE="${VENV_ACTIVATE:-$APP_DIR/venv/bin/activate}"
TMUX_SESSION="${TMUX_SESSION:-lbplate}"
APP_START_CMD="${APP_START_CMD:-python manage.py runserver 127.0.0.1:4000}"
RUN_TESTS="${RUN_TESTS:-1}"
PIP_INSTALL="${PIP_INSTALL:-1}"
AUTO_STASH_SETTINGS="${AUTO_STASH_SETTINGS:-1}"

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

restart_in_tmux() {
  local restart_cmd
  restart_cmd="cd $APP_DIR && source $VENV_ACTIVATE && set -a && source $ENV_FILE && set +a && $APP_START_CMD"

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

require_cmd git
require_cmd tmux
require_cmd python
require_cmd pip

cd "$APP_DIR"

[[ -f "$ENV_FILE" ]] || die "Missing env file: $ENV_FILE"
[[ -f "$VENV_ACTIVATE" ]] || die "Missing venv activate file: $VENV_ACTIVATE"
[[ -f "$APP_DIR/manage.py" ]] || die "manage.py not found in APP_DIR: $APP_DIR"

if [[ "$AUTO_STASH_SETTINGS" == "1" ]] && ! git diff --quiet -- config/settings.py; then
  log "Auto-stashing local changes in config/settings.py"
  git stash push -m "auto-stash: deploy config/settings.py" config/settings.py >/dev/null
fi

log "Pulling latest code from $REMOTE/$BRANCH"
git pull --ff-only "$REMOTE" "$BRANCH"

# shellcheck disable=SC1090
source "$VENV_ACTIVATE"
set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

if [[ "$PIP_INSTALL" == "1" ]]; then
  log "Installing requirements"
  pip install -r requirements.txt
fi

log "Running django checks"
python manage.py check

if [[ "$RUN_TESTS" == "1" ]]; then
  log "Running tests"
  python manage.py test core.tests -v 2
fi

log "Collecting static files"
python manage.py collectstatic --noinput

restart_in_tmux

log "Deployment complete."
log "tmux attach -t $TMUX_SESSION"
