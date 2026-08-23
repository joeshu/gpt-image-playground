#!/usr/bin/env python3
import sys
from pathlib import Path
ROOT = Path('/var/minis/skills/gpt-image-playground')
sys.path.insert(0, str(ROOT / 'scripts'))
from provider_base import ProviderContext, ProviderRegistry


def main():
    registry = ProviderRegistry(ROOT / 'scripts', Path('/var/minis/skills/gpt-image-tool/scripts'))
    context = ProviderContext(task={}, task_path=ROOT / 'tests' / 'fixture.json', output_dir=Path('/tmp/out'), workspace_dir=Path('/tmp/work'), dry_run=True, task_id='t')
    assert registry.resolve({'api_mode': 'responses'}).name == 'responses-script'
    assert registry.resolve({'provider': 'fal'}).name == 'fal-script'
    assert registry.resolve({'provider': 'custom-provider'}).name == 'custom-script'
    assert registry.resolve({'provider': 'openai-compatible'}).name == 'images-native'
    assert '--dry-run' in registry.resolve({'provider': 'openai-compatible', 'execution_mode': 'script'}).command(context)
    print('provider_registry_tests=ok')


if __name__ == '__main__':
    main()
