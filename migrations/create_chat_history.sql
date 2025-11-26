-- Create chat history table for conversation tracking
-- Migration: create_chat_history
-- Date: 2025-11-17

CREATE TABLE IF NOT EXISTS chat_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id TEXT NOT NULL,
    user_id TEXT NOT NULL DEFAULT 'anonymous',
    message_index INTEGER NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content TEXT NOT NULL,
    query TEXT, -- Original user query (for user messages)
    answer TEXT, -- AI response (for assistant messages)
    doc_id TEXT, -- Document context if specified
    intent TEXT, -- Query intent (search, metadata, visual, etc)
    citations JSONB, -- Citations array from response
    metadata JSONB, -- Additional metadata (chunks_used, images, etc)
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    CONSTRAINT chat_history_session_message UNIQUE (session_id, message_index)
);

-- Indexes for efficient queries
CREATE INDEX IF NOT EXISTS idx_chat_session_id ON chat_history(session_id);
CREATE INDEX IF NOT EXISTS idx_chat_user_id ON chat_history(user_id);
CREATE INDEX IF NOT EXISTS idx_chat_created_at ON chat_history(created_at);
CREATE INDEX IF NOT EXISTS idx_chat_session_order ON chat_history(session_id, message_index);

-- Add comments
COMMENT ON TABLE chat_history IS 'Stores conversation history for context-aware follow-up questions';
COMMENT ON COLUMN chat_history.session_id IS 'Unique session identifier for conversation thread';
COMMENT ON COLUMN chat_history.message_index IS 'Sequential message number within session (0, 1, 2, ...)';
COMMENT ON COLUMN chat_history.role IS 'Message sender: user or assistant';
COMMENT ON COLUMN chat_history.citations IS 'Array of citation objects with page, doc_id, doc_title, gdrive_link';

-- Function to get recent chat history for a session
CREATE OR REPLACE FUNCTION get_chat_history(
    p_session_id TEXT,
    p_limit INTEGER DEFAULT 5
)
RETURNS TABLE (
    message_index INTEGER,
    role TEXT,
    content TEXT,
    created_at TIMESTAMP WITH TIME ZONE
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        ch.message_index,
        ch.role,
        ch.content,
        ch.created_at
    FROM chat_history ch
    WHERE ch.session_id = p_session_id
    ORDER BY ch.message_index DESC
    LIMIT p_limit;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION get_chat_history IS 'Retrieves recent chat messages for a session in reverse chronological order';
