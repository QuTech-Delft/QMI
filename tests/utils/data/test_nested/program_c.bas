#Define PAR_foo Par_4

#Include ..\dep.inc
#Include .\dep2.inc

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
