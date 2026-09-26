from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', extra='ignore')

    app_name: str = 'Alibi API'
    environment: str = 'development'
    database_url: str
    supabase_url: str = 'https://zipzifhzgyjtiifhhsxy.supabase.co'
    supabase_publishable_key: str = 'sb_publishable___EaI8xGTvQvbkAY3m1eRA_Nvym7cOc'

    # Keep the OpenAI key server-side only. In AWS, inject it from Secrets Manager.
    openai_api_key: str | None = None
    openai_model: str = 'gpt-6-luna'
    openai_timeout_seconds: float = 30.0
    openai_max_output_tokens: int = 400

    cors_origins: str = '*'

    @property
    def cors_origin_list(self) -> list[str]:
        if self.cors_origins.strip() == '*':
            return ['*']
        return [item.strip() for item in self.cors_origins.split(',') if item.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
