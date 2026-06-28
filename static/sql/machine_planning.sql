CREATE TABLE IF NOT EXISTS machine_planning (
  mp_id         INT AUTO_INCREMENT PRIMARY KEY,
  machine_id    INT UNSIGNED NOT NULL,
  month_year    DATE NOT NULL,
  part_number   VARCHAR(100) NOT NULL,
  additional_qty INT DEFAULT 0,
  priority      INT DEFAULT 0,
  remarks       TEXT,
  created_by    INT,
  created_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at    DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uq_plan (machine_id, month_year, part_number)
);
