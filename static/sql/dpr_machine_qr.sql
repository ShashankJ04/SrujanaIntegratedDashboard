-- Machine QR codes for DPR shop-floor scan (run once on MySQL).
-- Idempotent: safe to re-run; existing machine_id rows are left unchanged.

CREATE TABLE IF NOT EXISTS dpr_machine_qr (
  machine_id VARCHAR(128) NOT NULL,
  qr_token VARCHAR(64) NOT NULL,
  png_filename VARCHAR(256) NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (machine_id),
  UNIQUE KEY uq_dpr_machine_qr_token (qr_token)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
