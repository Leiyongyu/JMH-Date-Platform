"""Sanitized health reports only; never persist credentials or GetUser raw XML."""
import json

from backend.database import db_connection


def baselines():
    with db_connection() as connection, connection.cursor() as cursor:
        cursor.execute('SELECT browser_id,seller_account,listing_count FROM ebay_token_health_state')
        return {row['browser_id']: row for row in cursor.fetchall()}


def save_report(report):
    with db_connection() as connection:
        try:
            connection.begin()
            with connection.cursor() as cursor:
                cursor.execute('INSERT INTO ebay_token_health_run (run_id,checked_at,account_count,report_json) VALUES (%s,%s,%s,%s)',
                    (report['sync_batch_id'], report['checked_at'], len(report['accounts']),
                     json.dumps(report, ensure_ascii=False, allow_nan=False)))
                for row in report['accounts']:
                    # An authenticated, identity-matched count remains an observation even if suspicious.
                    if row['status'] not in ('HEALTHY', 'SUSPICIOUS'):
                        continue
                    cursor.execute('''INSERT INTO ebay_token_health_state
                        (browser_id,seller_account,listing_count,checked_at,run_id) VALUES (%s,%s,%s,%s,%s)
                        ON DUPLICATE KEY UPDATE seller_account=VALUES(seller_account),listing_count=VALUES(listing_count),
                        checked_at=VALUES(checked_at),run_id=VALUES(run_id)''',
                        (row['browser_id'], row['seller_account'], row['listing_count'], report['checked_at'], report['sync_batch_id']))
            connection.commit()
        except Exception:
            connection.rollback()
            raise
