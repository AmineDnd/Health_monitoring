env['ir.ui.view'].search([('model', 'in', ['health.alert', 'health.vitals', 'health.vital.record', 'health.patient'])]).unlink()
env.cr.commit()
print("Successfully deleted all custom module views to prepare for clean upgrade.")
