import sys

print("\n==================================")
print("=== SYSTEM CLEANUP INITIATED ===")
print("==================================\n")

# 1. Purge all records
env['health.vital.record'].search([]).unlink()
env['health.alert'].search([]).unlink()
env['health.patient'].search([]).unlink()
env.cr.commit()
print("CLEANUP SUCCESS: Tables wiped pristine. All old test data removed.\n")

# 2. Add more doctors
doc_group = env.ref('health_monitoring.group_health_doctor')
base_user = env.ref('base.group_user')

docs_to_add = [
    {'name': 'Dr. Allison Cameron', 'login': 'allison.cameron@hospital.local', 'password': 'doctor'},
    {'name': 'Dr. Robert Chase', 'login': 'robert.chase@hospital.local', 'password': 'doctor'},
    {'name': 'Dr. Eric Foreman', 'login': 'eric.foreman@hospital.local', 'password': 'doctor'},
    {'name': 'Dr. Lisa Cuddy', 'login': 'lisa.cuddy@hospital.local', 'password': 'doctor'}
]

for d in docs_to_add:
    if not env['res.users'].search([('login', '=', d['login'])]):
        user = env['res.users'].create({
            'name': d['name'],
            'login': d['login'],
            'password': d['password'],
            'groups_id': [(4, doc_group.id), (4, base_user.id)]
        })
        print(f"Created Doctor: {user.name}")

env.cr.commit()
print("Added new doctor accounts.")
