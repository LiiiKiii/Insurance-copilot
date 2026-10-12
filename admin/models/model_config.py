"""LLM and embedding model configuration models."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from admin.db import Base
from admin.utils import now_beijing


class ModelConfig(Base):
    __tablename__ = "model_configs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("tenants.id"), nullable=True)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)  # openrouter|anthropic|openai|azure
    model_id: Mapped[str] = mapped_column(String(200), nullable=False)  # anthropic/claude-3.5-sonnet
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    model_type: Mapped[str] = mapped_column(String(20), default="llm")  # llm|embedding|reranker
    category: Mapped[str] = mapped_column(String(20), default="chat")  # chat|embedding|multimodal|ocr|image_gen|asr|tts|rerank
    api_key_encrypted: Mapped[str | None] = mapped_column(String(500), nullable=True)
    base_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    max_tokens: Mapped[int] = mapped_column(Integer, default=4096)
    temperature: Mapped[float] = mapped_column(Float, default=0.7)
    price_per_1k_input: Mapped[float] = mapped_column(Float, default=0.0)
    price_per_1k_output: Mapped[float] = mapped_column(Float, default=0.0)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_beijing)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now_beijing, onupdate=now_beijing)
