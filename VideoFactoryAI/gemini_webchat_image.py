"""Integração conservadora com Gemini Web para gerar/avaliar imagens.
Recupera downloads explícitos primeiro e só aceita imagens recentes e válidas.
Não cria placeholders. Requer Playwright e login manual no perfil persistente.
"""
from __future__ import annotations

import base64
import atexit
import json
import os
import re
import threading
import time
import unicodedata
from pathlib import Path
from typing import Optional, Tuple, Dict, Any

from webchat_research import (
    build_image_prompt,
    research_visual_description,
)

MIN_BYTES = 15_000
IMAGE_LIMIT_PATTERNS = (
    "quota exceeded",
    "rate limit",
    "resource exhausted",
    "daily limit",
    "image generation limit",
    "generation limit",
    "too many requests",
    "429",
    "try again later",
    "image generation unavailable",
    "nao posso gerar mais imagens",
    "limite atingido",
    "limite de imagens",
    "limite de geracao",
    "muitas solicitacoes",
)

_GEMINI_SESSION = None
_GEMINI_SESSION_LOCK = threading.RLock()


def _normalize_limit_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(text or ""))
    normalized = "".join(char for char in normalized if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", normalized).lower()


def _new_image_limit_message(before_text: str, after_text: str) -> Optional[str]:
    before = _normalize_limit_text(before_text)
    after = _normalize_limit_text(after_text)
    for pattern in IMAGE_LIMIT_PATTERNS:
        if after.count(pattern) > before.count(pattern):
            return pattern
    return None


class GeminiSessionError(RuntimeError):
    """A sessão do navegador foi encerrada ou deixou de estar utilizável."""


def _profile_dir() -> Path:
    return Path(os.environ.get(
        "VF_GEMINI_PROFILE_DIR",
        str(Path.home() / ".videofactory_gemini_profile")
    )).expanduser().resolve()


def _timeout_ms() -> int:
    try:
        return max(30, int(os.environ.get("VF_GEMINI_TIMEOUT", "180"))) * 1000
    except Exception:
        return 180_000


def _start_playwright():
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        raise RuntimeError("Playwright não está instalado no ambiente Python do VideoFactoryAI.") from exc
    return sync_playwright().start()


def _navigate_gemini(page):
    page.goto(
        os.environ.get("VF_GEMINI_URL", "https://gemini.google.com/app"),
        wait_until="domcontentloaded",
        timeout=60_000,
    )
    page.wait_for_timeout(1800)


def _open_gemini():
    global _GEMINI_SESSION
    owner_thread = threading.get_ident()
    with _GEMINI_SESSION_LOCK:
        if _GEMINI_SESSION is not None:
            pw, context, session_thread, _keeper_page = _GEMINI_SESSION
            if session_thread != owner_thread:
                raise GeminiSessionError(
                    "A sessão Playwright do Gemini não pode ser compartilhada entre threads."
                )
            try:
                if context.browser is not None:
                    page = context.new_page()
                    _navigate_gemini(page)
                    return pw, context, page
            except Exception as exc:
                if "closed" not in str(exc).lower():
                    raise
            close_gemini_session()

        pw = _start_playwright()
        context = None
        try:
            profile = _profile_dir()
            profile.mkdir(parents=True, exist_ok=True)
            context = pw.chromium.launch_persistent_context(
                user_data_dir=str(profile),
                headless=False,
                accept_downloads=True,
                viewport={"width": 1440, "height": 1000},
                args=["--disable-blink-features=AutomationControlled"],
            )
            keeper_page = context.pages[0] if context.pages else context.new_page()
            _navigate_gemini(keeper_page)
            page = context.new_page()
            _GEMINI_SESSION = (pw, context, owner_thread, keeper_page)
            _navigate_gemini(page)
            return pw, context, page
        except Exception:
            if context is not None:
                try:
                    context.close()
                finally:
                    pw.stop()
            else:
                pw.stop()
            _GEMINI_SESSION = None
            raise


def _close_gemini_at_exit():
    try:
        close_gemini_session()
    except Exception as exc:
        print(f"[GeminiWebchat] Falha ao encerrar navegador: {exc}")


def _close_gemini_page(page):
    if page is None:
        return
    try:
        if not page.is_closed():
            page.close()
    except Exception as exc:
        print(f"[GeminiWebchat] Falha ao fechar aba da conversa: {exc}")


def close_gemini_session():
    """Encerra o navegador persistente, usado uma vez ao final do processo."""
    global _GEMINI_SESSION
    with _GEMINI_SESSION_LOCK:
        session = _GEMINI_SESSION
        _GEMINI_SESSION = None
        if session is None:
            return
        pw, context, owner_thread, _keeper_page = session
        if owner_thread != threading.get_ident():
            _GEMINI_SESSION = session
            raise GeminiSessionError(
                "A sessão Playwright do Gemini deve ser encerrada pela thread que a criou."
            )

        errors = []
        try:
            context.close()
        except Exception as exc:
            errors.append(f"contexto: {exc}")
        try:
            pw.stop()
        except Exception as exc:
            errors.append(f"Playwright: {exc}")
        if errors:
            raise RuntimeError("Não foi possível encerrar a sessão Gemini (" + "; ".join(errors) + ").")


atexit.register(_close_gemini_at_exit)


def _ensure_session_active(context, page) -> None:
    """Fail before issuing another Playwright operation on a closed session."""
    try:
        if page is None or page.is_closed() or context is None or context.browser is None:
            raise GeminiSessionError("A página ou o navegador do Gemini já foi encerrado.")
    except GeminiSessionError:
        raise
    except Exception as exc:
        raise GeminiSessionError(f"Não foi possível confirmar a sessão do Gemini: {exc}") from exc


def _find_composer(page):
    for sel in [
        'rich-textarea [contenteditable="true"]',
        'div[contenteditable="true"][role="textbox"]',
        'div[contenteditable="true"]',
        'textarea',
    ]:
        try:
            loc = page.locator(sel).last
            if loc.count() and loc.is_visible(timeout=800):
                return loc
        except Exception:
            continue
    return None


def _send_prompt(page, prompt: str) -> None:
    if page.is_closed():
        raise GeminiSessionError("A página do Gemini foi encerrada antes do envio do prompt.")
    composer = _find_composer(page)
    if composer is None:
        if "accounts.google.com" in page.url or "Sign in" in page.title():
            raise RuntimeError("O Gemini exige login. Faça login na janela aberta e execute novamente.")
        raise RuntimeError("Não encontrei o campo de mensagem do Gemini; a interface pode ter mudado.")
    composer.click(timeout=5000)
    composer.fill(prompt, timeout=5000)
    for sel in [
        'button[aria-label*="Send"]',
        'button[aria-label*="Enviar"]',
        'button[data-test-id*="send"]',
    ]:
        try:
            btn = page.locator(sel).last
            if btn.count() and btn.is_visible(timeout=500):
                btn.click(timeout=2500)
                return
        except Exception:
            pass
    composer.press("Enter", timeout=3000)


def _image_src_snapshot(page) -> set[str]:
    try:
        return set(page.locator("img").evaluate_all(
            "(els) => els.map(e => e.currentSrc || e.src || '').filter(Boolean)"
        ))
    except Exception:
        return set()


def _download_buttons(page):
    selectors = [
        'button[aria-label*="Download"]',
        'button[aria-label*="download"]',
        'button[aria-label*="Baixar"]',
        'button[title*="Download"]',
        'button[title*="Baixar"]',
    ]
    found = []
    seen = set()
    for sel in selectors:
        try:
            loc = page.locator(sel)
            for i in range(loc.count()):
                item = loc.nth(i)
                try:
                    if not item.is_visible(timeout=150):
                        continue
                    box = item.bounding_box()
                    key = (round(box["x"]), round(box["y"])) if box else (sel, i)
                    if key not in seen:
                        seen.add(key)
                        found.append(item)
                except Exception:
                    continue
        except Exception:
            continue
    return found


def _bytes_are_image(data: bytes) -> bool:
    return bool(
        data and len(data) >= MIN_BYTES and (
            data.startswith(b"\xff\xd8\xff") or
            data.startswith(b"\x89PNG\r\n\x1a\n") or
            (len(data) > 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP")
        )
    )


def _extract_image_bytes(page, exclude_srcs=None, download_button_start=0):
    """Tenta o download explícito de controles recentes e depois imagens novas."""
    exclude_srcs = exclude_srcs or set()

    # Método preferencial: botão de download criado/atualizado após o pedido.
    buttons = _download_buttons(page)
    for item in reversed(buttons[max(0, download_button_start):]):
        try:
            with page.expect_download(timeout=4500) as info:
                item.click(timeout=2500)
            download = info.value
            suggested = download.suggested_filename or "gemini_image.png"
            suffix = Path(suggested).suffix.lower()
            if suffix not in {".png", ".jpg", ".jpeg", ".webp"}:
                suffix = ".png"
            tmp_dir = _profile_dir() / "downloads"
            tmp_dir.mkdir(parents=True, exist_ok=True)
            tmp_path = tmp_dir / f"vf_gemini_{time.time_ns()}{suffix}"
            download.save_as(str(tmp_path))
            try:
                data = tmp_path.read_bytes()
            finally:
                tmp_path.unlink(missing_ok=True)
            if _bytes_are_image(data):
                return data
        except Exception:
            continue

    # Fallback: apenas imagens novas, suficientemente grandes e recuperáveis.
    try:
        imgs = page.locator("img")
        count = imgs.count()
    except Exception:
        return None
    candidates = []
    for i in range(max(0, count - 50), count):
        try:
            img = imgs.nth(i)
            meta = img.evaluate("""e => ({
                src: e.currentSrc || e.src || '',
                w: e.naturalWidth || 0,
                h: e.naturalHeight || 0
            })""")
            src = meta.get("src", "")
            if not src or src in exclude_srcs:
                continue
            if int(meta.get("w", 0)) < 768 or int(meta.get("h", 0)) < 432:
                continue
            candidates.append((int(meta["w"]) * int(meta["h"]), src))
        except Exception:
            continue
    candidates.sort(reverse=True)
    for _, src in candidates:
        try:
            if src.startswith("data:image/") and "," in src:
                header, payload = src.split(",", 1)
                data = base64.b64decode(payload) if ";base64" in header else payload.encode()
            else:
                response = page.request.get(src, timeout=15000)
                if not response.ok:
                    continue
                data = response.body()
            if _bytes_are_image(data):
                return data
        except Exception:
            continue
    return None


def _normalize_image(data: bytes, dest_path: str) -> bool:
    try:
        from PIL import Image, ImageOps
        import io
        with Image.open(io.BytesIO(data)) as src:
            src.load()
            if src.width < 768 or src.height < 432:
                return False
            image = ImageOps.exif_transpose(src).convert("RGB")
            image = ImageOps.fit(
                image, (1920, 1080), method=Image.Resampling.LANCZOS,
                centering=(0.5, 0.5),
            )
            target = Path(dest_path)
            target.parent.mkdir(parents=True, exist_ok=True)
            image.save(target, format="JPEG", quality=94, optimize=True)
        return Path(dest_path).is_file() and Path(dest_path).stat().st_size >= MIN_BYTES
    except Exception as exc:
        print(f"[GeminiWebchat] Não foi possível normalizar a imagem: {exc}")
        return False


def _response_snapshot(page) -> set[str]:
    selectors = [
        "model-response",
        "message-content",
        '[data-message-author-role="model"]',
        ".response-container",
    ]
    texts = set()
    for selector in selectors:
        try:
            items = page.locator(selector)
            for index in range(max(0, items.count() - 8), items.count()):
                text = items.nth(index).inner_text(timeout=300).strip()
                if text:
                    texts.add(text)
        except Exception:
            continue
    return texts


def _wait_for_research_response(page, before: set[str]) -> str:
    deadline = time.monotonic() + 35
    while time.monotonic() < deadline:
        page.wait_for_timeout(800)
        for text in reversed(list(_response_snapshot(page))):
            if text not in before and len(text.strip()) >= 20:
                return text
    raise TimeoutError("Gemini não retornou uma descrição após a pesquisa web.")


def generate_image(
    prompt,
    dest_path,
    scene_id=1,
    topic="",
    web_research_before_generation=False,
    scene_text="",
    query="",
):
    pw = context = page = None
    try:
        pw, context, page = _open_gemini()
        before_research_text = page.inner_text("body") or ""
        if web_research_before_generation:
            before_research = _response_snapshot(page)
            research_summary = research_visual_description(
                scene_text=scene_text or prompt,
                query=query or prompt,
                topic=topic,
                send_prompt=lambda research_prompt: _send_prompt(page, research_prompt),
                wait_for_response=lambda: _wait_for_research_response(page, before_research),
            )
            limit_message = _new_image_limit_message(
                before_research_text, page.inner_text("body") or ""
            )
            if limit_message:
                raise RuntimeError(f"Gemini image generation limit reached: {limit_message}")
            if research_summary:
                prompt = build_image_prompt(prompt, research_summary)
        # Exclui thumbnails/resultados da pesquisa para aceitar somente a imagem gerada.
        prior_srcs = _image_src_snapshot(page)
        prior_button_count = len(_download_buttons(page))
        # Um único prompt direto: sem tema, cena ou texto extra que o modelo possa
        # responder com outro prompt em vez de imagem.
        instruction = f"Gere uma imagem 16:9, sem texto na imagem: {prompt}"
        style = os.environ.get("VF_IMAGE_STYLE", "").strip()
        modifiers = os.environ.get("VF_IMAGE_STYLE_MODIFIERS", "").strip()
        if style:
            instruction += f"\nEstilo opcional configurado: {style}.\n"
        if modifiers:
            instruction += f"Modificadores opcionais: {modifiers}.\n"
        before_generation_text = page.inner_text("body") or ""
        _send_prompt(page, instruction)
        deadline = time.monotonic() + (_timeout_ms() / 1000)
        data = None
        last_count = -1
        while time.monotonic() < deadline:
            _ensure_session_active(context, page)
            try:
                page.wait_for_timeout(1200)
            except Exception as exc:
                message = str(exc)
                if any(term in message.lower() for term in ("target page", "context or browser", "has been closed", "closed")):
                    raise GeminiSessionError(f"Sessão do Gemini encerrada durante a espera: {message}") from exc
                raise
            limit_message = _new_image_limit_message(
                before_generation_text, page.inner_text("body") or ""
            )
            if limit_message:
                raise RuntimeError(f"Gemini image generation limit reached: {limit_message}")
            try:
                current_count = page.locator("img").count()
                # Só começa a tentar extrair depois de algum sinal de mudança na UI.
                if current_count != last_count:
                    last_count = current_count
            except Exception:
                pass
            data = _extract_image_bytes(
                page, exclude_srcs=prior_srcs,
                download_button_start=prior_button_count,
            )
            if data:
                break
        if not data:
            raise RuntimeError(
                "Gemini não expôs um arquivo de imagem baixável dentro do prazo. "
                "A cena deve ser tentada por outra fonte; nenhum placeholder foi criado."
            )
        if not _normalize_image(data, dest_path):
            raise RuntimeError("O arquivo recuperado não passou na validação/normalização da imagem.")
        return ("https://gemini.google.com/app", "ai_generated_gemini_webchat")
    except Exception as exc:
        print(f"[GeminiWebchat] Geração falhou: {exc}")
        try:
            Path(dest_path).unlink(missing_ok=True)
        except Exception:
            pass
        if isinstance(exc, GeminiSessionError):
            raise
        if any(term in str(exc).lower() for term in ("target page", "context or browser", "has been closed")):
            raise GeminiSessionError(f"Sessão do Gemini indisponível: {exc}") from exc
        return None
    finally:
        _close_gemini_page(page)


def _extract_eval_object(text: str):
    """Extrai o último objeto JSON válido da resposta, inclusive se vier em bloco ```json."""
    decoder = json.JSONDecoder()
    found = []
    for match in re.finditer(r"\{", text):
        try:
            obj, end = decoder.raw_decode(text[match.start():])
            if isinstance(obj, dict) and isinstance(obj.get("approved"), bool):
                found.append(obj)
        except Exception:
            continue
    return found[-1] if found else None


def _log_eval_debug(scene_id: int, raw_text: str, parsed: dict | None, error: str = "") -> None:
    """Registra diagnóstico local para investigar notas/justificativas contraditórias."""
    try:
        log_path = Path(__file__).resolve().parent / "logs" / "gemini_eval_debug.jsonl"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "scene_id": scene_id,
            "raw_response": (raw_text or "")[-12000:],
            "parsed": parsed,
            "error": error,
        }
        with log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as exc:
        print(f"[ImageEval/Gemini] Não foi possível gravar diagnóstico: {exc}")


def evaluate_image(image_path, scene_text, query_used="", scene_id=1, topic=""):
    """Anexa a imagem ao Gemini e retorna avaliação estruturada; falha = None."""
    pw = context = page = None
    try:
        path = Path(image_path)
        if not path.is_file() or path.stat().st_size < MIN_BYTES:
            raise RuntimeError("Arquivo de imagem ausente ou pequeno demais.")
        # Validar que PIL consegue decodificar antes de abrir navegador.
        from PIL import Image
        with Image.open(path) as im:
            im.verify()

        pw, context, page = _open_gemini()
        before = set()
        for sel in ['model-response', 'message-content', '[data-message-author-role="model"]', '.response-container']:
            try:
                loc = page.locator(sel)
                for i in range(loc.count()):
                    try:
                        before.add(loc.nth(i).inner_text(timeout=250))
                    except Exception:
                        pass
            except Exception:
                pass

        attached = False
        try:
            inputs = page.locator('input[type="file"]')
            if inputs.count():
                inputs.last.set_input_files(str(path), timeout=5000)
                attached = True
        except Exception:
            pass
        if not attached:
            for sel in [
                'button[aria-label*="Attach"]',
                'button[aria-label*="Anexar"]',
                'button[aria-label*="Add files"]',
                'button[aria-label*="Adicionar arquivos"]',
            ]:
                try:
                    btn = page.locator(sel).last
                    if btn.count() and btn.is_visible(timeout=500):
                        btn.click(timeout=2000)
                        page.wait_for_timeout(350)
                        inputs = page.locator('input[type="file"]')
                        if inputs.count():
                            inputs.last.set_input_files(str(path), timeout=5000)
                            attached = True
                            break
                except Exception:
                    continue
        if not attached:
            raise RuntimeError("Não foi possível anexar os bytes da imagem à conversa do Gemini.")

        # Aguarda o preview do anexo aparecer, sem assumir que set_input_files basta.
        preview_deadline = time.monotonic() + 12
        while time.monotonic() < preview_deadline:
            try:
                preview_count = page.locator(
                    'img[src^="blob:"], img[src^="data:"], [data-test-id*="file"], [aria-label*="Remove attachment"]'
                ).count()
                if preview_count:
                    break
            except Exception:
                pass
            page.wait_for_timeout(400)

        threshold = 65
        try:
            threshold = max(0, min(100, int(os.environ.get("VF_IMAGE_EVAL_MIN_SCORE", "65"))))
        except Exception:
            pass
        prompt = (
            "Avalie SOMENTE a imagem anexada, comparando-a com os requisitos visuais da cena. "
            "A hierarquia é obrigatória: o TEMA e o conteúdo da CENA definem o assunto principal; "
            "a CONSULTA ORIGINAL é apenas uma pista de busca e nunca basta para aprovar. "
            "Se a imagem corresponder à consulta mas não ao tema/assunto da cena, marque approved=false "
            "e limite o score a 35. Não aprove uma imagem genérica apenas por representar uma metáfora "
            "ou conceito citado na consulta quando o roteiro exige outro assunto visual. "
            "Não invente elementos que não estejam visíveis. Não dê nota baixa automaticamente. "
            "Atribua score como NÚMERO INTEIRO de 0 a 100, onde 0 significa totalmente incompatível, "
            "50 significa parcialmente relacionado mas faltam requisitos importantes, e 100 significa "
            "que todos os requisitos essenciais estão claramente visíveis. "
            f"Use approved=true SOMENTE se score for >= {threshold} E todos os requisitos essenciais estiverem presentes; "
            f"use approved=false se score for < {threshold} ou faltar qualquer requisito essencial. "
            "A nota e a justificativa DEVEM ser coerentes: se disser 'perfeitamente', 'corresponde exatamente' "
            "ou 'atende a todos os requisitos', não atribua uma nota baixa. Se faltar algo essencial, explique qual. "
            "Responda com um único objeto JSON válido, sem Markdown nem texto antes/depois. "
            "Use exatamente quatro chaves: approved (booleano), score (inteiro de 0 a 100), "
            "reason (string em português) e suggestions (lista de strings). "
            "Calcule a nota independentemente; não reutilize nota fixa nem texto-modelo.\n"
            f"TEMA: {topic}\nCENA {scene_id}: {scene_text}\nCONSULTA ORIGINAL: {query_used}\n"
            "As suggestions devem ser termos positivos e concretos para corrigir uma nova geração."
        )
        _send_prompt(page, prompt)
        deadline = time.monotonic() + (_timeout_ms() / 1000)
        selectors = ['model-response', 'message-content', '[data-message-author-role="model"]', '.response-container']
        latest_raw = ""
        while time.monotonic() < deadline:
            page.wait_for_timeout(800)
            texts = []
            for sel in selectors:
                try:
                    loc = page.locator(sel)
                    for i in range(max(0, loc.count() - 5), loc.count()):
                        try:
                            txt = loc.nth(i).inner_text(timeout=400).strip()
                            if txt and txt not in before:
                                texts.append(txt)
                        except Exception:
                            pass
                except Exception:
                    pass
            for txt in reversed(texts):
                latest_raw = txt
                obj = _extract_eval_object(txt)
                if not obj:
                    continue
                try:
                    score_raw = obj.get("score", None)
                    if isinstance(score_raw, bool) or score_raw is None:
                        continue
                    score = max(0, min(100, int(float(score_raw))))
                    reason = str(obj.get("reason", "Sem justificativa retornada"))
                    suggestions = obj.get("suggestions", [])
                    if not isinstance(suggestions, list):
                        suggestions = []
                    normalized = {
                        "approved": bool(obj["approved"]),
                        "score": score,
                        "reason": reason,
                        "suggestions": [str(x) for x in suggestions[:8]],
                    }
                    # Regra de segurança: nunca permitir approved=true com nota abaixo do limite.
                    if score < threshold:
                        normalized["approved"] = False
                    _log_eval_debug(scene_id, txt, normalized)
                    print(
                        f"[ImageEval/Gemini-JSON] cena={scene_id} approved_raw={obj['approved']} "
                        f"score={score} threshold={threshold} approved_final={normalized['approved']}"
                    )
                    return normalized
                except Exception as parse_exc:
                    _log_eval_debug(scene_id, txt, None, f"normalização: {parse_exc}")
                    continue
        _log_eval_debug(scene_id, latest_raw, None, "Gemini não devolveu JSON válido")
        raise RuntimeError("O Gemini não devolveu uma avaliação JSON válida.")
    except Exception as exc:
        print(f"[GeminiWebchat] Avaliação visual falhou: {exc}")
        return None
    finally:
        _close_gemini_page(page)
