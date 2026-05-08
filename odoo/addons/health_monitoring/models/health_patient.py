from odoo import models, fields, api
from odoo.exceptions import AccessError, ValidationError

class HealthPatientTag(models.Model):
    _name = 'health.patient.tag'
    _description = 'Patient Tag'

    name = fields.Char('Tag Name', required=True)
    color = fields.Integer('Color Index')

class HealthPatient(models.Model):
    _name = 'health.patient'
    _description = 'Patient Registry'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char('Patient Name', required=True, tracking=True)
    image_1920 = fields.Image('Patient Photo', max_width=1920, max_height=1920)
    image_128 = fields.Image('Thumbnail', related='image_1920', max_width=128, max_height=128, store=True)
    date_of_birth = fields.Date('Date of Birth')
    age = fields.Integer('Age', compute='_compute_age', store=True, readonly=False, tracking=True)
    gender = fields.Selection([('male', 'Male'), ('female', 'Female'), ('other', 'Other')], 'Gender', required=True)
    category = fields.Selection([
        ('child', 'Child'),
        ('teen', 'Teen'),
        ('adult', 'Adult'),
        ('elderly', 'Elderly')
    ], 'Category', compute='_compute_category')
    tag_ids = fields.Many2many('health.patient.tag', string='Tags')
    
    ward_id = fields.Many2one('health.ward', string='Ward / Service', tracking=True)
    lifestyle_profile = fields.Selection([
        ('standard', 'Standard'),
        ('athlete', 'Athlete'),
        ('sedentary', 'Sedentary'),
        ('pregnant', 'Pregnant')
    ], string='Clinical Profile (Internal)', default='standard', tracking=True)

    profile_male = fields.Selection([
        ('standard', 'Standard'),
        ('athlete', 'Athlete'),
        ('sedentary', 'Sedentary')
    ], string='Clinical Profile', compute='_compute_profile', inverse='_inverse_profile')

    profile_female = fields.Selection([
        ('standard', 'Standard'),
        ('athlete', 'Athlete'),
        ('sedentary', 'Sedentary'),
        ('pregnant', 'Pregnant')
    ], string='Clinical Profile', compute='_compute_profile', inverse='_inverse_profile')

    @api.depends('lifestyle_profile')
    def _compute_profile(self):
        for rec in self:
            rec.profile_male = rec.lifestyle_profile if rec.lifestyle_profile != 'pregnant' else 'standard'
            rec.profile_female = rec.lifestyle_profile

    def _inverse_profile(self):
        for rec in self:
            if rec.gender == 'female':
                rec.lifestyle_profile = rec.profile_female
            else:
                rec.lifestyle_profile = rec.profile_male

    @api.depends('date_of_birth')
    def _compute_age(self):
        for rec in self:
            if rec.date_of_birth:
                today = fields.Date.today()
                dob = rec.date_of_birth
                age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
                rec.age = age
            elif not rec.age:
                rec.age = 0

    @api.onchange('age')
    def _onchange_age(self):
        if self.gender != 'female' and self.lifestyle_profile == 'pregnant':
            self.lifestyle_profile = 'standard'

    @api.onchange('gender')
    def _onchange_gender(self):
        if self.gender != 'female' and self.lifestyle_profile == 'pregnant':
            self.lifestyle_profile = 'standard'

    @api.constrains('age')
    def _check_age(self):
        for rec in self:
            if rec.age < 0 or rec.age > 130:
                raise ValidationError("Age must be between 0 and 130.")
    
    doctor_id = fields.Many2one('res.users', 'Assigned Doctor', tracking=True)
    
    status = fields.Selection([
        ('draft', 'Draft'),
        ('active', 'Active')
    ], 'Status', default='draft', tracking=True)
    
    admission_status = fields.Selection([
        ('triage', 'In Triage (ER)'),
        ('admitted', 'Admitted to Ward'),
        ('discharged', 'Discharged')
    ], string='Admission Status', default='triage', tracking=True)
    
    ai_recommended_ward_id = fields.Many2one('health.ward', string='AI Recommended Ward', tracking=True)
    ai_recommendation_msg = fields.Char('AI Recommendation Message', tracking=True)
    
    vitals_frequency_hours = fields.Float('Vitals Frequency (Hours)', default=4.0, tracking=True, 
                                          help="How often vitals should be logged for this patient.")
    
    is_doctor = fields.Boolean(compute='_compute_is_doctor')

    def _compute_is_doctor(self):
        for rec in self:
            rec.is_doctor = self.env.user.has_group('health_monitoring.group_health_doctor')

    def action_validate(self):
        for rec in self:
            if not self.env.user.has_group('health_monitoring.group_health_doctor'):
                raise AccessError("Only doctors can validate patient records.")
            rec.status = 'active'
            
    def action_admit(self):
        for rec in self:
            if not rec.ward_id:
                raise AccessError("Please select a Ward before admitting the patient.")
            rec.admission_status = 'admitted'
            rec.message_post(body=f"Patient officially admitted to {rec.ward_id.name}.")

    def action_admit_ai(self):
        for rec in self:
            if not rec.ai_recommended_ward_id:
                raise AccessError("No AI Recommended Ward to admit to.")
            rec.ward_id = rec.ai_recommended_ward_id
            rec.action_admit()
            
    def action_discharge(self):
        for rec in self:
            ward_name = rec.ward_id.name if rec.ward_id else 'the hospital'
            rec.admission_status = 'discharged'
            rec.ward_id = False
            
            # Auto-resolve active alerts for this patient
            active_alerts = self.env['health.alert'].search([
                ('patient_id', '=', rec.id),
                ('state', 'not in', ['resolved']),
            ])
            for alert in active_alerts:
                alert.write({
                    'status': 'handled',
                    'state': 'resolved',
                    'handled_at': fields.Datetime.now(),
                    'resolution_notes': 'Patient discharged from hospital. Alert auto-resolved.'
                })
            
            # Post message to chatter
            rec.message_post(
                body=f"Patient has been discharged from {ward_name}. {len(active_alerts)} active alert(s) auto-resolved."
            )
    
    @api.depends('age')
    def _compute_category(self):
        for rec in self:
            if not rec.age:
                rec.category = False
            elif rec.age < 13:
                rec.category = 'child'
            elif rec.age < 20:
                rec.category = 'teen'
            elif rec.age < 65:
                rec.category = 'adult'
            else:
                rec.category = 'elderly'

    risk_level = fields.Selection([
        ('low', 'Normal'),
        ('medium', 'Moderate'),
        ('high', 'High'),
        ('critical', 'Critical'),
        ('handled', 'Handled')
    ], 'Risk Level', compute='_compute_risk_level', store=True, tracking=True)

    @api.depends('last_score', 'last_alert_id', 'last_alert_id.state', 'last_alert_id.severity')
    def _compute_risk_level(self):
        for rec in self:
            score = rec.last_score or 0.0
            
            # 1. If the current physiological state is stable (low score), it's NORMAL
            if score < 35:
                rec.risk_level = 'low'
                continue

            # 2. If there's an active NEW alert, prioritize its clinical severity
            if rec.last_alert_id and rec.last_alert_id.state == 'new':
                rec.risk_level = rec.last_alert_id.severity
                continue

            # 3. If there's an alert that is being investigated or resolved, and the score hasn't dropped < 35 yet
            if rec.last_alert_id and rec.last_alert_id.state in ['investigating', 'resolved']:
                rec.risk_level = 'handled'
                continue

            # 4. Use AI score thresholds for baseline risks
            if score >= 80:
                rec.risk_level = 'critical'
            elif score >= 60:
                rec.risk_level = 'high'
            elif score >= 35:
                rec.risk_level = 'medium'
            else:
                rec.risk_level = 'low'
    
    dashboard_risk_score = fields.Float('Dashboard Risk %', compute='_compute_dashboard_risk_score')

    @api.depends('risk_level', 'last_score')
    def _compute_dashboard_risk_score(self):
        for rec in self:
            if rec.risk_level == 'handled':
                rec.dashboard_risk_score = 0.0
            else:
                rec.dashboard_risk_score = rec.last_score

    last_score = fields.Float('Last AI Score', readonly=True)
    last_alert_id = fields.Many2one('health.alert', 'Latest Alert', readonly=True)
    last_alert_state = fields.Selection(related='last_alert_id.state', string='Latest Alert Status', readonly=True)
    
    last_vital_time = fields.Datetime('Last Vitals Logged', compute='_compute_last_vital_time', store=True)

    @api.depends('vital_record_ids.recorded_at')
    def _compute_last_vital_time(self):
        for rec in self:
            vitals = rec.vital_record_ids.sorted('recorded_at', reverse=True)
            rec.last_vital_time = vitals[0].recorded_at if vitals else False
            
    vital_record_ids = fields.One2many('health.vital.record', 'patient_id', 'Vital Records')
    alert_ids = fields.One2many('health.alert', 'patient_id', 'Alerts')
    
    vitals_count = fields.Integer(compute='_compute_vitals_count', string='Vitals Count')
    alerts_count = fields.Integer(compute='_compute_alerts_count')
    critical_alerts_count = fields.Integer(compute='_compute_alerts_count')
    
    total_alerts_this_month = fields.Integer(compute='_compute_alert_trends')
    total_alerts_last_month = fields.Integer(compute='_compute_alert_trends')
    alert_trend_label = fields.Char(compute='_compute_alert_trends')

    def _compute_alerts_count(self):
        for rec in self:
            rec.alerts_count = self.env['health.alert'].search_count([('patient_id', '=', rec.id)])
            rec.critical_alerts_count = self.env['health.alert'].search_count([
                ('patient_id', '=', rec.id),
                ('severity', '=', 'critical')
            ])

    def _compute_alert_trends(self):
        for rec in self:
            today = fields.Date.today()
            # This Month
            start_this_month = today.replace(day=1)
            rec.total_alerts_this_month = self.env['health.alert'].search_count([
                ('patient_id', '=', rec.id),
                ('create_date', '>=', start_this_month)
            ])
            # Last Month
            # Handle january
            start_last_month = start_this_month.replace(month=start_this_month.month - 1) if start_this_month.month > 1 else start_this_month.replace(year=start_this_month.year - 1, month=12)
            
            rec.total_alerts_last_month = self.env['health.alert'].search_count([
                ('patient_id', '=', rec.id),
                ('create_date', '>=', start_last_month),
                ('create_date', '<', start_this_month)
            ])
            
            diff = rec.total_alerts_this_month - rec.total_alerts_last_month
            if diff > 0:
                rec.alert_trend_label = f"↑ {diff} from last month"
            elif diff < 0:
                rec.alert_trend_label = f"↓ {abs(diff)} from last month"
            else:
                rec.alert_trend_label = "Same as last month"

    @api.depends('vital_record_ids')
    def _compute_vitals_count(self):
        for rec in self:
            rec.vitals_count = len(rec.vital_record_ids)
