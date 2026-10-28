"""Busca de imagens no Google Imagens e geração por interfaces web.

Este módulo não usa APIs pagas. Playwright abre perfis persistentes por provedor.
A interface dos serviços pode mudar e exigir login/captcha; falhas retornam None.
Nenhum placeholder é criado. Google Images filtra por Creative Commons, mas a licença
individual do arquivo deve ser verificada na página de origem antes de uso comercial.
"""
from __future__ import annotations
import base64, concurrent.futures, io, json, os, re, time, unicodedata
from pathlib import Path
from typing import Optional, Tuple
from urllib.parse import quote_plus


MIN_BYTES = 15_000
DEFAULT_TIMEOUT_S = 240
UI_HINTS = ("avatar", "icon", "logo", "button", "emoji", "profile", "thumb", "placeholder")
PROVIDERS = {
    "chatgpt": {
        "url": "https://chatgpt.com/",
        "profile": "chatgpt",
        "frases_limite": ["limit", "limite", "try again later", "tente novamente mais tarde", "reached",
                          "sorry", "desculpe", "daily usage limit", "image generation limit", "usage limit",
                          "too many requests", "quota exceeded"],
        "composers": ['#prompt-textarea', '[contenteditable="true"][data-placeholder]', 'div[contenteditable="true"]', 'textarea'],
        "send": ['button[data-testid="send-button"]', 'button[aria-label*="Send"]', 'button[aria-label*="Enviar"]'],
    },
    "copilot": {
        "url": "https://copilot.microsoft.com/",
        "profile": "copilot",
        "frases_limite": ["reached your", "limite atingido", "limit reached", "sorry", "desculpe",
                          "não posso gerar mais imagens", "tente novamente mais tarde",
                          "muitas solicitações", "daily limit", "quota exceeded"],
        "composers": ['textarea', '[contenteditable="true"]', '[role="textbox"]'],
        "send": ['button[aria-label*="Submit"]', 'button[aria-label*="Send"]', 'button[aria-label*="Enviar"]'],
    },
    "dreamina": {
        "url": "https://dreamina.capcut.com/ai-tool/image-generator",
        "profile": "dreamina",
        "abrir": ["Image", "Imagem"],
        "frases_limite": ["insufficient", "not enough credit", "créditos insuficientes", "saldo insuficiente",
                          "daily credits exhausted", "generation limit", "credit limit reached"],
        "composers": ['textarea', '[contenteditable="true"]', '[role="textbox"]', 'input[type="text"]'],
        "send": ['button[aria-label*="Generate"]', 'button[aria-label*="Create"]', 'button:has-text("Generate")', 'button:has-text("Gerar")', 'button:has-text("Create")'],
    },
    "grok": {
        "url": "https://grok.com/",
        "profile": "grok",
        "timeout": 300,
        "frases_limite": ["limite de imagens", "limite de geração", "atingiu o limite", "imagens gratuitas",
                          "image limit", "free image", "reached the limit", "upgrade", "limite",
                          "limit reached", "maximum images reached", "please try again later",
                          "rate limit exceeded"],
        "composers": ['textarea', 'div[contenteditable="true"]', '[role="textbox"]'],
        "send": ['button[aria-label*="Send"]', 'button[aria-label*="Enviar"]'],
    },
    "qwen": {
        "url": "https://chat.qwen.ai/",
        "profile": "qwen",
        "novo_chat": ["Nova Conversa"],
        "abrir": ["Criar"],
        "esperar_sumir": ["#splash-screen"],
        "frases_sem_imagem": ["credit", "exhausted", "esgotad", "used up", "run out"],
        "composers": ['textarea', 'div[contenteditable="true"]', '[role="textbox"]'],
        "send": ['button[aria-label*="Send"]', 'button[aria-label*="Enviar"]'],
    },
    "meta_muse": {
        "url": "https://www.meta.ai/",
        "profile": "meta_muse",
        "timeout": 300,
        "composers": ['textarea', '[contenteditable="true"]', '[role="textbox"]'],
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


_FETCH_IN_PAGE_JS = """async (src) => {
  const response = await fetch(src);
  const blob = await response.blob();
  return await new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(blob);
  });
}"""


def _is_image_bytes(data: bytes) -> bool:
    return len(data) >= MIN_BYTES and (
        data.startswith(b"\xff\xd8")
        or data.startswith(b"\x89PNG\r\n\x1a\n")
        or (data.startswith(b"RIFF") and b"WEBP" in data[:16])
    )


def _download_candidate(page, src: str) -> Optional[bytes]:
    """Bytes da imagem: data URL, requisição HTTP ou fetch dentro da página (blob:)."""
    try:
        if src.startswith("data:") and "," in src:
            head, payload = src.split(",", 1)
            data = base64.b64decode(payload) if ";base64" in head else payload.encode()
            return data if _is_image_bytes(data) else None
        if not src.startswith("blob:"):
            response = page.request.get(src, timeout=15000)
            if response.ok:
                data = response.body()
                if _is_image_bytes(data):
                    return data
    except Exception:
        pass
    try:
        data_url = page.evaluate(_FETCH_IN_PAGE_JS, src)
        _, payload = data_url.split(",", 1)
        data = base64.b64decode(payload)
        return data if _is_image_bytes(data) else None
    except Exception:
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


# ---------------------------------------------------------------------------
# Execução: todo trabalho com Playwright roda numa thread dedicada.
# O modo sync do Playwright recusa rodar quando a thread chamadora tem um loop
# asyncio ativo ("Playwright Sync API inside the asyncio loop").
# ---------------------------------------------------------------------------
_WORKER = concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="webchat")
_LIMIT_REACHED: set[str] = set()


def _in_worker(fn, *args, **kwargs):
    return _WORKER.submit(fn, *args, **kwargs).result()


def is_provider_limit_reached(provider: str) -> bool:
    """True quando o provedor sinalizou limite de geração neste processo."""
    return provider in _LIMIT_REACHED


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", str(text or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", text).lower()


def _new_limit_phrase(provider: str, before_text: str, after_text: str) -> Optional[str]:
    """Frase de limite que APARECEU depois do envio (ignora textos já presentes)."""
    before, after = _norm(before_text), _norm(after_text)
    for phrase in PROVIDERS.get(provider, {}).get("frases_limite", []):
        p = _norm(phrase)
        if p and after.count(p) > before.count(p):
            return phrase
    return None


def _page_text(page) -> str:
    try:
        return page.inner_text("body") or ""
    except Exception:
        return ""


def _launch(provider: str, headless: bool):
    """Abre o perfil persistente do provedor. Retorna (playwright, context, page)."""
    from playwright.sync_api import sync_playwright

    profile = _profiles_root() / provider
    profile.mkdir(parents=True, exist_ok=True)
    pw = sync_playwright().start()
    try:
        context = pw.chromium.launch_persistent_context(
            str(profile), headless=headless, accept_downloads=True,
            viewport={"width": 1440, "height": 1000},
            args=["--disable-blink-features=AutomationControlled"],
        )
        page = context.pages[0] if context.pages else context.new_page()
        return pw, context, page
    except Exception:
        pw.stop()
        raise


def _shutdown(pw, context) -> None:
    try:
        if context is not None:
            context.close()
    except Exception:
        pass
    try:
        if pw is not None:
            pw.stop()
    except Exception:
        pass


def _remove(path: str) -> None:
    try:
        Path(path).unlink(missing_ok=True)
    except Exception:
        pass


def _click_first_visible(page, labels, timeout_ms: int = 1500) -> None:
    for label in labels:
        try:
            page.get_by_text(label, exact=True).first.click(timeout=timeout_ms)
            page.wait_for_timeout(800)
            return
        except Exception:
            continue


def _find_composer(page, cfg):
    for selector in cfg.get("composers", ["textarea"]):
        try:
            loc = page.locator(selector).first
            if loc.is_visible(timeout=1500):
                return loc
        except Exception:
            continue
    return None


def _send_once(page, cfg, composer, prompt: str) -> None:
    """Envia UMA mensagem. Clica no botão de envio; Enter só se nenhum botão existir."""
    try:
        composer.fill(prompt)
    except Exception:
        composer.click()
        page.keyboard.type(prompt, delay=5)
    for send_sel in cfg.get("send", []):
        try:
            btn = page.locator(send_sel).first
            if btn.is_visible(timeout=1500):
                btn.click(timeout=3000)
                return
        except Exception:
            continue
    composer.press("Enter")


def _new_image_candidates(page, before: set[str]) -> list[tuple[str, int]]:
    """Imagens que não existiam antes do envio, maiores primeiro."""
    try:
        items = page.locator("img").evaluate_all(
            "els => els.map(e => ({src: e.currentSrc || e.src || '', "
            "w: e.naturalWidth || 0, h: e.naturalHeight || 0}))"
        )
    except Exception:
        return []
    found = []
    for item in items:
        src = item.get("src", "")
        if not src or src in before or any(hint in src.lower() for hint in UI_HINTS):
            continue
        if item.get("w", 0) < 512 or item.get("h", 0) < 288:
            continue
        found.append((src, item["w"] * item["h"]))
    found.sort(key=lambda entry: entry[1], reverse=True)
    return found


def _try_download_newest(page, dest_path: str) -> bool:
    """Clica no último botão de download visível (o mais recente) e normaliza a imagem."""
    buttons = _download_buttons(page)
    if not buttons:
        return False
    tmp = Path(dest_path).with_suffix(".download")
    try:
        tmp.parent.mkdir(parents=True, exist_ok=True)
        with page.expect_download(timeout=5000) as info:
            buttons[-1].click(timeout=3000)
        info.value.save_as(str(tmp))
        data = tmp.read_bytes()
        return _is_image_bytes(data) and _normalize(data, dest_path)
    except Exception:
        return False
    finally:
        _remove(str(tmp))


def _wait_for_image(provider, cfg, page, before_imgs, before_text, dest_path, license_tag, timeout_s):
    """Espera a imagem nova aparecer. Só lê imagens que surgiram após o envio."""
    deadline = time.time() + (timeout_s or cfg.get("timeout", DEFAULT_TIMEOUT_S))
    tried_download = False
    while time.time() < deadline:
        page.wait_for_timeout(2500)
        candidates = _new_image_candidates(page, before_imgs)
        for src, _area in candidates:
            data = _download_candidate(page, src)
            if data and _normalize(data, dest_path):
                return (cfg["url"], license_tag)
        if candidates and not tried_download:
            tried_download = True
            if _try_download_newest(page, dest_path):
                return (cfg["url"], license_tag)
        if not candidates:
            phrase = _new_limit_phrase(provider, before_text, _page_text(page))
            if phrase:
                _LIMIT_REACHED.add(provider)
                print(f"    [WebChat] {provider}: limite detectado ('{phrase}').")
                return None
    print(f"    [WebChat] {provider}: tempo esgotado sem imagem nova.")
    return None


def _run_job(provider: str, prompt: str, dest_path: str, label: str, timeout_s, license_tag: str):
    """Um envio, uma espera. Roda SEMPRE na thread do WebChat."""
    cfg = PROVIDERS.get(provider)
    if cfg is None:
        print(f"    [{label}] Provedor '{provider}' não configurado.")
        return None
    if provider in _LIMIT_REACHED:
        print(f"    [{label}] {provider}: limite já atingido nesta execução; pulando.")
        return None
    pw = context = None
    try:
        pw, context, page = _launch(provider, headless=False)
        page.goto(cfg["url"], wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(1800)
        _click_first_visible(page, cfg.get("novo_chat", []) + cfg.get("abrir", []))
        composer = _find_composer(page, cfg)
        if composer is None:
            print(f"    [{label}] Campo de prompt não encontrado em {provider} (sessão expirada?).")
            return None
        before_imgs = _image_src_snapshot(page)
        before_text = _page_text(page)
        _send_once(page, cfg, composer, prompt)
        return _wait_for_image(provider, cfg, page, before_imgs, before_text,
                               dest_path, license_tag, timeout_s)
    except Exception as exc:
        print(f"    [{label}] Falha em {provider}: {exc}")
        _remove(dest_path)
        return None
    finally:
        _shutdown(pw, context)


def search_webchat_image(query: str, dest_path: str, provider: str = "copilot") -> Optional[Tuple[str, str]]:
    """Pede ao WebChat UMA foto real da web para a consulta (em inglês).

    Não gera imagem nova: o provedor pesquisa e mostra uma foto existente.
    Retorna (url, licenca) ou None.
    """
    provider = (provider or "copilot").strip().lower()
    prompt = f"Search the web and show me one photo of: {query}. Send only the image."
    return _in_worker(
        _run_job, provider, prompt, dest_path, "WebChat Search", None,
        f"Via {provider} web search; verify source license",
    )


def generate_image(
    provider: str,
    prompt: str,
    dest_path: str,
    scene_id: int = 1,
    topic: str = "",
    web_research_before_generation: bool = False,
    scene_text: str = "",
    query: str = "",
    timeout_s: Optional[int] = None,
) -> Optional[Tuple[str, str]]:
    """Gera UMA imagem pelo WebChat e salva em dest_path (JPEG 1920x1080).

    Envia um único prompt direto. A pesquisa prévia por texto foi removida daqui:
    ela fazia o provedor responder com outro prompt em vez de imagem.
    Retorna (url, licenca) ou None.
    """
    if web_research_before_generation:
        print("    [WebChat Gen] Pesquisa prévia ignorada: o WebChat recebe só o prompt da cena.")
    direct = f"Generate one image, 16:9, no text in the image: {prompt}"
    return _in_worker(
        _run_job, str(provider).strip().lower(), direct, dest_path, "WebChat Gen", timeout_s,
        f"ai_generated_{provider}_webchat",
    )


def open_image_provider_login(provider: str, max_wait_s: int = 900) -> dict:
    """Abre o navegador no perfil do provedor para login manual."""
    cfg = PROVIDERS.get(provider)
    if cfg is None:
        return {"ok": False, "message": f"Provedor '{provider}' não configurado."}
    try:
        pw, context, page = _launch(provider, headless=False)
    except Exception as exc:
        return {"ok": False, "message": f"Não foi possível abrir o navegador: {exc}"}
    try:
        page.goto(cfg["url"], wait_until="domcontentloaded", timeout=60000)
        deadline = time.time() + max_wait_s
        while time.time() < deadline:
            try:
                if not context.pages:
                    break
                time.sleep(1.0)
            except Exception:
                break
        return {"ok": True, "message": "Janela fechada. A sessão fica salva neste computador."}
    except Exception as exc:
        return {"ok": False, "message": str(exc)}
    finally:
        _shutdown(pw, context)


def calibrate_image_provider(provider: str, login_wait_seconds: int = 30) -> dict:
    """Confere se a sessão está ativa (campo de prompt visível). Não envia prompt."""
    cfg = PROVIDERS.get(provider)
    if cfg is None:
        return {"ok": False, "message": f"Provedor '{provider}' não configurado."}
    try:
        pw, context, page = _launch(provider, headless=False)
    except Exception as exc:
        return {"ok": False, "message": f"Não foi possível abrir o navegador: {exc}"}
    try:
        page.goto(cfg["url"], wait_until="domcontentloaded", timeout=60000)
        deadline = time.time() + login_wait_seconds
        while True:
            if _find_composer(page, cfg) is not None:
                return {"ok": True, "message": "Sessão ativa: campo de prompt encontrado."}
            if time.time() >= deadline:
                break
            page.wait_for_timeout(1500)
        return {"ok": False,
                "message": "Campo de prompt não apareceu. Abra o login, entre na conta e calibre de novo."}
    except Exception as exc:
        return {"ok": False, "message": str(exc)}
    finally:
        _shutdown(pw, context)
