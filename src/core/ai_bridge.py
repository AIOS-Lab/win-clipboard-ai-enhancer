import logging
import os
import time
import uuid
from logging.handlers import RotatingFileHandler
from pathlib import Path

import requests

from core.app_settings import AppSettings
from core.runtime_paths import get_data_root


class AIBridge:
    """AI 调用桥接层。优先从 QSettings 读取 LLM 配置，环境变量作为 fallback。"""

    APP_NAME = "WinClipboardAIEnhancer"
    INTERNAL_SYSTEM_RULES = (
        "你负责将用户提供的原始输入，优化为可直接交给其他大模型使用的高质量 Prompt。\n"
        "必须保持原始意图，不得改变任务本质；应先理解内容，再自行补全必要的角色、流程、"
        "信息采集维度、输出结构与约束。\n"
        "不要机械套用固定模板，也不要为了显得完整而加入无关内容。\n"
        "若输入更适合简洁表达，就保持简洁；若输入隐含复杂专业任务，就做结构化扩写与补全。\n"
        "最终只输出优化后的 Prompt 正文，不要附加解释、标题或客套话。"
    )
    THINKING_TOGGLE_MODELS = {
        "Pro/deepseek-ai/DeepSeek-V3.2",
        "deepseek-ai/DeepSeek-R1",
        "deepseek-ai/DeepSeek-V3",
    }
    _logger = None

    def __init__(self):
        pass  # 配置在每次调用时动态读取，以便用户改完设置无需重启

    # ------------------------------------------------------------------
    #  日志
    # ------------------------------------------------------------------
    @classmethod
    def get_app_data_dir(cls) -> Path:
        return get_data_root()

    @classmethod
    def ensure_log_dir(cls) -> Path:
        log_dir = cls.get_app_data_dir() / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        return log_dir

    @classmethod
    def get_log_path(cls) -> Path:
        return cls.ensure_log_dir() / "ai_bridge.log"

    @classmethod
    def get_logger(cls) -> logging.Logger:
        if cls._logger is not None:
            return cls._logger

        cls.ensure_log_dir()
        logger = logging.getLogger("win_clipboard_ai.ai_bridge")
        logger.setLevel(logging.INFO)
        logger.propagate = False

        if not logger.handlers:
            handler = RotatingFileHandler(
                cls.get_log_path(),
                maxBytes=1_000_000,
                backupCount=5,
                encoding="utf-8",
            )
            formatter = logging.Formatter(
                "%(asctime)s | %(levelname)s | %(message)s"
            )
            handler.setFormatter(formatter)
            logger.addHandler(handler)

        cls._logger = logger
        return logger

    @staticmethod
    def _preview_text(text: str, limit: int = 120) -> str:
        compact = " ".join(text.split())
        if len(compact) <= limit:
            return compact
        return compact[:limit] + "..."

    # ------------------------------------------------------------------
    #  配置读取
    # ------------------------------------------------------------------
    @staticmethod
    def _load_config() -> dict:
        AppSettings.ensure_defaults()
        cfg = AppSettings.load_llm_settings()
        api_key = cfg["api_key"]
        if not api_key:
            api_key = os.environ.get("SILICONFLOW_API_KEY", "")
        configured_timeout = int(cfg["timeout"])
        return {
            "api_key": api_key,
            "api_base": cfg["api_base"],
            "model": cfg["model"],
            "temperature": cfg["temperature"],
            "configured_timeout": configured_timeout,
            "timeout": max(configured_timeout, 60),
            "max_tokens": cfg["max_tokens"],
            "max_tokens_enabled": cfg["max_tokens_enabled"],
            "enable_thinking": cfg["enable_thinking"],
        }

    @classmethod
    def _build_messages(
        cls,
        text: str,
        prompt_settings: dict,
        prompt_slot_id: str | None,
    ) -> tuple[list[dict], dict | None]:
        selected_slot = AppSettings.get_prompt_slot_by_id(
            prompt_slot_id or prompt_settings["selected_slot_id"]
        )

        prompt_parts = [cls.INTERNAL_SYSTEM_RULES, prompt_settings["default_prompt"]]
        if selected_slot is not None:
            prompt_parts.append(selected_slot["prompt_text"])

        prompt_parts.append(
            "在保证结果完整可用的前提下，输出长度尽量不要超过原内容的 "
            f"{prompt_settings['output_length_percent']}%。"
        )

        system_prompt = "\n\n".join(
            part.strip() for part in prompt_parts if part and part.strip()
        )
        user_prompt = (
            "请直接输出优化后的最终 Prompt 正文。\n\n"
            f"【原始输入】\n{text}"
        )
        return (
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            selected_slot,
        )

    def _build_request_payload(
        self,
        text: str,
        prompt_slot_id: str | None = None,
    ) -> tuple[dict, dict, dict | None, dict]:
        cfg = self._load_config()
        prompt_settings = AppSettings.load_prompt_settings()
        messages, selected_slot = self._build_messages(
            text,
            prompt_settings,
            prompt_slot_id,
        )
        payload = {
            "model": cfg["model"],
            "messages": messages,
            "stream": False,
            "temperature": cfg["temperature"],
        }
        if cfg["max_tokens_enabled"]:
            payload["max_tokens"] = cfg["max_tokens"]
        if cfg["model"] in self.THINKING_TOGGLE_MODELS:
            payload["enable_thinking"] = cfg["enable_thinking"]
        return payload, cfg, selected_slot, prompt_settings

    # ------------------------------------------------------------------
    #  核心调用
    # ------------------------------------------------------------------
    def rewrite_text(self, text: str, prompt_slot_id: str | None = None) -> str:
        """调用 SiliconFlow OpenAI 兼容 API 重写文本。"""
        payload, cfg, selected_slot, prompt_settings = self._build_request_payload(
            text,
            prompt_slot_id=prompt_slot_id,
        )
        logger = self.get_logger()
        request_id = uuid.uuid4().hex[:8]

        if not cfg["api_key"]:
            logger.warning(
                "request_id=%s | missing_api_key | api_base=%s | model=%s",
                request_id,
                cfg["api_base"],
                cfg["model"],
            )
            return "[配置错误] 未配置 API Key，请在托盘菜单 → LLM 设置中填写。"

        headers = {
            "Authorization": f"Bearer {cfg['api_key']}",
            "Content-Type": "application/json",
        }

        logger.info(
            "request_id=%s | request_start | model=%s | configured_timeout=%s | effective_timeout=%s | max_tokens=%s | enable_thinking=%s | api_base=%s | prompt_slot_id=%s | prompt_slot_name=%s | output_length_percent=%s | input_len=%s | preview=%s",
            request_id,
            cfg["model"],
            cfg["configured_timeout"],
            cfg["timeout"],
            cfg["max_tokens"] if cfg["max_tokens_enabled"] else "disabled",
            cfg["enable_thinking"],
            cfg["api_base"],
            prompt_settings["selected_slot_id"]
            if selected_slot is None
            else selected_slot["id"],
            "默认" if selected_slot is None else selected_slot["name"],
            prompt_settings["output_length_percent"],
            len(text),
            self._preview_text(text),
        )

        started_at = time.perf_counter()
        try:
            response = requests.post(
                cfg["api_base"],
                json=payload,
                headers=headers,
                timeout=(10, cfg["timeout"]),
            )
            elapsed = round(time.perf_counter() - started_at, 2)

            if response.status_code == 200:
                data = response.json()
                choices = data.get("choices", [])
                if choices:
                    content = choices[0].get("message", {}).get("content", "AI 暂无返回")
                    reasoning_len = len(
                        choices[0].get("message", {}).get("reasoning_content", "") or ""
                    )
                    logger.info(
                        "request_id=%s | request_success | status=%s | elapsed=%s | output_len=%s | reasoning_len=%s",
                        request_id,
                        response.status_code,
                        elapsed,
                        len(content),
                        reasoning_len,
                    )
                    return content

                logger.warning(
                    "request_id=%s | malformed_response | elapsed=%s | body=%s",
                    request_id,
                    elapsed,
                    self._preview_text(response.text, 400),
                )
                return f"[AI 返回格式异常] 未找到 choices 节点。详情见日志：{self.get_log_path()}"

            logger.warning(
                "request_id=%s | http_error | status=%s | elapsed=%s | body=%s",
                request_id,
                response.status_code,
                elapsed,
                self._preview_text(response.text, 400),
            )
            return (
                f"[AI 请求错误] HTTP {response.status_code}。"
                f" 详情见日志：{self.get_log_path()}"
            )
        except requests.exceptions.ReadTimeout:
            elapsed = round(time.perf_counter() - started_at, 2)
            logger.exception(
                "request_id=%s | read_timeout | elapsed=%s | configured_timeout=%s | effective_timeout=%s | model=%s",
                request_id,
                elapsed,
                cfg["configured_timeout"],
                cfg["timeout"],
                cfg["model"],
            )
            return (
                f"[网络异常] AI 响应超时（{cfg['timeout']}秒）。"
                f" 当前模型或输出长度可能偏大。"
                f" 详情见日志：{self.get_log_path()}"
            )
        except requests.exceptions.ConnectTimeout:
            elapsed = round(time.perf_counter() - started_at, 2)
            logger.exception(
                "request_id=%s | connect_timeout | elapsed=%s | timeout=%s | api_base=%s",
                request_id,
                elapsed,
                cfg["timeout"],
                cfg["api_base"],
            )
            return f"[网络异常] 连接 AI 服务超时。详情见日志：{self.get_log_path()}"
        except requests.exceptions.ConnectionError:
            elapsed = round(time.perf_counter() - started_at, 2)
            logger.exception(
                "request_id=%s | connection_error | elapsed=%s | api_base=%s",
                request_id,
                elapsed,
                cfg["api_base"],
            )
            return f"[网络异常] 无法连接 AI 服务。详情见日志：{self.get_log_path()}"
        except Exception:
            elapsed = round(time.perf_counter() - started_at, 2)
            logger.exception(
                "request_id=%s | unexpected_error | elapsed=%s",
                request_id,
                elapsed,
            )
            return f"[内部异常] AI 调用失败。详情见日志：{self.get_log_path()}"
