/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, onWillStart, onMounted, onWillDestroy, useState, useRef, useEffect } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { loadJS } from "@web/core/assets";

export class AdminDashboard extends Component {
    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");

        this.trendChartRef = useRef("trendChart");
        this.statusChartRef = useRef("statusChart");
        this.charts = {};
        this.chartLoaded = false;

        this.state = useState({
            isLoading: true,
            currentTime: new Date().toLocaleTimeString(),
            dateRange: 'week',
            kpi: {
                activePatients: 0,
                activeDelta: 0,
                criticalAlerts: 0,
                criticalDelta: 0,
                avgResponse: '--',
                aiAnomalies: 0,
            },
            wards: [],
            leaderboard: [],
            escalations: [],
            insights: [],
            patientStatus: { stable: 0, warning: 0, critical: 0 },
            alertTrend: [],
            slaCompliance: 100,
        });

        onWillStart(async () => {
            // Load Chart.js first
            try {
                await loadJS("https://cdn.jsdelivr.net/npm/chart.js");
                this.chartLoaded = true;
            } catch (e) {
                console.warn("Chart.js load failed:", e);
            }
            await this.fetchAll();
        });

        onMounted(() => {
            // Delay chart rendering to ensure DOM is ready
            setTimeout(() => {
                this.renderCharts();
            }, 100);
            
            this.refreshInterval = setInterval(() => {
                this.fetchAll().then(() => {
                    setTimeout(() => this.renderCharts(), 50);
                });
            }, 30000); // 30 seconds
            
            this.clockInterval = setInterval(() => {
                this.state.currentTime = new Date().toLocaleTimeString();
            }, 1000);
        });

        onWillDestroy(() => {
            clearInterval(this.refreshInterval);
            clearInterval(this.clockInterval);
            Object.values(this.charts).forEach(c => c && c.destroy());
        });
    }

    // --- Helpers ---
    timeAgo(dateStr) {
        if (!dateStr) return '';
        const past = new Date(dateStr.replace(' ', 'T') + 'Z');
        const diffMins = Math.floor((new Date() - past) / 60000);
        if (diffMins < 1) return 'just now';
        if (diffMins < 60) return `${diffMins}m ago`;
        const diffHrs = Math.floor(diffMins / 60);
        if (diffHrs < 24) return `${diffHrs}h ago`;
        return `${Math.floor(diffHrs / 24)}d ago`;
    }

    _utcPad(n) { return String(n).padStart(2, '0'); }

    _utcDateStr(d) {
        return `${d.getUTCFullYear()}-${this._utcPad(d.getUTCMonth()+1)}-${this._utcPad(d.getUTCDate())}`;
    }

    getDateDomain(field) {
        const now = new Date();
        let start = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate()));
        if (this.state.dateRange === 'today') {
            // start is already UTC midnight today
        } else if (this.state.dateRange === 'week') {
            start.setUTCDate(start.getUTCDate() - 7);
        } else if (this.state.dateRange === 'month') {
            start.setUTCMonth(start.getUTCMonth() - 1);
        }
        return [[field, '>=', this._utcDateStr(start) + ' 00:00:00']];
    }

    // --- Navigation ---
    async openAllPatients() {
        const action = await this.orm.call("health.dashboard", "get_admin_kpi_action", ["active_patients"]);
        this.action.doAction(action);
    }

    async openAllAlerts() {
        const action = await this.orm.call("health.dashboard", "get_admin_kpi_action", ["critical_alerts"]);
        this.action.doAction(action);
    }

    async openAiAnomalies() {
        const action = await this.orm.call("health.dashboard", "get_admin_kpi_action", ["ai_anomalies"]);
        this.action.doAction(action);
    }

    async openSlaAlerts() {
        const action = await this.orm.call("health.dashboard", "get_admin_kpi_action", ["sla"]);
        this.action.doAction(action);
    }

    openAlert(alertId) {
        this.action.doAction({
            type: 'ir.actions.act_window',
            res_model: 'health.alert',
            res_id: alertId,
            views: [[false, 'form']],
            target: 'current'
        });
    }

    openPatient(patientId) {
        this.action.doAction({
            type: 'ir.actions.act_window',
            res_model: 'health.patient',
            res_id: patientId,
            views: [[false, 'form']],
            target: 'current'
        });
    }

    openDoctorAlerts(doctorId, doctorName) {
        this.action.doAction({
            type: 'ir.actions.act_window',
            name: `Alerts - ${doctorName}`,
            res_model: 'health.alert',
            views: [[false, 'list'], [false, 'form']],
            domain: [['assigned_doctor_id', '=', doctorId]],
            target: 'current'
        });
    }

    openDoctor(doctorId) {
        this.action.doAction({
            type: 'ir.actions.act_window',
            res_model: 'res.users',
            res_id: doctorId,
            views: [[false, 'form']],
            target: 'new',
        });
    }

    openWard(wardId) {
        this.action.doAction({
            type: 'ir.actions.act_window',
            res_model: 'health.ward',
            res_id: wardId,
            views: [[false, 'form']],
            target: 'current',
        });
    }

    // --- Range buttons ---
    async setRange(range) {
        this.state.dateRange = range;
        await this.fetchAll();
        // Small delay to let OWL re-render the loading/content swap before drawing canvas
        setTimeout(() => this.renderCharts(), 80);
    }

    async onRefresh() {
        await this.fetchAll();
        setTimeout(() => this.renderCharts(), 80);
    }

    async onDateRangeChange(ev) {
        this.state.dateRange = ev.target.value;
        await this.fetchAll();
        setTimeout(() => this.renderCharts(), 80);
    }

    // --- Data ---
    async fetchAll() {
        this.state.isLoading = true;
        try {
            const data = await this.orm.call("health.dashboard", "get_admin_dashboard_data", [this.state.dateRange]);
            this.state.kpi = data.kpi || this.state.kpi;
            this.state.slaCompliance = data.slaCompliance;
            this.state.wards = data.wards || [];
            this.state.leaderboard = data.leaderboard || [];
            this.state.escalations = data.escalations || [];
            this.state.insights = data.insights || [];
            this.state.patientStatus = data.patientStatus || { stable: 0, warning: 0, critical: 0 };
            this.state.alertTrend = data.alertTrend || [];
            this._patientData = [];
            this._trendData = [];
            return;
        } catch (e) {
            console.error("Admin dashboard fetch error:", e);
            this.notification.add("Failed to load dashboard data", { type: 'warning' });
        } finally {
            this.state.isLoading = false;
        }
    }

    // --- Charts ---
    renderCharts() {
        if (this.state.isLoading || !this.chartLoaded) return;
        if (!window.Chart) return;
        Object.values(this.charts).forEach(c => c && c.destroy());
        this.charts = {};

        Chart.defaults.color = '#94a3b8';
        Chart.defaults.font.family = "'Inter', sans-serif";

        // Alert Trend Line Chart
        if (this.trendChartRef.el && this.state.alertTrend) {
            const trend = this.state.alertTrend || [];
            const dayNames = trend.map(d => d.label);
            const totals = trend.map(d => d.total);
            const criticals = trend.map(d => d.critical);

            this.charts.trend = new Chart(this.trendChartRef.el, {
                type: 'line',
                data: {
                    labels: dayNames.length > 0 ? dayNames : ['Mon','Tue','Wed','Thu','Fri','Sat','Sun'],
                    datasets: [
                        { label: 'All Alerts', data: totals.length > 0 ? totals : [0,0,0,0,0,0,0],
                          borderColor: '#3B82F6', backgroundColor: 'rgba(59,130,246,0.08)',
                          tension: 0.4, fill: true, pointRadius: 3, pointBackgroundColor: '#3B82F6' },
                        { label: 'Critical', data: criticals.length > 0 ? criticals : [0,0,0,0,0,0,0],
                          borderColor: '#EF4444', backgroundColor: 'rgba(239,68,68,0.07)',
                          tension: 0.4, fill: true, pointRadius: 3, pointBackgroundColor: '#EF4444' },
                    ]
                },
                options: {
                    responsive: true, maintainAspectRatio: false,
                    plugins: { legend: { position: 'bottom', labels: { color: '#64748b', font: { size: 11 }, usePointStyle: true } } },
                    scales: {
                        x: { grid: { display: false }, ticks: { color: '#64748b', font: { size: 10 } } },
                        y: { grid: { color: '#F1F5F9' }, ticks: { color: '#64748b', font: { size: 10 } }, beginAtZero: true }
                    }
                }
            });
        }

        // Patient Status Donut
        if (this.statusChartRef.el && this._patientData) {
            const { stable, warning, critical } = this.state.patientStatus;
            const total = stable + warning + critical;

            this.charts.status = new Chart(this.statusChartRef.el, {
                type: 'doughnut',
                data: {
                    labels: ['Stable', 'Warning', 'Critical'],
                    datasets: [{
                        data: [stable, warning, critical],
                        backgroundColor: ['#10B981', '#FBBF24', '#FC8181'],
                        hoverBackgroundColor: ['#059669', '#F59E0B', '#F56565'],
                        borderWidth: 0,
                        hoverOffset: 4
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    cutout: '72%',
                    plugins: {
                        legend: {
                            position: 'bottom',
                            labels: { color: '#64748b', padding: 12, font: { size: 11 }, usePointStyle: true, pointStyle: 'circle' }
                        },
                        tooltip: {
                            callbacks: {
                                label: (ctx) => ` ${ctx.label}: ${ctx.raw} patients`
                            }
                        }
                    }
                },
                plugins: [{
                    id: 'centerText',
                    afterDraw(chart) {
                        const { ctx, chartArea } = chart;
                        if (!chartArea) return;
                        const centerX = (chartArea.left + chartArea.right) / 2;
                        const centerY = (chartArea.top + chartArea.bottom) / 2;
                        ctx.save();
                        ctx.font = "bold 26px 'Inter', sans-serif";
                        ctx.fillStyle = '#0F172A';
                        ctx.textAlign = 'center';
                        ctx.textBaseline = 'middle';
                        ctx.fillText(total, centerX, centerY - 8);
                        ctx.font = "11px 'Inter', sans-serif";
                        ctx.fillStyle = '#94a3b8';
                        ctx.fillText('patients', centerX, centerY + 12);
                        ctx.restore();
                    }
                }]
            });
        }
    }
}

AdminDashboard.template = "health_monitoring.AdminDashboardTemplate";
registry.category("actions").add("smartlab_admin_dashboard", AdminDashboard);
