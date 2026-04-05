import os
import sys

import keyboard
from PyQt6.QtCore import QObject, QTimer, pyqtSignal
from PyQt6.QtWidgets import QDialog
from PyQt6.QtWidgets import QApplication

from core.app_settings import AppSettings
from core.ai_bridge import AIBridge
from core.clipboard_mgr import ClipboardManager
from ui.panel import HistoryPanel
from ui.prompt_settings_dialog import PromptSettingsDialog
from ui.settings_dialog import LLMSettingsDialog
from ui.tray import TrayController


class HotkeyBridge(QObject):
    show_panel_signal = pyqtSignal()


def setup_global_hotkeys(panel):
    """Setup global hotkeys using a Qt signal bridge for thread safety."""
    bridge = HotkeyBridge()
    bridge.show_panel_signal.connect(panel.show_panel)
    keyboard.add_hotkey("ctrl+shift+v", bridge.show_panel_signal.emit)
    return bridge


def open_llm_settings(first_launch=False, tray=None):
    dialog = LLMSettingsDialog(first_launch=first_launch)
    result = dialog.exec()
    if first_launch and tray is not None:
        settings = AppSettings.settings()
        api_key = settings.value("llm/api_key", "", type=str).strip()
        if result == int(QDialog.DialogCode.Accepted) and api_key:
            tray.show_message(
                "配置已保存",
                "API Key 已保存，程序会继续在系统托盘后台运行。双击托盘图标即可打开主面板。",
            )
        else:
            tray.show_message(
                "程序正在后台运行",
                "当前未完成 API Key 配置。程序仍会停留在系统托盘中，稍后可从托盘菜单再次打开 LLM 设置。",
            )


def open_prompt_settings(panel=None):
    dialog = PromptSettingsDialog()
    if dialog.exec() and panel is not None:
        panel.reload_prompt_options()


def open_log_dir():
    log_dir = AIBridge.ensure_log_dir()
    os.startfile(log_dir)


def migrate_env_api_key(settings):
    """如果 QSettings 里还没有 API Key 但环境变量有，自动迁移过来。"""
    existing = settings.value("llm/api_key", "", type=str)
    if not existing:
        env_key = os.environ.get("SILICONFLOW_API_KEY", "")
        if env_key:
            settings.setValue("llm/api_key", env_key)
            settings.sync()


def migrate_llm_defaults(settings):
    """把过旧的 LLM 默认值迁移到更适合当前模型的配置。"""
    timeout = int(settings.value("llm/timeout", 0) or 0)
    max_tokens = int(settings.value("llm/max_tokens", 0) or 0)
    model = settings.value("llm/model", "", type=str).strip()
    has_enable_thinking = settings.contains("llm/enable_thinking")
    has_max_tokens_enabled = settings.contains("llm/max_tokens_enabled")

    changed = False
    if timeout < 60:
        settings.setValue("llm/timeout", 60)
        changed = True
    if max_tokens < 1200:
        settings.setValue("llm/max_tokens", 1200)
        changed = True
    if not model or model == "Qwen/Qwen2.5-7B-Instruct":
        settings.setValue("llm/model", "Pro/zai-org/GLM-5")
        changed = True
    if not has_enable_thinking:
        settings.setValue("llm/enable_thinking", False)
        changed = True
    if not has_max_tokens_enabled:
        settings.setValue("llm/max_tokens_enabled", False)
        changed = True

    if changed:
        settings.sync()


def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    settings = AppSettings.settings()
    AppSettings.ensure_defaults()

    # 自动迁移环境变量中的 API Key
    migrate_env_api_key(settings)
    migrate_llm_defaults(settings)

    # 1. Setup clipboard manager
    clip_mgr = ClipboardManager(app.clipboard())

    # 2. Setup Panel
    panel = HistoryPanel(clip_mgr)

    # 3. Setup Tray
    tray = TrayController(app)
    tray.show()

    # Connect signals
    tray.show_panel_signal.connect(panel.show_panel)
    tray.clear_history_signal.connect(panel.prompt_clear_history)
    tray.prompt_settings_signal.connect(lambda: open_prompt_settings(panel))
    tray.llm_settings_signal.connect(open_llm_settings)
    tray.open_logs_signal.connect(open_log_dir)

    auto_popup_enabled = settings.value("auto_popup_enabled", False, type=bool)
    tray.set_auto_popup_enabled(auto_popup_enabled)
    panel.set_auto_popup_enabled(auto_popup_enabled)

    def on_auto_popup_changed(enabled):
        settings.setValue("auto_popup_enabled", enabled)
        panel.set_auto_popup_enabled(enabled)

    tray.toggle_auto_popup_signal.connect(on_auto_popup_changed)

    # 4. Setup Global Hotkey
    hotkey_bridge = setup_global_hotkeys(panel)
    app.aboutToQuit.connect(keyboard.unhook_all_hotkeys)

    print("Win Clipboard AI Enhancer started. Press Ctrl+Shift+V to show history.")

    # 首次启动：如果没有配置 API Key，自动弹出设置对话框
    api_key = settings.value("llm/api_key", "", type=str)
    if not api_key:
        QTimer.singleShot(500, lambda: open_llm_settings(first_launch=True, tray=tray))

    # Keep references to avoid garbage-collection
    panel.hotkey_bridge = hotkey_bridge
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
