from datetime import datetime
from typing import List, Optional
import sqlite3

from .models import Lead, LeadCreate, LeadUpdate


def _row_to_lead(row: sqlite3.Row) -> Lead:
    return Lead(
        id=row["id"],
        name=row["name"],
        email=row["email"],
        phone=row["phone"],
        source=row["source"],
        notes=row["notes"],
        created_at=row["created_at"],
    )


def create_lead(conn: sqlite3.Connection, payload: LeadCreate) -> Lead:
    cur = conn.cursor()
    created_at = datetime.utcnow().isoformat()
    cur.execute(
        "INSERT INTO leads (name, email, phone, source, notes, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        [payload.name, str(payload.email), payload.phone, payload.source, payload.notes, created_at],
    )
    conn.commit()
    lead_id = cur.lastrowid
    cur.execute("SELECT * FROM leads WHERE id = ?", [lead_id])
    return _row_to_lead(cur.fetchone())


def list_leads(conn: sqlite3.Connection) -> List[Lead]:
    cur = conn.cursor()
    cur.execute("SELECT * FROM leads ORDER BY id DESC")
    return [_row_to_lead(r) for r in cur.fetchall()]


def get_lead(conn: sqlite3.Connection, lead_id: int) -> Optional[Lead]:
    cur = conn.cursor()
    cur.execute("SELECT * FROM leads WHERE id = ?", [lead_id])
    row = cur.fetchone()
    return _row_to_lead(row) if row else None


def update_lead(conn: sqlite3.Connection, lead_id: int, payload: LeadUpdate) -> Optional[Lead]:
    cur = conn.cursor()
    cur.execute("SELECT * FROM leads WHERE id = ?", [lead_id])
    row = cur.fetchone()
    if not row:
        return None
    current = _row_to_lead(row)
    name = payload.name if payload.name is not None else current.name
    email = str(payload.email) if payload.email is not None else current.email
    phone = payload.phone if payload.phone is not None else current.phone
    source = payload.source if payload.source is not None else current.source
    notes = payload.notes if payload.notes is not None else current.notes
    cur.execute(
        "UPDATE leads SET name = ?, email = ?, phone = ?, source = ?, notes = ? WHERE id = ?",
        [name, email, phone, source, notes, lead_id],
    )
    conn.commit()
    cur.execute("SELECT * FROM leads WHERE id = ?", [lead_id])
    return _row_to_lead(cur.fetchone())


def delete_lead(conn: sqlite3.Connection, lead_id: int) -> bool:
    cur = conn.cursor()
    cur.execute("DELETE FROM leads WHERE id = ?", [lead_id])
    conn.commit()
    return cur.rowcount > 0
