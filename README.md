# 🤖 Assistente Pessoal IA

Assistente pessoal inteligente integrado ao Google Workspace.  
100% em nuvem — sem instalação local.

**Stack:** Streamlit · LangGraph · Claude (Anthropic) · Google Workspace APIs · LlamaIndex RAG · Selenium

---

## 🗺️ Plano de Infraestrutura — Setup Completo

### Fase 1 — Google Cloud Console (≈15 min)

1. Acesse [console.cloud.google.com](https://console.cloud.google.com) e crie um projeto (ex: `assistente-pessoal`).

2. Ative as APIs necessárias em **APIs & Services → Library**:
   - Google Calendar API
   - Google Drive API
   - Google Docs API
   - Google Sheets API

3. Configure a **Tela de Consentimento OAuth**:
   - **APIs & Services → OAuth consent screen**
   - User Type: **External**
   - Preencha nome do app e e-mail de suporte
   - Escopos: adicione Calendar, Drive, Docs
   - Usuários de teste: adicione seu e-mail (obrigatório no modo "Testing")

4. Crie as **Credenciais OAuth**:
   - **APIs & Services → Credentials → Create Credentials → OAuth client ID**
   - Application type: **Web application** ← CRÍTICO (não "Desktop app")
   - Authorized redirect URIs:
     - Para desenvolvimento: `http://localhost:8501`
     - Para Streamlit Cloud: `https://SEU-APP.streamlit.app`
   - Salve o `client_id` e o `client_secret`.

---

### Fase 2 — GitHub Codespaces (IDE no navegador)

1. Acesse seu repositório em [github.com](https://github.com).
2. Clique em **Code → Codespaces → Create codespace on main**.
3. O Codespace abrirá o VS Code no navegador com Python já configurado.
4. O arquivo `.devcontainer/devcontainer.json` instalará as dependências automaticamente.
5. Para rodar o app localmente no Codespace:
   ```bash
   cp .streamlit/secrets.toml.example .streamlit/secrets.toml
   # Edite secrets.toml com suas credenciais reais
   streamlit run app.py
   ```
6. O Codespace exporá a porta 8501 e abrirá o browser automaticamente.

---

### Fase 3 — Streamlit Community Cloud (hospedagem gratuita)

1. Acesse [share.streamlit.io](https://share.streamlit.io) e conecte sua conta GitHub.
2. Clique em **New app**:
   - Repository: `seu-usuario/assistente-pessoal`
   - Branch: `main`
   - Main file path: `app.py`
3. Configure os **Secrets** antes de fazer deploy:
   - Clique em **Advanced settings → Secrets**
   - Cole o conteúdo de `.streamlit/secrets.toml.example` preenchido com valores reais
4. Anote a URL gerada (ex: `https://assistente-pessoal.streamlit.app`).
5. **Volte ao Google Cloud Console** e adicione esta URL em **Authorized redirect URIs**.
6. Clique em **Deploy**.

---

## 📁 Estrutura do Projeto

```
assistente-pessoal/
├── app.py                        # Ponto de entrada Streamlit
├── requirements.txt              # Dependências Python
├── packages.txt                  # Pacotes de sistema (Chrome/Selenium)
├── .streamlit/
│   ├── config.toml               # Tema e configurações
│   └── secrets.toml.example      # Template de secrets (nunca commitar o real)
├── .devcontainer/
│   └── devcontainer.json         # Configuração GitHub Codespaces
└── core/
    ├── auth.py                   # OAuth 2.0 Google (fluxo Web Application)
    ├── audio.py                  # Transcrição de voz via Whisper
    ├── agent.py                  # Agente LangGraph (ReAct)
    └── tools/
        ├── calendar_tool.py      # Google Calendar (CRUD + slots livres)
        ├── drive_tool.py         # Google Drive/Docs + RAG LlamaIndex
        └── scraper_tool.py       # Web scraping com Selenium headless
```

---

## 🔑 Configuração de Secrets

Copie `.streamlit/secrets.toml.example` para `.streamlit/secrets.toml` e preencha:

```toml
[google]
client_id     = "...apps.googleusercontent.com"
client_secret = "GOCSPX-..."
redirect_uri  = "https://SEU-APP.streamlit.app"

[anthropic]
api_key = "sk-ant-..."

[openai]
api_key = "sk-proj-..."   # Usado apenas para transcrição Whisper
```

No Streamlit Cloud, cole esses valores no painel **App settings → Secrets**.

---

## 🏗️ Fluxo OAuth 2.0 no Streamlit

O maior desafio técnico é que o Streamlit não tem roteamento tradicional. A solução:

```
Usuário clica "Conectar"
        │
        ▼
app.py gera auth_url + salva state em session_state
        │
        ▼
JavaScript redireciona browser → accounts.google.com/o/oauth2/auth
        │
        ▼  (usuário autoriza)
Google redireciona → https://seu-app.streamlit.app?code=X&state=Y
        │
        ▼
Streamlit reinicia o script (rerun automático)
        │
        ▼
handle_oauth_callback() detecta ?code=X no st.query_params
        │
        ▼
Troca code por access_token + refresh_token
        │
        ▼
Credenciais salvas em st.session_state → app carrega normalmente
```

**Por que "Web Application" e não "Desktop app"?**
O tipo Desktop usa um servidor HTTP local temporário que não existe no Streamlit Cloud.
"Web application" usa redirect URI fixo configurado no Console, que funciona em qualquer ambiente cloud.

---

## 🤖 Arquitetura do Agente LangGraph

```
Mensagem do usuário
        │
        ▼
   [LangGraph ReAct]
        │
   ┌────▼────┐
   │  agent  │ ◄── Claude + bind_tools()
   └────┬────┘
        │ tool_call?
   ┌────▼────┐        ┌─────────────────────────┐
   │  tools  │ ──────►│ Calendar / Drive / Scraper│
   └────┬────┘        └─────────────────────────┘
        │
        └──► [agent] ── resposta final ao usuário
```

---

## 🚀 Roadmap

- [ ] Módulo Gmail (leitura e redação de e-mails)
- [ ] Notificações proativas de agenda
- [ ] Memória persistente entre sessões (Cloud Firestore)
- [ ] Dashboard de produtividade semanal
- [ ] Integração com Google Meet (criação de links automática)
