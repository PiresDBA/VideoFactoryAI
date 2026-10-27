# Subtitle modes and Gemini score TDD evidence

## User journeys

- A creator can generate a PT-BR subtitle file from an existing narration without running voice generation, image acquisition, or video rendering.
- A creator can choose to burn PT-BR subtitles into a full video render, or disable subtitles.
- A creator selecting a script starts the file picker in `ROOT_DIR/roteiros`.
- A Gemini-approved image with a score greater than 85 is accepted without a second Director of Art evaluation; lower scores retain the existing validation path.

## RED/GREEN evidence

| Guarantee | Test | RED evidence | GREEN evidence |
|---|---|---|---|
| `--subtitles-only` is accepted and uses existing narration without TTS | `test_cli_exposes_standalone_subtitles_mode`, `test_generates_subtitles_from_existing_audio_without_regenerating_voice`, `test_standalone_subtitles_reports_missing_narration` in `tests/test_agent_resume_cli.py` | CLI rejected the option; helper did not exist; force-refresh behavior differed | All pass |
| GUI supports burn-in and standalone SRT modes | `test_build_command_passes_resume_and_media_options`, `test_subtitles_only_mode_uses_standalone_flag` in `tests/test_gui_media_controls.py` | Existing boolean UI could not build the new standalone command | Both pass |
| Script picker starts in the scripts folder | `test_script_picker_starts_in_roteiros_directory` in `tests/test_gui_media_controls.py` | It opened in the application folder | Passes with `ROOT_DIR/roteiros` |
| Gemini score above 85 overrides the Director's content rejection | `test_gemini_score_above_85_overrides_art_director_content_rejection`, `test_validate_all_uses_matching_high_score_from_media_agent` in `tests/test_image_validator_agent.py` | Validator rejected the score-86 image and re-ran the Director for a score-91 image | Both pass |
| Scores of 85 do not trigger automatic approval; heuristic fallback scores are not treated as Gemini verdicts | `test_gemini_score_of_85_does_not_bypass_art_director`, `test_high_score_from_heuristic_fallback_does_not_count_as_gemini_approval` in `tests/test_image_validator_agent.py` | Fallback score of 95 incorrectly appeared to be a Gemini verdict | All pass |
| Acquisition propagates only high-score approvals, tied to the exact asset | `test_gemini_high_score_is_recorded_for_art_director_bypass`, `test_gemini_score_of_85_is_not_recorded_as_auto_approval` in `tests/test_media_resume.py` | A score-91 verdict was not recorded for the Director; score threshold behavior was missing | Both pass |

## Validation

- Full suite: unittest discovery under `VideoFactoryAI/tests` — 55 tests passed.
- Focused tests: subtitle/GUI/resume/Gemini regression targets — 27 tests passed.
- Syntax: `py_compile` on `agent.py`, `videofactory_gui.py`, `media_research_agent.py`, and `image_validator_agent.py` — passed.
- Patch formatting: `git diff --check` on changed source, docs, and test files — passed.

Whisper and Gemini services were not called during tests; external evaluations were mocked. Coverage measurement and a real GUI/render run were not performed. Current subtitle-file output is PT-BR only; English and Spanish translation remain out of scope pending a translation-provider choice.
