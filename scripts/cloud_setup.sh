#!/usr/bin/env bash
# Prepares a Claude Code cloud session; .claude/settings.json runs it at session start.
# Local sessions skip it. It never fails the session: anything missing is reported instead.

if [ "$CLAUDE_CODE_REMOTE" != "true" ]; then
  exit 0
fi
cd "$CLAUDE_PROJECT_DIR" || exit 0
log=$(mktemp)

run() {
  if ! "$@" >"$log" 2>&1; then
    echo "cloud_setup: '$*' failed:"
    tail -n 20 "$log"
    return 1
  fi
}

run uv sync --frozen

if [ -f scripts/vendor.py ]; then
  run uv run scripts/vendor.py
fi

# Playwright's download hosts are outside the default network allowlist, and a downloaded
# Chromium can still lack system libraries, so only a real launch counts. The image's own
# Chromium is the fallback; tests/e2e/conftest.py launches whatever E2E_CHROMIUM names.
image_chromium=/opt/pw-browsers/chromium

# Launches Chromium through Playwright: its own build, or the executable given as $1.
launches() {
  run uv run python -c "import sys; from playwright.sync_api import sync_playwright as p; s = p().start(); s.chromium.launch(executable_path=sys.argv[1] or None).close(); s.stop()" "${1:-}"
}

if run uv run playwright install chromium && launches; then
  echo "cloud_setup: Chromium launches; e2e tests can run here"
elif [ -x "$image_chromium" ] && launches "$image_chromium"; then
  if [ -n "$CLAUDE_ENV_FILE" ]; then
    echo "export E2E_CHROMIUM=$image_chromium" >>"$CLAUDE_ENV_FILE"
    echo "cloud_setup: $image_chromium launches and E2E_CHROMIUM names it; e2e tests can run here"
  else
    echo "cloud_setup: $image_chromium launches; run e2e tests with E2E_CHROMIUM=$image_chromium"
  fi
else
  echo "cloud_setup: no working Chromium; e2e tests run in CI only"
fi
exit 0
