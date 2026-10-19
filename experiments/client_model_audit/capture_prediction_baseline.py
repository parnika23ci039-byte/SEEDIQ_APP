#!/usr/bin/env python3
"""Capture fixed-input prediction baselines from a SeedIQ backend.

Phase 2 parity artifact. Sends a small, FIXED set of payloads to the four
inference endpoints and records the exact response bytes + a SHA-256 per
endpoint. Re-running this after a code change and diffing the digest file is
the parity test: identical digests == identical predictions.

Inference only — no endpoint here trains, retrains or rewrites an artifact.

Usage:
    python3 capture_prediction_baseline.py <base_url> <out.json>
"""
import hashlib
import json
import sys
import urllib.request

ENDPOINTS = {
    "crop": ("/api/crop-recommendation", {
        "nitrogen": 90, "phosphorus": 42, "potassium": 43,
        "temperature": 20.9, "humidity": 82.0, "ph": 6.5, "rainfall": 202.9,
    }),
    "yield": ("/api/yield-prediction", {"crop": "Rice", "area_hectares": 10}),
    "seed": ("/api/seed-viability", {"moisture": 12.5, "weight": 45.0}),
    "quantum": ("/api/quantum-ml", {
        "nitrogen": 90, "phosphorus": 42, "potassium": 43,
        "temperature": 20.9, "humidity": 82.0, "ph": 6.5, "rainfall": 202.9,
        "crop": "Rice", "area_hectares": 10,
        "moisture": 12.5, "weight": 45.0,
    }),
}


def post(base, path, payload, timeout=180):
    req = urllib.request.Request(
        base.rstrip("/") + path,
        data=json.dumps(payload).encode(),
        method="POST",
        headers={"Content-Type": "application/json", "Accept": "application/json",
                 "User-Agent": "SeedIQ-parity-capture/1.0"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except Exception as e:
        return None, json.dumps({"transport_error": f"{type(e).__name__}: {e}"}).encode()


def main():
    if len(sys.argv) != 3:
        print(__doc__)
        return 2
    base, out_path = sys.argv[1], sys.argv[2]

    record = {"base_url": base, "endpoints": {}}
    print(f"base_url = {base}\n")
    print(f"{'endpoint':<10} {'http':<5} {'body sha256[:16]':<18} response (truncated)")
    print("-" * 100)
    for name, (path, payload) in ENDPOINTS.items():
        status, body = post(base, path, payload)
        digest = hashlib.sha256(body).hexdigest()
        try:
            parsed = json.loads(body.decode("utf-8", "replace"))
        except Exception:
            parsed = {"_raw": body.decode("utf-8", "replace")[:400]}
        record["endpoints"][name] = {
            "path": path,
            "payload": payload,
            "http_status": status,
            "sha256": digest,
            "response": parsed,
        }
        preview = json.dumps(parsed)[:150]
        print(f"{name:<10} {str(status):<5} {digest[:16]:<18} {preview}")

    with open(out_path, "w") as f:
        json.dump(record, f, indent=2, sort_keys=True)
    print(f"\nwrote {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
