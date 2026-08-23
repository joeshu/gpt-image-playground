# User Instruction Memory

This file records user instructions, preferences, and project operating knowledge for future interactions.

## Entries

### Project Knowledge Summary
- Date: 2026-08-23
- Context: Discovered while validating the image generation skill after provider and Agent changes
- Category: Build Methods
- Instructions:
  - Run `python3 -m py_compile scripts/*.py tests/*.py` before the functional checks.
  - Run provider tests with `PYTHONPATH=scripts python3 tests/test_providers.py`.
  - Run API tests with `PYTHONPATH=scripts python3 tests/test_api.py`.
   - Validate CLI behavior with `python3 scripts/skill.py check`, `python3 scripts/playground.py --validate-profiles`, and dry-run commands.

### Project Knowledge Summary
- Date: 2026-08-23
- Context: Discovered while correcting generated-image artifact paths
- Category: Environment Configuration
- Instructions:
  - When running from the repository, generated images belong under `outputs/gpt-image-playground/`.
  - Runtime data belongs under `.monkeycode/runtime/gpt-image-playground/`.
  - `GPT_IMAGE_PLAYGROUND_DATA` and `GPT_IMAGE_PLAYGROUND_ATTACHMENTS` override these local defaults for hosted environments.
