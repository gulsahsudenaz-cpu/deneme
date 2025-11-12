import uuid
from datetime import datetime, timedelta
from sqlalchemy import String, Text, DateTime, Boolean, Integer, ForeignKey, Enum, Index
from sqlalchemy.dialects.postgresql import UUID, BIGINT
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db import Base

class Visitor(Base):
    __tablename__ = "visitors"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    display_name: Mapped[str] = mapped_column(String(80), nullable=False)
    client_ip: Mapped[str] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    conversations: Mapped[list["Conversation"]] = relationship(back_populates="visitor", cascade="all, delete-orphan")

class Conversation(Base):
    __tablename__ = "conversations"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    visitor_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("visitors.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(String(16), default="open")  # open|closed|deleted
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_activity_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    visitor: Mapped["Visitor"] = relationship(back_populates="conversations")
    messages: Mapped[list["Message"]] = relationship(back_populates="conversation", cascade="all, delete-orphan")
    telegram_links: Mapped[list["TelegramLink"]] = relationship(back_populates="conversation", cascade="all, delete-orphan")

Index("idx_conv_visitor_created", Conversation.visitor_id, Conversation.created_at)
Index("idx_conv_status_activity", Conversation.status, Conversation.last_activity_at)

class Message(Base):
    __tablename__ = "messages"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"))
    sender: Mapped[str] = mapped_column(String(16))  # visitor|admin|telegram|system
    message_type: Mapped[str] = mapped_column(String(16), default="text")  # text|image|audio
    content: Mapped[str] = mapped_column(Text)  # text content or file description
    file_path: Mapped[str | None] = mapped_column(String(512), nullable=True)  # file path for media
    file_size: Mapped[int | None] = mapped_column(Integer, nullable=True)  # file size in bytes
    file_mime: Mapped[str | None] = mapped_column(String(64), nullable=True)  # MIME type
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    read_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)  # Message read receipt
    edited_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)  # Message edit timestamp

    conversation: Mapped["Conversation"] = relationship(back_populates="messages")

Index("idx_msg_conv_created", Message.conversation_id, Message.created_at)
Index("idx_msg_sender", Message.sender)
Index("idx_msg_type", Message.message_type)

class AdminOTP(Base):
    __tablename__ = "admin_otps"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code_hash: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    used: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

class AdminSession(Base):
    __tablename__ = "admin_sessions"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    token: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    client_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(256), nullable=True)

class TelegramLink(Base):
    __tablename__ = "telegram_links"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"))
    tg_chat_id: Mapped[int] = mapped_column(BIGINT, index=True)
    tg_message_id: Mapped[int] = mapped_column(Integer, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

    conversation: Mapped["Conversation"] = relationship(back_populates="telegram_links")

Index("idx_tg_link_conv_chat_msg", TelegramLink.conversation_id, TelegramLink.tg_chat_id, TelegramLink.tg_message_id)

class AdminActivityLog(Base):
    __tablename__ = "admin_activity_logs"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("admin_sessions.id", ondelete="CASCADE"))
    action: Mapped[str] = mapped_column(String(64))  # login, logout, send_message, delete_conversation, etc.
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    details: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON details
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

Index("idx_admin_activity_session", AdminActivityLog.session_id, AdminActivityLog.created_at)
Index("idx_admin_activity_action", AdminActivityLog.action, AdminActivityLog.created_at)

class ConversationTag(Base):
    __tablename__ = "conversation_tags"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"))
    tag: Mapped[str] = mapped_column(String(32))  # urgent, resolved, pending, etc.
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

Index("idx_conv_tag", ConversationTag.conversation_id, ConversationTag.tag)

