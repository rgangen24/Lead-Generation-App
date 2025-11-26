from pathlib import Path
from fastapi.testclient import TestClient

import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from app.main import app
from app.db import DB_PATH, init_db


def setup_function():
    if Path(DB_PATH).exists():
        Path(DB_PATH).unlink()
    init_db()


client = TestClient(app)


def test_create_and_get_lead():
    payload = {
        "name": "Alice",
        "email": "alice@example.com",
        "phone": "1234567890",
        "source": "web",
        "notes": "first contact",
    }
    r = client.post("/leads", json=payload)
    assert r.status_code == 201
    created = r.json()
    assert created["id"] > 0
    rid = created["id"]
    r = client.get(f"/leads/{rid}")
    assert r.status_code == 200
    got = r.json()
    assert got["name"] == "Alice"


def test_list_and_update_and_delete():
    p1 = {"name": "Bob", "email": "bob@example.com"}
    p2 = {"name": "Carol", "email": "carol@example.com"}
    r1 = client.post("/leads", json=p1)
    r2 = client.post("/leads", json=p2)
    assert r1.status_code == 201
    assert r2.status_code == 201
    r = client.get("/leads")
    assert r.status_code == 200
    items = r.json()
    assert len(items) >= 2
    rid = items[0]["id"]
    r = client.put(f"/leads/{rid}", json={"notes": "updated"})
    assert r.status_code == 200
    updated = r.json()
    assert updated["notes"] == "updated"
    r = client.delete(f"/leads/{rid}")
    assert r.status_code == 204
    r = client.get(f"/leads/{rid}")
    assert r.status_code == 404
