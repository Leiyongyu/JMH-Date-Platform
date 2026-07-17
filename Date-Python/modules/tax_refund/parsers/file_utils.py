"""文件处理服务"""
import os
import hashlib
import json
import re
import shutil
from datetime import datetime
from config import UPLOAD_FOLDER


def save_upload(file):
    """保存上传文件，返回 (saved_path, original_name, file_size)"""
    original_name = file.filename  # 保留原始文件名（含中文）
    saved_path = _upload_path(original_name)
    file.save(saved_path)
    return saved_path, original_name, os.path.getsize(saved_path)


def save_upload_stream(original_name, stream):
    """保存 FastAPI/Starlette 上传流，返回值与 save_upload 一致。"""
    saved_path = _upload_path(original_name)
    stream.seek(0)
    with open(saved_path, 'wb') as target:
        shutil.copyfileobj(stream, target)
    return saved_path, original_name, os.path.getsize(saved_path)


def _upload_path(original_name):
    base_name = os.path.basename(str(original_name).replace('\\', '/'))
    safe_name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', base_name).strip().rstrip('.')
    if not safe_name:
        _, ext = os.path.splitext(base_name)
        safe_name = f'upload{ext}' if ext else 'upload'
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    saved_name = f'{timestamp}_{safe_name}'
    saved_path = os.path.join(UPLOAD_FOLDER, saved_name)
    return saved_path


def compute_sha256(file_path):
    """计算文件SHA-256"""
    sha = hashlib.sha256()
    with open(file_path, 'rb') as f:
        while True:
            chunk = f.read(8192)
            if not chunk: break
            sha.update(chunk)
    return sha.hexdigest()


def save_preview_data(batch_id, data):
    """暂存预览数据到JSON文件"""
    preview_dir = os.path.join(UPLOAD_FOLDER, '.preview')
    os.makedirs(preview_dir, exist_ok=True)
    with open(os.path.join(preview_dir, f'{batch_id}.json'), 'w', encoding='utf-8') as f:
        json.dump(data, f, default=str, ensure_ascii=False)


def load_preview_data(batch_id):
    """读取预览数据"""
    path = os.path.join(UPLOAD_FOLDER, '.preview', f'{batch_id}.json')
    if not os.path.exists(path):
        return None
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def clean_preview_data(batch_id):
    """清理预览数据"""
    path = os.path.join(UPLOAD_FOLDER, '.preview', f'{batch_id}.json')
    if os.path.exists(path):
        os.remove(path)
