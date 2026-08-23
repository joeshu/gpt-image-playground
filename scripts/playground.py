#!/usr/bin/env python3
"""GPT Image Playground: batch-aware orchestration over gpt-image-tool."""
import argparse
import concurrent.futures
import getpass
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

try:
    from connection import apply_environment, connection, setup_from_json, setup_status
except ImportError:
    from scripts.connection import apply_environment, connection, setup_from_json, setup_status

try:
    from image_store import index_result
except ImportError:
    from scripts.image_store import index_result
try:
    from provider_base import ProviderContext, ProviderError, ProviderRegistry, provider_environment
except ImportError:
    from scripts.provider_base import ProviderContext, ProviderError, ProviderRegistry, provider_environment

ROOT = Path('/var/minis/skills/gpt-image-playground')
FALLBACK_ROOT = Path('/var/minis/workspace/gpt-image-playground-skill')
BASE = ROOT if ROOT.exists() else FALLBACK_ROOT
PRESETS = BASE / 'presets.json'
PROFILES = BASE / 'profiles.json'
MODEL_CATALOG = BASE / 'model_catalog.json'


def model_catalog():
    if not MODEL_CATALOG.exists():
        return []
    data = read_json(MODEL_CATALOG)
    return [item.get('id') for item in data.get('models', []) if isinstance(item, dict) and item.get('id')]


def valid_model_id(value):
    return isinstance(value, str) and bool(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._:-]{0,127}', value))
OUT = Path('/var/minis/attachments/gpt-image-playground')
WORK = Path('/var/minis/workspace/gpt-image-playground')
HISTORY = WORK / 'history.jsonl'
MAX_IMAGES = 16
MAX_CONCURRENCY = 4


def read_json(path):
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.tmp')
    with open(temp, 'w', encoding='utf-8') as f:
        json.dump(value, f, ensure_ascii=False, indent=2)
    temp.replace(path)


def minis_link(path):
    text = str(Path(path))
    for root, scheme in (
        ('/var/minis/attachments/', 'minis://attachments/'),
        ('/var/minis/workspace/', 'minis://workspace/'),
    ):
        if text.startswith(root):
            return scheme + text[len(root):].replace(' ', '%20')
    return text


def task_id(prefix='gip'):
    return f'{prefix}-{time.strftime("%Y%m%d-%H%M%S")}-{uuid.uuid4().hex[:6]}'


def parse_json_output(stdout):
    try:
        value = json.loads(stdout)
        return value if isinstance(value, dict) else {'raw': value}
    except json.JSONDecodeError:
        return {'raw': stdout.strip()} if stdout.strip() else {}


def decorate_result(data, current_id):
    data = dict(data or {})
    data['task_id'] = data.get('task_id') or current_id
    for key in ('request_file', 'initial_response_file', 'response_file', 'summary_path'):
        if data.get(key):
            data[key + '_link'] = minis_link(data[key])
    for item in data.get('saved_images', []):
        if item.get('path'):
            item['minis_url'] = minis_link(item['path'])
    return data


def add_history(entry):
    WORK.mkdir(parents=True, exist_ok=True)
    with open(HISTORY, 'a', encoding='utf-8') as f:
        f.write(json.dumps(entry, ensure_ascii=False) + '\n')
    try:
        record_task(entry)
    except Exception:
        pass
    result = entry.get('result') if isinstance(entry, dict) else None
    saved = result.get('saved_images', []) if isinstance(result, dict) else []
    if not saved:
        return
    image_entry = {'task_id': entry.get('task_id'), 'saved_images': saved}
    for attempt in range(3):
        try:
            if index_result(image_entry) or attempt == 2:
                return
        except Exception:
            if attempt == 2:
                return
        time.sleep(0.1 * (attempt + 1))


def read_history():
    if not HISTORY.exists():
        return []
    entries = []
    with open(HISTORY, encoding='utf-8') as f:
        for line in f:
            try:
                item = json.loads(line)
                if isinstance(item, dict):
                    entries.append(item)
            except json.JSONDecodeError:
                continue
    return entries


def history_entry(task_id_value):
    matches = [item for item in read_history() if item.get('task_id') == task_id_value]
    return matches[-1] if matches else None


def history_list(status=None, limit=20):
    entries = read_history()
    if status:
        entries = [item for item in entries if item.get('status') == status]
    entries = list(reversed(entries[-max(1, limit):]))
    return [{
        'task_id': item.get('task_id'),
        'created_at': item.get('created_at'),
        'status': item.get('status'),
        'prompt': item.get('prompt'),
        'total': item.get('total'),
        'succeeded': item.get('succeeded'),
        'failed': item.get('failed'),
        'summary_path_link': minis_link(item['summary_path']) if item.get('summary_path') else None,
    } for item in entries]


def validate_profiles_config():
    config = read_json(PROFILES)
    if not isinstance(config, dict):
        raise ValueError('profiles.json 顶层必须是对象')
    profiles = config.get('profiles')
    if not isinstance(profiles, list) or not profiles:
        raise ValueError('profiles.json 必须包含非空 profiles 数组')
    ids = set()
    providers = {item.get('id') for item in config.get('customProviders', []) if isinstance(item, dict)}
    for profile in profiles:
        if not isinstance(profile, dict) or not profile.get('id'):
            raise ValueError('每个 Profile 必须有 id')
        if profile['id'] in ids:
            raise ValueError(f'Profile id 重复: {profile["id"]}')
        ids.add(profile['id'])
        provider = profile.get('provider', 'openai-compatible')
        if provider not in ('openai', 'openai-compatible', 'fal', 'fal.ai') and provider not in providers:
            raise ValueError(f'Profile 引用不存在的供应商: {provider}')
        if profile.get('model') is not None and not valid_model_id(profile.get('model')):
            raise ValueError(f'Profile {profile["id"]} 的 model 无效')
        models = profile.get('models', model_catalog())
        if not isinstance(models, list) or any(not valid_model_id(item) for item in models):
            raise ValueError(f'Profile {profile["id"]} 的 models 必须是模型 ID 数组')
        if profile.get('model') and models and profile['model'] not in models:
            raise ValueError(f'Profile {profile["id"]} 的默认 model 不在 models 目录中')
        if profile.get('omit_model') and profile.get('model'):
            raise ValueError(f'Profile {profile["id"]} 不能同时设置 model 和 omit_model')
    default = config.get('default_profile')
    if default and default not in ids:
        raise ValueError(f'default_profile 不存在: {default}')
    for provider in config.get('customProviders', []):
        if not isinstance(provider, dict) or not provider.get('id'):
            raise ValueError('每个 customProvider 必须有 id')
        submit = provider.get('submit')
        if not isinstance(submit, dict) or not submit.get('path'):
            raise ValueError(f'供应商 {provider.get("id")} 缺少 submit.path')
        if provider.get('poll') and not submit.get('taskIdPath'):
            raise ValueError(f'供应商 {provider.get("id")} 有 poll 但 submit 缺少 taskIdPath')
    return {'profiles': len(profiles), 'customProviders': len(config.get('customProviders', [])), 'default_profile': default}


def import_profiles(source_path, merge=False):
    incoming = read_json(source_path)
    if not isinstance(incoming, dict) or not isinstance(incoming.get('profiles'), list):
        raise ValueError('导入文件必须包含 profiles 数组')
    existing = read_json(PROFILES) if merge and PROFILES.exists() else {}
    if merge:
        current_profiles = {item.get('id'): item for item in existing.get('profiles', [])}
        current_providers = {item.get('id'): item for item in existing.get('customProviders', [])}
        for item in incoming['profiles']: current_profiles[item.get('id')] = item
        for item in incoming.get('customProviders', []): current_providers[item.get('id')] = item
        merged = dict(existing)
        merged['profiles'] = list(current_profiles.values())
        merged['customProviders'] = list(current_providers.values())
        if incoming.get('default_profile'): merged['default_profile'] = incoming['default_profile']
    else:
        merged = incoming
    old = PROFILES.with_name(PROFILES.name + '.bak')
    if PROFILES.exists(): PROFILES.replace(old)
    try:
        write_json(PROFILES, merged)
        validate_profiles_config()
        if old.exists(): old.unlink()
    except Exception:
        if PROFILES.exists(): PROFILES.unlink()
        if old.exists(): old.replace(PROFILES)
        raise
    return {'status': 'imported', 'profiles': len(merged['profiles']), 'customProviders': len(merged.get('customProviders', [])), 'merged': merge}


def export_profiles(target):
    config = read_json(PROFILES)
    validate_profiles_config()
    output = Path(target)
    write_json(output, config)
    return {'status': 'exported', 'path': str(output), 'path_link': minis_link(output), 'profiles': len(config['profiles']), 'customProviders': len(config.get('customProviders', []))}


def apply_style(prompt, style, presets):
    if not style:
        return prompt
    styles = presets.get('style_presets', {})
    if style not in styles:
        raise ValueError(f'未知 style: {style}；可选: {", ".join(styles)}')
    return f'{prompt}\n风格要求：{styles[style]}'


def select_profile(source, cli):
    profiles = read_json(PROFILES)
    profile_id = source.get('profile') or cli.profile or profiles.get('default_profile')
    profile = next((item for item in profiles.get('profiles', []) if item.get('id') == profile_id), None)
    if not profile:
        raise ValueError(f'未知 profile: {profile_id}')
    provider_id = profile.get('provider', 'openai-compatible')
    manifest = None
    if provider_id not in ('openai', 'openai-compatible', 'fal', 'fal.ai'):
        manifest = next((item for item in profiles.get('customProviders', []) if item.get('id') == provider_id), None)
        if not manifest:
            raise ValueError(f'Profile 引用的自定义供应商不存在: {provider_id}')
    return profile, manifest


def probe_profile(profile_id):
    config = read_json(PROFILES)
    profile = next((item for item in config.get('profiles', []) if item.get('id') == profile_id), None)
    if not profile: raise ValueError(f'未知 profile: {profile_id}')
    provider = profile.get('provider', 'openai-compatible')
    manifest = next((item for item in config.get('customProviders', []) if item.get('id') == provider), None)
    base = profile.get('baseUrl') or profile.get('base_url') or profile.get('endpoint') or ''
    path = (manifest or {}).get('submit', {}).get('path', '')
    if provider in ('openai', 'openai-compatible') and base.endswith('/generations'):
        url = base
    elif base:
        url = base.rstrip('/') + '/' + path.lstrip('/') if path else base
    else:
        raise ValueError('Profile 没有可探测的 endpoint/baseUrl')
    key_env = profile.get('api_key_env', 'GPT_IMAGE_API_KEY')
    key = os.environ.get(key_env) or os.environ.get('GPT_IMAGE_API_KEY')
    if not key: raise ValueError(f'缺少环境变量 {key_env}')
    request = urllib.request.Request(url, method='HEAD', headers={'Authorization': f'Bearer {key}', 'User-Agent': 'gpt-image-playground-probe/0.5'})
    started = time.time()
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return {'status': 'reachable', 'profile': profile_id, 'provider': provider, 'url': url, 'http_status': response.status, 'elapsed_ms': round((time.time()-started)*1000)}
    except urllib.error.HTTPError as exc:
        # 401/403/405 still prove the host and route responded; report auth/method separately.
        label = 'reachable_auth_required' if exc.code in (401, 403) else ('reachable_method_not_allowed' if exc.code == 405 else 'http_error')
        return {'status': label, 'profile': profile_id, 'provider': provider, 'url': url, 'http_status': exc.code, 'elapsed_ms': round((time.time()-started)*1000)}
    except (urllib.error.URLError, TimeoutError) as exc:
        return {'status': 'unreachable', 'profile': profile_id, 'provider': provider, 'url': url, 'error': str(exc), 'elapsed_ms': round((time.time()-started)*1000)}


def build_task(source, cli, presets, current_id):
    profile, manifest = select_profile(source, cli)
    prompt = source.get('prompt') or cli.prompt
    if not prompt:
        raise ValueError('缺少 prompt：使用 --prompt 或任务文件中的 prompt')
    style = source.get('style') or cli.style
    prompt = apply_style(prompt, style, presets)
    images = list(source.get('images') or source.get('image_urls') or []) + list(cli.image or [])
    mask = source.get('mask') or cli.mask
    if mask:
        if not images:
            raise ValueError('使用遮罩时必须提供主图')
        images = [images[0]] + images[1:]
    if len(images) > MAX_IMAGES:
        raise ValueError(f'参考图最多 {MAX_IMAGES} 张')
    n = int(source.get('n') if source.get('n') is not None else cli.n)
    if not 1 <= n <= 16:
        raise ValueError('n 必须在 1 到 16 之间')
    quality = source.get('quality') or cli.quality
    if quality not in ('low', 'medium', 'high', 'auto'): raise ValueError('quality 必须是 low、medium、high 或 auto')
    output_format = source.get('output_format') or cli.output_format
    if output_format not in ('png', 'webp', 'jpeg', 'jpg'): raise ValueError('output_format 必须是 png、webp 或 jpeg')
    size = source.get('size') or cli.size
    if size == 'auto': size = 'auto'
    explicit_model = source.get('model') if 'model' in source else cli.model
    explicit_omit = source.get('omit_model') if 'omit_model' in source else (True if cli.omit_model else None)
    if explicit_model is not None and not valid_model_id(explicit_model):
        raise ValueError('model 必须是 1-128 位安全模型 ID')
    if explicit_model and explicit_omit:
        raise ValueError('model 与 omit_model 不能同时指定')
    if explicit_model is not None:
        model = explicit_model
        omit_model = False
    elif explicit_omit is not None:
        omit_model = bool(explicit_omit)
        model = None if omit_model else (profile.get('model') or 'gpt-image-2')
    else:
        omit_model = bool(profile.get('omit_model'))
        model = None if omit_model else (profile.get('model') or 'gpt-image-2')
    result = {
        'prompt': prompt,
        'profile': profile.get('id'),
        'provider': profile.get('provider', 'openai-compatible'),
        'api_key_env': profile.get('api_key_env', 'GPT_IMAGE_API_KEY'),
        'size': size,
        'quality': quality,
        'output_format': 'jpeg' if output_format == 'jpg' else output_format,
        'model': model,
        'omit_model': omit_model,
        'n': n,
        'images': images,
        'api_mode': source.get('api_mode') or profile.get('api_mode') or 'images',
        'execution_mode': source.get('execution_mode') or cli.execution_mode or profile.get('execution_mode') or 'auto',
        'background': source.get('background') or source.get('transparent_background') or profile.get('background') or 'auto',
        'moderation': source.get('moderation') or cli.moderation or profile.get('moderation') or 'auto',
    }
    if source.get('background') or cli.background or profile.get('background'):
        result['background'] = source.get('background') or cli.background or profile.get('background')
    compression = source.get('output_compression') if source.get('output_compression') is not None else (cli.output_compression if cli.output_compression is not None else profile.get('output_compression'))
    if compression is not None:
        result['output_compression'] = max(0, min(100, int(compression)))
    if mask:
        result['mask'] = mask
    transparent = source.get('transparent_background') or cli.transparent_background
    if transparent != 'none':
        result['transparent_background'] = transparent
        result['background_color'] = source.get('background_color') or cli.background_color
        result['background_fuzz'] = source.get('background_fuzz') or cli.background_fuzz
    poll_timeout = source.get('poll_timeout') or cli.poll_timeout
    if poll_timeout:
        result['poll_timeout'] = int(poll_timeout)
    configured_endpoint = connection(profile).get('endpoint')
    endpoint = os.environ.get('GPT_IMAGE_ENDPOINT') or source.get('endpoint') or cli.endpoint or configured_endpoint or profile.get('endpoint')
    key_env = profile.get('api_key_env', 'GPT_IMAGE_API_KEY')
    env_value = connection(profile)
    if not os.environ.get(key_env) and not os.environ.get('GPT_IMAGE_API_KEY') and not env_value.get('key') and not cli.dry_run:
        raise ValueError(f'首次使用请先配置图片服务器地址和 API Key：--setup 或 POST /v1/setup；缺少环境变量 {key_env}')
    if endpoint:
        result['endpoint'] = endpoint
    if manifest:
        result['provider_manifest'] = manifest
        result['profile_config'] = profile
    return result


def should_retry(returncode, stderr):
    if returncode != 4:
        return False
    text = (stderr or '').lower()
    transient = ('timeout', 'timed out', 'network', 'connection', '429', '500', '502', '503', '504', 'temporarily')
    return not text or any(token in text for token in transient)


def preprocess_mask_task(run_task, current_id):
    mask = run_task.get('mask')
    if not mask:
        return run_task, None
    try:
        from image_ops import prepare_mask_target
    except ImportError:
        from pathlib import Path as _Path
        sys.path.insert(0, str(_Path(__file__).parent))
        from image_ops import prepare_mask_target
    work_dir = WORK / f'{current_id}-mask'
    target, mask_path, meta = prepare_mask_target(run_task['images'][0], mask, work_dir)
    next_task = dict(run_task)
    next_task['images'] = [target] + run_task['images'][1:]
    next_task['mask'] = mask_path
    next_task['mask_metadata'] = meta
    return next_task, meta


def export_images_zip(result, target):
    import zipfile
    paths = []
    def collect(value):
        if isinstance(value, dict):
            item_path = value.get('path')
            if item_path and Path(item_path).is_file(): paths.append(Path(item_path))
            for child in value.values(): collect(child)
        elif isinstance(value, list):
            for child in value: collect(child)
    collect(result)
    if not paths:
        raise ValueError('没有可导出的生成图片')
    output = Path(target)
    if output.suffix.lower() != '.zip': output = output.with_suffix('.zip')
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        used = set()
        for path in paths:
            name = path.name
            if name in used:
                name = f'{len(used)+1}-{name}'
            used.add(name)
            archive.write(path, arcname=name)
    return str(output)


def postprocess_result(result, run_task):
    if run_task.get('transparent_background') != 'local' or result.get('status') == 'dry_run':
        return result
    try:
        from image_ops import remove_background
    except ImportError:
        sys.path.insert(0, str(Path(__file__).parent))
        from image_ops import remove_background
    color = run_task.get('background_color', '#00ff00')
    fuzz = run_task.get('background_fuzz', '12%')
    for item in result.get('saved_images', []):
        source = item.get('path')
        if not source or not Path(source).is_file(): continue
        target = str(Path(source).with_name(Path(source).stem + '-transparent.png'))
        remove_background(source, target, color, fuzz)
        item['path'] = target
        item['minis_url'] = minis_link(target)
        item['background_removed'] = True
    result['transparent_background'] = 'local'
    return result


def execute_one(run_task, current_id, dry_run, retries):
    try:
        effective_task, mask_meta = preprocess_mask_task(run_task, current_id)
    except (OSError, ValueError) as exc:
        return {'task_id': current_id, 'status': 'failed', 'attempts': 0,
                'error': str(exc)}
    run_task = effective_task
    OUT.mkdir(parents=True, exist_ok=True)
    WORK.mkdir(parents=True, exist_ok=True)
    task_path = WORK / f'{current_id}-orchestrator-task.json'
    write_json(task_path, run_task)
    registry = ProviderRegistry(BASE / 'scripts', Path('/var/minis/skills/gpt-image-tool/scripts'))
    process_env = provider_environment(apply_environment(os.environ.copy(), run_task), run_task)
    context = ProviderContext(task=run_task, task_path=task_path, output_dir=OUT,
                              workspace_dir=WORK, dry_run=dry_run, task_id=current_id, retries=retries)
    attempts = 0
    last_error = None
    while attempts <= retries:
        attempts += 1
        try:
            stdout = registry.run(context, process_env)
            result = decorate_result(parse_json_output(stdout), current_id)
            result = postprocess_result(result, run_task)
            result['attempts'] = attempts
            result['actual_params'] = {key: run_task.get(key) for key in ('model', 'omit_model', 'size', 'quality', 'output_format', 'n', 'background', 'moderation', 'output_compression', 'api_mode') if run_task.get(key) is not None}
            result['revised_prompts'] = [item.get('revised_prompt') for item in result.get('saved_images', []) if item.get('revised_prompt')]
            result['status'] = 'dry_run' if dry_run else 'completed'
            return result
        except ProviderError as exc:
            last_error = exc
            if attempts > retries or not should_retry(exc.returncode or 1, str(exc)):
                break
            time.sleep(min(2 ** (attempts - 1), 8))
        except (OSError, ValueError) as exc:
            last_error = ProviderError(str(exc), code='provider_setup_error')
            break
    error = {
        'task_id': current_id, 'status': 'failed', 'attempts': attempts,
        'returncode': last_error.returncode if last_error and last_error.returncode else 1,
        'error': str(last_error or '底层 Provider 执行失败')[:2000],
        'provider': last_error.provider if last_error else None,
        'error_code': last_error.code if last_error else 'provider_error',
        'task_file': str(task_path), 'task_file_link': minis_link(task_path),
    }
    return error


def retry_task(task_id_value, cli, presets):
    entry = history_entry(task_id_value)
    if not entry:
        raise ValueError(f'找不到任务: {task_id_value}')
    if entry.get('status') not in ('failed', 'partial_failed'):
        raise ValueError('只允许重试 failed 或 partial_failed 任务')
    result = entry.get('result')
    if isinstance(result, dict) and result.get('task_file'):
        source = read_json(result['task_file'])
    else:
        raise ValueError('历史记录缺少可重试的任务文件')
    return run_single(source, cli, presets, cli.dry_run)


def run_single(source, cli, presets, dry_run):
    current_id = task_id()
    run_task = build_task(source, cli, presets, current_id)
    result = execute_one(run_task, current_id, dry_run, cli.retry)
    add_history({'task_id': current_id, 'created_at': time.strftime('%Y-%m-%dT%H:%M:%S%z'),
                 'status': result.get('status'), 'prompt': run_task['prompt'],
                 'model': run_task['model'], 'size': run_task['size'],
                 'n': run_task['n'], 'images': run_task['images'],
                 'result': result})
    return result


def run_batch(source, cli, presets, dry_run):
    items = source.get('tasks') if isinstance(source, dict) else source
    if not isinstance(items, list) or not items:
        raise ValueError('批量任务必须是非空 tasks 数组')
    if len(items) > 100:
        raise ValueError('单次批量任务最多 100 个子任务')
    effective_dry_run = bool(dry_run or (isinstance(source, dict) and source.get('dry_run')) or any(isinstance(item, dict) and item.get('dry_run') for item in items))
    parent_id = task_id('gip-batch')
    defaults = {k: v for k, v in source.items() if k != 'tasks'} if isinstance(source, dict) else {}
    jobs = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError('tasks 中每项必须是 JSON 对象')
        merged = dict(defaults); merged.update(item)
        child_id = task_id('gip')
        jobs.append((child_id, build_task(merged, cli, presets, child_id)))
    workers = min(max(1, cli.concurrency), MAX_CONCURRENCY, len(jobs))
    results = [None] * len(jobs)
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        pending = {pool.submit(execute_one, run_task, child_id, effective_dry_run, cli.retry): index
                   for index, (child_id, run_task) in enumerate(jobs)}
        for future in concurrent.futures.as_completed(pending):
            results[pending[future]] = future.result()
    summary = {'task_id': parent_id, 'status': 'completed' if all(r.get('status') != 'failed' for r in results) else 'partial_failed',
               'total': len(results), 'succeeded': sum(r.get('status') in ('completed', 'dry_run') for r in results),
               'failed': sum(r.get('status') == 'failed' for r in results), 'concurrency': workers, 'results': results}
    for (child_id, run_task), result in zip(jobs, results):
        add_history({'task_id': child_id, 'parent_task_id': parent_id,
                     'created_at': time.strftime('%Y-%m-%dT%H:%M:%S%z'),
                     'status': result.get('status'), 'prompt': run_task['prompt'],
                     'model': run_task['model'], 'size': run_task['size'],
                     'n': run_task['n'], 'images': run_task['images'], 'result': result})
    summary_path = WORK / f'{parent_id}-summary.json'
    write_json(summary_path, summary)
    summary['summary_path'] = str(summary_path); summary['summary_path_link'] = minis_link(summary_path)
    add_history({'task_id': parent_id, 'created_at': time.strftime('%Y-%m-%dT%H:%M:%S%z'),
                 'status': summary['status'], 'total': summary['total'], 'succeeded': summary['succeeded'],
                 'failed': summary['failed'], 'summary_path': str(summary_path)})
    return summary


def main():
    parser = argparse.ArgumentParser(description='GPT Image Playground orchestrator')
    parser.add_argument('--prompt'); parser.add_argument('--task'); parser.add_argument('--batch')
    parser.add_argument('--image', action='append', default=[]); parser.add_argument('--mask')
    parser.add_argument('--transparent-background', choices=['none', 'local'], default='none')
    parser.add_argument('--background-color', default='#00ff00'); parser.add_argument('--background-fuzz', default='12%')
    parser.add_argument('--export-zip')
    parser.add_argument('--size', default='1:1')
    parser.add_argument('--quality', default='low'); parser.add_argument('--output-format', default='png')
    parser.add_argument('--background', choices=['auto', 'transparent', 'opaque'])
    parser.add_argument('--moderation', choices=['auto', 'low', 'medium', 'high'])
    parser.add_argument('--output-compression', type=int)
    parser.add_argument('--model'); parser.add_argument('--omit-model', action='store_true'); parser.add_argument('--execution-mode', choices=['auto', 'native', 'script'], default='auto'); parser.add_argument('--profile'); parser.add_argument('--n', type=int, default=1)
    parser.add_argument('--poll-timeout', type=int, default=300)
    parser.add_argument('--style'); parser.add_argument('--endpoint'); parser.add_argument('--retry', type=int, default=0)
    parser.add_argument('--validate-profiles', action='store_true')
    parser.add_argument('--import-profiles'); parser.add_argument('--merge-profiles', action='store_true')
    parser.add_argument('--export-profiles'); parser.add_argument('--test-profile')
    parser.add_argument('--retry-task'); parser.add_argument('--history-list', action='store_true')
    parser.add_argument('--history-get'); parser.add_argument('--history-status'); parser.add_argument('--history-limit', type=int, default=20)
    parser.add_argument('--concurrency', type=int, default=2); parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--setup', action='store_true')
    parser.add_argument('--setup-json')
    parser.add_argument('--connection-status', action='store_true')
    cli = parser.parse_args()
    if cli.retry < 0 or cli.retry > 3: parser.error('--retry 必须在 0 到 3 之间')
    if cli.concurrency < 1: parser.error('--concurrency 必须大于 0')
    if cli.history_limit < 1 or cli.history_limit > 200: parser.error('--history-limit 必须在 1 到 200 之间')
    try:
        if cli.setup_json:
            value = read_json(cli.setup_json)
            print(json.dumps(setup_from_json(value), ensure_ascii=False, indent=2)); return
        if cli.connection_status:
            print(json.dumps(setup_status(), ensure_ascii=False, indent=2)); return
        if cli.setup:
            endpoint = input('图片服务器地址（例如 https://api.example.com/v1/images/generations）: ').strip()
            key = getpass.getpass('API Key（输入不会回显）：')
            print(json.dumps(setup_from_json({'endpoint': endpoint, 'api_key': key, 'model': cli.model or 'gpt-image-2'}), ensure_ascii=False, indent=2)); return
        if cli.validate_profiles:
            print(json.dumps({'status': 'valid', **validate_profiles_config()}, ensure_ascii=False, indent=2))
            return
        if cli.import_profiles:
            print(json.dumps(import_profiles(cli.import_profiles, cli.merge_profiles), ensure_ascii=False, indent=2))
            return
        if cli.export_profiles:
            print(json.dumps(export_profiles(cli.export_profiles), ensure_ascii=False, indent=2))
            return
        if cli.test_profile:
            print(json.dumps(probe_profile(cli.test_profile), ensure_ascii=False, indent=2))
            return
        if cli.history_list:
            print(json.dumps(history_list(cli.history_status, cli.history_limit), ensure_ascii=False, indent=2))
            return
        if cli.history_get:
            item = history_entry(cli.history_get)
            if not item: parser.error(f'找不到任务: {cli.history_get}')
            print(json.dumps(item, ensure_ascii=False, indent=2))
            return
        presets = read_json(PRESETS)
        if cli.retry_task:
            result = retry_task(cli.retry_task, cli, presets)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return
        source = read_json(cli.batch or cli.task) if (cli.batch or cli.task) else {}
        if isinstance(source, dict) and 'tasks' in source:
            result = run_batch(source, cli, presets, cli.dry_run)
        else:
            result = run_single(source, cli, presets, cli.dry_run)
        if cli.export_zip:
            zip_path = export_images_zip(result, cli.export_zip)
            result['zip_path'] = zip_path
            result['zip_path_link'] = minis_link(zip_path)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))


if __name__ == '__main__':
    main()
