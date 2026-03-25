from __future__ import annotations

try:
    from openai import BadRequestError, OpenAI
except ImportError:  # pragma: no cover
    OpenAI = None

    class BadRequestError(Exception):
        pass

from .config import Config
from .utils import retry_on_failure, setup_logger

logger = setup_logger(__name__)


class LLMClient:
    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        self.client = None
        self.model = ""
        self._setup_client()

    def _setup_client(self) -> None:
        if OpenAI is None:
            raise RuntimeError("缺少 openai 依赖，请先安装 requirements.txt")

        provider = self.cfg.llm_provider.lower()
        if provider == "deepseek":
            if not self.cfg.deepseek_key:
                raise ValueError("DeepSeek API Key 未设置")
            self.client = OpenAI(
                api_key=self.cfg.deepseek_key,
                base_url="https://api.deepseek.com",
            )
            self.model = self.cfg.llm_model or "deepseek-chat"
        elif provider == "openai":
            if not self.cfg.openai_key:
                raise ValueError("OpenAI API Key 未设置")
            self.client = OpenAI(api_key=self.cfg.openai_key)
            self.model = self.cfg.llm_model or "gpt-4o-mini"
        else:
            raise ValueError(f"不支持的 LLM_PROVIDER: {self.cfg.llm_provider}")

        logger.info("🔧 LLM 初始化完成 → provider=%s model=%s", self.cfg.llm_provider, self.model)

    def _supports_sampling(self) -> bool:
        return "reasoner" not in self.model

    def _build_params(self, prompt: str, max_tokens: int, temperature: float, top_p: float):
        messages = [
            {
                "role": "system",
                "content": "你是一个专业的个人效率助手，善于总结任务完成情况并给出实用建议。请用中文回复，保持简洁有条理。",
            },
            {"role": "user", "content": prompt},
        ]
        params = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
        }
        if self._supports_sampling():
            params["temperature"] = temperature
            params["top_p"] = top_p
        return params

    @retry_on_failure(max_retries=3)
    def ask_llm(
        self,
        prompt: str,
        max_tokens: int = 1500,
        temperature: float = 0.7,
        top_p: float = 0.9,
    ) -> str:
        params = self._build_params(prompt, max_tokens, temperature, top_p)
        try:
            response = self.client.chat.completions.create(**params)
            message = response.choices[0].message
            content = (message.content or "").strip()
            if not content and getattr(message, "reasoning_content", None):
                content = message.reasoning_content.strip()
            if not content:
                content = "[❗模型返回空 content 与 reasoning_content]"
            logger.info("LLM 返回字数：%s", len(content))
            return content
        except BadRequestError as exc:
            logger.error("LLM 调用失败 (BadRequest): %s", exc)
            return f"[LLM 调用失败] {exc}"
        except Exception as exc:
            logger.error("LLM 调用失败: %s", exc)
            return f"[LLM 调用失败] {exc}"
