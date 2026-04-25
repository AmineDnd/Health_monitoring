from odoo import models, fields, api

class HealthWard(models.Model):
    _name = 'health.ward'
    _description = 'Hospital Ward / Service'

    name = fields.Char('Ward Name', required=True)
    description = fields.Text('Description')
    
    ward_type = fields.Selection([
        ('general', 'General Admission'),
        ('icu', 'Intensive Care Unit (ICU)'),
        ('emergency', 'Emergency Room (ER)'),
        ('cardiology', 'Cardiology'),
        ('neurology', 'Neurology'),
        ('pediatrics', 'Pediatrics'),
        ('specialized', 'Other Specialized')
    ], string='Ward Type', default='general', required=True)
    
    capacity = fields.Integer('Bed Capacity', default=10, help="Total number of beds available in this ward.")
    current_occupancy = fields.Integer('Current Occupancy', compute='_compute_occupancy', store=True)
    
    floor_number = fields.Char('Floor / Location', help="e.g., 3rd Floor North Wing")
    contact_extension = fields.Char('Nurse Station Ext.', help="Internal phone extension")
    
    active_alert_count = fields.Integer('Active Alerts', compute='_compute_alert_counts')
    unclaimed_alert_count = fields.Integer('Unclaimed Alerts', compute='_compute_alert_counts')

    # Doctors assigned to this ward
    doctor_ids = fields.Many2many(
        'res.users', 
        string='Assigned Doctors',
        domain=lambda self: [('groups_id', 'in', self.env.ref('health_monitoring.group_health_doctor').id)]
    )
    
    patient_ids = fields.One2many('health.patient', 'ward_id', string='Patients')

    @api.depends('patient_ids')
    def _compute_occupancy(self):
        for rec in self:
            rec.current_occupancy = len(rec.patient_ids)
            
    def _compute_alert_counts(self):
        for rec in self:
            alerts = self.env['health.alert'].search([
                ('patient_id.ward_id', '=', rec.id),
                ('state', '!=', 'resolved')
            ])
            rec.active_alert_count = len(alerts)
            rec.unclaimed_alert_count = len(alerts.filtered(lambda a: not a.assigned_doctor_id))
