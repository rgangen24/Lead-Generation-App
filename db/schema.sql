CREATE TABLE lead_sources (
  id INTEGER PRIMARY KEY,
  source_name TEXT,
  industry TEXT,
  platform_type TEXT,
  scrape_url TEXT,
  active_status BOOLEAN
);

CREATE TABLE raw_leads (
  id INTEGER PRIMARY KEY,
  name TEXT,
  company_name TEXT,
  email TEXT,
  phone TEXT,
  website TEXT,
  industry TEXT,
  source_id INTEGER,
  captured_at TIMESTAMP,
  raw_data_json TEXT,
  FOREIGN KEY (source_id) REFERENCES lead_sources(id)
);

CREATE TABLE qualified_leads (
  id INTEGER PRIMARY KEY,
  raw_lead_id INTEGER,
  name TEXT,
  company_name TEXT,
  phone TEXT,
  whatsapp TEXT,
  email TEXT,
  qualification_score INTEGER,
  score_category TEXT,
  industry TEXT,
  summary TEXT,
  enriched_data_json TEXT,
  verified_status BOOLEAN,
  FOREIGN KEY (raw_lead_id) REFERENCES raw_leads(id)
);

CREATE TABLE business_clients (
  id INTEGER PRIMARY KEY,
  business_name TEXT,
  industry TEXT,
  email TEXT,
  phone TEXT,
  whatsapp TEXT,
  subscription_plan TEXT,
  number_of_users INTEGER,
  next_billing_date TIMESTAMP
);

CREATE TABLE delivered_leads (
  id INTEGER PRIMARY KEY,
  qualified_lead_id INTEGER,
  business_client_id INTEGER,
  delivered_at TIMESTAMP,
  delivery_method TEXT,
  opened_status BOOLEAN,
  FOREIGN KEY (qualified_lead_id) REFERENCES qualified_leads(id),
  FOREIGN KEY (business_client_id) REFERENCES business_clients(id)
);

CREATE TABLE payments (
  id INTEGER PRIMARY KEY,
  business_client_id INTEGER,
  plan_name TEXT,
  amount DECIMAL(10,2),
  payment_date TIMESTAMP,
  payment_status TEXT,
  FOREIGN KEY (business_client_id) REFERENCES business_clients(id)
);

CREATE TABLE industry_rules (
  id INTEGER PRIMARY KEY,
  industry TEXT,
  qualification_questions TEXT,
  scoring_rules TEXT,
  enrichment_notes TEXT
);