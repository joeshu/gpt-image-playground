#!/usr/bin/env python3
"""Canonical task contract regression tests."""

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))

from task_schema import SCHEMA_VERSION, TaskValidationError, normalize_task


def fails(value, field):
    try:
        normalize_task(value)
    except TaskValidationError as exc:
        assert exc.field == field
        return
    raise AssertionError(f'expected {field} validation error')


def main():
    value = normalize_task({'prompt': '  poster  ', 'n': '2', 'quality': 'high', 'endpoint': 'https://evil', 'api_key': 'secret'})
    assert value['schema_version'] == SCHEMA_VERSION == 1
    assert value['prompt'] == 'poster' and value['n'] == 2
    assert 'endpoint' not in value and 'api_key' not in value
    fails({}, 'prompt')
    fails({'prompt': 'x', 'n': 17}, 'n')
    fails({'prompt': 'x', 'quality': 'ultra'}, 'quality')
    batch = normalize_task({'tasks': [{'prompt': 'a'}, {'prompt': 'b'}]}, batch=True)
    assert all(item['schema_version'] == 1 for item in batch['tasks'])
    print('task_schema_tests=ok')


if __name__ == '__main__':
    main()
