$ErrorActionPreference = 'Stop'
$documentPath = 'D:\DOANTOTNGHIEP\docs\section-3-2\Muc_3_2_Xay_dung_co_so_du_lieu.docx'
$pdfPath = 'D:\DOANTOTNGHIEP\artifacts\section-3-2-word-qa\Muc_3_2_Xay_dung_co_so_du_lieu.pdf'
$wordApplication = $null
$wordDocument = $null
try {
    $wordApplication = New-Object -ComObject Word.Application
    $wordApplication.Visible = $false
    $wordApplication.DisplayAlerts = 0
    $wordDocument = $wordApplication.Documents.Open($documentPath, $false, $true)
    $wordDocument.Repaginate()
    Write-Output ('Pages: ' + $wordDocument.ComputeStatistics(2))
    $wordDocument.ExportAsFixedFormat($pdfPath, 17)
    Write-Output $pdfPath
} finally {
    if ($null -ne $wordDocument) {
        $wordDocument.Close(0)
        [void][System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($wordDocument)
    }
    if ($null -ne $wordApplication) {
        $wordApplication.Quit()
        [void][System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($wordApplication)
    }
}
