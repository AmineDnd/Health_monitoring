import xmlrpc.client

url = 'http://localhost:8069'
db = 'smartlab_db'
username = 'admin'
password = 'admin'

try:
    common = xmlrpc.client.ServerProxy('{}/xmlrpc/2/common'.format(url))
    uid = common.authenticate(db, username, password, {})
    models = xmlrpc.client.ServerProxy('{}/xmlrpc/2/object'.format(url))

    patient_id = models.execute_kw(db, uid, password, 'health.patient', 'create', [{
        'name': 'Mohammed Tester',
        'age': 45,
        'gender': 'male',
        'ward_id': 2,
        'admission_status': 'admitted',
        'risk_level': 'low'
    }])
    print(f"Created patient ID: {patient_id}")
except Exception as e:
    print(f"Error: {e}")
