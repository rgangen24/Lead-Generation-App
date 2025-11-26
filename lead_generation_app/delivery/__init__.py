import logging
from datetime import datetime
from lead_generation_app.database.database import get_session
from lead_generation_app.database.models import DeliveredLead, QualifiedLead, BusinessClient
from sqlalchemy import select


def record_delivery(qualified_lead_id, business_client_id, delivery_method, delivered_at=None, opened_status=False):
    s = get_session()
    try:
        ql = s.execute(select(QualifiedLead).where(QualifiedLead.id == qualified_lead_id)).scalars().first()
        bc = s.execute(select(BusinessClient).where(BusinessClient.id == business_client_id)).scalars().first()
        if not ql or not bc:
            logging.info("{\"event\":\"record_delivery_skip\",\"reason\":\"fk_missing\"}")
            return None
        existing = s.execute(
            select(DeliveredLead)
            .where(DeliveredLead.qualified_lead_id == qualified_lead_id)
            .where(DeliveredLead.business_client_id == business_client_id)
            .where(DeliveredLead.delivery_method == delivery_method)
        ).scalars().first()
        if existing:
            logging.info("{\"event\":\"record_delivery_skip\",\"reason\":\"duplicate\"}")
            return existing.id
        row = DeliveredLead(
            qualified_lead_id=qualified_lead_id,
            business_client_id=business_client_id,
            delivery_method=delivery_method,
            delivered_at=delivered_at or datetime.utcnow(),
            opened_status=opened_status,
        )
        s.add(row)
        s.commit()
        logging.info("{\"event\":\"record_delivery_ok\",\"qualified_lead_id\":%d,\"business_client_id\":%d,\"method\":\"%s\"}" % (qualified_lead_id, business_client_id, delivery_method))
        return row.id
    except Exception as e:
        s.rollback()
        logging.error("{\"event\":\"record_delivery_error\",\"error\":\"%s\"}" % str(e).replace("\"","'"))
        raise
    finally:
        s.close()


def mark_dashboard_delivery(qualified_lead_id, business_client_id):
    return record_delivery(qualified_lead_id, business_client_id, "dashboard")
