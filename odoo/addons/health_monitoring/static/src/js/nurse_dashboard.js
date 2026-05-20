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
        this.chartLoaded = false;

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
            statusPatientIds: { total: [], critical: [], overdue: [], due_soon: [], up_to_date: [] },
            showHandoff: false,
            filterModal: { show: false, title: '', patients: [] },
        });

        onWillStart(async () => {
            try {
                await loadJS("https://cdn.jsdelivr.net/npm/chart.js");
                this.chartLoaded = Boolean(window.Chart);
            } catch (e) {
                console.warn("Chart.js load failed; nurse dashboard will continue without sparklines.", e);
            }
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

    async onOpenKpi(kpi) {
        const action = await this.orm.call("health.dashboard", "get_nurse_kpi_action", [kpi]);
        this.action.doAction(action, {
            onClose: () => this.fetchData(),
        });
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
            const data = await this.orm.call("health.dashboard", "get_nurse_dashboard_data", []);

            this.state.wardName = data.wardName || 'All Wards';
            this.state.patients = data.patients || [];
            this.state.stats = data.stats || { total: 0, upToDate: 0, dueSoon: 0, overdue: 0, critical: 0 };
            this.state.statusPatientIds = data.statusPatientIds || { total: [], critical: [], overdue: [], due_soon: [], up_to_date: [] };
            this.state.schedule = data.schedule || [];
            this.state.handoffList = data.handoffList || [];
            this.state.activityFeed = data.activityFeed || [];

            if (this.prevCriticalCount !== undefined && this.state.stats.critical > this.prevCriticalCount) this.playAlertSound();
            else if (this.prevOverdueCount !== undefined && this.state.stats.overdue > this.prevOverdueCount) this.playAlertSound();
            this.prevCriticalCount = this.state.stats.critical;
            this.prevOverdueCount = this.state.stats.overdue;

            setTimeout(() => this.renderSparklines(), 80);
            return;
        } catch (e) {
            console.error("Nurse dashboard fetch error:", e);
        }
    }

    renderSparklines() {
        if (!this.chartLoaded || !window.Chart) return;
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
