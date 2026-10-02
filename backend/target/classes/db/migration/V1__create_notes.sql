CREATE TABLE notes (
    id UUID PRIMARY KEY,
    title VARCHAR(160) NOT NULL,
    content VARCHAR(10000) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL
);
CREATE INDEX notes_updated_at_idx ON notes (updated_at DESC, id);
