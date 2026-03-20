"""
CodeOracle — Core Configuration
"""
import os
from pydantic_settings import BaseSettings
from pathlib import Path
from typing import Optional

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


class Settings(BaseSettings):
    # API Keys
    anthropic_api_key: str = ""
    gemini_api_key: str = ""
    model_name: str = "gemini-2.5-flash"

    # Embeddings & Vector DB
    embedding_model: str = "all-MiniLM-L6-v2"
    chroma_persist_dir: str = "./data/chroma"
    repos_dir: str = "./data/repos"

    # RAG Parameters
    max_file_size_kb: int = 500
    chunk_size: int = 800
    chunk_overlap: int = 150
    top_k_retrieval: int = 8

    # API
    frontend_url: str = "http://localhost:5173"
    log_level: str = "INFO"

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()

# Ensure Google SDK automatically detects the API key globally
if settings.gemini_api_key:
    os.environ["GOOGLE_API_KEY"] = settings.gemini_api_key

# Ensure dirs exist
for d in [settings.chroma_persist_dir, settings.repos_dir]:
    Path(d).mkdir(parents=True, exist_ok=True)
