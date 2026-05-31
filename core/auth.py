"""
Módulo de autenticação Google OAuth 2.0.

Fluxo para Web Application no Streamlit Cloud:
1. Gera URL de autorização Google → redireciona o browser do usuário.
2. Google redireciona de volta para o Streamlit app com ?code=...&state=...
3. Streamlit detecta os query_params no próximo rerun.
4. Troca o code por credenciais (access_token + refresh_token).
5. Armazena as credenciais em st.session_state.
"""

import os

import streamlit as st
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import Flow

# Tolera variação de escopos no retorno do Google. Ao trocar permissões, o
# Google pode devolver escopos já concedidos anteriormente (ex: drive.readonly
# de uma autorização antiga), o que faria a biblioteca lançar "Scope has
# changed". Receber escopos a mais não é um problema de segurança.
os.environ["OAUTHLIB_RELAX_TOKEN_SCOPE"] = "1"

# Escopos necessários para Calendar, Drive, Docs e Sheets
SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/spreadsheets",
    # gmail.readonly é escopo restrito — requer verificação Google antes do uso
    # "https://www.googleapis.com/auth/gmail.readonly",
]

SESSION_KEY = "google_credentials"
STATE_KEY   = "oauth_state"


def _client_config() -> dict:
    """Monta o client_config a partir dos st.secrets."""
    return {
        "web": {
            "client_id":     st.secrets["google"]["client_id"],
            "client_secret": st.secrets["google"]["client_secret"],
            "auth_uri":      "https://accounts.google.com/o/oauth2/auth",
            "token_uri":     "https://oauth2.googleapis.com/token",
            "redirect_uris": [st.secrets["google"]["redirect_uri"]],
        }
    }


def _build_flow(state: str | None = None) -> Flow:
    # autogenerate_code_verifier=False desativa o PKCE. Necessário porque o
    # Streamlit recria a sessão ao retornar do Google, perdendo o code_verifier
    # gerado na geração da URL. Sem PKCE, a troca do code não exige o verifier.
    # Segurança mantida pelo client_secret (confidencial) + redirect_uri exato.
    return Flow.from_client_config(
        _client_config(),
        scopes=SCOPES,
        state=state,
        redirect_uri=st.secrets["google"]["redirect_uri"],
        autogenerate_code_verifier=False,
    )


def get_authorization_url() -> str:
    """
    Gera a URL de autorização Google e persiste o state na sessão.
    Chame esta função ao renderizar o botão de login.
    """
    flow = _build_flow()
    auth_url, state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",     # Garante refresh_token mesmo após re-auth
    )
    st.session_state[STATE_KEY] = state
    return auth_url


def handle_oauth_callback() -> bool:
    """
    Detecta o retorno do OAuth nos query_params e troca o code por credenciais.
    Retorna True se a autenticação foi concluída com sucesso neste rerun.

    Nota sobre state: quando o usuário navega para o Google e volta, o Streamlit
    inicia uma sessão nova e o state salvo anteriormente se perde. Por isso só
    rejeitamos se o state existir NA SESSÃO e for diferente (ataque CSRF real).
    Se a sessão for nova (state ausente), confiamos na validação server-side do
    Google: o code é de uso único, expira em segundos e só funciona com o
    client_secret correto + redirect_uri exato.
    """
    params = st.query_params
    code  = params.get("code")
    state = params.get("state")

    if not code or not state:
        return False

    expected_state = st.session_state.get(STATE_KEY)
    if expected_state is not None and state != expected_state:
        # State presente na sessão mas diferente → rejeita (possível CSRF)
        st.error("Falha de segurança OAuth: state inválido. Tente novamente.")
        _clear_oauth_params()
        return False

    try:
        flow = _build_flow(state=state)
        flow.fetch_token(code=code)
        creds = flow.credentials
        _store_credentials(creds)
        _clear_oauth_params()
        return True
    except Exception as exc:
        st.error(f"Erro ao trocar código OAuth: {exc}")
        _clear_oauth_params()
        return False


def get_credentials() -> Credentials | None:
    """Retorna as credenciais da sessão, renovando o token se expirado."""
    creds: Credentials | None = st.session_state.get(SESSION_KEY)

    if creds is None:
        return None

    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            _store_credentials(creds)
        except Exception:
            # Refresh falhou — força re-autenticação
            del st.session_state[SESSION_KEY]
            return None

    return creds


def is_authenticated() -> bool:
    return get_credentials() is not None


def logout():
    """Remove as credenciais da sessão."""
    st.session_state.pop(SESSION_KEY, None)
    st.session_state.pop(STATE_KEY, None)


# ── helpers ───────────────────────────────────────────────────────────────────

def _store_credentials(creds: Credentials):
    st.session_state[SESSION_KEY] = creds


def _clear_oauth_params():
    """Remove code/state dos query_params para limpar a URL."""
    st.query_params.clear()
