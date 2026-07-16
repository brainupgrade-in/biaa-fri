"""Application configuration."""

from __future__ import annotations

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # LLM
    llm_api_key: str = ""
    llm_model: str = "llama-3.1-8b-instant"  # Groq model
    llm_temperature: float = 0.0

    # Groq API key (loaded from .env)
    groq_api_key: str = ""
    ollama_api_key: str = ""

    # Database. Defaults to embedded SQLite so the app runs as a single
    # container; point at Postgres by setting DATABASE_URL.
    database_url: str = "sqlite:///./data/app.db"

    # Vector store
    chroma_host: str = "localhost"
    chroma_port: int = 8000
    chroma_persist_dir: str = "./data/chroma_db"

    # Computation sandbox
    sandbox_host: str = "localhost"
    sandbox_port: int = 8080
    computation_timeout: int = 5

    # Anomaly detection
    z_score_threshold: float = 2.0
    materiality_threshold: float = 0.10

    # Precision
    precision_decimals: int = 2

    # Guardrail
    advisory_keywords: list[str] = [
        "you should", "recommend", "buy", "sell", "hold",
        "overweight", "underweight", "outperform", "underperform",
        "suggest", "advise", "opinion",
    ]
    advisory_patterns: list[str] = [
        r"should (I|we) (buy|sell|hold|invest)",
        r"(recommend|suggest) (buying|selling|holding)",
        r"(overweight|underweight|outperform|underperform)",
    ]

    # Trade tool
    trade_tool_enabled: bool = True

    # Performance
    max_concurrent_sessions: int = 100

    # Environment
    environment: str = "development"
    log_level: str = "INFO"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "allow"}


settings = Settings()
