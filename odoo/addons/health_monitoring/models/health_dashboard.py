from odoo import models, fields, api

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

    def _compute_recent_activity(self):
        for rec in self:
            # My Watchlist: Explicitly find patients followed by the current user
            followed_ids = self.env['mail.followers'].search([
                ('res_model', '=', 'health.patient'),
                ('partner_id', '=', self.env.user.partner_id.id)
            ]).mapped('res_id')
            rec.followed_patient_ids = self.env['health.patient'].browse(followed_ids)

            rec.recent_alert_ids = self.env['health.alert'].search([
                ('state', '!=', 'resolved')
            ], order='create_date desc', limit=10)
            rec.recent_vital_ids = self.env['health.vital.record'].search([], order='recorded_at desc', limit=10)

    def _compute_kpis(self):
        for rec in self:
            rec.total_patients = self.env['health.patient'].search_count([])

    def _compute_kpi_values(self):
        for rec in self:
            alerts = self.env['health.alert'].search([('state', '!=', 'resolved')])
            rec.active_alerts = len(alerts)
            rec.critical_alerts = len(alerts.filtered(lambda a: a.severity == 'critical'))
            
            patients = self.env['health.patient'].search([('last_score', '>', 0)])
            valid_scores = [float(s) for s in patients.mapped('last_score') if s]
            rec.avg_score = sum(valid_scores) / len(valid_scores) if valid_scores else 0.0

    def action_open_patients(self):
        return {
            'name': 'Patients',
            'type': 'ir.actions.act_window',
            'res_model': 'health.patient',
            'view_mode': 'kanban,tree,form',
        }

    def action_open_alerts(self):
        return {
            'name': 'Active Alerts',
            'type': 'ir.actions.act_window',
            'res_model': 'health.alert',
            'view_mode': 'kanban,tree,form',
            'domain': [('state', '!=', 'resolved')],
        }

    def action_open_critical(self):
        return {
            'name': 'Critical Alerts',
            'type': 'ir.actions.act_window',
            'res_model': 'health.alert',
            'view_mode': 'kanban,tree,form',
            'domain': [('severity', '=', 'critical'), ('state', '!=', 'resolved')],
        }
