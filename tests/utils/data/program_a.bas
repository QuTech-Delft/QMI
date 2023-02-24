#Define PAR_foo Par_1
#Define PAR_baz FPar_5
#Define DATA_boo Data_10
#Define PAR_elem_boo DATA_boo[1]

#Include .\dep.inc

Sub foo()
    Inc(PAR_foo)
EndSub

' ADbasic sections
Init:
    foo()

Event:
    bar()

Finish:
    foo()
