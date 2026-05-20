from odoo import models, fields, api
from odoo.exceptions import ValidationError


class PatientAdmitWizard(models.TransientModel):
    _name = 'health.patient.admit.wizard'
    _description = 'Admit Patient to Ward'

    patient_id = fields.Many2one('health.patient', 'Patient', required=True, readonly=True)
    patient_name = fields.Char(related='patient_id.name', readonly=True)
    current_status = fields.Selection(related='patient_id.admission_status', readonly=True)
    ai_recommended_ward_id = fields.Many2one(related='patient_id.ai_recommended_ward_id', readonly=True, string='AI Recommended Ward')
    ai_recommendation_msg = fields.Char(related='patient_id.ai_recommendation_msg', readonly=True)
    risk_level = fields.Selection(related='patient_id.risk_level', readonly=True)

    ward_id = fields.Many2one(
        'health.ward',
        string='Assign to Ward',
        required=True,
        help="Select the ward to admit this patient to.",
    )
    notes = fields.Text(
        'Admission Notes',
        placeholder='Optional: enter any clinical notes for this admission...',
    )

    @api.onchange('patient_id')
    def _onchange_patient(self):
        """Pre-fill ward from AI recommendation if available."""
        if self.patient_id and self.patient_id.ai_recommended_ward_id:
            self.ward_id = self.patient_id.ai_recommended_ward_id
        elif self.patient_id and self.patient_id.ward_id:
            self.ward_id = self.patient_id.ward_id

    def action_confirm_admit(self):
        self.ensure_one()
        patient = self.patient_id
        patient._ensure_can_admit()

        if patient.admission_status == 'admitted':
            raise ValidationError(f"{patient.name} is already admitted.")
        if patient.admission_status == 'discharged':
            raise ValidationError(f"{patient.name} has been discharged. Please reactivate first.")

        body = f"Patient admitted to <b>{self.ward_id.name}</b>."
        if self.notes:
            body += f"<br/>Notes: {self.notes}"

        patient.write({
            'ward_id': self.ward_id.id,
            'admission_status': 'admitted',
        })
        patient.sudo().message_post(body=body)

        return {'type': 'ir.actions.act_window_close'}
