from odoo import models, fields, api
from odoo.exceptions import AccessError, ValidationError
from datetime import timedelta


def _normalize_identity_value(value):
    return (value or '').strip().casefold()


class HealthPatientTag(models.Model):
    _name = 'health.patient.tag'
    _description = 'Patient Tag'

    name = fields.Char('Tag Name', required=True)
    color = fields.Integer('Color Index')

class HealthPatient(models.Model):
    _name = 'health.patient'
    _description = 'Patient Registry'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    _sql_constraints = [
        ('mrn_unique', 'unique(mrn)', 'Medical record number must be unique.'),
    ]

    def _auto_init(self):
        res = super()._auto_init()
        self._create_performance_indexes()
        return res

    def init(self):
        self._create_performance_indexes()

    def _create_performance_indexes(self):
        self.env.cr.execute("CREATE INDEX IF NOT EXISTS health_patient_ward_status_idx ON health_patient (ward_id, admission_status)")
        self.env.cr.execute("CREATE INDEX IF NOT EXISTS health_patient_risk_status_idx ON health_patient (risk_level, admission_status)")
        self.env.cr.execute("CREATE INDEX IF NOT EXISTS health_patient_create_status_idx ON health_patient (create_date, admission_status)")
        self.env.cr.execute("CREATE INDEX IF NOT EXISTS health_patient_last_score_idx ON health_patient (last_score)")

    active = fields.Boolean(default=True)
    mrn = fields.Char(
        'MRN',
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: self.env['ir.sequence'].next_by_code('health.patient.mrn') or 'New',
        tracking=True,
        index=True,
        help="Unique medical record number used as the durable patient identifier.",
    )
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
    
    ward_id = fields.Many2one('health.ward', string='Ward / Service', tracking=True, index=True)
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
                rec.age = rec._age_from_dob(rec.date_of_birth)
            elif not rec.age:
                rec.age = 0

    @api.model
    def _age_from_dob(self, date_of_birth):
        dob = fields.Date.to_date(date_of_birth)
        today = fields.Date.today()
        return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))

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
            if rec.age is not False and rec.age is not None:
                if rec.age < 0 or rec.age > 110:
                    raise ValidationError(
                        f"Age {rec.age} is not valid. Please enter an age between 0 and 110."
                    )

    @api.constrains('date_of_birth')
    def _check_date_of_birth(self):
        for rec in self:
            if rec.date_of_birth and rec.date_of_birth > fields.Date.today():
                raise ValidationError("Date of birth cannot be in the future.")

    @api.onchange('date_of_birth')
    def _onchange_date_of_birth(self):
        """Immediately sync age in the UI when DOB changes."""
        if self.date_of_birth:
            today = fields.Date.today()
            dob = self.date_of_birth
            self.age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
    
    doctor_id = fields.Many2one('res.users', 'Assigned Doctor', tracking=True, index=True)
    
    status = fields.Selection([
        ('draft', 'Draft'),
        ('active', 'Active')
    ], 'Status', default='draft', tracking=True)
    
    admission_status = fields.Selection([
        ('triage', 'In Triage (ER)'),
        ('admitted', 'Admitted to Ward'),
        ('discharged', 'Discharged')
    ], string='Admission Status', default='triage', tracking=True, index=True)
    
    ai_recommended_ward_id = fields.Many2one('health.ward', string='AI Recommended Ward', tracking=True, index=True)
    ai_recommendation_msg = fields.Char('AI Recommendation Message', tracking=True)
    
    vitals_frequency_hours = fields.Float('Vitals Frequency (Hours)', default=4.0, tracking=True, 
                                          help="How often vitals should be logged for this patient.")
    discharged_at = fields.Datetime('Discharged At', readonly=True, tracking=True)
    reactivated_at = fields.Datetime('Reactivated At', readonly=True, tracking=True)
    possible_duplicate_count = fields.Integer('Possible Duplicates', compute='_compute_possible_duplicate_count')
    
    is_doctor = fields.Boolean(compute='_compute_is_doctor')

    def _compute_is_doctor(self):
        for rec in self:
            rec.is_doctor = self.env.user.has_group('health_monitoring.group_health_doctor')

    @api.model_create_multi
    def create(self, vals_list):
        seen_identity_keys = set()
        for vals in vals_list:
            if not vals.get('mrn') or vals.get('mrn') == 'New':
                vals['mrn'] = self.env['ir.sequence'].next_by_code('health.patient.mrn') or 'New'
            self._normalize_patient_vals(vals)
            if vals.get('date_of_birth'):
                vals['age'] = self._age_from_dob(vals['date_of_birth'])
            identity_key = (
                _normalize_identity_value(vals.get('name')),
                vals.get('date_of_birth'),
                vals.get('gender'),
            )
            if all(identity_key):
                if identity_key in seen_identity_keys:
                    raise ValidationError("Duplicate patients in the same request are not allowed.")
                seen_identity_keys.add(identity_key)
            self._raise_on_duplicate_identity(vals)
        return super().create(vals_list)

    def write(self, vals):
        vals = dict(vals)
        self._normalize_patient_vals(vals)
        if vals.get('date_of_birth'):
            vals['age'] = self._age_from_dob(vals['date_of_birth'])
        elif 'age' in vals and any(rec.date_of_birth for rec in self):
            raise ValidationError("Age is calculated from date of birth. Clear DOB before editing age manually.")
        if 'date_of_birth' in vals or 'gender' in vals or 'name' in vals or 'mrn' in vals:
            for rec in self:
                candidate = {
                    'name': vals.get('name', rec.name),
                    'date_of_birth': vals.get('date_of_birth', rec.date_of_birth),
                    'gender': vals.get('gender', rec.gender),
                    'mrn': vals.get('mrn', rec.mrn),
                }
                rec._raise_on_duplicate_identity(candidate, exclude_id=rec.id)
        return super().write(vals)

    @api.model
    def _normalize_patient_vals(self, vals):
        if vals.get('name'):
            vals['name'] = vals['name'].strip()
        if vals.get('mrn'):
            vals['mrn'] = vals['mrn'].strip().upper()

    @api.model
    def _raise_on_duplicate_identity(self, vals, exclude_id=False):
        mrn = vals.get('mrn')
        if mrn:
            domain = [('mrn', '=', mrn)]
            if exclude_id:
                domain.append(('id', '!=', exclude_id))
            if self.search(domain, limit=1):
                raise ValidationError("A patient with this MRN already exists.")

        name = vals.get('name')
        dob = vals.get('date_of_birth')
        gender = vals.get('gender')
        if name and dob and gender:
            domain = [
                ('name', '=ilike', name.strip()),
                ('date_of_birth', '=', dob),
                ('gender', '=', gender),
            ]
            if exclude_id:
                domain.append(('id', '!=', exclude_id))
            if self.search(domain, limit=1):
                raise ValidationError(
                    "A possible duplicate patient already exists with the same name, date of birth, and gender. "
                    "Open the existing record or review possible duplicates before creating another one."
                )

    def _duplicate_domain(self):
        self.ensure_one()
        domain = [('id', '!=', self.id)]
        if self.name and self.date_of_birth and self.gender:
            return domain + [
                ('name', '=ilike', self.name.strip()),
                ('date_of_birth', '=', self.date_of_birth),
                ('gender', '=', self.gender),
            ]
        if self.mrn:
            return domain + [('mrn', '=', self.mrn)]
        return [('id', '=', 0)]

    def _compute_possible_duplicate_count(self):
        for rec in self:
            rec.possible_duplicate_count = self.search_count(rec._duplicate_domain())

    def action_review_possible_duplicates(self):
        self.ensure_one()
        return {
            'name': 'Possible Duplicate Patients',
            'type': 'ir.actions.act_window',
            'res_model': 'health.patient',
            'view_mode': 'tree,form',
            'domain': self._duplicate_domain(),
            'context': {'create': False},
        }

    def _ensure_can_admit(self):
        if not (
            self.env.user.has_group('health_monitoring.group_health_nurse')
            or self.env.user.has_group('health_monitoring.group_health_doctor')
            or self.env.user.has_group('health_monitoring.group_health_admin')
        ):
            raise AccessError("Only clinical staff can admit patients.")

    def _ensure_can_discharge(self):
        if not (
            self.env.user.has_group('health_monitoring.group_health_doctor')
            or self.env.user.has_group('health_monitoring.group_health_admin')
        ):
            raise AccessError("Only doctors and administrators can discharge patients.")

    def action_validate(self):
        for rec in self:
            if not self.env.user.has_group('health_monitoring.group_health_doctor'):
                raise AccessError("Only doctors can validate patient records.")
            rec.status = 'active'
        return True
            
    def action_admit(self):
        """Open admit wizard so nurses can select a ward and confirm admission."""
        self.ensure_one()
        self._ensure_can_admit()
        if self.admission_status != 'triage':
            raise ValidationError("Only triage patients can be admitted.")
        return {
            'name': 'Admit Patient',
            'type': 'ir.actions.act_window',
            'res_model': 'health.patient.admit.wizard',
            'view_mode': 'form',
            'views': [[False, 'form']],
            'target': 'new',
            'context': {
                'default_patient_id': self.id,
                'default_ward_id': (
                    self.ai_recommended_ward_id.id
                    if self.ai_recommended_ward_id
                    else self.ward_id.id if self.ward_id
                    else False
                ),
            },
        }


    def action_admit_ai(self):
        self._ensure_can_admit()
        for rec in self:
            if rec.admission_status == 'admitted':
                raise ValidationError(f"{rec.name} is already admitted.")
            if rec.admission_status == 'discharged':
                raise ValidationError(f"{rec.name} has been discharged. Please reactivate first.")
            if not rec.ai_recommended_ward_id:
                raise ValidationError("No AI Recommended Ward to admit to.")
            rec.write({
                'ward_id': rec.ai_recommended_ward_id.id,
                'admission_status': 'admitted',
            })
            rec.sudo().message_post(body=f"Patient officially admitted to {rec.ai_recommended_ward_id.name} (AI Recommendation).")
        return True
            
    def action_discharge(self):
        self._ensure_can_discharge()
        for rec in self:
            if rec.admission_status != 'admitted':
                raise ValidationError("Only admitted patients can be discharged.")
            ward_name = rec.ward_id.name if rec.ward_id else 'the hospital'
            rec.write({
                'admission_status': 'discharged',
                'ward_id': False,
                'discharged_at': fields.Datetime.now(),
            })
            
            # Auto-resolve active alerts for this patient
            active_alerts = self.env['health.alert'].sudo().search([
                ('patient_id', '=', rec.id),
                ('state', 'not in', ['resolved']),
            ])
            if active_alerts:
                active_alerts.sudo().write({
                    'status': 'handled',
                    'state': 'resolved',
                    'handled_at': fields.Datetime.now(),
                    'resolution_notes': 'Patient discharged from hospital. Alert auto-resolved.'
                })
            
            # Post message to chatter
            rec.sudo().message_post(
                body=f"Patient has been discharged from {ward_name}. {len(active_alerts)} active alert(s) auto-resolved."
            )
        return True

    def action_reactivate(self):
        self._ensure_can_admit()
        for rec in self:
            if rec.admission_status != 'discharged':
                raise ValidationError("Only discharged patients can be reactivated.")
            rec.write({
                'admission_status': 'triage',
                'ward_id': False,
                'reactivated_at': fields.Datetime.now(),
            })
            rec.sudo().message_post(body="Patient reactivated and returned to triage.")
        return True

    @api.constrains('gender', 'lifestyle_profile')
    def _check_gender_profile_consistency(self):
        for rec in self:
            if rec.gender != 'female' and rec.lifestyle_profile == 'pregnant':
                raise ValidationError("Pregnancy profile can only be selected for female patients.")

    @api.constrains('vitals_frequency_hours')
    def _check_vitals_frequency_hours(self):
        for rec in self:
            if rec.vitals_frequency_hours <= 0 or rec.vitals_frequency_hours > 24:
                raise ValidationError("Vitals frequency must be greater than 0 and no more than 24 hours.")

    @api.constrains('admission_status', 'ward_id')
    def _check_admission_consistency(self):
        for rec in self:
            if rec.admission_status == 'admitted' and not rec.ward_id:
                raise ValidationError("Admitted patients must be assigned to a ward.")
            if rec.admission_status == 'discharged' and rec.ward_id:
                raise ValidationError("Discharged patients cannot remain assigned to a ward.")
    
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
    ], 'Risk Level', compute='_compute_risk_level', store=True, tracking=True, index=True)

    @api.depends(
        'last_score',
        'last_alert_id',
        'last_alert_id.state',
        'last_alert_id.status',
        'last_alert_id.severity',
        'alert_ids.state',
        'alert_ids.status',
        'alert_ids.severity',
    )
    def _compute_risk_level(self):
        severity_rank = {
            'low': 1,
            'medium': 2,
            'high': 3,
            'critical': 4,
        }
        active_alerts_by_patient = {patient_id: self.env['health.alert'] for patient_id in self.ids}
        if self.ids:
            active_alerts = self.env['health.alert'].search([
                ('patient_id', 'in', self.ids),
                ('state', '!=', 'resolved'),
                ('status', '!=', 'handled'),
            ])
            for alert in active_alerts:
                active_alerts_by_patient.setdefault(alert.patient_id.id, self.env['health.alert'])
                active_alerts_by_patient[alert.patient_id.id] |= alert
        for rec in self:
            score = rec.last_score or 0.0

            active_alerts = active_alerts_by_patient.get(rec.id, self.env['health.alert'])
            if active_alerts:
                highest_alert = active_alerts.sorted(
                    key=lambda alert: (severity_rank.get(alert.severity, 0), alert.create_date or fields.Datetime.now()),
                    reverse=True,
                )[0]
                rec.risk_level = highest_alert.severity
                continue

            if rec.last_alert_id and (
                rec.last_alert_id.state == 'resolved'
                or rec.last_alert_id.status == 'handled'
            ) and score >= 35:
                rec.risk_level = 'handled'
                continue

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

    last_score = fields.Float('Last AI Score', readonly=True, index=True)
    last_alert_id = fields.Many2one('health.alert', 'Latest Alert', readonly=True, index=True)
    last_alert_state = fields.Selection(related='last_alert_id.state', string='Latest Alert Status', readonly=True)
    
    last_vital_time = fields.Datetime('Last Vitals Logged', compute='_compute_last_vital_time', store=True, index=True)
    vitals_due_status = fields.Selection([
        ('up_to_date', 'Up to Date'),
        ('due_soon', 'Due Soon'),
        ('overdue', 'Overdue'),
        ('not_applicable', 'Not Applicable'),
    ], string='Vitals Due Status', compute='_compute_vitals_due_status')
    vitals_due_at = fields.Datetime('Vitals Due At', compute='_compute_vitals_due_status')
    vitals_due_in_minutes = fields.Float('Vitals Due In Minutes', compute='_compute_vitals_due_status')

    @api.depends('vital_record_ids.recorded_at')
    def _compute_last_vital_time(self):
        latest_by_patient = {}
        if self.ids:
            rows = self.env['health.vital.record'].read_group(
                [('patient_id', 'in', self.ids)],
                ['patient_id', 'recorded_at:max'],
                ['patient_id'],
                lazy=False,
            )
            latest_by_patient = {
                row['patient_id'][0]: row.get('recorded_at')
                for row in rows
                if row.get('patient_id')
            }
        for rec in self:
            rec.last_vital_time = latest_by_patient.get(rec.id, False)

    @api.depends('last_vital_time', 'vitals_frequency_hours', 'admission_status')
    def _compute_vitals_due_status(self):
        now = fields.Datetime.now()
        for rec in self:
            if rec.admission_status not in ['triage', 'admitted']:
                rec.vitals_due_status = 'not_applicable'
                rec.vitals_due_at = False
                rec.vitals_due_in_minutes = 0.0
                continue

            frequency_hours = rec.vitals_frequency_hours or 4.0
            if not rec.last_vital_time:
                rec.vitals_due_status = 'overdue'
                rec.vitals_due_at = False
                rec.vitals_due_in_minutes = -1.0
                continue

            due_at = rec.last_vital_time + timedelta(hours=frequency_hours)
            minutes_until_due = (due_at - now).total_seconds() / 60.0
            due_soon_minutes = min(60.0, frequency_hours * 60.0 * 0.25)

            rec.vitals_due_at = due_at
            rec.vitals_due_in_minutes = minutes_until_due
            if minutes_until_due <= 0:
                rec.vitals_due_status = 'overdue'
            elif minutes_until_due <= due_soon_minutes:
                rec.vitals_due_status = 'due_soon'
            else:
                rec.vitals_due_status = 'up_to_date'
            
    vital_record_ids = fields.One2many('health.vital.record', 'patient_id', 'Vital Records')
    alert_ids = fields.One2many('health.alert', 'patient_id', 'Alerts')
    
    vitals_count = fields.Integer(compute='_compute_vitals_count', string='Vitals Count')
    alerts_count = fields.Integer(compute='_compute_alerts_count')
    critical_alerts_count = fields.Integer(compute='_compute_alerts_count')
    
    total_alerts_this_month = fields.Integer(compute='_compute_alert_trends')
    total_alerts_last_month = fields.Integer(compute='_compute_alert_trends')
    alert_trend_label = fields.Char(compute='_compute_alert_trends')

    def _compute_alerts_count(self):
        total_by_patient = {}
        critical_by_patient = {}
        if self.ids:
            total_rows = self.env['health.alert'].read_group(
                [('patient_id', 'in', self.ids)],
                ['patient_id'],
                ['patient_id'],
                lazy=False,
            )
            critical_rows = self.env['health.alert'].read_group(
                [('patient_id', 'in', self.ids), ('severity', '=', 'critical')],
                ['patient_id'],
                ['patient_id'],
                lazy=False,
            )
            total_by_patient = {
                row['patient_id'][0]: row.get('__count', 0)
                for row in total_rows
                if row.get('patient_id')
            }
            critical_by_patient = {
                row['patient_id'][0]: row.get('__count', 0)
                for row in critical_rows
                if row.get('patient_id')
            }
        for rec in self:
            rec.alerts_count = total_by_patient.get(rec.id, 0)
            rec.critical_alerts_count = critical_by_patient.get(rec.id, 0)

    def _compute_alert_trends(self):
        today = fields.Date.today()
        start_this_month = today.replace(day=1)
        start_last_month = (
            start_this_month.replace(month=start_this_month.month - 1)
            if start_this_month.month > 1
            else start_this_month.replace(year=start_this_month.year - 1, month=12)
        )
        current_by_patient = {}
        previous_by_patient = {}
        if self.ids:
            current_rows = self.env['health.alert'].read_group(
                [('patient_id', 'in', self.ids), ('create_date', '>=', start_this_month)],
                ['patient_id'],
                ['patient_id'],
                lazy=False,
            )
            previous_rows = self.env['health.alert'].read_group(
                [
                    ('patient_id', 'in', self.ids),
                    ('create_date', '>=', start_last_month),
                    ('create_date', '<', start_this_month),
                ],
                ['patient_id'],
                ['patient_id'],
                lazy=False,
            )
            current_by_patient = {
                row['patient_id'][0]: row.get('__count', 0)
                for row in current_rows
                if row.get('patient_id')
            }
            previous_by_patient = {
                row['patient_id'][0]: row.get('__count', 0)
                for row in previous_rows
                if row.get('patient_id')
            }
        for rec in self:
            rec.total_alerts_this_month = current_by_patient.get(rec.id, 0)
            rec.total_alerts_last_month = previous_by_patient.get(rec.id, 0)
            
            diff = rec.total_alerts_this_month - rec.total_alerts_last_month
            if diff > 0:
                rec.alert_trend_label = f"Up {diff} from last month"
            elif diff < 0:
                rec.alert_trend_label = f"Down {abs(diff)} from last month"
            else:
                rec.alert_trend_label = "Same as last month"

    @api.depends('vital_record_ids')
    def _compute_vitals_count(self):
        counts = {}
        if self.ids:
            rows = self.env['health.vital.record'].read_group(
                [('patient_id', 'in', self.ids)],
                ['patient_id'],
                ['patient_id'],
                lazy=False,
            )
            counts = {
                row['patient_id'][0]: row.get('__count', 0)
                for row in rows
                if row.get('patient_id')
            }
        for rec in self:
            rec.vitals_count = counts.get(rec.id, 0)
