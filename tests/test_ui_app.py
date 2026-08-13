"""Smoke tests da aplicação Streamlit sem rede nem chave Groq."""

from io import BytesIO
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from streamlit.testing.v1 import AppTest

from iica_csv.ui.app import (
    _assistant_history_message,
    _format_file_size,
    _history_results,
)


APP_PATH = Path(__file__).resolve().parents[1] / "src/iica_csv/ui/app.py"


def _demo_zip() -> bytes:
    target = BytesIO()
    dictionary = {
        "datasets": {
            "dados.csv": {
                "descricao": "Dados de teste",
                "colunas": {"VALOR TOTAL": {"descricao": "Valor monetário"}},
            }
        }
    }
    with ZipFile(target, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("dados.csv", "ID,VALOR TOTAL\n001,10.5\n002,20.0\n")
        archive.writestr(
            "dicionario_dados.json",
            json.dumps(dictionary, ensure_ascii=False).encode("utf-8"),
        )
    return target.getvalue()


def test_app_starts_and_keeps_query_unavailable_without_data(monkeypatch) -> None:
    # Uma string vazia bloqueia o fallback para um eventual .env local.
    monkeypatch.setenv("GROQ_API_KEY", "")

    app = AppTest.from_file(str(APP_PATH)).run(timeout=20)

    assert not app.exception
    assert not app.error
    assert len(app.get("file_uploader")) == 1
    assert app.get("file_uploader")[0].proto.max_upload_size_mb == 500
    assert not app.chat_input
    assert app.session_state["pending_clarification"] is None
    markup = " ".join(item.value for item in app.markdown)
    assert "IICA-CSV" in markup
    assert "Intelligent CSV Analytics" in markup


def test_upload_enables_disabled_chat_and_shows_dictionary(monkeypatch) -> None:
    # O teste precisa permanecer sem rede mesmo quando o desenvolvedor usa .env.
    monkeypatch.setenv("GROQ_API_KEY", "")
    app = AppTest.from_file(str(APP_PATH)).run(timeout=20)
    app.get("file_uploader")[0].upload(
        "demo.zip", _demo_zip(), "application/zip"
    ).run(timeout=20)

    next(button for button in app.button if button.label == "Processar pacote").click().run(
        timeout=20
    )

    assert not app.exception
    assert not app.error
    assert any("Carga concluída" in item.value for item in app.success)
    assert any("Dicionário de dados identificado" in item.value for item in app.success)
    assert len(app.chat_input) == 1
    assert app.chat_input[0].disabled is True
    metrics = {item.label: item.value for item in app.metric}
    assert metrics == {
        "Datasets": "1",
        "Registros": "2",
        "Dicionário": "Identificado",
    }

    app.session_state["pending_clarification"] = "contexto de teste"
    next(
        button for button in app.button
        if button.label == "Limpar histórico da conversa"
    ).click().run(timeout=20)
    assert app.session_state["pending_clarification"] is None


def test_chat_history_preserves_all_evidences_and_legacy_fallback() -> None:
    supplier = {"summary": "maior fornecedor", "rows": [{"nome": "F2"}]}
    client = {"summary": "maior cliente", "rows": [{"nome": "C2"}]}

    message = _assistant_history_message("F2 e C2 lideram.", [supplier, client])

    assert message["results"] == [supplier, client]
    assert _history_results(message) == [supplier, client]
    assert _history_results({"result": supplier}) == [supplier]


def test_file_size_format_is_readable() -> None:
    assert _format_file_size(512) == "512 B"
    assert _format_file_size(1536) == "1.5 KB"
    assert _format_file_size(None) == "tamanho não informado"
