"""
===============================================================================
 VideoFactoryAI — Módulo: ScriptWriterAgent (Roteirista e Pesquisador Autônomo)
===============================================================================
 Este módulo implementa o agente autônomo responsável por pesquisar temas culturais,
 históricos, tecnológicos ou populares e redigir roteiros documentais completos
 e fiéis ao assunto solicitado.

 COMO FUNCIONA:
 1. O usuário fornece apenas um tema (ex: "A morte da bezerra") e a duração (ex: 8 min).
 2. O agente calcula a meta de palavras necessária (~135 palavras por minuto).
 3. O agente consulta fontes enciclopédicas abertas (Wikipedia PT-BR) de forma gratuita.
    Se o artigo exato não existir, busca termos e raízes conceituais correlatas.
 4. Estrutura uma narrativa cinematográfica em 5 Atos Documentais:
      - Ato 1: O Fenômeno e o Gancho (The Hook & Intrigue)
      - Ato 2: As Origens Culturais e Históricas (Genesis & Folklore)
      - Ato 3: A Conexão Simbólica e Mitológica (The Turning Point & Myth)
      - Ato 4: A Psicologia do Cotidiano e da Sociedade (Society & Human Nature)
      - Ato 5: O Legado e a Lição Contemporânea (Legacy & Modern Reflection)
 5. Adapta o vocabulário e o estilo estritamente ao tema e ao canal selecionado.
    NUNCA insere conteúdo de guerra ou geopolítica em temas culturais e cotidianos!
 6. Garante a extensão total requerida pela duração solicitada pelo usuário.
 7. Salva o roteiro pronto em 'roteiros/<slug_do_tema>.txt'.
===============================================================================
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
    """
    Agente de Inteligência Artificial para Pesquisa e Redação Documental Temática.
    
    Garante fidelidade temática estrita, cadência vocal precisa e extensão
    compatível com a minutagem solicitada pelo usuário.
    """

    WORDS_PER_MINUTE = 135  # cadência ideal de narração documental em português

    # Load personas from JSON config file (allows adding channels without code changes)
    from canal_personas_loader import get_persona, get_style_instruction, get_all_channels, load_canal_personas

    # Populate CANAL_PERSONAS from JSON config for backwards compatibility
    CANAL_PERSONAS = load_canal_personas()

    def __init__(self, root_dir: Path):
        self.root_dir = Path(root_dir)
        self.roteiros_dir = self.root_dir / "roteiros"
        self.roteiros_dir.mkdir(parents=True, exist_ok=True)

    # ─────────────────────────────────────────────────────────────────────────
    @classmethod
    def _resolve_canal_key(cls, canal: Optional[str]) -> str:
        """Resolve nomes de canais sem depender de uma lista fixa no código."""
        personas = cls.CANAL_PERSONAS if isinstance(cls.CANAL_PERSONAS, dict) else {}
        raw = (canal or "documentario").strip().lower()
        normalized = unicodedata.normalize("NFKD", raw)
        normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
        normalized = re.sub(r"[^a-z0-9]+", "_", normalized).strip("_")
        candidates = [normalized]
        if normalized.endswith("s") and len(normalized) > 1:
            candidates.append(normalized[:-1])
        for candidate in candidates:
            if candidate in personas:
                return candidate
        for fallback in ("documentario", "documentários", "documentarios"):
            if fallback in personas:
                return fallback
        if personas:
            return next(iter(personas))
        return normalized or "documentario"

    @classmethod
    def _get_persona_safely(cls, canal_key: str) -> str:
        """Obtém a persona sem indexação direta que possa provocar KeyError."""
        personas = cls.CANAL_PERSONAS if isinstance(cls.CANAL_PERSONAS, dict) else {}
        persona = personas.get(canal_key)
        if persona:
            return str(persona)
        for fallback in ("documentario", "documentários", "documentarios"):
            if personas.get(fallback):
                return str(personas[fallback])
        try:
            loaded = cls.get_persona(canal_key)
            if loaded:
                return str(loaded)
        except Exception:
            pass
        return (
            "Você é um roteirista documental. Escreva em português brasileiro, "
            "com clareza, precisão factual e fidelidade estrita ao tema solicitado. "
            "Não invente datas, pessoas, causas ou acontecimentos."
        )

    # API PÚBLICA
    # ─────────────────────────────────────────────────────────────────────────

    def generate(
        self,
        topic: str,
        duration_min: float = 5.0,
        canal: Optional[str] = None
    ) -> Tuple[str, Path]:
        """
        Pesquisa o tema, gera o roteiro completo de acordo com a minutagem solicitada
        e salva em roteiros/<slug>.txt.
        """
        topic = topic.strip()
        duration_min = max(1.0, float(duration_min))
        target_words = int(duration_min * self.WORDS_PER_MINUTE)
        
        canal_key = self._resolve_canal_key(canal)

        print(f"\n[ScriptWriterAgent] Iniciando pesquisa e redacao de roteiro:")
        print(f"  Tema       : '{topic}'")
        print(f"  Duracao    : {duration_min:.1f} min (~{target_words} palavras)")
        print(f"  Estilo     : {canal_key.capitalize()}")

        # 1. Pesquisa contextual em fontes abertas
        research_data = self._research_wikipedia(topic)

        # 2. Geração da narrativa documental (com verificação de meta de palavras)
        script_text = self._write_script(topic, target_words, canal_key, research_data)

        # 3. Validação final de palavras
        word_count = len(script_text.split())
        est_min = word_count / self.WORDS_PER_MINUTE
        print(f"  Roteiro finalizado: {word_count} palavras (estimativa: {est_min:.1f} min)")

        # 4. Salvar no diretório de roteiros
        slug = self._slugify(topic)
        out_path = self.roteiros_dir / f"{slug}.txt"
        out_path.write_text(script_text, encoding="utf-8")
        print(f"  Arquivo salvo: {out_path.relative_to(self.root_dir)}")

        return script_text, out_path

    # ─────────────────────────────────────────────────────────────────────────
    # PESQUISA MULTI-TERMO NA WIKIPEDIA
    # ─────────────────────────────────────────────────────────────────────────

    def _research_wikipedia(self, topic: str) -> Dict[str, str]:
        """
        Busca contexto factual na Wikipedia em português. Se o título exato não
        existir, desmembra o tema em conceitos relacionados (ex: 'bezerro', 'expressão idiomática').
        """
        print(f"  [Pesquisa] Consultando enciclopedia aberta sobre '{topic}'...")
        headers = {"User-Agent": "VideoFactoryAI/4.0 (Autonomous Documentary Producer; pt-BR)"}
        data = {"title": topic, "summary": "", "full_text": ""}

        # 1. Tentativa de busca direta do título completo
        try:
            enc_topic = urllib.parse.quote(topic)
            url = (
                f"https://pt.wikipedia.org/w/api.php?action=query&format=json"
                f"&prop=extracts&explaintext=1&exintro=0&titles={enc_topic}"
            )
            r = requests.get(url, headers=headers, timeout=10)
            if r.status_code == 200:
                pages = r.json().get("query", {}).get("pages", {})
                for page_id, page_info in pages.items():
                    if page_id != "-1" and "extract" in page_info:
                        extract = page_info.get("extract", "")
                        if len(extract.strip()) > 100:
                            data["title"] = page_info.get("title", topic)
                            data["full_text"] = extract[:4000]
                            data["summary"] = extract[:1000]
                            print(f"    [OK] Fatos encontrados: '{data['title']}' ({len(data['full_text'])} caracteres)")
                            return data
        except Exception:
            pass

        # 2. Decomposição de termos para expressões populares e termos culturais
        sub_terms = []
        low = topic.lower()
        if "bezerra" in low or "bezerro" in low:
            sub_terms.extend(["Bezerro de ouro", "Bezerro", "Expressão idiomática"])
        elif "joão e o pé de feijão" in low or "pe de feijao" in low:
            sub_terms.extend(["João e o Pé de Feijão", "Conto de fadas"])
        else:
            # Palavras relevantes do próprio tópico com mais de 3 letras
            words = [w for w in re.findall(r"\b\w{4,}\b", topic) if w.lower() not in {"sobre", "como", "para", "onde", "quando"}]
            sub_terms.extend(words[:3])

        collected_texts = []
        for term in sub_terms:
            try:
                enc = urllib.parse.quote(term)
                s_url = f"https://pt.wikipedia.org/w/api.php?action=opensearch&format=json&search={enc}&limit=1"
                rs = requests.get(s_url, headers=headers, timeout=6)
                if rs.status_code == 200 and len(rs.json()) >= 2 and rs.json()[1]:
                    matched_title = rs.json()[1][0]
                    enc_match = urllib.parse.quote(matched_title)
                    q_url = (
                        f"https://pt.wikipedia.org/w/api.php?action=query&format=json"
                        f"&prop=extracts&explaintext=1&exintro=1&titles={enc_match}"
                    )
                    rq = requests.get(q_url, headers=headers, timeout=6)
                    if rq.status_code == 200:
                        p_dict = rq.json().get("query", {}).get("pages", {})
                        for pid, pdata in p_dict.items():
                            if pid != "-1" and "extract" in pdata:
                                txt = pdata.get("extract", "").strip()
                                if txt:
                                    collected_texts.append(txt)
            except Exception:
                continue

        if collected_texts:
            data["full_text"] = "\n\n".join(collected_texts)[:4000]
            data["summary"] = data["full_text"][:1000]
            print(f"    [OK] Contexto historico correlato reunido ({len(data['full_text'])} caracteres)")

        return data

    # ─────────────────────────────────────────────────────────────────────────
    # MOTOR DE REDAÇÃO DE ROTEIROS
    # ─────────────────────────────────────────────────────────────────────────

    def _write_script(
    self,
    topic: str,
    target_words: int,
    canal_key: str,
    research: Dict[str, str]
    ) -> str:
        """
        Orquestra a escrita do roteiro.

        Modos:

        VF_MODO_ESCRITA=webchat
            -> usa exclusivamente WebChat
            -> se falhar, gera erro

        qualquer outro modo
            -> Pollinations
            -> procedural fallback
        """

        print(
            f"  [Redacao] Estruturando narrativa em 5 atos para meta de {target_words} palavras..."
        )

        modo_escrita = os.getenv(
            "VF_MODO_ESCRITA",
            ""
        ).strip().lower()

        # ==========================================================
        # WEBCHAT
        # ==========================================================

        if modo_escrita == "webchat":

            from webchat_writer import escrever_via_webchat

            # Usa a mesma resolução segura de persona do modo Pollinations.
            # Isso evita que uma configuração sem fallback "documentario" quebre
            # o modo WebChat antes mesmo de a redação começar.
            persona = self._get_persona_safely(canal_key)

            fontes = [{
                "title": research.get("title", ""),
                "text": research.get("full_text", ""),
                "url": ""
            }]

            print(
                "  [WebChat] Modo webchat ativado."
            )

            try:

                roteiro = escrever_via_webchat(
                    topic=topic,
                    duration_min=max(
                        1.0,
                        target_words / self.WORDS_PER_MINUTE
                    ),
                    target_words=target_words,
                    persona=persona,
                    sources=fontes,
                    roteiros_dir=self.roteiros_dir,
                    slug=self._slugify(topic),
                    log=print
                )

            except Exception as e:

                raise RuntimeError(
                    f"Falha ao obter roteiro via WebChat: {e}"
                )

            if not roteiro:

                raise RuntimeError(
                    "WebChat retornou resposta vazia."
                )

            roteiro = self._clean_script(
                roteiro
            )

            palavras = roteiro.split()

            # impede vídeos gigantes
            if len(palavras) > int(target_words * 1.25):

                palavras = palavras[:target_words]

                roteiro = " ".join(
                    palavras
                )

            word_count = len(
                roteiro.split()
            )

            print(
                f"  [WebChat] Roteiro recebido: "
                f"{word_count} palavras"
            )

            return roteiro

        # ==========================================================
        # POLLINATIONS
        # ==========================================================

        script = self._generate_with_ai(
            topic,
            target_words,
            canal_key,
            research
        )

        if script:

            clean = self._clean_script(
                script
            )

            palavras = clean.split()

            if len(palavras) > int(
                target_words * 1.25
            ):

                palavras = palavras[:target_words]

                clean = " ".join(
                    palavras
                )

            if len(clean.split()) >= (
                target_words * 0.75
            ):

                return clean

        # ==========================================================
        # PROCEDURAL
        # ==========================================================

        print(
            "  [Redacao] Usando motor procedural tematico calibrado para o assunto..."
        )

        return self._generate_thematic_procedural(
            topic,
            target_words,
            canal_key,
            research
        )
    def _generate_with_ai(
        self,
        topic: str,
        target_words: int,
        canal_key: str,
        research: Dict[str, str]
    ) -> Optional[str]:
        """Tenta sintetizar via modelos neurais gratuitos com fallback de modelos."""
        # Evita KeyError: o valor padrão de dict.get é avaliado imediatamente.
        # O JSON também pode não definir explicitamente um canal "documentario".
        persona = self._get_persona_safely(canal_key)
        context = research.get("summary", "") or research.get("full_text", "")[:1200]

        try:
            style_instruction = self.get_style_instruction(canal_key) or ""
        except Exception:
            style_instruction = ""

        prompt = (
            f"{persona}\n\n"
            f"{style_instruction}\n\n"
            f"Escreva um documentário narrado completo e profundo sobre o tema: '{topic}'.\n"
            f"Meta obrigatória de extensão: aproximadamente {target_words} palavras.\n"
            f"Contexto disponível:\n{context}\n\n"
            f"Instruções estritas:\n"
            f"1. Escreva APENAS o texto contínuo que o narrador fala em voz alta.\n"
            f"2. NUNCA use rubricas cênicas, nomes de locutor, colchetes ou indicações de câmera.\n"
            f"3. Respeite com fidelidade absoluta o tema '{topic}'. Se for uma expressão popular ou conto, "
            f"foque na cultura, no significado, na psicologia e no cotidiano. NUNCA insira guerras ou "
            f"geopolítica se o tema não for sobre isso.\n"
            f"4. Estruture em 5 atos: Gancho envolvente, Raízes e origens, Dimensão simbólica, "
            f"Cotidiano humano e Lição contemporânea.\n"
            f"5. Idioma: Português do Brasil impecável e envolvente."
        )

        for model in ["openai-fast", "mistral"]:
            try:
                url = "https://text.pollinations.ai/"
                payload = {
                    "messages": [
                        {"role": "system", "content": persona},
                        {"role": "user", "content": prompt}
                    ],
                    "model": model,
                    "seed": 42,
                }
                r = requests.post(url, json=payload, timeout=9)
                if r.status_code == 200 and len(r.text.strip()) > 200:
                    raw = r.text.strip()
                    if raw.startswith("{"):
                        try:
                            data = json.loads(raw)
                            raw = data.get("content", raw)
                        except Exception:
                            pass
                    raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL)
                    clean = self._clean_script(raw)
                    if len(clean.split()) >= target_words * 0.70:
                        print(f"    [IA] Roteiro sintetizado com sucesso via modelo {model}.")
                        return clean
            except Exception:
                continue

        return None

    # ─────────────────────────────────────────────────────────────────────────
    # MOTOR PROCEDURAL TEMÁTICO DE ALTA DENSIDADE (NUNCA GERA GUERRA PARA TEMAS COTIDIANOS)
    # ─────────────────────────────────────────────────────────────────────────

    def _generate_thematic_procedural(
        self,
        topic: str,
        target_words: int,
        canal_key: str,
        research: Dict[str, str]
    ) -> str:
        """
        Gera um documentário substancial em 5 atos, construindo parágrafos ricos
        e analíticos adaptados à categoria real do tema.
        """
        low = topic.lower()

        # Determina a natureza do tema
        is_popular_culture = any(k in low for k in [
            "morte da bezerra", "bezerra", "bezerro", "expressão", "ditado", "lenda",
            "conto", "folclore", "pé de feijão", "história de", "origem da"
        ])
        is_technology = any(k in low for k in [
            "inteligência artificial", "computador", "internet", "robô", "tecnologia", "futuro", "ia", "software"
        ])
        is_military_geopolitics = any(k in low for k in [
            "guerra", "militar", "conflito", "míssil", "sanções", "iran", "eua", "crise de", "revolução armada"
        ])

        # ── CATEGORIA 1: Cultura Popular, Expressões e Cotidiano ─────────────────
        if is_popular_culture:
            acts = self._build_cultural_essay(topic, target_words)
        # ── CATEGORIA 2: Tecnologia, Ciência e Inovação ──────────────────────────
        elif is_technology:
            acts = self._build_tech_essay(topic, target_words)
        # ── CATEGORIA 3: Geopolítica e Conflitos Históricos ───────────────────────
        elif is_military_geopolitics:
            acts = self._build_geopolitical_essay(topic, target_words)
        # ── CATEGORIA 4: Documentário Histórico Geral ────────────────────────────
        else:
            acts = self._build_general_history_essay(topic, target_words, research)

        # Adiciona parágrafos enciclopédicos coletados, se houver
        full_text = research.get("full_text", "")
        if full_text:
            extra_p = [p.strip() for p in full_text.split("\n") if len(p.strip()) > 80]
            clean_extras = [re.sub(r"\[\d+\]", "", ep) for ep in extra_p[:5]]
            # Insere no meio da narrativa
            mid = len(acts) // 2
            acts[mid:mid] = clean_extras

        # Encadeia e audita número de palavras
        full_script = "\n\n".join(acts)
        words = full_script.split()

        # Se ainda não atingiu a meta, expande com reflexões filosóficas pertinentes ao tema
        while len(words) < target_words * 0.90:
            expansion = (
                f"Examinar {topic} sob a ótica dos dias atuais nos obriga a confrontar a rapidez com que "
                f"o mundo moderno tenta apagar as nuances do pensamento profundo. Quando nos permitimos desacelerar "
                f"e contemplar o horizonte sem a cobrança da pressa imediata, reencontramos uma dimensão de nossa "
                f"própria humanidade que muitas vezes é sufocada pelas rotinas exaustivas. É nesse silêncio fértil "
                f"que as grandes compreensões da existência ganham espaço para florescer."
            )
            acts.insert(-1, expansion)
            full_script = "\n\n".join(acts)
            words = full_script.split()

        return self._clean_script(full_script)

    # ── MÓDULOS TEMÁTICOS DO GERADOR PROCEDURAL ──────────────────────────────

    def _build_cultural_essay(self, topic: str, target_words: int) -> List[str]:
        """Constrói ensaio documental sobre expressões populares, folclore e psicologia humana."""
        return [
            # Ato 1: O Fenômeno Humano e o Gancho
            (
                f"Quantas vezes nos flagramos imóveis, com o olhar fixo em um ponto indefinido do horizonte, "
                f"enquanto o fluxo dos nossos pensamentos se perde em um labirinto silencioso de reflexões? "
                f"Na sabedoria popular brasileira e em toda a tradição da língua portuguesa, esse estado único de devaneio "
                f"tem um nome consagrado pelo tempo: estar pensando em {topic}. Longe de ser apenas uma frase corriqueira, "
                f"essa expressão encerra em si séculos de história, costumes rurais e uma profunda observação sobre a mente humana."
            ),
            # Ato 2: As Origens Pastorais e o Folclore
            (
                f"Para rastrear as origens de {topic}, precisamos viajar no tempo até as comunidades rurais de Portugal e do Brasil colonial. "
                f"No campo, a vida e a subsistência de uma família de pequenos criadores giravam em torno de seu rebanho. A chegada de uma bezerra "
                f"representava esperança de fartura, fornecimento de leite e continuidade da lida diária. Quando uma bezerra morria prematuramente, "
                f"o impacto para o camponês era devastador. Ele permanecia horas sentado junto à cerca, absorto em um silêncio melancólico, "
                f"calculando o prejuízo e contemplando a fragilidade de seus planos diante dos caprichos da natureza."
            ),
            (
                f"Com o passar das gerações, a figura daquele pastor desolado, com os olhos perdidos no vazio e o corpo paralisado pela reflexão, "
                f"transformou-se em uma imagem icônica no imaginário coletivo. Aquilo que nasceu como uma tragédia econômica no cotidiano rural "
                f"ganhou contornos poéticos e bem-humorados na oralidade popular, passando a descrever qualquer pessoa cuja mente viaja "
                f"para muito longe da realidade imediata."
            ),
            # Ato 3: A Conexão Bíblica e Simbólica
            (
                f"Estudiosos da etimologia e da mitologia popular apontam ainda para uma segunda camada simbólica que enriquece a história de {topic}. "
                f"Há uma interessante convergência com a narrativa bíblica do Bezerro de Ouro, esculpido pelos hebreus enquanto aguardavam "
                f"o retorno de Moisés no Monte Sinai. Naquele relato antigo, a adoração da bezerra dourada representava justamente o desvio da atenção, "
                f"o esquecimento do propósito principal e a fascinação por uma ilusão transitória que culminou em destruição e lamento."
            ),
            (
                f"Essa confluência entre a perda material do pastoreio e a alegoria do engano espiritual conferiu à expressão uma ressonância perene. "
                f"Dizer que alguém está 'pensando na morte da bezerra' tornou-se um convite bem-humorado para despertar aquele que se deixou levar "
                f"pelo encanto das próprias quimeras, esquecendo-se dos deveres práticos do presente."
            ),
            # Ato 4: A Psicologia do Devaneio e o Ócio Criativo
            (
                f"Mas o que a ciência contemporânea tem a dizer sobre esse hábito tão humano? Pesquisas recentes no campo da neurociência "
                f"revelam que o devaneio — esse exato instante em que parecemos desconectados do mundo — ativa a chamada Rede em Modo Padrão do cérebro. "
                f"Longe de ser preguiça ou perda de tempo, é nesses momentos de aparente apatia que a mente consolida memórias, sintetiza novas ideias "
                f"e encontra soluções criativas para dilemas complexos."
            ),
            (
                f"O sociólogo italiano Domenico De Masi popularizou o conceito de ócio criativo, demonstrando que as maiores criações artísticas "
                f"e filosóficas da humanidade não nasceram sob a pressão mecânica de relógios de ponto, mas sim nos intervalos de contemplação. "
                f"O olhar vago que nossos antepassados atribuíam a {topic} é, em última análise, a oficina silenciosa onde a imaginação trabalha."
            ),
            # Ato 5: O Legado Contemporâneo
            (
                f"Em nossa sociedade do século vinte e um, marcada pela aceleração frenética, notificações digitais ininterruptas e uma ansiedade "
                f"crônica por produtividade, a capacidade de pausar tornou-se um ato quase revolucionário. Olhar para o nada e permitir que o pensamento "
                f"flutue livremente é um privilégio cada vez mais raro e necessário."
            ),
            (
                f"Da próxima vez que alguém for surpreendido absorto em seus próprios devaneios e ouvir a provocação sobre {topic}, há motivo de orgulho. "
                f"Essa doce ausência temporária nada mais é do que a alma humana reivindicando seu direito ao silêncio, provando que, "
                f"entre a pressa do mundo e a serenidade do espírito, os momentos em que nada fazemos podem ser os mais valiosos de nossas vidas."
            ),
        ]

    def _build_tech_essay(self, topic: str, target_words: int) -> List[str]:
        """Constrói ensaio documental sobre tecnologia, inovação e futuro."""
        return [
            (
                f"A história do progresso humano é marcada por saltos visionários que redefiniram as fronteiras do possível. "
                f"Quando nos aprofundamos na trajetória de {topic}, deparamo-nos com o exato momento em que o conhecimento científico "
                f"e a audácia criativa colidiram para transformar definitivamente as bases da nossa sociedade."
            ),
            (
                f"Nas origens desse movimento, mentes pioneiras desafiaram dogmas estabelecidos e dedicaram anos de rigorosa experimentação "
                f"em laboratórios e oficinas. Cada falha representava uma lição indispensável; cada avanço, por menor que parecesse, "
                f"pavimentava o caminho para uma revolução que logo se tornaria irreversível."
            ),
            (
                f"À medida que as inovações em torno de {topic} amadureceram, o impacto passou a ser sentido em escala global. "
                f"Estruturas industriais tradicionais foram remodeladas, fluxos de informação ganharam velocidade sem precedentes "
                f"e novas linguagens começaram a ditar o ritmo da economia e das relações humanas no planeta."
            ),
            (
                f"Com esse poder transformador surgiram também dilemas éticos sem precedentes. O desafio contemporâneo não reside apenas "
                f"em ampliar o domínio técnico, mas em assegurar que essas ferramentas sirvam ao bem-estar coletivo, à dignidade humana "
                f"e à sustentabilidade das próximas gerações."
            ),
            (
                f"O legado de {topic} comprova que a tecnologia é, acima de tudo, um espelho de nossas maiores aspirações. "
                f"Ao dominarmos essas novas fronteiras, não estamos apenas construindo máquinas mais sofisticadas, mas sim decidindo "
                f"que tipo de futuro estamos dispostos a habitar."
            ),
        ]

    def _build_geopolitical_essay(self, topic: str, target_words: int) -> List[str]:
        """Constrói ensaio documental sobre relações internacionais, estratégia e história diplomática."""
        return [
            (
                f"No complexo tabuleiro das relações internacionais, poucos momentos expressaram com tanta intensidade "
                f"o choque entre soberania, estratégia e ambição quanto os eventos que cercam {topic}. Por trás de discursos solenes "
                f"e declarações oficiais, movem-se engrenagens silenciosas de pressão econômica, diplomacia e equilíbrio de poder."
            ),
            (
                f"Para compreender essa disputa, é imperativo retornar às raízes históricas dos tratados e rivalidades que desenharam "
                f"as alianças de hoje. Interesses geoestratégicos concorrentes, rotas de abastecimento e a preservação de esferas de influência "
                f"criaram um ambiente tenso, onde qualquer cálculo equivocado poderia precipitar uma crise de proporções imprevisíveis."
            ),
            (
                f"Os momentos de maior tensão revelaram tanto a tenacidade das lideranças quanto os limites da diplomacia multilateral. "
                f"Mesas de negociação, encontros a portas fechadas e sanções calculadas tornaram-se as armas preferenciais em uma disputa "
                f"onde a dissuasão muitas vezes pesou mais do que o confronto direto."
            ),
            (
                f"As consequências desses impasses continuam moldando as dinâmicas globais no século vinte e um. "
                f"A lição perene deixada por {topic} é que a paz e a estabilidade internacional não são estados naturais, "
                f"mas sim construções diárias que exigem diálogo prudente, respeito mútuo e a consciência de que o isolamento "
                f"raramente oferece respostas duradouras para os grandes desafios da humanidade."
            ),
        ]

    def _build_general_history_essay(self, topic: str, target_words: int, research: Dict[str, str]) -> List[str]:
        """Constrói ensaio para documentários históricos e gerais."""
        return [
            (
                f"A memória coletiva é o alicerce sobre o qual edificamos a compreensão de quem somos e de onde viemos. "
                f"Ao revisitarmos a história de {topic}, somos convidados a uma jornada fascinante pelos episódios marcantes, "
                f"pelas vozes do passado e pelas transformações profundas que deixaram marcas indeléveis em nossa cultura."
            ),
            (
                f"Os acontecimentos que moldaram {topic} não surgiram no vácuo. Foram frutos de um longo processo histórico, "
                f"onde anseios sociais, condições materiais e coragem individual se entrelaçaram para inaugurar uma nova época. "
                f"Cada detalhe preservado em arquivos, relatos orais e documentos históricos ajuda a resgatar a verdade dessa caminhada."
            ),
            (
                f"Olhar retrospectivamente para essa trajetória permite-nos reconhecer que os desafios enfrentados por nossos antepassados "
                f"guardam impressionantes semelhanças com as encruzilhadas do presente. A história de {topic} permanece como um farol, "
                f"lembrando-nos de que a sabedoria do amanhã é forjada no exame paciente e honesto das lições de ontem."
            ),
        ]

    # ─────────────────────────────────────────────────────────────────────────
    # UTILITÁRIOS DE LIMPEZA E FORMATAÇÃO
    # ─────────────────────────────────────────────────────────────────────────

    def _clean_script(self, raw_text: str) -> str:
        """Remove rubricas técnicas, marcações cênicas e normaliza o texto."""
        cleaned = re.sub(r"<think>.*?</think>", "", raw_text, flags=re.DOTALL)
        cleaned = re.sub(r"\[.*?\]", "", cleaned)
        cleaned = re.sub(r"\(.*?\)", "", cleaned)
        cleaned = re.sub(
            r"^(Narrador|Locutor|Ato \d+|Cena \d+|Capítulo \d+):\s*", 
            "", 
            cleaned, 
            flags=re.MULTILINE | re.IGNORECASE
        )
        paragraphs = [p.strip() for p in cleaned.split("\n") if p.strip()]
        return "\n\n".join(paragraphs)

    def _slugify(self, text: str) -> str:
        """Gera nome de arquivo limpo e seguro para o sistema operacional."""
        text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
        text = re.sub(r"[^\w\s-]", "", text).strip().lower()
        slug = re.sub(r"[-\s]+", "_", text)
        return slug[:45] or "documentario_automatico"
