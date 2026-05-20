/** @odoo-module **/

/**
 * vital_safety_check.js
 * Thresholds that require nurse confirmation before saving.
 * Values outside these ranges are so extreme they are likely entry errors.
 */

export const EXTREME_THRESHOLDS = {
    spo2: {
        min: 75,
        max: 100,
        label: 'SpO2',
        unit: '%',
        message: (val) => `SpO2 of ${val}% is extremely critical. Below 80% causes rapid organ damage. Please verify this reading with a pulse oximeter.`
    },
    heart_rate: {
        min: 35,
        max: 160,
        label: 'Heart Rate',
        unit: 'bpm',
        message: (val) => `Heart Rate of ${val} bpm is an extreme value. Please verify with the patient before saving.`
    },
    bp_systolic: {
        min: 70,
        max: 200,
        label: 'Systolic BP',
        unit: 'mmHg',
        message: (val) => `Systolic BP of ${val} mmHg is extremely abnormal. Please re-check with the patient.`
    },
    temperature: {
        min: 34.0,
        max: 41.0,
        label: 'Temperature',
        unit: 'C',
        message: (val) => `Temperature of ${val} C is life-threatening. Please verify this reading.`
    },
    respiratory_rate: {
        min: 6,
        max: 35,
        label: 'Respiratory Rate',
        unit: '/min',
        message: (val) => `Respiratory Rate of ${val}/min is an extreme value. Please verify.`
    },
    glucose: {
        min: 30,
        max: 500,
        label: 'Glucose',
        unit: 'mg/dL',
        message: (val) => `Glucose of ${val} mg/dL is a dangerous extreme. Please verify this reading.`
    }
};

/**
 * Checks vitals object against extreme thresholds.
 * Returns an array of warning objects for any fields outside extreme range.
 * @param {Object} vitals - object with numeric vital fields
 * @returns {Array} warnings - list of {field, value, label, unit, message}
 */
export function checkExtremeValues(vitals) {
    const warnings = [];
    for (const [field, config] of Object.entries(EXTREME_THRESHOLDS)) {
        const value = vitals[field];
        if (value !== null && value !== undefined && value !== 0) {
            if (value < config.min || value > config.max) {
                warnings.push({
                    field,
                    value,
                    label: config.label,
                    unit: config.unit,
                    message: config.message(value)
                });
            }
        }
    }
    return warnings;
}
