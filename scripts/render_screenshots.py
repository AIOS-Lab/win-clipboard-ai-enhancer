from __future__ import annotations

import os
import sys
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("WIN_CLIPBOARD_AI_PORTABLE", "1")

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QImage
from PyQt6.QtWidgets import QApplication

from core.app_settings import AppSettings
from ui.panel import HistoryPanel
from ui.prompt_settings_dialog import PromptSettingsDialog


class FakeClipboardManager:
    def __init__(self, history: list[dict]):
        self.history = list(history)
        self.callback = None

    def set_callback(self, callback):
        self.callback = callback

    def get_history(self):
        return list(self.history)

    def copy_item_to_clipboard(self, item):
        return item

    def add_ai_result(self, text, source_item_id=None):
        item = {
            "id": f"ai-{int(time.time())}",
            "type": "text",
            "content": text,
            "timestamp": time.time(),
            "source_kind": "ai_result",
            "source_item_id": source_item_id,
            "signature": str(hash(text)),
        }
        self.history.insert(0, item)
        if self.callback:
            self.callback("add", item)
        return item

    def clear_history(self):
        self.history.clear()
        if self.callback:
            self.callback("clear")


def ensure_prompt_defaults():
    AppSettings.ensure_defaults()
    AppSettings.save_prompt_settings(
        {
            "default_prompt": (
                "你是一位顶级的 Prompt Engineer（提示词工程师）。\n"
                "你的唯一任务是将用户提供的简短想法或指令，拓展并重写成结构清晰、约束明确、"
                "可直接用于驱动其他大模型的高质量系统提示词（Prompt）。\n"
                "你需要自动分析用户的原始输入，补充缺失的细节，完善逻辑框架，明确输出格式。\n"
                "务必确保内容包括：内容框架、设计规范/要求、交付物结构等维度（视情况调整）。\n"
                "【严格注意】：请直接输出优化后的最终 Prompt 正文！千万不要包含多余的自我介绍、"
                "不要复述原句、不要写诸如“为您优化完成”之类的客套话，必须直接以可用形式给出最终内容。"
            ),
            "output_length_percent": 350,
            "selected_slot_id": "none",
            "slots": [
                {"id": "slot_1", "name": "偏正式", "prompt_text": "输出风格更正式，适合汇报、方案和文书。"},
                {"id": "slot_2", "name": "", "prompt_text": ""},
                {"id": "slot_3", "name": "", "prompt_text": ""},
            ],
        }
    )


def make_text_item(item_id: str, content: str, source_kind: str, ts: float) -> dict:
    return {
        "id": item_id,
        "type": "text",
        "content": content,
        "timestamp": ts,
        "source_kind": source_kind,
        "source_item_id": None,
        "signature": str(hash((item_id, content))),
    }


def render_prompt_settings(app: QApplication, output_path: Path):
    dialog = PromptSettingsDialog()
    dialog.resize(780, 620)
    dialog.show()
    app.processEvents()
    dialog.grab().save(str(output_path))
    dialog.close()


def render_history_panel(app: QApplication, output_path: Path, user_text: str, ai_text: str):
    now = time.time()
    history = [
        make_text_item("ai-1", ai_text, "ai_result", now),
        make_text_item("text-1", user_text, "clipboard", now - 35),
    ]
    manager = FakeClipboardManager(history)
    panel = HistoryPanel(manager)
    panel.resize(1049, 755)
    panel.list_widget.setCurrentRow(0)
    panel.show()
    app.processEvents()
    panel.grab().save(str(output_path))
    panel.close()


def main():
    ensure_prompt_defaults()
    out_dir = ROOT / "assets" / "screenshots"
    out_dir.mkdir(parents=True, exist_ok=True)

    app = QApplication(sys.argv)

    render_prompt_settings(app, out_dir / "prompt-settings.png")
    render_history_panel(
        app,
        out_dir / "ai-optimize-work-report.png",
        "帮我写一个给老板汇报项目延期的说明，要显得专业一点，别太生硬，还要带上后续补救计划。",
        "你是一位经验丰富的项目经理，需要向公司高层（如 CEO、部门总监等）汇报一个重要项目出现延期的情况。你的目标是在保持专业、坦诚的同时，妥善管理预期，并展现对局面的掌控力，以维护信任。\n\n**核心任务：**\n基于当前项目状况，起草一份关于项目延期的正式汇报说明。\n\n**汇报内容必须清晰说明：**\n1. 延期原因与客观背景\n2. 当前影响范围与项目状态\n3. 已采取的补救措施\n4. 下一阶段计划与时间节点\n5. 对管理层的支持诉求\n\n整体表达应专业、克制、可信，不推责，不空泛。",
    )
    render_history_panel(
        app,
        out_dir / "ai-optimize-agent-prompt.png",
        "我想让一个AI帮我先理解需求，再拆任务，再写代码，最后自己检查问题，帮我整理成一段能直接用的提示词。",
        "你是一个专业的软件开发助手，遵循“需求理解 -> 任务拆解 -> 代码实现 -> 自查优化”的标准化流程来响应用户的编程请求。你的目标是生成高质量、可直接执行或易于集成的代码。\n\n**核心流程与要求：**\n1. 在需求理解阶段，主动识别缺失信息并进行针对性追问。\n2. 在任务拆解阶段，把开发任务拆成清晰可执行的小模块，并说明顺序。\n3. 在代码实现阶段，输出结构清晰、命名规范、注释得当的代码，并补充必要的异常处理。\n4. 在自查阶段，主动检查潜在 Bug、边界条件、依赖问题和可维护性风险。\n5. 最终输出应包含：需求理解摘要、任务拆解、实现方案、代码与自查结论。",
    )
    app.quit()


if __name__ == "__main__":
    main()
