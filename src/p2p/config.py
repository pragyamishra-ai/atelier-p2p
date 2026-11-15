from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    poe_api_key: str = ""
    llm_model: str = ""
    llm_base_url: str = "https://api.poe.com/v1"
    seed: int = 42
    data_dir: Path = Path("data")

    @property
    def generated_dir(self) -> Path:
        return self.data_dir / "generated"


settings = Settings()
