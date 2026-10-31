"""
Launcher used when JARVIS is packaged as a double-click Mac app (JARVIS.app).

- Asks for your free Gemini API key the first time and stores it in the macOS Keychain
- Starts JARVIS in voice mode ("Jarvis, ...")
- Writes logs to ~/Library/Logs/JARVIS.log (useful if something goes wrong)
"""

import os
import subprocess
import sys
import traceback

LOG = os.path.expanduser("~/Library/Logs/JARVIS.log")
os.makedirs(os.path.dirname(LOG), exist_ok=True)
_log = open(LOG, "a", buffering=1)
sys.stdout = _log
sys.stderr = _log

KEYCHAIN_SERVICE = "jarvis-gemini-key"


def alert(message: str):
    safe = message.replace("\\", "\\\\").replace('"', '\\"')
    subprocess.run([
        "osascript", "-e",
        f'display dialog "{safe}" with title "JARVIS" buttons {{"OK"}} default button "OK"',
    ])


def get_api_key():
    r = subprocess.run(
        ["security", "find-generic-password", "-a", "jarvis", "-s", KEYCHAIN_SERVICE, "-w"],
        capture_output=True, text=True,
    )
    if r.returncode == 0 and r.stdout.strip():
        return r.stdout.strip()

    script = (
        'text returned of (display dialog "Paste your free Gemini API key '
        '(from aistudio.google.com/apikey):" default answer "" with hidden answer '
        'with title "JARVIS setup" buttons {"Cancel", "Save"} default button "Save")'
    )
    r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    key = r.stdout.strip()
    if r.returncode != 0 or not key:
        return None
    subprocess.run([
        "security", "add-generic-password",
        "-a", "jarvis", "-s", KEYCHAIN_SERVICE, "-w", key, "-U",
    ])
    return key


def main():
    key = os.environ.get("JARVIS_API_KEY") or get_api_key()
    if not key:
        alert("No API key entered, so JARVIS can't start. Open the app again to retry.")
        return
    os.environ["JARVIS_API_KEY"] = key
    sys.argv = [sys.argv[0], "--voice"]

    import jarvis_mac
    jarvis_mac.main()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        alert("JARVIS hit an error. Details are in ~/Library/Logs/JARVIS.log")
