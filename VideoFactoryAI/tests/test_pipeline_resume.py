import hashlib
import tempfile
import unittest
from pathlib import Path

from pipeline_resume import (
    build_resume_report,
    narration_cache_matches,
    script_sha256,
)


class PipelineResumeTests(unittest.TestCase):
    def test_resume_report_counts_only_existing_assets_over_minimum_size(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            image = Path(temp_dir) / "scene.jpg"
            video = Path(temp_dir) / "scene.mp4"
            small_image = Path(temp_dir) / "small.jpg"
            image.write_bytes(b"x" * 15_000)
            video.write_bytes(b"x" * 100_000)
            small_image.write_bytes(b"x" * 14_999)

            report = build_resume_report(
                [
                    {"id": 1, "tipo": "image"},
                    {"id": 2, "tipo": "video"},
                    {"id": 3, "tipo": "image"},
                    {"id": 4, "tipo": "image"},
                ],
                {
                    1: str(image),
                    2: str(video),
                    3: str(small_image),
                },
                image_min_bytes=15_000,
                video_min_bytes=100_000,
            )

            self.assertEqual(report["total"], 4)
            self.assertEqual(report["completed"], 2)
            self.assertEqual(report["pending_scene_ids"], [3, 4])

    def test_narration_cache_requires_matching_script_hash_and_minimum_size(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            audio = Path(temp_dir) / "narracao.mp3"
            audio.write_bytes(b"a" * 10_000)
            hash_file = Path(f"{audio}.script.sha256")
            script = "texto do roteiro"
            hash_file.write_text(script_sha256(script), encoding="ascii")

            self.assertTrue(narration_cache_matches(audio, script, minimum_bytes=10_000))
            self.assertFalse(narration_cache_matches(audio, "roteiro alterado", minimum_bytes=10_000))
            self.assertFalse(narration_cache_matches(audio, script, minimum_bytes=10_001))

    def test_script_hash_is_sha256_of_utf8_text(self):
        self.assertEqual(
            script_sha256("Olá"),
            hashlib.sha256("Olá".encode("utf-8")).hexdigest(),
        )


if __name__ == "__main__":
    unittest.main()
