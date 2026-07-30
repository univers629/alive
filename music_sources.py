# coding: utf-8
"""Metadata and visitor-side stream resolver for public NetEase tracks."""

from __future__ import annotations

from dataclasses import dataclass
import re
from time import time
from typing import Any
from urllib.parse import urlencode, urlparse, urlunparse

import httpx


LRC_TIMESTAMP = re.compile(r"\[(\d{1,3}):(\d{2}(?:\.\d{1,3})?)\]")
NETEASE_ID = re.compile(r"^[1-9]\d{0,19}$")
MAX_RESOLVER_RESPONSE = 2 * 1024 * 1024


@dataclass(frozen=True)
class NeteaseResolution:
    available: bool
    song_id: str
    title: str = ""
    artist: str = ""
    cover_url: str = ""
    audio_url: str = ""
    lyrics: tuple[dict[str, Any], ...] = ()
    status: str = ""


def parse_lrc(value: str) -> tuple[dict[str, Any], ...]:
    """Convert ordinary LRC text into Alive's timestamped lyric rows."""
    rows: list[dict[str, Any]] = []
    for raw_line in value.replace("\r", "\n").split("\n"):
        timestamps = list(LRC_TIMESTAMP.finditer(raw_line))
        if not timestamps:
            continue
        text = LRC_TIMESTAMP.sub("", raw_line).strip()
        if not text:
            continue
        match = timestamps[0]
        seconds = int(match.group(1)) * 60 + float(match.group(2))
        rows.append(
            {
                "time": round(seconds, 3),
                "text": text[:500],
                "translation": "",
            }
        )
    rows.sort(key=lambda row: row["time"])
    return tuple(rows[:5000])


def _api_base(value: str) -> str:
    parsed = urlparse(value.strip())
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.fragment
    ):
        raise ValueError("Meting API must be a plain HTTPS URL")
    return urlunparse(("https", parsed.netloc, parsed.path or "/", "", "", ""))


def _api_url(base: str, kind: str, song_id: str) -> str:
    query = urlencode({"server": "netease", "type": kind, "id": song_id})
    return f"{base}?{query}"


def _trusted_result_url(value: str, allowed_hosts: set[str]) -> str:
    parsed = urlparse(value)
    if (
        parsed.scheme == "https"
        and parsed.hostname
        and parsed.hostname.casefold() in allowed_hosts
        and not parsed.username
        and not parsed.password
    ):
        return value
    return ""


class NeteaseResolver:
    """Resolve metadata and a stable public stream endpoint for one song ID."""

    def __init__(self) -> None:
        self._cache: dict[
            tuple[str, tuple[str, ...]], tuple[float, NeteaseResolution]
        ] = {}

    def resolve(
        self,
        song_id: str,
        api_values: list[str],
        timeout: float,
    ) -> NeteaseResolution:
        song_id = str(song_id).strip()
        if not NETEASE_ID.fullmatch(song_id):
            raise ValueError("NetEase song ID must contain 1 to 20 digits")

        bases: list[str] = []
        for value in api_values:
            if value.strip():
                base = _api_base(value)
                if base not in bases:
                    bases.append(base)
        if not bases:
            return NeteaseResolution(
                available=False,
                song_id=song_id,
                status="未配置网易云公开流媒体解析接口",
            )

        cache_key = (song_id, tuple(bases))
        cached = self._cache.get(cache_key)
        if cached and cached[0] > time():
            return cached[1]

        allowed_hosts = {
            urlparse(base).hostname.casefold()
            for base in bases
            if urlparse(base).hostname
        }
        with httpx.Client(
            timeout=timeout,
            follow_redirects=False,
            trust_env=False,
            headers={"User-Agent": "Alive-Music-Resolver/1.0"},
        ) as client:
            for base in bases:
                try:
                    response = client.get(
                        base,
                        params={"server": "netease", "type": "song", "id": song_id},
                    )
                    response.raise_for_status()
                    if len(response.content) > MAX_RESOLVER_RESPONSE:
                        raise ValueError("song response is too large")
                    payload = response.json()
                    item = payload[0] if isinstance(payload, list) and payload else payload
                    if not isinstance(item, dict):
                        raise ValueError("song response has no object")

                    lrc_response = client.get(
                        base,
                        params={"server": "netease", "type": "lrc", "id": song_id},
                    )
                    lyrics: tuple[dict[str, Any], ...] = ()
                    if (
                        lrc_response.is_success
                        and len(lrc_response.content) <= MAX_RESOLVER_RESPONSE
                    ):
                        lyrics = parse_lrc(lrc_response.text)

                    result = NeteaseResolution(
                        available=True,
                        song_id=song_id,
                        title=str(item.get("name") or "")[:300],
                        artist=str(item.get("artist") or "")[:300],
                        cover_url=_trusted_result_url(
                            str(item.get("pic") or ""), allowed_hosts
                        ),
                        # The browser opens this stable endpoint and follows its
                        # short-lived CDN redirect. Alive stores no NetEase audio.
                        audio_url=_api_url(base, "url", song_id),
                        lyrics=lyrics,
                    )
                    self._cache[cache_key] = (time() + 6 * 3600, result)
                    return result
                except (httpx.HTTPError, ValueError, TypeError):
                    continue

        result = NeteaseResolution(
            available=False,
            song_id=song_id,
            status="网易云公开流媒体暂时不可用，仅展示歌曲状态",
        )
        self._cache[cache_key] = (time() + 60, result)
        return result
