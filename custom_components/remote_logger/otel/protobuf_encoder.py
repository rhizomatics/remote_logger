"""Minimal protobuf wire-format encoder for OTLP ExportLogsServiceRequest.

Encodes the same dict structure used for JSON export into protobuf binary,
without requiring the opentelemetry-proto compiled classes.
"""
from __future__ import annotations

import logging
import struct
from typing import Any

# Protobuf wire types
WIRE_VARINT = 0
WIRE_64BIT = 1
WIRE_LENGTH_DELIMITED = 2

_LOGGER = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
#  Low-level protobuf primitives                                               #
# --------------------------------------------------------------------------- #


def _encode_varint(value: int) -> bytes:
    """Encode an unsigned integer as a protobuf varint."""
    parts = []
    while value > 0x7F:
        parts.append((value & 0x7F) | 0x80)
        value >>= 7
    parts.append(value & 0x7F)
    return bytes(parts)


def _tag(field_number: int, wire_type: int) -> bytes:
    return _encode_varint((field_number << 3) | wire_type)


def _encode_string_field(field_number: int, value: str) -> bytes:
    """Encode a string field (tag + length + UTF-8 bytes)."""
    try:
        data = value.encode("utf-8")
    except Exception:
        _LOGGER.exception("remote_logger non string found at %s: %s", field_number, value)
        data = b"TYPE ERROR"
    return _tag(field_number, WIRE_LENGTH_DELIMITED) + _encode_varint(len(data)) + data


def _encode_bytes_field(field_number: int, value: bytes) -> bytes:
    """Encode a bytes field (tag + length + raw bytes)."""
    return _tag(field_number, WIRE_LENGTH_DELIMITED) + _encode_varint(len(value)) + value


def _encode_submessage(field_number: int, data: bytes) -> bytes:
    """Encode an embedded message field (tag + length + serialized submessage)."""
    return _tag(field_number, WIRE_LENGTH_DELIMITED) + _encode_varint(len(data)) + data


def _encode_fixed64(field_number: int, value: int) -> bytes:
    """Encode a fixed64 field (tag + 8 bytes little-endian)."""
    return _tag(field_number, WIRE_64BIT) + struct.pack("<Q", value)


def _encode_uint32_field(field_number: int, value: int) -> bytes:
    """Encode a uint32/int32/enum as a varint field."""
    return _tag(field_number, WIRE_VARINT) + _encode_varint(value)


# --------------------------------------------------------------------------- #
#  OTLP message encoders                                                       #
#  Each function takes the same dict structure used for JSON and returns bytes. #
# --------------------------------------------------------------------------- #


def _encode_any_value(av: dict[str, Any]) -> bytes:
    """Encode an AnyValue message. We only support stringValue (field 1)."""
    if "stringValue" in av:
        return _encode_string_field(1, av["stringValue"])
    return b""


def _encode_key_value(kv: dict[str, Any]) -> bytes:
    """Encode a KeyValue message: key=1 (string), value=2 (AnyValue)."""
    result = _encode_string_field(1, kv["key"])
    if "value" in kv:
        value_bytes = _encode_any_value(kv["value"])
        result += _encode_submessage(2, value_bytes)
    return result


def _encode_resource(resource: dict[str, Any]) -> bytes:
    """Encode a Resource message: attributes=1 (repeated KeyValue)."""
    result = b""
    for attr in resource.get("attributes", []):
        result += _encode_submessage(1, _encode_key_value(attr))
    return result


def _encode_instrumentation_scope(scope: dict[str, Any]) -> bytes:
    """Encode an InstrumentationScope: name=1, version=2."""
    result = b""
    if "name" in scope:
        result += _encode_string_field(1, scope["name"])
    if "version" in scope:
        result += _encode_string_field(2, scope["version"])
    return result


def _encode_log_record(record: dict[str, Any]) -> bytes:
    """Encode a LogRecord message.

    Field mapping:
        time_unix_nano = 1 (fixed64)
        severity_number = 2 (enum/int32)
        severity_text = 3 (string)
        body = 5 (AnyValue)
        attributes = 6 (repeated KeyValue)
        trace_id = 9 (bytes)
        span_id = 10 (bytes)
        observed_time_unix_nano = 11 (fixed64)
    """
    result = b""

    if "timeUnixNano" in record:
        result += _encode_fixed64(1, int(record["timeUnixNano"]))

    if "severityNumber" in record:
        result += _encode_uint32_field(2, record["severityNumber"])

    if "severityText" in record:
        result += _encode_string_field(3, record["severityText"])

    if "body" in record:
        result += _encode_submessage(5, _encode_any_value(record["body"]))

    for attr in record.get("attributes", []):
        result += _encode_submessage(6, _encode_key_value(attr))

    if record.get("traceId"):
        result += _encode_bytes_field(9, bytes.fromhex(record["traceId"]))

    if record.get("spanId"):
        result += _encode_bytes_field(10, bytes.fromhex(record["spanId"]))

    if "observedTimeUnixNano" in record:
        result += _encode_fixed64(11, int(record["observedTimeUnixNano"]))

    return result


def _encode_scope_logs(scope_logs: dict[str, Any]) -> bytes:
    """Encode a ScopeLogs: scope=1, log_records=2."""
    result = b""
    if "scope" in scope_logs:
        result += _encode_submessage(
            1, _encode_instrumentation_scope(scope_logs["scope"])
        )
    for record in scope_logs.get("logRecords", []):
        result += _encode_submessage(2, _encode_log_record(record))
    return result


def _encode_resource_logs(rl: dict[str, Any]) -> bytes:
    """Encode a ResourceLogs: resource=1, scope_logs=2."""
    result = b""
    if "resource" in rl:
        result += _encode_submessage(1, _encode_resource(rl["resource"]))
    for sl in rl.get("scopeLogs", []):
        result += _encode_submessage(2, _encode_scope_logs(sl))
    return result


def encode_export_logs_request(request: dict[str, Any]) -> bytes:
    """Encode an ExportLogsServiceRequest: resource_logs=1 (repeated).

    Takes the same dict structure as the JSON payload and returns
    the serialized protobuf bytes.
    """
    result = b""
    for rl in request.get("resourceLogs", []):
        try:
            result += _encode_submessage(1, _encode_resource_logs(rl))
        except Exception as e:
            _LOGGER.error("remote_logger: failed to build protobuf: %s", e)
    return result
