"""Cliente HTTP mínimo (stdlib) com transporte injetável para testes."""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable


class ProviderError(RuntimeError):
    pass


# transporte: (method, url, headers, body_bytes|None, timeout) -> (status, body_bytes)
Transport = Callable[[str, str, dict, "bytes | None", float], "tuple[int, bytes]"]


def _urllib_transport(method, url, headers, body, timeout):
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except urllib.error.URLError as e:
        raise ProviderError(f"falha de rede: {e.reason}") from e


class HttpClient:
    def __init__(self, transport: Transport | None = None, timeout: float = 45.0):
        self.transport = transport or _urllib_transport
        self.timeout = timeout

    def request(self, method: str, url: str, *, params: dict | None = None,
                headers: dict | None = None, json_body: Any = None,
                form: dict | None = None) -> dict:
        if params:
            url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
        hdrs = {"Accept": "application/json", "User-Agent": "FlightHunterAI/0.1", **(headers or {})}
        body = None
        if json_body is not None:
            body = json.dumps(json_body).encode()
            hdrs["Content-Type"] = "application/json"
        elif form is not None:
            body = urllib.parse.urlencode(form).encode()
            hdrs["Content-Type"] = "application/x-www-form-urlencoded"
        status, raw = self.transport(method, url, hdrs, body, self.timeout)
        try:
            data = json.loads(raw.decode() or "{}")
        except ValueError:
            data = {"_raw": raw[:300].decode(errors="replace")}
        if status >= 400:
            # nunca inclui URL (pode conter api_key) na mensagem
            raise ProviderError(f"HTTP {status}: {str(data)[:300]}")
        return data
