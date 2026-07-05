import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

# Base workspace directory (dynamically resolved to the project root folder)
WORKSPACE_DIR = Path(__file__).resolve().parent.parent.parent

class Settings(BaseSettings):
    WORKSPACE_DIR: Path = WORKSPACE_DIR

    # App Settings
    APP_NAME: str = "Semantic EPUB Pipeline"
    
    # Paths (relative or absolute, defaulting within workspace)
    DATA_DIR: Path = WORKSPACE_DIR / "data"
    LOG_DIR: Path = WORKSPACE_DIR / "logs"
    PROMPTS_DIR: Path = WORKSPACE_DIR / "prompts"
    
    # Database
    DATABASE_URL: str = f"sqlite:///{WORKSPACE_DIR}/data/pipeline.db"
    
    # LLM Settings (Modular API Configuration)
    # Default to OpenAI compatible endpoint. Can support Gemini, OpenAI, etc.
    LLM_API_KEY: str = os.getenv("GEMINI_API_KEY") or os.getenv("OPENAI_API_KEY") or ""
    LLM_BASE_URL: str = "https://api.openai.com/v1"
    LLM_MODEL: str = "gpt-4o"  # or specific Gemini model like 'gemini-2.5-pro' / 'gemini-1.5-flash'
    
    # Settings configuration
    model_config = SettingsConfigDict(
        env_file=str(WORKSPACE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )

    def __init__(self, **values):
        super().__init__(**values)
        dynamic_path = str(WORKSPACE_DIR).replace('\\', '/')
        if self.DATABASE_URL:
            old_path = "d:/agentic_workflow"
            if old_path in self.DATABASE_URL:
                self.DATABASE_URL = self.DATABASE_URL.replace(old_path, dynamic_path)
            elif self.DATABASE_URL.startswith("sqlite:///data/"):
                self.DATABASE_URL = f"sqlite:///{dynamic_path}/" + self.DATABASE_URL[10:]
        else:
            self.DATABASE_URL = f"sqlite:///{dynamic_path}/data/pipeline.db"

    def create_required_directories(self):
        """Creates the required pipeline directories if they do not exist."""
        # Ensure base directories exist
        self.DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.LOG_DIR.mkdir(parents=True, exist_ok=True)
        self.PROMPTS_DIR.mkdir(parents=True, exist_ok=True)
        
        # Ensure database and intermediate data subdirs exist
        for subdir in ["input", "extracted", "formatted", "validated", "html", "epub"]:
            (self.DATA_DIR / subdir).mkdir(parents=True, exist_ok=True)

settings = Settings()
settings.create_required_directories()
