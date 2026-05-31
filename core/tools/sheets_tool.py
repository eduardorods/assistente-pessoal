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
    def ler_planilha(sheet_id: str, intervalo: str = "A1:BZ200", aba: str = "Página1") -> str:
        """
        Lê os dados de uma planilha e retorna como texto formatado.
        Indica colunas pela letra (A, B, ... AJ) para facilitar localizar uma célula específica.
        Args:
            sheet_id:  ID da planilha.
            intervalo: Intervalo de células, ex: "A1:AJ40" (padrão: "A1:BZ200", cobre até a coluna BZ).
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

        def col_letter(idx: int) -> str:
            """0 → A, 25 → Z, 26 → AA, 35 → AJ."""
            s = ""
            idx += 1
            while idx:
                idx, rem = divmod(idx - 1, 26)
                s = chr(65 + rem) + s
            return s

        # Formata como tabela com referência de coluna (col:valor) para localização precisa.
        linhas = []
        for i, row in enumerate(rows):
            prefixo = "[cabeçalho]" if i == 0 else f"Linha {i + 1}"
            celulas = " | ".join(f"{col_letter(j)}:{c}" for j, c in enumerate(row) if str(c).strip())
            linhas.append(f"{prefixo}: {celulas}")

        return "\n".join(linhas)

    @tool
    def ler_celula_planilha(sheet_id: str, celula: str, aba: str = "Página1") -> str:
        """
        Lê o valor de uma única célula específica (rápido e sem truncamento).
        Use quando souber exatamente a célula desejada, ex: "AJ31".
        Args:
            sheet_id: ID da planilha.
            celula:   Referência da célula, ex: "AJ31".
            aba:      Nome da aba (padrão: "Página1").
        """
        service = _sheets(creds)
        result = service.spreadsheets().values().get(
            spreadsheetId=sheet_id,
            range=f"{aba}!{celula}",
        ).execute()
        rows = result.get("values", [])
        valor = rows[0][0] if rows and rows[0] else "(vazia)"
        return f"{aba}!{celula} = {valor}"

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

    @tool
    def duplicar_aba(sheet_id: str, aba_origem: str, novo_nome: str) -> str:
        """
        Cria uma cópia de uma aba existente na mesma planilha com um novo nome.
        Use para replicar abas mensais, modelos ou templates.
        Args:
            sheet_id:    ID da planilha (obtido em buscar_documentos).
            aba_origem:  Nome da aba a ser copiada, ex: "mai26".
            novo_nome:   Nome da nova aba, ex: "jun26".
        """
        service = _sheets(creds)

        info = service.spreadsheets().get(spreadsheetId=sheet_id).execute()
        source_sheet_id = None
        for sheet in info["sheets"]:
            if sheet["properties"]["title"] == aba_origem:
                source_sheet_id = sheet["properties"]["sheetId"]
                break

        if source_sheet_id is None:
            abas_existentes = [s["properties"]["title"] for s in info["sheets"]]
            return f"Aba '{aba_origem}' não encontrada. Abas disponíveis: {abas_existentes}"

        service.spreadsheets().batchUpdate(
            spreadsheetId=sheet_id,
            body={"requests": [{"duplicateSheet": {
                "sourceSheetId": source_sheet_id,
                "newSheetName":  novo_nome,
            }}]},
        ).execute()

        link = f"https://docs.google.com/spreadsheets/d/{sheet_id}/edit"
        return f"Aba '{aba_origem}' copiada para '{novo_nome}' com sucesso. 🔗 [Abrir planilha]({link})"

    def _find_replace(sheet_id: str, tab_numeric_id: int, find: str, replace: str) -> int:
        """Usa a API findReplace do Sheets (preserva fórmulas). Retorna nº de substituições."""
        result = service_ref[0].spreadsheets().batchUpdate(
            spreadsheetId=sheet_id,
            body={"requests": [{"findReplace": {
                "find":             find,
                "replacement":      replace,
                "includeFormulas":  True,
                "sheetId":          tab_numeric_id,
            }}]},
        ).execute()
        return result["replies"][0].get("findReplace", {}).get("occurrencesChanged", 0)

    def _get_tab_ids(sheet_id: str) -> dict:
        info = service_ref[0].spreadsheets().get(spreadsheetId=sheet_id).execute()
        return {s["properties"]["title"]: s["properties"]["sheetId"] for s in info["sheets"]}

    # service_ref é uma lista para que as closures acima possam ler o service
    # sem depender de variáveis de escopo externo que mudam a cada chamada de tool.
    service_ref = [None]

    @tool
    def substituir_texto_aba(sheet_id: str, aba: str, texto_original: str, texto_novo: str) -> str:
        """
        Substitui todas as ocorrências de um texto por outro em toda uma aba,
        preservando fórmulas (usa findReplace nativo do Sheets).
        Útil para atualizar datas (ex: "2026-05" → "2026-06"), nomes ou qualquer padrão em massa.
        Args:
            sheet_id:       ID da planilha.
            aba:            Nome da aba onde fazer as substituições.
            texto_original: Texto a ser substituído, ex: "2026-05".
            texto_novo:     Novo texto, ex: "2026-06".
        """
        service_ref[0] = _sheets(creds)
        tab_ids = _get_tab_ids(sheet_id)
        if aba not in tab_ids:
            return f"Aba '{aba}' não encontrada. Abas disponíveis: {list(tab_ids)}"

        count = _find_replace(sheet_id, tab_ids[aba], texto_original, texto_novo)
        link  = f"https://docs.google.com/spreadsheets/d/{sheet_id}/edit"

        if count == 0:
            return f"Nenhuma ocorrência de '{texto_original}' encontrada na aba '{aba}'."
        return (f"{count} ocorrência(s) substituída(s): '{texto_original}' → '{texto_novo}' "
                f"na aba '{aba}'. 🔗 [Abrir planilha]({link})")

    @tool
    def abrir_mes(sheet_id: str, aba_origem: str, aba_destino: str) -> str:
        """
        Abre um novo mês no fluxo de caixa duplicando o par de abas do mês anterior
        (dados + fxcx) e atualizando todas as referências automaticamente.

        Executa 4 passos:
        1. Duplica aba_origem → aba_destino           (ex: mai26 → jun26)
        2. Duplica fxcx_<aba_origem> → fxcx_<aba_destino>  (ex: fxcx_mai26 → fxcx_jun26)
        3. Substitui prefixo de data em aba_destino   (ex: 2026-05 → 2026-06)
        4. Substitui referências a aba_origem em fxcx_aba_destino  (garante fórmulas corretas)

        Args:
            sheet_id:    ID da planilha de fluxo de caixa.
            aba_origem:  Nome da aba de dados do mês anterior, ex: "mai26".
            aba_destino: Nome da nova aba de dados,            ex: "jun26".
        """
        _MESES = {"jan": "01", "fev": "02", "mar": "03", "abr": "04",
                  "mai": "05", "jun": "06", "jul": "07", "ago": "08",
                  "set": "09", "out": "10", "nov": "11", "dez": "12"}

        def tab_to_date_prefix(name: str) -> str:
            mes_num = _MESES.get(name[:3].lower(), "")
            ano     = f"20{name[3:]}"
            return f"{ano}-{mes_num}" if mes_num else ""

        service_ref[0] = _sheets(creds)
        fxcx_origem  = f"fxcx_{aba_origem}"
        fxcx_destino = f"fxcx_{aba_destino}"
        data_origem  = tab_to_date_prefix(aba_origem)
        data_destino = tab_to_date_prefix(aba_destino)

        def duplicate(source_title: str, new_name: str):
            ids = _get_tab_ids(sheet_id)
            if source_title not in ids:
                raise ValueError(f"Aba '{source_title}' não encontrada. Disponíveis: {list(ids)}")
            service_ref[0].spreadsheets().batchUpdate(
                spreadsheetId=sheet_id,
                body={"requests": [{"duplicateSheet": {
                    "sourceSheetId": ids[source_title],
                    "newSheetName":  new_name,
                }}]},
            ).execute()

        duplicate(aba_origem, aba_destino)
        duplicate(fxcx_origem, fxcx_destino)

        tab_ids = _get_tab_ids(sheet_id)
        msgs = []

        if data_origem and data_destino:
            n = _find_replace(sheet_id, tab_ids[aba_destino], data_origem, data_destino)
            msgs.append(f"- Datas: `{data_origem}` → `{data_destino}` em `{aba_destino}` ({n} célula(s))")

        n2 = _find_replace(sheet_id, tab_ids[fxcx_destino], aba_origem, aba_destino)
        msgs.append(f"- Referências: `{aba_origem}` → `{aba_destino}` em `{fxcx_destino}` ({n2} ocorrência(s))")

        link = f"https://docs.google.com/spreadsheets/d/{sheet_id}/edit"
        return (f"Mês **{aba_destino}** aberto com sucesso!\n"
                f"- Abas criadas: `{aba_destino}` e `{fxcx_destino}`\n"
                + "\n".join(msgs)
                + f"\n🔗 [Abrir planilha]({link})")

    return [criar_planilha, adicionar_linha_planilha, ler_planilha, ler_celula_planilha,
            atualizar_celula_planilha, duplicar_aba, substituir_texto_aba, abrir_mes]
