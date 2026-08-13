"""Contrato semântico do dicionário demonstrativo versionado."""

import json
from pathlib import Path

import pandas as pd
import pytest

from iica_csv.agents.semantic_resolver import resolve_semantic_intent
from iica_csv.processing.data_manager import DataManager


DICTIONARY_PATH = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "dictionaries"
    / "dicionario_dados_202401.json"
)


@pytest.fixture(scope="module")
def demo_catalog() -> DataManager:
    dictionary = json.loads(DICTIONARY_PATH.read_text(encoding="utf-8"))
    manager = DataManager(data_dictionary=dictionary)
    for filename, details in dictionary["datasets"].items():
        columns = list(details["colunas"])
        manager.add_dataset(
            Path(filename).stem,
            pd.DataFrame(columns=columns),
            source_name=filename,
            data_dictionary=details,
        )
    return manager


def test_demo_dictionary_distinguishes_supplier_from_recipient(
    demo_catalog: DataManager,
) -> None:
    supplier = resolve_semantic_intent(
        "Qual fornecedor recebeu o maior valor?", demo_catalog
    )
    recipient = resolve_semantic_intent(
        "Qual cliente aparece com o maior valor?", demo_catalog
    )

    assert supplier is not None
    assert supplier.dataset_name == "202401_NFs_Cabecalho"
    assert supplier.group_by == ("RAZÃO SOCIAL EMITENTE",)
    assert supplier.value_column == "VALOR NOTA FISCAL"
    assert supplier.derived_from_dictionary is True
    assert recipient is not None
    assert recipient.group_by == ("NOME DESTINATÁRIO",)
    assert recipient.derived_from_dictionary is True


def test_demo_dictionary_maps_volume_to_quantity_sum(
    demo_catalog: DataManager,
) -> None:
    plan = resolve_semantic_intent(
        "Qual produto apresentou o maior volume comprado?", demo_catalog
    )

    assert plan is not None
    assert plan.dataset_name == "202401_NFs_Itens"
    assert plan.group_by == ("DESCRIÇÃO DO PRODUTO/SERVIÇO",)
    assert plan.value_column == "QUANTIDADE"
    assert plan.operation == "sum"
    assert plan.derived_from_dictionary is True


def test_demo_dictionary_maps_monthly_spend_to_invoice_header(
    demo_catalog: DataManager,
) -> None:
    plan = resolve_semantic_intent("Qual foi o total gasto por mês?", demo_catalog)

    assert plan is not None
    assert plan.tool == "time_aggregation"
    assert plan.dataset_name == "202401_NFs_Cabecalho"
    assert plan.date_column == "DATA EMISSÃO"
    assert plan.value_column == "VALOR NOTA FISCAL"
    assert plan.operation == "sum"
    assert plan.derived_from_dictionary is True


def test_demo_dictionary_reserves_item_total_for_explicit_item_question(
    demo_catalog: DataManager,
) -> None:
    plan = resolve_semantic_intent("Qual é o valor total dos itens?", demo_catalog)

    assert plan is not None
    assert plan.dataset_name == "202401_NFs_Itens"
    assert plan.value_column == "VALOR TOTAL"
    assert plan.operation == "sum"
    assert plan.derived_from_dictionary is True
