#!/usr/bin/env python3
"""Small ImageMagick-backed image helpers for the Playground skill."""
import re
import subprocess
from pathlib import Path

DEFAULT_MAX_EDGE = 1920
DEFAULT_MULTIPLE = 16


def _run(args):
    return subprocess.run(args, text=True, capture_output=True, check=True)


def dimensions(path):
    p = Path(path)
    if not p.is_file():
        raise ValueError(f'图片不存在: {path}')
    try:
        out = _run(['identify', '-format', '%w %h', str(p)]).stdout.strip()
        width, height = map(int, out.split()[:2])
    except (OSError, subprocess.CalledProcessError, ValueError) as exc:
        raise ValueError(f'无法读取图片尺寸: {path}') from exc
    if width < 1 or height < 1:
        raise ValueError(f'图片尺寸无效: {path}')
    return width, height


def _floor_multiple(value, multiple):
    return max(multiple, (value // multiple) * multiple)


def working_size(width, height, max_edge=DEFAULT_MAX_EDGE, multiple=DEFAULT_MULTIPLE):
    longest = max(width, height)
    if longest <= max_edge:
        return width, height
    scale = max_edge / longest
    return _floor_multiple(round(width * scale), multiple), _floor_multiple(round(height * scale), multiple)


def convert_png(source, output, width=None, height=None):
    args = ['convert', str(source)]
    if width and height:
        args += ['-resize', f'{width}x{height}!']
    args += ['-strip', 'PNG32:' + str(output)]
    try:
        _run(args)
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ValueError(f'图片 PNG 预处理失败: {source}') from exc
    return Path(output)


def prepare_mask_target(source, mask, output_dir, max_edge=DEFAULT_MAX_EDGE):
    """Normalize source and mask to matching PNG dimensions.

    The mask is intentionally not semantically inverted: providers differ on
    whether transparent or opaque pixels are editable. The caller must follow
    the provider's documented convention.
    """
    source_w, source_h = dimensions(source)
    mask_w, mask_h = dimensions(mask)
    if source_w != mask_w or source_h != mask_h:
        raise ValueError(f'遮罩尺寸必须与主图一致: 主图 {source_w}x{source_h}，遮罩 {mask_w}x{mask_h}')
    width, height = working_size(source_w, source_h, max_edge)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    target_path = out / 'mask-target.png'
    mask_path = out / 'mask.png'
    convert_png(source, target_path, width, height)
    convert_png(mask, mask_path, width, height)
    return str(target_path), str(mask_path), {'original_size': [source_w, source_h], 'working_size': [width, height]}


def remove_background(source, output, color='#00ff00', fuzz='12%'):
    """Remove a chroma background; deliberately explicit and lossy by design."""
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    try:
        _run(['convert', str(source), '-alpha', 'on', '-fuzz', str(fuzz), '-transparent', str(color), str(output)])
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ValueError(f'透明背景后处理失败: {source}') from exc
    return str(output)
