from datetime import datetime, time, timedelta

import pytz

from odoo import api, fields, models
from odoo.exceptions import AccessError


ACTIVE_PATIENT_DOMAIN = [('admission_status', 'in', ['triage', 'admitted'])]
OPEN_ALERT_DOMAIN = [('state', '!=', 'resolved'), ('status', '!=', 'handled')]
NURSE_RECENT_VITALS_PER_PATIENT = 5
DOCTOR_QUEUE_FETCH_LIMIT = 200


class HealthDashboard(models.TransientModel):
    _name = 'health.dashboard'
    _description = 'Dashboard KPI'

    name = fields.Char(default='Dashboard')
    total_patients = fields.Integer(compute='_compute_kpis')
    active_alerts = fields.Integer(compute='_compute_kpi_values')
    critical_alerts = fields.Integer(compute='_compute_kpi_values')
    avg_score = fields.Float(compute='_compute_kpi_values', string="Avg AI Risk")

    followed_patient_ids = fields.Many2many('health.patient', string="My Watchlist", compute='_compute_recent_activity')
    recent_alert_ids = fields.Many2many('health.alert', string="Recent Alerts", compute='_compute_recent_activity')
    recent_vital_ids = fields.Many2many('health.vital.record', compute='_compute_recent_activity')

    # -------------------------------------------------------------------------
    # Shared helpers
    # -------------------------------------------------------------------------
    def _active_patient_domain(self):
        return list(ACTIVE_PATIENT_DOMAIN)

    def _open_alert_domain(self):
        return list(OPEN_ALERT_DOMAIN)

    def _datetime_to_string(self, value):
        return fields.Datetime.to_string(value) if value else False

    def _rpc_safe(self, value):
        if value is None:
            return False
        if isinstance(value, dict):
            return {key: self._rpc_safe(val) for key, val in value.items()}
        if isinstance(value, (list, tuple)):
            return [self._rpc_safe(val) for val in value]
        return value

    def _time_ago(self, value):
        if not value:
            return ''
        dt_value = fields.Datetime.to_datetime(value)
        diff_mins = int((fields.Datetime.now() - dt_value).total_seconds() / 60.0)
        if diff_mins < 1:
            return 'Just now'
        if diff_mins < 60:
            return f'{diff_mins} min ago'
        diff_hours = diff_mins // 60
        if diff_hours < 24:
            return f'{diff_hours}h ago'
        return f'{diff_hours // 24}d ago'

    def _user_tz(self):
        return pytz.timezone(self.env.user.tz or 'UTC')

    def _local_date_to_utc_bounds(self, date_value):
        user_tz = self._user_tz()
        start_local = user_tz.localize(datetime.combine(date_value, time.min))
        end_local = start_local + timedelta(days=1)
        start_utc = start_local.astimezone(pytz.utc).replace(tzinfo=None)
        end_utc = end_local.astimezone(pytz.utc).replace(tzinfo=None)
        return fields.Datetime.to_string(start_utc), fields.Datetime.to_string(end_utc)

    def _last_calendar_days_bounds(self, days):
        today = fields.Date.context_today(self)
        start_date = today - timedelta(days=days - 1)
        start_utc, _ = self._local_date_to_utc_bounds(start_date)
        _, end_utc = self._local_date_to_utc_bounds(today)
        return start_date, today, start_utc, end_utc

    def _local_day_key(self, value):
        dt_value = fields.Datetime.to_datetime(value)
        if not dt_value:
            return False
        return fields.Datetime.context_timestamp(self, dt_value).date().isoformat()

    def _day_labels(self, start_date, days):
        return [(start_date + timedelta(days=offset)).isoformat() for offset in range(days)]

    def _group_count_map(self, model, domain, groupby):
        rows = self.env[model].read_group(domain, [groupby], [groupby], lazy=False)
        counts = {}
        for row in rows:
            key = row.get(groupby)
            if isinstance(key, (list, tuple)):
                key = key[0]
            if key:
                counts[key] = row.get('__count', 0)
        return counts

    def _read_group_count(self, record_model, domain):
        rows = record_model.read_group(domain, [], [], lazy=False)
        return rows[0].get('__count', 0) if rows else 0

    def _day_key_from_read_group_range(self, row, group_key):
        range_start = (row.get('__range') or {}).get(group_key, {}).get('from')
        return self._local_day_key(range_start) if range_start else False

    def _latest_vitals_by_patient(self, patient_ids, per_patient=NURSE_RECENT_VITALS_PER_PATIENT):
        if not patient_ids:
            return {}
        self.env['health.vital.record'].check_access_rights('read')
        self.env.cr.execute(
            """
            SELECT id, patient_id
              FROM (
                    SELECT id,
                           patient_id,
                           row_number() OVER (
                               PARTITION BY patient_id
                               ORDER BY recorded_at DESC, id DESC
                           ) AS rn
                      FROM health_vital_record
                     WHERE patient_id = ANY(%s)
                   ) latest
             WHERE rn <= %s
             ORDER BY patient_id, rn
            """,
            (patient_ids, per_patient),
        )
        rows = self.env.cr.fetchall()
        vital_ids = [row[0] for row in rows]
        vitals = self.env['health.vital.record'].browse(vital_ids).exists()
        if vitals:
            vitals.check_access_rule('read')
        vital_by_id = {vital.id: vital for vital in vitals}
        grouped = {patient_id: [] for patient_id in patient_ids}
        for vital_id, patient_id in rows:
            vital = vital_by_id.get(vital_id)
            if vital:
                grouped.setdefault(patient_id, []).append(vital)
        return grouped

    def _action_for_records(self, name, model, domain, view_mode='tree,form'):
        views = []
        for mode in view_mode.split(','):
            mode = mode.strip()
            views.append([False, 'list' if mode == 'tree' else mode])
        return {
            'name': name,
            'type': 'ir.actions.act_window',
            'res_model': model,
            'view_mode': view_mode,
            'views': views,
            'domain': domain,
            'target': 'current',
        }

    def _ensure_admin_dashboard_access(self):
        if not self.env.user.has_group('health_monitoring.group_health_admin'):
            raise AccessError("Only SmartLab administrators can view this dashboard.")

    def _ensure_doctor_dashboard_access(self):
        if not (
            self.env.user.has_group('health_monitoring.group_health_doctor')
            or self.env.user.has_group('health_monitoring.group_health_admin')
        ):
            raise AccessError("Only doctors and administrators can view this dashboard.")

    # -------------------------------------------------------------------------
    # Legacy form dashboard
    # -------------------------------------------------------------------------
    def _compute_recent_activity(self):
        for rec in self:
            rec.followed_patient_ids = self.env['health.patient'].search([
                ('message_partner_ids', 'in', [self.env.user.partner_id.id])
            ])

            if self.env['health.alert'].check_access_rights('read', raise_exception=False):
                rec.recent_alert_ids = self.env['health.alert'].search(
                    self._open_alert_domain(),
                    order='create_date desc',
                    limit=10,
                )
            else:
                rec.recent_alert_ids = False

            rec.recent_vital_ids = self.env['health.vital.record'].search([], order='recorded_at desc', limit=10)

    def _compute_kpis(self):
        for rec in self:
            rec.total_patients = self._read_group_count(self.env['health.patient'], [])

    def _compute_kpi_values(self):
        for rec in self:
            if self.env['health.alert'].check_access_rights('read', raise_exception=False):
                rec.active_alerts = self._read_group_count(self.env['health.alert'], self._open_alert_domain())
                rec.critical_alerts = self._read_group_count(
                    self.env['health.alert'],
                    self._open_alert_domain() + [('severity', '=', 'critical')]
                )
            else:
                rec.active_alerts = 0
                rec.critical_alerts = 0

            score_rows = self.env['health.patient'].read_group(
                [('last_score', '>', 0)],
                ['last_score:avg'],
                [],
                lazy=False,
            )
            rec.avg_score = score_rows[0].get('last_score', 0.0) if score_rows else 0.0

    def action_open_patients(self):
        return {
            'name': 'Registered Patients',
            'type': 'ir.actions.act_window',
            'res_model': 'health.patient',
            'view_mode': 'kanban,tree,form',
            'domain': self._active_patient_domain(),
            'context': {'search_default_active_patients': 1},
            'target': 'current',
        }

    def action_open_alerts(self):
        return self._action_for_records('Active Alerts', 'health.alert', self._open_alert_domain())

    def action_open_critical(self):
        return self._action_for_records(
            'Critical Alerts',
            'health.alert',
            self._open_alert_domain() + [('severity', '=', 'critical')],
        )

    # -------------------------------------------------------------------------
    # Nurse dashboard
    # -------------------------------------------------------------------------
    def _nurse_status_patient_ids(self, patients=False):
        patients = patients or self.env['health.patient'].search(self._active_patient_domain(), order='name asc')
        ids_by_status = {'total': patients.ids, 'critical': [], 'overdue': [], 'due_soon': [], 'up_to_date': []}
        for patient in patients:
            status = patient.vitals_due_status or 'overdue'
            if status not in ids_by_status:
                status = 'overdue'
            if patient.risk_level == 'critical':
                ids_by_status['critical'].append(patient.id)
            ids_by_status[status].append(patient.id)
        return ids_by_status

    def _nurse_patient_rows(self):
        Patient = self.env['health.patient']
        Vital = self.env['health.vital.record']
        Alert = self.env['health.alert']

        patients = Patient.search(self._active_patient_domain(), order='name asc')
        patient_ids = patients.ids
        vitals_by_patient = self._latest_vitals_by_patient(patient_ids)

        ids_by_status = self._nurse_status_patient_ids(patients)
        rows = []
        now = fields.Datetime.now()

        for patient in patients:
            patient_vitals = vitals_by_patient.get(patient.id, [])
            latest_vital = patient_vitals[0] if patient_vitals else False
            status = patient.vitals_due_status or 'overdue'
            if status not in ids_by_status:
                status = 'overdue'

            hours_since = 999.0
            if latest_vital and latest_vital.recorded_at:
                hours_since = (now - latest_vital.recorded_at).total_seconds() / 3600.0

            composite = {
                'heart_rate': None,
                'spo2': None,
                'bp_systolic': None,
                'bp_diastolic': None,
                'temperature': None,
            }
            for vital in patient_vitals:
                for field_name in composite:
                    if composite[field_name] is None and getattr(vital, field_name):
                        composite[field_name] = getattr(vital, field_name)
                if all(value is not None for value in composite.values()):
                    break

            minutes_until_due = patient.vitals_due_in_minutes
            if status == 'overdue':
                if minutes_until_due is not False and minutes_until_due < 0:
                    overdue_minutes = abs(minutes_until_due)
                    label = f'{round(overdue_minutes / 60)}h overdue' if overdue_minutes >= 60 else f'{round(overdue_minutes)}min overdue'
                    due_label = f'Was due {label.replace(" overdue", "")} ago'
                else:
                    label = 'Overdue'
                    due_label = 'Vitals overdue'
            elif status == 'due_soon':
                label = f'Due in {max(0, round(minutes_until_due or 0))}min'
                due_label = label
            else:
                label = 'Next check'
                due_label = 'Next check'

            heart_rate = composite['heart_rate']
            spo2 = composite['spo2']
            bp_systolic = composite['bp_systolic']
            bp_diastolic = composite['bp_diastolic']
            temperature = composite['temperature']
            recent_vitals = []
            for vital in reversed(patient_vitals[:5]):
                recent_vitals.append({
                    'id': vital.id,
                    'recorded_at': self._datetime_to_string(vital.recorded_at),
                    'heart_rate': vital.heart_rate or 0,
                    'spo2': vital.spo2 or 0,
                    'bp_systolic': vital.bp_systolic or 0,
                    'bp_diastolic': vital.bp_diastolic or 0,
                    'temperature': vital.temperature or 0,
                })

            rows.append({
                'id': patient.id,
                'name': patient.name,
                'admission_status': patient.admission_status,
                'risk_level': patient.risk_level or 'low',
                'age': patient.age,
                'gender': patient.gender,
                'vitals_frequency_hours': patient.vitals_frequency_hours,
                'last_vital_time': self._datetime_to_string(patient.last_vital_time),
                'vitals_due_status': status,
                'vitals_due_at': self._datetime_to_string(patient.vitals_due_at),
                'vitals_due_in_minutes': minutes_until_due,
                'vitalsStatus': status,
                'timeSinceVitals': (
                    f'{round(hours_since * 60)}min since vitals'
                    if hours_since < 1
                    else f'{hours_since:.1f}h since vitals'
                    if hours_since < 999
                    else 'No vitals'
                ),
                'statusLabel': label,
                'dueLabel': due_label,
                'hoursSort': hours_since,
                'latestHR': round(heart_rate) if heart_rate else ('--' if patient_vitals else None),
                'latestSpO2': round(spo2) if spo2 else ('--' if patient_vitals else None),
                'latestBP': f'{round(bp_systolic)}/{round(bp_diastolic)}' if bp_systolic and bp_diastolic else ('--/--' if patient_vitals else None),
                'latestTemp': f'{temperature:.1f}' if temperature else ('--' if patient_vitals else None),
                'rawBpSys': bp_systolic,
                'rawBpDia': bp_diastolic,
                'rawTemp': temperature,
                'hrAbnormal': bool(heart_rate and (heart_rate > 100 or heart_rate < 60)),
                'hrWarn': bool(heart_rate and not (heart_rate > 100 or heart_rate < 60) and (heart_rate > 90 or heart_rate < 65)),
                'spo2Abnormal': bool(spo2 and spo2 < 90),
                'spo2Warn': bool(spo2 and spo2 >= 90 and spo2 < 95),
                'bpAbnormal': bool(bp_systolic and (bp_systolic > 140 or bp_systolic < 90)),
                'bpWarn': bool(bp_systolic and not (bp_systolic > 140 or bp_systolic < 90) and bp_systolic > 130),
                'bpLow': bool(bp_systolic and bp_systolic < 90),
                'bpEqual': bool(bp_systolic and bp_diastolic and abs(bp_systolic - bp_diastolic) < 5),
                'tempAbnormal': bool(temperature and (temperature > 38.5 or temperature < 35.5)),
                'recentVitals': recent_vitals,
            })

        severity_order = {'critical': 4, 'high': 3, 'medium': 2, 'low': 1, 'handled': 0}
        rows.sort(key=lambda row: (
            -1 if row['risk_level'] == 'critical' else 0,
            -1 if row['vitalsStatus'] == 'overdue' else 0,
            -severity_order.get(row['risk_level'], 0),
            -row['hoursSort'],
        ))

        alerts = Alert
        if patient_ids and Alert.check_access_rights('read', raise_exception=False):
            alerts = Alert.search([('patient_id', 'in', patient_ids)], order='create_date desc', limit=20)

        feed = []
        alerts_by_patient = {}
        for alert in alerts:
            alerts_by_patient.setdefault(alert.patient_id.id, []).append(alert)
            feed.append({
                'id': f'a{alert.id}',
                'type': 'alert',
                'text': f'{(alert.severity or "alert").upper()}: {alert.headline or "Anomaly detected"}',
                'timeAgo': self._time_ago(alert.create_date),
                'timeSort': alert.create_date.timestamp() if alert.create_date else 0,
            })

        recent_vitals = []
        if patient_ids:
            recent_vitals = Vital.search([('patient_id', 'in', patient_ids)], order='recorded_at desc', limit=8)
        patient_name_by_id = {patient.id: patient.name for patient in patients}
        for vital in recent_vitals:
            patient_alerts = alerts_by_patient.get(vital.patient_id.id, [])
            near_alert = False
            for alert in patient_alerts:
                if (
                    alert.create_date
                    and vital.recorded_at
                    and abs((alert.create_date - vital.recorded_at).total_seconds()) < 5 * 60
                ):
                    near_alert = alert
                    break
            status_text = (
                f'{near_alert.severity.upper()} alert triggered'
                if near_alert
                else 'Values within normal range'
            )
            feed.append({
                'id': f'v{vital.id}',
                'type': 'alert' if near_alert else 'vitals',
                'text': f'Vitals logged - {patient_name_by_id.get(vital.patient_id.id, "Patient")}. {status_text}',
                'timeAgo': self._time_ago(vital.recorded_at),
                'timeSort': vital.recorded_at.timestamp() if vital.recorded_at else 0,
            })

        feed = sorted(feed, key=lambda item: item['timeSort'], reverse=True)[:8]
        schedule = [
            row for row in rows
            if row['vitalsStatus'] in ['overdue', 'due_soon']
        ][:8]
        handoff = [
            row for row in rows
            if row['risk_level'] in ['critical', 'high']
        ][:15]

        return rows, ids_by_status, schedule, handoff, feed

    @api.model
    def get_nurse_dashboard_data(self):
        rows, ids_by_status, schedule, handoff, feed = self._nurse_patient_rows()
        return self._rpc_safe({
            'wardName': 'All Wards',
            'patients': rows,
            'stats': {
                'total': len(ids_by_status['total']),
                'critical': len(ids_by_status['critical']),
                'overdue': len(ids_by_status['overdue']),
                'dueSoon': len(ids_by_status['due_soon']),
                'upToDate': len(ids_by_status['up_to_date']),
            },
            'statusPatientIds': ids_by_status,
            'schedule': schedule,
            'handoffList': handoff,
            'activityFeed': feed,
        })

    @api.model
    def get_nurse_kpi_action(self, kpi):
        ids_by_status = self._nurse_status_patient_ids()
        names = {
            'total': 'Active Patients',
            'critical': 'Critical Patients',
            'overdue': 'Overdue Vitals',
            'due_soon': 'Vitals Due Soon',
            'up_to_date': 'Vitals Up to Date',
        }
        if kpi == 'total':
            domain = self._active_patient_domain()
        elif kpi in ids_by_status:
            domain = [('id', 'in', ids_by_status[kpi])]
        else:
            domain = [('id', '=', 0)]
        return self._action_for_records(names.get(kpi, 'Patients'), 'health.patient', domain)

    # -------------------------------------------------------------------------
    # Doctor dashboard
    # -------------------------------------------------------------------------
    def _doctor_ward_context(self):
        wards = self.env['health.ward'].search([('doctor_ids', 'in', [self.env.user.id])])
        return {
            'wardIds': wards.ids,
            'wardName': ', '.join(wards.mapped('name')) if wards else 'Unassigned',
        }

    def _serialize_alert_card(self, alert):
        return {
            'id': alert.id,
            'headline': alert.headline or 'Anomaly detected',
            'severity': alert.severity,
            'patient_id': [alert.patient_id.id, alert.patient_id.name],
            'create_date': self._datetime_to_string(alert.create_date),
            'timeAgo': self._time_ago(alert.create_date),
        }

    def _dedupe_alerts_by_patient(self, alerts):
        severity_order = {'critical': 4, 'high': 3, 'warning': 2, 'medium': 2, 'low': 1, 'info': 1}
        selected = {}
        for alert in alerts:
            patient_id = alert.patient_id.id
            if patient_id not in selected:
                selected[patient_id] = alert
                continue
            current = selected[patient_id]
            if severity_order.get(alert.severity, 0) > severity_order.get(current.severity, 0):
                selected[patient_id] = alert
        return [self._serialize_alert_card(alert) for alert in selected.values()]

    @api.model
    def get_doctor_dashboard_data(self):
        self._ensure_doctor_dashboard_access()
        ward_context = self._doctor_ward_context()
        ward_ids = ward_context['wardIds']

        unclaimed_domain = [('state', '=', 'new'), ('assigned_doctor_id', '=', False)]
        if ward_ids:
            unclaimed_domain.append(('patient_id.ward_id', 'in', ward_ids))
        else:
            unclaimed_domain.append(('patient_id.ward_id', '=', False))

        unclaimed = self.env['health.alert'].search(
            unclaimed_domain,
            order='create_date desc',
            limit=DOCTOR_QUEUE_FETCH_LIMIT,
        )
        active = self.env['health.alert'].search([
            ('state', '=', 'investigating'),
            ('assigned_doctor_id', '=', self.env.user.id),
        ], order='create_date desc', limit=DOCTOR_QUEUE_FETCH_LIMIT)
        unclaimed_cards = self._dedupe_alerts_by_patient(unclaimed)
        active_cards = self._dedupe_alerts_by_patient(active)
        return self._rpc_safe({
            'wardName': ward_context['wardName'],
            'wardIds': ward_ids,
            'unclaimedAlerts': unclaimed_cards,
            'myActiveAlerts': active_cards,
            'activeCaseCount': len(unclaimed_cards) + len(active_cards),
        })

    def _risk_color(self, value):
        if value > 60:
            return '#F87171'
        if value > 30:
            return '#FBBF24'
        return '#34D399'

    @api.model
    def get_doctor_patient_panel_data(self, patient_id):
        self._ensure_doctor_dashboard_access()
        patient = self.env['health.patient'].browse(patient_id).exists()
        if not patient:
            return {'selectedPatient': False, 'vitals': {}, 'risk': {}, 'activeAlert': False, 'trendVitals': []}

        patient_data = patient.read(['name', 'age', 'gender', 'admission_status', 'risk_level'])[0]
        initials = ''.join([part[:1] for part in (patient.name or '').split()])[:2].upper()
        patient_data['initials'] = initials
        if patient_data.get('risk_level') not in ['low', 'medium', 'high', 'critical', 'handled']:
            patient_data['risk_level'] = 'low'

        vitals = self.env['health.vital.record'].search(
            [('patient_id', '=', patient.id)],
            order='recorded_at desc',
            limit=20,
        )
        active_alert = self.env['health.alert'].search(
            [('patient_id', '=', patient.id)] + self._open_alert_domain(),
            order='create_date desc',
            limit=1,
        )
        alert_data = False
        if active_alert:
            alert_data = {
                'id': active_alert.id,
                'headline': active_alert.headline,
                'severity': active_alert.severity,
                'state': active_alert.state,
                'create_date': self._datetime_to_string(active_alert.create_date),
                'timeAgo': self._time_ago(active_alert.create_date),
            }

        vital_data = {}
        risk = {
            'cardiac': 0, 'cardiacColor': self._risk_color(0),
            'respiratory': 0, 'respiratoryColor': self._risk_color(0),
            'hypoxia': 0, 'hypoxiaColor': self._risk_color(0),
            'bloodPressure': 0, 'bloodPressureColor': self._risk_color(0),
            'thermoregulation': 0, 'thermoregulationColor': self._risk_color(0),
            'metabolic': 0, 'metabolicColor': self._risk_color(0),
        }
        if vitals:
            latest = vitals[0]
            hr = latest.heart_rate or 0
            bp_sys = latest.bp_systolic or 0
            bp_dia = latest.bp_diastolic or 0
            spo2 = latest.spo2 or 0
            temp = latest.temperature or 0
            rr = latest.respiratory_rate or 0
            glucose = latest.glucose or 0

            cardiac = min(100, (hr - 100) * 3) if hr > 100 else min(100, (60 - hr) * 3) if 0 < hr < 60 else 0
            respiratory = min(100, (rr - 20) * 2) if rr > 20 else min(100, (12 - rr) * 5) if 0 < rr < 12 else 0
            hypoxia = min(100, max(0, (95 - spo2) * 8)) if spo2 > 0 else 0
            blood_pressure = min(100, (bp_sys - 140) * 2) if bp_sys > 140 else min(100, (90 - bp_sys) * 3) if 0 < bp_sys < 90 else 0
            thermo = min(100, (temp - 38.0) * 50) if temp > 38.0 else min(100, (36.1 - temp) * 50) if 0 < temp < 36.1 else 0
            metabolic = min(100, (glucose - 200) * 0.5) if glucose > 200 else min(100, (70 - glucose) * 2) if 0 < glucose < 70 else 0

            vital_data = {
                'heart_rate': round(hr) if hr else 0,
                'bp_systolic': round(bp_sys) if bp_sys else 0,
                'bp_diastolic': round(bp_dia) if bp_dia else 0,
                'spo2': round(spo2) if spo2 else 0,
                'temperature': f'{temp:.1f}' if temp else 0,
                'respiratory_rate': round(rr) if rr else 0,
                'glucose': round(glucose) if glucose else 0,
                'ai_score': round(latest.ai_score) if latest.ai_score else False,
                'hr_abnormal': hr > 100 or (0 < hr < 60),
                'spo2_abnormal': 0 < spo2 < 94,
                'bp_abnormal': bp_sys > 140 or (0 < bp_sys < 90) or bp_dia > 90 or (0 < bp_dia < 60),
                'temp_abnormal': temp > 38.5 or (0 < temp < 35.5),
                'rr_abnormal': rr > 20 or (0 < rr < 12),
                'glucose_abnormal': glucose > 200 or (0 < glucose < 70),
            }
            risk = {
                'cardiac': cardiac, 'cardiacColor': self._risk_color(cardiac),
                'respiratory': respiratory, 'respiratoryColor': self._risk_color(respiratory),
                'hypoxia': hypoxia, 'hypoxiaColor': self._risk_color(hypoxia),
                'bloodPressure': blood_pressure, 'bloodPressureColor': self._risk_color(blood_pressure),
                'thermoregulation': thermo, 'thermoregulationColor': self._risk_color(thermo),
                'metabolic': metabolic, 'metabolicColor': self._risk_color(metabolic),
            }

        trend_vitals = [{
            'heart_rate': vital.heart_rate or False,
            'bp_systolic': vital.bp_systolic or False,
            'bp_diastolic': vital.bp_diastolic or False,
            'spo2': vital.spo2 or False,
            'temperature': vital.temperature or False,
            'recorded_at': self._datetime_to_string(vital.recorded_at),
        } for vital in reversed(vitals)]
        return self._rpc_safe({
            'selectedPatient': patient_data,
            'vitals': vital_data,
            'risk': risk,
            'activeAlert': alert_data,
            'trendVitals': trend_vitals,
            'showVitalsChart': len(trend_vitals) >= 3,
        })

    # -------------------------------------------------------------------------
    # Admin dashboard
    # -------------------------------------------------------------------------
    def _dashboard_range_days(self, date_range):
        return {'today': 1, 'week': 7, 'month': 30}.get(date_range, 7)

    def _alert_trend(self, days):
        start_date, _today, start_utc, end_utc = self._last_calendar_days_bounds(days)
        day_keys = self._day_labels(start_date, days)
        day_map = {key: {'total': 0, 'critical': 0} for key in day_keys}
        alert_rows = self.env['health.alert'].read_group(
            [('create_date', '>=', start_utc), ('create_date', '<', end_utc)],
            ['create_date', 'severity'],
            ['create_date:day', 'severity'],
            lazy=False,
        )
        for alert in alert_rows:
            key = self._day_key_from_read_group_range(alert, 'create_date:day')
            if key in day_map:
                day_map[key]['total'] += alert.get('__count', 0)
                if alert.get('severity') == 'critical':
                    day_map[key]['critical'] += alert.get('__count', 0)
        return [{
            'day': key,
            'label': fields.Date.to_date(key).strftime('%a'),
            'total': day_map[key]['total'],
            'critical': day_map[key]['critical'],
        } for key in day_keys]

    @api.model
    def get_admin_dashboard_data(self, date_range='week'):
        self._ensure_admin_dashboard_access()
        Patient = self.env['health.patient']
        Alert = self.env['health.alert']
        Ward = self.env['health.ward']

        today = fields.Date.context_today(self)
        today_start, today_end = self._local_date_to_utc_bounds(today)
        yesterday_start, yesterday_end = self._local_date_to_utc_bounds(today - timedelta(days=1))

        active_domain = self._active_patient_domain()
        open_critical_domain = self._open_alert_domain() + [('severity', '=', 'critical')]

        active_patients = self._read_group_count(Patient, active_domain)
        new_patients_today = self._read_group_count(
            Patient,
            active_domain + [('create_date', '>=', today_start), ('create_date', '<', today_end)]
        )
        critical_alerts = self._read_group_count(Alert, open_critical_domain)
        crit_today = self._read_group_count(
            Alert,
            [('create_date', '>=', today_start), ('create_date', '<', today_end), ('severity', '=', 'critical')],
        )
        crit_yesterday = self._read_group_count(
            Alert,
            [('create_date', '>=', yesterday_start), ('create_date', '<', yesterday_end), ('severity', '=', 'critical')],
        )

        responded_domain = [('response_time_minutes', '>', 0)]
        responded_count = self._read_group_count(Alert, responded_domain)
        within_sla = self._read_group_count(Alert, responded_domain + [('response_time_minutes', '<=', 5)])
        sla_compliance = round((within_sla / responded_count) * 100) if responded_count else 100
        response_rows = Alert.read_group(responded_domain, ['response_time_minutes:avg'], [], lazy=False)
        avg_response_minutes = response_rows[0].get('response_time_minutes', 0.0) if response_rows else 0.0
        avg_response = (
            f'{avg_response_minutes:.1f} min'
            if responded_count
            else 'N/A'
        )

        ai_anomalies = self._read_group_count(Alert, [('create_date', '>=', today_start), ('create_date', '<', today_end)])

        wards = []
        for ward in Ward.search([], order='name asc'):
            occupancy_pct = min(100, round(ward.capacity_percentage or 0))
            wards.append({
                'id': ward.id,
                'name': ward.name,
                'occupancy_percentage': occupancy_pct,
                'current_occupancy': ward.current_occupancy,
                'capacity': ward.capacity,
                'isFull': occupancy_pct >= 100,
            })
        wards.sort(key=lambda ward: ward['current_occupancy'], reverse=True)

        patient_status = {'stable': 0, 'warning': 0, 'critical': 0}
        for row in Patient.read_group(active_domain, ['risk_level'], ['risk_level'], lazy=False):
            risk_level = row.get('risk_level')
            count = row.get('__count', 0)
            if risk_level == 'critical':
                patient_status['critical'] += count
            elif risk_level in ['high', 'medium']:
                patient_status['warning'] += count
            else:
                patient_status['stable'] += count

        doctor_group = self.env.ref('health_monitoring.group_health_doctor', raise_if_not_found=False)
        admin_group = self.env.ref('health_monitoring.group_health_admin', raise_if_not_found=False)
        doctor_users = doctor_group.users if doctor_group else self.env['res.users']
        admin_users = admin_group.users if admin_group else self.env['res.users']
        doctor_users = doctor_users.filtered(lambda user: user.active and user.id != 1 and user not in admin_users)

        leaderboard_map = {
            user.id: {'id': user.id, 'name': user.name, 'total': 0, 'resolved': 0, 'critical': 0}
            for user in doctor_users
        }
        if doctor_users:
            total_rows = Alert.read_group(
                [('assigned_doctor_id', 'in', doctor_users.ids)],
                ['assigned_doctor_id'],
                ['assigned_doctor_id'],
                lazy=False,
            )
            resolved_rows = Alert.read_group(
                [('assigned_doctor_id', 'in', doctor_users.ids), '|', ('state', '=', 'resolved'), ('status', '=', 'handled')],
                ['assigned_doctor_id'],
                ['assigned_doctor_id'],
                lazy=False,
            )
            critical_rows = Alert.read_group(
                [('assigned_doctor_id', 'in', doctor_users.ids), ('severity', '=', 'critical')],
                ['assigned_doctor_id'],
                ['assigned_doctor_id'],
                lazy=False,
            )
            for row in total_rows:
                doctor = row.get('assigned_doctor_id')
                if doctor and doctor[0] in leaderboard_map:
                    leaderboard_map[doctor[0]]['total'] = row.get('__count', 0)
            for row in resolved_rows:
                doctor = row.get('assigned_doctor_id')
                if doctor and doctor[0] in leaderboard_map:
                    leaderboard_map[doctor[0]]['resolved'] = row.get('__count', 0)
            for row in critical_rows:
                doctor = row.get('assigned_doctor_id')
                if doctor and doctor[0] in leaderboard_map:
                    leaderboard_map[doctor[0]]['critical'] = row.get('__count', 0)

        leaderboard = []
        for doctor in sorted(
            leaderboard_map.values(),
            key=lambda item: (-item['resolved'], -item['total'], item['name']),
        ):
            doctor['borderColor'] = '#E24B4A' if doctor['critical'] >= 3 else '#F59E0B' if doctor['critical'] >= 1 else '#185FA5'
            leaderboard.append(doctor)

        escalations = []
        for alert in Alert.search(['|', ('status', '=', 'escalated'), ('escalation_level', '>', 0)], order='create_date desc', limit=6):
            escalations.append({
                'id': alert.id,
                'headline': alert.headline or 'Clinical Alert',
                'severity': alert.severity,
                'state': alert.state,
                'patient_id': [alert.patient_id.id, alert.patient_id.name] if alert.patient_id else False,
                'timeAgo': self._time_ago(alert.create_date),
                'doctorName': alert.assigned_doctor_id.name if alert.assigned_doctor_id else 'Unassigned',
            })

        insights = []
        near_capacity = [ward['name'] for ward in wards if ward['occupancy_percentage'] >= 90]
        if near_capacity:
            insights.append(f'Wards near capacity: {", ".join(near_capacity[:2])}')
        if critical_alerts > 5:
            insights.append(f'{critical_alerts} critical alerts pending - escalation risk high.')
        if avg_response not in ['N/A', '--']:
            insights.append(f'Average response time is {avg_response}.')
        if not insights:
            insights.append('No capacity or alert anomalies detected.')

        days = self._dashboard_range_days(date_range)
        return self._rpc_safe({
            'dateRange': date_range,
            'kpi': {
                'activePatients': active_patients,
                'activeDelta': new_patients_today,
                'criticalAlerts': critical_alerts,
                'criticalDelta': crit_today - crit_yesterday,
                'avgResponse': avg_response,
                'aiAnomalies': ai_anomalies,
            },
            'slaCompliance': sla_compliance,
            'wards': wards,
            'leaderboard': leaderboard,
            'escalations': escalations,
            'insights': insights,
            'patientStatus': patient_status,
            'alertTrend': self._alert_trend(days),
        })

    @api.model
    def get_admin_kpi_action(self, kpi):
        today = fields.Date.context_today(self)
        today_start, today_end = self._local_date_to_utc_bounds(today)
        if kpi == 'active_patients':
            return self._action_for_records('Active Patients', 'health.patient', self._active_patient_domain())
        if kpi == 'critical_alerts':
            return self._action_for_records(
                'Active Critical Alerts',
                'health.alert',
                self._open_alert_domain() + [('severity', '=', 'critical')],
            )
        if kpi == 'ai_anomalies':
            return self._action_for_records(
                'AI Anomalies Today',
                'health.alert',
                [('create_date', '>=', today_start), ('create_date', '<', today_end)],
            )
        if kpi == 'sla':
            return self._action_for_records(
                'Responded Alerts',
                'health.alert',
                [('response_time_minutes', '>', 0)],
            )
        return self._action_for_records('Dashboard Records', 'health.patient', [('id', '=', 0)])

    # -------------------------------------------------------------------------
    # Analytics dashboard
    # -------------------------------------------------------------------------
    def _analytics_period(self, period):
        try:
            days = int(period)
        except (TypeError, ValueError):
            days = 30
        return days if days in [7, 30, 90] else 30

    @api.model
    def get_analytics_dashboard_data(self, period='30'):
        self._ensure_admin_dashboard_access()
        days = self._analytics_period(period)
        start_date, _today, start_utc, end_utc = self._last_calendar_days_bounds(days)
        day_keys = self._day_labels(start_date, days)

        vital_domain = [('recorded_at', '>=', start_utc), ('recorded_at', '<', end_utc)]
        alert_domain = [('create_date', '>=', start_utc), ('create_date', '<', end_utc)]
        Vital = self.env['health.vital.record']
        Alert = self.env['health.alert']

        vitals_per_day = {key: 0 for key in day_keys}
        avg_score_per_day = {key: 0 for key in day_keys}
        vital_day_rows = Vital.read_group(
            vital_domain,
            ['recorded_at'],
            ['recorded_at:day'],
            lazy=False,
        )
        for vital in vital_day_rows:
            key = self._day_key_from_read_group_range(vital, 'recorded_at:day')
            if key in vitals_per_day:
                vitals_per_day[key] = vital.get('__count', 0)
        score_day_rows = Vital.read_group(
            vital_domain + [('ai_score', '>', 0)],
            ['recorded_at', 'ai_score:avg'],
            ['recorded_at:day'],
            lazy=False,
        )
        for vital in score_day_rows:
            key = self._day_key_from_read_group_range(vital, 'recorded_at:day')
            if key in avg_score_per_day:
                avg_score_per_day[key] = round(vital.get('ai_score') or 0)

        severity_data = {'low': 0, 'medium': 0, 'high': 0, 'critical': 0}
        for alert in Alert.read_group(alert_domain, ['severity'], ['severity'], lazy=False):
            severity = alert.get('severity')
            if severity in severity_data:
                severity_data[severity] += alert.get('__count', 0)

        triage = {'low': 0, 'medium': 0, 'high': 0, 'critical': 0, 'handled': 0}
        for patient in self.env['health.patient'].read_group(
            self._active_patient_domain(),
            ['risk_level'],
            ['risk_level'],
            lazy=False,
        ):
            risk_level = patient.get('risk_level') or 'low'
            count = patient.get('__count', 0)
            if risk_level in triage:
                triage[risk_level] += count
            else:
                triage['low'] += count

        vital_summary = Vital.read_group(vital_domain, [], [], lazy=False)
        score_summary = Vital.read_group(vital_domain + [('ai_score', '>', 0)], ['ai_score:avg'], [], lazy=False)
        total_vitals = vital_summary[0].get('__count', 0) if vital_summary else 0
        avg_ai_score = round(score_summary[0].get('ai_score') or 0) if score_summary else 0
        total_alerts = sum(severity_data.values())
        return self._rpc_safe({
            'period': str(days),
            'totalVitals': total_vitals,
            'totalAlerts': total_alerts,
            'avgAiScore': avg_ai_score,
            'criticalRate': round((severity_data['critical'] / total_alerts) * 100) if total_alerts else 0,
            'triage': triage,
            'vitalsPerDay': [{'day': key[5:], 'count': vitals_per_day[key]} for key in day_keys],
            'avgScorePerDay': [{
                'day': key[5:],
                'avg': avg_score_per_day[key],
            } for key in day_keys],
            'severityData': severity_data,
        })

    @api.model
    def get_analytics_kpi_action(self, kpi, period='30'):
        days = self._analytics_period(period)
        _start_date, _today, start_utc, end_utc = self._last_calendar_days_bounds(days)
        if kpi == 'vitals':
            return self._action_for_records(
                f'Vitals - Last {days} Days',
                'health.vital.record',
                [('recorded_at', '>=', start_utc), ('recorded_at', '<', end_utc)],
            )
        if kpi == 'alerts':
            return self._action_for_records(
                f'Alerts - Last {days} Days',
                'health.alert',
                [('create_date', '>=', start_utc), ('create_date', '<', end_utc)],
            )
        return self._action_for_records('Analytics Records', 'health.alert', [('id', '=', 0)])
