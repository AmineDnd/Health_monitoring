/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, onWillStart, onMounted, onWillDestroy, useState, useRef } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

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
            // Get user name
            const userRec = await this.orm.read("res.users", [this.user.userId], ["name"]);
            if (userRec.length > 0) {
                this.state.doctorName = userRec[0].name;
            }
            // Find ward via doctor_ids
            const myWards = await this.orm.searchRead("health.ward", [['doctor_ids', 'in', [this.user.userId]]], ["name", "id"], { limit: 1 });
            if (myWards.length > 0) {
                this.wardId = myWards[0].id;
                this.state.wardName = myWards[0].name;
            } else {
                const wards = await this.orm.searchRead("health.ward", [], ["name", "id"], { limit: 1 });
                if (wards.length > 0) {
                    this.wardId = wards[0].id;
                    this.state.wardName = wards[0].name;
                }
            }
            await this.fetchQueue();
        });

        onMounted(() => {
            document.addEventListener("keydown", this._handleKeyDown);
            this.refreshInterval = setInterval(() => {
                this.fetchQueue();
                if (this.state.selectedPatient) {
                    this.fetchPatientData(this.state.selectedPatient.id);
                }
            }, 15000);
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
        await this.fetchPatientData(alert.patient_id[0]);
        setTimeout(() => this.renderTrendChart(), 100);
    }

    async onClaimAlert(alertId) {
        try {
            await this.orm.call("health.alert", "action_claim_alert", [[alertId]]);
        } catch (e) {
            // Fallback: direct write if method name differs
            await this.orm.write("health.alert", [alertId], {
                assigned_doctor_id: this.user.userId,
                state: 'investigating'
            });
        }
        await this.fetchQueue();
    }

    async onResolveAlert(alertId) {
        await this.orm.call("health.alert", "action_resolve", [[alertId]]);
        await this.fetchQueue();
        if (this.state.selectedPatient) {
            await this.fetchPatientData(this.state.selectedPatient.id);
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
            // Filter unclaimed alerts to the doctor's ward when possible
            const unclaimedDomain = this.wardId
                ? [['state', '=', 'new'], ['assigned_doctor_id', '=', false], ['patient_id.ward_id', '=', this.wardId]]
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

                const riskColor = (v) => v > 60 ? '#F87171' : v > 30 ? '#FBBF24' : '#34D399';

                this.state.risk = {
                    arrhythmia: arrRisk, arrhythmiaColor: riskColor(arrRisk),
                    hypoxia: hypRisk, hypoxiaColor: riskColor(hypRisk),
                    hypertension: bpRisk, hypertensionColor: riskColor(bpRisk),
                    fever: feverRisk, feverColor: riskColor(feverRisk),
                };
            } else {
                this.state.vitals = {};
            }

            this._patientVitals = vitals.reverse();
            setTimeout(() => this.renderTrendChart(), 100);
        } catch (e) {
            console.error("Patient data fetch error:", e);
        }
    }

    // --- Charts ---
    renderTrendChart() {
        if (!window.Chart || !this.trendChartRef.el || !this._patientVitals || this._patientVitals.length === 0) return;
        if (this.charts.trend) this.charts.trend.destroy();

        const data = this._patientVitals;
        const labels = data.map(v => {
            if (!v.recorded_at) return '';
            const d = new Date(v.recorded_at.replace(' ', 'T') + 'Z');
            return d.getHours() + ':' + d.getMinutes().toString().padStart(2, '0');
        });
        const hrValues = data.map(v => v.heart_rate || 0);

        // Color each bar as a gradient based on index (old to new)
        const barColors = hrValues.map((v, i) => {
            const pct = i / Math.max(1, hrValues.length - 1);
            // blend #1E3A5F and #F87171
            const r = Math.round(30 + pct * (248 - 30));
            const g = Math.round(58 + pct * (113 - 58));
            const b = Math.round(95 + pct * (113 - 95));
            return `rgb(${r}, ${g}, ${b})`;
        });

        this.charts.trend = new Chart(this.trendChartRef.el, {
            type: 'bar',
            data: {
                labels,
                datasets: [{
                    data: hrValues,
                    backgroundColor: barColors,
                    borderRadius: 4,
                    borderSkipped: false,
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { display: false } },
                scales: {
                    x: { grid: { display: false }, ticks: { color: '#94a3b8', font: { size: 10 } } },
                    y: { display: false, beginAtZero: false }
                }
            }
        });
    }
}

DoctorDashboard.template = "health_monitoring.DoctorDashboardTemplate";
registry.category("actions").add("smartlab_doctor_dashboard", DoctorDashboard);
