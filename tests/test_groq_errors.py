"""Classificação de falhas Groq sem chamadas de rede."""

import httpx
import pytest
from groq import (
    APIConnectionError,
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    PermissionDeniedError,
    RateLimitError,
)

from iica_csv.agents.groq_errors import (
    AUTHENTICATION_MESSAGE,
    CONNECTION_MESSAGE,
    GENERIC_MESSAGE,
    PERMISSION_MESSAGE,
    RATE_LIMIT_MESSAGE,
    TIMEOUT_MESSAGE,
    TOOL_VALIDATION_MESSAGE,
    classify_groq_error,
)


def _response(status: int) -> httpx.Response:
    request = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")
    return httpx.Response(status, request=request)


@pytest.mark.parametrize(
    "body",
    [
        {"error": {"code": "tool_use_failed", "message": "invalid tool"}},
        {"error": {"failed_generation": "<sensitive tool payload>"}},
    ],
)
def test_classifies_bad_request_tool_validation_without_leaking_body(body) -> None:
    error = BadRequestError("400 bad request", response=_response(400), body=body)

    message = classify_groq_error(error)

    assert message == TOOL_VALIDATION_MESSAGE
    assert "sensitive" not in message


def test_classifies_generic_bad_request() -> None:
    error = BadRequestError(
        "400 invalid request containing GROQ_API_KEY=secret",
        response=_response(400),
        body={"error": {"code": "invalid_request_error"}},
    )
    assert classify_groq_error(error) == GENERIC_MESSAGE


@pytest.mark.parametrize(
    ("error_type", "status", "expected"),
    [
        (AuthenticationError, 401, AUTHENTICATION_MESSAGE),
        (PermissionDeniedError, 403, PERMISSION_MESSAGE),
        (RateLimitError, 429, RATE_LIMIT_MESSAGE),
    ],
)
def test_classifies_http_status_errors(error_type, status: int, expected: str) -> None:
    error = error_type("provider failure", response=_response(status), body={})
    assert classify_groq_error(error) == expected


def test_classifies_timeout_before_connection_parent() -> None:
    request = httpx.Request("POST", "https://api.groq.com")
    assert classify_groq_error(APITimeoutError(request=request)) == TIMEOUT_MESSAGE


def test_classifies_connection_error() -> None:
    request = httpx.Request("POST", "https://api.groq.com")
    assert (
        classify_groq_error(
            APIConnectionError(message="connection failed", request=request)
        )
        == CONNECTION_MESSAGE
    )


def test_classifies_unknown_error() -> None:
    assert classify_groq_error(RuntimeError("internal sensitive detail")) == GENERIC_MESSAGE
