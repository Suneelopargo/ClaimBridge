CREATE TABLE IF NOT EXISTS activity_logs (
    id SERIAL PRIMARY KEY,
    username VARCHAR(100),
    action_type VARCHAR(100) NOT NULL,
    target VARCHAR(200) NOT NULL,
    details VARCHAR(1000),
    ip_address VARCHAR(50),
    timestamp TIMESTAMP NOT NULL DEFAULT timezone('Asia/Kolkata', now())
);

ALTER TABLE activity_logs
    ALTER COLUMN timestamp SET DEFAULT timezone('Asia/Kolkata', now());

CREATE INDEX IF NOT EXISTS ix_activity_logs_username ON activity_logs (username);
CREATE INDEX IF NOT EXISTS ix_activity_logs_action_type ON activity_logs (action_type);
CREATE INDEX IF NOT EXISTS ix_activity_logs_target ON activity_logs (target);
CREATE INDEX IF NOT EXISTS ix_activity_logs_timestamp ON activity_logs (timestamp DESC);
