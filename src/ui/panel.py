from datetime import datetime

import keyboard
from PyQt6.QtCore import QEvent, QRect, QThread, QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QCursor, QFont, QGuiApplication, QKeyEvent, QPixmap
from PyQt6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSizeGrip,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from core.app_settings import AppSettings
from core.ai_bridge import AIBridge


class AIRewriteThread(QThread):
    finished_signal = pyqtSignal(str)

    def __init__(self, ai_bridge, content, prompt_slot_id=None):
        super().__init__()
        self.ai = ai_bridge
        self.content = content
        self.prompt_slot_id = prompt_slot_id

    def run(self):
        new_content = self.ai.rewrite_text(
            self.content,
            prompt_slot_id=self.prompt_slot_id,
        )
        self.finished_signal.emit(new_content)


class HistoryPanel(QWidget):
    EDGE_MARGIN = 8  # 边缘拖拽感应宽度（px）

    def __init__(self, clipboard_mgr):
        super().__init__()
        self.clipboard_mgr = clipboard_mgr
        self.ai = AIBridge()
        self.auto_popup_enabled = False
        self._resize_edge = None  # 当前正在拖拽的边缘方向
        self._resize_start_pos = None
        self._resize_start_geometry = None
        self._move_drag_offset = None
        self._pending_rewrite_source_id = None
        self.rewrite_thread = None
        self._settings = AppSettings.settings()
        self._has_saved_geometry = False
        self._resize_widgets = set()
        self._move_widgets = set()
        self._updating_prompt_combo = False
        self.init_ui()

        self.clipboard_mgr.set_callback(self.on_history_event)
        self.load_history()

        # 恢复窗口几何
        self._restore_geometry()

    def init_ui(self):
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMouseTracking(True)
        self.resize(760, 560)

        main_layout = QVBoxLayout()
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
            QListWidget {
                border: 1px solid #303741;
                background-color: #16191D;
                color: #DDE3EA;
                font-size: 13px;
                padding: 4px;
                border-radius: 0px;
            }
            QListWidget::item {
                border-bottom: 1px solid #262C33;
                padding: 10px;
            }
            QListWidget::item:selected {
                background-color: #245D8C;
                color: white;
            }
            QTextEdit {
                border: 1px solid #303741;
                background-color: #111418;
                color: #E9EEF5;
                padding: 10px;
                font-size: 13px;
                border-radius: 0px;
            }
            QSplitter::handle {
                background-color: #3A414A;
                height: 12px;
                margin: 2px 16px;
                border-radius: 2px;
            }
            QSplitter::handle:hover {
                background-color: #5A9FD4;
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
            QPushButton:disabled {
                color: #8C96A3;
                background-color: #252B33;
                border-color: #2B323B;
            }
            QPushButton[accent="true"] {
                background-color: #0E639C;
                border-color: #167DC2;
            }
            QPushButton[accent="true"]:hover {
                background-color: #1177BB;
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
        self.header_bar.setObjectName("headerBar")
        self.header_bar.setMouseTracking(True)
        header_layout = QHBoxLayout(self.header_bar)
        header_layout.setContentsMargins(0, 0, 0, 0)

        self.title_label = QLabel("Win系统剪贴板AI增强")
        self.title_label.setFont(QFont("Microsoft YaHei UI", 13, QFont.Weight.Bold))

        self.subtitle_label = QLabel("双击历史项可直接粘贴，快捷键 Ctrl+Shift+V；中间横条调上下比例，右下角调窗口大小")
        self.subtitle_label.setStyleSheet("color: #9FAAB6;")

        self.header_text = QWidget()
        self.header_text.setMouseTracking(True)
        header_text_layout = QVBoxLayout(self.header_text)
        header_text_layout.setContentsMargins(0, 0, 0, 0)
        header_text_layout.addWidget(self.title_label)
        header_text_layout.addWidget(self.subtitle_label)

        close_btn = QPushButton("关闭")
        close_btn.setFixedWidth(70)
        close_btn.clicked.connect(self.hide)

        header_layout.addWidget(self.header_text)
        header_layout.addStretch()
        header_layout.addWidget(close_btn)
        layout.addWidget(self.header_bar)

        self.splitter = QSplitter(Qt.Orientation.Vertical)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setHandleWidth(12)
        self.splitter.setOpaqueResize(True)

        self.list_widget = QListWidget()
        self.list_widget.setWordWrap(True)
        self.list_widget.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list_widget.currentItemChanged.connect(self.on_current_item_changed)
        self.list_widget.itemDoubleClicked.connect(self.on_item_double_clicked)
        self.list_widget.setMinimumHeight(80)
        self.splitter.addWidget(self.list_widget)

        detail_widget = QWidget()
        detail_layout = QVBoxLayout(detail_widget)
        detail_layout.setContentsMargins(0, 0, 0, 0)
        detail_layout.setSpacing(10)

        self.meta_label = QLabel("当前还没有捕获到内容。")
        self.meta_label.setWordWrap(True)
        self.meta_label.setStyleSheet(
            "color: #AAB4C0; border: none; background: transparent;"
        )
        detail_layout.addWidget(self.meta_label)

        self.preview_stack = QStackedWidget()

        self.empty_state = QLabel("复制一段文本或一张图片后，这里会显示详细预览。")
        self.empty_state.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_state.setStyleSheet(
            "color: #7E8A98; border: 1px dashed #3A414A; background: #14181D; padding: 24px;"
        )
        self.empty_state.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self.text_preview = QTextEdit()
        self.text_preview.setReadOnly(True)
        self.text_preview.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self.image_preview = QLabel()
        self.image_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_preview.setMinimumHeight(120)
        self.image_preview.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Ignored)
        self.image_preview.setStyleSheet(
            "border: 1px solid #303741; background: #111418; padding: 12px;"
        )

        self.preview_stack.addWidget(self.empty_state)
        self.preview_stack.addWidget(self.text_preview)
        self.preview_stack.addWidget(self.image_preview)
        self.preview_stack.setMinimumHeight(120)
        self.preview_stack.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        detail_layout.addWidget(self.preview_stack)

        action_layout = QHBoxLayout()

        self.copy_btn = QPushButton("复制")
        self.copy_btn.clicked.connect(self.copy_selected_item)
        action_layout.addWidget(self.copy_btn)

        self.paste_btn = QPushButton("复制并粘贴")
        self.paste_btn.clicked.connect(self.paste_selected_item)
        action_layout.addWidget(self.paste_btn)

        self.ai_btn = QPushButton("AI 优化")
        self.ai_btn.setProperty("accent", True)
        self.ai_btn.clicked.connect(self.on_ai_rewrite)
        action_layout.addWidget(self.ai_btn)

        self.prompt_slot_combo = QComboBox()
        self.prompt_slot_combo.setMinimumWidth(128)
        self.prompt_slot_combo.setToolTip(
            "选择一个附加 Prompt 槽位；默认不选。当前选择会自动记住。"
        )
        self.prompt_slot_combo.currentIndexChanged.connect(self.on_prompt_slot_changed)
        action_layout.addWidget(self.prompt_slot_combo)

        self.save_btn = QPushButton("另存图片")
        self.save_btn.clicked.connect(self.save_selected_image)
        action_layout.addWidget(self.save_btn)

        action_layout.addStretch()

        self.clear_btn = QPushButton("清空历史")
        self.clear_btn.clicked.connect(self.prompt_clear_history)
        action_layout.addWidget(self.clear_btn)

        detail_layout.addLayout(action_layout)

        footer_layout = QHBoxLayout()
        footer_layout.setContentsMargins(0, 0, 0, 0)

        self.status_label = QLabel("等待新的剪切板内容。")
        self.status_label.setStyleSheet(
            "color: #8FC7FF; border: none; background: transparent;"
        )
        footer_layout.addWidget(self.status_label)
        footer_layout.addStretch()

        self.size_grip = QSizeGrip(self.container)
        self.size_grip.setToolTip("拖动这里调整窗口大小")
        footer_layout.addWidget(self.size_grip, 0, Qt.AlignmentFlag.AlignRight)

        detail_layout.addLayout(footer_layout)

        detail_widget.setMinimumHeight(140)
        detail_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self.splitter.addWidget(detail_widget)
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setSizes([220, 220])
        self.splitter.splitterMoved.connect(self._save_splitter_sizes)
        layout.addWidget(self.splitter)

        main_layout.addWidget(self.container)
        self.setLayout(main_layout)

        self._register_interaction_widgets()
        self.reload_prompt_options()
        self._restore_splitter_sizes()
        self._sync_action_state()

    def load_history(self):
        self.list_widget.clear()
        for item in self.clipboard_mgr.get_history():
            self.list_widget.addItem(self._build_list_item(item))

        if self.list_widget.count():
            self.list_widget.setCurrentRow(0)
        else:
            self._show_empty_state()

    def on_history_event(self, event, item=None):
        if event == "clear":
            self.list_widget.clear()
            self._show_empty_state()
            self._set_status("历史已清空。")
            return

        if event == "add" and item is not None:
            self.list_widget.insertItem(0, self._build_list_item(item))
            self.list_widget.setCurrentRow(0)

            if item.get("source_kind") == "clipboard" and self.auto_popup_enabled:
                self.show_panel()

    def _build_list_item(self, item):
        list_item = QListWidgetItem(self._build_item_text(item))
        list_item.setData(Qt.ItemDataRole.UserRole, item)
        return list_item

    def _build_item_text(self, item):
        time_text = datetime.fromtimestamp(item["timestamp"]).strftime("%H:%M:%S")
        source_kind = item.get("source_kind", "clipboard")

        if item["type"] == "image":
            prefix = "图片"
            title = f"{item['width']} x {item['height']}"
            detail = "支持复制回剪切板与另存为图片文件"
        else:
            prefix = "AI结果" if source_kind == "ai_result" else "文本"
            content = item["content"].replace("\n", " ").strip()
            title = content[:24] + ("..." if len(content) > 24 else "")
            detail = content[:60] + ("..." if len(content) > 60 else "")

        return f"[{prefix}] {title}\n{time_text}  {detail}"

    def on_current_item_changed(self, current, previous):
        del previous
        item = current.data(Qt.ItemDataRole.UserRole) if current else None
        self._render_item_detail(item)

    def _render_item_detail(self, item):
        if not item:
            self._show_empty_state()
            return

        created_at = datetime.fromtimestamp(item["timestamp"]).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        source_kind = "AI 优化结果" if item.get("source_kind") == "ai_result" else "剪切板原始内容"

        if item["type"] == "image":
            self.meta_label.setText(
                f"类型：图片 | 来源：{source_kind} | 时间：{created_at} | 尺寸：{item['width']} x {item['height']}"
            )
            self._update_image_preview(item)
            self.preview_stack.setCurrentWidget(self.image_preview)
        else:
            self.meta_label.setText(f"类型：文本 | 来源：{source_kind} | 时间：{created_at}")
            self.text_preview.setPlainText(item["content"])
            self.preview_stack.setCurrentWidget(self.text_preview)

        self._sync_action_state(item)

    def _show_empty_state(self):
        self.meta_label.setText("当前还没有捕获到内容。")
        self.preview_stack.setCurrentWidget(self.empty_state)
        self._sync_action_state(None)

    def _sync_action_state(self, item=None):
        current_item = item or self._selected_item()
        has_item = current_item is not None
        is_text = has_item and current_item["type"] == "text"
        is_image = has_item and current_item["type"] == "image"

        self.copy_btn.setEnabled(has_item)
        self.paste_btn.setEnabled(has_item)
        self.ai_btn.setEnabled(is_text)
        self.save_btn.setEnabled(is_image)
        self.clear_btn.setEnabled(self.list_widget.count() > 0)

    def _selected_item(self):
        current_item = self.list_widget.currentItem()
        if not current_item:
            return None
        return current_item.data(Qt.ItemDataRole.UserRole)

    def copy_selected_item(self):
        item = self._selected_item()
        if not item:
            self._set_status("请先选择一个历史项。")
            return

        self.clipboard_mgr.copy_item_to_clipboard(item)
        if item["type"] == "image":
            self._set_status("图片已复制回剪切板。")
        else:
            self._set_status("文本已复制回剪切板。")

    def paste_selected_item(self):
        item = self._selected_item()
        if not item:
            self._set_status("请先选择一个历史项。")
            return

        self.copy_selected_item()
        self.hide()
        QTimer.singleShot(150, lambda: keyboard.send("ctrl+v"))

    def on_item_double_clicked(self, item):
        del item
        self.paste_selected_item()

    def on_ai_rewrite(self):
        item = self._selected_item()
        if not item:
            self._set_status("请先选择一段文本。")
            return

        if item["type"] != "text":
            self._set_status("当前仅支持对文本执行 AI 优化。")
            return

        self.ai_btn.setEnabled(False)
        self.ai_btn.setText("正在优化...")
        self._pending_rewrite_source_id = item["id"]
        if self.prompt_slot_combo.currentData() == AppSettings.DEFAULT_SELECTED_SLOT_ID:
            self._set_status("AI 正在按默认 Prompt 优化文本，请稍候。")
        else:
            self._set_status(
                f"AI 正在按槽位“{self.prompt_slot_combo.currentText()}”优化文本，请稍候。"
            )

        self.rewrite_thread = AIRewriteThread(
            self.ai,
            item["content"],
            prompt_slot_id=self.prompt_slot_combo.currentData(),
        )
        self.rewrite_thread.finished_signal.connect(self.on_rewrite_finished)
        self.rewrite_thread.start()

    def on_rewrite_finished(self, new_content):
        self.ai_btn.setEnabled(True)
        self.ai_btn.setText("AI 优化")
        source_item_id = self._pending_rewrite_source_id
        self._pending_rewrite_source_id = None

        if self._looks_like_error(new_content):
            self._set_status(new_content)
            return

        result_item = self.clipboard_mgr.add_ai_result(
            new_content,
            source_item_id=source_item_id,
        )
        if result_item is not None:
            self.clipboard_mgr.copy_item_to_clipboard(result_item)
            self.list_widget.setCurrentRow(0)

        self._set_status("AI 优化完成，结果已复制到剪切板，可直接粘贴或继续修改。")

    def save_selected_image(self):
        item = self._selected_item()
        if not item or item["type"] != "image":
            self._set_status("当前选中的不是图片。")
            return

        default_name = f"win-clipboard-image-{datetime.now().strftime('%Y%m%d-%H%M%S')}.png"
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "另存图片",
            default_name,
            "PNG 图片 (*.png);;JPEG 图片 (*.jpg *.jpeg);;BMP 图片 (*.bmp)",
        )
        if not file_path:
            self._set_status("已取消保存。")
            return

        if item["image"].save(file_path):
            self._set_status(f"图片已保存到：{file_path}")
        else:
            self._set_status("图片保存失败。")

    def prompt_clear_history(self):
        if not self.list_widget.count():
            self._set_status("当前没有可清理的历史。")
            return

        result = QMessageBox.question(
            self,
            "清空历史",
            "确定要清空当前会话中的全部历史吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if result == QMessageBox.StandardButton.Yes:
            self.clipboard_mgr.clear_history()

    def set_auto_popup_enabled(self, enabled):
        self.auto_popup_enabled = enabled
        state_text = "已开启" if enabled else "已关闭"
        self._set_status(f"复制后自动弹出：{state_text}")

    def reload_prompt_options(self):
        prompt_settings = AppSettings.load_prompt_settings()
        current_selection = prompt_settings["selected_slot_id"]
        available_slots = AppSettings.get_available_prompt_slots()

        self._updating_prompt_combo = True
        self.prompt_slot_combo.blockSignals(True)
        self.prompt_slot_combo.clear()
        self.prompt_slot_combo.addItem("默认", AppSettings.DEFAULT_SELECTED_SLOT_ID)
        for slot in available_slots:
            self.prompt_slot_combo.addItem(slot["name"], slot["id"])

        selected_index = self.prompt_slot_combo.findData(current_selection)
        if selected_index < 0:
            selected_index = 0
        self.prompt_slot_combo.setCurrentIndex(selected_index)
        self.prompt_slot_combo.blockSignals(False)
        self._updating_prompt_combo = False

    def on_prompt_slot_changed(self, index):
        if self._updating_prompt_combo or index < 0:
            return

        slot_id = self.prompt_slot_combo.itemData(index)
        saved_slot_id = AppSettings.set_selected_slot_id(slot_id)
        if saved_slot_id == AppSettings.DEFAULT_SELECTED_SLOT_ID:
            self._set_status("AI 优化已切换为默认 Prompt。")
            return

        self._set_status(f"AI 优化已切换为槽位：{self.prompt_slot_combo.currentText()}")

    def show_panel(self):
        if self.list_widget.count() and self.list_widget.currentRow() < 0:
            self.list_widget.setCurrentRow(0)

        # 如果有保存的几何信息，直接恢复；否则跟随鼠标
        if self._has_saved_geometry:
            pass  # 位置已在 _restore_geometry 中设定
        else:
            pos = QCursor.pos()
            available = QGuiApplication.primaryScreen().availableGeometry()
            x = max(available.left(), min(pos.x() - 260, available.right() - self.width()))
            y = max(available.top(), min(pos.y() - 120, available.bottom() - self.height()))
            self.move(x, y)

        self.show()
        self.raise_()
        self.activateWindow()

    def eventFilter(self, watched, event):
        if watched in self._resize_widgets and self._handle_resize_event(watched, event):
            return True

        if watched in self._move_widgets and self._handle_move_event(event):
            return True

        return super().eventFilter(watched, event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        item = self._selected_item()
        if item and item["type"] == "image":
            self._update_image_preview(item)

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_Escape:
            self.hide()
            event.accept()
            return

        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.paste_selected_item()
            event.accept()
            return

        super().keyPressEvent(event)

    def hideEvent(self, event):
        self._save_geometry()
        super().hideEvent(event)

    # ------------------------------------------------------------------
    #  内部方法: 窗口边缘拖拽调整大小
    # ------------------------------------------------------------------
    def _detect_edge(self, pos, rect=None):
        """检测鼠标是否处于窗口边缘，返回方向字符串或 None。"""
        m = self.EDGE_MARGIN
        rect = rect or self.rect()
        x, y = pos.x(), pos.y()

        on_left = x <= rect.left() + m
        on_right = x >= rect.right() - m
        on_top = y <= rect.top() + m
        on_bottom = y >= rect.bottom() - m

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
        from PyQt6.QtCore import Qt as _Qt
        cursors = {
            "left": _Qt.CursorShape.SizeHorCursor,
            "right": _Qt.CursorShape.SizeHorCursor,
            "top": _Qt.CursorShape.SizeVerCursor,
            "bottom": _Qt.CursorShape.SizeVerCursor,
            "top-left": _Qt.CursorShape.SizeFDiagCursor,
            "bottom-right": _Qt.CursorShape.SizeFDiagCursor,
            "top-right": _Qt.CursorShape.SizeBDiagCursor,
            "bottom-left": _Qt.CursorShape.SizeBDiagCursor,
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
        min_w, min_h = 400, 350

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

        self.setGeometry(geo)

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
                self._move_drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
                return True

        if event_type == QEvent.Type.MouseMove:
            if self._move_drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
                self.move(event.globalPosition().toPoint() - self._move_drag_offset)
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

    # ------------------------------------------------------------------
    #  内部方法: 窗口几何持久化
    # ------------------------------------------------------------------
    def _save_geometry(self):
        geo = self.geometry()
        self._settings.setValue("panel/x", geo.x())
        self._settings.setValue("panel/y", geo.y())
        self._settings.setValue("panel/width", geo.width())
        self._settings.setValue("panel/height", geo.height())
        self._save_splitter_sizes()
        self._settings.sync()

    def _restore_geometry(self):
        x = self._settings.value("panel/x", None)
        if x is None:
            self._has_saved_geometry = False
            return
        try:
            x = int(x)
            y = int(self._settings.value("panel/y", 100))
            w = int(self._settings.value("panel/width", 760))
            h = int(self._settings.value("panel/height", 560))
        except (TypeError, ValueError):
            self._has_saved_geometry = False
            return

        self.setGeometry(x, y, w, h)
        self._has_saved_geometry = True

    def _save_splitter_sizes(self, *args):
        del args
        top, bottom = self.splitter.sizes()
        self._settings.setValue("panel/splitter_top", top)
        self._settings.setValue("panel/splitter_bottom", bottom)

    def _restore_splitter_sizes(self):
        top = self._settings.value("panel/splitter_top", None)
        bottom = self._settings.value("panel/splitter_bottom", None)
        if top is None or bottom is None:
            return

        try:
            top = int(top)
            bottom = int(bottom)
        except (TypeError, ValueError):
            return

        if top > 0 and bottom > 0:
            self.splitter.setSizes([top, bottom])

    # ------------------------------------------------------------------
    #  内部方法: 通用辅助
    # ------------------------------------------------------------------
    def _set_status(self, text):
        self.status_label.setText(text)

    def _looks_like_error(self, text):
        return text.startswith("[") and any(
            keyword in text for keyword in ("错误", "异常", "失败", "超时", "配置")
        )

    def _update_image_preview(self, item):
        pixmap = QPixmap.fromImage(item["image"])
        preview_size = self.image_preview.size()
        scaled = pixmap.scaled(
            max(preview_size.width() - 24, 200),
            max(preview_size.height() - 24, 200),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.image_preview.setPixmap(scaled)
