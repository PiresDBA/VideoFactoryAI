import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import agent
from pipeline_resume import save_narration_hash


class AgentResumeCliTests(unittest.TestCase):
    def test_cli_exposes_media_resume_controls(self):
        with patch.object(
            sys,
            "argv",
            [
                "agent.py",
                "script.txt",
                "--resume",
                "--gemini-only",
                "--web-research-before-generation",
                "--force-regeneration",
                "--debug",
            ],
        ):
            args = agent.parse_args()

        self.assertTrue(args.resume)
        self.assertTrue(args.gemini_only)
        self.assertTrue(args.web_research_before_generation)
        self.assertTrue(args.force_regeneration)
        self.assertTrue(args.debug)

    def test_cli_can_override_configured_resume(self):
        with patch.object(sys, "argv", ["agent.py", "script.txt", "--no-resume"]):
            args = agent.parse_args()

        self.assertFalse(args.resume)


class NarrationReuseTests(unittest.TestCase):
    def test_reuses_audio_only_when_resume_script_hash_matches(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            audio = Path(temp_dir) / "narracao.mp3"
            audio.write_bytes(b"a" * 10_000)
            save_narration_hash(audio, "unchanged script")

            with patch.object(agent, "log") as log, patch.object(agent.asyncio, "run") as run:
                result = agent.generate_voice(
                    "unchanged script",
                    str(audio),
                    {
                        "pipeline": {"resume_mode": True, "reuse_existing_audio": True},
                        "tts": {
                            "engine": "edge-tts",
                            "voice": "pt-BR-AntonioNeural",
                            "rate": "+0%",
                            "pitch": "+0Hz",
                        },
                    },
                )

            self.assertEqual(result, str(audio))
            run.assert_not_called()
            log.assert_called()

    def test_regenerates_audio_when_script_hash_differs(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            audio = Path(temp_dir) / "narracao.mp3"
            audio.write_bytes(b"a" * 10_000)
            save_narration_hash(audio, "old script")

            def fake_run(coroutine):
                coroutine.close()
                audio.write_bytes(b"b" * 10_000)

            with patch.object(agent, "log"), patch.object(agent.asyncio, "run", side_effect=fake_run) as run:
                result = agent.generate_voice(
                    "new script",
                    str(audio),
                    {
                        "pipeline": {"resume_mode": True, "reuse_existing_audio": True},
                        "tts": {
                            "engine": "edge-tts",
                            "voice": "pt-BR-AntonioNeural",
                            "rate": "+0%",
                            "pitch": "+0Hz",
                        },
                    },
                )

            self.assertEqual(result, str(audio))
            run.assert_called_once()


if __name__ == "__main__":
    unittest.main()
