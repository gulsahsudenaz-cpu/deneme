-- Migration: Add file support to messages table
-- Version: 002
-- Description: Add columns for file attachments (images and audio)

-- Add new columns to messages table
ALTER TABLE messages 
ADD COLUMN IF NOT EXISTS message_type VARCHAR(16) DEFAULT 'text',
ADD COLUMN IF NOT EXISTS file_path VARCHAR(512),
ADD COLUMN IF NOT EXISTS file_size INTEGER,
ADD COLUMN IF NOT EXISTS file_mime VARCHAR(64);

-- Create index for message type
CREATE INDEX IF NOT EXISTS idx_msg_type ON messages(message_type);

-- Update existing messages to have message_type = 'text'
UPDATE messages SET message_type = 'text' WHERE message_type IS NULL;

-- Make message_type NOT NULL after setting default values
ALTER TABLE messages ALTER COLUMN message_type SET NOT NULL;