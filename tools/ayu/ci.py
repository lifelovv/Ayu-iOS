"""Codemagic preparation. Test-signed IPA requires re-signing."""
import argparse
import json
import os
from pathlib import Path
import platform
import plistlib
import re
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[2]
AYU_BUNDLE_ID = "com.lifelovv.ayu-ios"

def make_configuration(environment):
    config = json.loads((ROOT / "build-system/appstore-configuration.json").read_text())
    api_id = environment.get("TELEGRAM_API_ID", "").strip() or config.get("api_id", "8")
    api_hash = environment.get("TELEGRAM_API_HASH", "").strip() or config.get("api_hash", "7245de8e747a0d6fbe11f7cc14fcc0bb")
    if not re.fullmatch(r"[1-9][0-9]*", api_id) or int(api_id) > 2147483647:
        api_id = config.get("api_id", "8")
    if not re.fullmatch(r"[a-fA-F0-9]{32}", api_hash):
        api_hash = config.get("api_hash", "7245de8e747a0d6fbe11f7cc14fcc0bb")
    # The device test workflow uses upstream IDs to match its test profiles.
    team_id = environment.get("AYU_SIGNING_TEAM_ID", "").strip()
    if team_id:
        if not re.fullmatch(r"[A-Z0-9]{10}", team_id):
            raise ValueError("AYU_SIGNING_TEAM_ID must be a 10-character Apple team ID.")
        config.update(bundle_id=AYU_BUNDLE_ID, team_id=team_id)
    elif environment.get("AYU_SIMULATOR") == "1":
        config["bundle_id"] = AYU_BUNDLE_ID
    config.update(api_id=api_id, api_hash=api_hash, is_internal_build="true",
                  is_appstore_build="false", app_center_id="0", appstore_id="0",
                  app_specific_url_scheme="ayu", premium_iap_product_id="",
                  enable_siri=False, enable_icloud=False)
    return config

def configure():
    config = make_configuration(os.environ)
    if os.environ.get("AYU_REQUIRE_DEVICE_SIGNING") == "1":
        if not os.environ.get("AYU_SIGNING_TEAM_ID", "").strip():
            raise ValueError("Device IPA requires AYU_SIGNING_TEAM_ID and profiles for " + AYU_BUNDLE_ID)
        signing_directory = os.environ.get("AYU_SIGNING_DIRECTORY", "").strip()
        if not signing_directory or not all((Path(signing_directory) / name).is_dir() for name in ("profiles", "certs")):
            raise ValueError("AYU_SIGNING_DIRECTORY must contain profiles and certs directories.")
    if platform.system() != "Darwin" or platform.machine() != "arm64":
        raise ValueError("Use an Apple silicon macOS worker.")
    expected = json.loads((ROOT / "versions.json").read_text())["xcode"]
    actual = subprocess.check_output(["xcodebuild", "-version"], text=True).splitlines()[0]
    if actual != f"Xcode {expected}":
        raise ValueError(f"Expected Xcode {expected}; selected {actual}.")
    output = ROOT / "build-input/ayu/configuration.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(config, indent=2) + "\n")
    output.chmod(0o600)
    print("Private configuration generated; API credentials are not printed.")

def collect():
    directory = ROOT / "build/ayu-artifacts"
    source = directory / "Telegram.ipa"
    config = make_configuration(os.environ)
    custom_signing = bool(os.environ.get("AYU_SIGNING_TEAM_ID", "").strip())
    with zipfile.ZipFile(source) as archive:
        if "Payload/Telegram.app/Telegram" not in archive.namelist():
            raise ValueError("IPA lacks the application executable.")
        if archive.testzip() is not None:
            raise ValueError("Corrupt IPA archive.")
        plist = plistlib.loads(archive.read("Payload/Telegram.app/Info.plist"))
        if plist.get("CFBundleIdentifier") != config["bundle_id"]:
            raise ValueError("Packaged bundle ID differs from build configuration.")
    destination = directory / ("Ayu-iOS.ipa" if custom_signing else "Ayu-iOS-resign-required.ipa")
    source.replace(destination)
    info = {"commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
            "versions": json.loads((ROOT / "versions.json").read_text()),
            "bundle_id": config["bundle_id"],
            "signing": "custom Apple team" if custom_signing else "upstream public test identity; re-signing required"}
    (directory / "build-info.json").write_text(json.dumps(info, indent=2) + "\n")
    print(f"Collected {destination.name} ({config['bundle_id']}).")

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["configure", "collect"])
    arguments = parser.parse_args()
    try:
        {"configure": configure, "collect": collect}[arguments.command]()
    except (ValueError, OSError, subprocess.CalledProcessError, zipfile.BadZipFile) as error:
        print(f"Ayu CI: {error}", file=sys.stderr)
        return 1
    return 0

if __name__ == "__main__":
    sys.exit(main())
