/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, onWillStart, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

import { AdminDashboard } from "@health_monitoring/js/admin_dashboard";
import { DoctorDashboard } from "@health_monitoring/js/doctor_dashboard";
import { NurseDashboard } from "@health_monitoring/js/nurse_dashboard";

export class DashboardRouter extends Component {
    setup() {
        this.user = useService("user");
        this.state = useState({
            activeComponent: null,
            loading: true
        });

        onWillStart(async () => {
            const isAdmin = await this.user.hasGroup("health_monitoring.group_health_admin");
            const isDoctor = await this.user.hasGroup("health_monitoring.group_health_doctor");
            const isNurse = await this.user.hasGroup("health_monitoring.group_health_nurse");

            if (isAdmin) {
                this.state.activeComponent = AdminDashboard;
            } else if (isDoctor) {
                this.state.activeComponent = DoctorDashboard;
            } else if (isNurse) {
                this.state.activeComponent = NurseDashboard;
            }
            this.state.loading = false;
        });
    }
}

DashboardRouter.template = "health_monitoring.DashboardRouterTemplate";
registry.category("actions").add("smartlab_dashboard_router", DashboardRouter);
