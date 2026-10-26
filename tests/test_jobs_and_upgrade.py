from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sqlite3
import subprocess
import sys
import time

from sqlalchemy import create_engine, inspect, select, func

from app.database import SessionLocal
from app.migrations import upgrade_database
from app.models import AnalysisTask, ReviewReport
from app.services.analysis import run_analysis_task
from app.services.documents import submit_document
from app.services.jobs import JobRunner


def test_upgrade_preserves_legacy_data_and_creates_backup(tmp_path):
    file=tmp_path/'legacy.db'
    with sqlite3.connect(file) as conn:
        conn.executescript('''
        CREATE TABLE financial_documents (id INTEGER PRIMARY KEY, document_no TEXT, total_amount NUMERIC);
        INSERT INTO financial_documents VALUES (1,'LEGACY-001',123.45);
        CREATE TABLE analysis_tasks (id INTEGER PRIMARY KEY,document_id INTEGER,task_status TEXT);
        INSERT INTO analysis_tasks VALUES (1,1,'succeeded');
        CREATE TABLE review_reports (id INTEGER PRIMARY KEY,report_markdown TEXT,amount_comparison_json TEXT);
        INSERT INTO review_reports VALUES (1,'原始报告','{"document_total":123.45}');
        ''')
    engine=create_engine('sqlite:///'+file.as_posix())
    backup=upgrade_database(engine)
    assert backup.is_file()
    assert 'document_version' in {c['name'] for c in inspect(engine).get_columns('analysis_tasks')}
    with sqlite3.connect(file) as conn:
        assert conn.execute('SELECT document_no,total_amount,revision FROM financial_documents').fetchone()==('LEGACY-001',123.45,1)
        assert conn.execute('SELECT snapshot_status,report_markdown FROM review_reports').fetchone()==('legacy','原始报告')
    with sqlite3.connect(backup) as conn:
        assert 'revision' not in {row[1] for row in conn.execute('PRAGMA table_info(financial_documents)')}
    assert upgrade_database(engine) is None
    engine.dispose()


def test_independent_worker_process_executes_persisted_job(db,document_factory):
    doc,owner=document_factory()
    _,task=submit_document(db,doc,owner)
    JobRunner(timeout_seconds=30).execute('analysis',task.id)
    db.expire_all()
    assert db.get(AnalysisTask,task.id).task_status=='succeeded'
    assert db.scalar(select(ReviewReport.id).where(ReviewReport.task_id==task.id))


def test_hard_timeout_terminates_only_its_worker(db,document_factory,monkeypatch):
    doc,owner=document_factory()
    _,task=submit_document(db,doc,owner)
    real_popen=subprocess.Popen
    def slow_worker(*args,**kwargs):
        return real_popen([sys.executable,'-c','import time; time.sleep(60)'],**kwargs)
    monkeypatch.setattr('app.services.jobs.subprocess.Popen',slow_worker)
    started=time.monotonic()
    JobRunner(timeout_seconds=1).execute('analysis',task.id)
    assert time.monotonic()-started<8
    db.expire_all()
    assert db.get(AnalysisTask,task.id).task_status=='failed'
    assert '超过' in db.get(AnalysisTask,task.id).error_message


def test_two_workers_only_publish_one_report(db,document_factory):
    doc,owner=document_factory()
    _,task=submit_document(db,doc,owner)
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(run_analysis_task,[task.id,task.id]))
    db.expire_all()
    assert db.get(AnalysisTask,task.id).task_status=='succeeded'
    assert db.scalar(select(func.count()).select_from(ReviewReport).where(ReviewReport.task_id==task.id))==1


def test_concurrent_analysis_requests_keep_single_active_job(db,client,headers,document_factory):
    doc,owner=document_factory()
    _,task=submit_document(db,doc,owner)
    run_analysis_task(task.id)
    credentials=headers('lina')
    def request(_):
        return client.post(f'/api/v1/documents/{doc.id}/analysis',headers=credentials,json={})
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses=list(pool.map(request,range(2)))
    assert all(response.status_code in {200,409} for response in responses)
    active=db.scalars(select(AnalysisTask).where(AnalysisTask.document_id==doc.id,AnalysisTask.task_status=='queued')).all()
    assert len(active)==1
