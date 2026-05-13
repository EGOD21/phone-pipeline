CREATE TABLE IF NOT EXISTS search_partitions (
  id BIGSERIAL PRIMARY KEY,
  state TEXT NOT NULL,
  city TEXT NOT NULL,
  category TEXT NOT NULL,
  page INTEGER NOT NULL DEFAULT 1,
  status TEXT NOT NULL DEFAULT 'pending',
  attempts INTEGER NOT NULL DEFAULT 0,
  last_error TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (state, city, category, page)
);

CREATE TABLE IF NOT EXISTS raw_businesses (
  id BIGSERIAL PRIMARY KEY,
  source TEXT NOT NULL,
  source_ref TEXT NOT NULL,
  source_url TEXT,
  raw_payload JSONB NOT NULL,
  normalized BOOLEAN NOT NULL DEFAULT false,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (source, source_ref)
);

CREATE TABLE IF NOT EXISTS businesses (
  id BIGSERIAL PRIMARY KEY,
  raw_business_id BIGINT REFERENCES raw_businesses(id),
  source TEXT NOT NULL,
  source_ref TEXT NOT NULL,
  source_url TEXT,
  business_name TEXT NOT NULL,
  canonical_name TEXT NOT NULL,
  category TEXT,
  address1 TEXT,
  city TEXT,
  state TEXT,
  postal_code TEXT,
  phone TEXT,
  website TEXT,
  website_domain TEXT,
  confidence_score INTEGER NOT NULL DEFAULT 0,
  duplicate_of BIGINT REFERENCES businesses(id),
  status TEXT NOT NULL DEFAULT 'pending',
  rejection_reason TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (source, source_ref)
);

CREATE INDEX IF NOT EXISTS businesses_phone_idx ON businesses (phone);
CREATE INDEX IF NOT EXISTS businesses_canonical_name_idx ON businesses (canonical_name);
CREATE INDEX IF NOT EXISTS businesses_status_idx ON businesses (status);

CREATE TABLE IF NOT EXISTS suppressions (
  id BIGSERIAL PRIMARY KEY,
  type TEXT NOT NULL CHECK (type IN ('phone', 'domain')),
  value TEXT NOT NULL,
  reason TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (type, value)
);
