import requests, re
try:
    r = requests.get('http://localhost:8069/web?debug=1', timeout=10)
    m = re.findall(r'/web/assets/\w+/web\.assets_backend[^"]*\.css', r.text)
    print("Backend CSS URLs:", m)
    # Check if sl-dashboard-container is in any of those CSS files
    for url in m[:3]:
        cr = requests.get('http://localhost:8069' + url, timeout=15)
        if 'sl-dashboard-container' in cr.text:
            print("FOUND sl-dashboard-container in:", url)
        else:
            print("NOT FOUND in:", url, "- size:", len(cr.text))
except Exception as e:
    print("Error:", e)
