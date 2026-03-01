from odoo import models, fields, api

class HealthDashboard(models.TransientModel):
    _name = 'health.dashboard'
    _description = 'Dashboard KPI'

    name = fields.Char(default='Dashboard')
    total_patients = fields.Integer(compute='_compute_kpis')
    active_alerts = fields.Integer(compute='_compute_kpis')
    critical_alerts = fields.Integer(compute='_compute_kpis')
    avg_score = fields.Float(compute='_compute_kpis')
    
    recent_alert_ids = fields.Many2many('health.alert', compute='_compute_recent_activity')
    recent_vital_ids = fields.Many2many('health.vital.record', compute='_compute_recent_activity')

    def _compute_recent_activity(self):
        for rec in self:
            rec.recent_alert_ids = self.env['health.alert'].search([], order='create_date desc', limit=5)
            rec.recent_vital_ids = self.env['health.vital.record'].search([], order='recorded_at desc', limit=5)

    def _compute_kpis(self):
        for rec in self:
            rec.total_patients = self.env['health.patient'].search_count([])
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
