import logging
from datetime import datetime, timedelta
from sqlalchemy import select
from lead_generation_app.config.pricing import BASE_PLANS, GRACE_PERIOD_DAYS, AUTO_DOWNGRADE
from lead_generation_app.database.database import get_session
from lead_generation_app.database.models import Payment, BusinessClient


def record_payment(business_client_id, plan_name, amount, payment_date=None, payment_status="paid"):
    s = get_session()
    try:
        bc = s.execute(select(BusinessClient).where(BusinessClient.id == business_client_id)).scalars().first()
        if not bc:
            logging.info("{\"event\":\"payment_skipped\",\"reason\":\"business_client_missing\"}")
            return None
        row = Payment(
            business_client_id=business_client_id,
            plan_name=plan_name,
            amount=amount,
            payment_date=payment_date or datetime.utcnow(),
            payment_status=payment_status,
        )
        s.add(row)
        s.commit()
        logging.info("{\"event\":\"payment_recorded\",\"business_client_id\":%d,\"plan\":\"%s\",\"status\":\"%s\"}" % (business_client_id, plan_name or "", payment_status))
        return row.id
    except Exception as e:
        s.rollback()
        logging.error("{\"event\":\"payment_error\",\"error\":\"%s\"}" % str(e).replace("\"","'"))
        raise
    finally:
        s.close()


def get_payments_by_client(business_client_id):
    s = get_session()
    try:
        rows = s.execute(select(Payment).where(Payment.business_client_id == business_client_id)).scalars().all()
        logging.info("{\"event\":\"payments_fetched\",\"business_client_id\":%d,\"count\":%d}" % (business_client_id, len(rows)))
        return rows
    finally:
        s.close()


def update_subscription(business_client_id, plan_name, number_of_users=None, payment_status="paid"):
    s = get_session()
    try:
        bc = s.execute(select(BusinessClient).where(BusinessClient.id == business_client_id)).scalars().first()
        if not bc:
            logging.info("{\"event\":\"subscription_update_skipped\",\"reason\":\"client_missing\"}")
            return False
        plan = BASE_PLANS.get(plan_name)
        if not plan:
            logging.info("{\"event\":\"subscription_update_skipped\",\"reason\":\"plan_missing\"}")
            return False
        if payment_status and payment_status.lower() in ("paid", "success"):
            bc.subscription_plan = plan_name
            if number_of_users is not None:
                bc.number_of_users = number_of_users
            bc.next_billing_date = datetime.utcnow() + timedelta(days=int(plan.get("period_days", 30)))
            s.commit()
            logging.info("{\"event\":\"subscription_updated\",\"business_client_id\":%d,\"plan\":\"%s\"}" % (business_client_id, plan_name))
            return True
        else:
            bc.subscription_plan = None
            s.commit()
            logging.info("{\"event\":\"subscription_deactivated\",\"reason\":\"failed_payment\"}")
            return False
    except Exception as e:
        s.rollback()
        logging.error("{\"event\":\"subscription_update_error\",\"error\":\"%s\"}" % str(e).replace("\"","'"))
        raise
    finally:
        s.close()


def is_client_active(business_client_id):
    s = get_session()
    try:
        bc = s.execute(select(BusinessClient).where(BusinessClient.id == business_client_id)).scalars().first()
        if not bc:
            return False
        paid = s.execute(
            select(Payment).where(Payment.business_client_id == business_client_id).where(
                Payment.payment_status.in_(['paid', 'success'])
            )
        ).scalars().first()
        if not bc.subscription_plan:
            return paid is not None
        if not bc.next_billing_date:
            return False
        now = datetime.utcnow()
        if bc.next_billing_date <= now and bc.next_billing_date + timedelta(days=GRACE_PERIOD_DAYS) <= now:
            return False
        return paid is not None
    finally:
        s.close()


def check_upcoming_billing(threshold_days=7):
    s = get_session()
    try:
        now = datetime.utcnow()
        soon = now + timedelta(days=threshold_days)
        rows = s.execute(select(BusinessClient)).scalars().all()
        due = [c for c in rows if c.next_billing_date and now <= c.next_billing_date <= soon]
        logging.info("{\"event\":\"billing_upcoming\",\"count\":%d,\"threshold_days\":%d}" % (len(due), threshold_days))
        return due
    finally:
        s.close()


def deactivate_expired_clients():
    s = get_session()
    try:
        now = datetime.utcnow()
        rows = s.execute(select(BusinessClient)).scalars().all()
        count = 0
        for c in rows:
            if AUTO_DOWNGRADE and c.next_billing_date and c.next_billing_date + timedelta(days=GRACE_PERIOD_DAYS) < now:
                c.subscription_plan = None
                count += 1
        s.commit()
        logging.info("{\"event\":\"expired_clients_deactivated\",\"count\":%d}" % count)
        return count
    except Exception as e:
        s.rollback()
        logging.error("{\"event\":\"deactivate_error\",\"error\":\"%s\"}" % str(e).replace("\"","'"))
        raise
    finally:
        s.close()


def generate_invoice(business_client_id):
    s = get_session()
    try:
        bc = s.execute(select(BusinessClient).where(BusinessClient.id == business_client_id)).scalars().first()
        if not bc or not bc.subscription_plan:
            return None
        plan = BASE_PLANS.get(bc.subscription_plan)
        if not plan:
            return None
        amount = plan.get("price", 0)
        row_id = record_payment(business_client_id, plan_name=bc.subscription_plan, amount=amount, payment_status="due")
        logging.info("{\"event\":\"invoice_generated\",\"business_client_id\":%d,\"amount\":%s}" % (business_client_id, str(amount)))
        return row_id
    finally:
        s.close()


def settle_invoice(payment_id):
    s = get_session()
    try:
        row = s.execute(select(Payment).where(Payment.id == payment_id)).scalars().first()
        if not row:
            return False
        row.payment_status = "paid"
        s.commit()
        logging.info("{\"event\":\"invoice_settled\",\"payment_id\":%d}" % payment_id)
        return True
    finally:
        s.close()
