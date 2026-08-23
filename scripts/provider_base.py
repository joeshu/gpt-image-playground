#!/usr/bin/env python3
"""Provider registry with script and native execution modes."""
from dataclasses import dataclass
from pathlib import Path
import base64
import importlib.util
import io
import json
import mimetypes
import os
import subprocess
import sys
import urllib.request


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
    mode = 'native'

    def run(self, context, env):
        raise NotImplementedError


class ScriptProvider(Provider):
    mode = 'script'

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

    def run(self, context, env):
        completed = subprocess.run(self.command(context), text=True, capture_output=True, env=env)
        if completed.returncode:
            raise ProviderError((completed.stderr or completed.stdout or 'Provider 执行失败').strip()[:2000],
                                provider=self.name, returncode=completed.returncode)
        return completed.stdout


def _multipart_value(value):
    if isinstance(value, str) and value.startswith('data:'):
        header, encoded = value.split(',', 1)
        mime = header[5:].split(';', 1)[0] or 'application/octet-stream'
        return base64.b64decode(encoded), mime
    if isinstance(value, str) and value.startswith(('http://', 'https://')):
        with urllib.request.urlopen(value, timeout=300) as response:
            return response.read(), response.headers.get_content_type() or 'application/octet-stream'
    path = Path(value)
    if not path.is_file():
        raise ProviderError(f'图片文件不存在: {value}', provider='images-native', code='missing_image')
    mime, _ = mimetypes.guess_type(str(path))
    return path.read_bytes(), mime or 'application/octet-stream'


def _stream_request(url, api_key, payload, timeout, events_path, partial_dir, task_id, output_format):
    request = urllib.request.Request(url, data=json.dumps(payload).encode(), method='POST', headers={'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json', 'Accept': 'text/event-stream'})
    final = None
    events_path.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(request, timeout=timeout) as response, events_path.open('w', encoding='utf-8') as stream:
        for raw in response:
            line = raw.decode('utf-8', errors='replace').strip()
            if not line.startswith('data:'):
                continue
            text = line[5:].strip()
            if not text or text == '[DONE]':
                continue
            try:
                event = json.loads(text)
            except json.JSONDecodeError:
                continue
            partial = event.get('partial_image_b64') or event.get('b64_json')
            if partial and 'partial' in event.get('type', ''):
                partial_dir.mkdir(parents=True, exist_ok=True)
                index = event.get('partial_image_index', 0)
                path = partial_dir / f'{task_id}-partial-{index}.{'jpg' if output_format in ('jpg', 'jpeg') else output_format}'
                path.write_bytes(base64.b64decode(partial)); event['partial_image_path'] = str(path)
            stream.write(json.dumps(event, ensure_ascii=False) + '\\n'); stream.flush()
            if event.get('data') or event.get('b64_json') or event.get('url'):
                if event.get('type', '').endswith('.completed') and isinstance(event.get('data'), list):
                    final = {'data': event['data']}
                else:
                    final = event
    return final or {}


def _multipart_request(url, api_key, fields, files, timeout):
    boundary = '----gip-' + os.urandom(12).hex()
    chunks = []
    for key, value in fields.items():
        chunks.extend([f'--{boundary}\\r\\n'.encode(), f'Content-Disposition: form-data; name="{key}"\\r\\n\\r\\n'.encode(), str(value).encode(), b'\\r\\n'])
    for field, filename, content, mime in files:
        chunks.extend([f'--{boundary}\\r\\n'.encode(), f'Content-Disposition: form-data; name="{field}"; filename="{filename}"\\r\\n'.encode(), f'Content-Type: {mime}\\r\\n\\r\\n'.encode(), content, b'\\r\\n'])
    chunks.append(f'--{boundary}--\\r\\n'.encode())
    request = urllib.request.Request(url, data=b''.join(chunks), method='POST', headers={'Authorization': f'Bearer {api_key}', 'Content-Type': f'multipart/form-data; boundary={boundary}', 'Accept': 'application/json'})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
    except Exception as exc:
        raise ProviderError(f'Native multipart 请求失败: {exc}', provider='images-native', code='native_request_failed') from exc
    try:
        return json.loads(raw.decode('utf-8'))
    except Exception as exc:
        raise ProviderError('Native multipart 返回非 JSON', provider='images-native', code='invalid_response') from exc


class NativeImagesProvider(Provider):
    name = 'images-native'
    mode = 'native'

    def __init__(self, script_dir):
        self.script_dir = Path(script_dir)
        self._generate = None

    def _module(self):
        if self._generate is None:
            path = self.script_dir / 'generate.py'
            spec = importlib.util.spec_from_file_location('gip_native_generate', path)
            if not spec or not spec.loader:
                raise ProviderError(f'原生 Images Provider 不存在: {path}', provider=self.name, code='missing_provider')
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            self._generate = module
        return self._generate

    def run(self, context, env):
        g = self._module()
        task = context.task
        endpoint = task.get('endpoint') or env.get('GPT_IMAGE_ENDPOINT') or env.get('GPT_IMAGE_API_URL')
        key_name = task.get('api_key_env', 'GPT_IMAGE_API_KEY')
        api_key = env.get(key_name) or env.get('GPT_IMAGE_API_KEY')
        if not endpoint:
            raise ProviderError('Native Images Provider 缺少 endpoint', provider=self.name, code='missing_endpoint')
        if not api_key and not context.dry_run:
            raise ProviderError(f'Native Images Provider 缺少 {key_name}', provider=self.name, code='missing_api_key')
        payload = {
            'prompt': task.get('prompt', ''),
            'n': max(1, min(int(task.get('n', 1)), 16)),
            'size': g.normalize_size(task.get('size', '1:1')),
            'quality': task.get('quality', 'low'),
            'output_format': task.get('output_format', 'png'),
        }
        model = task.get('model')
        if model is not None and not task.get('omit_model'):
            payload['model'] = model
        for key in ('background', 'moderation', 'output_compression'):
            if task.get(key) is not None:
                payload[key] = task[key]
        if task.get('images') or task.get('image_urls'):
            values = task.get('images') or task.get('image_urls')
            payload['image_urls'] = g.normalize_image_inputs(values)
        if task.get('mask'):
            payload['mask'] = g.normalize_image_inputs([task['mask']])[0]
        request_path = context.workspace_dir / f'{context.task_id}-native-request.json'
        request_path.parent.mkdir(parents=True, exist_ok=True)
        edit_values = task.get('images') or task.get('image_urls') or []
        is_edit = bool(edit_values or task.get('mask'))
        request_endpoint = endpoint
        if is_edit and request_endpoint.rstrip('/').endswith('/images/generations'):
            request_endpoint = request_endpoint.rstrip('/')[:-len('generations')] + 'edits'
        request_path.write_text(json.dumps({**payload, 'endpoint': request_endpoint, 'mode': 'native', 'request_type': 'multipart' if is_edit else 'json'}, ensure_ascii=False, indent=2))
        if context.dry_run:

            return json.dumps({'status': 'dry_run', 'task_id': context.task_id, 'endpoint': endpoint,
                               'model': model if not task.get('omit_model') else None,
                               'omit_model': bool(task.get('omit_model')), 'request_file': str(request_path)}, ensure_ascii=False)
        try:
            timeout = int(task.get('request_timeout', 900))
            if is_edit:
                fields = {key: value for key, value in payload.items() if key not in ('image_urls', 'mask')}
                files = []
                for index, value in enumerate(edit_values):
                    content, mime = _multipart_value(value)
                    files.append(('image[]', f'image-{index + 1}', content, mime))
                if task.get('mask'):
                    content, mime = _multipart_value(task['mask'])
                    files.append(('mask', 'mask', content, mime))
                response = _multipart_request(request_endpoint, api_key, fields, files, timeout)
            else:
                if task.get('stream'):
                    stream_payload = dict(payload); stream_payload['stream'] = True
                    response = _stream_request(endpoint, api_key, stream_payload, timeout, context.workspace_dir / f'{context.task_id}-events.jsonl', context.output_dir, context.task_id, task.get('output_format', 'png'))
                else:
                    response = g.request_json('POST', endpoint, g.build_headers(api_key), payload=payload,
                                              timeout=timeout, debug_prefix=request_path)
            saved = g.decode_b64_images(response, context.output_dir, context.task_id, task.get('output_format', 'png'))
            if not saved:
                raise ProviderError('Native Images Provider 返回中没有图片数据', provider=self.name, code='empty_result')
            result = {'status': 'completed', 'task_id': context.task_id, 'endpoint': request_endpoint,
                      'model': model, 'saved_images': saved, 'request_file': str(request_path),
                      'stream': bool(task.get('stream'))}
            if task.get('stream'):
                result['events_file'] = str(context.workspace_dir / f'{context.task_id}-events.jsonl')
            return json.dumps(result, ensure_ascii=False)
        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderError(str(exc)[:2000], provider=self.name, code='native_request_failed') from exc


class ProviderRegistry:
    def __init__(self, base_dir, legacy_dir=None):
        base = Path(base_dir)
        legacy = Path(legacy_dir) if legacy_dir else None
        self.native_images = NativeImagesProvider(base)
        self.script_images = ScriptProvider('images-script', base / 'generate.py')
        self.providers = {
            'images': self.native_images,
            'responses': ScriptProvider('responses-script', base / 'responses_provider.py'),
            'fal': ScriptProvider('fal-script', base / 'fal_provider.py'),
            'custom': ScriptProvider('custom-script', base / 'custom_provider.py'),
        }
        self.legacy_images = ScriptProvider('images-legacy', legacy / 'generate.py') if legacy else None

    def key(self, task):
        if task.get('api_mode') == 'responses': return 'responses'
        if task.get('provider') in ('fal', 'fal.ai'): return 'fal'
        if task.get('provider') not in ('openai', 'openai-compatible', None): return 'custom'
        return 'images'

    def resolve(self, task):
        key = self.key(task)
        if key == 'images' and task.get('execution_mode') == 'script':
            return self.script_images if self.script_images.script.is_file() else self.legacy_images
        return self.providers[key]

    def run(self, context, env):
        task = context.task
        provider = self.resolve(task)
        try:
            return provider.run(context, env)
        except ProviderError as first_error:
            if self.key(task) == 'images' and task.get('execution_mode', 'auto') == 'auto':
                fallback = self.script_images if self.script_images.script.is_file() else self.legacy_images
                if fallback and fallback is not provider:
                    result = json.loads(fallback.run(context, env))
                    result['execution_mode'] = 'script'
                    result['fallback_from'] = provider.name
                    result['fallback_reason'] = first_error.code
                    return json.dumps(result, ensure_ascii=False)
            raise


def provider_environment(env, task):
    result = dict(env)
    key_env = task.get('api_key_env', 'GPT_IMAGE_API_KEY')
    if result.get(key_env) and not result.get('GPT_IMAGE_API_KEY'):
        result['GPT_IMAGE_API_KEY'] = result[key_env]
    return result
