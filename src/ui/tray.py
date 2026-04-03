from PyQt6.QtWidgets import QMenu, QSystemTrayIcon
from PyQt6.QtGui import QAction
from PyQt6.QtCore import pyqtSignal, QObject

class TrayController(QObject):
    show_panel_signal = pyqtSignal()
    toggle_auto_popup_signal = pyqtSignal(bool)
    clear_history_signal = pyqtSignal()
    prompt_settings_signal = pyqtSignal()
    llm_settings_signal = pyqtSignal()
    open_logs_signal = pyqtSignal()
    
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.tray = QSystemTrayIcon()
        self.auto_popup_action = None
        
        # We will need an icon. For MVP, we can just use a standard style icon if available.
        # A simple fallback icon:
        self.tray.setIcon(self.app.style().standardIcon(
            self.app.style().StandardPixmap.SP_ComputerIcon
        ))
        
        # Setup context menu
        self.menu = QMenu()
        
        show_action = QAction("显示历史面板", self.menu)
        show_action.triggered.connect(self.show_panel_signal.emit)

        self.auto_popup_action = QAction("复制后自动弹出", self.menu)
        self.auto_popup_action.setCheckable(True)
        self.auto_popup_action.toggled.connect(self.toggle_auto_popup_signal.emit)

        prompt_settings_action = QAction("Prompt 设置...", self.menu)
        prompt_settings_action.triggered.connect(self.prompt_settings_signal.emit)

        llm_settings_action = QAction("LLM 设置...", self.menu)
        llm_settings_action.triggered.connect(self.llm_settings_signal.emit)

        open_logs_action = QAction("打开日志目录", self.menu)
        open_logs_action.triggered.connect(self.open_logs_signal.emit)

        clear_action = QAction("清空历史", self.menu)
        clear_action.triggered.connect(self.clear_history_signal.emit)
        
        exit_action = QAction("退出", self.menu)
        exit_action.triggered.connect(self.app.quit)
        
        self.menu.addAction(show_action)
        self.menu.addSeparator()
        self.menu.addAction(self.auto_popup_action)
        self.menu.addAction(prompt_settings_action)
        self.menu.addAction(llm_settings_action)
        self.menu.addAction(open_logs_action)
        self.menu.addAction(clear_action)
        self.menu.addSeparator()
        self.menu.addAction(exit_action)
        
        self.tray.setContextMenu(self.menu)
        self.tray.setToolTip("Win系统剪贴板AI增强")
        
        # Also show on double click
        self.tray.activated.connect(self._on_tray_activated)

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.show_panel_signal.emit()

    def show(self):
        self.tray.show()

    def set_auto_popup_enabled(self, enabled):
        if self.auto_popup_action is None:
            return
        self.auto_popup_action.blockSignals(True)
        self.auto_popup_action.setChecked(enabled)
        self.auto_popup_action.blockSignals(False)
