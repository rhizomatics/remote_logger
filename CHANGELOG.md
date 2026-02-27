# 1.1.0
- More customization for OTLP, now able to use more platforms, including OpenObserve
    - Custom HTTP headers
    - Bearer token
    - Alternative API endpoint or custom path prefix
# 1.0.0
- Dependencies and docs update for public release
# 0.4.0
- Add Device to bundle entities
# 0.3.0
- Unique names for exporters
# 0.2.0
- Add entities to track incoming events, outgoing postings, errors
- Refactor to common exporter class
# 0.0.5
- Use the OpenTelemetry convention of prefixing Syslog structured data parameters with the non-IANA standard `opentelemetry`
- Messages retried if connection down
