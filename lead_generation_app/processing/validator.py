import re
from urllib.parse import urlparse


def _is_valid_email(v):
    if not v:
        return False
    return re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", v) is not None


def _is_valid_phone(v):
    if not v:
        return False
    digits = re.sub(r"\D", "", v)
    return len(digits) >= 7


def _is_valid_url(v):
    if not v:
        return False
    p = urlparse(v)
    if p.scheme and p.netloc:
        return True
    p = urlparse("http://" + v)
    return bool(p.netloc)


def validate_leads(leads):
    out = []
    for r in leads or []:
        email_ok = _is_valid_email(getattr(r, "email", None))
        phone_ok = _is_valid_phone(getattr(r, "phone", None))
        web_ok = _is_valid_url(getattr(r, "website", None))
        out.append(
            {
                "raw_lead_id": getattr(r, "id", None),
                "name": getattr(r, "name", None),
                "company_name": getattr(r, "company_name", None),
                "phone": (getattr(r, "phone", None) if phone_ok else None),
                "email": (getattr(r, "email", None) if email_ok else None),
                "website": (getattr(r, "website", None) if web_ok else None),
                "industry": getattr(r, "industry", None),
            }
        )
    return out
