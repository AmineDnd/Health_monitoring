from odoo import models, fields, api
from markupsafe import Markup
import requests
import logging

_logger = logging.getLogger(__name__)

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
    
    status = fields.Selection([
        ('pending', 'Pending'),
        ('handled', 'Handled'),
        ('escalated', 'Escalated')
    ], 'Status', default='pending', tracking=True)
    
    created_at = fields.Datetime('Created At', default=fields.Datetime.now, readonly=True)
    handled_at = fields.Datetime('Handled At', readonly=True)
    assigned_doctor_id = fields.Many2one('res.users', 'Assigned Doctor')
    escalation_level = fields.Integer('Escalation Level', default=0)
    
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
                    icon = "fa-arrow-trend-up" if "increase" in trend_text.lower() else "fa-arrow-trend-down" if "decrease" in trend_text.lower() or "drop" in trend_text.lower() else "fa-chart-line"
                    html += f"<div class='d-flex align-items-center mb-1 text-primary'><i class='fa {icon} me-2 small'></i><span style='font-size: 0.9em;'>{trend_text}</span></div>"
                
                elif ':' in part:
                    # Individual Vital Violation
                    label, val = part.split(':', 1)
                    html += f"<div class='d-flex justify-content-between py-1 border-bottom border-light' style='font-size: 0.95em;'><span class='text-dark'>{label}</span><span class='fw-bold text-danger'>{val}</span></div>"
                else:
                    html += f"<div class='mb-1'>{part}</div>"
            
            html += "</div>"
            rec.parsed_message_html = html

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for rec in records:
            if rec.severity in ['high', 'critical'] and rec.patient_id.doctor_id:
                rec.patient_id.message_subscribe(partner_ids=rec.patient_id.doctor_id.partner_id.ids)
        return records

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
            'state': 'resolved',
            'status': 'handled',
            'handled_at': fields.Datetime.now()
        })

    def _send_telegram(self, chat_id, message):
        if not chat_id: return
        # Securely pull the bot token from Odoo's internal configuration parameters
        token = self.env['ir.config_parameter'].sudo().get_param('health_monitoring.telegram_bot_token')
        if not token: 
            _logger.warning("Telegram Bot Token missing. Add 'health_monitoring.telegram_bot_token' to System Parameters.")
            return
            
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {'chat_id': chat_id, 'text': message, 'parse_mode': 'HTML'}
        try:
            requests.post(url, json=payload, timeout=5)
        except Exception as e:
            _logger.error(f"Telegram Delivery Failed: {e}")

    @api.model
    def _cron_escalate_alerts(self):
        pending_alerts = self.search([('status', '=', 'pending')])
        now = fields.Datetime.now()
        
        for alert in pending_alerts:
            start_time = alert.created_at or alert.create_date
            if not start_time:
                continue
                
            elapsed_mins = (now - start_time).total_seconds() / 60.0
            
            if elapsed_mins > 30 and alert.escalation_level < 3:
                alert.write({
                    'escalation_level': 3,
                    'status': 'escalated'
                })
                alert.message_post(
                    body=Markup("<span class='text-danger fw-bold'>CRITICAL ESCALATION:</span> Alert unresolved for over 30 minutes. Status transition to Escalated."),
                    message_type="notification"
                )
                
            elif elapsed_mins > 15 and alert.escalation_level < 2:
                alert.write({'escalation_level': 2})
                boss_group = self.env.ref('health_monitoring.group_health_admin', raise_if_not_found=False)
                boss_users = boss_group.users if boss_group else self.env['res.users']
                if boss_users:
                    mentions = ", ".join([f"<a href='#' data-oe-model='res.users' data-oe-id='{u.id}'>@{u.name}</a>" for u in boss_users])
                    alert.message_post(
                        body=Markup(f"<span class='text-warning fw-bold'>ESCALATION LEVEL 2:</span> Alert unresolved for over 15 minutes. Notifying Administrators: {mentions}"),
                        partner_ids=boss_users.mapped('partner_id').ids,
                        message_type="notification"
                    )
                    # Trigger Telegram Pipeline for all Admins
                    for boss in boss_users:
                        if boss.telegram_chat_id:
                            tg_msg = f"⚠️ <b>LEVEL 2 ESCALATION</b> ⚠️\n\nPatient: {alert.patient_id.name}\nAlert: {alert.headline}\nDelay: 15+ Minutes!\n\n<i>This alert was ignored by the assigned doctor and has routed to Administration.</i>"
                            alert._send_telegram(boss.telegram_chat_id, tg_msg)
                else:
                    alert.message_post(
                        body=Markup("<span class='text-warning fw-bold'>ESCALATION LEVEL 2:</span> Alert unresolved for over 15 minutes. (No administrators found to notify)."),
                        message_type="notification"
                    )
            
            elif elapsed_mins > 5 and alert.escalation_level < 1:
                alert.write({'escalation_level': 1})
                doc = alert.assigned_doctor_id or alert.doctor_id
                if doc:
                    mention = f"<a href='#' data-oe-model='res.users' data-oe-id='{doc.id}'>@{doc.name}</a>"
                    alert.message_post(
                        body=Markup(f"<span class='text-info fw-bold'>ESCALATION LEVEL 1:</span> Alert unresolved for over 5 minutes. Notifying Doctor: {mention}"),
                        partner_ids=doc.partner_id.ids,
                        message_type="notification"
                    )
                    # Trigger Telegram Pipeline for the Doctor
                    if doc.telegram_chat_id:
                        tg_msg = f"🚨 <b>LEVEL 1 ESCALATION</b> 🚨\n\nPatient: {alert.patient_id.name}\nAlert: {alert.headline}\nDelay: 5+ Minutes!\n\n<i>Immediate clinical review required on the dashboard!</i>"
                        alert._send_telegram(doc.telegram_chat_id, tg_msg)
                else:
                    alert.message_post(
                        body=Markup("<span class='text-info fw-bold'>ESCALATION LEVEL 1:</span> Alert unresolved for over 5 minutes. (No specific doctor to notify)."),
                        message_type="notification"
                    )
