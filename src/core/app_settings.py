import json
from copy import deepcopy

from PyQt6.QtCore import QSettings

from core.runtime_paths import get_settings_path, is_portable_mode

APP_ORG = "WinClipboardAIEnhancer"
APP_NAME = "WinClipboardAIEnhancer"

DEFAULT_PROMPT_TEXT = (
    "你是一位顶级的 Prompt Engineer（提示词工程师）。\n"
    "你的唯一任务是将用户提供的简短想法或指令，拓展并重写成结构清晰、约束明确、"
    "可直接用于驱动其他大模型的高质量系统提示词（Prompt）。\n"
    "你需要自动分析用户的原始输入，补充缺失的细节，完善逻辑框架，明确输出格式。\n"
    "务必确保内容包括：内容框架、设计规范/要求、交付物结构等维度（视情况调整）。\n"
    "【严格注意】：请直接输出优化后的最终 Prompt 正文！"
    "千万不要包含多余的自我介绍、不要复述原句、"
    "不要写诸如“为您优化完成”之类的客套话，必须直接以可用形式给出最终内容。"
)


class AppSettings:
    DEFAULT_SELECTED_SLOT_ID = "none"
    SLOT_IDS = ["slot_1", "slot_2", "slot_3"]

    @classmethod
    def settings(cls) -> QSettings:
        if is_portable_mode():
            return QSettings(
                str(get_settings_path()),
                QSettings.Format.IniFormat,
            )
        return QSettings(APP_ORG, APP_NAME)

    @classmethod
    def _default_slots(cls) -> list[dict]:
        return [
            {"id": slot_id, "name": "", "prompt_text": ""}
            for slot_id in cls.SLOT_IDS
        ]

    @classmethod
    def default_prompt_settings(cls) -> dict:
        return {
            "default_prompt": DEFAULT_PROMPT_TEXT,
            "output_length_percent": 300,
            "selected_slot_id": cls.DEFAULT_SELECTED_SLOT_ID,
            "slots": cls._default_slots(),
        }

    @classmethod
    def default_llm_settings(cls) -> dict:
        return {
            "api_key": "",
            "api_base": "https://api.siliconflow.cn/v1/chat/completions",
            "model": "Qwen/Qwen2.5-7B-Instruct",
            "temperature": 0.7,
            "timeout": 60,
            "max_tokens": 1200,
            "max_tokens_enabled": False,
            "enable_thinking": False,
        }

    @classmethod
    def ensure_defaults(cls) -> None:
        settings = cls.settings()
        prompt_defaults = cls.default_prompt_settings()
        llm_defaults = cls.default_llm_settings()
        changed = False

        if not settings.value("prompt/default_prompt", "", type=str).strip():
            settings.setValue("prompt/default_prompt", prompt_defaults["default_prompt"])
            changed = True

        if not settings.contains("prompt/output_length_percent"):
            settings.setValue(
                "prompt/output_length_percent",
                prompt_defaults["output_length_percent"],
            )
            changed = True

        if not settings.value("prompt/slots_json", "", type=str).strip():
            settings.setValue(
                "prompt/slots_json",
                json.dumps(prompt_defaults["slots"], ensure_ascii=False),
            )
            changed = True

        if not settings.contains("prompt/selected_slot_id"):
            settings.setValue(
                "prompt/selected_slot_id",
                prompt_defaults["selected_slot_id"],
            )
            changed = True

        for key, value in llm_defaults.items():
            full_key = f"llm/{key}"
            if not settings.contains(full_key):
                settings.setValue(full_key, value)
                changed = True

        normalized_prompt = cls.load_prompt_settings()
        settings.setValue("prompt/default_prompt", normalized_prompt["default_prompt"])
        settings.setValue(
            "prompt/output_length_percent",
            normalized_prompt["output_length_percent"],
        )
        settings.setValue("prompt/selected_slot_id", normalized_prompt["selected_slot_id"])
        settings.setValue(
            "prompt/slots_json",
            json.dumps(normalized_prompt["slots"], ensure_ascii=False),
        )
        changed = True

        if changed:
            settings.sync()

    @classmethod
    def _normalize_percent(cls, value) -> int:
        try:
            percent = int(value)
        except (TypeError, ValueError):
            percent = 300

        percent = max(100, min(500, percent))
        remainder = percent % 50
        if remainder >= 25:
            percent += 50 - remainder
        else:
            percent -= remainder
        return max(100, min(500, percent))

    @classmethod
    def _normalize_slots(cls, slots) -> list[dict]:
        normalized: list[dict] = []
        source = slots if isinstance(slots, list) else []

        for index, slot_id in enumerate(cls.SLOT_IDS):
            slot = source[index] if index < len(source) and isinstance(source[index], dict) else {}
            normalized.append(
                {
                    "id": slot.get("id", slot_id) or slot_id,
                    "name": str(slot.get("name", "") or "").strip(),
                    "prompt_text": str(slot.get("prompt_text", "") or "").strip(),
                }
            )

        return normalized

    @classmethod
    def _load_slots_from_settings(cls, settings: QSettings) -> list[dict]:
        raw_slots = settings.value("prompt/slots_json", "", type=str)
        if not raw_slots:
            return cls._default_slots()

        try:
            parsed = json.loads(raw_slots)
        except json.JSONDecodeError:
            parsed = []
        return cls._normalize_slots(parsed)

    @classmethod
    def _resolve_selected_slot_id(cls, selected_slot_id: str, slots: list[dict]) -> str:
        valid_ids = {
            slot["id"]
            for slot in slots
            if slot["name"].strip() and slot["prompt_text"].strip()
        }
        if selected_slot_id in valid_ids:
            return selected_slot_id
        return cls.DEFAULT_SELECTED_SLOT_ID

    @classmethod
    def load_prompt_settings(cls) -> dict:
        settings = cls.settings()
        default_prompt = settings.value(
            "prompt/default_prompt",
            DEFAULT_PROMPT_TEXT,
            type=str,
        ).strip()
        if not default_prompt:
            default_prompt = DEFAULT_PROMPT_TEXT

        output_length_percent = cls._normalize_percent(
            settings.value("prompt/output_length_percent", 300)
        )
        slots = cls._load_slots_from_settings(settings)
        selected_slot_id = str(
            settings.value("prompt/selected_slot_id", cls.DEFAULT_SELECTED_SLOT_ID, type=str)
        )
        selected_slot_id = cls._resolve_selected_slot_id(selected_slot_id, slots)

        return {
            "default_prompt": default_prompt,
            "output_length_percent": output_length_percent,
            "selected_slot_id": selected_slot_id,
            "slots": slots,
        }

    @classmethod
    def save_prompt_settings(cls, payload: dict) -> dict:
        current = cls.load_prompt_settings()
        merged = {
            "default_prompt": str(
                payload.get("default_prompt", current["default_prompt"]) or ""
            ).strip()
            or DEFAULT_PROMPT_TEXT,
            "output_length_percent": cls._normalize_percent(
                payload.get("output_length_percent", current["output_length_percent"])
            ),
            "selected_slot_id": str(
                payload.get("selected_slot_id", current["selected_slot_id"]) or ""
            ),
            "slots": cls._normalize_slots(payload.get("slots", current["slots"])),
        }
        merged["selected_slot_id"] = cls._resolve_selected_slot_id(
            merged["selected_slot_id"],
            merged["slots"],
        )

        settings = cls.settings()
        settings.setValue("prompt/default_prompt", merged["default_prompt"])
        settings.setValue("prompt/output_length_percent", merged["output_length_percent"])
        settings.setValue("prompt/selected_slot_id", merged["selected_slot_id"])
        settings.setValue(
            "prompt/slots_json",
            json.dumps(merged["slots"], ensure_ascii=False),
        )
        settings.sync()
        return deepcopy(merged)

    @classmethod
    def reset_prompt_settings(cls) -> dict:
        return cls.save_prompt_settings(cls.default_prompt_settings())

    @classmethod
    def get_available_prompt_slots(cls) -> list[dict]:
        settings = cls.load_prompt_settings()
        return [
            deepcopy(slot)
            for slot in settings["slots"]
            if slot["name"].strip() and slot["prompt_text"].strip()
        ]

    @classmethod
    def get_prompt_slot_by_id(cls, slot_id: str | None) -> dict | None:
        if not slot_id or slot_id == cls.DEFAULT_SELECTED_SLOT_ID:
            return None
        for slot in cls.get_available_prompt_slots():
            if slot["id"] == slot_id:
                return slot
        return None

    @classmethod
    def set_selected_slot_id(cls, slot_id: str | None) -> str:
        settings = cls.load_prompt_settings()
        normalized = cls._resolve_selected_slot_id(slot_id or "", settings["slots"])
        return cls.save_prompt_settings(
            {
                "default_prompt": settings["default_prompt"],
                "output_length_percent": settings["output_length_percent"],
                "selected_slot_id": normalized,
                "slots": settings["slots"],
            }
        )["selected_slot_id"]

    @classmethod
    def load_llm_settings(cls) -> dict:
        settings = cls.settings()
        defaults = cls.default_llm_settings()
        return {
            "api_key": settings.value("llm/api_key", defaults["api_key"], type=str),
            "api_base": settings.value("llm/api_base", defaults["api_base"], type=str),
            "model": settings.value("llm/model", defaults["model"], type=str),
            "temperature": float(settings.value("llm/temperature", defaults["temperature"])),
            "timeout": int(settings.value("llm/timeout", defaults["timeout"])),
            "max_tokens": int(settings.value("llm/max_tokens", defaults["max_tokens"])),
            "max_tokens_enabled": settings.value(
                "llm/max_tokens_enabled",
                defaults["max_tokens_enabled"],
                type=bool,
            ),
            "enable_thinking": settings.value(
                "llm/enable_thinking",
                defaults["enable_thinking"],
                type=bool,
            ),
        }

    @classmethod
    def save_llm_settings(cls, payload: dict) -> dict:
        current = cls.load_llm_settings()
        merged = {
            "api_key": str(payload.get("api_key", current["api_key"]) or "").strip(),
            "api_base": str(payload.get("api_base", current["api_base"]) or "").strip()
            or cls.default_llm_settings()["api_base"],
            "model": str(payload.get("model", current["model"]) or "").strip()
            or cls.default_llm_settings()["model"],
            "temperature": float(payload.get("temperature", current["temperature"])),
            "timeout": int(payload.get("timeout", current["timeout"])),
            "max_tokens": int(payload.get("max_tokens", current["max_tokens"])),
            "max_tokens_enabled": bool(
                payload.get("max_tokens_enabled", current["max_tokens_enabled"])
            ),
            "enable_thinking": bool(
                payload.get("enable_thinking", current["enable_thinking"])
            ),
        }

        settings = cls.settings()
        for key, value in merged.items():
            settings.setValue(f"llm/{key}", value)
        settings.sync()
        return merged
