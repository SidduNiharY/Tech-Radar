rule pdf_js_openaction {
    meta:
        description = "PDF with JavaScript and OpenAction"
    strings:
        $js = "/JavaScript"
        $oa = "/OpenAction"
    condition:
        $js and $oa
}

rule embedded_pe {
    meta:
        description = "Embedded Windows PE executable"
    strings:
        $mz = "MZ"
        $dos = "This program cannot be run in DOS mode"
    condition:
        $mz at 0 and $dos
}
