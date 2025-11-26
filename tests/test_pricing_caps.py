import os
import unittest
from datetime import datetime
from lead_generation_app.database.database import init_db, get_session
from lead_generation_app.database.models import LeadSource, RawLead, QualifiedLead, BusinessClient, DeliveredLead
from lead_generation_app.config.pricing import BASE_PLANS, INDUSTRY_TIERS
from lead_generation_app.payments import update_subscription, record_payment
from lead_generation_app.delivery.whatsapp_sender import send_whatsapp_leads
from lead_generation_app.delivery.email_sender import send_email_leads


class PricingCapsTests(unittest.TestCase):
    def setUp(self):
        init_db()
        self.s = get_session()

    def tearDown(self):
        self.s.close()

    def _seed_leads(self, industry, n=600):
        ls = LeadSource(source_name=f"{industry}_maps", industry=industry, platform_type="maps", scrape_url="", active_status=True)
        self.s.add(ls)
        self.s.commit()
        for i in range(n):
            rl = RawLead(name=f"L{i}", company_name=f"{industry} Co", email=f"{i}@{industry}.example.com", phone=f"+1{i:07d}", website="https://example.com", industry=industry, source_id=ls.id, captured_at=datetime.utcnow(), raw_data_json="{}")
            self.s.add(rl)
            self.s.flush()
            ql = QualifiedLead(raw_lead_id=rl.id, name=rl.name, company_name=rl.company_name, phone=rl.phone, whatsapp=None, email=rl.email, qualification_score=80, score_category="hot", industry=industry, summary="", enriched_data_json="{}", verified_status=True)
            self.s.add(ql)
        self.s.commit()

    def test_subscription_caps(self):
        bc = BusinessClient(business_name="Sub_Starter", industry="restaurants", email="s@example.com", phone="+1000000000", whatsapp="+1000000000")
        self.s.add(bc)
        self.s.commit()
        update_subscription(bc.id, plan_name="starter", number_of_users=1, payment_status="paid")
        self._seed_leads("restaurants", n=600)
        wl = send_whatsapp_leads(business_client_id=bc.id)
        el = send_email_leads(business_client_id=bc.id)
        delivered = len([x for x in wl if x.get("status") == "delivered"]) + len([x for x in el if x.get("status") == "delivered"])
        self.assertEqual(delivered, BASE_PLANS["starter"]["lead_cap"])

    def test_pay_per_lead_caps(self):
        bc = BusinessClient(business_name="PPL_Fitness", industry="fitness", email="p@example.com", phone="+2000000000", whatsapp="+2000000000")
        self.s.add(bc)
        self.s.commit()
        record_payment(bc.id, plan_name="ppl", amount=0, payment_status="paid")
        self._seed_leads("fitness", n=300)
        wl = send_whatsapp_leads(business_client_id=bc.id)
        el = send_email_leads(business_client_id=bc.id)
        delivered = len([x for x in wl if x.get("status") == "delivered"]) + len([x for x in el if x.get("status") == "delivered"])
        cap = 100
        self.assertEqual(delivered, cap)


if __name__ == "__main__":
    unittest.main()
