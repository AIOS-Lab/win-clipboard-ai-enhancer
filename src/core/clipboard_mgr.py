import hashlib
import time
import uuid
from contextlib import contextmanager

from PyQt6.QtCore import QBuffer, QByteArray, QIODevice
from PyQt6.QtGui import QImage

class ClipboardManager:
    def __init__(self, q_clipboard):
        self.q_clip = q_clipboard
        self.history = []
        self._callback = None
        self._capture_suspended = 0
        self._last_signature = None
        self.max_history = 100
        
        # Connect to clipboard change signal
        self.q_clip.dataChanged.connect(self._on_clipboard_changed)

    def set_callback(self, callback):
        """Register a callback to notify when new content is added."""
        self._callback = callback

    def get_history(self):
        return list(self.history)

    @contextmanager
    def suspend_capture(self):
        self._capture_suspended += 1
        try:
            yield
        finally:
            self._capture_suspended = max(0, self._capture_suspended - 1)

    def copy_item_to_clipboard(self, item):
        self._last_signature = item.get("signature")
        with self.suspend_capture():
            if item["type"] == "image":
                self.q_clip.setImage(item["image"])
            else:
                self.q_clip.setText(item["content"])

    def add_ai_result(self, text, source_item_id=None):
        item = self._make_text_item(
            text=text,
            source_kind="ai_result",
            source_item_id=source_item_id,
        )
        return self._record_item(item)

    def clear_history(self):
        self.history.clear()
        self._notify("clear")

    def _on_clipboard_changed(self):
        """Called by Qt when OS clipboard changes."""
        if self._capture_suspended:
            return

        mime_data = self.q_clip.mimeData()

        if mime_data.hasImage():
            image = self.q_clip.image()
            if not image.isNull():
                self._record_item(self._make_image_item(QImage(image)))
                return

        if mime_data.hasText():
            text = mime_data.text()
            if text and text.strip():
                self._record_item(self._make_text_item(text))

    def _make_text_item(self, text, source_kind="clipboard", source_item_id=None):
        return {
            "id": str(uuid.uuid4()),
            "type": "text",
            "content": text,
            "timestamp": time.time(),
            "source_kind": source_kind,
            "source_item_id": source_item_id,
            "signature": self._hash_text(text),
        }

    def _make_image_item(self, image, source_kind="clipboard", source_item_id=None):
        return {
            "id": str(uuid.uuid4()),
            "type": "image",
            "image": image,
            "timestamp": time.time(),
            "width": image.width(),
            "height": image.height(),
            "source_kind": source_kind,
            "source_item_id": source_item_id,
            "signature": self._hash_image(image),
        }

    def _record_item(self, item):
        if item["signature"] == self._last_signature:
            return None

        self._last_signature = item["signature"]
        self.history.insert(0, item)  # prepend to history list
        if len(self.history) > self.max_history:
            self.history.pop()

        self._notify("add", item)
        return item

    def _notify(self, event, item=None):
        if not self._callback:
            return

        try:
            self._callback(event, item)
        except TypeError:
            if item is not None:
                self._callback(item)

    def _hash_text(self, text):
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def _hash_image(self, image):
        data = QByteArray()
        buffer = QBuffer(data)
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        image.save(buffer, "PNG")
        return hashlib.sha256(bytes(data)).hexdigest()
