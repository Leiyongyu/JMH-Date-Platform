"""图片路径管理：按 SKU 找到子文件夹，按文件名排序返回图片列表。"""
from __future__ import annotations

import os
import re
from pathlib import Path

# 支持的图片扩展名
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".tif", ".tiff"}


def _natural_key(name: str) -> list:
    """自然排序 key：1.jpg < 2.jpg < 10.jpg。"""
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", name)]


def get_sku_images(sku: str, image_root: str) -> list[str]:
    """返回某个 SKU 文件夹内排序后的图片绝对路径列表。

    目录结构预期：
        image_root/
            SKU1/
                1.jpg
                2.jpg
            SKU2/
                1.jpg

    兼容情况：如果用户误把 SKU 子文件夹本身选为根目录（如 image_root=SKU/123456），
    且该文件夹自身就是和 sku 同名的目录，则直接返回该文件夹内的图片。

    Args:
        sku: SKU 编号
        image_root: 图片根目录

    Returns:
        排序后的图片绝对路径列表；文件夹不存在则返回空列表
    """
    root = Path(image_root)
    sku_dir = root / sku

    # 标准结构：image_root/sku/
    if sku_dir.exists() and sku_dir.is_dir():
        target_dir = sku_dir
    # 兼容：用户直接选了 sku 子文件夹作为根目录
    elif root.name == sku and root.is_dir():
        target_dir = root
    else:
        return []

    images: list[str] = []
    for f in target_dir.iterdir():
        if f.is_file() and f.suffix.lower() in IMAGE_EXTS:
            images.append(str(f.resolve()))
    images.sort(key=lambda p: _natural_key(os.path.basename(p)))
    return images


def check_sku_ready(sku: str, image_root: str) -> tuple[bool, str]:
    """检查 SKU 是否准备好上传，返回 (是否就绪, 说明)。"""
    imgs = get_sku_images(sku, image_root)
    if not imgs:
        return False, f"SKU {sku} 的图片文件夹不存在或为空"
    return True, f"SKU {sku} 找到 {len(imgs)} 张图片"
