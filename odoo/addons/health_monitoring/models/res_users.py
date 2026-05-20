import random
from datetime import timedelta

from odoo import api, models, fields, _
from odoo.exceptions import ValidationError

class ResUsers(models.Model):
    _inherit = 'res.users'

    telegram_chat_id = fields.Char(
        string='Verified Telegram Chat ID',
        readonly=True,
        help="Verified Telegram Chat ID used for clinical notifications."
    )
    telegram_pending_chat_id = fields.Char(
        string='Telegram Chat ID to Verify',
        help="Enter your Telegram chat ID here, then request a verification code."
    )
    telegram_verification_code = fields.Char('Telegram Verification Code', readonly=True, copy=False)
    telegram_verification_input = fields.Char('Verification Code', copy=False)
    telegram_verification_sent_at = fields.Datetime('Verification Sent At', readonly=True)
    telegram_verified_at = fields.Datetime('Telegram Verified At', readonly=True)
    telegram_chat_verified = fields.Boolean(
        'Telegram Verified',
        compute='_compute_telegram_chat_verified',
        store=True,
    )

    @api.depends('telegram_chat_id', 'telegram_verified_at')
    def _compute_telegram_chat_verified(self):
        for user in self:
            user.telegram_chat_verified = bool(user.telegram_chat_id and user.telegram_verified_at)

    def write(self, vals):
        if vals.get('telegram_chat_id') and not self.env.context.get('telegram_verified_write'):
            raise ValidationError(_("Telegram chat IDs must be verified before activation."))
        if vals.get('telegram_pending_chat_id'):
            vals['telegram_pending_chat_id'] = vals['telegram_pending_chat_id'].strip()
        return super().write(vals)

    def action_request_telegram_verification(self):
        for user in self:
            chat_id = (user.telegram_pending_chat_id or '').strip()
            if not chat_id:
                raise ValidationError(_("Enter a Telegram chat ID to verify."))
            cutoff = fields.Datetime.now() - timedelta(minutes=1)
            if self.env['health.notification.log'].sudo().search([
                ('user_id', '=', user.id),
                ('channel', '=', 'telegram'),
                ('purpose', '=', 'telegram_verification'),
                ('result', 'in', ['sent', 'failed']),
                ('create_date', '>=', cutoff),
            ], limit=1):
                raise ValidationError(_("A Telegram verification was requested recently. Please wait before requesting another code."))
            code = f"{random.SystemRandom().randint(100000, 999999)}"
            message = _(
                "SmartLab Telegram verification code: %s\n"
                "Enter this code in your SmartLab profile to activate clinical alerts."
            ) % code
            user.sudo().write({
                'telegram_verification_code': code,
                'telegram_verification_sent_at': fields.Datetime.now(),
            })
            self.env['health.alert'].sudo()._send_telegram_to_chat(
                chat_id,
                message,
                bot_type='doctor',
                user=user,
                purpose='telegram_verification',
                cooldown_minutes=1,
            )
        return True

    def action_confirm_telegram_verification(self):
        for user in self:
            entered = (user.telegram_verification_input or '').strip()
            expected = (user.telegram_verification_code or '').strip()
            if not entered or entered != expected:
                raise ValidationError(_("Invalid Telegram verification code."))
            if not user.telegram_pending_chat_id:
                raise ValidationError(_("No pending Telegram chat ID to verify."))
            user.sudo().with_context(telegram_verified_write=True).write({
                'telegram_chat_id': user.telegram_pending_chat_id.strip(),
                'telegram_pending_chat_id': False,
                'telegram_verification_code': False,
                'telegram_verification_input': False,
                'telegram_verified_at': fields.Datetime.now(),
            })
        return True

    def action_clear_telegram_chat(self):
        self.sudo().with_context(telegram_verified_write=True).write({
            'telegram_chat_id': False,
            'telegram_pending_chat_id': False,
            'telegram_verification_code': False,
            'telegram_verification_input': False,
            'telegram_verified_at': False,
        })
        return True

    @property
    def SELF_READABLE_FIELDS(self):
        return super().SELF_READABLE_FIELDS + [
            'telegram_chat_id',
            'telegram_pending_chat_id',
            'telegram_verification_input',
            'telegram_verification_sent_at',
            'telegram_verified_at',
            'telegram_chat_verified',
        ]

    @property
    def SELF_WRITEABLE_FIELDS(self):
        return super().SELF_WRITEABLE_FIELDS + [
            'telegram_pending_chat_id',
            'telegram_verification_input',
        ]
