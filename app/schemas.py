from pydantic import BaseModel, Field, field_validator
from typing import Optional, List
from datetime import datetime
import uuid

class VisitorCreate(BaseModel):
    display_name: str = Field(min_length=1, max_length=80)

class ConversationOut(BaseModel):
    id: uuid.UUID
    visitor_name: str
    last_activity_at: datetime
    status: str

class MessageOut(BaseModel):
    id: uuid.UUID
    conversation_id: uuid.UUID
    sender: str
    content: str
    created_at: datetime

class AdminLoginRequest(BaseModel):
    code: str = Field(min_length=6, max_length=6, pattern=r'^\d{6}$')

class AdminLoginResponse(BaseModel):
    token: str
    expires_at: datetime

class OTPRequestResponse(BaseModel):
    sent: bool

class SendAdminMessage(BaseModel):
    conversation_id: uuid.UUID
    content: str = Field(min_length=1, max_length=2000)

