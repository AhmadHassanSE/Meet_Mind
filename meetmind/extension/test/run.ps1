# Runs the extension page tests in headless Chrome and exits non-zero on failure.
$chrome = "C:\Program Files\Google\Chrome\Application\chrome.exe"
$path = (Resolve-Path (Join-Path $PSScriptRoot "hints.test.html")).Path
$page = "file:///" + $path.Replace([string][char]92, "/")
$out = Join-Path $env:TEMP "meetmind-ext-test.html"
$profile = Join-Path $env:TEMP "meetmind-ext-test-profile"
Start-Process -FilePath $chrome -ArgumentList "--headless=new", "--disable-gpu", "--no-sandbox", "--user-data-dir=$profile", "--virtual-time-budget=3000", "--dump-dom", $page -RedirectStandardOutput $out -Wait -NoNewWindow
$result = Select-String -Path $out -Pattern '<pre id="results">(.*)' -Context 0, 8
if ($result -and $result.Line -match 'PASS') { "hints tests: PASS"; exit 0 }
$result | Out-String
exit 1
