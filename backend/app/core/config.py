from pydantic_settings import BaseSettings
from pathlib import Path


class Settings(BaseSettings):
    # App
    APP_NAME: str = "Pax Venture"
    DEBUG: bool = False

    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:///./data/runtime/pax_venture.db"

    # LLM
    LLM_API_KEY: str = ""
    LLM_BASE_URL: str = "https://api.openai.com/v1"
    LLM_MODEL: str = "gpt-4o"
    LLM_MAX_TOKENS: int = 4096

    # Game
    STARTING_CASH: float = 10_000_000  # $10M
    MAX_MONTHS: int = 24
    MONTHS_PER_TURN: int = 1

    # Data paths
    DATA_DIR: Path = Path(__file__).parent.parent.parent.parent / "data"
    PLAYERS_DIR: Path = Path("")  # resolved at startup

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    def model_post_init(self, __context):
        if not self.PLAYERS_DIR or str(self.PLAYERS_DIR) == ".":
            self.PLAYERS_DIR = self.DATA_DIR / "players"


settings = Settings()
