"""
Ferramenta de busca geral na internet via DuckDuckGo.

Diferente do scraper_tool (que lê uma URL específica que você fornece),
esta ferramenta faz uma PESQUISA: descobre páginas relevantes a partir de
uma consulta em linguagem natural. Gratuita e sem necessidade de API key.
"""

from __future__ import annotations

from langchain_core.tools import tool


def make_search_tools() -> list:
    """Retorna a lista de tools de busca na web."""

    @tool
    def buscar_internet(query: str, max_results: int = 5) -> str:
        """
        Pesquisa na internet (DuckDuckGo) e retorna os principais resultados.
        Use para responder perguntas sobre fatos atuais, notícias, previsão do
        tempo, cotações, definições e qualquer informação pública recente.
        Se precisar de mais detalhes de um resultado, use 'buscar_na_web' com a URL.
        Args:
            query:       Termos de pesquisa em linguagem natural.
            max_results: Número máximo de resultados (padrão: 5).
        """
        try:
            from ddgs import DDGS          # pacote novo (renomeado)
        except ImportError:
            from duckduckgo_search import DDGS  # fallback p/ versões antigas

        try:
            resultados = []
            with DDGS() as ddgs:
                for r in ddgs.text(query, region="br-pt", max_results=max_results):
                    resultados.append(
                        f"**{r.get('title', '')}**\n"
                        f"{r.get('body', '')}\n"
                        f"🔗 {r.get('href', '')}"
                    )
            if not resultados:
                return "Nenhum resultado encontrado para a pesquisa."
            return "\n\n".join(resultados)
        except Exception as exc:
            return f"Erro ao pesquisar na internet: {exc}"

    return [buscar_internet]
