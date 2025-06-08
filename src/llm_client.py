# src/llm_client.py

from __future__ import annotations
from typing import Dict
from openai import OpenAI, BadRequestError
from .config import Config
from .utils import retry_on_failure, setup_logger

logger = setup_logger(__name__)

class LLMClient:
    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        self.client: OpenAI
        self.model: str
        self._setup_client()

    # ------------------------------------------------------------------
    # 初始化：根据 provider 创建 Client，并设定默认模型
    # ------------------------------------------------------------------
    def _setup_client(self) -> None:
        provider = self.cfg.llm_provider.lower()

        if provider == "deepseek":
            if not self.cfg.deepseek_key:
                raise ValueError("DeepSeek API Key 未设置")
            self.client = OpenAI(
                api_key=self.cfg.deepseek_key,
                base_url="https://api.deepseek.com",
            )
            # 默认 reasoner，可通过 cfg 覆盖
            self.model = self.cfg.llm_model or "deepseek-reasoner"

        elif provider == "openai":
            if not self.cfg.openai_key:
                raise ValueError("OpenAI API Key 未设置")
            self.client = OpenAI(api_key=self.cfg.openai_key)
            self.model = self.cfg.llm_model or "gpt-3.5-turbo"

        else:
            raise ValueError(f"不支持的 LLM_PROVIDER: {self.cfg.llm_provider}")

        logger.info(f"🔧 LLM 初始化完成 → provider={self.cfg.llm_provider}  model={self.model}")

    # ------------------------------------------------------------------
    # 主接口：向 LLM 发送 prompt，拿回回答
    # ------------------------------------------------------------------
    @retry_on_failure(max_retries=3)
    def ask_llm(
        self,
        prompt: str,
        max_tokens: int = 800,
        temperature: float = 0.7,
    ) -> str:
        system_msg = (
            "你是一个专业的个人效率助手，善于总结任务完成情况并给出实用建议。"
            "请用中文回复，保持简洁有条理。"
        )
        messages: list[Dict[str, str]] = [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": prompt},
        ]

        params = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

        try:
            resp = self.client.chat.completions.create(**params)
            msg = resp.choices[0].message

            # ① 先取标准 content
            content = (msg.content or "").strip()

            # ② 如为空，回退 reasoning_content（reasoner 专属字段）
            if not content and getattr(msg, "reasoning_content", None):
                content = msg.reasoning_content.strip()

            # ③ 依旧为空，给出占位文本，便于后续排查
            if not content:
                content = "[❗模型返回空 content 与 reasoning_content]"

            logger.info(f"LLM 返回字数：{len(content)}")
            return content

        except BadRequestError as e:
            logger.error(f"LLM 调用失败 (BadRequest): {e}")
            return f"[LLM 调用失败] {e}"
        except Exception as e:
            logger.error(f"LLM 调用失败: {e}")
            return f"[LLM 调用失败] {e}"
