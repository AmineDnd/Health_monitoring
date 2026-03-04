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
    
    display_name = fields.Char('Alert Name', compute='_compute_display_name')
    
    @api.depends('patient_id', 'severity')
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = f"Alert: {rec.patient_id.name} ({rec.severity.upper() if rec.severity else 'N/A'})"

    message = fields.Text('Message')
    parsed_message_html = fields.Html('AI Clinical Analysis', compute='_compute_parsed_message')
    ai_confidence = fields.Float('AI Confidence (%)', help="Confidence score from the AI model (0-100%).")
    
    @api.depends('message')
    def _compute_parsed_message(self):
        for rec in self:
            msg = rec.message or ""
            if not msg:
                rec.parsed_message_html = False
                continue
            
            # Reuse similar logic for consistency
            html = "<ul class='list-unstyled mb-0'>"
            parts = [p.strip() for p in msg.split('|')]
            for part in parts:
                icon = "fa-warning text-warning"
                if "CRITICAL" in part.upper(): icon = "fa-exclamation-triangle text-danger"
                
                if "=" in part:
                    vital_name = part.split('=')[0].replace('_', ' ').title()
                    the_rest = part.split('=', 1)[1]
                    part_html = f"<b>{vital_name}</b>: {the_rest}"
                else:
                    part_html = part
                
                html += f"<li class='mb-2 d-flex align-items-start'><i class='fa {icon} mt-1 me-2' style='width: 20px;'></i><span>{part_html}</span></li>"
            html += "</ul>"
            rec.parsed_message_html = html

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
