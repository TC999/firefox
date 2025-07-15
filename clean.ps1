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

foreach ($path in $toRemove) {
    Get-ChildItem -Path $path -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

# 卸载 Chocolatey 安装的包（保留 git）
choco list --local-only | Select-String -Pattern '^[a-zA-Z0-9\.\-]+' | ForEach-Object {
    $pkg = $_.Line.Split('|')[0]
    if ($pkg -notlike "chocolatey*" -and $pkg -notlike "git*") {
        choco uninstall $pkg -y --remove-dependencies
    }

# 停止并卸载数据库服务
Stop-Service "postgresql-x64-17" -ErrorAction SilentlyContinue
& "C:\Program Files\PostgreSQL\17\uninstall-postgresql.exe" --mode unattended
Stop-Service "MongoDB" -ErrorAction SilentlyContinue
& "C:\Program Files\MongoDB\Server\7.0\unins000.exe" /VERYSILENT