import os
import json
import logging
from base64 import b64encode
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from datetime import datetime, timedelta
from calendar import monthrange
from sqlalchemy import select, func

from lead_generation_app.delivery import record_delivery
from lead_generation_app.payments import is_client_active
from lead_generation_app.database.database import get_session
from lead_generation_app.database.models import QualifiedLead, DeliveredLead, BusinessClient, Payment, OptOut, Bounce
from lead_generation_app.config.pricing import BASE_PLANS, LEAD_PRICING, PAY_PER_LEAD_CAP, INDUSTRY_TIERS, TRIAL_CONFIG
from lead_generation_app.metrics import inc_success, inc_skip_cap, inc_skip_inactive, inc_trial_used


def _month_window(dt):
    start = datetime(dt.year, dt.month, 1)
    end = datetime(dt.year, dt.month, monthrange(dt.year, dt.month)[1]) + timedelta(days=1)
    return start, end


def _tier_for(industry):
    key = (industry or "").lower().replace(" ", "_")
    return INDUSTRY_TIERS.get(key, "basic")


def _send_whatsapp_via_twilio(to_number, body):
    sid = os.getenv("TWILIO_ACCOUNT_SID")
    token = os.getenv("TWILIO_AUTH_TOKEN")
    from_num = os.getenv("TWILIO_WHATSAPP_FROM")
    if not sid or not token or not from_num:
        return {"status": "simulated"}
    url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"
    data = urlencode({
        "From": f"whatsapp:{from_num}",
        "To": f"whatsapp:{to_number}",
        "Body": body or "",
    }).encode("utf-8")
    auth = b64encode(f"{sid}:{token}".encode("utf-8")).decode("utf-8")
    req = Request(url, data=data, headers={"Authorization": f"Basic {auth}"}, method="POST")
    try:
        with urlopen(req) as resp:
            return {"status": str(resp.getcode())}
    except Exception as e:
        return {"status": f"error:{e}"}


def send_whatsapp_leads(qualified_lead_ids=None, business_client_id=None):
    s = get_session()
    try:
        now = datetime.utcnow()
        start, end = _month_window(now)
        bc = s.execute(select(BusinessClient).where(BusinessClient.id == business_client_id)).scalars().first()
        if not bc:
            logging.info("{\"event\":\"whatsapp_skip\",\"reason\":\"client_missing\"}")
            return []
        active = is_client_active(business_client_id)
        plan = BASE_PLANS.get(bc.subscription_plan) if bc.subscription_plan else None
        trial_pay = s.execute(
            select(Payment).where(Payment.business_client_id == business_client_id).where(Payment.plan_name == "trial").where(
                Payment.payment_status.in_(["paid", "success"]))
        ).scalars().first()
        trial_active = False
        trial_deadline = None
        trial_used = 0
        if trial_pay:
            trial_deadline = trial_pay.payment_date + timedelta(days=int(TRIAL_CONFIG.get("days_valid", 7)))
            if now <= trial_deadline:
                trial_active = True
                trial_used = s.execute(
                    select(func.count(DeliveredLead.id)).where(DeliveredLead.business_client_id == business_client_id).where(
                        DeliveredLead.delivered_at >= trial_pay.payment_date).where(DeliveredLead.delivered_at <= trial_deadline)
                ).scalar_one()

        ids = list(qualified_lead_ids or [])
        if not ids:
            rows = s.execute(select(QualifiedLead).where(QualifiedLead.score_category.in_(["hot", "warm"]))\
                .where(QualifiedLead.industry == bc.industry)).scalars().all()
        else:
            rows = s.execute(select(QualifiedLead).where(QualifiedLead.id.in_(ids))).scalars().all()

        delivered_count_month = s.execute(
            select(func.count(DeliveredLead.id)).where(DeliveredLead.business_client_id == business_client_id).where(
                DeliveredLead.delivered_at >= start).where(DeliveredLead.delivered_at < end)
        ).scalar_one()

        tier_counts = {}
        out = []
        for r in rows:
            candidate_phone = (bc.whatsapp or r.phone or "").lower()
            if candidate_phone:
                o = s.execute(select(OptOut).where(OptOut.method == "whatsapp").where(OptOut.value == candidate_phone)).scalars().first()
                if o:
                    out.append({"lead_id": r.id, "status": "skipped", "reason": "opt_out", "price": None})
                    continue
            tier = _tier_for(r.industry)
            base_price = LEAD_PRICING.get(tier, 0)
            price = base_price
            reason = None
            status = "skipped"

            if not active and not trial_active and not plan:
                reason = "inactive"
                out.append({"lead_id": r.id, "status": status, "reason": reason, "price": None})
                inc_skip_inactive(business_client_id, "whatsapp", r.industry)
                continue

            if plan:
                cap = int(plan.get("lead_cap", 0))
                if delivered_count_month >= cap:
                    reason = "cap_reached_subscription"
                    out.append({"lead_id": r.id, "status": status, "reason": reason, "price": None})
                    inc_skip_cap(business_client_id, "whatsapp", r.industry)
                    continue
                discount = float(plan.get("discount", 0))
                price = max(0, round(base_price * (1 - discount), 2))
            else:
                cap = int(PAY_PER_LEAD_CAP.get(tier, 0))
                if tier not in tier_counts:
                    tier_counts[tier] = s.execute(
                        select(func.count(DeliveredLead.id))
                        .join(QualifiedLead, QualifiedLead.id == DeliveredLead.qualified_lead_id)
                        .where(DeliveredLead.business_client_id == business_client_id)
                        .where(DeliveredLead.delivered_at >= start)
                        .where(DeliveredLead.delivered_at < end)
                        .where(QualifiedLead.industry == r.industry)
                    ).scalar_one()
                if tier_counts[tier] >= cap:
                    reason = "cap_reached_ppl"
                    out.append({"lead_id": r.id, "status": status, "reason": reason, "price": None})
                    inc_skip_cap(business_client_id, "whatsapp", r.industry)
                    continue

            if trial_active and trial_used < int(TRIAL_CONFIG.get("leads", 0)):
                price = 0
                trial_used += 1
                inc_trial_used(business_client_id, "whatsapp", r.industry)

            try:
                send_status = _send_whatsapp_via_twilio(bc.whatsapp or r.phone, "New qualified lead")
                if str(send_status.get("status", "")).startswith("error"):
                    raise RuntimeError(send_status.get("status"))
                record_delivery(r.id, business_client_id, "whatsapp")
                delivered_count_month += 1
                if not plan:
                    tier_counts[tier] = tier_counts.get(tier, 0) + 1
                status = "delivered"
                out.append({"lead_id": r.id, "status": status, "reason": None, "price": price})
                inc_success(business_client_id, "whatsapp", r.industry)
            except Exception as e:
                try:
                    b = Bounce(method="whatsapp", target=candidate_phone or "", reason=str(e), created_at=datetime.utcnow())
                    s.add(b)
                    s.commit()
                except Exception:
                    s.rollback()
                reason = f"error:{e}"
                out.append({"lead_id": r.id, "status": "failed", "reason": reason, "price": None})

        total = len(rows)
        delivered = len([x for x in out if x["status"] == "delivered"])
        skipped_cap = len([x for x in out if (x["reason"] or "").startswith("cap_reached")])
        skipped_inactive = len([x for x in out if x["reason"] == "inactive"])
        logging.info("{\"event\":\"whatsapp_summary\",\"processed\":%d,\"delivered\":%d,\"skipped_cap\":%d,\"skipped_inactive\":%d,\"trial_used\":%d}" % (total, delivered, skipped_cap, skipped_inactive, trial_used))
        return out
    finally:
        s.close()
