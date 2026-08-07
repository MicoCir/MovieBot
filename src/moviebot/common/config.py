from pydantic import SecretStr
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Configuración centralizada del proyecto MovieBot."""

    openai_api_key: SecretStr
    openai_model: str
    openai_base_url: str | None = None
    tmdb_api_key: SecretStr
    meilisearch_url: str = "http://localhost:7700"
    meilisearch_api_key: SecretStr | None = None
    meilisearch_index: str = "netflix"
    log_level: str = "INFO"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}
