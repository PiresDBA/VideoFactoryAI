"""
webchat_bridge.py - ponte entre o seu RAG local e web chats (ChatGPT, Gemini,
Claude, Copilot, Perplexity, DeepSeek), SEM API, via navegador (Playwright).
O sistema APRENDE cada site e se ajusta sozinho.

Instalação:
    pip install playwright requests
    playwright install chromium

Primeiros passos (uma vez por site):
    python webchat_bridge.py --login chatgpt      # você loga manualmente
    python webchat_bridge.py --calibrar chatgpt   # ele testa e aprende o site
    python webchat_bridge.py --calibrar todos
    python webchat_bridge.py --status             # o que ele aprendeu de cada um
    python webchat_ui.py                          # painel visual (opcional)

Uso no pipeline:
    from webchat_bridge import ask_web, converse, WebSession
    r = ask_web("Pergunta + trechos do RAG")                # uma pergunta
    r = converse("Pergunta", tools={"BUSCAR": minha_busca}) # bidirecional
    print(r["site"], r["answer"])

O que ele aprende e guarda em sites.json (campo "perfil" de cada site):
  - seletores: caixa de texto (por tela + modelo local), resposta (por
    diferença da página), botão "parar" (observando o que aparece enquanto
    o chat gera)
  - como enviar: botão ou Enter (verifica se a mensagem realmente saiu)
  - limite de tamanho do prompt (reduz sozinho se o site recusar)
  - qual formato de marcador o site consegue devolver ([[X: y]] ou @@X: y@@);
    se nenhum, usa modo "pré-busca" (busca antes e manda tudo numa mensagem)
  - estatísticas: sucesso, latência, falhas seguidas -> reordena os sites e
    coloca em "quarentena" o que está falhando
  - fecha banners/popups comuns e detecta tela de login

Validação humana (opcional, via painel webchat_ui.py):
    converse(..., validar="ambos")   # "envio" | "resposta" | "ambos"
  Antes de qualquer trecho dos seus documentos sair para a nuvem, e/ou antes
  da resposta entrar no pipeline, ele pausa e espera você aprovar, editar ou
  rejeitar no painel. Sem resposta no prazo = rejeitado (lado seguro).
"""
import argparse
import base64
import importlib
import json
import os
import random
import re
import string
import sys
import time
from pathlib import Path

import requests
from playwright.sync_api import sync_playwright

BASE = Path(__file__).parent
CFG_FILE = BASE / "sites.json"
PROFILES = BASE / "perfis"
SHOTS = BASE / "telas"
OLLAMA = os.getenv("OLLAMA_URL", "http://localhost:11434")
HEAL_MODEL = os.getenv("HEAL_MODEL", "gemma4-turbo-perfeito:latest")    # modelo que "olha" a tela
LOCAL_MODEL = os.getenv("LOCAL_MODEL", "gemma4-turbo-perfeito:latest")  # fallback final
MAX_RESULTADO = 12000  # caracteres devolvidos ao chat por ferramenta

# Seletores iniciais (melhor esforço: a autocura corrige quando mudarem)
DEFAULT_SITES = {
    "chatgpt": {
        "url": "https://chatgpt.com",
        "input": 'div#prompt-textarea, #prompt-textarea, div[contenteditable="true"][role="textbox"][aria-label^="Pergunte"], div[contenteditable="true"][role="textbox"]',
        "send": "button[data-testid='send-button']",
        "response": "[data-message-author-role='assistant']",
        "busy": "button[data-testid='stop-button']",
    },
    "gemini": {
        "url": "https://gemini.google.com/app",
        "input": "rich-textarea div[contenteditable='true']",
        "send": "button[aria-label*='Enviar'], button[aria-label*='Send']",
        "response": "message-content",
        "busy": "button[aria-label*='Parar'], button[aria-label*='Stop']",
    },
    "claude": {
        "url": "https://claude.ai/new",
        "input": "div[contenteditable='true']",
        "send": "button[aria-label*='Send'], button[aria-label*='Enviar']",
        "response": "div.font-claude-message",
        "busy": "button[aria-label*='Stop'], button[aria-label*='Parar']",
    },
    "copilot": {
        "url": "https://copilot.microsoft.com",
        "input": "textarea",
        "send": "button[aria-label*='Submit'], button[aria-label*='Enviar']",
        "response": "[data-content='ai-message']",
        "busy": "button[aria-label*='Stop'], button[aria-label*='Parar']",
    },
    "perplexity": {
        "url": "https://www.perplexity.ai",
        "input": "div[contenteditable='true'], textarea",
        "send": "button[aria-label*='Submit'], button[aria-label*='Enviar']",
        "response": "div[id^='markdown-content']",
        "busy": "",
    },
    "deepseek": {
        "url": "https://chat.deepseek.com",
        "input": "textarea",
        "send": "",
        "response": "div.ds-markdown",
        "busy": "",
    },
}

# O que o sistema aprende de cada site
PERFIL_PADRAO = {
    "estilo": None,        # formato de marcador que o site devolve bem
    "enter_send": None,    # True=Enter envia, False=botão envia, None=não sabe
    "max_chars": 20000,    # limite de prompt aprendido
    "ok": 0, "falhas": 0, "seguidas": 0,
    "lat": 0.0,            # latência média (s)
    "cooldown": 0,         # timestamp até quando o site fica em quarentena
}

# Formatos de marcador que o chat usa para pedir coisas ao sistema
ESTILOS = {
    "colchetes": {"fmt": "[[{n}: argumento]]",
                  "re": r"\[\[\s*([A-Za-z_]+)\s*:\s*(.+?)\s*\]\]"},
    "arroba": {"fmt": "@@{n}: argumento@@",
               "re": r"@@\s*([A-Za-z_]+)\s*:\s*(.+?)\s*@@"},
}

INPUT_Q = ('textarea,[contenteditable="true"],[contenteditable="plaintext-only"],'
           'input[type="text"]')
BTN_Q = 'button,[role="button"]'

JS_ELEMS = """
(q) => {
  const sel = el => {
    if (el.id) return '#' + CSS.escape(el.id);
    const t = el.getAttribute('data-testid');
    if (t) return el.tagName.toLowerCase() + '[data-testid="' + t + '"]';
    const a = el.getAttribute('aria-label');
    if (a) return el.tagName.toLowerCase() + '[aria-label="' + a + '"]';
    const parts = []; let e = el;
    while (e && e.nodeType === 1 && parts.length < 4) {
      const c = [...e.classList].slice(0, 2).map(x => '.' + CSS.escape(x)).join('');
      parts.unshift(e.tagName.toLowerCase() + c); e = e.parentElement;
    }
    return parts.join(' > ');
  };
  return [...document.querySelectorAll(q)].filter(e => e.getClientRects().length > 0)
    .slice(0, 60).map(e => ({
      sel: sel(e), tag: e.tagName.toLowerCase(),
      hint: (e.getAttribute('aria-label') || e.placeholder || e.innerText || '').trim().slice(0, 50)
    }));
}
"""

JS_LEARN_RESPONSE = """
([head, tail]) => {
  const els = [...document.querySelectorAll('body *')].filter(e => {
    const t = e.innerText || ''; return t.includes(head) && t.includes(tail);
  });
  if (!els.length) return null;
  const e = els[els.length - 1];   // o menor elemento que contém a resposta toda
  const cls = [...e.classList].slice(0, 2).map(x => '.' + CSS.escape(x)).join('');
  return e.tagName.toLowerCase() + cls;
}
"""

JS_POPUP = """
() => {
  const re = /^(aceitar tudo|aceitar|aceito|accept all|accept|i agree|concordo|entendi|got it|fechar|close|dismiss|dispensar|agora não|not now|continuar sem (fazer )?login|stay logged out|skip|pular)$/i;
  const b = [...document.querySelectorAll('button,[role="button"],a')].find(e =>
    e.getClientRects().length > 0 && re.test((e.innerText || e.getAttribute('aria-label') || '').trim()));
  if (b) { b.click(); return true; }
  return false;
}
"""


# ----------------------------------------------------------------- config
def _normalizar(cfg):
    for c in cfg.values():
        pf = c.setdefault("perfil", {})
        for k, v in PERFIL_PADRAO.items():
            pf.setdefault(k, v)
    return cfg


def load_cfg():
    if CFG_FILE.exists():
        cfg = json.loads(CFG_FILE.read_text(encoding="utf-8"))
        for k, v in DEFAULT_SITES.items():
            cfg.setdefault(k, json.loads(json.dumps(v)))
    else:
        cfg = json.loads(json.dumps(DEFAULT_SITES))
    # Migração: o ChatGPT deixou de usar o id #prompt-textarea sozinho. Atualiza o que já estava salvo.
    if "chatgpt" in cfg and cfg["chatgpt"].get("input") == "#prompt-textarea":
        cfg["chatgpt"]["input"] = DEFAULT_SITES["chatgpt"]["input"]
    _normalizar(cfg)
    save_cfg(cfg)
    return cfg


def save_cfg(cfg):
    CFG_FILE.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")


def ordenar(cfg, order=None):
    """Ordem de tentativa: melhores primeiro (taxa de sucesso e latência);
    sites em quarentena (falhas seguidas ou sem login) ficam de fora."""
    agora = time.time()
    nomes = [n for n in (order or cfg) if n in cfg and cfg[n].get("enabled", True)]
    ativos = [n for n in nomes if cfg[n]["perfil"]["cooldown"] <= agora]

    def score(n):
        pf = cfg[n]["perfil"]
        taxa = (pf["ok"] + 1) / (pf["ok"] + pf["falhas"] + 2)  # suavizada
        return taxa - min(pf["lat"], 120) / 400
    if order is None:
        ativos.sort(key=score, reverse=True)
    return ativos or nomes  # se todos estão em quarentena, tenta todos


# ------------------------------------------------------------------ Ollama
def _ollama(prompt, images=None, json_mode=False, model=None):
    msg = {"role": "user", "content": prompt}
    if images:
        msg["images"] = images
    body = {"model": model or LOCAL_MODEL, "messages": [msg], "stream": False}
    if json_mode:
        body["format"] = "json"
    r = requests.post(f"{OLLAMA}/api/chat", json=body, timeout=300)
    r.raise_for_status()
    return r.json()["message"]["content"]


def ask_local(prompt):
    return {"site": "local", "answer": _ollama(prompt)}


# ----------------------------------------------------------------- helpers
def ajustar_prompt(prompt, limite):
    """Se passar do limite aprendido do site, corta o miolo (mantém início e fim)."""
    if len(prompt) <= limite:
        return prompt
    corte = "\n[... trecho cortado por limite do site ...]\n"
    ini = int(limite * 0.3)
    fim = max(limite - ini - len(corte), 0)
    return prompt[:ini] + corte + (prompt[-fim:] if fim else "")


def achar_pedidos(resp, tools, estilo):
    """Extrai pedidos [(FERRAMENTA, argumento)] da resposta do chat.
    Tenta o formato exato; se o chat 'errou' o formato, tenta uma leitura
    tolerante (só em respostas curtas, para não confundir com a resposta final)."""
    estilo = estilo if estilo in ESTILOS else "colchetes"
    rx = re.compile(ESTILOS[estilo]["re"], re.S)
    achados = [(n.upper(), a.strip()) for n, a in rx.findall(resp) if n.upper() in tools]
    if achados or len(resp) > 600:
        return achados
    nomes = "|".join(re.escape(n) for n in tools)
    lx = re.compile(rf"^\W{{0,3}}({nomes})\s*[:：]\s*(.+?)\W{{0,3}}$", re.I | re.M)
    return [(n.upper(), a.strip(" *_`\"'")) for n, a in lx.findall(resp)]


# ------------------------------------------- validação humana (opcional)
# Modos suportados via VF_WEBCHAT_VALIDAR:
#   "nenhum" (padrão) - sem validação
#   "terminal"        - validação A/E/R/C direto no terminal (SEM painel visual)
#   "envio"           - valida antes de enviar
#   "resposta"        - valida após receber
#   "ambos"           - valida ambos
# O modo "terminal" substitui o antigo painel webchat_ui.py

# Cache para não repetir validação do mesmo texto
_VALIDACAO_CACHE: dict = {}


def _validar_terminal(tipo: str, texto: str, site: str, log=print) -> tuple[str, str]:
    """
    Validação interativa no terminal: A/E/R/C.
    Retorna (acao, texto_final) onde acao in {'aprovar', 'rejeitar'}.
    """
    # Chave de cache: hash do texto + tipo + site
    import hashlib
    cache_key = hashlib.md5(f"{tipo}:{site}:{texto}".encode()).hexdigest()[:16]
    if cache_key in _VALIDACAO_CACHE:
        cached = _VALIDACAO_CACHE[cache_key]
        log(f"[{site}] validação em cache: {cached[0]}")
        return cached

    # Exibe o conteúdo formatado (usa repr para evitar problemas de encoding)
    titulo = f" {tipo.upper()} DO {site.upper()} "
    print("\n" + "=" * 80)
    try:
        print(f"{titulo:=^80}")
    except UnicodeEncodeError:
        print(f"=== {titulo.strip()} ===")
    print("=" * 80)
    # Print seguro para encoding Windows
    try:
        print(texto)
    except UnicodeEncodeError:
        print(texto.encode('ascii', 'replace').decode('ascii'))
    print("=" * 80)

    # Contagem de palavras para referência
    n_palavras = len(texto.split())
    print(f"Palavras: {n_palavras}")

    while True:
        try:
            op = input(
                "\n[A]provar   [E]ditar   [R]egerar   [C]ancelar : "
            ).strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\nCancelado pelo usuário.")
            return "rejeitar", texto

        if op in ("", "a"):
            _VALIDACAO_CACHE[cache_key] = ("aprovar", texto)
            return "aprovar", texto

        if op == "e":
            print(
                "\nCole abaixo a versão final."
                "\nQuando terminar, digite ::fim em linha separada."
            )
            linhas = []
            while True:
                try:
                    linha = input()
                except (EOFError, KeyboardInterrupt):
                    print("\nEdição cancelada.")
                    break
                if linha.strip() == "::fim":
                    break
                linhas.append(linha)
            if linhas:
                texto_editado = "\n".join(linhas)
                print(f"Editado: {len(texto_editado.split())} palavras")
                texto = texto_editado
                # Re-exibe para confirmação
                print("\n--- Texto editado ---")
                try:
                    print(texto)
                except UnicodeEncodeError:
                    print(texto.encode('ascii', 'replace').decode('ascii'))
                print("---------------------")
                continue
            else:
                print("Nenhuma alteração feita.")
                continue

        if op == "r":
            return "rejeitar", texto

        if op == "c":
            raise KeyboardInterrupt("Operação cancelada pelo usuário.")

        print("Opção inválida. Use A, E, R ou C.")


def pedir_validacao(tipo: str, texto: str, site: str, timeout=900, log=print) -> tuple[str, str]:
    """
    Validação unificada:
    - Se VF_WEBCHAT_VALIDAR=terminal: usa _validar_terminal (A/E/R/C no terminal)
    - Se VF_WEBCHAT_VALIDAR=envio/resposta/ambos (sem "terminal"): usa fila JSON (webchat_ui.py)
    - Se "nenhum" ou não definido: aprova automaticamente
    """
    modo = os.getenv("VF_WEBCHAT_VALIDAR", "").strip().lower()

    # Modo terminal (novo padrão recomendado)
    if modo == "terminal":
        return _validar_terminal(tipo, texto, site, log)

    # Modo fila JSON (painel webchat_ui.py) - compatibilidade
    if modo in ("envio", "resposta", "ambos"):
        FILA = BASE / "fila"
        FILA.mkdir(exist_ok=True)
        vid = f"{int(time.time() * 1000)}_{random.randint(100, 999)}"
        pend = FILA / f"pendente_{vid}.json"
        resp = FILA / f"resposta_{vid}.json"
        tmp = FILA / f"pendente_{vid}.tmp"
        tmp.write_text(json.dumps({"id": vid, "tipo": tipo, "site": site, "texto": texto},
                                  ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, pend)
        log(f"[{site}] aguardando validação ({tipo}) no painel...")
        fim = time.time() + timeout
        try:
            while time.time() < fim:
                if resp.exists():
                    try:
                        r = json.loads(resp.read_text(encoding="utf-8"))
                    except ValueError:
                        time.sleep(0.3)
                        continue
                    resp.unlink(missing_ok=True)
                    return r.get("acao", "rejeitar"), r.get("texto", texto)
                time.sleep(0.8)
            log(f"[{site}] sem resposta na validação; rejeitado por segurança")
            return "rejeitar", texto
        finally:
            pend.unlink(missing_ok=True)

    # Sem validação
    return "aprovar", texto


def _validar(modo, tipo, texto, site, log=print):
    """modo: None/'nenhum'/'terminal'/'envio'/'resposta'/'ambos'. Devolve (aprovado, texto).
    
    Regras para modo 'terminal':
    - tipo='resposta': SEMPRE valida (A/E/R/C no terminal) ← principal
    - tipo='envio': valida apenas se VF_WEBCHAT_VALIDAR_ENVIO=1
    - tipo='assistido': valida apenas se VF_WEBCHAT_VALIDAR_ASSISTIDO=1
    """
    if modo in (None, "nenhum"):
        return True, texto
    
    # Modo terminal: valida 'resposta' sempre; 'envio' e 'assistido' apenas se flags explícitas
    if modo == "terminal":
        if tipo == "resposta":
            pass  # sempre valida
        elif tipo == "envio":
            if os.getenv("VF_WEBCHAT_VALIDAR_ENVIO", "").strip() not in ("1", "true", "yes"):
                return True, texto
        elif tipo == "assistido":
            if os.getenv("VF_WEBCHAT_VALIDAR_ASSISTIDO", "").strip() not in ("1", "true", "yes"):
                return True, texto
        else:
            return True, texto
    elif modo != "ambos" and modo != tipo:
        return True, texto
    
    acao, novo = pedir_validacao(tipo, texto, site, log=log)
    return acao != "rejeitar", novo


# ------------------------------------------------ busca de demonstração
def busca_simples(pasta, topo=3, janela=500):
    """Busca por palavras nos .md de uma pasta, só para testar o fluxo sem o seu
    RAG. Para usar o Qdrant de verdade: --buscar-func meu_modulo:minha_funcao."""
    raiz = Path(pasta)

    def buscar(consulta):
        palavras = re.findall(r"\w{3,}", consulta.lower())
        if not palavras:
            return "(consulta vazia)"
        pontuados = []
        for f in raiz.rglob("*.md"):
            try:
                t = f.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            baixo = t.lower()
            pts = sum(baixo.count(w) for w in palavras)
            if pts:
                pontuados.append((pts, f, t, baixo))
        pontuados.sort(key=lambda x: -x[0])
        saida = []
        for _, f, t, baixo in pontuados[:topo]:
            i = min((baixo.find(w) for w in palavras if w in baixo), default=0)
            ini = max(i - janela // 2, 0)
            saida.append(f"### {f.name}\n{t[ini:ini + janela].strip()}")
        return "\n\n".join(saida) or "(nada encontrado)"
    return buscar


def carregar_busca(spec):
    """'modulo:funcao' -> função de busca do seu RAG (str -> str)."""
    sys.path.insert(0, os.getcwd())
    modulo, _, func = spec.partition(":")
    return getattr(importlib.import_module(modulo), func)


# -------------------------------------------------------------------- Chat
class Chat:
    def __init__(self, pw, name, cfg, headless=False, interactive=True):
        self.name, self.cfg, self.interactive = name, cfg, interactive
        _normalizar({name: cfg})
        self.perfil = cfg["perfil"]
        PROFILES.mkdir(exist_ok=True)
        SHOTS.mkdir(exist_ok=True)
        self.ctx = pw.chromium.launch_persistent_context(
            str(PROFILES / name),
###            channel="msedge",
            headless=False,
            viewport={"width": 1280, "height": 900},
            args=[
                "--disable-blink-features=AutomationControlled",
                "--start-maximized"
            ])

        self.page = self.ctx.pages[0] if self.ctx.pages else self.ctx.new_page()
      
        self.page.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', {
            get: () => undefined
        });
        """)

        self.novo_chat() 
        
        
#       self.ctx = pw.chromium.launch_persistent_context(
#           str(PROFILES / name), headless=headless,
#           viewport={"width": 1280, "height": 900})
#       self.page = self.ctx.pages[0] if self.ctx.pages else self.ctx.new_page()
#       self.novo_chat()

    def novo_chat(self):
        self.page.goto(
            self.cfg["url"],
            wait_until="domcontentloaded"
        )
        self.page.wait_for_timeout(10000)
        self.descartar_popups()

    def close(self):
        try:
            self.ctx.close()
        except Exception:
            pass

    # -- utilidades
    def shot(self, tag="erro"):
        path = SHOTS / f"{self.name}_{tag}_{int(time.time())}.png"
        self.page.screenshot(path=str(path))
        return path

    def body(self):
        return self.page.evaluate("document.body.innerText")

    def visible(self, selector):
        if not selector:
            return False
        try:
            return self.page.locator(selector).first.is_visible()
        except Exception:
            return False

    def _wait_visible(self, selector, ms):
        try:
            self.page.locator(selector).first.wait_for(state="visible", timeout=ms)
            return True
        except Exception:
            return False

    def _botoes(self):
        try:
            return self.page.evaluate(JS_ELEMS, BTN_Q)
        except Exception:
            return []

    def descartar_popups(self):
        for _ in range(2):
            try:
                if self.page.evaluate(JS_POPUP):
                    self.page.wait_for_timeout(1800)
                else:
                    break
            except Exception:
                break

    def precisa_login(self):
        try:
            if self.page.locator("input[type='password']").first.is_visible():
                return True
        except Exception:
            pass
        try:
            # Variante deslogada (ex.: landing "Conheça o Gemini"): a caixa de
            # texto existe, mas o botao "Fazer login" entrega a sessao expirada.
            # NOTA: .first e proibido aqui — o primeiro match na ordem do
            # documento pode ser um link oculto; vale QUALQUER visivel.
            _botoes = self.page.locator(
                "button:has-text('Fazer login'), "
                "a:has-text('Fazer login')")
            try:
                _n = _botoes.count()
            except Exception:
                _n = 0
            for _i in range(min(_n, 5)):
                try:
                    if _botoes.nth(_i).is_visible():
                        return True
                except Exception:
                    continue
        except Exception:
            pass
        na_url = re.search(r"/(login|signin|sign-in|auth)|accounts\.", self.page.url, re.I)
        return bool(na_url) and not self.visible(self.cfg["input"])

    def _registrar(self, ok, lat):
        pf = self.perfil
        if ok:
            pf["ok"] += 1
            pf["seguidas"] = 0
            pf["lat"] = round(lat if not pf["lat"] else 0.7 * pf["lat"] + 0.3 * lat, 1)
        else:
            pf["falhas"] += 1
            pf["seguidas"] += 1
            if pf["seguidas"] >= 3:  # quarentena de 30 min
                pf["cooldown"] = time.time() + 1800

    # -- autocura da caixa de texto: tela + elementos -> modelo local
    def heal_input(self):
        print(f"[{self.name}] caixa de texto não achada; pedindo ajuda ao modelo...")
        cands = self.page.evaluate(JS_ELEMS, INPUT_Q)
        if not cands:
            return False
        png = base64.b64encode(self.shot("heal").read_bytes()).decode()
        prompt = (
            "Esta é a tela de um chat de IA na web. Abaixo há uma lista de campos "
            "de texto da página. Escolha o campo onde o usuário digita a mensagem "
            "para o chat. Responda SOMENTE JSON: {\"input\": \"<sel exato da lista>\"}\n"
            + json.dumps(cands, ensure_ascii=False)
        )
        try:
            try:
                out = _ollama(prompt, images=[png], json_mode=True, model=HEAL_MODEL)
            except Exception:  # modelo sem visão: usa só a lista
                out = _ollama(prompt, json_mode=True, model=HEAL_MODEL)
            new = json.loads(out).get("input", "")
        except Exception as e:
            print(f"[{self.name}] autocura falhou: {e}")
            return False
        if new in {c["sel"] for c in cands} and self.visible(new):
            self.cfg["input"] = new
            print(f"[{self.name}] novo seletor de entrada: {new}")
            return True
        return False

    def assisted(self, motivo):
        """Última chance: você resolve na tela (login, captcha, popup)."""
        self.shot("assistido")
        modo = os.getenv("VF_WEBCHAT_VALIDAR", "").strip().lower()

        # Modo terminal: validação A/E/R/C direto no terminal
        if modo == "terminal":
            try:
                print(f"\n[{self.name}] ASSISTÊNCIA NECESSÁRIA: {motivo}")
            except UnicodeEncodeError:
                print(f"\n[{self.name}] ASSISTENCIA NECESSARIA: {motivo.encode('ascii', 'replace').decode('ascii')}")
            print("Ajuste a janela do navegador se necessário.")
            op = input("\n[C]ontinuar  [A]bortar : ").strip().lower()
            if op in ("", "c"):
                self.descartar_popups()
                return True
            return False

        # Modo painel webchat_ui.py (compatibilidade)
        if self.interactive and os.getenv("WEBCHAT_UI") == "1":
            acao, _ = pedir_validacao("assistido", motivo, self.name, timeout=300)
            if acao == "rejeitar":
                return False
            self.descartar_popups()
            return True

        # Fallback: input simples no terminal (sem WEBCHAT_UI)
        if self.interactive and sys.stdin.isatty():
            try:
                msg = f"[{self.name}] {motivo}\n  Ajuste a janela do navegador e tecle ENTER... "
                print(msg)
            except UnicodeEncodeError:
                print(msg.encode('ascii', 'replace').decode('ascii'))
            input()
            self.descartar_popups()
            return True

        return False

    # -- envio (aprende botão x Enter e o limite de tamanho)
    def _caixa_vazia(self, head, antes):
        try:
            return self.page.locator(self.cfg["input"]).first.evaluate(
                "e => (((e.value ?? e.innerText) || '').trim().length === 0)")
        except Exception:  # caixa foi recriada: confere se a mensagem apareceu
            return " ".join(self.body().split()).count(head) > antes

    def _digitar_e_enviar(self, prompt):
        p, c, pf = self.page, self.cfg, self.perfil
        head = " ".join(prompt.split())[:40]
        antes = " ".join(self.body().split()).count(head)
        box = p.locator(c["input"]).first
        box.click()
        p.keyboard.insert_text(prompt)
        p.wait_for_timeout(500)
        ordem = ["enter", "botao"] if pf["enter_send"] else ["botao", "enter"]
        for metodo in ordem:
            if metodo == "botao":
                if not (c.get("send") and self.visible(c["send"])):
                    continue
                try:
                    p.locator(c["send"]).first.click(timeout=3000)
                except Exception:
                    continue
            else:
                p.keyboard.press("Enter")
            p.wait_for_timeout(800)
            if self._caixa_vazia(head, antes):
                if pf["enter_send"] != (metodo == "enter"):
                    print(f"[{self.name}] aprendi: envio por {metodo}")
                pf["enter_send"] = (metodo == "enter")
                return True
        return False

    def send(self, prompt):
        """Envia e devolve o texto realmente enviado (pode ter sido cortado)."""
        c, pf = self.cfg, self.perfil
        self.descartar_popups()
        if self.precisa_login():
            if not self.assisted("Parece que falta fazer login."):
                pf["cooldown"] = time.time() + 6 * 3600
                raise RuntimeError("precisa de login (use --login)")
        for tentativa in range(3):
            if self.visible(c["input"]) or self._wait_visible(c["input"], 8000):
                if self._digitar_e_enviar(prompt):
                    return prompt
                # Falha de envio com login expirado nao e limite de tamanho:
                # rechecagem impede encolher max_chars sem motivo (ex.:
                # 18000 -> 1932 por sessao deslogada) e aponta o erro certo.
                if self.precisa_login():
                    if not self.assisted("Parece que falta fazer login."):
                        pf["cooldown"] = time.time() + 6 * 3600
                    raise RuntimeError("precisa de login (use --login)")
                if len(prompt) > 3000:  # talvez passou do limite do site
                    pf["max_chars"] = int(len(prompt) * 0.6)
                    print(f"[{self.name}] não enviou; reduzindo limite p/ {pf['max_chars']}")
                    self.page.keyboard.press("ControlOrMeta+A")
                    self.page.keyboard.press("Delete")
                    prompt = ajustar_prompt(prompt, pf["max_chars"])
                    if self._digitar_e_enviar(prompt):
                        return prompt
                raise RuntimeError("mensagem não foi enviada")
            if tentativa == 0 and self.heal_input():
                continue
            if not self.assisted("Não encontrei a caixa de texto."):
                break
        raise RuntimeError("caixa de texto não encontrada")

    # -- leitura (aprende seletor de resposta e botão "parar")
    @staticmethod
    def _diff(before, after, prompt):
        antes = set(l.strip() for l in before.splitlines())
        pedido = set(l.strip() for l in prompt.splitlines())
        novas = [l.strip() for l in after.splitlines()
                 if l.strip() and l.strip() not in antes and l.strip() not in pedido]
        return "\n".join(novas).strip()

    def snapshot(self):
        """(nº de respostas, texto da última) antes de enviar: base do multi-turno."""
        sel = self.cfg.get("response")
        if sel:
            try:
                loc = self.page.locator(sel)
                n = loc.count()
                return (n, loc.last.inner_text().strip() if n else "")
            except Exception:
                pass
        return (0, "")

    def read(self, before, prompt, timeout=180, prev=(0, ""), btn_antes=None):
        p, c = self.page, self.cfg
        inicio = time.time()
        fim = inicio + timeout
        ultimo, estavel, via_diff = "", 0, False
        viu_busy, durante, ticks, busy_ticks = False, None, 0, 0
        precisa = 3 if c.get("busy") else 4  # sem "parar" conhecido: mais cautela
        while time.time() < fim:
            time.sleep(1.5)
            ticks += 1
            txt, achou = "", False
            if c.get("response"):
                loc = p.locator(c["response"])
                if loc.count():
                    achou = True
                    t = loc.last.inner_text().strip()
                    # ainda é a resposta da rodada anterior? então ignora
                    if not (loc.count() <= prev[0] and t == prev[1]):
                        txt = t
                    via_diff = False
            if not txt and not achou:  # seletor quebrou: lê pela diferença
                txt = self._diff(before, self.body(), prompt)
                via_diff = bool(txt)
            ocupado = bool(c.get("busy")) and p.locator(c["busy"]).count() > 0
            viu_busy = viu_busy or ocupado
            busy_ticks += 1 if ocupado else 0
            if durante is None and btn_antes is not None and 2 < time.time() - inicio < 8:
                durante = self._botoes()  # fotografa a tela enquanto gera
            estavel = estavel + 1 if (txt and txt == ultimo and not ocupado) else 0
            ultimo = txt
            if estavel >= precisa and time.time() - inicio > 6:
                break
        if estavel < precisa and ticks > 8 and busy_ticks == ticks:
            print(f"[{self.name}] seletor de 'parar' parece errado (sempre ativo); removendo")
            c["busy"] = ""
        if not ultimo:
            self.shot("sem_resposta")
            raise TimeoutError("sem resposta")
        if via_diff:
            self.learn_response(ultimo)
        if not viu_busy and durante and btn_antes is not None and len(ultimo) > 80:
            self.learn_busy(btn_antes, durante)
        return ultimo

    def learn_response(self, resposta):
        if len(resposta) < 20:
            return
        head, tail = resposta[:40], resposta[-40:]
        try:
            novo = self.page.evaluate(JS_LEARN_RESPONSE, [head, tail])
        except Exception:
            return
        if novo:
            print(f"[{self.name}] novo seletor de resposta aprendido: {novo}")
            self.cfg["response"] = novo

    def learn_busy(self, antes, durante):
        """Botão que aparece só enquanto o chat gera = botão 'parar'."""
        antes_s = {b["sel"] for b in antes}
        depois = {b["sel"] for b in self._botoes()}
        novos = [b for b in durante if b["sel"] not in antes_s and b["sel"] not in depois
                 and re.search(r"stop|parar|interromp|cancel|pausar", b["hint"], re.I)]
        if novos:
            print(f"[{self.name}] botão 'parar' aprendido: {novos[0]['sel']}")
            self.cfg["busy"] = novos[0]["sel"]

    def ask(self, prompt, timeout=180):
        t0 = time.time()
        try:
            prompt = ajustar_prompt(prompt, self.perfil["max_chars"])
            before = self.body()
            prev = self.snapshot()
            btn_antes = self._botoes()
            prompt = self.send(prompt)
            resp = self.read(before, prompt, timeout, prev, btn_antes)
        except Exception:
            self._registrar(False, 0)
            raise
        self._registrar(True, time.time() - t0)
        return resp


# ---------------------------------------------------- uma pergunta só
def ask_web(prompt, order=None, headless=False, interactive=True,
            fallback_local=True, validar=None):
    """Tenta cada site (melhores primeiro); devolve {'site', 'answer'}.
    validar: None | 'envio' | 'resposta' | 'ambos' (aprovação no painel)."""
    ok, prompt = _validar(validar, "envio", prompt, "(a definir)")
    if not ok:
        raise PermissionError("envio rejeitado pelo usuário")
    cfg = load_cfg()
    with sync_playwright() as pw:
        for name in ordenar(cfg, order):
            chat = None
            try:
                chat = Chat(pw, name, cfg[name], headless, interactive)
                resp = chat.ask(prompt)
                ok, resp = _validar(validar, "resposta", resp, name)
                if not ok:
                    raise RuntimeError("resposta rejeitada pelo usuário")
                return {"site": name, "answer": resp}
            except Exception as e:
                print(f"[{name}] falhou: {e}")
                if chat:
                    chat.shot("falha")
            finally:
                if chat:
                    cfg[name] = chat.cfg
                    save_cfg(cfg)

                    print("Aguardando gravação dos cookies...")
                    time.sleep(10)

                    chat.close()
    if fallback_local:
        return ask_local(prompt)
    raise RuntimeError("todos os web chats falharam")


# ---------------------------------------------------------- bidirecional
PROTOCOLO = """Você está conectado a um sistema local do usuário que tem acesso aos
documentos dele. Para pedir informações ao sistema, responda SOMENTE com uma ou
mais linhas no formato {exemplo}. Ferramentas disponíveis:
{ferramentas}
Regras: use só quando precisar; o sistema responde na próxima mensagem com
RESULTADO; quando já tiver o que precisa, dê a resposta final normalmente, SEM
nenhum marcador nesse formato.
"""


def calibrar_protocolo(chat, log=print):
    """Descobre qual formato de marcador o site devolve de forma legível
    (alguns renderizam markdown e 'comem' os colchetes). Se nenhum servir,
    o site passa a usar o modo 'pré-busca'."""
    for estilo, d in ESTILOS.items():
        tok = "T" + "".join(random.choices(string.digits, k=6))
        linha = d["fmt"].format(n="BUSCAR").replace("argumento", tok)
        r = chat.ask("Teste de integração. Responda SOMENTE com a linha abaixo, "
                     f"exatamente como está, sem explicar nada:\n{linha}")
        chat.novo_chat()
        if any(tok in a for _, a in achar_pedidos(r, {"BUSCAR": None}, estilo)):
            chat.perfil["estilo"] = estilo
            log(f"[{chat.name}] protocolo aprendido: {estilo}")
            return estilo
    chat.perfil["estilo"] = "nenhum"
    log(f"[{chat.name}] sem marcador viável; usará modo pré-busca")
    return "nenhum"


def converse(pergunta, tools=None, descs=None, order=None, max_rounds=4,
             headless=False, interactive=True, log=print, validar=None):
    """Conversa bidirecional: o chat pode pedir coisas ao seu sistema.

    tools: {"BUSCAR": funcao_rag(str)->str, ...}  (LOCAL, o Gemma, já vem pronto)
    descs: {"BUSCAR": "busca nos documentos do usuário"}
    validar: None | 'envio' | 'resposta' | 'ambos' (aprovação no painel).
    Devolve {"site", "answer", "rodadas", "modo", "historico"}.
    """
    tools = {"LOCAL": lambda q: ask_local(q)["answer"], **(tools or {})}
    descs = {"LOCAL": "pergunta ao modelo local (Gemma) do usuário", **(descs or {})}
    cfg = load_cfg()
    with sync_playwright() as pw:
        for name in ordenar(cfg, order):
            chat, historico = None, []
            try:
                chat = Chat(pw, name, cfg[name], headless, interactive)
                estilo = chat.perfil.get("estilo") or calibrar_protocolo(chat, log)

                def _fim(resp, modo, rodada):
                    aprovado, resp = _validar(validar, "resposta", resp, name, log)
                    if not aprovado:
                        raise RuntimeError("resposta rejeitada pelo usuário")
                    return {"site": name, "answer": resp, "rodadas": rodada,
                            "modo": modo, "historico": historico}

                if estilo == "nenhum":  # modo pré-busca: tudo numa mensagem
                    ctx = str(tools["BUSCAR"](pergunta))[:MAX_RESULTADO] if "BUSCAR" in tools else ""
                    if ctx:
                        liberado, ctx = _validar(validar, "envio", ctx, name, log)
                        ctx = ctx if liberado else ""
                    msg = (f"Contexto dos documentos do usuário:\n{ctx}\n\n" if ctx else "")
                    resp = chat.ask(msg + "Pergunta do usuário:\n" + pergunta)
                    historico.append(("chat", resp))
                    return _fim(resp, "pre-busca", 0)

                fmt = ESTILOS[estilo]["fmt"]
                lista = "\n".join(f"- {fmt.format(n=n)} -> {descs.get(n, 'consulta ao sistema local')}"
                                  for n in tools)
                msg = (PROTOCOLO.format(exemplo=fmt.format(n="FERRAMENTA"), ferramentas=lista)
                       + "\nPergunta do usuário:\n" + pergunta)
                vistos = set()
                for rodada in range(max_rounds + 1):
                    resp = chat.ask(msg)
                    historico.append(("chat", resp))
                    pedidos = achar_pedidos(resp, tools, estilo)
                    if not pedidos or rodada == max_rounds:
                        return _fim(resp, "bidirecional", rodada)
                    novos = [pd for pd in pedidos if pd not in vistos]
                    if not novos:  # o chat entrou em loop pedindo a mesma coisa
                        msg = ("Você já recebeu esse resultado acima. Responda agora com a "
                               "resposta final, sem marcadores.")
                        continue
                    partes = []
                    for nome, arg in novos:
                        vistos.add((nome, arg))
                        log(f"[{name}] pediu {nome}: {arg[:80]}")
                        try:
                            out = str(tools[nome](arg))
                        except Exception as e:
                            out = f"erro ao executar: {e}"
                        liberado, out = _validar(validar, "envio", out[:MAX_RESULTADO], name, log)
                        if not liberado:
                            out = "[o usuário não autorizou o envio deste resultado]"
                        historico.append((nome, out))
                        partes.append(f"RESULTADO {nome} ({arg}):\n{out[:MAX_RESULTADO]}")
                    msg = ("\n\n".join(partes) + "\n\nContinue. Se já tiver o necessário, "
                           "dê a resposta final sem marcadores.")
            except Exception as e:
                log(f"[{name}] falhou: {e}")
                if chat:
                    chat.shot("falha")
            finally:
                if chat:
                    cfg[name] = chat.cfg
                    save_cfg(cfg)
                    chat.close()
    return {**ask_local(pergunta), "rodadas": 0, "modo": "local", "historico": []}


class WebSession:
    """Sessão aberta para você conduzir a conversa de dentro do pipeline:

        with WebSession("claude") as s:
            r1 = s.say("Resuma este contexto: ...")
            r2 = s.say("Agora compare com: ...")   # mesma conversa
    """

    def __init__(self, site, headless=False, interactive=True):
        self.site, self.headless, self.interactive = site, headless, interactive

    def __enter__(self):
        self.cfg_all = load_cfg()
        self.pw = sync_playwright().start()
        self.chat = Chat(self.pw, self.site, self.cfg_all[self.site],
                         self.headless, self.interactive)
        return self

    def say(self, msg, timeout=180):
        return self.chat.ask(msg, timeout)

    def __exit__(self, *exc):
        self.cfg_all[self.site] = self.chat.cfg
        save_cfg(self.cfg_all)
        self.chat.close()
        self.pw.stop()


# ----------------------------------------------------- calibração / CLI
def calibrar(nome, limites=False, log=print):
    """Testa o site de ponta a ponta e grava o que aprendeu."""
    cfg = load_cfg()
    with sync_playwright() as pw:
        chat = Chat(pw, nome, cfg[nome], headless=False, interactive=True)
        try:
            tok = "PONG" + "".join(random.choices(string.digits, k=5))
            t0 = time.time()
            r = chat.ask(f"Responda somente com esta palavra: {tok}")
            log(f"[{nome}] resposta {'OK' if tok in r else 'DIFERENTE'} "
                f"em {time.time() - t0:.0f}s | envio={'Enter' if chat.perfil['enter_send'] else 'botão'}"
                f" | parar={chat.cfg.get('busy') or '(sem)'}")
            chat.novo_chat()
            calibrar_protocolo(chat, log)
            if limites:  # manda textos grandes de verdade: gasta mensagens do site
                for n in (20000, 8000, 3000):
                    chat.perfil["max_chars"] = 10 ** 9
                    enchimento = ("lorem ipsum dolor sit amet " * (n // 27 + 1))[:n]
                    try:
                        r = chat.ask(enchimento + f"\n\nIgnore o texto acima. Responda somente: {tok}")
                        if tok in r:
                            chat.perfil["max_chars"] = int(n * 0.9)
                            log(f"[{nome}] aceita ~{n} caracteres")
                            break
                    except Exception:
                        pass
                    chat.novo_chat()
                else:
                    chat.perfil["max_chars"] = 2000
                    log(f"[{nome}] limite baixo: usando 2000")
        finally:
            cfg[nome] = chat.cfg
            save_cfg(cfg)
            chat.close()


def login(name):
    """Abre o site para você logar manualmente; a sessão fica no perfil.
    Sem terminal (painel): termina quando você FECHAR a janela do navegador."""
    cfg = load_cfg()
    with sync_playwright() as pw:
        chat = Chat(pw, name, cfg[name])
        if sys.stdin.isatty():
            input(f"Faça login em {name} na janela aberta e tecle ENTER aqui... ")
        else:
            print(f"Faça login em {name} e FECHE a janela do navegador quando terminar.")
            try:
                while not chat.page.is_closed():
                    time.sleep(1)
            except Exception:
                pass
        chat.perfil["cooldown"] = 0
        cfg[name] = chat.cfg
        save_cfg(cfg)
        chat.close()


def status():
    cfg, agora = load_cfg(), time.time()
    for n, c in cfg.items():
        pf = c["perfil"]
        envio = {True: "Enter", False: "botão", None: "?"}[pf["enter_send"]]
        cd = int(pf["cooldown"] - agora)
        print(f"{n:11} ok={pf['ok']:<3} falhas={pf['falhas']:<3} lat={pf['lat']:<5}s "
              f"protocolo={pf['estilo']} limite={pf['max_chars']} envio={envio} "
              f"parar={'sim' if c.get('busy') else 'não'}"
              + (f" QUARENTENA {cd}s" if cd > 0 else ""))


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="Ponte entre o seu RAG e web chats")
    ap.add_argument("pergunta", nargs="?")
    ap.add_argument("--site", action="append", help="sites a usar, em ordem (repetível)")
    ap.add_argument("--login", metavar="SITE")
    ap.add_argument("--calibrar", nargs="?", const="todos", metavar="SITE|todos")
    ap.add_argument("--limites", action="store_true", help="com --calibrar: testa tamanho máximo")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--bidirecional", action="store_true")
    ap.add_argument("--buscar-dir", help="pasta de .md para a busca de demonstração")
    ap.add_argument("--buscar-func", help="modulo:funcao com a busca do seu RAG (str -> str)")
    ap.add_argument("--validar", choices=["nenhum", "envio", "resposta", "ambos"],
                    default="nenhum", help="aprovação humana pelo painel")
    ap.add_argument("--json", action="store_true", help="saída final em JSON (usado pelo painel)")
    a = ap.parse_args()

    if a.login:
        return login(a.login)
    if a.status:
        return status()
    if a.calibrar:
        for s in (list(load_cfg()) if a.calibrar == "todos" else [a.calibrar]):
            calibrar(s, limites=a.limites)
        return
    if not a.pergunta:
        return print(__doc__)

    tools = {}
    if a.buscar_func:
        tools["BUSCAR"] = carregar_busca(a.buscar_func)
    elif a.buscar_dir:
        tools["BUSCAR"] = busca_simples(a.buscar_dir)
    if a.bidirecional or tools:
        r = converse(a.pergunta, tools=tools, order=a.site, validar=a.validar,
                     descs={"BUSCAR": "busca nos documentos do usuário"})
    else:
        r = ask_web(a.pergunta, order=a.site, validar=a.validar)
    if a.json:
        print("@@RESULTADO@@ " + json.dumps(r, ensure_ascii=False, default=str))
    else:
        print(f"\n=== {r['site']} ===\n{r['answer']}")


if __name__ == "__main__":
    try:
        main()
    except PermissionError as e:
        print(f"CANCELADO: {e}")
        sys.exit(2)
    except Exception as e:
        print(f"ERRO: {type(e).__name__}: {e}")
        sys.exit(1)