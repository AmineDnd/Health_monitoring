from odoo import api, models


class HealthPerformanceIndex(models.AbstractModel):
    _name = 'health.performance.index'
    _description = 'SmartLab Performance Index Installer'

    PERFORMANCE_INDEX_SQL = [
        "CREATE INDEX IF NOT EXISTS health_alert_patient_state_idx ON health_alert (patient_id, state)",
        "CREATE INDEX IF NOT EXISTS health_alert_state_status_severity_idx ON health_alert (state, status, severity)",
        "CREATE INDEX IF NOT EXISTS health_alert_create_severity_idx ON health_alert (create_date DESC, severity)",
        "CREATE INDEX IF NOT EXISTS health_alert_assigned_state_idx ON health_alert (assigned_doctor_id, state)",
        "CREATE INDEX IF NOT EXISTS health_alert_escalation_idx ON health_alert (status, escalation_level, create_date DESC)",
        "CREATE INDEX IF NOT EXISTS health_vital_patient_recorded_idx ON health_vital_record (patient_id, recorded_at DESC)",
        "CREATE INDEX IF NOT EXISTS health_vital_recorded_idx ON health_vital_record (recorded_at DESC)",
        "CREATE INDEX IF NOT EXISTS health_vital_create_idx ON health_vital_record (create_date DESC)",
        "CREATE INDEX IF NOT EXISTS health_vital_ai_state_idx ON health_vital_record (ai_analysis_state)",
        "CREATE INDEX IF NOT EXISTS health_patient_ward_status_idx ON health_patient (ward_id, admission_status)",
        "CREATE INDEX IF NOT EXISTS health_patient_risk_status_idx ON health_patient (risk_level, admission_status)",
        "CREATE INDEX IF NOT EXISTS health_patient_create_status_idx ON health_patient (create_date, admission_status)",
        "CREATE INDEX IF NOT EXISTS health_patient_last_score_idx ON health_patient (last_score)",
        "CREATE INDEX IF NOT EXISTS health_notification_log_create_idx ON health_notification_log (create_date DESC)",
        "CREATE INDEX IF NOT EXISTS health_notification_log_cooldown_idx ON health_notification_log (alert_id, user_id, channel, purpose, result, create_date DESC)",
        "CREATE INDEX IF NOT EXISTS health_ai_job_state_next_idx ON health_ai_analysis_job (state, next_attempt_at, requested_at)",
        "CREATE INDEX IF NOT EXISTS health_ai_job_patient_state_idx ON health_ai_analysis_job (patient_id, state)",
        "CREATE INDEX IF NOT EXISTS health_ai_job_create_idx ON health_ai_analysis_job (create_date DESC)",
        "CREATE INDEX IF NOT EXISTS health_handoff_ward_create_idx ON health_handoff (ward_id, create_date DESC)",
        "CREATE INDEX IF NOT EXISTS health_ward_type_idx ON health_ward (ward_type)",
    ]

    @api.model
    def ensure_performance_indexes(self):
        for statement in self.PERFORMANCE_INDEX_SQL:
            self.env.cr.execute(statement)
        return True
