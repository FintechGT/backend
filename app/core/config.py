from pydantic import BaseModel
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    DB_URL: str

    JWT_SECRET: str
    JWT_ALG: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    GOOGLE_CLIENT_ID: str = ""
feature/appi_catalogo
    ALLOWED_EMAIL_DOMAIN: str | None = None
    CORS_ORIGINS: str = "*"
    ROOT_PATH: str = ""
    DOCS_URL: str = "/docs"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True


settings = Settings()
