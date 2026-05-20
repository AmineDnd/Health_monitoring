from odoo import models, fields, api

class HealthWard(models.Model):
    _name = 'health.ward'
    _description = 'Hospital Ward / Service'
    _inherit = ['mail.thread']

    def _auto_init(self):
        res = super()._auto_init()
        self._create_performance_indexes()
        return res

    def init(self):
        self._create_performance_indexes()

    def _create_performance_indexes(self):
        self.env.cr.execute("CREATE INDEX IF NOT EXISTS health_ward_type_idx ON health_ward (ward_type)")

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
    ], string='Ward Type', default='general', required=True, index=True)
    
    capacity = fields.Integer('Bed Capacity', default=10, help="Total number of beds available in this ward.")
    current_occupancy = fields.Integer('Current Occupancy', compute='_compute_occupancy', store=True)
    capacity_percentage = fields.Float('Capacity %', compute='_compute_capacity_percentage', store=True)
    
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

    @api.depends('patient_ids', 'patient_ids.admission_status')
    def _compute_occupancy(self):
        occupancy_by_ward = {}
        if self.ids:
            rows = self.env['health.patient'].read_group(
                [('ward_id', 'in', self.ids), ('admission_status', '=', 'admitted')],
                ['ward_id'],
                ['ward_id'],
                lazy=False,
            )
            occupancy_by_ward = {
                row['ward_id'][0]: row.get('__count', 0)
                for row in rows
                if row.get('ward_id')
            }
        for rec in self:
            rec.current_occupancy = occupancy_by_ward.get(rec.id, 0)

    @api.depends('capacity', 'current_occupancy')
    def _compute_capacity_percentage(self):
        for rec in self:
            if rec.capacity > 0:
                rec.capacity_percentage = (rec.current_occupancy / rec.capacity) * 100
            else:
                rec.capacity_percentage = 0.0
            
    def _compute_alert_counts(self):
        patients_by_id = {}
        active_by_ward = {ward_id: 0 for ward_id in self.ids}
        unclaimed_by_ward = {ward_id: 0 for ward_id in self.ids}
        if self.ids:
            patients = self.env['health.patient'].search([('ward_id', 'in', self.ids)])
            patients_by_id = {patient.id: patient for patient in patients}
            rows = self.env['health.alert'].read_group(
                [('patient_id', 'in', patients.ids), ('state', '!=', 'resolved')],
                ['patient_id', 'assigned_doctor_id'],
                ['patient_id', 'assigned_doctor_id'],
                lazy=False,
            )
            for row in rows:
                patient = row.get('patient_id')
                if not patient:
                    continue
                ward = patients_by_id.get(patient[0]).ward_id if patients_by_id.get(patient[0]) else False
                if not ward:
                    continue
                count = row.get('__count', 0)
                active_by_ward[ward.id] = active_by_ward.get(ward.id, 0) + count
                if not row.get('assigned_doctor_id'):
                    unclaimed_by_ward[ward.id] = unclaimed_by_ward.get(ward.id, 0) + count
        for rec in self:
            rec.active_alert_count = active_by_ward.get(rec.id, 0)
            rec.unclaimed_alert_count = unclaimed_by_ward.get(rec.id, 0)
