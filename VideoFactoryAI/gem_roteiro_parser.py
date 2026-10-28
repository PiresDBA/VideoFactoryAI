# -*- coding: utf-8 -*-
"""
Parser para saída do Gem @roteiroparavideos (Gemini personalizado).

O Gem gera um roteiro em 2 partes:
  PARTE 1: Estrutura de cenas (timestamps, visual, duração)
  PARTE 2: Texto único de narração (locução completa)

Este módulo extrai ambas as partes e as converte no formato que o
pipeline do VideoFactoryAI espera.
"""

import re
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass, field


@dataclass
class CenaGem:
    """Representa uma cena extraída da PARTE 1 do Gem."""
    inicio: str          # "00:00"
    fim: str             # "00:30"
    titulo: str          # "Gancho Inicial"
    visual: str          # Descrição do que aparece na tela
    duracao_seg: int     # Duração em segundos
    duracao_txt: str     # "30 segundos" ou "1 minuto e 30 segundos"
    
    def duracao_float(self) -> float:
        """Retorna duração em segundos como float."""
        return float(self.duracao_seg)


@dataclass
class RoteiroGem:
    """Roteiro completo extraído do Gem."""
    titulo: str                          # Título do vídeo
    cenas: List[CenaGem] = field(default_factory=list)  # PARTE 1
    narracao: str = ""                   # PARTE 2 (texto puro para TTS)
    narracao_completa: str = ""          # Narração + CTA final
    
    @property
    def narracao_para_tts(self) -> str:
        """Texto limpo para TTS (sem marcadores, sem CTA)."""
        return self.narracao.strip()
    
    @property
    def narracao_com_cta(self) -> str:
        """Narração completa incluindo CTA/final."""
        return self.narracao_completa.strip()
    
    @property
    def duracao_total_seg(self) -> float:
        """Duração total em segundos."""
        return sum(c.duracao_seg for c in self.cenas)
    
    @property
    def duracao_total_min(self) -> float:
        """Duração total em minutos."""
        return self.duracao_total_seg / 60.0


def _parse_duracao(txt: str) -> int:
    """
    Converte duração em texto para segundos.
    Exemplos:
      "30 segundos" → 30
      "1 minuto e 30 segundos" → 90
      "2 minutos" → 120
      "1 min" → 60
    """
    txt = txt.lower().strip()
    segundos = 0
    
    # Procura minutos
    m_min = re.search(r'(\d+)\s*min', txt)
    if m_min:
        segundos += int(m_min.group(1)) * 60
    
    # Procura segundos
    m_seg = re.search(r'(\d+)\s*seg', txt)
    if m_seg:
        segundos += int(m_seg.group(1))
    
    # Se não encontrou nada mas tem número, assume segundos
    if segundos == 0:
        m_num = re.search(r'(\d+)', txt)
        if m_num:
            segundos = int(m_num.group(1))
    
    return segundos


def _extrair_titulo(texto: str) -> str:
    """Extrai o título do vídeo da primeira linha."""
    linhas = texto.strip().split('\n')
    for linha in linhas[:5]:
        linha = linha.strip()
        # Procura padrões como "Roteiro para Vídeo: TÍTULO"
        m = re.search(r'(?:roteiro\s+para\s+v[íi]deo\s*(?:do\s+youtube\s*)?:\s*)(.+)', linha, re.I)
        if m:
            return m.group(1).strip()
        # Se a linha não é uma instrução e tem conteúdo substancial
        if linha and not re.match(r'^(parte|@|##|#)', linha, re.I) and len(linha) > 10:
            return linha
    return "Sem título"


def _extrair_cenas(texto: str) -> List[CenaGem]:
    """
    Extrai as cenas da PARTE 1.
    
    Padrão esperado:
      00:00 - 00:30 | Gancho Inicial
      [VISUAL]: Descrição...
      [DURAÇÃO]: 30 segundos
    """
    cenas = []
    
    # Divide por seções de cena (linhas com timestamp)
    # Padrão: HH:MM - HH:MM | Título
    padrao_cena = re.compile(
        r'(\d{1,2}:\d{2})\s*[-–—]\s*(\d{1,2}:\d{2})\s*\|\s*(.+)',
        re.MULTILINE
    )
    
    matches = list(padrao_cena.finditer(texto))
    
    for i, match in enumerate(matches):
        inicio = match.group(1)
        fim = match.group(2)
        titulo = match.group(3).strip()
        
        # Pega o texto desta cena (até a próxima cena ou fim)
        inicio_pos = match.end()
        fim_pos = matches[i+1].start() if i+1 < len(matches) else len(texto)
        texto_cena = texto[inicio_pos:fim_pos]
        
        # Extrai [VISUAL]
        visual = ""
        # O visual termina na próxima tag, numa linha em branco ou no cabeçalho da PARTE 2;
        # antes, sem colchete depois, ele engolia a narração inteira.
        m_visual = re.search(
            r'\[VISUAL\]\s*:?\s*(.+?)(?=\n\s*\[|\n\s*\n|\n\s*PARTE\b|\Z)',
            texto_cena, re.DOTALL | re.I,
        )
        if m_visual:
            visual = m_visual.group(1).strip()
        
        # Extrai [DURAÇÃO]
        duracao_txt = ""
        duracao_seg = 0
        m_dur = re.search(r'\[DURA[ÇC][ÃA]O\]\s*:?\s*(.+?)(?=\n|$)', texto_cena, re.I)
        if m_dur:
            duracao_txt = m_dur.group(1).strip()
            duracao_seg = _parse_duracao(duracao_txt)
        
        # Se não achou duração, calcula pelo timestamp
        if duracao_seg == 0:
            try:
                h1, m1 = map(int, inicio.split(':'))
                h2, m2 = map(int, fim.split(':'))
                duracao_seg = (h2 * 60 + m2) - (h1 * 60 + m1)
                duracao_txt = f"{duracao_seg} segundos"
            except:
                duracao_seg = 30
                duracao_txt = "30 segundos"
        
        cenas.append(CenaGem(
            inicio=inicio,
            fim=fim,
            titulo=titulo,
            visual=visual,
            duracao_seg=duracao_seg,
            duracao_txt=duracao_txt
        ))
    
    return cenas


def _extrair_narracao(texto: str) -> Tuple[str, str]:
    """
    Extrai a PARTE 2 (narração).
    
    Retorna: (narracao_principal, narracao_completa)
    - narracao_principal: texto sem o CTA final
    - narracao_completa: texto incluindo CTA
    """
    # Procura "PARTE 2" ou "TEXTO ÚNICO DE NARRAÇÃO" ou "NARRAÇÃO"
    padrao_parte2 = re.compile(
        r'(?:PARTE\s*2|TEXTO\s*[ÚU]NICO\s*DE\s*NARRA[ÇC][ÃA]O|'
        r'NARRA[ÇC][ÃA]O|LOCU[ÇC][ÃA]O|TEXTO\s*DA\s*NARRA[ÇC][ÃA]O)\s*'
        r'(?:\(.*?\))?\s*:?\s*\n',
        re.I
    )
    
    m = padrao_parte2.search(texto)
    if not m:
        # Se não achou marcador, tenta pegar tudo depois da última cena
        # Procura última linha de duração
        matches_dur = list(re.finditer(r'\[DURA[ÇC][ÃA]O\]\s*:?\s*.+', texto, re.I))
        if matches_dur:
            pos = matches_dur[-1].end()
            narracao = texto[pos:].strip()
        else:
            narracao = texto
    else:
        narracao = texto[m.end():].strip()
    
    # Remove marcadores residuais
    narracao = re.sub(r'^\[.*?\]\s*:?\s*', '', narracao, flags=re.MULTILINE)
    
    # Detecta CTA final (frases com "like", "inscreva", "siga", "FUI")
    padrao_cta = re.compile(
        r'(?:Se voc[êe]\s+gostou|Deixe\s+seu\s+like|'
        r'[Ii]nscreva-se|se\s+inscreva|'
        r'Siga\s+o\s+canal|nos\s+siga|'
        r'Fortale[çc]a\s+nosso\s+canal|'
        r'^FUI\s*[!.]*$)',
        re.MULTILINE | re.IGNORECASE
    )
    
    m_cta = padrao_cta.search(narracao)
    if m_cta:
        # Encontrou CTA - separa
        narracao_principal = narracao[:m_cta.start()].strip()
        narracao_completa = narracao
    else:
        narracao_principal = narracao
        narracao_completa = narracao
    
    return narracao_principal, narracao_completa


def parse_gem_output(texto: str) -> RoteiroGem:
    """
    Faz o parse completo da saída do Gem @roteiroparavideos.
    
    Args:
        texto: Texto bruto retornado pelo Gem
        
    Returns:
        RoteiroGem com cenas e narração extraídas
    """
    # Limpa UI lixo
    texto = re.sub(r'\n{3,}', '\n\n', texto)  # Reduce 3+ newlines to 2
    
    # Extrai título
    titulo = _extrair_titulo(texto)
    
    # Extrai cenas (PARTE 1)
    cenas = _extrair_cenas(texto)
    
    # Extrai narração (PARTE 2)
    narracao, narracao_completa = _extrair_narracao(texto)
    
    return RoteiroGem(
        titulo=titulo,
        cenas=cenas,
        narracao=narracao,
        narracao_completa=narracao_completa
    )


def gem_para_cenas_pipeline(roteiro_gem: RoteiroGem, topic: str) -> List[Dict]:
    """
    Converte as cenas do Gem para o formato que o pipeline espera.
    
    O pipeline (plan_scenes) gera algo como:
    {
        "idx": 0,
        "texto": "texto narrado desta cena",
        "duracao": 12.5,
        "tipo": "imagem" ou "video",
        "query": "query de busca para mídia",
        "ai_prompt": "prompt para gerador de imagem"
    }
    
    Aqui mapeamos as cenas do Gem para esse formato.
    """
    cenas_pipeline = []
    
    # Distribui a narração entre as cenas proporcionalmente
    narracao = roteiro_gem.narracao_para_tts
    palavras = narracao.split()
    total_palavras = len(palavras)
    
    if roteiro_gem.cenas:
        # Calcula proporção de palavras por cena baseado na duração
        duracao_total = roteiro_gem.duracao_total_seg
        if duracao_total == 0:
            duracao_total = sum(c.duracao_seg for c in roteiro_gem.cenas)
        
        pos_palavra = 0
        for i, cena in enumerate(roteiro_gem.cenas):
            # Proporção de palavras baseada na duração
            proporcao = cena.duracao_seg / duracao_total if duracao_total > 0 else 1.0 / len(roteiro_gem.cenas)
            n_palavras = int(total_palavras * proporcao)
            
            # Extrai trecho da narração
            inicio_palavra = pos_palavra
            fim_palavra = min(pos_palavra + n_palavras, total_palavras)
            texto_cena = ' '.join(palavras[inicio_palavra:fim_palavra])
            
            # Se é a última cena, pega o resto
            if i == len(roteiro_gem.cenas) - 1:
                texto_cena = ' '.join(palavras[pos_palavra:])
            
            pos_palavra = fim_palavra
            
            # Gera query de busca baseada no visual e título
            query = f"{topic} {cena.titulo}"
            if cena.visual:
                # Usa primeiras palavras do visual como query
                visual_palavras = cena.visual.split()[:10]
                query = f"{topic} {' '.join(visual_palavras)}"
            
            # ai_prompt é derivado do visual (o que deve aparecer na tela)
            ai_prompt = cena.visual if cena.visual else f"{topic}, {cena.titulo}"
            
            cenas_pipeline.append({
                "idx": i,
                "texto": texto_cena,
                "duracao": cena.duracao_seg,
                "tipo": "imagem",  # Default, pode ser ajustado
                "query": query[:200],  # Limita tamanho
                "ai_prompt": ai_prompt[:500],
                "titulo_cena": cena.titulo,
                "timestamp": f"{cena.inicio}-{cena.fim}"
            })
    
    return cenas_pipeline


def validar_roteiro_gem(roteiro_gem: RoteiroGem, min_palavras: int = 0) -> Tuple[bool, str]:
    """
    Valida se o roteiro do Gem é aceitável.
    
    Returns:
        (True, mensagem) se válido
        (False, mensagem) se inválido
    """
    narracao = roteiro_gem.narracao_para_tts
    palavras = narracao.split()
    wc = len(palavras)
    
    if wc == 0:
        return False, "Narração vazia"
    
    if min_palavras > 0 and wc < min_palavras:
        return False, f"Narração com {wc} palavras (mínimo {min_palavras})"
    
    if len(roteiro_gem.cenas) == 0:
        return False, "Nenhuma cena extraída da PARTE 1"
    
    # Verifica se tem pelo menos 2 cenas
    if len(roteiro_gem.cenas) < 2:
        return False, f"Apenas {len(roteiro_gem.cenas)} cena(s) extraída(s) (mínimo 2)"
    
    # Verifica anti-alucinação básica
    lower = narracao.lower()
    red_flags = [
        "segundo a wikipedia", "conforme a fonte", "de acordo com o texto",
        "a fonte diz", "o texto menciona", "[fonte", "[1]", "[2]",
        "referência:", "citado em"
    ]
    for flag in red_flags:
        if flag in lower:
            return False, f"Violação anti-alucinação: contém '{flag}'"
    
    return True, f"OK: {wc} palavras, {len(roteiro_gem.cenas)} cenas, {roteiro_gem.duracao_total_min:.1f} min"
