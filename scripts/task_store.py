#!/usr/bin/env python3
"""SQLite task index for CLI, API and Web history."""
import json
import sqlite3
import time
from pathlib import Path

try:
    from runtime_paths import data_root
except ImportError:
    from scripts.runtime_paths import data_root

WORK = data_root()
DB = WORK / 'tasks.sqlite3'
_LEGACY_MIGRATED = False


def connect(path=DB):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(str(path), timeout=10)
    db.row_factory = sqlite3.Row
    db.execute('''CREATE TABLE IF NOT EXISTS tasks (
        task_id TEXT PRIMARY KEY, parent_task_id TEXT, created_at TEXT,
        status TEXT, prompt TEXT, profile TEXT, model TEXT, size TEXT,
        provider TEXT, result_json TEXT NOT NULL
    )''')
    db.execute('CREATE INDEX IF NOT EXISTS idx_tasks_created ON tasks(created_at DESC)')
    db.execute('CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status)')
    db.commit()
    return db


def get(task_id, path=DB):
    with connect(path) as db:
        row=db.execute('SELECT result_json FROM tasks WHERE task_id=?',(str(task_id),)).fetchone()
    return json.loads(row['result_json']) if row else None


def record(entry, path=DB):
    if not isinstance(entry, dict) or not entry.get('task_id'): return
    with connect(path) as db:
        db.execute('''INSERT INTO tasks(task_id,parent_task_id,created_at,status,prompt,profile,model,size,provider,result_json)
            VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(task_id) DO UPDATE SET
            status=excluded.status, result_json=excluded.result_json''', (
            entry.get('task_id'), entry.get('parent_task_id'), entry.get('created_at'),
            entry.get('status'), entry.get('prompt'), entry.get('profile'), entry.get('model'),
            entry.get('size'), entry.get('provider'), json.dumps(entry, ensure_ascii=False)))
        db.commit()


def upsert(entry, path=DB, conflict='replace'):
    if not isinstance(entry,dict) or not entry.get('task_id'): return 'ignored'
    existing=get(entry['task_id'],path)
    if existing and conflict=='fail': raise ValueError(f'任务已存在: {entry["task_id"]}')
    if existing and conflict=='skip': return 'skipped'
    record(entry,path); return 'replaced' if existing else 'inserted'


def migrate_legacy(path=DB):
    global _LEGACY_MIGRATED
    if _LEGACY_MIGRATED: return
    _LEGACY_MIGRATED = True
    legacy = Path(path).parent / 'history.jsonl'
    if not legacy.exists(): return
    try:
        for line in legacy.read_text(encoding='utf-8').splitlines():
            try: record(json.loads(line), path)
            except (ValueError, json.JSONDecodeError): pass
    except OSError: pass


def search(query='', status='', profile='', limit=20, path=DB):
    migrate_legacy(path)
    limit = max(1, min(int(limit), 200))
    clauses, args = [], []
    if query:
        clauses.append('(prompt LIKE ? OR task_id LIKE ?)'); args += [f'%{query}%', f'%{query}%']
    if status: clauses.append('status=?'); args.append(status)
    if profile: clauses.append('profile=?'); args.append(profile)
    where = (' WHERE ' + ' AND '.join(clauses)) if clauses else ''
    with connect(path) as db:
        rows = db.execute('SELECT result_json FROM tasks' + where + ' ORDER BY created_at DESC LIMIT ?', args + [limit]).fetchall()
    return [json.loads(row['result_json']) for row in rows]
