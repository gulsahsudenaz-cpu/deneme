ALTER TABLE messages ADD COLUMN IF NOT EXISTS message_type VARCHAR(16) DEFAULT 'text';
ALTER TABLE messages ADD COLUMN IF NOT EXISTS file_path VARCHAR(512);
ALTER TABLE messages ADD COLUMN IF NOT EXISTS file_size INTEGER;
ALTER TABLE messages ADD COLUMN IF NOT EXISTS file_mime VARCHAR(64);
CREATE INDEX IF NOT EXISTS idx_msg_type ON messages(message_type);
UPDATE messages SET message_type = 'text' WHERE message_type IS NULL;
ALTER TABLE messages ALTER COLUMN message_type SET NOT NULL;