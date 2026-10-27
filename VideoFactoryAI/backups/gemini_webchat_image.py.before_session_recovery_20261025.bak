"""Integração conservadora com Gemini Web para gerar/avaliar imagens.
Recupera downloads explícitos primeiro e só aceita imagens recentes e válidas.
Não cria placeholders. Requer Playwright e login manual no perfil persistente.
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
    return Path(os.environ.get(
        "VF_GEMINI_PROFILE_DIR",
        str(Path.home() / ".videofactory_gemini_profile")
    )).expanduser().resolve()


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
            user_data_dir=str(profile),
            headless=False,
            accept_downloads=True,
            viewport={"width": 1440, "height": 1000},
            args=["--disable-blink-features=AutomationControlled"],
        )
    except Exception:
        pw.stop()
        raise
    page = context.pages[0] if context.pages else context.new_page()
    page.goto(
        os.environ.get("VF_GEMINI_URL", "https://gemini.google.com/app"),
        wait_until="domcontentloaded",
        timeout=60_000,
    )
    page.wait_for_timeout(1800)
    return pw, context, page


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


def generate_image(prompt, dest_path, scene_id=1, topic=""):
    pw = context = page = None
    try:
        pw, context, page = _open_gemini()
        instruction = (
            "Gere uma IMAGEM original para uma cena de vídeo documental/educacional. "
            "Não responda apenas com texto: produza a imagem. "
            "Composição horizontal 16:9, adequada para saída Full HD 1920x1080. "
            "Mostre especificamente o conteúdo descrito; não substitua por assunto apenas parecido. "
            "Sem texto sobreposto, logotipos ou marcas d'água. "
            "Não imponha estética cinematográfica se ela não for necessária.\n"
            f"TEMA: {topic}\nCENA: {scene_id}\nDESCRIÇÃO/PROMPT: {prompt}\n"
        )
        style = os.environ.get("VF_IMAGE_STYLE", "").strip()
        modifiers = os.environ.get("VF_IMAGE_STYLE_MODIFIERS", "").strip()
        if style:
            instruction += f"\nEstilo opcional configurado: {style}.\n"
        if modifiers:
            instruction += f"Modificadores opcionais: {modifiers}.\n"

        prior_srcs = _image_src_snapshot(page)
        prior_button_count = len(_download_buttons(page))
        _send_prompt(page, instruction)
        deadline = time.monotonic() + (_timeout_ms() / 1000)
        data = None
        last_count = -1
        while time.monotonic() < deadline:
            page.wait_for_timeout(1200)
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
