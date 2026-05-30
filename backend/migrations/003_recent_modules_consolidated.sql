-- Consolidated migration for recent modules and inquiry reference enhancements

-- Franchise module
CREATE TABLE IF NOT EXISTS franchises (
  id SERIAL PRIMARY KEY,
  code VARCHAR(50) UNIQUE NOT NULL,
  name VARCHAR(150) NOT NULL,
  phone VARCHAR(50),
  address TEXT,
  created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS sales_executives (
  id SERIAL PRIMARY KEY,
  franchise_id INTEGER REFERENCES franchises(id) ON DELETE CASCADE,
  name VARCHAR(150) NOT NULL,
  phone VARCHAR(50),
  email VARCHAR(200),
  address TEXT,
  remarks TEXT,
  created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Channel partners module
CREATE TABLE IF NOT EXISTS channel_partners (
  id SERIAL PRIMARY KEY,
  name VARCHAR(150) NOT NULL,
  phone VARCHAR(50),
  email VARCHAR(200),
  address TEXT,
  trainer_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
  created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Inquiry reference enhancements
ALTER TABLE inquiries ADD COLUMN IF NOT EXISTS ref1_payment_method VARCHAR(20);
ALTER TABLE inquiries ADD COLUMN IF NOT EXISTS ref1_channel_partner_id INTEGER REFERENCES channel_partners(id) ON DELETE SET NULL;
ALTER TABLE inquiries ADD COLUMN IF NOT EXISTS ref1_franchise_id INTEGER REFERENCES franchises(id) ON DELETE SET NULL;
ALTER TABLE inquiries ADD COLUMN IF NOT EXISTS ref1_sales_exec_id INTEGER REFERENCES sales_executives(id) ON DELETE SET NULL;
ALTER TABLE inquiries ADD COLUMN IF NOT EXISTS ref2_payment_method VARCHAR(20);
ALTER TABLE inquiries ADD COLUMN IF NOT EXISTS ref3_payment_method VARCHAR(20);

-- Helpful indexes
CREATE INDEX IF NOT EXISTS idx_franchises_code ON franchises(code);
CREATE INDEX IF NOT EXISTS idx_sales_execs_franchise_id ON sales_executives(franchise_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_channel_partners_trainer_id ON channel_partners(trainer_id);
CREATE INDEX IF NOT EXISTS idx_channel_partners_name_email ON channel_partners(name, email);
