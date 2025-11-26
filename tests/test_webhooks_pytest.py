import json
import pytest
from datetime import datetime
from lead_generation_app.database.database import init_db, get_session
from lead_generation_app.database.models import BusinessClient, QualifiedLead, DeliveredLead, OptOut, Bounce, LeadSource, RawLead
from lead_generation_app.webhooks import handle_sendgrid_events, handle_twilio_event


@pytest.mark.integration
def test_sendgrid_unsubscribe_and_bounce_and_delivered():
    init_db()
    s = get_session()
    try:
        bc = BusinessClient(business_name="EmailClient", industry="restaurants", email="client@example.com")
        s.add(bc)
        s.commit()
        ls = LeadSource(source_name="restaurants_maps", industry="restaurants", platform_type="maps", scrape_url="", active_status=True)
        s.add(ls)
        s.commit()
        rl = RawLead(name="N", company_name="C", email="lead@example.com", phone="+1234567", website="https://example.com", industry="restaurants", source_id=ls.id, captured_at=datetime.utcnow(), raw_data_json="{}")
        s.add(rl)
        s.commit()
        ql = QualifiedLead(raw_lead_id=rl.id, name="N", company_name="C", phone="+1234567", whatsapp=None, email="lead@example.com", qualification_score=80, score_category="hot", industry="restaurants", summary="", enriched_data_json="{}", verified_status=True)
        s.add(ql)
        s.commit()
        dl = DeliveredLead(qualified_lead_id=ql.id, business_client_id=bc.id, delivered_at=datetime.utcnow(), delivery_method="email", opened_status=False)
        s.add(dl)
        s.commit()
        evs = [{"email": "lead@example.com", "event": "delivered"}, {"email": "lead@example.com", "event": "unsubscribe"}, {"email": "bounce@example.com", "event": "bounce", "reason": "hard"}]
        ok = handle_sendgrid_events(evs)
        assert ok
        dl2 = s.get(DeliveredLead, dl.id)
        assert dl2.opened_status is True
        oo = s.query(OptOut).filter(OptOut.method == "email", OptOut.value == "lead@example.com").all()
        assert len(oo) >= 1
        bb = s.query(Bounce).filter(Bounce.method == "email", Bounce.target == "bounce@example.com").all()
        assert len(bb) >= 1
    finally:
        s.close()


@pytest.mark.integration
def test_twilio_delivered_failed_and_stopped():
    init_db()
    s = get_session()
    try:
        bc = BusinessClient(business_name="WAClient", industry="restaurants", whatsapp="+15550000")
        s.add(bc)
        s.commit()
        ls = LeadSource(source_name="restaurants_maps", industry="restaurants", platform_type="maps", scrape_url="", active_status=True)
        s.add(ls)
        s.commit()
        rl = RawLead(name="N", company_name="C", email="wa@example.com", phone="+15551234", website="https://example.com", industry="restaurants", source_id=ls.id, captured_at=datetime.utcnow(), raw_data_json="{}")
        s.add(rl)
        s.commit()
        ql = QualifiedLead(raw_lead_id=rl.id, name="N", company_name="C", phone="+15551234", whatsapp=None, email="wa@example.com", qualification_score=80, score_category="hot", industry="restaurants", summary="", enriched_data_json="{}", verified_status=True)
        s.add(ql)
        s.commit()
        dl = DeliveredLead(qualified_lead_id=ql.id, business_client_id=bc.id, delivered_at=datetime.utcnow(), delivery_method="whatsapp", opened_status=False)
        s.add(dl)
        s.commit()
        ok1 = handle_twilio_event({"MessageStatus": "delivered", "To": "whatsapp:+15551234"})
        assert ok1
        dl2 = s.get(DeliveredLead, dl.id)
        assert dl2.opened_status is True
        ok2 = handle_twilio_event({"MessageStatus": "failed", "To": "+15559999"})
        assert ok2
        bb = s.query(Bounce).filter(Bounce.method == "whatsapp", Bounce.target == "+15559999").all()
        assert len(bb) >= 1
        ok3 = handle_twilio_event({"MessageStatus": "stopped", "To": "+15551234"})
        assert ok3
        oo = s.query(OptOut).filter(OptOut.method == "whatsapp", OptOut.value == "+15551234").all()
        assert len(oo) >= 1
    finally:
        s.close()
