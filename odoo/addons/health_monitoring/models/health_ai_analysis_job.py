import json
import logging
import os
from datetime import timedelta

import requests

from odoo import api, fields, models, _


_logger = logging.getLogger(__name__)

AI_URL = os.environ.get('AI_SERVICE_URL', 'http://ai_service:8000')
AI_SERVICE_TOKEN = os.environ.get('AI_SERVICE_TOKEN')


def _ai_headers():
    headers = {'Content-Type': 'application/json'}
    if AI_SERVICE_TOKEN:
        headers['X-SmartLab-Token'] = AI_SERVICE_TOKEN
    return headers


class HealthAIModelEvent(models.Model):
    _name = 'health.ai.model.event'
    _description = 'AI Model Governance Event'
    _order = 'requested_at desc'

    event_type = fields.Selection([
        ('retrain', 'Retrain'),
        ('model_info', 'Model Info'),
    ], required=True, default='retrain')
    requested_by = fields.Many2one('res.users', default=lambda self: self.env.user, readonly=True)
    requested_at = fields.Datetime(default=fields.Datetime.now, readonly=True)
    source = fields.Char(readonly=True)
    records_count = fields.Integer(readonly=True)
    status = fields.Selection([
        ('requested', 'Requested'),
        ('success', 'Success'),
        ('failed', 'Failed'),
    ], default='requested', readonly=True)
    model_version = fields.Char(readonly=True)
    result_message = fields.Text(readonly=True)


class HealthAIAnalysisJob(models.Model):
    _name = 'health.ai.analysis.job'
    _description = 'AI Analysis Job'
    _order = 'requested_at desc'

    def _auto_init(self):
        res = super()._auto_init()
        self._create_performance_indexes()
        return res

    def init(self):
        self._create_performance_indexes()

    def _create_performance_indexes(self):
        self.env.cr.execute("CREATE INDEX IF NOT EXISTS health_ai_job_state_next_idx ON health_ai_analysis_job (state, next_attempt_at, requested_at)")
        self.env.cr.execute("CREATE INDEX IF NOT EXISTS health_ai_job_patient_state_idx ON health_ai_analysis_job (patient_id, state)")
        self.env.cr.execute("CREATE INDEX IF NOT EXISTS health_ai_job_create_idx ON health_ai_analysis_job (create_date DESC)")

    MAX_ATTEMPTS = 3
    RETRY_BASE_MINUTES = 5
    NORMAL_RANGES = {
        'bp_systolic': (90, 140),
        'bp_diastolic': (60, 90),
        'heart_rate': (60, 100),
        'glucose': (70, 140),
        'temperature': (36.0, 37.5),
        'spo2': (95, 100),
        'respiratory_rate': (12, 20),
    }

    vital_record_id = fields.Many2one(
        'health.vital.record',
        'Vital Record',
        required=True,
        ondelete='cascade',
        index=True,
    )
    patient_id = fields.Many2one(
        'health.patient',
        'Patient',
        required=True,
        ondelete='cascade',
        index=True,
    )
    state = fields.Selection([
        ('pending', 'Pending'),
        ('retrying', 'Retrying'),
        ('analyzed', 'Analyzed'),
        ('failed', 'Failed'),
    ], default='pending', required=True, index=True)
    requested_at = fields.Datetime(default=fields.Datetime.now, readonly=True, index=True)
    started_at = fields.Datetime(readonly=True)
    finished_at = fields.Datetime(readonly=True)
    next_attempt_at = fields.Datetime(index=True)
    attempt_count = fields.Integer(default=0, readonly=True)
    last_error = fields.Text(readonly=True)
    model_version = fields.Char(readonly=True)
    anomaly_score = fields.Float(readonly=True)
    severity = fields.Selection([
        ('normal', 'Normal'),
        ('warning', 'Warning'),
        ('critical', 'Critical'),
    ], readonly=True, index=True)
    is_anomaly = fields.Boolean(readonly=True)
    result_message = fields.Text(readonly=True)
    payload_json = fields.Text(readonly=True)

    @api.model
    def cron_process_pending_jobs(self):
        return self.process_pending_jobs(limit=25)

    @api.model
    def process_pending_jobs(self, limit=25):
        now = fields.Datetime.now()
        jobs = self.search([
            ('state', 'in', ['pending', 'retrying']),
            '|',
            ('next_attempt_at', '=', False),
            ('next_attempt_at', '<=', now),
        ], order='requested_at asc', limit=limit)
        processed = 0
        for job in jobs:
            try:
                with self.env.cr.savepoint():
                    job._process_one()
                    processed += 1
            except Exception as exc:
                _logger.exception("AI analysis job %s failed outside retry handler: %s", job.id, exc)
                job._record_failure(exc)
        return processed

    def _process_one(self):
        self.ensure_one()
        vital = self.vital_record_id
        if not vital.exists():
            self.write({
                'state': 'failed',
                'finished_at': fields.Datetime.now(),
                'last_error': 'Vital record no longer exists.',
            })
            return
        if vital.confirmation_state == 'pending':
            self.write({
                'state': 'pending',
                'last_error': 'Waiting for extreme vital confirmation.',
            })
            return

        self.write({
            'started_at': fields.Datetime.now(),
            'attempt_count': self.attempt_count + 1,
            'last_error': False,
        })

        payload = vital._prepare_ai_analysis_payload()
        self.write({'payload_json': json.dumps(payload, sort_keys=True)})

        try:
            resp = requests.post(
                f'{AI_URL}/analyze',
                json=payload,
                timeout=12,
                headers=_ai_headers(),
            )
            resp.raise_for_status()
            result = resp.json()
        except Exception as exc:
            self._record_failure(exc)
            return

        model_version = result.get('model_version') or self._get_model_version()
        self._apply_result(vital, payload, result, model_version)

    def _record_failure(self, exc):
        self.ensure_one()
        attempts = self.attempt_count or 1
        now = fields.Datetime.now()
        final_failure = attempts >= self.MAX_ATTEMPTS
        next_attempt = False
        state = 'failed' if final_failure else 'retrying'
        if not final_failure:
            next_attempt = now + timedelta(minutes=self.RETRY_BASE_MINUTES * attempts)

        message = str(exc)
        self.write({
            'state': state,
            'next_attempt_at': next_attempt,
            'finished_at': now if final_failure else False,
            'last_error': message,
        })
        self.vital_record_id.sudo().with_context(no_ai=True).write({
            'ai_analysis_state': state,
            'ai_analysis_error': message,
        })

    def _get_model_version(self):
        try:
            resp = requests.get(f'{AI_URL}/model-info', timeout=5, headers=_ai_headers())
            resp.raise_for_status()
            data = resp.json()
            return data.get('model_version') or data.get('algorithm') or 'unknown'
        except Exception:
            return 'unknown'

    def _apply_result(self, vital, payload, result, model_version):
        self.ensure_one()
        patient = vital.patient_id
        score = result.get('anomaly_score', 0.0)
        is_anomaly = result.get('is_anomaly', False)
        ai_sev = result.get('severity', 'normal')
        record_severity = ai_sev if ai_sev in ['normal', 'warning', 'critical'] else 'normal'
        message = result.get('message', '')

        vital.sudo().with_context(no_ai=True).write({
            'ai_score': score,
            'ai_severity': record_severity,
            'anomaly_detected': is_anomaly,
            'clinical_hints': message,
            'ai_model_version': model_version,
            'ai_analysis_state': 'analyzed',
            'ai_analysis_error': False,
        })
        patient.sudo().write({'last_score': score})

        if self._payload_is_clinically_stable(payload):
            self._resolve_stabilized_alerts(vital, patient)
            self._set_stable_recommendation(patient)
        elif is_anomaly:
            alert = self._create_or_update_alert(vital, patient, record_severity, score, message)
            patient.sudo().write({'last_alert_id': alert.id})
        else:
            self._set_stable_recommendation(patient)

        self.write({
            'state': 'analyzed',
            'finished_at': fields.Datetime.now(),
            'next_attempt_at': False,
            'model_version': model_version,
            'anomaly_score': score,
            'severity': record_severity,
            'is_anomaly': is_anomaly,
            'result_message': message,
            'last_error': False,
        })

    def _create_or_update_alert(self, vital, patient, record_severity, score, raw_message):
        clean_msg = (raw_message or 'Anomaly detected').replace('[WARNING]', '').replace('[CRITICAL]', '').replace('[INFO]', '').strip()
        alert_sev_map = {
            'normal': 'low',
            'warning': 'high',
            'critical': 'critical',
        }
        alert_severity = alert_sev_map.get(record_severity, 'low')
        if alert_severity == 'low':
            alert_severity = 'medium'

        icu_ward = self.env['health.ward'].sudo().search([('ward_type', '=', 'icu')], limit=1)
        gen_ward = self.env['health.ward'].sudo().search([('ward_type', '=', 'general')], limit=1)
        rec_ward = icu_ward if alert_severity == 'critical' else gen_ward
        rec_msg = (
            "Critical Situation. AI recommends ICU review."
            if alert_severity == 'critical'
            else "Patient requires attention. AI recommends general ward review."
        )
        patient.sudo().write({
            'ai_recommended_ward_id': rec_ward.id if rec_ward else False,
            'ai_recommendation_msg': rec_msg,
        })

        cutoff = fields.Datetime.now() - timedelta(hours=2)
        existing = self.env['health.alert'].sudo().search([
            ('patient_id', '=', patient.id),
            ('severity', '=', alert_severity),
            ('state', '!=', 'resolved'),
            ('status', '!=', 'handled'),
            ('create_date', '>=', cutoff),
        ], order='create_date desc', limit=1)
        if existing:
            existing.write({
                'vital_record_id': vital.id,
                'message': clean_msg,
                'ai_confidence': score,
            })
            existing.message_post(
                body=_("Repeated anomaly merged into this open alert from vital record #%s.") % vital.id
            )
            return existing

        return self.env['health.alert'].sudo().create({
            'patient_id': patient.id,
            'vital_record_id': vital.id,
            'severity': alert_severity,
            'message': clean_msg,
            'ai_confidence': score,
            'state': 'new',
        })

    def _payload_is_clinically_stable(self, payload):
        for field_name, (low, high) in self.NORMAL_RANGES.items():
            value = payload.get(field_name)
            if value in [None, False, 0]:
                return False
            if value < low or value > high:
                return False
        return True

    def _resolve_stabilized_alerts(self, vital, patient):
        active_alerts = self.env['health.alert'].sudo().search([
            ('patient_id', '=', patient.id),
            ('state', 'in', ['new', 'investigating']),
            ('status', '!=', 'handled'),
        ])
        if active_alerts:
            active_alerts.write({
                'state': 'resolved',
                'status': 'handled',
                'handled_at': fields.Datetime.now(),
                'resolution_notes': _(
                    "System: Latest analyzed vital values are within deterministic SmartLab normal ranges "
                    "(Vital Record #%s)."
                ) % vital.id,
            })

    def _set_stable_recommendation(self, patient):
        gen_ward = self.env['health.ward'].sudo().search([('ward_type', '=', 'general')], limit=1)
        patient.sudo().write({
            'ai_recommended_ward_id': gen_ward.id if gen_ward else False,
            'ai_recommendation_msg': "Patient stable. Continue standard clinical monitoring.",
        })
