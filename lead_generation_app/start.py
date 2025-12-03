import os
import sys
import signal
import subprocess


def run_admin():
    port = os.getenv('PORT') or os.getenv('ADMIN_PORT') or '10000'
    args = [
        'gunicorn',
        '--bind', f'0.0.0.0:{port}',
        '--timeout', '120',
        'lead_generation_app.admin_web:app',
    ]
    os.execvp('gunicorn', args)


def run_worker():
    os.execvp(sys.executable, [sys.executable, '-m', 'lead_generation_app.app_main'])


def run_all():
    procs = []

    def _term(signum, frame):
        for p in procs:
            try:
                p.terminate()
            except Exception:
                pass
        for p in procs:
            try:
                p.wait(timeout=10)
            except Exception:
                try:
                    p.kill()
                except Exception:
                    pass
        sys.exit(0)

    signal.signal(signal.SIGTERM, _term)
    signal.signal(signal.SIGINT, _term)

    port = os.getenv('PORT') or os.getenv('ADMIN_PORT') or '10000'
    admin = subprocess.Popen([
        'gunicorn',
        '--bind', f'0.0.0.0:{port}',
        '--timeout', '120',
        'lead_generation_app.admin_web:app',
    ])
    procs.append(admin)

    worker = subprocess.Popen([sys.executable, '-m', 'lead_generation_app.app_main'])
    procs.append(worker)

    exit_code = 0
    try:
        exit_code = admin.wait()
    finally:
        _term(signal.SIGTERM, None)
    sys.exit(exit_code)


def main():
    mode = (os.getenv('SERVICE_MODE') or os.getenv('RUN_MODE') or 'admin').strip().lower()
    if mode in ('admin', 'web'):
        run_admin()
    elif mode in ('worker', 'background'):
        run_worker()
    elif mode in ('all', 'both', 'combined'):
        run_all()
    else:
        run_admin()


if __name__ == '__main__':
    main()
