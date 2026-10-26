# -*- coding: utf-8 -*-
"""
Mede a geração de imagem de UM provedor pelo MESMO caminho que o pipeline usa.

Uso (com as janelas do pipeline e do bridge FECHADAS):
  C:\\Docling\\venv\\Scripts\\python.exe diag_imagem.py grok
  C:\\Docling\\venv\\Scripts\\python.exe diag_imagem.py meta_muse "Uma maquete HO com trem a vapor"

Fluxo:
  1. Abre o site com o perfil do pipeline (perfis\\<provedor>).
  2. Se houver tela de login, faça o login na janela e tecle ENTER aqui.
  3. Digita e envia o prompt de teste.
  4. Marca o tempo até a primeira imagem nova grande aparecer (ou até o tempo limite).
  5. Grava em logs\\diagnostico_imagem\\ : print, JSON com imagens/botões/campos e tempos.
"""
import json
import os
import sys
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

import web_image_providers as w  # type: ignore  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

JS_NOVAS = """(conhecidas) => [...document.querySelectorAll('img')]
  .filter(i => i.naturalWidth >= 300 && i.naturalHeight >= 200 && !conhecidas.includes(i.currentSrc || i.src))
  .map(i => ({src: (i.currentSrc || i.src || '').slice(0, 140), w: i.naturalWidth, h: i.naturalHeight}))"""

JS_INFO = """() => ({
  url: location.href,
  texto_fim: (document.body && document.body.innerText || '').slice(-1200),
  imgs: [...document.querySelectorAll('img')].slice(-40).map(i => ({
      src: (i.currentSrc || i.src || '').slice(0, 140), w: i.naturalWidth, h: i.naturalHeight,
      visivel: i.getClientRects().length > 0})),
  botoes: [...document.querySelectorAll('button,[role="button"]')]
      .filter(b => /download|baixar|save|salvar|copy|copiar/i.test((b.getAttribute('aria-label')||'') + (b.title||'') + b.innerText))
      .map(b => ({rotulo: (b.getAttribute('aria-label') || b.title || b.innerText || '').slice(0, 60),
                  visivel: b.getClientRects().length > 0})),
  campos: [...document.querySelectorAll('textarea,[contenteditable],[role="textbox"]')].map(e => ({
      tag: e.tagName, visivel: e.getClientRects().length > 0,
      dica: (e.placeholder || e.getAttribute('aria-label') || '').slice(0, 60)})),
})"""


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in w.PROVIDERS:
        print("Uso: diag_imagem.py <provedor> [prompt]")
        print("Provedores:", ", ".join(w.PROVIDERS))
        return
    prov = sys.argv[1]
    prompt = sys.argv[2] if len(sys.argv) > 2 else (
        "Maquete ferroviária HO com uma locomotiva a vapor numa curva, luz natural, sem texto.")
    cfg = w.PROVIDERS[prov]
    url = os.environ.get(f"VF_{prov.upper()}_URL", cfg["url"])
    perfil = w._profiles_root() / prov
    perfil.mkdir(parents=True, exist_ok=True)
    saida = BASE / "logs" / "diagnostico_imagem"
    saida.mkdir(parents=True, exist_ok=True)
    timeout = int(os.environ.get(f"VF_WEB_IMAGE_TIMEOUT_{prov.upper()}", cfg.get("timeout") or 180))

    with sync_playwright() as pw:
        ctx = pw.chromium.launch_persistent_context(
            str(perfil), headless=False, accept_downloads=True,
            viewport={"width": 1440, "height": 1000},
            args=["--disable-blink-features=AutomationControlled"])
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(2000)
        for sel in cfg.get("esperar_sumir", []):
            try:
                page.wait_for_selector(sel, state="hidden", timeout=15000)
            except Exception:
                pass
        for txt in cfg.get("abrir", []):
            try:
                alvo = page.get_by_text(txt, exact=True).first
                if alvo.is_visible(timeout=800):
                    alvo.click(timeout=2000)
                    page.wait_for_timeout(2500)
                    break
            except Exception:
                pass

        input(f"\n[{prov}] Confirme na janela que está logado e com a caixa de prompt visível. ENTER para enviar o teste... ")
        conhecidas = list(w._image_src_snapshot(page))
        antes_txt = (page.inner_text("body") or "").lower()
        print(f"[{prov}] enviando prompt de teste...")
        t0 = time.monotonic()
        composer = w._digitar_no_campo(page, cfg["composers"], prompt)
        enviado = False
        for sel in cfg.get("send", []):
            try:
                btn = w._primeiro_visivel(page, sel)
                if btn is not None:
                    btn.click(timeout=1800)
                    enviado = True
                    break
            except Exception:
                pass
        if not enviado:
            composer.press("Enter", timeout=2500)
        print(f"[{prov}] enviado. Aguardando imagem (até {timeout}s)...")

        primeira = None
        achadas = []
        limite_msg = None
        while time.monotonic() - t0 < timeout:
            try:
                page.wait_for_timeout(2000)
            except Exception:
                print(f"\n[{prov}] A janela foi fechada antes do fim do teste. Não é preciso fechar; o programa já saiu.")
                return
            try:
                w._checar_limite(page, prov, cfg, antes_txt)
            except RuntimeError as exc:
                limite_msg = str(exc)
                print(f"\n[{prov}] LIMITE DETECTADO: {limite_msg}")
                break
            try:
                novas = page.evaluate(JS_NOVAS, conhecidas)
            except Exception:
                novas = []
            if novas and primeira is None:
                primeira = round(time.monotonic() - t0, 1)
                achadas = novas
                print(f"[{prov}] primeira imagem nova em {primeira}s: {novas[0]['w']}x{novas[0]['h']}")
                page.wait_for_timeout(4000)
                break

        try:
            info = page.evaluate(JS_INFO)
        except Exception:
            print(f"[{prov}] Janela fechada antes de gravar o diagnóstico.")
            return
        resultado = {
            "provedor": prov,
            "prompt": prompt,
            "limite_de_geracao_detectado": limite_msg,
            "tempo_ate_primeira_imagem_s": primeira,
            "limite_s": timeout,
            "imagens_novas": achadas,
            "pagina": info,
        }
        nome = f"{prov}_{time.strftime('%Y%m%d_%H%M%S')}"
        page.screenshot(path=str(saida / f"{nome}.png"))
        (saida / f"{nome}.json").write_text(json.dumps(resultado, ensure_ascii=False, indent=2), encoding="utf-8")
        ctx.close()

    if limite_msg:
        print(f"\n[{prov}] O site informou limite de geração. Este provedor fica de fora do pipeline "
              "até o limite voltar. Não há problema no código.")
    elif primeira is None:
        print(f"\n[{prov}] NENHUMA imagem nova em {timeout}s.")
    print(f"Arquivos em: {saida}")
    print(f"  {nome}.json  e  {nome}.png  -> me mande os dois")


if __name__ == "__main__":
    main()
