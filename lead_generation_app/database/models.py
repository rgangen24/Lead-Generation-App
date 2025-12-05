from sqlalchemy import Column, Integer, Text, Boolean, DateTime, Numeric, ForeignKey
from sqlalchemy.orm import declarative_base, relationship

try:
    from sqlalchemy.dialects.postgresql import JSON
except Exception:
    JSON = Text

Base = declarative_base()


class LeadSource(Base):
    __tablename__ = "lead_sources"

    id = Column(Integer, primary_key=True)
    source_name = Column(Text)
    industry = Column(Text)
    platform_type = Column(Text)
    scrape_url = Column(Text)
    active_status = Column(Boolean)

    raw_leads = relationship("RawLead", back_populates="source")


class RawLead(Base):
    __tablename__ = "raw_leads"

    id = Column(Integer, primary_key=True)
    name = Column(Text)
    company_name = Column(Text)
    email = Column(Text)
    phone = Column(Text)
    website = Column(Text)
    industry = Column(Text)
    source_id = Column(Integer, ForeignKey("lead_sources.id"), nullable=False)
    captured_at = Column(DateTime)
    raw_data_json = Column(JSON)

    source = relationship("LeadSource", back_populates="raw_leads")
    qualified_lead = relationship("QualifiedLead", back_populates="raw_lead", uselist=False)


class QualifiedLead(Base):
    __tablename__ = "qualified_leads"

    id = Column(Integer, primary_key=True)
    raw_lead_id = Column(Integer, ForeignKey("raw_leads.id"), nullable=False)
    name = Column(Text)
    company_name = Column(Text)
    phone = Column(Text)
    whatsapp = Column(Text)
    email = Column(Text)
    qualification_score = Column(Integer)
    score_category = Column(Text)
    industry = Column(Text)
    summary = Column(Text)
    enriched_data_json = Column(JSON)
    verified_status = Column(Boolean)

    raw_lead = relationship("RawLead", back_populates="qualified_lead")
    delivered_leads = relationship("DeliveredLead", back_populates="qualified_lead")


class BusinessClient(Base):
    __tablename__ = "business_clients"

    id = Column(Integer, primary_key=True)
    business_name = Column(Text)
    industry = Column(Text)
    email = Column(Text)
    phone = Column(Text)
    whatsapp = Column(Text)
    subscription_plan = Column(Text)
    number_of_users = Column(Integer)
    next_billing_date = Column(DateTime)
    is_deleted = Column(Boolean, default=False)
    deleted_at = Column(DateTime)

    delivered_leads = relationship("DeliveredLead", back_populates="business_client")
    payments = relationship("Payment", back_populates="business_client")


class DeliveredLead(Base):
    __tablename__ = "delivered_leads"

    id = Column(Integer, primary_key=True)
    qualified_lead_id = Column(Integer, ForeignKey("qualified_leads.id"), nullable=False)
    business_client_id = Column(Integer, ForeignKey("business_clients.id"), nullable=False)
    delivered_at = Column(DateTime)
    delivery_method = Column(Text)
    opened_status = Column(Boolean)

    qualified_lead = relationship("QualifiedLead", back_populates="delivered_leads")
    business_client = relationship("BusinessClient", back_populates="delivered_leads")


class Payment(Base):
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True)
    business_client_id = Column(Integer, ForeignKey("business_clients.id"), nullable=False)
    plan_name = Column(Text)
    amount = Column(Numeric(10, 2))
    payment_date = Column(DateTime)
    payment_status = Column(Text)

    business_client = relationship("BusinessClient", back_populates="payments")


class IndustryRule(Base):
    __tablename__ = "industry_rules"

    id = Column(Integer, primary_key=True)
    industry = Column(Text)
    qualification_questions = Column(JSON)
    scoring_rules = Column(JSON)
    enrichment_notes = Column(JSON)


class OptOut(Base):
    __tablename__ = "opt_outs"

    id = Column(Integer, primary_key=True)
    method = Column(Text)
    value = Column(Text)
    created_at = Column(DateTime)


class Bounce(Base):
    __tablename__ = "bounces"

    id = Column(Integer, primary_key=True)
    method = Column(Text)
    target = Column(Text)
    reason = Column(Text)
    created_at = Column(DateTime)


class SourceAttribution(Base):
    __tablename__ = "source_attributions"

    id = Column(Integer, primary_key=True)
    raw_lead_id = Column(Integer, ForeignKey("raw_leads.id"))
    source_platform = Column(Text)
    source_reference = Column(Text)
    campaign = Column(Text)
    collected_at = Column(DateTime)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    username = Column(Text, unique=True)
    hashed_password = Column(Text)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime)
