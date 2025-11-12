-- Version: 2.0.0
-- Date: 2024

-- Ensure pgcrypto is available for gen_random_uuid
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- Add read_at and edited_at to messages
ALTER TABLE messages 
ADD COLUMN IF NOT EXISTS read_at TIMESTAMP,
ADD COLUMN IF NOT EXISTS edited_at TIMESTAMP;

-- Add client_ip and user_agent to admin_sessions
ALTER TABLE admin_sessions 
ADD COLUMN IF NOT EXISTS client_ip VARCHAR(64),
ADD COLUMN IF NOT EXISTS user_agent VARCHAR(256);

-- Create admin_activity_logs table
CREATE TABLE IF NOT EXISTS admin_activity_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES admin_sessions(id) ON DELETE CASCADE,
    action VARCHAR(64) NOT NULL,
    conversation_id UUID,
    details TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_admin_activity_session ON admin_activity_logs(session_id, created_at);
CREATE INDEX IF NOT EXISTS idx_admin_activity_action ON admin_activity_logs(action, created_at);

-- Create conversation_tags table
CREATE TABLE IF NOT EXISTS conversation_tags (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    tag VARCHAR(32) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_conv_tag ON conversation_tags(conversation_id, tag);

-- Add indexes for better search performance
CREATE INDEX IF NOT EXISTS idx_message_content_search ON messages USING gin(to_tsvector('english', content));
CREATE INDEX IF NOT EXISTS idx_admin_sessions_client_ip ON admin_sessions(client_ip);
