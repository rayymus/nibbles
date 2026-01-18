import platform
import re
import subprocess
from pathlib import Path
from typing import Optional, Sequence, Tuple

from PyQt5 import QtCore
from PyQt5.QtMultimedia import QMediaPlayer, QMediaContent

from CONFIG import *


_audio_players: dict[str, QMediaPlayer] = {}
_sound_effects_dir = Path(__file__).resolve().parent / "sound_effects"


def _resolve_audio_path(path: str | Path) -> Path:
    audio_path = Path(path)
    if not audio_path.is_absolute():
        audio_path = Path(__file__).resolve().parent / audio_path
    return audio_path


def _get_or_create_player(path: Path, volume: int) -> QMediaPlayer:
    key = str(path)
    player = _audio_players.get(key)
    if player is None:
        player = QMediaPlayer()
        url = QtCore.QUrl.fromLocalFile(key)
        player.setMedia(QMediaContent(url))
        _audio_players[key] = player
    player.setVolume(volume)
    return player


def preload_sound_effects(directory: Optional[Path] = None, volume: int = 90) -> None:
    audio_dir = Path(directory) if directory is not None else _sound_effects_dir
    if not audio_dir.exists():
        return
    for path in sorted(audio_dir.iterdir()):
        if not path.is_file():
            continue
        if path.suffix.lower() not in {".mp3", ".wav", ".ogg", ".m4a"}:
            continue
        _get_or_create_player(path, volume)


def play_audio(path: str, volume: int = 90) -> None:
    global _audio_players
    audio_path = _resolve_audio_path(path)
    player = _get_or_create_player(audio_path, volume)
    player.stop()
    player.setPosition(0)
    player.play()


def get_open_window_info() -> Sequence[Tuple[Optional[str], Optional[str]]]:
    system = platform.system().lower()
    if system == "windows":
        return _get_open_windows_windows()
    if system == "darwin":
        return _get_open_windows_macos()
    return _get_open_windows_linux()


def _get_open_windows_windows() -> Sequence[Tuple[Optional[str], Optional[str]]]:
    try:
        import ctypes
        from ctypes import wintypes
    except Exception:
        return []

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    windows: list[tuple[Optional[str], Optional[str]]] = []

    EnumWindowsProc = ctypes.WINFUNCTYPE(
        wintypes.BOOL, wintypes.HWND, wintypes.LPARAM
    )

    def enum_callback(hwnd: wintypes.HWND, _lparam: wintypes.LPARAM) -> wintypes.BOOL:
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length == 0:
            return True
        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buffer, length + 1)
        title = buffer.value
        if not title:
            return True

        process_id = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(process_id))
        handle = kernel32.OpenProcess(0x1000, False, process_id.value)
        app_name = None
        if handle:
            try:
                size = wintypes.DWORD(1024)
                exe_buffer = ctypes.create_unicode_buffer(size.value)
                if kernel32.QueryFullProcessImageNameW(
                    handle, 0, exe_buffer, ctypes.byref(size)
                ):
                    app_name = exe_buffer.value.split("\\")[-1]
            finally:
                kernel32.CloseHandle(handle)
        windows.append((app_name, title))
        return True

    user32.EnumWindows(EnumWindowsProc(enum_callback), 0)
    return windows


def _get_open_windows_macos() -> Sequence[Tuple[Optional[str], Optional[str]]]:
    script = (
        'tell application "System Events"\n'
        "set appList to application processes whose visible is true\n"
        'set output to ""\n'
        "repeat with proc in appList\n"
        "set appName to name of proc\n"
        "set windowNames to {}\n"
        "try\n"
        "set windowNames to name of windows of proc\n"
        "end try\n"
        "if (count of windowNames) is 0 then\n"
        'set output to output & appName & "||" & "" & "\\n"\n'
        "else\n"
        "repeat with w in windowNames\n"
        'set output to output & appName & "||" & w & "\\n"\n'
        "end repeat\n"
        "end if\n"
        "end repeat\n"
        "return output\n"
        "end tell"
    )
    result = _run_command(["osascript", "-e", script])
    if not result:
        return []
    windows = []
    for line in result.splitlines():
        if "||" not in line:
            continue
        app_name, title = line.split("||", 1)
        windows.append((app_name or None, title or None))
    return windows


def _get_open_windows_linux() -> Sequence[Tuple[Optional[str], Optional[str]]]:
    root_output = _run_command(["xprop", "-root", "_NET_CLIENT_LIST"])
    if not root_output:
        return []
    ids = re.findall(r"0x[0-9a-fA-F]+", root_output)
    windows = []
    for window_id in ids:
        title = _parse_xprop_value(
            _run_command(["xprop", "-id", window_id, "_NET_WM_NAME"])
        )
        if title is None:
            title = _parse_xprop_value(
                _run_command(["xprop", "-id", window_id, "WM_NAME"])
            )
        app_name = _parse_xprop_value(
            _run_command(["xprop", "-id", window_id, "WM_CLASS"]),
            prefer_last=True,
        )
        windows.append((app_name, title))
    return windows


def _run_command(args: Sequence[str]) -> Optional[str]:
    try:
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def _parse_xprop_value(output: Optional[str], prefer_last: bool = False) -> Optional[str]:
    if not output or "=" not in output:
        return None
    _, value = output.split("=", 1)
    matches = re.findall(r'"([^"]+)"', value)
    if matches:
        return matches[-1] if prefer_last else matches[0]
    cleaned = value.strip().strip('"')
    return cleaned or None


def _macos_accessibility_trusted() -> bool:
    if platform.system().lower() != "darwin":
        return True
    try:
        import Quartz  # type: ignore
    except Exception:
        return True
    try:
        return bool(Quartz.AXIsProcessTrusted())
    except Exception:
        return True
