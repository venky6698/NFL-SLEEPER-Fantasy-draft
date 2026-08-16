from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


class HttpError(RuntimeError):
    pass


def request_json(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    body: Any = None,
    timeout: float = 20.0,
) -> Any:
    data = None
    request_headers = {
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0 AppleWebKit/537.36 draft-analyst/0.1",
        **(headers or {}),
    }
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        request_headers.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url, data=data, headers=request_headers, method=method.upper())
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            content_type = resp.headers.get("content-type", "")
    except urllib.error.HTTPError as exc:
        raw_error = exc.read().decode("utf-8", errors="replace")
        raise HttpError(f"{method} {url} failed: HTTP {exc.code} {raw_error[:500]}") from exc
    except urllib.error.URLError as exc:
        raise HttpError(f"{method} {url} failed: {exc.reason}") from exc

    if "text/event-stream" in content_type or raw.startswith("event:") or raw.startswith("data:"):
        for line in raw.splitlines():
            if line.startswith("data:"):
                payload = line.removeprefix("data:").strip()
                if payload and payload != "[DONE]":
                    return json.loads(payload)
        raise HttpError(f"{method} {url} returned empty event stream")
    return json.loads(raw) if raw else None


def url_join(base: str, path: str) -> str:
    return urllib.parse.urljoin(base.rstrip("/") + "/", path.lstrip("/"))
