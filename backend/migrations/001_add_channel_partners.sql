-- Migration: add channel_partners and indexes
CREATE TABLE IF NOT EXISTS channel_partners (
  id SERIAL PRIMARY KEY,
  name VARCHAR(150) NOT NULL,
  phone VARCHAR(50),
  email VARCHAR(200),
  address TEXT,
  trainer_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
  created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_channel_partners_trainer_id ON channel_partners(trainer_id);
CREATE INDEX IF NOT EXISTS idx_channel_partners_name_email ON channel_partners(name, email);
