from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    anthropic_api_key: str = ""
    anthropic_model: str = ""
    seed: int = 42
    data_dir: Path = Path("data")

    @property
    def generated_dir(self) -> Path:
        return self.data_dir / "generated"


settings = Settings()
