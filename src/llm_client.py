# src/llm_client.py - 🔄 支持多模型
import openai
from typing import Dict, Any, Optional
from .config import Config
from .utils import retry_on_failure, setup_logger

logger = setup_logger(__name__)


class LLMClient:
    def __init__(self, config: Config):
        self.config = config
        self._setup_client()

    def _setup_client(self):
        """设置LLM客户端"""
        if self.config.llm_provider == "deepseek":
            if not self.config.deepseek_key:
                raise ValueError("DeepSeek API密钥未设置")
            openai.api_key = self.config.deepseek_key
            openai.api_base = "https://api.deepseek.com/v1"
            self.model = "deepseek-chat"
        elif self.config.llm_provider == "openai":
            if not self.config.openai_key:
                raise ValueError("OpenAI API密钥未设置")
            openai.api_key = self.config.openai_key
            self.model = "gpt-3.5-turbo"
        else:
            raise ValueError(f"不支持的LLM提供商: {self.config.llm_provider}")

    @retry_on_failure(max_retries=3)
    def ask_llm(self, prompt: str, max_tokens: int = 800, temperature: float = 0.7) -> str:
        """调用LLM生成回复"""
        try:
            messages = [
                {
                    "role": "system",
                    "content": "你是一个专业的个人效率助手，善于总结任务完成情况并给出实用建议。请用中文回复，保持简洁有条理。"
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ]

            response = openai.ChatCompletion.create(
                model=self.model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
                top_p=0.9
            )

            content = response.choices[0].message.content.strip()
            logger.info(f"LLM响应长度: {len(content)} 字符")
            return content

        except Exception as e:
            logger.error(f"LLM调用失败: {e}")
            return f"AI总结生成失败: {str(e)}"