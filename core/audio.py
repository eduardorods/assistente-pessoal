"""
Módulo de processamento de áudio.

Estratégia:
- st.audio_input() captura áudio direto do microfone no browser.
- OpenAI Whisper API transcreve o áudio para texto.
- O texto é então injetado no chat como mensagem do usuário.
"""

import io
import streamlit as st
from openai import OpenAI


@st.cache_resource
def _whisper_client() -> OpenAI:
    return OpenAI(api_key=st.secrets["openai"]["api_key"])


def transcribe_audio(audio_bytes: bytes, filename: str = "audio.wav") -> str:
    """
    Envia bytes de áudio para a API Whisper e retorna o texto transcrito.
    Lança exceção em caso de falha para que o chamador trate o erro.
    """
    client = _whisper_client()
    audio_file = io.BytesIO(audio_bytes)
    audio_file.name = filename

    transcript = client.audio.transcriptions.create(
        model="whisper-1",
        file=audio_file,
        language="pt",          # Força português; remova para auto-detect
        response_format="text",
    )
    return transcript.strip()


def render_audio_input() -> str | None:
    """
    Renderiza o widget de input de áudio e retorna o texto transcrito,
    ou None se nenhum áudio foi gravado/transcrito ainda.
    """
    audio_value = st.audio_input(
        label="🎙️ Gravar mensagem de voz",
        key="audio_recorder",
    )

    if audio_value is None:
        return None

    with st.spinner("Transcrevendo áudio..."):
        try:
            text = transcribe_audio(audio_value.getvalue(), filename="gravacao.wav")
            return text
        except Exception as exc:
            st.warning(f"Falha na transcrição: {exc}")
            return None
