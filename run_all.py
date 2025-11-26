import os
import re
import json
from urllib.parse import urlparse
from urllib.request import urlopen
from sqlalchemy import create_engine, Column, Integer, String, Boolean, JSON
from sqlalchemy.orm import sessionmaker, declarative_base

# -------------------------
# DATABASE SETUP
# -------------------------
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "your_db_name")
DB_USER = os.getenv("DB_USER", "your_user")
DB_PASS = os.getenv("DB_PASS", "your_pass")

DATABASE_URL = f"postgresql+psycopg2://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

engine = create_engine(DATABASE_URL, echo=True)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

class RawLead(Base):
    __tablename__ = "raw_leads"
    id = Column(Integer, primary_key=True)
    name = Column(String)
    company_name = Column(String)
    phone = Column(String)
    whatsapp = Column(String)
    email = Column(String)
    website = Column(String)
    industry = Column(String)

class QualifiedLead(Base):
    __tablename__ = "qualified_leads"
    id = Column(Integer, primary_key=True)
    raw_lead_id = Column(Integer)
    name = Column(String)
    company_name = Column(String)
    phone = Column(String)
    whatsapp = Column(String)
    email = Column(String)
    qualification_score = Column(Integer)
    score_category = Column(String)
    industry = Column(String)
    summary = Column(String)
    enriched_data_json = Column(JSON)
    verified_status = Column(Boolean)

Base.metadata.create_all(engine)

# -------------------------
# VALIDATION
# -------------------------
def is_valid_email(v):
    if not v: return False
    return re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", v) is not None

def is_valid_phone(v):
    if not v: return False
    digits = re.sub(r"\D", "", v)
    return len(digits) >= 7

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

# -------------------------
# QUALIFICATION (simple example)
# -------------------------
def qualify_leads(lead):
    score = 0
    if lead.get("email"): score += 1
    if lead.get("phone"): score += 1
    lead["qualification_score"] = score
    lead["score_category"] = "high" if score >= 2 else "low"
    return lead

# -------------------------
# ENRICHMENT
# -------------------------
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

# -------------------------
# MAIN PROCESS
# -------------------------
def run_all():
    session = SessionLocal()
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
