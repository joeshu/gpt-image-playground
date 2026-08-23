#!/usr/bin/env python3
"""Image index and favorites built on the task store database."""
import hashlib
import json
import sqlite3
import time
from pathlib import Path
from task_store import DB, connect


def init(db=DB):
    with connect(db) as cx:
        cx.execute('''CREATE TABLE IF NOT EXISTS images (
            image_id TEXT PRIMARY KEY, task_id TEXT, path TEXT, sha256 TEXT UNIQUE,
            mime TEXT, created_at TEXT, favorite INTEGER DEFAULT 0, metadata_json TEXT
        )''')
        cx.execute('CREATE INDEX IF NOT EXISTS idx_images_created ON images(created_at DESC)')
        cx.execute('CREATE INDEX IF NOT EXISTS idx_images_favorite ON images(favorite)')
        cx.commit()


def index_result(result, db=DB):
    init(db); count = 0
    def walk(value, task_id=''):
        nonlocal count
        if isinstance(value, dict):
            path = value.get('path') or value.get('file')
            if isinstance(path, str) and Path(path).is_file() and Path(path).suffix.lower() in ('.png','.jpg','.jpeg','.webp','.gif'):
                raw = Path(path).read_bytes(); digest = hashlib.sha256(raw).hexdigest(); image_id = value.get('id') or digest[:20]
                with connect(db) as cx:
                    cx.execute('''INSERT INTO images(image_id,task_id,path,sha256,mime,created_at,metadata_json)
                        VALUES(?,?,?,?,?,?,?) ON CONFLICT(sha256) DO UPDATE SET path=excluded.path,metadata_json=excluded.metadata_json''',
                        (image_id, task_id, path, digest, 'image/'+Path(path).suffix[1:], time.strftime('%Y-%m-%dT%H:%M:%S%z'), json.dumps(value,ensure_ascii=False)))
                    cx.commit()
                count += 1
            for child in value.values(): walk(child, task_id)
        elif isinstance(value, list):
            for child in value: walk(child, task_id)
    walk(result, result.get('task_id','') if isinstance(result,dict) else '')
    return count


def list_images(favorite=False, limit=50, db=DB):
    init(db); limit=max(1,min(int(limit),200))
    with connect(db) as cx:
        rows=cx.execute('SELECT * FROM images'+(' WHERE favorite=1' if favorite else '')+' ORDER BY created_at DESC LIMIT ?', (limit,)).fetchall()
    return [dict(row) for row in rows]


def delete_images(image_ids, remove_files=False, db=DB):
    init(db); ids=[str(x) for x in image_ids if x]
    removed=[]
    with connect(db) as cx:
        rows=cx.execute('SELECT image_id,path FROM images WHERE image_id IN (%s)' % ','.join('?'*len(ids)), ids).fetchall() if ids else []
        for row in rows:
            if remove_files:
                path=Path(row['path'])
                try: path.unlink(missing_ok=True)
                except OSError: pass
            removed.append(row['image_id'])
        if ids: cx.execute('DELETE FROM images WHERE image_id IN (%s)' % ','.join('?'*len(ids)), ids)
        cx.commit()
    return {'deleted': removed, 'count': len(removed), 'files_removed': bool(remove_files)}


def set_favorite(image_id, favorite=True, db=DB):
    init(db)
    with connect(db) as cx:
        cx.execute('UPDATE images SET favorite=? WHERE image_id=?',(1 if favorite else 0,image_id)); cx.commit()
    return {'image_id':image_id,'favorite':bool(favorite)}
