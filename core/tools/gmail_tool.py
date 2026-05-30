"""
Ferramentas LangChain para Gmail.

Operações:
- Listar e-mails não lidos / recentes com resumo
- Ler conteúdo completo de uma mensagem
- Listar anexos de uma mensagem
- Salvar anexos numa pasta do Google Drive (após confirmação do usuário)
"""

from __future__ import annotations

import base64
from email.utils import parseaddr

from googleapiclient.discovery import build
from googleapiclient.http import MediaInMemoryUpload
from google.oauth2.credentials import Credentials
from langchain_core.tools import tool


def _gmail(creds: Credentials):
    return build("gmail", "v1", credentials=creds)


def _drive(creds: Credentials):
    return build("drive", "v3", credentials=creds)


def _header(headers: list, name: str) -> str:
    for h in headers:
        if h.get("name", "").lower() == name.lower():
            return h.get("value", "")
    return ""


def make_gmail_tools(creds: Credentials) -> list:
    """Retorna a lista de tools do Gmail."""

    @tool
    def listar_emails(apenas_nao_lidos: bool = True, max_resultados: int = 10) -> str:
        """
        Lista e-mails recentes da caixa de entrada com remetente, assunto e prévia.
        Args:
            apenas_nao_lidos: Se True, lista só os não lidos (padrão: True).
            max_resultados:   Número máximo de e-mails (padrão: 10).
        """
        service = _gmail(creds)
        query   = "is:unread" if apenas_nao_lidos else ""

        result = service.users().messages().list(
            userId="me", q=query, maxResults=max_resultados, labelIds=["INBOX"],
        ).execute()

        mensagens = result.get("messages", [])
        if not mensagens:
            return "Nenhum e-mail encontrado." if not apenas_nao_lidos else "Nenhum e-mail não lido. 🎉"

        linhas = []
        for m in mensagens:
            msg = service.users().messages().get(
                userId="me", id=m["id"], format="metadata",
                metadataHeaders=["From", "Subject", "Date"],
            ).execute()
            headers = msg.get("payload", {}).get("headers", [])
            remetente = parseaddr(_header(headers, "From"))[0] or _header(headers, "From")
            assunto   = _header(headers, "Subject") or "(sem assunto)"
            preview   = msg.get("snippet", "")[:120]
            linhas.append(
                f"• **{assunto}**\n  De: {remetente} | ID: `{m['id']}`\n  _{preview}…_"
            )

        return "\n\n".join(linhas)

    @tool
    def ler_email(message_id: str) -> str:
        """
        Lê o conteúdo completo de um e-mail específico.
        Args:
            message_id: ID da mensagem (obtido em listar_emails).
        """
        service = _gmail(creds)
        msg = service.users().messages().get(
            userId="me", id=message_id, format="full",
        ).execute()

        headers   = msg.get("payload", {}).get("headers", [])
        remetente = _header(headers, "From")
        assunto   = _header(headers, "Subject") or "(sem assunto)"
        data      = _header(headers, "Date")

        corpo = _extract_body(msg.get("payload", {}))
        anexos = _list_attachments(msg.get("payload", {}))
        anexos_msg = ""
        if anexos:
            nomes = ", ".join(a["filename"] for a in anexos)
            anexos_msg = f"\n\n📎 Anexos: {nomes}"

        return (
            f"**{assunto}**\nDe: {remetente}\nData: {data}\n\n{corpo[:4000]}{anexos_msg}"
        )

    @tool
    def salvar_anexos_no_drive(message_id: str, nome_pasta: str = "Anexos Email") -> str:
        """
        Salva todos os anexos de um e-mail numa pasta do Google Drive.
        IMPORTANTE: confirme com o usuário antes de executar esta ação.
        Args:
            message_id: ID da mensagem com os anexos.
            nome_pasta: Nome da pasta no Drive onde salvar (padrão: "Anexos Email").
        """
        gmail = _gmail(creds)
        drive = _drive(creds)

        msg = gmail.users().messages().get(
            userId="me", id=message_id, format="full",
        ).execute()
        anexos = _list_attachments(msg.get("payload", {}))

        if not anexos:
            return "Este e-mail não possui anexos."

        # Encontra ou cria a pasta de destino
        folder_id = _get_or_create_folder(drive, nome_pasta)

        salvos = []
        for anexo in anexos:
            att = gmail.users().messages().attachments().get(
                userId="me", messageId=message_id, id=anexo["attachment_id"],
            ).execute()
            file_data = base64.urlsafe_b64decode(att["data"])

            media = MediaInMemoryUpload(file_data, mimetype=anexo["mime_type"])
            drive.files().create(
                body={"name": anexo["filename"], "parents": [folder_id]},
                media_body=media,
                fields="id",
            ).execute()
            salvos.append(anexo["filename"])

        link = f"https://drive.google.com/drive/folders/{folder_id}"
        return f"{len(salvos)} anexo(s) salvo(s) na pasta [{nome_pasta}]({link}): {', '.join(salvos)}"

    return [listar_emails, ler_email, salvar_anexos_no_drive]


# ── helpers ───────────────────────────────────────────────────────────────────

def _extract_body(payload: dict) -> str:
    """Extrai o corpo textual de um e-mail (prefere text/plain)."""
    if payload.get("mimeType") == "text/plain":
        data = payload.get("body", {}).get("data", "")
        if data:
            return base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")

    for part in payload.get("parts", []):
        text = _extract_body(part)
        if text:
            return text

    # Fallback: text/html simplificado
    if payload.get("mimeType") == "text/html":
        data = payload.get("body", {}).get("data", "")
        if data:
            html = base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
            import re
            return re.sub(r"<[^>]+>", "", html)

    return ""


def _list_attachments(payload: dict) -> list[dict]:
    """Retorna a lista de anexos (filename, mime_type, attachment_id)."""
    anexos = []

    def _walk(part):
        filename = part.get("filename", "")
        body     = part.get("body", {})
        if filename and body.get("attachmentId"):
            anexos.append({
                "filename":      filename,
                "mime_type":     part.get("mimeType", "application/octet-stream"),
                "attachment_id": body["attachmentId"],
            })
        for sub in part.get("parts", []):
            _walk(sub)

    _walk(payload)
    return anexos


def _get_or_create_folder(drive, nome_pasta: str) -> str:
    """Encontra ou cria uma pasta no Drive. Retorna o ID."""
    result = drive.files().list(
        q=(
            f"name = '{nome_pasta}' "
            "and mimeType = 'application/vnd.google-apps.folder' "
            "and trashed = false"
        ),
        fields="files(id)",
        pageSize=1,
    ).execute()

    files = result.get("files", [])
    if files:
        return files[0]["id"]

    folder = drive.files().create(
        body={"name": nome_pasta, "mimeType": "application/vnd.google-apps.folder"},
        fields="id",
    ).execute()
    return folder["id"]
