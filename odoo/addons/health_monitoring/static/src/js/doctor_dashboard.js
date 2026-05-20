/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, onWillStart, onMounted, onWillDestroy, useState, useRef } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { loadJS } from "@web/core/assets";

export class DoctorDashboard extends Component {
    setup() {
        this.orm = useService("orm");
        this.user = useService("user");
        this.action = useService("action");
        this.notification = useService("notification");

        this.trendChartRef = useRef("trendChart");
        this.charts = {};
        this.chartLoaded = false;

        this.state = useState({
            doctorName: '',
            wardName: 'Unassigned',
            activeCaseCount: 0,
            unclaimedAlerts: [],
            myActiveAlerts: [],
            selectedPatient: null,
            vitals: {},
            showVitalsChart: false,
            risk: {
                arrhythmia: 0, arrhythmiaColor: '#10b981',
                hypoxia: 0, hypoxiaColor: '#10b981',
                hypertension: 0, hypertensionColor: '#10b981',
                fever: 0, feverColor: '#10b981',
            },
        });

        this._handleKeyDown = this.handleKeyDown.bind(this);

        onWillStart(async () => {
            try {
                await loadJS("https://cdn.jsdelivr.net/npm/chart.js");
                this.chartLoaded = Boolean(window.Chart);
            } catch (e) {
                console.warn("Chart.js load failed; doctor dashboard will continue without trend charts.", e);
            }
            // Get user name
            const userRec = await this.orm.read("res.users", [this.user.userId], ["name"]);
            if (userRec.length > 0) {
                this.state.doctorName = userRec[0].name;
            }
            this.wardIds = [];
            this.wardId = null;
            await this.fetchQueue();
        });

        onMounted(() => {
            document.addEventListener("keydown", this._handleKeyDown);
            this.refreshInterval = setInterval(async () => {
                await this.fetchQueue();
                if (this.state.selectedPatient) {
                    await this.fetchPatientData(this.state.selectedPatient.id);
                    // Re-render chart after background refresh
                    setTimeout(() => this.renderTrendChart(), 150);
                }
            }, 30000);  // 30s auto-refresh
        });

        onWillDestroy(() => {
            document.removeEventListener("keydown", this._handleKeyDown);
            clearInterval(this.refreshInterval);
            Object.values(this.charts).forEach(c => c && c.destroy());
        });
    }

    // --- Helpers ---
    timeAgo(dateStr) {
        if (!dateStr) return '';
        const past = new Date(dateStr.replace(' ', 'T') + 'Z');
        const diffMins = Math.floor((new Date() - past) / 60000);
        if (diffMins < 1) return 'Just now';
        if (diffMins < 60) return `${diffMins}m ago`;
        const diffHrs = Math.floor(diffMins / 60);
        if (diffHrs < 24) return `${diffHrs}h ago`;
        return `${Math.floor(diffHrs / 24)}d ago`;
    }

    // --- Keyboard ---
    handleKeyDown(ev) {
        if (ev.target.tagName === "INPUT" || ev.target.tagName === "TEXTAREA") return;
        if (ev.key.toLowerCase() === 'c' && this.state.unclaimedAlerts.length > 0) {
            this.onClaimAlert(this.state.unclaimedAlerts[0].id);
        } else if (ev.key.toLowerCase() === 'r' && this.state.selectedPatient) {
            const active = this.state.myActiveAlerts.find(a => a.patient_id[0] === this.state.selectedPatient.id);
            if (active) this.onResolveAlert(active.id);
        }
    }

    // --- Actions ---
    async onRefresh() {
        await this.fetchQueue();
        if (this.state.selectedPatient) {
            await this.fetchPatientData(this.state.selectedPatient.id);
        }
    }

    async onViewPatient(alert) {
        // Destroy existing chart so the canvas is clean before new data renders
        if (this.charts.trend) {
            this.charts.trend.destroy();
            this.charts.trend = null;
        }
        this.state.selectedPatient = null;  // clear panel immediately for visual feedback
        await this.fetchPatientData(alert.patient_id[0]);
        // chart rendered inside fetchPatientData with 300ms delay
    }

    async onClaimAlert(alertId) {
        // Find the alert before claiming so we know which patient to load
        const alertRec = this.state.unclaimedAlerts.find(a => a.id === alertId);
        try {
            await this.orm.call("health.alert", "action_claim_alert", [[alertId]]);
        } catch (e) {
            console.error("Alert claim failed:", e);
            this.notification.add("Could not claim this alert. Refresh the queue and try again.", { type: "warning" });
            return;
        }
        // Refresh queue first so the card moves to My Cases
        await this.fetchQueue();
        // Auto-load the claimed patient into the right panel
        if (alertRec && alertRec.patient_id) {
            if (this.charts.trend) { this.charts.trend.destroy(); this.charts.trend = null; }
            await this.fetchPatientData(alertRec.patient_id[0]);
        }
    }

    async onResolveAlert(alertId) {
        // Check if we're resolving the currently-selected patient's alert
        const resolvedAlert = this.state.myActiveAlerts.find(a => a.id === alertId);
        const isSelectedPatient = resolvedAlert && this.state.selectedPatient
            && resolvedAlert.patient_id[0] === this.state.selectedPatient.id;

        const action = await this.orm.call("health.alert", "action_resolve", [[alertId]]);
        if (action) {
            this.action.doAction(action, {
                onClose: () => {
                    this.fetchQueue();
                }
            });
        } else {
            await this.fetchQueue();
        }

        // If the resolved alert belonged to the patient in the right panel,
        // Check if they still have active alerts. If not, clear the panel.
        if (isSelectedPatient) {
            const stillActive = this.state.myActiveAlerts.find(
                a => a.patient_id[0] === this.state.selectedPatient.id
            );
            if (!stillActive) {
                if (this.charts.trend) { this.charts.trend.destroy(); this.charts.trend = null; }
                this.state.selectedPatient = null;
                this.state.vitals = {};
            } else {
                await this.fetchPatientData(this.state.selectedPatient.id);
            }
        }
    }

    onOpenPatientRecord() {
        if (this.state.selectedPatient) {
            this.action.doAction({
                type: 'ir.actions.act_window',
                res_model: 'health.patient',
                res_id: this.state.selectedPatient.id,
                views: [[false, 'form']],
                target: 'current'
            });
        }
    }

    openPatientForm(patientId) {
        this.action.doAction({
            type: 'ir.actions.act_window',
            res_model: 'health.patient',
            res_id: patientId,
            views: [[false, 'form']],
            target: 'current'
        });
    }

    openAlertForm(alertId) {
        this.action.doAction({
            type: 'ir.actions.act_window',
            res_model: 'health.alert',
            res_id: alertId,
            views: [[false, 'form']],
            target: 'current'
        });
    }

    // --- Data ---
    async fetchQueue() {
        try {
            const data = await this.orm.call("health.dashboard", "get_doctor_dashboard_data", []);
            this.wardIds = data.wardIds || [];
            this.state.wardName = data.wardName || 'Unassigned';
            this.state.unclaimedAlerts = data.unclaimedAlerts || [];
            this.state.myActiveAlerts = data.myActiveAlerts || [];
            this.state.activeCaseCount = data.activeCaseCount || 0;
            return;
        } catch (e) {
            console.error("Doctor queue fetch error:", e);
        }
    }


    async fetchPatientData(patientId) {
        try {
            const data = await this.orm.call("health.dashboard", "get_doctor_patient_panel_data", [patientId]);
            this.state.selectedPatient = data.selectedPatient || null;
            this.state.vitals = data.vitals || {};
            this.state.risk = data.risk || {};
            this.state.activeAlert = data.activeAlert || null;
            this.state.showVitalsChart = Boolean(data.showVitalsChart);
            this._patientVitals = data.trendVitals || [];
            setTimeout(() => this.renderTrendChart(), 300);
            return;
        } catch (e) {
            console.error("Patient data fetch error:", e);
        }
    }

    // --- Charts ---
    renderTrendChart() {
        if (!this.chartLoaded || !window.Chart || !this.trendChartRef.el) return;
        if (this.charts.trend) { this.charts.trend.destroy(); this.charts.trend = null; }

        const data = this._patientVitals || [];

        // Need at least 3 data points to show a meaningful trend
        if (data.length < 3) {
            this.state.showVitalsChart = false;
            return;
        }
        this.state.showVitalsChart = true;

        const labels = data.map(v => {
            if (!v.recorded_at) return '';
            const d = new Date(v.recorded_at.replace(' ', 'T') + 'Z');
            return d.getHours() + ':' + d.getMinutes().toString().padStart(2, '0');
        });

        const hrValues  = data.map(v => v.heart_rate  || null);
        const spo2Values = data.map(v => v.spo2        || null);
        const bpValues  = data.map(v => v.bp_systolic || null);
        const tempValues = data.map(v => v.temperature ? v.temperature * 10 : null); // scale x10 to fit same axis

        const makeDataset = (label, values, color, hidden) => ({
            label,
            data: values,
            borderColor: color,
            backgroundColor: color + '18',
            borderWidth: 2,
            pointRadius: 3,
            pointHoverRadius: 5,
            fill: false,
            tension: 0.4,
            spanGaps: true,
            hidden: hidden || false,
        });

        this.charts.trend = new Chart(this.trendChartRef.el, {
            type: 'line',
            data: {
                labels,
                datasets: [
                    makeDataset('HR (bpm)',    hrValues,   '#E24B4A', false),
                    makeDataset('SpO2 (%)',   spo2Values, '#185FA5', false),
                    makeDataset('BP Sys',     bpValues,   '#F59E0B', false),
                    makeDataset('Temp x10',   tempValues, '#16A34A', true),  // hidden by default
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: { mode: 'index', intersect: false },
                plugins: {
                    legend: {
                        display: true,
                        position: 'top',
                        align: 'end',
                        labels: {
                            boxWidth: 10,
                            boxHeight: 10,
                            font: { size: 10, family: 'Inter, system-ui' },
                            color: '#64748B',
                            padding: 10,
                        }
                    },
                    tooltip: {
                        callbacks: {
                            label: (ctx) => {
                                if (ctx.dataset.label === 'Temp x10') {
                                    return `Temp: ${(ctx.parsed.y / 10).toFixed(1)} C`;
                                }
                                return `${ctx.dataset.label}: ${ctx.parsed.y}`;
                            }
                        }
                    }
                },
                scales: {
                    x: {
                        grid: { display: false },
                        ticks: { color: '#94a3b8', font: { size: 10 } }
                    },
                    y: {
                        display: true,
                        beginAtZero: false,
                        grid: { color: '#F1F5F9' },
                        ticks: { color: '#94a3b8', font: { size: 10 }, maxTicksLimit: 5 }
                    }
                }
            }
        });
    }
}

DoctorDashboard.template = "health_monitoring.DoctorDashboardTemplate";
registry.category("actions").add("smartlab_doctor_dashboard", DoctorDashboard);
