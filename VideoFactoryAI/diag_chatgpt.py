# -*- coding: utf-8 -*-
"""
Diagnóstico do ChatGPT no webchat_bridge.

Abre o MESMO perfil que o bridge usa (perfis/chatgpt), mostra a tela e grava:
  - uma captura de tela (.png)
  - um JSON com a URL, o título, o início do texto da página e todos os campos
    de digitação encontrados.

Uso (na pasta VideoFactoryAI, com as janelas do bridge FECHADAS):
  C:\\Docling\\venv\\Scripts\\python.exe diag_chatgpt.py
"""
import json
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = Path(__file__).resolve().parent
PERFIL = BASE / "perfis" / "chatgpt"
SAIDA = BASE / "logs" / "diagnostico_chatgpt"
SAIDA.mkdir(parents=True, exist_ok=True)

JS_INFO = """() => {
  const vis = e => e.getClientRects().length > 0;
  const campos = [...document.querySelectorAll('textarea, [contenteditable], [role="textbox"], input[type="text"]')]
    .map(e => ({
      tag: e.tagName,
      id: e.id || '',
      role: e.getAttribute('role') || '',
      contenteditable: e.getAttribute('contenteditable') || '',
      placeholder: e.getAttribute('placeholder') || e.getAttribute('data-placeholder') || '',
      aria_label: e.getAttribute('aria-label') || '',
      visivel: vis(e),
      classe: String(e.className || '').slice(0, 80),
    }));
  return {
    url: location.href,
    titulo: document.title,
    campos: campos,
    texto_inicio: (document.body && document.body.innerText || '').slice(0, 800),
  };
}"""


def main():
    print("Abrindo o ChatGPT com o perfil do bridge...")
    print("Feche o bridge antes (perfil travado se houver outra janela aberta).")
    with sync_playwright() as pw:
        ctx = pw.chromium.launch_persistent_context(
            str(PERFIL),
            headless=False,
            viewport={"width": 1280, "height": 900},
            args=["--disable-blink-features=AutomationControlled"],
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto("https://chatgpt.com/", wait_until="domcontentloaded", timeout=60000)
        print("\nAguarde a página carregar por completo. Se aparecer login, verificação")
        print("ou pop-up, resolva na janela. Quando a tela estiver como você veria")
        print("para escrever uma mensagem, volte aqui e tecle ENTER.")
        input()
        page.wait_for_timeout(1500)
        info = page.evaluate(JS_INFO)
        nome = f"chatgpt_{time.strftime('%Y%m%d_%H%M%S')}"
        png = SAIDA / f"{nome}.png"
        page.screenshot(path=str(png))
        js = SAIDA / f"{nome}.json"
        js.write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")
        ctx.close()
    print(f"\nDiagnóstico salvo em: {SAIDA}")
    print(f"  - {png.name}")
    print(f"  - {js.name}")
    print("Me mande esses dois arquivos.")


if __name__ == "__main__":
    main()
