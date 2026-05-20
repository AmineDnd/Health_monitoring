from odoo import models, fields, api, _


class HealthVitalConfirmWizard(models.TransientModel):
    """
    Confirmation wizard shown when a nurse enters extreme vital values.
    Opens as target='new' in a native Odoo modal dialog on top of the vitals form.

    action_reenter re-opens the vitals form.
    action_confirm returns act_window_close, which cascades to close the parent form too.
    """
    _name = 'health.vital.confirm.wizard'
    _description = 'Extreme Vital Values Confirmation'

    vital_record_id = fields.Many2one(
        'health.vital.record',
        string='Vital Record',
        required=True,
        ondelete='cascade',
    )
    warnings_text = fields.Text(string='Warnings', readonly=True)
    confirmation_notes = fields.Text(
        string='Confirmation Notes',
        required=True,
        help="Document how the reading was verified before AI analysis and alerts run.",
    )

    def action_confirm(self):
        """
        Nurse confirmed values are real.
        Returning the result of action_manual_save_close() from a wizard causes Odoo to:
        1. Close this wizard dialog
        2. Execute act_window_close in the parent context, closing the vitals form too.
        One click, both dialogs close, nurse returns to dashboard.
        """
        return self.vital_record_id.action_confirm_extreme_values(self.confirmation_notes)

    def action_reenter(self):
        """
        Nurse wants to fix the values.
        Explicitly re-open the vitals form at the same record ID.
        This replaces the wizard dialog with the vitals form dialog so nurses can edit and re-submit.
        """
        return {
            'type': 'ir.actions.act_window',
            'name': 'Clinical Checkup',
            'res_model': 'health.vital.record',
            'res_id': self.vital_record_id.id,
            'views': [[False, 'form']],
            'target': 'new',
        }
