"""持久化单机任务队列。固定一个调度器，重任务放入可终止的独立进程。"""
import logging
import os
import subprocess
import sys
import threading
import time
from datetime import timedelta

from sqlalchemy import or_, select, update

from app.config import BASE_DIR, DATABASE_URL, DATA_DIR, STORAGE_DIR
from app.database import SessionLocal
from app.models import AnalysisTask, DocumentAttachment
from app.services.analysis import ACTIVE_STATUSES
from app.utils import now

logger = logging.getLogger(__name__)


def recover_interrupted(db, timeout_seconds=180):
    cutoff = now() - timedelta(seconds=timeout_seconds)
    result = db.execute(update(AnalysisTask).where(AnalysisTask.task_status.in_(ACTIVE_STATUSES[1:]),
        or_(AnalysisTask.heartbeat_at.is_(None), AnalysisTask.heartbeat_at < cutoff)).values(
        task_status='failed', current_step='failed', error_message='上次分析被中断或超时，请重新发起分析', finished_at=now()))
    db.commit()
    return result.rowcount


class JobRunner:
    def __init__(self, timeout_seconds=180):
        self.timeout = timeout_seconds
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self.run, name='risk-review-job-runner', daemon=True)

    def start(self):
        with SessionLocal() as db:
            recover_interrupted(db, self.timeout)
            db.execute(update(DocumentAttachment).where(DocumentAttachment.parse_status == 'parsing',
                DocumentAttachment.storage_status == 'stored').values(parse_status='pending'))
            db.commit()
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        self.thread.join(timeout=8)

    def run(self):
        while not self.stop_event.is_set():
            try:
                with SessionLocal() as db:
                    recover_interrupted(db, self.timeout)
                    task = db.scalar(select(AnalysisTask.id).where(AnalysisTask.task_status == 'queued').order_by(AnalysisTask.id))
                    attachment = None if task else db.scalar(select(DocumentAttachment.id).where(
                        DocumentAttachment.storage_status == 'stored', DocumentAttachment.parse_status == 'pending').order_by(DocumentAttachment.id))
                if task or attachment:
                    self.execute('analysis' if task else 'attachment', task or attachment)
                    continue
            except Exception:
                logger.exception('任务调度失败，将稍后重试')
            self.stop_event.wait(.5)

    def execute(self, kind, item_id):
        env = os.environ.copy()
        env.update(RISK_REVIEW_DATABASE_URL=DATABASE_URL, RISK_REVIEW_DATA_DIR=str(DATA_DIR.resolve()),
                   RISK_REVIEW_STORAGE_DIR=str(STORAGE_DIR.resolve()), PYTHONDONTWRITEBYTECODE='1')
        process = subprocess.Popen([sys.executable, '-B', '-m', 'app.worker', kind, str(item_id)],
            cwd=BASE_DIR, env=env, stdin=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        started = time.monotonic()
        reason = None
        try:
            while process.poll() is None:
                if self.stop_event.wait(.2):
                    reason = '服务停止，任务已中断，可重新发起'
                    break
                if time.monotonic() - started > self.timeout:
                    reason = f'任务超过 {self.timeout} 秒，已停止，请检查材料后重试'
                    break
                if kind == 'analysis':
                    with SessionLocal() as db:
                        status = db.scalar(select(AnalysisTask.task_status).where(AnalysisTask.id == item_id))
                    if status in {'cancelled', 'failed'}:
                        reason = '任务已取消或已失效'
                        break
            if not reason and process.returncode not in (0, None):
                reason = f'后台进程异常退出（代码 {process.returncode}），请重新发起任务'
            if reason:
                if process.poll() is None:
                    process.terminate()
                    process.wait(timeout=5)
                with SessionLocal() as db:
                    if kind == 'analysis':
                        db.execute(update(AnalysisTask).where(AnalysisTask.id == item_id,
                            AnalysisTask.task_status.in_(ACTIVE_STATUSES)).values(task_status='failed', current_step='failed',
                            error_message=reason, finished_at=now()))
                    else:
                        attachment = db.get(DocumentAttachment, item_id)
                        if attachment and attachment.parse_status in {'pending', 'parsing'}:
                            attachment.parse_status = 'failed'
                            from app.models import AttachmentParseResult
                            db.add(AttachmentParseResult(attachment_id=item_id, document_category='other', full_text='',
                                confidence=0, parser_source='error', error_message=reason))
                    db.commit()
        finally:
            if process.poll() is None:
                process.kill()
            process.wait()

