"""单机版本的增量升级。先备份 SQLite，再增加字段；绝不回填虚构历史数据。"""
from datetime import datetime
from pathlib import Path
import sqlite3

from sqlalchemy import inspect, text

ADDITIONS = {
    "financial_documents": {"revision": "INTEGER NOT NULL DEFAULT 1"},
    "analysis_tasks": {
        "document_version": "INTEGER", "document_revision": "INTEGER",
        "input_snapshot_json": "TEXT", "context_snapshot_json": "TEXT", "heartbeat_at": "DATETIME",
    },
    "review_reports": {
        "document_snapshot_json": "TEXT", "supplier_snapshot_json": "TEXT",
        "snapshot_status": "VARCHAR(24) NOT NULL DEFAULT 'legacy'",
    },
}


def upgrade_database(engine):
    inspector = inspect(engine)
    existing = set(inspector.get_table_names())
    pending = [(table, name, kind) for table, columns in ADDITIONS.items() if table in existing
               for name, kind in columns.items() if name not in {c['name'] for c in inspector.get_columns(table)}]
    if not pending:
        return None
    backup = None
    if engine.dialect.name == 'sqlite' and engine.url.database not in (None, '', ':memory:'):
        source = Path(engine.url.database).resolve()
        backup = source.parent / 'backups' / f'{source.stem}-before-v1.1-{datetime.now():%Y%m%d-%H%M%S-%f}.db'
        backup.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(source.as_uri() + '?mode=ro', uri=True) as reader:
            with sqlite3.connect(backup) as writer:
                reader.backup(writer)
    with engine.begin() as conn:
        for table, name, kind in pending:
            conn.execute(text(f'ALTER TABLE {table} ADD COLUMN {name} {kind}'))
        if 'analysis_tasks' in existing:
            conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_analysis_active_version ON analysis_tasks(document_id,document_version) WHERE task_status IN ('queued','querying_document','loading_attachments','parsing_attachments','analyzing','generating_report')"))
    return backup
