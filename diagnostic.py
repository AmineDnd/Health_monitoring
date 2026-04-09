print("\n--- DIAGNOSTIC ACCESS CHECK ---")
nurse_group = env.ref('health_monitoring.group_health_nurse')
nurse = env['res.users'].search([('login', '=', 'nurse@test.com')], limit=1)

if nurse:
    print(f"Found Nurse: {nurse.name} (ID: {nurse.id})")
    print("Groups:", [g.name for g in nurse.groups_id])
    print("Has Health Nurse Group explicitly?", nurse.has_group('health_monitoring.group_health_nurse'))
    
    nurse_env = env(user=nurse)
    
    can_create = nurse_env['health.patient'].check_access_rights('create', raise_exception=False)
    can_read = nurse_env['health.patient'].check_access_rights('read', raise_exception=False)
    
    print(f"health.patient -> Read: {can_read} | Create: {can_create}")
    print(f"health.patient.tag -> Read: {nurse_env['health.patient.tag'].check_access_rights('read', raise_exception=False)}")
    print(f"health.alert -> Read: {nurse_env['health.alert'].check_access_rights('read', raise_exception=False)}")
else:
    print("nurse@test.com NOT FOUND in this DB!")
print("--- DIAGNOSTIC END ---\n")
