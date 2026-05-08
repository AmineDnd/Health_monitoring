from odoo import models, fields, api

class AlertResolveWizard(models.TransientModel):
    _name = 'health.alert.resolve.wizard'
    _description = 'Resolve Alert Wizard'

    alert_id = fields.Many2one('health.alert', 'Alert', required=True)
    resolution_notes = fields.Text('Resolution Notes', required=True)

    def action_confirm_resolve(self):
        self.ensure_one()
        from odoo import fields as odoo_fields
        self.alert_id.write({
            'state': 'resolved',
            'status': 'handled',
            'handled_at': odoo_fields.Datetime.now(),
            'resolution_notes': self.resolution_notes
        })
        self.alert_id.message_post(body=f"Alert resolved. Notes: {self.resolution_notes}")
        return {'type': 'ir.actions.act_window_close'}
