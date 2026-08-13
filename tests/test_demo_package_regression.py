"""Oráculos locais do pacote demo; os valores não entram no código de produção."""

from pathlib import Path

import pytest

from iica_csv.agents.semantic_resolver import resolve_semantic_query
from iica_csv.processing.zip_processor import ZipProcessor
from iica_csv.tools.data_tools import DataTools


DEMO_PACKAGE = (
    Path(__file__).resolve().parents[1]
    / "outputs"
    / "entrega"
    / "pacote_demo_202401.zip"
)


pytestmark = pytest.mark.skipif(
    not DEMO_PACKAGE.is_file(),
    reason="Pacote demo local não foi gerado; execute scripts/build_demo_package.py.",
)


@pytest.fixture(scope="module")
def demo_tools_and_manager():
    package = ZipProcessor().process(DEMO_PACKAGE)
    return DataTools(package.data_manager), package.data_manager


def _execute(question: str, tools: DataTools, manager):
    resolution = resolve_semantic_query(question, manager)
    assert resolution.clarification is None
    results = []
    for plan in resolution.plans:
        result = getattr(tools, plan.tool)(**plan.tool_arguments())
        assert result.result_type != "error"
        assert plan.matches_result(result)
        results.append(result)
    return results


def test_demo_largest_supplier_and_top_five(demo_tools_and_manager) -> None:
    tools, manager = demo_tools_and_manager
    largest = _execute(
        "Qual fornecedor recebeu o maior valor?", tools, manager
    )[0]
    top_five = _execute(
        "Quais foram os cinco maiores fornecedores por valor total?", tools, manager
    )[0]

    assert largest.rows[0] == {
        "RAZÃO SOCIAL EMITENTE": "CHEMYUNION LTDA",
        "sum_VALOR NOTA FISCAL": pytest.approx(1_292_418.75),
    }
    assert top_five.rows == [
        {
            "RAZÃO SOCIAL EMITENTE": "CHEMYUNION LTDA",
            "sum_VALOR NOTA FISCAL": pytest.approx(1_292_418.75),
        },
        {
            "RAZÃO SOCIAL EMITENTE": "LABORATORIOS B.BRAUN S.A",
            "sum_VALOR NOTA FISCAL": pytest.approx(726_081.60),
        },
        {
            "RAZÃO SOCIAL EMITENTE": "XCMG BRASIL INDUSTRIA LTDA",
            "sum_VALOR NOTA FISCAL": pytest.approx(330_000.00),
        },
        {
            "RAZÃO SOCIAL EMITENTE": "EDITORA FTD S.A.",
            "sum_VALOR NOTA FISCAL": pytest.approx(292_486.11),
        },
        {
            "RAZÃO SOCIAL EMITENTE": "MALTACARE DISTRIBUIDORA LTDA",
            "sum_VALOR NOTA FISCAL": pytest.approx(122_202.60),
        },
    ]


def test_demo_product_volume_and_monthly_invoice_total(
    demo_tools_and_manager,
) -> None:
    tools, manager = demo_tools_and_manager
    volume = _execute(
        "Qual produto apresentou o maior volume comprado?", tools, manager
    )[0]
    monthly = _execute("Qual foi o total gasto por mês?", tools, manager)[0]

    assert volume.rows[0] == {
        "DESCRIÇÃO DO PRODUTO/SERVIÇO": (
            "DIPIFARMA INJETAVEL(DIPIRONA MONOIDR 500MG/ML) 2ML"
        ),
        "sum_QUANTIDADE": pytest.approx(51_000.0),
    }
    assert monthly.rows == [
        {
            "periodo": "2024-01",
            "sum_VALOR NOTA FISCAL": pytest.approx(3_371_754.84),
        }
    ]


def test_demo_supplier_and_client_keep_two_distinct_evidences(
    demo_tools_and_manager,
) -> None:
    tools, manager = demo_tools_and_manager
    supplier, client = _execute(
        "Qual fornecedor ou cliente teve maior valor total?", tools, manager
    )

    assert supplier.rows[0] == {
        "RAZÃO SOCIAL EMITENTE": "CHEMYUNION LTDA",
        "sum_VALOR NOTA FISCAL": pytest.approx(1_292_418.75),
    }
    assert client.rows[0] == {
        "NOME DESTINATÁRIO": "INSTITUTO DE TECNOLOGIA EM FÁRMACOS",
        "sum_VALOR NOTA FISCAL": pytest.approx(1_293_018.75),
    }
