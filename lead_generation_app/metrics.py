import json
import copy
import logging
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

_lock = threading.Lock()
_data = {}


def _get_bucket(client_id, method, industry):
    with _lock:
        c = _data.setdefault(int(client_id), {})
        m = c.setdefault(method, {})
        b = m.setdefault(industry or "", {"delivered": 0, "skipped_cap": 0, "skipped_inactive": 0, "trial_used": 0})
        return b


def inc_success(client_id, method, industry):
    b = _get_bucket(client_id, method, industry)
    with _lock:
        b["delivered"] += 1


def inc_skip_cap(client_id, method, industry):
    b = _get_bucket(client_id, method, industry)
    with _lock:
        b["skipped_cap"] += 1


def inc_skip_inactive(client_id, method, industry):
    b = _get_bucket(client_id, method, industry)
    with _lock:
        b["skipped_inactive"] += 1


def inc_trial_used(client_id, method, industry):
    b = _get_bucket(client_id, method, industry)
    with _lock:
        b["trial_used"] += 1


def get_metrics():
    with _lock:
        return copy.deepcopy(_data)


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/metrics":
            data = get_metrics()
            lines = []
            lines.append("# TYPE leadgen_delivered_total counter")
            lines.append("# TYPE leadgen_skipped_cap_total counter")
            lines.append("# TYPE leadgen_skipped_inactive_total counter")
            lines.append("# TYPE leadgen_trial_used_total counter")
            for cid, methods in data.items():
                for method, inds in methods.items():
                    for industry, vals in inds.items():
                        labels = f"client_id=\"{cid}\",method=\"{method}\",industry=\"{industry}\""
                        lines.append(f"leadgen_delivered_total{{{labels}}} {int(vals.get('delivered', 0))}")
                        lines.append(f"leadgen_skipped_cap_total{{{labels}}} {int(vals.get('skipped_cap', 0))}")
                        lines.append(f"leadgen_skipped_inactive_total{{{labels}}} {int(vals.get('skipped_inactive', 0))}")
                        lines.append(f"leadgen_trial_used_total{{{labels}}} {int(vals.get('trial_used', 0))}")
            body = ("\n".join(lines) + "\n").encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; version=0.0.4")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()


def start_http_server(host="127.0.0.1", port=8000):
    srv = HTTPServer((host, int(port)), _Handler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    logging.info("{\"event\":\"metrics_server_started\",\"host\":\"%s\",\"port\":%d}" % (host, port))
    return srv
