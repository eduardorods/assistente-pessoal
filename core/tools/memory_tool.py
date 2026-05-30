"""
Memória persistente do assistente via Google Doc.

O agente mantém um documento especial (criado automaticamente na primeira
vez) onde registra fatos, preferências e contexto sobre o usuário ao longo
do tempo. Diferente do perfil estático, esta memória é dinâmica: o agente
escreve nela quando aprende algo novo e a lê no início das conversas.

Implementação: o ID do doc de memória é guardado em st.session_state após
ser encontrado/criado por nome no Drive, evitando recriação a cada uso.
"""

from __future__ import annotations

import streamlit as st
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from langchain_core.tools import tool

MEMORY_DOC_NAME = "🧠 Memória do Assistente Pessoal"
_MEMORY_ID_KEY  = "memory_doc_id"


def _drive(creds: Credentials):
    return build("drive", "v3", credentials=creds)


def _docs(creds: Credentials):
    return build("docs", "v1", credentials=creds)


def _get_or_create_memory_doc(creds: Credentials) -> str:
    """Encontra o doc de memória por nome, ou cria se não existir. Retorna o ID."""
    if _MEMORY_ID_KEY in st.session_state:
        return st.session_state[_MEMORY_ID_KEY]

    drive = _drive(creds)
    # Procura um doc existente com o nome reservado
    result = drive.files().list(
        q=(
            f"name = '{MEMORY_DOC_NAME}' "
            "and mimeType = 'application/vnd.google-apps.document' "
            "and trashed = false"
        ),
        fields="files(id)",
        pageSize=1,
    ).execute()

    files = result.get("files", [])
    if files:
        doc_id = files[0]["id"]
    else:
        # Cria o documento de memória
        doc = _docs(creds).documents().create(
            body={"title": MEMORY_DOC_NAME}
        ).execute()
        doc_id = doc["documentId"]

    st.session_state[_MEMORY_ID_KEY] = doc_id
    return doc_id


def _read_doc_text(creds: Credentials, doc_id: str) -> str:
    doc = _docs(creds).documents().get(documentId=doc_id).execute()
    lines = []
    for block in doc.get("body", {}).get("content", []):
        paragraph = block.get("paragraph")
        if not paragraph:
            continue
        for elem in paragraph.get("elements", []):
            text_run = elem.get("textRun")
            if text_run:
                lines.append(text_run.get("content", ""))
    return "".join(lines)


def make_memory_tools(creds: Credentials) -> list:
    """Retorna as tools de memória persistente."""

    @tool
    def lembrar() -> str:
        """
        Lê a memória de longo prazo do assistente (fatos e preferências do usuário
        registrados em conversas anteriores). Use no início de tarefas para ter
        contexto sobre o usuário.
        """
        doc_id = _get_or_create_memory_doc(creds)
        texto  = _read_doc_text(creds, doc_id).strip()
        if not texto:
            return "A memória ainda está vazia. Use 'memorizar' para registrar fatos importantes."
        return f"Memória atual:\n{texto}"

    @tool
    def memorizar(fato: str) -> str:
        """
        Registra um novo fato ou preferência na memória de longo prazo do assistente.
        Use quando o usuário compartilhar algo que valha lembrar no futuro
        (preferências, decisões, contexto de projetos, datas importantes).
        Args:
            fato: O fato a ser memorizado, em uma frase clara.
        """
        from datetime import datetime
        import pytz

        doc_id = _get_or_create_memory_doc(creds)
        docs   = _docs(creds)

        # Insere o novo fato no final, com data
        doc = docs.documents().get(documentId=doc_id).execute()
        end_index = doc["body"]["content"][-1]["endIndex"] - 1

        tz   = pytz.timezone("America/Sao_Paulo")
        data = datetime.now(tz).strftime("%d/%m/%Y")

        docs.documents().batchUpdate(
            documentId=doc_id,
            body={"requests": [{
                "insertText": {
                    "location": {"index": end_index},
                    "text": f"\n• [{data}] {fato}",
                }
            }]},
        ).execute()

        return f"Memorizado: {fato}"

    return [lembrar, memorizar]
