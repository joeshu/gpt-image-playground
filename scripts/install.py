#!/usr/bin/env python3
"""Install the lightweight HTML skill runtime for another Agent/environment."""
from pathlib import Path
import argparse, io, json, os, shutil, tarfile, tempfile, time, urllib.request

DEFAULT_REPO = 'joeshu/gpt-image-playground'


def safe_extract(archive, destination):
    root = destination.resolve()
    for member in archive.getmembers():
        target = (destination / member.name).resolve()
        if root != target and root not in target.parents:
            raise RuntimeError(f'安装包包含不安全路径: {member.name}')
        if member.issym() or member.islnk() or member.isdev():
            raise RuntimeError(f'安装包包含不支持的链接或设备文件: {member.name}')
    archive.extractall(destination)

def main():
    p = argparse.ArgumentParser(description='Install prebuilt GPT Image Playground skill')
    p.add_argument('--target', default=os.environ.get('SKILL_ROOT', str(Path.home() / '.skills' / 'gpt-image-playground')))
    p.add_argument('--repo', default=os.environ.get('GPT_IMAGE_PLAYGROUND_REPO', DEFAULT_REPO))
    p.add_argument('--ref', default=os.environ.get('GPT_IMAGE_PLAYGROUND_REF', 'main'))
    p.add_argument('--token-env', default='GITHUB_TOKEN')
    args = p.parse_args()
    token = os.environ.get(args.token_env, '')
    url = f'https://codeload.github.com/{args.repo}/tar.gz/refs/heads/{args.ref}'
    request = urllib.request.Request(url, headers={'User-Agent': 'gpt-image-playground-installer', **({'Authorization': f'Bearer {token}'} if token else {})})
    payload = None
    last_error = None
    for attempt in range(4):
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                payload = response.read()
            break
        except (OSError, TimeoutError) as exc:
            last_error = exc
            if attempt < 3: time.sleep(2 ** attempt)
    if payload is None: raise RuntimeError(f'下载技能包失败：{last_error}')
    target = Path(args.target).expanduser().resolve()
    with tempfile.TemporaryDirectory(prefix='gip-install-') as td:
        stage = Path(td) / 'stage'; stage.mkdir()
        with tarfile.open(fileobj=io.BytesIO(payload), mode='r:gz') as archive:
            safe_extract(archive, stage)
        roots = [x for x in stage.iterdir() if x.is_dir()]
        if len(roots) != 1: raise RuntimeError('下载包结构无效')
        source = roots[0]
        required = ('SKILL.md', 'scripts/skill.py', 'web/index.html')
        missing = [item for item in required if not (source / item).is_file()]
        if missing: raise RuntimeError('发布包缺少技能文件: ' + ', '.join(missing))
        if target.exists(): shutil.rmtree(target)
        shutil.copytree(source, target, ignore=shutil.ignore_patterns('.git', 'tests', 'node_modules', '__pycache__'))
        for name in ('src', 'package.json', 'package-lock.json', 'tsconfig.json', 'vite.config.ts', 'tailwind.config.js', 'postcss.config.js'):
            path = target / 'web-react' / name
            if path.is_dir(): shutil.rmtree(path)
            elif path.exists(): path.unlink()
    result = {'status': 'installed', 'name': 'gpt-image-playground', 'root': str(target), 'web': str(target / 'web'), 'next': f'cd {target} && python3 scripts/skill.py check'}
    print(json.dumps(result, ensure_ascii=False, indent=2))

if __name__ == '__main__': main()
