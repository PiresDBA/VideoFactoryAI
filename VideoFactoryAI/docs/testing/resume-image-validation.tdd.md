# Resume image validation TDD evidence

## Source and journey

No plan file was provided. The user journey is: when resuming a production, reuse image assets already present in the checkpoint without validating or regenerating them again, unless image revalidation is explicitly requested.

## Execution evidence

| Behavior | Test | RED evidence | GREEN evidence |
|---|---|---|---|
| A checkpoint asset reused during resume bypasses image validation when reuse is enabled | `test_resume_skips_validation_for_assets_reused_from_checkpoint` in `tests/test_image_validator_agent.py` | Failed because `validate_all()` called `_validate_scene()` for the resumed image | Passed in targeted tests and full suite |
| Explicit revalidation still validates a resumed image | `test_explicit_revalidation_does_not_skip_resumed_assets` in `tests/test_image_validator_agent.py` | Not applicable; this is a guard against regressing the explicit override | Passed in targeted tests and full suite |
| Media acquisition records which assets were reused from the checkpoint | `test_resume_returns_sufficient_existing_asset_without_revalidation` in `tests/test_media_resume.py` | Not applicable; existing resume behavior extended with an assertion for tracking | Passed in targeted tests and full suite |

Validation commands:

- RED: `C:\Docling\venv\Scripts\python.exe` running unittest discovery for `test_image_validator_agent.py` — 1 expected failure, caused by the missing resume skip.
- GREEN: unittest discovery for `test_image_validator_agent.py` and `test_media_resume.py` — 11 tests passed.
- Full suite: unittest discovery under `tests` — 44 tests passed.
- Syntax: `C:\Docling\venv\Scripts\python.exe -m py_compile` on `image_validator_agent.py` and `media_research_agent.py` — passed.
- Formatting: `git diff --check` on changed source and test files — passed.

## Guarantee and limitations

Only scene IDs returned by `MediaResearchAgent`'s valid local-resume branch are skipped by the ImageValidator, and only when resume reuse is enabled, force regeneration is off, and explicit revalidation is off. Newly sourced assets and missing/undersized assets continue through the existing validation path. Coverage measurement was not run.
