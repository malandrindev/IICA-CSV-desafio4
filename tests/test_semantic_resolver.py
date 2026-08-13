"""Regressões da escolha semântica de dataset, coluna e operação."""

import pandas as pd
import pytest

from iica_csv.agents.semantic_resolver import (
    PendingClarification,
    resolve_pending_clarification,
    resolve_semantic_intent,
    resolve_semantic_query,
)
from iica_csv.processing.data_manager import DataManager
from iica_csv.tools.data_tools import DataTools


@pytest.fixture
def semantic_manager() -> DataManager:
    """Catálogo adversarial com nomes artificiais e semântica no dicionário."""

    manager = DataManager()
    manager.add_dataset(
        "LoteDocumento",
        pd.DataFrame(
            {
                "Parte A": ["F1", "F2"],
                "Parte B": ["C1", "C2"],
                "Momento": pd.to_datetime(["2024-01-01", "2024-02-01"]),
                "Montante Documento": [100.0, 200.0],
            }
        ),
        data_dictionary={
            "descricao": "Registros no grão de cabeçalho de notas fiscais.",
            "colunas": {
                "Parte A": {
                    "descricao": "Nome ou razão social do emitente, fornecedor ou vendedor."
                },
                "Parte B": {
                    "descricao": "Nome do destinatário, cliente ou comprador da nota."
                },
                "Momento": {"descricao": "Data de emissão da nota fiscal."},
                "Montante Documento": {
                    "descricao": "Valor total da nota fiscal no cabeçalho."
                },
            },
        },
    )
    manager.add_dataset(
        "LoteLinha",
        pd.DataFrame(
            {
                "Parte A": ["F1", "F2", "F2", "F2"],
                "Parte B": ["C1", "C2", "C2", "C2"],
                "Momento": pd.to_datetime(
                    ["2024-01-01", "2024-02-01", "2024-02-01", "2024-02-01"]
                ),
                "Mercadoria": ["A", "B", "B", "B"],
                "Medida Física": [10.0, 1.0, 1.0, 1.0],
                "Montante Linha": [100.0, 50.0, 50.0, 50.0],
            }
        ),
        data_dictionary={
            "descricao": "Registros no grão de itens de notas fiscais.",
            "colunas": {
                "Parte A": {
                    "descricao": "Nome ou razão social do emitente, fornecedor ou vendedor."
                },
                "Parte B": {
                    "descricao": "Nome do destinatário, cliente ou comprador da nota."
                },
                "Momento": {"descricao": "Data de emissão da nota fiscal."},
                "Mercadoria": {
                    "descricao": "Descrição do produto ou serviço registrado no item."
                },
                "Medida Física": {
                    "descricao": "Quantidade ou volume comprado do item."
                },
                "Montante Linha": {
                    "descricao": "Valor total registrado para o item."
                },
            },
        },
    )
    return manager


@pytest.mark.parametrize("term", ["fornecedor", "supplier", "emitente", "vendedor"])
def test_supplier_aliases_use_issuer_name_and_invoice_total(
    semantic_manager: DataManager, term: str
) -> None:
    plan = resolve_semantic_intent(
        f"Qual {term} recebeu o maior valor no período?", semantic_manager
    )

    assert plan is not None
    assert plan.tool == "top_n"
    assert plan.dataset_name == "LoteDocumento"
    assert plan.group_by == ("Parte A",)
    assert plan.value_column == "Montante Documento"
    assert plan.operation == "sum"
    assert plan.n == 1
    assert plan.derived_from_dictionary is True


@pytest.mark.parametrize("term", ["destinatário", "cliente", "comprador"])
def test_recipient_aliases_use_recipient_name(
    semantic_manager: DataManager, term: str
) -> None:
    plan = resolve_semantic_intent(
        f"Qual {term} aparece com o maior valor?", semantic_manager
    )

    assert plan is not None
    assert plan.dataset_name == "LoteDocumento"
    assert plan.group_by == ("Parte B",)
    assert plan.value_column == "Montante Documento"
    assert plan.operation == "sum"


def test_top_five_suppliers_keeps_sum_and_requested_limit(
    semantic_manager: DataManager,
) -> None:
    plan = resolve_semantic_intent(
        "Quais foram os cinco maiores fornecedores por valor total?",
        semantic_manager,
    )

    assert plan is not None
    assert plan.tool == "top_n"
    assert plan.dataset_name == "LoteDocumento"
    assert plan.value_column == "Montante Documento"
    assert plan.n == 5
    assert plan.order == "desc"
    assert plan.operation == "sum"
    assert plan.group_by == ("Parte A",)


def test_product_volume_is_sum_of_quantity_not_count(
    semantic_manager: DataManager,
) -> None:
    plan = resolve_semantic_intent(
        "Qual produto apresentou o maior volume comprado?", semantic_manager
    )

    assert plan is not None
    assert plan.tool == "top_n"
    assert plan.dataset_name == "LoteLinha"
    assert plan.group_by == ("Mercadoria",)
    assert plan.value_column == "Medida Física"
    assert plan.operation == "sum"
    assert plan.operation != "count"
    assert plan.n == 1


@pytest.mark.parametrize(
    "question",
    ["Qual foi o total gasto?", "Qual é o valor total das notas?"],
)
def test_invoice_spend_uses_header_total(
    semantic_manager: DataManager, question: str
) -> None:
    plan = resolve_semantic_intent(question, semantic_manager)

    assert plan is not None
    assert plan.tool == "aggregate_data"
    assert plan.dataset_name == "LoteDocumento"
    assert plan.value_column == "Montante Documento"
    assert plan.operation == "sum"
    assert plan.group_by == ()


def test_monthly_spend_uses_header_date_and_invoice_total(
    semantic_manager: DataManager,
) -> None:
    plan = resolve_semantic_intent("Qual foi o gasto por mês?", semantic_manager)

    assert plan is not None
    assert plan.tool == "time_aggregation"
    assert plan.dataset_name == "LoteDocumento"
    assert plan.date_column == "Momento"
    assert plan.value_column == "Montante Documento"
    assert plan.operation == "sum"
    assert plan.period == "year-month"


@pytest.mark.parametrize(
    "question", ["Qual foi o total gasto em janeiro/2024?", "Total gasto em 01/2024?"]
)
def test_specific_month_still_uses_header_time_aggregation(
    semantic_manager: DataManager, question: str
) -> None:
    plan = resolve_semantic_intent(question, semantic_manager)

    assert plan is not None
    assert plan.tool == "time_aggregation"
    assert plan.dataset_name == "LoteDocumento"
    assert plan.date_column == "Momento"
    assert plan.value_column == "Montante Documento"
    assert plan.period == "year-month"


def test_explicit_item_value_uses_item_granularity(
    semantic_manager: DataManager,
) -> None:
    plan = resolve_semantic_intent(
        "Qual é o valor total dos itens?", semantic_manager
    )

    assert plan is not None
    assert plan.tool == "aggregate_data"
    assert plan.dataset_name == "LoteLinha"
    assert plan.value_column == "Montante Linha"
    assert plan.operation == "sum"


def test_list_suppliers_uses_issuer_column_without_forcing_financial_ranking(
    semantic_manager: DataManager,
) -> None:
    plan = resolve_semantic_intent("Quais fornecedores existem?", semantic_manager)

    assert plan is not None
    assert plan.tool == "unique_values"
    assert plan.dataset_name == "LoteDocumento"
    assert plan.column == "Parte A"


@pytest.mark.parametrize(
    "question",
    [
        "Qual é o maior fornecedor?",
        "Qual fornecedor teve uma soma maior?",
        "Qual fornecedor e cliente tiveram o maior valor?",
        "Qual é o total de notas fiscais?",
        "Top 5 fornecedores por quantidade de notas",
        "Qual fornecedor vendeu maior quantidade?",
        "Qual fornecedor recebeu o maior valor por mês?",
    ],
)
def test_materially_ambiguous_intentions_are_not_forced(
    semantic_manager: DataManager, question: str
) -> None:
    assert resolve_semantic_intent(question, semantic_manager) is None


def test_schema_names_are_a_conservative_fallback_without_dictionary() -> None:
    manager = DataManager()
    manager.add_dataset(
        "cabecalho",
        pd.DataFrame(
            columns=[
                "RAZÃO SOCIAL EMITENTE",
                "NOME DESTINATÁRIO",
                "DATA EMISSÃO",
                "VALOR NOTA FISCAL",
            ]
        ),
        source_name="202401_NFs_Cabecalho.csv",
    )
    manager.add_dataset(
        "itens",
        pd.DataFrame(
            columns=[
                "DESCRIÇÃO DO PRODUTO/SERVIÇO",
                "QUANTIDADE",
                "VALOR TOTAL",
            ]
        ),
        source_name="202401_NFs_Itens.csv",
    )

    supplier = resolve_semantic_intent(
        "Qual fornecedor recebeu o maior valor?", manager
    )
    volume = resolve_semantic_intent(
        "Qual produto apresentou o maior volume comprado?", manager
    )

    assert supplier is not None
    assert supplier.group_by == ("RAZÃO SOCIAL EMITENTE",)
    assert supplier.value_column == "VALOR NOTA FISCAL"
    assert supplier.derived_from_dictionary is False
    assert volume is not None
    assert volume.group_by == ("DESCRIÇÃO DO PRODUTO/SERVIÇO",)
    assert volume.value_column == "QUANTIDADE"
    assert volume.operation == "sum"
    assert volume.derived_from_dictionary is False


def test_opaque_schema_without_dictionary_is_not_guessed() -> None:
    manager = DataManager(
        {
            "A": pd.DataFrame({"x": [1], "y": [2]}),
            "B": pd.DataFrame({"z": [3], "w": [4]}),
        }
    )

    assert (
        resolve_semantic_intent("Qual fornecedor recebeu o maior valor?", manager)
        is None
    )


def test_time_intent_without_date_column_is_not_degraded_to_scalar_total() -> None:
    manager = DataManager()
    manager.add_dataset(
        "DocumentosSemData",
        pd.DataFrame({"Montante": [10.0]}),
        data_dictionary={
            "descricao": "Cabeçalho de notas fiscais.",
            "colunas": {
                "Montante": {"descricao": "Valor total da nota fiscal no cabeçalho."}
            },
        },
    )

    assert resolve_semantic_intent("Qual foi o gasto por mês?", manager) is None


def test_supplier_or_client_without_metric_requests_clarification(
    semantic_manager: DataManager,
) -> None:
    resolution = resolve_semantic_query(
        "Qual foi o maior fornecedor ou cliente?", semantic_manager
    )

    assert resolution.plans == ()
    assert resolution.clarification is not None
    assert "por qual métrica" in resolution.clarification
    assert resolution.pending_clarification == PendingClarification()


@pytest.mark.parametrize(
    ("question", "reply", "dimensions", "group_by", "n"),
    [
        (
            "top 5 fornecedores",
            "valor total das notas",
            ("supplier",),
            ("Parte A",),
            5,
        ),
        (
            "top 3 clientes",
            "valor total",
            ("recipient",),
            ("Parte B",),
            3,
        ),
    ],
)
def test_single_actor_clarification_preserves_complete_ranking_intent(
    semantic_manager: DataManager,
    question: str,
    reply: str,
    dimensions: tuple[str, ...],
    group_by: tuple[str, ...],
    n: int,
) -> None:
    clarification = resolve_semantic_query(question, semantic_manager)

    assert clarification.plans == ()
    assert clarification.clarification is not None
    pending = clarification.pending_clarification
    assert pending is not None
    assert pending.kind == "comparison_metric"
    assert pending.dimensions == dimensions
    assert pending.n == n
    assert pending.order == "desc"
    assert "invoice_value" in pending.metric_options

    resumed = resolve_pending_clarification(reply, pending, semantic_manager)

    assert resumed is not None
    assert resumed.clarification is None
    assert resumed.pending_clarification is None
    assert len(resumed.plans) == 1
    plan = resumed.plans[0]
    assert plan.tool == "top_n"
    assert plan.dataset_name == "LoteDocumento"
    assert plan.group_by == group_by
    assert plan.value_column == "Montante Documento"
    assert plan.operation == "sum"
    assert plan.order == "desc"
    assert plan.n == n


@pytest.mark.parametrize(
    ("reply", "operation", "dataset", "value_column"),
    [
        ("Valor total", "sum", "LoteDocumento", "Montante Documento"),
        ("quantidade comprada", "sum", "LoteLinha", "Medida Física"),
        ("número de documentos", "count", "LoteDocumento", None),
    ],
)
def test_pending_comparison_metric_resumes_both_dimensions(
    semantic_manager: DataManager,
    reply: str,
    operation: str,
    dataset: str,
    value_column: str | None,
) -> None:
    resolution = resolve_pending_clarification(
        reply,
        PendingClarification(),
        semantic_manager,
    )

    assert resolution is not None
    assert resolution.clarification is None
    assert resolution.pending_clarification is None
    assert len(resolution.plans) == 2
    assert [plan.group_by for plan in resolution.plans] == [
        ("Parte A",),
        ("Parte B",),
    ]
    assert {plan.dataset_name for plan in resolution.plans} == {dataset}
    assert {plan.operation for plan in resolution.plans} == {operation}
    assert {plan.value_column for plan in resolution.plans} == {value_column}


def test_dual_clarification_preserves_both_dimensions_from_original_question(
    semantic_manager: DataManager,
) -> None:
    clarification = resolve_semantic_query(
        "Qual foi o maior fornecedor ou cliente?", semantic_manager
    )
    pending = clarification.pending_clarification

    assert pending is not None
    assert pending.dimensions == ("supplier", "recipient")
    assert pending.n == 1
    assert pending.order == "desc"

    resumed = resolve_pending_clarification("valor total", pending, semantic_manager)

    assert resumed is not None
    assert resumed.pending_clarification is None
    assert [plan.group_by for plan in resumed.plans] == [
        ("Parte A",),
        ("Parte B",),
    ]
    assert all(plan.tool == "top_n" for plan in resumed.plans)
    assert all(plan.operation == "sum" for plan in resumed.plans)
    assert all(plan.n == 1 for plan in resumed.plans)
    assert all(plan.order == "desc" for plan in resumed.plans)


def test_pending_context_does_not_capture_an_independent_question(
    semantic_manager: DataManager,
) -> None:
    resolution = resolve_pending_clarification(
        "Qual produto teve maior volume comprado?",
        PendingClarification(),
        semantic_manager,
    )

    assert resolution is None


def test_pending_comparison_preserves_qualitative_guard(
    semantic_manager: DataManager,
) -> None:
    clarification = resolve_semantic_query(
        "Qual foi o fornecedor ou cliente mais importante?",
        semantic_manager,
    )

    assert clarification.pending_clarification is not None
    assert clarification.pending_clarification.qualitative_qualifier == "importante"

    resumed = resolve_pending_clarification(
        "valor total",
        clarification.pending_clarification,
        semantic_manager,
    )

    assert resumed is not None
    assert resumed.qualitative_qualifier == "importante"


def test_document_count_completion_counts_header_rows_without_value_column(
    semantic_manager: DataManager,
) -> None:
    resolution = resolve_pending_clarification(
        "número de documentos",
        PendingClarification(),
        semantic_manager,
    )
    assert resolution is not None
    supplier_plan = resolution.plans[0]
    tools = DataTools(semantic_manager)

    correct = tools.top_n(
        supplier_plan.dataset_name,
        list(supplier_plan.group_by),
        None,
        "count",
        1,
        "desc",
    )
    wrong = tools.top_n(
        supplier_plan.dataset_name,
        list(supplier_plan.group_by),
        "Montante Documento",
        "count",
        1,
        "desc",
    )

    assert supplier_plan.matches_result(correct)
    assert not supplier_plan.matches_result(wrong)


def test_supplier_or_client_with_total_value_produces_two_plans(
    semantic_manager: DataManager,
) -> None:
    resolution = resolve_semantic_query(
        "Qual fornecedor ou cliente teve maior valor total?", semantic_manager
    )

    assert resolution.clarification is None
    assert len(resolution.plans) == 2
    supplier, client = resolution.plans
    assert supplier.group_by == ("Parte A",)
    assert client.group_by == ("Parte B",)
    for plan in resolution.plans:
        assert plan.tool == "top_n"
        assert plan.dataset_name == "LoteDocumento"
        assert plan.value_column == "Montante Documento"
        assert plan.operation == "sum"
        assert plan.n == 1


def test_supplier_or_client_with_explicit_item_value_uses_item_dataset(
    semantic_manager: DataManager,
) -> None:
    resolution = resolve_semantic_query(
        "Qual fornecedor ou cliente teve maior valor total dos itens?",
        semantic_manager,
    )

    assert len(resolution.plans) == 2
    assert {plan.dataset_name for plan in resolution.plans} == {"LoteLinha"}
    assert {plan.value_column for plan in resolution.plans} == {"Montante Linha"}


def test_largest_supplier_without_metric_requests_clarification(
    semantic_manager: DataManager,
) -> None:
    resolution = resolve_semantic_query(
        "Qual foi o maior fornecedor?", semantic_manager
    )

    assert resolution.plans == ()
    assert resolution.clarification is not None
    assert "métrica" in resolution.clarification


@pytest.mark.parametrize(
    "question", ["Qual foi o fornecedor mais estratégico?", "Qual foi o melhor cliente?"]
)
def test_qualitative_ranking_without_metric_is_not_converted_to_value(
    semantic_manager: DataManager, question: str
) -> None:
    resolution = resolve_semantic_query(question, semantic_manager)

    assert resolution.plans == ()
    assert resolution.clarification is not None
    assert "não permitem concluir" in resolution.clarification
    assert "critério quantitativo" in resolution.clarification


def test_qualitative_product_without_metric_is_not_delegated_to_model(
    semantic_manager: DataManager,
) -> None:
    resolution = resolve_semantic_query(
        "Qual foi o produto mais estratégico?", semantic_manager
    )

    assert resolution.plans == ()
    assert resolution.clarification is not None
    assert "estrategico" in resolution.clarification


def test_qualitative_product_with_item_metric_keeps_disclaimer(
    semantic_manager: DataManager,
) -> None:
    resolution = resolve_semantic_query(
        "Qual foi o produto mais importante por valor total dos itens?",
        semantic_manager,
    )

    assert len(resolution.plans) == 1
    assert resolution.plans[0].dataset_name == "LoteLinha"
    assert resolution.qualitative_qualifier == "importante"


def test_qualitative_product_with_volume_metric_keeps_quantitative_plan(
    semantic_manager: DataManager,
) -> None:
    resolution = resolve_semantic_query(
        "Qual produto foi o mais relevante por volume comprado?", semantic_manager
    )

    assert len(resolution.plans) == 1
    assert resolution.plans[0].value_column == "Medida Física"
    assert resolution.plans[0].operation == "sum"
    assert resolution.qualitative_qualifier == "relevante"


def test_resolved_volume_plan_produces_sum_winner_not_count_winner(
    semantic_manager: DataManager,
) -> None:
    plan = resolve_semantic_intent(
        "Qual produto apresentou o maior volume comprado?", semantic_manager
    )
    assert plan is not None

    result = DataTools(semantic_manager).top_n(
        plan.dataset_name,
        list(plan.group_by),
        plan.value_column,
        plan.operation or "sum",
        plan.n or 1,
        plan.order or "desc",
    )

    assert result.rows[0] == {"Mercadoria": "A", "sum_Medida Física": 10.0}


def test_resolved_spend_plan_uses_invoice_sum_not_item_sum(
    semantic_manager: DataManager,
) -> None:
    plan = resolve_semantic_intent("Qual foi o total gasto?", semantic_manager)
    assert plan is not None

    tools = DataTools(semantic_manager)
    invoice_result = tools.aggregate_data(
        plan.dataset_name, plan.operation or "sum", plan.value_column
    )
    item_result = tools.aggregate_data(
        "LoteLinha", "sum", "Montante Linha"
    )

    assert invoice_result.rows == [{"valor": 300.0}]
    assert item_result.rows == [{"valor": 250.0}]


def test_resolved_supplier_plan_executes_expected_ranking(
    semantic_manager: DataManager,
) -> None:
    plan = resolve_semantic_intent(
        "Qual fornecedor recebeu o maior valor?", semantic_manager
    )
    assert plan is not None

    result = DataTools(semantic_manager).top_n(
        plan.dataset_name,
        list(plan.group_by),
        plan.value_column,
        plan.operation or "sum",
        plan.n or 1,
        plan.order or "desc",
    )

    assert result.rows[0] == {"Parte A": "F2", "sum_Montante Documento": 200.0}


def test_resolved_monthly_plan_executes_header_series(
    semantic_manager: DataManager,
) -> None:
    plan = resolve_semantic_intent("Qual foi o gasto por mês?", semantic_manager)
    assert plan is not None

    result = DataTools(semantic_manager).time_aggregation(
        plan.dataset_name,
        plan.date_column or "",
        plan.period or "year-month",
        plan.operation or "sum",
        plan.value_column,
    )

    assert result.rows == [
        {"periodo": "2024-01", "sum_Montante Documento": 100.0},
        {"periodo": "2024-02", "sum_Montante Documento": 200.0},
    ]


def test_resolved_item_value_plan_executes_item_sum(
    semantic_manager: DataManager,
) -> None:
    plan = resolve_semantic_intent("Qual é o valor total dos itens?", semantic_manager)
    assert plan is not None

    result = DataTools(semantic_manager).aggregate_data(
        plan.dataset_name, plan.operation or "sum", plan.value_column
    )

    assert result.rows == [{"valor": 250.0}]
