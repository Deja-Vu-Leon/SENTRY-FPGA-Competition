$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Console]::InputEncoding = [System.Text.Encoding]::ASCII
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding = [Console]::OutputEncoding
$project = $env:SENTRY_LAUNCHER_PROJECT
$bringup = Join-Path $project 'RK/bringup'
$programLogs = Join-Path $project 'validation/jtag'
New-Item -ItemType Directory -Force $programLogs | Out-Null
$bridge = Join-Path $bringup 'ftdi-rbb.py'
$known = Join-Path $bringup 'rk-known-hosts'
$fpga = Join-Path $project 'FPGA/prj/isp_imx415'
$bit = Join-Path $fpga 'vid007_hdr_quiesce.bit'
$timing = Join-Path $fpga 'vid007_hdr_quiesce.timing'
$key = $env:SENTRY_RK_KEY
$board = 'linaro@192.168.137.212'
$rk = '/home/linaro/sentry-vid007'
$unit = 'sentry-vid007-ai'
$gatewayUrl = $env:SENTRY_ESP_URL
if (!$gatewayUrl) { $gatewayUrl = 'http://192.168.50.1' }
if ($gatewayUrl -notmatch '^http://(?:\d{1,3}\.){3}\d{1,3}(?::\d+)?$') {
    throw 'ESP32 地址配置无效，请使用 http://IPv4地址 或 http://IPv4地址:端口。'
}
$serial = $env:SENTRY_FTDI_SERIAL
if ($serial -notmatch '^[A-Za-z0-9]{4,32}$') { throw '请设置 SENTRY_FTDI_SERIAL 为下载器序列号。' }
$usbProbe = "import ctypes as c; d=c.WinDLL('ftd2xx.dll'); h=c.c_void_p(); s=d.FT_OpenEx(b'$serial',1,c.byref(h)); print('FTDI/JTAG status:', s); d.FT_Close(h) if s == 0 else None; raise SystemExit(s)"

function Stage([int]$Number, [string]$Message) {
    Write-Output "[STAGE $Number] $Message"
}

function Board([string]$Command) {
    & $script:ssh @opts $board $Command
    if ($LASTEXITCODE -ne 0) { throw ('RK 网口命令失败，退出码 {0}。' -f $LASTEXITCODE) }
}

function Test-Gateway([switch]$Full) {
    $flags = if ($Full) { '--full' } else { '' }
    $result = & $script:ssh @opts $board "sudo -n python3 /home/linaro/sentry-esp32/check_gateway.py --url $gatewayUrl $flags --report /var/lib/sentry-esp32/launch-health.json" 2>&1
    $code = $LASTEXITCODE
    $result | ForEach-Object { Write-Output ([string]$_) }
    if ($code -ne 0) {
        $reason = $result | Where-Object { [string]$_ -like '[[]ERROR[]]*' } | Select-Object -Last 1
        if ($reason) { throw ([string]$reason).Replace('[ERROR] ','') }
        throw "ESP32 检查失败，退出码 $code，请查看上方错误。"
    }
}

function Program-Board {
    $listener = [Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback,0)
    $listener.Start()
    $port = $listener.LocalEndpoint.Port
    $listener.Stop()
    $bridgeError = Join-Path $programLogs 'jtag-rbb-errors.log'
    $server = Start-Process -FilePath $python -ArgumentList ('"{0}" --port {1} --serial {2}' -f $bridge,$port,$serial) -WorkingDirectory $bringup -WindowStyle Hidden -RedirectStandardOutput (Join-Path $programLogs 'jtag-rbb.log') -RedirectStandardError $bridgeError -PassThru
    try {
        Start-Sleep -Seconds 1
        if ($server.HasExited) {
            Get-Content -LiteralPath $bridgeError -ErrorAction SilentlyContinue
            throw 'USB-C 下载桥未启动。'
        }
        $file = $bit.Replace([char]92,[char]47)
        $commands = @(
            ('if {{[catch {{connect_cable -host_name 127.0.0.1:{0}}} err]}} {{puts $err; exit 1}}' -f $port),
            'if {[catch {read_device_id -cable 0} err]} {puts $err; exit 1}',
            ('if {{[catch {{download -bit {{{0}}} -mode jtag_burst -spd 7 -cable 0 -total_dev 1 -cur_dev 1 -bypass 0}} err]}} {{puts $err; exit 1}}' -f $file),
            'exit 0'
        )
        $options = [Diagnostics.ProcessStartInfo]::new($downloader)
        $options.UseShellExecute = $false
        $options.CreateNoWindow = $true
        $options.RedirectStandardInput = $true
        $options.RedirectStandardOutput = $true
        $options.RedirectStandardError = $true
        $tool = [Diagnostics.Process]::Start($options)
        try {
            $errors = $tool.StandardError.ReadToEndAsync()
            $inputBytes = [Text.Encoding]::ASCII.GetBytes(($commands -join ([string][char]10)) + [char]10)
            $inputStream = $tool.StandardInput.BaseStream
            $inputStream.Write($inputBytes,0,$inputBytes.Length)
            $inputStream.Close()
            & {
                while ($null -ne ($line = $tool.StandardOutput.ReadLine())) { $line }
                $errors.Result
            } | Tee-Object -FilePath (Join-Path $programLogs 'program-vid007_hdr_quiesce.log')
            $tool.WaitForExit()
            if ($tool.ExitCode -ne 0) { throw "FPGA 烧录工具返回失败，退出码 $($tool.ExitCode)。" }
        } finally {
            $tool.Dispose()
        }
    } finally {
        if (!$server.HasExited) { Stop-Process -Id $server.Id }
    }
}

function Attach-AndStart {
    Board "sudo -n bash $rk/rk-edge-bringup.sh attach"
    $readVersion = 'base=$(awk ''NR==1 {print $1}'' /sys/bus/pci/devices/0000:21:00.0/resource); test -n $base && sudo -n busybox devmem $((base + 0x40)) 32'
    $version = (Board $readVersion | Select-Object -Last 1).Trim()
    if ($version -ne '0x5607040E') { throw "FPGA 回读版本为 $version，预期为 0x5607040E。" }
    Write-Output "FPGA firmware $version"
    Board "if systemctl is-active --quiet $unit; then exit 0; fi; if systemctl cat $unit >/dev/null 2>&1; then sudo -n systemctl start $unit; else sudo -n systemd-run --unit=$unit --collect --property=Restart=on-failure --property=RestartSec=2s /bin/bash $rk/rk-ai/start-rk-cockpit.sh; fi"
}

$needsRecovery = $false
try {
    Stage 1 '检查 USB-C 下载器、固件和 RK 网口'
    foreach ($path in @($known, $bit, $timing, $key, $bridge)) {
        if (!$path -or !(Test-Path -LiteralPath $path -PathType Leaf)) { throw "缺少所需文件 $path" }
    }
    $report = Get-Content -LiteralPath $timing -Raw
    if ($report -notmatch '(?m)^\s*SWNS: [\d.]+ns, STNS: 0\.000ns' -or
        $report -notmatch '(?m)^\s*HWNS: [\d.]+ns, HTNS: 0\.000ns') { throw 'FPGA 固件的时序检查未通过。' }
    $td = (Get-Command td.exe -ErrorAction SilentlyContinue).Source
    if (!$td) {
        $td = 'G:\Anlogic\TD_Release_2026.1_SP2.200.067\bin\td.exe'
        if (!(Test-Path -LiteralPath $td -PathType Leaf)) { throw '找不到安路 TD 下载工具。' }
        $env:Path = "$(Split-Path $td);$env:Path"
    }
    $downloader = Join-Path (Split-Path $td) 'bw_commands_prompt.exe'
    if (!(Test-Path -LiteralPath $downloader)) { throw 'TD 目录缺少下载命令工具。' }
    $python = (Get-Command python.exe).Source
    $script:ssh = (Get-Command ssh.exe).Source
    $opts = @('-o','BatchMode=yes','-o','ConnectTimeout=5','-o','ServerAliveInterval=5',
              '-o','ServerAliveCountMax=2','-o','StrictHostKeyChecking=yes',
              '-o',"UserKnownHostsFile=$known",'-o','IdentitiesOnly=yes','-i',$key)
    & $python -c $usbProbe
    if ($LASTEXITCODE -ne 0) { throw 'USB-C 下载器无法打开。请确认数据线已连接，并关闭占用下载器的软件。' }
    Board "set -e; hostname; ip -br addr show end0; sudo -n true; test -r $rk/rk-edge-bringup.sh; test -r $rk/rk-ai/start-rk-cockpit.sh; test -x $rk/rk-ai/vid007-cockpit-preview"
    Stage 2 '检查 ESP32 启动、热点、校时及 RK 中文输入组件'
    Test-Gateway
    if ($env:SENTRY_LAUNCHER_CHECK -eq '1') { Stage 6 '系统检查通过（未烧录，未调用付费 API）'; exit 0 }

    Stage 3 '准备烧录，检查 SoC 录像状态'
    $recording = Board 'if sudo -n test -e /run/sentry-vid007-ai/record.enabled; then echo RECORDING; else echo IDLE; fi'
    if ($recording -ne 'IDLE') { throw 'TF 卡正在录像。请先在 SoC 的 F6 页面停止录像。' }
    $needsRecovery = $true
    Board "set -e; if systemctl is-active --quiet $unit; then sudo -n systemctl stop $unit; fi; sudo -n bash $rk/rk-edge-bringup.sh prepare"

    Stage 4 '通过 USB-C 烧录 FPGA'
    Program-Board

    Stage 5 '启动中文输入界面，验证四路帧率和 DeepSeek 联网'
    $start = (Board 'date +%s' | Select-Object -Last 1).Trim()
    Attach-AndStart
    $deadline = (Get-Date).AddSeconds(120)
    $framePattern = '(?m)^HDMI KMS flips[^\r\n]* A0 (\d+\.\d+) fps[^\r\n]* A1 (\d+\.\d+) fps[^\r\n]* B0 (\d+\.\d+) fps[^\r\n]* B1 (\d+\.\d+) fps'
    $last = $null
    do {
        Start-Sleep -Seconds 2
        $entries = (Board "sudo -n journalctl -u $unit --since '@$start' -n 42 -o cat --no-pager") -join "`n"
        $matchesFound = [regex]::Matches($entries,$framePattern)
        if (!$matchesFound.Count) { continue }
        $item = $matchesFound[$matchesFound.Count-1]
        $rates = 1..4 | ForEach-Object {
            [double]::Parse($item.Groups[$_].Value,[Globalization.CultureInfo]::InvariantCulture)
        }
        $lowest = ($rates | Measure-Object -Minimum).Minimum
        if ($lowest -gt 0) { $last = $item.Value }
        if ($lowest -ge 48) { break }
    } while ((Get-Date) -lt $deadline)
    Board "systemctl is-active $unit"
    if (!$last) { throw 'HDMI 服务已启动，等待期间未收到四路同时送显的日志。请查看运行日志。' }
    Write-Output $last
    if ($lowest -lt 48) { throw '四路帧率尚未全部达到 48 fps，请检查摄像头和送显诊断日志。' }
    $needsRecovery = $false
    Board 'sudo -n systemctl start sentry-esp32-alerts sentry-esp32-chat'
    Test-Gateway -Full
    Stage 6 'FPGA 烧录、RK 中文界面、ESP32 联网及 DeepSeek 实测全部通过'
    exit 0
} catch {
    Write-Output ("[ERROR] " + $_.Exception.Message)
    if ($needsRecovery) {
        try {
            Write-Output '尝试恢复 SoC 界面'
            Attach-AndStart
        } catch {
            Write-Output ("[ERROR] 恢复界面失败。" + $_.Exception.Message)
        }
    }
    exit 1
}
