# -*- coding: utf-8 -*-
"""
Escrita de roteiro via web chat, usando o webchat_bridge.py (ask_web).

Fluxo:
1. Se existir roteiros/<slug>_resposta.txt (resposta que VOCE colou manualmente), usa esse texto.
2. Senao, monta o prompt com as fontes, salva em roteiros/<slug>_prompt.txt e chama ask_web()
   tentando os sites na ordem de VF_WEBCHAT_SITES.
3. A resposta bruta fica em roteiros/<slug>_webchat_bruto.txt para auditoria.

Nunca cai para o Ollama local: ask_web e chamado com fallback_local=False.

Configuracao (variaveis de ambiente):
  VF_WEBCHAT_DIR      pasta onde esta webchat_bridge.py (se nao estiver no PYTHONPATH)
  VF_WEBCHAT_SITES    ordem dos sites, ex.: gemini,chatgpt,copilot,deepseek,perplexity
  VF_WEBCHAT_VALIDAR  nenhum (padrao) | terminal | resposta | envio | ambos
                      'terminal' pede aprovacao A/E/R/C no proprio terminal (bridge)

Obs.: o bridge sempre abre o navegador visivel; o parametro headless nao tem efeito.
"""
import os
import re
import sys
import json
from pathlib import Path
from typing import Dict, List, Optional

BUDGET_FONTES = 15000        # caracteres de fontes no prompt (o bridge corta acima de 20000)
MAX_CHARS_POR_FONTE = 4000

# Configuração de geração sequencial para roteiros longos
SEQUENTIAL_THRESHOLD_WORDS = 600    # acima disso, usa geração em partes
MAX_WORDS_PER_PART = 400            # palavras alvo por parte (meta realista para LLM web)
MAX_PARTS = 18                      # até ~7200 palavras (~53 min de narração)
UI_LIXO = re.compile(
    r"^\s*(copiar|copy|regenerar|regenerate|curtir|descurtir|good response|bad response|"
    r"compartilhar|share|editar|edit|mais opções|more options|ver mais|show more|"
    r"fontes|sources|pensando|thinking)\s*$",
    re.I,
)


class WebChatError(RuntimeError):
    pass


def montar_prompt(
    topic: str,
    duration_min: float,
    target_words: int,
    persona: str,
    sources: List[Dict],
    canal: str = "documentario",
    min_words: int = 0
) -> str:
    """Monta prompt otimizado para webchat com anti-alucinação rigoroso."""
    lo, hi = int(target_words * 0.95), int(target_words * 1.05)
    min_req = min_words if min_words > 0 else int(target_words * 0.90)
    por_fonte = max(1000, min(MAX_CHARS_POR_FONTE, BUDGET_FONTES // max(1, len(sources))))

    blocos = []
    for i, s in enumerate(sources, 1):
        title = s.get('title', 'Sem título')
        url = s.get('url', '')
        text = s.get('text', '')[:por_fonte]
        blocos.append(f"[FONTE {i}] {title}\nURL: {url}\n{text}")
    fontes_txt = "\n\n---\n\n".join(blocos)

    # Load style instruction from JSON config (allows adding channels without code changes)
    from canal_personas_loader import get_style_instruction

    estilo_canal = get_style_instruction(canal)


    return f"""{persona}

{estilo_canal}

TAREFA
Escreva o roteiro narrado COMPLETO de um vídeo documentário para YouTube sobre: "{topic}".
Duração alvo: {duration_min:.1f} minutos.
Extensão OBRIGATÓRIA: NO MÍNIMO {min_req} palavras e no máximo {hi} palavras (alvo ideal: {lo}-{hi} palavras).
Se você terminar antes de {min_req} palavras, o roteiro será REJEITADO. Desenvolva cada ato com profundidade real.

REGRAS ANTI-ALUCINAÇÃO (VIOLAÇÃO = ROTEIRO REJEITADO)
1. Você PODE e DEVE usar conhecimento consolidado e amplamente aceito (consenso histórico, científico e enciclopédico) para construir contexto, análise, narrativa e explicações. O objetivo é um documentário rico, não um resumo das fontes.
2. NUNCA invente dados verificáveis: datas exatas, nomes próprios, números, estatísticas, citações, tratados, leis ou resultados de estudos dos quais você não tenha certeza.
3. Se um dado específico não estiver nas fontes nem for de conhecimento consolidado, escreva de forma honesta e genérica ("os registros divergem sobre a data exata", "não há consenso sobre o número de vítimas") em vez de inventar.
4. Se o tema for ficção (conto, lenda, fábula, mito), DECLARE EXPLICITAMENTE no roteiro: "Esta é uma narrativa ficcional / lenda / conto tradicional".
5. IGNORE trechos das fontes que não tenham relação direta com o tema.
6. NÃO cite fontes no texto falado. NÃO use colchetes, números de nota, referências, "segundo a Wikipedia", "conforme a fonte".
7. NÃO use frases genéricas de enchimento ("é importante notar que", "vale ressaltar que", "no entanto", "além disso") — cada frase deve agregar informação nova.
8. NÃO repita a mesma informação com palavras diferentes. Cada parágrafo = fato novo.

ESTRUTURA OBRIGATÓRIA (5 ATOS)
Ato 1 - GANCHO (primeiros ~15% das palavras): Cena vívida, pergunta provocativa ou fato surpreendente que prenda o espectador.
Ato 2 - CONTEXTO E ORIGENS (~25%): Fatos históricos/científicos/culturais fundamentais — datas, lugares, agentes, motivações.
Ato 3 - DESENVOLVIMENTO E CONFLITO (~30%): A "carne" do documentário — eventos, transformações, tensões, pontos de virada.
Ato 4 - IMPACTO E LEGADO (~20%): Consequências duradouras, influência no presente, lições, estado atual do tema.
Ato 5 - REFLEXÃO FINAL (~10%): Conexão humana/filosófica, pergunta aberta, convite à reflexão do espectador.

ESTILO DE NARRAÇÃO
- Português do Brasil impecável, gramática correta, acentuação padrão.
- Frases de ritmo falado: nem telegráficas, nem excessivamente longas (15-25 palavras ideal).
- Parágrafos curtos (2-4 frases). Quebra de linha entre parágrafos.
- Voz ativa. Verbos precisos. Substantivos concretos. Adjetivos raros e necessários.
- Transições naturais entre parágrafos (não "além disso", "por outro lado" — use conectivos semânticos).

FORMATO DE SAÍDA
Responda SOMENTE com o texto narrado, em parágrafos separados por linha em branco.
SEM títulos, SEM listas, SEM markdown, SEM asteriscos, SEM rubricas, SEM nome de locutor.
Apenas o texto que o narrador vai ler.

TEXTOS-FONTE
{fontes_txt}"""


def _carregar_ask_web():
    pasta = os.getenv("VF_WEBCHAT_DIR", "").strip()
    if pasta and pasta not in sys.path:
        sys.path.insert(0, pasta)
    from webchat_bridge import ask_web  # type: ignore
    return ask_web


def _limpar_ui(texto: str) -> str:
    linhas = [l for l in texto.splitlines() if not UI_LIXO.match(l)]
    return "\n".join(linhas).strip()


def _validar_roteiro(texto: str, target_words: int, topic: str,
                     min_words: int = 0) -> tuple[bool, str]:
    """Valida qualidade básica do roteiro gerado."""
    words = texto.split()
    wc = len(words)
    lo = min_words if min_words > 0 else int(target_words * 0.85)
    hi = int(target_words * 1.20)
    
    if wc < lo:
        return False, f"Roteiro curto demais: {wc} palavras (mínimo {lo})"
    if wc > hi:
        return False, f"Roteiro longo demais: {wc} palavras (máximo {hi})"
    
    # Verifica alucinações óbvias
    lower = texto.lower()
    red_flags = [
        "segundo a wikipedia", "conforme a fonte", "de acordo com o texto",
        "a fonte diz", "o texto menciona", "como vimos na fonte",
        "[fonte", "[1]", "[2]", "referência:", "citado em"
    ]
    for flag in red_flags:
        if flag in lower:
            return False, f"Violação anti-alucinação: contém '{flag}'"
    
    # Verifica se menciona o tema
    topic_words = [w for w in topic.lower().split() if len(w) > 3]
    if topic_words and not any(tw in lower for tw in topic_words[:2]):
        return False, f"Tema '{topic}' não aparece no roteiro"
    
    # Verifica estrutura mínima (pelo menos 4 parágrafos)
    paragraphs = [p.strip() for p in texto.split("\n\n") if p.strip()]
    if len(paragraphs) < 4:
        return False, f"Estrutura insuficiente: {len(paragraphs)} parágrafos (mínimo 4)"
    
    return True, f"OK: {wc} palavras, {len(paragraphs)} parágrafos"


# =============================================================================
# GERAÇÃO SEQUENCIAL PARA ROTEIROS LONGOS
# =============================================================================

def _montar_prompt_parte(
    topic: str,
    duration_min: float,
    target_words: int,
    persona: str,
    sources: List[Dict],
    canal: str,
    parte_atual: int,
    total_partes: int,
    palavras_alvo_parte: int,
    partes_anteriores: List[str],
    estrutura_planejada: List[str]
) -> str:
    """Monta prompt para uma parte específica do roteiro."""
    lo, hi = int(palavras_alvo_parte * 0.90), int(palavras_alvo_parte * 1.10)
    por_fonte = max(1000, min(MAX_CHARS_POR_FONTE, BUDGET_FONTES // max(1, len(sources))))
    
    blocos = []
    for i, s in enumerate(sources, 1):
        title = s.get('title', 'Sem título')
        url = s.get('url', '')
        text = s.get('text', '')[:por_fonte]
        blocos.append(f"[FONTE {i}] {title}\nURL: {url}\n{text}")
    fontes_txt = "\n\n---\n\n".join(blocos)

    canal_instrucoes = {
        "historia": (
            "ESTILO HISTÓRICO: Tom solene, cronológico, épico. Foque em datas, nomes, "
            "causas e consequências. Use 'Em X ano', 'No século Y', 'Durante o reinado de Z'. "
            "Evite especulação. Se houver controvérsia histórica, apresente as teses principais."
        ),
        "geopolitica": (
            "ESTILO GEOPOLÍTICO: Tom analítico, estratégico, sóbrio. Foque em interesses nacionais, "
            "equilíbrio de poder, doutrinas, tratados, sanções, logística. Evite adjetivos emocionais. "
            "Use 'O país X busca', 'A doutrina Y prevê', 'O interesse estratégico é'."
        ),
        "tecnologia": (
            "ESTILO TECNOLOGIA: Tom moderno, preciso, curioso. Foque em inovação, arquitetura, "
            "limitações técnicas, marcos, pioneiros, impacto social. Explique conceitos complexos "
            "com analogias acessíveis. Use 'Em YEAR, pesquisadores de X demonstraram...'"
        ),
        "documentario": (
            "ESTILO DOCUMENTÁRIO: Tom envolvente, reflexivo, culturalmente rico, cinematográfico. "
            "Equilibre narrativa humana com fatos verificáveis. Use gancho sensorial no início. "
            "Termine com reflexão que conecte passado/presente/futuro."
        ),
    }
    estilo_canal = canal_instrucoes.get(canal.lower(), canal_instrucoes["documentario"])

    # Contexto das partes anteriores
    contexto_anterior = ""
    if partes_anteriores:
        contexto_anterior = f"\n\n=== PARTES JÁ ESCRITAS (NÃO REPITA) ===\n"
        for i, parte in enumerate(partes_anteriores, 1):
            contexto_anterior += f"\n--- PARTE {i} ---\n{parte[:800]}...\n"
        contexto_anterior += "\n=== FIM DAS PARTES ANTERIORES ===\n"

    # Estrutura planejada para esta parte
    estrutura_parte = ""
    if parte_atual <= len(estrutura_planejada):
        estrutura_parte = f"\nESTRUTURA DESTA PARTE ({parte_atual}/{total_partes}):\n{estrutura_planejada[parte_atual - 1]}\n"

    return f"""{persona}

{estilo_canal}

TAREFA
Escreva a PARTE {parte_atual} DE {total_partes} do roteiro narrado de um vídeo documentário para YouTube sobre: "{topic}".
Esta parte deve ter entre {int(palavras_alvo_parte * 0.90)} e {int(palavras_alvo_parte * 1.10)} palavras.
Duração total do vídeo: {duration_min:.1f} minutos (~{int(duration_min * 135)} palavras total).

{estrutura_parte}
{contexto_anterior}

REGRAS ANTI-ALUCINAÇÃO (VIOLAÇÃO = ROTEIRO REJEITADO)
1. Você PODE e DEVE usar conhecimento consolidado e amplamente aceito (consenso histórico, científico e enciclopédico) para contexto, análise e narrativa. Não se limite a resumir as fontes.
2. NUNCA invente dados verificáveis: datas exatas, nomes próprios, números, estatísticas, citações, tratados, leis ou resultados de estudos dos quais você não tenha certeza.
3. Se um dado específico não estiver nas fontes nem for de conhecimento consolidado, escreva de forma honesta e genérica ("os registros divergem sobre a data exata") em vez de inventar.
4. Se o tema for ficção (conto, lenda, fábula, mito), DECLARE EXPLICITAMENTE no roteiro: "Esta é uma narrativa ficcional / lenda / conto tradicional".
5. IGNORE trechos das fontes que não tenham relação direta com o tema.
6. NÃO cite fontes no texto falado. NÃO use colchetes, números de nota, referências, "segundo a Wikipedia", "conforme a fonte".
7. NÃO use frases genéricas de enchimento ("é importante notar que", "vale ressaltar que", "no entanto", "além disso") — cada frase deve agregar informação nova.
8. NÃO repita a mesma informação com palavras diferentes. Cada parágrafo = fato novo.
9. NÃO REPITA CONTEÚDO DAS PARTES ANTERIORES. Continue a narrativa de onde parou.
10. MANTENHA CONTINUIDADE NARRATIVA: a transição entre partes deve ser imperceptível ao ouvinte.

⚠️⚠️⚠️ EXTENSÃO OBRIGATÓRIA: {int(palavras_alvo_parte * 0.85)} A {int(palavras_alvo_parte * 1.15)} PALAVRAS. ⚠️⚠️⚠️
⚠️ ABAIXO DO MÍNIMO = REJEIÇÃO AUTOMÁTICA + REGENERAÇÃO FORÇADA.
⚠️ NÃO RESUMA. NÃO CONDENSE. NÃO ECONOMIZE PALAVRAS.
⚠️ EXPANDA cada subtópico: causas, consequências, números, nomes, cronologia, detalhes táticos, contexto político, impacto humano.
⚠️ MÍNIMO 8-12 PARÁGRAFOS DE 3-5 FRASES CADA. Use toda a extensão permitida.
⚠️ Se o tópico é "Batalha de Stalingrado", NÃO escreva "houve uma batalha". ESCREVA: o cerco, o inverno de 1942-43, a Operação Urano, o 6º Exército cercado, 2 milhões de baixas, a rendição de Paulus, o significado estratégico para o flanco oriental.
⚠️ CADA FRASE DEVE TRAZER INFORMAÇÃO NOVA E ESPECÍFICA.

ESTRUTURA E ESTILO
- Português do Brasil impecável, gramática correta, acentuação padrão.
- Frases de ritmo falado: nem telegráficas, nem excessivamente longas (15-25 palavras ideal).
- Parágrafos curtos (2-4 frases). Quebra de linha entre parágrafos.
- Voz ativa. Verbos precisos. Substantivos concretos. Adjetivos raros e necessários.
- Transições naturais entre parágrafos (não "além disso", "por outro lado" — use conectivos semânticos).

FORMATO DE SAÍDA
Responda SOMENTE com o texto narrado desta parte, em parágrafos separados por linha em branco.
SEM títulos, SEM listas, SEM markdown, SEM asteriscos, SEM rubricas, SEM nome de locutor.
Apenas o texto que o narrador vai ler.

TEXTOS-FONTE
{fontes_txt}"""


def _planejar_estrutura(
    topic: str,
    duration_min: float,
    target_words: int,
    persona: str,
    sources: List[Dict],
    canal: str,
    total_partes: int
) -> List[str]:
    """Usa o LLM para planejar a estrutura do roteiro em partes."""
    # Prompt simplificado só para planejamento
    planejamento_prompt = f"""Você é um roteirista de documentários planejando a estrutura de um vídeo sobre "{topic}".
    
Duração: {duration_min:.1f} minutos (~{int(duration_min * 135)} palavras)
Divida em {total_partes} partes sequenciais, cada uma com foco narrativo claro.

Retorne APENAS uma lista JSON com {total_partes} strings, cada uma descrevendo o foco da parte.
Exemplo para 3 partes:
[
  "Ato 1 - Gancho e Origens: O cenário inicial, eventos precipitantes, contexto histórico/cultural",
  "Ato 2-3 - Desenvolvimento e Conflito: Eventos centrais, tensões, pontos de virada, personagens chave",
  "Ato 4-5 - Desfecho e Legado: Desfecho, consequências, lições, reflexão final conectando ao presente"
]"""
    
    try:
        from webchat_bridge import ask_web
        sites = [s.strip() for s in os.getenv("VF_WEBCHAT_SITES", "gemini,chatgpt,copilot,deepseek").split(",") if s.strip()]
        resultado = ask_web(planejamento_prompt, order=sites, interactive=True, fallback_local=False, validar=None)
        texto = str(resultado.get("answer", "") or "").strip()
        
        # Tenta extrair JSON
        import re
        json_match = re.search(r'\[.*\]', texto, re.DOTALL)
        if json_match:
            estrutura = json.loads(json_match.group())
            if isinstance(estrutura, list) and len(estrutura) == total_partes:
                return estrutura
    except Exception:
        pass
    
    # Fallback: estrutura genérica baseada em 5 atos
    atos_por_parte = max(1, 5 // total_partes)
    estrutura = []
    for i in range(total_partes):
        inicio = i * atos_por_parte + 1
        fim = min((i + 1) * atos_por_parte, 5)
        if inicio == fim:
            estrutura.append(f"Ato {inicio}: Foco narrativo específico desta parte")
        else:
            estrutura.append(f"Atos {inicio} a {fim}: Desenvolvimento narrativo contínuo")
    return estrutura


def _gerar_parte(
    topic: str,
    duration_min: float,
    target_words: int,
    persona: str,
    sources: List[Dict],
    canal: str,
    parte_atual: int,
    total_partes: int,
    palavras_alvo_parte: int,
    partes_anteriores: List[str],
    estrutura_planejada: List[str],
    log=print
) -> str:
    """Gera uma única parte do roteiro."""
    prompt = _montar_prompt_parte(
        topic, duration_min, target_words, persona, sources, canal,
        parte_atual, total_partes, palavras_alvo_parte,
        partes_anteriores, estrutura_planejada
    )
    
    # Salva prompt para debug
    slug = re.sub(r'[^\w\s-]', '', topic).strip().lower()
    slug = re.sub(r'[-\s]+', '_', slug)[:45]
    roteiros_dir = Path.cwd() / "roteiros"
    roteiros_dir.mkdir(exist_ok=True)
    prompt_path = roteiros_dir / f"{slug}_parte_{parte_atual}_prompt.txt"
    prompt_path.write_text(prompt, encoding="utf-8")
    
    from webchat_bridge import ask_web
    sites = [s.strip() for s in os.getenv("VF_WEBCHAT_SITES", "gemini,chatgpt,copilot,deepseek").split(",") if s.strip()]
    validar = os.getenv("VF_WEBCHAT_VALIDAR", "nenhum").strip().lower()
    if validar in ("nenhum", ""):
        validar = None
    
    log(f"  [WebChat] Gerando parte {parte_atual}/{total_partes} (~{palavras_alvo_parte} palavras)...")
    
    max_tentativas = 3
    for tentativa in range(1, 4):
        try:
            resultado = ask_web(prompt, order=sites, interactive=True, fallback_local=False, validar=validar)
        except Exception as e:
            if tentativa == 3:
                raise WebChatError(f"Falha na parte {parte_atual} após 3 tentativas: {e}")
            log(f"  [Parte {parte_atual}] Tentativa {tentativa} falhou: {e}")
            continue
        
        texto = _limpar_ui(str(resultado.get("answer", "") or ""))
        site = resultado.get("site", "?")
        if not texto:
            if tentativa == 3:
                raise WebChatError(f"Resposta vazia na parte {parte_atual}")
            continue
        
        # Validação básica
        words = texto.split()
        wc = len(words)
        lo, hi = int(palavras_alvo_parte * 0.80), int(palavras_alvo_parte * 1.20)
        
        if wc < lo or wc > hi:
            log(f"  [Parte {parte_atual}] Fora da faixa: {wc} palavras (esperado {lo}-{hi}). Tentativa {tentativa}/3")
            if tentativa == 3:
                raise WebChatError(f"Parte {parte_atual} não atingiu contagem de palavras")
            continue
        
        # Verifica se não repete partes anteriores
        if partes_anteriores:
            ultimas_palavras_anterior = " ".join(partes_anteriores[-1].split()[-50:])
            primeiras_palavras_atual = " ".join(texto.split()[:50])
            # Verificação simples de sobreposição excessiva
            overlap = len(set(ultimas_palavras_anterior.split()) & set(primeiras_palavras_atual.split()))
            if overlap > 15:
                log(f"  [Parte {parte_atual}] Possível repetição detectada (overlap={overlap}). Tentativa {tentativa}/3")
                if tentativa == 3:
                    log(f"  [Parte {parte_atual}] Aceitando mesmo com possível repetição")
                else:
                    continue
        
        log(f"  [WebChat] ✓ Parte {parte_atual}/{total_partes} validada: {wc} palavras (site: {site})")
        return texto
    
    raise WebChatError(f"Todas as tentativas esgotadas para parte {parte_atual}")


def _juntar_partes(partes: List[str]) -> str:
    """Junta as partes do roteiro com transição suave."""
    if not partes:
        return ""
    if len(partes) == 1:
        return partes[0]
    
    resultado = [partes[0]]
    for i in range(1, len(partes)):
        anterior = partes[i-1].strip()
        atual = partes[i].strip()
        
        # Verifica se a última frase da parte anterior parece completa
        ultima_frase = re.search(r'[.!?][\s]*$', anterior)
        primeira_frase = re.search(r'^[^.!?]+[.!?]', atual)
        
        # Se a parte anterior não termina com pontuação forte, adiciona espaço
        if not ultima_frase:
            resultado.append(" ")
        else:
            resultado.append("\n\n")
        resultado.append(atual)
    
    return "".join(resultado)


def _gerar_roteiro_sequencial(
    topic: str,
    duration_min: float,
    target_words: int,
    persona: str,
    sources: List[Dict],
    canal: str,
    roteiros_dir: Path,
    slug: str,
    sites: List[str],
    log=print,
    min_words: int = 0,
) -> str:
    """Gera roteiro longo em partes sequenciais."""
    log(f"  [Sequencial] Iniciando geração em partes para {target_words} palavras...")
    
    # Calcula número de partes
    total_partes = min(MAX_PARTS, max(2, (target_words + MAX_WORDS_PER_PART - 1) // MAX_WORDS_PER_PART))
    palavras_por_parte = target_words // total_partes
    min_words_parte = int(palavras_por_parte * 0.85)
    max_words_parte = int(palavras_por_parte * 1.15)
    
    log(f"  [Sequencial] {total_partes} partes de ~{palavras_por_parte} palavras cada (faixa: {min_words_parte}-{max_words_parte})")
    
    # 1. Planeja estrutura
    estrutura = _planejar_estrutura(topic, duration_min, target_words, persona, sources, canal, total_partes)
    log(f"  [Sequencial] Estrutura planejada: {estrutura}")
    
    # 2. Gera cada parte sequencialmente
    partes = []
    for parte_num in range(1, total_partes + 1):
        log(f"  [Sequencial] Gerando parte {parte_num}/{total_partes}...")
        
        parte_texto = _gerar_parte(
            topic, duration_min, target_words, persona, sources, canal,
            parte_num, total_partes, palavras_por_parte,
            partes, estrutura, log
        )
        
        if not parte_texto or len(parte_texto.strip()) < 50:
            raise WebChatError(f"Parte {parte_num} gerada vazia ou muito curta")
        
        partes.append(parte_texto)
        log(f"  [Sequencial] ✓ Parte {parte_num} concluída ({len(parte_texto.split())} palavras)")
    
    # 3. Junta partes
    roteiro_completo = _juntar_partes(partes)
    
    # Validação final
    total_wc = len(roteiro_completo.split())
    min_total = min_words if min_words > 0 else int(target_words * 0.85)
    max_total = int(target_words * 1.20)
    
    if total_wc < min_total:
        log(f"  [Sequencial] ATENÇÃO: Roteiro final com {total_wc} palavras (mínimo {min_total})")
        # Tenta expandir pedindo continuação
        roteiro_completo = _expandir_roteiro(roteiro_completo, target_words, topic, persona, sources, canal, sites, log)
        total_wc = len(roteiro_completo.split())
    
    if total_wc > max_total:
        # Trunca respeitando limites de parágrafo (não corta frase no meio)
        paragrafos = [p for p in roteiro_completo.split("\n\n") if p.strip()]
        saida, acumulado = [], 0
        for p in paragrafos:
            n = len(p.split())
            if acumulado + n > max_total:
                break
            saida.append(p)
            acumulado += n
        roteiro_completo = "\n\n".join(saida) if saida else roteiro_completo
        total_wc = len(roteiro_completo.split())
        log(f"  [Sequencial] Roteiro truncado para {total_wc} palavras")
    
    log(f"  [Sequencial] Roteiro final: {total_wc} palavras em {total_partes} partes")
    return roteiro_completo


def _expandir_roteiro(
    roteiro_atual: str,
    target_words: int,
    topic: str,
    persona: str,
    sources: List[Dict],
    canal: str,
    sites: List[str],
    log=print
) -> str:
    """Tenta expandir um roteiro que ficou curto demais."""
    log(f"  [Expandir] Tentando expandir roteiro de {len(roteiro_atual.split())} para ~{target_words} palavras...")
    
    # Prepara prompt de expansão
    por_fonte = max(1000, min(MAX_CHARS_POR_FONTE, BUDGET_FONTES // max(1, len(sources))))
    blocos = []
    for i, s in enumerate(sources, 1):
        title = s.get('title', 'Sem título')
        url = s.get('url', '')
        text = s.get('text', '')[:por_fonte]
        blocos.append(f"[FONTE {i}] {title}\nURL: {url}\n{text}")
    fontes_txt = "\n\n---\n\n".join(blocos)
    
    palavras_faltando = target_words - len(roteiro_atual.split())
    
    prompt_expansao = f"""{persona}

TAREFA: EXPANDIR o roteiro abaixo para atingir ~{target_words} palavras (atualmente tem {len(roteiro_atual.split())}, faltam ~{palavras_faltando}).

ROTEIRO ATUAL (NÃO REPITA, CONTINUE/EXPANDA):
{roteiro_atual}

INSTRUÇÕES DE EXPANSÃO:
1. Adicione DETALHES HISTÓRICOS/FACTUAIS das fontes que ainda não foram usados
2. Desenvolva mais os eventos, causas, consequências, personagens
3. Adicione exemplos concretos, datas, números, nomes
4. Aprofunde as consequências e o legado
5. Mantenha continuidade narrativa perfeita
6. NÃO REPITA o que já está escrito
7. Extensão alvo da expansão: ~{palavras_faltando} palavras

TEXTOS-FONTE (use para adicionar detalhes não usados):
{chr(10).join([f"[FONTE {i+1}] {s.get('title','')}\n{s.get('text','')[:por_fonte]}" for i, s in enumerate(sources)])}

Responda APENAS com o texto da EXPANSÃO (continuação direta), sem repetir o roteiro atual.
"""
    
    try:
        from webchat_bridge import ask_web
        resultado = ask_web(prompt_expansao, order=sites, interactive=True, fallback_local=False, validar=None)
        texto_expansao = _limpar_ui(str(resultado.get("answer", "") or ""))
        
        if texto_expansao and len(texto_expansao.split()) > 100:
            log(f"  [Expandir] Expansão gerada: {len(texto_expansao.split())} palavras")
            return _juntar_partes([roteiro_atual, texto_expansao])
    except Exception as e:
        log(f"  [Expandir] Falha na expansão: {e}")
    
    return roteiro_atual


def escrever_via_webchat(
    topic: str,
    duration_min: float,
    target_words: int,
    persona: str,
    sources: List[Dict],
    roteiros_dir: Path,
    slug: str,
    canal: str = "documentario",
    log=print,
    min_words: int = 0,  # NOVO: palavra-chave mínima obrigatória
) -> str:
    manual = roteiros_dir / f"{slug}_resposta.txt"
    if manual.exists() and manual.read_text(encoding="utf-8").strip():
        log(f"  [WebChat] Usando resposta colada manualmente: {manual.name}")
        return manual.read_text(encoding="utf-8")

    prompt = montar_prompt(topic, duration_min, target_words, persona, sources, canal, min_words)
    prompt_path = roteiros_dir / f"{slug}_prompt.txt"
    prompt_path.write_text(prompt, encoding="utf-8")

    instrucoes = (
        f"Cole o conteúdo de {prompt_path.name} num chat (Gemini, ChatGPT, Copilot ou DeepSeek), "
        f"copie a resposta inteira e salve em {manual}. Depois rode o agente de novo."
    )

    try:
        ask_web = _carregar_ask_web()
    except Exception as e:
        raise WebChatError(f"webchat_bridge não carregou ({e}). {instrucoes}")

    sites = [s.strip() for s in os.getenv("VF_WEBCHAT_SITES", "gemini,chatgpt,copilot,deepseek").split(",") if s.strip()]
    validar = os.getenv("VF_WEBCHAT_VALIDAR", "nenhum").strip().lower()
    if validar in ("nenhum", ""):
        validar = None

    # Verifica se deve usar geração sequencial (roteiros longos)
    if target_words > SEQUENTIAL_THRESHOLD_WORDS:
        log(f"  [WebChat] Roteiro longo ({target_words} palavras) - ativando geração sequencial em partes...")
        return _gerar_roteiro_sequencial(
            topic, duration_min, target_words, persona, sources, canal,
            roteiros_dir, slug, sites, log, min_words
        )

    log(f"  [WebChat] Enviando prompt ({len(prompt)} chars) para: {', '.join(sites)}")
    
    max_tentativas = 3
    for tentativa in range(1, max_tentativas + 1):
        try:
            resultado = ask_web(prompt, order=sites, interactive=True, fallback_local=False, validar=validar)
        except Exception as e:
            if tentativa == max_tentativas:
                raise WebChatError(f"Falha no web chat após {max_tentativas} tentativas ({e}). {instrucoes}")
            log(f"  [WebChat] Tentativa {tentativa} falhou: {e}. Tentando próximo site...")
            continue

        texto = _limpar_ui(str(resultado.get("answer", "") or ""))
        site = resultado.get("site", "?")
        if not texto:
            if tentativa == max_tentativas:
                raise WebChatError(f"Resposta vazia do site {site}. {instrucoes}")
            log(f"  [WebChat] Resposta vazia de {site}, tentando próximo...")
            continue

        # Exibe o roteiro recebido (já validado pelo bridge se VF_WEBCHAT_VALIDAR=terminal)
        print("\n")
        print("=" * 80)
        print(f"ROTEIRO RECEBIDO DO {site.upper()}")
        print("=" * 80)
        print(texto)
        print("=" * 80)

        # Validação automática (estrutura, contagem de palavras, etc.)
        ok, msg = _validar_roteiro(texto, target_words, topic, min_words)
        if not ok:
            log(f"  [WebChat] Validação automática falhou ({msg}). Tentativa {tentativa}/{max_tentativas}")
            if tentativa == max_tentativas:
                raise WebChatError(f"Roteiro não passou na validação: {msg}. {instrucoes}")
            continue

        log(f"  [WebChat] ✓ Roteiro validado: {msg} (site: {site})")
        (roteiros_dir / f"{slug}_webchat_bruto.txt").write_text(f"[site: {site}]\n{texto}", encoding="utf-8")
        return texto

    raise WebChatError("Todas as tentativas esgotadas")


def pesquisar_fontes_web(topic: str, max_fontes: int = 6) -> List[Dict]:
    """
    Busca fontes adicionais na web (DuckDuckGo HTML + Wikipedia completa).
    Retorna lista de dicts com title, url, text.
    """
    import urllib.parse
    import urllib.request
    
    fontes = []
    
    # 1. Wikipedia completa (não truncada)
    try:
        enc = urllib.parse.quote(topic)
        url = f"https://pt.wikipedia.org/w/api.php?action=query&format=json&prop=extracts&explaintext=1&titles={enc}"
        req = urllib.request.Request(url, headers={"User-Agent": "VideoFactoryAI/4.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.load(resp)
            pages = data.get("query", {}).get("pages", {})
            for page_id, page_info in pages.items():
                if page_id != "-1" and "extract" in page_info:
                    extract = page_info["extract"]
                    if len(extract) > 500:
                        fontes.append({
                            "title": page_info.get("title", topic),
                            "url": f"https://pt.wikipedia.org/wiki/{enc}",
                            "text": extract  # Artigo COMPLETO
                        })
    except Exception:
        pass
    
    # 2. DuckDuckGo HTML scraping para fontes complementares
    try:
        query = urllib.parse.quote(f"{topic} história origem significado")
        ddg_url = f"https://html.duckduckgo.com/html/?q={query}"
        req = urllib.request.Request(ddg_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode("utf-8", errors="ignore")
        
        # Extrai snippets dos resultados
        import re
        results = re.findall(r'class="result__snippet">([^<]+)</a>', html)
        for i, snippet in enumerate(results[:max_fontes-1]):
            if len(snippet) > 100:
                fontes.append({
                    "title": f"Fonte web {i+1}: {topic}",
                    "url": "duckduckgo.com",
                    "text": snippet[:MAX_CHARS_POR_FONTE]
                })
    except Exception:
        pass
    
    return fontes[:max_fontes]


# =============================================================================
# FUNÇÕES PARA USAR O GEM @roteiroparavideos (GEMINI PERSONALIZADO)
# =============================================================================

def montar_prompt_gem(topic: str, duration_min: float) -> str:
    """
    Monta prompt no formato do Gem @roteiroparavideos.
    
    O Gem já tem instruções internas de:
    - Gerar roteiro documental completo
    - Definir cenas com timestamps, visuais e durações
    - Gerar narração única (locução completa)
    
    Formato de saída do Gem:
      PARTE 1: Estrutura de cenas (timestamps + visual + duração)
      PARTE 2: Texto único de narração
    """
    return f"@roteiroparavideos {topic} — Duração alvo: {duration_min:.0f} minutos"


def escrever_via_webchat_gem(
    topic: str,
    duration_min: float,
    target_words: int,
    roteiros_dir: Path,
    slug: str,
    log=print,
    min_words: int = 0,
) -> Dict:
    """
    Usa o Gem @roteiroparavideos para gerar roteiro + cenas + narração.
    
    Retorna dict com:
      - "titulo": str
      - "cenas": List[Dict] (formato pipeline)
      - "narracao": str (texto para TTS)
      - "narracao_completa": str (inclui CTA)
      - "roteiro_bruto": str (saída completa do Gem)
      - "site": str (qual site respondeu)
    """
    from gem_roteiro_parser import parse_gem_output, gem_para_cenas_pipeline, validar_roteiro_gem
    
    # Verifica se existe resposta manual colada
    manual = roteiros_dir / f"{slug}_resposta.txt"
    if manual.exists() and manual.read_text(encoding="utf-8").strip():
        log(f"  [Gem] Usando resposta colada manualmente: {manual.name}")
        texto_bruto = manual.read_text(encoding="utf-8")
    else:
        # Monta prompt simples para o Gem
        prompt = montar_prompt_gem(topic, duration_min)
        prompt_path = roteiros_dir / f"{slug}_prompt.txt"
        prompt_path.write_text(prompt, encoding="utf-8")
        
        try:
            ask_web = _carregar_ask_web()
        except Exception as e:
            raise WebChatError(
                f"webchat_bridge não carregou ({e}). "
                f"Cole o conteúdo de {prompt_path.name} no Gemini com @roteiroparavideos, "
                f"copie a resposta e salve em {manual}."
            )
        
        sites = [s.strip() for s in os.getenv("VF_WEBCHAT_SITES", "gemini").split(",") if s.strip()]
        # Prioriza gemini para usar o Gem
        if "gemini" in sites:
            sites.remove("gemini")
            sites.insert(0, "gemini")
        
        validar = os.getenv("VF_WEBCHAT_VALIDAR", "nenhum").strip().lower()
        if validar in ("nenhum", ""):
            validar = None
        
        log(f"  [Gem] Enviando prompt para: {', '.join(sites)}")
        log(f"  [Gem] Prompt: {prompt}")
        
        max_tentativas = 3
        texto_bruto = None
        site_respondeu = "?"
        
        for tentativa in range(1, max_tentativas + 1):
            try:
                resultado = ask_web(prompt, order=sites, interactive=True, fallback_local=False, validar=validar)
            except Exception as e:
                if tentativa == max_tentativas:
                    raise WebChatError(
                        f"Falha no web chat após {max_tentativas} tentativas ({e}). "
                        f"Cole manualmente em {manual}"
                    )
                log(f"  [Gem] Tentativa {tentativa} falhou: {e}. Tentando próximo site...")
                continue
            
            texto = _limpar_ui(str(resultado.get("answer", "") or ""))
            site_respondeu = resultado.get("site", "?")
            
            if not texto:
                if tentativa == max_tentativas:
                    raise WebChatError(f"Resposta vazia do site {site_respondeu}. Cole manualmente em {manual}")
                log(f"  [Gem] Resposta vazia de {site_respondeu}, tentando próximo...")
                continue
            
            texto_bruto = texto
            break
        
        if not texto_bruto:
            raise WebChatError(f"Não foi possível obter resposta do Gem. Cole manualmente em {manual}")
        
        # Salva resposta bruta para auditoria
        (roteiros_dir / f"{slug}_webchat_bruto.txt").write_text(
            f"[site: {site_respondeu}]\n{texto_bruto}", encoding="utf-8"
        )
    
    # Parse da saída do Gem
    log(f"  [Gem] Fazendo parse da saída ({len(texto_bruto)} chars)...")
    roteiro_gem = parse_gem_output(texto_bruto)
    
    # Valida
    ok, msg = validar_roteiro_gem(roteiro_gem, min_words)
    if not ok:
        raise WebChatError(f"Roteiro do Gem inválido: {msg}")
    
    log(f"  [Gem] ✓ Roteiro validado: {msg}")
    log(f"  [Gem]   Título: {roteiro_gem.titulo}")
    log(f"  [Gem]   Cenas: {len(roteiro_gem.cenas)}")
    log(f"  [Gem]   Narração: {len(roteiro_gem.narracao_para_tts.split())} palavras")
    
    # Converte cenas para formato do pipeline
    cenas_pipeline = gem_para_cenas_pipeline(roteiro_gem, topic)
    log(f"  [Gem]   Cenas convertidas para pipeline: {len(cenas_pipeline)}")
    
    # Salva dados processados
    dados = {
        "titulo": roteiro_gem.titulo,
        "cenas": cenas_pipeline,
        "narracao": roteiro_gem.narracao_para_tts,
        "narracao_completa": roteiro_gem.narracao_completa,
        "roteiro_bruto": texto_bruto,
        "site": site_respondeu if 'site_respondeu' in dir() else "manual",
        "duracao_total_min": roteiro_gem.duracao_total_min,
        "total_cenas": len(roteiro_gem.cenas),
    }
    
    # Salva JSON processado
    import json
    dados_path = roteiros_dir / f"{slug}_gem_dados.json"
    dados_path.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"  [Gem] Dados salvos em: {dados_path.name}")
    
    # Salva narração separadamente para TTS
    narracao_path = roteiros_dir / f"{slug}_narracao.txt"
    narracao_path.write_text(roteiro_gem.narracao_para_tts, encoding="utf-8")
    log(f"  [Gem] Narração salva em: {narracao_path.name}")
    
    # Salva narração com CTA
    narracao_cta_path = roteiros_dir / f"{slug}_narracao_completa.txt"
    narracao_cta_path.write_text(roteiro_gem.narracao_completa, encoding="utf-8")
    
    return dados


def gerar_roteiro_gem(
    topic: str,
    duration_min: float,
    target_words: int,
    roteiros_dir: Path,
    slug: str,
    log=print,
    min_words: int = 0,
) -> str:
    """
    Função wrapper que usa o Gem e retorna APENAS a narração (texto puro).
    
    Compatível com a assinatura esperada pelo agent.py.
    O JSON completo com cenas fica salvo em <slug>_gem_dados.json.
    """
    dados = escrever_via_webchat_gem(
        topic, duration_min, target_words, roteiros_dir, slug, log, min_words
    )
    
    # Retorna narração completa (com CTA) como texto principal
    return dados["narracao_completa"]