#!/usr/bin/env python3
import json
import os
import stat
import sys
import tempfile
from pathlib import Path

ROOT = Path('/var/minis/skills/gpt-image-playground')
sys.path.insert(0, str(ROOT / 'scripts'))
import api_server as api
import connection


def check(condition, message):
    if not condition: raise AssertionError(message)


def main():
    check(api.VERSION == '2.3.0', 'version')
    from pathlib import Path as _Path
    import json as _json
    catalog = _json.loads((_Path('/var/minis/skills/gpt-image-playground/model_catalog.json')).read_text())
    check({'gpt-image-2', 'gpt-5.6-sol', 'gpt-5.6-terra', 'gpt-5.6-luna'} <= {item['id'] for item in catalog['models']}, 'model catalog')
    from task_store import record, search
    with tempfile.TemporaryDirectory() as temp:
        db = Path(temp) / 'tasks.sqlite3'; record({'task_id':'t1','created_at':'2026','status':'completed','prompt':'lake','profile':'p'}, db); check(search('lake', path=db)[0]['task_id'] == 't1', 'task store')
    check(api.safe_json('data:image/png;base64,abc').startswith('[data URL omitted'), 'redaction')
    check(api.normalize_task({'prompt': 'x', 'endpoint': 'evil', 'api_key': 'secret'})['prompt'] == 'x', 'normalization')
    try: api.validate_input_image('/etc/passwd'); raise AssertionError('path accepted')
    except ValueError: pass
    image = next(Path('/var/minis/attachments/gpt-image-playground').glob('*.png'))
    paths = api.result_paths({'saved_images': [{'path': str(image)}]})
    check(paths == [image.resolve()], 'result paths')
    try: api.validate_input_image('http://127.0.0.1:1/secret'); raise AssertionError('remote URL accepted')
    except ValueError: pass
    check(api.safe_download_path(str(image)).resolve() == image.resolve(), 'download path')
    try: api.safe_download_path('/etc/passwd'); raise AssertionError('download path accepted')
    except ValueError: pass
    check(set(json.loads((ROOT / 'profiles.json').read_text())['profiles'][0]) <= {'id', 'name', 'provider', 'endpoint', 'model', 'models', 'omit_model', 'api_key_env', 'agent_endpoint', 'baseUrl', 'base_url'}, 'profile schema')
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
