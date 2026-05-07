/** @odoo-module **/

import { Component, onWillStart, onMounted, useState, useRef } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { loadJS } from "@web/core/assets";
import { registry } from "@web/core/registry";

export class AnalyticsDashboard extends Component {
    static template = "health_monitoring.AnalyticsDashboard";

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.charts = {};
        this.trendRef = useRef("trendChart");
        this.severityRef = useRef("severityChart");
        this.scoreRef = useRef("scoreChart");

        this.state = useState({
            loading: true,
            period: '30', // days
            totalVitals: 0,
            totalAlerts: 0,
            avgAiScore: 0,
            criticalRate: 0,
            triage: { low: 0, medium: 0, high: 0, critical: 0, handled: 0 }
        });

        onWillStart(async () => {
            await loadJS("https://cdn.jsdelivr.net/npm/chart.js");
        });

        onMounted(async () => {
            await this.fetchAll();
            this.renderCharts();
            this.state.loading = false;
        });
    }

    async fetchAll() {
        const days = parseInt(this.state.period);
        const since = new Date();
        since.setDate(since.getDate() - days);
        const sinceStr = since.toISOString().slice(0, 19).replace('T', ' ');

        // Fetch vitals
        const vitals = await this.orm.searchRead(
            'health.vital.record',
            [['recorded_at', '>=', sinceStr]],
            ['recorded_at', 'ai_score', 'status', 'patient_id']
        );

        // Fetch alerts
        const alerts = await this.orm.searchRead(
            'health.alert',
            [['create_date', '>=', sinceStr]],
            ['severity', 'state', 'create_date']
        );

        // Fetch live patient triage state
        const patients = await this.orm.searchRead(
            'health.patient',
            [['admission_status', 'in', ['triage', 'admitted']]],
            ['risk_level']
        );

        // Calculate triage distribution
        const triageCounts = { low: 0, medium: 0, high: 0, critical: 0, handled: 0 };
        patients.forEach(p => {
            if (p.risk_level && triageCounts[p.risk_level] !== undefined) {
                triageCounts[p.risk_level]++;
            } else if (!p.risk_level) {
                triageCounts.low++; // default to low if none
            }
        });
        this.state.triage = triageCounts;

        // Generate all dates in range
        const allDays = [];
        for (let i = days - 1; i >= 0; i--) {
            const d = new Date();
            d.setDate(d.getDate() - i);
            allDays.push(d.toISOString().slice(0, 10));
        }

        const dayMap = {};
        const scoreMap = {};
        allDays.forEach(d => {
            dayMap[d] = 0;
            scoreMap[d] = [];
        });

        vitals.forEach(v => {
            if (v.recorded_at) {
                const day = v.recorded_at.slice(0, 10);
                if (dayMap[day] !== undefined) {
                    dayMap[day]++;
                    scoreMap[day].push(v.ai_score || 0);
                }
            }
        });

        this.vitalsPerDay = allDays.map(d => ({ day: d.slice(5), count: dayMap[d] }));
        this.avgScorePerDay = allDays.map(d => ({
            day: d.slice(5),
            avg: scoreMap[d].length ? Math.round(scoreMap[d].reduce((a,b) => a+b,0) / scoreMap[d].length) : 0
        }));

        // Alert severity breakdown
        const sevCount = { low: 0, medium: 0, high: 0, critical: 0 };
        alerts.forEach(a => { if (sevCount[a.severity] !== undefined) sevCount[a.severity]++; });
        this.severityData = sevCount;

        // Summary stats
        this.state.totalVitals = vitals.length;
        this.state.totalAlerts = alerts.length;
        const scores = vitals.map(v => v.ai_score || 0).filter(s => s > 0);
        this.state.avgAiScore = scores.length ? Math.round(scores.reduce((a,b)=>a+b,0)/scores.length) : 0;
        this.state.criticalRate = alerts.length
            ? Math.round((sevCount.critical / alerts.length) * 100)
            : 0;
    }

    renderCharts() {
        Chart.defaults.font.family = "'Inter', system-ui, sans-serif";
        Chart.defaults.color = '#64748B';

        // Chart 1 — Vitals logged per day (bar)
        if (this.charts.trend) this.charts.trend.destroy();
        if (this.trendRef.el) {
            this.charts.trend = new Chart(this.trendRef.el, {
                type: 'bar',
                data: {
                    labels: this.vitalsPerDay.map(d => d.day),
                    datasets: [{
                        label: 'Vitals Logged',
                        data: this.vitalsPerDay.map(d => d.count),
                        backgroundColor: '#185FA5',
                        borderRadius: 6,
                        barPercentage: 0.6
                    }]
                },
                options: {
                    responsive: true, maintainAspectRatio: false,
                    plugins: { 
                        legend: { display: false },
                        tooltip: { backgroundColor: '#0F172A', padding: 12, cornerRadius: 8 }
                    },
                    scales: {
                        y: { beginAtZero: true, grid: { color: '#F1F5F9', drawBorder: false } },
                        x: { grid: { display: false, drawBorder: false } }
                    }
                }
            });
        }

        // Chart 2 — Alert severity donut
        if (this.charts.severity) this.charts.severity.destroy();
        if (this.severityRef.el) {
            this.charts.severity = new Chart(this.severityRef.el, {
                type: 'doughnut',
                data: {
                    labels: ['Low', 'Medium', 'High', 'Critical'],
                    datasets: [{
                        data: [
                            this.severityData.low,
                            this.severityData.medium,
                            this.severityData.high,
                            this.severityData.critical
                        ],
                        backgroundColor: ['#10B981', '#60A5FA', '#F59E0B', '#E24B4A'],
                        borderWidth: 2,
                        borderColor: '#ffffff',
                        hoverOffset: 4
                    }]
                },
                options: {
                    responsive: true, maintainAspectRatio: false,
                    cutout: '75%',
                    plugins: { 
                        legend: { position: 'right', labels: { padding: 20, usePointStyle: true, pointStyle: 'circle' } },
                        tooltip: { backgroundColor: '#0F172A', padding: 12, cornerRadius: 8 }
                    }
                }
            });
        }

        // Chart 3 — Avg AI score per day (line)
        if (this.charts.score) this.charts.score.destroy();
        if (this.scoreRef.el) {
            // Create gradient
            const ctx = this.scoreRef.el.getContext('2d');
            const gradient = ctx.createLinearGradient(0, 0, 0, 180);
            gradient.addColorStop(0, 'rgba(226, 75, 74, 0.25)');
            gradient.addColorStop(1, 'rgba(226, 75, 74, 0)');

            this.charts.score = new Chart(this.scoreRef.el, {
                type: 'line',
                data: {
                    labels: this.avgScorePerDay.map(d => d.day),
                    datasets: [{
                        label: 'Avg AI Risk Score',
                        data: this.avgScorePerDay.map(d => d.avg),
                        borderColor: '#E24B4A',
                        backgroundColor: gradient,
                        fill: true,
                        tension: 0.4,
                        borderWidth: 2,
                        pointRadius: 4,
                        pointBackgroundColor: '#fff',
                        pointBorderColor: '#E24B4A',
                        pointBorderWidth: 2,
                        pointHoverRadius: 6
                    }]
                },
                options: {
                    responsive: true, maintainAspectRatio: false,
                    plugins: { 
                        legend: { display: false },
                        tooltip: { backgroundColor: '#0F172A', padding: 12, cornerRadius: 8 }
                    },
                    scales: {
                        y: { min: 0, max: 100, grid: { color: '#F1F5F9', drawBorder: false } },
                        x: { grid: { display: false, drawBorder: false } }
                    }
                }
            });
        }
    }

    async setPeriod(days) {
        this.state.period = days;
        this.state.loading = true;
        await this.fetchAll();
        this.renderCharts();
        this.state.loading = false;
    }

    // --- Actions ---
    openVitals() {
        this.action.doAction({
            type: 'ir.actions.act_window',
            name: 'Vitals History',
            res_model: 'health.vital.record',
            views: [[false, 'list'], [false, 'form']],
            target: 'current'
        });
    }

    openAlerts() {
        this.action.doAction({
            type: 'ir.actions.act_window',
            name: 'Alert History',
            res_model: 'health.alert',
            views: [[false, 'list'], [false, 'form']],
            target: 'current'
        });
    }

    // From Task 6
    async retrainModel() {
        this.state.loading = true;
        try {
            await this.orm.call('health.vital.record', 'action_retrain_ai_model', []);
            // Notification handled by python returning action, but fallback here
        } catch(e) {
            alert('Retraining failed: ' + e.message);
        }
        this.state.loading = false;
    }
}

registry.category("actions").add("smartlab_analytics", AnalyticsDashboard);
