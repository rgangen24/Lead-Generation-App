from collections import defaultdict
from lead_generation_app.database.database import get_session
from lead_generation_app.database.models import RawLead, QualifiedLead, DeliveredLead, LeadSource, BusinessClient, Bounce
from sqlalchemy import select


def lead_to_qualified_rate_by_platform():
    s = get_session()
    try:
        raw = s.execute(select(RawLead.id, LeadSource.platform_type).join(LeadSource, RawLead.source_id == LeadSource.id)).all()
        q = s.execute(select(QualifiedLead.id, RawLead.id, LeadSource.platform_type).join(RawLead, QualifiedLead.raw_lead_id == RawLead.id).join(LeadSource, RawLead.source_id == LeadSource.id)).all()
        raw_counts = defaultdict(int)
        qual_counts = defaultdict(int)
        for _, pf in raw:
            raw_counts[pf or ""] += 1
        for _, _, pf in q:
            qual_counts[pf or ""] += 1
        out = {}
        for pf, rc in raw_counts.items():
            qc = qual_counts.get(pf, 0)
            rate = (qc / rc) if rc else 0.0
            out[pf] = {"raw": rc, "qualified": qc, "rate": rate}
        return out
    finally:
        s.close()


def qualified_to_delivered_rate_by_client_platform():
    s = get_session()
    try:
        qual = s.execute(select(QualifiedLead.id, RawLead.id, LeadSource.platform_type).join(RawLead, QualifiedLead.raw_lead_id == RawLead.id).join(LeadSource, RawLead.source_id == LeadSource.id)).all()
        qual_by_pf = defaultdict(int)
        for _, _, pf in qual:
            qual_by_pf[pf or ""] += 1
        dl = s.execute(select(DeliveredLead.business_client_id, DeliveredLead.qualified_lead_id, LeadSource.platform_type).join(QualifiedLead, DeliveredLead.qualified_lead_id == QualifiedLead.id).join(RawLead, QualifiedLead.raw_lead_id == RawLead.id).join(LeadSource, RawLead.source_id == LeadSource.id)).all()
        delivered_by_client_pf = defaultdict(int)
        for bc_id, _, pf in dl:
            key = (int(bc_id), pf or "")
            delivered_by_client_pf[key] += 1
        out = {}
        for (bc_id, pf), delivered in delivered_by_client_pf.items():
            denom = qual_by_pf.get(pf, 0)
            rate = (delivered / denom) if denom else 0.0
            out.setdefault(bc_id, {})[pf] = {"qualified": denom, "delivered": delivered, "rate": rate}
        return out
    finally:
        s.close()


def delivered_opened_bounced_rates_by_client_platform():
    s = get_session()
    try:
        rows = s.execute(select(DeliveredLead.id, DeliveredLead.business_client_id, DeliveredLead.opened_status, QualifiedLead.id, QualifiedLead.email, QualifiedLead.phone, DeliveredLead.delivery_method, LeadSource.platform_type).join(QualifiedLead, DeliveredLead.qualified_lead_id == QualifiedLead.id).join(RawLead, QualifiedLead.raw_lead_id == RawLead.id).join(LeadSource, RawLead.source_id == LeadSource.id)).all()
        delivered = defaultdict(int)
        opened = defaultdict(int)
        targets_by_group = defaultdict(set)
        for dl_id, bc_id, opened_status, qid, email, phone, method, pf in rows:
            key = (int(bc_id), method or "", pf or "")
            delivered[key] += 1
            if opened_status:
                opened[key] += 1
            if (method or "") == "email" and email:
                targets_by_group[key].add(("email", email.lower()))
            if (method or "") == "whatsapp" and phone:
                targets_by_group[key].add(("whatsapp", (phone or "").lower()))
        bounces = s.execute(select(Bounce.method, Bounce.target)).all()
        bounce_map = defaultdict(int)
        for method, target in bounces:
            bounce_map[(method or "", (target or "").lower())] += 1
        out = {}
        for key, dcount in delivered.items():
            bc_id, method, pf = key
            oc = opened.get(key, 0)
            bc = 0
            for t in targets_by_group.get(key, set()):
                bc += bounce_map.get(t, 0)
            rate_open = (oc / dcount) if dcount else 0.0
            rate_bounce = (bc / dcount) if dcount else 0.0
            out.setdefault(bc_id, {}).setdefault(pf, {})[method] = {"delivered": dcount, "opened": oc, "bounced": bc, "open_rate": rate_open, "bounce_rate": rate_bounce}
        return out
    finally:
        s.close()
