import os
import time
import logging
from datetime import datetime
from sqlalchemy import select
from lead_generation_app.jobs import start_workers, enqueue
from lead_generation_app.database.database import init_db, get_session
from lead_generation_app.database.models import RawLead, QualifiedLead, BusinessClient
from lead_generation_app.scrapers.linkedin_scraper import scrape_linkedin_companies
from lead_generation_app.scrapers.instagram_scraper import scrape_instagram_businesses
from lead_generation_app.processing import validator, qualifier, enricher
from lead_generation_app.delivery.whatsapp_sender import send_whatsapp_leads
from lead_generation_app.delivery.email_sender import send_email_leads
from lead_generation_app.run_all import start_scheduler
from lead_generation_app.payments import is_client_active


def main():
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    init_db()
    count = int(os.getenv("WORKER_COUNT", "2"))
    start_workers(n=count)
    def run_linkedin_cycle():
        try:
            q = os.getenv("LINKEDIN_QUERY", "saas")
            limit = int(os.getenv("LINKEDIN_LIMIT", "25"))
            start_ts = datetime.utcnow()
            res = scrape_linkedin_companies(query=q, limit=limit)
            raw_ids = [r.get("raw_lead_id") for r in (res or []) if r.get("raw_lead_id")]
            s = get_session()
            try:
                raws = s.execute(select(RawLead).where(RawLead.id.in_(raw_ids))).scalars().all() if raw_ids else []
            finally:
                s.close()
            validated = validator.validate_leads(raws) if raws else []
            qualified_data = qualifier.qualify_leads(validated) if validated else []
            qualified_data = [enricher.enrich_leads(qd) for qd in qualified_data] if qualified_data else []
            q_ids = []
            if qualified_data:
                s = get_session()
                try:
                    # Insert if not already present
                    for qd in qualified_data:
                        rl_id = qd.get("raw_lead_id")
                        exists = s.execute(select(QualifiedLead).where(QualifiedLead.raw_lead_id == rl_id)).scalars().first()
                        if exists:
                            q_ids.append(exists.id)
                        else:
                            ql = QualifiedLead(
                                raw_lead_id=rl_id,
                                name=qd.get("name"),
                                company_name=qd.get("company_name"),
                                phone=qd.get("phone"),
                                whatsapp=None,
                                email=qd.get("email"),
                                qualification_score=int(qd.get("qualification_score", 70)),
                                score_category=qd.get("score_category", "warm"),
                                industry=qd.get("industry"),
                                summary=qd.get("summary") or "",
                                enriched_data_json=qd.get("enriched_data_json") or "{}",
                                verified_status=bool(qd.get("verified_status", True)),
                            )
                            s.add(ql)
                            s.flush()
                            q_ids.append(ql.id)
                    s.commit()
                finally:
                    s.close()
            if q_ids:
                s = get_session()
                try:
                    clients = s.execute(select(BusinessClient)).scalars().all()
                finally:
                    s.close()
                for bc in clients:
                    if not is_client_active(bc.id):
                        continue
                    send_whatsapp_leads(qualified_lead_ids=q_ids, business_client_id=bc.id)
                    send_email_leads(qualified_lead_ids=q_ids, business_client_id=bc.id)
        except Exception as e:
            logging.error("{\"event\":\"linkedin_cycle_error\",\"error\":\"%s\"}" % str(e).replace("\"","'"))
    interval = int(os.getenv("LINKEDIN_SCRAPE_INTERVAL", "3600"))
    start_scheduler(lambda: enqueue(run_linkedin_cycle), interval_seconds=interval)

    def run_instagram_cycle():
        try:
            q = os.getenv("INSTAGRAM_QUERY", "restaurants")
            limit = int(os.getenv("INSTAGRAM_LIMIT", "25"))
            start_ts = datetime.utcnow()
            res = scrape_instagram_businesses(query=q, limit=limit)
            raw_ids = [r.get("raw_lead_id") for r in (res or []) if r.get("raw_lead_id")]
            s = get_session()
            try:
                raws = s.execute(select(RawLead).where(RawLead.id.in_(raw_ids))).scalars().all() if raw_ids else []
            finally:
                s.close()
            validated = validator.validate_leads(raws) if raws else []
            qualified_data = qualifier.qualify_leads(validated) if validated else []
            qualified_data = [enricher.enrich_leads(qd) for qd in qualified_data] if qualified_data else []
            q_ids = []
            if qualified_data:
                s = get_session()
                try:
                    for qd in qualified_data:
                        rl_id = qd.get("raw_lead_id")
                        exists = s.execute(select(QualifiedLead).where(QualifiedLead.raw_lead_id == rl_id)).scalars().first()
                        if exists:
                            q_ids.append(exists.id)
                        else:
                            ql = QualifiedLead(
                                raw_lead_id=rl_id,
                                name=qd.get("name"),
                                company_name=qd.get("company_name"),
                                phone=qd.get("phone"),
                                whatsapp=None,
                                email=qd.get("email"),
                                qualification_score=int(qd.get("qualification_score", 70)),
                                score_category=qd.get("score_category", "warm"),
                                industry=qd.get("industry"),
                                summary=qd.get("summary") or "",
                                enriched_data_json=qd.get("enriched_data_json") or "{}",
                                verified_status=bool(qd.get("verified_status", True)),
                            )
                            s.add(ql)
                            s.flush()
                            q_ids.append(ql.id)
                    s.commit()
                finally:
                    s.close()
            if q_ids:
                s = get_session()
                try:
                    clients = s.execute(select(BusinessClient)).scalars().all()
                finally:
                    s.close()
                for bc in clients:
                    if not is_client_active(bc.id):
                        continue
                    send_whatsapp_leads(qualified_lead_ids=q_ids, business_client_id=bc.id)
                    send_email_leads(qualified_lead_ids=q_ids, business_client_id=bc.id)
        except Exception as e:
            logging.error("{\"event\":\"instagram_cycle_error\",\"error\":\"%s\"}" % str(e).replace("\"","'"))
    insta_interval = int(os.getenv("INSTAGRAM_SCRAPE_INTERVAL", "3600"))
    start_scheduler(lambda: enqueue(run_instagram_cycle), interval_seconds=insta_interval)
    while True:
        time.sleep(60)


if __name__ == "__main__":
    main()
