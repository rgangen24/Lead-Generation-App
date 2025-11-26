import json
import logging
import os
import hmac
import hashlib
import base64
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs
from lead_generation_app.database.database import get_session
from lead_generation_app.database.models import DeliveredLead, QualifiedLead, OptOut, Bounce
from sqlalchemy import select
from datetime import datetime


def _mark_opened(session, method, target):
    if method == "email":
        ql = session.execute(select(QualifiedLead).where(QualifiedLead.email == target)).scalars().first()
    else:
        ql = session.execute(select(QualifiedLead).where(QualifiedLead.phone == target)).scalars().first()
    if not ql:
        return False
    row = session.execute(
        select(DeliveredLead)
        .where(DeliveredLead.qualified_lead_id == ql.id)
        .where(DeliveredLead.delivery_method == method)
    ).scalars().first()
    if not row:
        return False
    row.opened_status = True
    session.commit()
    return True


def handle_sendgrid_events(events):
    s = get_session()
    try:
        for ev in events or []:
            email = (ev.get("email") or "").lower()
            et = (ev.get("event") or "").lower()
            if not email:
                continue
            if et in ("delivered", "open"):
                _mark_opened(s, "email", email)
            elif et in ("unsubscribe", "unsubscribed"):
                s.add(OptOut(method="email", value=email, created_at=datetime.utcnow()))
                s.commit()
            elif et == "bounce":
                s.add(Bounce(method="email", target=email, reason=str(ev.get("reason") or "bounce"), created_at=datetime.utcnow()))
                s.commit()
        return True
    finally:
        s.close()


def handle_twilio_event(params):
    s = get_session()
    try:
        status = (params.get("MessageStatus") or params.get("messageStatus") or "").lower()
        to = (params.get("To") or params.get("to") or "").lower()
        if to.startswith("whatsapp:"):
            to = to.split(":", 1)[1]
        if not to:
            return False
        if status in ("delivered", "read"):
            _mark_opened(s, "whatsapp", to)
        elif status in ("undelivered", "failed"):
            s.add(Bounce(method="whatsapp", target=to, reason=status, created_at=datetime.utcnow()))
            s.commit()
        elif status in ("stopped", "optout"):
            s.add(OptOut(method="whatsapp", value=to, created_at=datetime.utcnow()))
            s.commit()
        return True
    finally:
        s.close()


class WebhookHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            ln = int(self.headers.get("Content-Length", "0"))
        except Exception:
            ln = 0
        body = self.rfile.read(ln or 0)
        ok = False
        if self.path == "/webhook/sendgrid":
            sig = self.headers.get("X-Twilio-Email-Event-Webhook-Signature")
            ts = self.headers.get("X-Twilio-Email-Event-Webhook-Timestamp")
            pub = os.getenv("SENDGRID_EVENT_PUBLIC_KEY")
            token = os.getenv("SENDGRID_WEBHOOK_TOKEN")
            verified = False
            if pub and sig and ts:
                try:
                    from nacl.signing import VerifyKey
                    from nacl.encoding import Base64Encoder
                    vk = VerifyKey(pub, encoder=Base64Encoder)
                    vk.verify((ts or "").encode("utf-8") + body, base64.b64decode(sig))
                    verified = True
                except Exception:
                    verified = False
            if not verified and token:
                auth = self.headers.get("Authorization") or ""
                if auth.strip().lower().startswith("bearer ") and auth.strip().split(" ", 1)[1] == token:
                    verified = True
            if not verified:
                self.send_response(403)
                self.end_headers()
                return
            try:
                events = json.loads(body.decode("utf-8") or "[]")
            except Exception:
                events = []
            ok = bool(handle_sendgrid_events(events))
        elif self.path == "/webhook/twilio":
            url = os.getenv("TWILIO_WEBHOOK_URL") or ("http://" + (self.headers.get("Host") or "") + self.path)
            sig = self.headers.get("X-Twilio-Signature") or ""
            token = os.getenv("TWILIO_AUTH_TOKEN") or ""
            try:
                params = {k: (v[0] if isinstance(v, list) else v) for k, v in parse_qs((body or b"").decode("utf-8")).items()}
            except Exception:
                params = {}
            expected = None
            if token:
                items = sorted(params.items(), key=lambda x: x[0])
                s = url
                for k, v in items:
                    s += str(v)
                digest = hmac.new(token.encode("utf-8"), s.encode("utf-8"), hashlib.sha1).digest()
                expected = base64.b64encode(digest).decode("utf-8")
            if not sig or not expected or sig != expected:
                self.send_response(403)
                self.end_headers()
                return
            ok = bool(handle_twilio_event(params))
        code = 200 if ok else 400
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        out = json.dumps({"ok": ok}).encode("utf-8")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)


def start_webhook_server(host="0.0.0.0", port=8080):
    srv = HTTPServer((host, int(port)), WebhookHandler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    logging.info("{\"event\":\"webhook_server_started\",\"host\":\"%s\",\"port\":%d}" % (host, port))
    return srv
