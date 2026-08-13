"""Configurações centralizadas da aplicação.

Os valores vêm do ambiente; quando existe um arquivo ``.env`` na raiz do
projeto, ``python-dotenv`` o carrega sem sobrescrever variáveis já exportadas.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path

try:  # Mantém o módulo importável antes da instalação das dependências.
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - exercitado apenas em ambiente incompleto
    load_dotenv = None  # type: ignore[assignment]


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_GROQ_MODEL = "llama-3.3-70b-versatile"
DEFAULT_MAX_UPLOAD_MB = 500
DEFAULT_LOG_LEVEL = "INFO"


class ConfigurationError(ValueError):
    """Indica uma configuração inválida informada pelo ambiente."""


def _positive_integer(value: str | None, *, name: str, default: int) -> int:
    if value is None or not value.strip():
        return default
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ConfigurationError(f"{name} deve ser um número inteiro positivo.") from exc
    if parsed <= 0:
        raise ConfigurationError(f"{name} deve ser um número inteiro positivo.")
    return parsed


@dataclass(frozen=True, slots=True)
class Settings:
    """Configurações imutáveis usadas pelas camadas da aplicação."""

    groq_api_key: str | None = None
    groq_model: str = DEFAULT_GROQ_MODEL
    app_max_upload_mb: int = DEFAULT_MAX_UPLOAD_MB
    log_level: str = DEFAULT_LOG_LEVEL

    @property
    def has_groq_api_key(self) -> bool:
        """Informa se uma chave não vazia foi configurada."""

        return bool(self.groq_api_key and self.groq_api_key.strip())

    @classmethod
    def from_env(cls, env_file: str | Path | None = None) -> "Settings":
        """Carrega configurações do ``.env`` e das variáveis de ambiente.

        Variáveis já presentes no processo têm precedência sobre o arquivo.
        """

        dotenv_path = Path(env_file) if env_file is not None else PROJECT_ROOT / ".env"
        if load_dotenv is not None and dotenv_path.is_file():
            load_dotenv(dotenv_path=dotenv_path, override=False)

        api_key = os.getenv("GROQ_API_KEY")
        return cls(
            groq_api_key=api_key.strip() if api_key and api_key.strip() else None,
            groq_model=os.getenv("GROQ_MODEL", DEFAULT_GROQ_MODEL).strip()
            or DEFAULT_GROQ_MODEL,
            app_max_upload_mb=_positive_integer(
                os.getenv("APP_MAX_UPLOAD_MB"),
                name="APP_MAX_UPLOAD_MB",
                default=DEFAULT_MAX_UPLOAD_MB,
            ),
            log_level=os.getenv("LOG_LEVEL", DEFAULT_LOG_LEVEL).strip().upper()
            or DEFAULT_LOG_LEVEL,
        )


def get_settings(env_file: str | Path | None = None) -> Settings:
    """Retorna uma nova fotografia das configurações atuais."""

    return Settings.from_env(env_file)
