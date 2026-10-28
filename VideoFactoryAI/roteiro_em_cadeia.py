# -*- coding: utf-8 -*-
"""
Cadeia de webchats para roteiro.

  1. Um site (padrão: Gemini) CRIA o prompt de roteiro.
  2. Outro site (padrão: ChatGPT) EXECUTA o prompt e escreve o roteiro.
  3. Um crítico (padrão: Gemini) avalia o roteiro e aponta problemas.
  4. Se não passar, a crítica volta ao criador, que melhora o prompt; repete
     até aceitar ou esgotar as rodadas. Fica com o melhor roteiro obtido.

Ativação: VF_MODO_ESCRITA=cadeia (no agent.py).

Variáveis de ambiente:
  VF_CADEIA_ARQUITETO   site(s) que criam o prompt   (padrão: gemini)
  VF_CADEIA_REDATOR     site(s) que escrevem o roteiro (padrão: chatgpt)
  VF_CADEIA_CRITICO     site(s) que avaliam; vazio = sem avaliação por IA (padrão: gemini)
  VF_CADEIA_RODADAS     máximo de rodadas          (padrão: 3)
  VF_CADEIA_NOTA_MIN    nota mínima para aceitar   (padrão: 80)
  Listas aceitam vários sites separados por vírgula: o primeiro que responder vence.

Artefatos: roteiros/<slug>_cadeia/rNN_prompt.txt, rNN_roteiro.txt, rNN_avaliacao.json,
e melhor.txt com o roteiro escolhido.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Callable, List, Optional, Tuple


class CadeiaError(RuntimeError):
    pass


PROMPT_OPEN = "<<<PROMPT>>>"
PROMPT_CLOSE = "<<<FIM>>>"


def _sites(nome_env: str, padrao: str) -> List[str]:
    raw = (os.getenv(nome_env, padrao) or "").strip().lower()
    return [s.strip() for s in raw.split(",") if s.strip()]


def _default_ask() -> Callable[[str, str], str]:
    from webchat_bridge import ask_web  # type: ignore
    try:
        from webchat_writer import _limpar_ui  # type: ignore
    except Exception:
        def _limpar_ui(t):
            return t

    def ask(prompt: str, site: str) -> str:
        resultado = ask_web(prompt, order=[site], interactive=True, fallback_local=False, validar=None)
        return _limpar_ui(str(resultado.get("answer", "") or ""))

    return ask


def _pedir(ask, prompt: str, sites: List[str], log) -> Tuple[str, str]:
    """Tenta cada site da lista em ordem; devolve (site, resposta)."""
    erros = []
    for site in sites:
        try:
            resposta = ask(prompt, site)
            if resposta and resposta.strip():
                return site, resposta
            erros.append(f"{site}: resposta vazia")
        except Exception as exc:
            erros.append(f"{site}: {exc}")
            log(f"  [Cadeia] {site} falhou: {exc}")
    raise CadeiaError("nenhum site respondeu (" + " | ".join(erros) + ")")


def limpar_roteiro(texto: str) -> str:
    """Remove o bloco de metadados, marcação de markdown e espaços excedentes."""
    t = texto.replace("\r\n", "\n")
    m = re.search(r"^\s*-{3,}\s*METADADOS\s*-{3,}\s*$", t, flags=re.M | re.I)
    if m:
        t = t[:m.start()]
    t = re.sub(r"[*#`]+", "", t)
    t = re.sub(r"^\s*(roteiro|script|narração|narracao)\s*:?\s*$", "", t, flags=re.M | re.I)
    t = re.sub(r"^\s*you\s+said:.*$", "", t, flags=re.M | re.I)
    t = re.sub(r"^\s*voc\u00ea\s+disse:.*$", "", t, flags=re.M | re.I)
    t = re.sub(r"^\s*\.\.\..*$", "", t, flags=re.M | re.I)
    t = re.sub(r"^\s*show\s+more\s*$", "", t, flags=re.M | re.I)
    t = re.sub(r"^\s*mostrar\s+mais\s*$", "", t, flags=re.M | re.I)
    t = re.sub(r"^\s*chat\s+gpt\s*$", "", t, flags=re.M | re.I)
    t = re.sub(r"^\s*chatgpt\s+disse:.*$", "", t, flags=re.M | re.I)
    t = re.sub(r"^\s*a\s+ideia\s+central.*", "", t, flags=re.M | re.I)
    t = re.sub(r"^\s*escrita\s+e\s+abaixo\s+de\s+se\s+escrita.*", "", t, flags=re.M | re.I)
    t = re.sub(r"^\s*written\s*:\s*.*$", "", t, flags=re.M | re.I)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


def checar(texto: str, alvo: int) -> List[str]:
    """Checagens objetivas. Devolve a lista de problemas (vazia = passou)."""
    problemas = []
    n = len(texto.split())
    if n < alvo * 0.9:
        problemas.append(f"muito curto: {n} palavras (alvo mínimo {int(alvo * 0.9)})")
    if n > alvo * 1.15:
        problemas.append(f"muito longo: {n} palavras (alvo máximo {int(alvo * 1.15)})")
    if re.search(r"^\s*[-•]\s", texto, flags=re.M):
        problemas.append("contém lista com marcadores; a narração precisa ser texto corrido")
    if re.search(r"[\U0001F300-\U0001FAFF\u2600-\u27BF]", texto):
        problemas.append("contém emojis")
    return problemas


_STOP = {"como", "para", "uma", "com", "sem", "por", "dos", "das", "que", "nos", "nas", "sobre",
         "viver", "conviver", "morar", "esse", "essa", "isso", "mais", "muito", "onde", "quando",
         "seu", "sua", "meu", "minha", "quais", "pode", "fazer", "ter", "ser", "estar"}


def _sem_acento(s: str) -> str:
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFKD", s.lower()) if not unicodedata.combining(c))


def palavras_do_tema(topic: str) -> List[str]:
    """Palavras que definem o assunto (ignora conectivos e termos curtos)."""
    base = re.findall(r"[a-z0-9]+", _sem_acento(topic))
    return [w for w in base if len(w) >= 5 and w not in _STOP]


def cobertura_tema(texto: str, topic: str, limiar_palavra: float = 0.8) -> float:
    """Fração das palavras-chave do tema presentes no texto.
    Palavras com 6+ letras aceitam erro de digitação; as menores precisam ser exatas
    (senão 'vicer' casaria com 'vice' e o filtro ficaria frouxo)."""
    import difflib
    chaves = palavras_do_tema(topic)
    if not chaves:
        return 1.0
    vocab = set(re.findall(r"[a-z0-9]+", _sem_acento(texto)))
    achadas = 0
    for k in chaves:
        if k in vocab:
            achadas += 1
        elif len(k) >= 6 and any(difflib.SequenceMatcher(None, k, v).ratio() >= limiar_palavra
                                 for v in vocab if abs(len(v) - len(k)) <= 2):
            achadas += 1
    return achadas / len(chaves)


def _fontes_relevantes(sources: List[dict], topic: str, minimo: float = 0.4) -> List[dict]:
    """Mantém só fontes que tratam do tema. Evita que uma página de outro assunto vire base do roteiro."""
    ok = []
    for s in sources:
        corpo = f"{s.get('title', '')} {str(s.get('text', ''))[:3000]}"
        if cobertura_tema(corpo, topic) >= minimo:
            ok.append(s)
    return ok


def extrair_prompt(resposta: str) -> str:
    m = re.search(re.escape(PROMPT_OPEN) + r"(.*?)" + re.escape(PROMPT_CLOSE), resposta, flags=re.S)
    texto = m.group(1) if (m and m.group(1).strip()) else resposta
    texto = re.sub(r"<+\s*-*\s*(FIM|PROMPT)\s*-*\s*>+", "", texto, flags=re.I)
    return texto.strip()


def _parse_critica(resposta: str) -> Tuple[Optional[int], List[str]]:
    m = re.search(r"\{.*\}", resposta, flags=re.S)
    if not m:
        return None, []
    try:
        dados = json.loads(m.group(0))
    except (ValueError, TypeError):
        return None, []
    try:
        nota = int(float(dados.get("nota")))
    except (TypeError, ValueError):
        nota = None
    if nota is not None:
        nota = max(0, min(100, nota))
    problemas = [str(x) for x in (dados.get("problemas") or [])][:8]
    return nota, problemas


def _resumo_fontes(sources: List[dict], limite: int = 2500) -> str:
    partes = []
    for s in sources[:4]:
        titulo = str(s.get("title", "") or "")
        texto = str(s.get("text", "") or "")
        if texto:
            partes.append(f"- {titulo}: {texto[:800]}")
    return "\n".join(partes)[:limite]


def _texto_persona(persona) -> str:
    """A persona pode vir como texto ou como dicionário (CANAL_PERSONAS). Converte para texto."""
    if persona is None:
        return ""
    if isinstance(persona, str):
        return persona
    if isinstance(persona, dict):
        return json.dumps(persona, ensure_ascii=False)
    return str(persona)


def _meta_arquiteto(tema, duracao, alvo, persona, fontes, feedback, prompt_anterior) -> str:
    persona_txt = _texto_persona(persona)
    blocos = [
        "Você é especialista em criar prompts para roteiros de vídeos do YouTube.",
        "Sua tarefa é escrever UM prompt completo, que será colado em outro chat de IA para gerar o roteiro.",
        f"ASSUNTO OBRIGATÓRIO DO VÍDEO: {tema}",
        "Corrija apenas erros de digitação óbvios no assunto, sem trocá-lo. O prompt deve tratar SOMENTE deste assunto.",
        "Não mude o assunto, não use exemplos de outros temas e não cite obras ou filmes que não sejam do assunto.",
        "Se alguma fonte de apoio tratar de outro assunto, ignore essa fonte.",
        f"DURAÇÃO: {duracao} minutos, ou seja, cerca de {alvo} palavras de narração.",
        f"ESTILO DO CANAL: {persona_txt[:800]}",
        "O prompt que você escrever deve exigir:",
        "- gancho nos primeiros 15 segundos, com uma afirmação surpreendente e verdadeira;",
        "- uma promessa do que será descoberto até o fim;",
        "- uma virada a cada 40 a 60 segundos (fato inesperado, contradição ou pergunta respondida depois);",
        "- um mistério aberto no meio e resolvido só no final;",
        "- encerramento com um resumo forte, uma pergunta para os comentários e um pedido curto de inscrição;",
        "- somente fatos verificáveis; quando houver dúvida, usar 'segundo registros da época' ou omitir;",
        "- texto corrido para narração por voz: sem títulos, listas, asteriscos, emojis ou marcações de cena;",
        f"- entre 90% e 110% de {alvo} palavras;",
        "- ao final, a linha ---METADADOS--- seguida de 3 títulos (até 60 caracteres), uma descrição de 2 parágrafos, 10 palavras-chave e 5 fatos para conferir.",
    ]
    if fontes:
        blocos += ["FONTES DE APOIO (use como base factual):", fontes]
    if feedback:
        blocos += [
            "AVALIAÇÃO DA TENTATIVA ANTERIOR (corrija estes pontos obrigatoriamente):",
            feedback,
        ]
        if prompt_anterior:
            blocos += ["PROMPT ANTERIOR (melhore-o, não o repita):", prompt_anterior[:2500]]
    blocos += [
        f"Responda SOMENTE com o prompt, entre as marcações {PROMPT_OPEN} e {PROMPT_CLOSE}. Nada fora delas.",
    ]
    return "\n".join(blocos)


def _meta_critico(tema: str, alvo: int, roteiro: str) -> str:
    return (
        "Você é editor de roteiros de documentários para YouTube. Avalie o roteiro abaixo sobre "
        f"'{tema}' (alvo de {alvo} palavras, narrado por voz). Primeiro verifique se o roteiro trata "
        "do assunto pedido; se não tratar, dê nota 0 e use o problema 'fora do tema'. "
        "Depois avalie, com o mesmo peso: "
        "gancho forte nos primeiros 15 segundos; ritmo com viradas a cada 40 a 60 segundos; "
        "mistério aberto e resolvido; fatos plausíveis, sem invenções óbvias; linguagem falada e clara; "
        "encerramento com pergunta para os comentários.\n"
        'Responda SOMENTE com JSON neste formato: {"nota": <0 a 100>, "problemas": ["..."]}\n\n'
        "ROTEIRO:\n" + roteiro[:12000]
    )


def gerar_roteiro_em_cadeia(
    topic: str,
    duration_min: float,
    target_words: int,
    persona: str,
    sources: List[dict],
    roteiros_dir: Path,
    slug: str,
    canal: str = "documentario",
    log=print,
    min_words: int = 0,
    ask: Optional[Callable[[str, str], str]] = None,
) -> str:
    """Mesma assinatura de escrever_via_webchat, para o agent.py poder usar as duas."""
    ask = ask or _default_ask()
    sites_arq = _sites("VF_CADEIA_ARQUITETO", "gemini")
    sites_red = _sites("VF_CADEIA_REDATOR", "chatgpt")
    sites_cri = _sites("VF_CADEIA_CRITICO", "gemini")
    rodadas = max(1, int(os.getenv("VF_CADEIA_RODADAS", "3") or 3))
    nota_min = int(os.getenv("VF_CADEIA_NOTA_MIN", "80") or 80)

    pasta = Path(roteiros_dir) / f"{slug}_cadeia"
    pasta.mkdir(parents=True, exist_ok=True)

    alvo = max(int(min_words or 0), int(target_words * 0.9))
    fontes_ok = _fontes_relevantes(sources, topic)
    log(f"  [Cadeia] Fontes relevantes para o tema: {len(fontes_ok)} de {len(sources)}.")
    fontes = _resumo_fontes(fontes_ok)
    log(f"  [Cadeia] {', '.join(sites_arq)} cria o prompt -> {', '.join(sites_red)} escreve o roteiro"
        + (f" -> {', '.join(sites_cri)} avalia" if sites_cri else " (sem avaliação por IA)")
        + f". Até {rodadas} rodadas, nota mínima {nota_min}.")

    melhor: Optional[Tuple[int, str]] = None
    feedback = ""
    prompt_anterior = ""
    erros_rodadas = []

    for r in range(1, rodadas + 1):
        registro = {"rodada": r}
        try:
            log(f"  [Cadeia] Rodada {r}/{rodadas}: pedindo o prompt...")
            site_arq, resp_arq = _pedir(
                ask,
                _meta_arquiteto(topic, duration_min, alvo, persona, fontes, feedback, prompt_anterior),
                sites_arq, log,
            )
            prompt = extrair_prompt(resp_arq)
            (pasta / f"r{r:02d}_prompt.txt").write_text(prompt, encoding="utf-8")
            registro["criador"] = site_arq

            if cobertura_tema(prompt, topic) < 0.4:
                msg = f"o prompt não trata do assunto '{topic}'"
                registro.update({"problemas_objetivos": [msg], "nota": 0, "criticas": []})
                (pasta / f"r{r:02d}_avaliacao.json").write_text(
                    json.dumps(registro, ensure_ascii=False, indent=2), encoding="utf-8")
                log(f"  [Cadeia] Rodada {r}: {msg}. Pedindo novo prompt sem gastar o redator.")
                feedback = f"- {msg}. Reescreva o prompt inteiro sobre este assunto."
                prompt_anterior = prompt
                continue

            log(f"  [Cadeia] Rodada {r}/{rodadas}: pedindo o roteiro...")
            site_red, resp_red = _pedir(ask, prompt, sites_red, log)
            texto = limpar_roteiro(resp_red)
            (pasta / f"r{r:02d}_roteiro.txt").write_text(texto, encoding="utf-8")
            registro["redator"] = site_red
            registro["palavras"] = len(texto.split())

            problemas = checar(texto, alvo)
            if cobertura_tema(texto, topic) < 0.4:
                problemas.append(f"fora do tema: o roteiro não trata de '{topic}'")
            nota = None
            criticas: List[str] = []
            if sites_cri and not problemas:
                try:
                    _, resp_cri = _pedir(ask, _meta_critico(topic, alvo, texto), sites_cri, log)
                    nota, criticas = _parse_critica(resp_cri)
                except CadeiaError as exc:
                    log(f"  [Cadeia] crítico indisponível nesta rodada: {exc}")
            if problemas:
                score = 0
            elif nota is not None:
                score = nota
            else:
                score = 100

            registro.update({"problemas_objetivos": problemas, "nota": score, "criticas": criticas})
            (pasta / f"r{r:02d}_avaliacao.json").write_text(
                json.dumps(registro, ensure_ascii=False, indent=2), encoding="utf-8")
            log(f"  [Cadeia] Rodada {r}: {registro['palavras']} palavras | nota {score} | "
                f"pendências {len(problemas) + len(criticas)}")

            # Desempate: entre notas iguais, fica o roteiro mais próximo do tamanho alvo.
            chave = (score, -abs(registro["palavras"] - alvo))
            if melhor is None or chave > melhor[0]:
                melhor = (chave, texto)
            if score >= nota_min and not problemas:
                log(f"  [Cadeia] ✓ Roteiro aceito na rodada {r}.")
                break

            pendencias = problemas + criticas
            feedback = "\n".join(f"- {p}" for p in pendencias) or "- aumentar o gancho e o ritmo"
            prompt_anterior = prompt
        except CadeiaError as exc:
            erros_rodadas.append(f"rodada {r}: {exc}")
            registro["erro"] = str(exc)
            (pasta / f"r{r:02d}_avaliacao.json").write_text(
                json.dumps(registro, ensure_ascii=False, indent=2), encoding="utf-8")
            log(f"  [Cadeia] Rodada {r} falhou: {exc}")

    if melhor is None:
        raise CadeiaError("nenhuma rodada produziu roteiro. " + " | ".join(erros_rodadas))

    (pasta / "melhor.txt").write_text(melhor[1], encoding="utf-8")
    nota_final = melhor[0][0]
    if nota_final < nota_min:
        log(f"  [Cadeia] Melhor roteiro ficou com nota {nota_final} (mínimo {nota_min}). "
            "Revise pasta " + str(pasta) + " ou aumente VF_CADEIA_RODADAS.")
    return melhor[1]
