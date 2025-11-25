import time
import logging
import threading
from queue import Queue


class Job:
    def __init__(self, fn, args=None, kwargs=None, retries=3, backoff=0.5):
        self.fn = fn
        self.args = args or []
        self.kwargs = kwargs or {}
        self.retries = int(retries)
        self.backoff = float(backoff)


class Worker(threading.Thread):
    def __init__(self, q, dead_letter):
        super().__init__(daemon=True)
        self.q = q
        self.dead = dead_letter
        self.stop_evt = threading.Event()

    def run(self):
        while not self.stop_evt.is_set():
            try:
                job = self.q.get(timeout=0.5)
            except Exception:
                continue
            tries = 0
            while tries <= job.retries:
                try:
                    job.fn(*job.args, **job.kwargs)
                    break
                except Exception as e:
                    tries += 1
                    if tries > job.retries:
                        self.dead.append({"fn": str(job.fn), "args": job.args, "kwargs": job.kwargs, "error": str(e)})
                        logging.error("{\"event\":\"job_failed\"}")
                        break
                    time.sleep(job.backoff * (2 ** (tries - 1)))
            self.q.task_done()

    def stop(self):
        self.stop_evt.set()


_queue = Queue()
_dead_letter = []
_workers = []


def start_workers(n=2):
    global _workers
    for _ in range(int(n)):
        w = Worker(_queue, _dead_letter)
        w.start()
        _workers.append(w)
    logging.info("{\"event\":\"workers_started\",\"count\":%d}" % int(n))


def stop_workers():
    for w in _workers:
        w.stop()
    logging.info("{\"event\":\"workers_stopped\"}")


def enqueue(fn, *args, **kwargs):
    j = Job(fn=fn, args=list(args), kwargs=dict(kwargs))
    _queue.put(j)
    logging.info("{\"event\":\"job_enqueued\"}")
    return j


def dead_letter():
    return list(_dead_letter)
