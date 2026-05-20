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
        this.chartLoaded = false;

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
            try {
                await loadJS("https://cdn.jsdelivr.net/npm/chart.js");
                this.chartLoaded = Boolean(window.Chart);
            } catch (e) {
                console.warn("Chart.js load failed; analytics dashboard will continue without charts.", e);
            }
        });

        onMounted(async () => {
            await this.fetchAll();
            this.renderCharts();
            this.state.loading = false;
        });
    }

    async fetchAll() {
        const data = await this.orm.call('health.dashboard', 'get_analytics_dashboard_data', [this.state.period]);
        this.state.period = data.period || this.state.period;
        this.state.totalVitals = data.totalVitals || 0;
        this.state.totalAlerts = data.totalAlerts || 0;
        this.state.avgAiScore = data.avgAiScore || 0;
        this.state.criticalRate = data.criticalRate || 0;
        this.state.triage = data.triage || { low: 0, medium: 0, high: 0, critical: 0, handled: 0 };
        this.vitalsPerDay = data.vitalsPerDay || [];
        this.avgScorePerDay = data.avgScorePerDay || [];
        this.severityData = data.severityData || { low: 0, medium: 0, high: 0, critical: 0 };
        return;
    }

    renderCharts() {
        if (!this.chartLoaded || !window.Chart) return;

        Chart.defaults.font.family = "'Inter', system-ui, sans-serif";
        Chart.defaults.color = '#64748B';

        // Chart 1: vitals logged per day.
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

        // Chart 2: alert severity donut.
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

        // Chart 3: average AI score per day.
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
    async openVitals() {
        const action = await this.orm.call('health.dashboard', 'get_analytics_kpi_action', ['vitals', this.state.period]);
        this.action.doAction(action);
    }

    async openAlerts() {
        const action = await this.orm.call('health.dashboard', 'get_analytics_kpi_action', ['alerts', this.state.period]);
        this.action.doAction(action);
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
