from pydantic_settings import BaseSettings

class AISettings(BaseSettings):
    llm_provider: str = "openai"
    openai_api_key: str | None = None
    deepseek_api_key: str | None = None

ai_settings = AISettings(_env_file='.env')
