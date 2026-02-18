Listen to Home Assistant system log events and send log telemetry remotely
using Syslog or OTEL.


## OTEL

OpenTelemetry logs used, with following additional attributes:

* `code.file.path`
* `code.line.number`
* `code.function.name`
* `exception.count`
* `exception.first_occurred`
* `exception.stacktrace`


## Syslog

RFC5424 formatted messages, with additional structured data using OTEL taxonomy.

Syslog can be sent as TCP or UDP.
