# Example Configuration - OpenObserve with Vector

These are working examples, not ideal recommendations.

They are meant for a home network you trust: the syslog and OTLP listeners accept logs from anything that can reach them, without a login or encryption. Before using them, set your own passwords, pin the image versions rather than `latest`, and don't publish the ports beyond your own network. Vector is given the Docker socket, read-only, to collect container logs: that still lets it see everything about every container on the host.

The Vector config will also pull in Docker logs and systemd journal from the box on which it runs ( excluding Vector and OpenObserve from the Docker logging to prevent cycles).

OpenObserve handles OTLP directly, so Vector can be skipped if there's no syslog to capture, and no Docker ( or a native OTLP collector installed for Docker)
