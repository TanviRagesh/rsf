-- Migration: extend inquiry references with payment method and entity links
ALTER TABLE inquiries ADD COLUMN IF NOT EXISTS ref1_payment_method VARCHAR(20);
ALTER TABLE inquiries ADD COLUMN IF NOT EXISTS ref1_channel_partner_id INTEGER REFERENCES channel_partners(id) ON DELETE SET NULL;
ALTER TABLE inquiries ADD COLUMN IF NOT EXISTS ref1_franchise_id INTEGER REFERENCES franchises(id) ON DELETE SET NULL;
ALTER TABLE inquiries ADD COLUMN IF NOT EXISTS ref1_sales_exec_id INTEGER REFERENCES sales_executives(id) ON DELETE SET NULL;
ALTER TABLE inquiries ADD COLUMN IF NOT EXISTS ref2_payment_method VARCHAR(20);
ALTER TABLE inquiries ADD COLUMN IF NOT EXISTS ref3_payment_method VARCHAR(20);
