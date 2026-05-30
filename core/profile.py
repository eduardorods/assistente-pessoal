"""
Perfil do usuário.

Lê os dados pessoais do st.secrets (seção [user_profile]) e os formata
para injeção no system prompt do agente. Os dados reais ficam apenas no
secrets.toml (fora do controle de versão), nunca no repositório.
"""

import streamlit as st


def get_user_profile() -> str:
    """
    Retorna o bloco de perfil do usuário formatado para o system prompt.
    Se não houver perfil configurado, retorna string vazia.
    """
    try:
        info = st.secrets["user_profile"]["info"]
    except (KeyError, FileNotFoundError):
        return ""

    if not info or not info.strip():
        return ""

    return (
        "\n\nPERFIL DO USUÁRIO (use para personalizar o atendimento, "
        "mas nunca exponha dados sensíveis sem necessidade):\n"
        f"{info.strip()}"
    )
