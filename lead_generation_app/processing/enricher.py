import json
from urllib.parse import urlparse
from urllib.request import urlopen

def _ensure_scheme(url):
    if not url:
        return None
    p = urlparse(url)
    if p.scheme:
        return url
    return "http://" + url

def enrich_leads(lead):
    """
    Enrich a single qualified lead and return it.
    """
    site_ok = False
    content_len = 0
    kw_hits = []
    u = _ensure_scheme(lead.get("website"))
    if u:
        try:
            with urlopen(u, timeout=8) as resp:
                body = resp.read()
                content_len = len(body)
                text = body[:5000].decode("utf-8", errors="ignore").lower()
                for k in ["contact", "review", "rating", "about"]:
                    if k in text:
                        kw_hits.append(k)
                site_ok = True
        except Exception:
            site_ok = False

    summary = "site_ok=" + ("true" if site_ok else "false") + ", content_len=" + str(content_len)
    enriched = {
        "site_ok": site_ok,
        "content_len": content_len,
        "keywords": kw_hits,
    }

    lead["summary"] = summary
    lead["enriched_data_json"] = json.dumps(enriched)
    lead["verified_status"] = bool(site_ok)
    return lead
