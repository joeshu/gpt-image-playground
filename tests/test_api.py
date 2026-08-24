#!/usr/bin/env python3
import json
import os
import stat
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import api_server as api
import connection


def check(condition, message):
    if not condition: raise AssertionError(message)


def main():
    check(api.VERSION == '2.7.1', 'version')
    from pathlib import Path as _Path
    import json as _json
    catalog = _json.loads((ROOT / 'model_catalog.json').read_text())
    check({'gpt-image-2', 'gpt-5.6-sol', 'gpt-5.6-terra', 'gpt-5.6-luna'} <= {item['id'] for item in catalog['models']}, 'model catalog')
    from task_store import record, search
    with tempfile.TemporaryDirectory() as temp:
        db = Path(temp) / 'tasks.sqlite3'; record({'task_id':'t1','created_at':'2026','status':'completed','prompt':'lake','profile':'p'}, db); check(search('lake', path=db)[0]['task_id'] == 't1', 'task store')
    check(api.safe_json('data:image/png;base64,abc').startswith('[data URL omitted'), 'redaction')
    with tempfile.TemporaryDirectory() as idem_temp:
        old_work = api.API_WORK; api.API_WORK = Path(idem_temp)
        api.save_idempotent('retry-1', {'status': 200, 'body': {'ok': True}})
        check(api.load_idempotent('retry-1')['body']['ok'] is True, 'idempotency load')
        stale = api.idempotency_file('stale'); stale.write_text('{}'); os.utime(stale, (time.time() - 10, time.time() - 10))
        check(api.cleanup_idempotency(1) == 1, 'idempotency cleanup')
        api.API_WORK = old_work
    with tempfile.TemporaryDirectory() as event_temp:
        old_work = api.WORK
        api.WORK = Path(event_temp)
        event_file = api.WORK / 'agent-events.jsonl'
        event_file.write_text(json.dumps({'event': 'tool.completed', 'tool_call_id': 'call-1'}) + '\n', encoding='utf-8')
        api.JOB_EVENTS.clear()
        check(api.forward_agent_events('job-test', {'events_file': str(event_file)}) == 1, 'agent event forwarding')
        check(api.JOB_EVENTS['job-test'][0]['data']['event_id'] == 'job-test-event-1', 'event id')
        api.WORK = old_work
    with tempfile.TemporaryDirectory() as event_temp:
        event_file = Path(event_temp) / 'events.jsonl'
        event_file.write_text(json.dumps({'event': 'round.started'}) + '\n', encoding='utf-8')
        received = []
        position = api.stream_event_file(event_file, 0, received.append)
        check(position == event_file.stat().st_size and received[0]['event'] == 'round.started', 'event streaming')
    check(len({item['data']['event_id'] for item in api.JOB_EVENTS.get('job-test', [])}) == len(api.JOB_EVENTS.get('job-test', [])), 'event ids unique')
    with tempfile.TemporaryDirectory() as process_temp:
        output_script = Path(process_temp) / 'writer.py'
        output_script.write_text("import json, sys\nprint(json.dumps({'status': 'ok'}))\nprint('err', file=sys.stderr)\n", encoding='utf-8')
        result = api.run_executor([sys.executable, str(output_script)], {}, 10)
        check(result == {'status': 'ok'}, 'process output collection')
    normalized_batch = api.normalize_task({'batch_id': 'batch-1', 'tasks': [{'prompt': 'a'}, {'prompt': 'b'}]}, batch=True)
    check(normalized_batch['batch_id'] == 'batch-1' and len(normalized_batch['tasks']) == 2, 'batch normalization')
    old_pool, old_work, old_jobs = api.JOB_POOL, api.API_WORK, api.JOBS
    class FakeFuture: pass
    class FakePool:
        def submit(self, *args): return FakeFuture()
    with tempfile.TemporaryDirectory() as batch_temp:
        api.JOB_POOL, api.API_WORK, api.JOBS = FakePool(), Path(batch_temp), {}
        submitted = api.submit_job('batch', normalized_batch, 10)
        job = api.get_job(submitted['job_id'])
        check(job['parent_task_id'] == 'batch-1' and job['total'] == 2, 'batch parent metadata')
    api.JOB_POOL, api.API_WORK, api.JOBS = old_pool, old_work, old_jobs
    check(api.normalize_task({'prompt': 'x', 'endpoint': 'evil', 'api_key': 'secret'})['prompt'] == 'x', 'normalization')
    try: api.validate_input_image('/etc/passwd'); raise AssertionError('path accepted')
    except ValueError: pass
    with tempfile.TemporaryDirectory() as image_temp:
        image = Path(image_temp) / 'fixture.png'
        image.write_bytes(b'fixture')
        api.ALLOWED_ROOTS = (*api.ALLOWED_ROOTS, Path(image_temp).resolve())
        paths = api.result_paths({'saved_images': [{'path': str(image)}]})
        check(paths == [image.resolve()], 'result paths')
        check(api.safe_download_path(str(image)).resolve() == image.resolve(), 'download path')
    try: api.validate_input_image('http://127.0.0.1:1/secret'); raise AssertionError('remote URL accepted')
    except ValueError: pass
    try: api.safe_download_path('/etc/passwd'); raise AssertionError('download path accepted')
    except ValueError: pass
    check(set(json.loads((ROOT / 'profiles.json').read_text())['profiles'][0]) <= {'id', 'name', 'provider', 'endpoint', 'model', 'agent_model', 'models', 'omit_model', 'api_key_env', 'agent_endpoint', 'baseUrl', 'base_url'}, 'profile schema')
    with tempfile.TemporaryDirectory() as temp:
        old_config, old_work = connection.CONFIG, connection.WORK
        connection.CONFIG, connection.WORK = Path(temp) / 'connection.json', Path(temp)
        saved = connection.save_config('https://example.com/v1/images/generations', 'audit-key', 'gpt-image-2')
        check(saved['configured'], 'setup configured')
        check(stat.S_IMODE(connection.CONFIG.stat().st_mode) == 0o600, 'setup permissions')
        check('audit-key' not in json.dumps(connection.setup_status()), 'setup redaction')
        connection.CONFIG, connection.WORK = old_config, old_work
    print(json.dumps({'status': 'ok', 'tests': 12}, ensure_ascii=False))

if __name__ == '__main__': main()
