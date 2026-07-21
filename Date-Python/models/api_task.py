"""统一 RESTful 任务资源的数据访问。"""

import json

from models.base import get_conn


def _json_dump(value):
    return json.dumps(value, ensure_ascii=False, default=str) if value is not None else None


def _json_load(value):
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def _normalize(row):
    if not row:
        return row
    row['request_payload'] = _json_load(row.get('request_payload'))
    row['result_payload'] = _json_load(row.get('result_payload'))
    return row


def create_task(task_type, request_payload=None, original_file_name=None,
                stored_file_path=None, file_sha256=None, created_by='ERP',
                operator_id=None, operator_name=None, idempotency_key=None):
    conn = get_conn()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT INTO api_task (
                task_type, task_status, request_payload,
                original_file_name, stored_file_path, file_sha256, created_by,
                operator_id, operator_name, idempotency_key
            ) VALUES (%s, 'PENDING', %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE id=LAST_INSERT_ID(id)
        ''', (
            task_type, _json_dump(request_payload), original_file_name,
            stored_file_path, file_sha256, created_by,
            operator_id or created_by, operator_name or created_by, idempotency_key,
        ))
        task_id = cursor.lastrowid
        conn.commit()
        return task_id
    finally:
        cursor.close()
        conn.close()


def mark_task_running(task_id):
    _update_task(task_id, """
        task_status='RUNNING', started_at=NOW(3), completed_at=NULL,
        error_message=NULL
    """)


def mark_task_success(task_id, result_payload, status='SUCCESS'):
    if status not in ('SUCCESS', 'PARTIAL'):
        raise ValueError('成功任务状态只能是 SUCCESS 或 PARTIAL')
    _update_task(
        task_id,
        """
        task_status=%s, result_payload=%s, error_message=NULL,
        progress_current=progress_total, completed_at=NOW(3)
        """,
        (status, _json_dump(result_payload)),
    )


def mark_task_failed(task_id, error_message, result_payload=None):
    _update_task(
        task_id,
        """
        task_status='FAILED', result_payload=%s, error_message=%s,
        completed_at=NOW(3)
        """,
        (_json_dump(result_payload), str(error_message)[:10000]),
    )


def update_task_progress(task_id, current, total):
    _update_task(
        task_id,
        'progress_current=%s, progress_total=%s',
        (max(0, int(current)), max(0, int(total))),
    )


def _update_task(task_id, assignments, params=()):
    conn = get_conn()
    cursor = conn.cursor()
    try:
        cursor.execute(
            f'UPDATE api_task SET {assignments} WHERE id=%s',
            tuple(params) + (task_id,),
        )
        conn.commit()
    finally:
        cursor.close()
        conn.close()


def get_task(task_id):
    conn = get_conn()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute('SELECT * FROM api_task WHERE id=%s', (task_id,))
        return _normalize(cursor.fetchone())
    finally:
        cursor.close()
        conn.close()


def list_tasks(page=1, page_size=20, task_type=None, task_status=None):
    clauses = ['1=1']
    params = []
    if task_type:
        clauses.append('task_type=%s')
        params.append(task_type)
    if task_status:
        clauses.append('task_status=%s')
        params.append(task_status)
    where = ' AND '.join(clauses)
    offset = (page - 1) * page_size
    conn = get_conn()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            f'SELECT * FROM api_task WHERE {where} '
            'ORDER BY id DESC LIMIT %s OFFSET %s',
            params + [page_size, offset],
        )
        rows = [_normalize(row) for row in cursor.fetchall()]
        cursor.execute(f'SELECT COUNT(*) AS cnt FROM api_task WHERE {where}', params)
        return rows, cursor.fetchone()['cnt']
    finally:
        cursor.close()
        conn.close()
