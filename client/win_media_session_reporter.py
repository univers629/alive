# coding: utf-8
"""把 Windows 当前媒体会话上报给 Alive。

本地音乐：从 Windows 媒体会话读取播放状态，按文件名或内嵌标签在本机音乐目录
中定位音频；上传当前文件，并使用它的歌名、歌手、专辑、时长和内嵌封面。

网易云音乐：从客户端的 webdb.dat / cloudmusic.elog 取得歌曲 ID，交给 Alive
解析歌词和公开流媒体地址；不会上传网易云本地缓存文件，也不会保存账号 Cookie。

安装：
    py -m pip install -r client/requirements-windows.txt

运行：
    py client/win_media_session_reporter.py
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import hashlib
import json
import os
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from time import monotonic
from typing import Any

import requests
from mutagen import File as MutagenFile  # type: ignore
from mutagen.flac import Picture  # type: ignore
from winsdk.windows.media.control import (  # type: ignore
    GlobalSystemMediaTransportControlsSessionManager as MediaSessionManager,
    GlobalSystemMediaTransportControlsSessionPlaybackStatus as PlaybackStatus,
)


SUPPORTED_AUDIO = {".flac", ".mp3", ".m4a", ".wav", ".ogg", ".opus"}
UPLOAD_CONTENT_TYPES = {
    ".flac": "audio/flac",
    ".mp3": "audio/mpeg",
    ".m4a": "audio/mp4",
    ".wav": "audio/wav",
    ".ogg": "audio/ogg",
    ".opus": "audio/ogg",
}
BROWSER_MEDIA_SOURCES = {
    "chrome",
    "msedge",
    "firefox",
    "brave",
    "vivaldi",
    "opera",
    "chromium",
}


def project_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if value:
        return value
    env_file = Path(__file__).resolve().parents[1] / ".env"
    try:
        for raw_line in env_file.read_text(encoding="utf-8-sig").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            if key.strip() == name:
                return value.strip().strip("\"'")
    except FileNotFoundError:
        pass
    return ""


def server_url(value: str) -> str:
    """Return an absolute Alive base URL accepted by requests."""
    value = value.strip().rstrip("/")
    if "://" not in value:
        return f"https://{value}"
    return value


def log(message: str) -> None:
    print(f"[{datetime.now():%H:%M:%S}] {message}", flush=True)


def normalized(value: str) -> str:
    return "".join(character.casefold() for character in value if character.isalnum())


@dataclass(frozen=True)
class LocalTrack:
    path: Path
    title: str = ""
    artist: str = ""
    album: str = ""
    duration: float = 0


class MusicLibrary:
    """Local audio index that uses embedded tags only for local-upload tracks."""

    def __init__(self, root: Path, explicit_file: Path | None = None):
        self.root = root.resolve()
        self.explicit_file = explicit_file.resolve() if explicit_file else None
        self.tracks: list[LocalTrack] = []
        self._covers: dict[Path, tuple[bytes, str] | None] = {}

    @staticmethod
    def _tag_value(tags: Any, key: str) -> str:
        if tags is None:
            return ""
        value = tags.get(key)
        if isinstance(value, (list, tuple)):
            value = value[0] if value else ""
        return str(value or "").strip()

    @classmethod
    def _read_track(cls, path: Path) -> LocalTrack:
        try:
            audio = MutagenFile(path, easy=True)
            tags = getattr(audio, "tags", None)
            duration = float(getattr(getattr(audio, "info", None), "length", 0) or 0)
            return LocalTrack(
                path=path,
                title=cls._tag_value(tags, "title"),
                artist=cls._tag_value(tags, "artist"),
                album=cls._tag_value(tags, "album"),
                duration=max(0, duration),
            )
        except Exception:
            return LocalTrack(path=path)

    @staticmethod
    def _image_type(content: bytes) -> str:
        if content.startswith(b"\xff\xd8\xff"):
            return "image/jpeg"
        if content.startswith(b"\x89PNG\r\n\x1a\n"):
            return "image/png"
        if content.startswith(b"RIFF") and content[8:12] == b"WEBP":
            return "image/webp"
        return ""

    def cover(self, track: LocalTrack) -> tuple[bytes, str] | None:
        if track.path in self._covers:
            return self._covers[track.path]
        content = b""
        try:
            audio = MutagenFile(track.path, easy=False)
            pictures = getattr(audio, "pictures", None)
            if pictures:
                content = bytes(pictures[0].data)
            tags = getattr(audio, "tags", None)
            if not content and tags is not None and hasattr(tags, "getall"):
                frames = tags.getall("APIC")
                if frames:
                    content = bytes(frames[0].data)
            if not content and tags is not None:
                covers = tags.get("covr")
                if covers:
                    value = covers[0] if isinstance(covers, (list, tuple)) else covers
                    content = bytes(value)
            if not content and tags is not None:
                encoded = tags.get("metadata_block_picture")
                if encoded:
                    value = encoded[0] if isinstance(encoded, (list, tuple)) else encoded
                    content = Picture(base64.b64decode(str(value))).data
        except Exception:
            content = b""
        media_type = self._image_type(content)
        result = (content, media_type) if media_type and len(content) <= 3 * 1024 * 1024 else None
        self._covers[track.path] = result
        return result

    def scan(self) -> None:
        if self.explicit_file:
            if (
                not self.explicit_file.is_file()
                or self.explicit_file.suffix.casefold() not in SUPPORTED_AUDIO
            ):
                raise SystemExit(f"--file 不是受支持的音频文件：{self.explicit_file}")
            self.tracks = [self._read_track(self.explicit_file)]
            log(f"本次固定上传文件：{self.explicit_file}")
            return
        if not self.root.is_dir():
            log(f"音乐目录不存在：{self.root}")
            self.tracks = []
            return
        self.tracks = [
            self._read_track(path)
            for path in self.root.rglob("*")
            if path.is_file() and path.suffix.casefold() in SUPPORTED_AUDIO
        ]
        tagged = sum(bool(track.title or track.artist or track.album) for track in self.tracks)
        log(
            f"已索引 {len(self.tracks)} 首本地音频：{self.root}；"
            f"其中 {tagged} 首读取到内嵌标签"
        )

    def match(self, title: str, artist: str) -> LocalTrack | None:
        if self.explicit_file and self.tracks:
            return self.tracks[0]
        wanted_title = normalized(title)
        wanted_artist = normalized(artist)
        best: tuple[int, LocalTrack] | None = None
        for track in self.tracks:
            stem = normalized(track.path.stem)
            tagged_title = normalized(track.title)
            if not wanted_title or (
                wanted_title not in stem
                and tagged_title != wanted_title
                and wanted_title not in tagged_title
            ):
                continue
            score = 12 if tagged_title == wanted_title else (8 if stem == wanted_title else 5)
            tagged_artist = normalized(track.artist)
            if wanted_artist and (
                wanted_artist in stem or wanted_artist in tagged_artist
            ):
                score += 4
            score -= min(len(stem) - len(wanted_title), 20) // 5
            if best is None or score > best[0]:
                best = (score, track)
        return best[1] if best else None


@dataclass(frozen=True)
class NowPlaying:
    source_id: str
    title: str
    artist: str
    album: str
    duration: float
    position: float
    playing: bool


@dataclass(frozen=True)
class NeteaseTrack:
    song_id: str
    title: str = ""
    artist: str = ""
    album: str = ""
    cover_url: str = ""
    duration: float = 0


def _netease_detail(value: Any) -> NeteaseTrack | None:
    if not isinstance(value, dict):
        return None
    if isinstance(value.get("track"), dict):
        value = value["track"]
    song_id = str(value.get("id") or value.get("songId") or "").strip()
    if not re.fullmatch(r"[1-9]\d{0,19}", song_id):
        return None
    artists_value = value.get("artists")
    artists = [
        str(artist.get("name") or "").strip()
        for artist in artists_value
        if isinstance(artist, dict)
    ] if isinstance(artists_value, list) else []
    album_value = value.get("album") if isinstance(value.get("album"), dict) else {}
    raw_duration = float(value.get("duration") or value.get("songDuration") or 0)
    duration = raw_duration / 1000 if raw_duration > 86400 else raw_duration
    return NeteaseTrack(
        song_id=song_id,
        title=str(value.get("name") or "").strip(),
        artist=" / ".join(name for name in artists if name),
        album=str(album_value.get("name") or album_value.get("albumName") or "").strip(),
        cover_url=str(
            album_value.get("picUrl")
            or album_value.get("cover")
            or value.get("cover")
            or ""
        ).strip(),
        duration=max(0, duration),
    )


class NeteaseDetector:
    """Port of the reference project's local ID idea, without its Telegram code."""

    def __init__(self, root: Path):
        self.root = root.resolve()
        self.database = self.root / "Library" / "webdb.dat"
        self.elog = self.root / "cloudmusic.elog"
        self._elog_signature: tuple[int, int] | None = None
        self._elog_track: NeteaseTrack | None = None
        self._elog_position = 0.0
        self._elog_playing = False
        self._elog_exited = False
        self._elog_clock = monotonic()
        self._elog_offset = 0
        self._elog_partial_line = ""

    @property
    def available(self) -> bool:
        return self.database.is_file() or self.elog.is_file()

    @staticmethod
    def _same_song(track: NeteaseTrack, playing: NowPlaying) -> bool:
        if not track.title:
            return True
        detected = normalized(track.title)
        current = normalized(playing.title)
        return bool(
            detected
            and current
            and (detected == current or detected in current or current in detected)
        )

    def _from_database(self) -> NeteaseTrack | None:
        if not self.database.is_file():
            return None
        uri = f"file:{self.database.as_posix()}?mode=ro"
        try:
            connection = sqlite3.connect(uri, uri=True, timeout=1)
            try:
                row = connection.execute(
                    "SELECT jsonStr FROM historyTracks "
                    "ORDER BY playtime DESC LIMIT 1"
                ).fetchone()
            finally:
                connection.close()
            return _netease_detail(json.loads(row[0])) if row else None
        except (OSError, sqlite3.Error, json.JSONDecodeError, TypeError):
            return None

    @staticmethod
    def _decode_elog(content: bytes) -> str:
        decoded = bytes(
            (
                ((byte // 16) ^ ((byte % 16) + 8)) % 16 * 16
                + (byte // 64) * 4
                + (~(byte // 16) & 3)
            )
            for byte in content
        )
        return decoded.decode("utf-8", "ignore")

    @staticmethod
    def _json_from_line(line: str) -> dict[str, Any] | None:
        start = line.find("{")
        if start < 0:
            return None
        try:
            value, _ = json.JSONDecoder().raw_decode(line[start:])
            return value if isinstance(value, dict) else None
        except json.JSONDecodeError:
            return None

    def _current_elog_position(self, now: float | None = None) -> float:
        clock = monotonic() if now is None else now
        position = self._elog_position
        if self._elog_playing:
            position += max(0, clock - self._elog_clock)
        if self._elog_track and self._elog_track.duration > 0:
            duration = self._elog_track.duration
            # Some 网易云 versions do not log a seek back to zero for single-track
            # repeat, even though playback remains active.
            position = position % duration if self._elog_playing else min(position, duration)
        return max(0, position)

    def _set_elog_playing(self, playing: bool, now: float) -> None:
        self._elog_position = self._current_elog_position(now)
        self._elog_clock = now
        self._elog_playing = playing

    def _set_elog_position(self, position: float, now: float) -> None:
        self._elog_position = max(0, position)
        self._elog_clock = now

    def _consume_elog_lines(self, lines: list[str], now: float) -> None:
        for line in lines:
            if '【app】,{"actionId":"exitApp"}' in line:
                self._set_elog_playing(False, now)
                self._elog_exited = True
                continue
            position_match = re.search(
                r'【playing】,"setPlayingPosition",(\d+(?:\.\d+)?)',
                line,
            )
            if position_match:
                self._set_elog_position(float(position_match.group(1)), now)
                self._elog_exited = False
                continue
            status_match = re.search(
                r'【playing】,"native播放state",(\d+),',
                line,
            )
            if status_match:
                status = int(status_match.group(1))
                if status in {1, 2}:
                    self._set_elog_playing(status == 1, now)
                    self._elog_exited = False
                continue
            if not any(
                marker in line
                for marker in (
                    '"checkPlayPrivilege"',
                    '"playOneTrackInPlayingList"',
                    '"native播放资源load完成，开始播放"',
                )
            ):
                continue
            value = self._json_from_line(line)
            candidate = _netease_detail(value)
            if candidate:
                if (
                    self._elog_track is not None
                    and self._elog_track.song_id != candidate.song_id
                ):
                    self._set_elog_position(0, now)
                self._elog_track = candidate
                self._elog_exited = False

    def _from_elog(self) -> NeteaseTrack | None:
        if not self.elog.is_file():
            return None
        try:
            stat = self.elog.stat()
            signature = (stat.st_mtime_ns, stat.st_size)
            if signature == self._elog_signature:
                return self._elog_track
            if self._elog_offset and stat.st_size >= self._elog_offset:
                start = self._elog_offset
            else:
                start = max(0, stat.st_size - 8 * 1024 * 1024)
                self._elog_partial_line = ""
            with self.elog.open("rb") as file:
                file.seek(start)
                decoded = self._decode_elog(file.read())
        except OSError:
            return self._elog_track

        self._elog_offset = stat.st_size
        text = self._elog_partial_line + decoded
        parts = text.splitlines(keepends=True)
        lines: list[str] = []
        self._elog_partial_line = ""
        for index, part in enumerate(parts):
            if part.endswith(("\r", "\n")):
                lines.append(part.rstrip("\r\n"))
            elif index == len(parts) - 1:
                self._elog_partial_line = part
            else:
                lines.append(part)

        self._consume_elog_lines(lines, monotonic())
        self._elog_signature = signature
        return self._elog_track

    def lookup(self, playing: NowPlaying) -> NeteaseTrack | None:
        for track in (self._from_database(), self._from_elog()):
            if track and self._same_song(track, playing):
                return track
        return None

    def now_playing(self) -> NowPlaying | None:
        """Fallback when CloudMusic does not register a Windows media session."""
        elog_track = self._from_elog()
        if self._elog_exited:
            return None
        track = elog_track or self._from_database()
        if track is None:
            return None
        return NowPlaying(
            source_id="cloudmusic.elog",
            title=track.title,
            artist=track.artist,
            album=track.album,
            duration=track.duration,
            position=self._current_elog_position(),
            playing=self._elog_playing,
        )


async def read_now_playing(manager: Any) -> NowPlaying | None:
    sessions = [
        session
        for session in manager.get_sessions()
        if not any(
            browser in str(session.source_app_user_model_id or "").casefold()
            for browser in BROWSER_MEDIA_SOURCES
        )
    ]
    if not sessions:
        return None

    def session_priority(session: Any) -> int:
        source = str(session.source_app_user_model_id or "").casefold()
        priority = 0
        if "zunemusic" in source:
            priority += 100
        elif any(name in source for name in ("wmplayer", "cloudmusic", "spotify", "foobar")):
            priority += 80
        if session.get_playback_info().playback_status == PlaybackStatus.PLAYING:
            priority += 20
        return priority

    selected = max(sessions, key=session_priority)
    properties = await selected.try_get_media_properties_async()
    if not properties or not str(properties.title or "").strip():
        return None
    timeline = selected.get_timeline_properties()
    status = selected.get_playback_info().playback_status
    return NowPlaying(
        source_id=str(selected.source_app_user_model_id or ""),
        title=str(properties.title or "").strip(),
        artist=str(properties.artist or "").strip(),
        album=str(properties.album_title or "").strip(),
        duration=max(0, timeline.end_time.total_seconds()),
        position=max(0, timeline.position.total_seconds()),
        playing=status == PlaybackStatus.PLAYING,
    )


def player_identity(source_id: str) -> tuple[str, str]:
    source = source_id.casefold()
    if "zunemusic" in source:
        return "Windows 媒体播放器", "media-player"
    if "wmplayer" in source or "mediaplayer32" in source:
        return "Windows Media Player", "windows-media-player"
    if "cloudmusic" in source:
        return "网易云音乐", "cloudmusic"
    if "spotify" in source:
        return "Spotify", "spotify"
    if "foobar" in source:
        return "foobar2000", "foobar2000"
    return "Windows 媒体会话", "media-player"


class Reporter:
    def __init__(self, server: str, secret: str, library: MusicLibrary):
        self.server = server.rstrip("/")
        self.library = library
        self.session = requests.Session()
        self.session.trust_env = False
        self.session.headers.update(
            {
                "Accept": "application/json",
                "Authorization": f"Bearer {secret}",
                "User-Agent": "Alive-Windows-Media-Session/2.0",
            }
        )
        self.uploaded_tracks: dict[str, str] = {}
        self.track_digests: dict[Path, tuple[int, int, str]] = {}
        self.uploaded_covers: dict[str, str] = {}
        self.last_signature = ""
        self.last_sent_at = 0.0
        self.was_active = False
        self.netease_position_id = ""
        self.netease_position = 0.0
        self.netease_position_clock = monotonic()
        self.netease_was_playing = False

    def continuous_netease_position(self, playing: NowPlaying, song_id: str) -> NowPlaying:
        now = monotonic()
        if song_id != self.netease_position_id:
            self.netease_position_id = song_id
            self.netease_position = playing.position
            self.netease_position_clock = now
        predicted = self.netease_position
        if self.netease_was_playing:
            predicted += max(0, now - self.netease_position_clock)
        if playing.position > 0.5:
            predicted = playing.position
            self.netease_position = playing.position
            self.netease_position_clock = now
        elif not playing.playing:
            self.netease_position = predicted
            self.netease_position_clock = now
        self.netease_was_playing = playing.playing
        if playing.duration > 0 and playing.playing:
            predicted %= playing.duration
        return NowPlaying(
            source_id=playing.source_id,
            title=playing.title,
            artist=playing.artist,
            album=playing.album,
            duration=playing.duration,
            position=max(0, predicted),
            playing=playing.playing,
        )

    def track_digest(self, path: Path) -> str:
        stat = path.stat()
        signature = (stat.st_mtime_ns, stat.st_size)
        cached = self.track_digests.get(path)
        if cached and cached[:2] == signature:
            return cached[2]
        hasher = hashlib.sha256()
        with path.open("rb") as file:
            for chunk in iter(lambda: file.read(1024 * 1024), b""):
                hasher.update(chunk)
        digest = hasher.hexdigest()
        self.track_digests[path] = (*signature, digest)
        return digest

    def ensure_track_uploaded(self, track: LocalTrack | None) -> str:
        if track is None:
            return ""
        digest = self.track_digest(track.path)
        if digest in self.uploaded_tracks:
            return self.uploaded_tracks[digest]
        suffix = track.path.suffix.casefold()
        size = track.path.stat().st_size
        checked = self.session.post(
            f"{self.server}/api/music/track/check",
            json={"sha256": digest, "suffix": suffix, "size": size},
            timeout=20,
        )
        checked.raise_for_status()
        result = checked.json()
        library_path = str(result.get("library_path", ""))
        if not result.get("exists"):
            log(f"正在上传当前本地音频：{track.path.name}（{size / 1024 / 1024:.1f} MiB）")
            with track.path.open("rb") as file:
                uploaded = self.session.post(
                    f"{self.server}/api/music/track/upload",
                    data=file,
                    headers={
                        "Content-Type": UPLOAD_CONTENT_TYPES[suffix],
                        "Content-Length": str(size),
                        "X-Alive-Audio-Sha256": digest,
                        "X-Alive-Audio-Suffix": suffix,
                    },
                    timeout=(20, 600),
                )
            uploaded.raise_for_status()
            library_path = str(uploaded.json().get("library_path", ""))
        if not library_path:
            raise requests.RequestException("Alive 未返回已保存音频路径")
        self.uploaded_tracks[digest] = library_path
        return library_path

    def ensure_cover_uploaded(self, track: LocalTrack | None) -> str:
        if track is None:
            return ""
        cover = self.library.cover(track)
        if cover is None:
            return ""
        content, media_type = cover
        digest = hashlib.sha256(content).hexdigest()
        if digest in self.uploaded_covers:
            return self.uploaded_covers[digest]
        response = self.session.post(
            f"{self.server}/api/music/cover",
            data=content,
            headers={"Content-Type": media_type},
            timeout=30,
        )
        response.raise_for_status()
        url = str(response.json().get("url", ""))
        if url:
            self.uploaded_covers[digest] = url
        return url

    def send_local(self, playing: NowPlaying, track: LocalTrack | None) -> None:
        player_name, player_icon = player_identity(playing.source_id)
        library_path = self.ensure_track_uploaded(track)
        cover_url = self.ensure_cover_uploaded(track)
        payload = {
            "source_mode": "local-upload" if library_path else "metadata-only",
            "source_id": "",
            "device_id": "windows-media-session",
            "title": (track.title if track else "") or playing.title,
            "artist": (track.artist if track else "") or playing.artist,
            "album": (track.album if track else "") or playing.album,
            "cover_url": cover_url,
            "audio_url": "",
            "source_url": "",
            "player_name": player_name,
            "player_icon": player_icon,
            "library_path": library_path,
            "duration": (track.duration if track else 0) or playing.duration,
            "position": playing.position,
            "playing": playing.playing,
            "lyrics": [],
        }
        response = self.session.post(
            f"{self.server}/api/music/set", json=payload, timeout=30
        )
        response.raise_for_status()
        self.was_active = True
        match_text = (
            f"；已使用本地标签并上传 {track.path.name}"
            if track
            else "；未按文件名或标签匹配到音频"
        )
        log(f"已上报：{playing.title} — {playing.artist}（{player_name}）{match_text}")

    def send_netease(self, playing: NowPlaying, track: NeteaseTrack) -> None:
        payload = {
            "source_mode": "netease-api",
            "source_id": track.song_id,
            "device_id": "windows-netease-cloudmusic",
            "title": playing.title or track.title,
            "artist": playing.artist or track.artist,
            "album": playing.album or track.album,
            "cover_url": track.cover_url,
            "audio_url": "",
            "source_url": "",
            "player_name": "网易云音乐",
            "player_icon": "cloudmusic",
            "library_path": "",
            "duration": playing.duration or track.duration,
            "position": playing.position,
            "playing": playing.playing,
            "lyrics": [],
        }
        response = self.session.post(
            f"{self.server}/api/music/set", json=payload, timeout=30
        )
        response.raise_for_status()
        self.was_active = True
        log(
            f"已上报网易云 ID {track.song_id}：{playing.title} — "
            f"{playing.artist}；访客将直接连接公开流媒体"
        )

    def clear(self) -> None:
        response = self.session.post(f"{self.server}/api/music/clear", json={}, timeout=10)
        response.raise_for_status()
        self.was_active = False
        self.last_signature = ""
        log("已清除 Alive 当前音乐。")


async def run(args: argparse.Namespace) -> None:
    secret = project_env("ALIVE_SECRET")
    if len(secret) < 6:
        raise SystemExit("全局 ALIVE_SECRET 不存在或长度不足 6 位，请检查项目根目录 .env。")
    explicit = Path(args.file) if args.file else None
    library = MusicLibrary(Path(args.library), explicit)
    library.scan()
    netease = NeteaseDetector(Path(args.netease_dir))
    if netease.available:
        log(f"已找到网易云本地状态目录：{netease.root}")
    else:
        log("未找到网易云本地状态目录；本地音乐上传功能不受影响。")
    reporter = Reporter(args.server, secret, library)
    if args.clear:
        reporter.clear()
        return

    try:
        manager = await MediaSessionManager.request_async()
    except Exception as error:
        raise SystemExit(f"无法读取 Windows 媒体会话：{error}") from error

    log("正在监听 Windows 媒体会话；按 Ctrl+C 只停止上报器，不会停止播放器。")
    while True:
        try:
            playing = await read_now_playing(manager)
            if playing is None and netease.available:
                playing = netease.now_playing()
            if playing is None:
                if reporter.was_active:
                    reporter.clear()
                if args.once:
                    log("没有检测到媒体会话，请播放一首歌后重试。")
                    return
            else:
                is_netease = "cloudmusic" in playing.source_id.casefold()
                netease_track = netease.lookup(playing) if is_netease else None
                if is_netease and netease_track and playing.position <= 0.5:
                    elog_playing = netease.now_playing()
                    if (
                        elog_playing
                        and normalized(elog_playing.title) == normalized(playing.title)
                        and elog_playing.position > playing.position
                    ):
                        playing = NowPlaying(
                            source_id=playing.source_id,
                            title=playing.title,
                            artist=playing.artist,
                            album=playing.album,
                            duration=playing.duration or elog_playing.duration,
                            position=elog_playing.position,
                            playing=playing.playing,
                        )
                if is_netease and netease_track:
                    playing = reporter.continuous_netease_position(
                        playing, netease_track.song_id
                    )
                local_track = None if is_netease else library.match(
                    playing.title, playing.artist
                )
                source_key = (
                    f"netease:{netease_track.song_id}"
                    if netease_track
                    else f"local:{local_track.path if local_track else ''}"
                )
                signature = "|".join(
                    (
                        playing.source_id,
                        source_key,
                        playing.title,
                        playing.artist,
                        str(playing.playing),
                    )
                )
                now = asyncio.get_running_loop().time()
                should_send = (
                    args.once
                    or signature != reporter.last_signature
                    or now - reporter.last_sent_at >= 10
                )
                if should_send:
                    if netease_track:
                        reporter.send_netease(playing, netease_track)
                    else:
                        reporter.send_local(playing, local_track)
                        if is_netease:
                            log("尚未取得网易云歌曲 ID，本次仅显示媒体会话信息。")
                    reporter.last_signature = signature
                    reporter.last_sent_at = now
                if args.once:
                    return
        except requests.RequestException as error:
            log(f"上报失败，将自动重试：{error}")
            if args.once:
                raise
        await asyncio.sleep(1)


def main() -> None:
    default_netease = (
        Path(os.getenv("LOCALAPPDATA", "")) / "NetEase" / "CloudMusic"
    )
    parser = argparse.ArgumentParser(description="Alive Windows 当前音乐上报器")
    parser.add_argument(
        "--server",
        default=project_env("ALIVE_SERVER") or "http://127.0.0.1:9010",
        help="Alive 地址（默认：http://127.0.0.1:9010）",
    )
    parser.add_argument(
        "--library",
        default=project_env("ALIVE_MUSIC_DIR") or str(Path.home() / "Music"),
        help="本机音乐目录（默认：当前用户的 Music 文件夹）",
    )
    parser.add_argument(
        "--file",
        default="",
        help="直接指定当前本地音频；跳过文件名自动匹配，适合单曲测试",
    )
    parser.add_argument(
        "--netease-dir",
        default=project_env("ALIVE_NETEASE_DIR") or str(default_netease),
        help="网易云 Windows 客户端数据目录",
    )
    parser.add_argument("--once", action="store_true", help="只读取并上报一次，用于测试")
    parser.add_argument("--clear", action="store_true", help="清除 Alive 当前音乐后退出")
    args = parser.parse_args()
    args.server = server_url(args.server)
    try:
        asyncio.run(run(args))
    except KeyboardInterrupt:
        log("监听已停止；播放器和 Alive 服务不会被关闭。")


if __name__ == "__main__":
    main()
