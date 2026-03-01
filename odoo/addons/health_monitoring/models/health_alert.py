from odoo import models, fields, api

class HealthAlert(models.Model):
    _name = 'health.alert'
    _description = 'Health Alert'
    _order = 'create_date desc'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    patient_id = fields.Many2one('health.patient', 'Patient', required=True, ondelete='cascade', tracking=True)
    vital_record_id = fields.Many2one('health.vital.record', 'Triggering Vital')
    doctor_id = fields.Many2one('res.users', related='patient_id.doctor_id', string='Assigned Doctor', store=True)
    
    severity = fields.Selection([
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('critical', 'Critical')
    ], 'Severity', required=True, tracking=True)
    
    message = fields.Text('Message')
    parsed_message_html = fields.Html('AI Clinical Analysis', compute='_compute_parsed_message')
    ai_confidence = fields.Float('AI Confidence (%)', help="Confidence score from the AI model (0-100%).")
    
    @api.depends('message')
    def _compute_parsed_message(self):
        for rec in self:
            msg = rec.message or ""
            # Professional cleanup for the UI
            clean_msg = msg.replace('[WARNING]', '').replace('[CRITICAL]', '').replace('[INFO]', '').strip()
            rec.parsed_message_html = f"<div class='alert alert-info' style='border-left: 4px solid #3A86FF;'>{clean_msg}</div>"

    acknowledged = fields.Boolean('Acknowledged', default=False, tracking=True)
    acknowledged_by = fields.Many2one('res.users', 'Acknowledged By')
    acknowledged_at = fields.Datetime('Acknowledged At')
    
    state = fields.Selection([
        ('new', 'New'),
        ('investigating', 'Investigating'),
        ('resolved', 'Resolved')
    ], 'State', default='new', tracking=True)

    def action_acknowledge(self):
        self.write({
            'acknowledged': True,
            'acknowledged_by': self.env.user.id,
            'acknowledged_at': fields.Datetime.now(),
            'state': 'investigating'
        })
        
    def action_resolve(self):
        self.write({
            'state': 'resolved'
        })
