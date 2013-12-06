Autohub
=======

Autohub is a simple system to keep track of devices like switches and
temp senors connected to a RFXtrx433 transceiver.

Autohub has two parts; one is the server process which keeps track of
the devices and their state, names etc and the other is a client
program "ahc" which present a command-line interface to the user
and/or other scripts (typically cron). ahc uses JSON-RPC to talk to
the server, and thus it works across a TCP/IP network.

Autohub does not support all devices RFXtrx433, but only the very limited
subset I've happen to own.

In its current form, it's very unlikely you're going to be able to use
this package "as is", but rather you need to modify it to support your
devices. You will need to know Python, and you will also need to
understand a bit how the RFXtrx433 works. I just put the software up
on Github because one of my colleagues wanted a copy, but maybe there's
someone else out there that will find it useful.

If you add support for new devices, please feel free to submit these
improvements.

Have fun.
