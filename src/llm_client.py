# src/llm_client.py - 🔄 支持多模型
"""
LLMClient  —— 统一封装 DeepSeek / OpenAI 聊天模型
-------------------------------------------------
依赖版本：
    pip install "openai>=1.17.0"
"""

from __future__ import annotations

from typing import Any, Dict
from openai import OpenAI          # ✅ 新版 SDK 都从这里 import
from .config import Config
from .utils import retry_on_failure, setup_logger

logger = setup_logger(__name__)


class LLMClient:
    """支持 DeepSeek 与 OpenAI 的聊天补全封装"""

    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        self.client: OpenAI        # 声明类型
        self.model: str
        self._setup_client()

    # --------------------------------------------------------------------- #
    # 初始化
    # --------------------------------------------------------------------- #
    def _setup_client(self) -> None:
        """根据 env 配置实例化 OpenAI / DeepSeek 客户端"""
        if self.cfg.llm_provider.lower() == "deepseek":
            if not self.cfg.deepseek_key:
                raise ValueError("DeepSeek API Key 未设置")

            # ⚠️ base_url **不带** /v1
            self.client = OpenAI(
                api_key=self.cfg.deepseek_key,
                base_url="https://api.deepseek.com",
            )
            self.model = self.cfg.llm_model or "deepseek-reasoner"

        elif self.cfg.llm_provider.lower() == "openai":
            if not self.cfg.openai_key:
                raise ValueError("OpenAI API Key 未设置")

            self.client = OpenAI(api_key=self.cfg.openai_key)
            self.model = self.cfg.llm_model or "gpt-3.5-turbo"

        else:
            raise ValueError(f"不支持的 LLM_PROVIDER: {self.cfg.llm_provider}")

        logger.info(f"🔧 LLM 初始化完成 → provider={self.cfg.llm_provider}  model={self.model}")

    # --------------------------------------------------------------------- #
    # 调用
    # --------------------------------------------------------------------- #
    @retry_on_failure(max_retries=3)
    def ask_llm(
            self,
            prompt: str,
            max_tokens: int = 800,
            temperature: float = 0.7,
    ) -> str:
        """
        向 LLM 发送 prompt，返回文本
        """
        system_msg = (
            "你是一个专业的个人效率助手，善于总结任务完成情况并给出实用建议。"
            "请用中文回复，保持简洁有条理。"
        )
        messages: list[Dict[str, str]] = [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": prompt},
        ]

        try:
            # ✅ 动态构建请求参数
            params = {
                "model": self.model,
                "messages": messages,
                "max_tokens": max_tokens,
            }

            # 只有当模型不是 deepseek-reasoner 时，才添加 temperature 和 top_p
            if self.model != "deepseek-reasoner":
                params["temperature"] = temperature
                params["top_p"] = 0.9

            # 使用 **params 解包传递参数
            resp = self.client.chat.completions.create(**params)

            content = resp.choices[0].message.content.strip()
            logger.info(f"LLM 响应字数：{len(content)}")
            return content

        except Exception as e:
            logger.error(f"LLM 调用失败: {e}")
            return f"[LLM 调用失败] {e}"

