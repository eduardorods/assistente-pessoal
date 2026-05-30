"""
Ferramenta de web scraping com Selenium headless.

Configurada especificamente para o ambiente Debian do Streamlit Community Cloud,
onde o Chromium é instalado via packages.txt.
"""

from __future__ import annotations

import re
from langchain_core.tools import tool

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from bs4 import BeautifulSoup


def _make_driver() -> webdriver.Chrome:
    """
    Cria uma instância headless do Chrome compatível com Streamlit Cloud.
    O Chromium e o chromedriver são instalados via packages.txt.
    """
    opts = Options()
    opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--disable-extensions")
    opts.add_argument("--window-size=1920,1080")
    opts.add_argument(
        "--user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
    # No Streamlit Cloud o chromedriver fica em /usr/bin/chromedriver
    service = Service(executable_path="/usr/bin/chromedriver")
    return webdriver.Chrome(service=service, options=opts)


def _clean_text(html: str) -> str:
    """Remove tags HTML e normaliza espaços em branco."""
    soup  = BeautifulSoup(html, "lxml")
    # Remove scripts, styles e navigation
    for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
        tag.decompose()
    text = soup.get_text(separator="\n")
    # Colapsa linhas em branco múltiplas
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def make_scraper_tools() -> list:
    """Retorna a lista de tools de scraping."""

    @tool
    def buscar_na_web(url: str, seletor_css: str = "body", timeout: int = 15) -> str:
        """
        Acessa uma URL e extrai o conteúdo textual da página.
        Útil para monitorar relatórios de mercado, notícias e dados públicos.
        Args:
            url:          URL completa da página a ser acessada.
            seletor_css:  Seletor CSS do elemento a extrair (padrão: 'body').
            timeout:      Segundos de espera pelo elemento (padrão: 15).
        """
        driver = _make_driver()
        try:
            driver.get(url)
            WebDriverWait(driver, timeout).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, seletor_css))
            )
            element = driver.find_element(By.CSS_SELECTOR, seletor_css)
            html    = element.get_attribute("innerHTML") or ""
            text    = _clean_text(html)
            return text[:6000] if text else "Conteúdo não encontrado."
        except TimeoutException:
            return f"Timeout: elemento '{seletor_css}' não encontrado em {url}."
        except Exception as exc:
            return f"Erro ao acessar {url}: {exc}"
        finally:
            driver.quit()

    @tool
    def monitorar_pagina(url: str, texto_esperado: str) -> str:
        """
        Verifica se determinado texto aparece em uma página web.
        Útil para monitorar mudanças em relatórios ou dashboards.
        Args:
            url:            URL da página.
            texto_esperado: Texto a procurar (case-insensitive).
        """
        conteudo = buscar_na_web.invoke({"url": url})
        encontrado = texto_esperado.lower() in conteudo.lower()
        status = "✅ Encontrado" if encontrado else "❌ Não encontrado"
        return f"{status}: '{texto_esperado}' em {url}"

    return [buscar_na_web, monitorar_pagina]
