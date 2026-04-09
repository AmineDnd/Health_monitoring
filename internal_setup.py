import sys
def run():
    g_nurse = env.ref('health_monitoring.group_health_nurse')
    g_doc = env.ref('health_monitoring.group_health_doctor')
    g_boss = env.ref('health_monitoring.group_health_admin')
    base_user = env.ref('base.group_user')
    
    def ensure_user(name, login, pw, group):
        u = env['res.users'].search([('login', '=', login)])
        if not u:
            u = env['res.users'].create({
                'name': name,
                'login': login,
                'password': pw,
                'groups_id': [(6, 0, [group.id, base_user.id])]
            })
            print(f"Created {login}")
        else:
            u.write({
                'password': pw,
                'groups_id': [(6, 0, [group.id, base_user.id])]
            })
            print(f"Updated {login}")
    
    ensure_user("Test Nurse", "nurse@test.com", "123", g_nurse)
    ensure_user("Test Doctor", "doc@test.com", "123", g_doc)
    ensure_user("Test Boss", "boss@test.com", "123", g_boss)
    env.cr.commit()

run()
