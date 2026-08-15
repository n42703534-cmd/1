param(
    [string]$InputCsv = '.\outputs\algorithm_compare\mode4_20260704_141656\route_source_catalog_AA.csv'
)

$ErrorActionPreference = 'Stop'

function Parse-Distribution([string]$text, [string]$line) {
    if ([string]::IsNullOrWhiteSpace($text) -or $text -eq '—') { return @() }
    $items = @()
    foreach ($part in ($text -split '; ')) {
        if ($part -match '^(.+?):\s*([\d.]+)') {
            $name = $matches[1]
            $count = [double]$matches[2]
            if ($line -eq 'Maglev' -and $name -like '*_Exit*') { continue }
            $items += [pscustomobject]@{ Name = $name; Count = $count }
        }
    }
    return $items
}

function Fixed-Exit([string]$gate) {
    switch -Wildcard ($gate) {
        'Gate_L2_N_West' { return 'Exit_L2_2' }
        'Gate_L2_N_East' { return 'Exit_L2_6' }
        'Gate_L2_S_West' { return 'Exit_L2_4' }
        'Gate_L2_S_East' { return 'Exit_L2_3' }
        'Gate_L16_N*' { return 'Exit_L16_10' }
        'Gate_L16_S1' { return 'Exit_L16_11_west' }
        'Gate_L16_S2' { return 'Exit_L16_11_east' }
        'Gate_L18_E*' { return 'Exit_L18_12' }
        'Gate_L18_S*' { return 'Exit_L18_17' }
        'Gate_Maglev_W1' { return 'Exit_Maglev_18' }
        'Gate_Maglev_W3' { return 'Exit_Maglev_20' }
        default { return $null }
    }
}

function Couple-Greedy($left, $right) {
    $a = @($left | ForEach-Object { [pscustomobject]@{ Name=$_.Name; Remaining=[double]$_.Count } })
    $b = @($right | ForEach-Object { [pscustomobject]@{ Name=$_.Name; Remaining=[double]$_.Count } })
    $pairs = @()
    $i = 0; $j = 0
    while ($i -lt $a.Count -and $j -lt $b.Count) {
        $flow = [math]::Min($a[$i].Remaining, $b[$j].Remaining)
        if ($flow -gt 1e-9) {
            $pairs += [pscustomobject]@{ Left=$a[$i].Name; Right=$b[$j].Name; Count=$flow }
            $a[$i].Remaining -= $flow; $b[$j].Remaining -= $flow
        }
        if ($a[$i].Remaining -le 1e-9) { $i++ }
        if ($b[$j].Remaining -le 1e-9) { $j++ }
    }
    return $pairs
}

function Build-GateExit($gates, $exits) {
    $remaining = @{}
    foreach ($e in $exits) { $remaining[$e.Name] = [double]$e.Count }
    $result = @()

    foreach ($g in $gates) {
        $fixed = Fixed-Exit $g.Name
        if ($fixed) {
            $availableFixed = if ($remaining.ContainsKey($fixed)) { [double]$remaining[$fixed] } else { 0.0 }
            $take = [math]::Min([double]$g.Count, $availableFixed)
            if ($take -gt 0) {
                $result += [pscustomobject]@{ Gate=$g.Name; Exit=$fixed; Count=$take }
                $remaining[$fixed] -= $take
            }
        }
    }

    foreach ($g in $gates) {
        $used = ($result | Where-Object Gate -eq $g.Name | Measure-Object Count -Sum).Sum
        if ($null -eq $used) { $used = 0.0 }
        $need = [double]$g.Count - [double]$used
        foreach ($e in $exits) {
            if ($need -le 1e-9) { break }
            $available = if ($remaining.ContainsKey($e.Name)) { [double]$remaining[$e.Name] } else { 0.0 }
            if ($available -le 1e-9) { continue }
            $take = [math]::Min($need, $available)
            $result += [pscustomobject]@{ Gate=$g.Name; Exit=$e.Name; Count=$take }
            $remaining[$e.Name] -= $take; $need -= $take
        }
    }
    return $result
}

$rows = Import-Csv -LiteralPath $InputCsv
foreach ($row in $rows) {
    $total = [double]$row.evacuated_people
    $verticals = @(Parse-Distribution $row.vertical_distribution $row.line)
    if ($verticals.Count -eq 0) { $verticals = @([pscustomobject]@{Name='DIRECT';Count=$total}) }
    $gates = @(Parse-Distribution $row.gate_distribution $row.line)
    $exits = @(Parse-Distribution $row.exit_distribution $row.line)
    $vg = @(Couple-Greedy $verticals $gates)
    $ge = @(Build-GateExit $gates $exits)
    $complete = @()
    foreach ($gate in $gates.Name) {
        $incoming = @($vg | Where-Object Right -eq $gate | ForEach-Object {[pscustomobject]@{Name=$_.Left;Count=$_.Count}})
        $outgoing = @($ge | Where-Object Gate -eq $gate | ForEach-Object {[pscustomobject]@{Name=$_.Exit;Count=$_.Count}})
        foreach ($pair in @(Couple-Greedy $incoming $outgoing)) {
            $complete += [pscustomobject]@{ Vertical=$pair.Left; Gate=$gate; Exit=$pair.Right; Count=$pair.Count }
        }
    }
    Write-Output "## $($row.line) | $($row.source_group) | $([int]$total)人"
    foreach ($route in $complete) {
        $middle = if ($route.Vertical -eq 'DIRECT') { '' } else { " -> $($route.Vertical)" }
        $pct = 100.0 * $route.Count / $total
        Write-Output ("$($row.source_group)$middle -> $($route.Gate) -> $($route.Exit): {0:N1}% ({1:g}人)" -f $pct,$route.Count)
    }
}
