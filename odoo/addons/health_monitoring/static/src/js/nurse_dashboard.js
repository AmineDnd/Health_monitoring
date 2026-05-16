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
            stats: { total: 0, upToDate: 0, dueSoon: 0, overdue: 0, critical: 0 },
            showHandoff: false,
            filterModal: { show: false, title: '', patients: [] },
        });

        onWillStart(async () => {
            await loadJS("https://cdn.jsdelivr.net/npm/chart.js");
            // Get user
            const userRec = await this.orm.read("res.users", [this.user.userId], ["name"]);
            if (userRec.length > 0) this.state.nurseName = userRec[0].name;
            // Nurse sees all wards by default, or we could add a ward selector later
            this.wardId = null;
            this.state.wardName = 'All Wards';
            await this.fetchData();
        });

        onMounted(() => {
            this.interval = setInterval(() => this.fetchData(), 30000);  // 30s auto-refresh
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
            target: 'new',
        }, {
            onClose: () => this.fetchData(),
        });
    }

    onOpenPatient(patientId) {
        // Open patient profile in a dialog so nurse stays on the dashboard
        this.action.doAction({
            type: 'ir.actions.act_window',
            res_model: 'health.patient',
            res_id: patientId,
            views: [[false, 'form']],
            target: 'new',
        }, {
            onClose: () => this.fetchData(),
        });
    }

    onOpenHandoffModal() {
        this.action.doAction({
            type: 'ir.actions.act_window',
            res_model: 'health.handoff',
            views: [[false, 'form']],
            target: 'new',
        });
    }

    onCloseHandoffModal() {
        this.state.showHandoff = false;
    }

    // --- KPI filter modal ---
    onFilterCritical() {
        const filtered = this.state.patients.filter(p => p.risk_level === 'critical');
        this.state.filterModal = { show: true, title: 'Critical Patients', patients: filtered };
    }

    onFilterOverdue() {
        const filtered = this.state.patients.filter(p => p.vitalsStatus === 'overdue');
        this.state.filterModal = { show: true, title: 'Overdue Patients', patients: filtered };
    }

    onFilterDueSoon() {
        const filtered = this.state.patients.filter(p => p.vitalsStatus === 'due_soon');
        this.state.filterModal = { show: true, title: 'Due Soon', patients: filtered };
    }

    onFilterUpToDate() {
        const filtered = this.state.patients.filter(p => p.vitalsStatus === 'up_to_date');
        this.state.filterModal = { show: true, title: 'Up to Date', patients: filtered };
    }

    onCloseFilterModal() {
        this.state.filterModal = { show: false, title: '', patients: [] };
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
            // Show all admitted or triage patients (not just 'active' which requires doctor validation)
            const domain = [['admission_status', 'in', ['triage', 'admitted']]];

            const patients = await this.orm.searchRead("health.patient", domain,
                ["id", "name", "admission_status", "risk_level", "age", "gender", "vitals_frequency_hours"]);

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
                    ["id", "headline", "create_date", "severity", "patient_id"],
                    { limit: 20, order: "create_date desc" });
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
                    
                    const freq = p.vitals_frequency_hours || 4; // Default to 4h if missing
                    const soonThreshold = Math.max(freq - 1, freq * 0.75); // Due soon 1 hr before or at 75% of time

                    if (hours >= freq) status = 'overdue';
                    else if (hours >= soonThreshold) status = 'due_soon';
                    else status = 'up_to_date';
                }

                if (p.risk_level === 'critical') critical++;
                else if (status === 'overdue') overdue++;
                else if (status === 'due_soon') due++;
                else stable++;

                // Build composite latest vitals to handle partial submissions
                let cHR = null, cSpO2 = null, cBpSys = null, cBpDia = null, cTemp = null;
                for (const v of pv) {
                    if (cHR === null && v.heart_rate) cHR = v.heart_rate;
                    if (cSpO2 === null && v.spo2) cSpO2 = v.spo2;
                    if (cBpSys === null && v.bp_systolic) cBpSys = v.bp_systolic;
                    if (cBpDia === null && v.bp_diastolic) cBpDia = v.bp_diastolic;
                    if (cTemp === null && v.temperature) cTemp = v.temperature;
                }

                const hrAbnormal  = cHR ? (cHR > 100 || cHR < 60) : false;
                const hrWarn      = !hrAbnormal && cHR ? (cHR > 90 || cHR < 65) : false;
                const spo2Abnormal = cSpO2 ? (cSpO2 < 90) : false;
                const spo2Warn    = !spo2Abnormal && cSpO2 ? (cSpO2 < 95) : false;
                const bpAbnormal  = cBpSys ? (cBpSys > 140 || cBpSys < 90) : false;
                const bpWarn      = !bpAbnormal && cBpSys ? (cBpSys > 130) : false;
                const bpLow       = cBpSys ? (cBpSys < 90) : false;
                const bpEqual     = (cBpSys && cBpDia) ? (Math.abs(cBpSys - cBpDia) < 5) : false;
                const tempAbnormal= cTemp ? (cTemp > 38.5 || cTemp < 35.5) : false;

                let timeSince = 'No vitals';
                if (hours < 1) timeSince = `${Math.round(hours * 60)}min since vitals`;
                else if (hours < 999) timeSince = `${hours.toFixed(1)}h since vitals`;

                // Due label for schedule
                let dueLabel = '';
                let statusLabel = '';
                const freq = p.vitals_frequency_hours || 4;
                if (status === 'overdue') {
                    statusLabel = `${(hours - freq).toFixed(0)}h overdue`;
                    dueLabel = `Was due ${(hours - freq).toFixed(0)}h ago`;
                } else if (status === 'due_soon') {
                    statusLabel = 'Due in ' + Math.round((freq - hours) * 60) + 'min';
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
                    latestHR: pv.length > 0 ? (cHR ? Math.round(cHR) : '--') : null,
                    latestSpO2: pv.length > 0 ? (cSpO2 ? Math.round(cSpO2) : '--') : null,
                    latestBP: pv.length > 0 ? ((cBpSys && cBpDia) ? `${Math.round(cBpSys)}/${Math.round(cBpDia)}` : '--/--') : null,
                    latestTemp: pv.length > 0 ? (cTemp ? cTemp.toFixed(1) : '--') : null,
                    rawBpSys: cBpSys,
                    rawBpDia: cBpDia,
                    rawTemp: cTemp,
                    hrAbnormal, hrWarn,
                    spo2Abnormal, spo2Warn,
                    bpAbnormal, bpWarn, bpLow, bpEqual,
                    tempAbnormal,
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

            // Store all processed patients — used by filter modal
            this.state.patients = processed;

            this.state.stats = {
                total: patients.length,
                upToDate: stable,
                dueSoon: due, overdue, critical,
            };

            // Schedule: overdue + due_soon + patients with no vitals at all
            this.state.schedule = processed
                .filter(p => p.vitalsStatus === 'overdue' || p.vitalsStatus === 'due_soon')
                .sort((a, b) => {
                    if (a.vitalsStatus === 'overdue' && b.vitalsStatus !== 'overdue') return -1;
                    if (b.vitalsStatus === 'overdue' && a.vitalsStatus !== 'overdue') return 1;
                    return b.hoursSort - a.hoursSort;
                })
                .slice(0, 8);

            // Handoff list: high-risk + critical patients
            this.state.handoffList = processed
                .filter(p => p.risk_level === 'critical' || p.risk_level === 'high')
                .slice(0, 15);

            // Activity Feed — cross-reference vitals with alerts to show real status
            const feed = [];

            // Build a map: patient_id → list of alerts
            const patientAlertMap = {};
            alerts.forEach(a => {
                if (!a.patient_id) return;
                const pid = Array.isArray(a.patient_id) ? a.patient_id[0] : a.patient_id;
                if (!patientAlertMap[pid]) patientAlertMap[pid] = [];
                patientAlertMap[pid].push(a);
            });

            // Alert entries
            alerts.forEach(a => {
                if (!a.create_date) return;
                const sevLabel = (a.severity || 'alert').toUpperCase();
                const icon = a.severity === 'critical' ? '🚨' : a.severity === 'warning' ? '⚠️' : '🔔';
                feed.push({
                    id: `a${a.id}`, type: 'alert',
                    text: `${icon} ${sevLabel}: ${a.headline || 'Anomaly detected'}`,
                    timeAgo: this.timeAgo(a.create_date),
                    timeSort: new Date(a.create_date.replace(' ', 'T') + 'Z').getTime()
                });
            });

            // Vitals entries — look for a matching alert within 5 minutes of the vital
            vitals.slice(0, 8).forEach(v => {
                if (!v.recorded_at) return;
                const pid = Array.isArray(v.patient_id) ? v.patient_id[0] : v.patient_id;
                const pName = patients.find(p => p.id === pid)?.name || 'Patient';
                const vTime = new Date(v.recorded_at.replace(' ', 'T') + 'Z').getTime();

                // Find closest alert for this patient within 5 min of the vital
                const patAlerts = patientAlertMap[pid] || [];
                const nearAlert = patAlerts.find(a => {
                    if (!a.create_date) return false;
                    const aTime = new Date(a.create_date.replace(' ', 'T') + 'Z').getTime();
                    return Math.abs(aTime - vTime) < 5 * 60 * 1000;
                });

                let statusText, feedType;
                if (nearAlert) {
                    const sev = (nearAlert.severity || 'alert').toUpperCase();
                    statusText = `${sev} alert triggered`;
                    feedType = 'alert';
                } else {
                    statusText = 'Values within normal range';
                    feedType = 'vitals';
                }

                feed.push({
                    id: `v${v.id}`, type: feedType,
                    text: `Vitals logged — ${pName}. ${statusText}`,
                    timeAgo: this.timeAgo(v.recorded_at),
                    timeSort: vTime
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
            const lineColor = patient.vitalsStatus === 'overdue' ? '#E24B4A' : (patient.vitalsStatus === 'due_soon' ? '#F59E0B' : '#16A34A');

            this.sparklineInstances[patient.id] = new Chart(canvas, {
                type: 'line',
                data: {
                    labels: hrData.map(() => ''),
                    datasets: [{
                        data: hrData,
                        borderColor: lineColor,
                        backgroundColor: lineColor + '18',
                        borderWidth: 1.5,
                        pointRadius: 0,
                        fill: true,
                        tension: 0.4,
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
