import base64
import io
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image

import media_research_agent
from local_media_agent import LocalMediaAgent
from media_research_agent import MediaResearchAgent


class FakeOllamaResponse:
    def __init__(self, response):
        self.response = response

    def raise_for_status(self):
        return None

    def json(self):
        return {"response": json.dumps(self.response)}


class LocalMediaAgentTests(unittest.TestCase):
    def test_ollama_visually_ranks_shortlisted_images_using_portuguese_titles(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir) / "library"
            folder.mkdir()
            Image.new("RGB", (12, 12), "red").save(folder / "trilhos_bancada.jpg")
            Image.new("RGB", (12, 12), "blue").save(folder / "locomotiva_azul_ho.png")
            Image.new("RGB", (12, 12), "green").save(folder / "vegetacao_maquete.jpg")
            agent = LocalMediaAgent(
                folder,
                threshold=0.8,
                model="llava-phi3",
                candidate_count=2,
            )

            with patch(
                "local_media_agent.requests.post",
                return_value=FakeOllamaResponse({"selected": 1, "confidence": 9.4}),
            ) as post:
                result = agent.find_best("A locomotiva azul atravessa a maquete HO")

            self.assertEqual(Path(result["path"]).name, "locomotiva_azul_ho.png")
            self.assertAlmostEqual(result["score"], 0.94)
            self.assertEqual(post.call_count, 1)
            args, kwargs = post.call_args
            self.assertEqual(args[0], "http://127.0.0.1:11434/api/generate")
            self.assertEqual(kwargs["json"]["model"], "llava-phi3")
            self.assertEqual(
                kwargs["json"]["format"]["properties"]["selected"]["enum"],
                [1, 2],
            )
            self.assertEqual(len(kwargs["json"]["images"]), 2)
            self.assertIn("locomotiva azul ho", kwargs["json"]["prompt"].lower())
            self.assertTrue(all(base64.b64decode(item) for item in kwargs["json"]["images"]))

    def test_returns_below_threshold_candidate_for_optional_manual_review(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir)
            Image.new("RGB", (8, 8), "red").save(folder / "locomotiva.jpg")
            agent = LocalMediaAgent(folder, threshold=0.8)

            with patch(
                "local_media_agent.requests.post",
                return_value=FakeOllamaResponse({"selected": 1, "confidence": 2.5}),
            ):
                result = agent.find_best("locomotiva na maquete")

        self.assertEqual(Path(result["path"]).name, "locomotiva.jpg")
        self.assertFalse(result["accepted"])
        self.assertEqual(result["score"], 0.25)

    def test_normalizes_ten_point_ollama_confidence_to_threshold_scale(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir)
            Image.new("RGB", (8, 8), "red").save(folder / "locomotiva.jpg")
            agent = LocalMediaAgent(folder, threshold=0.8)

            with patch(
                "local_media_agent.requests.post",
                return_value=FakeOllamaResponse({"selected": 1, "confidence": 9.0}),
            ):
                result = agent.find_best("locomotiva na maquete")

        self.assertAlmostEqual(result["score"], 0.9)

    def test_skips_previously_used_images_and_selects_next_candidate(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir)
            Image.new("RGB", (8, 8), "red").save(folder / "locomotiva_vermelha.jpg")
            Image.new("RGB", (8, 8), "blue").save(folder / "locomotiva_azul.jpg")
            agent = LocalMediaAgent(folder, threshold=0.8, candidate_count=2)
            responses = [
                FakeOllamaResponse({"selected": 1, "confidence": 9.6}),
                FakeOllamaResponse({"selected": 1, "confidence": 9.2}),
            ]

            with patch("local_media_agent.requests.post", side_effect=responses) as post:
                first = agent.find_best("locomotiva na maquete")
                second = agent.find_best(
                    "locomotiva na maquete",
                    exclude_paths={first["path"]},
                )

        self.assertNotEqual(first["path"], second["path"])
        self.assertEqual(post.call_count, 2)

    def test_raises_clear_error_for_invalid_ollama_response(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir)
            Image.new("RGB", (8, 8), "red").save(folder / "locomotiva.jpg")
            agent = LocalMediaAgent(folder)

            with patch(
                "local_media_agent.requests.post",
                return_value=SimpleNamespace(
                    raise_for_status=lambda: None,
                    json=lambda: {"response": "not json"},
                ),
            ):
                with self.assertRaisesRegex(RuntimeError, "Ollama"):
                    agent.find_best("locomotiva")

    def test_empty_library_does_not_call_ollama(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch("local_media_agent.requests.post") as post:
                agent = LocalMediaAgent(Path(temp_dir))
                result = agent.find_best("locomotiva")

        self.assertEqual(agent.index, [])
        self.assertIsNone(result)
        post.assert_not_called()

    def test_analysis_thumbnail_is_reduced_in_memory_without_changing_original(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "large.png"
            Image.new("RGBA", (2400, 1600), (10, 20, 30, 128)).save(path)
            original_bytes = path.read_bytes()

            encoded = LocalMediaAgent._encode_image(path)

            with Image.open(io.BytesIO(base64.b64decode(encoded))) as analysis_image:
                self.assertEqual(analysis_image.size, (768, 512))
                self.assertEqual(analysis_image.mode, "RGB")
            self.assertEqual(path.read_bytes(), original_bytes)

    def test_media_research_uses_ollama_match_without_remote_image_validation(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            library_image = root / "locomotiva_modelo.png"
            Image.new("RGB", (12, 12), "blue").save(library_image)
            destination = root / "images" / "scene_01.jpg"
            agent = MediaResearchAgent.__new__(MediaResearchAgent)
            agent.resume_mode = False
            agent.cache = None
            agent.ignore_cache = False
            agent.force_regeneration = False
            agent.local_media_enabled = True
            agent.local_media_mode = "required"
            agent.local_media = SimpleNamespace(
                find_best=lambda _text, exclude_paths=None: (
                    None if str(library_image) in (exclude_paths or set())
                    else {"path": str(library_image), "score": 0.91}
                )
            )
            agent.used_hashes = {}
            agent.used_paths = {}
            agent.used_urls = set()
            agent.media_report = []
            agent._dest_path = lambda _scene: str(destination)
            agent._asset_valid = lambda *_args: False
            agent._validate_asset = lambda *_args: self.fail(
                "local Ollama assessment should replace remote image validation"
            )
            agent._record_hit = lambda *_args: None
            agent._add_report = lambda *args: agent.media_report.append(args)
            assessed_queries = []
            review_results = iter([False, True])
            review_candidates = []

            def review_candidate(review_scene, candidate):
                review_candidates.append((review_scene["id"], candidate["path"]))
                return next(review_results)

            def find_best(text, exclude_paths=None):
                assessed_queries.append(text)
                if str(library_image) not in (exclude_paths or set()):
                    return {
                        "path": str(library_image),
                        "score": 0.52,
                        "accepted": False,
                    }
                next_image = root / "segunda_locomotiva.jpg"
                Image.new("RGB", (12, 12), "red").save(next_image)
                return {
                    "path": str(next_image),
                    "score": 0.60,
                    "accepted": False,
                }

            agent.local_media.find_best = find_best
            agent.local_media_review_callback = review_candidate

            result = agent.source_scene(
                {
                    "id": 1,
                    "tipo": "image",
                    "arquivo": "scene_01.jpg",
                    "query": "model railroad HO scale",
                    "texto": "Uma locomotiva em miniatura",
                }
            )

            self.assertEqual(result, str(destination))
            with Image.open(destination) as output_image:
                self.assertEqual(output_image.format, "JPEG")
            self.assertEqual(agent.media_report[0][2], "local_library")
            self.assertEqual(agent.media_report[0][3], str(root / "segunda_locomotiva.jpg"))
            self.assertIn("Uma locomotiva em miniatura", assessed_queries[0])
            self.assertIn("model railroad HO scale", assessed_queries[0])
            self.assertEqual(
                review_candidates,
                [(1, str(library_image)), (1, str(root / "segunda_locomotiva.jpg"))],
            )

    def test_rejected_candidate_remains_available_to_later_scenes(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            library_image = root / "locomotiva_vermelha.jpg"
            Image.new("RGB", (12, 12), "red").save(library_image)
            agent = MediaResearchAgent.__new__(MediaResearchAgent)
            agent.resume_mode = False
            agent.cache = None
            agent.ignore_cache = False
            agent.force_regeneration = False
            agent.local_media_enabled = True
            agent.local_media_mode = "required"
            agent.local_media = SimpleNamespace(
                find_best=lambda _text, exclude_paths=None: (
                    None if str(library_image.resolve()) in (exclude_paths or set())
                    else {
                        "path": str(library_image),
                        "score": 0.45,
                        "accepted": False,
                    }
                )
            )
            agent.used_hashes = {}
            agent.used_paths = {}
            agent.used_urls = set()
            agent.media_report = []
            agent._dest_path = lambda scene: str(root / "output" / f"scene_{scene['id']}.jpg")
            agent._asset_valid = lambda *_args: False
            agent._record_hit = lambda *_args: None
            agent._add_report = lambda *args: agent.media_report.append(args)
            decisions = iter([False, True])
            agent.local_media_review_callback = lambda *_args: next(decisions)
            scene = {
                "id": 1,
                "tipo": "image",
                "arquivo": "scene_1.jpg",
                "texto": "Locomotiva vermelha",
            }

            first_result = agent._try_local_image(
                scene,
                agent._dest_path(scene),
            )
            second_scene = dict(scene, id=2, arquivo="scene_2.jpg")
            second_result = agent._try_local_image(
                second_scene,
                agent._dest_path(second_scene),
            )
            second_output_exists = Path(second_result).is_file() if second_result else False
            second_report_scene_id = agent.media_report[0][0] if agent.media_report else None

        self.assertIsNone(first_result)
        self.assertTrue(second_result)
        self.assertTrue(second_output_exists)
        self.assertEqual(second_report_scene_id, 2)

    def test_only_accepts_localhost_ollama_url(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaisesRegex(ValueError, "localhost"):
                LocalMediaAgent(
                    Path(temp_dir),
                    base_url="http://example.com:11434",
                )

    def test_required_mode_never_calls_online_providers_for_video_scene(self):
        agent = MediaResearchAgent.__new__(MediaResearchAgent)
        agent.resume_mode = False
        agent.cache = None
        agent.ignore_cache = False
        agent.force_regeneration = False
        agent.local_media_enabled = True
        agent.local_media_mode = "required"
        agent.local_media = SimpleNamespace(find_best=lambda *_args, **_kwargs: None)
        agent.used_hashes = {}
        agent.used_paths = {}
        agent.used_urls = set()
        agent.media_report = []
        agent._dest_path = lambda scene: f"unused{Path(scene['arquivo']).suffix}"
        agent._asset_valid = lambda *_args: False
        scene = {
            "id": 1,
            "tipo": "video",
            "arquivo": "scene_01.mp4",
            "query": "model railway",
        }

        with patch(
            "media_research_agent._l1_pixabay_video",
            side_effect=AssertionError("online provider called"),
        ) as video_provider, patch(
            "media_research_agent._l2_pixabay_image",
            side_effect=AssertionError("online provider called"),
        ) as image_provider:
            result = agent.source_scene(scene)

        self.assertIsNone(result)
        self.assertEqual(scene["tipo"], "image")
        self.assertEqual(scene["arquivo"], "scene_01.jpg")
        video_provider.assert_not_called()
        image_provider.assert_not_called()

    def test_required_mode_keeps_low_confidence_image_pending_without_online_fallback(self):
        agent = MediaResearchAgent.__new__(MediaResearchAgent)
        agent.resume_mode = False
        agent.cache = None
        agent.ignore_cache = False
        agent.force_regeneration = False
        agent.local_media_enabled = True
        agent.local_media_mode = "required"
        agent.local_media_review_callback = None
        agent.local_similarity_threshold = 0.8
        unavailable_image = str(Path("unavailable-for-review.jpg").resolve())
        agent.local_media = SimpleNamespace(
            find_best=lambda _text, exclude_paths=None: (
                None
                if unavailable_image in (exclude_paths or set())
                else {
                    "path": unavailable_image,
                    "score": 0.42,
                    "accepted": False,
                }
            )
        )
        agent.used_hashes = {}
        agent.used_paths = {}
        agent.used_urls = set()
        agent.media_report = []
        agent._dest_path = lambda _scene: "unused.jpg"
        agent._asset_valid = lambda *_args: False

        with patch(
            "media_research_agent._l2_pixabay_image",
            side_effect=AssertionError("online image provider called"),
        ) as image_provider:
            result = agent.source_scene(
                {
                    "id": 1,
                    "tipo": "image",
                    "arquivo": "scene_01.jpg",
                    "query": "locomotiva",
                    "texto": "Locomotiva em escala HO",
                }
            )

        self.assertIsNone(result)
        image_provider.assert_not_called()


if __name__ == "__main__":
    unittest.main()
