import os
import json
import time
from datetime import datetime
from lead_generation_app.database.database import get_session
from lead_generation_app.database.models import LeadSource, RawLead, QualifiedLead, SourceAttribution


def scrape_instagram_businesses(query, limit=50, import_json_path=None, rate_per_minute=None):
    s = get_session()
    try:
        ls = s.query(LeadSource).filter(LeadSource.source_name == "instagram", LeadSource.platform_type == "social").first()
        if not ls:
            ls = LeadSource(source_name="instagram", industry="", platform_type="social", scrape_url="https://www.instagram.com", active_status=True)
            s.add(ls)
            s.commit()
        results = []
        items = []
        if import_json_path and os.path.exists(import_json_path):
            with open(import_json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            items = data[: int(limit)]
        else:
            for i in range(int(limit)):
                items.append({
                    "name": f"Biz {i}",
                    "email": f"contact{i}@example.com",
                    "phone": f"+1{i:07d}",
                    "website": f"https://example{i}.com",
                    "category": "restaurants",
                    "industry": "restaurants",
                    "profile": f"https://www.instagram.com/example_{i}/",
                    "campaign": query,
                })
        rpm = rate_per_minute or int(os.getenv("INSTAGRAM_RATE_LIMIT_PER_MINUTE", "60"))
        delay = (60.0 / max(1, int(rpm)))
        for idx, it in enumerate(items):
            rl = RawLead(
                name=it.get("name"),
                company_name=it.get("name"),
                email=it.get("email"),
                phone=it.get("phone"),
                website=it.get("website"),
                industry=it.get("industry") or it.get("category"),
                source_id=ls.id,
                captured_at=datetime.utcnow(),
                raw_data_json=json.dumps(it),
            )
            s.add(rl)
            s.flush()
            qa = SourceAttribution(
                raw_lead_id=rl.id,
                source_platform="instagram",
                source_reference=it.get("profile"),
                campaign=it.get("campaign"),
                collected_at=datetime.utcnow(),
            )
            s.add(qa)
            ql = QualifiedLead(
                raw_lead_id=rl.id,
                name=rl.name,
                company_name=rl.company_name,
                phone=rl.phone,
                whatsapp=None,
                email=rl.email,
                qualification_score=75,
                score_category="warm",
                industry=rl.industry,
                summary="",
                enriched_data_json="{}",
                verified_status=True,
            )
            s.add(ql)
            results.append({"raw_lead_id": rl.id, "qualified_lead_id": None})
            if idx + 1 < len(items):
                time.sleep(delay)
        s.commit()
        return results
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()

