"""Shared redaction and SSRF-safe image download helpers."""

import ipaddress
import os
import socket
import urllib.parse
import urllib.request


DEFAULT_MAX_IMAGE_BYTES = 25 * 1024 * 1024


class UnsafeURLError(ValueError):
    pass


def _public_ip(value):
    address = ipaddress.ip_address(value)
    return not any((address.is_private, address.is_loopback, address.is_link_local,
                    address.is_multicast, address.is_reserved, address.is_unspecified))


def validate_public_url(url, resolver=socket.getaddrinfo):
    parsed = urllib.parse.urlsplit(str(url))
    if parsed.scheme not in ('http', 'https') or not parsed.hostname:
        raise UnsafeURLError('只允许带主机名的 HTTP/HTTPS 图片 URL')
    if parsed.username or parsed.password:
        raise UnsafeURLError('图片 URL 不允许包含用户凭据')
    try:
        addresses = {item[4][0].split('%', 1)[0] for item in resolver(parsed.hostname, parsed.port or (443 if parsed.scheme == 'https' else 80), type=socket.SOCK_STREAM)}
    except socket.gaierror as exc:
        raise UnsafeURLError(f'图片主机无法解析: {parsed.hostname}') from exc
    if not addresses or any(not _public_ip(value) for value in addresses):
        raise UnsafeURLError('图片 URL 解析到本机、内网或保留地址')
    return url


class SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    def __init__(self, maximum=5):
        super().__init__()
        self.maximum = maximum
        self.count = 0

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        self.count += 1
        if self.count > self.maximum:
            raise UnsafeURLError('图片下载重定向次数过多')
        validate_public_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch_image(url, headers=None, timeout=120, max_bytes=None):
    validate_public_url(url)
    limit = int(max_bytes or os.environ.get('GPT_IMAGE_MAX_DOWNLOAD_BYTES', DEFAULT_MAX_IMAGE_BYTES))
    request = urllib.request.Request(url, headers=headers or {})
    opener = urllib.request.build_opener(SafeRedirectHandler())
    with opener.open(request, timeout=timeout) as response:
        content_type = response.headers.get_content_type() or 'application/octet-stream'
        if not (content_type.startswith('image/') or content_type == 'application/octet-stream'):
            raise UnsafeURLError(f'图片下载返回了不支持的 Content-Type: {content_type}')
        declared = response.headers.get('Content-Length')
        if declared and int(declared) > limit:
            raise UnsafeURLError(f'图片超过下载上限: {limit} bytes')
        raw = response.read(limit + 1)
        if len(raw) > limit:
            raise UnsafeURLError(f'图片超过下载上限: {limit} bytes')
        return raw, content_type


def display_url(url):
    parsed = urllib.parse.urlsplit(str(url))
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path, '', ''))


def redact(value):
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            lowered = str(key).lower()
            result[key] = '[redacted]' if any(token in lowered for token in ('api_key', 'authorization', 'cookie', 'token', 'secret')) else redact(item)
        return result
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, str):
        if value.startswith('data:'):
            return f'[data-url-redacted:{len(value)}]'
        if value.startswith(('http://', 'https://')):
            return display_url(value)
    return value
