param(
    [Parameter(Mandatory = $true)][string]$InputDocx,
    [Parameter(Mandatory = $true)][string]$OutputPdf,
    [Parameter(Mandatory = $true)][string]$LogPath
)

$ErrorActionPreference = "Stop"
$word = $null
$doc = $null

function Write-RenderLog([string]$Message) {
    [System.IO.File]::AppendAllText($LogPath, "$(Get-Date -Format o) $Message`r`n")
}

try {
    [System.IO.File]::WriteAllText($LogPath, "")
    Write-RenderLog "start"
    $word = New-Object -ComObject Word.Application
    Write-RenderLog "word-created"
    $word.Visible = $false
    $word.DisplayAlerts = 0
    $word.AutomationSecurity = 3
    $word.Options.SaveNormalPrompt = $false
    $word.Options.UpdateLinksAtOpen = $false
    Write-RenderLog "opening"
    $doc = $word.Documents.OpenNoRepairDialog($InputDocx, $false, $true, $false)
    Write-RenderLog "opened pages=$($doc.ComputeStatistics(2))"
    $doc.ExportAsFixedFormat($OutputPdf, 17, $false, 0, 0, 1, $doc.ComputeStatistics(2), 0, $true, $true, 1, $true, $true, $false)
    Write-RenderLog "exported"
    $doc.Close($false)
    $doc = $null
    $word.Quit()
    $word = $null
    Write-RenderLog "complete"
}
catch {
    Write-RenderLog "error=$($_.Exception.Message)"
    throw
}
finally {
    if ($null -ne $doc) {
        try { $doc.Close($false) } catch {}
    }
    if ($null -ne $word) {
        try { $word.Quit() } catch {}
    }
}
