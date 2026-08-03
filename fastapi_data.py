# coding: utf-8
"""Framework-independent persistence used by the FastAPI application."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta
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
from sqlalchemy import JSON, Boolean, Float, Integer, String, Text, create_engine, delete, func, inspect, or_, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, scoped_session, sessionmaker
from sqlalchemy.pool import StaticPool

import utils as u
from models import ConfigModel, _StatusItemModel

l = getLogger(__name__)
LIMIT = 1024
ACTIVITY_HISTORY_RETENTION_SECONDS = 183 * 24 * 60 * 60


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


class _AppActivityData(Base):
    __tablename__ = "app_activities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_id: Mapped[str] = mapped_column(String(LIMIT), nullable=False, index=True)
    device_type: Mapped[str] = mapped_column(String(24), nullable=False, default="desktop", index=True)
    app_key: Mapped[str] = mapped_column(String(240), nullable=False, index=True)
    app_name: Mapped[str] = mapped_column(String(240), nullable=False, default="")
    app_icon_url: Mapped[str] = mapped_column(String(LIMIT), nullable=False, default="")
    window_title: Mapped[str] = mapped_column(Text, nullable=False, default="")
    started_at: Mapped[float] = mapped_column(Float, nullable=False, default=time, index=True)
    ended_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_seen_at: Mapped[float] = mapped_column(Float, nullable=False, default=time, index=True)


class _AppActivityEventData(Base):
    __tablename__ = "app_activity_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_id: Mapped[str] = mapped_column(String(LIMIT), nullable=False, index=True)
    device_type: Mapped[str] = mapped_column(String(24), nullable=False, default="desktop", index=True)
    app_key: Mapped[str] = mapped_column(String(240), nullable=False, default="", index=True)
    app_name: Mapped[str] = mapped_column(String(240), nullable=False, default="")
    app_icon_url: Mapped[str] = mapped_column(String(LIMIT), nullable=False, default="")
    event_type: Mapped[str] = mapped_column(String(32), nullable=False, default="app_open")
    previous_app_name: Mapped[str] = mapped_column(String(240), nullable=False, default="")
    created_at: Mapped[float] = mapped_column(Float, nullable=False, default=time, index=True)


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
    client_updated_at: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    updated_at: Mapped[float] = mapped_column(Float, nullable=False, default=time)


class _MusicPlayerMetaData(Base):
    __tablename__ = "music_player_meta"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=0)
    player_name: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    player_icon: Mapped[str] = mapped_column(String(64), nullable=False, default="media-player")
    player_icon_url: Mapped[str] = mapped_column(String(1024), nullable=False, default="")
    library_path: Mapped[str] = mapped_column(Text, nullable=False, default="")


class _MusicLibraryTrackData(Base):
    """Metadata index for content-addressed files in the private music library."""

    __tablename__ = "music_library_tracks"

    library_path: Mapped[str] = mapped_column(Text, primary_key=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    artist: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    album: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    updated_at: Mapped[float] = mapped_column(Float, nullable=False, default=time)


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
    is_favorite: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_pinned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


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
        self._migrate_schema()

        with self.session() as session:
            if session.scalar(select(_MainData).limit(1)) is None:
                session.add(_MainData(id=0))
            if self._c.metrics.enabled and session.scalar(select(_MetricsMetaData).limit(1)) is None:
                session.add(_MetricsMetaData(id=0))
            if session.scalar(select(_SiteSettingsData).limit(1)) is None:
                session.add(_SiteSettingsData(id=0))
        self.prune_activity_history()

    def _migrate_schema(self) -> None:
        """Apply small idempotent migrations for databases created by older releases."""
        if self.engine.dialect.name != "sqlite":
            return
        with self.engine.begin() as connection:
            comments_columns = {column["name"] for column in inspect(self.engine).get_columns("comments")}
            missing_comments = {
                "is_favorite": "ALTER TABLE comments ADD COLUMN is_favorite BOOLEAN NOT NULL DEFAULT 0",
                "is_pinned": "ALTER TABLE comments ADD COLUMN is_pinned BOOLEAN NOT NULL DEFAULT 0",
            }
            for name, statement in missing_comments.items():
                if name not in comments_columns:
                    connection.execute(text(statement))
            music_columns = {column["name"] for column in inspect(self.engine).get_columns("music_player_meta")}
            missing_music = {
                "player_icon_url": "ALTER TABLE music_player_meta ADD COLUMN player_icon_url VARCHAR(1024) NOT NULL DEFAULT ''",
            }
            for name, statement in missing_music.items():
                if name not in music_columns:
                    connection.execute(text(statement))
            music_state_columns = {column["name"] for column in inspect(self.engine).get_columns("music_state")}
            if "client_updated_at" not in music_state_columns:
                connection.execute(text("ALTER TABLE music_state ADD COLUMN client_updated_at FLOAT NOT NULL DEFAULT 0"))
            activity_columns = {column["name"] for column in inspect(self.engine).get_columns("app_activities")}
            if "device_type" not in activity_columns:
                connection.execute(text("ALTER TABLE app_activities ADD COLUMN device_type VARCHAR(24) NOT NULL DEFAULT 'desktop'"))
            if "app_icon_url" not in activity_columns:
                connection.execute(text("ALTER TABLE app_activities ADD COLUMN app_icon_url VARCHAR(1024) NOT NULL DEFAULT ''"))
            # App activity records intentionally retain only app identity and time.
            # Remove titles saved by the first preview implementation.
            connection.execute(text("UPDATE app_activities SET window_title = '' WHERE window_title <> ''"))

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
        scheduler.every().day.at("00:05:00", self._c.main.timezone).do(self.prune_activity_history)
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
            status = self._c.status.status_list[status_id]
            if status_id == 0:
                status = status.model_copy(update={"desc": self.online_status_desc})
            elif status_id == 1:
                status = status.model_copy(update={"desc": self.offline_status_desc})
            return True, status
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
    def _normalize_reported_device_fields(fields: dict[str, Any]) -> dict[str, Any]:
        """Canonicalize client model and activity categories without breaking legacy reports."""
        normalized = dict(fields)
        raw_model = str(normalized.get("device_type") or "").strip().casefold()
        model_aliases = {
            "mobile": "phone",
            "computer": "desktop",
            "pc": "desktop",
        }
        model = model_aliases.get(raw_model, raw_model)
        supported_models = {"desktop", "laptop", "phone", "tablet", "watch", "server", "game", "other"}
        if model in supported_models:
            normalized["device_type"] = model

        if normalized.get("activity_reporting") is True:
            raw_activity_type = str(normalized.get("activity_device_type") or model or "desktop").strip().casefold()
            normalized["activity_device_type"] = (
                "mobile" if raw_activity_type in {"mobile", "phone", "tablet", "watch"} else "desktop"
            )
        return normalized

    @staticmethod
    def _default_device_icon(fields: dict[str, Any]) -> str:
        model = str(fields.get("device_type") or "").strip().casefold()
        if model in {"mobile", "phone"}:
            return "phone"
        if model in {"desktop", "laptop", "tablet", "watch", "server", "game", "other"}:
            return model
        return "desktop"

    @staticmethod
    def _serialize_device(
        device: _DeviceStatusData,
        profile: _DeviceProfileData | None = None,
        redact_desktop_window_title: bool = False,
    ) -> dict[str, Any]:
        fields = device.fields or {}
        status = device.status
        device_type = str(fields.get("device_type") or fields.get("activity_device_type") or "").casefold()
        platform = str(fields.get("platform") or fields.get("os") or "").casefold()
        is_desktop = (
            device_type in {"desktop", "laptop", "server"}
            or platform.startswith("windows")
            or "cpu_cores" in fields
            or "processor_count" in fields
        )
        if redact_desktop_window_title and is_desktop:
            app_name = str(
                fields.get("activity_app_name")
                or fields.get("app_name")
                or fields.get("activity_app_id")
                or ""
            ).strip()
            status = app_name or ("正在使用应用" if device.using else "未在使用")
        result = {
            "id": device.id,
            "show_name": profile.display_name if profile and profile.display_name else device.show_name,
            "using": device.using,
            "status": status,
            "fields": fields,
            "last_updated": device.last_updated,
        }
        result["profile"] = {
            "display_name": profile.display_name if profile else "",
            "icon_key": profile.icon_key if profile else Data._default_device_icon(fields),
            "sort_order": profile.sort_order if profile else 0,
            "public": profile.is_public if profile else True,
        }
        return result

    @property
    def _raw_device_list(self) -> dict[str, _DeviceStatusData]:
        with self.session() as session:
            devices = list(session.scalars(select(_DeviceStatusData)).all())
            return {device.id: device for device in devices}

    @property
    def _raw_device_list_dict(self) -> dict[str, dict[str, Any]]:
        devices = self._raw_device_list
        if not devices:
            return {}
        redact_desktop_window_title = self.private_mode
        with self.session() as session:
            profiles = {
                profile.id: profile
                for profile in session.scalars(select(_DeviceProfileData)).all()
            }
            return {
                device_id: self._serialize_device(
                    device,
                    profiles.get(device_id),
                    redact_desktop_window_title,
                )
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
                    item[0],
                ),
            )
        )
        return devices

    @property
    def admin_device_list(self) -> dict[str, dict[str, Any]]:
        redact_desktop_window_title = self.private_mode
        with self.session() as session:
            devices = list(session.scalars(select(_DeviceStatusData)).all())
            profiles = {
                profile.id: profile
                for profile in session.scalars(select(_DeviceProfileData)).all()
            }
            serialized = {
                device.id: self._serialize_device(
                    device,
                    profiles.get(device.id),
                    redact_desktop_window_title,
                )
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
        sort_order: int | None,
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
            "bilibili",
        }
        if not id:
            raise u.APIUnsuccessful(400, "device id cannot be empty")
        if len(display_name) > LIMIT:
            raise u.APIUnsuccessful(400, "display_name is too long")
        if icon_key not in allowed_icons:
            raise u.APIUnsuccessful(400, "unsupported icon_key")
        if sort_order is not None and not -100000 <= sort_order <= 100000:
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
            if sort_order is not None:
                profile.sort_order = sort_order
            profile.is_public = is_public
            now = time()
            self._main(session).last_updated = now
            session.flush()
            return self._serialize_device(device, profile)

    def device_reorder(self, id: str, direction: str) -> dict[str, dict[str, Any]]:
        if not id:
            raise u.APIUnsuccessful(400, "device id cannot be empty")
        if direction not in {"up", "down"}:
            raise u.APIUnsuccessful(400, "direction must be up or down")
        with self._write_lock, self.session() as session:
            devices = list(session.scalars(select(_DeviceStatusData)).all())
            target = session.get(_DeviceStatusData, id)
            if target is None:
                raise u.APIUnsuccessful(404, "Device not found")
            profiles = {}
            for device in devices:
                profile = session.get(_DeviceProfileData, device.id)
                if profile is None:
                    profile = _DeviceProfileData(
                        id=device.id,
                        display_name="",
                        icon_key=self._default_device_icon(device.fields or {}),
                        sort_order=0,
                        is_public=True,
                    )
                    session.add(profile)
                profiles[device.id] = profile
            ordered = sorted(
                devices,
                key=lambda device: (
                    profiles[device.id].sort_order,
                    (profiles[device.id].display_name or device.show_name).casefold(),
                    device.id,
                ),
            )
            # Normalize legacy duplicate order values before moving.  More importantly,
            # move a device relative to the next device with the same visibility.  A
            # hidden device between two public devices must not make the homepage look
            # as though a public-device reorder had no effect.
            for sort_order, device in enumerate(ordered):
                profiles[device.id].sort_order = sort_order
            target = next(device for device in ordered if device.id == id)
            visibility_group = [
                device for device in ordered
                if profiles[device.id].is_public == profiles[target.id].is_public
            ]
            index = next(index for index, device in enumerate(visibility_group) if device.id == id)
            other_index = index - 1 if direction == "up" else index + 1
            if 0 <= other_index < len(visibility_group):
                other = visibility_group[other_index]
                profiles[target.id].sort_order, profiles[other.id].sort_order = (
                    profiles[other.id].sort_order,
                    profiles[target.id].sort_order,
                )
            self._main(session).last_updated = time()
        return self.admin_device_list

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
        normalized_fields = self._normalize_reported_device_fields(fields or {})
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
                    fields=normalized_fields,
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
                if normalized_fields:
                    device.fields = u.deep_merge_dict(device.fields or {}, normalized_fields)
                device.last_updated = time()
            self._record_app_activity(session, id, bool(using), normalized_fields)
            self._prune_activity_history_in_session(session)
            self._main(session).last_updated = time()

    @staticmethod
    def _activity_duration(activity: _AppActivityData, now: float, grace: float) -> float:
        ended_at = activity.ended_at
        if ended_at is None:
            ended_at = min(now, activity.last_seen_at + grace)
        return max(0.0, ended_at - activity.started_at)

    @staticmethod
    def _record_activity_event(
        session: Any,
        device_id: str,
        device_type: str,
        app_key: str,
        app_name: str,
        app_icon_url: str,
        event_type: str,
        previous_app_name: str = "",
    ) -> None:
        session.add(
            _AppActivityEventData(
                device_id=device_id,
                device_type=device_type,
                app_key=app_key[:240],
                app_name=app_name[:240],
                app_icon_url=app_icon_url[:LIMIT],
                event_type=event_type[:32],
                previous_app_name=previous_app_name[:240],
            )
        )

    def _record_app_activity(self, session: Any, device_id: str, using: bool, fields: dict) -> None:
        """Close/open a foreground-app interval when a capable client reports it."""
        if fields.get("activity_reporting") is not True:
            return
        now = time()
        current = session.scalar(
            select(_AppActivityData)
            .where(_AppActivityData.device_id == device_id, _AppActivityData.ended_at.is_(None))
            .order_by(_AppActivityData.started_at.desc())
            .limit(1)
        )
        app_key = str(fields.get("activity_app_id") or "").strip()[:240]
        app_name = str(fields.get("activity_app_name") or "").strip()[:240]
        app_icon_url = str(fields.get("activity_app_icon_url") or fields.get("app_icon_url") or "").strip()[:LIMIT]
        device_type = self._activity_category(
            str(fields.get("activity_device_type") or fields.get("device_type") or "desktop").strip().lower()
        )
        reported_event = str(fields.get("activity_event") or "").strip().lower()[:32]

        if not using or not app_key:
            if current is not None:
                current.ended_at = now
                current.last_seen_at = now
                self._record_activity_event(
                    session, device_id, device_type, current.app_key, current.app_name,
                    current.app_icon_url, reported_event or "inactive",
                )
            return

        if current is not None and current.app_key == app_key:
            current.last_seen_at = now
            current.device_type = device_type
            if app_name:
                current.app_name = app_name
            if app_icon_url:
                current.app_icon_url = app_icon_url
            if reported_event:
                self._record_activity_event(
                    session, device_id, device_type, current.app_key, current.app_name,
                    current.app_icon_url, reported_event,
                )
            return

        if current is not None:
            current.ended_at = now
            current.last_seen_at = now
            self._record_activity_event(
                session, device_id, device_type, app_key, app_name or app_key, app_icon_url,
                reported_event or "app_switch", current.app_name,
            )
        else:
            self._record_activity_event(
                session, device_id, device_type, app_key, app_name or app_key, app_icon_url,
                reported_event or "app_open",
            )
        session.add(
            _AppActivityData(
                device_id=device_id,
                device_type=device_type,
                app_key=app_key,
                app_name=app_name or app_key,
                app_icon_url=app_icon_url,
                window_title="",
                started_at=now,
                last_seen_at=now,
            )
        )

    @staticmethod
    def _activity_category(device_type: str) -> str:
        return "mobile" if device_type in {"mobile", "phone", "tablet", "watch"} else "desktop"

    @staticmethod
    def _prune_activity_history_in_session(session: Any, now: float | None = None) -> int:
        cutoff = (now if now is not None else time()) - ACTIVITY_HISTORY_RETENTION_SECONDS
        removed = session.execute(delete(_AppActivityData).where(_AppActivityData.last_seen_at < cutoff)).rowcount or 0
        removed += session.execute(delete(_AppActivityEventData).where(_AppActivityEventData.created_at < cutoff)).rowcount or 0
        return int(removed)

    def prune_activity_history(self) -> int:
        """Keep application usage and event history to a rolling six months."""
        with self._write_lock, self.session() as session:
            return self._prune_activity_history_in_session(session)

    def activity_snapshot(
        self,
        timeout: float = 60,
        period: str = "daily",
        selected_date: str | None = None,
    ) -> dict[str, Any]:
        """Return period-aware application statistics without mixing mobile and desktop."""
        period = period if period in {"daily", "weekly", "monthly"} else "daily"
        timezone = pytz.timezone(self._c.main.timezone)
        local_now = datetime.now(timezone)
        try:
            selected = timezone.localize(datetime.strptime(selected_date or "", "%Y-%m-%d"))
        except ValueError:
            selected = local_now
        selected = min(selected, local_now)
        if period == "daily":
            range_start_local = selected.replace(hour=0, minute=0, second=0, microsecond=0)
            range_end_local = range_start_local + timedelta(days=1)
            labels = [f"{hour:02d}" for hour in range(24)]
        elif period == "weekly":
            range_start_local = (selected - timedelta(days=selected.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
            range_end_local = range_start_local + timedelta(days=7)
            labels = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
        else:
            range_start_local = selected.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            next_month = (range_start_local.replace(day=28) + timedelta(days=4)).replace(day=1)
            range_end_local = next_month
            labels = [str(day) for day in range(1, (range_end_local - range_start_local).days + 1)]
        range_start = range_start_local.timestamp()
        range_end = min(range_end_local.timestamp(), time())
        grace = max(15.0, float(timeout) if timeout > 0 else 75.0)
        now = time()

        with self.session() as session:
            rows = session.scalars(
                select(_AppActivityData)
                .where(_AppActivityData.started_at < range_end, _AppActivityData.last_seen_at >= range_start)
                .order_by(_AppActivityData.last_seen_at.desc(), _AppActivityData.id.desc())
            ).all()
            event_rows = session.scalars(
                select(_AppActivityEventData)
                .where(_AppActivityEventData.created_at >= range_start, _AppActivityEventData.created_at < range_end)
                .order_by(_AppActivityEventData.created_at.desc(), _AppActivityEventData.id.desc())
                .limit(300)
            ).all()
            count_rows = session.execute(
                select(_AppActivityData.device_type, func.count()).group_by(_AppActivityData.device_type)
            ).all()

        categories: dict[str, dict[str, Any]] = {
            category: {
                "period_seconds": 0, "today_seconds": 0, "recent": [], "top_apps": [],
                "total_records": 0, "time_series": [{"label": label, "seconds": 0} for label in labels],
            }
            for category in ("mobile", "desktop")
        }
        app_totals: dict[str, dict[str, dict[str, Any]]] = {"mobile": {}, "desktop": {}}
        latest_events: dict[str, dict[str, dict[str, Any]]] = {"mobile": {}, "desktop": {}}
        for device_type, count in count_rows:
            categories[self._activity_category(device_type)]["total_records"] += int(count)
        for event in event_rows:
            category = self._activity_category(event.device_type)
            if not event.app_key:
                continue
            if event.app_key not in latest_events[category]:
                latest_events[category][event.app_key] = {
                    "event_type": event.event_type,
                    "app_name": event.app_name or event.app_key,
                    "previous_app_name": event.previous_app_name,
                    "timestamp": event.created_at,
                }

        for row in rows:
            category = self._activity_category(row.device_type)
            effective_end = row.ended_at if row.ended_at is not None else min(now, row.last_seen_at + grace)
            clipped_start, clipped_end = max(range_start, row.started_at), min(range_end, effective_end)
            overlap = max(0.0, clipped_end - clipped_start)
            if overlap <= 0:
                continue
            active = row.ended_at is None and row.last_seen_at + grace >= now
            record = {
                "id": row.id,
                "device_id": row.device_id,
                "device_type": category,
                "app_name": row.app_name or row.app_key,
                "app_icon_url": row.app_icon_url or "",
                "started_at": row.started_at,
                "ended_at": effective_end,
                "duration_seconds": round(overlap),
                "active": active,
            }
            categories[category]["period_seconds"] += overlap
            item = app_totals[category].setdefault(
                row.app_key,
                {
                    "app_key": row.app_key,
                    "app_name": record["app_name"],
                    "app_icon_url": record["app_icon_url"],
                    "duration_seconds": 0.0,
                    "last_seen_at": effective_end,
                    "active": active,
                },
            )
            item["duration_seconds"] += overlap
            item["last_seen_at"] = max(float(item["last_seen_at"]), effective_end)
            item["active"] = bool(item["active"] or active)
            if record["app_icon_url"]:
                item["app_icon_url"] = record["app_icon_url"]

            cursor = clipped_start
            while cursor < clipped_end:
                cursor_local = datetime.fromtimestamp(cursor, timezone)
                if period == "daily":
                    index = cursor_local.hour
                    next_bucket = (cursor_local.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)).timestamp()
                elif period == "weekly":
                    index = cursor_local.weekday()
                    next_bucket = (cursor_local.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)).timestamp()
                else:
                    index = cursor_local.day - 1
                    next_bucket = (cursor_local.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)).timestamp()
                piece_end = min(clipped_end, next_bucket)
                categories[category]["time_series"][index]["seconds"] += max(0.0, piece_end - cursor)
                cursor = piece_end

        for category, data in categories.items():
            data["period_seconds"] = round(data["period_seconds"])
            data["today_seconds"] = data["period_seconds"]
            data["time_series"] = [{**item, "seconds": round(item["seconds"])} for item in data["time_series"]]
            apps = list(app_totals[category].values())
            data["top_apps"] = [
                {**item, "duration_seconds": round(item["duration_seconds"])}
                for item in sorted(apps, key=lambda item: item["duration_seconds"], reverse=True)[:12]
            ]
            data["recent"] = [
                {
                    **item,
                    "duration_seconds": round(item["duration_seconds"]),
                    "latest_event": latest_events[category].get(item["app_key"]),
                }
                for item in sorted(apps, key=lambda item: item["last_seen_at"], reverse=True)[:50]
            ]
        return {
            "period": period,
            "range_start": range_start,
            "range_end": range_end,
            "date_label": range_start_local.strftime("%Y 年 %m 月 %d 日") if period == "daily" else range_start_local.strftime("%Y 年 %m 月") if period == "monthly" else f"{range_start_local.strftime('%m/%d')} – {(range_start_local + timedelta(days=6)).strftime('%m/%d')}",
            "today_seconds": sum(category["period_seconds"] for category in categories.values()),
            "total_records": sum(category["total_records"] for category in categories.values()),
            "categories": categories,
        }

    def activity_events(self, category: str, app_key: str, selected_date: str | None = None) -> dict[str, Any]:
        """Return one application's detailed events for the selected local day."""
        category = "mobile" if category == "mobile" else "desktop"
        app_key = str(app_key or "").strip()[:240]
        if not app_key:
            return {"date_label": "", "events": []}
        timezone = pytz.timezone(self._c.main.timezone)
        local_now = datetime.now(timezone)
        try:
            selected = timezone.localize(datetime.strptime(selected_date or "", "%Y-%m-%d"))
        except ValueError:
            selected = local_now
        selected = min(selected, local_now)
        range_start_local = selected.replace(hour=0, minute=0, second=0, microsecond=0)
        range_start = range_start_local.timestamp()
        range_end = min((range_start_local + timedelta(days=1)).timestamp(), time())
        with self.session() as session:
            rows = session.scalars(
                select(_AppActivityEventData)
                .where(
                    _AppActivityEventData.app_key == app_key,
                    _AppActivityEventData.created_at >= range_start,
                    _AppActivityEventData.created_at < range_end,
                )
                .order_by(_AppActivityEventData.created_at.desc(), _AppActivityEventData.id.desc())
            ).all()
        return {
            "date_label": range_start_local.strftime("%Y 年 %m 月 %d 日"),
            "events": [
                {
                    "event_type": row.event_type,
                    "app_name": row.app_name or row.app_key,
                    "previous_app_name": row.previous_app_name,
                    "timestamp": row.created_at,
                }
                for row in rows
                if self._activity_category(row.device_type) == category
            ],
        }

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
        if key not in {
            "danmaku_enabled",
            "health_section_enabled",
            "activity_event_details_enabled",
            "comment_display_limit",
            "danmaku_replay_count",
            "danmaku_replay_interval",
            "page_name",
            "page_title",
            "card_style",
            "social_links",
            "music_library",
            "online_status_desc",
            "offline_status_desc",
        }:
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
    def health_section_enabled(self) -> bool:
        return self.runtime_setting("health_section_enabled", "true") == "true"

    @property
    def activity_event_details_enabled(self) -> bool:
        return self.runtime_setting("activity_event_details_enabled", "true") == "true"

    def _runtime_int(self, key: str, default: int, minimum: int, maximum: int) -> int:
        try:
            value = int(self.runtime_setting(key, str(default)))
        except (TypeError, ValueError):
            return default
        return max(minimum, min(maximum, value))

    @property
    def comment_display_limit(self) -> int:
        return self._runtime_int("comment_display_limit", 8, 1, 50)

    @property
    def danmaku_replay_count(self) -> int:
        return self._runtime_int("danmaku_replay_count", 1, 1, 10)

    @property
    def danmaku_replay_interval(self) -> int:
        return self._runtime_int("danmaku_replay_interval", 30, 3, 300)

    @property
    def page_name(self) -> str:
        return self.runtime_setting("page_name", self._c.page.name)

    @property
    def page_title(self) -> str:
        return self.runtime_setting("page_title", self._c.page.title)

    @property
    def card_style(self) -> str:
        """Keep existing installations on the established glass-card presentation."""
        value = self.runtime_setting("card_style", "glass")
        return value if value in {"glass", "solid"} else "glass"

    @property
    def music_library(self) -> str:
        return self.runtime_setting("music_library", self._c.main.music_library)

    @property
    def online_status_desc(self) -> str:
        return self.runtime_setting("online_status_desc", self._c.status.status_list[0].desc)

    @property
    def offline_status_desc(self) -> str:
        return self.runtime_setting("offline_status_desc", self._c.status.status_list[1].desc)

    @property
    def status_list(self) -> list[_StatusItemModel]:
        return [self.get_status(index)[1] for index in range(len(self._c.status.status_list))]

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
            "favorite": bool(comment.is_favorite),
            "pinned": bool(comment.is_pinned),
        }

    def comment_list(self, limit: int = 50) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 300))
        with self.session() as session:
            pinned = list(session.scalars(
                select(_CommentData).where(_CommentData.is_pinned.is_(True))
                .order_by(_CommentData.id.desc()).limit(limit)
            ).all())
            if len(pinned) < limit:
                recent = session.scalars(
                    select(_CommentData).where(_CommentData.is_pinned.is_(False))
                    .order_by(_CommentData.id.desc()).limit(limit - len(pinned))
                ).all()
            else:
                recent = []
        return [self._serialize_comment(comment) for comment in [*pinned, *recent]]

    def comment_admin_list(self) -> list[dict[str, Any]]:
        with self.session() as session:
            comments = list(session.scalars(
                select(_CommentData).order_by(
                    _CommentData.is_pinned.desc(), _CommentData.is_favorite.desc(), _CommentData.id.desc()
                ).limit(300)
            ).all())
        return [self._serialize_comment(comment) for comment in comments]

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

    def comment_update(self, comment_id: int, favorite: bool, pinned: bool) -> dict[str, Any] | None:
        with self._write_lock, self.session() as session:
            comment = session.get(_CommentData, comment_id)
            if comment is None:
                return None
            comment.is_favorite = favorite
            comment.is_pinned = pinned
            session.flush()
            return self._serialize_comment(comment)

    def comment_clear(self) -> int:
        with self._write_lock, self.session() as session:
            comments = list(session.scalars(select(_CommentData)).all())
            for comment in comments:
                session.delete(comment)
            return len(comments)

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
                "player_icon_url": "",
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
            "player_icon_url": meta.player_icon_url if meta else "",
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
        client_updated_at = float(payload.get("client_updated_at") or 0)
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
            elif (
                client_updated_at > 0
                and state.client_updated_at > 0
                and client_updated_at < state.client_updated_at
            ):
                # Concurrent requests can arrive out of order after a rapid
                # track change. Keep the newer client observation visible.
                return self._serialize_music(state)
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
            state.client_updated_at = client_updated_at
            state.updated_at = now
            meta.player_name = payload.get("player_name", "")
            meta.player_icon = payload.get("player_icon", "media-player")
            meta.player_icon_url = payload.get("player_icon_url", "")
            meta.library_path = payload.get("library_path", "")
            if meta.library_path:
                track = session.get(_MusicLibraryTrackData, meta.library_path)
                if track is None:
                    track = _MusicLibraryTrackData(library_path=meta.library_path)
                    session.add(track)
                track.title = state.title
                track.artist = state.artist
                track.album = state.album
                track.updated_at = now
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

    @property
    def active_music_library_path(self) -> str:
        """The private storage path of the current local-upload track, if any."""
        with self.session() as session:
            state = session.get(_MusicStateData, 0)
            meta = session.get(_MusicPlayerMetaData, 0)
            source = session.get(_MusicSourceData, 0)
            if (
                state is None
                or not state.title
                or meta is None
                or not meta.library_path
                or (source is not None and source.source_mode != "local-upload")
                or (
                    self._c.main.music_session_timeout > 0
                    and time() - state.updated_at > self._c.main.music_session_timeout
                )
            ):
                return ""
            return meta.library_path

    def music_library_metadata(self, paths: list[str]) -> dict[str, dict[str, Any]]:
        """Look up catalogued tags without touching or scanning audio files."""
        if not paths:
            return {}
        with self.session() as session:
            rows = session.scalars(
                select(_MusicLibraryTrackData).where(_MusicLibraryTrackData.library_path.in_(paths))
            ).all()
            return {
                row.library_path: {
                    "title": row.title,
                    "artist": row.artist,
                    "album": row.album,
                    "updated_at": row.updated_at,
                }
                for row in rows
            }

    def search_music_library_metadata(self, query: str, limit: int = 1000) -> dict[str, dict[str, Any]]:
        """Search the persisted song index without reading audio files or tags."""
        needle = query.strip().casefold()
        if not needle:
            return {}
        pattern = f"%{needle}%"
        with self.session() as session:
            rows = session.scalars(
                select(_MusicLibraryTrackData)
                .where(or_(
                    func.lower(_MusicLibraryTrackData.title).like(pattern),
                    func.lower(_MusicLibraryTrackData.artist).like(pattern),
                    func.lower(_MusicLibraryTrackData.album).like(pattern),
                ))
                .order_by(_MusicLibraryTrackData.updated_at.desc())
                .limit(limit)
            ).all()
            return {
                row.library_path: {
                    "title": row.title,
                    "artist": row.artist,
                    "album": row.album,
                    "updated_at": row.updated_at,
                }
                for row in rows
            }

    def remove_music_library_metadata(self, paths: list[str]) -> None:
        if not paths:
            return
        with self._write_lock, self.session() as session:
            for path in paths:
                row = session.get(_MusicLibraryTrackData, path)
                if row is not None:
                    session.delete(row)

    def music_audio_path(self, token: str) -> Path | None:
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
