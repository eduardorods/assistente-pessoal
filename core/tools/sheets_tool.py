"""
Ferramentas LangChain para Google Sheets.

Operações suportadas:
- Criar planilha com cabeçalhos
- Ler dados de uma planilha
- Adicionar linhas
- Atualizar células específicas
"""

from __future__ import annotations

import streamlit as st
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from langchain_core.tools import tool


def _sheets(creds: Credentials):
    return build("sheets", "v4", credentials=creds)


def _drive(creds: Credentials):
    return build("drive", "v3", credentials=creds)


def make_sheets_tools(creds: Credentials) -> list:
    """Retorna a lista de tools para Google Sheets."""

    @tool
    def criar_planilha(titulo: str, cabecalhos: list[str], primeira_linha: list[str] | None = None) -> str:
        """
        Cria uma nova planilha no Google Sheets com cabeçalhos e opcionalmente uma primeira linha de dados.
        Args:
            titulo:        Nome da planilha.
            cabecalhos:    Lista com os nomes das colunas, ex: ["Data", "Quantidade"].
            primeira_linha: Valores da primeira linha de dados (opcional), ex: ["2025-05-30", "5"].
        """
        service = _sheets(creds)

        planilha = service.spreadsheets().create(body={
            "properties": {"title": titulo},
            "sheets": [{"properties": {"title": "Página1"}}],
        }).execute()

        sheet_id  = planilha["spreadsheetId"]
        link      = f"https://docs.google.com/spreadsheets/d/{sheet_id}/edit"

        # Monta os dados a inserir: cabeçalhos + primeira linha (se fornecida)
        valores = [cabecalhos]
        if primeira_linha:
            valores.append(primeira_linha)

        service.spreadsheets().values().update(
            spreadsheetId=sheet_id,
            range="Página1!A1",
            valueInputOption="USER_ENTERED",
            body={"values": valores},
        ).execute()

        linhas_msg = " e primeira linha de dados inserida" if primeira_linha else ""
        return f"Planilha **{titulo}** criada{linhas_msg}: [{titulo}]({link})\nID: `{sheet_id}`"

    @tool
    def adicionar_linha_planilha(sheet_id: str, valores: list[str], aba: str = "Página1") -> str:
        """
        Adiciona uma nova linha no final de uma planilha existente.
        Args:
            sheet_id: ID da planilha (obtido em criar_planilha ou buscar_documentos).
            valores:  Lista de valores para a linha, ex: ["2025-05-31", "10"].
            aba:      Nome da aba/sheet (padrão: "Página1").
        """
        service = _sheets(creds)

        service.spreadsheets().values().append(
            spreadsheetId=sheet_id,
            range=f"{aba}!A1",
            valueInputOption="USER_ENTERED",
            insertDataOption="INSERT_ROWS",
            body={"values": [valores]},
        ).execute()

        link = f"https://docs.google.com/spreadsheets/d/{sheet_id}/edit"
        return f"Linha adicionada: {valores}\n🔗 [Abrir planilha]({link})"

    @tool
    def ler_planilha(sheet_id: str, intervalo: str = "A1:Z100", aba: str = "Página1") -> str:
        """
        Lê os dados de uma planilha e retorna como texto formatado.
        Args:
            sheet_id:  ID da planilha.
            intervalo: Intervalo de células, ex: "A1:D20" (padrão: "A1:Z100").
            aba:       Nome da aba (padrão: "Página1").
        """
        service = _sheets(creds)

        result = service.spreadsheets().values().get(
            spreadsheetId=sheet_id,
            range=f"{aba}!{intervalo}",
        ).execute()

        rows = result.get("values", [])
        if not rows:
            return "A planilha está vazia."

        # Formata como tabela simples
        linhas = []
        for i, row in enumerate(rows):
            prefixo = "**[cabeçalho]**" if i == 0 else f"Linha {i}"
            linhas.append(f"{prefixo}: {' | '.join(str(c) for c in row)}")

        return "\n".join(linhas)

    @tool
    def atualizar_celula_planilha(sheet_id: str, celula: str, valor: str, aba: str = "Página1") -> str:
        """
        Atualiza o valor de uma célula específica de uma planilha.
        Args:
            sheet_id: ID da planilha.
            celula:   Referência da célula, ex: "B3", "C5".
            valor:    Novo valor da célula.
            aba:      Nome da aba (padrão: "Página1").
        """
        service = _sheets(creds)

        service.spreadsheets().values().update(
            spreadsheetId=sheet_id,
            range=f"{aba}!{celula}",
            valueInputOption="USER_ENTERED",
            body={"values": [[valor]]},
        ).execute()

        link = f"https://docs.google.com/spreadsheets/d/{sheet_id}/edit"
        return f"Célula **{celula}** atualizada para `{valor}`. 🔗 [Abrir planilha]({link})"

    return [criar_planilha, adicionar_linha_planilha, ler_planilha, atualizar_celula_planilha]
