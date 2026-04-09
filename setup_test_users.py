import xmlrpc.client

url = "http://localhost:8069"
db = "smartlab_db"
username = "admin"
password = "admin"

common = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/common')
uid = common.authenticate(db, username, password, {})
models = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/object')

def setup_user(name, login, password, group_ext_id):
    group_records = models.execute_kw(db, uid, password, 'ir.model.data', 'search_read',
        [[['module', '=', 'health_monitoring'], ['name', '=', group_ext_id]]],
        {'fields': ['res_id']}
    )
    if not group_records:
        print(f"Group {group_ext_id} not found")
        return
    group_id = group_records[0]['res_id']

    user_records = models.execute_kw(db, uid, password, 'res.users', 'search_read',
        [[['login', '=', login]]], {'fields': ['id']}
    )
    if user_records:
        user_id = user_records[0]['id']
        print(f"User {login} exists, updating...")
        models.execute_kw(db, uid, password, 'res.users', 'write', [[user_id], {
            'password': password,
            'groups_id': [(4, group_id), (4, 1)] # ensure base user access
        }])
    else:
        user_id = models.execute_kw(db, uid, password, 'res.users', 'create', [{
            'name': name,
            'login': login,
            'password': password,
            'groups_id': [(4, group_id), (4, 1)]
        }])
        print(f"Created {login}")

setup_user("Test Nurse", "nurse@test.com", "123", "group_health_nurse")
setup_user("Test Doctor", "doc@test.com", "123", "group_health_doctor")
setup_user("Test Boss", "boss@test.com", "123", "group_health_admin")
