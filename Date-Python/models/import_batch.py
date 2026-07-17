"""导入批次表"""
from models.base import get_conn


def create_import_batch(import_type, file_name, file_path, file_hash, file_size, created_by='SYSTEM'):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO import_batch (import_type, original_file_name, stored_file_path,
            file_sha256, file_size, parse_status, created_by)
        VALUES (%s, %s, %s, %s, %s, 'PENDING', %s)
        ON DUPLICATE KEY UPDATE
            original_file_name = VALUES(original_file_name),
            stored_file_path = VALUES(stored_file_path),
            file_size = VALUES(file_size),
            parse_status = 'PENDING',
            error_message = NULL, total_count = 0, success_count = 0, error_count = 0,
            updated_by = VALUES(created_by)
    ''', (import_type, file_name, file_path, file_hash, file_size, created_by))
    batch_id = cursor.lastrowid
    if batch_id == 0:
        cursor.execute(
            'SELECT id FROM import_batch WHERE file_sha256 = %s AND import_type = %s',
            (file_hash, import_type))
        batch_id = cursor.fetchone()[0]
    conn.commit()
    cursor.close()
    conn.close()
    return batch_id


def update_import_batch(batch_id, **kwargs):
    conn = get_conn()
    cursor = conn.cursor()
    sets = ', '.join(f'{k} = %s' for k in kwargs)
    values = list(kwargs.values()) + [batch_id]
    cursor.execute(f'UPDATE import_batch SET {sets} WHERE id = %s', values)
    conn.commit()
    cursor.close()
    conn.close()


def check_duplicate_file(file_sha256, import_type):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(
        'SELECT id, parse_status FROM import_batch WHERE file_sha256 = %s AND import_type = %s',
        (file_sha256, import_type))
    row = cursor.fetchone()
    cursor.close()
    conn.close()
    return row
