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

            const active = await this.orm.searchRead("health.alert",
                [['state', '=', 'investigating'], ['assigned_doctor_id', '=', this.user.userId]],
                ['headline', 'severity', 'patient_id', 'create_date'],
                { order: 'create_date desc' });
            active.forEach(a => a.timeAgo = this.timeAgo(a.create_date));

            // Deduplicate by patient — one card per patient, keep most severe alert
            // Severity order: critical > high > warning > info/other
            const sevOrder = { critical: 4, high: 3, warning: 2, info: 1 };
            const dedupe = (alerts) => {
                const seen = new Map(); // patient_id → alert
                for (const a of alerts) {
                    const pid = Array.isArray(a.patient_id) ? a.patient_id[0] : a.patient_id;
                    if (!seen.has(pid)) {
                        seen.set(pid, a);
                    } else {
                        const existing = seen.get(pid);
                        const newSev  = sevOrder[a.severity]        || 0;
                        const exSev   = sevOrder[existing.severity]  || 0;
                        if (newSev > exSev) seen.set(pid, a); // replace with more severe
                    }
                }
                return Array.from(seen.values());
            };

            this.state.unclaimedAlerts = dedupe(unclaimed);
            this.state.myActiveAlerts  = dedupe(active);
            this.state.activeCaseCount = this.state.unclaimedAlerts.length + this.state.myActiveAlerts.length;
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
                ["heart_rate", "bp_systolic", "bp_diastolic", "spo2", "temperature", "respiratory_rate", "glucose", "recorded_at", "ai_score"],
                { limit: 20, order: 'recorded_at desc' });

            // Fetch active alert for this patient (most recent non-resolved)
            const patientAlerts = await this.orm.searchRead("health.alert",
                [['patient_id', '=', patientId], ['state', '!=', 'resolved']],
                ["headline", "severity", "create_date", "state"],
                { limit: 1, order: 'create_date desc' });
            this.state.activeAlert = patientAlerts.length > 0 ? {
                ...patientAlerts[0],
                timeAgo: this.timeAgo(patientAlerts[0].create_date),
            } : null;

            if (vitals.length > 0) {
                const latest = vitals[0];
                const hr = latest.heart_rate || 0;
                const bpSys = latest.bp_systolic || 0;
                const bpDia = latest.bp_diastolic || 0;
                const spo2 = latest.spo2 || 0;
                const temp = latest.temperature || 0;
                const rr = latest.respiratory_rate || 0;
                const glu = latest.glucose || 0;

                this.state.vitals = {
                    heart_rate: Math.round(hr),
                    bp_systolic: Math.round(bpSys),
                    bp_diastolic: Math.round(bpDia),
                    spo2: Math.round(spo2),
                    temperature: temp ? temp.toFixed(1) : 0,
                    respiratory_rate: Math.round(rr),
                    glucose: Math.round(glu),
                    ai_score: latest.ai_score ? Math.round(latest.ai_score) : null,
                    // Abnormal flags — clinically correct ranges
                    hr_abnormal: hr > 100 || hr < 60,
                    spo2_abnormal: spo2 < 94,
                    bp_abnormal: bpSys > 140 || bpSys < 90 || bpDia > 90 || bpDia < 60,
                    temp_abnormal: temp > 38.5 || temp < 35.5,
                    rr_abnormal: rr > 20 || rr < 12,
                    glucose_abnormal: glu > 200 || glu < 70,
                };

                // Risk factors — clinically meaningful deviation from normal ranges
                const riskColor = (v) => v > 60 ? '#F87171' : v > 30 ? '#FBBF24' : '#34D399';

                // Cardiac: deviation from 60-100 bpm range
                let cardiacRisk = 0;
                if (hr > 0) {
                    if (hr > 100) cardiacRisk = Math.min(100, (hr - 100) * 3);
                    else if (hr < 60) cardiacRisk = Math.min(100, (60 - hr) * 3);
                }

                // Respiratory: deviation from 12-20 breaths/min
                let respRisk = 0;
                if (rr > 0) {
                    if (rr > 20) respRisk = Math.min(100, (rr - 20) * 2);
                    else if (rr < 12) respRisk = Math.min(100, (12 - rr) * 5);
                }

                // Hypoxia: deviation below 95%
                const hypoxiaRisk = spo2 > 0 ? Math.min(100, Math.max(0, (95 - spo2) * 8)) : 0;

                // Blood Pressure: deviation from 90-140 systolic
                let bpRisk = 0;
                if (bpSys > 0) {
                    if (bpSys > 140) bpRisk = Math.min(100, (bpSys - 140) * 2);
                    else if (bpSys < 90) bpRisk = Math.min(100, (90 - bpSys) * 3);
                }

                // Thermoregulation: deviation from 36.1-38.0
                let thermoRisk = 0;
                if (temp > 0) {
                    if (temp > 38.0) thermoRisk = Math.min(100, (temp - 38.0) * 50);
                    else if (temp < 36.1) thermoRisk = Math.min(100, (36.1 - temp) * 50);
                }

                // Metabolic: glucose deviation from 70-200
                let metabolicRisk = 0;
                if (glu > 0) {
                    if (glu > 200) metabolicRisk = Math.min(100, (glu - 200) * 0.5);
                    else if (glu < 70) metabolicRisk = Math.min(100, (70 - glu) * 2);
                }

                this.state.risk = {
                    cardiac: cardiacRisk, cardiacColor: riskColor(cardiacRisk),
                    respiratory: respRisk, respiratoryColor: riskColor(respRisk),
                    hypoxia: hypoxiaRisk, hypoxiaColor: riskColor(hypoxiaRisk),
                    bloodPressure: bpRisk, bloodPressureColor: riskColor(bpRisk),
                    thermoregulation: thermoRisk, thermoregulationColor: riskColor(thermoRisk),
                    metabolic: metabolicRisk, metabolicColor: riskColor(metabolicRisk),
                };
            } else {
                this.state.vitals = {};
                this.state.activeAlert = null;
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
