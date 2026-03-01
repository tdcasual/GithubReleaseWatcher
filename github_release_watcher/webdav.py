from __future__ import annotations

from pathlib import PurePosixPath
from typing import Any
from urllib.parse import quote

import requests

from .config import WebDAVConfig


class WebDAVError(RuntimeError):
    pass


def _normalize_base_url(base_url: str) -> str:
    url = str(base_url or "").strip()
    if not url:
        raise WebDAVError("webdav.base_url is required")
    return url.rstrip("/") + "/"


def _safe_rel_path(rel_path: str) -> str:
    raw = str(rel_path or "").strip()
    raw = raw.lstrip("/")
    if raw in ("", "."):
        return ""

    p = PurePosixPath(raw)
    if any(part in ("..", ".") for part in p.parts):
        raise WebDAVError("unsafe path")
    return "/".join(p.parts)


def _encode_path(rel_path: str, *, trailing_slash: bool) -> str:
    rel = _safe_rel_path(rel_path)
    if not rel:
        return "" if not trailing_slash else ""
    encoded = "/".join(quote(part, safe="") for part in rel.split("/"))
    if trailing_slash and not encoded.endswith("/"):
        encoded += "/"
    return encoded

class WebDAVClient:
    def __init__(self, config: WebDAVConfig):
        self._base_url = _normalize_base_url(config.base_url)
        self._timeout = max(5, int(config.timeout_seconds))
        self._verify = bool(config.verify_tls)
        self._auth = (config.username, config.password) if config.username and config.password else None
        self._session = requests.Session()

    def _url(self, rel_path: str, *, trailing_slash: bool = False) -> str:
        suffix = _encode_path(rel_path, trailing_slash=trailing_slash)
        return self._base_url if not suffix else self._base_url + suffix

    def _request(self, method: str, url: str, **kwargs: Any) -> requests.Response:
        return self._session.request(
            method,
            url,
            auth=self._auth,
            verify=self._verify,
            allow_redirects=True,
            timeout=(10, self._timeout),
            **kwargs,
        )

    def detect_capabilities(self) -> dict[str, bool]:
        caps = {
            "propfind": False,
            "mkcol": False,
            "put": False,
            "delete": False,
            "head": False,
            "move": False,
        }
        url = self._base_url
        resp = self._request("OPTIONS", url)
        try:
            allow_raw = str(resp.headers.get("Allow") or "")
            dav_raw = str(resp.headers.get("DAV") or "")
            methods = {x.strip().upper() for x in allow_raw.split(",") if x.strip()}
            caps["mkcol"] = "MKCOL" in methods
            caps["put"] = "PUT" in methods
            caps["delete"] = "DELETE" in methods
            caps["move"] = "MOVE" in methods
            caps["propfind"] = "PROPFIND" in methods or bool(dav_raw.strip())
        finally:
            resp.close()

        head_resp = self._request("HEAD", url)
        try:
            caps["head"] = head_resp.status_code != 405
        finally:
            head_resp.close()

        return caps

    def ensure_dir(self, rel_dir: str) -> None:
        rel = _safe_rel_path(rel_dir)
        if not rel:
            return
        parts = rel.split("/")
        current = ""
        for part in parts:
            current = f"{current}/{part}" if current else part
            url = self._url(current, trailing_slash=True)
            resp = self._request("MKCOL", url)
            try:
                if resp.status_code in (200, 201, 204, 405):
                    continue
                raise WebDAVError(f"MKCOL failed ({resp.status_code}): {resp.text[:500]}")
            finally:
                resp.close()

    def stat_file(self, rel_path: str) -> tuple[bool, int | None]:
        url = self._url(rel_path)
        resp = self._request("HEAD", url)
        try:
            if resp.status_code == 404:
                return False, None
            if resp.status_code in (401, 403):
                raise WebDAVError("unauthorized")
            if resp.status_code == 405:
                # Some servers disable HEAD; treat as unknown.
                return True, None
            if resp.status_code not in (200, 204):
                raise WebDAVError(f"HEAD failed ({resp.status_code}): {resp.text[:500]}")
            size_hdr = resp.headers.get("Content-Length")
            if size_hdr is None:
                return True, None
            try:
                return True, int(size_hdr)
            except ValueError:
                return True, None
        finally:
            resp.close()

    def put_bytes(self, rel_path: str, data: bytes, *, content_type: str = "application/octet-stream") -> None:
        parent = str(PurePosixPath(_safe_rel_path(rel_path)).parent)
        if parent and parent != ".":
            self.ensure_dir(parent)
        url = self._url(rel_path)
        resp = self._request("PUT", url, data=data, headers={"Content-Type": content_type})
        try:
            if resp.status_code in (200, 201, 204):
                return
            raise WebDAVError(f"PUT failed ({resp.status_code}): {resp.text[:500]}")
        finally:
            resp.close()

    def put_file(self, rel_path: str, local_path, *, content_type: str = "application/octet-stream") -> None:
        parent = str(PurePosixPath(_safe_rel_path(rel_path)).parent)
        if parent and parent != ".":
            self.ensure_dir(parent)
        url = self._url(rel_path)
        with open(local_path, "rb") as f:
            resp = self._request("PUT", url, data=f, headers={"Content-Type": content_type})
            try:
                if resp.status_code in (200, 201, 204):
                    return
                raise WebDAVError(f"PUT failed ({resp.status_code}): {resp.text[:500]}")
            finally:
                resp.close()

    def delete(self, rel_path: str, *, is_dir: bool = False) -> None:
        url = self._url(rel_path, trailing_slash=is_dir)
        resp = self._request("DELETE", url)
        try:
            if resp.status_code in (200, 202, 204, 404):
                return
            raise WebDAVError(f"DELETE failed ({resp.status_code}): {resp.text[:500]}")
        finally:
            resp.close()

    def move(self, src_rel_path: str, dst_rel_path: str, *, overwrite: bool = True) -> None:
        src_url = self._url(src_rel_path)
        dst_url = self._url(dst_rel_path)
        resp = self._request(
            "MOVE",
            src_url,
            headers={
                "Destination": dst_url,
                "Overwrite": "T" if overwrite else "F",
            },
        )
        try:
            if resp.status_code in (200, 201, 204):
                return
            raise WebDAVError(f"MOVE failed ({resp.status_code}): {resp.text[:500]}")
        finally:
            resp.close()

    def test_connection(self) -> None:
        url = self._base_url
        resp = self._request("PROPFIND", url, headers={"Depth": "0"}, data=b'<?xml version="1.0"?><propfind xmlns="DAV:"><prop><resourcetype/></prop></propfind>')
        try:
            if resp.status_code in (200, 207):
                return
            if resp.status_code in (401, 403):
                raise WebDAVError("unauthorized")
            raise WebDAVError(f"PROPFIND failed ({resp.status_code}): {resp.text[:500]}")
        finally:
            resp.close()
