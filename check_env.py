import xmlrpc.client

url = 'http://localhost:8069'
db = 'smartlab_db'
username = 'admin'
password = 'admin_password' # wait, I don't know the exact admin password, let's look at .env.

import os
with open('.env') as f:
    env_vars = f.read()
    print(env_vars)
