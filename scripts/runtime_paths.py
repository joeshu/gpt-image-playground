"""Portable paths shared by CLI, Agent, REST and generic skill runners."""

import os
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parent.parent
MINIS_ROOT = Path('/var/minis/skills/gpt-image-playground')
MINIS_DATA = Path('/var/minis/workspace/gpt-image-playground')
MINIS_ATTACHMENTS = Path('/var/minis/attachments/gpt-image-playground')
LOCAL_DATA = PACKAGE_ROOT / '.monkeycode' / 'runtime' / 'gpt-image-playground'
LOCAL_ATTACHMENTS = PACKAGE_ROOT / 'outputs' / 'gpt-image-playground'


def _path_env(name):
    value = os.environ.get(name, '').strip()
    return Path(value).expanduser() if value else None


def skill_root():
    configured = _path_env('GPT_IMAGE_PLAYGROUND_ROOT')
    if configured:
        return configured
    if (PACKAGE_ROOT / 'profiles.json').is_file():
        return PACKAGE_ROOT
    return MINIS_ROOT


def data_root():
    configured = _path_env('GPT_IMAGE_PLAYGROUND_DATA')
    if configured:
        return configured
    if (PACKAGE_ROOT / 'profiles.json').is_file():
        return LOCAL_DATA
    return MINIS_DATA


def attachments_root():
    configured = _path_env('GPT_IMAGE_PLAYGROUND_ATTACHMENTS')
    if configured:
        return configured
    if (PACKAGE_ROOT / 'profiles.json').is_file():
        return LOCAL_ATTACHMENTS
    return MINIS_ATTACHMENTS


def external_tool_root():
    return _path_env('GPT_IMAGE_TOOL_ROOT') or Path('/var/minis/skills/gpt-image-tool')


def allowed_roots():
    configured = _path_env('GPT_IMAGE_PLAYGROUND_INPUT_ROOT')
    roots = [attachments_root(), data_root(), skill_root(), Path('/var/minis/mounts')]
    if configured:
        roots.append(configured)
    return tuple(dict.fromkeys(root.resolve() for root in roots))
