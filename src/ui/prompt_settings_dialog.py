from PyQt6.QtCore import QEvent, QRect, Qt
from PyQt6.QtGui import QFont, QGuiApplication, QKeyEvent
from PyQt6.QtWidgets import (
    QDialog,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizeGrip,
    QSlider,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from core.app_settings import AppSettings


class CollapsibleSection(QWidget):
    def __init__(self, title: str, expanded: bool = False, parent=None):
        super().__init__(parent)
        self.toggle_button = QToolButton()
        self.toggle_button.setText(title)
        self.toggle_button.setCheckable(True)
        self.toggle_button.setChecked(expanded)
        self.toggle_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.toggle_button.setArrowType(
            Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow
        )
        self.toggle_button.clicked.connect(self._on_toggled)

        self.content = QWidget()
        self.content.setVisible(expanded)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(self.toggle_button)
        layout.addWidget(self.content)

    def _on_toggled(self, checked: bool):
        self.toggle_button.setArrowType(
            Qt.ArrowType.DownArrow if checked else Qt.ArrowType.RightArrow
        )
        self.content.setVisible(checked)


class PromptSettingsDialog(QDialog):
    EDGE_MARGIN = 8

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Prompt 设置")
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMouseTracking(True)
        self.resize(780, 620)
        self.setMinimumSize(620, 460)

        self.slot_name_edits: list[QLineEdit] = []
        self.slot_prompt_edits: list[QTextEdit] = []
        self.slot_sections: list[CollapsibleSection] = []
        self._resize_edge = None
        self._resize_start_pos = None
        self._resize_start_geometry = None
        self._move_drag_offset = None
        self._resize_widgets = set()
        self._move_widgets = set()
        self._settings = AppSettings.settings()
        self._has_saved_geometry = False

        self._build_ui()
        self._register_interaction_widgets()
        self._load_settings()
        self._restore_geometry()

    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)

        self.container = QWidget()
        self.container.setObjectName("container")
        self.container.setMouseTracking(True)
        self.container.setStyleSheet(
            """
            #container {
                background-color: #202327;
                color: #F5F7FA;
                border-radius: 12px;
                border: 1px solid #3A414A;
            }
            QScrollArea {
                border: none;
                background: transparent;
            }
            QGroupBox {
                border: 1px solid #303741;
                border-radius: 8px;
                margin-top: 10px;
                padding-top: 12px;
                background-color: #171B20;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 4px;
                color: #DDE3EA;
            }
            QTextEdit, QLineEdit {
                border: 1px solid #303741;
                background-color: #111418;
                color: #E9EEF5;
                padding: 10px;
                font-size: 13px;
                border-radius: 6px;
            }
            QPushButton {
                background-color: #2B3440;
                color: white;
                padding: 8px 12px;
                border-radius: 6px;
                border: 1px solid #3B4756;
            }
            QPushButton:hover {
                background-color: #354251;
            }
            QToolButton {
                color: #F5F7FA;
                font-weight: 600;
                border: 1px solid #303741;
                border-radius: 8px;
                padding: 10px 12px;
                background-color: #1B2128;
                text-align: left;
            }
            QToolButton:hover {
                background-color: #242C35;
            }
            QLabel {
                border: none;
                background: transparent;
            }
            """
        )

        layout = QVBoxLayout(self.container)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(12)

        self.header_bar = QWidget()
        self.header_bar.setMouseTracking(True)
        header_layout = QHBoxLayout(self.header_bar)
        header_layout.setContentsMargins(0, 0, 0, 0)

        self.title_label = QLabel("Prompt 设置")
        self.title_label.setFont(QFont("Microsoft YaHei UI", 13, QFont.Weight.Bold))

        self.subtitle_label = QLabel("默认 Prompt + 长度约束 + 自定义槽位；拖标题可移动，拖边缘或右下角可缩放")
        self.subtitle_label.setStyleSheet("color: #9FAAB6;")
        self.subtitle_label.setWordWrap(True)

        self.header_text = QWidget()
        self.header_text.setMouseTracking(True)
        header_text_layout = QVBoxLayout(self.header_text)
        header_text_layout.setContentsMargins(0, 0, 0, 0)
        header_text_layout.addWidget(self.title_label)
        header_text_layout.addWidget(self.subtitle_label)

        close_btn = QPushButton("关闭")
        close_btn.setFixedWidth(70)
        close_btn.clicked.connect(self.reject)

        header_layout.addWidget(self.header_text, 1)
        header_layout.addStretch()
        header_layout.addWidget(close_btn)
        layout.addWidget(self.header_bar)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.viewport().setStyleSheet("background: transparent;")

        self.scroll_content = QWidget()
        self.scroll_content.setMouseTracking(True)
        content_layout = QVBoxLayout(self.scroll_content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(14)

        default_group = QGroupBox("默认 Prompt")
        default_layout = QVBoxLayout(default_group)
        default_layout.setSpacing(10)

        default_hint = QLabel(
            "AI 优化默认使用这段 Prompt 作为主规则；模型会根据输入内容自行判断如何优化。"
        )
        default_hint.setWordWrap(True)
        default_hint.setStyleSheet("color: #98A3AF;")
        default_layout.addWidget(default_hint)

        self.default_prompt_edit = QTextEdit()
        self.default_prompt_edit.setPlaceholderText("请输入默认 Prompt")
        self.default_prompt_edit.setMinimumHeight(220)
        default_layout.addWidget(self.default_prompt_edit)

        slider_row = QHBoxLayout()
        slider_row.addWidget(QLabel("输出长度："))

        self.length_slider = QSlider(Qt.Orientation.Horizontal)
        self.length_slider.setRange(100, 500)
        self.length_slider.setSingleStep(50)
        self.length_slider.setPageStep(50)
        self.length_slider.setTickInterval(50)
        self.length_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.length_slider.valueChanged.connect(self._on_slider_changed)
        slider_row.addWidget(self.length_slider, 1)

        self.length_value_label = QLabel("300%")
        self.length_value_label.setMinimumWidth(60)
        slider_row.addWidget(self.length_value_label)
        default_layout.addLayout(slider_row)

        length_hint = QLabel("这是大概约束，不是精确长度控制。")
        length_hint.setWordWrap(True)
        length_hint.setStyleSheet("color: #98A3AF;")
        length_hint.setToolTip(
            "例如 200% 表示优化结果尽量不要超过原内容的 2 倍。\n"
            "该限制是目标范围，不保证逐字精确。"
        )
        default_layout.addWidget(length_hint)
        content_layout.addWidget(default_group)

        slots_group = QGroupBox("自定义 Prompt 槽位")
        slots_layout = QVBoxLayout(slots_group)
        slots_tip = QLabel(
            "槽位默认折叠，按需展开编辑；空槽位不会出现在主面板下拉框。"
        )
        slots_tip.setWordWrap(True)
        slots_tip.setStyleSheet("color: #98A3AF;")
        slots_layout.addWidget(slots_tip)

        for index in range(3):
            section = CollapsibleSection(f"槽位 {index + 1}", expanded=False)
            section_layout = QFormLayout(section.content)
            section_layout.setContentsMargins(4, 2, 4, 4)
            section_layout.setSpacing(10)

            name_edit = QLineEdit()
            name_edit.setPlaceholderText("例如：偏正式 / 会议纪要 / Agent 指令")
            self.slot_name_edits.append(name_edit)
            section_layout.addRow("名称：", name_edit)

            prompt_edit = QTextEdit()
            prompt_edit.setPlaceholderText("输入这条槽位的附加 Prompt")
            prompt_edit.setMinimumHeight(120)
            self.slot_prompt_edits.append(prompt_edit)
            section_layout.addRow("Prompt：", prompt_edit)

            self.slot_sections.append(section)
            slots_layout.addWidget(section)

        content_layout.addWidget(slots_group)
        content_layout.addStretch()

        self.scroll_area.setWidget(self.scroll_content)
        layout.addWidget(self.scroll_area, 1)

        footer_layout = QHBoxLayout()
        footer_layout.setContentsMargins(0, 0, 0, 0)

        footer_hint = QLabel("槽位保持自由定义；主面板只显示有名称且有内容的槽位。")
        footer_hint.setStyleSheet("color: #8FC7FF;")
        footer_layout.addWidget(footer_hint)
        footer_layout.addStretch()

        restore_btn = QPushButton("恢复默认")
        restore_btn.clicked.connect(self._restore_defaults)
        footer_layout.addWidget(restore_btn)

        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        footer_layout.addWidget(cancel_btn)

        save_btn = QPushButton("保存")
        save_btn.clicked.connect(self._save_and_close)
        footer_layout.addWidget(save_btn)

        self.size_grip = QSizeGrip(self.container)
        self.size_grip.setToolTip("拖动这里调整窗口大小")
        footer_layout.addWidget(self.size_grip, 0, Qt.AlignmentFlag.AlignRight)

        layout.addLayout(footer_layout)
        main_layout.addWidget(self.container)

    def _register_interaction_widgets(self):
        self._resize_widgets = {self, self.container}
        self._move_widgets = {
            self.header_bar,
            self.header_text,
            self.title_label,
            self.subtitle_label,
        }
        for widget in self._resize_widgets | self._move_widgets:
            widget.setMouseTracking(True)
            widget.installEventFilter(self)

    def _on_slider_changed(self, value: int):
        rounded = AppSettings._normalize_percent(value)
        if rounded != value:
            self.length_slider.blockSignals(True)
            self.length_slider.setValue(rounded)
            self.length_slider.blockSignals(False)
            value = rounded
        self.length_value_label.setText(f"{value}%")

    def _load_into_form(self, prompt_settings: dict):
        self.default_prompt_edit.setPlainText(prompt_settings["default_prompt"])
        self.length_slider.setValue(prompt_settings["output_length_percent"])
        self._on_slider_changed(prompt_settings["output_length_percent"])

        for index, slot in enumerate(prompt_settings["slots"]):
            self.slot_name_edits[index].setText(slot["name"])
            self.slot_prompt_edits[index].setPlainText(slot["prompt_text"])
            self.slot_sections[index].toggle_button.setChecked(False)
            self.slot_sections[index]._on_toggled(False)

    def _load_settings(self):
        self._load_into_form(AppSettings.load_prompt_settings())

    def _restore_defaults(self):
        self._load_into_form(AppSettings.default_prompt_settings())

    def _save_and_close(self):
        current = AppSettings.load_prompt_settings()
        slots = []
        for index, slot_id in enumerate(AppSettings.SLOT_IDS):
            slots.append(
                {
                    "id": slot_id,
                    "name": self.slot_name_edits[index].text().strip(),
                    "prompt_text": self.slot_prompt_edits[index].toPlainText().strip(),
                }
            )

        AppSettings.save_prompt_settings(
            {
                "default_prompt": self.default_prompt_edit.toPlainText().strip(),
                "output_length_percent": self.length_slider.value(),
                "selected_slot_id": current["selected_slot_id"],
                "slots": slots,
            }
        )
        self.accept()

    def accept(self):
        self._save_geometry()
        super().accept()

    def reject(self):
        self._save_geometry()
        super().reject()

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_Escape:
            self.reject()
            event.accept()
            return
        super().keyPressEvent(event)

    def eventFilter(self, watched, event):
        if watched in self._resize_widgets and self._handle_resize_event(watched, event):
            return True
        if watched in self._move_widgets and self._handle_move_event(event):
            return True
        return super().eventFilter(watched, event)

    def hideEvent(self, event):
        self._save_geometry()
        super().hideEvent(event)

    def showEvent(self, event):
        self._ensure_visible_on_screen()
        super().showEvent(event)

    def _detect_edge(self, pos, rect=None):
        margin = self.EDGE_MARGIN
        rect = rect or self.rect()
        x, y = pos.x(), pos.y()

        on_left = x <= rect.left() + margin
        on_right = x >= rect.right() - margin
        on_top = y <= rect.top() + margin
        on_bottom = y >= rect.bottom() - margin

        if on_top and on_left:
            return "top-left"
        if on_top and on_right:
            return "top-right"
        if on_bottom and on_left:
            return "bottom-left"
        if on_bottom and on_right:
            return "bottom-right"
        if on_left:
            return "left"
        if on_right:
            return "right"
        if on_top:
            return "top"
        if on_bottom:
            return "bottom"
        return None

    def _update_cursor(self, edge):
        cursors = {
            "left": Qt.CursorShape.SizeHorCursor,
            "right": Qt.CursorShape.SizeHorCursor,
            "top": Qt.CursorShape.SizeVerCursor,
            "bottom": Qt.CursorShape.SizeVerCursor,
            "top-left": Qt.CursorShape.SizeFDiagCursor,
            "bottom-right": Qt.CursorShape.SizeFDiagCursor,
            "top-right": Qt.CursorShape.SizeBDiagCursor,
            "bottom-left": Qt.CursorShape.SizeBDiagCursor,
        }
        if edge and edge in cursors:
            self.setCursor(cursors[edge])
        else:
            self.unsetCursor()

    def _do_resize(self, global_pos):
        if self._resize_start_pos is None or self._resize_start_geometry is None:
            return

        delta = global_pos - self._resize_start_pos
        geo = QRect(self._resize_start_geometry)
        min_w, min_h = 620, 460

        edge = self._resize_edge
        if "right" in edge:
            geo.setWidth(max(min_w, self._resize_start_geometry.width() + delta.x()))
        if "bottom" in edge:
            geo.setHeight(max(min_h, self._resize_start_geometry.height() + delta.y()))
        if "left" in edge:
            new_left = min(
                self._resize_start_geometry.right() - min_w,
                self._resize_start_geometry.left() + delta.x(),
            )
            geo.setLeft(new_left)
        if "top" in edge:
            new_top = min(
                self._resize_start_geometry.bottom() - min_h,
                self._resize_start_geometry.top() + delta.y(),
            )
            geo.setTop(new_top)

        self.setGeometry(self._clamp_geometry_to_screen(geo))

    def _handle_resize_event(self, watched, event):
        event_type = event.type()

        if event_type == QEvent.Type.Leave and self._resize_edge is None:
            self.unsetCursor()
            return False

        local_pos = self._map_event_pos_to_self(watched, event)
        if local_pos is None:
            return False

        edge_rect = self.rect() if watched is self else self.container.geometry()
        edge = self._detect_edge(local_pos, edge_rect)

        if event_type in (QEvent.Type.MouseMove, QEvent.Type.HoverMove):
            if self._resize_edge and hasattr(event, "buttons") and event.buttons() & Qt.MouseButton.LeftButton:
                self._do_resize(event.globalPosition().toPoint())
                return True
            self._update_cursor(edge)
            return edge is not None

        if event_type == QEvent.Type.MouseButtonPress:
            if event.button() == Qt.MouseButton.LeftButton and edge:
                self._resize_edge = edge
                self._resize_start_pos = event.globalPosition().toPoint()
                self._resize_start_geometry = QRect(self.geometry())
                return True

        if event_type == QEvent.Type.MouseButtonRelease:
            if event.button() == Qt.MouseButton.LeftButton and self._resize_edge:
                self._resize_edge = None
                self._resize_start_pos = None
                self._resize_start_geometry = None
                self.unsetCursor()
                return True

        return False

    def _handle_move_event(self, event):
        if self._resize_edge:
            return False

        event_type = event.type()
        if event_type == QEvent.Type.MouseButtonPress:
            if event.button() == Qt.MouseButton.LeftButton:
                self._move_drag_offset = (
                    event.globalPosition().toPoint() - self.frameGeometry().topLeft()
                )
                return True

        if event_type == QEvent.Type.MouseMove:
            if self._move_drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
                target = event.globalPosition().toPoint() - self._move_drag_offset
                geo = QRect(target.x(), target.y(), self.width(), self.height())
                self.setGeometry(self._clamp_geometry_to_screen(geo, keep_size=True))
                return True

        if event_type == QEvent.Type.MouseButtonRelease:
            if event.button() == Qt.MouseButton.LeftButton and self._move_drag_offset is not None:
                self._move_drag_offset = None
                return True

        return False

    def _map_event_pos_to_self(self, watched, event):
        if not hasattr(event, "position"):
            return None
        local_point = event.position().toPoint()
        if watched is self:
            return local_point
        return watched.mapTo(self, local_point)

    def _available_geometry(self):
        screen = QGuiApplication.primaryScreen()
        return screen.availableGeometry() if screen else QRect(0, 0, 1280, 720)

    def _clamp_geometry_to_screen(self, geometry: QRect, keep_size: bool = False) -> QRect:
        available = self._available_geometry()
        margin = 12
        max_width = max(self.minimumWidth(), available.width() - margin * 2)
        max_height = max(self.minimumHeight(), available.height() - margin * 2)

        width = geometry.width() if keep_size else min(geometry.width(), max_width)
        height = geometry.height() if keep_size else min(geometry.height(), max_height)
        width = min(width, available.width() - margin * 2)
        height = min(height, available.height() - margin * 2)

        x = max(available.left() + margin, min(geometry.x(), available.right() - width - margin + 1))
        y = max(available.top() + margin, min(geometry.y(), available.bottom() - height - margin + 1))
        return QRect(x, y, width, height)

    def _center_default_geometry(self):
        available = self._available_geometry()
        width = min(780, max(self.minimumWidth(), available.width() - 80))
        height = min(620, max(self.minimumHeight(), available.height() - 80))
        x = available.left() + (available.width() - width) // 2
        y = available.top() + (available.height() - height) // 2
        self.setGeometry(QRect(x, y, width, height))

    def _save_geometry(self):
        geo = self.geometry()
        self._settings.setValue("prompt_dialog/x", geo.x())
        self._settings.setValue("prompt_dialog/y", geo.y())
        self._settings.setValue("prompt_dialog/width", geo.width())
        self._settings.setValue("prompt_dialog/height", geo.height())
        self._settings.sync()

    def _restore_geometry(self):
        x = self._settings.value("prompt_dialog/x", None)
        if x is None:
            self._center_default_geometry()
            self._has_saved_geometry = False
            return

        try:
            x = int(x)
            y = int(self._settings.value("prompt_dialog/y", 100))
            w = int(self._settings.value("prompt_dialog/width", 780))
            h = int(self._settings.value("prompt_dialog/height", 620))
        except (TypeError, ValueError):
            self._center_default_geometry()
            self._has_saved_geometry = False
            return

        self.setGeometry(self._clamp_geometry_to_screen(QRect(x, y, w, h)))
        self._has_saved_geometry = True

    def _ensure_visible_on_screen(self):
        self.setGeometry(self._clamp_geometry_to_screen(self.geometry()))
