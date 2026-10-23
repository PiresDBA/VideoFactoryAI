"""
===============================================================================
 VideoFactoryAI — Módulo: ScriptWriterAgent (Roteirista e Pesquisador Autônomo)
===============================================================================
 Este módulo implementa o agente autônomo responsável por pesquisar fatos históricos
 e redigir roteiros documentais completos sem intervenção humana.

 COMO FUNCIONA:
 1. O usuário fornece apenas um tema (ex: "A Guerra Fria") e a duração (ex: 8 min).
 2. O agente calcula a meta de palavras necessária (~135 palavras por minuto).
 3. O agente consulta fontes enciclopédicas abertas (Wikipedia PT-BR) de forma gratuita.
 4. O agente estrutura uma narrativa cinematográfica clássica em 5 Atos Documentais:
      - Ato 1: Gancho Dramático e Ruptura (Hook & Inciting Incident)
      - Ato 2: As Origens Históricas e o Cenário (Context & Genesis)
      - Ato 3: A Escalada e os Pontos de Virada (Climax & Turning Points)
      - Ato 4: As Consequências e o Desfecho (Aftermath & Resolution)
      - Ato 5: O Legado Contemporâneo (Legacy & Philosophical Reflection)
 5. Adapta o vocabulário e a persona conforme o canal escolhido (Geopolítica, História, etc.).
 6. Salva o roteiro pronto em 'roteiros/<tema>.txt' para ser usado pelo pipeline.

 COMO EXECUTAR ESTE AGENTE:
 
 Modo A: Diretamente pelo orquestrador principal (Recomendado):
     python VideoFactoryAI/agent.py --topic "A Guerra Fria" --duration 8 --channel historia

 Modo B: Importando em um script Python:
     from pathlib import Path
     from VideoFactoryAI.script_writer_agent import ScriptWriterAgent
     
     agent = ScriptWriterAgent(root_dir=Path("."))
     texto, caminho = agent.generate(topic="A Guerra Fria", duration_min=5, canal="historia")
     print(f"Roteiro gerado em: {caminho}")

 DEPENDÊNCIAS:
   - requests (requisições HTTP para a API da Wikipedia e API neural)
   - Nenhuma chave de API paga é necessária (100% gratuito e aberto)
===============================================================================
"""

# =============================================================================
# IMPORTAÇÃO DE BIBLIOTECAS DO SISTEMA
# =============================================================================
import os             # Manipulação de arquivos e caminhos no sistema operacional
import re             # Expressões regulares para sanitização e limpeza do roteiro
import json           # Decodificação de respostas JSON de APIs
import time           # Controle de tempos e pausas se necessário
import unicodedata    # Normalização de acentuação para criação de nomes de arquivos seguros
import urllib.parse   # Codificação de termos de busca em URLs seguras
import urllib.request # Módulo padrão de requisições de rede
import requests       # Cliente HTTP robusto para chamadas de API externas
from pathlib import Path  # Orientação a objetos para caminhos de diretórios e arquivos
from typing import Dict, List, Optional, Tuple  # Anotações de tipo estático para robustez


class ScriptWriterAgent:
    """
    Agente de Inteligência Artificial para Pesquisa Histórica e Redação Documental.
    
    Responsabilidades:
      - Determinar a cadência vocal e calcular o volume de texto por minuto.
      - Fazer pesquisa documental em enciclopédias abertas.
      - Orquestrar a geração neural com fallback procedural determinístico.
      - Limpar o texto de qualquer rubrica cênica para narração contínua e fluida.
    """

    # Cadência média de fala em documentários narrados em português do Brasil.
    # 135 palavras por minuto proporciona dicção clara, pausas dramáticas e tom solene.
    WORDS_PER_MINUTE = 135

    # Dicionário de personas por canal. Cada canal define o tom da narrativa:
    CANAL_PERSONAS = {
        # Canal Geopolítica: Foco em relações de poder, acordos de inteligência e sanções.
        "geopolitica": (
            "Você é um analista geopolítico e documentarista investigativo renomado. "
            "Seu tom é sóbrio, analítico, tenso e estratégico. Foque no equilíbrio de poder, "
            "serviços de inteligência, doutrinas militares, sanções, alianças e o impacto global."
        ),
        # Canal História: Foco em fatos solenes, datas, grandes decisões e épica humana.
        "historia": (
            "Você é um historiador e narrador de documentários épicos de prestígio internacional. "
            "Seu tom é solene, dramático, cronológico e focado nas grandes decisões humanas, "
            "discursos memoráveis e no peso das transformações históricas."
        ),
        # Canal Tecnologia: Foco em inovação, pioneirismo, disrupção e implicações futuras.
        "tecnologia": (
            "Você é um documentarista de ciência e tecnologia de vanguarda. "
            "Seu tom é moderno, ágil, visionário e preciso. Foque na corrida tecnológica, "
            "na inovação, nos pioneiros e nas implicações éticas e futuras das invenções."
        ),
        # Canal Documentário Geral: Jornalismo profundo de alto padrão internacional.
        "documentario": (
            "Você é um diretor e roteirista de documentários de alto padrão para cinema e TV. "
            "Seu tom é jornalístico, imparcial, profundo, cativante e de ritmo impecável."
        ),
    }

    def __init__(self, root_dir: Path):
        """
        Inicializa o agente roteirista.
        
        Parâmetros:
          root_dir (Path): Diretório raiz do projeto onde a pasta 'roteiros/' será criada.
        """
        self.root_dir = Path(root_dir)
        self.roteiros_dir = self.root_dir / "roteiros"
        
        # Garante a existência do diretório onde os roteiros gerados serão gravados
        self.roteiros_dir.mkdir(parents=True, exist_ok=True)

    # ─────────────────────────────────────────────────────────────────────────
    # MÉTODO PRINCIPAL DE GERAÇÃO (PONTO DE ENTRADA DO AGENTE)
    # ─────────────────────────────────────────────────────────────────────────

    def generate(
        self,
        topic: str,
        duration_min: float = 5.0,
        canal: Optional[str] = None
    ) -> Tuple[str, Path]:
        """
        Executa todo o ciclo de vida da criação do roteiro:
          1. Valida os parâmetros de entrada e calcula as palavras necessárias.
          2. Consulta a Wikipedia em português para obter contexto verídico.
          3. Redige o roteiro utilizando IA neural ou o motor procedural.
          4. Audita a contagem de palavras e calcula a duração estimada.
          5. Salva o texto pronto em 'roteiros/<slug_do_tema>.txt'.

        Parâmetros:
          topic (str): Assunto ou tema do documentário (ex: 'A Guerra Fria').
          duration_min (float): Duração pretendida do vídeo final em minutos (padrão: 5.0).
          canal (str, opcional): Estilo do canal ('geopolitica', 'historia', 'tecnologia', 'documentario').

        Retorna:
          Tuple[str, Path]: Texto completo da narração e caminho do arquivo salvo no disco.
        """
        # Sanitiza o texto do tema
        topic = topic.strip()
        
        # Assegura duração mínima de pelo menos 1 minuto para viabilidade documental
        duration_min = max(1.0, float(duration_min))
        
        # Calcula a meta de palavras proporcional à velocidade de narração
        target_words = int(duration_min * self.WORDS_PER_MINUTE)
        
        # Determina a chave canônica do canal
        canal_key = (canal or "documentario").lower().rstrip("s")
        if canal_key not in self.CANAL_PERSONAS:
            canal_key = "documentario"

        # Mensagens explicativas no console
        print(f"\n[ScriptWriterAgent] Iniciando pesquisa e redacao de documentario:")
        print(f"  Tema       : '{topic}'")
        print(f"  Duracao    : {duration_min:.1f} min (~{target_words} palavras)")
        print(f"  Estilo     : {canal_key.capitalize()}")

        # ETAPA 1: Pesquisa factual em fontes enciclopédicas abertas (Wikipedia PT-BR)
        research_data = self._research_wikipedia(topic)

        # ETAPA 2: Redação da narrativa documental em 5 Atos estruturados
        script_text = self._write_script(topic, target_words, canal_key, research_data)

        # ETAPA 3: Auditoria estatística do roteiro gerado
        word_count = len(script_text.split())
        est_min = word_count / self.WORDS_PER_MINUTE
        print(f"  Roteiro finalizado: {word_count} palavras (estimativa: {est_min:.1f} min)")

        # ETAPA 4: Salvamento persistente no disco
        slug = self._slugify(topic)
        out_path = self.roteiros_dir / f"{slug}.txt"
        out_path.write_text(script_text, encoding="utf-8")
        print(f"  Arquivo salvo: {out_path.relative_to(self.root_dir)}")

        return script_text, out_path

    # ─────────────────────────────────────────────────────────────────────────
    # PESQUISA ENCICLOPÉDICA ABERTA (WIKIPEDIA API GRATUITA)
    # ─────────────────────────────────────────────────────────────────────────

    def _research_wikipedia(self, topic: str) -> Dict[str, str]:
        """
        Consulta a API oficial da Wikipedia em língua portuguesa para extrair
        fatos históricos, contextos e parágrafos detalhados sobre o tema.
        
        Não necessita de token ou credencial privada. Respeita os padrões de
        User-Agent exigidos pela Wikimedia Foundation.

        Parâmetros:
          topic (str): Termo a pesquisar.

        Retorna:
          Dict[str, str]: Dicionário com 'title', 'summary' e 'full_text'.
        """
        print(f"  [Pesquisa] Consultando enciclopedia aberta sobre '{topic}'...")
        headers = {"User-Agent": "VideoFactoryAI/4.0 (Autonomous Documentary Producer; pt-BR)"}
        data = {"title": topic, "summary": "", "full_text": ""}

        try:
            # 1. Primeira tentativa: Busca pelo título direto exato
            enc_topic = urllib.parse.quote(topic)
            url = (
                f"https://pt.wikipedia.org/w/api.php?action=query&format=json"
                f"&prop=extracts&explaintext=1&exintro=0&titles={enc_topic}"
            )
            r = requests.get(url, headers=headers, timeout=12)
            if r.status_code == 200:
                pages = r.json().get("query", {}).get("pages", {})
                for page_id, page_info in pages.items():
                    # Se page_id != "-1", significa que a página existe e foi encontrada
                    if page_id != "-1" and "extract" in page_info:
                        data["title"] = page_info.get("title", topic)
                        extract = page_info.get("extract", "")
                        data["full_text"] = extract[:4000]
                        data["summary"] = extract[:1000]
                        print(f"    [OK] Fatos encontrados: '{data['title']}' ({len(data['full_text'])} caracteres)")
                        return data

            # 2. Segunda tentativa: Busca por similaridade semântica (OpenSearch) caso o termo exato falhe
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
            # Em caso de falha de conexão com a Wikipedia, o agente não interrompe a produção
            print(f"    [Aviso] Pesquisa online falhou ({e}). Usando motor heuristico.")

        return data

    # ─────────────────────────────────────────────────────────────────────────
    # MOTOR DE REDAÇÃO DE ROTEIROS (DUAL-ENGINE: IA NEURAL + PROCEDURAL)
    # ─────────────────────────────────────────────────────────────────────────

    def _write_script(
        self,
        topic: str,
        target_words: int,
        canal_key: str,
        research: Dict[str, str]
    ) -> str:
        """
        Orquestra a escrita do roteiro aplicando estratégia defensiva de dois níveis:
          1. Nível 1: IA Neural Aberta (Pollinations Text API) para síntese fluida.
          2. Nível 2 (Fallback): Motor documental procedural com 5 atos predefinidos.

        Parâmetros:
          topic (str): Tema do documentário.
          target_words (int): Quantidade de palavras almejada.
          canal_key (str): Canal escolhido para direcionar a persona.
          research (Dict): Contexto histórico extraído da pesquisa.

        Retorna:
          str: Roteiro limpo e pronto para narração contínua.
        """
        print(f"  [Redacao] Estruturando narrativa em 5 atos para {target_words} palavras...")

        # Tentativa primária: Geração por rede neural
        script = self._generate_with_ai(topic, target_words, canal_key, research)
        if script and len(script.split()) >= (target_words * 0.5):
            return self._clean_script(script)

        # Fallback de segurança: Motor procedural interno
        print("  [Redacao] Usando motor procedural documental de alta densidade...")
        return self._generate_procedural(topic, target_words, canal_key, research)

    def _generate_with_ai(
        self,
        topic: str,
        target_words: int,
        canal_key: str,
        research: Dict[str, str]
    ) -> Optional[str]:
        """
        Submete o prompt instrucional à API neural de texto.
        Garante que nenhuma marcação de cena seja gerada (apenas narração falada).
        """
        persona = self.CANAL_PERSONAS.get(canal_key, self.CANAL_PERSONAS["documentario"])
        context = research.get("summary", "") or research.get("full_text", "")[:1200]

        # Montagem do prompt com engenharia de instrução estrita
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
            # Timeout curto para não bloquear a produção caso a rede oscile
            r = requests.post(url, json=payload, timeout=14)
            if r.status_code == 200 and len(r.text.strip()) > 100:
                raw = r.text.strip()
                # Se a resposta vier em JSON estruturado, extrai o campo de texto
                if raw.startswith("{"):
                    try:
                        data = json.loads(raw)
                        content = data.get("content")
                        if content and isinstance(content, str):
                            raw = content
                    except Exception:
                        pass

                # Remove eventuais blocos de pensamento interno da IA (<think>...</think>)
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
        Motor procedural determinístico. Constrói uma narrativa cinematográfica
        em 5 atos combinando ganchos dramáticos específicos de cada canal, fatos
        enciclopédicos coletados e expansões históricas formais.
        """
        full_text = research.get("full_text", "")
        # Extrai os parágrafos mais densos e relevantes da pesquisa enciclopédica
        paragraphs = [p.strip() for p in full_text.split("\n") if len(p.strip()) > 100]

        # ATO 1: Ganchos dramáticos introdutórios calibrados por nicho de canal
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

        # ATO 5: Desfechos e reflexões solenes de encerramento por nicho de canal
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
        
        # Insere o gancho inicial (Ato 1)
        body_parts.append(hooks.get(canal_key, hooks["documentario"]))
        current_words = len(body_parts[0].split())

        # Insere os fatos enciclopédicos coletados (Atos 2 e 3)
        if paragraphs:
            for p in paragraphs:
                if current_words >= target_words - 80:
                    break
                # Remove citações de referências da Wikipedia como [1], [2], etc.
                clean_p = re.sub(r"\[\d+\]", "", p).strip()
                if len(clean_p) > 50:
                    body_parts.append(clean_p)
                    current_words += len(clean_p.split())

        # ATOS 3 e 4: Expansão narrativa caso o texto ainda não tenha atingido a extensão necessária
        if current_words < target_words * 0.7:
            expansions = [
                (
                    f"Para compreender a verdadeira magnitude de {topic}, é preciso recuar até as raízes que alimentaram "
                    f"esse movimento. As tensões acumuladas ao longo de anos criaram um terreno fértil para que a disputa se aprofundasse, "
                    f"envolvendo atores decisivos cujas ações ecoaram por continentes inteiros."
                ),
                (
                    f"À medida que as semanas se transformavam em meses, a escalada tornou-se inevitável. Em gabinetes fechados e bases estratégicas, "
                    f"cada relatório de inteligência era examinado minuciosamente. Decisões tomadas sob extrema pressão revelaram "
                    f"tanto a fragilidade dos acordos diplomáticos quanto a intransigência de lideranças dispostas a arriscar tudo por sua hegemonia."
                ),
                (
                    f"O clímax desse embate marcou uma virada definitiva. Novas fronteiras foram traçadas, alianças foram testadas ao limite "
                    f"e a população acompanhou com apreensão o desenrolar de uma disputa onde o menor erro de cálculo poderia resultar "
                    f"em catástrofe irreversível."
                ),
                (
                    f"A resolução desse impasse exigiu concessões dolorosas e diplomacia de bastidores. Tratados secretos, canais de comunicação de emergência "
                    f"e o recuo estratégico de forças militares permitiram que a crise encontrasse um desfecho, ainda que temporário, "
                    f"redesenhando para sempre as regras do jogo internacional."
                ),
            ]
            for exp in expansions:
                if current_words >= target_words - 80:
                    break
                body_parts.append(exp)
                current_words += len(exp.split())

        # Insere o desfecho solene (Ato 5)
        body_parts.append(outros.get(canal_key, outros["documentario"]))

        script = "\n\n".join(body_parts)
        return self._clean_script(script)

    # ─────────────────────────────────────────────────────────────────────────
    # SANITIZAÇÃO, LIMPEZA E PADRONIZAÇÃO DE TEXTO
    # ─────────────────────────────────────────────────────────────────────────

    def _clean_script(self, raw_text: str) -> str:
        """
        Higieniza o texto bruto gerado, eliminando:
          - Blocos de raciocínio de modelos neurais (<think>...</think>).
          - Marcações de cena entre colchetes [ex: Câmera abre em plano geral].
          - Rubricas entre parênteses (ex: Narrador respira fundo).
          - Rótulos de atores como 'Narrador:', 'Locutor:', 'Ato 1:', etc.
          - Linhas em branco redundantes.

        Parâmetros:
          raw_text (str): Texto original com potenciais impurezas.

        Retorna:
          str: Texto pronto para ser vocalizado diretamente pelo Edge-TTS.
        """
        # Se veio como string JSON serializada com reasoning
        if raw_text.startswith("{") and "reasoning" in raw_text:
            matches = re.findall(r'"([^"\\]*(?:\\.[^"\\]*)*)"', raw_text)
            long_matches = [
                m for m in matches 
                if len(m) > 120 and not m.startswith("The user") and not m.startswith("We'll")
            ]
            if long_matches:
                raw_text = "\n\n".join(long_matches)

        # Remove blocos de reasoning
        cleaned = re.sub(r"<think>.*?</think>", "", raw_text, flags=re.DOTALL)
        
        # Remove colchetes com instruções técnicas [ex: música dramática]
        cleaned = re.sub(r"\[.*?\]", "", cleaned)
        
        # Remove parênteses com indicações (ex: pausa de 2 segundos)
        cleaned = re.sub(r"\(.*?\)", "", cleaned)
        
        # Remove identificadores no início de parágrafos
        cleaned = re.sub(
            r"^(Narrador|Locutor|Ato \d+|Cena \d+):\s*", 
            "", 
            cleaned, 
            flags=re.MULTILINE | re.IGNORECASE
        )

        # Remove quebras de linha múltiplas desnecessárias
        paragraphs = [p.strip() for p in cleaned.split("\n") if p.strip()]
        return "\n\n".join(paragraphs)

    def _slugify(self, text: str) -> str:
        """
        Converte uma string arbitrária em um identificador seguro para arquivos (slug).
        Remove acentos, caracteres especiais e substitui espaços por underscores.
        Exemplo: 'A Guerra Fria (1947–1991)' -> 'a_guerra_fria_19471991'

        Parâmetros:
          text (str): String com o título.

        Retorna:
          str: Nome de arquivo seguro e limpo em minúsculas.
        """
        # Remove diacríticos e acentuação gráfica
        text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
        # Mantém apenas caracteres alfanuméricos, espaços e hifens
        text = re.sub(r"[^\w\s-]", "", text).strip().lower()
        # Substitui espaços ou hifens repetidos por underscore único
        slug = re.sub(r"[-\s]+", "_", text)
        return slug[:45] or "documentario_automatico"
