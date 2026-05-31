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
)
from core.audio import render_audio_input, speak
from core.agent import create_agent, run_agent

# ── Chaves de session_state ───────────────────────────────────────────────────
CHAT_HISTORY_KEY = "chat_history"
AGENT_KEY        = "agent"


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

        # Geramos a URL de autorização a cada render (o state é salvo em
        # session_state junto). Apresentamos como um LINK que o usuário clica:
        # o clique conta como "ação do usuário", então o navegador permite a
        # navegação na mesma aba — preservando a sessão para validar o callback.
        # (Redirect automático via JS é bloqueado dentro do iframe do Codespaces.)
        auth_url = get_authorization_url()
        st.markdown(
            f'''
            <a href="{auth_url}" target="_top" style="
                display:inline-block; width:100%; box-sizing:border-box;
                text-align:center; background:#4F46E5; color:#ffffff;
                padding:0.65rem 1rem; border-radius:0.5rem;
                text-decoration:none; font-weight:600;">
                🔐 Conectar com Google
            </a>
            ''',
            unsafe_allow_html=True,
        )

        st.caption(
            "Escopos solicitados: Calendar (leitura/escrita), "
            "Drive (leitura), Docs (leitura/escrita), perfil básico."
        )


def init_session():
    """Inicializa variáveis de sessão na primeira visita autenticada."""
    if CHAT_HISTORY_KEY not in st.session_state:
        st.session_state[CHAT_HISTORY_KEY] = []

    if AGENT_KEY not in st.session_state:
        creds = get_credentials()
        st.session_state[AGENT_KEY] = create_agent(creds)


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

# PASSO 1: Detecta e trata o callback OAuth antes de qualquer renderização.
# Quando o Google redireciona de volta, os query_params contêm code + state.
oauth_just_completed = handle_oauth_callback()
if oauth_just_completed:
    st.rerun()  # Rerun limpo após persistir as credenciais

# PASSO 2: Processa quick prompts (ações rápidas ou voz), se houver
if "_quick_prompt" in st.session_state and is_authenticated():
    pending_prompt   = st.session_state.pop("_quick_prompt")
    pending_by_voice = st.session_state.pop("_prompt_by_voice", False)
else:
    pending_prompt   = None
    pending_by_voice = False

# PASSO 3: Roteamento — login ou app
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
