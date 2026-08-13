"""Classificação segura e centralizada de falhas da API Groq."""

from __future__ import annotations

import json
from typing import Any, Mapping

try:
    import httpx
except ImportError:  # pragma: no cover - dependência transitiva de langchain-groq
    httpx = None  # type: ignore[assignment]

try:
    from groq import (
        APIConnectionError,
        APIStatusError,
        APITimeoutError,
        AuthenticationError,
        BadRequestError,
        PermissionDeniedError,
        RateLimitError,
    )
except ImportError:  # pragma: no cover - ambiente incompleto antes da instalação
    APIConnectionError = APIStatusError = APITimeoutError = ()  # type: ignore[assignment,misc]
    AuthenticationError = BadRequestError = PermissionDeniedError = ()  # type: ignore[assignment,misc]
    RateLimitError = ()  # type: ignore[assignment,misc]


AUTHENTICATION_MESSAGE = (
    "Não foi possível autenticar na Groq. Verifique a GROQ_API_KEY configurada."
)
PERMISSION_MESSAGE = "A Groq recusou a operação por falta de permissão."
RATE_LIMIT_MESSAGE = (
    "O limite temporário da API Groq foi atingido. Aguarde alguns segundos e "
    "tente novamente."
)
TOOL_VALIDATION_MESSAGE = (
    "A API não conseguiu validar a chamada de ferramenta gerada pelo modelo. "
    "Tente novamente."
)
TIMEOUT_MESSAGE = "A API demorou mais que o esperado para responder. Tente novamente."
CONNECTION_MESSAGE = (
    "Não foi possível conectar à API Groq no momento. Tente novamente."
)
GENERIC_MESSAGE = "Não foi possível concluir a consulta no momento."


def _status_code(exc: Exception) -> int | None:
    raw = getattr(exc, "status_code", None)
    if raw is None:
        response = getattr(exc, "response", None)
        raw = getattr(response, "status_code", None)
    try:
        return int(raw) if raw is not None else None
    except (TypeError, ValueError):
        return None


def _safe_error_text(exc: Exception) -> str:
    """Materializa apenas para classificação local; o texto nunca chega à UI."""

    fragments: list[str] = [str(exc)]
    body = getattr(exc, "body", None)
    if body is not None:
        try:
            fragments.append(json.dumps(body, ensure_ascii=False, default=str))
        except (TypeError, ValueError):
            fragments.append(str(type(body).__name__))
    return " ".join(fragments).casefold()


def _is_tool_validation_failure(exc: Exception) -> bool:
    body = getattr(exc, "body", None)
    error: Any = body.get("error") if isinstance(body, Mapping) else body
    if isinstance(error, Mapping):
        if str(error.get("code", "")).casefold() == "tool_use_failed":
            return True
        if "failed_generation" in error:
            return True
    text = _safe_error_text(exc)
    return any(
        marker in text
        for marker in (
            "tool_use_failed",
            "failed_generation",
            "tool call",
            "tool validation",
            "function call",
            "failed to call a function",
        )
    )


def classify_groq_error(exc: Exception) -> str:
    """Converte exceções externas em uma mensagem estável e não sensível."""

    status = _status_code(exc)

    timeout_types: tuple[type[BaseException], ...] = (TimeoutError,)
    connection_types: tuple[type[BaseException], ...] = (ConnectionError,)
    if httpx is not None:
        timeout_types += (httpx.TimeoutException,)
        connection_types += (httpx.NetworkError,)

    if isinstance(exc, APITimeoutError) or isinstance(exc, timeout_types):
        return TIMEOUT_MESSAGE
    if isinstance(exc, AuthenticationError) or status == 401:
        return AUTHENTICATION_MESSAGE
    if isinstance(exc, PermissionDeniedError) or status == 403:
        return PERMISSION_MESSAGE
    if isinstance(exc, RateLimitError) or status == 429:
        return RATE_LIMIT_MESSAGE
    if (isinstance(exc, BadRequestError) or status == 400) and _is_tool_validation_failure(
        exc
    ):
        return TOOL_VALIDATION_MESSAGE
    if isinstance(exc, APIConnectionError) or isinstance(exc, connection_types):
        return CONNECTION_MESSAGE
    if isinstance(exc, APIStatusError) or status is not None:
        return GENERIC_MESSAGE
    return GENERIC_MESSAGE


__all__ = [
    "AUTHENTICATION_MESSAGE",
    "CONNECTION_MESSAGE",
    "GENERIC_MESSAGE",
    "PERMISSION_MESSAGE",
    "RATE_LIMIT_MESSAGE",
    "TIMEOUT_MESSAGE",
    "TOOL_VALIDATION_MESSAGE",
    "classify_groq_error",
]
