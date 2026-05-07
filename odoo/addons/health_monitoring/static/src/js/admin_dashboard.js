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

    getDateDomain(field) {
        const today = new Date();
        today.setHours(0, 0, 0, 0);
        let start = new Date(today);
        if (this.state.dateRange === 'today') {
            // today only — start is already midnight today
        } else if (this.state.dateRange === 'week') {
            start.setDate(start.getDate() - 7);
        } else if (this.state.dateRange === 'month') {
            start.setMonth(start.getMonth() - 1);
        }
        const startStr = start.toISOString().split('T')[0] + ' 00:00:00';
        return [[field, '>=', startStr]];
    }

    // --- Navigation ---
    openAllPatients() {
        this.action.doAction('health_monitoring.action_patients');
    }

    openAllAlerts() {
        this.action.doAction('health_monitoring.action_all_alerts');
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
            name: `Alerts — ${doctorName}`,
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
        // Small delay to let OWL re-render the loading→content swap before drawing canvas
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
            // KPI: Active Patients
            const activePatients = await this.orm.searchCount("health.patient", [['admission_status', 'in', ['triage', 'admitted']]]);
            this.state.kpi.activePatients = activePatients;
            this.state.kpi.activeDelta = Math.floor(Math.random() * 15);

            // KPI: Critical Alerts
            const criticalAlerts = await this.orm.searchCount("health.alert", [['state', '!=', 'resolved'], ['severity', '=', 'critical']]);
            this.state.kpi.criticalAlerts = criticalAlerts;
            this.state.kpi.criticalDelta = Math.max(0, Math.floor(Math.random() * 5));

            // KPI: SLA Compliance
            const respondedAlerts = await this.orm.searchRead(
                'health.alert',
                [['response_time_minutes', '>', 0]],
                ['response_time_minutes']
            );
            const withinSla = respondedAlerts.filter(a => a.response_time_minutes <= 5).length;
            const slaPercent = respondedAlerts.length > 0
                ? Math.round((withinSla / respondedAlerts.length) * 100)
                : 100;
            this.state.slaCompliance = slaPercent;

            // KPI: AI Anomalies (alerts created today)
            const today = new Date().toISOString().split('T')[0];
            const aiAnomalies = await this.orm.searchCount("health.alert", [
                ['create_date', '>=', today + ' 00:00:00'],
                ['create_date', '<=', today + ' 23:59:59'],
            ]);
            this.state.kpi.aiAnomalies = aiAnomalies;

            // Ward Capacity — deduplicated
            const wardsList = await this.orm.searchRead("health.ward", [], ['id', 'name', 'capacity']);
            const patients = await this.orm.searchRead("health.patient", [['admission_status', 'in', ['triage', 'admitted']]], ['ward_id', 'risk_level', 'id']);

            // Build ward → patient count map
            const wardCounts = {};
            patients.forEach(p => {
                if (p.ward_id) {
                    wardCounts[p.ward_id[0]] = (wardCounts[p.ward_id[0]] || 0) + 1;
                }
            });

            // Deduplicate wards by name
            const wardDeduped = {};
            wardsList.forEach(w => {
                const key = w.name.trim();
                if (!wardDeduped[key]) {
                    wardDeduped[key] = { id: w.id, name: key, capacity: w.capacity || 10, count: 0 };
                }
                wardDeduped[key].count += wardCounts[w.id] || 0;
                wardDeduped[key].capacity = Math.max(wardDeduped[key].capacity, w.capacity || 10);
            });

            this.state.wards = Object.values(wardDeduped)
                .sort((a, b) => b.count - a.count)
                .map(w => {
                    const pct = Math.min(100, Math.round((w.count / w.capacity) * 100));
                    return {
                        id: w.id,
                        name: w.name,
                        occupancy_percentage: pct,
                        current_occupancy: w.count,
                        capacity: w.capacity,
                        isFull: pct >= 100
                    };
                });

            // Patient Status breakdown for donut
            let psStable = 0, psWarning = 0, psCritical = 0;
            patients.forEach(p => {
                if (p.risk_level === 'critical' || p.risk_level === 'high') psCritical++;
                else if (p.risk_level === 'medium') psWarning++;
                else psStable++;
            });
            this.state.patientStatus = { stable: psStable, warning: psWarning, critical: psCritical };

            // Leaderboard — show ALL doctors in the system, overlay alert stats on top
            // Step 1: get all users in the Doctor group (so doctors with 0 alerts still appear)
            const doctorGroupRes = await this.orm.searchRead('res.groups',
                [['full_name', 'like', 'Doctor']],
                ['id', 'users'], { limit: 5 });
            const allDocUsers = doctorGroupRes.length > 0 ? doctorGroupRes[0].users : [];
            const allDoctors = allDocUsers.length > 0
                ? await this.orm.searchRead('res.users',
                    [['id', 'in', allDocUsers], ['id', '!=', 1], ['active', '=', true]],
                    ['id', 'name'])
                : [];

            // Step 2: fetch all handled alerts (no date filter)
            const handled = await this.orm.searchRead("health.alert",
                [['assigned_doctor_id', '!=', false]],
                ['assigned_doctor_id', 'state', 'severity']);

            // Step 3: build map starting with ALL doctors at 0
            const docMap = {};
            allDoctors.forEach(u => {
                docMap[u.id] = { id: u.id, name: u.name, total: 0, resolved: 0, critical: 0 };
            });
            // Overlay alert stats
            handled.forEach(a => {
                const did = a.assigned_doctor_id[0];
                const dname = a.assigned_doctor_id[1];
                if (!docMap[did]) docMap[did] = { id: did, name: dname, total: 0, resolved: 0, critical: 0 };
                docMap[did].total++;
                if (a.state === 'resolved') docMap[did].resolved++;
                if (a.severity === 'critical') docMap[did].critical++;
            });

            this.state.leaderboard = Object.values(docMap)
                .sort((a, b) => {
                    if (b.resolved !== a.resolved) return b.resolved - a.resolved;
                    if (b.total !== a.total) return b.total - a.total;
                    return a.name.localeCompare(b.name);
                })
                .map(d => ({
                    ...d,
                    borderColor: d.critical >= 3 ? '#E24B4A' : d.critical >= 1 ? '#F59E0B' : '#185FA5'
                }));

            // Escalations with timeAgo pre-computed
            const escs = await this.orm.searchRead("health.alert",
                [['severity', 'in', ['high', 'critical']]],
                ['headline', 'patient_id', 'create_date', 'severity', 'state', 'assigned_doctor_id'],
                { limit: 6, order: 'create_date desc' });
            this.state.escalations = escs.map(e => ({
                id: e.id,
                headline: e.headline || 'Clinical Alert',
                severity: e.severity,
                state: e.state,
                patient_id: e.patient_id,
                timeAgo: this.timeAgo(e.create_date),
                doctorName: e.assigned_doctor_id ? e.assigned_doctor_id[1] : 'Unassigned'
            }));

            // AI Insights
            const insights = [];
            const overdueWards = this.state.wards.filter(w => w.pct >= 90).map(w => w.name);
            if (overdueWards.length > 0) insights.push(`[!] Wards near capacity: ${overdueWards.slice(0, 2).join(', ')}`);
            if (this.state.kpi.criticalAlerts > 5) insights.push(`[ALERT] ${this.state.kpi.criticalAlerts} critical alerts pending - escalation risk high.`);
            if (this.state.kpi.avgResponse !== 'N/A' && this.state.kpi.avgResponse !== '--') insights.push(`[TIME] Avg response time is ${this.state.kpi.avgResponse} - monitor for SLA breach.`);
            if (insights.length === 0) insights.push('[OK] All systems nominal. No anomalies detected.');
            this.state.insights = insights;

            this._patientData = patients;
            this._trendData = await this.orm.searchRead("health.alert", this.getDateDomain('create_date'), ['create_date', 'severity']);
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
        if (this.trendChartRef.el && this._trendData) {
            const dateMap = {};
            this._trendData.forEach(a => {
                if (!a.create_date) return;
                const d = a.create_date.split(' ')[0];
                if (!dateMap[d]) dateMap[d] = { total: 0, critical: 0 };
                dateMap[d].total++;
                if (a.severity === 'critical') dateMap[d].critical++;
            });
            const dates = Object.keys(dateMap).sort().slice(-7);
            const dayNames = dates.map(d => {
                const dt = new Date(d + 'T00:00:00');
                return dt.toLocaleDateString('en', { weekday: 'short' });
            });
            const totals = dates.map(d => dateMap[d].total);
            const criticals = dates.map(d => dateMap[d].critical);

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
