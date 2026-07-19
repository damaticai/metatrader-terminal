from pathlib import Path


MT5_ROOT = Path(__file__).resolve().parents[2]
TERMINAL_SHA256 = (
    "e87e8b77fa415fc91e9acbe692826e76b7907fb53db4244aed36618f9af30b9e"
)
SOURCE_IMAGE_DIGEST = (
    "sha256:4a10bcc649bd448425ec31fd8c80baf5f4c02d7d7ff0e1267c78c79a2b261f9e"
)


def test_dockerfile_pins_known_good_mt5_build_5836() -> None:
    dockerfile = (MT5_ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert f"metatrader-terminal@{SOURCE_IMAGE_DIGEST}" in dockerfile
    assert 'org.opencontainers.image.mt5-build="5836"' in dockerfile
    assert TERMINAL_SHA256 in dockerfile
    assert "COPY --from=mt5-build-5836 /opt/wineprefix /opt/wineprefix" in dockerfile
    assert "BUILD_MODE=1 xvfb-run /tmp/run-mt5.sh" not in dockerfile


def test_auto_login_marker_requires_verified_api_login() -> None:
    source = (MT5_ROOT / "assets" / "auto_login.py").read_text(encoding="utf-8")
    main_source = source.split("def main():", 1)[1]

    assert "if not vnc_mt5_client.verify_login(login, password, server):" in main_source
    assert "with open('/tmp/login_complete', 'w')" not in main_source
    assert "actual_login != int(login)" in source
    assert "MT5 IPC timeout (-10005)" in source
