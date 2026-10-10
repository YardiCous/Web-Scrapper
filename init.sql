CREATE TABLE listings (
    id               SERIAL PRIMARY KEY,
    sku              TEXT NOT NULL,            
    source_platform  TEXT NOT NULL,           
    product_url      TEXT NOT NULL,
    title            TEXT,
    price            NUMERIC(10,2),
    currency         CHAR(3),                
    seller_id        TEXT,
    seller_name      TEXT,
    selling_since    DATE,
    rating           NUMERIC(3,2),          
    review_count     INTEGER DEFAULT 0,
    scraped_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (source_platform, product_url)  
);

CREATE TABLE reviews (
    id           SERIAL PRIMARY KEY,
    listing_id   INTEGER NOT NULL REFERENCES listings(id) ON DELETE CASCADE,
    text         TEXT,
    rating       SMALLINT NOT NULL CHECK (rating BETWEEN 1 AND 5),
    review_date  DATE
);

CREATE INDEX idx_listings_sku ON listings(sku);
CREATE INDEX idx_reviews_listing ON reviews(listing_id);
