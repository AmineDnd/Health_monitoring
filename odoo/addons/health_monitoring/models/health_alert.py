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
    
    headline = fields.Char('Alert Headline', compute='_compute_headline', store=True)
    
    @api.depends('message')
    def _compute_headline(self):
        for rec in self:
            msg = rec.message or ""
            if "SUMMARY:" in msg:
                # SUMMARY:Headline | SYSTEM:Cardio ...
                headline = msg.split('SUMMARY:')[1].split('|')[0].strip()
                rec.headline = headline
            else:
                rec.headline = "Clinical Anomaly Detected"

    display_name = fields.Char('Alert Name', compute='_compute_display_name')
    
    @api.depends('patient_id', 'severity', 'headline')
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = f"{rec.headline} ({rec.severity.upper() if rec.severity else 'N/A'})"

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
            
            html = "<div class='sl-clinical-narrative'>"
            parts = [p.strip() for p in msg.split('|')]
            
            for part in parts:
                if part.startswith('SUMMARY:'):
                    # Clinical Headline
                    headline = part.replace('SUMMARY:', '')
                    html += f"<div class='alert alert-danger border-0 shadow-sm mb-3' style='border-radius:10px; background:rgba(239, 68, 68, 0.05); color:#991B1B;'><i class='fa fa-shield-heart me-2'></i><strong>{headline}</strong></div>"
                
                elif part.startswith('SYSTEM:'):
                    # Section Header
                    system_name = part.replace('SYSTEM:', '')
                    icon = "fa-lungs" if "Respiratory" in system_name else "fa-heartbeat" if "Cardiovascular" in system_name else "fa-microscope" if "Metabolic" in system_name else "fa-chart-line"
                    html += f"<h6 class='text-uppercase fw-bold text-muted small mt-3 mb-2' style='letter-spacing: 0.05em;'><i class='fa {icon} me-2'></i>{system_name}</h6>"
                
                elif part.startswith('TREND:'):
                    # Trend Alert
                    trend_text = part.replace('TREND:', '')
                    html += f"<div class='d-flex align-items-center mb-1 text-primary'><i class='fa fa-arrow-trend-up me-2 small'></i><span style='font-size: 0.9em;'>{trend_text}</span></div>"
                
                elif ':' in part:
                    # Individual Vital Violation
                    label, val = part.split(':', 1)
                    html += f"<div class='d-flex justify-content-between py-1 border-bottom border-light' style='font-size: 0.95em;'><span class='text-dark'>{label}</span><span class='fw-bold text-danger'>{val}</span></div>"
                else:
                    html += f"<div class='mb-1'>{part}</div>"
            
            html += "</div>"
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
