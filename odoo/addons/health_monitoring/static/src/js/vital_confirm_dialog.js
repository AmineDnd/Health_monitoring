/** @odoo-module **/

import { Component, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

/**
 * VitalConfirmDialog
 *
 * OWL client action shown when a nurse tries to save vital values that are
 * outside the extreme safety thresholds. The nurse must explicitly confirm
 * that the values are real before the record is saved and AI analysis runs.
 *
 * Registered as client action tag: "smartlab_confirm_vitals"
 */
class VitalConfirmDialog extends Component {
    static template = "health_monitoring.VitalConfirmDialog";

    setup() {
        this.action = useService("action");
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.state = useState({
            loading: false,
        });
        // params are passed from the Python action_check_and_save return value
        this.params = this.props.action.params || {};
    }

    async onConfirm() {
        // Nurse confirmed the values are real — proceed with save
        this.state.loading = true;
        try {
            await this.orm.call(
                'health.vital.record',
                'action_manual_save_close',
                [[this.params.record_id]],
                { context: { extreme_confirmed: true } }
            );
            this.notification.add(
                "Record saved. Doctors in the ward have been notified.",
                { type: 'warning', title: 'Extreme values saved', sticky: false }
            );
            // Close the dialog
            this.action.doAction({ type: 'ir.actions.act_window_close' });
        } catch (e) {
            console.error('Vital save failed:', e);
            this.notification.add("Failed to save record. Please try again.", { type: 'danger' });
        }
        this.state.loading = false;
    }

    onReEnter() {
        // Nurse wants to fix the values — close the dialog, form stays open
        this.action.doAction({ type: 'ir.actions.act_window_close' });
    }
}

VitalConfirmDialog.template = "health_monitoring.VitalConfirmDialog";
registry.category("actions").add("smartlab_confirm_vitals", VitalConfirmDialog);
