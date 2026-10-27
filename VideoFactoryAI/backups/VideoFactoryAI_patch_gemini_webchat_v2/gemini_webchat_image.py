"""Integração conservadora de geração/avaliação de imagens via interface web do Gemini.

Não usa API paga. Usa Playwright e um perfil de navegador dedicado persistente.
Na primeira execução, faça login manualmente na conta Google nessa janela.

Variáveis:
  VF_GEMINI_PROFILE_DIR: diretório do perfil persistente (padrão ~/.videofactory_gemini_profile)
  VF_GEMINI_URL: URL da aplicação Gemini (padrão https://gemini.google.com/app)
  VF_GEMINI_TIMEOUT: tempo máximo de espera por resposta, em segundos (padrão 180)

A UI do Gemini pode mudar; se os seletores não funcionarem, a função falha explicitamente.
Nunca cria imagens sintéticas/placeholder para simular geração.
"""
from __future__ import annotations
import base64
import json
import os
import re
import time
from pathlib import Path
from typing import Optional, Tuple, Dict, Any

MIN_BYTES = 15_000


def _profile_dir() -> Path:
    return Path(os.environ.get("VF_GEMINI_PROFILE_DIR", str(Path.home() / ".videofactory_gemini_profile"))).expanduser().resolve()


def _timeout_ms() -> int:
    try:
        return max(30, int(os.environ.get("VF_GEMINI_TIMEOUT", "180"))) * 1000
    except Exception:
        return 180_000


def _open_gemini():
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        raise RuntimeError("Playwright não está instalado no ambiente Python do VideoFactoryAI.") from exc
    pw = sync_playwright().start()
    profile = _profile_dir()
    profile.mkdir(parents=True, exist_ok=True)
    try:
        context = pw.chromium.launch_persistent_context(
            user_data_dir=str(profile), headless=False, accept_downloads=True,
            viewport={"width": 1440, "height": 1000},
            args=["--disable-blink-features=AutomationControlled"],
        )
    except Exception:
        pw.stop()
        raise
    page = context.pages[0] if context.pages else context.new_page()
    page.goto(os.environ.get("VF_GEMINI_URL", "https://gemini.google.com/app"), wait_until="domcontentloaded", timeout=60_000)
    page.wait_for_timeout(1500)
    return pw, context, page


def _find_composer(page):
    selectors = [
        'rich-textarea [contenteditable="true"]',
        'div[contenteditable="true"][role="textbox"]',
        'div[contenteditable="true"]',
        'textarea',
    ]
    for sel in selectors:
        loc = page.locator(sel).last
        try:
            if loc.count() and loc.is_visible(timeout=800):
                return loc
        except Exception:
            continue
    return None


def _send_prompt(page, prompt: str) -> None:
    composer = _find_composer(page)
    if composer is None:
        if "accounts.google.com" in page.url or "Sign in" in page.title():
            raise RuntimeError("O Gemini exige login. Faça login na janela aberta e execute novamente.")
        raise RuntimeError("Não encontrei o campo de mensagem do Gemini; a interface pode ter mudado.")
    composer.click(timeout=5000)
    composer.fill(prompt, timeout=5000)
    # Prioriza botão de envio visível; Enter é o fallback da interface.
    sent = False
    for sel in ['button[aria-label*="Send"]', 'button[aria-label*="Enviar"]', 'button[data-test-id*="send"]']:
        try:
            btn = page.locator(sel).last
            if btn.count() and btn.is_visible(timeout=500):
                btn.click(timeout=2500)
                sent = True
                break
        except Exception:
            pass
    if not sent:
        composer.press("Enter", timeout=3000)


def _image_src_snapshot(page) -> set[str]:
    """Captura URLs já presentes antes da ação atual para evitar reutilizar imagem antiga."""
    try:
        return set(page.locator("img").evaluate_all("els => els.map(e => e.currentSrc || e.src || '').filter(Boolean)"))
    except Exception:
        return set()


def _extract_image_bytes(page, exclude_srcs: Optional[set[str]] = None,
                         download_button_start: int = 0) -> Optional[bytes]:
    """Recupera bytes de uma imagem nova, ignorando imagens que já existiam na página."""
    exclude_srcs = exclude_srcs or set()
    # Primeiro tenta botões de download adicionados após a solicitação atual.
    for sel in ['button[aria-label*="Download"]', 'button[aria-label*="download"]', 'button[title*="Download"]', 'button[title*="download"]']:
        try:
            buttons = page.locator(sel)
            for i in range(buttons.count() - 1, max(-1, download_button_start - 1), -1):
                btn = buttons.nth(i)
                if not btn.is_visible(timeout=250):
                    continue
                try:
                    with page.expect_download(timeout=2500) as info:
                        btn.click(timeout=1500)
                    download = info.value
                    tmp = Path(download.suggested_filename or "gemini_image.bin")
                    temp_path = _profile_dir() / ("download_" + str(int(time.time() * 1000)) + tmp.suffix)
                    download.save_as(str(temp_path))
                    data = temp_path.read_bytes()
                    temp_path.unlink(missing_ok=True)
                    if len(data) >= MIN_BYTES:
                        return data
                except Exception:
                    continue
        except Exception:
            continue

    # Fallback: lê src de imagens grandes da resposta e baixa os bytes originais.
    candidates = []
    try:
        imgs = page.locator("img")
        count = imgs.count()
        for i in range(max(0, count - 30), count):
            img = imgs.nth(i)
            try:
                meta = img.evaluate("e => ({src:e.currentSrc||e.src||'', w:e.naturalWidth||0, h:e.naturalHeight||0, alt:e.alt||''})")
                if (meta["w"] >= 768 and meta["h"] >= 432 and meta["src"]
                        and meta["src"] not in exclude_srcs):
                    candidates.append(meta)
            except Exception:
                pass
    except Exception:
        pass
    candidates.sort(key=lambda x: x["w"] * x["h"], reverse=True)
    for item in candidates:
        src = item["src"]
        try:
            if src.startswith("data:") and "," in src:
                head, payload = src.split(",", 1)
                data = base64.b64decode(payload) if ";base64" in head else payload.encode()
            else:
                response = page.request.get(src, timeout=15_000)
                if not response.ok:
                    continue
                data = response.body()
            if len(data) >= MIN_BYTES and (data[:2] == b"\xff\xd8" or data.startswith(b"\x89PNG\r\n\x1a\n")):
                return data
        except Exception:
            continue
    return None


def _normalize_image(data: bytes, dest_path: str) -> bool:
    """Confirma bytes de imagem e converte/corta para Full HD 1920x1080."""
    try:
        from PIL import Image, ImageOps
        import io
        img = Image.open(io.BytesIO(data))
        img.load()
        if img.width < 768 or img.height < 432:
            return False
        img = img.convert("RGB")
        # Crop central 16:9 preservando conteúdo real, sem desenhar texto/artefatos.
        img = ImageOps.fit(img, (1920, 1080), method=Image.Resampling.LANCZOS, centering=(0.5, 0.5))
        dest = Path(dest_path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        img.save(dest, "JPEG", quality=94, optimize=True)
        return dest.exists() and dest.stat().st_size >= MIN_BYTES
    except Exception:
        return False


def generate_image(prompt: str, dest_path: str, scene_id: int = 1, topic: str = "") -> Optional[Tuple[str, str]]:
    """Solicita ao Gemini uma imagem e grava os bytes reais em dest_path."""
    pw = context = page = None
    try:
        pw, context, page = _open_gemini()
        instruction = (
            "Gere uma imagem visual original para um vídeo documental. "
            "Use composição horizontal 16:9, alvo Full HD 1920x1080. "
            "Não inclua palavras, letras, legendas, logotipos nem marcas d'água. "
            "Retrate o assunto descrito sem acrescentar estilo cinematográfico obrigatório.\n\n"
            f"Tópico do vídeo: {topic or 'não especificado'}\n"
            f"Cena {scene_id:02d}: {prompt}\n"
            f"Estilo opcional: {os.environ.get('VF_IMAGE_STYLE', '').strip()}\n"
            f"Modificadores técnicos opcionais: {os.environ.get('VF_IMAGE_STYLE_MODIFIERS', '').strip()}\n\n"
            "Se os campos de estilo estiverem vazios, priorize apenas o assunto e a necessidade da cena. "
            "Preciso de uma imagem gerada, não de uma descrição textual."
        )
        # Snapshot antes de enviar: não confundir imagens antigas do histórico com a nova geração.
        prior_image_srcs = _image_src_snapshot(page)
        prior_download_count = 0
        for download_sel in ['button[aria-label*="Download"]', 'button[aria-label*="download"]', 'button[title*="Download"]', 'button[title*="download"]']:
            try:
                prior_download_count = max(prior_download_count, page.locator(download_sel).count())
            except Exception:
                pass
        _send_prompt(page, instruction)
        deadline = time.monotonic() + _timeout_ms() / 1000
        data = None
        last_count = -1
        stable = 0
        while time.monotonic() < deadline:
            page.wait_for_timeout(1500)
            data = _extract_image_bytes(page, exclude_srcs=prior_image_srcs,
                                        download_button_start=prior_download_count)
            if data:
                break
            try:
                count = page.locator("img").count()
                stable = stable + 1 if count == last_count else 0
                last_count = count
            except Exception:
                pass
        if not data:
            raise RuntimeError("Gemini não expôs um arquivo de imagem baixável. Nenhum placeholder foi criado.")
        if not _normalize_image(data, dest_path):
            raise RuntimeError("O conteúdo retornado pelo Gemini não passou na validação de imagem/Full HD.")
        return ("https://gemini.google.com/app", "ai_generated_gemini_webchat")
    except Exception as exc:
        print(f"    [GeminiWebchat] Geração falhou: {exc}")
        try:
            Path(dest_path).unlink(missing_ok=True)
        except Exception:
            pass
        return None
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


def evaluate_image(image_path: str, scene_text: str, query_used: str = "", scene_id: int = 1, topic: str = "") -> Optional[Dict[str, Any]]:
    """Anexa o arquivo real ao Gemini e exige resposta JSON de avaliação visual."""
    pw = context = page = None
    try:
        path = Path(image_path)
        if not path.is_file() or path.stat().st_size < MIN_BYTES:
            raise RuntimeError("Arquivo de imagem ausente ou pequeno demais.")
        pw, context, page = _open_gemini()
        # O Gemini normalmente oferece um input file oculto para anexos.
        file_inputs = page.locator('input[type="file"]')
        attached = False
        for i in range(file_inputs.count()):
            try:
                file_inputs.nth(i).set_input_files(str(path), timeout=5000)
                attached = True
                break
            except Exception:
                continue
        if not attached:
            # Tenta abrir o menu de anexos, que pode criar o input de arquivo.
            for sel in ['button[aria-label*="Attach"]', 'button[aria-label*="Anexar"]', 'button[aria-label*="Add files"]']:
                try:
                    btn = page.locator(sel).last
                    if btn.count() and btn.is_visible(timeout=500):
                        btn.click(timeout=1500)
                        page.wait_for_timeout(500)
                        break
                except Exception:
                    pass
            file_inputs = page.locator('input[type="file"]')
            for i in range(file_inputs.count()):
                try:
                    file_inputs.nth(i).set_input_files(str(path), timeout=5000)
                    attached = True
                    break
                except Exception:
                    continue
        if not attached:
            raise RuntimeError("Não foi possível anexar os bytes da imagem à conversa do Gemini.")
        page.wait_for_timeout(1000)
        # Registra as respostas existentes para nunca aceitar por engano um JSON antigo.
        prior_response_texts = set()
        response_selectors = ['model-response', 'message-content', '[data-message-author-role="model"]', '.response-container']
        for response_sel in response_selectors:
            try:
                prior_response_texts.update(t.strip() for t in page.locator(response_sel).all_inner_texts() if t.strip())
            except Exception:
                pass

        prompt = (
            "Analise visualmente a IMAGEM ANEXADA (não avalie apenas o texto). Compare-a com a cena abaixo. "
            "Responda SOMENTE JSON válido com as chaves approved (boolean), score (0-100), reason (string), suggestions (array de strings). "
            "approved=true somente se a imagem mostrar visualmente o assunto/ação principal da cena; não aprove só por semelhança de palavras.\n"
            f"Tópico: {topic}\nCena {scene_id:02d}: {scene_text}\nConsulta de busca/prompt: {query_used}\n"
        )
        _send_prompt(page, prompt)
        deadline = time.monotonic() + _timeout_ms() / 1000
        last_text = ""
        while time.monotonic() < deadline:
            page.wait_for_timeout(1200)
            # Resposta textual mais recente da página; não inclui o prompt enviado quando possível.
            for sel in response_selectors:
                try:
                    loc = page.locator(sel).last
                    if loc.count():
                        txt = loc.inner_text(timeout=1000).strip()
                        if txt and txt != last_text and txt not in prior_response_texts:
                            last_text = txt
                except Exception:
                    pass
            m = re.search(r"\{[\s\S]*?\"approved\"\s*:\s*(?:true|false)[\s\S]*?\}", last_text, re.I)
            if m:
                try:
                    obj = json.loads(m.group(0))
                    if isinstance(obj.get("approved"), bool) and isinstance(obj.get("score"), (int, float)):
                        obj["score"] = max(0, min(100, int(obj["score"])))
                        obj.setdefault("reason", "Avaliação visual Gemini")
                        obj.setdefault("suggestions", [])
                        return obj
                except Exception:
                    pass
        raise RuntimeError("Gemini não retornou JSON válido de avaliação visual.")
    except Exception as exc:
        print(f"    [GeminiWebchat] Avaliação visual falhou: {exc}")
        return None
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
