import tempfile
import unittest
import hashlib
import json
from pathlib import Path

from image_validator_agent import ImageValidatorAgent, ValidationResult


class ImageValidatorRegenerationTests(unittest.TestCase):
    def test_resume_reuses_approved_asset_when_hash_matches(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            asset_path = root / "scene.jpg"
            asset_path.write_bytes(b"approved image")
            asset_hash = hashlib.sha256(asset_path.read_bytes()).hexdigest()
            memory_dir = root / "memory"
            memory_dir.mkdir()
            (memory_dir / "validated_assets.json").write_text(
                json.dumps({
                    "1": {
                        "asset": str(asset_path),
                        "approved": True,
                        "hash": asset_hash,
                    }
                }),
                encoding="utf-8",
            )
            agent = ImageValidatorAgent(
                cfg={
                    "pipeline": {"resume_mode": True},
                    "media": {"image_validator_use_llm": False},
                },
                project_dir=root,
                topic="",
                script_text="",
                scenes=[{"id": 1, "query": "scene"}],
                asset_map={1: str(asset_path)},
                log_func=lambda *args, **kwargs: None,
            )
            agent._validate_scene = lambda *args: self.fail("cached asset must not be validated")

            results = agent.validate_all(None)

            self.assertTrue(results[1].approved)
            self.assertEqual(results[1].asset_path, str(asset_path))

    def test_resume_revalidates_asset_when_hash_changed(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            asset_path = root / "scene.jpg"
            asset_path.write_bytes(b"changed image")
            memory_dir = root / "memory"
            memory_dir.mkdir()
            (memory_dir / "validated_assets.json").write_text(
                json.dumps({
                    "1": {
                        "asset": str(asset_path),
                        "approved": True,
                        "hash": "old-hash",
                    }
                }),
                encoding="utf-8",
            )
            agent = ImageValidatorAgent(
                cfg={
                    "pipeline": {"resume_mode": True},
                    "media": {"image_validator_use_llm": False},
                },
                project_dir=root,
                topic="",
                script_text="",
                scenes=[{"id": 1, "query": "scene"}],
                asset_map={1: str(asset_path)},
                log_func=lambda *args, **kwargs: None,
            )
            calls = []
            agent._validate_scene = lambda scene, path: calls.append(path) or ValidationResult(
                scene_id=1,
                approved=True,
                score=90,
                reason="Approved",
                suggestions=[],
                timing_ok=True,
                content_ok=True,
                asset_path=str(asset_path),
                asset_type="image",
                query_used="scene",
            )

            results = agent.validate_all(None)

            self.assertEqual(calls, [str(asset_path)])
            self.assertTrue(results[1].approved)
            saved = json.loads((memory_dir / "validated_assets.json").read_text(encoding="utf-8"))
            self.assertEqual(saved["1"]["hash"], hashlib.sha256(asset_path.read_bytes()).hexdigest())

    def test_heuristic_approves_short_cross_language_query(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            agent = ImageValidatorAgent(
                cfg={"media": {"image_validator_use_llm": False}},
                project_dir=Path(temp_dir),
                topic="",
                script_text="",
                scenes=[],
                asset_map={},
                log_func=lambda *args, **kwargs: None,
            )

            approved, _, _, _, _ = agent._validate_content_heuristic(
                "ferrovia em miniatura", "model railroad", "image"
            )

            self.assertTrue(approved)

    def test_heuristic_accepts_score_above_thirty_five(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            agent = ImageValidatorAgent(
                cfg={"media": {"image_validator_use_llm": False}},
                project_dir=Path(temp_dir),
                topic="",
                script_text="",
                scenes=[],
                asset_map={},
                log_func=lambda *args, **kwargs: None,
            )

            approved, score, _, _, _ = agent._validate_content_heuristic(
                "ferrovia miniatura modelismo locomotiva trilho",
                "ferrovia modelismo maquete trem",
                "image",
            )

            self.assertEqual(score, 40)
            self.assertTrue(approved)

    def test_regenerates_scene_with_corrected_query_and_topic(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            asset_path = Path(temp_dir) / "scene.jpg"
            asset_path.write_bytes(b"image")
            scene = {"id": 1, "query": "original query", "wikimedia_q": "original query"}
            agent = ImageValidatorAgent(
                cfg={"media": {"image_validator_use_llm": False}},
                project_dir=Path(temp_dir),
                topic="documentary topic",
                script_text="",
                scenes=[scene],
                asset_map={1: str(asset_path)},
                log_func=lambda *args, **kwargs: None,
            )
            validation_results = iter(
                [
                    ValidationResult(
                        scene_id=1,
                        approved=False,
                        score=20,
                        reason="Wrong image",
                        suggestions=[],
                        timing_ok=True,
                        content_ok=False,
                        asset_path=str(asset_path),
                        asset_type="image",
                        query_used="original query",
                        corrected_query="corrected query",
                    ),
                    ValidationResult(
                        scene_id=1,
                        approved=True,
                        score=90,
                        reason="Approved",
                        suggestions=[],
                        timing_ok=True,
                        content_ok=True,
                        asset_path=str(asset_path),
                        asset_type="image",
                        query_used="corrected query",
                    ),
                ]
            )
            agent._validate_scene = lambda scene, path: next(validation_results)

            class MediaAgent:
                def __init__(self):
                    self.scene = None
                    self.topic = None

                def regenerate_scene(self, scene, topic=""):
                    self.scene = scene
                    self.topic = topic
                    return str(asset_path)

            media_agent = MediaAgent()

            agent.validate_all(media_agent)

            self.assertEqual(media_agent.scene["query"], "corrected query")
            self.assertEqual(media_agent.scene["wikimedia_q"], "corrected query")
            self.assertEqual(media_agent.topic, "documentary topic")
            self.assertEqual(scene["query"], "original query")
            self.assertEqual(scene["wikimedia_q"], "original query")

    def test_failed_regeneration_disables_regeneration_and_preserves_asset(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            asset_path = Path(temp_dir) / "scene.jpg"
            asset_path.write_bytes(b"image")
            scene = {"id": 1, "query": "original query"}
            agent = ImageValidatorAgent(
                cfg={"media": {"image_validator_use_llm": False, "image_validator_max_retries": 2}},
                project_dir=Path(temp_dir),
                topic="documentary topic",
                script_text="",
                scenes=[scene],
                asset_map={1: str(asset_path)},
                log_func=lambda *args, **kwargs: None,
            )
            agent._validate_scene = lambda scene, path: ValidationResult(
                scene_id=1,
                approved=False,
                score=20,
                reason="Wrong image",
                suggestions=[],
                timing_ok=True,
                content_ok=False,
                asset_path=str(asset_path),
                asset_type="image",
                query_used="original query",
                regenerate=True,
                corrected_query="corrected query",
            )

            class MediaAgent:
                calls = 0

                def regenerate_scene(self, scene, topic=""):
                    self.calls += 1
                    return None

            media_agent = MediaAgent()

            results = agent.validate_all(media_agent)

            self.assertEqual(media_agent.calls, 1)
            self.assertFalse(results[1].regenerate)
            self.assertEqual(agent.asset_map[1], str(asset_path))


if __name__ == "__main__":
    unittest.main()
