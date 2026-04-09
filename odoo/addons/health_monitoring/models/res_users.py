from odoo import models, fields

class ResUsers(models.Model):
    _inherit = 'res.users'

    telegram_chat_id = fields.Char(
        string='Telegram Chat ID', 
        help="Your personal Telegram Chat ID. The system will send critical AI alerts directly to your phone."
    )

    @property
    def SELF_READABLE_FIELDS(self):
        return super().SELF_READABLE_FIELDS + ['telegram_chat_id']

    @property
    def SELF_WRITEABLE_FIELDS(self):
        return super().SELF_WRITEABLE_FIELDS + ['telegram_chat_id']
