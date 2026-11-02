"""Apply the checked-in Ayu patch series, or verify an already prepared checkout.

Usage: python ayu_prepare.py [--verify]
Never resets, cleans, overwrites conflicting edits, or downloads dependencies.
"""
import argparse
import hashlib
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
PATCHES = ("ayu-privacy.patch", "ayu-history.patch")
EXPECTED_FILES = {
    "submodules/SettingsUI/Sources/AyuMessageHistoryController.swift": "20cf778563f9dc846da511ac373ac77da07aaa0840c3411d61aabd51ee3bf6ed",
    "submodules/SettingsUI/Sources/AyuSettingsController.swift": "787be71d827c28aaad2fcef2a1f02032d1c00e429cac6659f5fd963373f64b9a",
    "submodules/SettingsUI/Sources/Privacy and Security/PrivacyAndSecurityController.swift": "562ab7bed023479d573850cbeaa2ff91274dd0a2806805c5acce5ea5755bc507",
    "submodules/TelegramCore/Sources/Account/Account.swift": "36a707b1b85f14cbbd798168356f5da69d78116e792420f9b9bc2802cedfad9f",
    "submodules/TelegramCore/Sources/Settings/AyuMessageHistory.swift": "389767a7478646916c02d9d9157dc50f297a6fb3a7f4e5131338c736e288ebb9",
    "submodules/TelegramCore/Sources/Settings/AyuMessageHistoryStorage.swift": "4152fa9b8ee313f850307801aa87294941c27f112cfb8ce75b6ac566b1301f70",
    "submodules/TelegramCore/Sources/Settings/AyuPrivacySettings.swift": "ae700f739604062c23e0f2af5a487f1f48ed407201e296bf952552fe6ae7b056",
    "submodules/TelegramCore/Sources/Settings/AyuPrivacySettingsStorage.swift": "d606ac2cdc2dd3683fa46ecd8ae5b338995ff300aa7ef40502e82530b3e15ee1",
    "submodules/TelegramCore/Sources/State/AccountStateManagementUtils.swift": "ba55cedcd25bd0be89fde0bad986e6130343b63affeeab357911b588b1b3e532",
    "submodules/TelegramCore/Sources/State/ManagedLocalInputActivities.swift": "9cac9044465777dcf48749a02c5f3acfaf078189cd9402b355761b42b6d66971",
    "submodules/TelegramCore/Sources/TelegramEngine/Messages/ApplyMaxReadIndexInteractively.swift": "8cfa5c9334508708ef90acc79d839b90d4e3774a96d260a8733be6c141c33388",
    "submodules/TelegramCore/Sources/TelegramEngine/Messages/InstallInteractiveReadMessagesAction.swift": "ad9eeb1c48d62c4ae6b6ab5e2e3c5f8378c4a53c030ebc464c03ae4aa8a19d76",
    "submodules/TelegramCore/Sources/TelegramEngine/Privacy/TelegramEnginePrivacy.swift": "6a3b2db9bb44b4e8b24cb485ce6617d622f5c414acb040191315a492473e6c30",
    "tools/ayu/tests/main.swift": "f86e335d4c92ae425acf8b7eb082587947abe683c07227f1b1a559c3ec881b10"
}


def matches_expected():
    for name, expected in EXPECTED_FILES.items():
        path = ROOT / name
        if not path.is_file():
            return False
        content = path.read_bytes().replace(b"\r\n", b"\n")
        if hashlib.sha256(content).hexdigest() != expected:
            return False
    return bool(EXPECTED_FILES)


def git(*arguments):
    return subprocess.run(["git", "-C", str(ROOT), *arguments], capture_output=True, text=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify", action="store_true", help="Read-only verification of the prepared sources")
    args = parser.parse_args()
    if matches_expected():
        print("Ayu source overlay is already prepared and verified.")
        return 0
    if args.verify:
        print("Sources differ from the reviewed overlay. Inspect git diff before making changes.", file=sys.stderr)
        return 1
    root = git("rev-parse", "--show-toplevel")
    if root.returncode or Path(root.stdout.strip()).resolve() != ROOT:
        raise RuntimeError("Run this script from the Ayu Git checkout.")
    for name in PATCHES:
        patch = str(ROOT / name)
        if not Path(patch).is_file():
            raise RuntimeError(f"Missing patch: {name}")
        # Handles a checkout prepared through only the first patch as well.
        if git("apply", "--reverse", "--check", patch).returncode == 0:
            print(f"Already applied: {name}")
            continue
        check = git("apply", "--check", patch)
        if check.returncode:
            raise RuntimeError(f"Cannot safely apply {name}. No reset was performed.\n{check.stderr}")
        result = git("apply", patch)
        if result.returncode:
            raise RuntimeError(result.stderr)
        print(f"Applied: {name}")
    if not matches_expected():
        raise RuntimeError("Overlay differs from the expected source hashes; inspect git diff.")
    print("Ayu source overlay prepared and verified.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (RuntimeError, OSError) as error:
        print(f"Ayu preparation: {error}", file=sys.stderr)
        sys.exit(1)
