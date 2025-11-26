from pydantic import BaseModel, EmailStr
from typing import Optional


class LeadBase(BaseModel):
    name: str
    email: EmailStr
    phone: Optional[str] = None
    source: Optional[str] = None
    notes: Optional[str] = None


class LeadCreate(LeadBase):
    pass


class Lead(LeadBase):
    id: int
    created_at: str


class LeadUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    source: Optional[str] = None
    notes: Optional[str] = None
