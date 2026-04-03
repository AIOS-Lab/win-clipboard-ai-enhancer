import os
import sys
from pathlib import Path

from PyQt6.QtCore import QStandardPaths


APP_FOLDER_NAME = "WinClipboardAIEnhancer"
PORTABLE_MARKER_FILE = "portable_mode.flag"
PORTABLE_DATA_DIRNAME = "data"


def get_app_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def is_portable_mode() -> bool:
    if os.environ.get("WIN_CLIPBOARD_AI_PORTABLE", "").strip() == "1":
        return True
    return (get_app_root() / PORTABLE_MARKER_FILE).exists()


def get_data_root() -> Path:
    if is_portable_mode():
        path = get_app_root() / PORTABLE_DATA_DIRNAME
        path.mkdir(parents=True, exist_ok=True)
        return path

    base_dir = QStandardPaths.writableLocation(
        QStandardPaths.StandardLocation.AppDataLocation
    )
    if base_dir:
        path = Path(base_dir)
        if path.name.lower() != APP_FOLDER_NAME.lower():
            path = path / APP_FOLDER_NAME
        path.mkdir(parents=True, exist_ok=True)
        return path

    fallback = Path.home() / ".win_clipboard_ai_enhancer"
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


def get_settings_path() -> Path:
    return get_data_root() / "settings.ini"
