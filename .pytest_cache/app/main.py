from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .db import init_db, get_connection
from .models import Lead, LeadCreate, LeadUpdate
from .repository import create_lead, list_leads, get_lead, update_lead, delete_lead


app = FastAPI(title="Lead Generation API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup():
    init_db()


@app.get("/leads", response_model=list[Lead])
def get_leads():
    conn = get_connection()
    leads = list_leads(conn)
    conn.close()
    return leads


@app.get("/leads/{lead_id}", response_model=Lead)
def get_lead_by_id(lead_id: int):
    conn = get_connection()
    lead = get_lead(conn, lead_id)
    conn.close()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    return lead


@app.post("/leads", response_model=Lead, status_code=201)
def create_lead_endpoint(payload: LeadCreate):
    conn = get_connection()
    lead = create_lead(conn, payload)
    conn.close()
    return lead


@app.put("/leads/{lead_id}", response_model=Lead)
def update_lead_endpoint(lead_id: int, payload: LeadUpdate):
    conn = get_connection()
    lead = update_lead(conn, lead_id, payload)
    conn.close()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    return lead


@app.delete("/leads/{lead_id}", status_code=204)
def delete_lead_endpoint(lead_id: int):
    conn = get_connection()
    ok = delete_lead(conn, lead_id)
    conn.close()
    if not ok:
        raise HTTPException(status_code=404, detail="Lead not found")
