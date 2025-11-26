import json
import logging
from lead_generation_app.database.database import get_session
from lead_generation_app.database.models import IndustryRule
from sqlalchemy import select


def _parse_rules(r):
    if r is None:
        return {}
    if isinstance(r, dict):
        return r
    try:
        return json.loads(r)
    except Exception:
        return {}


def _score(lead, rules):
    w = rules.get("weights", {})
    t = rules.get("thresholds", {})
    score = 0
    score += (w.get("email", 30) if lead.get("email") else 0)
    score += (w.get("phone", 25) if lead.get("phone") else 0)
    score += (w.get("website", 20) if lead.get("website") else 0)
    kws = rules.get("keywords", [])
    name = (lead.get("company_name") or "") + " " + (lead.get("name") or "")
    if kws:
        for k in kws:
            if k and k.lower() in name.lower():
                score += w.get("keyword", 5)
    score = max(0, min(100, score))
    hot = int(t.get("hot", 75))
    warm = int(t.get("warm", 50))
    cat = "hot" if score >= hot else ("warm" if score >= warm else "cold")
    return score, cat


def qualify_leads(validated_leads):
    s = get_session()
    try:
        out = []
        seen = set()
        for lead in validated_leads:
            key = ((lead.get("email") or "").strip().lower(), (lead.get("phone") or "").strip(), (lead.get("company_name") or "").strip().lower())
            if key in seen:
                logging.info("{\"event\":\"qualify_dedup_skipped\"}")
                continue
            seen.add(key)
            ind = lead.get("industry")
            rule = None
            if ind:
                ir = s.execute(select(IndustryRule).where(IndustryRule.industry == ind)).scalars().first()
                rule = _parse_rules(ir.scoring_rules) if ir else {}
            score, cat = _score(lead, rule or {})
            out.append(
                {
                    "raw_lead_id": lead.get("raw_lead_id"),
                    "name": lead.get("name"),
                    "company_name": lead.get("company_name"),
                    "phone": lead.get("phone"),
                    "whatsapp": None,
                    "email": lead.get("email"),
                    "qualification_score": int(score),
                    "score_category": cat,
                    "industry": ind,
                    "summary": "",
                    "enriched_data_json": None,
                    "verified_status": False,
                }
            )
        logging.info("{\"event\":\"qualifier_processed\",\"input\":%d,\"output\":%d}" % (len(validated_leads), len(out)))
        return out
    finally:
        s.close()
