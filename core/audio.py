"""
Módulo de processamento de áudio.

Estratégia:
- st.audio_input() captura áudio direto do microfone no browser.
- Gemini transcreve o áudio nativamente (multimodal) para texto.
- O texto é então injetado no chat como mensagem do usuário.
"""

import streamlit as st
import google.generativeai as genai


def transcribe_audio(audio_bytes: bytes, mime_type: str = "audio/wav") -> str:
    """
    Envia bytes de áudio para o Gemini e retorna o texto transcrito.
    Lança exceção em caso de falha para que o chamador trate o erro.
    """
    genai.configure(api_key=st.secrets["gemini"]["api_key"])
    model = genai.GenerativeModel("gemini-2.5-flash")

    response = model.generate_content(
        [
            "Transcreva o áudio a seguir em português brasileiro. "
            "Retorne apenas o texto transcrito, sem comentários ou pontuação extra.",
            {"mime_type": mime_type, "data": audio_bytes},
        ]
    )
    return response.text.strip()


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
            text = transcribe_audio(audio_value.getvalue(), mime_type="audio/wav")
            return text
        except Exception as exc:
            st.warning(f"Falha na transcrição: {exc}")
            return None
