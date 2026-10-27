import io
import json
import sys
import tempfile
import threading
import types
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import agent
import media_research_agent as media
from media_research_agent import MediaResearchAgent, _media_source_permissions
from pipeline_resume import narration_cache_matches, save_narration_hash
from voice_memory import VoiceMemory

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

    def set(self, value):
        self.value = value


class LocalMediaReviewTests(unittest.TestCase):
    def test_audio_only_generates_narration_without_planning_scenes(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            script = root / "roteiro.txt"
            script.write_text("Texto do roteiro para narrar.", encoding="utf-8")
            channels = root / "VideoFactoryAI" / "channels"
            channels.mkdir(parents=True)
            (channels / "documentario.yaml").write_text("tts: {}", encoding="utf-8")
            config = {
                "agent": {"verbose": False},
                "media": {},
                "pipeline": {},
                "tts": {
                    "engine": "edge-tts",
                    "voice": "pt-BR-ThalitaNeural",
                    "rate": "+0%",
                    "pitch": "+0Hz",
                },
            }

            with (
                patch.object(
                    sys,
                    "argv",
                    [
                        "agent.py",
                        str(script),
                        "--audio-only",
                        "--no-subtitles",
                        "--voice",
                        "pt-BR-ThalitaNeural",
                        "--tts-engine",
                        "edge-tts",
                        "--channel",
                        "documentario",
                    ],
                ),
                patch.object(agent, "ROOT_DIR", root),
                patch.object(agent, "AGENT_DIR", root / "VideoFactoryAI"),
                patch.object(agent, "get_config", return_value=config),
                patch.object(
                    agent,
                    "load_config",
                    return_value={"tts": {"voice": "pt-BR-AntonioNeural"}},
                ),
                patch.object(agent, "_VOICE_MEM_AVAILABLE", False),
                patch.object(agent, "generate_voice", return_value="narracao.mp3") as tts,
                patch.object(agent, "plan_scenes") as plan_scenes,
            ):
                agent.main()

            self.assertEqual(
                tts.call_args.args[1],
                str(root / "projetos" / "texto_do_roteiro_para_narrar" / "narracao.mp3"),
            )
            self.assertIn("Texto do roteiro para narrar.", tts.call_args.args[0])
            self.assertEqual(
                tts.call_args.args[2]["tts"]["voice"],
                "pt-BR-ThalitaNeural",
            )
            plan_scenes.assert_not_called()

    def test_script_pipeline_derives_gem_metadata_slug_without_topic(self):
        class PlanningReached(Exception):
            pass

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            script = root / "makete_HO.txt"
            script.write_text("Roteiro de teste com conteúdo suficiente.", encoding="utf-8")
            config = {
                "agent": {"verbose": False},
                "media": {},
                "pipeline": {},
            }
            argv = [
                "agent.py",
                str(script),
                "--media-source-mode",
                "local_only",
                "--resume",
                "--no-subtitles",
            ]

            with (
                patch.object(sys, "argv", argv),
                patch.object(agent, "ROOT_DIR", root),
                patch.object(agent, "AGENT_DIR", root / "VideoFactoryAI"),
                patch.object(agent, "get_config", return_value=config),
                patch.object(agent, "_VOICE_MEM_AVAILABLE", False),
                patch.object(agent, "plan_scenes", side_effect=PlanningReached),
            ):
                with self.assertRaises(PlanningReached):
                    agent.main()

    def test_voice_memory_summary_reports_the_active_gui_voice(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            memory = VoiceMemory(Path(temp_dir))
            memory.save(
                voice="pt-BR-AntonioNeural",
                rate="+0%",
                pitch="+0Hz",
                engine="edge-tts",
            )
            active_config = {
                "tts": {
                    "voice": "pt-BR-FranciscaNeural",
                    "engine": "edge-tts",
                    "rate": "+0%",
                    "pitch": "+0Hz",
                }
            }

            summary = memory.log_summary(active_config)

        self.assertIn("Voz: pt-BR-FranciscaNeural", summary)

    def test_narration_cache_changes_when_selected_voice_changes(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            audio = Path(temp_dir) / "narracao.mp3"
            audio.write_bytes(b"a" * 10_000)
            script = "texto do roteiro"
            antonio_config = {
                "engine": "edge-tts",
                "voice": "pt-BR-AntonioNeural",
                "rate": "+0%",
                "pitch": "+0Hz",
            }
            francisca_config = {
                **antonio_config,
                "voice": "pt-BR-FranciscaNeural",
            }
            save_narration_hash(audio, script, antonio_config)

            antonio_matches = narration_cache_matches(
                audio, script, tts_settings=antonio_config
            )
            francisca_matches = narration_cache_matches(
                audio, script, tts_settings=francisca_config
            )

        self.assertTrue(antonio_matches)
        self.assertFalse(francisca_matches)

    def test_voice_change_regenerates_cached_narration(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            audio = Path(temp_dir) / "narracao.mp3"
            audio.write_bytes(b"a" * 10_000)
            script = "roteiro sem alterações"
            save_narration_hash(
                audio,
                script,
                {
                    "engine": "edge-tts",
                    "voice": "pt-BR-AntonioNeural",
                    "rate": "+0%",
                    "pitch": "+0Hz",
                },
            )

            def fake_run(coroutine):
                coroutine.close()
                audio.write_bytes(b"b" * 10_000)

            with patch.object(agent, "log"), patch.object(
                agent.asyncio, "run", side_effect=fake_run
            ) as run:
                result = agent.generate_voice(
                    script,
                    str(audio),
                    {
                        "pipeline": {"resume_mode": True, "reuse_existing_audio": True},
                        "tts": {
                            "engine": "edge-tts",
                            "voice": "pt-BR-FranciscaNeural",
                            "rate": "+0%",
                            "pitch": "+0Hz",
                        },
                    },
                )

            self.assertEqual(result, str(audio))
            run.assert_called_once()

    def test_media_source_modes_allow_only_the_selected_source_families(self):
        expected = {
            "local_only": (True, False, False),
            "local_then_online": (True, True, True),
            "webchat_only": (False, False, True),
            "internet_images": (False, True, False),
        }
        for mode, permissions in expected.items():
            with self.subTest(mode=mode):
                allowed = _media_source_permissions(mode)
                self.assertEqual(
                    (
                        allowed["local"],
                        allowed["internet_images"],
                        allowed["webchat"],
                    ),
                    permissions,
                )

    def test_cli_accepts_media_source_mode_and_local_folder(self):
        with patch.object(
            sys,
            "argv",
            [
                "agent.py",
                "script.txt",
                "--media-source-mode",
                "webchat_only",
                "--local-media-folder",
                "C:\\library",
            ],
        ):
            args = agent.parse_args()

        self.assertEqual(args.media_source_mode, "webchat_only")
        self.assertEqual(args.local_media_folder, "C:\\library")

    def test_cli_accepts_minimum_local_image_count(self):
        with patch.object(
            sys,
            "argv",
            ["agent.py", "script.txt", "--min-local-images", "150"],
        ):
            args = agent.parse_args()

        self.assertEqual(args.min_local_images, 150)

    def test_cli_exposes_local_media_review_flag(self):
        with patch.object(
            sys,
            "argv",
            ["agent.py", "script.txt", "--review-local-media"],
        ):
            args = agent.parse_args()

        self.assertTrue(args.review_local_media)

    def test_review_callback_emits_gui_event_and_reads_approval(self):
        scene = {"id": 7, "texto": "A locomotiva cruza a ponte."}
        candidate = {
            "path": "C:\\library\\locomotiva.jpg",
            "title": "locomotiva",
            "score": 0.42,
        }
        output = io.StringIO()
        with patch.object(agent.sys, "stdin", io.StringIO("aprovar\n")), \
                patch.dict(agent.os.environ, {"VF_LOCAL_MEDIA_REVIEW_GUI": "1"}), \
                redirect_stdout(output):
            approved = agent._request_local_media_review(scene, candidate)

        self.assertTrue(approved)
        event = output.getvalue().strip()
        self.assertTrue(event.startswith(agent.LOCAL_MEDIA_REVIEW_MARKER))
        payload = json.loads(event[len(agent.LOCAL_MEDIA_REVIEW_MARKER):])
        self.assertEqual(payload["scene_id"], 7)
        self.assertEqual(payload["scene_text"], scene["texto"])
        self.assertEqual(payload["image_path"], candidate["path"])

    def test_gui_sends_review_decision_to_pipeline(self):
        gui = VideoFactoryGUI.__new__(VideoFactoryGUI)
        gui.proc = SimpleNamespace(stdin=io.StringIO(), poll=lambda: 0)
        gui._show_local_media_review = lambda request: request["scene_id"] == 4
        gui._append_log = lambda _message: None
        payload = {
            "scene_id": 4,
            "scene_text": "Uma locomotiva atravessa a ponte.",
            "image_path": "C:\\library\\locomotiva.jpg",
            "image_title": "locomotiva",
            "score": 0.43,
        }

        gui._handle_local_media_review_event(
            agent.LOCAL_MEDIA_REVIEW_MARKER + json.dumps(payload)
        )

        self.assertEqual(gui.proc.stdin.getvalue(), "aprovar\n")

    def test_gui_command_can_enable_or_disable_review(self):
        project = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temp_dir:
            script = Path(temp_dir) / "script.txt"
            script.write_text("documentary script", encoding="utf-8")
            commands = []
            for enabled in (True, False):
                gui = VideoFactoryGUI.__new__(VideoFactoryGUI)
                options = {
                    "project_dir": project,
                    "mode": "script",
                    "script_path": str(script),
                    "channel": "historia",
                    "voice": "pt-BR-FranciscaNeural",
                    "tts_engine": "edge-tts",
                    "whisper_model": "base",
                    "art_director": "standard",
                    "youtube_mode": "off",
                    "subtitle_mode": "burn",
                    "resume": True,
                    "checkpoint": True,
                    "reuse_audio": True,
                    "reuse_approved_images": True,
                    "revalidate_images": False,
                    "force_regeneration": False,
                    "gemini_only": False,
                    "web_research_before_generation": True,
                    "prefer_real_media": True,
                    "gemini_fallback": True,
                    "debug_verbose": True,
                    "ignore_cache": False,
                    "review_local_media": enabled,
                    "media_source_mode": "local_then_online",
                    "local_media_folder": temp_dir,
                }
                for name, value in options.items():
                    setattr(gui, name, Value(value))
                gui.xtts_reference = Value("")
                gui.authorized_video = Value("")
                gui.rights_confirmed = Value(False)
                gui.source_url = Value("")
                command, _ = gui._build_command()
                commands.append(command)

        self.assertIn("--review-local-media", commands[0])
        self.assertNotIn("--review-local-media", commands[1])
        self.assertEqual(
            commands[0][commands[0].index("--voice") + 1],
            "pt-BR-FranciscaNeural",
        )

    def test_gui_command_passes_selected_media_source_and_local_folder(self):
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
                "subtitle_mode": "burn",
                "resume": True,
                "checkpoint": True,
                "reuse_audio": True,
                "reuse_approved_images": True,
                "revalidate_images": False,
                "force_regeneration": False,
                "gemini_only": False,
                "web_research_before_generation": True,
                "prefer_real_media": True,
                "gemini_fallback": True,
                "debug_verbose": True,
                "ignore_cache": False,
                "review_local_media": True,
                "media_source_mode": "Somente biblioteca local",
                "local_media_folder": temp_dir,
            }
            for name, value in options.items():
                setattr(gui, name, Value(value))
            gui.media_source_labels = {
                "local_only": "Somente biblioteca local",
                "local_then_online": "Biblioteca local → internet / WebChat",
                "webchat_only": "Somente WebChat (geração por navegador)",
                "internet_images": "Somente imagens da internet (bancos/Openverse)",
            }
            gui.media_source_by_label = {
                label: key for key, label in gui.media_source_labels.items()
            }
            gui.xtts_reference = Value("")
            gui.authorized_video = Value("")
            gui.rights_confirmed = Value(False)
            gui.source_url = Value("")

            command, _ = gui._build_command()

        self.assertEqual(
            command[command.index("--media-source-mode") + 1],
            "local_only",
        )
        self.assertEqual(
            command[command.index("--local-media-folder") + 1],
            temp_dir,
        )

    def test_gui_selection_keeps_display_label_separate_from_cli_mode(self):
        gui = VideoFactoryGUI.__new__(VideoFactoryGUI)
        gui.media_source_display = Value("Somente biblioteca local")
        gui.media_source_mode = Value("webchat_only")
        gui.media_source_by_label = {
            "Somente biblioteca local": "local_only",
        }

        gui._select_media_source_mode()

        self.assertEqual(gui.media_source_mode.get(), "local_only")


class MediaSourceRoutingTests(unittest.TestCase):
    def _agent(self, root, source_mode, providers):
        instance = MediaResearchAgent.__new__(MediaResearchAgent)
        instance.cfg = {"agent": {"verbose": False}}
        instance.media_source_mode = source_mode
        instance.media_source_permissions = _media_source_permissions(source_mode)
        instance.local_media_mode = "off"
        instance.local_media_enabled = False
        instance.resume_mode = False
        instance.force_regeneration = False
        instance.cache = None
        instance.ignore_cache = True
        instance.pixabay_key = ""
        instance.pexels_key = ""
        instance.unsplash_key = ""
        instance.youtube_mode = "off"
        instance.generation_providers = providers
        instance._provider_locks = {
            provider: threading.Lock() for provider in providers
        }
        instance.stock_candidates_per_scene = 1
        instance.used_urls = set()
        instance.used_hashes = {}
        instance.used_paths = {}
        instance.media_report = []
        instance._source_stats = {}
        instance._prefs = {}
        instance._current_topic = "teste"
        instance._dest_path = lambda scene: str(
            Path(root) / f"scene_{scene['id']}.jpg"
        )
        instance._asset_valid = Mock(return_value=False)
        instance._try_local_image = Mock(return_value=None)
        instance._validate_asset = Mock(return_value=True)
        instance._record_hit = Mock()
        instance._add_report = Mock()
        instance._provider_disabled = Mock(return_value=False)
        instance._disable_provider = Mock()
        instance.web_research_before_generation = False
        instance.gemini_only = False
        instance.gemini_fallback = False
        instance.prefer_real_media = True
        instance._current_topic = "teste"
        return instance

    def _local_only_all_agent(self, root, minimum, extra_selector):
        instance = self._agent(root, "local_only", [])
        instance.local_media_mode = "required"
        instance.local_media_enabled = True
        instance.local_media = SimpleNamespace(index=[object()] * 10)
        instance.min_local_images = minimum
        instance.root = Path(root)
        instance.videos_dir = str(Path(root) / "videos")
        instance.imagens_dir = str(Path(root) / "imagens")
        instance.local_assets_by_scene = {}
        instance._local_media_used_paths = set()
        instance.source_scene = Mock(
            side_effect=lambda scene: str(
                Path(root) / f"primary_{scene['id']}.jpg"
            )
        )
        instance._try_local_image = Mock(side_effect=extra_selector)
        instance._enforce_final_uniqueness = Mock(return_value=0)
        instance._save_prefs = Mock()
        instance._save_media_report = Mock()
        return instance

    def test_local_only_assigns_extra_images_until_minimum_is_met(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)

            def choose_extra(_scene, dest_path):
                destination = Path(dest_path)
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(b"image")
                return dest_path

            instance = self._local_only_all_agent(root, 3, choose_extra)
            scenes = [
                {"id": 1, "tipo": "image", "duration": 3},
                {"id": 2, "tipo": "image", "duration": 3},
            ]

            instance.source_all(scenes)

        assigned = [
            path
            for scene_paths in instance.local_assets_by_scene.values()
            for path in scene_paths
        ]
        self.assertEqual(len(assigned), 3)
        self.assertEqual(len(set(assigned)), 3)

    def test_local_only_fails_if_minimum_local_image_count_cannot_be_met(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            instance = self._local_only_all_agent(root, 3, lambda _scene, _path: None)
            scenes = [
                {"id": 1, "tipo": "image", "duration": 3},
                {"id": 2, "tipo": "image", "duration": 3},
            ]

            with self.assertRaisesRegex(RuntimeError, "mínimo de 3 imagens"):
                instance.source_all(scenes)

    def test_local_only_fails_instead_of_returning_incomplete_asset_map(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            instance = self._local_only_all_agent(root, 0, lambda _scene, _path: None)
            instance.source_scene = Mock(return_value=None)

            with self.assertRaisesRegex(RuntimeError, "cenas sem mídia local"):
                instance.source_all([
                    {"id": 1, "tipo": "image", "duration": 3},
                ])

    def test_webchat_only_does_not_query_internet_image_sources(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            instance = self._agent(temp_dir, "webchat_only", ["chatgpt"])
            web_module = types.ModuleType("web_image_providers")
            web_module.generate_image = Mock(return_value=None)
            web_module.is_provider_limit_reached = Mock(return_value=False)
            with patch.dict(sys.modules, {"web_image_providers": web_module}), \
                    patch.object(media, "_l2_pixabay_image") as pixabay, \
                    patch.object(media, "_l2_free_image_source") as free_image, \
                    patch.object(media, "_l3_openverse_image") as openverse, \
                    patch.object(media.time, "sleep"):
                result = instance.source_scene({
                    "id": 1,
                    "tipo": "image",
                    "query": "locomotiva",
                    "texto": "A locomotiva cruza a ponte.",
                })

        self.assertIsNone(result)
        instance._try_local_image.assert_not_called()
        pixabay.assert_not_called()
        free_image.assert_not_called()
        openverse.assert_not_called()
        web_module.generate_image.assert_called_once()

    def test_internet_images_does_not_generate_through_webchat(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            instance = self._agent(temp_dir, "internet_images", ["gemini"])
            web_module = types.ModuleType("web_image_providers")
            web_module.generate_image = Mock(return_value=None)
            web_module.is_provider_limit_reached = Mock(return_value=False)
            with patch.dict(sys.modules, {"web_image_providers": web_module}), \
                    patch.object(media, "_l2_pixabay_image", return_value=None) as pixabay, \
                    patch.object(media, "_l2_wikimedia_image", return_value=None), \
                    patch.object(media, "_l2_pexels_image", return_value=None), \
                    patch.object(media, "_l2_unsplash_image", return_value=None), \
                    patch.object(media, "_l2_free_image_source", return_value=None), \
                    patch.object(media, "_l3_openverse_image", return_value=None), \
                    patch.object(media.time, "sleep"):
                result = instance.source_scene({
                    "id": 1,
                    "tipo": "video",
                    "query": "locomotiva",
                    "texto": "A locomotiva cruza a ponte.",
                })

        self.assertIsNone(result)
        self.assertEqual(instance.media_source_mode, "internet_images")
        self.assertEqual(instance.media_source_permissions["internet_images"], True)
        instance._try_local_image.assert_not_called()
        pixabay.assert_called_once()
        web_module.generate_image.assert_not_called()
