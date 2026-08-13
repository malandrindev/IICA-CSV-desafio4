"""Testes do contrato do agente sem chamar a Groq."""

import json
import re
from types import SimpleNamespace

import pandas as pd
import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult

import iica_csv.agents.csv_agent as agent_module
from iica_csv.agents.csv_agent import (
    AgentConfigurationError,
    AgentExecutionError,
    AgentResponse,
    CSVAgent,
    SYSTEM_PROMPT,
)
from iica_csv.processing.data_manager import DataManager
from iica_csv.tools.data_tools import ToolResult


class FakeExecutor:
    def __init__(self, content: str, before_response=None) -> None:
        self.content = content
        self.before_response = before_response
        self.last_state = None
        self.last_config = None

    def invoke(self, state, config=None):
        self.last_state = state
        self.last_config = config
        if self.before_response:
            self.before_response()
        return {"messages": [SimpleNamespace(content=self.content)]}


class ToolCallingFakeModel(BaseChatModel):
    """Modelo mínimo que força um tool call no loop real do LangChain."""

    @property
    def _llm_type(self) -> str:
        return "tool-calling-fake"

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        if any(isinstance(message, ToolMessage) for message in messages):
            message = AIMessage(content="A soma calculada pela ferramenta é 3.")
        else:
            message = AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "aggregate_data",
                        "args": {
                            "dataset_name": "dados",
                            "operation": "sum",
                            "value_column": "Valor",
                        },
                        "id": "call-1",
                        "type": "tool_call",
                    }
                ],
            )
        return ChatResult(generations=[ChatGeneration(message=message)])


class SemanticToolCallingFakeModel(BaseChatModel):
    """Loop LangChain real com a chamada exigida pelo plano semântico."""

    @property
    def _llm_type(self) -> str:
        return "semantic-tool-calling-fake"

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        if any(isinstance(message, ToolMessage) for message in messages):
            message = AIMessage(content="F2 possui o maior valor.")
        else:
            message = AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "top_n",
                        "args": {
                            "dataset_name": "Documentos",
                            "group_by": "Origem",
                            "value_column": "Valor Documento",
                            "aggregation": "sum",
                            "n": 1,
                            "order": "desc",
                        },
                        "id": "semantic-call-1",
                        "type": "tool_call",
                    }
                ],
            )
        return ChatResult(generations=[ChatGeneration(message=message)])


@pytest.fixture
def manager() -> DataManager:
    return DataManager({"dados": pd.DataFrame({"Valor": [1.0, 2.0]})})


@pytest.fixture
def semantic_manager() -> DataManager:
    manager = DataManager()
    manager.add_dataset(
        "Documentos",
        pd.DataFrame(
            {
                "Origem": ["F1", "F2"],
                "Destino": ["C1", "C2"],
                "Emissão": pd.to_datetime(["2024-01-01", "2024-02-01"]),
                "Valor Documento": [100.0, 200.0],
            }
        ),
        data_dictionary={
            "descricao": "Cabeçalho de notas fiscais.",
            "colunas": {
                "Origem": {"descricao": "Nome ou razão social do emitente."},
                "Destino": {"descricao": "Nome do destinatário ou cliente."},
                "Emissão": {"descricao": "Data de emissão da nota fiscal."},
                "Valor Documento": {
                    "descricao": "Valor total da nota fiscal no cabeçalho."
                },
            },
        },
    )
    manager.add_dataset(
        "Linhas",
        pd.DataFrame(
            {
                "Origem": ["F1", "F2", "F2"],
                "Destino": ["C1", "C2", "C2"],
                "Produto": ["A", "B", "B"],
                "Volume": [10.0, 1.0, 1.0],
                "Valor Linha": [100.0, 50.0, 50.0],
            }
        ),
        data_dictionary={
            "descricao": "Itens de notas fiscais.",
            "colunas": {
                "Origem": {"descricao": "Nome ou razão social do emitente."},
                "Destino": {"descricao": "Nome do destinatário ou cliente."},
                "Produto": {"descricao": "Descrição do produto do item."},
                "Volume": {"descricao": "Quantidade ou volume comprado."},
                "Valor Linha": {"descricao": "Valor total do item."},
            },
        },
    )
    return manager


def make_agent(monkeypatch, manager: DataManager, content: str) -> CSVAgent:
    executor = FakeExecutor(content)
    monkeypatch.setattr(agent_module, "create_agent", lambda **_: executor)
    agent = CSVAgent(manager, model=object())
    agent._executor = executor
    return agent


def test_missing_key_has_clear_configuration_error(manager: DataManager) -> None:
    with pytest.raises(AgentConfigurationError, match="GROQ_API_KEY"):
        CSVAgent(manager)


def test_data_question_without_tool_is_rejected(monkeypatch, manager: DataManager) -> None:
    agent = make_agent(monkeypatch, manager, "O total é 3.")

    with pytest.raises(AgentExecutionError, match="não acionou uma ferramenta"):
        agent.ask("Qual é o valor total?")


def test_tool_result_is_returned_as_evidence(monkeypatch, manager: DataManager) -> None:
    agent = make_agent(monkeypatch, manager, "A soma calculada é 3.")
    executor = FakeExecutor(
        "A soma calculada é 3.",
        before_response=lambda: agent.data_tools.aggregate_data(
            "dados", "sum", "Valor"
        ),
    )
    agent._executor = executor

    response = agent.ask(
        "Qual é a soma?",
        history=[{"role": "user", "content": "Consulte os dados."}],
    )

    assert response.text == "A soma calculada é 3."
    assert response.display_result is not None
    assert response.display_result.result_type == "scalar"
    assert response.display_result.rows == [{"valor": 3.0}]
    assert executor.last_state["messages"][-1]["content"] == "Qual é a soma?"
    assert executor.last_config == {"recursion_limit": 18}


def test_final_tool_error_is_not_hidden_by_old_success(
    monkeypatch, manager: DataManager
) -> None:
    agent = make_agent(monkeypatch, manager, "Não foi possível calcular.")
    results = [
        ToolResult("table", "ok"),
        ToolResult("error", "coluna ausente"),
    ]

    assert agent._choose_display_result(results) is results[-1]


def test_agent_response_keeps_singular_and_plural_evidence_consistent() -> None:
    first = ToolResult("scalar", "primeira")
    second = ToolResult("scalar", "segunda")

    legacy = AgentResponse("texto", display_result=first)
    plural = AgentResponse("texto", display_results=[first, second])

    assert legacy.display_results == [first]
    assert plural.display_result is second


def test_unplanned_query_preserves_multiple_analytical_results(
    monkeypatch, manager: DataManager
) -> None:
    agent = make_agent(monkeypatch, manager, "A soma é 3 e a média é 1,5.")

    def call_two_metrics() -> None:
        agent.data_tools.aggregate_data("dados", "sum", "Valor")
        agent.data_tools.aggregate_data("dados", "mean", "Valor")

    agent._executor = FakeExecutor(
        "A soma é 3 e a média é 1,5.", before_response=call_two_metrics
    )

    response = agent.ask("Informe soma e média do valor.")

    assert len(response.display_results) == 2
    assert [result.metadata["operation"] for result in response.display_results] == [
        "sum",
        "mean",
    ]


def test_analytical_answer_after_tool_error_is_rejected(
    monkeypatch, manager: DataManager
) -> None:
    agent = make_agent(monkeypatch, manager, "O total é 999.")
    agent._executor = FakeExecutor(
        "O total é 999.",
        before_response=lambda: agent.data_tools.aggregate_data(
            "dados", "sum", "Coluna inexistente"
        ),
    )

    with pytest.raises(AgentExecutionError, match="consulta determinística falhou"):
        agent.ask("Qual é o valor total?")


def test_catalog_tool_alone_does_not_ground_ranking(
    monkeypatch, manager: DataManager
) -> None:
    agent = make_agent(monkeypatch, manager, "Alfa lidera.")
    agent._executor = FakeExecutor(
        "Alfa lidera.", before_response=agent.data_tools.list_datasets
    )

    with pytest.raises(AgentExecutionError, match="ferramenta analítica"):
        agent.ask("Quem lidera?")


def test_greeting_does_not_require_a_tool(monkeypatch, manager: DataManager) -> None:
    agent = make_agent(monkeypatch, manager, "Olá! Posso consultar seus CSVs.")

    response = agent.ask("Olá")

    assert response.text.startswith("Olá")
    assert response.tool_results == []


def test_system_prompt_contains_mandatory_grounding_rules() -> None:
    lowered = SYSTEM_PROMPT.casefold()

    assert "toda afirmação numérica" in lowered
    assert "mais importante" in lowered
    assert "causalidade" in lowered
    assert "groq_api_key" in lowered
    assert "nunca gere nem execute python" in lowered
    assert "supplier" in lowered
    assert "destinatário, cliente e comprador" in lowered
    assert "sum" in lowered
    assert "count" in lowered
    assert "granularidade de cabeçalho" in lowered


def test_semantic_plan_is_sent_to_model_and_correct_call_is_accepted(
    monkeypatch, semantic_manager: DataManager
) -> None:
    agent = make_agent(monkeypatch, semantic_manager, "F2 possui o maior valor.")
    executor = FakeExecutor(
        "F2 possui o maior valor.",
        before_response=lambda: agent.data_tools.top_n(
            "Documentos", "Origem", "Valor Documento", "sum", 1, "desc"
        ),
    )
    agent._executor = executor

    response = agent.ask("Qual fornecedor recebeu o maior valor?")

    assert response.display_result is not None
    assert response.display_result.metadata["group_by"] == ["Origem"]
    semantic_messages = [
        message["content"]
        for message in executor.last_state["messages"]
        if "<semantic-plan>" in message["content"]
    ]
    semantic_message = next(iter(semantic_messages))
    match = re.search(r"<semantic-plan>(.*?)</semantic-plan>", semantic_message)
    assert match is not None
    payload = json.loads(match.group(1))
    assert payload["arguments"]["dataset_name"] == "Documentos"
    assert payload["arguments"]["aggregation"] == "sum"
    assert "operation" not in payload["arguments"]
    assert payload["derived_from_dictionary"] is True
    top_tool = next(
        tool for tool in agent.data_tools.langchain_tools() if tool.name == "top_n"
    )
    assert set(payload["arguments"]) <= set(top_tool.args_schema.model_fields)
    assert executor.last_state["messages"][-1] == {
        "role": "user",
        "content": "Qual fornecedor recebeu o maior valor?",
    }


def test_supplier_answer_using_recipient_column_is_blocked(
    monkeypatch, semantic_manager: DataManager
) -> None:
    agent = make_agent(monkeypatch, semantic_manager, "C2 possui o maior valor.")
    agent._executor = FakeExecutor(
        "C2 possui o maior valor.",
        before_response=lambda: agent.data_tools.top_n(
            "Documentos", "Destino", "Valor Documento", "sum", 1, "desc"
        ),
    )

    with pytest.raises(AgentExecutionError, match="semanticamente incorreto"):
        agent.ask("Qual fornecedor recebeu o maior valor?")


def test_recipient_answer_using_supplier_column_is_blocked(
    monkeypatch, semantic_manager: DataManager
) -> None:
    agent = make_agent(monkeypatch, semantic_manager, "F2 possui o maior valor.")
    agent._executor = FakeExecutor(
        "F2 possui o maior valor.",
        before_response=lambda: agent.data_tools.top_n(
            "Documentos", "Origem", "Valor Documento", "sum", 1, "desc"
        ),
    )

    with pytest.raises(AgentExecutionError, match="semanticamente incorreto"):
        agent.ask("Qual cliente aparece com o maior valor?")


def test_correct_semantic_call_followed_by_wrong_call_is_blocked(
    monkeypatch, semantic_manager: DataManager
) -> None:
    agent = make_agent(monkeypatch, semantic_manager, "C2 possui o maior valor.")

    def call_correct_then_wrong() -> None:
        agent.data_tools.top_n(
            "Documentos", "Origem", "Valor Documento", "sum", 1, "desc"
        )
        agent.data_tools.top_n(
            "Documentos", "Destino", "Valor Documento", "sum", 1, "desc"
        )

    agent._executor = FakeExecutor(
        "C2 possui o maior valor.", before_response=call_correct_then_wrong
    )

    with pytest.raises(AgentExecutionError, match="plano semântico"):
        agent.ask("Qual fornecedor recebeu o maior valor?")


def test_product_volume_using_count_is_blocked(
    monkeypatch, semantic_manager: DataManager
) -> None:
    agent = make_agent(monkeypatch, semantic_manager, "B aparece mais vezes.")
    agent._executor = FakeExecutor(
        "B aparece mais vezes.",
        before_response=lambda: agent.data_tools.top_n(
            "Linhas", "Produto", "Volume", "count", 1, "desc"
        ),
    )

    with pytest.raises(AgentExecutionError, match="semanticamente incorreto"):
        agent.ask("Qual produto teve o maior volume comprado?")


def test_general_spend_using_item_total_is_blocked(
    monkeypatch, semantic_manager: DataManager
) -> None:
    agent = make_agent(monkeypatch, semantic_manager, "O total é 200.")
    agent._executor = FakeExecutor(
        "O total é 200.",
        before_response=lambda: agent.data_tools.aggregate_data(
            "Linhas", "sum", "Valor Linha"
        ),
    )

    with pytest.raises(AgentExecutionError, match="semanticamente incorreto"):
        agent.ask("Qual foi o total gasto?")


def test_scalar_spend_plan_rejects_unrequested_grouping(
    monkeypatch, semantic_manager: DataManager
) -> None:
    agent = make_agent(monkeypatch, semantic_manager, "F2 soma 200.")
    agent._executor = FakeExecutor(
        "F2 soma 200.",
        before_response=lambda: agent.data_tools.aggregate_data(
            "Documentos", "sum", "Valor Documento", "Origem"
        ),
    )

    with pytest.raises(AgentExecutionError, match="semanticamente incorreto"):
        agent.ask("Qual foi o total gasto?")


def test_qualitative_supplier_premise_is_rejected_without_calling_model(
    monkeypatch, semantic_manager: DataManager
) -> None:
    agent = make_agent(
        monkeypatch,
        semantic_manager,
        "F2 foi o mais importante porque teve maior valor.",
    )

    response = agent.ask("Por que F2 foi o fornecedor mais importante?")

    assert "não permitem concluir" in response.text
    assert "julgamento qualitativo 'importante'" in response.text
    assert response.tool_results == []
    assert agent._executor.last_state is None


def test_qualitative_supplier_with_explicit_metric_separates_fact_from_inference(
    monkeypatch, semantic_manager: DataManager
) -> None:
    agent = make_agent(
        monkeypatch,
        semantic_manager,
        "F2 foi o fornecedor mais importante porque liderou por valor.",
    )
    agent._executor = FakeExecutor(
        "F2 foi o fornecedor mais importante porque liderou por valor.",
        before_response=lambda: agent.data_tools.top_n(
            "Documentos", "Origem", "Valor Documento", "sum", 1, "desc"
        ),
    )

    response = agent.ask("Qual foi o fornecedor mais importante por valor total?")

    assert "resultado quantitativo" in response.text
    assert "não sustenta o julgamento qualitativo" in response.text
    assert "importante" in response.text
    assert "F2" in response.text
    assert "200" in response.text
    assert len(response.display_results) == 1


def test_supplier_or_client_without_metric_does_not_call_model(
    monkeypatch, semantic_manager: DataManager
) -> None:
    agent = make_agent(monkeypatch, semantic_manager, "F2 e C2.")

    response = agent.ask("Qual foi o maior fornecedor ou cliente?")

    assert "por qual métrica" in response.text
    assert response.tool_results == []
    assert response.pending_clarification is not None
    assert agent._executor.last_state is None


def test_short_metric_resumes_comparison_and_consumes_pending_context(
    monkeypatch, semantic_manager: DataManager
) -> None:
    agent = make_agent(monkeypatch, semantic_manager, "não deve ser usado")

    clarification = agent.ask("Qual foi o maior fornecedor ou cliente?")
    pending = clarification.pending_clarification
    assert pending is not None

    def call_both_dimensions() -> None:
        agent.data_tools.top_n(
            "Documentos", "Origem", "Valor Documento", "sum", 1, "desc"
        )
        agent.data_tools.top_n(
            "Documentos", "Destino", "Valor Documento", "sum", 1, "desc"
        )

    agent._executor = FakeExecutor(
        "F2 é o fornecedor e C2 é o cliente com maior valor.",
        before_response=call_both_dimensions,
    )
    comparison = agent.ask("Valor total", pending_clarification=pending)

    assert comparison.pending_clarification is None
    assert len(comparison.display_results) == 2
    assert [result.metadata["group_by"] for result in comparison.display_results] == [
        ["Origem"],
        ["Destino"],
    ]

    agent._executor = FakeExecutor(
        "A é o produto com maior volume.",
        before_response=lambda: agent.data_tools.top_n(
            "Linhas", "Produto", "Volume", "sum", 1, "desc"
        ),
    )
    independent = agent.ask(
        "Qual produto teve maior volume comprado?",
        pending_clarification=comparison.pending_clarification,
    )

    assert independent.pending_clarification is None
    assert len(independent.display_results) == 1
    assert independent.display_results[0].metadata["group_by"] == ["Produto"]


def test_single_ranking_clarification_keeps_top_n_and_does_not_leak(
    monkeypatch, semantic_manager: DataManager
) -> None:
    agent = make_agent(monkeypatch, semantic_manager, "não deve ser usado")

    clarification = agent.ask("top 5 fornecedores")
    pending = clarification.pending_clarification
    assert pending is not None
    assert pending.dimensions == ("supplier",)
    assert pending.n == 5

    agent._executor = FakeExecutor(
        "Top 5 fornecedores por valor calculado.",
        before_response=lambda: agent.data_tools.top_n(
            "Documentos", "Origem", "Valor Documento", "sum", 5, "desc"
        ),
    )
    resumed = agent.ask(
        "valor total das notas",
        pending_clarification=pending,
    )

    assert resumed.pending_clarification is None
    assert len(resumed.display_results) == 1
    evidence = resumed.display_results[0]
    assert evidence.metadata["group_by"] == ["Origem"]
    assert evidence.metadata["value_column"] == "Valor Documento"
    assert evidence.metadata["n"] == 5
    assert evidence.metadata["order"] == "desc"

    agent._executor = FakeExecutor(
        "Produto com maior volume calculado.",
        before_response=lambda: agent.data_tools.top_n(
            "Linhas", "Produto", "Volume", "sum", 1, "desc"
        ),
    )
    independent = agent.ask(
        "Qual produto teve maior volume comprado?",
        pending_clarification=resumed.pending_clarification,
    )

    assert independent.pending_clarification is None
    assert len(independent.display_results) == 1
    independent_evidence = independent.display_results[0]
    assert independent_evidence.metadata["group_by"] == ["Produto"]
    assert independent_evidence.metadata["value_column"] == "Volume"
    assert independent_evidence.metadata["n"] == 1


def test_supplier_and_client_by_value_preserves_two_evidences(
    monkeypatch, semantic_manager: DataManager
) -> None:
    agent = make_agent(monkeypatch, semantic_manager, "F2 e C2 lideram por valor.")

    def call_both_dimensions() -> None:
        agent.data_tools.top_n(
            "Documentos", "Origem", "Valor Documento", "sum", 1, "desc"
        )
        agent.data_tools.top_n(
            "Documentos", "Destino", "Valor Documento", "sum", 1, "desc"
        )

    agent._executor = FakeExecutor(
        "F2 é o fornecedor e C2 é o cliente com maior valor.",
        before_response=call_both_dimensions,
    )

    response = agent.ask("Qual fornecedor ou cliente teve maior valor total?")

    assert len(response.display_results) == 2
    assert [result.metadata["group_by"] for result in response.display_results] == [
        ["Origem"],
        ["Destino"],
    ]
    assert response.display_result is response.display_results[-1]
    assert len(response.tool_results) == 2
    guidance = " ".join(
        message["content"] for message in agent._executor.last_state["messages"]
    )
    assert "Execute TODOS" in guidance
    assert "exatamente uma chamada analítica por plano" in guidance


def test_supplier_and_client_answer_is_blocked_when_one_evidence_is_missing(
    monkeypatch, semantic_manager: DataManager
) -> None:
    agent = make_agent(monkeypatch, semantic_manager, "F2 e C2 lideram.")
    agent._executor = FakeExecutor(
        "F2 e C2 lideram.",
        before_response=lambda: agent.data_tools.top_n(
            "Documentos", "Origem", "Valor Documento", "sum", 1, "desc"
        ),
    )

    with pytest.raises(AgentExecutionError, match="semanticamente incorreto"):
        agent.ask("Qual fornecedor ou cliente teve maior valor total?")


def test_semantic_plan_cannot_be_bypassed_by_model_clarification_suffix(
    monkeypatch, semantic_manager: DataManager
) -> None:
    agent = make_agent(
        monkeypatch,
        semantic_manager,
        "F2 teve o maior valor: 200. Pode esclarecer?",
    )

    with pytest.raises(AgentExecutionError, match="não acionou uma ferramenta"):
        agent.ask("Qual fornecedor recebeu o maior valor?")


def test_real_langchain_agent_loop_executes_deterministic_tool(
    manager: DataManager,
) -> None:
    agent = CSVAgent(manager, model=ToolCallingFakeModel())

    response = agent.ask("Qual é a soma do valor?")

    assert response.text == "A soma calculada pela ferramenta é 3."
    assert len(response.tool_results) == 1
    assert response.tool_results[0].metadata["operation"] == "sum"
    assert response.tool_results[0].rows == [{"valor": 3.0}]


def test_real_langchain_loop_respects_semantic_plan(
    semantic_manager: DataManager,
) -> None:
    agent = CSVAgent(semantic_manager, model=SemanticToolCallingFakeModel())

    response = agent.ask("Qual fornecedor recebeu o maior valor?")

    assert response.text == "F2 possui o maior valor."
    assert response.display_result is not None
    assert response.display_result.metadata == {
        "dataset": "Documentos",
        "tool": "top_n",
        "operation": "sum",
        "value_column": "Valor Documento",
        "group_by": ["Origem"],
        "order": "desc",
        "n": 1,
        "total_groups": 2,
        "groups_without_values": 0,
    }
