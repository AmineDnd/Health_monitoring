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

        this.trendChartRef = useRef("trendChart");
        this.charts = {};

        this.state = useState({
            doctorName: '',
            wardName: 'Unassigned',
            activeCaseCount: 0,
            unclaimedAlerts: [],
            myActiveAlerts: [],
            selectedPatient: null,
            vitals: {},
            risk: {
                arrhythmia: 0, arrhythmiaColor: '#10b981',
                hypoxia: 0, hypoxiaColor: '#10b981',
                hypertension: 0, hypertensionColor: '#10b981',
                fever: 0, feverColor: '#10b981',
            },
        });

        this._handleKeyDown = this.handleKeyDown.bind(this);

        onWillStart(async () => {
            // Load Chart.js first
            await loadJS("https://cdn.jsdelivr.net/npm/chart.js");
            // Get user name
            const userRec = await this.orm.read("res.users", [this.user.userId], ["name"]);
            if (userRec.length > 0) {
                this.state.doctorName = userRec[0].name;
            }
            // Find ALL wards this doctor belongs to (no limit:1 — a doctor can cover multiple wards)
            const myWards = await this.orm.searchRead("health.ward", [['doctor_ids', 'in', [this.user.userId]]], ["name", "id"]);
            if (myWards.length > 0) {
                this.wardIds = myWards.map(w => w.id);         // ALL ward IDs
                this.wardId  = myWards[0].id;                  // primary (for display)
                this.state.wardName = myWards.map(w => w.name).join(', ');
            } else {
                // Fallback: if not assigned to any ward, load the first available ward
                const wards = await this.orm.searchRead("health.ward", [], ["name", "id"], { limit: 1 });
                if (wards.length > 0) {
                    this.wardIds = [wards[0].id];
                    this.wardId  = wards[0].id;
                    this.state.wardName = wards[0].name;
                }
            }
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
            // Fallback: direct write if method name differs
            await this.orm.write("health.alert", [alertId], {
                assigned_doctor_id: this.user.userId,
                state: 'investigating'
            });
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
        // check if they still have active alerts — if not, clear the panel
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
            // Use ALL ward IDs the doctor belongs to (wardIds array)
            const unclaimedDomain = (this.wardIds && this.wardIds.length > 0)
                ? [['state', '=', 'new'], ['assigned_doctor_id', '=', false], ['patient_id.ward_id', 'in', this.wardIds]]
                : [['state', '=', 'new'], ['assigned_doctor_id', '=', false]];

            const unclaimed = await this.orm.searchRead("health.alert",
                unclaimedDomain,
                ['headline', 'severity', 'patient_id', 'create_date'],
                { order: 'create_date desc', limit: 50 });
            unclaimed.forEach(a => a.timeAgo = this.timeAgo(a.create_date));
            this.state.unclaimedAlerts = unclaimed;

            const active = await this.orm.searchRead("health.alert",
                [['state', '=', 'investigating'], ['assigned_doctor_id', '=', this.user.userId]],
                ['headline', 'severity', 'patient_id', 'create_date'],
                { order: 'create_date desc' });
            active.forEach(a => a.timeAgo = this.timeAgo(a.create_date));
            this.state.myActiveAlerts = active;

            this.state.activeCaseCount = unclaimed.length + active.length;
        } catch (e) {
            console.error("Doctor queue fetch error:", e);
        }
    }

    async fetchPatientData(patientId) {
        try {
            const pRec = await this.orm.read("health.patient", [patientId], ["name", "age", "gender", "admission_status", "risk_level"]);
            if (pRec.length > 0) {
                const p = pRec[0];
                p.initials = p.name.split(' ').map(n => n[0]).join('').substring(0, 2).toUpperCase();
                // Sanitize risk_level — only allow known values
                const validLevels = ['low', 'medium', 'high', 'critical'];
                if (!validLevels.includes(p.risk_level)) {
                    p.risk_level = 'low';
                }
                this.state.selectedPatient = p;
            }

            // Vitals
            const vitals = await this.orm.searchRead("health.vital.record",
                [['patient_id', '=', patientId]],
                ["heart_rate", "bp_systolic", "bp_diastolic", "spo2", "temperature", "recorded_at"],
                { limit: 20, order: 'recorded_at desc' });

            if (vitals.length > 0) {
                const latest = vitals[0];
                this.state.vitals = {
                    heart_rate: Math.round(latest.heart_rate) || 0,
                    bp_systolic: Math.round(latest.bp_systolic) || 0,
                    bp_diastolic: Math.round(latest.bp_diastolic) || 0,
                    spo2: Math.round(latest.spo2) || 0,
                    temperature: latest.temperature ? latest.temperature.toFixed(1) : 0,
                    hr_abnormal: latest.heart_rate > 100 || latest.heart_rate < 60,
                    spo2_abnormal: latest.spo2 < 94,
                    bp_abnormal: latest.bp_systolic > 140,
                    temp_abnormal: latest.temperature > 38.5,
                };

                // Risk factors as percentages (0-100)
                const hr = latest.heart_rate || 70;
                const spo2 = latest.spo2 || 98;
                const bp = latest.bp_systolic || 120;
                const temp = latest.temperature || 37;

                const arrRisk = Math.min(100, Math.max(0, Math.abs(hr - 75) * 2));
                const hypRisk = Math.min(100, Math.max(0, (100 - spo2) * 10));
                const bpRisk = Math.min(100, Math.max(0, (bp - 120) * 2));
                const feverRisk = Math.min(100, Math.max(0, (temp - 37) * 40));

                const bradyRisk = Math.min(100, Math.max(0, hr < 60 ? (60 - hr) * 3 : 0));

                const riskColor = (v) => v > 60 ? '#F87171' : v > 30 ? '#FBBF24' : '#34D399';

                this.state.risk = {
                    arrhythmia: arrRisk, arrhythmiaColor: riskColor(arrRisk),
                    hypoxia: hypRisk, hypoxiaColor: riskColor(hypRisk),
                    hypertension: bpRisk, hypertensionColor: riskColor(bpRisk),
                    fever: feverRisk, feverColor: riskColor(feverRisk),
                    bradycardia: bradyRisk, bradycardiaColor: riskColor(bradyRisk),
                };
            } else {
                this.state.vitals = {};
            }

            this._patientVitals = vitals.reverse();
            setTimeout(() => this.renderTrendChart(), 300);
        } catch (e) {
            console.error("Patient data fetch error:", e);
        }
    }

    // --- Charts ---
    renderTrendChart() {
        if (!window.Chart || !this.trendChartRef.el) return;
        if (this.charts.trend) { this.charts.trend.destroy(); this.charts.trend = null; }

        const data = this._patientVitals || [];

        if (data.length === 0) {
            // Draw empty state message on canvas
            const canvas = this.trendChartRef.el;
            const ctx = canvas.getContext('2d');
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            ctx.fillStyle = '#94A3B8';
            ctx.font = '12px Inter, system-ui';
            ctx.textAlign = 'center';
            ctx.fillText('No vitals recorded yet', canvas.width / 2, canvas.height / 2);
            return;
        }

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
                    makeDataset('SpO₂ (%)',   spo2Values, '#185FA5', false),
                    makeDataset('BP Sys',     bpValues,   '#F59E0B', false),
                    makeDataset('Temp ×10',   tempValues, '#16A34A', true),  // hidden by default
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
                                if (ctx.dataset.label === 'Temp ×10') {
                                    return `Temp: ${(ctx.parsed.y / 10).toFixed(1)}°C`;
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
