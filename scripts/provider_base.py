#!/usr/bin/env python3
"""Provider abstraction used by the image task orchestrator.

The first migration stage keeps the existing provider executors behind one
stable interface. This lets CLI, REST, batch, and Agent share routing and
error semantics while provider implementations are migrated incrementally.
"""
from dataclasses import dataclass
from pathlib import Path
import os
import subprocess
import sys
import time


class ProviderError(RuntimeError):
    def __init__(self, message, *, provider=None, code='provider_error', returncode=None):
        super().__init__(message)
        self.provider = provider
        self.code = code
        self.returncode = returncode


@dataclass(frozen=True)
class ProviderContext:
    task: dict
    task_path: Path
    output_dir: Path
    workspace_dir: Path
    dry_run: bool
    task_id: str
    retries: int = 0


class Provider:
    name = 'base'

    def command(self, context):
        raise NotImplementedError

    def run(self, context, env):
        command = self.command(context)
        completed = subprocess.run(command, text=True, capture_output=True, env=env)
        if completed.returncode:
            raise ProviderError(
                (completed.stderr or completed.stdout or 'Provider 执行失败').strip()[:2000],
                provider=self.name, returncode=completed.returncode,
            )
        return completed.stdout


class ScriptProvider(Provider):
    def __init__(self, name, script):
        self.name = name
        self.script = Path(script)

    def command(self, context):
        if not self.script.is_file():
            raise ProviderError(f'Provider 执行器不存在: {self.script}', provider=self.name, code='missing_provider')
        command = [sys.executable, str(self.script), '--task', str(context.task_path),
                   '--out-prefix', context.task_id, '--attachments-dir', str(context.output_dir),
                   '--workspace-dir', str(context.workspace_dir)]
        if context.dry_run:
            command.append('--dry-run')
        return command


class ProviderRegistry:
    def __init__(self, base_dir, legacy_dir=None):
        base = Path(base_dir)
        legacy = Path(legacy_dir) if legacy_dir else None
        self.providers = {
            'images': ScriptProvider('images', base / 'generate.py'),
            'responses': ScriptProvider('responses', base / 'responses_provider.py'),
            'fal': ScriptProvider('fal', base / 'fal_provider.py'),
            'custom': ScriptProvider('custom', base / 'custom_provider.py'),
        }
        self.legacy_images = ScriptProvider('images-legacy', legacy / 'generate.py') if legacy else None

    def resolve(self, task):
        if task.get('api_mode') == 'responses':
            key = 'responses'
        elif task.get('provider') in ('fal', 'fal.ai'):
            key = 'fal'
        elif task.get('provider') not in ('openai', 'openai-compatible', None):
            key = 'custom'
        else:
            key = 'images'
        provider = self.providers[key]
        if key == 'images' and not provider.script.is_file() and self.legacy_images:
            provider = self.legacy_images
        return provider

    def run(self, context, env):
        return self.resolve(context.task).run(context, env)


def provider_environment(env, task):
    result = dict(env)
    key_env = task.get('api_key_env', 'GPT_IMAGE_API_KEY')
    if result.get(key_env) and not result.get('GPT_IMAGE_API_KEY'):
        result['GPT_IMAGE_API_KEY'] = result[key_env]
    return result
