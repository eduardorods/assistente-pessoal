"""
Ferramentas LangChain para Google Drive e Docs.

Inclui:
- Busca textual no Drive
- Leitura de documentos (Docs, Sheets como texto)
- RAG via LlamaIndex sobre o conteúdo dos documentos
- Criação de novos Google Docs
"""

from __future__ import annotations

import io
import streamlit as st
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from google.oauth2.credentials import Credentials
from langchain_core.tools import tool

from llama_index.core import VectorStoreIndex, Document
from llama_index.llms.gemini import Gemini
from llama_index.embeddings.gemini import GeminiEmbedding


# ── helpers privados ──────────────────────────────────────────────────────────

def _drive(creds: Credentials):
    return build("drive", "v3", credentials=creds)


def _docs(creds: Credentials):
    return build("docs", "v1", credentials=creds)


def _sheets(creds: Credentials):
    return build("sheets", "v4", credentials=creds)


def _extract_doc_text(creds: Credentials, file_id: str, mime: str) -> str:
    """Extrai texto de um arquivo Drive de acordo com o MIME type."""
    drive_service = _drive(creds)

    if mime == "application/vnd.google-apps.document":
        docs_service = _docs(creds)
        doc = docs_service.documents().get(documentId=file_id).execute()
        return _parse_docs_body(doc.get("body", {}).get("content", []))

    if mime == "application/vnd.google-apps.spreadsheet":
        # Exporta como CSV do primeiro sheet
        request  = drive_service.files().export_media(fileId=file_id, mimeType="text/csv")
        buf = io.BytesIO()
        dl  = MediaIoBaseDownload(buf, request)
        done = False
        while not done:
            _, done = dl.next_chunk()
        return buf.getvalue().decode("utf-8")

    # Arquivo binário ou tipo não suportado: exporta como texto plano
    try:
        request = drive_service.files().export_media(fileId=file_id, mimeType="text/plain")
        buf = io.BytesIO()
        dl  = MediaIoBaseDownload(buf, request)
        done = False
        while not done:
            _, done = dl.next_chunk()
        return buf.getvalue().decode("utf-8")
    except Exception:
        return "(conteúdo não pôde ser extraído)"


def _parse_docs_body(content: list) -> str:
    """Extrai texto puro do corpo de um Google Doc."""
    lines = []
    for block in content:
        paragraph = block.get("paragraph")
        if not paragraph:
            continue
        for elem in paragraph.get("elements", []):
            text_run = elem.get("textRun")
            if text_run:
                lines.append(text_run.get("content", ""))
    return "".join(lines)


@st.cache_resource(ttl=600, show_spinner=False)
def _build_rag_index(_creds_token: str, file_ids: tuple[str, ...], creds: Credentials):
    """
    Constrói um índice LlamaIndex em memória com os documentos fornecidos.
    Cacheia por 10 min para evitar re-indexação a cada pergunta.
    O argumento _creds_token é usado como chave de cache (não enviado à API).
    """
    gemini_key = st.secrets["gemini"]["api_key"]
    llm   = Gemini(model="models/gemini-2.5-flash", api_key=gemini_key)
    embed = GeminiEmbedding(model_name="models/text-embedding-004", api_key=gemini_key)

    docs = []
    drive_service = _drive(creds)
    for fid in file_ids:
        meta = drive_service.files().get(fileId=fid, fields="name,mimeType").execute()
        text = _extract_doc_text(creds, fid, meta["mimeType"])
        docs.append(Document(text=text, metadata={"file_id": fid, "name": meta["name"]}))

    return VectorStoreIndex.from_documents(docs, llm=llm, embed_model=embed)


# ── Ferramentas públicas ──────────────────────────────────────────────────────

def make_drive_tools(creds: Credentials) -> list:
    """Retorna a lista de tools para Drive/Docs instanciadas com credenciais."""

    @tool
    def buscar_documentos(query: str, max_results: int = 10) -> str:
        """
        Busca arquivos no Google Drive pelo nome ou conteúdo.
        Args:
            query:       Termos de busca.
            max_results: Número máximo de resultados (padrão: 10).
        """
        service = _drive(creds)
        escaped = query.replace("'", "\\'")
        result  = service.files().list(
            q=f"fullText contains '{escaped}' and trashed = false",
            fields="files(id, name, mimeType, modifiedTime, webViewLink)",
            pageSize=max_results,
            orderBy="modifiedTime desc",
        ).execute()

        files = result.get("files", [])
        if not files:
            return "Nenhum documento encontrado."

        linhas = []
        for f in files:
            modified = f.get("modifiedTime", "")[:10]
            linhas.append(
                f"• [{f['name']}]({f.get('webViewLink','#')}) "
                f"| ID: `{f['id']}` | Modificado: {modified}"
            )
        return "\n".join(linhas)

    @tool
    def ler_documento(file_id: str) -> str:
        """
        Lê e retorna o conteúdo textual de um documento Google Drive.
        Args:
            file_id: ID do arquivo (obtido de buscar_documentos).
        """
        service = _drive(creds)
        meta    = service.files().get(fileId=file_id, fields="name,mimeType").execute()
        text    = _extract_doc_text(creds, file_id, meta["mimeType"])
        return f"**{meta['name']}**\n\n{text[:8000]}"   # Trunca para caber no contexto

    @tool
    def perguntar_sobre_documentos(pergunta: str, file_ids: list[str]) -> str:
        """
        Faz uma pergunta sobre o conteúdo de um ou mais documentos do Drive (RAG).
        Args:
            pergunta: Pergunta em linguagem natural.
            file_ids: Lista de IDs de arquivos a incluir no contexto.
        """
        # Usa token do access_token como chave de cache (não o objeto inteiro)
        cache_key = creds.token or "no-token"
        index     = _build_rag_index(cache_key, tuple(file_ids), creds)
        engine    = index.as_query_engine()
        response  = engine.query(pergunta)
        return str(response)

    @tool
    def criar_documento(titulo: str, conteudo: str) -> str:
        """
        Cria um novo Google Doc com o conteúdo fornecido.
        Args:
            titulo:   Título do documento.
            conteudo: Texto inicial do documento.
        """
        docs_service = _docs(creds)
        doc = docs_service.documents().create(body={"title": titulo}).execute()
        doc_id = doc["documentId"]

        requests_body = [
            {
                "insertText": {
                    "location": {"index": 1},
                    "text": conteudo,
                }
            }
        ]
        docs_service.documents().batchUpdate(
            documentId=doc_id, body={"requests": requests_body}
        ).execute()

        link = f"https://docs.google.com/document/d/{doc_id}/edit"
        return f"Documento criado: [{titulo}]({link})"

    @tool
    def adicionar_texto_ao_documento(file_id: str, texto: str) -> str:
        """
        Adiciona texto ao FINAL de um Google Doc existente.
        Use para incluir novos parágrafos, seções ou anotações num documento já criado.
        Args:
            file_id: ID do documento Google Docs.
            texto:   Texto a ser adicionado no final do documento.
        """
        docs_service = _docs(creds)
        doc = docs_service.documents().get(documentId=file_id).execute()

        # Posição final do documento (antes do caractere de fim de arquivo)
        end_index = doc["body"]["content"][-1]["endIndex"] - 1

        requests_body = [
            {
                "insertText": {
                    "location": {"index": end_index},
                    "text": f"\n{texto}",
                }
            }
        ]
        docs_service.documents().batchUpdate(
            documentId=file_id, body={"requests": requests_body}
        ).execute()

        titulo = doc.get("title", file_id)
        link   = f"https://docs.google.com/document/d/{file_id}/edit"
        return f"Texto adicionado ao final de [{titulo}]({link})"

    @tool
    def substituir_texto_no_documento(file_id: str, texto_antigo: str, texto_novo: str) -> str:
        """
        Substitui uma ocorrência de texto em um Google Doc existente.
        Útil para corrigir trechos, atualizar dados ou reformular parágrafos.
        Args:
            file_id:      ID do documento Google Docs.
            texto_antigo: Trecho exato a ser substituído.
            texto_novo:   Novo texto que substituirá o trecho.
        """
        docs_service = _docs(creds)
        requests_body = [
            {
                "replaceAllText": {
                    "containsText": {
                        "text":      texto_antigo,
                        "matchCase": False,
                    },
                    "replaceText": texto_novo,
                }
            }
        ]
        result = docs_service.documents().batchUpdate(
            documentId=file_id, body={"requests": requests_body}
        ).execute()

        ocorrencias = (
            result.get("replies", [{}])[0]
            .get("replaceAllText", {})
            .get("occurrencesChanged", 0)
        )
        doc   = docs_service.documents().get(documentId=file_id).execute()
        titulo = doc.get("title", file_id)
        link   = f"https://docs.google.com/document/d/{file_id}/edit"

        if ocorrencias == 0:
            return f"Trecho não encontrado no documento [{titulo}]({link}). Verifique o texto exato."
        return f"{ocorrencias} ocorrência(s) substituída(s) em [{titulo}]({link})"

    return [
        buscar_documentos,
        ler_documento,
        perguntar_sobre_documentos,
        criar_documento,
        adicionar_texto_ao_documento,
        substituir_texto_no_documento,
    ]
