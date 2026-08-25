#!/usr/bin/env python3
"""Create a minimal runtime ZIP without source, tests, Git, or build tools."""
from pathlib import Path
import shutil, sys, tempfile, zipfile

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / 'dist' / 'gpt-image-playground-runtime.zip'
KEEP_ROOT = ('SKILL.md', 'AGENTS.md', 'README.md', 'ARCHITECTURE.md', 'requirements.txt', 'profiles.json', 'model_catalog.json', 'presets.json', 'connection.example.json')
KEEP_SCRIPTS = ('agent.py', 'api_server.py', 'connection.py', 'custom_provider.py', 'fal_provider.py', 'generate.py', 'image_ops.py', 'image_store.py', 'playground.py', 'provider_base.py', 'responses_provider.py', 'runtime_paths.py', 'skill.py', 'task_store.py', 'version.py')

def main():
    out = Path(sys.argv[1]).expanduser() if len(sys.argv) > 1 else DEFAULT_OUT
    with tempfile.TemporaryDirectory(prefix='gip-runtime-') as td:
        stage = Path(td) / 'gpt-image-playground'
        (stage / 'scripts').mkdir(parents=True)
        (stage / 'web').mkdir(parents=True)
        for name in KEEP_ROOT:
            src = ROOT / name
            if src.is_file(): shutil.copy2(src, stage / name)
        if (ROOT / 'agents').is_dir():
            shutil.copytree(ROOT / 'agents', stage / 'agents')
        for name in KEEP_SCRIPTS:
            src = ROOT / 'scripts' / name
            if src.is_file(): shutil.copy2(src, stage / 'scripts' / name)
        web = ROOT / 'web'
        if not web.is_dir() or not (web / 'index.html').is_file():
            raise SystemExit('缺少 web/index.html')
        for src in web.iterdir():
            dst = stage / 'web' / src.name
            shutil.copytree(src, dst) if src.is_dir() else shutil.copy2(src, dst)
        out.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as z:
            for path in stage.rglob('*'):
                if path.is_file(): z.write(path, path.relative_to(stage.parent))
    print(f'created {out} ({out.stat().st_size} bytes)')

if __name__ == '__main__': main()
