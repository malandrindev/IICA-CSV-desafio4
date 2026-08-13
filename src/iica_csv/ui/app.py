"""Aplicação Streamlit do MVP IICA-CSV."""

from __future__ import annotations

import logging
from dataclasses import asdict, is_dataclass
from pathlib import Path
import sys
from typing import Any, Mapping


# Permite o comando documentado sem exigir instalação editável do pacote ``src``.
SRC_DIR = Path(__file__).resolve().parents[2]
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import pandas as pd
import streamlit as st

from iica_csv.agents.csv_agent import (
    AgentConfigurationError,
    AgentExecutionError,
    create_csv_agent,
)
from iica_csv.config import ConfigurationError, Settings, get_settings
from iica_csv.processing.zip_processor import ZipProcessingError, ZipProcessor
from iica_csv.ui.rendering import (
    render_tool_results,
    result_payload,
)
from iica_csv.ui.styles import apply_app_styles


LOGGER = logging.getLogger(__name__)


def main() -> None:
    """Renderiza as interfaces de carga e consulta no mesmo aplicativo."""

    st.set_page_config(
        page_title="IICA-CSV | Intelligent CSV Analytics",
        page_icon="📊",
        layout="wide",
        initial_sidebar_state="collapsed",
    )
    apply_app_styles()
    _render_header()

    try:
        settings = get_settings()
    except ConfigurationError as exc:
        st.error(f"Configuração inválida: {exc}")
        st.stop()
        return

    logging.basicConfig(
        level=getattr(logging, settings.log_level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    _initialize_session()
    _render_load_interface(settings)
    _render_query_interface(settings)


def _render_header() -> None:
    """Apresenta a marca sem interpolar conteúdo dinâmico em HTML."""

    st.markdown(
        """
        <section class="iica-hero">
          <div class="iica-brand-row">
            <span class="iica-brand-mark" aria-hidden="true">▦</span>
            <div>
              <div class="iica-brand-title">IICA-CSV</div>
              <div class="iica-brand-kicker">Intelligent CSV Analytics</div>
            </div>
          </div>
          <p class="iica-hero-copy">
            Consulte dados de arquivos CSV em linguagem natural com IA e
            cálculos determinísticos executados localmente.
          </p>
        </section>
        """,
        unsafe_allow_html=True,
    )


def _section_heading(eyebrow: str, title: str, description: str) -> None:
    """Cria hierarquia de seção com componentes seguros do Streamlit."""

    st.caption(eyebrow.upper())
    st.subheader(title)
    st.caption(description)


def _initialize_session() -> None:
    defaults = {
        "data_manager": None,
        "processed_package": None,
        "csv_agent": None,
        "chat_history": [],
        "pending_clarification": None,
        "loaded_upload_identity": None,
        "upload_change_pending": False,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def _render_load_interface(settings: Settings) -> None:
    _section_heading(
        "01 · Ingestão",
        "📦 Carregue seu pacote de dados",
        (
            "Envie um ZIP com um ou mais CSVs. O dicionário JSON/CSV será usado "
            "quando estiver presente no pacote."
        ),
    )
    upload_card = st.container(key="upload_card", border=True)
    with upload_card:
        uploaded_file = st.file_uploader(
            "Arquivo ZIP",
            type=["zip"],
            max_upload_size=settings.app_max_upload_mb,
            help=(
                "Arraste o pacote ou selecione o arquivo. Tamanho compactado "
                f"máximo configurado: {settings.app_max_upload_mb} MB."
            ),
        )
        if uploaded_file is not None:
            st.caption(
                f"Arquivo selecionado: **{uploaded_file.name}** · "
                f"{_format_file_size(getattr(uploaded_file, 'size', None))}"
            )
    upload_identity = _upload_identity(uploaded_file) if uploaded_file else None
    st.session_state.upload_change_pending = bool(
        upload_identity
        and st.session_state.loaded_upload_identity
        and upload_identity != st.session_state.loaded_upload_identity
    )
    if st.session_state.upload_change_pending:
        st.warning(
            "Um novo ZIP foi selecionado, mas ainda não foi processado. A consulta "
            "ao pacote anterior ficará bloqueada até processar ou remover a seleção."
        )

    with upload_card:
        action_column, clear_column = st.columns([1.35, 1])
        process_clicked = action_column.button(
            "Processar pacote",
            type="primary",
            disabled=uploaded_file is None,
            width="stretch",
        )
        clear_clicked = clear_column.button(
            "Limpar dados da sessão",
            disabled=st.session_state.data_manager is None,
            width="stretch",
        )

    if clear_clicked:
        st.session_state.data_manager = None
        st.session_state.processed_package = None
        st.session_state.csv_agent = None
        st.session_state.chat_history = []
        st.session_state.pending_clarification = None
        st.session_state.loaded_upload_identity = None
        st.session_state.upload_change_pending = False
        st.success("Dados e histórico removidos desta sessão.")

    if process_clicked and uploaded_file is not None:
        _process_upload(uploaded_file, settings, upload_identity)

    package = st.session_state.processed_package
    manager = st.session_state.data_manager
    if package is not None and manager is not None and manager.has_data:
        _render_package_summary(package, manager)
    elif uploaded_file is None:
        st.info("Envie um arquivo ZIP para habilitar a interface de consulta.")


def _process_upload(
    uploaded_file: Any,
    settings: Settings,
    upload_identity: tuple[Any, ...] | None,
) -> None:
    # Libera o pacote anterior antes de uma carga potencialmente grande.
    st.session_state.data_manager = None
    st.session_state.processed_package = None
    st.session_state.csv_agent = None
    st.session_state.chat_history = []
    st.session_state.pending_clarification = None
    st.session_state.loaded_upload_identity = None
    processing_status = st.status(
        "Validando o pacote e interpretando os CSVs...",
        expanded=True,
        state="running",
    )
    try:
        with processing_status:
            st.write("Validando a estrutura segura do ZIP e lendo os arquivos CSV...")
            uploaded_file.seek(0)
            package = ZipProcessor(
                max_upload_mb=settings.app_max_upload_mb
            ).process(uploaded_file, filename=uploaded_file.name)
    except ZipProcessingError as exc:
        processing_status.update(
            label="Não foi possível processar o pacote.", state="error", expanded=True
        )
        st.error(str(exc))
        return
    except Exception:
        LOGGER.exception("Falha inesperada ao processar upload")
        processing_status.update(
            label="Não foi possível processar o pacote.", state="error", expanded=True
        )
        st.error(
            "Não foi possível processar o pacote. Confirme se o ZIP e os CSVs "
            "estão íntegros e tente novamente."
        )
        return

    with processing_status:
        st.write(
            f"✓ {len(package.csv_files)} arquivo(s) CSV identificado(s) e carregado(s)."
        )
        st.write(
            "✓ Dicionário de dados identificado."
            if package.dictionary_found
            else "• Dicionário de dados não identificado; schema inferido dos CSVs."
        )
        st.write("✓ Dados preparados em memória para consulta.")
    processing_status.update(
        label="Dados prontos para consulta", state="complete", expanded=False
    )

    st.session_state.data_manager = package.data_manager
    st.session_state.processed_package = package
    st.session_state.csv_agent = None
    st.session_state.chat_history = []
    st.session_state.pending_clarification = None
    st.session_state.loaded_upload_identity = upload_identity
    st.session_state.upload_change_pending = False
    st.success(
        f"Carga concluída: {len(package.csv_files)} CSV(s) e "
        f"{len(package.data_manager):,} dataset(s)."
    )


def _render_package_summary(package: Any, manager: Any) -> None:
    metadata_rows: list[dict[str, Any]] = []
    for metadata in manager.list_metadata():
        raw = _as_display_mapping(metadata)
        metadata_rows.append(
            {
                "dataset": _first(raw, "name", "nome", default=""),
                "linhas": _first(raw, "rows", "row_count", "numero_linhas"),
                "colunas": _first(
                    raw, "column_count", "columns_count", "numero_colunas"
                ),
                "encoding": raw.get("encoding", ""),
                "separador": _first(raw, "separator", "delimiter", default=""),
                "decimal": raw.get("decimal", ""),
                "dicionário": (
                    "Identificado" if raw.get("dictionary") else "Não identificado"
                ),
            }
        )

    total_rows = sum(int(row.get("linhas") or 0) for row in metadata_rows)
    with st.container(key="summary_card", border=True):
        st.markdown("#### Pacote processado")
        st.caption("Resumo dos dados disponíveis nesta sessão.")
        datasets_metric, rows_metric, dictionary_metric = st.columns(3)
        datasets_metric.metric(
            "Datasets",
            f"{len(metadata_rows):,}".replace(",", "."),
            icon="📄",
            border=True,
        )
        rows_metric.metric(
            "Registros",
            f"{total_rows:,}".replace(",", "."),
            icon="📊",
            border=True,
        )
        dictionary_metric.metric(
            "Dicionário",
            "Identificado" if package.dictionary_found else "Não identificado",
            icon="✅" if package.dictionary_found else "ℹ️",
            border=True,
        )

    st.markdown("#### Datasets carregados")
    st.caption("Metadados técnicos detectados durante a leitura dos CSVs.")
    st.dataframe(
        pd.DataFrame(metadata_rows),
        hide_index=True,
        width="stretch",
        column_config={
            "dataset": st.column_config.TextColumn("Dataset", width="large"),
            "linhas": st.column_config.NumberColumn("Linhas", format="localized"),
            "colunas": st.column_config.NumberColumn("Colunas", format="localized"),
            "encoding": st.column_config.TextColumn("Encoding"),
            "separador": st.column_config.TextColumn("Separador"),
            "decimal": st.column_config.TextColumn("Decimal"),
            "dicionário": st.column_config.TextColumn("Dicionário"),
        },
    )

    with st.expander("Arquivos encontrados no pacote", expanded=False):
        file_rows = [_as_display_mapping(item) for item in package.files]
        if file_rows and all("arquivo" not in row for row in file_rows):
            file_rows = [{"arquivo": str(item)} for item in package.files]
        st.dataframe(pd.DataFrame(file_rows), hide_index=True, width="stretch")

    if package.dictionary_found:
        names = ", ".join(package.dictionary_files)
        st.success(f"Dicionário de dados identificado: {names}")
    else:
        st.warning("Dicionário de dados não identificado no pacote.")
    for warning in package.warnings:
        if warning != "Dicionário de dados não identificado no pacote.":
            st.warning(warning)


def _render_query_interface(settings: Settings) -> None:
    st.divider()
    _section_heading(
        "02 · Análise",
        "💬 Consulte seus dados",
        (
            "Faça perguntas em linguagem natural. A IA interpreta a intenção; "
            "os cálculos são executados pelas ferramentas determinísticas."
        ),
    )
    manager = st.session_state.data_manager
    if manager is None or not manager.has_data:
        st.info("A consulta será habilitada depois de uma carga válida.")
        return
    if st.session_state.upload_change_pending:
        st.info("Processe o novo ZIP selecionado antes de continuar a consulta.")
        return

    if not settings.has_groq_api_key:
        st.warning(
            "GROQ_API_KEY não configurada. Copie `.env.example` para `.env`, "
            "preencha a chave e reinicie a aplicação. Os dados já carregados "
            "continuam visíveis nesta sessão."
        )

    if st.button("Limpar histórico da conversa"):
        st.session_state.chat_history = []
        st.session_state.pending_clarification = None

    with st.container(key="query_card", border=True):
        st.caption(
            "Exemplos: “Quais arquivos foram carregados?”, “Qual fornecedor "
            "recebeu o maior valor?” ou “Qual foi o total gasto por mês?”"
        )
        for message in st.session_state.chat_history:
            with st.chat_message(message["role"]):
                if message.get("is_error"):
                    st.error(message["content"])
                else:
                    _render_answer_text(message["content"], message["role"])
                render_tool_results(_history_results(message))

    question = st.chat_input(
        "Faça uma pergunta sobre os CSVs carregados",
        disabled=not settings.has_groq_api_key,
    )
    if not question:
        return

    model_history = [
        {"role": item["role"], "content": item["content"]}
        for item in st.session_state.chat_history
        if not item.get("is_error")
    ]
    st.session_state.chat_history.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)

    with st.chat_message("assistant"):
        try:
            if st.session_state.csv_agent is None:
                st.session_state.csv_agent = create_csv_agent(manager, settings)
            with st.spinner("Consultando os dados..."):
                response = st.session_state.csv_agent.ask(
                    question,
                    model_history,
                    pending_clarification=st.session_state.pending_clarification,
                )
            # O contrato devolvido substitui o anterior: ``None`` significa que
            # a continuação foi consumida ou que a pergunta era independente.
            st.session_state.pending_clarification = response.pending_clarification
            response_results = response.display_results or (
                [response.display_result] if response.display_result else []
            )
            payloads = [result_payload(result) for result in response_results]
            _render_answer_text(response.text, "assistant")
            render_tool_results(payloads)
            st.session_state.chat_history.append(
                _assistant_history_message(response.text, payloads)
            )
        except (AgentConfigurationError, AgentExecutionError) as exc:
            message = str(exc)
            st.error(message)
            st.session_state.chat_history.append(
                {
                    "role": "assistant",
                    "content": message,
                    "result": {},
                    "is_error": True,
                }
            )
        except Exception:
            LOGGER.exception("Falha inesperada na interface de consulta")
            message = "A consulta falhou sem alterar os dados. Tente novamente."
            st.error(message)
            st.session_state.chat_history.append(
                {
                    "role": "assistant",
                    "content": message,
                    "result": {},
                    "is_error": True,
                }
            )


def _as_display_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if hasattr(value, "to_dict"):
        return value.to_dict()
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, str):
        return {"arquivo": value}
    return {"valor": str(value)}


def _first(mapping: Mapping[str, Any], *names: str, default: Any = 0) -> Any:
    for name in names:
        if name in mapping:
            value = mapping[name]
            if isinstance(value, list) and "column" in name:
                return len(value)
            return value
    if "columns" in mapping and isinstance(mapping["columns"], list):
        return len(mapping["columns"])
    return default


def _upload_identity(uploaded_file: Any) -> tuple[Any, ...]:
    """Identifica a seleção sem copiar seu conteúdo potencialmente grande."""

    return (
        getattr(uploaded_file, "name", None),
        getattr(uploaded_file, "size", None),
        getattr(uploaded_file, "file_id", None),
    )


def _format_file_size(size: Any) -> str:
    """Formata somente a apresentação do tamanho informado pelo uploader."""

    if not isinstance(size, (int, float)) or size < 0:
        return "tamanho não informado"
    value = float(size)
    units = ("B", "KB", "MB", "GB")
    unit = units[0]
    for unit in units:
        if value < 1024 or unit == units[-1]:
            break
        value /= 1024
    return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"


def _render_answer_text(content: str, role: str) -> None:
    """Distingue visualmente a resposta sem modificar seu conteúdo."""

    if role == "assistant":
        st.markdown(
            '<div class="iica-answer-label">Resposta</div>',
            unsafe_allow_html=True,
        )
    st.markdown(content)


def _assistant_history_message(
    content: str, results: list[dict[str, Any]]
) -> dict[str, Any]:
    """Mantém juntas a resposta e todas as evidências que a sustentam."""

    return {"role": "assistant", "content": content, "results": list(results)}


def _history_results(message: Mapping[str, Any]) -> list[Any]:
    """Lê o contrato plural e preserva sessões criadas no formato singular."""

    results = message.get("results")
    if isinstance(results, list):
        return results
    legacy = message.get("result")
    return [legacy] if legacy else []


if __name__ == "__main__":
    main()
