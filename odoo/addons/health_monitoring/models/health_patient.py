from odoo import models, fields, api

class HealthPatientTag(models.Model):
    _name = 'health.patient.tag'
    _description = 'Patient Tag'

    name = fields.Char('Tag Name', required=True)
    color = fields.Integer('Color Index')

class HealthPatient(models.Model):
    _name = 'health.patient'
    _description = 'Patient Registry'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char('Patient Name', required=True, tracking=True)
    age = fields.Integer('Age')
    gender = fields.Selection([('male', 'Male'), ('female', 'Female'), ('other', 'Other')], 'Gender')
    category = fields.Selection([
        ('child', 'Child'),
        ('teen', 'Teen'),
        ('adult', 'Adult'),
        ('elderly', 'Elderly')
    ], 'Category', compute='_compute_category')
    tag_ids = fields.Many2many('health.patient.tag', string='Tags')
    
    doctor_id = fields.Many2one('res.users', 'Assigned Doctor', tracking=True)
    
    @api.depends('age')
    def _compute_category(self):
        for rec in self:
            if not rec.age:
                rec.category = False
            elif rec.age < 13:
                rec.category = 'child'
            elif rec.age < 20:
                rec.category = 'teen'
            elif rec.age < 65:
                rec.category = 'adult'
            else:
                rec.category = 'elderly'

    risk_level = fields.Selection([
        ('low', 'Normal'),
        ('medium', 'Moderate'),
        ('high', 'High'),
        ('critical', 'Critical'),
        ('handled', 'Handled')
    ], 'Risk Level', compute='_compute_risk_level', store=True, tracking=True)

    @api.depends('last_score', 'last_alert_id', 'last_alert_id.state', 'last_alert_id.severity')
    def _compute_risk_level(self):
        for rec in self:
            # Check if there's an active alert being handled or already resolved
            if rec.last_alert_id and rec.last_alert_id.state in ['investigating', 'resolved']:
                rec.risk_level = 'handled'
                continue

            # Prioritize latest alert severity if it's still 'new'
            if rec.last_alert_id and rec.last_alert_id.state == 'new':
                rec.risk_level = rec.last_alert_id.severity
                continue

            # Otherwise, use AI Score thresholds as fallback
            score = rec.last_score or 0.0
            if score >= 80:
                rec.risk_level = 'critical'
            elif score >= 60:
                rec.risk_level = 'high'
            elif score >= 35:
                rec.risk_level = 'medium'
            else:
                rec.risk_level = 'low'
    
    dashboard_risk_score = fields.Float('Dashboard Risk %', compute='_compute_dashboard_risk_score')

    @api.depends('risk_level', 'last_score')
    def _compute_dashboard_risk_score(self):
        for rec in self:
            if rec.risk_level == 'handled':
                rec.dashboard_risk_score = 0.0
            else:
                rec.dashboard_risk_score = rec.last_score

    last_score = fields.Float('Last AI Score', readonly=True)
    last_alert_id = fields.Many2one('health.alert', 'Latest Alert', readonly=True)
    last_alert_state = fields.Selection(related='last_alert_id.state', string='Latest Alert Status', readonly=True)
    
    vital_record_ids = fields.One2many('health.vital.record', 'patient_id', 'Vital Records')
    alert_ids = fields.One2many('health.alert', 'patient_id', 'Alerts')
    
    vitals_count = fields.Integer(compute='_compute_vitals_count', string='Vitals Count')
    alerts_count = fields.Integer(compute='_compute_alerts_count', string='Alerts Count')
    critical_alerts_count = fields.Integer(compute='_compute_alerts_count', string='Critical Alerts Count')

    @api.depends('vital_record_ids')
    def _compute_vitals_count(self):
        for rec in self:
            rec.vitals_count = len(rec.vital_record_ids)

    @api.depends('alert_ids')
    def _compute_alerts_count(self):
        for rec in self:
            rec.alerts_count = len(rec.alert_ids)
            rec.critical_alerts_count = len(rec.alert_ids.filtered(lambda a: a.severity == 'critical'))
