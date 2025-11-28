import os
import re
import json
import threading
import time
from urllib.parse import urlparse
from urllib.request import urlopen
from lead_generation_app.database.database import get_session
from lead_generation_app.database.models import RawLead, QualifiedLead


def is_valid_email(v):
    if not v: return False
    return re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", v) is not None


def is_valid_phone(v):
    if not v: return False
    digits = re.sub(r"\D", "", v)
    return len(digits) >= 7


def start_scheduler(task_fn, interval_seconds=3600):
    stop = threading.Event()
    def loop():
        while not stop.is_set():
            try:
                task_fn()
            except Exception:
                pass
            time.sleep(int(interval_seconds))
    t = threading.Thread(target=loop, daemon=True)
    t.start()
    return stop


def is_valid_url(v):
    if not v: return False
    p = urlparse(v)
    if p.scheme and p.netloc: return True
    p = urlparse("http://" + v)
    return bool(p.netloc)


def validate_leads(leads):
    out = []
    for r in leads:
        email_ok = is_valid_email(r.email)
        phone_ok = is_valid_phone(r.phone)
        web_ok = is_valid_url(r.website)
        lead = {
            "raw_lead_id": r.id,
            "name": r.name,
            "company_name": r.company_name,
            "phone": r.phone if phone_ok else None,
            "email": r.email if email_ok else None,
            "website": r.website if web_ok else None,
            "industry": r.industry,
        }
        out.append(lead)
    print(f"Validated {len(out)} leads")
    return out


def qualify_leads(lead):
    score = 0
    if lead.get("email"): score += 1
    if lead.get("phone"): score += 1
    lead["qualification_score"] = score
    lead["score_category"] = "high" if score >= 2 else "low"
    return lead


def enrich_leads(lead):
    u = lead.get("website")
    content_len = 0
    keywords = []
    site_ok = False
    if u:
        try:
            with urlopen(u, timeout=5) as resp:
                body = resp.read()
                content_len = len(body)
                text = body[:5000].decode("utf-8", errors="ignore").lower()
                for k in ["contact", "review", "about", "rating"]:
                    if k in text: keywords.append(k)
                site_ok = True
        except: site_ok = False
    lead["summary"] = f"site_ok={site_ok}, content_len={content_len}"
    lead["enriched_data_json"] = {"site_ok": site_ok, "content_len": content_len, "keywords": keywords}
    lead["verified_status"] = site_ok
    return lead


def run_all():
    session = get_session()
    try:
        print("Loading raw leads...")
        raw_leads = session.query(RawLead).all()
        print(f"Loaded {len(raw_leads)} raw leads")
        if not raw_leads:
            print("No leads to process")
            return

        print("Validating leads...")
        validated = validate_leads(raw_leads)

        print("Qualifying leads...")
        qualified = [qualify_leads(l) for l in validated]

        print("Enriching leads...")
        enriched = [enrich_leads(l) for l in qualified]

        print("Inserting qualified leads...")
        for l in enriched:
            ql = QualifiedLead(
                raw_lead_id=l["raw_lead_id"],
                name=l["name"],
                company_name=l["company_name"],
                phone=l["phone"],
                whatsapp=l.get("whatsapp"),
                email=l["email"],
                qualification_score=l["qualification_score"],
                score_category=l["score_category"],
                industry=l["industry"],
                summary=l["summary"],
                enriched_data_json=l["enriched_data_json"],
                verified_status=l["verified_status"]
            )
            session.add(ql)
        session.commit()
        print(f"Inserted {len(enriched)} qualified leads")
    finally:
        session.close()

if __name__ == "__main__":
    run_all()
