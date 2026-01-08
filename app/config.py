"""
Application configuration - loads from environment variables
"""
from pydantic_settings import BaseSettings
from typing import Optional
from functools import lru_cache


class Settings(BaseSettings):
    # App
    app_name: str = "Procurement API"
    app_version: str = "1.0.0"
    debug: bool = False
    
    # Database
    database_url: str = "postgresql://procurement:procurement@localhost:5432/procurement"
    
    # File Storage
    upload_dir: str = "./uploads"
    max_upload_size_mb: int = 25
    allowed_extensions: str = "pdf,doc,docx,xls,xlsx,png,jpg,jpeg,csv"
    
    # Auth
    secret_key: str = "change-me-in-production-use-openssl-rand-hex-32"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 480  # 8 hours
    
    # API Keys (simple auth for now)
    api_keys: str = ""  # Comma-separated list of valid API keys
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
