# coding: utf-8
"""Windows 前台窗口状态上报脚本（Alive 本地测试稳健版）。

依赖：
    py -m pip install -r client/requirements-win-device-reliable.txt

启动 Alive 后运行：
    py client/win_device_reliable.py
"""

from __future__ import annotations

import atexit
import ctypes
import os
import signal
import threading
from datetime import datetime
from pathlib import Path
from time import monotonic
from typing import TypeAlias

import requests
from win32gui import GetClassName, GetForegroundWindow, GetWindowText  # type: ignore


def _project_env(name: str) -> str:
    """读取项目根目录 .env，方便与本地 Docker Compose 共用密钥。"""
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


# --- config start -----------------------------------------------------------
# 默认连接本机 Docker 中的 Alive。也可以通过同名环境变量覆盖。
SERVER = os.getenv("ALIVE_SERVER", "http://127.0.0.1:9010")
# 优先读取当前进程环境变量，否则读取 Alive 根目录的 .env。
SECRET = os.getenv("ALIVE_SECRET") or _project_env("ALIVE_SECRET")
DEVICE_ID = os.getenv("ALIVE_CLIENT_DEVICE_ID", "windows-device")
DEVICE_SHOW_NAME = os.getenv("ALIVE_CLIENT_DEVICE_NAME", "Windows 设备")

# 轮询间隔；网络失败时下一个轮询会自动重试。
CHECK_INTERVAL = 3
# 窗口没有变化时仍定时发送心跳，弥补偶发丢包。
HEARTBEAT_INTERVAL = 60
REQUEST_TIMEOUT = 15
# Windows 关闭控制台时留给脚本的时间很短。
SHUTDOWN_TIMEOUT = (1, 3)

BYPASS_SAME_REQUEST = True
SKIPPED_NAMES = {
    "",
    "系统托盘溢出窗口。",
    "新通知",
    "任务切换",
    "快速设置",
    "通知中心",
    "搜索",
    "Flow.Launcher",
}
NOT_USING_NAMES = {"我们喜欢这张图片，因此我们将它与你共享。"}
REVERSE_APP_NAME = True
REPORT_OFFLINE_ON_EMPTY_TITLE = True
NOT_USING_WINDOW_CLASSES = {
    "Progman",
    "WorkerW",
    "Shell_TrayWnd",
    "Shell_SecondaryTrayWnd",
}
# --- config end -------------------------------------------------------------


def _api_url(server: str) -> str:
    value = server.strip().rstrip("/")
    if value.endswith("/api/device/set"):
        return value
    # 只修正用户配置，不依赖服务端旧路由。
    if value.endswith("/device/set"):
        value = value.removesuffix("/device/set")
    return f"{value}/api/device/set"


URL = _api_url(SERVER)
BASE_URL = URL.removesuffix("/api/device/set")
SESSION = requests.Session()
SESSION.trust_env = False
SESSION.headers.update(
    {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": f"Bearer {SECRET}",
        "User-Agent": "Alive-Windows-Reliable/1.0",
    }
)
STOP_EVENT = threading.Event()
LAST_SUCCESSFUL_PAYLOAD: tuple[bool, str] | None = None
LAST_SUCCESSFUL_AT = 0.0
OFFLINE_REPORTED = False
RequestTimeout: TypeAlias = float | tuple[float, float]


def log(message: str) -> None:
    try:
        print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {message}", flush=True)
    except Exception:
        pass


def display_name(title: str) -> str:
    if not REVERSE_APP_NAME:
        return title
    return " - ".join(reversed(title.split(" - ")))


def foreground_window() -> tuple[int, str, str] | None:
    """返回（句柄、标题、窗口类）；None 表示本轮 Windows API 读取失败。"""
    try:
        hwnd = GetForegroundWindow()
        return (hwnd, GetWindowText(hwnd), GetClassName(hwnd)) if hwnd else (0, "", "")
    except Exception as error:
        log(f"读取前台窗口失败，将重试：{error}")
        return None


def check_server() -> bool:
    """启动时确认目标确实是正在运行的 Alive FastAPI 服务。"""
    try:
        response = requests.get(
            f"{BASE_URL}/api/meta",
            headers={
                "Accept": "application/json",
                "User-Agent": "Alive-Windows-Reliable/1.0",
            },
            timeout=5,
        )
        response.raise_for_status()
        result = response.json()
        if result.get("framework") != "FastAPI":
            log(f"目标响应不是 Alive FastAPI：{result}")
            return False
        log(
            f"已连接 Alive {result.get('version_str', 'unknown')}："
            f"{BASE_URL}"
        )
        return True
    except (requests.RequestException, ValueError) as error:
        log(f"无法连接本地 Alive：{error}")
        log("请先在项目目录运行：docker compose up --build")
        return False


def post(
    using: bool,
    status: str,
    timeout: RequestTimeout = REQUEST_TIMEOUT,
) -> bool:
    """仅在 Alive 返回 2xx 且 success=true 后才确认上报成功。"""
    payload = {
        "id": DEVICE_ID,
        "show_name": DEVICE_SHOW_NAME,
        "using": using,
        "status": status if using else "",
    }
    try:
        response = SESSION.post(URL, json=payload, timeout=timeout)
        response.raise_for_status()
        result = response.json()
        if result.get("success") is not True:
            log(f"Alive 拒绝上报：{result}")
            return False
        log(f"POST {response.status_code}：using={using}, status={payload['status']!r}")
        return True
    except requests.HTTPError as error:
        body = error.response.text[:300] if error.response is not None else ""
        log(f"上报被拒绝：{error}；响应：{body}")
        return False
    except (requests.RequestException, ValueError) as error:
        # 不更新 LAST_SUCCESSFUL_*，所以下一轮仍会重试。
        log(f"上报失败，将在下次轮询重试：{error}")
        return False


def update() -> None:
    global LAST_SUCCESSFUL_PAYLOAD, LAST_SUCCESSFUL_AT

    window = foreground_window()
    if window is None:
        return
    _hwnd, title, window_class = window
    no_application = (
        (not title and REPORT_OFFLINE_ON_EMPTY_TITLE)
        or window_class in NOT_USING_WINDOW_CLASSES
    )
    if no_application:
        state = (False, "")
        now = monotonic()
        if state != LAST_SUCCESSFUL_PAYLOAD or now - LAST_SUCCESSFUL_AT >= HEARTBEAT_INTERVAL:
            log(f"前台为桌面/任务栏（类：{window_class or '无'}），正在上报未使用")
            if post(False, ""):
                LAST_SUCCESSFUL_PAYLOAD = state
                LAST_SUCCESSFUL_AT = now
        return
    if title in SKIPPED_NAMES:
        return

    using = title not in NOT_USING_NAMES
    status = display_name(title) if using else ""
    state = (using, status)
    now = monotonic()
    unchanged = state == LAST_SUCCESSFUL_PAYLOAD
    heartbeat_due = now - LAST_SUCCESSFUL_AT >= HEARTBEAT_INTERVAL
    if BYPASS_SAME_REQUEST and unchanged and not heartbeat_due:
        return

    log(f"窗口：{title!r}；上报：using={using}, status={status!r}")
    if post(using, status):
        LAST_SUCCESSFUL_PAYLOAD = state
        LAST_SUCCESSFUL_AT = now


def report_offline() -> None:
    """正常退出时尽力发送未使用状态。"""
    global OFFLINE_REPORTED
    if OFFLINE_REPORTED or len(SECRET) < 6:
        return
    OFFLINE_REPORTED = True
    log("正在上报未使用状态")
    post(False, "", timeout=SHUTDOWN_TIMEOUT)


def request_stop(*_args: object) -> None:
    STOP_EVENT.set()


CTRL_CLOSE_EVENT = 2
CTRL_LOGOFF_EVENT = 5
CTRL_SHUTDOWN_EVENT = 6
CONSOLE_HANDLER = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_uint)


@CONSOLE_HANDLER
def console_close_handler(event: int) -> bool:
    if event in {CTRL_CLOSE_EVENT, CTRL_LOGOFF_EVENT, CTRL_SHUTDOWN_EVENT}:
        try:
            report_offline()
        except Exception:
            pass
    return False


def install_console_close_handler() -> None:
    try:
        ctypes.windll.kernel32.SetConsoleCtrlHandler(console_close_handler, True)
    except Exception as error:
        log(f"无法注册窗口关闭处理器：{error}")


def validate_config() -> None:
    if len(SECRET) < 6:
        raise SystemExit(
            "没有读取到有效的 ALIVE_SECRET。\n"
            "请先复制 .env.example 为 .env，并设置至少 6 位的全局 ALIVE_SECRET。"
        )


def main() -> None:
    validate_config()
    if not check_server():
        raise SystemExit(1)
    log(f"开始监控前台窗口，上报目标：{URL}")
    while not STOP_EVENT.is_set():
        try:
            update()
        except Exception as error:
            log(f"本轮发生未预料异常，将继续运行：{error}")
        STOP_EVENT.wait(CHECK_INTERVAL)


if __name__ == "__main__":
    atexit.register(report_offline)
    install_console_close_handler()
    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)
    try:
        main()
    finally:
        report_offline()
