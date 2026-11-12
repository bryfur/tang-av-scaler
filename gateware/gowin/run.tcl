# run.tcl: the second half of the build (build.sh): the project avb.tcl made, opened again with the
# transceivers' register file named in it (csr_result.py), and run
proc env {name default} {
    if {[info exists ::env($name)] && $::env($name) ne ""} { return $::env($name) }
    return $default
}
set here [file dirname [file normalize [info script]]]
set out  [file normalize [env GW_OUT $here/build/avb]]
open_project $out/avb/avb.gprj
run all
