#!/usr/bin/env python3
import base64
import json
import sys
import threading
import tempfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from argparse import Namespace
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from provider_base import ProviderContext, ProviderRegistry


def main():
    registry = ProviderRegistry(ROOT / 'scripts', ROOT / 'scripts')
    context = ProviderContext(task={}, task_path=ROOT / 'tests' / 'fixture.json', output_dir=Path('/tmp/out'), workspace_dir=Path('/tmp/work'), dry_run=True, task_id='t')
    assert registry.resolve({'api_mode': 'responses'}).name == 'responses-script'
    assert registry.resolve({'provider': 'fal'}).name == 'fal-script'
    assert registry.resolve({'provider': 'custom-provider'}).name == 'custom-script'
    assert registry.resolve({'provider': 'openai-compatible'}).name == 'images-native'
    assert '--dry-run' in registry.resolve({'provider': 'openai-compatible', 'execution_mode': 'script'}).command(context)
    import custom_provider
    assert custom_provider.retryable_poll_status(429)
    assert custom_provider.retryable_poll_status(503)
    assert not custom_provider.retryable_poll_status(400)
    assert custom_provider.poll_delay(2, 3) == 8
    from provider_base import ProviderError, _retryable_network_error
    assert ProviderError('x', code='missing_endpoint').code == 'missing_endpoint'
    assert _retryable_network_error(ProviderError('Native multipart 请求失败: EOF occurred in violation of protocol', code='native_request_failed'))
    assert not _retryable_network_error(ProviderError('HTTP 400 from image endpoint: invalid_value', code='provider_request_rejected'))

    import provider_base as pb
    with tempfile.TemporaryDirectory() as temp:
        temp = Path(temp); source = temp / 'source.png'; mask = temp / 'mask.png'
        (temp / 'out').mkdir(); (temp / 'work').mkdir()
        source.write_bytes(b'PNG-SOURCE'); mask.write_bytes(b'PNG-MASK')
        captured = {}
        def fake_multipart(url, key, fields, files, timeout):
            captured.update(url=url, key=key, fields=fields, files=files, timeout=timeout)
            return {'data': [{'b64_json': base64.b64encode(b'PNG-RESULT').decode()}]}
        original_multipart = pb._multipart_request; pb._multipart_request = fake_multipart
        try:
            edit_context = ProviderContext(task={'prompt': 'edit', 'endpoint': 'https://example.test/v1/images/generations', 'images': [str(source)], 'mask': str(mask), 'model': 'gpt-image-2'}, task_path=temp / 'task.json', output_dir=temp / 'out', workspace_dir=temp / 'work', dry_run=False, task_id='edit-1')
            result = json.loads(registry.native_images.run(edit_context, {'GPT_IMAGE_API_KEY': 'fixture-key'}))
        finally:
            pb._multipart_request = original_multipart
        assert captured['url'].endswith('/images/edits')
        assert captured['key'] == 'fixture-key'
        assert [item[0] for item in captured['files']] == ['image[]', 'mask']
        assert captured['fields']['prompt'] == 'edit'
        assert result['saved_images']

    class NativeFixture:
        name = 'images-native-fixture'
        mode = 'native'
        def __init__(self, error=None): self.error = error
        def is_file(self): return True
        def run(self, _context, _env):
            if self.error: raise self.error
            return json.dumps({'status': 'completed', 'execution_mode': 'native', 'provider': self.name})

    class ScriptFixture:
        name = 'images-script-fixture'
        mode = 'script'
        class _Script:
            def is_file(self): return True
        script = _Script()
        def run(self, _context, _env):
            return json.dumps({'status': 'completed', 'execution_mode': 'script', 'provider': self.name})

    fallback_registry = ProviderRegistry(ROOT / 'scripts', ROOT / 'scripts')
    fallback_registry.native_images = NativeFixture(ProviderError('network down', provider='images-native', code='native_request_failed'))
    fallback_registry.providers['images'] = fallback_registry.native_images
    fallback_registry.script_images = ScriptFixture()
    fallback_result = json.loads(fallback_registry.run(context, {'GPT_IMAGE_API_KEY': 'fixture'}))
    assert fallback_result['execution_mode'] == 'script'
    assert fallback_result['fallback_from'] == 'images-native-fixture'
    assert fallback_result['fallback_reason'] == 'native_request_failed'

    strict_registry = ProviderRegistry(ROOT / 'scripts', ROOT / 'scripts')
    strict_registry.native_images = NativeFixture(ProviderError('bad input', provider='images-native', code='missing_image'))
    strict_registry.providers['images'] = strict_registry.native_images
    strict_registry.script_images = ScriptFixture()
    try:
        strict_registry.run(ProviderContext(task={'execution_mode': 'native'}, task_path=context.task_path, output_dir=context.output_dir, workspace_dir=context.workspace_dir, dry_run=True, task_id='strict'), {})
    except ProviderError as exc:
        assert exc.code == 'missing_image'
    else:
        raise AssertionError('strict native mode must not fall back')

    import agent
    import inspect
    profiles = json.loads((ROOT / 'profiles.json').read_text(encoding='utf-8'))['profiles']
    default_profile = next(item for item in profiles if item['id'] == 'default')
    assert default_profile['model'] == 'gpt-image-2'
    assert default_profile['agent_model'] == 'gpt-5.6-terra'
    assert "profile.get('agent_model', 'gpt-5.6-terra')" in inspect.getsource(agent.run)
    assert "if native_mode:" in inspect.getsource(agent.run)
    assert 'native_image_outputs' in inspect.getsource(agent.run)
    assert "default='native'" in inspect.getsource(agent.main)
    references = {'base': '/tmp/base.png', 'round-1-image-1': '/tmp/round.png'}
    prompt, images = agent.resolve_prompt_references('保持 <ref id="base" /> 的风格', references)
    assert prompt == '保持  的风格'
    assert images == ['/tmp/base.png']
    call = agent.normalize_tool_call({'name': 'generate_image_batch', 'arguments': json.dumps({'images': [{'id': 'x x', 'prompt': 'a'}, {'id': 'x x', 'prompt': 'b'}]})})
    parsed = json.loads(call['arguments'])
    assert [item['id'] for item in parsed['images']] == ['x-x', 'x-x-2']
    assert 'pending_tool_calls' in inspect.getsource(agent.run)
    assert 'completed_tool_calls' in inspect.getsource(agent.run)
    assert '--execution-mode' in inspect.getsource(agent.run_playground)
    batch_call = agent.normalize_tool_call({'call_id': 'batch-call', 'name': 'generate_image_batch', 'arguments': json.dumps({'images': [{'id': 'a', 'prompt': 'a'}, {'id': 'b', 'prompt': 'b'}]})})
    assert json.loads(batch_call['arguments'])['images'][0]['id'] == 'a'
    assert 'batch_call_id' in inspect.getsource(agent.execute_call)
    import playground
    assert 'reused' in inspect.getsource(playground.retry_batch)
    assert 'retried' in inspect.getsource(playground.retry_batch)
    import responses_provider
    state = {'output': []}
    responses_provider.apply_stream_event(state, {'type': 'response.output_text.delta', 'delta': 'hello'})
    responses_provider.apply_stream_event(state, {'type': 'response.output_item.done', 'item': {'type': 'image_generation_call', 'result': base64.b64encode(b'image').decode()}})
    assert state['text'] == 'hello'
    assert len(responses_provider.output_items(state)) == 1
    class ResponsesFixture(BaseHTTPRequestHandler):
        requests = []

        def do_POST(self):
            length = int(self.headers.get('Content-Length', '0'))
            body = json.loads(self.rfile.read(length).decode())
            self.__class__.requests.append(body)
            if len(self.__class__.requests) == 1:
                output = [{'type': 'function_call', 'call_id': 'call-fixture-1', 'name': 'generate_image',
                           'arguments': json.dumps({'id': 'fixture-image', 'prompt': 'fixture prompt'})}]
            else:
                output = [{'type': 'message', 'content': [{'type': 'output_text', 'text': 'fixture complete'}]}]
            payload = json.dumps({'id': f'response-{len(self.__class__.requests)}', 'output': output}).encode()
            self.send_response(200); self.send_header('Content-Type', 'application/json'); self.send_header('Content-Length', str(len(payload))); self.end_headers(); self.wfile.write(payload)

        def log_message(self, *_):
            return

    fixture = ThreadingHTTPServer(('127.0.0.1', 0), ResponsesFixture)
    thread = threading.Thread(target=fixture.serve_forever, daemon=True); thread.start()
    with tempfile.TemporaryDirectory() as temp:
        temp_path = Path(temp)
        old_values = {name: getattr(agent, name) for name in ('PROFILES', 'WORK', 'AGENT_HISTORY', 'connection', 'execute_call')}
        profile_path = temp_path / 'profiles.json'
        profile_path.write_text(json.dumps({'profiles': [{'id': 'fixture', 'model': 'fixture-model', 'api_key_env': 'FIXTURE_KEY'}]}), encoding='utf-8')
        agent.PROFILES = profile_path
        agent.WORK = temp_path / 'work'
        agent.AGENT_HISTORY = temp_path / 'history.jsonl'
        agent.connection = lambda _profile: {'configured': True, 'key': 'fixture-key'}
        agent.execute_call = lambda _args, _call, references=None: ({'status': 'completed', 'images': []}, [])
        args = Namespace(profile='fixture', endpoint=f'http://127.0.0.1:{fixture.server_port}', image_endpoint=None,
                         prompt='fixture request', image=[], task=None, timeout=10, execution_mode='script', max_rounds=3,
                         image_retry=0, session=None, resume=None, agent_retry=0, stream=False, dry_run=False)
        result = agent.run(args)
        assert result['text'] == 'fixture complete'
        assert len(ResponsesFixture.requests) == 2
        assert any(isinstance(item, dict) and item.get('type') == 'function_call_output' for item in ResponsesFixture.requests[1]['input'])
        assert any(json.loads(line).get('event') == 'tool.completed' for line in (agent.WORK / f"{result['conversation_id']}-events.jsonl").read_text().splitlines())
        for name, value in old_values.items(): setattr(agent, name, value)
    fixture.shutdown(); fixture.server_close(); thread.join(timeout=2)

    class SSEFixture(BaseHTTPRequestHandler):
        requests = []

        def do_POST(self):
            length = int(self.headers.get('Content-Length', '0'))
            body = json.loads(self.rfile.read(length).decode())
            self.__class__.requests.append(body)
            call = {'type': 'function_call', 'call_id': 'sse-call-1', 'name': 'generate_image',
                    'arguments': json.dumps({'id': 'sse-image', 'prompt': 'sse prompt'})}
            if len(self.__class__.requests) == 1:
                response = {'id': 'sse-response-1', 'output': [call]}
                events = [
                    {'type': 'response.output_item.done', 'item': call},
                    {'type': 'response.completed', 'response': response},
                ]
            else:
                response = {'id': 'sse-response-2', 'output': [{'type': 'message', 'content': [{'type': 'output_text', 'text': 'stream complete'}]}]}
                events = [
                    {'type': 'response.output_text.delta', 'delta': 'stream '},
                    {'type': 'response.output_text.delta', 'delta': 'complete'},
                    {'type': 'response.completed', 'response': response},
                ]
            raw = ''.join(f'data: {json.dumps(event)}\n\n' for event in events) + 'data: [DONE]\n\n'
            payload = raw.encode()
            self.send_response(200); self.send_header('Content-Type', 'text/event-stream'); self.send_header('Content-Length', str(len(payload))); self.end_headers(); self.wfile.write(payload)

        def log_message(self, *_):
            return

    sse_fixture = ThreadingHTTPServer(('127.0.0.1', 0), SSEFixture)
    sse_thread = threading.Thread(target=sse_fixture.serve_forever, daemon=True); sse_thread.start()
    with tempfile.TemporaryDirectory() as temp:
        temp_path = Path(temp)
        old_values = {name: getattr(agent, name) for name in ('PROFILES', 'WORK', 'AGENT_HISTORY', 'connection', 'execute_call')}
        profile_path = temp_path / 'profiles.json'
        profile_path.write_text(json.dumps({'profiles': [{'id': 'sse', 'model': 'sse-model', 'api_key_env': 'SSE_KEY'}]}), encoding='utf-8')
        agent.PROFILES = profile_path; agent.WORK = temp_path / 'work'; agent.AGENT_HISTORY = temp_path / 'history.jsonl'
        agent.connection = lambda _profile: {'configured': True, 'key': 'sse-key'}
        agent.execute_call = lambda _args, _call, references=None: ({'status': 'completed', 'images': []}, [])
        args = Namespace(profile='sse', endpoint=f'http://127.0.0.1:{sse_fixture.server_port}', image_endpoint=None,
                         prompt='sse request', image=[], task=None, timeout=10, execution_mode='script', max_rounds=3,
                         image_retry=0, session=None, resume=None, agent_retry=0, stream=True, dry_run=False)
        result = agent.run(args)
        assert result['text'] == 'stream complete'
        assert len(SSEFixture.requests) == 2
        assert all(request.get('stream') is True for request in SSEFixture.requests)
        event_lines = (agent.WORK / f"{result['conversation_id']}-events.jsonl").read_text().splitlines()
        assert any(json.loads(line).get('event') == 'tool.completed' for line in event_lines)
        for name, value in old_values.items(): setattr(agent, name, value)
    sse_fixture.shutdown(); sse_fixture.server_close(); sse_thread.join(timeout=2)
    print('provider_registry_tests=ok')


if __name__ == '__main__':
    main()
