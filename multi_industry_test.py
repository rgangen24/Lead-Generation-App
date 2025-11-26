import logging
from datetime import datetime
from lead_generation_app.database.database import init_db, get_session
from lead_generation_app.database.models import LeadSource, BusinessClient, Payment, RawLead, QualifiedLead, SourceAttribution
from sqlalchemy import select
from lead_generation_app.scrapers.linkedin_scraper import scrape_linkedin_companies
from lead_generation_app.scrapers.instagram_scraper import scrape_instagram_businesses
from lead_generation_app.payments import update_subscription, record_payment
from lead_generation_app.delivery.whatsapp_sender import send_whatsapp_leads
from lead_generation_app.delivery.email_sender import send_email_leads


def seed_lead_sources(s):
    industries = ["restaurants", "fitness", "salons", "real_estate", "legal"]
    platforms = ["maps", "linkedin", "facebook"]
    out = []
    for ind in industries:
        for pf in platforms:
            ls = LeadSource(
                source_name=f"{ind}_{pf}",
                industry=ind,
                platform_type=pf,
                scrape_url=f"https://example.com/{ind}/{pf}",
                active_status=True,
            )
            s.add(ls)
            out.append(ls)
    s.commit()
    return out


def seed_business_clients(s):
    clients = []
    subs = ["starter", "pro", "elite"]
    for i, plan in enumerate(subs, start=1):
        bc = BusinessClient(
            business_name=f"Subscriber_{plan}",
            industry="restaurants",
            email=f"sub_{plan}@example.com",
            phone=f"+100000000{i}",
            whatsapp=f"+100000000{i}",
        )
        s.add(bc)
        s.commit()
        update_subscription(bc.id, plan_name=plan, number_of_users=5, payment_status="paid")
        clients.append(bc)
    ppl1 = BusinessClient(
        business_name="PPL_Client_A",
        industry="fitness",
        email="ppl_a@example.com",
        phone="+2000000001",
        whatsapp="+2000000001",
    )
    s.add(ppl1)
    ppl2 = BusinessClient(
        business_name="PPL_Client_B",
        industry="salons",
        email="ppl_b@example.com",
        phone="+2000000002",
        whatsapp="+2000000002",
    )
    s.add(ppl2)
    trial = BusinessClient(
        business_name="Trial_Client",
        industry="real_estate",
        email="trial@example.com",
        phone="+3000000001",
        whatsapp="+3000000001",
    )
    s.add(trial)
    s.commit()
    clients.extend([ppl1, ppl2, trial])
    record_payment(ppl1.id, plan_name="ppl", amount=0, payment_status="paid")
    record_payment(ppl2.id, plan_name="ppl", amount=0, payment_status="paid")
    record_payment(trial.id, plan_name="trial", amount=49, payment_status="paid")
    return clients


def seed_raw_leads(s, lead_sources):
    out = []
    for ls in lead_sources:
        for i in range(5):
            rl = RawLead(
                name=f"Contact {i}",
                company_name=f"{ls.industry.title()} Co {i}",
                email=f"lead{i}@{ls.industry}.example.com",
                phone=f"+4000000{i:03d}",
                website=f"https://{ls.industry}{i}.example.com",
                industry=ls.industry,
                source_id=ls.id,
                captured_at=datetime.utcnow(),
                raw_data_json="{}",
            )
            s.add(rl)
            out.append(rl)
    s.commit()
    return out


def seed_qualified_leads(s, raw_leads):
    for i, rl in enumerate(raw_leads):
        score = 85 if i % 2 == 0 else 60
        cat = "hot" if score >= 75 else "warm"
        ql = QualifiedLead(
            raw_lead_id=rl.id,
            name=rl.name,
            company_name=rl.company_name,
            phone=rl.phone,
            whatsapp=None,
            email=rl.email,
            qualification_score=score,
            score_category=cat,
            industry=rl.industry,
            summary="Auto summary",
            enriched_data_json="{}",
            verified_status=True,
        )
        s.add(ql)
    s.commit()


def run_delivery_tests(s, clients):
    logs = {}
    for bc in clients:
        wl = send_whatsapp_leads(business_client_id=bc.id)
        el = send_email_leads(business_client_id=bc.id, template="default")
        logs[bc.business_name] = {"whatsapp": wl, "email": el}
    return logs


def summarize(logs):
    for cname, res in logs.items():
        for method, items in res.items():
            total = len(items)
            delivered = len([x for x in items if x.get("status") == "delivered"])
            skipped_cap = len([x for x in items if str(x.get("reason", "")).startswith("cap_reached")])
            skipped_inactive = len([x for x in items if x.get("reason") == "inactive"])
            logging.info("{\"event\":\"client_summary\",\"client\":\"%s\",\"method\":\"%s\",\"total\":%d,\"delivered\":%d,\"skipped_cap\":%d,\"skipped_inactive\":%d}" % (cname, method, total, delivered, skipped_cap, skipped_inactive))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    init_db()
    s = get_session()
    try:
        lead_sources = seed_lead_sources(s)
        clients = seed_business_clients(s)
        raw_leads = seed_raw_leads(s, lead_sources)
        seed_qualified_leads(s, raw_leads)
        logs1 = run_delivery_tests(s, clients)
        summarize(logs1)
        logs2 = run_linkedin_case(s, clients)
        summarize(logs2)
        logs3 = run_instagram_case(s, clients)
        summarize(logs3)
    finally:
        s.close()
def run_linkedin_case(s, clients):
    res = scrape_linkedin_companies(query="saas", limit=10)
    raw_ids = [r.get("raw_lead_id") for r in (res or []) if r.get("raw_lead_id")]
    atts = s.execute(select(SourceAttribution).where(SourceAttribution.raw_lead_id.in_(raw_ids))).scalars().all() if raw_ids else []
    qls = s.execute(select(QualifiedLead).where(QualifiedLead.raw_lead_id.in_(raw_ids))).scalars().all() if raw_ids else []
    q_ids = [q.id for q in qls]
    logs = {}
    for bc in clients:
        wl = send_whatsapp_leads(qualified_lead_ids=q_ids, business_client_id=bc.id)
        el = send_email_leads(qualified_lead_ids=q_ids, business_client_id=bc.id, template="default")
        logs[bc.business_name] = {"whatsapp": wl, "email": el}
    logging.info("{\"event\":\"linkedin_attributions\",\"count\":%d}" % len(atts))
    return logs

def run_instagram_case(s, clients):
    res = scrape_instagram_businesses(query="restaurants", limit=10)
    raw_ids = [r.get("raw_lead_id") for r in (res or []) if r.get("raw_lead_id")]
    atts = s.execute(select(SourceAttribution).where(SourceAttribution.raw_lead_id.in_(raw_ids))).scalars().all() if raw_ids else []
    qls = s.execute(select(QualifiedLead).where(QualifiedLead.raw_lead_id.in_(raw_ids))).scalars().all() if raw_ids else []
    q_ids = [q.id for q in qls]
    logs = {}
    for bc in clients:
        wl = send_whatsapp_leads(qualified_lead_ids=q_ids, business_client_id=bc.id)
        el = send_email_leads(qualified_lead_ids=q_ids, business_client_id=bc.id, template="default")
        logs[bc.business_name] = {"whatsapp": wl, "email": el}
    logging.info("{\"event\":\"instagram_attributions\",\"count\":%d}" % len(atts))
    return logs
