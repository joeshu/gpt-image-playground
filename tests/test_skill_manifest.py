#!/usr/bin/env python3
"""Validate the portable skill manifest and UI metadata."""

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def load_frontmatter(path):
    text = path.read_text(encoding='utf-8')
    if not text.startswith('---\n'):
        raise AssertionError(f'{path.name} is missing YAML frontmatter')
    _, raw, _ = text.split('---', 2)
    return yaml.safe_load(raw)


def main():
    manifest = load_frontmatter(ROOT / 'SKILL.md')
    assert set(manifest) == {'name', 'description'}
    assert manifest['name'] == 'gpt-image-playground'
    assert manifest['description'].strip()

    metadata = yaml.safe_load((ROOT / 'agents' / 'openai.yaml').read_text(encoding='utf-8'))
    interface = metadata['interface']
    assert 25 <= len(interface['short_description']) <= 64
    assert '$gpt-image-playground' in interface['default_prompt']
    print('skill_manifest_tests=ok')


if __name__ == '__main__':
    main()
