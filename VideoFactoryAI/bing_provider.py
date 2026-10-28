# bing_provider.py

import json
import urllib.parse
import concurrent.futures
import re

from pathlib import Path

import requests
from PIL import Image
from playwright.sync_api import sync_playwright


# ------------------------------------------------------------------
# Playwright worker thread
# Evita:
# "Playwright Sync API inside the asyncio loop"
# ------------------------------------------------------------------

_WORKER = concurrent.futures.ThreadPoolExecutor(
    max_workers=1,
    thread_name_prefix="bing"
)


def _run_in_worker(fn, *args, **kwargs):
    return _WORKER.submit(
        fn,
        *args,
        **kwargs
    ).result()


class BingImageProvider:

    def __init__(
        self,
        min_width=1280,
        min_height=720,
        headless=True
    ):
        self.min_width = min_width
        self.min_height = min_height
        self.headless = headless

    def _valid_image(self, path: str) -> bool:

        try:

            with Image.open(path) as img:
                w, h = img.size

            return (
                w >= self.min_width
                and h >= self.min_height
            )

        except Exception:
            return False

    # --------------------------------------------------------------
    # EXECUÇÃO REAL DO PLAYWRIGHT
    # Roda dentro da thread dedicada
    # --------------------------------------------------------------

    def _search_impl(
        self,
        query: str,
        limit: int = 10
    ):

        results = []

        with sync_playwright() as p:

            browser = p.chromium.launch(
                headless=self.headless
            )

            try:

                page = browser.new_page()

                url = (
                    "https://www.bing.com/images/search?q="
                    + urllib.parse.quote(query)
                )

                page.goto(
                    url,
                    wait_until="networkidle",
                    timeout=30000
                )

                cards = page.locator(".iusc")

                total = cards.count()

                print(
                    f"[BING] encontrados {total} resultados"
                )

                for i in range(min(total, 100)):

                    try:

                        metadata = cards.nth(i).get_attribute("m")

                        if not metadata:
                            continue

                        data = json.loads(metadata)

                        image_url = str(
                            data.get("murl", "")
                        ).strip()

                        match = re.search(
                            r'https?://[^"]+',
                            image_url
                        )

                        if match:
                            image_url = match.group(0)

                        if not image_url:
                            continue

                        results.append(image_url)

                        if len(results) >= limit:
                            break

                    except Exception:
                        continue

            finally:
                browser.close()

        return results

    # --------------------------------------------------------------
    # MÉTODO PÚBLICO
    # Agora roda SEMPRE em outra thread
    # --------------------------------------------------------------

    def search(
        self,
        query: str,
        limit: int = 10
    ):

        return _run_in_worker(
            self._search_impl,
            query,
            limit
        )

    def download(
        self,
        query: str,
        dest_dir="downloads",
        max_images=5
    ):

        dest_dir = Path(dest_dir)

        dest_dir.mkdir(
            parents=True,
            exist_ok=True
        )

        urls = self.search(
            query=query,
            limit=max_images * 5
        )

        downloaded = []

        for idx, url in enumerate(urls, 1):

            try:

                print(
                    f"[BING] tentando {idx}: "
                    f"{url[:120]}"
                )

                r = requests.get(
                    url,
                    timeout=30,
                    headers={
                        "User-Agent": "Mozilla/5.0"
                    },
                    stream=True
                )

                if r.status_code != 200:
                    continue

                file_path = (
                    dest_dir
                    / f"img_{len(downloaded)+1}.jpg"
                )

                with open(file_path, "wb") as f:

                    for chunk in r.iter_content(
                        chunk_size=8192
                    ):
                        if chunk:
                            f.write(chunk)

                if not self._valid_image(
                    str(file_path)
                ):

                    file_path.unlink(
                        missing_ok=True
                    )

                    continue

                with Image.open(file_path) as img:
                    w, h = img.size

                print(
                    f"[OK] "
                    f"{file_path.name} "
                    f"{w}x{h}"
                )

                downloaded.append(
                    str(file_path)
                )

                if len(downloaded) >= max_images:
                    break

            except Exception as e:

                print(
                    f"[ERRO] {e}"
                )

        return downloaded


if __name__ == "__main__":

    provider = BingImageProvider(
        min_width=1280,
        min_height=720,
        headless=False
    )

    files = provider.download(
        query="golden retriever",
        dest_dir="bing_images",
        max_images=5
    )

    print()
    print("=" * 80)
    print("ARQUIVOS BAIXADOS")
    print("=" * 80)

    for f in files:
        print(f)