#!/usr/bin/env python3
"""Declarative synchronous/asynchronous image provider runner.

The manifest is intentionally data-driven and contains no credentials. Secrets
are read only from the profile's api_key_env variable.
"""
import argparse
import base64
import json
import mimetypes
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

try:
    import requests
except Exception:
    print('requests is required. Install with: apk add py3-requests', file=sys.stderr)
    raise SystemExit(2)

OMIT = object()


def read_json(path):
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def write_json(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(value, f, ensure_ascii=False, indent=2)


def path_get(source, path):
    current = source
    for part in str(path or '').split('.'):
        if not part: continue
        if part == '*':
            return current
        if isinstance(current, list) and part.isdigit():
            index = int(part)
            if index >= len(current): return None
            current = current[index]
        elif isinstance(current, dict):
            if part not in current: return None
            current = current[part]
        else:
            return None
    return current


def path_values(source, path):
    parts = [p for p in str(path or '').split('.') if p]
    values = [source]
    for part in parts:
        next_values = []
        for value in values:
            if part == '*':
                if isinstance(value, list): next_values.extend(value)
                elif isinstance(value, dict): next_values.extend(value.values())
            elif isinstance(value, list) and part.isdigit():
                index = int(part)
                if index < len(value): next_values.append(value[index])
            elif isinstance(value, dict) and part in value:
                next_values.append(value[part])
        values = next_values
    return [v for v in values if v is not None]


def to_data_url(value):
    if not isinstance(value, str):
        raise ValueError('图片输入必须是路径、URL 或 data URL')
    if value.startswith(('data:', 'http://', 'https://')):
        return value
    path = Path(value)
    if not path.is_file(): raise ValueError(f'图片不存在: {value}')
    mime = mimetypes.guess_type(str(path))[0] or 'application/octet-stream'
    return f'data:{mime};base64,{base64.b64encode(path.read_bytes()).decode("ascii")}'


def data_bytes(value):
    if value.startswith('data:'):
        match = re.match(r'^data:([^;,]+)?(;base64)?,(.*)$', value, re.S)
        if not match: raise ValueError('无效 data URL')
        mime = match.group(1) or 'application/octet-stream'
        body = match.group(3)
        raw = base64.b64decode(body) if match.group(2) else urllib.parse.unquote_to_bytes(body)
        return raw, mime
    response = requests.get(value, timeout=120)
    response.raise_for_status()
    return response.content, response.headers.get('content-type', 'application/octet-stream').split(';')[0]


def render(value, context):
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            rendered = render(item, context)
            if rendered is not OMIT: result[key] = rendered
        return result
    if isinstance(value, list):
        rendered_items = []
        for item in value:
            rendered = render(item, context)
            if rendered is not OMIT:
                rendered_items.append(rendered)
        return rendered_items
    if not isinstance(value, str): return value
    if value.startswith('$') and re.fullmatch(r'\$[A-Za-z][A-Za-z0-9_.]*', value):
        found = path_get(context, value[1:])
        return OMIT if found is None else found
    pattern = re.compile(r'\$[A-Za-z][A-Za-z0-9_.]*')
    def replace(match):
        found = path_get(context, match.group(0)[1:])
        return '' if found is None else str(found)
    return pattern.sub(replace, value)


def join_url(base, path):
    base = str(base or '')
    if not base: return path
    if path.startswith(('http://', 'https://')): return path
    if base.endswith('/'): return base + path.lstrip('/')
    return base.rstrip('/') + '/' + path.lstrip('/')


def safe_summary(value):
    if isinstance(value, dict): return {k: safe_summary(v) for k, v in value.items()}
    if isinstance(value, list): return [safe_summary(v) for v in value]
    if isinstance(value, str) and value.startswith('data:'):
        return f'[data URL omitted: {len(value)} chars]'
    return value


def endpoint_and_headers(task):
    profile = task.get('profile_config') or {}
    base = profile.get('baseUrl') or profile.get('base_url') or profile.get('endpoint') or ''
    key_env = task.get('api_key_env') or profile.get('api_key_env') or 'GPT_IMAGE_API_KEY'
    key = os.environ.get(key_env) or os.environ.get('GPT_IMAGE_API_KEY')
    if not key: raise ValueError(f'缺少环境变量 {key_env}')
    return base, {'Authorization': f'Bearer {key}'}


def request(method, url, headers, query=None, body=None, files=None, timeout=900):
    if query:
        url += ('&' if '?' in url else '?') + urllib.parse.urlencode(query, doseq=True)
    method = str(method or 'POST').upper()
    if files is not None:
        response = requests.request(method, url, headers=headers, params=None, data=body or {}, files=files, timeout=timeout)
    elif method == 'GET':
        response = requests.get(url, headers=headers, params=body or {}, timeout=timeout)
    else:
        response = requests.request(method, url, headers={**headers, 'Content-Type': 'application/json'}, json=body or {}, timeout=timeout)
    content_type = response.headers.get('content-type', '')
    raw_text = response.text
    try: payload = response.json()
    except ValueError: payload = {'_raw_text': raw_text[:4000]}
    meta = {'status_code': response.status_code, 'content_type': content_type,
            'content_length': response.headers.get('content-length', ''), 'url': url}
    if not response.ok:
        raise RuntimeError(f'HTTP {response.status_code}: {json.dumps(payload, ensure_ascii=False)[:1500]}')
    return payload, meta, raw_text


def extract_images(payload, mapping, output_dir, prefix, headers):
    mapping = mapping or {}
    outputs = []
    for path in mapping.get('b64JsonPaths', []):
        for index, value in enumerate(path_values(payload, path), 1):
            if not isinstance(value, str): continue
            raw = base64.b64decode(value)
            target = Path(output_dir) / f'{prefix}-{len(outputs)+1}.png'
            target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(raw)
            outputs.append({'index': len(outputs)+1, 'path': str(target), 'source': 'b64_json'})
    for path in mapping.get('imageUrlPaths', []):
        for value in path_values(payload, path):
            if not isinstance(value, str): continue
            if value.startswith('data:'):
                raw, mime = data_bytes(value)
            else:
                response = requests.get(value, headers=headers, timeout=120); response.raise_for_status()
                raw, mime = response.content, response.headers.get('content-type', 'image/png').split(';')[0]
            ext = 'jpg' if mime in ('image/jpeg', 'image/jpg') else (mime.split('/')[-1] if '/' in mime else 'png')
            target = Path(output_dir) / f'{prefix}-{len(outputs)+1}.{ext}'
            target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(raw)
            outputs.append({'index': len(outputs)+1, 'path': str(target), 'source': 'url', 'url': value})
    return outputs


def build_files(files_spec, context):
    files = []
    for spec in files_spec or []:
        source = spec.get('source'); field = spec.get('field', 'file')
        if source == 'inputImages':
            values = context.get('inputImages', {}).get('dataUrls')
        elif source == 'mask':
            values = context.get('mask', {}).get('dataUrl')
        else:
            values = path_get(context, source) if source else None
        if values is None: continue
        if not isinstance(values, list): values = [values]
        for index, value in enumerate(values, 1):
            data_url = to_data_url(value)
            raw, mime = data_bytes(data_url)
            ext = mime.split('/')[-1] or 'bin'
            name = f'{source}-{index}.{ext}'
            files.append((field, (name, raw, mime)))
            if not spec.get('array'): break
    return files


def main():
    parser = argparse.ArgumentParser(description='Run a declarative custom image provider')
    parser.add_argument('--task', required=True); parser.add_argument('--out-prefix', required=True)
    parser.add_argument('--attachments-dir', required=True); parser.add_argument('--workspace-dir', required=True)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    task = read_json(args.task); manifest = task.get('provider_manifest') or {}
    profile = task.get('profile_config') or {}
    submit = manifest.get('editSubmit') if (task.get('images') and manifest.get('editSubmit')) else manifest.get('submit')
    if not submit: raise SystemExit('自定义供应商缺少 submit/editSubmit 映射')
    profile_base = profile.get('baseUrl') or profile.get('base_url') or profile.get('endpoint') or ''
    if args.dry_run:
        base, headers = profile_base, {}
    else:
        base, headers = endpoint_and_headers(task)
    context = {'profile': {'model': task.get('model')}, 'prompt': task.get('prompt'),
               'params': {'size': task.get('size'), 'quality': task.get('quality'), 'output_format': task.get('output_format'), 'n': task.get('n'),
                          'background': 'transparent' if task.get('transparent_background') == 'api' else None},
               'inputImages': {'dataUrls': [to_data_url(v) for v in task.get('images', [])]},
               'mask': {'dataUrl': to_data_url(task['mask'])} if task.get('mask') else {}}
    body = render(submit.get('body', {}), context)
    query = render(submit.get('query', {}), context)
    url = join_url(base, submit.get('path', ''))
    work = Path(args.workspace_dir); out = Path(args.attachments_dir); work.mkdir(parents=True, exist_ok=True); out.mkdir(parents=True, exist_ok=True)
    prefix = args.out_prefix
    request_path = work / f'{prefix}-request.json'; initial_path = work / f'{prefix}-initial-response.json'; response_path = work / f'{prefix}-response.json'; summary_path = work / f'{prefix}-summary.json'
    write_json(request_path, {'endpoint': url, 'method': submit.get('method', 'POST'), 'query': safe_summary(query), 'body': safe_summary(body), 'content_type': submit.get('contentType', 'json')})
    if args.dry_run:
        print(json.dumps({'request_file': str(request_path), 'endpoint': url, 'model': task.get('model'), 'size': task.get('size')}, ensure_ascii=False, indent=2)); return
    files = build_files(submit.get('files'), context) if submit.get('contentType') == 'multipart' else None
    payload, meta, raw_text = request(submit.get('method', 'POST'), url, headers, query, body, files)
    write_json(initial_path, payload)
    write_json(work / f'{prefix}-post-meta.json', meta)
    (work / f'{prefix}-post-raw.txt').write_text(raw_text, encoding='utf-8')
    final = payload; async_note = None
    task_id_value = path_get(payload, submit.get('taskIdPath')) if submit.get('taskIdPath') else None
    poll = manifest.get('poll')
    if task_id_value is not None and poll:
        deadline = time.time() + int(task.get('poll_timeout', 300)); last = payload
        while time.time() < deadline:
            time.sleep(max(0, int(poll.get('intervalSeconds', 5))))
            poll_context = dict(context); poll_context['task_id'] = task_id_value
            poll_url = join_url(base, str(poll.get('path', '')).replace('{task_id}', urllib.parse.quote(str(task_id_value), safe='')))
            poll_body = render(poll.get('body', {}), poll_context); poll_query = render(poll.get('query', {}), poll_context)
            last, poll_meta, poll_raw = request(poll.get('method', 'GET'), poll_url, headers, poll_query, poll_body)
            status = str(path_get(last, poll.get('statusPath', ''))).lower()
            if status in {str(v).lower() for v in poll.get('successValues', [])}:
                final = last; break
            if status in {str(v).lower() for v in poll.get('failureValues', [])}:
                reason = path_get(last, poll.get('errorPath', '')) if poll.get('errorPath') else status
                raise RuntimeError(f'异步任务失败: {reason}')
        else:
            raise RuntimeError(f'异步任务轮询超时: {task_id_value}')
    write_json(response_path, final)
    result_mapping = poll.get('result') if (poll and task_id_value is not None) else submit.get('result')
    saved = extract_images(final, result_mapping, out, prefix, headers)
    if not saved and not async_note:
        raise RuntimeError('自定义供应商响应未提取到图片，请检查 result.imageUrlPaths/b64JsonPaths')
    summary = {'endpoint': url, 'model': task.get('model'), 'size': task.get('size'), 'n': task.get('n'), 'has_input_images': bool(task.get('images')), 'request_file': str(request_path), 'initial_response_file': str(initial_path), 'response_file': str(response_path), 'saved_images': saved, 'async_note': async_note}
    write_json(summary_path, summary); print(json.dumps({**summary, 'summary_path': str(summary_path)}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    try: main()
    except Exception as exc:
        print(json.dumps({'error': str(exc)}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(4)
