import time

import requests
from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/network", tags=["Network"])


@router.get("/public-ip")
def get_public_ip():
    providers = (
        ("ipify", "https://api.ipify.org?format=json"),
        ("ifconfig.me", "https://ifconfig.me/ip"),
        ("ipinfo", "https://ipinfo.io/json"),
    )
    errors = []
    for provider, url in providers:
        started = time.monotonic()
        try:
            response = requests.get(url, timeout=8)
            response.raise_for_status()
            latency_ms = int((time.monotonic() - started) * 1000)
            if provider in ("ipify", "ipinfo"):
                ip = str(response.json().get("ip") or "").strip()
            else:
                ip = response.text.strip()
            if ip:
                return {"success": True, "ip": ip, "provider": provider, "latency_ms": latency_ms}
        except Exception as exc:
            errors.append(f"{provider}: {exc}")
    raise HTTPException(status_code=502, detail={"success": False, "errors": errors})
