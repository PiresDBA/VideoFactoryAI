"""
ScriptWriterAgent — Roteirista e Pesquisador Autônomo do VideoFactoryAI
========================================================================
Permite a produção completa de documentários a partir de um único tema:

    python VideoFactoryAI/agent.py --topic "A Guerra Fria" --duration 8

Executa automaticamente:
  1. Pesquisa factual e histórica via Wikipedia / fontes enciclopédicas abertas
  2. Cálculo de ritmo e contagem de palavras (~135 palavras por minuto)
  3. Estruturação em 5 Atos Documentais clássicos:
     - Ato 1: O Gancho e a Ruptura (Hook & Inciting Incident)
     - Ato 2: As Origens e o Cenário (Context & Genesis)
     - Ato 3: A Escalada e o Ponto Crítico (Climax & Turning Points)
     - Ato 4: As Consequências e o Desfecho (Aftermath & Resolution)
     - Ato 5: O Legado e a Lição Contemporânea (Legacy & Reflection)
  4. Adaptação do vocabulário e tom ao Canal selecionado (Geopolítica, História, Tecnologia, etc.)
  5. Exportação para roteiros/<slug_do_tema>.txt
"""

import os
import re
import json
import time
import unicodedata
import urllib.parse
import urllib.request
import requests
from pathlib import Path
from typing import Dict, List, Optional, Tuple


class ScriptWriterAgent:
    """Agente de pesquisa e geração de roteiros documentais."""

    WORDS_PER_MINUTE = 135  # cadência ideal de narração documental em português

    CANAL_PERSONAS = {
        "geopolitica": (
            "Você é um analista geopolítico e documentarista investigativo renomado. "
            "Seu tom é sóbrio, analítico, tenso e estratégico. Foque no equilíbrio de poder, "
            "serviços de inteligência, doutrinas militares, sanções, alianças e o impacto global."
        ),
        "historia": (
            "Você é um historiador e narrador de documentários épicos de prestígio internacional. "
            "Seu tom é solene, dramático, cronológico e focado nas grandes decisões humanas, "
            "discursos memoráveis e no peso das transformações históricas."
        ),
        "tecnologia": (
            "Você é um documentarista de ciência e tecnologia de vanguarda. "
            "Seu tom é moderno, ágil, visionário e preciso. Foque na corrida tecnológica, "
            "na inovação, nos pioneiros e nas implicações éticas e futuras das invenções."
        ),
        "documentario": (
            "Você é um diretor e roteirista de documentários de alto padrão para cinema e TV. "
            "Seu tom é jornalístico, imparcial, profundo, cativante e de ritmo impecável."
        ),
    }

    def __init__(self, root_dir: Path):
        self.root_dir     = Path(root_dir)
        self.roteiros_dir = self.root_dir / "roteiros"
        self.roteiros_dir.mkdir(parents=True, exist_ok=True)

    # ─────────────────────────────────────────────────────────────────────────
    # API pública
    # ─────────────────────────────────────────────────────────────────────────

    def generate(
        self,
        topic: str,
        duration_min: float = 5.0,
        canal: Optional[str] = None
    ) -> Tuple[str, Path]:
        """
        Pesquisa o tema, gera o roteiro completo e salva em roteiros/<slug>.txt.
        Retorna (texto_do_roteiro, caminho_do_arquivo).
        """
        topic = topic.strip()
        duration_min = max(1.0, float(duration_min))
        target_words = int(duration_min * self.WORDS_PER_MINUTE)
        canal_key = (canal or "documentario").lower().rstrip("s")
        if canal_key not in self.CANAL_PERSONAS:
            canal_key = "documentario"

        print(f"\n[ScriptWriterAgent] Iniciando pesquisa e redacao de documentario:")
        print(f"  Tema       : '{topic}'")
        print(f"  Duracao    : {duration_min:.1f} min (~{target_words} palavras)")
        print(f"  Estilo     : {canal_key.capitalize()}")

        # 1. Pesquisa factual na Wikipedia (PT-BR)
        research_data = self._research_wikipedia(topic)

        # 2. Geração do roteiro em 5 atos
        script_text = self._write_script(topic, target_words, canal_key, research_data)

        # 3. Validação e polimento
        word_count = len(script_text.split())
        est_min = word_count / self.WORDS_PER_MINUTE
        print(f"  Roteiro finalizado: {word_count} palavras (estimativa: {est_min:.1f} min)")

        # 4. Salvar arquivo
        slug = self._slugify(topic)
        out_path = self.roteiros_dir / f"{slug}.txt"
        out_path.write_text(script_text, encoding="utf-8")
        print(f"  Arquivo salvo: {out_path.relative_to(self.root_dir)}")

        return script_text, out_path

    # ─────────────────────────────────────────────────────────────────────────
    # Pesquisa Enciclopédica (Wikipedia API gratuita, sem chave)
    # ─────────────────────────────────────────────────────────────────────────

    def _research_wikipedia(self, topic: str) -> Dict[str, str]:
        """Busca contexto histórico confiável na Wikipedia em português."""
        print(f"  [Pesquisa] Consultando enciclopedia aberta sobre '{topic}'...")
        headers = {"User-Agent": "VideoFactoryAI/4.0 (Autonomous Documentary Producer; pt-BR)"}
        data = {"title": topic, "summary": "", "full_text": ""}

        try:
            # 1. Tenta buscar pelo termo direto
            enc_topic = urllib.parse.quote(topic)
            url = (
                f"https://pt.wikipedia.org/w/api.php?action=query&format=json"
                f"&prop=extracts&explaintext=1&exintro=0&titles={enc_topic}"
            )
            r = requests.get(url, headers=headers, timeout=12)
            if r.status_code == 200:
                pages = r.json().get("query", {}).get("pages", {})
                for page_id, page_info in pages.items():
                    if page_id != "-1" and "extract" in page_info:
                        data["title"] = page_info.get("title", topic)
                        extract = page_info.get("extract", "")
                        data["full_text"] = extract[:4000]
                        data["summary"] = extract[:1000]
                        print(f"    [OK] Fatos encontrados: '{data['title']}' ({len(data['full_text'])} caracteres)")
                        return data

            # 2. Se não achou página exata, faz busca de termos relacionados
            search_url = (
                f"https://pt.wikipedia.org/w/api.php?action=opensearch&format=json"
                f"&search={enc_topic}&limit=3"
            )
            r_search = requests.get(search_url, headers=headers, timeout=10)
            if r_search.status_code == 200:
                res = r_search.json()
                if len(res) >= 2 and len(res[1]) > 0:
                    best_match = res[1][0]
                    print(f"    [Refinamento] Buscando melhor correspondencia: '{best_match}'...")
                    enc_best = urllib.parse.quote(best_match)
                    url_best = (
                        f"https://pt.wikipedia.org/w/api.php?action=query&format=json"
                        f"&prop=extracts&explaintext=1&exintro=0&titles={enc_best}"
                    )
                    r_best = requests.get(url_best, headers=headers, timeout=12)
                    if r_best.status_code == 200:
                        pages = r_best.json().get("query", {}).get("pages", {})
                        for page_id, page_info in pages.items():
                            if page_id != "-1" and "extract" in page_info:
                                data["title"] = page_info.get("title", best_match)
                                extract = page_info.get("extract", "")
                                data["full_text"] = extract[:4000]
                                data["summary"] = extract[:1000]
                                print(f"    [OK] Fatos encontrados: '{data['title']}' ({len(data['full_text'])} caracteres)")
                                return data
        except Exception as e:
            print(f"    [Aviso] Pesquisa online falhou ({e}). Usando motor heuristico.")

        return data

    # ─────────────────────────────────────────────────────────────────────────
    # Redação do Roteiro (Narrativa em 5 Atos)
    # ─────────────────────────────────────────────────────────────────────────

    def _write_script(
        self,
        topic: str,
        target_words: int,
        canal_key: str,
        research: Dict[str, str]
    ) -> str:
        """Gera o texto completo estruturado em 5 atos documentais."""
        print(f"  [Redacao] Estruturando narrativa em 5 atos para {target_words} palavras...")

        # Tenta gerar com IA neural gratuita (Pollinations Text)
        script = self._generate_with_ai(topic, target_words, canal_key, research)
        if script and len(script.split()) >= (target_words * 0.5):
            return self._clean_script(script)

        # Fallback: motor procedural interno baseado nos fatos enciclopédicos
        print("  [Redacao] Usando motor procedural documental de alta densidade...")
        return self._generate_procedural(topic, target_words, canal_key, research)

    def _generate_with_ai(
        self,
        topic: str,
        target_words: int,
        canal_key: str,
        research: Dict[str, str]
    ) -> Optional[str]:
        """Tenta gerar via API neural de texto (Pollinations OpenAI model)."""
        persona = self.CANAL_PERSONAS.get(canal_key, self.CANAL_PERSONAS["documentario"])
        context = research.get("summary", "") or research.get("full_text", "")[:1200]

        prompt = (
            f"{persona}\n\n"
            f"Escreva o roteiro de narração completo para um documentário em vídeo com o tema: '{topic}'.\n"
            f"Meta de extensão: aproximadamente {target_words} palavras.\n"
            f"Contexto histórico e fatos disponíveis:\n{context}\n\n"
            f"Instruções obrigatórias de formato:\n"
            f"1. Escreva SOMENTE o texto contínuo que o narrador fala em voz alta.\n"
            f"2. NUNCA inclua marcações de cena como [Câmera corta], (Música sobe), [Ato 1] ou nomes de locutor.\n"
            f"3. Estruture a narração em 5 atos fluidos: gancho dramático inicial, contexto histórico das origens, "
            f"a escalada e os pontos críticos de virada, o desfecho/consequências e uma reflexão final solene.\n"
            f"4. Use frases fortes, ritmo cinematográfico e excelente cadência para leitura por voz neural.\n"
            f"5. Idioma: Português do Brasil impecável."
        )

        try:
            url = "https://text.pollinations.ai/"
            payload = {
                "messages": [
                    {"role": "system", "content": persona},
                    {"role": "user", "content": prompt}
                ],
                "model": "openai-fast",
                "seed": 42,
            }
            r = requests.post(url, json=payload, timeout=14)
            if r.status_code == 200 and len(r.text.strip()) > 100:
                raw = r.text.strip()
                # Se retornou JSON, tenta decodificar content
                if raw.startswith("{"):
                    try:
                        data = json.loads(raw)
                        content = data.get("content")
                        if content and isinstance(content, str):
                            raw = content
                    except Exception:
                        pass

                # Remove blocos de reasoning / thinking
                raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL)
                print("    [IA] Roteiro sintetizado com sucesso via gerador neural.")
                return raw.strip()
        except Exception as e:
            print(f"    [Aviso] Gerador neural indisponivel ({e}).")

        return None

    def _generate_procedural(
        self,
        topic: str,
        target_words: int,
        canal_key: str,
        research: Dict[str, str]
    ) -> str:
        """
        Gera roteiro documental factual procedural de alta qualidade
        utilizando a pesquisa enciclopédica estruturada em 5 atos.
        """
        full_text = research.get("full_text", "")
        # Extrai parágrafos substantivos
        paragraphs = [p.strip() for p in full_text.split("\n") if len(p.strip()) > 100]

        # Hooks introdutórios por canal
        hooks = {
            "geopolitica": (
                f"No tabuleiro das disputas globais, poucos momentos redefiniram com tanta intensidade "
                f"o destino das nações quanto {topic}. Por trás de discursos oficiais e tratados celebrados em público, "
                f"um jogo invisível de poder, pressões econômicas e estratégias de inteligência moldou os rumos do planeta."
            ),
            "historia": (
                f"Há momentos na história humana em que o tempo parece acelerar e o destino de milhões "
                f"é decidido em um punhado de escolhas cruciais. A história de {topic} é uma dessas narrativas fundamentais, "
                f"onde coragem, tragédia e ambição colidiram de maneira definitiva."
            ),
            "tecnologia": (
                f"A busca pelo domínio do futuro sempre foi impulsionada por saltos audaciosos e inovações que desafiaram os limites. "
                f"Ao explorarmos a trajetória de {topic}, deparamo-nos com o ponto exato em que a ciência, a engenhosidade "
                f"e a necessidade transformaram para sempre a realidade como a conhecemos."
            ),
            "documentario": (
                f"Compreender o presente exige examinar criticamente as forças profundas que moldaram o nosso passado. "
                f"A jornada de {topic} nos coloca diante de um dos episódios mais reveladores da história recente, "
                f"cujas lições continuam a ecoar em todas as esferas da sociedade moderna."
            ),
        }

        # Conclusões solenes por canal
        outros = {
            "geopolitica": (
                f"Hoje, ao examinarmos o legado deixado por {topic}, fica evidente que os impasses de outrora "
                f"não desapareceram, apenas assumiram novas formas e territórios. As nações que compreendem essas dinâmicas "
                f"conseguem antecipar o futuro; aquelas que as esquecem estão condenadas a repetir suas crises mais profundas."
            ),
            "historia": (
                f"O tempo segue seu curso implacável, mas a memória dos acontecimentos de {topic} permanece como um monumento "
                f"à capacidade de transformação da humanidade. Lembrar esses passos não é apenas olhar para trás, mas sim "
                f"iluminar o caminho que ainda temos por construir."
            ),
            "tecnologia": (
                f"As fronteiras que antes pareciam intransponíveis foram vencidas. O legado de {topic} comprova que "
                f"cada avanço técnico é também um reflexo de nossas maiores aspirações e dilemas morais, anunciando os novos desafios "
                f"que nos aguardam no horizonte do amanhã."
            ),
            "documentario": (
                f"Ao final desta investigação sobre {topic}, resta a constatação de que nenhum acontecimento histórico é um ponto isolado. "
                f"Cada vitória, cada sacrifício e cada decisão continuam vivos nas estruturas do mundo em que habitamos."
            ),
        }

        body_parts = []
        body_parts.append(hooks.get(canal_key, hooks["documentario"]))

        if paragraphs:
            # Seleciona parágrafos enciclopédicos mais relevantes e adapta
            for p in paragraphs[:6]:
                # Limpa citações como [1], [2]
                clean_p = re.sub(r"\[\d+\]", "", p).strip()
                if len(clean_p) > 60:
                    body_parts.append(clean_p)
        else:
            # Se a enciclopédia veio vazia, constrói narrativa temática sólida
            body_parts.append(
                f"Para compreender a verdadeira magnitude de {topic}, é preciso recuar até as raízes que alimentaram "
                f"esse movimento. As tensões acumuladas ao longo de décadas criaram um terreno propício para que a ruptura ocorresse, "
                f"envolvendo atores decisivos cujos nomes ficaram gravados de forma indelével nos arquivos do tempo."
            )
            body_parts.append(
                f"À medida que os eventos se desenrolavam, a escalada tornou-se inevitável. As decisões tomadas sob extrema pressão "
                f"revelaram tanto a fragilidade dos pactos existentes quanto a determinação inabalável de lideranças em defender suas visões, "
                f"desencadeando consequências que rapidamente ultrapassaram fronteiras e atingiram proporções épicas."
            )
            body_parts.append(
                f"O clímax desse processo representou uma virada sem retorno. Alianças foram testadas, novos equilíbrios se estabeleceram "
                f"e os impactos sociais e políticos começaram a se fazer sentir em cada recanto afetado por esse desfecho histórico."
            )

        body_parts.append(outros.get(canal_key, outros["documentario"]))

        script = "\n\n".join(body_parts)
        return self._clean_script(script)

    # ─────────────────────────────────────────────────────────────────────────
    # Limpeza e Padronização
    # ─────────────────────────────────────────────────────────────────────────

    def _clean_script(self, raw_text: str) -> str:
        """Remove marcações de cena, JSON residual e normaliza pontuação."""
        if raw_text.startswith("{") and "reasoning" in raw_text:
            # Tenta extrair blocos de narrativa entre aspas
            matches = re.findall(r'"([^"\\]*(?:\\.[^"\\]*)*)"', raw_text)
            long_matches = [m for m in matches if len(m) > 120 and not m.startswith("The user") and not m.startswith("We'll")]
            if long_matches:
                raw_text = "\n\n".join(long_matches)

        cleaned = re.sub(r"<think>.*?</think>", "", raw_text, flags=re.DOTALL)
        cleaned = re.sub(r"\[.*?\]", "", cleaned)
        cleaned = re.sub(r"\(.*?\)", "", cleaned)
        cleaned = re.sub(r"^(Narrador|Locutor|Ato \d+|Cena \d+):\s*", "", cleaned, flags=re.MULTILINE | re.IGNORECASE)

        # Remove linhas vazias excessivas
        paragraphs = [p.strip() for p in cleaned.split("\n") if p.strip()]
        return "\n\n".join(paragraphs)

    def _slugify(self, text: str) -> str:
        """Gera um nome de arquivo amigável a partir do título."""
        text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
        text = re.sub(r"[^\w\s-]", "", text).strip().lower()
        slug = re.sub(r"[-\s]+", "_", text)
        return slug[:45] or "documentario_automatico"
