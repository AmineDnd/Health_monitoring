/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, onWillStart, onMounted, onWillDestroy, useState, useRef } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { loadJS } from "@web/core/assets";

export class NurseDashboard extends Component {
    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.user = useService("user");

        this.sparklineInstances = {};
        this.prevCriticalCount = undefined;
        this.prevOverdueCount = undefined;

        this.state = useState({
            nurseName: '',
            wardName: 'Loading...',
            currentTime: new Date().toLocaleTimeString(),
            shiftInfo: this._getShift(),
            patients: [],
            schedule: [],
            activityFeed: [],
            handoffList: [],
            stats: { total: 0, stable: 0, dueSoon: 0, overdue: 0, critical: 0 },
            showHandoff: false,
        });

        onWillStart(async () => {
            await loadJS("https://cdn.jsdelivr.net/npm/chart.js");
            // Get user
            const userRec = await this.orm.read("res.users", [this.user.userId], ["name"]);
            if (userRec.length > 0) this.state.nurseName = userRec[0].name;
            // Find ward
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
            await this.fetchData();
        });

        onMounted(() => {
            this.interval = setInterval(() => this.fetchData(), 60000);
            this.clockInterval = setInterval(() => {
                this.state.currentTime = new Date().toLocaleTimeString();
            }, 1000);
        });

        onWillDestroy(() => {
            if (this.interval) clearInterval(this.interval);
            if (this.clockInterval) clearInterval(this.clockInterval);
            Object.values(this.sparklineInstances).forEach(c => c && c.destroy());
        });
    }

    _getShift() {
        const h = new Date().getHours();
        if (h < 12) return 'Morning';
        if (h < 18) return 'Afternoon';
        return 'Night';
    }

    timeAgo(dateStr) {
        if (!dateStr) return '';
        const past = new Date(dateStr.replace(' ', 'T') + 'Z');
        const diffMins = Math.floor((new Date() - past) / 60000);
        if (diffMins < 1) return 'Just now';
        if (diffMins < 60) return `${diffMins} min ago`;
        const diffHrs = Math.floor(diffMins / 60);
        if (diffHrs < 24) return `${diffHrs}h ago`;
        return `${Math.floor(diffHrs / 24)}d ago`;
    }

    // --- Actions ---
    async onRefresh() {
        await this.fetchData();
    }

    onLogVitals(id) {
        this.action.doAction({
            type: 'ir.actions.act_window',
            res_model: 'health.vital.record',
            views: [[false, 'form']],
            context: { default_patient_id: id },
            target: 'new'
        });
    }

    onOpenHandoffModal() {
        this.state.handoffList = this.state.patients.filter(p => p.risk_level === 'high' || p.risk_level === 'critical');
        this.state.showHandoff = true;
    }

    onCloseHandoffModal() {
        this.state.showHandoff = false;
    }

    onExportCSV() {
        const rows = [["Patient", "Risk", "HR", "SpO2", "BP", "Temp", "Last Check"]];
        this.state.handoffList.forEach(p => {
            rows.push([
                `"${p.name}"`, p.risk_level,
                p.latestHR || '', p.latestSpO2 || '', p.latestBP || '', p.latestTemp || '',
                `"${p.timeSinceVitals}"`
            ]);
        });
        const csv = rows.map(r => r.join(",")).join("\n");
        const blob = new Blob([csv], { type: 'text/csv' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `handoff_${Date.now()}.csv`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    }

    onPrintHandoff() {
        window.print();
    }

    async onMarkAllStable() {
        const stables = this.state.patients.filter(p => {
            return p.vitalsStatus === 'up_to_date' && p.risk_level !== 'critical' && p.risk_level !== 'high' && p.latestHR;
        });
        for (const p of stables) {
            await this.orm.create("health.vital.record", [{
                patient_id: p.id,
                heart_rate: p.latestHR,
                bp_systolic: p.rawBpSys || 120,
                bp_diastolic: p.rawBpDia || 80,
                spo2: p.latestSpO2 || 98,
                temperature: p.rawTemp || 37,
            }]);
        }
        await this.fetchData();
    }

    playAlertSound() {
        if (!document.hasFocus()) return;
        try {
            const AC = window.AudioContext || window.webkitAudioContext;
            if (!AC) return;
            const ctx = new AC();
            const osc = ctx.createOscillator();
            const gain = ctx.createGain();
            osc.connect(gain);
            gain.connect(ctx.destination);
            osc.type = "sine";
            osc.frequency.setValueAtTime(880, ctx.currentTime);
            gain.gain.setValueAtTime(0, ctx.currentTime);
            gain.gain.linearRampToValueAtTime(0.5, ctx.currentTime + 0.05);
            gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.4);
            osc.start(ctx.currentTime);
            osc.stop(ctx.currentTime + 0.4);
        } catch (e) { /* ignore */ }
    }

    // --- Data ---
    async fetchData() {
        try {
            const domain = [['status', '=', 'active']];
            if (this.wardId) domain.push(['ward_id', '=', this.wardId]);

            const patients = await this.orm.searchRead("health.patient", domain,
                ["id", "name", "admission_status", "risk_level", "age", "gender"]);

            const patientIds = patients.map(p => p.id);
            let vitals = [];
            let alerts = [];

            if (patientIds.length > 0) {
                vitals = await this.orm.searchRead("health.vital.record",
                    [['patient_id', 'in', patientIds]],
                    ["id", "patient_id", "recorded_at", "heart_rate", "bp_systolic", "bp_diastolic", "spo2", "temperature"],
                    { order: "recorded_at desc" });
                alerts = await this.orm.searchRead("health.alert",
                    [['patient_id', 'in', patientIds]],
                    ["id", "headline", "create_date", "severity"],
                    { limit: 10, order: "create_date desc" });
            }

            const vitalsByPatient = {};
            for (const v of vitals) {
                const pid = v.patient_id[0];
                if (!vitalsByPatient[pid]) vitalsByPatient[pid] = [];
                vitalsByPatient[pid].push(v);
            }

            let stable = 0, due = 0, overdue = 0, critical = 0;
            const now = new Date();

            const processed = patients.map(p => {
                const pv = vitalsByPatient[p.id] || [];
                const latest = pv[0];
                let status = 'overdue';
                let hours = 999;

                if (latest && latest.recorded_at) {
                    const recDate = new Date(latest.recorded_at.replace(' ', 'T') + 'Z');
                    hours = (now - recDate) / (1000 * 60 * 60);
                    if (hours >= 2) status = 'overdue';
                    else if (hours >= 1) status = 'due_soon';
                    else status = 'up_to_date';
                }

                if (p.risk_level === 'critical' || p.risk_level === 'high') critical++;
                else if (status === 'overdue') overdue++;
                else if (status === 'due_soon') due++;
                else stable++;

                const hrAbnormal  = latest ? (latest.heart_rate > 100 || latest.heart_rate < 60) : false;
                const hrWarn      = !hrAbnormal && latest ? (latest.heart_rate > 90 || latest.heart_rate < 65) : false;
                const spo2Abnormal = latest ? (latest.spo2 < 90) : false;
                const spo2Warn    = !spo2Abnormal && latest ? (latest.spo2 < 95) : false;
                const bpAbnormal  = latest ? (latest.bp_systolic > 140 || latest.bp_systolic < 90) : false;
                const bpWarn      = !bpAbnormal && latest ? (latest.bp_systolic > 130) : false;

                let timeSince = 'No vitals';
                if (hours < 1) timeSince = `${Math.round(hours * 60)}min since vitals`;
                else if (hours < 999) timeSince = `${hours.toFixed(1)}h since vitals`;

                // Due label for schedule
                let dueLabel = '';
                let statusLabel = '';
                if (status === 'overdue') {
                    statusLabel = `${hours.toFixed(0)}h overdue`;
                    dueLabel = 'Was due ' + Math.round(hours) + 'h ago';
                } else if (status === 'due_soon') {
                    statusLabel = 'Due in ' + Math.round((2 - hours) * 60) + 'min';
                    dueLabel = statusLabel;
                } else {
                    statusLabel = 'Next check';
                    dueLabel = 'Next check';
                }

                return {
                    ...p,
                    vitalsStatus: status,
                    timeSinceVitals: timeSince,
                    statusLabel,
                    dueLabel,
                    hoursSort: hours,
                    latestHR: latest ? Math.round(latest.heart_rate) : null,
                    latestSpO2: latest ? Math.round(latest.spo2) : null,
                    latestBP: latest ? `${Math.round(latest.bp_systolic)}/${Math.round(latest.bp_diastolic)}` : null,
                    latestTemp: latest ? latest.temperature?.toFixed(1) : null,
                    rawBpSys: latest ? latest.bp_systolic : null,
                    rawBpDia: latest ? latest.bp_diastolic : null,
                    rawTemp: latest ? latest.temperature : null,
                    hrAbnormal, hrWarn,
                    spo2Abnormal, spo2Warn,
                    bpAbnormal, bpWarn,
                    recentVitals: pv.slice(0, 5).reverse()
                };
            });

            processed.sort((a, b) => {
                if (a.risk_level === 'critical' && b.risk_level !== 'critical') return -1;
                if (b.risk_level === 'critical' && a.risk_level !== 'critical') return 1;
                if (a.vitalsStatus === 'overdue' && b.vitalsStatus !== 'overdue') return -1;
                if (b.vitalsStatus === 'overdue' && a.vitalsStatus !== 'overdue') return 1;
                return b.hoursSort - a.hoursSort;
            });

            this.state.patients = processed;
            this.state.stats = { total: patients.length, stable, ok: stable, dueSoon: due, overdue, critical };
            this.state.schedule = processed.filter(p => p.vitalsStatus !== 'up_to_date').slice(0, 6);

            // Activity Feed
            const feed = [];
            alerts.forEach(a => {
                if (!a.create_date) return;
                feed.push({
                    id: `a${a.id}`, type: 'alert',
                    text: `AI alert: ${a.headline || 'Anomaly'} — ${a.severity}`,
                    timeAgo: this.timeAgo(a.create_date),
                    timeSort: new Date(a.create_date.replace(' ', 'T') + 'Z').getTime()
                });
            });
            vitals.slice(0, 5).forEach(v => {
                if (!v.recorded_at) return;
                const pName = patients.find(p => p.id === v.patient_id[0])?.name || 'Patient';
                feed.push({
                    id: `v${v.id}`, type: 'vitals',
                    text: `Vitals logged — ${pName}. All normal`,
                    timeAgo: this.timeAgo(v.recorded_at),
                    timeSort: new Date(v.recorded_at.replace(' ', 'T') + 'Z').getTime()
                });
            });
            this.state.activityFeed = feed.sort((a, b) => b.timeSort - a.timeSort).slice(0, 8);

            // Audio alert
            if (this.prevCriticalCount !== undefined && critical > this.prevCriticalCount) this.playAlertSound();
            else if (this.prevOverdueCount !== undefined && overdue > this.prevOverdueCount) this.playAlertSound();
            this.prevCriticalCount = critical;
            this.prevOverdueCount = overdue;

            setTimeout(() => this.renderSparklines(), 80);
        } catch (e) {
            console.error("Nurse dashboard fetch error:", e);
        }
    }

    renderSparklines() {
        if (!window.Chart) return;
        for (const patient of this.state.patients) {
            const canvas = document.getElementById(`sparkline_${patient.id}`);
            if (!canvas) continue;
            // Fix canvas height to prevent solid-block rendering
            canvas.width = canvas.parentElement ? (canvas.parentElement.clientWidth || 200) : 200;
            canvas.height = 36;
            canvas.style.height = '36px';
            if (this.sparklineInstances[patient.id]) {
                this.sparklineInstances[patient.id].destroy();
            }
            if (!patient.recentVitals || patient.recentVitals.length === 0) continue;

            const hrData = patient.recentVitals.map(v => v.heart_rate || 0);
            // Color bars based on value
            const colors = hrData.map(v => {
                if (v > 100 || v < 55) return '#ef4444';
                if (v > 90 || v < 60) return '#f59e0b';
                return patient.vitalsStatus === 'overdue' ? '#ef4444' : (patient.vitalsStatus === 'due_soon' ? '#f59e0b' : '#10b981');
            });

            this.sparklineInstances[patient.id] = new Chart(canvas, {
                type: 'bar',
                data: {
                    labels: hrData.map(() => ''),
                    datasets: [{
                        data: hrData,
                        backgroundColor: colors,
                        borderRadius: 3,
                        borderSkipped: false,
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: { legend: { display: false }, tooltip: { enabled: false } },
                    scales: {
                        x: { display: false },
                        y: { display: false, min: Math.min(...hrData) - 15, max: Math.max(...hrData) + 10 }
                    },
                    layout: { padding: { top: 2, bottom: 2 } }
                }
            });
        }
    }
}

NurseDashboard.template = "health_monitoring.NurseDashboardTemplate";
registry.category("actions").add("smartlab_nurse_dashboard", NurseDashboard);
