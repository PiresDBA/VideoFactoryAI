import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from modules.visual_processor import (
    build_fade_zoom_filter,
    build_ken_burns_smooth_filter,
    process_all_scenes,
    process_single_scene,
)


class VisualProcessorRegressionTests(unittest.TestCase):
    def test_zoompan_filters_use_output_frame_counter(self):
        with patch("modules.visual_processor.random.choice", return_value=True):
            ken_burns = build_ken_burns_smooth_filter(2)
        fade_zoom = build_fade_zoom_filter(2)

        self.assertIn("pow(on/", ken_burns)
        self.assertNotIn("pow(n/", ken_burns)
        self.assertIn("pow(on/", fade_zoom)
        self.assertNotIn("pow(n/", fade_zoom)

    def test_slide_overlay_expressions_are_not_quoted(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            asset_path = Path(temp_dir) / "source.jpg"
            asset_path.write_bytes(b"image")
            output_path = Path(temp_dir) / "clip.mp4"

            def fake_run(command, **kwargs):
                output_path.write_bytes(b"x" * 2000)
                return SimpleNamespace(returncode=0, stderr="")

            with patch("modules.visual_processor.get_effect_for_scene", return_value="slide"), patch(
                "modules.visual_processor.subprocess.run", side_effect=fake_run
            ) as run:
                success = process_single_scene(
                    {"id": 1, "duration": 1, "tipo": "image"},
                    str(asset_path),
                    str(output_path),
                    "ffmpeg",
                    {},
                )

            self.assertTrue(success)
            command = run.call_args.args[0]
            filter_graph = command[command.index("-filter_complex") + 1]
            self.assertIn("overlay=x=", filter_graph)
            self.assertNotIn("overlay=x='", filter_graph)
            self.assertNotIn(":y='", filter_graph)

    def test_missing_scene_asset_uses_fallback_image(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            fallback = Path(temp_dir) / "fallback.jpg"
            fallback.write_bytes(b"image")
            missing_asset = Path(temp_dir) / "missing.mp4"
            scene = {"id": 1, "duration": 1, "tipo": "video"}

            with patch(
                "modules.visual_processor.process_single_scene", return_value=True
            ) as process:
                clips = process_all_scenes(
                    [scene],
                    {1: str(missing_asset)},
                    str(Path(temp_dir) / "clips"),
                    "ffmpeg",
                    {"fallback_image": str(fallback)},
                )

            self.assertEqual(len(clips), 1)
            call_scene, call_asset = process.call_args.args[:2]
            self.assertEqual(call_scene["tipo"], "image")
            self.assertEqual(call_asset, str(fallback))
            self.assertEqual(scene["tipo"], "video")

    def test_missing_scene_asset_without_fallback_is_skipped(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            scene = {"id": 1, "duration": 1, "tipo": "image"}
            with patch("modules.visual_processor.process_single_scene") as process:
                clips = process_all_scenes(
                    [scene],
                    {},
                    str(Path(temp_dir) / "clips"),
                    "ffmpeg",
                    {},
                )

            self.assertEqual(clips, [])
            process.assert_not_called()


if __name__ == "__main__":
    unittest.main()
