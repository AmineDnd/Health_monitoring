from odoo import models, fields, api

class HealthPatient(models.Model):
    _name = 'health.patient'
    _description = 'Patient Registry'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char('Patient Name', required=True, tracking=True)
    age = fields.Integer('Age')
    gender = fields.Selection([('male', 'Male'), ('female', 'Female'), ('other', 'Other')], 'Gender')
    doctor_id = fields.Many2one('res.users', 'Assigned Doctor', tracking=True)
    
    risk_level = fields.Selection([
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('critical', 'Critical')
    ], 'Risk Level', default='low', tracking=True)
    
    last_score = fields.Float('Last AI Score', readonly=True)
    last_alert_id = fields.Many2one('health.alert', 'Latest Alert', readonly=True)
    
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
