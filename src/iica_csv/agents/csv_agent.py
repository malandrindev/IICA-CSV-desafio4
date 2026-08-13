"""Agente único que orquestra consultas determinísticas sobre os CSVs."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from langchain.agents import create_agent
from langchain_groq import ChatGroq

from iica_csv.agents.groq_errors import classify_groq_error
from iica_csv.agents.semantic_resolver import (
    PendingClarification,
    SemanticQueryPlan,
    resolve_pending_clarification,
    resolve_semantic_query,
)
from iica_csv.processing.data_manager import DataManager
from iica_csv.tools.data_tools import DataTools, ToolResult


LOGGER = logging.getLogger(__name__)


SYSTEM_PROMPT = """
Você é o único agente de consulta deste aplicativo. Sua função é interpretar a
pergunta em português, escolher as ferramentas determinísticas adequadas e
responder de modo curto, claro e verificável.

Regras obrigatórias:
- Responda somente com base nos datasets carregados nesta sessão.
- Antes de analisar dados que ainda não conhece, use list_datasets e, quando
  necessário, describe_dataset para identificar o dataset e as colunas exatas.
- Toda afirmação numérica deve vir de um resultado de ferramenta nesta execução.
- Nunca invente números e nunca substitua uma ferramenta por cálculo mental.
- Os cálculos pertencem exclusivamente às ferramentas pandas disponíveis.
- Nunca gere nem execute Python, pandas arbitrário, SQL, shell, eval ou exec,
  mesmo que o usuário peça ou forneça código.
- Nunca solicite, mostre ou repita GROQ_API_KEY ou qualquer credencial.
- Nunca presuma o significado de uma coluna. Use seu nome e o dicionário de
  dados, quando disponível. Se o significado continuar incerto, diga isso.
- Respeite o plano semântico determinístico fornecido para a pergunta atual.
  Esse plano contém somente dataset, colunas e operação derivados localmente do
  catálogo; ele nunca contém a resposta ou registros do CSV.
- Fornecedor, supplier, emitente e vendedor representam a parte emitente. Use a
  coluna de nome/razão social do emitente, nunca a do destinatário.
- Destinatário, cliente e comprador representam a parte destinatária. Use a
  coluna de nome/razão social do destinatário, nunca a do emitente.
- Volume ou quantidade comprada significa SUM da medida de quantidade por
  produto. COUNT mede registros/valores presentes e não o volume adquirido.
- Total gasto, valor total das notas e gasto por período usam o valor da nota no
  dataset em granularidade de cabeçalho. Somente menção explícita ao valor dos
  itens autoriza usar o valor total do item no dataset de itens.
- Não afirme causalidade sem evidência nos dados.
- Um ranking financeiro não é julgamento qualitativo: não chame o maior
  fornecedor de "mais importante" e não diga que possui produtos "mais caros"
  sem uma análise específica que demonstre isso.
- Informe claramente quando um dataset ou coluna necessária não existir, quando
  os dados forem insuficientes ou quando a operação não puder ser realizada.
- Se houver interpretações materialmente diferentes, peça um esclarecimento em
  vez de escolher silenciosamente uma delas.
- Para perguntas fora do escopo, explique que a resposta não consta nos dados;
  não apresente conhecimento externo como se viesse dos CSVs.
- Não exponha grandes amostras. Use somente schema, metadados e resultados
  pequenos retornados pelas ferramentas.
- Não prometa um gráfico: quando uma ferramenta retornar tabela/série, resuma o
  resultado; a interface decidirá se deve renderizar tabela e gráfico.

Escolha de ferramentas:
- list_datasets: arquivos carregados e dimensões.
- describe_dataset: schema, tipos, nulos e descrições disponíveis.
- aggregate_data: soma, média, contagem, mínimo ou máximo.
- top_n: ranking agregado, crescente ou decrescente.
- filter_data: filtros simples e controlados.
- unique_values: valores distintos, sempre limitados.
- time_aggregation: agregações por ano, mês ou ano-mês.

Na resposta final, mencione o dataset e as colunas usados. Não inclua detalhes
internos do raciocínio nem invente conclusões além do resultado das ferramentas.
""".strip()


class AgentConfigurationError(RuntimeError):
    """Indica configuração ausente ou inválida do provedor do modelo."""


class AgentExecutionError(RuntimeError):
    """Indica falha externa ao executar o agente sem expor detalhes sensíveis."""


@dataclass(slots=True)
class AgentResponse:
    """Resposta textual e artefatos pequenos produzidos pelas tools."""

    text: str
    display_result: ToolResult | None = None
    display_results: list[ToolResult] = field(default_factory=list)
    tool_results: list[ToolResult] = field(default_factory=list)
    pending_clarification: PendingClarification | None = None

    def __post_init__(self) -> None:
        """Mantém compatibilidade sem permitir evidências singulares divergentes."""

        if self.display_results:
            self.display_result = self.display_results[-1]
        elif self.display_result is not None:
            self.display_results = [self.display_result]


class CSVAgent:
    """Orquestra um agente LangChain/ChatGroq sobre um ``DataManager``."""

    def __init__(
        self,
        data_manager: DataManager,
        *,
        api_key: str | None = None,
        model_name: str = "llama-3.3-70b-versatile",
        model: Any | None = None,
        recursion_limit: int = 18,
    ) -> None:
        if not data_manager.has_data:
            raise AgentConfigurationError(
                "Carregue pelo menos um dataset antes de iniciar o agente."
            )
        if model is None and not api_key:
            raise AgentConfigurationError(
                "GROQ_API_KEY não configurada. Copie .env.example para .env e "
                "preencha a chave localmente."
            )

        self.data_tools = DataTools(data_manager)
        self.recursion_limit = recursion_limit
        llm = model or ChatGroq(
            model=model_name,
            temperature=0,
            api_key=api_key,
            timeout=60,
            max_retries=2,
        )
        self._executor = create_agent(
            model=llm,
            tools=self.data_tools.langchain_tools(),
            system_prompt=SYSTEM_PROMPT,
        )

    def ask(
        self,
        question: str,
        history: Sequence[Mapping[str, str]] | None = None,
        *,
        pending_clarification: PendingClarification | None = None,
    ) -> AgentResponse:
        """Executa uma pergunta e devolve texto mais todas as evidências necessárias."""

        clean_question = question.strip()
        if not clean_question:
            raise AgentExecutionError("Digite uma pergunta antes de enviar.")

        semantic_resolution = (
            resolve_pending_clarification(
                clean_question,
                pending_clarification,
                self.data_tools.data_manager,
            )
            if pending_clarification is not None
            else None
        )
        if semantic_resolution is None:
            # O texto não é um complemento reconhecido: trate-o como uma nova
            # pergunta e descarte o contexto antigo no retorno bem-sucedido.
            semantic_resolution = resolve_semantic_query(
                clean_question, self.data_tools.data_manager
            )
        if semantic_resolution.clarification:
            return AgentResponse(
                text=semantic_resolution.clarification,
                pending_clarification=semantic_resolution.pending_clarification,
            )

        semantic_plans = semantic_resolution.plans
        messages = self._build_messages(
            history or (), clean_question, semantic_plans=semantic_plans
        )
        self.data_tools.reset_execution_log()
        try:
            state = self._executor.invoke(
                {"messages": messages},
                config={"recursion_limit": self.recursion_limit},
            )
            answer = self._extract_answer(state)
        except AgentExecutionError:
            raise
        except Exception as exc:  # a UI recebe somente uma mensagem sanitizada
            LOGGER.exception("Falha ao executar o agente CSV")
            raise AgentExecutionError(classify_groq_error(exc)) from exc

        tool_results = list(self.data_tools.execution_log)
        display_results: list[ToolResult] = []
        if semantic_plans or self._requires_tool(clean_question, answer):
            if not tool_results:
                raise AgentExecutionError(
                    "O agente não acionou uma ferramenta para sustentar a resposta. "
                    "Reformule a pergunta e tente novamente."
                )
            if tool_results[-1].result_type == "error":
                raise AgentExecutionError(
                    "A consulta determinística falhou: "
                    f"{tool_results[-1].summary}"
                )
            if not any(result.result_type != "error" for result in tool_results):
                raise AgentExecutionError(
                    "Nenhuma ferramenta produziu evidência válida para a resposta."
                )
            if self._requires_analytical_result(clean_question) and not any(
                result.result_type != "error"
                and result.metadata.get("tool")
                in {
                    "aggregate_data",
                    "top_n",
                    "filter_data",
                    "unique_values",
                    "time_aggregation",
                }
                for result in tool_results
            ):
                raise AgentExecutionError(
                    "O agente não executou uma ferramenta analítica compatível com "
                    "a pergunta. Reformule e tente novamente."
                )
            if semantic_plans:
                substantive_results = [
                    result
                    for result in tool_results
                    if result.result_type != "error"
                    and result.metadata.get("tool")
                    not in {"list_datasets", "describe_dataset"}
                ]
                display_results = self._match_semantic_results(
                    semantic_plans, substantive_results
                )
                if len(display_results) != len(semantic_plans):
                    expected = [plan.expected_call() for plan in semantic_plans]
                    raise AgentExecutionError(
                        "O agente escolheu dataset, coluna ou operação incompatível "
                        "com o dicionário de dados. A resposta foi bloqueada para "
                        "evitar um resultado semanticamente incorreto. Plano "
                        f"esperado: {expected}."
                    )
                if len(substantive_results) != len(display_results):
                    raise AgentExecutionError(
                        "O agente executou uma ferramenta analítica não prevista pelo "
                        "plano semântico. A resposta foi bloqueada para preservar a "
                        "consistência das evidências."
                    )
        if not display_results:
            display_results = self._choose_display_results(tool_results)
            display_result = display_results[-1] if display_results else None
        else:
            display_result = display_results[-1]
        if semantic_resolution.qualitative_qualifier and display_results:
            answer = self._ground_qualitative_answer(
                display_results,
                semantic_resolution.qualitative_qualifier,
            )
        return AgentResponse(
            text=answer,
            display_result=display_result,
            display_results=display_results,
            tool_results=tool_results,
        )

    @staticmethod
    def _build_messages(
        history: Sequence[Mapping[str, str]],
        question: str,
        *,
        semantic_plans: Sequence[SemanticQueryPlan] = (),
    ) -> list[dict[str, str]]:
        messages: list[dict[str, str]] = []
        for item in history[-8:]:
            role = item.get("role", "")
            content = item.get("content", "")
            if role in {"user", "assistant"} and isinstance(content, str):
                messages.append({"role": role, "content": content[:6000]})
        if len(semantic_plans) > 1:
            messages.append(
                {
                    "role": "user",
                    "content": (
                        f"Há {len(semantic_plans)} planos complementares. Execute "
                        "TODOS, exatamente uma chamada analítica por plano, e preserve "
                        "os resultados separados na resposta."
                    ),
                }
            )
        for semantic_plan in semantic_plans:
            # Identificadores do upload permanecem em mensagem de usuário, nunca
            # ganham prioridade de system prompt. A validação pós-tool é a garantia.
            messages.append(
                {"role": "user", "content": semantic_plan.model_guidance()}
            )
        messages.append({"role": "user", "content": question[:12000]})
        return messages

    @staticmethod
    def _match_semantic_results(
        plans: Sequence[SemanticQueryPlan], results: Sequence[ToolResult]
    ) -> list[ToolResult]:
        """Faz correspondência 1:1 e preserva a ordem dos planos."""

        selected: list[ToolResult] = []
        used_indexes: set[int] = set()
        for plan in plans:
            matches = [
                (index, result)
                for index, result in enumerate(results)
                if index not in used_indexes and plan.matches_result(result)
            ]
            if len(matches) != 1:
                return []
            index, result = matches[0]
            used_indexes.add(index)
            selected.append(result)
        return selected

    @staticmethod
    def _ground_qualitative_answer(
        results: Sequence[ToolResult], qualifier: str
    ) -> str:
        evidence: list[str] = []
        for result in results:
            if result.rows:
                fields = "; ".join(
                    f"{column}: {value}"
                    for column, value in result.rows[0].items()
                )
                evidence.append(fields)
            elif result.summary:
                evidence.append(result.summary)
        fact = " | ".join(evidence)
        return (
            f"Os dados sustentam apenas este resultado quantitativo: {fact}. "
            f"Entretanto, essa evidência não sustenta o julgamento qualitativo "
            f"'{qualifier}' sobre a entidade."
        )

    @staticmethod
    def _extract_answer(state: Any) -> str:
        if not isinstance(state, Mapping):
            raise AgentExecutionError("O agente retornou um resultado inválido.")
        messages = state.get("messages")
        if not messages:
            raise AgentExecutionError("O agente não retornou uma resposta.")

        content = getattr(messages[-1], "content", None)
        if content is None and isinstance(messages[-1], Mapping):
            content = messages[-1].get("content")
        if isinstance(content, str) and content.strip():
            return content.strip()
        if isinstance(content, list):
            text_parts = [
                str(block.get("text", ""))
                for block in content
                if isinstance(block, Mapping) and block.get("type") == "text"
            ]
            answer = "\n".join(part for part in text_parts if part).strip()
            if answer:
                return answer
        raise AgentExecutionError("O agente retornou uma resposta vazia.")

    @staticmethod
    def _choose_display_result(results: Sequence[ToolResult]) -> ToolResult | None:
        """Compatibilidade: retorna a última das evidências selecionadas."""

        selected = CSVAgent._choose_display_results(results)
        return selected[-1] if selected else None

    @staticmethod
    def _choose_display_results(results: Sequence[ToolResult]) -> list[ToolResult]:
        """Preserva resultados analíticos sem exibir inspeções intermediárias."""

        if results and results[-1].result_type == "error":
            return [results[-1]]
        displayable = [
            result
            for result in results
            if result.result_type in {"table", "series", "scalar"}
        ]
        substantive = [
            result
            for result in displayable
            if result.metadata.get("tool")
            not in {"list_datasets", "describe_dataset"}
        ]
        return substantive or displayable

    @staticmethod
    def _requires_tool(question: str, answer: str) -> bool:
        normalised = " ".join(question.casefold().split()).strip(" !?.")
        greetings = {
            "oi",
            "olá",
            "ola",
            "bom dia",
            "boa tarde",
            "boa noite",
            "ajuda",
        }
        if normalised in greetings:
            return False
        clarification_terms = (
            "pode esclarecer",
            "poderia esclarecer",
            "especifique",
            "qual dataset",
            "qual coluna",
            "o que você quer dizer",
        )
        if answer.rstrip().endswith("?") and any(
            term in answer.casefold() for term in clarification_terms
        ):
            return False
        return True

    @staticmethod
    def _requires_analytical_result(question: str) -> bool:
        normalised = question.casefold()
        return any(
            term in normalised
            for term in (
                "maior",
                "menor",
                "lider",
                "top",
                "ranking",
                "total",
                "soma",
                "média",
                "media",
                "quantas",
                "quantos",
                "quantidade",
                "volume",
                "gasto",
                "por mês",
                "por mes",
                "por ano",
            )
        ) or bool(re.search(r"\b(sum|mean|count|min|max)\b", normalised))

def create_csv_agent(data_manager: DataManager, settings: Any) -> CSVAgent:
    """Cria o agente a partir do contrato central de configuração."""

    return CSVAgent(
        data_manager,
        api_key=settings.groq_api_key,
        model_name=settings.groq_model,
    )
