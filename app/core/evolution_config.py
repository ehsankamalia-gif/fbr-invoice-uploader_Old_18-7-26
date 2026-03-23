import os
import logging
from pathlib import Path
from dotenv import load_dotenv
from pydantic import BaseModel, Field, field_validator
from typing import Optional

logger = logging.getLogger(__name__)

# Load .env from project root
env_path = Path(__file__).resolve().parent.parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

class EvolutionSettings(BaseModel):
    """Configuration for Evolution API integration."""
    API_URL: str = Field(default_factory=lambda: os.getenv("EVOLUTION_API_URL_BASE", "http://localhost:8082"))
    GLOBAL_API_KEY: str = Field(default_factory=lambda: os.getenv("EVOLUTION_GLOBAL_API_KEY", "B6D711FCDE4D4FD5936544120E713976"))
    INSTANCE_NAME: str = Field(default_factory=lambda: os.getenv("EVOLUTION_INSTANCE_NAME", "whatapps2"))
    
    @field_validator("API_URL")
    @classmethod
    def validate_url(cls, v):
        if not v.startswith("http"):
            raise ValueError("EVOLUTION_API_URL_BASE must start with http:// or https://")
        return v.rstrip('/')

    @field_validator("GLOBAL_API_KEY")
    @classmethod
    def validate_key(cls, v):
        if not v or len(v) < 10:
            raise ValueError("EVOLUTION_GLOBAL_API_KEY is missing or invalid")
        return v

def get_evolution_settings() -> EvolutionSettings:
    """Initialize and validate settings."""
    try:
        settings = EvolutionSettings()
        logger.info(f"Evolution API settings loaded: URL={settings.API_URL}")
        return settings
    except Exception as e:
        logger.error(f"Failed to load Evolution settings: {e}")
        # Return defaults for robustness if .env is missing, but log the error
        return EvolutionSettings()

evolution_settings = get_evolution_settings()
