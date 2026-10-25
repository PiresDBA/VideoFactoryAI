import unittest

from gemini_webchat_image import _new_image_limit_message
from webchat_research import (
    build_image_prompt,
    build_web_research_prompt,
    extract_visual_description,
    research_visual_description,
)


class WebChatResearchTests(unittest.TestCase):
    def test_detects_new_limit_messages_but_ignores_old_history(self):
        self.assertEqual(
            _new_image_limit_message(
                "Earlier conversation",
                "Earlier conversation\nSorry, image generation limit reached. Try again later.",
            ),
            "image generation limit",
        )
        self.assertIsNone(
            _new_image_limit_message(
                "Daily limit reached in an old message",
                "Daily limit reached in an old message",
            )
        )

    def test_research_prompt_requests_web_search_and_visual_facts(self):
        prompt = build_web_research_prompt(
            scene_text="Marshall construiu os primeiros trilhos de sua maquete.",
            query="model railroad benchwork",
            topic="modelismo ferroviário",
        )

        self.assertIn("Pesquise na web", prompt)
        self.assertIn("model railroad benchwork", prompt)
        self.assertIn("Marshall construiu", prompt)
        self.assertIn("elementos obrigatórios", prompt)

    def test_image_prompt_combines_original_scene_and_research(self):
        prompt = build_image_prompt(
            "miniature railway workshop",
            "Historical model railways use wooden benchwork and miniature track.",
        )

        self.assertIn("miniature railway workshop", prompt)
        self.assertIn("wooden benchwork", prompt)

    def test_empty_or_too_short_research_is_rejected(self):
        self.assertIsNone(extract_visual_description(""))
        self.assertIsNone(extract_visual_description("Não sei."))

    def test_research_response_is_trimmed(self):
        response = "A realistic model railway workshop with wooden benchwork, miniature rails, and period locomotives."
        self.assertEqual(extract_visual_description(response), response)

    def test_research_failure_logs_and_returns_no_description(self):
        logs = []

        description = research_visual_description(
            "scene text",
            "search query",
            "topic",
            lambda prompt: None,
            lambda: (_ for _ in ()).throw(RuntimeError("search unavailable")),
            log=logs.append,
        )

        self.assertIsNone(description)
        self.assertTrue(any("prompt original" in item for item in logs))


if __name__ == "__main__":
    unittest.main()
