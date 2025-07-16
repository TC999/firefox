$cpu = Get-WmiObject Win32_Processor
Write-Output "硬件信息："
Write-Output "-------------------"
Write-Output "处理器信息："
Write-Output "-------------------"
Write-Output "处理器：$($cpu.Name)"
Write-Output "核心数：$($cpu.NumberOfCores)"
Write-Output "逻辑处理器数：$($cpu.NumberOfLogicalProcessors)"

# 内存单位换算
function Convert-Size($bytes) {
    switch ($bytes) {
        {$_ -ge 1TB} { "{0:N2} TB" -f ($bytes / 1TB); break }
        {$_ -ge 1GB} { "{0:N2} GB" -f ($bytes / 1GB); break }
        {$_ -ge 1MB} { "{0:N2} MB" -f ($bytes / 1MB); break }
        {$_ -ge 1KB} { "{0:N2} KB" -f ($bytes / 1KB); break }
        default      { "$bytes B" }
    }
}

# 内存
Write-Output "-------------------"
Write-Output "内存信息："
Get-WmiObject Win32_PhysicalMemory | ForEach-Object {
    $size = Convert-Size $_.Capacity
    Write-Host "容量: $size"
    Write-Host "厂商: $($_.Manufacturer)"
    #Write-Host "部件号: $($_.PartNumber)"
    #Write-Host "速度: $($_.Speed) MHz"
    Write-Host "----------------------"
}

# 硬盘
Write-Output "-------------------"
Write-Output "硬盘信息："
Get-WmiObject Win32_DiskDrive | ForEach-Object {
    $size = Convert-Size $_.Size
    Write-Host "型号: $($_.Model)"
    Write-Host "容量: $size"
    Write-Host "接口类型: $($_.InterfaceType)"
    Write-Host "分区数: $($_.Partitions)"
    #Write-Host "状态: $($_.Status)"
    #Write-Host "文件系统: $($_.FileSystem)"
    Write-Host "----------------------"
}