from pydantic_settings import BaseSettings
from functools import lru_cache
import os
from dotenv import load_dotenv

load_dotenv()

class Settings(BaseSettings):
    # Bitcoin Node Settings
    BITCOIN_RPC_HOST: str = "127.0.0.1"
    BITCOIN_RPC_PORT: int = 18443
    BITCOIN_RPC_USER: str = os.getenv("BITCOIN_RPC_USER", "")
    BITCOIN_RPC_PASSWORD: str = os.getenv("BITCOIN_RPC_PASSWORD", "")
    
    # Database Settings
    DATABASE_URL: str = "tokens.db"
    
    # API Settings
    API_HOST: str = "127.0.0.1"
    API_PORT: int = 8000
    
    class Config:
        env_file = ".env"

@lru_cache()
def get_settings():
    return Settings() 