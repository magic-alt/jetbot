from __future__ import annotations

import http.client
import os
import sys
import time
import urllib.error
import urllib.request
import webbrowser


def _env_flag(name: str, default: bool = True) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() not in {"0", "false", "no", "off"}


def main() -> int:
    health_url = os.getenv("JETBOT_HEALTHCHECK_URL", "http://127.0.0.1:18000/health")
    ui_url = os.getenv("JETBOT_UI_URL", "http://127.0.0.1:18000/ui/")
    timeout_seconds = float(os.getenv("JETBOT_UI_OPEN_TIMEOUT", "90"))
    open_browser = _env_flag("JETBOT_OPEN_BROWSER", default=True)

    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(health_url, timeout=2) as response:
                if 200 <= response.status < 300:
                    break
        except (
            http.client.RemoteDisconnected,
            urllib.error.HTTPError,
            urllib.error.URLError,
            TimeoutError,
        ):
            time.sleep(1)
    else:
        print(
            f"Jetbot did not become healthy within {timeout_seconds:.0f}s. Check 'docker compose ps' and open {ui_url} manually.",
            file=sys.stderr,
        )
        return 1

    if not open_browser:
        print(f"Jetbot UI is ready at {ui_url}")
        return 0

    opened = False
    try:
        opened = webbrowser.open(ui_url, new=2)
    except webbrowser.Error:
        opened = False

    if opened:
        print(f"Jetbot UI is ready at {ui_url}")
    else:
        print(f"Jetbot UI is ready at {ui_url}. Open it manually if your browser did not launch.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())