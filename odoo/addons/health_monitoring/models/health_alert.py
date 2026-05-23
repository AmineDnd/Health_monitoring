from odoo import models, fields, api
from odoo.exceptions import AccessError, ValidationError
from markupsafe import Markup, escape
from datetime import timedelta
import requests
import logging

_logger = logging.getLogger(__name__)

class HealthAlert(models.Model):
    _name = 'health.alert'
    _description = 'Health Alert'
    _order = 'create_date desc'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    def _auto_init(self):
        res = super()._auto_init()
        self._create_performance_indexes()
        return res

    def init(self):
        self._create_performance_indexes()

    def _create_performance_indexes(self):
        self.env.cr.execute("CREATE INDEX IF NOT EXISTS health_alert_patient_state_idx ON health_alert (patient_id, state)")
        self.env.cr.execute("CREATE INDEX IF NOT EXISTS health_alert_state_status_severity_idx ON health_alert (state, status, severity)")
        self.env.cr.execute("CREATE INDEX IF NOT EXISTS health_alert_create_severity_idx ON health_alert (create_date DESC, severity)")
        self.env.cr.execute("CREATE INDEX IF NOT EXISTS health_alert_assigned_state_idx ON health_alert (assigned_doctor_id, state)")
        self.env.cr.execute("CREATE INDEX IF NOT EXISTS health_alert_escalation_idx ON health_alert (status, escalation_level, create_date DESC)")

    patient_id = fields.Many2one('health.patient', 'Patient', required=True, ondelete='cascade', tracking=True, index=True)
    vital_record_id = fields.Many2one('health.vital.record', 'Triggering Vital', index=True)
    doctor_id = fields.Many2one('res.users', related='patient_id.doctor_id', string='Assigned Doctor', store=True, index=True)
    
    severity = fields.Selection([
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('critical', 'Critical')
    ], 'Severity', required=True, tracking=True, index=True)
    
    status = fields.Selection([
        ('pending', 'Pending'),
        ('handled', 'Handled'),
        ('escalated', 'Escalated')
    ], 'Status', default='pending', tracking=True, index=True)
    
    created_at = fields.Datetime('Created At', default=fields.Datetime.now, readonly=True, index=True)
    handled_at = fields.Datetime('Handled At', readonly=True, index=True)
    assigned_doctor_id = fields.Many2one('res.users', 'Assigned Doctor', index=True)
    escalation_level = fields.Integer('Escalation Level', default=0, index=True)
    
    headline = fields.Char('Alert Headline', compute='_compute_headline', store=True)
    
    response_time_minutes = fields.Float(
        'Response Time (min)',
        compute='_compute_response_time',
        store=True,
        help="Minutes from alert creation to being handled"
    )
    
    resolution_notes = fields.Text('Resolution Notes', tracking=True)
    notification_log_ids = fields.One2many('health.notification.log', 'alert_id', 'Notification Audit Logs')

    @api.depends('created_at', 'handled_at', 'status')
    def _compute_response_time(self):
        for rec in self:
            if rec.status == 'handled' and rec.handled_at and rec.created_at:
                delta = rec.handled_at - rec.created_at
                rec.response_time_minutes = round(delta.total_seconds() / 60.0, 1)
            else:
                rec.response_time_minutes = 0.0
    
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

    # Patient notes surfaced read-only on the alert for quick clinical context
    patient_nurse_notes = fields.Text(
        related='patient_id.nurse_notes',
        string='Nurse Notes',
        readonly=True,
    )
    patient_doctor_notes = fields.Text(
        related='patient_id.doctor_notes',
        string='Doctor Notes',
        readonly=True,
    )
    ai_confidence = fields.Float(
        'AI Anomaly Score (%)',
        help="Anomaly score from the AI model (0-100%). This is not a clinical confidence value.",
    )
    
    @api.depends('message')
    def _compute_parsed_message(self):
        for rec in self:
            msg = rec.message or ""
            if not msg:
                rec.parsed_message_html = False
                continue
            
            html = "<div class='sl-clinical-narrative'>"
            
            # --- INJECT CLINICAL CONTEXT ---
            profile = rec.patient_id.lifestyle_profile.title() if rec.patient_id.lifestyle_profile else 'Standard'
            age = rec.patient_id.age or 0
            
            html += f"<div class='mb-3 p-3 rounded' style='background-color: #F8FAFC; border-left: 4px solid #3B82F6; font-size: 0.9em;'>"
            html += f"<div class='d-flex align-items-center mb-2'><i class='fa fa-user-md text-primary me-2'></i><strong class='text-dark'>Patient Clinical Context</strong></div>"
            html += f"<div class='d-flex gap-3 mb-1'>"
            html += f"<div><span class='text-muted'>Age:</span> <strong>{age}</strong></div>"
            html += f"<div><span class='text-muted'>Profile:</span> <span class='badge bg-info text-dark'>{profile}</span></div>"
            html += f"</div>"
            html += f"<div class='text-muted small'><em>* AI boundary thresholds dynamically adapted for this specific demographic.</em></div>"
            html += f"</div>"
            # -------------------------------
            
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
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url', 'http://localhost:8069')
        
        for rec in records:
            if rec.severity in ['high', 'critical']:
                # Extract AI Action from message
                ai_action = "Review required."
                msg_parts = (rec.message or "").split('|')
                for part in msg_parts:
                    if part.strip().startswith('Action:'):
                        ai_action = part.replace('Action:', '').strip()
                        break
                        
                profile = rec.patient_id.lifestyle_profile.title() if rec.patient_id.lifestyle_profile else 'Standard'
                age = rec.patient_id.age or 0
                
                partners_to_notify = self.env['res.partner']
                doctors_to_ping = self.env['res.users']
                
                ward_name = rec.patient_id.ward_id.name if rec.patient_id.ward_id else 'Triage'
                
                if rec.patient_id.ward_id:
                    doctors_to_ping |= rec.patient_id.ward_id.doctor_ids
                elif rec.patient_id.admission_status == 'triage':
                    # AI-DRIVEN TRIAGE ROUTING
                    recommended_ward = False
                    if 'ICU' in ai_action:
                        recommended_ward = self.env['health.ward'].search([('ward_type', '=', 'icu')], limit=1)
                    elif 'Pediatrics' in ai_action:
                        recommended_ward = self.env['health.ward'].search([('ward_type', '=', 'pediatrics')], limit=1)
                    else:
                        recommended_ward = self.env['health.ward'].search([('ward_type', '=', 'general')], limit=1)
                        
                    if recommended_ward:
                        doctors_to_ping |= recommended_ward.doctor_ids
                        ward_name = f"Triage -> Routing to {recommended_ward.name}"
                
                if rec.patient_id.doctor_id:
                    doctors_to_ping |= rec.patient_id.doctor_id
                    
                # Direct Deep Link to this specific alert
                alert_url = f"{base_url}/web#id={rec.id}&model=health.alert&view_type=form"
                
                # Telegram Message Payload
                anomaly_score_text = f"{int(rec.ai_confidence)}%" if rec.ai_confidence else "N/A"
                severity_label = "CRITICAL" if rec.severity == 'critical' else "HIGH"
                tg_msg = (
                    f"<b>SMARTLAB CLINICAL ALERT</b>\n"
                    f"------------------------\n"
                    f"<b>Ward:</b> {ward_name}\n"
                    f"<b>Priority:</b> {severity_label}\n\n"
                    f"<b>Patient Information</b>\n"
                    f"- <b>Name:</b> {rec.patient_id.name}\n"
                    f"- <b>Context:</b> Age {age} | {profile}\n\n"
                    f"<b>AI Clinical Assessment</b>\n"
                    f"- <b>Analysis:</b> {rec.headline}\n"
                    f"- <b>Directive:</b> <i>{ai_action}</i>\n"
                    f"- <b>Anomaly Score:</b> {anomaly_score_text}\n\n"
                    f"<b>Status:</b> UNCLAIMED\n"
                    f"------------------------\n"
                    f"<a href='{alert_url}'>Open alert in SmartLab</a>"
                )
                
                if doctors_to_ping:
                    # 1. Send Instant Telegrams
                    rec._notify_users(
                        doctors_to_ping,
                        'telegram',
                        tg_msg,
                        purpose='initial_alert',
                        cooldown_minutes=10,
                    )
                            
                    # 2. Loud Odoo Chatter Ping
                    partners_to_notify = doctors_to_ping.mapped('partner_id')
                    mentions = ", ".join([f"<a href='#' data-oe-model='res.users' data-oe-id='{u.id}'>@{u.name}</a>" for u in doctors_to_ping])
                    
                    odoo_msg = (
                        f"<p><span class='text-danger fw-bold'>URGENT:</span> {mentions}</p>"
                        f"<p>A new <b>UNCLAIMED</b> alert has arrived in <b>{ward_name}</b>.</p>"
                        f"<p><b>AI Directive:</b> {ai_action}</p>"
                        f"<p>Please review and <a href='{alert_url}'>Claim the Alert</a> immediately.</p>"
                    )
                    
                    rec._notify_users(
                        doctors_to_ping,
                        'odoo_chatter',
                        Markup(odoo_msg),
                        purpose='initial_alert',
                        cooldown_minutes=5,
                    )
        return records

    acknowledged = fields.Boolean('Acknowledged', default=False, tracking=True)
    acknowledged_by = fields.Many2one('res.users', 'Acknowledged By')
    acknowledged_at = fields.Datetime('Acknowledged At')
    
    state = fields.Selection([
        ('new', 'New'),
        ('investigating', 'Investigating'),
        ('resolved', 'Resolved')
    ], 'State', default='new', tracking=True, index=True)

    def _ensure_can_handle_alert(self):
        if not (
            self.env.user.has_group('health_monitoring.group_health_doctor')
            or self.env.user.has_group('health_monitoring.group_health_admin')
        ):
            raise AccessError("Only doctors and administrators can handle clinical alerts.")

    def _ensure_alert_is_open(self):
        for rec in self:
            if rec.state == 'resolved' or rec.status == 'handled':
                raise ValidationError("Resolved alerts cannot be claimed, acknowledged, or resolved again.")

    def action_claim_alert(self):
        self._ensure_can_handle_alert()
        self._ensure_alert_is_open()
        for rec in self:
            if rec.assigned_doctor_id and rec.assigned_doctor_id != self.env.user and not self.env.user.has_group('health_monitoring.group_health_admin'):
                raise AccessError("This alert is already assigned to another doctor.")
            if not rec.assigned_doctor_id:
                rec.write({
                    'assigned_doctor_id': self.env.user.id,
                    'state': 'investigating',
                })
                rec.sudo().message_post(body=Markup(f"Alert claimed by {escape(self.env.user.name)}."))
        return True

    def action_acknowledge(self):
        self._ensure_can_handle_alert()
        self._ensure_alert_is_open()
        for rec in self:
            if rec.assigned_doctor_id and rec.assigned_doctor_id != self.env.user and not self.env.user.has_group('health_monitoring.group_health_admin'):
                raise AccessError("Only the assigned doctor or an administrator can acknowledge this alert.")
            # Auto-claim if acknowledging without being assigned
            if not rec.assigned_doctor_id:
                rec.assigned_doctor_id = self.env.user.id
                
            rec.write({
                'acknowledged': True,
                'acknowledged_by': self.env.user.id,
                'acknowledged_at': fields.Datetime.now(),
                'state': 'investigating'
            })
        return True
        
    def action_resolve(self):
        self.ensure_one()
        self._ensure_can_handle_alert()
        self._ensure_alert_is_open()
        if self.assigned_doctor_id and self.assigned_doctor_id != self.env.user and not self.env.user.has_group('health_monitoring.group_health_admin'):
            raise AccessError("Only the assigned doctor or an administrator can resolve this alert.")
        # Auto-claim if not yet assigned, so doctor can resolve in one step
        if not self.assigned_doctor_id:
            self.write({
                'assigned_doctor_id': self.env.user.id,
                'state': 'investigating',
            })
        return {
            'name': 'Resolve Alert',
            'type': 'ir.actions.act_window',
            'res_model': 'health.alert.resolve.wizard',
            'view_mode': 'form',
            'views': [[False, 'form']],
            'target': 'new',
            'context': {'default_alert_id': self.id}
        }

    def _notification_log_vals(self, user, channel, purpose, recipient, result, message, detail=False, cooldown_until=False):
        self.ensure_one()
        return {
            'alert_id': self.id,
            'patient_id': self.patient_id.id if self.patient_id else False,
            'user_id': user.id if user else False,
            'channel': channel,
            'purpose': purpose,
            'recipient': recipient,
            'result': result,
            'result_detail': detail,
            'payload_excerpt': (str(message or '')[:500]),
            'cooldown_until': cooldown_until,
        }

    def _has_recent_notification(self, user, channel, purpose, cooldown_minutes):
        if not cooldown_minutes or not self:
            return False
        cutoff = fields.Datetime.now() - timedelta(minutes=cooldown_minutes)
        return bool(self.env['health.notification.log'].sudo().search([
            ('alert_id', '=', self.id),
            ('user_id', '=', user.id if user else False),
            ('channel', '=', channel),
            ('purpose', '=', purpose),
            ('result', '=', 'sent'),
            ('create_date', '>=', cutoff),
        ], limit=1))

    def _notify_users(self, users, channel, message, purpose, cooldown_minutes=0, bot_type='doctor'):
        self.ensure_one()
        if self.state == 'resolved' or self.status == 'handled':
            for user in users:
                self.env['health.notification.log'].sudo().create(
                    self._notification_log_vals(user, channel, purpose, False, 'skipped', message, 'Alert already resolved or handled.')
                )
            return False

        users = users.filtered(lambda user: bool(user.active))
        if not users:
            self.env['health.notification.log'].sudo().create(
                self._notification_log_vals(False, channel, purpose, False, 'skipped', message, 'No active recipients.')
            )
            return False

        if channel == 'telegram':
            for user in users:
                if self._has_recent_notification(user, channel, purpose, cooldown_minutes):
                    self.env['health.notification.log'].sudo().create(
                        self._notification_log_vals(
                            user,
                            channel,
                            purpose,
                            user.telegram_chat_id,
                            'cooldown',
                            message,
                            'Recent successful notification exists.',
                            fields.Datetime.now() + timedelta(minutes=cooldown_minutes),
                        )
                    )
                    continue
                if not user.telegram_chat_verified or not user.telegram_chat_id:
                    self.env['health.notification.log'].sudo().create(
                        self._notification_log_vals(user, channel, purpose, False, 'skipped', message, 'Telegram chat ID is not verified.')
                    )
                    continue
                self._send_telegram_to_chat(
                    user.telegram_chat_id,
                    message,
                    bot_type=bot_type,
                    alert=self,
                    user=user,
                    purpose=purpose,
                    cooldown_minutes=cooldown_minutes,
                )
            return True

        if channel == 'odoo_chatter':
            users_to_notify = self.env['res.users']
            for user in users:
                if self._has_recent_notification(user, channel, purpose, cooldown_minutes):
                    self.env['health.notification.log'].sudo().create(
                        self._notification_log_vals(user, channel, purpose, user.partner_id.email or user.name, 'cooldown', message, 'Recent chatter notification exists.')
                    )
                else:
                    users_to_notify |= user
            if users_to_notify:
                self.with_context(mail_notify_noemail=True).message_post(
                    body=message,
                    message_type="notification",
                    partner_ids=users_to_notify.mapped('partner_id').ids,
                )
                for user in users_to_notify:
                    self.env['health.notification.log'].sudo().create(
                        self._notification_log_vals(user, channel, purpose, user.partner_id.email or user.name, 'sent', message)
                    )
            return True

        return False

    @api.model
    def _send_telegram_to_chat(self, chat_id, message, bot_type='doctor', alert=False, user=False, purpose='initial_alert', cooldown_minutes=0):
        Log = self.env['health.notification.log'].sudo()
        if not chat_id:
            Log.create({
                'alert_id': alert.id if alert else False,
                'patient_id': alert.patient_id.id if alert and alert.patient_id else False,
                'user_id': user.id if user else False,
                'channel': 'telegram',
                'purpose': purpose,
                'recipient': False,
                'result': 'skipped',
                'result_detail': 'Missing Telegram chat ID.',
                'payload_excerpt': str(message or '')[:500],
            })
            return False
        if user and cooldown_minutes:
            cutoff = fields.Datetime.now() - timedelta(minutes=cooldown_minutes)
            if Log.search([
                ('user_id', '=', user.id),
                ('channel', '=', 'telegram'),
                ('purpose', '=', purpose),
                ('result', 'in', ['sent', 'failed']),
                ('create_date', '>=', cutoff),
            ], limit=1):
                Log.create({
                    'alert_id': alert.id if alert else False,
                    'patient_id': alert.patient_id.id if alert and alert.patient_id else False,
                    'user_id': user.id,
                    'channel': 'telegram',
                    'purpose': purpose,
                    'recipient': chat_id,
                    'result': 'cooldown',
                    'result_detail': 'Recent Telegram notification attempt exists.',
                    'payload_excerpt': str(message or '')[:500],
                    'cooldown_until': fields.Datetime.now() + timedelta(minutes=cooldown_minutes),
                })
                return False

        # Securely pull the bot token from Odoo's internal configuration parameters
        sudo_env = self.env['ir.config_parameter'].sudo()
        if bot_type == 'admin':
            token = sudo_env.get_param('health_monitoring.telegram_admin_bot_token')
            if not token:
                token = sudo_env.get_param('health_monitoring.telegram_bot_token')
        else:
            token = sudo_env.get_param('health_monitoring.telegram_bot_token')
            
        if not token:
            _logger.warning("Telegram Bot Token missing.")
            Log.create({
                'alert_id': alert.id if alert else False,
                'patient_id': alert.patient_id.id if alert and alert.patient_id else False,
                'user_id': user.id if user else False,
                'channel': 'telegram',
                'purpose': purpose,
                'recipient': chat_id,
                'result': 'failed',
                'result_detail': 'Telegram bot token missing.',
                'payload_excerpt': str(message or '')[:500],
            })
            return False
            
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {'chat_id': chat_id, 'text': message, 'parse_mode': 'HTML'}
        try:
            resp = requests.post(url, json=payload, timeout=5)
            if 200 <= resp.status_code < 300:
                Log.create({
                    'alert_id': alert.id if alert else False,
                    'patient_id': alert.patient_id.id if alert and alert.patient_id else False,
                    'user_id': user.id if user else False,
                    'channel': 'telegram',
                    'purpose': purpose,
                    'recipient': chat_id,
                    'result': 'sent',
                    'result_detail': 'Delivered to Telegram API.',
                    'payload_excerpt': str(message or '')[:500],
                    'cooldown_until': fields.Datetime.now() + timedelta(minutes=cooldown_minutes) if cooldown_minutes else False,
                })
                return True
            Log.create({
                'alert_id': alert.id if alert else False,
                'patient_id': alert.patient_id.id if alert and alert.patient_id else False,
                'user_id': user.id if user else False,
                'channel': 'telegram',
                'purpose': purpose,
                'recipient': chat_id,
                'result': 'failed',
                'result_detail': f'Telegram API status {resp.status_code}: {resp.text[:200]}',
                'payload_excerpt': str(message or '')[:500],
            })
            return False
        except Exception as e:
            _logger.error(f"Telegram Delivery Failed: {e}")
            Log.create({
                'alert_id': alert.id if alert else False,
                'patient_id': alert.patient_id.id if alert and alert.patient_id else False,
                'user_id': user.id if user else False,
                'channel': 'telegram',
                'purpose': purpose,
                'recipient': chat_id,
                'result': 'failed',
                'result_detail': str(e),
                'payload_excerpt': str(message or '')[:500],
            })
            return False

    def _send_telegram(self, chat_id, message, bot_type='doctor'):
        return self._send_telegram_to_chat(chat_id, message, bot_type=bot_type, alert=self if self else False)

    @api.model
    def _cron_escalate_alerts(self):
        active_alerts = self.search([
            ('state', '!=', 'resolved'),
            ('status', '!=', 'handled'),
            ('severity', 'in', ['medium', 'high', 'critical']),
        ])
        for alert in active_alerts:
            level = alert._target_escalation_level()
            if not level or level <= alert.escalation_level:
                continue
            alert._apply_escalation_level(level)
        return True

    def _target_escalation_level(self):
        self.ensure_one()
        if self.state == 'resolved' or self.status == 'handled':
            return 0
        thresholds = {
            'critical': (5, 15, 30),
            'high': (15, 30, 60),
            'medium': (60, 120, 240),
        }.get(self.severity)
        if not thresholds:
            return 0

        start_time = self.acknowledged_at or self.created_at or self.create_date
        if not start_time:
            return 0
        elapsed_mins = (fields.Datetime.now() - start_time).total_seconds() / 60.0

        if elapsed_mins >= thresholds[2]:
            return 3
        if elapsed_mins >= thresholds[1]:
            return 2
        if elapsed_mins >= thresholds[0]:
            return 1
        return 0

    def _apply_escalation_level(self, level):
        self.ensure_one()
        if self.state == 'resolved' or self.status == 'handled':
            return False

        purpose = f'escalation_l{level}'
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url', 'http://localhost:8069')
        alert_url = f"{base_url}/web#id={self.id}&model=health.alert&view_type=form"
        ward_name = self.patient_id.ward_id.name if self.patient_id.ward_id else 'No Ward'
        acknowledged_label = 'acknowledged' if self.acknowledged_at else 'unacknowledged'
        assigned_label = self.assigned_doctor_id.name if self.assigned_doctor_id else 'unassigned'
        delay_start = self.acknowledged_at or self.created_at or self.create_date
        elapsed_mins = int((fields.Datetime.now() - delay_start).total_seconds() / 60.0) if delay_start else 0

        if level >= 2:
            self.write({'escalation_level': level, 'status': 'escalated'})
        else:
            self.write({'escalation_level': level})

        if level == 1:
            recipients = self._level_one_recipients()
        else:
            admin_group = self.env.ref('health_monitoring.group_health_admin', raise_if_not_found=False)
            recipients = admin_group.users if admin_group else self.env['res.users']

        if recipients:
            mentions = ', '.join([f"<a href='#' data-oe-model='res.users' data-oe-id='{u.id}'>@{u.name}</a>" for u in recipients])
            body = Markup(
                f"<span class='text-warning fw-bold'>ESCALATION LEVEL {level}:</span> "
                f"{self.severity.upper()} alert is still open after {elapsed_mins} minutes "
                f"({acknowledged_label}, {assigned_label}). Notifying: {mentions}."
            )
            self._notify_users(recipients, 'odoo_chatter', body, purpose=purpose, cooldown_minutes=10)

            tg_msg = (
                f"<b>SMARTLAB ESCALATION - LEVEL {level}</b>\n"
                f"<b>Ward:</b> {ward_name}\n"
                f"<b>Priority:</b> {self.severity.upper()}\n"
                f"<b>Status:</b> {acknowledged_label}, {assigned_label}\n"
                f"<b>Delay:</b> {elapsed_mins} minutes\n"
                f"<b>Patient:</b> {self.patient_id.name}\n"
                f"<b>Alert:</b> {self.headline}\n"
                f"<a href='{alert_url}'>Open alert</a>"
            )
            bot_type = 'admin' if level >= 2 else 'doctor'
            self._notify_users(recipients, 'telegram', tg_msg, purpose=purpose, cooldown_minutes=10, bot_type=bot_type)
        else:
            self.env['health.notification.log'].sudo().create(
                self._notification_log_vals(False, 'system', purpose, False, 'skipped', 'Escalation had no eligible recipients.', 'No recipients found.')
            )
        return True

    def _level_one_recipients(self):
        self.ensure_one()
        recipients = self.env['res.users']
        if self.assigned_doctor_id:
            recipients |= self.assigned_doctor_id
        elif self.patient_id.ward_id:
            recipients |= self.patient_id.ward_id.doctor_ids
        if self.patient_id.doctor_id:
            recipients |= self.patient_id.doctor_id
        return recipients
