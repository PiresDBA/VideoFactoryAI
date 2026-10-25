import tempfile
import unittest
from pathlib import Path

try:
    from videofactory_gui import VideoFactoryGUI
except ModuleNotFoundError as exc:
    if exc.name == "tkinter":
        raise unittest.SkipTest("Tkinter is unavailable in this Python environment") from exc
    raise


class Value:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value


class GuiMediaControlTests(unittest.TestCase):
    def test_build_command_passes_resume_and_media_options(self):
        project = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temp_dir:
            script = Path(temp_dir) / "script.txt"
            script.write_text("documentary script", encoding="utf-8")
            gui = VideoFactoryGUI.__new__(VideoFactoryGUI)
            options = {
                "project_dir": project,
                "mode": "script",
                "script_path": str(script),
                "channel": "historia",
                "voice": "pt-BR-AntonioNeural",
                "tts_engine": "edge-tts",
                "whisper_model": "base",
                "art_director": "standard",
                "youtube_mode": "off",
                "subtitles": True,
                "resume": False,
                "checkpoint": True,
                "reuse_audio": True,
                "reuse_approved_images": False,
                "revalidate_images": True,
                "force_regeneration": True,
                "gemini_only": True,
                "web_research_before_generation": True,
                "prefer_real_media": True,
                "gemini_fallback": True,
                "debug_verbose": True,
                "ignore_cache": True,
            }
            for name, value in options.items():
                setattr(gui, name, Value(value))
            gui.xtts_reference = Value("")
            gui.authorized_video = Value("")
            gui.rights_confirmed = Value(False)
            gui.source_url = Value("")

            command, _ = gui._build_command()

        for option in (
            "--no-resume",
            "--reuse-existing-audio",
            "--revalidate-images",
            "--force-regeneration",
            "--gemini-only",
            "--web-research-before-generation",
            "--prefer-real-media",
            "--gemini-fallback",
            "--debug",
            "--ignore-cache",
        ):
            self.assertIn(option, command)


if __name__ == "__main__":
    unittest.main()
