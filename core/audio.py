"""
Módulo de processamento de áudio.

Estratégia:
- st.audio_input() captura áudio direto do microfone no browser.
- Gemini transcreve o áudio nativamente (multimodal) para texto.
- O texto é então injetado no chat como mensagem do usuário.
"""

import hashlib
import json

import streamlit as st
import streamlit.components.v1 as components
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

    Deduplica por hash do áudio: o widget mantém a última gravação na
    memória entre reruns, então sem isso a mesma fala seria transcrita e
    enviada repetidamente em loop.
    """
    audio_value = st.audio_input(
        label="🎙️ Gravar mensagem de voz",
        key="audio_recorder",
    )

    if audio_value is None:
        return None

    audio_bytes = audio_value.getvalue()
    audio_hash  = hashlib.md5(audio_bytes).hexdigest()

    # Se este áudio já foi processado, não transcreve de novo.
    if st.session_state.get("_last_audio_hash") == audio_hash:
        return None

    with st.spinner("Transcrevendo áudio..."):
        try:
            text = transcribe_audio(audio_bytes, mime_type="audio/wav")
            st.session_state["_last_audio_hash"] = audio_hash
            return text
        except Exception as exc:
            st.warning(f"Falha na transcrição: {exc}")
            return None


def speak(text: str):
    """
    Faz o navegador falar o texto em voz alta (text-to-speech) usando a
    Web Speech API nativa — gratuita, sem chamada de API, funciona no celular.
    Cada chamada usa uma key única para forçar o navegador a reexecutar o script.
    """
    if not text:
        return

    # json.dumps escapa aspas/quebras de linha de forma segura para JS.
    safe_text = json.dumps(text)
    components.html(
        f"""
        <script>
            const synth = window.parent.speechSynthesis;
            if (synth) {{
                synth.cancel();  // interrompe fala anterior
                const u = new SpeechSynthesisUtterance({safe_text});
                u.lang = 'pt-BR';
                u.rate = 1.05;
                synth.speak(u);
            }}
        </script>
        """,
        height=0,
    )
