#!/usr/bin/python3
# coding: utf-8
"""Alive FastAPI server."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import io
import json
import logging
import os
import secrets
from contextlib import asynccontextmanager
from datetime import datetime
from mimetypes import guess_type
from pathlib import Path
from time import time
from traceback import format_exc
from urllib.parse import urlparse

import pytz
import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    RedirectResponse,
    Response,
    StreamingResponse,
)
from jinja2 import Environment, select_autoescape
from PIL import Image, UnidentifiedImageError
from toml import load as load_toml

from config import Config as config_init
from fastapi_data import Data
from models import (
    CommentCreateModel,
    HealthStateUpdateModel,
    MusicStateUpdateModel,
    MusicTrackCheckModel,
)
from music_sources import NeteaseResolver
import utils as u


print(
    """
Welcome to Alive (FastAPI)!
""".strip(),
    flush=True,
)


def _load_version() -> tuple[tuple[int, int, int], str]:
    with open(u.get_path("pyproject.toml"), "r", encoding="utf-8") as file:
        metadata = load_toml(file).get("project", {})
    raw = str(metadata.get("version", "0.0.0"))
    numbers = tuple(int(part) for part in raw.split(".")[:3])
    return (
        numbers,
        raw,
    )


MIN_SECRET_LENGTH = 6
version, version_str = _load_version()
c = config_init().config
SECRET_OVERRIDE_FILE = Path(u.get_path("data/admin-secret"))
if SECRET_OVERRIDE_FILE.is_file():
    stored_secret = SECRET_OVERRIDE_FILE.read_text(encoding="utf-8").strip()
    if stored_secret:
        c.main.secret = stored_secret


def _validate_main_secret(secret: str) -> None:
    if len(secret) < MIN_SECRET_LENGTH:
        raise RuntimeError(
            f"alive_main_secret must be set to a value of at least {MIN_SECRET_LENGTH} characters"
        )


_validate_main_secret(c.main.secret)

l = logging.getLogger(__name__)
root_logger = logging.getLogger()
root_logger.handlers.clear()
root_logger.setLevel(logging.DEBUG if c.main.debug else logging.INFO)
stream_handler = logging.StreamHandler()
stream_handler.setFormatter(
    u.CustomFormatter(colorful=c.main.colorful_log, timezone=c.main.timezone)
)
root_logger.addHandler(stream_handler)
if c.main.log_file:
    file_handler = logging.FileHandler(
        u.get_path(c.main.log_file), encoding="utf-8", errors="ignore"
    )
    file_handler.setFormatter(u.CustomFormatter(colorful=False, timezone=c.main.timezone))
    root_logger.addHandler(file_handler)

l.info("=============== Application Startup ===============")
l.info("Alive version %s, powered by FastAPI", version_str)

d = Data(config=c)
netease_resolver = NeteaseResolver()
tz = pytz.timezone(c.main.timezone)
FAVICON_PATH = Path(u.get_path("data/public/favicon.ico"))
PROFILE_AVATAR_PATH = Path(u.get_path("data/public/profile-avatar.webp"))
MAX_FAVICON_BYTES = 5 * 1024 * 1024

SOCIAL_PLATFORMS = {
    "website": {"label": "个人网站", "icon": "◎"},
    "github": {"label": "GitHub", "icon": "https://cdn.simpleicons.org/github"},
    "gitlab": {"label": "GitLab", "icon": "https://cdn.simpleicons.org/gitlab"},
    "bilibili": {"label": "哔哩哔哩", "icon": "https://cdn.simpleicons.org/bilibili"},
    "weibo": {"label": "微博", "icon": "https://cdn.simpleicons.org/sinaweibo"},
    "xiaohongshu": {"label": "小红书", "icon": "https://cdn.simpleicons.org/xiaohongshu"},
    "douyin": {"label": "抖音", "icon": "https://cdn.simpleicons.org/douyin"},
    "zhihu": {"label": "知乎", "icon": "https://cdn.simpleicons.org/zhihu"},
    "qq": {"label": "QQ", "icon": "https://cdn.simpleicons.org/qq"},
    "wechat": {"label": "微信", "icon": "https://cdn.simpleicons.org/wechat"},
    "telegram": {"label": "Telegram", "icon": "https://cdn.simpleicons.org/telegram"},
    "discord": {"label": "Discord", "icon": "https://cdn.simpleicons.org/discord"},
    "x": {"label": "X", "icon": "https://cdn.simpleicons.org/x"},
    "bluesky": {"label": "Bluesky", "icon": "https://cdn.simpleicons.org/bluesky"},
    "mastodon": {"label": "Mastodon", "icon": "https://cdn.simpleicons.org/mastodon"},
    "instagram": {"label": "Instagram", "icon": "https://cdn.simpleicons.org/instagram"},
    "youtube": {"label": "YouTube", "icon": "https://cdn.simpleicons.org/youtube"},
    "linkedin": {"label": "LinkedIn", "icon": "https://cdn.simpleicons.org/linkedin"},
    "steam": {"label": "Steam", "icon": "https://cdn.simpleicons.org/steam"},
    "email": {"label": "邮箱", "icon": "✉"},
}


def _social_links() -> list[dict[str, str]]:
    """Return saved public links after re-validating their persisted JSON."""
    try:
        configured = json.loads(d.runtime_setting("social_links", "[]"))
    except (TypeError, json.JSONDecodeError):
        return []
    if not isinstance(configured, list):
        return []

    links: list[dict[str, str]] = []
    used: set[str] = set()
    for item in configured[:len(SOCIAL_PLATFORMS)]:
        if not isinstance(item, dict):
            continue
        platform = item.get("platform")
        url = item.get("url")
        if platform not in SOCIAL_PLATFORMS or platform in used or not isinstance(url, str):
            continue
        url = url.strip()
        if platform == "email":
            if "@" not in url or any(character.isspace() for character in url):
                continue
            url = url if url.startswith("mailto:") else f"mailto:{url}"
        else:
            parsed = urlparse(url)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                continue
        used.add(platform)
        links.append({"platform": platform, "url": url, **SOCIAL_PLATFORMS[platform]})
    return links


def _normalize_social_links(value: object) -> list[dict[str, str]]:
    if not isinstance(value, list):
        raise u.APIUnsuccessful(400, "social_links must be a list")
    normalized: list[dict[str, str]] = []
    used: set[str] = set()
    for item in value:
        if not isinstance(item, dict):
            raise u.APIUnsuccessful(400, "each social link must be an object")
        platform = item.get("platform")
        url = str(item.get("url", "")).strip()
        if platform not in SOCIAL_PLATFORMS:
            raise u.APIUnsuccessful(400, "unsupported social platform")
        if platform in used:
            raise u.APIUnsuccessful(400, "each social platform can only be shown once")
        if not url or len(url) > 2048:
            raise u.APIUnsuccessful(400, "social link must be 1 to 2048 characters")
        if platform == "email":
            if url.startswith("mailto:"):
                url = url.removeprefix("mailto:")
            if "@" not in url or any(character.isspace() for character in url):
                raise u.APIUnsuccessful(400, "email must be a valid email address")
            url = f"mailto:{url}"
        else:
            parsed = urlparse(url)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                raise u.APIUnsuccessful(400, "social links must use an http or https URL")
        used.add(platform)
        normalized.append({"platform": platform, "url": url})
    return normalized


_active_viewers = 0
_presence_revision = 0


@asynccontextmanager
async def lifespan(_: FastAPI):
    d.ensure_schema()
    if c.metrics.enabled:
        d._metrics_refresh()
    yield
    d.close()


def generate_operation_id(route) -> str:
    path = route.path_format.strip("/").replace("/", "_").replace("{", "").replace("}", "") or "root"
    methods = "_".join(sorted(route.methods or {"ANY"})).lower()
    return f"{route.name}_{methods}_{path}"


app = FastAPI(
    title="Alive",
    description=(
        "Alive 个人在线状态服务。公开读取使用 GET；数据修改使用 POST。"
        "设备、音乐与后台修改需要 Bearer 密钥或后台登录会话；"
        "公开评论使用限流和内容长度限制。"
    ),
    version=".".join(map(str, version)),
    docs_url="/swagger",
    redoc_url=None,
    lifespan=lifespan,
    generate_unique_id_function=generate_operation_id,
)

cors_origins = [c.main.cors_origins] if isinstance(c.main.cors_origins, str) else c.main.cors_origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials="*" not in cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

templates = Environment(autoescape=select_autoescape(("html", "xml")))


def template_url_for(endpoint: str, **values: str) -> str:
    if endpoint == "static":
        filename = values.get("filename", "")
        file = _safe_file(
            Path(u.get_path("theme/default/static", is_dir=True)),
            filename,
        )
        asset_version = file.stat().st_mtime_ns if file else version_str
        return f"/static/{filename}?v={asset_version}"
    return f"/{endpoint.lstrip('/')}"


templates.globals["url_for"] = template_url_for

def _theme(request: Request) -> str:
    return "default"


def render_template(
    request: Request,
    filename: str,
    dirname: str = "templates",
    theme: str | None = None,
    **context,
) -> str | None:
    selected = theme or _theme(request)
    content = d.get_cached_text("theme", f"{selected}/{dirname}/{filename}")
    if content is None and selected != "default":
        content = d.get_cached_text("theme", f"default/{dirname}/{filename}")
    if content is None:
        return None
    return templates.from_string(content).render(**context)


def _client_ip(request: Request) -> str:
    direct = request.client.host if request.client else ""
    forwarded = request.headers.get("X-Real-IP") or request.headers.get("X-Forwarded-For")
    return direct + (f" / {forwarded}" if forwarded else "")


@app.middleware("http")
async def request_context(request: Request, call_next):
    started = time()
    request.state.ipstr = _client_ip(request)
    request.state.theme = "default"

    try:
        response = await call_next(request)
    except Exception as exc:
        l.error("Unhandled error: %s\n%s", exc, format_exc())
        response = JSONResponse(
            {"success": False, "code": 500, "details": "Internal Server Error", "message": str(exc)},
            status_code=500,
        )

    if c.metrics.enabled:
        d.record_metrics(request.url.path)
    response.headers["X-Powered-By"] = "Alive / FastAPI"
    response.headers["Alive-Version"] = version_str
    l.info(
        "[Request] %s | %s -> %s (%sms)",
        request.state.ipstr,
        request.url.path,
        response.status_code,
        round((time() - started) * 1000, 2),
    )
    return response


@app.exception_handler(u.APIUnsuccessful)
async def api_unsuccessful_handler(_: Request, exc: u.APIUnsuccessful):
    return JSONResponse(
        {
            "success": False,
            "code": exc.code,
            "details": exc.details,
            "message": exc.message,
        },
        status_code=exc.code,
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(_: Request, exc: RequestValidationError):
    return JSONResponse(
        {
            "success": False,
            "code": 422,
            "details": "Unprocessable Entity",
            "message": str(exc),
        },
        status_code=422,
    )


SESSION_COOKIE = "alive-session"
SESSION_MAX_AGE = 30 * 24 * 60 * 60


def _session_token() -> str:
    issued = str(int(time()))
    signature = hmac.new(
        c.main.secret.encode("utf-8"),
        f"alive-session:{issued}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"{issued}.{signature}"


def _valid_session(token: str | None) -> bool:
    if not token:
        return False
    try:
        issued_raw, supplied_signature = token.split(".", 1)
        issued = int(issued_raw)
    except (ValueError, TypeError):
        return False
    age = int(time()) - issued
    if age < 0 or age > SESSION_MAX_AGE:
        return False
    expected = hmac.new(
        c.main.secret.encode("utf-8"),
        f"alive-session:{issued_raw}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(supplied_signature, expected)


async def require_secret(request: Request) -> None:
    authorization = request.headers.get("Authorization", "")
    header_secret = request.headers.get("Alive-Secret") or (
        authorization[7:] if authorization.startswith("Bearer ") else None
    )
    if header_secret and hmac.compare_digest(str(header_secret), c.main.secret):
        return
    if _valid_session(request.cookies.get(SESSION_COOKIE)):
        return

    body: dict = {}
    if request.method in {"POST", "PUT", "PATCH"}:
        try:
            parsed = await request.json()
            if isinstance(parsed, dict):
                body = parsed
        except (json.JSONDecodeError, UnicodeDecodeError, RuntimeError):
            pass
    supplied = body.get("secret")
    if not supplied or not hmac.compare_digest(str(supplied), c.main.secret):
        raise u.APIUnsuccessful(401, "Wrong Secret")


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def index(request: Request):
    main_card = render_template(
        request,
        "main.index.html",
        dirname="cards",
        username=d.page_name,
        status=d.status_dict[1],
        profile_avatar=profile_avatar_url(),
        social_links=_social_links(),
        last_updated=datetime.fromtimestamp(d.last_updated, tz).strftime("%Y-%m-%d %H:%M:%S %Z"),
        visit_metric=d.public_visit_metric,
        online_viewers=_active_viewers,
    )
    music_island = render_template(request, "music_island.html")
    comment_wall = render_template(
        request,
        "comment_wall.html",
        danmaku_enabled=d.danmaku_enabled,
    )
    site_chrome = render_template(request, "site_chrome.html", current_page="home")
    site_footer = render_template(request, "site_footer.html", alive_version=version_str)
    content = render_template(
        request,
        "index.html",
        page_title=d.page_title,
        page_desc=c.page.desc,
        page_favicon=favicon_url(),
        page_background=c.page.background,
        cards={"main": main_card or ""},
        music_island=music_island or "",
        comment_wall=comment_wall or "",
        site_chrome=site_chrome or "",
        site_footer=site_footer or "",
        inject="",
    )
    if content is None:
        raise HTTPException(status_code=404)
    return HTMLResponse(content)


@app.get("/details", response_class=HTMLResponse, include_in_schema=False)
def details_page(request: Request):
    site_chrome = render_template(request, "site_chrome.html", current_page="details")
    site_footer = render_template(request, "site_footer.html", alive_version=version_str)
    music_island = render_template(request, "music_island.html")
    content = render_template(
        request,
        "details.html",
        page_title=f"{d.page_title} · 详情",
        page_desc=f"{d.page_title} 的设备、访问和互动详情",
        page_favicon=favicon_url(),
        page_background=c.page.background,
        site_chrome=site_chrome or "",
        site_footer=site_footer or "",
        music_island=music_island or "",
    )
    if content is None:
        raise HTTPException(status_code=404)
    return HTMLResponse(content)


@app.get("/static/{filename:path}", include_in_schema=False)
def static_proxy(request: Request, filename: str):
    root = Path(u.get_path("theme", is_dir=True))
    file = _safe_file(root / _theme(request) / "static", filename)
    if file is None and _theme(request) != "default":
        file = _safe_file(root / "default" / "static", filename)
    if file is None:
        raise HTTPException(status_code=404, detail=f"Static file {filename} not found")
    cache_control = (
        "public, max-age=31536000, immutable"
        if request.query_params.get("v")
        else "no-cache"
    )
    return FileResponse(
        file,
        media_type=guess_type(filename)[0],
        headers={"Cache-Control": cache_control},
    )


@app.get("/static-themed/{theme}/{filename:path}", include_in_schema=False)
def static_themed(request: Request, theme: str, filename: str):
    file = _safe_file(Path(u.get_path("theme", is_dir=True)) / theme / "static", filename)
    if file is None and theme != "default":
        file = _safe_file(
            Path(u.get_path("theme", is_dir=True)) / "default" / "static",
            filename,
        )
    if file is None:
        raise HTTPException(status_code=404, detail=f"Static file {filename} not found")
    return FileResponse(
        file,
        media_type=guess_type(filename)[0],
        headers={
            "Cache-Control": (
                "public, max-age=31536000, immutable"
                if request.query_params.get("v")
                else "no-cache"
            )
        },
    )


@app.get("/default/{filename:path}", include_in_schema=False)
def static_default_theme(filename: str):
    if not filename.endswith(".js"):
        filename += ".js"
    file = _safe_file(Path(u.get_path("theme/default", is_dir=True)), filename)
    if file:
        return FileResponse(file, media_type=guess_type(filename)[0])
    raise HTTPException(status_code=404)


def _safe_file(root: Path, relative: str) -> Path | None:
    root = root.resolve()
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return None
    return candidate if candidate.is_file() else None


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    if FAVICON_PATH.is_file():
        return FileResponse(FAVICON_PATH, media_type="image/x-icon")
    if c.page.favicon != "/favicon.ico":
        return RedirectResponse(c.page.favicon, status_code=302)
    return _serve_public("favicon.ico")


def favicon_url() -> str:
    if FAVICON_PATH.is_file():
        try:
            return f"/favicon.ico?v={FAVICON_PATH.stat().st_mtime_ns}"
        except OSError:
            pass
    return c.page.favicon


def profile_avatar_url() -> str:
    if PROFILE_AVATAR_PATH.is_file():
        try:
            return f"/profile-avatar.webp?v={PROFILE_AVATAR_PATH.stat().st_mtime_ns}"
        except OSError:
            pass
    return ""


@app.get("/docs", response_class=HTMLResponse, include_in_schema=False)
def documentation():
    return FileResponse(
        Path(u.get_path("public/docs.html")),
        media_type="text/html; charset=utf-8",
    )


@app.get("/github", include_in_schema=False)
def github():
    return RedirectResponse("/docs", status_code=302)


@app.get("/none", include_in_schema=False)
def none():
    return Response(status_code=204)


def metadata_response() -> dict:
    return {
        "success": True,
        "version": version,
        "version_str": version_str,
        "timezone": c.main.timezone,
        "page": {
            "name": d.page_name,
            "title": d.page_title,
            "desc": c.page.desc,
            "favicon": favicon_url(),
            "profile_avatar": profile_avatar_url(),
            "social_links": _social_links(),
            "background": c.page.background,
            "theme": "default",
        },
        "status": {
            "device_slice": c.status.device_slice,
            "refresh_interval": c.status.refresh_interval,
            "device_timeout": c.status.device_timeout,
            "not_using": c.status.not_using,
            "sorted": c.status.sorted,
            "using_first": c.status.using_first,
        },
        "metrics": c.metrics.enabled,
        "public_settings": {
            "visit_display_mode": d.visit_display_mode,
        },
        "framework": "FastAPI",
    }


@app.get("/api/meta", tags=["公开读取 / Public reads"], summary="获取站点元数据")
def metadata():
    return metadata_response()


@app.get("/api/metrics", tags=["公开读取 / Public reads"], summary="获取访问统计")
def metrics():
    return d.metrics_resp


def query_response(include_meta: bool = False, include_metrics: bool = False) -> dict:
    status_id = d.status_id
    _, status = d.get_status(status_id)
    result = {
        "success": True,
        "time": datetime.now().timestamp(),
        "status": status.model_dump(),
        "device": d.device_list,
        "health": d.health_state,
        "music": d.music_state,
        "visit_metric": d.public_visit_metric,
        "online_viewers": _active_viewers,
        "private_mode": d.private_mode,
        "last_updated": d.last_updated,
    }
    if include_meta:
        result["meta"] = metadata_response()
    if include_metrics:
        result["metrics"] = d.metrics_resp
    return result


def details_response() -> dict:
    generated_at = time()
    timeout = c.status.device_timeout
    devices = []
    state_counts = {"active": 0, "idle": 0, "offline": 0}
    for device in d.device_list.values():
        fresh = timeout <= 0 or generated_at - float(device.get("last_updated") or 0) <= timeout
        state = "active" if fresh and device.get("using") else "idle" if fresh else "offline"
        state_counts[state] += 1
        devices.append({**device, "public_state": state})

    metrics = d.metrics_resp
    visit_periods = {
        period: int((metrics.get(period) or {}).get("/", 0))
        for period in ("daily", "weekly", "monthly", "yearly", "total")
    }
    now_local = datetime.now(tz)
    today_start = now_local.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
    comment_counts = {
        "today": d.comment_count(since=today_start),
        "total": d.comment_count(),
    }
    health = d.health_state
    music = d.music_state
    _, status = d.status

    online_count = state_counts["active"] + state_counts["idle"]
    summary_parts = [
        f"当前状态为“{status.name}”",
        f"{len(devices)} 台公开设备中有 {online_count} 台在线",
    ]
    if state_counts["active"]:
        summary_parts.append(f"其中 {state_counts['active']} 台正在使用")
    if health.get("active"):
        health_bits = []
        if health.get("heart_rate") is not None:
            health_bits.append(f"心率 {health['heart_rate']} BPM")
        if health.get("steps") is not None:
            health_bits.append(f"今日 {health['steps']} 步")
        if health_bits:
            summary_parts.append("身体状态：" + "、".join(health_bits))
    if music.get("active"):
        summary_parts.append(
            f"正在听《{music.get('title') or '未知歌曲'}》"
            f" — {music.get('artist') or '未知艺术家'}"
        )
    else:
        summary_parts.append("当前没有公开的音乐会话")
    summary_parts.append(
        f"今天主页被查看 {visit_periods['daily']} 次，收到 {comment_counts['today']} 条留言"
    )

    return {
        "success": True,
        "generated_at": generated_at,
        "timezone": c.main.timezone,
        "status": status.model_dump(),
        "summary": "；".join(summary_parts) + "。",
        "devices": devices,
        "device_counts": {
            "total": len(devices),
            "online": online_count,
            **state_counts,
        },
        "visits": {
            "enabled": bool(metrics.get("enabled")),
            **visit_periods,
        },
        "comments": comment_counts,
        "health": health,
        "music": music,
        "history_available": False,
    }


@app.get("/api/status/query", tags=["公开读取 / Public reads"], summary="查询当前状态")
def query(meta: str | None = None, metrics: str | None = None):
    return query_response(
        include_meta=u.tobool(meta) is True,
        include_metrics=u.tobool(metrics) is True,
    )


@app.get(
    "/api/details/query",
    tags=["公开读取 / Public reads"],
    summary="获取详情页统计、设备排序数据和情况总结",
)
def details_query():
    return details_response()


async def _event_stream(request: Request, event_id: int):
    global _active_viewers, _presence_revision
    _active_viewers += 1
    _presence_revision += 1
    last_updated = None
    last_presence_revision = None
    last_heartbeat = time()
    try:
        while not await request.is_disconnected():
            current = time()
            updated = d.last_updated
            if last_updated != updated or last_presence_revision != _presence_revision:
                last_updated = updated
                last_presence_revision = _presence_revision
                last_heartbeat = current
                event_id += 1
                payload = query_response()
                yield f"id: {event_id}\nevent: update\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
            elif current - last_heartbeat >= 30:
                event_id += 1
                yield f"id: {event_id}\nevent: heartbeat\ndata:\n\n"
                last_heartbeat = current
            await asyncio.sleep(1)
    finally:
        _active_viewers = max(0, _active_viewers - 1)
        _presence_revision += 1


@app.get("/api/status/events", tags=["公开读取 / Public reads"], summary="订阅状态更新事件")
async def events(request: Request):
    try:
        event_id = int(request.headers.get("Last-Event-ID", "0"))
    except ValueError as exc:
        raise u.APIUnsuccessful(400, "Invalid Last-Event-ID header, it must be int!") from exc
    return StreamingResponse(
        _event_stream(request, event_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post(
    "/api/status/set",
    dependencies=[Depends(require_secret)],
    tags=["数据修改 / Mutations"],
    summary="设置手动状态",
)
async def set_status(request: Request):
    body = await _json_object(request)
    try:
        new_id = int(body.get("status"))
    except (TypeError, ValueError) as exc:
        raise u.APIUnsuccessful(400, "argument 'status' must be int") from exc
    if not 0 <= new_id < len(c.status.status_list):
        raise u.APIUnsuccessful(400, "status is outside the configured status list")
    d.status_id = new_id
    return {"success": True, "set_to": new_id}


@app.get("/api/status/list", tags=["公开读取 / Public reads"], summary="获取手动状态列表")
def get_status_list():
    return {
        "success": True,
        "status_list": [item.model_dump() for item in d.status_list],
    }


@app.get("/api/health/query", tags=["公开读取 / Public reads"], summary="获取当前身体状态")
def health_query():
    return {"success": True, "health": d.health_state}


@app.post(
    "/api/health/set",
    dependencies=[Depends(require_secret)],
    tags=["数据修改 / Mutations"],
    summary="更新心率和今日步数",
)
def health_set(payload: HealthStateUpdateModel):
    values = payload.model_dump(exclude_unset=True)
    if not any(
        values.get(key) is not None
        for key in ("heart_rate", "resting_heart_rate", "heart_rate_min", "heart_rate_max", "steps")
    ):
        raise u.APIUnsuccessful(400, "at least one health value is required")
    return {"success": True, "health": d.health_set(values)}


@app.post(
    "/api/health/clear",
    dependencies=[Depends(require_secret)],
    tags=["数据修改 / Mutations"],
    summary="清空身体状态",
)
def health_clear():
    d.health_clear()
    return {"success": True}


@app.get("/api/music/query", tags=["公开读取 / Public reads"], summary="获取当前音乐状态")
def music_query():
    return {"success": True, "music": d.music_state}


@app.get(
    "/api/comments/query",
    tags=["评论与弹幕 / Comments"],
    summary="读取最近的公开评论",
)
def comments_query(limit: int = 8):
    return {
        "success": True,
        "danmaku_enabled": d.danmaku_enabled,
        "comments": d.comment_list(min(max(limit, 1), 8)),
    }


def _comment_visitor_hash(request: Request) -> str:
    return hmac.new(
        c.main.secret.encode("utf-8"),
        f"alive-comment:{request.state.ipstr}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _single_line_text(value: str, fallback: str = "") -> str:
    cleaned = "".join(character for character in value if ord(character) >= 32)
    return " ".join(cleaned.split()) or fallback


@app.post(
    "/api/comments/create",
    tags=["评论与弹幕 / Comments"],
    summary="发表匿名或自定义昵称评论",
)
def comments_create(request: Request, payload: CommentCreateModel):
    if payload.website:
        raise u.APIUnsuccessful(400, "Invalid submission")
    nickname = _single_line_text(payload.nickname, "匿名访客")[:24]
    content = _single_line_text(payload.content)[:160]
    if not content:
        raise u.APIUnsuccessful(400, "评论内容不能为空")
    return {
        "success": True,
        "comment": d.comment_create(
            nickname=nickname,
            content=content,
            color=payload.color,
            visitor_hash=_comment_visitor_hash(request),
        ),
    }


MUSIC_AUDIO_TYPES = {
    ".flac": "audio/flac",
    ".mp3": "audio/mpeg",
    ".m4a": "audio/mp4",
    ".ogg": "audio/ogg",
    ".opus": "audio/ogg",
    ".wav": "audio/wav",
}


def _music_track_location(digest: str, suffix: str) -> tuple[str, Path]:
    safe_digest = digest.casefold()
    safe_suffix = suffix.casefold()
    relative = f"{safe_digest[:2]}/{safe_digest}{safe_suffix}"
    root = Path(u.get_path(d.music_library, is_dir=True)).resolve()
    destination = (root / relative).resolve()
    try:
        destination.relative_to(root)
    except ValueError as exc:
        raise u.APIUnsuccessful(400, "invalid audio identity") from exc
    return relative, destination


def _valid_audio_container(path: Path, suffix: str) -> bool:
    with path.open("rb") as file:
        head = file.read(16)
    if suffix == ".flac":
        return head.startswith(b"fLaC")
    if suffix == ".mp3":
        return head.startswith(b"ID3") or (
            len(head) >= 2 and head[0] == 0xFF and head[1] & 0xE0 == 0xE0
        )
    if suffix == ".m4a":
        return len(head) >= 8 and head[4:8] == b"ftyp"
    if suffix == ".wav":
        return len(head) >= 12 and head[:4] == b"RIFF" and head[8:12] == b"WAVE"
    if suffix in {".ogg", ".opus"}:
        return head.startswith(b"OggS")
    return False


@app.post(
    "/api/music/track/check",
    dependencies=[Depends(require_secret)],
    tags=["数据修改 / Mutations"],
    summary="检查音频是否已经按内容保存",
)
def music_track_check(payload: MusicTrackCheckModel):
    maximum = c.main.music_upload_max_mb * 1024 * 1024
    if payload.size > maximum:
        raise u.APIUnsuccessful(
            413,
            f"audio exceeds the configured {c.main.music_upload_max_mb} MiB limit",
        )
    relative, destination = _music_track_location(payload.sha256, payload.suffix)
    exists = destination.is_file() and destination.stat().st_size == payload.size
    return {
        "success": True,
        "exists": exists,
        "library_path": relative,
        "max_bytes": maximum,
    }


@app.post(
    "/api/music/track/upload",
    dependencies=[Depends(require_secret)],
    tags=["数据修改 / Mutations"],
    summary="流式上传一首当前播放的音频",
)
async def music_track_upload(request: Request):
    digest = request.headers.get("X-Alive-Audio-Sha256", "").casefold()
    suffix = request.headers.get("X-Alive-Audio-Suffix", "").casefold()
    if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
        raise u.APIUnsuccessful(400, "X-Alive-Audio-Sha256 must be 64 hexadecimal characters")
    if suffix not in MUSIC_AUDIO_TYPES:
        raise u.APIUnsuccessful(415, "X-Alive-Audio-Suffix is not supported")
    try:
        advertised_size = int(request.headers.get("Content-Length", ""))
    except (TypeError, ValueError) as exc:
        raise u.APIUnsuccessful(411, "Content-Length is required") from exc
    if advertised_size <= 0:
        raise u.APIUnsuccessful(411, "Content-Length must be greater than zero")

    maximum = c.main.music_upload_max_mb * 1024 * 1024
    if advertised_size > maximum:
        raise u.APIUnsuccessful(
            413,
            f"audio exceeds the configured {c.main.music_upload_max_mb} MiB limit",
        )

    relative, destination = _music_track_location(digest, suffix)
    if destination.is_file() and destination.stat().st_size == advertised_size:
        return {
            "success": True,
            "uploaded": False,
            "library_path": relative,
            "size": advertised_size,
        }

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(
        f".{destination.name}.{secrets.token_hex(8)}.part"
    )
    received = 0
    hasher = hashlib.sha256()
    try:
        with temporary.open("xb") as file:
            async for chunk in request.stream():
                if not chunk:
                    continue
                received += len(chunk)
                if received > maximum:
                    raise u.APIUnsuccessful(
                        413,
                        f"audio exceeds the configured {c.main.music_upload_max_mb} MiB limit",
                    )
                hasher.update(chunk)
                file.write(chunk)
        if received != advertised_size:
            raise u.APIUnsuccessful(400, "uploaded audio size does not match Content-Length")
        if not hmac.compare_digest(hasher.hexdigest(), digest):
            raise u.APIUnsuccessful(400, "uploaded audio sha256 does not match")
        if not _valid_audio_container(temporary, suffix):
            raise u.APIUnsuccessful(415, "uploaded bytes do not match the audio suffix")
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)

    return {
        "success": True,
        "uploaded": True,
        "library_path": relative,
        "size": received,
    }


@app.get(
    "/api/music/audio/{token}",
    tags=["公开读取 / Public reads"],
    summary="收听机主当前正在播放的已上传歌曲",
)
def music_audio(token: str):
    file = d.music_audio_path(token)
    if file is None:
        raise HTTPException(status_code=404, detail="Current music is unavailable")
    return FileResponse(
        file,
        media_type=MUSIC_AUDIO_TYPES.get(file.suffix.casefold())
        or guess_type(file.name)[0]
        or "application/octet-stream",
        headers={"Cache-Control": "no-store"},
    )


@app.post(
    "/api/music/set",
    dependencies=[Depends(require_secret)],
    tags=["数据修改 / Mutations"],
    summary="更新当前音乐与同步歌词",
)
def music_set(payload: MusicStateUpdateModel):
    music = payload.model_dump()
    if payload.source_mode == "netease-api":
        try:
            resolution = netease_resolver.resolve(
                payload.source_id,
                [
                    c.main.netease_meting_api,
                    c.main.netease_meting_fallback_api,
                ],
                c.main.netease_api_timeout,
            )
        except ValueError as error:
            raise u.APIUnsuccessful(422, str(error)) from error
        music.update(
            {
                "title": payload.title or resolution.title,
                "artist": payload.artist or resolution.artist,
                "cover_url": payload.cover_url or resolution.cover_url,
                "audio_url": resolution.audio_url if resolution.available else "",
                "source_url": f"https://music.163.com/song?id={payload.source_id}",
                "player_name": payload.player_name or "网易云音乐",
                "player_icon": "cloudmusic",
                "library_path": "",
                "lyrics": list(resolution.lyrics),
                "source_status": (
                    resolution.status
                    or "访客将直接连接公开流媒体，Alive 不保存网易云音频"
                ),
            }
        )
    return {
        "success": True,
        "music": d.music_set(music),
    }


@app.post(
    "/api/music/clear",
    dependencies=[Depends(require_secret)],
    tags=["数据修改 / Mutations"],
    summary="清空当前音乐",
)
def music_clear():
    d.music_clear()
    return {"success": True}


@app.post(
    "/api/music/cover",
    dependencies=[Depends(require_secret)],
    tags=["数据修改 / Mutations"],
    summary="上传当前歌曲的内嵌封面",
)
async def music_cover(request: Request):
    content = await request.body()
    if not content or len(content) > 3 * 1024 * 1024:
        raise u.APIUnsuccessful(400, "cover must be between 1 byte and 3 MiB")
    signatures = (
        (b"\xff\xd8\xff", ".jpg"),
        (b"\x89PNG\r\n\x1a\n", ".png"),
        (b"RIFF", ".webp"),
    )
    suffix = next((ext for signature, ext in signatures if content.startswith(signature)), "")
    if suffix == ".webp" and content[8:12] != b"WEBP":
        suffix = ""
    if not suffix:
        raise u.APIUnsuccessful(400, "cover must be JPEG, PNG, or WebP")
    digest = hashlib.sha256(content).hexdigest()
    directory = Path(u.get_path("data/public/music-covers", is_dir=True))
    file = directory / f"{digest}{suffix}"
    if not file.exists():
        file.write_bytes(content)
    return {"success": True, "url": f"/music-covers/{file.name}"}


@app.post(
    "/api/device/app-icon",
    dependencies=[Depends(require_secret)],
    tags=["数据修改 / Mutations"],
    summary="上传 Android 当前应用图标",
)
async def device_app_icon(request: Request):
    content = await request.body()
    if not content or len(content) > 1024 * 1024:
        raise u.APIUnsuccessful(400, "app icon must be between 1 byte and 1 MiB")
    signatures = (
        (b"\x89PNG\r\n\x1a\n", ".png"),
        (b"\xff\xd8\xff", ".jpg"),
        (b"RIFF", ".webp"),
    )
    suffix = next((ext for signature, ext in signatures if content.startswith(signature)), "")
    if suffix == ".webp" and content[8:12] != b"WEBP":
        suffix = ""
    if not suffix:
        raise u.APIUnsuccessful(400, "app icon must be PNG, JPEG, or WebP")
    digest = hashlib.sha256(content).hexdigest()
    directory = Path(u.get_path("data/public/app-icons", is_dir=True))
    file = directory / f"{digest}{suffix}"
    if not file.exists():
        file.write_bytes(content)
    return {"success": True, "url": f"/app-icons/{file.name}", "sha256": digest}


@app.post(
    "/api/music/player-icon",
    dependencies=[Depends(require_secret)],
    tags=["数据修改 / Mutations"],
    summary="上传音乐应用图标",
)
async def music_player_icon(request: Request):
    content = await request.body()
    if not content or len(content) > 1024 * 1024:
        raise u.APIUnsuccessful(400, "player icon must be between 1 byte and 1 MiB")
    signatures = (
        (b"\x89PNG\r\n\x1a\n", ".png"),
        (b"\xff\xd8\xff", ".jpg"),
        (b"RIFF", ".webp"),
    )
    suffix = next((ext for signature, ext in signatures if content.startswith(signature)), "")
    if suffix == ".webp" and content[8:12] != b"WEBP":
        suffix = ""
    if not suffix:
        raise u.APIUnsuccessful(400, "player icon must be PNG, JPEG, or WebP")
    digest = hashlib.sha256(content).hexdigest()
    directory = Path(u.get_path("data/public/music-player-icons", is_dir=True))
    file = directory / f"{digest}{suffix}"
    if not file.exists():
        file.write_bytes(content)
    return {"success": True, "url": f"/music-player-icons/{file.name}", "sha256": digest}


async def _json_object(request: Request) -> dict:
    try:
        body = await request.json()
    except json.JSONDecodeError as exc:
        raise u.APIUnsuccessful(400, "request body must be valid JSON") from exc
    if not isinstance(body, dict):
        raise u.APIUnsuccessful(400, "request body must be a JSON object")
    return body


@app.post(
    "/api/device/set",
    dependencies=[Depends(require_secret)],
    tags=["数据修改 / Mutations"],
    summary="新增或更新设备状态",
)
async def device_set(request: Request):
    body = await _json_object(request)
    device_id = body.get("id")
    show_name = body.get("show_name")
    using_raw = body.get("using")
    using = using_raw if isinstance(using_raw, bool) else u.tobool(using_raw)
    status = body.get("status")
    fields = body.get("fields") or {}
    if not isinstance(fields, dict):
        raise u.APIUnsuccessful(400, "fields must be a JSON object")
    d.device_set(
        id=device_id,
        show_name=show_name,
        using=using,
        status=status,
        fields=fields,
    )
    return {"success": True}


@app.post(
    "/api/device/remove",
    dependencies=[Depends(require_secret)],
    tags=["数据修改 / Mutations"],
    summary="删除一个设备",
)
async def device_remove(request: Request):
    device_id = (await _json_object(request)).get("id")
    if not device_id:
        raise u.APIUnsuccessful(400, "Missing device id!")
    if not d.device_remove(str(device_id)):
        raise u.APIUnsuccessful(404, "Device not found")
    return {"success": True}


@app.post(
    "/api/device/clear",
    dependencies=[Depends(require_secret)],
    tags=["数据修改 / Mutations"],
    summary="清空所有设备",
)
def device_clear():
    d.device_clear()
    return {"success": True}


@app.post(
    "/api/device/private",
    dependencies=[Depends(require_secret)],
    tags=["数据修改 / Mutations"],
    summary="设置设备隐私模式",
)
async def device_private_mode(request: Request):
    raw = (await _json_object(request)).get("private")
    value = raw if isinstance(raw, bool) else u.tobool(raw)
    if value is None:
        raise u.APIUnsuccessful(400, "'private' arg must be boolean")
    d.private_mode = value
    return {"success": True}


@app.get(
    "/api/admin/snapshot",
    dependencies=[Depends(require_secret)],
    tags=["后台管理 / Admin"],
    summary="获取后台设备和展示设置",
)
def admin_snapshot():
    status_id = d.status_id
    _, status = d.get_status(status_id)
    return {
        "success": True,
        "status": status.model_dump(),
        "private_mode": d.private_mode,
        "devices": d.admin_device_list,
        "settings": {
            "visit_display_mode": d.visit_display_mode,
            "danmaku_enabled": d.danmaku_enabled,
            "page_name": d.page_name,
            "page_title": d.page_title,
            "favicon": favicon_url(),
            "profile_avatar": profile_avatar_url(),
            "social_links": _social_links(),
            "music_library": d.music_library,
            "online_status_desc": d.online_status_desc,
            "offline_status_desc": d.offline_status_desc,
        },
        "metrics": d.metrics_resp,
        "comments": d.comment_admin_list(),
    }


@app.post(
    "/api/admin/settings",
    dependencies=[Depends(require_secret)],
    tags=["后台管理 / Admin"],
    summary="修改公开页面展示设置",
)
async def admin_settings(request: Request):
    body = await _json_object(request)
    if "visit_display_mode" in body:
        d.visit_display_mode = str(body["visit_display_mode"])
    if "danmaku_enabled" in body:
        raw = body["danmaku_enabled"]
        enabled = raw if isinstance(raw, bool) else u.tobool(raw)
        if enabled is None:
            raise u.APIUnsuccessful(400, "danmaku_enabled must be boolean")
        d.set_runtime_setting("danmaku_enabled", "true" if enabled else "false")
    if "page_name" in body:
        page_name = _single_line_text(str(body["page_name"]))[:64]
        if not page_name:
            raise u.APIUnsuccessful(400, "page_name cannot be empty")
        d.set_runtime_setting("page_name", page_name)
    if "page_title" in body:
        page_title = _single_line_text(str(body["page_title"]))
        if not page_title:
            raise u.APIUnsuccessful(400, "page_title cannot be empty")
        if len(page_title) > 120:
            raise u.APIUnsuccessful(400, "page_title must be 120 characters or fewer")
        d.set_runtime_setting("page_title", page_title)
    if "social_links" in body:
        d.set_runtime_setting(
            "social_links",
            json.dumps(_normalize_social_links(body["social_links"]), ensure_ascii=False),
        )
    for key in ("online_status_desc", "offline_status_desc"):
        if key in body:
            description = _single_line_text(str(body[key]))
            if not description:
                raise u.APIUnsuccessful(400, f"{key} cannot be empty")
            if len(description) > 300:
                raise u.APIUnsuccessful(400, f"{key} must be 300 characters or fewer")
            d.set_runtime_setting(key, description)
    if "music_library" in body:
        raw_path = str(body["music_library"]).strip()
        if not raw_path or len(raw_path) > 4096:
            raise u.APIUnsuccessful(400, "music_library must be a non-empty path")
        path = Path(raw_path)
        if not path.is_absolute():
            path = Path(u.current_dir()) / path
        path.mkdir(parents=True, exist_ok=True)
        if not path.is_dir():
            raise u.APIUnsuccessful(400, "music_library is not a directory")
        d.set_runtime_setting("music_library", str(path.resolve()))
    return {
        "success": True,
        "settings": {
            "visit_display_mode": d.visit_display_mode,
            "danmaku_enabled": d.danmaku_enabled,
            "page_name": d.page_name,
            "page_title": d.page_title,
            "favicon": favicon_url(),
            "profile_avatar": profile_avatar_url(),
            "social_links": _social_links(),
            "music_library": d.music_library,
            "online_status_desc": d.online_status_desc,
            "offline_status_desc": d.offline_status_desc,
        },
        "visit_metric": d.public_visit_metric,
    }


@app.post(
    "/api/admin/favicon",
    dependencies=[Depends(require_secret)],
    tags=["后台管理 / Admin"],
    summary="上传后台 favicon",
)
async def admin_favicon(request: Request):
    body = await request.body()
    if not body:
        raise u.APIUnsuccessful(400, "favicon body is required")
    if len(body) > MAX_FAVICON_BYTES:
        raise u.APIUnsuccessful(413, "favicon must be 5 MiB or smaller")
    try:
        with Image.open(io.BytesIO(body)) as source:
            if source.format not in {"PNG", "JPEG", "WEBP"}:
                raise u.APIUnsuccessful(415, "favicon must be PNG, JPEG, or WebP")
            width, height = source.size
            if width != height:
                raise u.APIUnsuccessful(400, "favicon source image must be square")
            if not 16 <= width <= 4096:
                raise u.APIUnsuccessful(400, "favicon dimensions must be between 16 and 4096 pixels")
            converted = source.convert("RGBA").resize((64, 64), Image.Resampling.LANCZOS)
            FAVICON_PATH.parent.mkdir(parents=True, exist_ok=True)
            temporary = FAVICON_PATH.with_name(f".{FAVICON_PATH.name}.{secrets.token_hex(8)}.tmp")
            try:
                converted.save(temporary, format="ICO", sizes=[(64, 64)])
                os.replace(temporary, FAVICON_PATH)
            finally:
                temporary.unlink(missing_ok=True)
    except u.APIUnsuccessful:
        raise
    except (UnidentifiedImageError, OSError, ValueError):
        raise u.APIUnsuccessful(415, "favicon must be a valid PNG, JPEG, or WebP image")
    return {"success": True, "favicon": favicon_url()}


@app.post(
    "/api/admin/profile/avatar",
    dependencies=[Depends(require_secret)],
    tags=["后台管理 / Admin"],
    summary="上传主页头像并生成网站图标",
)
async def admin_profile_avatar(request: Request):
    body = await request.body()
    if not body:
        raise u.APIUnsuccessful(400, "avatar body is required")
    if len(body) > MAX_FAVICON_BYTES:
        raise u.APIUnsuccessful(413, "avatar must be 5 MiB or smaller")
    try:
        with Image.open(io.BytesIO(body)) as source:
            if source.format not in {"PNG", "JPEG", "WEBP"}:
                raise u.APIUnsuccessful(415, "avatar must be PNG, JPEG, or WebP")
            width, height = source.size
            if not 16 <= width <= 4096 or not 16 <= height <= 4096:
                raise u.APIUnsuccessful(400, "avatar dimensions must be between 16 and 4096 pixels")
            size = min(width, height)
            left = (width - size) // 2
            top = (height - size) // 2
            square = source.convert("RGBA").crop((left, top, left + size, top + size))
            avatar = square.resize((512, 512), Image.Resampling.LANCZOS)
            favicon_image = square.resize((64, 64), Image.Resampling.LANCZOS)
            PROFILE_AVATAR_PATH.parent.mkdir(parents=True, exist_ok=True)
            FAVICON_PATH.parent.mkdir(parents=True, exist_ok=True)
            avatar_temp = PROFILE_AVATAR_PATH.with_name(
                f".{PROFILE_AVATAR_PATH.name}.{secrets.token_hex(8)}.tmp"
            )
            favicon_temp = FAVICON_PATH.with_name(f".{FAVICON_PATH.name}.{secrets.token_hex(8)}.tmp")
            try:
                avatar.save(avatar_temp, format="WEBP", quality=90, method=6)
                favicon_image.save(favicon_temp, format="ICO", sizes=[(64, 64)])
                os.replace(avatar_temp, PROFILE_AVATAR_PATH)
                os.replace(favicon_temp, FAVICON_PATH)
            finally:
                avatar_temp.unlink(missing_ok=True)
                favicon_temp.unlink(missing_ok=True)
    except u.APIUnsuccessful:
        raise
    except (UnidentifiedImageError, OSError, ValueError):
        raise u.APIUnsuccessful(415, "avatar must be a valid PNG, JPEG, or WebP image")
    return {
        "success": True,
        "profile_avatar": profile_avatar_url(),
        "favicon": favicon_url(),
    }


@app.post(
    "/api/admin/secret",
    dependencies=[Depends(require_secret)],
    tags=["后台管理 / Admin"],
    summary="轮换后台和客户端共用密钥",
)
async def admin_secret(request: Request):
    new_secret = str((await _json_object(request)).get("new_secret", ""))
    if len(new_secret) < MIN_SECRET_LENGTH or len(new_secret) > 1024:
        raise u.APIUnsuccessful(400, "new_secret must contain 6 to 1024 characters")
    if any(ord(character) < 32 for character in new_secret):
        raise u.APIUnsuccessful(400, "new_secret cannot contain control characters")
    SECRET_OVERRIDE_FILE.parent.mkdir(parents=True, exist_ok=True)
    temporary = SECRET_OVERRIDE_FILE.with_suffix(".part")
    temporary.write_text(new_secret, encoding="utf-8")
    temporary.replace(SECRET_OVERRIDE_FILE)
    try:
        SECRET_OVERRIDE_FILE.chmod(0o600)
    except OSError:
        pass
    c.main.secret = new_secret
    response = JSONResponse(
        {"success": True, "message": "Secret updated; existing sessions and clients must sign in again"}
    )
    forwarded_proto = request.headers.get("X-Forwarded-Proto", "").split(",")[0].strip()
    secure_cookie = request.url.scheme == "https" or forwarded_proto == "https"
    response.set_cookie(
        SESSION_COOKIE,
        _session_token(),
        max_age=SESSION_MAX_AGE,
        httponly=True,
        secure=secure_cookie,
        samesite="strict",
    )
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


@app.post(
    "/api/admin/device/profile",
    dependencies=[Depends(require_secret)],
    tags=["后台管理 / Admin"],
    summary="修改设备显示资料",
)
async def admin_device_profile(request: Request):
    body = await _json_object(request)
    sort_order = None
    if "sort_order" in body:
        try:
            sort_order = int(body["sort_order"])
        except (TypeError, ValueError) as exc:
            raise u.APIUnsuccessful(400, "sort_order must be int") from exc
    public_raw = body.get("public", True)
    is_public = public_raw if isinstance(public_raw, bool) else u.tobool(public_raw)
    if is_public is None:
        raise u.APIUnsuccessful(400, "public must be boolean")
    profile = d.device_profile_set(
        id=str(body.get("id", "")),
        display_name=str(body.get("display_name", "")),
        icon_key=str(body.get("icon_key", "desktop")),
        sort_order=sort_order,
        is_public=is_public,
    )
    return {"success": True, "device": profile}


@app.post(
    "/api/admin/device/reorder",
    dependencies=[Depends(require_secret)],
    tags=["后台管理 / Admin"],
    summary="相邻移动设备并返回完整排序",
)
async def admin_device_reorder(request: Request):
    body = await _json_object(request)
    device_id = body.get("id")
    direction = body.get("direction")
    if not isinstance(device_id, str) or not device_id:
        raise u.APIUnsuccessful(400, "device id must be a non-empty string")
    if direction not in {"up", "down"}:
        raise u.APIUnsuccessful(400, "direction must be up or down")
    return {"success": True, "devices": d.device_reorder(device_id, direction)}


@app.post(
    "/api/admin/comments/remove",
    dependencies=[Depends(require_secret)],
    tags=["后台管理 / Admin"],
    summary="删除一条公开评论",
)
async def admin_comment_remove(request: Request):
    try:
        comment_id = int((await _json_object(request)).get("id"))
    except (TypeError, ValueError) as exc:
        raise u.APIUnsuccessful(400, "comment id must be int") from exc
    if not d.comment_remove(comment_id):
        raise u.APIUnsuccessful(404, "Comment not found")
    return {"success": True}


@app.post(
    "/api/admin/comments/update",
    dependencies=[Depends(require_secret)],
    tags=["后台管理 / Admin"],
    summary="修改评论收藏和置顶状态",
)
async def admin_comment_update(request: Request):
    body = await _json_object(request)
    try:
        comment_id = int(body.get("id"))
    except (TypeError, ValueError) as exc:
        raise u.APIUnsuccessful(400, "comment id must be int") from exc
    if not isinstance(body.get("favorite"), bool) or not isinstance(body.get("pinned"), bool):
        raise u.APIUnsuccessful(400, "favorite and pinned must be boolean")
    comment = d.comment_update(comment_id, body["favorite"], body["pinned"])
    if comment is None:
        raise u.APIUnsuccessful(404, "Comment not found")
    return {"success": True, "comment": comment}


@app.post(
    "/api/admin/comments/clear",
    dependencies=[Depends(require_secret)],
    tags=["后台管理 / Admin"],
    summary="清空所有公开评论",
)
def admin_comments_clear():
    return {"success": True, "removed": d.comment_clear()}


async def _panel_authorized(request: Request) -> bool:
    try:
        await require_secret(request)
        return True
    except u.APIUnsuccessful:
        return False


@app.get("/panel", response_class=HTMLResponse, include_in_schema=False)
async def admin_panel(request: Request):
    if not await _panel_authorized(request):
        return RedirectResponse("/panel/login", status_code=302)
    content = render_template(
        request,
        "panel.html",
        c=c,
        page_name=d.page_name,
        page_title=d.page_title,
        page_favicon=favicon_url(),
        profile_avatar=profile_avatar_url(),
        inject="",
    )
    if content is None:
        raise HTTPException(status_code=404)
    return HTMLResponse(content)


@app.get("/panel/login", response_class=HTMLResponse, include_in_schema=False)
def login(request: Request):
    if _valid_session(request.cookies.get(SESSION_COOKIE)):
        return RedirectResponse("/panel", status_code=302)
    content = render_template(
        request,
        "login.html",
        c=c,
        page_title=d.page_title,
        page_favicon=favicon_url(),
    )
    if content is None:
        raise HTTPException(status_code=404)
    return HTMLResponse(
        content,
        headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"},
    )


@app.post(
    "/panel/auth",
    dependencies=[Depends(require_secret)],
    include_in_schema=False,
)
def auth(request: Request):
    response = JSONResponse(
        {"success": True, "code": "OK", "message": "Login successful"}
    )
    forwarded_proto = request.headers.get("X-Forwarded-Proto", "").split(",")[0].strip()
    secure_cookie = request.url.scheme == "https" or forwarded_proto == "https"
    response.set_cookie(
        SESSION_COOKIE,
        _session_token(),
        max_age=SESSION_MAX_AGE,
        httponly=True,
        secure=secure_cookie,
        samesite="strict",
    )
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


@app.post("/panel/logout", include_in_schema=False)
def logout():
    response = JSONResponse({"success": True})
    response.delete_cookie(SESSION_COOKIE)
    return response


@app.post(
    "/panel/verify",
    dependencies=[Depends(require_secret)],
    include_in_schema=False,
)
def verify_secret():
    return {"success": True, "code": "OK", "message": "Secret verified"}


POST_ONLY_PATHS = {
    "/api/status/set",
    "/api/device/set",
    "/api/device/remove",
    "/api/device/clear",
    "/api/device/private",
    "/api/health/set",
    "/api/health/clear",
    "/api/music/set",
    "/api/music/clear",
    "/api/music/cover",
    "/api/music/player-icon",
    "/api/device/app-icon",
    "/api/music/track/check",
    "/api/music/track/upload",
    "/api/comments/create",
    "/api/admin/settings",
    "/api/admin/favicon",
    "/api/admin/profile/avatar",
    "/api/admin/secret",
    "/api/admin/device/profile",
    "/api/admin/device/reorder",
    "/api/admin/comments/remove",
    "/api/admin/comments/update",
    "/api/admin/comments/clear",
    "/panel/auth",
    "/panel/logout",
    "/panel/verify",
}


def _serve_public(path_name: str):
    for root in (Path(u.get_path("data/public", is_dir=True)), Path(u.get_path("public", is_dir=True))):
        file = _safe_file(root, path_name)
        if file:
            return FileResponse(file, media_type=guess_type(path_name)[0])
    raise HTTPException(status_code=404)


@app.get("/{path_name:path}", include_in_schema=False)
def serve_public(path_name: str):
    if f"/{path_name}" in POST_ONLY_PATHS:
        raise HTTPException(
            status_code=405,
            detail="This operation only accepts POST",
            headers={"Allow": "POST"},
        )
    return _serve_public(path_name)


if __name__ == "__main__":
    listening = f'{f"[{c.main.host}]" if ":" in c.main.host else c.main.host}:{c.main.port}'
    scheme = "https" if c.main.https else "http"
    l.info("Listening service on: %s://%s", scheme, listening)
    uvicorn.run(
        app,
        host=c.main.host,
        port=c.main.port,
        log_config=None,
        access_log=False,
        ssl_certfile=c.main.ssl_cert if c.main.https else None,
        ssl_keyfile=c.main.ssl_key if c.main.https else None,
    )
