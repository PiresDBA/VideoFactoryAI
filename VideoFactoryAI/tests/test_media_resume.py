import tempfile
import unittest
from pathlib import Path

from media_research_agent import MediaResearchAgent


class MediaResumeTests(unittest.TestCase):
    def test_resume_skips_final_deduplication(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            agent = MediaResearchAgent.__new__(MediaResearchAgent)
            agent.resume_mode = True
            agent.force_regeneration = False
            agent.videos_dir = temp_dir
            agent.imagens_dir = temp_dir
            agent.media_report = []
            agent.pending_scene_ids = []
            agent._save_prefs = lambda: None
            agent._save_media_report = lambda: None
            agent._enforce_final_uniqueness = lambda *args: self.fail(
                "resume must not regenerate cached assets during final deduplication"
            )

            result = agent.source_all([])

            self.assertEqual(result, {})

    def test_resume_returns_sufficient_existing_asset_without_revalidation(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            asset_path = Path(temp_dir) / "scene.jpg"
            asset_path.write_bytes(b"x" * 15_001)
            agent = MediaResearchAgent.__new__(MediaResearchAgent)
            agent.resume_mode = True
            agent.force_regeneration = False
            agent.ignore_cache = False
            agent.videos_dir = temp_dir
            agent.imagens_dir = temp_dir
            agent.used_hashes = {}
            agent.used_paths = {}
            agent.used_urls = set()
            agent.media_report = []
            agent._dest_path = lambda scene: str(asset_path)
            agent._add_report = lambda *args: None
            agent._validate_asset = lambda *args: self.fail("resumed asset must not be revalidated")

            result = agent.source_scene({"id": 1, "tipo": "image", "arquivo": "scene.jpg"})

            self.assertEqual(result, str(asset_path))
            self.assertIn(str(asset_path), agent.used_paths)

    def test_resume_does_not_skip_asset_below_minimum_size(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            asset_path = Path(temp_dir) / "scene.jpg"
            asset_path.write_bytes(b"x" * 100)
            agent = MediaResearchAgent.__new__(MediaResearchAgent)
            agent.resume_mode = True
            agent.force_regeneration = False
            agent.ignore_cache = False
            agent.videos_dir = temp_dir
            agent.imagens_dir = temp_dir
            agent.used_hashes = {}
            agent.used_paths = {}
            agent.used_urls = set()
            agent.media_report = []
            agent.cache = None
            agent.pixabay_key = ""
            agent.pexels_key = ""
            agent.unsplash_key = ""
            agent.youtube_mode = "off"
            agent.stock_candidates_per_scene = 1
            agent._dest_path = lambda scene: str(asset_path)
            agent._add_report = lambda *args: None
            agent._validate_asset = lambda *args: False
            agent._record_hit = lambda *args: None
            agent.generation_providers = []
            agent._provider_locks = {}
            agent._last_visual_feedback = ""
            agent._save_media_report = lambda: None

            result = agent.source_scene({"id": 1, "tipo": "image", "arquivo": "scene.jpg"})

            self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
