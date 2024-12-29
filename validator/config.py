from pydantic import BaseSettings, validator
from pathlib import Path

class Settings(BaseSettings):
    """Application settings"""
    # Bitcoin node settings
    bitcoin_rpc_host: str = "localhost"
    bitcoin_rpc_port: int = 18443
    bitcoin_rpc_user: str = "user"
    bitcoin_rpc_password: str = "password"

    # Database settings
    database_url: str = "sqlite:///validator.db"

    # Security settings
    secret_key: str = "your-secret-key-here"
    token_expire_minutes: int = 30

    # API settings
    api_rate_limit: int = 100
    api_rate_limit_period: int = 60

    @validator('database_url')
    def validate_database_url(cls, v: str) -> str:
        # If it's just a path, convert it to sqlite URL format
        if not v.startswith('sqlite:///'):
            v = f"sqlite:///{v}"
        return v

    class Config:
        env_file = ".env"
        case_sensitive = False

def get_settings() -> Settings:
    """Get application settings"""
    return Settings() 