-- Production Scheduler tables

CREATE TABLE IF NOT EXISTS scheduler_working_calendar (
  cal_date      DATE PRIMARY KEY,
  is_working    TINYINT(1) NOT NULL DEFAULT 1,
  shift_hours   DECIMAL(4,2) NULL,
  notes         VARCHAR(200) NULL,
  updated_by    VARCHAR(100) NULL,
  updated_at    DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS scheduler_scenario (
  scenario_id     INT AUTO_INCREMENT PRIMARY KEY,
  name            VARCHAR(200) NOT NULL,
  month           TINYINT NOT NULL,
  year            SMALLINT NOT NULL,
  weights_json    JSON NOT NULL,
  overrides_json  JSON NULL,
  frozen_days     TINYINT NOT NULL DEFAULT 0,
  created_by      VARCHAR(100) NULL,
  created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at      DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX idx_scenario_period (year, month)
);

CREATE TABLE IF NOT EXISTS scheduler_run (
  run_id          INT AUTO_INCREMENT PRIMARY KEY,
  scenario_id     INT NOT NULL,
  status          ENUM('running','completed','failed') DEFAULT 'running',
  kpi_json        JSON NULL,
  assignments_json LONGTEXT NULL,
  started_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
  completed_at    DATETIME NULL,
  CONSTRAINT fk_run_scenario
    FOREIGN KEY (scenario_id) REFERENCES scheduler_scenario(scenario_id) ON DELETE CASCADE,
  INDEX idx_run_scenario (scenario_id)
);
