"""OTA manifest upload endpoint for the Custom Data Storage add-on.

Adds a single POST endpoint that writes a Matter OTA manifest JSON to the
matter-server addon's `updates/` directory so that
`python_matter_server`'s `load_local_updates` can pick it up.

This module is intentionally self-contained: it exposes a Flask Blueprint
named ``ota_manifest_bp`` that is registered from ``main.py``. None of the
add-on's pre-existing routes (data CRUD, websocket, metadata, health) are
touched.

Configuration (all optional):

* ``OTA_PROVIDER_DIR`` — directory where the manifest JSON is written.
  Default: ``/addon_configs/core_matter_server/updates``. Override if your
  matter-server addon stores updates elsewhere.

The endpoint reuses the same ``API_KEY`` env var as the rest of the add-on
so existing auth conventions stay consistent.
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from flask import Blueprint, jsonify, request

logger = logging.getLogger(__name__)

ota_manifest_bp = Blueprint("ota_manifest", __name__)

DEFAULT_OTA_PROVIDER_DIR = "/addon_configs/core_matter_server/updates"
SAFE_FILENAME_RE = re.compile(r"^[A-Za-z0-9._\-]+\.json$")

# Mirrors the env var read in main.py without importing it (avoids cycles).
_API_KEY = os.getenv("API_KEY", "") or ""


def _ota_dir() -> Path:
    return Path(os.getenv("OTA_PROVIDER_DIR", DEFAULT_OTA_PROVIDER_DIR))


def _check_api_key() -> bool:
    if not _API_KEY:
        return True
    provided = request.headers.get("X-API-Key") or request.args.get("api_key")
    return provided == _API_KEY


def _validate_manifest(content: Any) -> str | None:
    """Lightweight schema check. Returns an error string or None."""
    if not isinstance(content, dict):
        return "content must be a JSON object"
    mv = content.get("modelVersion")
    if not isinstance(mv, dict):
        return "content.modelVersion must be a JSON object"
    required = (
        "vid",
        "pid",
        "softwareVersion",
        "softwareVersionString",
        "otaUrl",
    )
    for f in required:
        if f not in mv:
            return f"content.modelVersion missing field: {f}"
    if not isinstance(mv["vid"], int) or not isinstance(mv["pid"], int):
        return "vid and pid must be integers"
    if not isinstance(mv["softwareVersion"], int):
        return "softwareVersion must be an integer"
    if not isinstance(mv["otaUrl"], str) or not mv["otaUrl"].strip():
        return "otaUrl must be a non-empty string"
    return None


@ota_manifest_bp.route("/api/ota/manifest/upload", methods=["POST"])
def upload_ota_manifest():
    """Write a Matter OTA manifest JSON to the hub.

    Request body::

        {
          "filename": "light_v2.json",
          "content":  { "modelVersion": { ... } }
        }

    Response::

        { "success": true, "path": "/addon_configs/core_matter_server/updates/light_v2.json" }
    """
    if not _check_api_key():
        return jsonify({"success": False, "error": "Invalid API key"}), 401

    try:
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            return jsonify({"success": False, "error": "Body must be JSON object"}), 400

        filename = (body.get("filename") or "").strip()
        content = body.get("content")

        if not filename:
            return jsonify({"success": False, "error": "filename is required"}), 400
        if not SAFE_FILENAME_RE.match(filename):
            return (
                jsonify(
                    {
                        "success": False,
                        "error": "filename must match [A-Za-z0-9._-]+\\.json (no paths)",
                    }
                ),
                400,
            )

        validation_err = _validate_manifest(content)
        if validation_err:
            return jsonify({"success": False, "error": validation_err}), 400

        ota_dir = _ota_dir()
        try:
            ota_dir.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            logger.error("Failed to create OTA dir %s: %s", ota_dir, e)
            return (
                jsonify(
                    {
                        "success": False,
                        "error": (
                            f"Cannot create {ota_dir}. The addon needs write "
                            f"access to that path; see README. ({e})"
                        ),
                    }
                ),
                500,
            )

        target = ota_dir / filename
        # Write atomically: write to .tmp, then rename.
        tmp = target.with_suffix(target.suffix + ".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(content, f, indent=2, sort_keys=True)
        os.replace(tmp, target)

        logger.info(
            "OTA manifest written: %s (%d bytes)",
            target,
            target.stat().st_size,
        )
        return jsonify(
            {
                "success": True,
                "path": str(target),
                "bytes_written": target.stat().st_size,
                "written_at": datetime.now(timezone.utc).isoformat(),
            }
        )
    except Exception as e:  # noqa: BLE001 — surface error verbatim to caller
        logger.exception("Unexpected error writing OTA manifest")
        return jsonify({"success": False, "error": str(e)}), 500


@ota_manifest_bp.route("/api/ota/manifest", methods=["GET"])
def list_ota_manifests():
    """List manifest filenames currently in the OTA provider dir."""
    if not _check_api_key():
        return jsonify({"success": False, "error": "Invalid API key"}), 401
    ota_dir = _ota_dir()
    if not ota_dir.exists():
        return jsonify({"success": True, "files": [], "path": str(ota_dir)})
    files = []
    for p in sorted(ota_dir.glob("*.json")):
        try:
            stat = p.stat()
            files.append(
                {
                    "name": p.name,
                    "size": stat.st_size,
                    "modified": datetime.fromtimestamp(
                        stat.st_mtime, tz=timezone.utc
                    ).isoformat(),
                }
            )
        except OSError:
            continue
    return jsonify({"success": True, "path": str(ota_dir), "files": files})
