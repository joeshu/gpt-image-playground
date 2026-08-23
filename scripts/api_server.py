#!/usr/bin/env python3
"""Local REST API for the GPT Image Playground.

The server is intentionally stdlib-only and delegates work to the existing
CLI executors. It binds localhost by default and never accepts client-supplied
provider endpoints or API keys.
"""
import argparse
import base64
import concurrent.futures
import ipaddress
import json
import mimetypes
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import uuid
import zipfile
try:
    from connection import connection, setup_from_json, setup_status
except ImportError:
    from scripts.connection import connection, setup_from_json, setup_status
try:
    from task_store import search as search_tasks, record as record_task, get as get_task, upsert as upsert_task, DB as TASK_DB
except ImportError:
    from scripts.task_store import search as search_tasks, record as record_task, get as get_task, upsert as upsert_task, DB as TASK_DB
try:
    from image_store import list_images, set_favorite, delete_images, index_result, thumbnail
except ImportError:
    from scripts.image_store import list_images, set_favorite, delete_images, index_result, thumbnail
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

VERSION = '2.0.1'
API_MIN_CLIENT = '1.0.0'
ROOT = Path('/var/minis/skills/gpt-image-playground')
WORK = Path('/var/minis/workspace/gpt-image-playground')
ATTACHMENTS = Path('/var/minis/attachments/gpt-image-playground')
API_WORK = WORK / 'api'
PLAYGROUND = ROOT / 'scripts' / 'playground.py'
AGENT = ROOT / 'scripts' / 'agent.py'
PROFILES = ROOT / 'profiles.json'
MAX_BODY = 12 * 1024 * 1024
MAX_TIMEOUT = 1200
ALLOWED_ROOTS = (Path('/var/minis/attachments'), Path('/var/minis/workspace'), Path('/var/minis/mounts'))


def read_json(path):
    with open(path, encoding='utf-8') as stream:
        return json.load(stream)


def safe_json(value):
    if isinstance(value, dict): return {key: safe_json(item) for key, item in value.items()}
    if isinstance(value, list): return [safe_json(item) for item in value]
    if isinstance(value, str) and value.startswith('data:'):
        return f'[data URL omitted: {len(value)} chars]'
    return value


def parse_output(stdout):
    try:
        value = json.loads(stdout)
    except json.JSONDecodeError:
        raise ValueError('执行器返回了非 JSON 输出')
    return safe_json(value)


def validate_input_image(value):
    if not isinstance(value, str):
        raise ValueError('图片输入必须是字符串')
    if value.startswith('data:image/'):
        return value
    if value.startswith(('https://', 'http://')):
        raise ValueError('API 不接受远程图片 URL，请先上传图片或使用白名单本地路径')
    path = Path(value).expanduser()
    try:
        resolved = path.resolve()
    except OSError as exc:
        raise ValueError(f'图片路径无效: {value}') from exc
    if not any(resolved == root or root in resolved.parents for root in ALLOWED_ROOTS):
        raise ValueError('图片路径必须位于 /var/minis/attachments、workspace 或 mounts')
    if not resolved.is_file():
        raise ValueError(f'图片不存在: {value}')
    return str(resolved)


def normalize_task(task, batch=False):
    if not isinstance(task, dict): raise ValueError('请求体必须是 JSON 对象')
    result = dict(task)
    for key in ('images', 'image_urls'):
        if key in result:
            values = result[key]
            if not isinstance(values, list) or len(values) > 16:
                raise ValueError('参考图必须是最多 16 项的数组')
            result[key] = [validate_input_image(item) for item in values]
    if 'mask' in result and result['mask']:
        result['mask'] = validate_input_image(result['mask'])
    if 'tasks' in result:
        if not isinstance(result['tasks'], list) or not result['tasks'] or len(result['tasks']) > 100:
            raise ValueError('tasks 必须是 1-100 项的数组')
        result['tasks'] = [normalize_task(item) for item in result['tasks']]
    if not batch and 'tasks' in result:
        raise ValueError('单任务接口不接受 tasks，请使用 /v1/batch')
    result.pop('endpoint', None)
    result.pop('agent_endpoint', None)
    result.pop('api_key', None)
    result.pop('api_key_env', None)
    return result


def profile_exists(profile_id):
    profiles = read_json(PROFILES)
    ids = {item.get('id') for item in profiles.get('profiles', [])}
    if profile_id not in ids: raise ValueError(f'未知 profile: {profile_id}')


def write_request(kind, payload):
    API_WORK.mkdir(parents=True, exist_ok=True)
    path = API_WORK / f'{kind}-{time.strftime("%Y%m%d-%H%M%S")}-{uuid.uuid4().hex[:8]}.json'
    with open(path, 'w', encoding='utf-8') as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2)
    return path


def has_data_url(value):
    if isinstance(value, str): return value.startswith('data:image/')
    if isinstance(value, list): return any(has_data_url(item) for item in value)
    if isinstance(value, dict): return any(has_data_url(item) for item in value.values())
    return False


def materialize_data_url(value, temporary):
    if not isinstance(value, str) or not value.startswith('data:image/'):
        return value
    try:
        header, encoded = value.split(',', 1)
        suffix = '.png' if 'png' in header else ('.webp' if 'webp' in header else ('.jpg' if 'jpeg' in header or 'jpg' in header else '.bin'))
        fd, name = tempfile.mkstemp(prefix='gip-upload-', suffix=suffix)
        os.close(fd)
        Path(name).write_bytes(base64.b64decode(encoded))
        temporary.append(Path(name)); return name
    except (ValueError, OSError, base64.binascii.Error) as exc:
        raise ValueError('图片 Data URL 无效') from exc


def materialize_payload(value, temporary):
    if isinstance(value, str): return materialize_data_url(value, temporary)
    if isinstance(value, list): return [materialize_payload(item, temporary) for item in value]
    if isinstance(value, dict): return {key: materialize_payload(item, temporary) for key, item in value.items()}
    return value


def run_executor(command, payload, timeout):
    temporary = []
    payload = materialize_payload(payload, temporary)
    dry_run = bool(payload.pop('dry_run', False))
    contains_data = has_data_url(payload)
    if contains_data:
        fd, name = tempfile.mkstemp(prefix='gip-api-', suffix='.json')
        os.close(fd)
        request_path = Path(name)
    else:
        request_path = write_request('request', payload)
    try:
        with open(request_path, 'w', encoding='utf-8') as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2)
        command += ['--task', str(request_path)]
        if dry_run:
            command.append('--dry-run')
        env = os.environ.copy()
        completed = subprocess.run(command, capture_output=True, text=True, timeout=timeout, env=env)
    finally:
        if contains_data:
            request_path.unlink(missing_ok=True)
        for item in temporary:
            item.unlink(missing_ok=True)
    if completed.returncode:
        message = (completed.stderr or completed.stdout or '执行器失败').strip()[-4000:]
        raise ExecutorError(message, 502)
    return parse_output(completed.stdout)


class ExecutorError(Exception):
    def __init__(self, message, status=500):
        super().__init__(message); self.status = status


def run_generate(payload, timeout):
    profile = payload.get('profile')
    if profile: profile_exists(profile)
    value = connection(next((x for x in read_json(PROFILES).get('profiles', []) if x.get('id') == (profile or 'default')), {}))
    if not value['configured']:
        raise ExecutorError('首次使用请先配置图片服务器地址和 API Key：POST /v1/setup 或运行 playground.py --setup', 428)
    return run_executor([sys.executable, str(PLAYGROUND), '--profile', profile or 'default'], payload, timeout)


def run_batch(payload, timeout):
    profile = payload.get('profile')
    if profile: profile_exists(profile)
    value = connection(next((x for x in read_json(PROFILES).get('profiles', []) if x.get('id') == (profile or 'default')), {}))
    if not value['configured']:
        raise ExecutorError('首次使用请先配置图片服务器地址和 API Key：POST /v1/setup 或运行 playground.py --setup', 428)
    return run_executor([sys.executable, str(PLAYGROUND), '--profile', profile or 'default'], payload, timeout)


def run_agent(payload, timeout):
    profile = payload.get('profile') or 'default'
    profile_exists(profile)
    value = connection(next((x for x in read_json(PROFILES).get('profiles', []) if x.get('id') == profile), {}))
    if not value['configured']:
        raise ExecutorError('首次使用请先配置图片服务器地址和 API Key：POST /v1/setup 或运行 agent.py --setup', 428)
    return run_executor([sys.executable, str(AGENT), '--profile', profile], payload, timeout)


JOB_POOL = concurrent.futures.ThreadPoolExecutor(max_workers=2, thread_name_prefix='gip-api-job')
JOB_LOCK = threading.Lock()
JOBS = {}
JOB_EVENTS = {}
JOB_CONDITION = threading.Condition(JOB_LOCK)
MAX_JOBS = 32


def emit_job(job_id, event, data):
    with JOB_CONDITION:
        JOB_EVENTS.setdefault(job_id, []).append({'event': event, 'data': data, 'at': time.time()})
        JOB_CONDITION.notify_all()


def job_file(job_id):
    API_WORK.joinpath('jobs').mkdir(parents=True, exist_ok=True)
    return API_WORK / 'jobs' / f'{job_id}.json'


def save_job(job):
    path = job_file(job['id'])
    persisted = {key: value for key, value in job.items() if key != 'future'}
    with open(path, 'w', encoding='utf-8') as stream:
        json.dump(safe_json(persisted), stream, ensure_ascii=False, indent=2)


def get_job(job_id):
    with JOB_LOCK:
        job = JOBS.get(job_id)
    if job:
        return {key: value for key, value in job.items() if key != 'future'}
    path = job_file(job_id)
    if path.exists():
        return read_json(path)
    return None


def execute_job(job_id, kind, payload, timeout):
    with JOB_LOCK:
        job = JOBS[job_id]
        job['status'] = 'running'
        job['started_at'] = time.time()
        save_job(job)
    emit_job(job_id, 'running', {'status': 'running'})
    try:
        if kind == 'generate': result = run_generate(payload, timeout)
        elif kind == 'batch': result = run_batch(payload, timeout)
        else: result = run_agent(payload, timeout)
        with JOB_LOCK:
            job['status'] = 'completed'
            job['result'] = result
            job['finished_at'] = time.time()
            save_job(job)
        emit_job(job_id, 'completed', {'status': 'completed', 'result': result})
    except Exception as exc:
        with JOB_LOCK:
            job['status'] = 'failed'
            job['error'] = str(exc)[-4000:]
            job['finished_at'] = time.time()
            save_job(job)
        emit_job(job_id, 'failed', {'status': 'failed', 'error': str(exc)[-4000:]})


def submit_job(kind, payload, timeout):
    with JOB_LOCK:
        active = sum(item.get('status') in ('queued', 'running') for item in JOBS.values())
        if active >= MAX_JOBS:
            raise ExecutorError('后台任务队列已满', 429)
        job_id = f'job-{time.strftime("%Y%m%d-%H%M%S")}-{uuid.uuid4().hex[:8]}'
        job = {'id': job_id, 'kind': kind, 'status': 'queued', 'created_at': time.time()}
        JOBS[job_id] = job
        save_job(job)
    future = JOB_POOL.submit(execute_job, job_id, kind, dict(payload), timeout)
    with JOB_LOCK:
        JOBS[job_id]['future'] = future
    return {'job_id': job_id, 'status': 'queued', 'status_url': f'/v1/jobs/{job_id}'}


def restore_jobs():
    jobs_dir = API_WORK / 'jobs'
    if not jobs_dir.is_dir(): return
    for path in jobs_dir.glob('job-*.json'):
        try:
            job = read_json(path)
            if job.get('status') in ('queued', 'running'):
                job['status'] = 'failed'
                job['error'] = 'API 服务重启时任务未完成'
                job['finished_at'] = time.time()
                with JOB_LOCK:
                    JOBS[job['id']] = job
                save_job(job)
            elif job.get('id'):
                with JOB_LOCK: JOBS[job['id']] = job
        except (OSError, ValueError, json.JSONDecodeError):
            continue


def result_paths(value, found=None):
    if found is None: found = []
    if isinstance(value, dict):
        for child in value.values(): result_paths(child, found)
    elif isinstance(value, list):
        for child in value: result_paths(child, found)
    elif isinstance(value, str):
        path = Path(value)
        if path.is_file() and path.suffix.lower() in ('.png', '.jpg', '.jpeg', '.webp', '.gif'):
            resolved = path.resolve()
            if any(resolved == root or root in resolved.parents for root in ALLOWED_ROOTS) and resolved not in found:
                found.append(resolved)
    return found


def make_zip(value):
    paths = result_paths(value)
    if not paths: raise ValueError('结果中没有可下载图片')
    API_WORK.mkdir(parents=True, exist_ok=True)
    target = API_WORK / f'export-{time.strftime("%Y%m%d-%H%M%S")}-{uuid.uuid4().hex[:8]}.zip'
    with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED) as archive:
        used = set()
        for path in paths:
            name = path.name
            if name in used: name = f'{len(used)+1}-{name}'
            used.add(name); archive.write(path, name)
    return target


def make_backup():
    API_WORK.mkdir(parents=True, exist_ok=True)
    target=API_WORK / f'backup-{time.strftime("%Y%m%d-%H%M%S")}-{uuid.uuid4().hex[:8]}.zip'
    manifest={'version':1,'created_at':time.time(),'history':search_tasks(limit=200),'gallery':list_images(limit=200)}
    with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('manifest.json',json.dumps(manifest,ensure_ascii=False,indent=2))
        for item in manifest['gallery']:
            path=Path(item.get('path',''))
            if path.is_file() and any(path.resolve()==root or root in path.resolve().parents for root in ALLOWED_ROOTS): archive.write(path,'images/'+path.name)
    return target


def extract_manifest(zip_path):
    with zipfile.ZipFile(zip_path) as z:
        names=set(z.namelist())
        if 'manifest.json' not in names: raise ValueError('备份缺少 manifest.json')
        manifest=json.loads(z.read('manifest.json').decode('utf-8'))
        if not isinstance(manifest,dict) or manifest.get('version') != 1: raise ValueError('不支持的备份版本')
        for name in names:
            if name.startswith('/') or '..' in Path(name).parts: raise ValueError('备份包含不安全路径')
        return manifest, names


def restore_backup(zip_path, apply=False, conflict='skip'):
    manifest,names=extract_manifest(zip_path); restored=0; tasks=0; skipped=0; copied=[]
    if conflict not in ('fail','skip','replace'): raise ValueError('conflict 必须是 fail、skip 或 replace')
    if apply:
        extract_root=API_WORK/'restore-staging'/uuid.uuid4().hex; extract_root.mkdir(parents=True,exist_ok=False)
        db_backup=None
        try:
            if TASK_DB.exists(): db_backup=TASK_DB.with_suffix('.restore-backup'); shutil.copy2(TASK_DB,db_backup)
            with zipfile.ZipFile(zip_path) as z: z.extractall(extract_root)
            for item in manifest.get('history',[]):
                result=upsert_task(item, conflict=conflict)
                tasks += result in ('inserted','replaced'); skipped += result=='skipped'
            for item in manifest.get('gallery',[]):
                original=Path(item.get('path','')); source=extract_root/'images'/original.name
                if source.is_file():
                    target=ATTACHMENTS/original.name; target.parent.mkdir(parents=True,exist_ok=True)
                    if target.exists() and conflict=='fail': raise ValueError(f'图片已存在: {target.name}')
                    if not target.exists() or conflict=='replace': shutil.copy2(source,target); copied.append(target)
                    if target.exists():
                        item=dict(item); item['path']=str(target); index_result({'task_id':item.get('task_id'),'saved_images':[item]}); restored += 1
        except Exception:
            for path in copied: path.unlink(missing_ok=True)
            if db_backup and db_backup.exists(): shutil.copy2(db_backup,TASK_DB)
            raise
        finally:
            if db_backup: db_backup.unlink(missing_ok=True)
            shutil.rmtree(extract_root,ignore_errors=True)
    else: restored=sum(1 for item in manifest.get('gallery',[]) if 'images/'+Path(item.get('path','')).name in names)
    return {'status':'restored' if apply else 'validated','version':manifest['version'],'tasks':int(tasks) if apply else len(manifest.get('history',[])),'images':restored,'skipped':skipped,'conflict':conflict}


def safe_download_path(raw_path, allow_zip=False):
    path = Path(raw_path).expanduser().resolve()
    if not any(path == root or root in path.parents for root in ALLOWED_ROOTS):
        raise ValueError('文件路径不在允许目录内')
    allowed = ('.png', '.jpg', '.jpeg', '.webp', '.gif') + (('.zip',) if allow_zip else ())
    if path.suffix.lower() not in allowed or not path.is_file():
        raise ValueError('文件不存在或类型不受支持')
    return path


OPENAPI = {
    'openapi': '3.0.3', 'info': {'title': 'GPT Image Playground API', 'version': VERSION},
    'paths': {
        '/v1/version': {'get': {'responses': {'200': {'description': 'Version compatibility'}}}},
        '/v1/profiles': {'get': {'responses': {'200': {'description': 'Profiles'}}}},
        '/v1/history': {'get': {'responses': {'200': {'description': 'History'}}}},
        '/v1/setup': {'post': {'requestBody': {'required': True}, 'responses': {'200': {'description': 'Configured'}}}},
        '/v1/setup/status': {'get': {'responses': {'200': {'description': 'Configuration status'}}}},
        '/v1/gallery': {'get': {'responses': {'200': {'description': 'Image gallery'}}}},
        '/v1/favorites': {'get': {'responses': {'200': {'description': 'Favorite images'}}}},
        '/v1/favorite': {'post': {'requestBody': {'required': True}, 'responses': {'200': {'description': 'Favorite updated'}}}},
        '/v1/backup/export': {'post': {'responses': {'200': {'description': 'Backup ZIP'}}}},
        '/v1/delete-images': {'post': {'requestBody': {'required': True}, 'responses': {'200': {'description': 'Deleted'}}}},
        '/v1/agent/branch': {'post': {'requestBody': {'required': True}, 'responses': {'200': {'description': 'Forked'}}}},
        '/v1/agent/regenerate': {'post': {'requestBody': {'required': True}, 'responses': {'200': {'description': 'Regeneration requested'}}}},
        '/v1/thumbnails': {'get': {'responses': {'200': {'description': 'Thumbnail'}}}},
        '/v1/backup/import': {'post': {'requestBody': {'required': True}, 'responses': {'200': {'description': 'Restored backup'}}}},
        '/v1/agent/branch': {'post': {'requestBody': {'required': True}, 'responses': {'200': {'description': 'Forked'}}}},
        '/v1/agent/regenerate': {'post': {'requestBody': {'required': True}, 'responses': {'200': {'description': 'Regeneration requested'}}}},
        '/v1/generate': {'post': {'requestBody': {'required': True}, 'responses': {'200': {'description': 'Result'}, '202': {'description': 'Job'}}}},
        '/v1/batch': {'post': {'requestBody': {'required': True}, 'responses': {'200': {'description': 'Result'}, '202': {'description': 'Job'}}}},
        '/v1/agent': {'post': {'requestBody': {'required': True}, 'responses': {'200': {'description': 'Result'}, '202': {'description': 'Job'}}}},
        '/v1/jobs/{job_id}': {'get': {'parameters': [{'name': 'job_id', 'in': 'path', 'required': True}], 'responses': {'200': {'description': 'Job'}}}},
        '/v1/files': {'get': {'parameters': [{'name': 'path', 'in': 'query', 'required': True}], 'responses': {'200': {'description': 'Image'}}}},
    }
}


class Handler(BaseHTTPRequestHandler):
    server_version = 'GPTImagePlaygroundAPI/2.0.1'

    def log_message(self, fmt, *args):
        sys.stderr.write('[playground-api] ' + (fmt % args) + '\n')

    def send_error(self, status, code, message, details=None):
        return self.send_json(status, {'error': {'code': code, 'message': message, 'details': details or {}}})

    def send_json(self, status, value):
        raw = json.dumps(safe_json(value), ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(raw)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Access-Control-Allow-Origin', 'http://127.0.0.1')
        self.end_headers()
        self.wfile.write(raw)

    def authorized(self):
        expected = os.environ.get('GPT_PLAYGROUND_API_TOKEN')
        if not expected: return True
        supplied = self.headers.get('Authorization', '')
        return supplied == f'Bearer {expected}'

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header('Access-Control-Allow-Origin', 'http://127.0.0.1')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.end_headers()

    def serve_web(self, path):
        relative = 'index.html' if path in ('/', '/index.html') else path.removeprefix('/web/')
        candidate = (ROOT / 'web' / relative).resolve()
        web_root = (ROOT / 'web').resolve()
        if web_root not in candidate.parents and candidate != web_root:
            return self.send_error(403, 'forbidden', '禁止访问')
        if not candidate.is_file(): return self.send_error(404, 'not_found', '资源不存在')
        raw = candidate.read_bytes()
        content_type = mimetypes.guess_type(candidate.name)[0] or 'application/octet-stream'
        self.send_response(200)
        self.send_header('Content-Type', content_type + ('; charset=utf-8' if content_type.startswith('text/') or content_type == 'application/javascript' else ''))
        self.send_header('Content-Length', str(len(raw)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers(); self.wfile.write(raw)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path in ('/', '/index.html') or parsed.path.startswith('/web/'):
            return self.serve_web(parsed.path)
        if not self.authorized(): return self.send_error(401, 'unauthorized', '需要 Bearer Token')
        try:
            if parsed.path == '/v1/version':
                return self.send_json(200, {'api_version': VERSION, 'skill_version': VERSION, 'min_client_version': API_MIN_CLIENT, 'compatibility': 'v1'})
            if parsed.path == '/v1/setup/status':
                profile_id = parse_qs(parsed.query).get('profile', ['default'])[0]
                config = read_json(PROFILES); profile = next((x for x in config.get('profiles', []) if x.get('id') == profile_id), {'id': profile_id})
                return self.send_json(200, setup_status(profile))
            if parsed.path == '/openapi.json':
                return self.send_json(200, OPENAPI)
            if parsed.path == '/healthz':
                return self.send_json(200, {'status': 'ok', 'version': VERSION, 'active_jobs': sum(item.get('status') in ('queued', 'running') for item in JOBS.values())})
            if parsed.path == '/v1/profiles':
                config = read_json(PROFILES)
                profiles = []
                for item in config.get('profiles', []):
                    profiles.append({key: item.get(key) for key in ('id', 'name', 'provider', 'model', 'agent_endpoint')})
                return self.send_json(200, {'default_profile': config.get('default_profile'), 'profiles': profiles})
            if parsed.path.startswith('/v1/jobs/') and parsed.path.endswith('/events'):
                job_id = parsed.path.split('/')[-2]
                if not get_job(job_id): return self.send_error(404, 'job_not_found', 'Job 不存在')
                self.send_response(200); self.send_header('Content-Type', 'text/event-stream'); self.send_header('Cache-Control', 'no-cache'); self.send_header('Connection', 'close'); self.end_headers()
                index = 0; deadline = time.time() + 300
                while time.time() < deadline:
                    with JOB_CONDITION:
                        events = JOB_EVENTS.get(job_id, [])[index:]
                        if not events: JOB_CONDITION.wait(timeout=2); events = JOB_EVENTS.get(job_id, [])[index:]
                    for item in events:
                        self.wfile.write(('event: '+item['event']+'\ndata: '+json.dumps(safe_json(item['data']),ensure_ascii=False)+'\n\n').encode()); self.wfile.flush(); index += 1
                        if item['event'] in ('completed','failed'): return
                return
            if parsed.path.startswith('/v1/jobs/'):
                job_id = parsed.path.rsplit('/', 1)[-1]
                job = get_job(job_id)
                if not job: return self.send_error(404, 'job_not_found', 'Job 不存在')
                return self.send_json(200, job)
            if parsed.path == '/v1/thumbnails':
                raw_path=parse_qs(parsed.query).get('path',[''])[0]; file_path=safe_download_path(raw_path)
                thumb=Path(thumbnail(file_path)); raw=thumb.read_bytes(); self.send_response(200); self.send_header('Content-Type','image/jpeg'); self.send_header('Content-Length',str(len(raw))); self.send_header('Cache-Control','public, max-age=86400'); self.end_headers(); self.wfile.write(raw); return
            if parsed.path == '/v1/files':
                raw_path = parse_qs(parsed.query).get('path', [''])[0]
                if not raw_path or raw_path.startswith(('data:', 'http://', 'https://')):
                    raise ValueError('只允许读取本地图片文件')
                file_path = safe_download_path(raw_path)
                raw = file_path.read_bytes()
                self.send_response(200)
                self.send_header('Content-Type', mimetypes.guess_type(str(file_path))[0] or 'application/octet-stream')
                self.send_header('Content-Length', str(len(raw)))
                self.send_header('Content-Disposition', f'inline; filename="{file_path.name}"')
                self.send_header('Cache-Control', 'no-store')
                self.end_headers(); self.wfile.write(raw); return
            if parsed.path == '/v1/download-zip':
                raw_result = parse_qs(parsed.query).get('result', [''])[0]
                if not raw_result: raise ValueError('缺少 result 参数')
                result_path = safe_download_path(raw_result, allow_zip=True)
                if result_path.suffix.lower() != '.zip': raise ValueError('result 必须是 ZIP 文件')
                raw = result_path.read_bytes()
                self.send_response(200)
                self.send_header('Content-Type', 'application/zip')
                self.send_header('Content-Length', str(len(raw)))
                self.send_header('Content-Disposition', f'attachment; filename="{result_path.name}"')
                self.end_headers(); self.wfile.write(raw); return
            if parsed.path == '/v1/gallery':
                params=parse_qs(parsed.query); return self.send_json(200, {'items': list_images(params.get('favorite',['0'])[0]=='1', int(params.get('limit',['50'])[0]))})
            if parsed.path == '/v1/favorites':
                return self.send_json(200, {'items': list_images(True)})
            if parsed.path == '/v1/history':
                params = parse_qs(parsed.query); limit = int(params.get('limit', ['20'])[0])
                return self.send_json(200, {'items': search_tasks(params.get('q', [''])[0], params.get('status', [''])[0], params.get('profile', [''])[0], limit)})
            return self.send_error(404, 'not_found', '接口不存在')
        except Exception as exc:
            return self.send_error(400, 'invalid_json', str(exc))

    def read_body(self):
        length = int(self.headers.get('Content-Length', '0'))
        if length < 0 or length > MAX_BODY: raise ExecutorError('请求体过大', 413)
        raw = self.rfile.read(length)
        try: return json.loads(raw.decode('utf-8')) if raw else {}
        except (UnicodeDecodeError, json.JSONDecodeError) as exc: raise ExecutorError('请求体必须是 UTF-8 JSON', 400) from exc

    def do_POST(self):
        if not self.authorized(): return self.send_error(401, 'unauthorized', '需要 Bearer Token')
        parsed = urlparse(self.path)
        try:
            payload = self.read_body()
            if parsed.path == '/v1/agent/branch':
                source=payload.get('session_path'); target=payload.get('target_path')
                if not source or not target: raise ValueError('缺少 session_path 或 target_path')
                from agent import fork_session
                return self.send_json(200, fork_session(source,target,payload.get('branch_id')))
            if parsed.path == '/v1/agent/regenerate':
                source=payload.get('session_path')
                if not source: raise ValueError('缺少 session_path')
                from agent import regenerate_session
                return self.send_json(200, regenerate_session(source,payload.get('target_path'),payload.get('round_index')))
            if parsed.path == '/v1/setup':
                return self.send_json(200, setup_from_json(payload))
            if parsed.path == '/v1/backup/import':
                archive=payload.get('path')
                if not isinstance(archive,str): raise ValueError('缺少备份文件路径')
                archive=safe_download_path(archive, allow_zip=True)
                return self.send_json(200, restore_backup(archive, bool(payload.get('apply', False)), payload.get('conflict','skip')))
            if parsed.path == '/v1/delete-images':
                ids=payload.get('image_ids') or ([payload.get('image_id')] if payload.get('image_id') else [])
                return self.send_json(200, delete_images(ids, bool(payload.get('remove_files', False))))
            if parsed.path == '/v1/favorite':
                return self.send_json(200, set_favorite(str(payload.get('image_id','')), bool(payload.get('favorite', True))))
            if parsed.path == '/v1/backup/export':
                target = make_backup()
                return self.send_json(200, {'status':'exported','path':str(target),'download_url':'/v1/download-zip?result='+str(target)})
            if parsed.path == '/v1/export-zip':
                target = make_zip(payload.get('result', payload))
                return self.send_json(200, {'status': 'exported', 'path': str(target), 'download_url': '/v1/download-zip?result=' + str(target)})
            timeout = min(max(int(payload.pop('timeout', 900)), 10), MAX_TIMEOUT)
            async_job = bool(payload.pop('async', False))
            if parsed.path == '/v1/generate':
                kind, clean = 'generate', normalize_task(payload)
            elif parsed.path == '/v1/batch':
                kind, clean = 'batch', normalize_task(payload, batch=True)
            elif parsed.path == '/v1/agent':
                if payload.get('images'):
                    payload['images'] = [validate_input_image(item) for item in payload['images']]
                kind, clean = 'agent', normalize_task(payload)
            else:
                return self.send_error(404, 'not_found', '接口不存在')
            if async_job:
                return self.send_json(202, submit_job(kind, clean, timeout))
            if kind == 'generate': result = run_generate(clean, timeout)
            elif kind == 'batch': result = run_batch(clean, timeout)
            else: result = run_agent(clean, timeout)
            return self.send_json(200, result)
        except ExecutorError as exc:
            return self.send_error(exc.status, 'executor_error', str(exc))
        except (ValueError, OSError, subprocess.TimeoutExpired) as exc:
            status = 504 if isinstance(exc, subprocess.TimeoutExpired) else 422
            return self.send_error(status, 'request_invalid' if status == 422 else 'executor_timeout', str(exc))
        except Exception as exc:
            return self.send_error(500, 'internal_error', str(exc))


def main():
    parser = argparse.ArgumentParser(description='GPT Image Playground local REST API')
    parser.add_argument('--host', default=os.environ.get('GPT_PLAYGROUND_API_HOST', '127.0.0.1'))
    parser.add_argument('--port', type=int, default=int(os.environ.get('GPT_PLAYGROUND_API_PORT', '8765')))
    parser.add_argument('--stop', action='store_true')
    args = parser.parse_args()
    if args.stop:
        pid_path = API_WORK / 'api-server.pid'
        if not pid_path.exists(): print(json.dumps({'status': 'not_running'}, ensure_ascii=False)); return
        pid = int(pid_path.read_text(encoding='utf-8'))
        try: os.kill(pid, signal.SIGTERM)
        except ProcessLookupError: pid_path.unlink(missing_ok=True)
        print(json.dumps({'status': 'stopping', 'pid': pid}, ensure_ascii=False)); return
    if args.host not in ('127.0.0.1', 'localhost', '::1') and not os.environ.get('GPT_PLAYGROUND_API_TOKEN'):
        parser.error('非 localhost 监听必须设置 GPT_PLAYGROUND_API_TOKEN')
    if not 1 <= args.port <= 65535: parser.error('port 必须在 1-65535')
    WORK.mkdir(parents=True, exist_ok=True)
    restore_jobs()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    pid_path = API_WORK / 'api-server.pid'
    API_WORK.mkdir(parents=True, exist_ok=True)
    pid_path.write_text(str(os.getpid()), encoding='utf-8')
    signal.signal(signal.SIGTERM, lambda *_: threading.Thread(target=server.shutdown, daemon=True).start())
    print(json.dumps({'status': 'listening', 'host': args.host, 'port': args.port, 'version': VERSION}, ensure_ascii=False), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt: pass
    finally:
        server.server_close()
        pid_path.unlink(missing_ok=True)

if __name__ == '__main__': main()
