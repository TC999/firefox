# 保留 Git，删除常见开发工具和运行时
$toRemove = @(
    "C:\Program Files\Docker",
    "C:\Miniconda",
    "C:\msys64",
    "C:\hostedtoolcache\windows\Python",
    "C:\hostedtoolcache\windows\Node",
    "C:\hostedtoolcache\windows\Ruby",
    "C:\hostedtoolcache\windows\go",
    "C:\hostedtoolcache\windows\Java_Adopt_jdk*",
    "C:\hostedtoolcache\windows\Java_Temurin_jdk*",
    "C:\Android",
    "C:\Program Files\PostgreSQL",
    "C:\Program Files\MongoDB",
    "C:\tools\Apache24",
    "C:\tools\nginx-*",
    "C:\vcpkg",
    "C:\Miniconda",
    "C:\selenium",
    "C:\R"
)

# 并行删除目录，加快清理速度
$jobs = @()
foreach ($path in $toRemove) {
    $jobs += Start-Job -ScriptBlock {
        param($p)
        Write-Host "正在尝试删除：$p"
        if (Test-Path $p) {
            Remove-Item $p -Recurse -Force -ErrorAction SilentlyContinue
        } else {
            Write-Host "  路径不存在，跳过"
        }
    } -ArgumentList $path
}
# 等待所有后台任务完成
$jobs | Wait-Job | Out-Null
$jobs | Remove-Job

# 卸载 Chocolatey 安装的包（保留 git），批量卸载提升速度
# 注意：不再使用 --local-only
$pkgs = choco list | Select-String -Pattern '^[a-zA-Z0-9\.\-]+' | ForEach-Object {
    $_.Line.Split('|')[0]
} | Where-Object { $_ -notlike "chocolatey*" -and $_ -notlike "git*" }
if ($pkgs.Count -gt 0) {
    Write-Host "批量卸载 Chocolatey 包：" ($pkgs -join ', ')
    choco uninstall $($pkgs -join ' ') -y --remove-dependencies
}

# 停止并卸载数据库服务（先检测文件是否存在，静默卸载）
Write-Host "正在停止并卸载 PostgreSQL..."
Stop-Service "postgresql-x64-17" -ErrorAction SilentlyContinue
$pgUninstaller = "C:\Program Files\PostgreSQL\17\uninstall-postgresql.exe"
if (Test-Path $pgUninstaller) {
    & $pgUninstaller --mode unattended
} else {
    Write-Host "PostgreSQL 卸载器不存在，跳过此步"
}

Write-Host "正在停止并卸载 MongoDB..."
Stop-Service "MongoDB" -ErrorAction SilentlyContinue
$mongoUninstaller = "C:\Program Files\MongoDB\Server\7.0\unins000.exe"
if (Test-Path $mongoUninstaller) {
    & $mongoUninstaller /VERYSILENT
} else {
    Write-Host "MongoDB 卸载器不存在，跳过此步"
}