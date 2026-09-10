from __future__ import annotations

import shutil
import json
import os
from pathlib import Path
from urllib.parse import urlencode
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from src.core.pipeline.layout import find_repo_root


API_ENDPOINT_JSON = "https://api.trafikinfo.trafikverket.se/v2/data.json"
LASTKAJEN_API_BASE = "https://lastkajen.trafikverket.se/api/"
LASTKAJEN_USERNAME_SECRET = "trafikverket_lastkajen_username"
LASTKAJEN_PASSWORD_SECRET = "trafikverket_lastkajen_password"


def read_api_key(root: Path | None = None) -> str:
    repo_root = find_repo_root(root)
    fallback_path = repo_root / "setup" / "secrets" / "trafikverket_api_key"
    api_key = os.environ.get("TRAFIKVERKET_API_KEY")
    if api_key:
        return api_key.strip()
    if fallback_path.exists():
        return fallback_path.read_text(encoding="utf-8").strip()
    raise RuntimeError(f"Set TRAFIKVERKET_API_KEY or create {fallback_path}.")


def trafikverket_api_call_json(request_xml: str, endpoint: str = API_ENDPOINT_JSON) -> dict:
    request = Request(
        endpoint,
        data=request_xml.encode("utf-8"),
        headers={"Content-Type": "text/xml; charset=utf-8"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=120) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {body}") from exc
    except URLError as exc:
        raise RuntimeError(f"Request failed: {exc}") from exc


def read_lastkajen_credentials(root: Path | None = None) -> tuple[str, str]:
    repo_root = find_repo_root(root)
    secrets_dir = repo_root / "setup" / "secrets"
    username_path = secrets_dir / LASTKAJEN_USERNAME_SECRET
    password_path = secrets_dir / LASTKAJEN_PASSWORD_SECRET

    missing_paths = [path for path in [username_path, password_path] if not path.exists()]
    if missing_paths:
        expected = ", ".join(str(path) for path in [username_path, password_path])
        raise RuntimeError(f"Create Lastkajen credential files: {expected}.")

    username = username_path.read_text(encoding="utf-8").strip()
    password = password_path.read_text(encoding="utf-8").strip()
    if not username or not password:
        expected = ", ".join(str(path) for path in [username_path, password_path])
        raise RuntimeError(f"Lastkajen credential files must be non-empty: {expected}.")
    return username, password


def _lastkajen_url(path_or_url: str, params: dict[str, object] | None = None) -> str:
    if path_or_url.startswith("http://") or path_or_url.startswith("https://"):
        base_url = path_or_url
    else:
        base_url = f"{LASTKAJEN_API_BASE.rstrip('/')}/{path_or_url.lstrip('/')}"
    if not params:
        return base_url
    query = urlencode({key: value for key, value in params.items() if value is not None})
    separator = "&" if "?" in base_url else "?"
    return f"{base_url}{separator}{query}"


def _read_json_response(request: Request, *, timeout: int = 120):
    try:
        with urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {body}") from exc
    except URLError as exc:
        raise RuntimeError(f"Request failed: {exc}") from exc


def lastkajen_login(root: Path | None = None) -> dict:
    username, password = read_lastkajen_credentials(root)
    request = Request(
        _lastkajen_url("Identity/Login"),
        data=json.dumps({"UserName": username, "Password": password}).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    payload = _read_json_response(request)
    if not isinstance(payload, dict) or not payload.get("access_token"):
        raise RuntimeError("Lastkajen login response did not contain an access token.")
    return payload


def lastkajen_authenticated_get(
    path_or_url: str,
    access_token: str,
    *,
    params: dict[str, object] | None = None,
    timeout: int = 120,
):
    request = Request(
        _lastkajen_url(path_or_url, params),
        headers={"Authorization": f"Bearer {access_token}"},
        method="GET",
    )
    return _read_json_response(request, timeout=timeout)


def lastkajen_download_file(
    download_token: str,
    destination: str | Path,
    *,
    path_or_url: str = "File/GetFileStream",
    timeout: int = 120,
) -> str:
    output_path = Path(destination)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    request = Request(_lastkajen_url(path_or_url, {"token": download_token}), method="GET")
    try:
        with urlopen(request, timeout=timeout) as response, output_path.open("wb") as handle:
            shutil.copyfileobj(response, handle)
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {body}") from exc
    except URLError as exc:
        raise RuntimeError(f"Request failed: {exc}") from exc
    return str(output_path)
