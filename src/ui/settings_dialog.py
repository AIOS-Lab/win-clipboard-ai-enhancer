from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from core.ai_bridge import AIBridge
from core.app_settings import AppSettings


# 预置模型列表（用户也可以手动输入自定义模型）
DEFAULT_MODELS = [
    "Qwen/Qwen2.5-7B-Instruct",
    "Qwen/Qwen2.5-14B-Instruct",
    "Qwen/Qwen2.5-72B-Instruct",
    "deepseek-ai/DeepSeek-V3",
    "deepseek-ai/DeepSeek-R1",
    "THUDM/glm-4-9b-chat",
    "meta-llama/Meta-Llama-3.1-8B-Instruct",
]


class LLMSettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("LLM 配置")
        self.setMinimumWidth(520)
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.WindowCloseButtonHint
            | Qt.WindowType.WindowStaysOnTopHint
        )

        self._build_ui()
        self._load_settings()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(16)

        api_group = QGroupBox("API 配置")
        api_form = QFormLayout()

        self.api_key_edit = QLineEdit()
        self.api_key_edit.setPlaceholderText("sk-xxxxxxxxxxxxxxxxxxxxxxxx")
        self.api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        api_form.addRow("API Key：", self.api_key_edit)

        self.api_base_edit = QLineEdit()
        self.api_base_edit.setPlaceholderText("https://api.siliconflow.cn/v1/chat/completions")
        api_form.addRow("API Base：", self.api_base_edit)

        api_group.setLayout(api_form)
        layout.addWidget(api_group)

        model_group = QGroupBox("模型配置")
        model_form = QFormLayout()

        self.model_combo = QComboBox()
        self.model_combo.setEditable(True)
        self.model_combo.addItems(DEFAULT_MODELS)
        model_form.addRow("模型名称：", self.model_combo)

        self.temperature_spin = QDoubleSpinBox()
        self.temperature_spin.setRange(0.0, 2.0)
        self.temperature_spin.setSingleStep(0.1)
        self.temperature_spin.setDecimals(1)
        model_form.addRow("Temperature：", self.temperature_spin)

        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(10, 180)
        self.timeout_spin.setSuffix(" 秒")
        model_form.addRow("请求超时：", self.timeout_spin)

        self.max_tokens_enabled_check = QCheckBox("启用 max_tokens 高级限制")
        model_form.addRow("高级限制：", self.max_tokens_enabled_check)

        self.max_tokens_spin = QSpinBox()
        self.max_tokens_spin.setRange(128, 4096)
        self.max_tokens_spin.setSingleStep(128)
        model_form.addRow("max_tokens：", self.max_tokens_spin)

        self.enable_thinking_check = QCheckBox("启用思维链 / CoT")
        model_form.addRow("深度思考：", self.enable_thinking_check)

        self.max_tokens_enabled_check.toggled.connect(self.max_tokens_spin.setEnabled)

        model_group.setLayout(model_form)
        layout.addWidget(model_group)

        hint_label = QLabel(
            "提示：输出长度百分比在“Prompt 设置”里控制；"
            "这里的 max_tokens 是底层高级参数，默认关闭。\n"
            f"日志文件：{AIBridge.get_log_path()}\n如果 AI 优化失败，先看这份日志。"
        )
        hint_label.setWordWrap(True)
        hint_label.setStyleSheet("color: #666;")
        layout.addWidget(hint_label)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        save_btn = QPushButton("保存")
        save_btn.clicked.connect(self._save_and_close)
        btn_layout.addWidget(save_btn)

        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        layout.addLayout(btn_layout)

    def _load_settings(self):
        config = AppSettings.load_llm_settings()
        self.api_key_edit.setText(config["api_key"])
        self.api_base_edit.setText(config["api_base"])

        idx = self.model_combo.findText(config["model"])
        if idx >= 0:
            self.model_combo.setCurrentIndex(idx)
        else:
            self.model_combo.setCurrentText(config["model"])

        self.temperature_spin.setValue(config["temperature"])
        self.timeout_spin.setValue(config["timeout"])
        self.max_tokens_spin.setValue(config["max_tokens"])
        self.max_tokens_enabled_check.setChecked(config["max_tokens_enabled"])
        self.max_tokens_spin.setEnabled(config["max_tokens_enabled"])
        self.enable_thinking_check.setChecked(config["enable_thinking"])

    def _save_and_close(self):
        AppSettings.save_llm_settings(
            {
                "api_key": self.api_key_edit.text().strip(),
                "api_base": self.api_base_edit.text().strip(),
                "model": self.model_combo.currentText().strip(),
                "temperature": self.temperature_spin.value(),
                "timeout": self.timeout_spin.value(),
                "max_tokens": self.max_tokens_spin.value(),
                "max_tokens_enabled": self.max_tokens_enabled_check.isChecked(),
                "enable_thinking": self.enable_thinking_check.isChecked(),
            }
        )
        self.accept()

    @staticmethod
    def get_llm_config() -> dict:
        """Read persisted LLM config from QSettings. Usable anywhere."""
        return AppSettings.load_llm_settings()
