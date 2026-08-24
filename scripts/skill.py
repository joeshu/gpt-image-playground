#!/usr/bin/env python3
"""Universal command adapter for Codex, Minis, Claude and other Agents."""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent

try:
    from version import VERSION
except ImportError:
    from scripts.version import VERSION


def run_script(name, arguments):
    command = [sys.executable, str(ROOT / 'scripts' / name), *arguments]
    completed = subprocess.run(command, text=True, capture_output=True, env=os.environ.copy())
    output = completed.stdout.strip()
    if completed.returncode:
        message = completed.stderr.strip() or output or f'{name} 执行失败'
        raise RuntimeError(message)
    if output:
        try:
            return json.loads(output)
        except json.JSONDecodeError:
            return {'status': 'ok', 'output': output}
    return {'status': 'ok'}


def check():
    scripts = sorted((ROOT / 'scripts').glob('*.py'))
    compile_result = subprocess.run(
        [sys.executable, '-m', 'py_compile', *(str(path) for path in scripts)],
        text=True, capture_output=True,
    )
    if compile_result.returncode:
        raise RuntimeError(compile_result.stderr.strip() or 'Python 语法检查失败')
    from runtime_paths import attachments_root, data_root, skill_root
    return {
        'status': 'ready',
        'name': 'gpt-image-playground',
        'version': VERSION,
        'root': str(skill_root()),
        'data_dir': str(data_root()),
        'attachments_dir': str(attachments_root()),
        'commands': ['generate', 'agent', 'serve', 'check', 'doctor'],
    }


def doctor():
    from runtime_paths import attachments_root, data_root, skill_root
    checks = {}
    try:
        import sqlite3  # noqa: F401
        checks['python'] = 'ok'
        checks['sqlite'] = 'ok'
    except Exception as exc:
        checks['python'] = f'failed: {exc}'
        checks['sqlite'] = 'failed'
    checks['skill_manifest'] = 'ok' if (ROOT / 'SKILL.md').is_file() else 'failed'
    checks['web_dist'] = 'ok' if (ROOT / 'web-react' / 'dist' / 'index.html').is_file() else 'failed'
    checks['profiles'] = 'ok' if (ROOT / 'profiles.json').is_file() else 'warning: profiles.json missing'
    try:
        import requests  # noqa: F401
        checks['requests'] = 'ok'
    except ImportError:
        checks['requests'] = 'missing: install Python package requests'
    for path in (data_root(), attachments_root()):
        try:
            path.mkdir(parents=True, exist_ok=True)
            checks[f'write:{path.name}'] = 'ok'
        except OSError as exc:
            checks[f'write:{path.name}'] = f'failed: {exc}'
    hard = [value for value in checks.values() if str(value).startswith('failed')]
    return {'status': 'ready' if not hard else 'failed', 'name': 'gpt-image-playground', 'version': VERSION, 'root': str(skill_root()), 'checks': checks}


def main():
    parser = argparse.ArgumentParser(description='GPT Image Playground 通用 Agent 技能入口')
    parser.add_argument('command', choices=['check', 'doctor', 'generate', 'agent', 'serve'])
    args, remainder = parser.parse_known_args()
    try:
        result = doctor() if args.command == 'doctor' else check() if args.command == 'check' else run_script(
            {'generate': 'playground.py', 'agent': 'agent.py', 'serve': 'api_server.py'}[args.command],
            remainder,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (OSError, RuntimeError, ValueError) as exc:
        print(json.dumps({'status': 'failed', 'error': str(exc)}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(1)


if __name__ == '__main__':
    main()
