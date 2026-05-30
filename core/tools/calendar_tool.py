"""
Ferramentas LangChain para Google Calendar.
Cada função é um @tool injetado no agente LangGraph.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta

import pytz
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from langchain_core.tools import tool


def _service(creds: Credentials):
    return build("calendar", "v3", credentials=creds)


# ── Ferramentas ───────────────────────────────────────────────────────────────

def make_calendar_tools(creds: Credentials) -> list:
    """Retorna a lista de tools instanciadas com as credenciais do usuário."""

    @tool
    def listar_eventos(dias: int = 7) -> str:
        """
        Lista os próximos eventos do Google Calendar.
        Args:
            dias: Número de dias a consultar a partir de hoje (padrão: 7).
        """
        service = _service(creds)
        tz    = pytz.timezone("America/Sao_Paulo")
        now   = datetime.now(tz)
        end   = now + timedelta(days=dias)

        result = service.events().list(
            calendarId="primary",
            timeMin=now.isoformat(),
            timeMax=end.isoformat(),
            maxResults=20,
            singleEvents=True,
            orderBy="startTime",
        ).execute()

        events = result.get("items", [])
        if not events:
            return "Nenhum evento encontrado nos próximos dias."

        linhas = []
        for ev in events:
            start = ev["start"].get("dateTime", ev["start"].get("date", ""))
            linhas.append(f"• {start[:16].replace('T',' ')} — {ev.get('summary','(sem título)')}")
        return "\n".join(linhas)

    @tool
    def criar_evento(
        titulo: str,
        data_inicio: str,
        data_fim: str,
        descricao: str = "",
        convidados: list[str] | None = None,
    ) -> str:
        """
        Cria um novo evento no Google Calendar.
        Args:
            titulo: Título do evento.
            data_inicio: ISO 8601, ex: '2025-07-10T14:00:00-03:00'.
            data_fim:    ISO 8601, ex: '2025-07-10T15:00:00-03:00'.
            descricao:   Texto opcional de descrição.
            convidados:  Lista de e-mails dos convidados (opcional).
        """
        service = _service(creds)
        body: dict = {
            "summary":     titulo,
            "description": descricao,
            "start": {"dateTime": data_inicio, "timeZone": "America/Sao_Paulo"},
            "end":   {"dateTime": data_fim,    "timeZone": "America/Sao_Paulo"},
        }
        if convidados:
            body["attendees"] = [{"email": e} for e in convidados]

        ev = service.events().insert(calendarId="primary", body=body).execute()
        return f"Evento criado: {ev.get('htmlLink')}"

    @tool
    def reagendar_evento(event_id: str, nova_data_inicio: str, nova_data_fim: str) -> str:
        """
        Reagenda um evento existente.
        Args:
            event_id:         ID do evento (obtido em listar_eventos ou buscar_evento).
            nova_data_inicio: Nova data/hora de início em ISO 8601.
            nova_data_fim:    Nova data/hora de fim em ISO 8601.
        """
        service = _service(creds)
        ev = service.events().get(calendarId="primary", eventId=event_id).execute()
        ev["start"] = {"dateTime": nova_data_inicio, "timeZone": "America/Sao_Paulo"}
        ev["end"]   = {"dateTime": nova_data_fim,    "timeZone": "America/Sao_Paulo"}
        updated = service.events().update(calendarId="primary", eventId=event_id, body=ev).execute()
        return f"Evento reagendado: {updated.get('htmlLink')}"

    @tool
    def cancelar_evento(event_id: str) -> str:
        """
        Cancela (exclui) um evento do Calendar.
        Args:
            event_id: ID do evento a cancelar.
        """
        service = _service(creds)
        service.events().delete(calendarId="primary", eventId=event_id).execute()
        return f"Evento {event_id} cancelado com sucesso."

    @tool
    def buscar_slots_livres(duracao_minutos: int = 60, dias: int = 5) -> str:
        """
        Encontra horários livres nos próximos dias para reuniões.
        Args:
            duracao_minutos: Duração desejada em minutos.
            dias: Janela de busca em dias.
        """
        service = _service(creds)
        tz  = pytz.timezone("America/Sao_Paulo")
        now = datetime.now(tz)
        end = now + timedelta(days=dias)

        body = {
            "timeMin":  now.isoformat(),
            "timeMax":  end.isoformat(),
            "timeZone": "America/Sao_Paulo",
            "items":    [{"id": "primary"}],
        }
        fb = service.freebusy().query(body=body).execute()
        busy_periods = fb["calendars"]["primary"]["busy"]

        # Horário comercial: 09:00 – 18:00
        slots = []
        cursor = now.replace(hour=9, minute=0, second=0, microsecond=0)
        if cursor < now:
            cursor += timedelta(days=1)

        while cursor < end and len(slots) < 5:
            slot_end = cursor + timedelta(minutes=duracao_minutos)
            hora = cursor.hour
            if 9 <= hora and slot_end.hour <= 18:
                conflito = any(
                    datetime.fromisoformat(b["start"]) < slot_end and
                    datetime.fromisoformat(b["end"])   > cursor
                    for b in busy_periods
                )
                if not conflito:
                    slots.append(f"• {cursor.strftime('%d/%m %H:%M')} – {slot_end.strftime('%H:%M')}")
            cursor += timedelta(minutes=30)
            if cursor.hour >= 18:
                cursor = (cursor + timedelta(days=1)).replace(hour=9, minute=0, second=0)

        return "\n".join(slots) if slots else "Nenhum slot livre encontrado."

    return [listar_eventos, criar_evento, reagendar_evento, cancelar_evento, buscar_slots_livres]
