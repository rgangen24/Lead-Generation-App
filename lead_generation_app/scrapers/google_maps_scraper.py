import os
import json
import time
from urllib.parse import urlencode
from urllib.request import urlopen, Request
from datetime import datetime

from lead_generation_app.database.database import get_session
from lead_generation_app.database.models import RawLead


def _api_get(path, params, retry=3, delay=0.5):
    key = os.getenv("GOOGLE_MAPS_API_KEY")
    if not key:
        raise RuntimeError("GOOGLE_MAPS_API_KEY missing")
    params = dict(params or {})
    params["key"] = key
    url = f"https://maps.googleapis.com/maps/api/place/{path}/json?" + urlencode(params)
    last = None
    for _ in range(int(retry)):
        req = Request(url, headers={"Accept": "application/json"})
        with urlopen(req) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        status = data.get("status")
        if status in ("OK", "ZERO_RESULTS"):
            return data
        last = data
        time.sleep(float(delay))
    return last or {"status": "ERROR"}


def scrape_google_maps(search_term=None, location=None, industry=None, source_id=None):
    query = search_term or ""
    if location:
        query = f"{query} in {location}" if query else location
    search = _api_get("textsearch", {"query": query})
    results = []
    for item in search.get("results", [])[:50]:
        place_id = item.get("place_id")
        details = _api_get(
            "details",
            {
                "place_id": place_id,
                "fields": "name,formatted_phone_number,website,types",
            },
        )
        d = details.get("result", {})
        lead = {
            "name": None,
            "company_name": d.get("name"),
            "phone": d.get("formatted_phone_number"),
            "whatsapp": None,
            "email": None,
            "website": d.get("website"),
            "industry": industry or ",".join(d.get("types", []) or []),
            "raw_data_json": json.dumps({"search": item, "details": d}),
        }
        results.append(lead)

    print(f"scraped {len(results)} leads")

    if source_id is None:
        print("skip insert: source_id missing")
        return results

    session = get_session()
    inserted = 0
    try:
        for lead in results:
            row = RawLead(
                name=lead["name"],
                company_name=lead["company_name"],
                email=lead["email"],
                phone=lead["phone"],
                website=lead["website"],
                industry=lead["industry"],
                source_id=source_id,
                captured_at=datetime.utcnow(),
                raw_data_json=lead["raw_data_json"],
            )
            session.add(row)
            inserted += 1
        session.commit()
        print(f"inserted {inserted} leads")
    except Exception as e:
        session.rollback()
        print(f"insert error: {e}")
        raise
    finally:
        session.close()

    return results
