# Run this in PowerShell AS ADMINISTRATOR

$confPath = "C:\Program Files\Odoo 19.0.20260216\server\odoo.conf"
$customAddons = "c:\users\amine\desktop\smartlab\odoo\addons"

# Read current conf
$content = Get-Content $confPath -Raw

# Replace addons_path line to include custom path
$newContent = $content -replace `
    "addons_path = c:\\program files\\odoo 19.0.20260216\\server\\odoo\\addons", `
    "addons_path = c:\program files\odoo 19.0.20260216\server\odoo\addons,$customAddons"

# Write back
Set-Content -Path $confPath -Value $newContent -Encoding UTF8

Write-Host "addons_path updated!" -ForegroundColor Green

# Restart Odoo service so it picks up the new path
Restart-Service -Name "odoo-server-19.0" -Force
Write-Host "Odoo service restarted!" -ForegroundColor Green
Write-Host ""
Write-Host "Now go to: http://localhost:8069/web/database/manager" -ForegroundColor Cyan
Write-Host "Create a new database named: health_monitor" -ForegroundColor Cyan
Write-Host "Then install the Health Monitoring module from Apps." -ForegroundColor Cyan
