#!/usr/bin/env python3
"""Security regression tests that never access the network."""

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))

import security


def resolver(address):
    return lambda *_args, **_kwargs: [(2, 1, 6, '', (address, 443))]


def rejected(url, address='8.8.8.8'):
    try:
        security.validate_public_url(url, resolver=resolver(address))
    except security.UnsafeURLError:
        return True
    return False


def main():
    assert security.validate_public_url('https://images.example/path.png', resolver=resolver('8.8.8.8'))
    assert rejected('http://127.0.0.1/image.png', '127.0.0.1')
    assert rejected('http://169.254.169.254/latest/meta-data', '169.254.169.254')
    assert rejected('https://user:pass@example.com/image.png')
    assert rejected('file:///etc/passwd')
    assert security.display_url('https://cdn.example/a.png?token=secret#x') == 'https://cdn.example/a.png'
    value = security.redact({
        'api_key': 'secret',
        'image': 'data:image/png;base64,U0VDUkVU',
        'url': 'https://cdn.example/a.png?token=secret',
        'nested': [{'authorization': 'Bearer secret'}],
    })
    assert value['api_key'] == '[redacted]'
    assert 'U0VDUkVU' not in value['image']
    assert value['url'] == 'https://cdn.example/a.png'
    assert value['nested'][0]['authorization'] == '[redacted]'
    print('security_tests=ok')


if __name__ == '__main__':
    main()
