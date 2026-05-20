from odoo import models, fields, api

class HealthHandoff(models.Model):
    _name = 'health.handoff'
    _description = 'Nurse Shift Handoff'
    _order = 'create_date desc'

    def _auto_init(self):
        res = super()._auto_init()
        self._create_performance_indexes()
        return res

    def init(self):
        self._create_performance_indexes()

    def _create_performance_indexes(self):
        self.env.cr.execute("CREATE INDEX IF NOT EXISTS health_handoff_ward_create_idx ON health_handoff (ward_id, create_date DESC)")

    outgoing_nurse_id = fields.Many2one('res.users', 'Outgoing Nurse', default=lambda self: self.env.user, required=True, index=True)
    incoming_nurse_id = fields.Many2one('res.users', 'Incoming Nurse', required=True, index=True)
    notes = fields.Text('Handoff Notes', required=True)
    ward_id = fields.Many2one('health.ward', 'Ward', index=True)

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
