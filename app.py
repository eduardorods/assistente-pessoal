"""
Assistente Pessoal Inteligente — app principal Streamlit.

Gerencia:
1. Fluxo OAuth 2.0 do Google (detecção de callback, troca de tokens).
2. Interface de chat multimodal (texto + voz).
3. Inicialização e execução do agente LangGraph.
"""

import streamlit as st
from langchain_core.messages import HumanMessage, AIMessage

# ── Configuração da página — DEVE ser a primeira chamada Streamlit ────────────
st.set_page_config(
    page_title="Assistente Pessoal IA",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
)

from core.auth  import (
    get_authorization_url,
    handle_oauth_callback,
    get_credentials,
    is_authenticated,
    logout,
    init_cookie_manager,
    try_restore_from_cookie,
)
from core.audio import render_audio_input, speak
from core.agent import create_agent, run_agent

# ── Chaves de session_state ───────────────────────────────────────────────────
CHAT_HISTORY_KEY = "chat_history"
AGENT_KEY        = "agent"
AGENT_VER_KEY    = "agent_version"

# Versão do agente. Incremente sempre que tools/system prompt mudarem para
# forçar a recriação do agente em sessões já abertas (sem precisar de logout).
AGENT_VERSION = "2026-05-31-sheets-v4"


# =============================================================================
# Funções de renderização (definidas antes de serem chamadas)
# =============================================================================

def render_login_screen():
    """Tela de boas-vindas e botão de login Google."""
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("## 🤖 Assistente Pessoal IA")
        st.markdown(
            "Seu assistente integrado ao Google Workspace.  \n"
            "Conecte sua conta Google para começar."
        )
        st.divider()

        auth_url = get_authorization_url()
        st.link_button(
            "🔐 Conectar com Google",
            auth_url,
            use_container_width=True,
            type="primary",
        )

        st.caption(
            "Escopos solicitados: Calendar (leitura/escrita), "
            "Drive (leitura), Docs (leitura/escrita), perfil básico."
        )


def init_session():
    """Inicializa variáveis de sessão na primeira visita autenticada."""
    if CHAT_HISTORY_KEY not in st.session_state:
        st.session_state[CHAT_HISTORY_KEY] = []

    # Recria o agente se ele não existe ou se a versão do código mudou
    # (após um redeploy do app). Evita tools antigas cacheadas na sessão.
    if (AGENT_KEY not in st.session_state
            or st.session_state.get(AGENT_VER_KEY) != AGENT_VERSION):
        creds = get_credentials()
        st.session_state[AGENT_KEY]     = create_agent(creds)
        st.session_state[AGENT_VER_KEY] = AGENT_VERSION


def render_sidebar():
    """Painel lateral com informações do usuário e ações rápidas."""
    with st.sidebar:
        st.markdown("### 🤖 Assistente Pessoal")
        st.divider()

        # Exibe e-mail do usuário se disponível no id_token
        creds = get_credentials()
        if creds and getattr(creds, "id_token", None):
            import json, base64
            try:
                payload = creds.id_token.split(".")[1]
                payload += "=" * (-len(payload) % 4)
                info = json.loads(base64.b64decode(payload))
                st.caption(f"👤 {info.get('email', '')}")
            except Exception:
                pass

        st.divider()
        st.markdown("**Ações Rápidas**")

        if st.button("📅  Ver agenda hoje", use_container_width=True):
            st.session_state["_quick_prompt"] = "Liste minha agenda de hoje."
            st.rerun()

        if st.button("🔍  Buscar documentos", use_container_width=True):
            st.session_state["_quick_prompt"] = "Busque nos meus documentos do Drive por:"
            st.rerun()

        if st.button("⏰  Horários livres", use_container_width=True):
            st.session_state["_quick_prompt"] = (
                "Encontre um horário livre de 1 hora nos próximos 3 dias úteis."
            )
            st.rerun()

        if st.button("📝  Criar documento", use_container_width=True):
            st.session_state["_quick_prompt"] = "Crie um novo Google Doc com o título:"
            st.rerun()

        st.divider()

        if st.button("🗑️  Limpar conversa", use_container_width=True):
            st.session_state[CHAT_HISTORY_KEY] = []
            st.rerun()

        if st.button("🚪  Sair", use_container_width=True):
            st.session_state.pop(AGENT_KEY, None)
            st.session_state.pop(CHAT_HISTORY_KEY, None)
            logout()
            st.rerun()

        st.divider()
        st.caption("Powered by Gemini · LangGraph · Google Workspace")


def process_message(text: str, falar: bool = False):
    """
    Envia a mensagem ao agente e exibe a resposta.
    Se falar=True, a resposta também é lida em voz alta (TTS no navegador).
    """
    history: list = st.session_state[CHAT_HISTORY_KEY]
    agent         = st.session_state[AGENT_KEY]

    with st.chat_message("user"):
        st.markdown(text)

    history.append(HumanMessage(content=text))

    with st.chat_message("assistant"):
        with st.spinner("Pensando…"):
            try:
                response = run_agent(agent, history)
            except Exception as exc:
                response = f"❌ Erro ao processar: {exc}"
        st.markdown(response)
        if falar and not response.startswith("❌"):
            speak(response)

    history.append(AIMessage(content=response))
    st.session_state[CHAT_HISTORY_KEY] = history


def render_chat():
    """Interface principal de chat com suporte a texto e voz."""
    st.markdown("### 💬 Chat")

    history: list = st.session_state.get(CHAT_HISTORY_KEY, [])

    for msg in history:
        if isinstance(msg, HumanMessage):
            with st.chat_message("user"):
                st.markdown(msg.content)
        elif isinstance(msg, AIMessage):
            with st.chat_message("assistant"):
                st.markdown(msg.content)

    # ── Entrada por voz (envio automático) ────────────────────────────────────
    # Assim que a transcrição fica pronta, enviamos automaticamente — sem botão.
    # render_audio_input deduplica por hash, então não reenvia a mesma gravação.
    # Guardamos em _quick_prompt e deixamos o fluxo principal processar.
    with st.expander("🎙️ Entrada por voz", expanded=False):
        st.caption("Grave e a mensagem é enviada automaticamente. A resposta será falada.")
        transcribed = render_audio_input()
        if transcribed:
            st.session_state["_quick_prompt"]  = transcribed
            st.session_state["_prompt_by_voice"] = True
            st.rerun()

    # ── Entrada por texto ─────────────────────────────────────────────────────
    user_input = st.chat_input("Digite sua mensagem…")
    if user_input:
        process_message(user_input)


# =============================================================================
# Fluxo principal — executado a cada rerun do Streamlit
# =============================================================================

# PASSO 1: Renderiza o componente de cookies (necessário antes de qualquer leitura).
init_cookie_manager()

# PASSO 2: Detecta e trata o callback OAuth.
oauth_just_completed = handle_oauth_callback()
if oauth_just_completed:
    st.rerun()

# PASSO 3: Tenta restaurar sessão a partir do cookie (evita re-login).
# O CookieManager precisa de um render para disponibilizar os dados,
# por isso só tenta uma vez por sessão (flag _cookie_checked).
if not is_authenticated() and "_cookie_checked" not in st.session_state:
    st.session_state["_cookie_checked"] = True
    if try_restore_from_cookie():
        # Garante que o agente seja recriado com as tools da versão atual do app.
        st.session_state.pop(AGENT_KEY, None)
        st.rerun()

# PASSO 4: Processa quick prompts (ações rápidas ou voz), se houver
if "_quick_prompt" in st.session_state and is_authenticated():
    pending_prompt   = st.session_state.pop("_quick_prompt")
    pending_by_voice = st.session_state.pop("_prompt_by_voice", False)
else:
    pending_prompt   = None
    pending_by_voice = False

# PASSO 5: Roteamento — login ou app
if not is_authenticated():
    render_login_screen()
else:
    init_session()
    render_sidebar()
    render_chat()

    # Injeta o quick prompt após renderizar o chat (para aparecer no histórico).
    # Se veio por voz, a resposta é lida em voz alta (TTS).
    if pending_prompt:
        process_message(pending_prompt, falar=pending_by_voice)
