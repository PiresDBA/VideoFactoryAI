import unittest
from unittest.mock import patch

from media_research_agent import (
    MediaResearchAgent,
    _generation_provider_order,
    _parse_generation_providers,
    _resolve_api_key,
)


class GenerationProviderOrderTests(unittest.TestCase):
    def test_defaults_to_supported_generation_providers(self):
        self.assertEqual(
            _parse_generation_providers(""),
            ["gemini", "dreamina", "copilot", "chatgpt", "grok", "qwen"],
        )

    def test_ignores_unknown_and_repeated_provider_names(self):
        self.assertEqual(
            _parse_generation_providers("copilot, desconhecido, gemini, copilot"),
            ["copilot", "gemini"],
        )

    def test_rotates_the_first_provider_between_scenes(self):
        providers = ["gemini", "dreamina", "copilot"]
        self.assertEqual(_generation_provider_order(providers, 1), providers)
        self.assertEqual(_generation_provider_order(providers, 2), ["dreamina", "copilot", "gemini"])
        self.assertEqual(_generation_provider_order(providers, 3), ["copilot", "gemini", "dreamina"])

    def test_api_key_uses_environment_when_config_is_empty(self):
        with patch.dict("os.environ", {"VF_PIXABAY_API_KEY": "local-test-key"}):
            self.assertEqual(
                _resolve_api_key({}, "pixabay_api_key", "VF_PIXABAY_API_KEY"),
                "local-test-key",
            )

    def test_api_key_prefers_explicit_config_value(self):
        with patch.dict("os.environ", {"VF_PIXABAY_API_KEY": "environment-key"}):
            self.assertEqual(
                _resolve_api_key(
                    {"pixabay_api_key": "configured-test-key"},
                    "pixabay_api_key",
                    "VF_PIXABAY_API_KEY",
                ),
                "configured-test-key",
            )


class RegenerateSceneCompatibilityTests(unittest.TestCase):
    def test_regenerate_scene_accepts_corrected_query_without_mutating_input(self):
        agent = MediaResearchAgent.__new__(MediaResearchAgent)
        agent._current_topic = ""
        agent.used_hashes = {}
        agent.used_paths = {}
        agent._dest_path = lambda scene: "unused.jpg"
        received_scenes = []
        agent.source_scene = lambda scene: received_scenes.append(scene) or "asset.jpg"
        scene = {"id": 1, "query": "original", "wikimedia_q": "original"}

        result = agent.regenerate_scene(
            scene,
            topic="documentary topic",
            corrected_query="corrected",
        )

        self.assertEqual(result, "asset.jpg")
        self.assertEqual(agent._current_topic, "documentary topic")
        self.assertEqual(received_scenes[0]["query"], "corrected")
        self.assertEqual(received_scenes[0]["wikimedia_q"], "corrected")
        self.assertEqual(scene["query"], "original")
        self.assertEqual(scene["wikimedia_q"], "original")


if __name__ == "__main__":
    unittest.main()
