alert = env['health.alert'].search([('patient_id.name', 'ilike', 'adin')], limit=1)
if alert:
    print("\n--- Diagnostic Dump ---")
    doc = alert.assigned_doctor_id or alert.doctor_id
    boss_group = env.ref('health_monitoring.group_health_admin', raise_if_not_found=False)
    boss_users = boss_group.users if boss_group else env['res.users']
    
    print(f"Alert ID: {alert.id} for Patient: {alert.patient_id.name}")
    print(f"Current Escalation Level: {alert.escalation_level}")
    print(f"Assigned Doctor: {doc.name if doc else 'NONE'}")
    if doc:
        print(f"-> Doctor Telegram ID value: '{doc.telegram_chat_id}'")
        
    print(f"\nAdministrator Count: {len(boss_users)}")
    for b in boss_users:
         print(f"-> Boss {b.name} Telegram ID value: '{b.telegram_chat_id}'")
         
    token = env['ir.config_parameter'].sudo().get_param('health_monitoring.telegram_bot_token')
    print(f"\nGlobal Bot Token value: '{token}'")
    print("--- End Dump ---\n")
else:
    print("\nPatient 'adin' not found!")
