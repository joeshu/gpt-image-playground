#!/usr/bin/env python3
import argparse
import base64
import json
import mimetypes
import os
import re
import sys
import time
import urllib.request
from pathlib import Path

try:
    import requests
except Exception:
    print("requests is required. Install with: apk add py3-requests", file=sys.stderr)
    sys.exit(2)

# Endpoint and API key are read from environment variables when available.
# This keeps provider-specific URLs and secrets out of task/config files.
ENDPOINT_DEFAULT = "https://twofishai.com/v1/images/generations"
ENDPOINT_ENV = "GPT_IMAGE_ENDPOINT"
API_KEY_ENV = "GPT_IMAGE_API_KEY"
LEGACY_API_KEY_ENV = "TWOFISHAI_API_KEY"
MODEL_DEFAULT = "gpt-image-2"
POLL_INTERVAL_DEFAULT = 3
POLL_TIMEOUT_DEFAULT = 300
CONNECT_TIMEOUT_DEFAULT = 30
REQUEST_TIMEOUT_DEFAULT = 900


def now_stamp():
    return time.strftime("%Y%m%d-%H%M%S")


def ensure_dir(path: Path):
    path.mkdir(parents=True, exist_ok=True)


def read_json(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, data):
    ensure_dir(path.parent)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


SIZE_MULTIPLE = 16
MAX_EDGE = 3840
MAX_ASPECT_RATIO = 3.0
MIN_PIXELS = 655_360
MAX_PIXELS = 8_294_400


def _floor_multiple(value, multiple=SIZE_MULTIPLE):
    return max(multiple, int(value // multiple) * multiple)


def _round_multiple(value, multiple=SIZE_MULTIPLE):
    return max(multiple, int(round(value / multiple)) * multiple)


def normalize_size(value: str) -> str:
    """Normalize ratios and dimensions to provider-safe 16px dimensions."""
    raw = (value or "").strip().lower().replace("×", "x")
    ratios = {
        "1:1": (1024, 1024), "16:9": (1536, 864), "9:16": (864, 1536),
        "4:3": (1536, 1152), "3:4": (1152, 1536), "3:2": (1536, 1024),
        "2:3": (1024, 1536), "5:4": (1280, 1024), "4:5": (1024, 1280),
        "2:1": (1536, 768), "1:2": (768, 1536), "21:9": (1792, 768),
        "9:21": (768, 1792), "1k": (1024, 1024), "2k": (1536, 1024),
        "4k": (3840, 2160), "auto": (1536, 1024),
    }
    if raw in ratios:
        width, height = ratios[raw]
    else:
        match = re.fullmatch(r"(\d+)\s*x\s*(\d+)", raw)
        if not match:
            return "1536x1024"
        width, height = map(int, match.groups())
    width, height = _round_multiple(width), _round_multiple(height)
    longest = max(width, height)
    if longest > MAX_EDGE:
        scale = MAX_EDGE / longest
        width, height = _floor_multiple(width * scale), _floor_multiple(height * scale)
    if width / height > MAX_ASPECT_RATIO:
        width = _floor_multiple(height * MAX_ASPECT_RATIO)
    elif height / width > MAX_ASPECT_RATIO:
        height = _floor_multiple(width * MAX_ASPECT_RATIO)
    pixels = width * height
    if pixels > MAX_PIXELS:
        scale = (MAX_PIXELS / pixels) ** 0.5
        width, height = _floor_multiple(width * scale), _floor_multiple(height * scale)
    elif pixels < MIN_PIXELS:
        scale = (MIN_PIXELS / pixels) ** 0.5
        width, height = _round_multiple(width * scale), _round_multiple(height * scale)
    return f"{width}x{height}"


def safe_endpoint(endpoint: str) -> str:
    endpoint = (endpoint or "").strip()
    if not endpoint:
        return ENDPOINT_DEFAULT
    if not endpoint.startswith(("http://", "https://")):
        raise ValueError("Endpoint must start with http:// or https://")
    return endpoint


def response_summary(resp):
    return {
        "status_code": resp.status_code,
        "content_type": resp.headers.get("content-type", ""),
        "content_length": resp.headers.get("content-length", ""),
        "text_preview": resp.text[:1000],
    }


def write_text(path: Path, text: str):
    ensure_dir(path.parent)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def local_file_to_data_url(path: str) -> str:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Local image not found: {path}")
    mime, _ = mimetypes.guess_type(str(p))
    if not mime:
        mime = "application/octet-stream"
    raw = p.read_bytes()
    b64 = base64.b64encode(raw).decode("ascii")
    return f"data:{mime};base64,{b64}"


def normalize_image_inputs(values):
    result = []
    for item in values or []:
        if item.startswith("http://") or item.startswith("https://") or item.startswith("data:"):
            result.append(item)
        else:
            result.append(local_file_to_data_url(item))
    return result


def save_url_image(url: str, out_path: Path, headers=None):
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=300) as resp:
        out_path.write_bytes(resp.read())


def response_items(resp_json):
    data = resp_json.get("data") if isinstance(resp_json, dict) else None
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return [data]
    # Some compatible gateways return the image object at top level.
    if isinstance(resp_json, dict) and any(k in resp_json for k in ("b64_json", "url", "image_url", "download_url")):
        return [resp_json]
    return []


def has_image_data(resp_json):
    return any(isinstance(item, dict) and any(item.get(k) for k in ("b64_json", "url", "image_url", "download_url")) for item in response_items(resp_json))


def decode_b64_images(resp_json, out_dir: Path, prefix: str, output_format="png"):
    saved = []
    data = response_items(resp_json)
    extension = "jpg" if output_format in ("jpeg", "jpg") else output_format
    for i, item in enumerate(data, start=1):
        b64 = item.get("b64_json")
        if b64:
            out_path = out_dir / f"{prefix}-{i}.{extension}"
            out_path.write_bytes(base64.b64decode(b64))
            saved.append({
                "index": i,
                "path": str(out_path),
                "source": "b64_json",
                "revised_prompt": item.get("revised_prompt")
            })
            continue
        url = item.get("url") or item.get("image_url") or item.get("download_url")
        if url:
            out_path = out_dir / f"{prefix}-{i}.{extension}"
            save_url_image(url, out_path)
            saved.append({
                "index": i,
                "path": str(out_path),
                "source": "url",
                "url": url,
                "revised_prompt": item.get("revised_prompt")
            })
    return saved


def extract_async_hint(resp_json):
    status = str(resp_json.get("status", "")).lower()
    task_id = resp_json.get("task_id") or resp_json.get("id") or resp_json.get("job_id")
    if task_id and (status in ("", "queued", "pending", "processing", "running", "submitted") or not resp_json.get("data")):
        return {"id": task_id, "status": status or "unknown"}
    return None


def candidate_poll_urls(resp_json, endpoint: str):
    urls = []
    for key in ("status_url", "poll_url", "result_url", "url"):
        v = resp_json.get(key)
        if isinstance(v, str) and v.startswith("http"):
            urls.append(v)
    task_id = resp_json.get("task_id") or resp_json.get("id") or resp_json.get("job_id")
    if task_id:
        base = endpoint.rstrip("/")
        urls.extend([
            f"{base}/{task_id}",
            f"{base}/status/{task_id}",
            f"{base}/result/{task_id}",
        ])
    dedup = []
    seen = set()
    for u in urls:
        if u not in seen:
            dedup.append(u)
            seen.add(u)
    return dedup


def build_headers(api_key: str):
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


def request_json(method: str, url: str, headers: dict, payload=None, timeout=REQUEST_TIMEOUT_DEFAULT, debug_prefix: Path | None = None):
    try:
        if method.upper() == "POST":
            r = requests.post(url, json=payload, headers=headers, timeout=(CONNECT_TIMEOUT_DEFAULT, timeout))
        else:
            r = requests.get(url, headers=headers, timeout=(CONNECT_TIMEOUT_DEFAULT, timeout))
    except requests.RequestException as e:
        if debug_prefix is not None:
            write_json(debug_prefix.parent / f"{debug_prefix.name}-error.json", {"error": str(e), "url": url})
        raise RuntimeError(f"Network request failed: {e}") from e
    if debug_prefix is not None:
        write_json(debug_prefix.parent / f"{debug_prefix.name}-meta.json", response_summary(r))
        header_text = "\n".join(f"{k}: {v}" for k, v in r.headers.items())
        write_text(debug_prefix.parent / f"{debug_prefix.name}-headers.txt", f"HTTP {r.status_code}\n{header_text}\n")
        write_text(debug_prefix.parent / f"{debug_prefix.name}-raw.txt", r.text)
    if not r.ok:
        raise RuntimeError(f"HTTP {r.status_code} from image endpoint: {r.text[:1000]}")
    try:
        return r.json()
    except ValueError as e:
        raise RuntimeError(f"Image endpoint returned non-JSON content: {r.text[:1000]}") from e


def maybe_poll(resp_json, endpoint: str, headers: dict, poll_interval: int, poll_timeout: int, workspace_dir: Path, prefix: str):
    hint = extract_async_hint(resp_json)
    if not hint:
        return resp_json, None
    poll_urls = candidate_poll_urls(resp_json, endpoint)
    if not poll_urls:
        return None, {
            "async_detected": True,
            "message": "Detected async-style response, but no poll URL could be inferred.",
            "task": hint,
        }
    deadline = time.time() + poll_timeout
    last = resp_json
    errors = []
    round_num = 0
    while time.time() < deadline:
        time.sleep(poll_interval)
        round_num += 1
        for idx, poll_url in enumerate(poll_urls, start=1):
            try:
                polled = request_json(
                    "GET",
                    poll_url,
                    headers=headers,
                    timeout=max(60, poll_interval + 20),
                    debug_prefix=workspace_dir / f"{prefix}-poll-{round_num}-{idx}"
                )
                last = polled
                if has_image_data(polled):
                    return polled, None
                status = str(polled.get("status", "")).lower()
                if status in ("failed", "error", "cancelled"):
                    return polled, {"async_detected": True, "message": f"Async task ended with status: {status}", "task": hint, "poll_urls": poll_urls}
            except Exception as e:
                errors.append(f"{poll_url}: {e}")
                continue
    return last, {"async_detected": True, "message": "Polling timed out before image data became available.", "task": hint, "poll_urls": poll_urls, "errors": errors[-10:]}


def main():
    global REQUEST_TIMEOUT_DEFAULT, CONNECT_TIMEOUT_DEFAULT
    parser = argparse.ArgumentParser(description="Generate images via GPT Image style API")
    parser.add_argument("--prompt")
    parser.add_argument("--size", default="1:1")
    parser.add_argument("--n", type=int, default=1)
    parser.add_argument("--model", default=MODEL_DEFAULT)
    parser.add_argument("--background", choices=("auto", "transparent", "opaque"))
    parser.add_argument("--moderation", choices=("auto", "low", "medium", "high"))
    parser.add_argument("--output-compression", type=int)
    parser.add_argument("--endpoint", default=ENDPOINT_DEFAULT)
    parser.add_argument("--image", action="append", default=[])
    parser.add_argument("--config")
    parser.add_argument("--task")
    parser.add_argument("--out-prefix", default="gpt-image-2")
    parser.add_argument("--attachments-dir", default="/var/minis/attachments/gpt-image-tool")
    parser.add_argument("--workspace-dir", default="/var/minis/workspace/gpt-image-tool")
    parser.add_argument("--poll-interval", type=int, default=POLL_INTERVAL_DEFAULT)
    parser.add_argument("--poll-timeout", type=int, default=POLL_TIMEOUT_DEFAULT)
    parser.add_argument("--request-timeout", type=int, default=REQUEST_TIMEOUT_DEFAULT)
    parser.add_argument("--connect-timeout", type=int, default=CONNECT_TIMEOUT_DEFAULT)
    parser.add_argument("--dry-run", action="store_true", help="只生成脱敏请求，不调用接口")
    args = parser.parse_args()

    # Allow per-run timeout tuning without changing the script constants.
    REQUEST_TIMEOUT_DEFAULT = max(30, args.request_timeout)
    CONNECT_TIMEOUT_DEFAULT = max(5, args.connect_timeout)

    config = {}
    if args.config:
        config = read_json(args.config)
    task = {}
    if args.task:
        task = read_json(args.task)

    prompt = task.get("prompt") or args.prompt or config.get("prompt")
    if not prompt:
        print("Missing prompt. Use --prompt or --task/--config.", file=sys.stderr)
        sys.exit(2)

    # Priority: task/config override, then environment endpoint; key is never read from files.
    api_key = os.environ.get(API_KEY_ENV) or os.environ.get(LEGACY_API_KEY_ENV)
    if not api_key:
        print(f"Missing {API_KEY_ENV} (legacy fallback: {LEGACY_API_KEY_ENV})", file=sys.stderr)
        sys.exit(3)

    endpoint = safe_endpoint(task.get("endpoint") or config.get("endpoint") or os.environ.get(ENDPOINT_ENV) or args.endpoint)
    if endpoint.rstrip("/").endswith("2api.aiwanwu.cc"):
        endpoint = endpoint.rstrip("/") + "/v1/images/generations"
    omit_model = bool(task.get("omit_model") or config.get("omit_model"))
    model = None if omit_model else (task.get("model") or config.get("model") or args.model)
    size = normalize_size(task.get("size") or args.size or config.get("size") or "16:9")
    n = task.get("n") or args.n or config.get("n") or 1
    image_values = task.get("image_urls") or task.get("images") or args.image or config.get("image_urls") or []
    normalized_images = normalize_image_inputs(image_values)
    mask_value = task.get("mask") or config.get("mask")
    normalized_mask = normalize_image_inputs([mask_value])[0] if mask_value else None

    quality = task.get("quality") or config.get("quality") or "low"
    output_format = task.get("output_format") or config.get("output_format") or "png"
    payload = {
        "prompt": prompt,
        "n": max(1, min(int(n), 10)),
        "size": size,
        "quality": quality,
        "output_format": output_format,
    }
    for key in ("background", "moderation", "output_compression"):
        value = task.get(key) if task.get(key) is not None else config.get(key)
        if value is None:
            value = getattr(args, key.replace("output_compression", "output_compression"), None)
        if value is not None:
            payload[key] = value
    if model is not None:
        payload["model"] = model
    if normalized_images:
        payload["image_urls"] = normalized_images
    if normalized_mask:
        payload["mask"] = normalized_mask

    headers = build_headers(api_key)
    stamp = now_stamp()
    prefix = f"{args.out_prefix}-{stamp}"
    workspace_dir = Path(args.workspace_dir)
    attachments_dir = Path(args.attachments_dir)
    ensure_dir(workspace_dir)
    ensure_dir(attachments_dir)

    request_path = workspace_dir / f"{prefix}-request.json"
    initial_response_path = workspace_dir / f"{prefix}-initial-response.json"
    response_path = workspace_dir / f"{prefix}-response.json"
    summary_path = workspace_dir / f"{prefix}-summary.json"
    write_json(request_path, {**payload, "endpoint": endpoint, "api_key_source": API_KEY_ENV if os.environ.get(API_KEY_ENV) else LEGACY_API_KEY_ENV, "timeouts": {"connect": CONNECT_TIMEOUT_DEFAULT, "read": REQUEST_TIMEOUT_DEFAULT}})
    if args.dry_run:
        print(json.dumps({"request_file": str(request_path), "endpoint": endpoint, "model": model, "omit_model": omit_model, "size": size}, ensure_ascii=False, indent=2))
        return

    try:
        resp_json = request_json(
            "POST",
            endpoint,
            headers=headers,
            payload=payload,
            timeout=REQUEST_TIMEOUT_DEFAULT,
            debug_prefix=workspace_dir / f"{prefix}-post"
        )
        write_json(initial_response_path, resp_json)
    except Exception as e:
        err = {"error": str(e), "endpoint": endpoint, "model": model, "size": size,
               "payload_preview": {k: v for k, v in payload.items() if k != "image_urls"}}
        write_json(summary_path, err)
        print(json.dumps(err, ensure_ascii=False, indent=2), file=sys.stderr)
        sys.exit(4)

    final_json, async_note = maybe_poll(resp_json, endpoint, headers, args.poll_interval, args.poll_timeout, workspace_dir, prefix)
    if final_json is None:
        final_json = resp_json
    write_json(response_path, final_json)
    saved_images = decode_b64_images(final_json, attachments_dir, prefix, payload.get("output_format", "png"))

    summary = {
        "endpoint": endpoint,
        "model": model,
        "omit_model": omit_model,
        "size": size,
        "n": n,
        "has_input_images": bool(normalized_images),
        "request_file": str(request_path),
        "initial_response_file": str(initial_response_path),
        "response_file": str(response_path),
        "saved_images": saved_images,
        "async_note": async_note,
    }
    write_json(summary_path, summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
