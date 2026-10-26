"""调度器启动的单个后台工作进程。"""
import sys


def main():
    kind, identifier = sys.argv[1], int(sys.argv[2])
    if kind == 'analysis':
        from app.services.analysis import run_analysis_task
        run_analysis_task(identifier)
    elif kind == 'attachment':
        from app.services.parsing import parse_attachment_background
        parse_attachment_background(identifier)
    else:
        raise ValueError('未知任务类型')


if __name__ == '__main__':
    main()
