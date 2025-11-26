from lead_generation_app.database.database import get_session, init_db, get_engine
from lead_generation_app.database.models import RawLead
from lead_generation_app.processing.validator import validate_raw_leads as validate_leads
from lead_generation_app.processing.enricher import enrich_leads


def run_model1():
    # 1) Create engine and ensure tables exist
    engine = get_engine()
    init_db(engine)

    # 2) ALWAYS create session AFTER engine is ready
    session = get_session()

    # 3) Load Raw Leads
    print("Loading raw leads...")
    raw_leads = session.query(RawLead).all()
    print(f"Loaded {len(raw_leads)} raw leads")

    # 4) Validate Leads
    print("Validating leads...")
    validated = validate_leads(raw_leads)
    print(f"Validated: {len(validated)} leads")

    # 5) Enrich leads
    print("Enriching leads...")
    enriched_count = enrich_leads(validated)
    print(f"Enriched and inserted: {enriched_count}")

    session.close()
    print("Process completed.")


if __name__ == "__main__":
    run_model1()
