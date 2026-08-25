#!/usr/bin/env python3
"""Installed-skill, quota-free regression matrix.

This suite intentionally uses dry-run and local fixtures only. It must not
send requests to a real image Provider.
"""
import argparse
import base64, json, os, subprocess, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable

def run(*args, expect=0):
    p = subprocess.run(args, cwd=ROOT, text=True, capture_output=True)
    if p.returncode != expect:
        raise AssertionError(f"{args}: rc={p.returncode}\nstdout={p.stdout[-1000:]}\nstderr={p.stderr[-1000:]}")
    return json.loads(p.stdout) if p.stdout.strip().startswith(('{','[')) else p.stdout

def check(cond, msg):
    if not cond: raise AssertionError(msg)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--real', action='store_true', help='显式允许真实 Provider 探测；默认不联网')
    parser.add_argument('--profile', default='default')
    args = parser.parse_args()
    cases = []
    def case(name, fn):
        fn(); cases.append(name)

    case('manifest_check', lambda: check(run(PY, 'scripts/skill.py', 'check')['status'] == 'ready', 'manifest'))
    case('doctor_check', lambda: check(run(PY, 'scripts/skill.py', 'doctor')['status'] == 'ready', 'doctor'))
    def capability_shape():
        sys.path.insert(0, str(ROOT / 'scripts'))
        import api_server as api
        value = api.capabilities_for('default')
        check('transparent_background' in value['native'], 'transparent capability')
        check(value['native']['transparent_background'] in ('unknown', 'available', 'unavailable'), 'capability state')
        check(value['probe_required'] is True, 'probe gate')
    case('capability_granularity', capability_shape)
    if args.real:
        check(os.environ.get('GPT_IMAGE_API_KEY'), '--real requires GPT_IMAGE_API_KEY')
        def real_probe():
            result = run(PY, 'scripts/playground.py', '--profile', args.profile,
                         '--prompt', 'Darwin capability probe: a simple blue glass sphere on a plain background',
                         '--execution-mode', 'native', '--quality', 'low', '--n', '1')
            check(result.get('status') == 'completed', 'real provider probe')
            check(result.get('saved_images'), 'real provider image')
        case('real_provider_probe', real_probe)
    case('single_native_dry_run', lambda: check(run(PY, 'scripts/playground.py', '--prompt', 'fixture', '--dry-run', '--execution-mode', 'native')['execution_mode'] == 'native', 'native dry run'))
    case('single_script_dry_run', lambda: check(run(PY, 'scripts/playground.py', '--prompt', 'fixture', '--dry-run', '--execution-mode', 'script')['execution_mode'] == 'script', 'script dry run'))
    case('single_auto_dry_run', lambda: check(run(PY, 'scripts/playground.py', '--prompt', 'fixture', '--dry-run', '--execution-mode', 'auto')['execution_mode'] == 'auto', 'auto dry run'))
    case('parameter_normalization', lambda: check(run(PY, 'scripts/playground.py', '--prompt', 'fixture', '--size', '4:5', '--quality', 'high', '--n', '2', '--dry-run')['requested_params']['size'] == '4:5', 'params'))
    case('batch_dry_run', lambda: check(run(PY, 'scripts/playground.py', '--batch', 'tests/batch.fixture.json', '--dry-run')['total'] >= 1, 'batch'))
    case('agent_native_dry_run', lambda: check(run(PY, 'scripts/agent.py', '--prompt', 'fixture', '--dry-run', '--execution-mode', 'native')['status'] == 'dry_run', 'agent native'))
    case('agent_script_dry_run', lambda: check(run(PY, 'scripts/agent.py', '--prompt', 'fixture', '--dry-run', '--execution-mode', 'script')['status'] == 'dry_run', 'agent script'))

    def local_inputs():
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); image = root / 'input.png'; mask = root / 'mask.png'
            image.write_bytes(b'PNG-FIXTURE'); mask.write_bytes(b'MASK-FIXTURE')
            sys.path.insert(0, str(ROOT / 'scripts'))
            import api_server as api
            old = api.ALLOWED_ROOTS; api.ALLOWED_ROOTS = (*old, root.resolve())
            try:
                task = api.normalize_task({'prompt':'edit', 'images':[str(image)], 'mask':str(mask)}, batch=False)
                check(task['images'] == [str(image)], 'local image validation')
                try: api.validate_input_image('https://example.com/image.png')
                except ValueError: pass
                else: raise AssertionError('remote image accepted')
            finally: api.ALLOWED_ROOTS = old
    case('local_image_and_mask_validation', local_inputs)

    def provider_dry_run():
        sys.path.insert(0, str(ROOT / 'scripts'))
        from provider_base import NativeImagesProvider, ProviderContext
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); ctx = ProviderContext({'prompt':'edit','endpoint':'https://example.test/v1/images/generations','images':['data:image/png;base64,UE5H'],'mask':'data:image/png;base64,TUFTSw=='}, root/'task.json', root/'out', root/'work', True, 'fixture')
            result = json.loads(NativeImagesProvider(ROOT/'scripts').run(ctx, {}))
            request = json.loads(Path(result['request_file']).read_text())
            check(request['request_type'] == 'multipart', 'multipart route')
            check(request['endpoint'].endswith('/images/edits'), 'edit endpoint')
            check('UE5H' not in json.dumps(request) and 'TUFTSw==' not in json.dumps(request), 'request artifact redaction')
    case('native_edit_mask_dry_run', provider_dry_run)

    def idempotency():
        sys.path.insert(0, str(ROOT / 'scripts'))
        import api_server as api
        with tempfile.TemporaryDirectory() as td:
            old = api.API_WORK; api.API_WORK = Path(td)
            try:
                api.save_idempotent('matrix-1', {'status':200,'body':{'ok':True}})
                check(api.load_idempotent('matrix-1')['body']['ok'], 'idempotent load')
                check(api.idempotency_file('matrix-1').name == 'matrix-1.json', 'safe key')
            finally: api.API_WORK = old
    case('idempotency_storage', idempotency)

    def redaction():
        sys.path.insert(0, str(ROOT / 'scripts'))
        import api_server as api
        text = json.dumps(api.safe_json({'image':'data:image/png;base64,AAAA'}))
        check('AAAA' not in text and 'data:image' not in text, 'data URL redaction')
        check('api_key' not in api.normalize_task({'prompt':'x','api_key':'secret'}), 'task key removal')
    case('secret_and_data_url_redaction', redaction)

    print(json.dumps({'status':'ok','cases':len(cases),'passed':cases}, ensure_ascii=False, indent=2))

if __name__ == '__main__': main()
