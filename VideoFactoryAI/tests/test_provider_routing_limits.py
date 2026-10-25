import json
import sys
import tempfile
import threading
import types
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch

import media_research_agent as media
from media_research_agent import MediaResearchAgent, provider_limit_reached


class ProviderLimitDetectionTests(unittest.TestCase):
    def test_detects_localized_and_provider_specific_limit_messages(self):
        messages = (
            "Desculpe, você atingiu o limite de geração de imagens",
            "limite alcançado para hoje",
            "429 Too Many Requests",
            "RESOURCE_EXHAUSTED: quota exceeded",
            "daily image generation limit reached",
        )
        for message in messages:
            with self.subTest(message=message):
                self.assertTrue(provider_limit_reached(message))

    def test_detects_http_status_without_message(self):
        self.assertTrue(provider_limit_reached("", status_code=429))

    def test_does_not_treat_unrelated_failures_as_quota_limits(self):
        self.assertFalse(provider_limit_reached("login session expired"))
        self.assertFalse(provider_limit_reached("image could not be downloaded"))


class ProviderLimitPersistenceTests(unittest.TestCase):
    def test_limit_is_persisted_until_next_local_day_then_expires(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            agent = MediaResearchAgent.__new__(MediaResearchAgent)
            agent.memory_dir = Path(temp_dir)
            now = datetime(2026, 10, 25, 18, 0).astimezone()

            agent._disable_provider("gemini", "429 quota exceeded", now=now)

            state_path = Path(temp_dir) / "provider_limits.json"
            self.assertTrue(state_path.is_file())
            saved = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertIn("gemini", saved["providers"])
            self.assertTrue(agent._provider_disabled("gemini", now=now))
            reloaded = MediaResearchAgent.__new__(MediaResearchAgent)
            reloaded.memory_dir = Path(temp_dir)
            self.assertTrue(reloaded._provider_disabled("gemini", now=now))
            expired_at = (now + timedelta(days=1)).replace(hour=0, minute=1)
            self.assertFalse(agent._provider_disabled("gemini", now=expired_at))
            self.assertNotIn("gemini", json.loads(state_path.read_text(encoding="utf-8"))["providers"])


class GeminiPriorityRoutingTests(unittest.TestCase):
    def _agent(self, root, media_options):
        agent = MediaResearchAgent.__new__(MediaResearchAgent)
        agent.cfg = {"media": media_options}
        agent.gemini_only = bool(media_options.get("gemini_only"))
        agent.prefer_real_media = media_options.get("prefer_real_media", True)
        agent.web_research_before_generation = False
        agent.root = Path(root)
        agent.memory_dir = Path(root) / "memory"
        agent.pixabay_key = ""
        agent.pexels_key = ""
        agent.unsplash_key = ""
        agent.youtube_mode = "off"
        agent.generation_providers = ["gemini", "chatgpt"]
        agent._provider_locks = {
            provider: threading.Lock() for provider in agent.generation_providers
        }
        agent.stock_candidates_per_scene = 1
        agent.cache = None
        agent.used_urls = set()
        agent.used_hashes = {}
        agent.used_paths = {}
        agent.media_report = []
        agent._source_stats = {}
        agent._prefs = {}
        agent._current_topic = "test"
        agent._dest_path = lambda scene: str(Path(root) / f"scene_{scene['id']}.jpg")
        agent._asset_valid = Mock(return_value=False)
        agent._validate_asset = Mock(return_value=True)
        agent._record_hit = Mock()
        agent._add_report = Mock()
        return agent

    def test_prefer_real_media_keeps_stock_search_before_generation(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            agent = self._agent(temp_dir, {"prefer_real_media": True})
            events = []

            def stock_hit(*args, **kwargs):
                events.append("stock")
                return ("stock://image", "public domain")

            def generate(**kwargs):
                events.append("gemini")
                return None

            gemini_module = types.SimpleNamespace(
                GeminiSessionError=RuntimeError,
                generate_image=generate,
            )
            with patch.dict(sys.modules, {"gemini_webchat_image": gemini_module}), patch.object(
                media, "_file_hash", side_effect=lambda path: Path(path).name
            ), patch.object(
                media, "_l2_pixabay_image", side_effect=stock_hit
            ), patch.object(media, "_l2_wikimedia_image", return_value=None), patch.object(
                media, "_l2_pexels_image", return_value=None
            ), patch.object(media, "_l2_unsplash_image", return_value=None), patch.object(
                media, "_l2_free_image_source", return_value=None
            ), patch.object(media, "_l3_openverse_image", return_value=None), patch.dict(
                sys.modules,
                {"web_image_providers": types.SimpleNamespace(generate_image=Mock())},
            ):
                result = agent.source_scene(
                    {
                        "id": 1,
                        "tipo": "image",
                        "query": "test subject",
                        "wikimedia_q": "test subject",
                        "ai_prompt": "original prompt",
                        "arquivo": "scene_1.jpg",
                    }
                )

            self.assertEqual(result, str(Path(temp_dir) / "scene_1.jpg"))
            self.assertEqual(events, ["stock"])

    def test_gemini_only_attempts_gemini_before_stock_search(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            agent = self._agent(temp_dir, {"gemini_only": True})
            events = []

            def generate(**kwargs):
                events.append("gemini")
                Path(kwargs["dest_path"]).write_bytes(b"generated")
                return ("gemini://image", "ai_generated")

            gemini_module = types.SimpleNamespace(
                GeminiSessionError=RuntimeError,
                generate_image=generate,
            )
            with patch.dict(sys.modules, {"gemini_webchat_image": gemini_module}), patch.object(
                media, "_file_hash", side_effect=lambda path: Path(path).name
            ), patch.object(
                media, "_l2_pixabay_image", side_effect=lambda *a, **k: events.append("stock")
            ), patch.object(media, "_l2_wikimedia_image", return_value=None), patch.object(
                media, "_l2_pexels_image", return_value=None
            ), patch.object(media, "_l2_unsplash_image", return_value=None), patch.object(
                media, "_l2_free_image_source", return_value=None
            ), patch.object(media, "_l3_openverse_image", return_value=None), patch.dict(
                sys.modules,
                {"web_image_providers": types.SimpleNamespace(generate_image=Mock())},
            ):
                result = agent.source_scene(
                    {
                        "id": 1,
                        "tipo": "image",
                        "query": "test subject",
                        "wikimedia_q": "test subject",
                        "ai_prompt": "original prompt",
                        "arquivo": "scene_1.jpg",
                    }
                )

            self.assertEqual(result, str(Path(temp_dir) / "scene_1.jpg"))
            self.assertEqual(events, ["gemini"])

    def test_disabling_real_media_preference_prioritizes_gemini(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            agent = self._agent(temp_dir, {"prefer_real_media": False})
            events = []

            def generate(**kwargs):
                events.append("gemini")
                Path(kwargs["dest_path"]).write_bytes(b"generated")
                return ("gemini://image", "ai_generated")

            gemini_module = types.SimpleNamespace(
                GeminiSessionError=RuntimeError,
                generate_image=generate,
            )
            with patch.dict(sys.modules, {"gemini_webchat_image": gemini_module}), patch.object(
                media, "_file_hash", side_effect=lambda path: Path(path).name
            ), patch.object(
                media, "_l2_pixabay_image", side_effect=lambda *a, **k: events.append("stock")
            ), patch.object(media, "_l2_wikimedia_image", return_value=None), patch.object(
                media, "_l2_pexels_image", return_value=None
            ), patch.object(media, "_l2_unsplash_image", return_value=None), patch.object(
                media, "_l2_free_image_source", return_value=None
            ), patch.object(media, "_l3_openverse_image", return_value=None):
                result = agent.source_scene(
                    {
                        "id": 1,
                        "tipo": "image",
                        "query": "test subject",
                        "wikimedia_q": "test subject",
                        "ai_prompt": "original prompt",
                        "arquivo": "scene_1.jpg",
                    }
                )

            self.assertEqual(result, str(Path(temp_dir) / "scene_1.jpg"))
            self.assertEqual(events, ["gemini"])

    def test_quota_disables_gemini_and_falls_through_to_stock_and_other_ai(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            agent = self._agent(temp_dir, {"gemini_only": True})
            events = []

            def hit_quota(**kwargs):
                events.append("gemini")
                print("Gemini: Desculpe, limite de imagens alcançado para hoje")
                return None

            def stock_miss(*args, **kwargs):
                events.append("stock")
                return None

            def other_provider(**kwargs):
                events.append(kwargs["provider"])
                Path(kwargs["dest_path"]).write_bytes(b"other provider image")
                return ("provider://image", "ai_generated")

            gemini_module = types.SimpleNamespace(
                GeminiSessionError=RuntimeError,
                generate_image=hit_quota,
            )
            web_module = types.SimpleNamespace(generate_image=other_provider)
            scene = {
                "id": 1,
                "tipo": "image",
                "query": "test subject",
                "wikimedia_q": "test subject",
                "ai_prompt": "original prompt",
                "arquivo": "scene_1.jpg",
            }
            with patch.dict(
                sys.modules,
                {
                    "gemini_webchat_image": gemini_module,
                    "web_image_providers": web_module,
                },
            ), patch.object(
                media, "_file_hash", side_effect=lambda path: Path(path).name
            ), patch.object(
                media, "_l2_pixabay_image", side_effect=stock_miss
            ), patch.object(
                media, "_l2_wikimedia_image", return_value=None
            ), patch.object(
                media, "_l2_pexels_image", return_value=None
            ), patch.object(
                media, "_l2_unsplash_image", return_value=None
            ), patch.object(
                media, "_l2_free_image_source", return_value=None
            ), patch.object(
                media, "_l3_openverse_image", return_value=None
            ):
                result = agent.source_scene(scene)
                first_events = list(events)
                events.clear()
                next_scene = dict(scene, id=2, arquivo="scene_2.jpg")
                next_result = agent.source_scene(next_scene)

            self.assertEqual(result, str(Path(temp_dir) / "scene_1.jpg"))
            self.assertEqual(first_events[0], "gemini")
            self.assertIn("stock", first_events)
            self.assertIn("chatgpt", first_events)
            self.assertTrue(agent._provider_disabled("gemini"))
            self.assertEqual(next_result, str(Path(temp_dir) / "scene_2.jpg"))
            self.assertNotIn("gemini", events)
            self.assertIn("stock", events)

    def test_webchat_quota_is_persisted_for_later_scenes(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            agent = self._agent(temp_dir, {"gemini_only": False})
            agent.generation_providers = ["chatgpt"]
            agent._provider_locks = {"chatgpt": threading.Lock()}
            scene = {
                "id": 1,
                "tipo": "image",
                "query": "test subject",
                "wikimedia_q": "test subject",
                "ai_prompt": "original prompt",
                "arquivo": "scene_1.jpg",
            }
            web_module = types.SimpleNamespace(
                generate_image=lambda **kwargs: None,
                is_provider_limit_reached=lambda provider: provider == "chatgpt",
            )
            with patch.object(media, "_l2_pixabay_image", return_value=None), patch.object(
                media, "_l2_wikimedia_image", return_value=None
            ), patch.object(media, "_l2_pexels_image", return_value=None), patch.object(
                media, "_l2_unsplash_image", return_value=None
            ), patch.object(media, "_l2_free_image_source", return_value=None), patch.object(
                media, "_l3_openverse_image", return_value=None
            ), patch.dict(sys.modules, {"web_image_providers": web_module}):
                agent.source_scene(scene)

            self.assertTrue(agent._provider_disabled("chatgpt"))


if __name__ == "__main__":
    unittest.main()
