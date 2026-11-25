$ErrorActionPreference = 'Stop'
$documentPath = 'D:\DOANTOTNGHIEP\docs\section-3-3\Muc_3_3_Xay_dung_he_thong_quan_ly.docx'
$pdfPath = 'D:\DOANTOTNGHIEP\artifacts\section-3-3-word-qa\Muc_3_3_Xay_dung_he_thong_quan_ly.pdf'
$sectionApplication = $null
$sectionDocument = $null
try {
    $sectionApplication = New-Object -ComObject Word.Application
    $sectionApplication.Visible = $false
    $sectionApplication.DisplayAlerts = 0
    $sectionDocument = $sectionApplication.Documents.Open($documentPath, $false, $true)
    $sectionDocument.Repaginate()
    Write-Output ('Pages: ' + $sectionDocument.ComputeStatistics(2))
    $sectionDocument.ExportAsFixedFormat($pdfPath, 17)
    Write-Output $pdfPath
} finally {
    if ($null -ne $sectionDocument) {
        $sectionDocument.Close(0)
        [void][System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($sectionDocument)
    }
    if ($null -ne $sectionApplication) {
        $sectionApplication.Quit()
        [void][System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($sectionApplication)
    }
}
