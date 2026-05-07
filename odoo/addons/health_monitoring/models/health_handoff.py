from odoo import models, fields, api

class HealthHandoff(models.Model):
    _name = 'health.handoff'
    _description = 'Nurse Shift Handoff'
    _order = 'create_date desc'

    outgoing_nurse_id = fields.Many2one('res.users', 'Outgoing Nurse', default=lambda self: self.env.user, required=True)
    incoming_nurse_id = fields.Many2one('res.users', 'Incoming Nurse', required=True)
    notes = fields.Text('Handoff Notes', required=True)
    ward_id = fields.Many2one('health.ward', 'Ward')

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for rec in records:
            if rec.ward_id:
                msg = f"<p><b>Shift Handoff Logged</b><br/>"
                msg += f"<b>Outgoing:</b> {rec.outgoing_nurse_id.name}<br/>"
                msg += f"<b>Incoming:</b> {rec.incoming_nurse_id.name}<br/>"
                msg += f"<b>Notes:</b> {rec.notes}</p>"
                rec.ward_id.message_post(body=msg, subject="Shift Handoff")
        return records
