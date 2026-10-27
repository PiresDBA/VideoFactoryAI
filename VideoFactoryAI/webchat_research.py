"""Pure helpers for turning WebChat research into a visual generation prompt."""

import re


def build_web_research_prompt(scene_text: str, query: str, topic: str = "") -> str:
    return (
        "Pesquise na web informações confiáveis sobre a cena abaixo e produza apenas "
        "uma descrição visual objetiva para orientar uma imagem documental. "
        "Não gere imagem ainda. Informe personagens/objetos, época, local, contexto "
        "visual e elementos obrigatórios; não invente detalhes sem evidência. "
        "Mantenha a resposta concisa.\n"
        f"Tema: {topic or 'não informado'}\n"
        f"Consulta: {query or 'não informada'}\n"
        f"Texto da cena: {scene_text or 'não informado'}"
    )


def extract_visual_description(response: str) -> str | None:
    cleaned = re.sub(r"```(?:\w+)?", "", str(response or "")).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    if len(cleaned) < 20:
        return None
    return cleaned[:1800]


def build_image_prompt(original_prompt: str, research_description: str) -> str:
    original = str(original_prompt or "").strip()
    research = str(research_description or "").strip()
    if not research:
        return original
    return (
        f"{original}\n\nDESCRIÇÃO VISUAL BASEADA EM PESQUISA WEB: {research}\n"
        "Use os fatos pesquisados como referência e mantenha os elementos obrigatórios "
        "do texto da cena."
    )


def research_visual_description(
    scene_text: str,
    query: str,
    topic: str,
    send_prompt,
    wait_for_response,
    log=print,
) -> str | None:
    """Run one WebChat research turn and return its concise visual summary."""
    try:
        send_prompt(build_web_research_prompt(scene_text, query, topic))
        response = wait_for_response()
    except Exception as exc:
        log(f"[WebResearch] Pesquisa indisponível; usando prompt original: {exc}")
        return None
    description = extract_visual_description(response)
    if not description:
        log("[WebResearch] Nenhum resumo visual foi retornado; usando prompt original.")
    return description
