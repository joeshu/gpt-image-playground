#!/usr/bin/env python3
"""Hybrid Responses Agent for GPT Image Playground.

The model plans with function tools; local image generation is delegated back
through playground.py, preserving provider profiles, history, and diagnostics.
"""
import argparse
import concurrent.futures
import base64
import json
import mimetypes
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

try:
    from connection import connection, setup_from_json, setup_status
except ImportError:
    from scripts.connection import connection, setup_from_json, setup_status

ROOT = Path('/var/minis/skills/gpt-image-playground')
PLAYGROUND = ROOT / 'scripts' / 'playground.py'
PROFILES = ROOT / 'profiles.json'
WORK = Path('/var/minis/workspace/gpt-image-playground')
AGENT_HISTORY = WORK / 'agent-history.jsonl'
MAX_ROUNDS = 8
MAX_IMAGES_PER_CALL = 16


def read_json(path):
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def write_json(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.tmp')
    with open(temp, 'w', encoding='utf-8') as f:
        json.dump(value, f, ensure_ascii=False, indent=2)
    temp.replace(path)


def minis_link(path):
    text = str(Path(path))
    for root, scheme in (('/var/minis/attachments/', 'minis://attachments/'), ('/var/minis/workspace/', 'minis://workspace/')):
        if text.startswith(root): return scheme + text[len(root):].replace(' ', '%20')
    return text


def data_url(value):
    if str(value).startswith(('data:', 'http://', 'https://')): return value
    path = Path(value)
    if not path.is_file(): raise ValueError(f'图片不存在: {value}')
    mime = mimetypes.guess_type(str(path))[0] or 'application/octet-stream'
    return f'data:{mime};base64,{base64.b64encode(path.read_bytes()).decode("ascii")}'


def safe(value):
    if isinstance(value, dict): return {k: safe(v) for k, v in value.items()}
    if isinstance(value, list): return [safe(v) for v in value]
    if isinstance(value, str) and value.startswith('data:'):
        return f'[data URL omitted: {len(value)} chars]'
    return value


def output_text(output):
    parts = []
    for item in output or []:
        if item.get('type') != 'message': continue
        for content in item.get('content') or []:
            if content.get('type') in ('output_text', 'text') and content.get('text'):
                parts.append(content['text'])
    return '\n'.join(parts).strip()


def function_calls(output):
    return [item for item in output or [] if item.get('type') == 'function_call' and item.get('name')]


def image_tools():
    image_schema = {
        'type': 'object',
        'properties': {
            'id': {'type': 'string'},
            'prompt': {'type': 'string'},
            'images': {'type': 'array', 'items': {'type': 'string'}},
            'size': {'type': 'string'},
            'style': {'type': 'string'},
        },
        'required': ['id', 'prompt'], 'additionalProperties': False,
    }
    return [
        {'type': 'function', 'name': 'generate_image',
         'description': 'Generate one image. Use this for a single image or a prerequisite/base image.',
         'parameters': image_schema, 'strict': True},
        {'type': 'function', 'name': 'generate_image_batch',
         'description': 'Generate independent images concurrently. Use only when all requested images are independent.',
         'parameters': {'type': 'object', 'properties': {'images': {'type': 'array', 'items': image_schema}}, 'required': ['images'], 'additionalProperties': False}, 'strict': True},
        {'type': 'function', 'name': 'continue_generation',
         'description': 'Continue after a prerequisite image when dependent images still need generation.',
         'parameters': {'type': 'object', 'properties': {'reason': {'type': 'string'}}, 'required': ['reason'], 'additionalProperties': False}, 'strict': True},
    ]


def endpoint_for(profile, cli_endpoint):
    endpoint = cli_endpoint or os.environ.get('GPT_AGENT_ENDPOINT') or profile.get('agent_endpoint')
    if endpoint: return endpoint
    configured = connection(profile).get('endpoint')
    if configured and configured.endswith('/images/generations'):
        return configured[:-len('/images/generations')] + '/responses'
    if configured: return configured.rstrip('/') + '/responses'
    base = profile.get('baseUrl') or profile.get('base_url')
    if base: return base.rstrip('/') + '/responses'
    endpoint = profile.get('endpoint', '')
    if endpoint.endswith('/images/generations'):
        return endpoint[:-len('/images/generations')] + '/responses'
    raise ValueError('缺少 Agent Responses endpoint；请设置 GPT_AGENT_ENDPOINT 或 Profile 的 agent_endpoint')


def call_api(endpoint, key, body, timeout):
    request = urllib.request.Request(endpoint, method='POST', headers={
        'Authorization': f'Bearer {key}', 'Content-Type': 'application/json',
        'User-Agent': 'gpt-image-playground-agent/0.7',
    }, data=json.dumps(body, ensure_ascii=False).encode())
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode('utf-8', errors='replace')
            payload = json.loads(raw)
            return payload, response.status, raw
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode('utf-8', errors='replace')
        raise RuntimeError(f'Agent HTTP {exc.code}: {raw[:1500]}')
    except (urllib.error.URLError, TimeoutError) as exc:
        raise RuntimeError(f'Agent 网络请求失败: {exc}')


def should_retry_agent_error(error):
    text = str(error).lower()
    return any(token in text for token in ('timeout', 'timed out', 'network', 'connection', '429', '500', '502', '503', '504', 'temporarily'))


def call_api_with_retry(endpoint, key, body, timeout, retries):
    attempts = 0
    while True:
        attempts += 1
        try:
            payload, status, raw = call_api(endpoint, key, body, timeout)
            return payload, status, raw, attempts
        except RuntimeError as exc:
            if attempts > retries or not should_retry_agent_error(exc):
                raise
            time.sleep(min(2 ** (attempts - 1), 8))


def resolve_image(value, references):
    if not isinstance(value, str):
        raise ValueError('图片引用必须是字符串')
    text = value.strip()
    if text in references:
        return references[text]
    if text.startswith('<ref ') and 'id=' in text:
        marker = text.split('id=', 1)[1].lstrip('"\'').split('"', 1)[0].split("'", 1)[0]
        if marker in references: return references[marker]
    if text.startswith('ref:') and text[4:] in references:
        return references[text[4:]]
    return text


def run_playground(args, call, index=0, references=None):
    references = references or {}
    prompt = call.get('prompt')
    if not isinstance(prompt, str) or not prompt.strip(): raise ValueError('generate_image 缺少 prompt')
    images = call.get('images') or []
    if not isinstance(images, list) or len(images) > MAX_IMAGES_PER_CALL: raise ValueError('Agent 参考图数量无效')
    images = [resolve_image(item, references) for item in images]
    command = [sys.executable, str(PLAYGROUND), '--prompt', prompt, '--profile', args.profile,
               '--n', '1', '--retry', str(args.image_retry)]
    image_endpoint = args.image_endpoint
    if image_endpoint:
        command += ['--endpoint', image_endpoint]
    if call.get('size'): command += ['--size', str(call['size'])]
    if call.get('style'): command += ['--style', str(call['style'])]
    for image in images: command += ['--image', image]
    completed = subprocess.run(command, text=True, capture_output=True, env=os.environ.copy())
    if completed.returncode:
        raise RuntimeError((completed.stderr or completed.stdout or '图片生成失败')[-2000:])
    try: result = json.loads(completed.stdout)
    except json.JSONDecodeError as exc: raise RuntimeError('图片生成器返回非 JSON') from exc
    outputs = []
    for item in result.get('saved_images', []):
        if item.get('path'):
            outputs.append({'id': call.get('id') or f'image-{index+1}', 'path': item['path'], 'minis_url': minis_link(item['path'])})
    return outputs, result


def execute_call(args, call, references=None):
    name = call.get('name')
    try: arguments = json.loads(call.get('arguments') or '{}')
    except json.JSONDecodeError as exc: raise ValueError(f'{name} 参数不是有效 JSON') from exc
    if name == 'continue_generation':
        return {'status': 'continue', 'reason': arguments.get('reason', '')}, []
    if name == 'generate_image':
        images, result = run_playground(args, arguments, references=references)
        return {'status': 'completed', 'images': images, 'result': safe(result)}, images
    if name == 'generate_image_batch':
        requested = arguments.get('images') or []
        if not requested or len(requested) > 16: raise ValueError('批量图片数量必须为 1-16')
        all_images = []; details = [None] * len(requested)
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(4, len(requested))) as pool:
            pending = {pool.submit(run_playground, args, item, index, references): index for index, item in enumerate(requested)}
            for future in concurrent.futures.as_completed(pending):
                index = pending[future]
                try:
                    images, result = future.result()
                    all_images.extend(images); details[index] = {'status': 'completed', 'result': safe(result), 'images': images}
                except Exception as exc:
                    details[index] = {'status': 'failed', 'error': str(exc)}
        failed = sum(item.get('status') == 'failed' for item in details if item)
        status = 'partial_failed' if failed and failed < len(details) else ('failed' if failed else 'completed')
        return {'status': status, 'images': all_images, 'succeeded': len(details) - failed, 'failed': failed, 'results': details}, all_images
    raise ValueError(f'不支持的 Agent 工具: {name}')


def agent_input(prompt, images):
    if not images: return prompt
    return [{'role': 'user', 'content': [{'type': 'input_text', 'text': prompt}, *({'type': 'input_image', 'image_url': data_url(image)} for image in images)]}]


def save_session(path, value):
    if not path:
        return
    write_json(path, value)


def fork_session(source, target, branch_id=None):
    value=read_json(source)
    if not isinstance(value,dict) or not value.get('conversation_id'): raise ValueError('无效 Agent session')
    value['parent_session']=str(source); value['branch_id']=branch_id or ('branch-'+uuid.uuid4().hex[:8]); value['status']='forked'
    write_json(target,value); return {'status':'forked','branch_id':value['branch_id'],'session_path':str(target)}


def regenerate_session(source, target=None, round_index=None):
    value=read_json(source)
    if not isinstance(value,dict) or not value.get('conversation_id'): raise ValueError('无效 Agent session')
    total=max(0,int(value.get('rounds',0)))
    if round_index is None: round_index=max(0,total-1)
    if not isinstance(round_index,int) or round_index < 0 or round_index >= max(total,1): raise ValueError('round_index 超出会话轮次')
    value['branch_id']='regen-'+uuid.uuid4().hex[:8]; value['parent_session']=str(source); value['status']='regenerate_requested'; value['regenerate_round']=round_index; value['rounds']=round_index
    target=target or source; write_json(target,value); return {'status':'regenerate_requested','branch_id':value['branch_id'],'round_index':round_index,'session_path':str(target)}


def read_agent_history():
    if not AGENT_HISTORY.exists(): return []
    rows = []
    with open(AGENT_HISTORY, encoding='utf-8') as stream:
        for line in stream:
            try:
                value = json.loads(line)
                if isinstance(value, dict): rows.append(value)
            except json.JSONDecodeError:
                continue
    return rows


def agent_history_list(limit=20):
    rows = read_agent_history()
    return list(reversed(rows[-limit:]))


def agent_history_get(conversation_id):
    rows = [row for row in read_agent_history() if row.get('conversation_id') == conversation_id]
    return rows[-1] if rows else None


def run(args):
    config = read_json(PROFILES)
    profile = next((item for item in config.get('profiles', []) if item.get('id') == args.profile), None)
    if not profile: raise ValueError(f'未知 profile: {args.profile}')
    key_env = profile.get('api_key_env', 'GPT_IMAGE_API_KEY')
    key = os.environ.get(key_env) or os.environ.get('GPT_IMAGE_API_KEY') or connection(profile).get('key')
    if not key and not args.dry_run: raise ValueError(f'首次使用请先配置图片服务器地址和 API Key：--setup 或 POST /v1/setup；缺少环境变量 {key_env}')
    endpoint = endpoint_for(profile, args.endpoint)
    session_path = Path(args.resume) if args.resume else (Path(args.session) if args.session else None)
    session = read_json(session_path) if session_path else None
    if session:
        if session.get('profile') and session.get('profile') != args.profile:
            raise ValueError(f'会话使用 Profile {session.get("profile")}，当前指定为 {args.profile}')
        conversation_id = session.get('conversation_id') or f'agent-{time.strftime("%Y%m%d-%H%M%S")}-{uuid.uuid4().hex[:6]}'
        current_input = session.get('current_input') or []
        raw_responses = session.get('raw_responses') or []
        generated = session.get('generated') or []
        final_text = session.get('final_text') or ''
        start_round = int(session.get('rounds', 0)) + 1
        if not current_input:
            raise ValueError('会话缺少 current_input，无法恢复')
    else:
        task = read_json(args.task) if args.task else {'prompt': args.prompt, 'images': args.image}
        prompt = task.get('prompt')
        if not prompt: raise ValueError('缺少 Agent prompt')
        current_input = agent_input(prompt, task.get('images') or args.image)
        conversation_id = f'agent-{time.strftime("%Y%m%d-%H%M%S")}-{uuid.uuid4().hex[:6]}'
        raw_responses = []; generated = []; final_text = ''
        start_round = 1
    instructions = ('You are a concise image-generation assistant. Use generate_image for one image, '
                    'generate_image_batch only for independent images, and continue_generation only when '
                    'dependent images require another round. Do not expose XML reference tags to the user.')
    session_path = session_path or WORK / f'{conversation_id}-session.json'
    for round_index in range(start_round, start_round + min(args.max_rounds, MAX_ROUNDS)):
        body = {'model': profile.get('model', 'gpt-image-2'), 'instructions': instructions,
                'input': current_input, 'tools': image_tools()}
        if args.dry_run:
            path = WORK / f'{conversation_id}-request.json'; write_json(path, safe(body))
            return {'conversation_id': conversation_id, 'status': 'dry_run', 'request_path': str(path), 'request_path_link': minis_link(path), 'endpoint': endpoint, 'model': body['model']}
        payload, status, raw, attempts = call_api_with_retry(endpoint, key, body, args.timeout, args.agent_retry)
        raw_responses.append({'attempts': attempts, 'payload': safe(payload)}); output = payload.get('output') or []
        final_text = output_text(output) or final_text
        calls = function_calls(output)
        if not calls:
            break
        current_input = [*current_input, *output]
        for call in calls:
            try:
                result, images = execute_call(args, call, references={item.get('id'): item.get('path') for item in generated if item.get('id') and item.get('path')})
            except Exception as exc:
                result, images = {'status': 'failed', 'error': str(exc)}, []
            generated.extend(images)
            current_input.append({'type': 'function_call_output', 'call_id': call.get('call_id'), 'output': json.dumps(result, ensure_ascii=False)})
            if images:
                content = []
                for image in images:
                    image_id = image.get('id', 'generated-image')
                    content.append({'type': 'input_text', 'text': f'<ref id="{image_id}" />'})
                    if image.get('path'):
                        content.append({'type': 'input_image', 'image_url': data_url(image['path'])})
                current_input.append({'role': 'user', 'content': content})
        save_session(session_path, {
            'conversation_id': conversation_id, 'profile': args.profile,
            'rounds': len(raw_responses), 'current_input': current_input,
            'generated': generated, 'raw_responses': raw_responses,
            'final_text': final_text, 'status': 'paused',
        })
    else:
        raise RuntimeError('Agent 达到最大轮次仍未结束')
    WORK.mkdir(parents=True, exist_ok=True)
    response_path = WORK / f'{conversation_id}-responses.json'
    write_json(response_path, raw_responses)
    result = {'conversation_id': conversation_id, 'status': 'completed', 'text': final_text,
              'images': generated, 'rounds': len(raw_responses), 'session_path': str(session_path),
              'session_path_link': minis_link(session_path), 'response_path': str(response_path), 'response_path_link': minis_link(response_path)}
    save_session(session_path, {
        'conversation_id': conversation_id, 'profile': args.profile,
        'branch_id': session.get('branch_id', 'main') if session else 'main',
        'parent_branch_id': session.get('branch_id') if session else None,
        'rounds': len(raw_responses), 'current_input': current_input,
        'generated': generated, 'raw_responses': raw_responses,
        'final_text': final_text, 'status': 'completed',
    })
    with open(AGENT_HISTORY, 'a', encoding='utf-8') as f: f.write(json.dumps(safe(result), ensure_ascii=False) + '\n')
    return result


def main():
    parser = argparse.ArgumentParser(description='GPT Image Playground Responses Agent')
    parser.add_argument('--prompt'); parser.add_argument('--image', action='append', default=[]); parser.add_argument('--task')
    parser.add_argument('--profile', default='default'); parser.add_argument('--endpoint'); parser.add_argument('--image-endpoint'); parser.add_argument('--timeout', type=int, default=900)
    parser.add_argument('--max-rounds', type=int, default=4); parser.add_argument('--image-retry', type=int, default=1)
    parser.add_argument('--session'); parser.add_argument('--resume'); parser.add_argument('--history-list', action='store_true')
    parser.add_argument('--history-get'); parser.add_argument('--history-limit', type=int, default=20)
    parser.add_argument('--agent-retry', type=int, default=1); parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--setup', action='store_true'); parser.add_argument('--setup-json'); parser.add_argument('--connection-status', action='store_true')
    parser.add_argument('--branch-from'); parser.add_argument('--branch-to'); parser.add_argument('--regenerate-session'); parser.add_argument('--round-index', type=int)
    args = parser.parse_args()
    if args.max_rounds < 1 or args.max_rounds > MAX_ROUNDS: parser.error('--max-rounds 必须为 1-8')
    if args.agent_retry < 0 or args.agent_retry > 3: parser.error('--agent-retry 必须为 0-3')
    if args.history_limit < 1 or args.history_limit > 200: parser.error('--history-limit 必须为 1-200')
    if args.timeout < 10 or args.timeout > 3600: parser.error('--timeout 必须为 10-3600')
    try:
        if args.branch_from:
            if not args.branch_to: parser.error('--branch-from 必须配合 --branch-to')
            print(json.dumps(fork_session(args.branch_from,args.branch_to),ensure_ascii=False,indent=2)); return
        if args.regenerate_session:
            print(json.dumps(regenerate_session(args.regenerate_session,args.branch_to,args.round_index),ensure_ascii=False,indent=2)); return
        if args.setup_json:
            print(json.dumps(setup_from_json(read_json(args.setup_json)), ensure_ascii=False, indent=2)); return
        if args.connection_status:
            print(json.dumps(setup_status(), ensure_ascii=False, indent=2)); return
        if args.setup:
            import getpass
            endpoint = input('图片服务器地址: ').strip()
            key = getpass.getpass('API Key（输入不会回显）：')
            print(json.dumps(setup_from_json({'endpoint': endpoint, 'api_key': key, 'model': 'gpt-image-2'}), ensure_ascii=False, indent=2)); return
        if args.history_list:
            print(json.dumps(agent_history_list(args.history_limit), ensure_ascii=False, indent=2)); return
        if args.history_get:
            value = agent_history_get(args.history_get)
            if not value: parser.error(f'找不到 Agent 会话: {args.history_get}')
            print(json.dumps(value, ensure_ascii=False, indent=2)); return
        print(json.dumps(run(args), ensure_ascii=False, indent=2))
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc: parser.error(str(exc))

if __name__ == '__main__': main()
