#!/usr/bin/env python3
"""First-use connection setup shared by CLI, Agent and REST API."""
import json
import os
import re
import stat
import tempfile
from pathlib import Path
from urllib.parse import urlparse

WORK = Path('/var/minis/workspace/gpt-image-playground')
CONFIG = WORK / 'connection.json'
DEFAULT_MODEL = 'gpt-image-2'


def valid_endpoint(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError('图片服务器地址不能为空')
    value = value.strip().rstrip('/')
    parsed = urlparse(value)
    if parsed.scheme not in ('http', 'https') or not parsed.netloc:
        raise ValueError('图片服务器地址必须是 http(s) URL')
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError('图片服务器地址不能包含用户信息、查询参数或片段')
    if any(char in value for char in ('\n', '\r', '\x00')):
        raise ValueError('图片服务器地址包含非法字符')
    return value


def valid_key(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError('API Key 不能为空')
    if any(char in value for char in ('\n', '\r', '\x00')):
        raise ValueError('API Key 包含非法换行或空字符')
    return value.strip()


def read_config():
    if not CONFIG.is_file():
        return None
    try:
        value = json.loads(CONFIG.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f'连接配置无法读取: {exc}') from exc
    if not isinstance(value, dict):
        raise ValueError('连接配置必须是 JSON 对象')
    return value


def configured_from_environment(profile=None):
    profile = profile or {}
    key_env = profile.get('api_key_env', 'GPT_IMAGE_API_KEY')
    key = os.environ.get(key_env) or os.environ.get('GPT_IMAGE_API_KEY')
    endpoint = os.environ.get('GPT_IMAGE_ENDPOINT') or profile.get('endpoint') or profile.get('baseUrl') or profile.get('base_url')
    return bool(endpoint and key)


def setup_status(profile=None):
    value = read_config()
    configured = bool(value and value.get('endpoint') and value.get('api_key'))
    if not configured and configured_from_environment(profile):
        configured = True
    endpoint = os.environ.get('GPT_IMAGE_ENDPOINT') or (value or {}).get('endpoint') or (profile or {}).get('endpoint') or (profile or {}).get('baseUrl') or (profile or {}).get('base_url')
    parsed = urlparse(endpoint) if endpoint else None
    return {
        'configured': configured,
        'source': 'file' if value and value.get('endpoint') and value.get('api_key') else ('environment' if configured else 'none'),
        'endpoint': endpoint,
        'host': parsed.netloc if parsed else '',
        'model': (value or {}).get('model') or (profile or {}).get('model') or DEFAULT_MODEL,
        'config_path': str(CONFIG),
    }


def save_config(endpoint, api_key, model=DEFAULT_MODEL):
    endpoint = valid_endpoint(endpoint)
    api_key = valid_key(api_key)
    if not isinstance(model, str) or not model.strip():
        model = DEFAULT_MODEL
    WORK.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(WORK, stat.S_IRWXU)
    except OSError:
        pass
    fd, name = tempfile.mkstemp(prefix='connection-', suffix='.json', dir=str(WORK))
    path = Path(name)
    try:
        os.fchmod(fd, stat.S_IRUSR | stat.S_IWUSR)
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump({'version': 1, 'endpoint': endpoint, 'api_key': api_key, 'model': model.strip()}, stream, ensure_ascii=False, indent=2)
        os.replace(path, CONFIG)
        try: os.chmod(CONFIG, stat.S_IRUSR | stat.S_IWUSR)
        except OSError: pass
    finally:
        path.unlink(missing_ok=True)
    return {'configured': True, 'source': 'file', 'endpoint': endpoint, 'model': model.strip(), 'config_path': str(CONFIG)}


def connection(profile=None):
    profile = profile or {}
    value = read_config() or {}
    endpoint = os.environ.get('GPT_IMAGE_ENDPOINT') or value.get('endpoint') or profile.get('endpoint') or profile.get('baseUrl') or profile.get('base_url')
    key_env = profile.get('api_key_env', 'GPT_IMAGE_API_KEY')
    key = os.environ.get(key_env) or os.environ.get('GPT_IMAGE_API_KEY') or value.get('api_key')
    model = profile.get('model') or value.get('model') or DEFAULT_MODEL
    return {'endpoint': endpoint, 'key': key, 'model': model, 'configured': bool(endpoint and key)}


def apply_environment(env, profile=None):
    value = connection(profile)
    if value['key'] and not env.get('GPT_IMAGE_API_KEY'):
        env['GPT_IMAGE_API_KEY'] = value['key']
    if value['endpoint'] and not env.get('GPT_IMAGE_ENDPOINT'):
        env['GPT_IMAGE_ENDPOINT'] = value['endpoint']
    return env


def setup_from_json(value):
    if not isinstance(value, dict): raise ValueError('配置请求必须是 JSON 对象')
    return save_config(value.get('endpoint'), value.get('api_key'), value.get('model', DEFAULT_MODEL))
