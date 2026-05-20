import os, json, logging, requests
from odoo import models, fields, api, _
from odoo.exceptions import AccessError, ValidationError

_logger = logging.getLogger(__name__)
AI_URL = os.environ.get('AI_SERVICE_URL', 'http://ai_service:8000')
AI_SERVICE_TOKEN = os.environ.get('AI_SERVICE_TOKEN')

def _ai_headers():
    headers = {'Content-Type': 'application/json'}
    if AI_SERVICE_TOKEN:
        headers['X-SmartLab-Token'] = AI_SERVICE_TOKEN
    return headers

class HealthVitalRecord(models.Model):
    _name = 'health.vital.record'
    _description = 'Patient Vital Record'
    _order = 'recorded_at desc'

    def _auto_init(self):
        res = super()._auto_init()
        self._create_performance_indexes()
        return res

    def init(self):
        self._create_performance_indexes()

    def _create_performance_indexes(self):
        self.env.cr.execute("CREATE INDEX IF NOT EXISTS health_vital_patient_recorded_idx ON health_vital_record (patient_id, recorded_at DESC)")
        self.env.cr.execute("CREATE INDEX IF NOT EXISTS health_vital_recorded_idx ON health_vital_record (recorded_at DESC)")
        self.env.cr.execute("CREATE INDEX IF NOT EXISTS health_vital_create_idx ON health_vital_record (create_date DESC)")
        self.env.cr.execute("CREATE INDEX IF NOT EXISTS health_vital_ai_state_idx ON health_vital_record (ai_analysis_state)")

    VITAL_FIELDS = [
        'heart_rate', 'bp_systolic', 'bp_diastolic', 'spo2',
        'temperature', 'glucose', 'respiratory_rate'
    ]
    HARD_LIMITS = {
        'heart_rate': (1, 260, 'Heart Rate', 'bpm'),
        'bp_systolic': (40, 300, 'Systolic BP', 'mmHg'),
        'bp_diastolic': (20, 220, 'Diastolic BP', 'mmHg'),
        'spo2': (1, 100, 'SpO2', '%'),
        'temperature': (25, 45, 'Temperature', 'C'),
        'glucose': (10, 1000, 'Glucose', 'mg/dL'),
        'respiratory_rate': (1, 80, 'Respiratory Rate', '/min'),
    }
    EXTREME_LIMITS = {
        'heart_rate': (35, 160, 'Heart Rate', 'bpm'),
        'bp_systolic': (70, 200, 'Systolic BP', 'mmHg'),
        'bp_diastolic': (35, 130, 'Diastolic BP', 'mmHg'),
        'spo2': (75, 100, 'SpO2', '%'),
        'temperature': (34.0, 41.0, 'Temperature', 'C'),
        'glucose': (30, 500, 'Glucose', 'mg/dL'),
        'respiratory_rate': (6, 35, 'Respiratory Rate', '/min'),
    }

    def action_manual_save_close(self):
        """Dummy method just to give users a 'Save & Close' button that closes the popup wizard"""
        return {'type': 'ir.actions.act_window_close'}

    def action_check_and_save(self):
        """Open confirmation when extreme readings were saved pending review."""
        self.ensure_one()
        if self.confirmation_state == 'pending':
            return self._action_open_confirmation_wizard()
        return self.action_manual_save_close()

    def _action_open_confirmation_wizard(self):
        self.ensure_one()
        return {
            'name': 'Verify Vital Readings',
            'type': 'ir.actions.act_window',
            'res_model': 'health.vital.confirm.wizard',
            'view_mode': 'form',
            'views': [[False, 'form']],
            'target': 'new',
            'context': {
                'default_vital_record_id': self.id,
                'default_warnings_text': self.confirmation_warnings,
            },
        }

    def action_confirm_extreme_values(self, confirmation_notes):
        self.ensure_one()
        if self.confirmation_state != 'pending':
            return self.action_manual_save_close()
        if not confirmation_notes or not confirmation_notes.strip():
            raise ValidationError(_("Confirmation notes are required for extreme vital readings."))
        self.with_context(no_ai=True).write({
            'confirmation_state': 'confirmed',
            'confirmation_required': False,
            'confirmed_by': self.env.user.id,
            'confirmed_at': fields.Datetime.now(),
            'confirmation_notes': confirmation_notes.strip(),
        })
        self._enqueue_ai_analysis(reason='confirmed_extreme')
        return self.action_manual_save_close()

    @api.model
    def action_retrain_ai_model(self):
        """Collect all real vitals and send to AI service for retraining."""
        if not self.env.user.has_group('health_monitoring.group_health_admin'):
            raise AccessError(_("Only SmartLab administrators can retrain the AI model."))

        records = self.search([], order='patient_id, recorded_at asc', limit=5000)
        model_event = self.env['health.ai.model.event'].sudo().create({
            'event_type': 'retrain',
            'source': 'odoo_vital_records',
            'records_count': len(records),
            'status': 'requested',
        })
        
        if len(records) < 50:
            model_event.write({
                'status': 'failed',
                'result_message': f'Only {len(records)} vital records found. Need at least 50 to retrain.',
            })
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Not Enough Data',
                    'message': f'Only {len(records)} vital records found. Need at least 50 to retrain.',
                    'type': 'warning',
                    'sticky': False,
                }
            }
        
        payload_records = []
        for rec in records:
            payload_records.append({
                'bp_systolic': rec.bp_systolic or 0,
                'bp_diastolic': rec.bp_diastolic or 0,
                'heart_rate': rec.heart_rate or 0,
                'glucose': rec.glucose or 0,
                'temperature': rec.temperature or 0,
                'spo2': rec.spo2 or 0,
                'respiratory_rate': rec.respiratory_rate or 0,
            })
        
        try:
            import requests as req_lib
            resp = req_lib.post(
                f'{AI_URL}/retrain',
                json={'records': payload_records},
                headers=_ai_headers(),
                timeout=60
            )
            resp.raise_for_status()
            result = resp.json()
            model_event.write({
                'status': 'success' if result.get('status') != 'error' else 'failed',
                'model_version': result.get('model_version'),
                'result_message': result.get('message', ''),
            })
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'AI Model Retrained',
                    'message': result.get('message', 'Model updated successfully.'),
                    'type': 'success',
                    'sticky': False,
                }
            }
        except Exception as e:
            model_event.write({
                'status': 'failed',
                'result_message': str(e),
            })
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Retraining Failed',
                    'message': str(e),
                    'type': 'danger',
                    'sticky': True,
                }
            }

    patient_id = fields.Many2one('health.patient', 'Patient', required=True, ondelete='cascade', index=True)
    type = fields.Selection([
        ('blood_pressure', 'Blood Pressure'),
        ('heart_rate', 'Heart Rate'),
        ('glucose', 'Glucose'),
        ('temperature', 'Temperature'),
        ('oxygen', 'Oxygen (SpO2)'),
        ('respiratory_rate', 'Respiratory Rate')
    ], string='Vital Type')
    
    value = fields.Float('Value/Systolic')
    value2 = fields.Float('Diastolic (for BP)')
    unit = fields.Char('Unit', compute='_compute_unit', store=True)

    recorded_at = fields.Datetime('Recorded At', default=fields.Datetime.now, required=True, index=True)
    
    ai_score = fields.Float('AI Score', readonly=True, help="Anomaly score from 0.0 to 100.0 generated by the AI.")
    ai_severity = fields.Selection([
        ('normal', 'Normal'),
        ('warning', 'Warning'),
        ('critical', 'Critical')
    ], string='AI Severity', readonly=True, index=True)
    anomaly_detected = fields.Boolean('Anomaly Detected', readonly=True, help="True if ML or Rule thresholds were violated.")
    
    # NEW FIELDS DEMANDED BY THE VIEW
    bp_systolic = fields.Float('BP Systolic')
    bp_diastolic = fields.Float('BP Diastolic')
    heart_rate = fields.Float('Heart Rate')
    spo2 = fields.Float('SpO2')
    temperature = fields.Float('Temperature')
    glucose = fields.Float('Glucose')
    respiratory_rate = fields.Float('Respiratory Rate')
    clinical_hints = fields.Text('Clinical Hints')
    parsed_clinical_hints = fields.Html('AI Clinical Analysis', compute='_compute_parsed_hints')
    status = fields.Selection([
        ('normal', 'Normal'),
        ('warning', 'Warning'),
        ('critical', 'Critical')
    ], string='Status', compute='_compute_status', store=True, index=True)
    confirmation_state = fields.Selection([
        ('not_required', 'Not Required'),
        ('pending', 'Pending Confirmation'),
        ('confirmed', 'Confirmed Extreme'),
    ], string='Confirmation State', default='not_required', readonly=True, index=True)
    confirmation_required = fields.Boolean('Needs Confirmation', default=False, readonly=True)
    confirmation_warnings = fields.Text('Confirmation Warnings', readonly=True)
    confirmed_by = fields.Many2one('res.users', 'Confirmed By', readonly=True)
    confirmed_at = fields.Datetime('Confirmed At', readonly=True)
    confirmation_notes = fields.Text('Confirmation Notes', readonly=True)
    ai_payload_context = fields.Text('AI Payload Context', readonly=True)
    ai_analysis_state = fields.Selection([
        ('pending', 'Pending'),
        ('retrying', 'Retrying'),
        ('analyzed', 'Analyzed'),
        ('failed', 'Failed'),
    ], string='AI Analysis Status', default='pending', readonly=True, index=True)
    ai_analysis_job_id = fields.Many2one('health.ai.analysis.job', 'Latest AI Job', readonly=True)
    ai_analysis_error = fields.Text('AI Analysis Error', readonly=True)
    ai_model_version = fields.Char('AI Model Version', readonly=True)

    @api.depends('ai_severity', 'ai_score', 'anomaly_detected', 'confirmation_state')
    def _compute_status(self):
        for rec in self:
            if rec.confirmation_state == 'pending':
                rec.status = 'warning'
                continue
            # Priority 1: Use AI severity if we have it
            if rec.ai_severity:
                rec.status = rec.ai_severity
            # Priority 2: Fallback to score thresholds (0-100 scale)
            elif rec.ai_score >= 80:
                rec.status = 'critical'
            elif rec.ai_score >= 50 or rec.anomaly_detected:
                rec.status = 'warning'
            else:
                rec.status = 'normal'
    
    def _compute_parsed_hints(self):
        for rec in self:
            hints = rec.clinical_hints or ""
            if not hints or "normal range" in hints.lower():
                rec.parsed_clinical_hints = "<div class='text-success'><i class='fa fa-check-circle me-2'></i>All vitals within normal range.</div>"
                continue
            
            html = "<div class='sl-clinical-narrative'>"
            parts = [p.strip() for p in hints.split('|')]
            for part in parts:
                if part.startswith('SUMMARY:'):
                    headline = part.replace('SUMMARY:', '')
                    html += f"<div class='alert alert-info border-0 shadow-sm mb-3 py-2' style='border-radius:8px; font-size:0.9em;'><i class='fa fa-info-circle me-2'></i>{headline}</div>"
                
                elif part.startswith('SYSTEM:'):
                    system_name = part.replace('SYSTEM:', '')
                    icon = "fa-lungs" if "Respiratory" in system_name else "fa-heartbeat" if "Cardiovascular" in system_name else "fa-microscope" if "Metabolic" in system_name else "fa-chart-line"
                    html += f"<h6 class='text-uppercase fw-bold text-muted small mt-2 mb-1' style='font-size: 0.75em;'><i class='fa {icon} me-2'></i>{system_name}</h6>"
                
                elif part.startswith('TREND:'):
                    trend_text = part.replace('TREND:', '')
                    icon = "fa-arrow-trend-up" if "increase" in trend_text.lower() else "fa-arrow-trend-down" if "decrease" in trend_text.lower() or "drop" in trend_text.lower() else "fa-chart-line"
                    html += f"<div class='d-flex align-items-center mb-1 text-primary' style='font-size: 0.85em;'><i class='fa {icon} me-2'></i><span>{trend_text}</span></div>"
                
                elif ':' in part:
                    label, val = part.split(':', 1)
                    icon = "fa-warning text-warning"
                    if "CRITICAL" in val.upper(): icon = "fa-exclamation-triangle text-danger"
                    html += f"<div class='d-flex align-items-start mb-1' style='font-size: 0.85em;'><i class='fa {icon} mt-1 me-2' style='width:15px;'></i><b>{label}</b>: {val}</div>"
                else:
                    html += f"<div class='mb-1' style='font-size: 0.85em;'>{part}</div>"
            
            html += "</div>"
            rec.parsed_clinical_hints = html
    
    @api.depends('type')
    def _compute_unit(self):
        units = {
            'blood_pressure': 'mmHg',
            'heart_rate': 'bpm',
            'glucose': 'mg/dL',
            'temperature': 'C',
            'oxygen': '%',
            'respiratory_rate': '/min'
        }
        for rec in self:
            rec.unit = units.get(rec.type, '')

    @api.model_create_multi
    def create(self, vals_list):
        self._prepare_vital_vals_list(vals_list)
        records = super().create(vals_list)
        for rec in records:
            if rec.confirmation_state != 'pending':
                rec._enqueue_ai_analysis(reason='created')
        return records

    def write(self, vals):
        vals = dict(vals)
        if any(field in vals for field in self.VITAL_FIELDS + ['patient_id']):
            self._prepare_vital_vals_for_write(vals)
        res = super().write(vals)
        # Only call AI if physiological vitals actually changed. This prevents infinite loops
        # and prevents double-triggering when merely opening/saving a form without edits.
        if any(f in vals for f in self.VITAL_FIELDS):
            for rec in self:
                if rec.confirmation_state != 'pending':
                    rec._enqueue_ai_analysis(reason='updated')
        return res

    @api.model
    def _prepare_vital_vals_list(self, vals_list):
        patient_ids = {vals.get('patient_id') for vals in vals_list if vals.get('patient_id')}
        patients_by_id = {patient.id: patient for patient in self.env['health.patient'].browse(patient_ids)}
        for vals in vals_list:
            patient = patients_by_id.get(vals.get('patient_id'))
            if patient:
                self._validate_patient_can_record(patient)
            self._validate_hard_ranges(vals)
            self._apply_confirmation_state(vals)

    def _prepare_vital_vals_for_write(self, vals):
        patients = self.env['health.patient']
        if vals.get('patient_id'):
            patients |= self.env['health.patient'].browse(vals['patient_id'])
        else:
            patients |= self.mapped('patient_id')
        for patient in patients:
            self._validate_patient_can_record(patient)
        for rec in self:
            candidate = {field: vals.get(field, getattr(rec, field)) for field in self.VITAL_FIELDS}
            self._validate_hard_ranges(candidate)
        self._apply_confirmation_state(vals, current_records=self)

    @api.model
    def _validate_patient_can_record(self, patient):
        if self.env.context.get('allow_discharged_vitals'):
            return
        if not patient.active:
            raise ValidationError(_("Cannot record vitals for archived patients: %s") % patient.name)
        if patient.admission_status not in ['triage', 'admitted']:
            raise ValidationError(_(
                "Cannot record vitals for patients outside triage/admitted care. "
                "Reactivate the patient first: %s"
            ) % patient.name)

    @api.model
    def _validate_hard_ranges(self, vals):
        errors = []
        for field, (min_value, max_value, label, unit) in self.HARD_LIMITS.items():
            value = vals.get(field)
            if value in [None, False, '']:
                continue
            value = float(value)
            if value == 0:
                continue
            if value < min_value or value > max_value:
                errors.append(_("%s %.1f %s is outside the allowed recording range (%s-%s %s).") % (
                    label, value, unit, min_value, max_value, unit
                ))
        if errors:
            raise ValidationError("\n".join(errors))

    @api.model
    def _extreme_warnings_for_vals(self, vals):
        warnings = []
        for field, (min_value, max_value, label, unit) in self.EXTREME_LIMITS.items():
            value = vals.get(field)
            if value in [None, False, '']:
                continue
            value = float(value)
            if value == 0:
                continue
            if value < min_value or value > max_value:
                warnings.append(_("%s: %.1f %s is outside the extreme safety range (%s-%s %s).") % (
                    label, value, unit, min_value, max_value, unit
                ))
        return warnings

    @api.model
    def _apply_confirmation_state(self, vals, current_records=False):
        candidate = dict(vals)
        if current_records and len(current_records) == 1:
            for field in self.VITAL_FIELDS:
                candidate.setdefault(field, getattr(current_records, field))
        warnings = self._extreme_warnings_for_vals(candidate)
        if not warnings:
            if any(field in vals for field in self.VITAL_FIELDS):
                vals.update({
                    'confirmation_state': 'not_required',
                    'confirmation_required': False,
                    'confirmation_warnings': False,
                    'confirmed_by': False,
                    'confirmed_at': False,
                    'confirmation_notes': False,
                })
            return

        warning_text = "\n".join(warnings)
        if self.env.context.get('extreme_confirmed'):
            notes = (self.env.context.get('extreme_confirmation_notes') or '').strip()
            if not notes:
                raise ValidationError(_("Confirmation notes are required for extreme vital readings."))
            vals.update({
                'confirmation_state': 'confirmed',
                'confirmation_required': False,
                'confirmation_warnings': warning_text,
                'confirmed_by': self.env.user.id,
                'confirmed_at': fields.Datetime.now(),
                'confirmation_notes': notes,
            })
        else:
            vals.update({
                'confirmation_state': 'pending',
                'confirmation_required': True,
                'confirmation_warnings': warning_text,
            })

    @api.constrains('patient_id', 'heart_rate', 'bp_systolic', 'bp_diastolic', 'spo2', 'temperature', 'glucose', 'respiratory_rate')
    def _check_first_record_completeness(self):
        for record in self:
            # Only check if this is a "Full Profile" entry or we want broad enforcement
            # The user specifically said: "when i put the first data for a patient it should be all obligatoire"
            
            # Count existing records for this patient
            existing_record = self.env['health.vital.record'].search([
                ('patient_id', '=', record.patient_id.id),
                ('id', '!=', record.id)
            ], limit=1)
            
            if not existing_record:
                # This is the first record, all core vitals must be > 0
                missing = []
                if not record.heart_rate: missing.append("Heart Rate")
                if not record.bp_systolic: missing.append("Systolic BP")
                if not record.bp_diastolic: missing.append("Diastolic BP")
                if not record.spo2: missing.append("SpO2")
                if not record.temperature: missing.append("Temperature")
                if not record.glucose: missing.append("Glucose")
                if not record.respiratory_rate: missing.append("Respiratory Rate")
                
                if missing:
                    raise ValidationError(
                        _("This is the first record for this patient. "
                          "Please provide a complete baseline by filling: %s") % ", ".join(missing)
                    )

    def _enqueue_ai_analysis(self, reason='vitals_saved'):
        if self.env.context.get('no_ai'):
            return False

        Job = self.env['health.ai.analysis.job'].sudo()
        created_jobs = Job
        for rec in self:
            if rec.confirmation_state == 'pending':
                continue

            existing_job = Job.search([
                ('vital_record_id', '=', rec.id),
                ('state', 'in', ['pending', 'retrying']),
            ], order='requested_at desc', limit=1)
            if existing_job:
                rec.sudo().with_context(no_ai=True).write({
                    'ai_analysis_state': existing_job.state,
                    'ai_analysis_job_id': existing_job.id,
                })
                created_jobs |= existing_job
                continue

            job = Job.create({
                'vital_record_id': rec.id,
                'patient_id': rec.patient_id.id,
                'state': 'pending',
                'result_message': reason,
            })
            rec.sudo().with_context(no_ai=True).write({
                'ai_analysis_state': 'pending',
                'ai_analysis_job_id': job.id,
                'ai_analysis_error': False,
            })
            created_jobs |= job
        return created_jobs

    def _prepare_ai_analysis_payload(self):
        self.ensure_one()
        patient = self.patient_id

        latest_recs = self.env['health.vital.record'].search([
            ('patient_id', '=', patient.id),
            ('id', '!=', self.id)
        ], order='recorded_at desc', limit=5)

        is_first = not bool(latest_recs)
        history = [{
            'bp_systolic': r.bp_systolic or 0,
            'bp_diastolic': r.bp_diastolic or 0,
            'heart_rate': r.heart_rate or 0,
            'glucose': r.glucose or 90,
            'temperature': r.temperature or 37.0,
            'spo2': r.spo2 or 0,
            'respiratory_rate': r.respiratory_rate or 16,
        } for r in latest_recs]

        baseline = history[0] if history else {
            'bp_systolic': 0, 'bp_diastolic': 0, 'heart_rate': 0,
            'glucose': 0, 'temperature': 0, 'spo2': 0, 'respiratory_rate': 0
        }
        field_values = {
            'bp_systolic': self.bp_systolic,
            'bp_diastolic': self.bp_diastolic,
            'heart_rate': self.heart_rate,
            'glucose': self.glucose,
            'temperature': self.temperature,
            'spo2': self.spo2,
            'respiratory_rate': self.respiratory_rate,
        }
        measured_fields = [field for field, value in field_values.items() if value not in [None, False, 0]]
        carried_forward_fields = {
            field: baseline.get(field, 0.0)
            for field, value in field_values.items()
            if value in [None, False, 0]
        }
        payload_context = {
            'measured_fields': measured_fields,
            'carried_forward_fields': carried_forward_fields,
            'partial_record': bool(carried_forward_fields),
        }

        payload = {
            'patient_code': str(patient.id),
            'age': patient.age or 0,
            'gender': patient.gender or 'unknown',
            'category': patient.category or 'unknown',
            'lifestyle_profile': patient.lifestyle_profile or 'standard',
            'bp_systolic': field_values['bp_systolic'] or baseline.get('bp_systolic', 0.0),
            'bp_diastolic': field_values['bp_diastolic'] or baseline.get('bp_diastolic', 0.0),
            'heart_rate': field_values['heart_rate'] or baseline.get('heart_rate', 0.0),
            'glucose': field_values['glucose'] or baseline.get('glucose', 0.0),
            'temperature': field_values['temperature'] or baseline.get('temperature', 0.0),
            'spo2': field_values['spo2'] or baseline.get('spo2', 0.0),
            'respiratory_rate': field_values['respiratory_rate'] or baseline.get('respiratory_rate', 0.0),
            'history': history,
            'is_initial': is_first,
            'measurement_context': payload_context,
        }
        self.sudo().with_context(no_ai=True).write({
            'ai_payload_context': json.dumps(payload_context, sort_keys=True)
        })
        return payload

    def _call_ai_service(self):
        return self._enqueue_ai_analysis(reason='legacy_call')

    @api.model
    def cron_reanalyze_recent(self):
        processed = self.env['health.ai.analysis.job'].sudo().process_pending_jobs(limit=25)
        _logger.info('Cron: processed %s pending AI analysis jobs', processed)

    @api.model
    def cron_process_unanalysed_vitals(self):
        return self.env['health.ai.analysis.job'].sudo().process_pending_jobs(limit=25)
