import re
from odoo import api, fields, models


def _strip_html_tags(text):
    """Remove HTML/XML tags from a string, collapse whitespace."""
    if not text:
        return ''
    clean = re.sub(r'<[^>]+>', ' ', str(text))
    clean = re.sub(r'[ \t]+', ' ', clean).strip()
    return clean


class HealthNotificationLog(models.Model):
    _name = 'health.notification.log'
    _description = 'Clinical Notification Audit Log'
    _order = 'create_date desc'

    def _auto_init(self):
        res = super()._auto_init()
        self._create_performance_indexes()
        return res

    def init(self):
        self._create_performance_indexes()

    def _create_performance_indexes(self):
        self.env.cr.execute("CREATE INDEX IF NOT EXISTS health_notification_log_create_idx ON health_notification_log (create_date DESC)")
        self.env.cr.execute("CREATE INDEX IF NOT EXISTS health_notification_log_cooldown_idx ON health_notification_log (alert_id, user_id, channel, purpose, result, create_date DESC)")

    alert_id = fields.Many2one('health.alert', 'Alert', ondelete='cascade', index=True)
    patient_id = fields.Many2one('health.patient', 'Patient', index=True)
    user_id = fields.Many2one('res.users', 'Recipient User', index=True)
    channel = fields.Selection([
        ('telegram', 'Telegram'),
        ('odoo_chatter', 'Odoo Chatter'),
        ('system', 'System'),
    ], required=True, index=True)
    purpose = fields.Selection([
        ('telegram_verification', 'Telegram Verification'),
        ('initial_alert', 'Initial Alert'),
        ('escalation_l1', 'Escalation Level 1'),
        ('escalation_l2', 'Escalation Level 2'),
        ('escalation_l3', 'Escalation Level 3'),
    ], required=True, index=True)
    recipient = fields.Char('Recipient')
    result = fields.Selection([
        ('sent', 'Sent'),
        ('failed', 'Failed'),
        ('skipped', 'Skipped'),
        ('cooldown', 'Cooldown'),
    ], required=True, index=True)
    result_detail = fields.Text('Result Detail')
    payload_excerpt = fields.Text('Payload Excerpt')
    cooldown_until = fields.Datetime('Cooldown Until')

    @api.model_create_multi
    def create(self, vals_list):
        """Strip HTML tags from payload_excerpt before storage."""
        for vals in vals_list:
            raw = vals.get('payload_excerpt') or ''
            vals['payload_excerpt'] = _strip_html_tags(raw)[:500]
        return super().create(vals_list)
