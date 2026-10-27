"""Busca de imagens no Google Imagens e geração por interfaces web.

Este módulo não usa APIs pagas. Playwright abre perfis persistentes por provedor.
A interface dos serviços pode mudar e exigir login/captcha; falhas retornam None.
Nenhum placeholder é criado. Google Images filtra por Creative Commons, mas a licença
individual do arquivo deve ser verificada na página de origem antes de uso comercial.
"""
from __future__ import annotations
import base64, io, os, re, time
from pathlib import Path
from typing import Optional, Tuple
from urllib.parse import quote_plus

MIN_BYTES = 15_000
PROVIDERS = {
    "chatgpt": {
        "url": "https://chatgpt.com/",
        "profile": "chatgpt",
        "composers": ['#prompt-textarea', '[contenteditable="true"][data-placeholder]', 'div[contenteditable="true"]', 'textarea'],
        "send": ['button[data-testid="send-button"]', 'button[aria-label*="Send"]', 'button[aria-label*="Enviar"]'],
    },
    "copilot": {
        "url": "https://copilot.microsoft.com/",
        "profile": "copilot",
        "composers": ['textarea', 'div[contenteditable="true"]', '[role="textbox"]'],
        "send": ['button[aria-label*="Submit"]', 'button[aria-label*="Send"]', 'button[aria-label*="Enviar"]'],
    },
    "dreamina": {
        "url": "https://dreamina.capcut.com/ai-tool/image-generator",
        "profile": "dreamina",
        "composers": ['textarea', '[contenteditable="true"]', '[role="textbox"]', 'input[type="text"]'],
        "send": ['button[aria-label*="Generate"]', 'button[aria-label*="Create"]', 'button:has-text("Generate")', 'button:has-text("Gerar")', 'button:has-text("Create")'],
    },
    "grok": {
        "url": "https://grok.com/",
        "profile": "grok",
        "composers": ['textarea', 'div[contenteditable="true"]', '[role="textbox"]'],
        "send": ['button[aria-label*="Send"]', 'button[aria-label*="Enviar"]'],
    },
    "qwen": {
        "url": "https://chat.qwen.ai/",
        "profile": "qwen",
        "composers": ['textarea', 'div[contenteditable="true"]', '[role="textbox"]'],
        "send": ['button[aria-label*="Send"]', 'button[aria-label*="Enviar"]'],
    },
    "google_ai_studio": {
        "url": "https://aistudio.google.com/",
        "profile": "google_ai_studio",
        "composers": ['textarea', 'div[contenteditable="true"]', '[role="textbox"]'],
        "send": ['button[aria-label*="Run"]', 'button[aria-label*="Send"]'],
    },
}


def _profiles_root() -> Path:
    # Reuse the persistent profiles already used by webchat_bridge (notably the
    # signed-in Copilot profile), unless the user explicitly chooses another root.
    configured = os.environ.get("VF_WEB_IMAGE_PROFILES", "").strip()
    root = configured or str(Path(__file__).resolve().parent / "perfis")
    return Path(root).expanduser().resolve()


def _normalize(data: bytes, dest_path: str) -> bool:
    try:
        from PIL import Image, ImageOps
        img = Image.open(io.BytesIO(data)); img.load()
        if img.width < 768 or img.height < 432:
            return False
        img = ImageOps.fit(img.convert("RGB"), (1920,1080), method=Image.Resampling.LANCZOS, centering=(0.5,0.5))
        dest = Path(dest_path); dest.parent.mkdir(parents=True, exist_ok=True)
        img.save(dest, "JPEG", quality=94, optimize=True)
        return dest.is_file() and dest.stat().st_size >= MIN_BYTES
    except Exception:
        return False


def _download_candidate(page, src: str) -> Optional[bytes]:
    try:
        if src.startswith("data:") and "," in src:
            head, payload = src.split(",",1)
            return base64.b64decode(payload) if ";base64" in head else payload.encode()
        response = page.request.get(src, timeout=15000)
        if response.ok:
            data = response.body()
            if len(data) >= MIN_BYTES and (data.startswith(b"\xff\xd8") or data.startswith(b"\x89PNG\r\n\x1a\n") or data.startswith(b"RIFF")):
                return data
    except Exception:
        pass
    return None


def _download_buttons(page):
    selectors = ['button[aria-label*="Download"]', 'button[aria-label*="download"]',
                 'button[aria-label*="Baixar"]', 'button[title*="Download"]',
                 'button[title*="Baixar"]']
    found, seen = [], set()
    for selector in selectors:
        try:
            loc = page.locator(selector)
            for index in range(loc.count()):
                button = loc.nth(index)
                try:
                    if not button.is_visible(timeout=150):
                        continue
                    box = button.bounding_box()
                    key = (round(box["x"]), round(box["y"])) if box else (selector, index)
                    if key not in seen:
                        seen.add(key)
                        found.append(button)
                except Exception:
                    continue
        except Exception:
            continue
    return found


def _image_src_snapshot(page) -> set[str]:
    try:
        return set(page.locator("img").evaluate_all(
            "els => els.map(e => e.currentSrc || e.src || '').filter(Boolean)"
        ))
    except Exception:
        return set()


def open_image_provider_login(provider: str, wait_seconds: int = 1200) -> dict:
    """Open a provider's persistent browser profile for manual sign-in.

    The browser stays open until the user closes it. The saved session then
    belongs to the same profile later used by calibration and generation.
    """
    provider = (provider or "").strip().lower()
    pw = context = page = None
    try:
        if provider == "gemini":
            from gemini_webchat_image import _open_gemini
            pw, context, page = _open_gemini()
        else:
            if provider not in PROVIDERS:
                return {"ok": False, "provider": provider, "message": "Provedor desconhecido."}
            from playwright.sync_api import sync_playwright
            cfg = PROVIDERS[provider]
            profile = _profiles_root() / cfg["profile"]
            profile.mkdir(parents=True, exist_ok=True)
            pw = sync_playwright().start()
            context = pw.chromium.launch_persistent_context(
                str(profile), headless=False, accept_downloads=True,
                viewport={"width": 1440, "height": 1000},
                args=["--disable-blink-features=AutomationControlled"],
            )
            page = context.pages[0] if context.pages else context.new_page()
            page.goto(os.environ.get(f"VF_{provider.upper()}_URL", cfg["url"]),
                      wait_until="domcontentloaded", timeout=60000)

        deadline = time.monotonic() + max(60, int(wait_seconds))
        while time.monotonic() < deadline and page is not None and not page.is_closed():
            try:
                page.wait_for_timeout(1000)
            except Exception as exc:
                # Fechar o navegador é a conclusão esperada deste fluxo. O
                # Playwright pode lançar antes de page.is_closed() refletir o
                # fechamento da página ou do contexto persistente.
                if "closed" in str(exc).lower():
                    return {
                        "ok": True, "provider": provider,
                        "message": "Janela de login fechada; o perfil persistente foi preservado.",
                    }
                raise
        if page is not None and page.is_closed():
            return {"ok": True, "provider": provider, "message": "Janela de login fechada; sessão persistente salva no perfil."}
        return {"ok": True, "provider": provider, "message": "Tempo de login encerrado; o perfil persistente foi salvo."}
    except Exception as exc:
        return {"ok": False, "provider": provider, "message": str(exc)}
    finally:
        try:
            if context:
                context.close()
        except Exception:
            pass
        try:
            if pw:
                pw.stop()
        except Exception:
            pass


def calibrate_image_provider(provider: str, login_wait_seconds: int = 30) -> dict:
    """Open a persistent image-provider profile and verify its prompt control.

    Login is performed separately by open_image_provider_login(). Calibration
    only checks the saved session and prompt control for a short period; it
    does not consume a generation credit or claim generation was verified.
    """
    provider = (provider or "").strip().lower()
    if provider == "gemini":
        from gemini_webchat_image import _open_gemini, _find_composer
        pw = context = page = None
        try:
            pw, context, page = _open_gemini()
            composer = _find_composer(page)
            deadline = time.monotonic() + max(0, int(login_wait_seconds))
            while composer is None and time.monotonic() <= deadline and not page.is_closed():
                page.wait_for_timeout(1000)
                composer = _find_composer(page)
            if composer is None:
                return {"ok": False, "provider": provider, "message": "Campo de prompt do Gemini não apareceu em 30 segundos; abra o login novamente ou confira a interface."}
            return {"ok": True, "provider": provider, "message": "Sessão aberta e campo de prompt do Gemini localizado."}
        except Exception as exc:
            return {"ok": False, "provider": provider, "message": str(exc)}
        finally:
            try:
                if context: context.close()
            except Exception: pass
            try:
                if pw: pw.stop()
            except Exception: pass

    if provider not in PROVIDERS:
        return {"ok": False, "provider": provider, "message": "Provedor de imagem desconhecido."}

    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        return {"ok": False, "provider": provider, "message": f"Playwright indisponível: {exc}"}

    pw = context = page = None
    try:
        cfg = PROVIDERS[provider]
        profile = _profiles_root() / provider
        profile.mkdir(parents=True, exist_ok=True)
        pw = sync_playwright().start()
        context = pw.chromium.launch_persistent_context(
            str(profile), headless=False, accept_downloads=True,
            viewport={"width": 1440, "height": 1000},
            args=["--disable-blink-features=AutomationControlled"],
        )
        page = context.pages[0] if context.pages else context.new_page()
        page.goto(os.environ.get(f"VF_{provider.upper()}_URL", cfg["url"]),
                  wait_until="domcontentloaded", timeout=60000)
        deadline = time.monotonic() + max(0, int(login_wait_seconds))
        composer_selector = ""
        while time.monotonic() <= deadline:
            if page.is_closed():
                return {"ok": False, "provider": provider, "message": "A janela foi fechada antes da calibração."}
            for selector in cfg["composers"]:
                try:
                    loc = page.locator(selector).last
                    if loc.count() and loc.is_visible(timeout=300):
                        composer_selector = selector
                        break
                except Exception:
                    continue
            if composer_selector:
                return {
                    "ok": True, "provider": provider, "url": page.url,
                    "composer": composer_selector,
                    "message": f"Sessão acessível; campo de prompt localizado ({composer_selector}).",
                }
            page.wait_for_timeout(1000)
        return {"ok": False, "provider": provider, "message": "Campo de prompt não apareceu em 30 segundos. Abra o login novamente ou a interface do provedor mudou."}
    except Exception as exc:
        return {"ok": False, "provider": provider, "message": str(exc)}
    finally:
        try:
            if context: context.close()
        except Exception: pass
        try:
            if pw: pw.stop()
        except Exception: pass


def _extract_image(page, exclude_srcs=None, download_button_start=0) -> Optional[bytes]:
    # First try an actual download button; do not use screenshots of the browser.
    exclude_srcs = exclude_srcs or set()
    buttons = _download_buttons(page)
    for b in reversed(buttons[max(0, download_button_start):]):
        try:
            with page.expect_download(timeout=1800) as info:
                b.click(timeout=1200)
            download = info.value
            target = _profiles_root() / f"download_{time.time_ns()}{Path(download.suggested_filename or 'image.jpg').suffix}"
            target.parent.mkdir(parents=True, exist_ok=True)
            download.save_as(str(target))
            try:
                data = target.read_bytes()
            finally:
                target.unlink(missing_ok=True)
            if len(data) >= MIN_BYTES:
                return data
        except Exception:
            continue
    candidates=[]
    try:
        imgs=page.locator("img")
        for i in range(max(0,imgs.count()-50),imgs.count()):
            try:
                m=imgs.nth(i).evaluate("e=>({src:e.currentSrc||e.src||'',w:e.naturalWidth||0,h:e.naturalHeight||0})")
                if m['src'] and m['src'] not in exclude_srcs and m['w']>=768 and m['h']>=432 and not m['src'].startswith('blob:'):
                    candidates.append(m)
            except Exception: pass
    except Exception: pass
    candidates.sort(key=lambda x:x['w']*x['h'],reverse=True)
    for item in candidates:
        data=_download_candidate(page,item['src'])
        if data: return data
    return None


def search_google_images(query: str, dest_path: str) -> Optional[Tuple[str,str]]:
    """Busca Google Imagens com filtro de licença Creative Commons e tenta obter bytes de imagem.

    O filtro não substitui a verificação da licença na página de origem.
    """
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        raise RuntimeError("Playwright não está instalado.") from exc
    pw=context=page=None
    try:
        prof=_profiles_root()/"google_images"; prof.mkdir(parents=True,exist_ok=True)
        pw=sync_playwright().start()
        context=pw.chromium.launch_persistent_context(str(prof),headless=False,accept_downloads=True,viewport={"width":1440,"height":1000},args=["--disable-blink-features=AutomationControlled"])
        page=context.pages[0] if context.pages else context.new_page()
        url="https://www.google.com/search?tbm=isch&tbs=il:cl&q="+quote_plus(query)
        page.goto(url,wait_until="domcontentloaded",timeout=45000); page.wait_for_timeout(1800)
        # Google results are thumbnails first. Open a result and inspect large images from the preview.
        for idx in range(min(8,page.locator('div[data-ri]').count())):
            try:
                card=page.locator('div[data-ri]').nth(idx)
                card.click(timeout=1800); page.wait_for_timeout(500)
                data=_extract_image(page)
                if data and _normalize(data,dest_path):
                    # The page may not expose a stable source URL; record the search URL honestly.
                    return (page.url, "Creative Commons filter in Google Images; verify source license")
            except Exception: continue
        # Fallback: inspect result images, but still require a sufficiently large real image.
        data=_extract_image(page)
        if data and _normalize(data,dest_path):
            return (url, "Creative Commons filter in Google Images; verify source license")
        return None
    except Exception as exc:
        print(f"    [Google Images] Falha: {exc}")
        try: Path(dest_path).unlink(missing_ok=True)
        except Exception: pass
        return None
    finally:
        try:
            if context: context.close()
        except Exception: pass
        try:
            if pw: pw.stop()
        except Exception: pass


def generate_image(provider: str, prompt: str, dest_path: str, scene_id: int = 1, topic: str = "") -> Optional[Tuple[str,str]]:
    """Gera imagem pela interface web do provedor e recupera arquivo real, se exposto."""
    provider=(provider or "").strip().lower()
    if provider not in PROVIDERS:
        return None
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        raise RuntimeError("Playwright não está instalado.") from exc
    pw=context=page=None
    try:
        cfg=PROVIDERS[provider]
        profile=_profiles_root()/provider; profile.mkdir(parents=True,exist_ok=True)
        pw=sync_playwright().start()
        context=pw.chromium.launch_persistent_context(str(profile),headless=False,accept_downloads=True,viewport={"width":1440,"height":1000},args=["--disable-blink-features=AutomationControlled"])
        page=context.pages[0] if context.pages else context.new_page()
        page.goto(os.environ.get(f"VF_{provider.upper()}_URL",cfg['url']),wait_until="domcontentloaded",timeout=60000)
        page.wait_for_timeout(1800)
        previous_sources = _image_src_snapshot(page)
        previous_download_buttons = len(_download_buttons(page))
        composer=None
        for sel in cfg['composers']:
            try:
                loc=page.locator(sel).last
                if loc.count() and loc.is_visible(timeout=500): composer=loc; break
            except Exception: pass
        if composer is None:
            raise RuntimeError("Campo de prompt não encontrado; faça login ou a interface mudou.")
        instruction=("Create/generate an original landscape image for a documentary scene. "
                     "Target 16:9, 1920x1080 where supported. No text, captions, logos, or watermarks. "
                     "Do not impose a cinematic style unless it serves the scene.\n"
                     f"Video topic: {topic or 'unspecified'}\nScene {scene_id}: {prompt}\n"
                     "Generate the actual image, not a textual description.")
        composer.click(timeout=4000); composer.fill(instruction,timeout=7000)
        sent=False
        for sel in cfg['send']:
            try:
                btn=page.locator(sel).last
                if btn.count() and btn.is_visible(timeout=300): btn.click(timeout=1800); sent=True; break
            except Exception: pass
        if not sent: composer.press("Enter",timeout=2500)
        timeout=max(45,int(os.environ.get("VF_WEB_IMAGE_TIMEOUT","180")))
        deadline=time.monotonic()+timeout
        data=None; previous_count=-1; stable=0
        while time.monotonic()<deadline:
            page.wait_for_timeout(1500)
            if page.is_closed():
                raise RuntimeError("A janela do provedor foi encerrada durante a geração.")
            data=_extract_image(
                page, exclude_srcs=previous_sources,
                download_button_start=previous_download_buttons,
            )
            if data: break
            try:
                count=page.locator('img').count()
                stable=stable+1 if count==previous_count else 0; previous_count=count
            except Exception: pass
        if not data:
            raise RuntimeError("Nenhum arquivo de imagem real baixável foi detectado.")
        if not _normalize(data,dest_path):
            raise RuntimeError("Arquivo recuperado não passou na validação de imagem.")
        return (cfg['url'],f"ai_generated_{provider}_webchat")
    except Exception as exc:
        print(f"    [{provider}] Geração falhou: {exc}")
        try: Path(dest_path).unlink(missing_ok=True)
        except Exception: pass
        return None
    finally:
        try:
            if context: context.close()
        except Exception: pass
        try:
            if pw: pw.stop()
        except Exception: pass
