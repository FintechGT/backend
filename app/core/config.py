from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    DB_URL: str

    JWT_SECRET: str
    JWT_ALG: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    GOOGLE_CLIENT_ID: str = ""
    ALLOWED_EMAIL_DOMAIN: Optional[str] = None
    AUTH_GOOGLE_ONLY: bool = False
    CORS_ORIGINS: str = "*"
    ROOT_PATH: str = ""
    DOCS_URL: str = "/docs"


    CLOUDINARY_CLOUD_NAME: str = ""
    CLOUDINARY_API_KEY: str = ""
    CLOUDINARY_API_SECRET: str = ""
    CLOUDINARY_UPLOAD_PRESET: Optional[str] = None

    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
