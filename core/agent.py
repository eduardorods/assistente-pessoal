"""
Agente LangGraph com arquitetura ReAct.

Fluxo:
  usuário → [nó: agent] → decide ferramenta? → [nó: tools] → [nó: agent] → resposta
                                              ↓ não
                                           resposta final

O agente é recriado a cada sessão (as tools dependem das credenciais Google).
"""

from __future__ import annotations

import streamlit as st
from google.oauth2.credentials import Credentials

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, BaseMessage
from langgraph.graph import StateGraph, MessagesState, END
from langgraph.prebuilt import ToolNode, tools_condition

from core.tools.calendar_tool import make_calendar_tools
from core.tools.drive_tool    import make_drive_tools
from core.tools.scraper_tool  import make_scraper_tools

SYSTEM_PROMPT = """Você é um assistente pessoal inteligente e proativo, integrado ao Google Workspace.

Suas capacidades:
- **Google Calendar**: consultar agenda, criar/reagendar/cancelar eventos, encontrar horários livres.
- **Google Drive & Docs**: buscar documentos, ler conteúdo, fazer análises com RAG, criar documentos.
- **Web Scraping**: acessar páginas públicas para monitorar relatórios e notícias de mercado.

Diretrizes:
- Responda sempre em português brasileiro.
- Seja conciso, direto e útil. Use markdown para formatar respostas longas.
- Ao criar ou alterar eventos, confirme os detalhes antes de executar.
- Ao usar RAG, cite o nome do documento fonte.
- Equilibre proativamente compromissos profissionais com blocos de tempo pessoal na agenda.
- Se não encontrar uma informação, diga claramente e sugira alternativas.
"""


def create_agent(creds: Credentials):
    """
    Monta e compila o grafo LangGraph para a sessão atual.
    Recria toda vez que chamado — as tools fecham sobre as credenciais.
    """
    tools = (
        make_calendar_tools(creds)
        + make_drive_tools(creds)
        + make_scraper_tools()
    )

    llm = ChatGoogleGenerativeAI(
        model="gemini-2.5-flash",
        google_api_key=st.secrets["gemini"]["api_key"],
        temperature=0.3,
        max_output_tokens=4096,
    ).bind_tools(tools)

    # ── nós ────────────────────────────────────────────────────────────────────

    def call_model(state: MessagesState):
        messages = [SystemMessage(content=SYSTEM_PROMPT)] + state["messages"]
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
    result = agent.invoke({"messages": messages})
    last   = result["messages"][-1]
    return last.content if hasattr(last, "content") else str(last)
