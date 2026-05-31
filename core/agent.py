"""
Agente LangGraph com arquitetura ReAct.

Fluxo:
  usuário → [nó: agent] → decide ferramenta? → [nó: tools] → [nó: agent] → resposta
                                              ↓ não
                                           resposta final

O agente é recriado a cada sessão (as tools dependem das credenciais Google).
"""

from __future__ import annotations

from datetime import datetime

import pytz
import streamlit as st
from google.oauth2.credentials import Credentials

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, BaseMessage
from langgraph.graph import StateGraph, MessagesState, END
from langgraph.prebuilt import ToolNode, tools_condition

from core.tools.calendar_tool import make_calendar_tools
from core.tools.drive_tool    import make_drive_tools
from core.tools.sheets_tool   import make_sheets_tools
from core.tools.gmail_tool    import make_gmail_tools
from core.tools.memory_tool   import make_memory_tools
from core.tools.scraper_tool  import make_scraper_tools
from core.tools.search_tool   import make_search_tools
from core.profile             import get_user_profile

SYSTEM_PROMPT = """Você é um assistente pessoal inteligente e proativo, integrado ao Google Workspace.

Suas capacidades:
- **Google Calendar**: consultar agenda, criar/reagendar/cancelar eventos, encontrar horários livres.
- **Google Drive & Docs**: buscar documentos, ler conteúdo, fazer análises com RAG, criar e editar documentos.
- **Google Sheets**: criar planilhas, adicionar/ler/atualizar dados, duplicar/copiar abas (ex: replicar modelo mensal) e substituir texto em massa em uma aba (ex: atualizar datas "2026/05" → "2026/06").
- **Gmail**: listar e-mails não lidos com resumo, ler mensagens, salvar anexos no Drive.
- **Memória**: lembrar e memorizar fatos sobre o usuário ao longo do tempo (tools lembrar/memorizar).
- **Busca na internet**: pesquisar qualquer assunto público (notícias, clima, cotações, fatos atuais) com a ferramenta buscar_internet.
- **Web Scraping**: acessar uma URL específica para monitorar relatórios e notícias de mercado.

Diretrizes:
- Responda sempre em português brasileiro.
- Seja conciso, direto e útil. Use markdown para formatar respostas longas.
- O fuso horário padrão é America/Sao_Paulo e a cidade padrão do usuário é
  **São Paulo, SP, Brasil**. Use esses padrões sempre que não for especificado
  outra localização. NUNCA pergunte o fuso ou a cidade ao usuário.
- Ao criar ou alterar eventos, confirme os detalhes antes de executar.
- Ao usar RAG, cite o nome do documento fonte.
- Use o nome do usuário (perfil) ao se dirigir a ele, de forma natural.
- Quando o usuário compartilhar uma preferência, decisão ou fato relevante e
  duradouro, use a tool 'memorizar' para registrá-lo. Não memorize trivialidades.

GESTÃO DE ROTINA (trabalho × vida pessoal):
- Ao analisar a agenda, identifique desequilíbrios (ex: dias sobrecarregados
  de reuniões, ausência de tempo pessoal, refeições ou exercício).
- Proponha proativamente blocos protegidos de tempo pessoal (treino/musculação,
  família, foco). Só crie eventos após confirmação do usuário.
- Ao agendar compromissos profissionais, verifique conflito com blocos pessoais
  já existentes e avise antes de sobrepor.

BRIEFING DIÁRIO:
- Quando o usuário pedir um "briefing", "resumo do dia" ou "bom dia", produza um
  resumo conciso combinando: e-mails não lidos (listar_emails), agenda do dia
  (listar_eventos) e qualquer lembrete relevante da memória (lembrar).

FLUXO DE CAIXA MENSAL:
- Planilha de fluxo de caixa: ID `1DK3x-OBMGFYb7lVgt1a2fN77ZP8q6xT2Cc2etAKrayM`
- Cada mês tem SEMPRE um par de abas:
    • `mai26`      — dados brutos do mês (datas no formato `2026-05-DD`)
    • `fxcx_mai26` — resumo/análise com fórmulas que referenciam `mai26`
- Nomes de aba: 3 letras do mês em português + 2 dígitos do ano (mai26, jun26, jul26…).
- Quando o usuário pedir "abrir o mês de X", "criar aba de X" ou "virar o mês",
  use a tool `abrir_mes` passando aba_origem (mês atual) e aba_destino (novo mês).
  Ela faz tudo automaticamente:
    1. Duplica `mai26` → `jun26`
    2. Duplica `fxcx_mai26` → `fxcx_jun26`
    3. Atualiza prefixo de datas em `jun26` (2026-05 → 2026-06)
    4. Atualiza referências de aba em `fxcx_jun26` (mai26 → jun26), preservando fórmulas
- Confirme apenas aba_origem e aba_destino antes de executar.
"""


def _current_datetime_context() -> str:
    """Gera uma linha com data/hora atual no fuso de São Paulo."""
    tz  = pytz.timezone("America/Sao_Paulo")
    now = datetime.now(tz)
    dias   = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira",
              "sexta-feira", "sábado", "domingo"]
    dia_semana = dias[now.weekday()]
    return (
        f"\n\nDATA/HORA ATUAL: {dia_semana}, {now.strftime('%d/%m/%Y %H:%M')} "
        f"(fuso America/Sao_Paulo)."
    )


def create_agent(creds: Credentials):
    """
    Monta e compila o grafo LangGraph para a sessão atual.
    Recria toda vez que chamado — as tools fecham sobre as credenciais.
    """
    tools = (
        make_calendar_tools(creds)
        + make_drive_tools(creds)
        + make_sheets_tools(creds)
        + make_gmail_tools(creds)
        + make_memory_tools(creds)
        + make_scraper_tools()
        + make_search_tools()
    )

    llm = ChatGoogleGenerativeAI(
        model="gemini-2.5-flash",
        google_api_key=st.secrets["gemini"]["api_key"],
        temperature=0.3,
        max_output_tokens=4096,
    ).bind_tools(tools)

    # ── nós ────────────────────────────────────────────────────────────────────

    # Perfil é estático na sessão — lê uma vez ao montar o agente.
    user_profile = get_user_profile()

    def call_model(state: MessagesState):
        # Injeta data/hora atual e perfil do usuário a cada chamada.
        system_content = SYSTEM_PROMPT + _current_datetime_context() + user_profile
        messages = [SystemMessage(content=system_content)] + state["messages"]
        response = llm.invoke(messages)
        return {"messages": [response]}

    tool_node = ToolNode(tools)

    # ── grafo ──────────────────────────────────────────────────────────────────

    graph = StateGraph(MessagesState)
    graph.add_node("agent", call_model)
    graph.add_node("tools", tool_node)

    graph.set_entry_point("agent")
    graph.add_conditional_edges("agent", tools_condition)
    graph.add_edge("tools", "agent")

    return graph.compile()


def run_agent(agent, messages: list[BaseMessage]) -> str:
    """
    Executa o agente com o histórico de mensagens e retorna a resposta final.
    """
    result  = agent.invoke({"messages": messages})
    last    = result["messages"][-1]
    content = last.content if hasattr(last, "content") else str(last)

    # Gemini via LangChain pode retornar content como lista de blocos
    # ex: [{'type': 'text', 'text': '...', 'extras': {...}}]
    if isinstance(content, list):
        content = " ".join(
            block["text"]
            for block in content
            if isinstance(block, dict) and block.get("type") == "text" and block.get("text")
        ).strip()

    # Blindagem: nunca devolver resposta vazia ao usuário.
    if not content or not str(content).strip():
        return (
            "Concluí o processamento, mas não recebi um texto de resposta do modelo. "
            "Pode reformular o pedido ou tentar novamente?"
        )

    return content
