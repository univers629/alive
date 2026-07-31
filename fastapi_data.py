# coding: utf-8
"""Framework-independent persistence used by the FastAPI application."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
import hashlib
import hmac
from io import BytesIO
from logging import getLogger
from pathlib import Path
from threading import RLock, Thread
from time import sleep, time
from typing import Any, Iterator

import pytz
import schedule
from sqlalchemy import JSON, Boolean, Float, Integer, String, Text, create_engine, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, scoped_session, sessionmaker
from sqlalchemy.pool import StaticPool

import utils as u
from models import ConfigModel, _StatusItemModel

l = getLogger(__name__)
LIMIT = 1024


class Base(DeclarativeBase):
    pass


class _MainData(Base):
    __tablename__ = "main"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=0)
    status: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    private_mode: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_updated: Mapped[float] = mapped_column(Float, default=time, onupdate=time)


class _DeviceStatusData(Base):
    __tablename__ = "device_status"

    id: Mapped[str] = mapped_column(String(LIMIT), primary_key=True, unique=True, nullable=False)
    show_name: Mapped[str] = mapped_column(String(LIMIT), nullable=False)
    using: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    status: Mapped[str | None] = mapped_column(Text, nullable=True)
    fields: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    last_updated: Mapped[float] = mapped_column(Float, default=time, onupdate=time)


class _MetricsMetaData(Base):
    __tablename__ = "metrics_meta"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=0)
    today: Mapped[str] = mapped_column(String(LIMIT), nullable=False, default="")
    week: Mapped[str] = mapped_column(String(LIMIT), nullable=False, default="")
    month: Mapped[str] = mapped_column(String(LIMIT), nullable=False, default="")
    year: Mapped[str] = mapped_column(String(LIMIT), nullable=False, default="")


class _MetricsData(Base):
    __tablename__ = "metrics"

    path: Mapped[str] = mapped_column(String(LIMIT), primary_key=True, unique=True, nullable=False)
    daily: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    weekly: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    monthly: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    yearly: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class _MusicStateData(Base):
    __tablename__ = "music_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=0)
    device_id: Mapped[str] = mapped_column(String(LIMIT), nullable=False, default="")
    title: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    artist: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    album: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    cover_url: Mapped[str] = mapped_column(Text, nullable=False, default="")
    audio_url: Mapped[str] = mapped_column(Text, nullable=False, default="")
    source_url: Mapped[str] = mapped_column(Text, nullable=False, default="")
    duration: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    position: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    playing: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    lyrics: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    updated_at: Mapped[float] = mapped_column(Float, nullable=False, default=time)


class _MusicPlayerMetaData(Base):
    __tablename__ = "music_player_meta"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=0)
    player_name: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    player_icon: Mapped[str] = mapped_column(String(64), nullable=False, default="media-player")
    library_path: Mapped[str] = mapped_column(Text, nullable=False, default="")


class _MusicSourceData(Base):
    __tablename__ = "music_source"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=0)
    source_mode: Mapped[str] = mapped_column(
        String(32), nullable=False, default="metadata-only"
    )
    source_id: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(300), nullable=False, default="")


class _HealthStateData(Base):
    __tablename__ = "health_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=0)
    heart_rate: Mapped[int | None] = mapped_column(Integer, nullable=True)
    resting_heart_rate: Mapped[int | None] = mapped_column(Integer, nullable=True)
    heart_rate_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    heart_rate_max: Mapped[int | None] = mapped_column(Integer, nullable=True)
    steps: Mapped[int | None] = mapped_column(Integer, nullable=True)
    step_goal: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    measured_at: Mapped[float] = mapped_column(Float, nullable=False, default=time)
    updated_at: Mapped[float] = mapped_column(Float, nullable=False, default=time)


class _SiteSettingsData(Base):
    __tablename__ = "site_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=0)
    visit_display_mode: Mapped[str] = mapped_column(
        String(16), nullable=False, default="total"
    )


class _RuntimeSettingData(Base):
    __tablename__ = "runtime_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False, default="")


class _DeviceProfileData(Base):
    __tablename__ = "device_profiles"

    id: Mapped[str] = mapped_column(
        String(LIMIT), primary_key=True, unique=True, nullable=False
    )
    display_name: Mapped[str] = mapped_column(String(LIMIT), nullable=False, default="")
    icon_key: Mapped[str] = mapped_column(String(32), nullable=False, default="desktop")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_public: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class _CommentData(Base):
    __tablename__ = "comments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nickname: Mapped[str] = mapped_column(String(24), nullable=False, default="匿名访客")
    content: Mapped[str] = mapped_column(String(160), nullable=False)
    color: Mapped[str] = mapped_column(String(16), nullable=False, default="violet")
    visitor_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    created_at: Mapped[float] = mapped_column(Float, nullable=False, default=time)


def _database_url(configured_url: str) -> str:
    """Resolve a relative SQLite URL below the project instance directory."""
    if not configured_url.startswith("sqlite:///"):
        return configured_url

    raw_path = configured_url.removeprefix("sqlite:///")
    if raw_path == ":memory:":
        return configured_url

    path = Path(raw_path)
    if not path.is_absolute():
        # The default ``../data/alive.db`` resolves to the project's data folder.
        base = Path(u.current_dir()) / "instance"
        path = (base / path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{path.as_posix()}"


class Data:
    """Thread-safe synchronous data access for FastAPI endpoints."""

    def __init__(self, config: ConfigModel, start_scheduler: bool = True):
        perf = u.perf_counter()
        self._c = config
        self._write_lock = RLock()
        url = _database_url(config.main.database)
        engine_kwargs: dict[str, Any] = {"pool_pre_ping": True}
        if url.startswith("sqlite:"):
            engine_kwargs["connect_args"] = {"check_same_thread": False}
        if url == "sqlite:///:memory:":
            engine_kwargs["poolclass"] = StaticPool
        self.engine = create_engine(url, **engine_kwargs)
        self._session_factory = scoped_session(
            sessionmaker(bind=self.engine, expire_on_commit=False)
        )
        self.ensure_schema()

        if config.metrics.enabled:
            self._metrics_refresh()
        if start_scheduler:
            self._schedule_loop_th = Thread(target=self._schedule_loop, daemon=True)
            self._schedule_loop_th.start()
        l.debug("[data] FastAPI data init took %sms", perf())

    def ensure_schema(self) -> None:
        """Create missing tables and singleton rows (safe to call on startup)."""
        Base.metadata.create_all(self.engine)

        with self.session() as session:
            if session.scalar(select(_MainData).limit(1)) is None:
                session.add(_MainData(id=0))
            if self._c.metrics.enabled and session.scalar(select(_MetricsMetaData).limit(1)) is None:
                session.add(_MetricsMetaData(id=0))
            if session.scalar(select(_SiteSettingsData).limit(1)) is None:
                session.add(_SiteSettingsData(id=0))

    @contextmanager
    def session(self) -> Iterator[Any]:
        session = self._session_factory()
        try:
            yield session
            session.commit()
        except SQLAlchemyError as exc:
            session.rollback()
            l.error("SQL call failed: %s", exc)
            raise u.APIUnsuccessful(500, "Database Error") from exc
        finally:
            session.close()
            self._session_factory.remove()

    def close(self) -> None:
        self._session_factory.remove()
        self.engine.dispose()

    def _schedule_loop(self) -> None:
        scheduler = schedule.Scheduler()
        if self._c.metrics.enabled:
            scheduler.every().day.at("00:00:00", self._c.main.timezone).do(self._metrics_refresh)
        if self._c.status.device_timeout > 0:
            scheduler.every(5).seconds.do(self._expire_devices)
        scheduler.every(max(self._c.main.cache_age, 1)).seconds.do(self._clean_cache)
        while True:
            scheduler.run_pending()
            sleep(1)

    def _main(self, session: Any) -> _MainData:
        row = session.scalar(select(_MainData).limit(1))
        if row is None:
            row = _MainData(id=0)
            session.add(row)
            session.flush()
        return row

    @property
    def status_id(self) -> int:
        with self.session() as session:
            return self._main(session).status

    @status_id.setter
    def status_id(self, value: int) -> None:
        with self._write_lock, self.session() as session:
            row = self._main(session)
            row.status = value
            row.last_updated = time()

    def get_status(self, status_id: int) -> tuple[bool, _StatusItemModel]:
        try:
            return True, self._c.status.status_list[status_id]
        except IndexError:
            return False, _StatusItemModel(
                id=status_id,
                name="Unknown",
                desc="未知的标识符，可能是配置问题。",
                color="error",
            )

    @property
    def status(self) -> tuple[bool, _StatusItemModel]:
        return self.get_status(self.status_id)

    @property
    def status_dict(self) -> tuple[bool, dict[str, int | str]]:
        exists, status = self.status
        return exists, status.model_dump()

    @property
    def private_mode(self) -> bool:
        with self.session() as session:
            return self._main(session).private_mode

    @private_mode.setter
    def private_mode(self, value: bool) -> None:
        with self._write_lock, self.session() as session:
            row = self._main(session)
            row.private_mode = value
            row.last_updated = time()

    @property
    def last_updated(self) -> float:
        with self.session() as session:
            return self._main(session).last_updated

    @last_updated.setter
    def last_updated(self, value: float) -> None:
        with self._write_lock, self.session() as session:
            self._main(session).last_updated = value

    @staticmethod
    def _serialize_device(
        device: _DeviceStatusData,
        profile: _DeviceProfileData | None = None,
    ) -> dict[str, Any]:
        result = {
            "id": device.id,
            "show_name": profile.display_name if profile and profile.display_name else device.show_name,
            "using": device.using,
            "status": device.status,
            "fields": device.fields or {},
            "last_updated": device.last_updated,
        }
        result["profile"] = {
            "display_name": profile.display_name if profile else "",
            "icon_key": profile.icon_key if profile else "desktop",
            "sort_order": profile.sort_order if profile else 0,
            "public": profile.is_public if profile else True,
        }
        return result

    @property
    def _raw_device_list(self) -> dict[str, _DeviceStatusData]:
        if self.private_mode:
            return {}
        with self.session() as session:
            devices = list(session.scalars(select(_DeviceStatusData)).all())
            return {device.id: device for device in devices}

    @property
    def _raw_device_list_dict(self) -> dict[str, dict[str, Any]]:
        devices = self._raw_device_list
        if not devices:
            return {}
        with self.session() as session:
            profiles = {
                profile.id: profile
                for profile in session.scalars(select(_DeviceProfileData)).all()
            }
            return {
                device_id: self._serialize_device(device, profiles.get(device_id))
                for device_id, device in devices.items()
            }

    @property
    def device_list(self) -> dict[str, dict[str, Any]]:
        devices = self._raw_device_list_dict
        devices = {
            device_id: device
            for device_id, device in devices.items()
            if device["profile"]["public"]
        }
        if self._c.status.not_using:
            for device in devices.values():
                if device.get("using") is False:
                    device["status"] = self._c.status.not_using
        if self._c.status.sorted:
            devices = dict(sorted(devices.items()))
        if self._c.status.using_first:
            rank = {True: 0, False: 1, None: 2}
            devices = dict(
                sorted(
                    devices.items(),
                    key=lambda item: (rank.get(item[1].get("using"), 2), item[0] if self._c.status.sorted else ""),
                )
            )
        devices = dict(
            sorted(
                devices.items(),
                key=lambda item: (
                    item[1]["profile"]["sort_order"],
                    item[1]["show_name"].casefold(),
                ),
            )
        )
        return devices

    @property
    def admin_device_list(self) -> dict[str, dict[str, Any]]:
        with self.session() as session:
            devices = list(session.scalars(select(_DeviceStatusData)).all())
            profiles = {
                profile.id: profile
                for profile in session.scalars(select(_DeviceProfileData)).all()
            }
            serialized = {
                device.id: self._serialize_device(device, profiles.get(device.id))
                for device in devices
            }
        return dict(
            sorted(
                serialized.items(),
                key=lambda item: (
                    item[1]["profile"]["sort_order"],
                    item[1]["show_name"].casefold(),
                ),
            )
        )

    def device_profile_set(
        self,
        id: str,
        display_name: str,
        icon_key: str,
        sort_order: int,
        is_public: bool,
    ) -> dict[str, Any]:
        allowed_icons = {
            "desktop",
            "laptop",
            "phone",
            "tablet",
            "watch",
            "server",
            "game",
            "other",
        }
        if not id:
            raise u.APIUnsuccessful(400, "device id cannot be empty")
        if len(display_name) > LIMIT:
            raise u.APIUnsuccessful(400, "display_name is too long")
        if icon_key not in allowed_icons:
            raise u.APIUnsuccessful(400, "unsupported icon_key")
        if not -100000 <= sort_order <= 100000:
            raise u.APIUnsuccessful(400, "sort_order is outside the allowed range")

        with self._write_lock, self.session() as session:
            device = session.get(_DeviceStatusData, id)
            if device is None:
                raise u.APIUnsuccessful(404, "Device not found")
            profile = session.get(_DeviceProfileData, id)
            if profile is None:
                profile = _DeviceProfileData(id=id)
                session.add(profile)
            profile.display_name = display_name.strip()
            profile.icon_key = icon_key
            profile.sort_order = sort_order
            profile.is_public = is_public
            now = time()
            self._main(session).last_updated = now
            session.flush()
            return self._serialize_device(device, profile)

    def device_get(self, id: str) -> _DeviceStatusData | None:
        with self.session() as session:
            return session.get(_DeviceStatusData, id)

    def device_set(
        self,
        id: str | None = None,
        show_name: str | None = None,
        using: bool | None = None,
        status: str | None = None,
        fields: dict | None = None,
    ) -> None:
        if not id:
            raise u.APIUnsuccessful(400, "device id cannot be empty!")
        with self._write_lock, self.session() as session:
            device = session.get(_DeviceStatusData, id)
            if device is None:
                if not show_name:
                    raise u.APIUnsuccessful(400, "device show_name cannot be empty!")
                device = _DeviceStatusData(
                    id=id,
                    show_name=show_name,
                    using=using,
                    status=status,
                    fields=fields or {},
                    last_updated=time(),
                )
                session.add(device)
            else:
                if show_name:
                    device.show_name = show_name
                if using is not None:
                    device.using = using
                if status is not None:
                    device.status = status
                if fields:
                    device.fields = u.deep_merge_dict(device.fields or {}, fields)
                device.last_updated = time()
            self._main(session).last_updated = time()

    def device_remove(self, id: str) -> bool:
        with self._write_lock, self.session() as session:
            device = session.get(_DeviceStatusData, id)
            if device is None:
                return False
            profile = session.get(_DeviceProfileData, id)
            if profile is not None:
                session.delete(profile)
            session.delete(device)
            self._main(session).last_updated = time()
            return True

    def device_clear(self) -> None:
        with self._write_lock, self.session() as session:
            for device in session.scalars(select(_DeviceStatusData)).all():
                session.delete(device)
            for profile in session.scalars(select(_DeviceProfileData)).all():
                session.delete(profile)
            self._main(session).last_updated = time()

    @property
    def visit_display_mode(self) -> str:
        with self.session() as session:
            settings = session.get(_SiteSettingsData, 0)
            return settings.visit_display_mode if settings else "total"

    @visit_display_mode.setter
    def visit_display_mode(self, value: str) -> None:
        if value not in {"total", "daily", "monthly"}:
            raise u.APIUnsuccessful(400, "unsupported visit_display_mode")
        with self._write_lock, self.session() as session:
            settings = session.get(_SiteSettingsData, 0)
            if settings is None:
                settings = _SiteSettingsData(id=0)
                session.add(settings)
            settings.visit_display_mode = value
            self._main(session).last_updated = time()

    def runtime_setting(self, key: str, default: str = "") -> str:
        with self.session() as session:
            setting = session.get(_RuntimeSettingData, key)
            return setting.value if setting else default

    def set_runtime_setting(self, key: str, value: str) -> None:
        if key not in {"danmaku_enabled", "page_name", "music_library"}:
            raise u.APIUnsuccessful(400, "unsupported runtime setting")
        with self._write_lock, self.session() as session:
            setting = session.get(_RuntimeSettingData, key)
            if setting is None:
                setting = _RuntimeSettingData(key=key)
                session.add(setting)
            setting.value = value
            self._main(session).last_updated = time()

    @property
    def danmaku_enabled(self) -> bool:
        return self.runtime_setting("danmaku_enabled", "true") == "true"

    @property
    def page_name(self) -> str:
        return self.runtime_setting("page_name", self._c.page.name)

    @property
    def music_library(self) -> str:
        return self.runtime_setting("music_library", self._c.main.music_library)

    @property
    def public_visit_metric(self) -> dict[str, Any]:
        mode = self.visit_display_mode
        labels = {
            "total": "已被视奸",
            "daily": "今日被视奸",
            "monthly": "本月被视奸",
        }
        if not self._c.metrics.enabled:
            return {"enabled": False, "mode": mode, "label": labels[mode], "value": 0}
        daily, _, monthly, _, total = self.metric_data_index
        values = {"total": total, "daily": daily, "monthly": monthly}
        return {
            "enabled": True,
            "mode": mode,
            "label": labels[mode],
            "value": values[mode],
        }

    @staticmethod
    def _serialize_comment(comment: _CommentData) -> dict[str, Any]:
        return {
            "id": comment.id,
            "nickname": comment.nickname,
            "content": comment.content,
            "color": comment.color,
            "created_at": comment.created_at,
        }

    def comment_list(self, limit: int = 50) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 100))
        with self.session() as session:
            comments = list(
                session.scalars(
                    select(_CommentData)
                    .order_by(_CommentData.id.desc())
                    .limit(limit)
                ).all()
            )
        return [self._serialize_comment(comment) for comment in reversed(comments)]

    def comment_count(self, since: float | None = None) -> int:
        statement = select(func.count()).select_from(_CommentData)
        if since is not None:
            statement = statement.where(_CommentData.created_at >= since)
        with self.session() as session:
            return int(session.scalar(statement) or 0)

    def comment_create(
        self,
        nickname: str,
        content: str,
        color: str,
        visitor_hash: str,
    ) -> dict[str, Any]:
        now = time()
        with self._write_lock, self.session() as session:
            latest = session.scalar(
                select(_CommentData)
                .where(_CommentData.visitor_hash == visitor_hash)
                .order_by(_CommentData.id.desc())
                .limit(1)
            )
            if latest is not None and now - latest.created_at < 8:
                wait_seconds = max(1, 8 - int(now - latest.created_at))
                raise u.APIUnsuccessful(
                    429,
                    f"发送得太快了，请等待 {wait_seconds} 秒",
                )

            comment = _CommentData(
                nickname=nickname,
                content=content,
                color=color,
                visitor_hash=visitor_hash,
                created_at=now,
            )
            session.add(comment)
            session.flush()

            stale_comments = list(
                session.scalars(
                    select(_CommentData)
                    .order_by(_CommentData.id.desc())
                    .offset(300)
                ).all()
            )
            for stale in stale_comments:
                session.delete(stale)
            return self._serialize_comment(comment)

    def comment_remove(self, comment_id: int) -> bool:
        with self._write_lock, self.session() as session:
            comment = session.get(_CommentData, comment_id)
            if comment is None:
                return False
            session.delete(comment)
            return True

    @staticmethod
    def _serialize_health(state: _HealthStateData | None, timeout: int = 0) -> dict[str, Any]:
        if state is None or (state.heart_rate is None and state.steps is None):
            return {
                "active": False,
                "stale": False,
                "heart_rate": None,
                "resting_heart_rate": None,
                "heart_rate_min": None,
                "heart_rate_max": None,
                "steps": None,
                "step_goal": None,
                "source": "",
                "measured_at": 0,
                "updated_at": 0,
            }
        return {
            "active": True,
            "stale": bool(timeout > 0 and time() - state.updated_at > timeout),
            "heart_rate": state.heart_rate,
            "resting_heart_rate": state.resting_heart_rate,
            "heart_rate_min": state.heart_rate_min,
            "heart_rate_max": state.heart_rate_max,
            "steps": state.steps,
            "step_goal": state.step_goal,
            "source": state.source,
            "measured_at": state.measured_at,
            "updated_at": state.updated_at,
        }

    @property
    def health_state(self) -> dict[str, Any]:
        if self.private_mode:
            return self._serialize_health(None)
        with self.session() as session:
            return self._serialize_health(
                session.get(_HealthStateData, 0),
                self._c.main.health_session_timeout,
            )

    def health_set(self, payload: dict[str, Any]) -> dict[str, Any]:
        now = time()
        value_keys = (
            "heart_rate",
            "resting_heart_rate",
            "heart_rate_min",
            "heart_rate_max",
            "steps",
            "step_goal",
        )
        with self._write_lock, self.session() as session:
            state = session.get(_HealthStateData, 0)
            if state is None:
                state = _HealthStateData(id=0)
                session.add(state)
            for key in value_keys:
                value = payload.get(key)
                if value is not None:
                    setattr(state, key, value)
            if "source" in payload:
                state.source = str(payload.get("source") or "")
            state.measured_at = float(payload.get("measured_at") or now)
            state.updated_at = now
            self._main(session).last_updated = now
            session.flush()
            return self._serialize_health(state, self._c.main.health_session_timeout)

    def health_clear(self) -> None:
        with self._write_lock, self.session() as session:
            state = session.get(_HealthStateData, 0)
            if state is not None:
                session.delete(state)
            self._main(session).last_updated = time()

    @staticmethod
    def _serialize_music(
        state: _MusicStateData | None,
        meta: _MusicPlayerMetaData | None = None,
        source: _MusicSourceData | None = None,
        audio_url: str = "",
        expires_at: float = 0,
    ) -> dict[str, Any]:
        source_mode = (
            source.source_mode
            if source
            else ("local-upload" if meta and meta.library_path else "metadata-only")
        )
        if state is None or not state.title:
            return {
                "active": False,
                "source_mode": "metadata-only",
                "source_id": "",
                "source_status": "",
                "device_id": "",
                "title": "",
                "artist": "",
                "album": "",
                "cover_url": "",
                "audio_url": "",
                "source_url": "",
                "player_name": "",
                "player_icon": "media-player",
                "duration": 0,
                "position": 0,
                "playing": False,
                "lyrics": [],
                "updated_at": 0,
                "expires_at": 0,
            }
        result = {
            "active": True,
            "source_mode": source_mode,
            "source_id": source.source_id if source else "",
            "source_status": source.status if source else "",
            "device_id": state.device_id,
            "title": state.title,
            "artist": state.artist,
            "album": state.album,
            "cover_url": state.cover_url,
            "audio_url": state.audio_url,
            "source_url": state.source_url,
            "player_name": meta.player_name if meta else "",
            "player_icon": meta.player_icon if meta else "media-player",
            "duration": state.duration,
            "position": state.position,
            "playing": state.playing,
            "lyrics": state.lyrics or [],
            "updated_at": state.updated_at,
            "expires_at": expires_at,
        }
        if audio_url:
            result["audio_url"] = audio_url
        return result

    @property
    def music_state(self) -> dict[str, Any]:
        if self.private_mode:
            return self._serialize_music(None)
        with self.session() as session:
            state = session.get(_MusicStateData, 0)
            meta = session.get(_MusicPlayerMetaData, 0)
            source = session.get(_MusicSourceData, 0)
            if (
                state is not None
                and self._c.main.music_session_timeout > 0
                and time() - state.updated_at > self._c.main.music_session_timeout
            ):
                return self._serialize_music(None)
            audio_url = ""
            if (
                meta
                and meta.library_path
                and (
                    source is None
                    or source.source_mode == "local-upload"
                )
            ):
                token = hmac.new(
                    self._c.main.secret.encode("utf-8"),
                    f"alive-music:{meta.library_path}".encode("utf-8"),
                    hashlib.sha256,
                ).hexdigest()[:32]
                audio_url = f"/api/music/audio/{token}"
            expires_at = (
                state.updated_at + self._c.main.music_session_timeout
                if state and self._c.main.music_session_timeout > 0
                else 0
            )
            return self._serialize_music(state, meta, source, audio_url, expires_at)

    def music_set(self, payload: dict[str, Any]) -> dict[str, Any]:
        now = time()
        lyrics = sorted(payload.get("lyrics") or [], key=lambda line: line.get("time", 0))
        duration = float(payload.get("duration") or 0)
        position = float(payload.get("position") or 0)
        if duration > 0:
            position = min(position, duration)

        with self._write_lock, self.session() as session:
            state = session.get(_MusicStateData, 0)
            if state is None:
                state = _MusicStateData(id=0)
                session.add(state)
            meta = session.get(_MusicPlayerMetaData, 0)
            if meta is None:
                meta = _MusicPlayerMetaData(id=0)
                session.add(meta)
            source = session.get(_MusicSourceData, 0)
            if source is None:
                source = _MusicSourceData(id=0)
                session.add(source)
            source_mode = payload.get("source_mode") or "metadata-only"
            if source_mode == "metadata-only" and payload.get("library_path"):
                source_mode = "local-upload"
            elif source_mode == "metadata-only" and payload.get("audio_url"):
                source_mode = "external-url"
            state.device_id = payload.get("device_id", "")
            state.title = payload.get("title", "")
            state.artist = payload.get("artist", "")
            state.album = payload.get("album", "")
            state.cover_url = payload.get("cover_url", "")
            state.audio_url = payload.get("audio_url", "")
            state.source_url = payload.get("source_url", "")
            state.duration = duration
            state.position = position
            state.playing = bool(payload.get("playing"))
            state.lyrics = lyrics
            state.updated_at = now
            meta.player_name = payload.get("player_name", "")
            meta.player_icon = payload.get("player_icon", "media-player")
            meta.library_path = payload.get("library_path", "")
            source.source_mode = source_mode
            source.source_id = payload.get("source_id", "")
            source.status = payload.get("source_status", "")
            self._main(session).last_updated = now
            session.flush()
            audio_url = ""
            if (
                meta.library_path
                and source.source_mode == "local-upload"
            ):
                token = hmac.new(
                    self._c.main.secret.encode("utf-8"),
                    f"alive-music:{meta.library_path}".encode("utf-8"),
                    hashlib.sha256,
                ).hexdigest()[:32]
                audio_url = f"/api/music/audio/{token}"
            expires_at = (
                state.updated_at + self._c.main.music_session_timeout
                if self._c.main.music_session_timeout > 0
                else 0
            )
            return self._serialize_music(state, meta, source, audio_url, expires_at)

    def music_clear(self) -> None:
        with self._write_lock, self.session() as session:
            state = session.get(_MusicStateData, 0)
            if state is not None:
                session.delete(state)
            meta = session.get(_MusicPlayerMetaData, 0)
            if meta is not None:
                session.delete(meta)
            source = session.get(_MusicSourceData, 0)
            if source is not None:
                session.delete(source)
            self._main(session).last_updated = time()

    def music_audio_path(self, token: str) -> Path | None:
        if self.private_mode:
            return None
        with self.session() as session:
            state = session.get(_MusicStateData, 0)
            meta = session.get(_MusicPlayerMetaData, 0)
            source = session.get(_MusicSourceData, 0)
            relative = meta.library_path if meta else ""
            if (
                state is None
                or not state.title
                or (
                    source is not None
                    and source.source_mode != "local-upload"
                )
                or (
                    self._c.main.music_session_timeout > 0
                    and time() - state.updated_at > self._c.main.music_session_timeout
                )
            ):
                return None
        if not relative:
            return None
        expected = hmac.new(
            self._c.main.secret.encode("utf-8"),
            f"alive-music:{relative}".encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()[:32]
        if not hmac.compare_digest(token, expected):
            return None
        root = Path(self.music_library)
        if not root.is_absolute():
            root = Path(u.current_dir()) / root
        root = root.resolve()
        candidate = (root / relative).resolve()
        try:
            candidate.relative_to(root)
        except ValueError:
            return None
        return candidate if candidate.is_file() else None

    def _expire_devices(self) -> int:
        """Mark devices offline when their client heartbeat disappears."""
        timeout = self._c.status.device_timeout
        if timeout <= 0:
            return 0
        cutoff = time() - timeout
        with self._write_lock, self.session() as session:
            expired = list(
                session.scalars(
                    select(_DeviceStatusData).where(
                        _DeviceStatusData.using.is_(True),
                        _DeviceStatusData.last_updated < cutoff,
                    )
                ).all()
            )
            if not expired:
                return 0
            for device in expired:
                device.using = False
                device.status = ""
            self._main(session).last_updated = time()
            l.info(
                "[Device] Marked %s stale device(s) as not using after %ss",
                len(expired),
                timeout,
            )
            return len(expired)

    def record_metrics(self, path: str, count: int = 1, override: bool = False) -> None:
        if path.startswith("/static/") or path.startswith("/static-themed/"):
            path = "[static]"
        if path not in self._c.metrics.allow_list:
            return
        with self._write_lock, self.session() as session:
            metric = session.get(_MetricsData, path)
            if metric is None:
                metric = _MetricsData(path=path, daily=0, weekly=0, monthly=0, yearly=0, total=0)
                session.add(metric)
            if override:
                metric.daily = metric.weekly = metric.monthly = metric.yearly = metric.total = count
            else:
                metric.daily += count
                metric.weekly += count
                metric.monthly += count
                metric.yearly += count
                metric.total += count

    @property
    def metrics_data(self) -> tuple[dict[str, int], dict[str, int], dict[str, int], dict[str, int], dict[str, int]]:
        with self.session() as session:
            metrics = list(session.scalars(select(_MetricsData)).all())
            return (
                {item.path: item.daily for item in metrics},
                {item.path: item.weekly for item in metrics},
                {item.path: item.monthly for item in metrics},
                {item.path: item.yearly for item in metrics},
                {item.path: item.total for item in metrics},
            )

    @property
    def metric_data_index(self) -> tuple[int, int, int, int, int]:
        with self.session() as session:
            metric = session.get(_MetricsData, "/")
            if metric is None:
                return 0, 0, 0, 0, 0
            return metric.daily, metric.weekly, metric.monthly, metric.yearly, metric.total

    @property
    def metrics_resp(self) -> dict[str, Any]:
        if not self._c.metrics.enabled:
            return {"success": True, "enabled": False}
        daily, weekly, monthly, yearly, total = self.metrics_data
        now = datetime.now(pytz.timezone(self._c.main.timezone))
        return {
            "success": True,
            "enabled": True,
            "time": now.timestamp(),
            "time_local": now.strftime("%Y-%m-%d %H:%M:%S"),
            "timezone": self._c.main.timezone,
            "daily": daily,
            "weekly": weekly,
            "monthly": monthly,
            "yearly": yearly,
            "total": total,
        }

    def _metrics_refresh(self) -> None:
        if not self._c.metrics.enabled:
            return
        with self._write_lock, self.session() as session:
            meta = session.scalar(select(_MetricsMetaData).limit(1))
            if meta is None:
                meta = _MetricsMetaData(id=0)
                session.add(meta)
            metrics = list(session.scalars(select(_MetricsData)).all())
            now = datetime.now(pytz.timezone(self._c.main.timezone))
            today = f"{now.year}-{now.month}-{now.day}"
            week = f"{now.isocalendar().year}-{now.isocalendar().week}"
            month = f"{now.year}-{now.month}"
            year = str(now.year)
            if meta.today != today:
                meta.today = today
                for item in metrics:
                    item.daily = 0
            if meta.week != week:
                meta.week = week
                for item in metrics:
                    item.weekly = 0
            if meta.month != month:
                meta.month = month
                for item in metrics:
                    item.monthly = 0
            if meta.year != year:
                meta.year = year
                for item in metrics:
                    item.yearly = 0

    _cache: dict[str, tuple[float, bytes]] = {}

    def get_cached_file(self, dirname: str, filename: str) -> BytesIO | None:
        root = Path(u.get_path(dirname, is_dir=True)).resolve()
        filepath = (root / filename).resolve()
        try:
            filepath.relative_to(root)
        except ValueError:
            return None
        try:
            cache_key = f"f-{dirname}/{filename}"
            now = time()
            cached = self._cache.get(cache_key)
            if not self._c.main.debug and cached and now - cached[0] < self._c.main.cache_age:
                return BytesIO(cached[1])
            content = filepath.read_bytes()
            if not self._c.main.debug:
                self._cache[cache_key] = (now, content)
            return BytesIO(content)
        except (FileNotFoundError, IsADirectoryError):
            return None

    def get_cached_text(self, dirname: str, filename: str) -> str | None:
        raw = self.get_cached_file(dirname, filename)
        if raw is None:
            return None
        try:
            return raw.getvalue().decode("utf-8")
        except UnicodeDecodeError:
            return None

    def _clean_cache(self) -> None:
        if self._c.main.debug:
            return
        now = time()
        expired = [
            key for key, (created, _) in self._cache.items()
            if now - created > self._c.main.cache_age
        ]
        for key in expired:
            self._cache.pop(key, None)
