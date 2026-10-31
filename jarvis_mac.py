"""
JARVIS for macOS - control your MacBook by voice or text, like Siri.

Uses a FREE Google Gemini API key by default (get one at https://aistudio.google.com/apikey).
Works with any OpenAI-compatible provider by setting JARVIS_BASE_URL and JARVIS_MODEL.

Run:
  python3 jarvis_mac.py           -> text mode
  python3 jarvis_mac.py --voice   -> say "Jarvis, <command>" (wake word)

What it can do:
  volume, mute, brightness, open/close apps, websites, web search,
  music play/pause/next/previous, Wi-Fi on/off, dark mode, battery,
  screenshots, lock screen, sleep, timers, notes, time/date.
"""

import argparse
import datetime
import inspect
import json
import os
import subprocess
import sys
import threading
from urllib.parse import quote_plus

import openai
from openai import OpenAI

if sys.platform != "darwin":
    sys.exit("This version is for macOS only.")

BASE_URL = os.environ.get(
    "JARVIS_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai/"
)
MODEL = os.environ.get("JARVIS_MODEL", "gemini-2.5-flash")
VOICE_NAME = "Daniel"  # British male voice, very JARVIS. Try "Samantha" etc.

SYSTEM_PROMPT = (
    "You are JARVIS, a witty, polite and highly capable AI assistant running on the "
    "user's MacBook, like the one from Iron Man. Address the user as 'sir' or 'ma'am' "
    "occasionally, with light dry humour. Keep replies to 1-2 short sentences because "
    "they are spoken aloud. When the user asks you to do something on the Mac, call the "
    "matching tool, then confirm briefly. Never claim you did something unless a tool "
    "result says it worked."
)


# ---------- helpers ----------

def osa(script: str) -> str:
    """Run an AppleScript and return its output."""
    r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip() or "AppleScript failed")
    return r.stdout.strip()


def sh(cmd: list) -> str:
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip() or f"{cmd[0]} failed")
    return r.stdout.strip()


def esc(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


def speak(text: str):
    try:
        subprocess.run(["say", "-v", VOICE_NAME, text], check=True)
    except Exception:
        subprocess.run(["say", text])


# ---------- actions ----------

def set_volume(level: int) -> str:
    level = max(0, min(100, int(level)))
    osa(f"set volume output volume {level}")
    return f"Volume set to {level}%"


def get_volume() -> str:
    return f"Volume is {osa('output volume of (get volume settings)')}%"


def set_mute(muted: bool) -> str:
    osa(f"set volume output muted {'true' if muted else 'false'}")
    return "Muted" if muted else "Unmuted"


def change_brightness(direction: str, steps: int = 3) -> str:
    # Key codes 144/145 = brightness up/down (needs Accessibility permission)
    code = 144 if direction == "up" else 145
    for _ in range(max(1, min(16, int(steps)))):
        osa(f'tell application "System Events" to key code {code}')
    return f"Brightness turned {direction}"


def open_app(name: str) -> str:
    sh(["open", "-a", name])
    return f"Opened {name}"


def close_app(name: str) -> str:
    osa(f'tell application "{esc(name)}" to quit')
    return f"Closed {name}"


def open_website(url: str) -> str:
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    sh(["open", url])
    return f"Opened {url}"


def search_web(query: str) -> str:
    sh(["open", f"https://www.google.com/search?q={quote_plus(query)}"])
    return f"Searched Google for: {query}"


def media_control(action: str, app: str = "Music") -> str:
    cmds = {"play_pause": "playpause", "next": "next track", "previous": "previous track"}
    if action not in cmds:
        return "Unknown media action"
    osa(f'tell application "{esc(app)}" to {cmds[action]}')
    return f"{app}: {action}"


def toggle_wifi(on: bool) -> str:
    # Find the Wi-Fi device name (usually en0)
    out = sh(["networksetup", "-listallhardwareports"])
    device = "en0"
    lines = out.splitlines()
    for i, line in enumerate(lines):
        if "Wi-Fi" in line and i + 1 < len(lines):
            device = lines[i + 1].split(":")[-1].strip()
            break
    sh(["networksetup", "-setairportpower", device, "on" if on else "off"])
    return f"Wi-Fi turned {'on' if on else 'off'}"


def toggle_dark_mode() -> str:
    osa('tell application "System Events" to tell appearance preferences '
        "to set dark mode to not dark mode")
    return "Toggled dark mode"


def battery_status() -> str:
    return sh(["pmset", "-g", "batt"]).splitlines()[-1].strip()


def take_screenshot() -> str:
    path = os.path.expanduser(
        f"~/Desktop/Screenshot-{datetime.datetime.now():%Y%m%d-%H%M%S}.png"
    )
    sh(["screencapture", "-x", path])
    return f"Screenshot saved to Desktop as {os.path.basename(path)}"


def lock_screen() -> str:
    sh(["pmset", "displaysleepnow"])
    return "Display sleeping (Mac locks if 'require password' is on)"


def sleep_mac() -> str:
    sh(["pmset", "sleepnow"])
    return "Putting the Mac to sleep"


def set_timer(seconds: int, label: str = "Timer") -> str:
    seconds = int(seconds)

    def done():
        subprocess.run(["osascript", "-e",
                        f'display notification "{esc(label)} is done" with title "JARVIS"'])
        speak(f"Sir, your {label} is done.")

    threading.Timer(seconds, done).start()
    return f"Timer set for {seconds} seconds: {label}"


def create_note(text: str) -> str:
    osa(f'tell application "Notes" to make new note with properties {{body:"{esc(text)}"}}')
    return "Note created in Notes"


def get_time() -> str:
    return datetime.datetime.now().strftime("%A, %d %B %Y, %I:%M %p")


# name -> (function, description, input schema properties, required)
TOOL_TABLE = {
    "set_volume": (set_volume, "Set the Mac output volume (0-100).",
                   {"level": {"type": "integer"}}, ["level"]),
    "get_volume": (get_volume, "Get the current volume.", {}, []),
    "set_mute": (set_mute, "Mute or unmute the Mac.",
                 {"muted": {"type": "boolean"}}, ["muted"]),
    "change_brightness": (change_brightness, "Raise or lower screen brightness.",
                          {"direction": {"type": "string", "enum": ["up", "down"]},
                           "steps": {"type": "integer", "description": "1-16, default 3"}},
                          ["direction"]),
    "open_app": (open_app, "Open an app, e.g. Safari, Notes, Spotify, Calculator.",
                 {"name": {"type": "string"}}, ["name"]),
    "close_app": (close_app, "Quit an app by name.",
                  {"name": {"type": "string"}}, ["name"]),
    "open_website": (open_website, "Open a URL in the default browser.",
                     {"url": {"type": "string"}}, ["url"]),
    "search_web": (search_web, "Search Google in the default browser.",
                   {"query": {"type": "string"}}, ["query"]),
    "media_control": (media_control, "Play/pause, next or previous track.",
                      {"action": {"type": "string", "enum": ["play_pause", "next", "previous"]},
                       "app": {"type": "string", "enum": ["Music", "Spotify"]}},
                      ["action"]),
    "toggle_wifi": (toggle_wifi, "Turn Wi-Fi on or off.",
                    {"on": {"type": "boolean"}}, ["on"]),
    "toggle_dark_mode": (toggle_dark_mode, "Switch between dark and light mode.", {}, []),
    "battery_status": (battery_status, "Get battery percentage and charging state.", {}, []),
    "take_screenshot": (take_screenshot, "Take a screenshot and save it to the Desktop.", {}, []),
    "lock_screen": (lock_screen, "Turn off the display / lock the screen.", {}, []),
    "sleep_mac": (sleep_mac, "Put the Mac to sleep.", {}, []),
    "set_timer": (set_timer, "Set a countdown timer that speaks when done.",
                  {"seconds": {"type": "integer"}, "label": {"type": "string"}},
                  ["seconds"]),
    "create_note": (create_note, "Create a new note in the Notes app.",
                    {"text": {"type": "string"}}, ["text"]),
    "get_time": (get_time, "Get the current date and time.", {}, []),
}


def _make_tool(name, description, props, required):
    # Some providers reject tools with empty parameter lists, so give those a
    # harmless optional placeholder (it is ignored when the tool runs).
    if not props:
        props = {"note": {"type": "string", "description": "Unused. Leave empty."}}
    params = {"type": "object", "properties": props}
    if required:
        params["required"] = required
    return {"type": "function",
            "function": {"name": name, "description": description, "parameters": params}}


TOOLS = [_make_tool(n, d, p, r) for n, (_, d, p, r) in TOOL_TABLE.items()]


def run_tool(name: str, args: dict) -> str:
    entry = TOOL_TABLE.get(name)
    if not entry:
        return f"Unknown tool: {name}"
    fn = entry[0]
    allowed = inspect.signature(fn).parameters
    clean = {k: v for k, v in (args or {}).items() if k in allowed}
    try:
        return fn(**clean)
    except Exception as e:
        return f"Failed: {e}"


# ---------- voice ----------

class Ears:
    def __init__(self):
        import speech_recognition as sr
        self.sr = sr
        self.rec = sr.Recognizer()
        self.mic = sr.Microphone()
        with self.mic as src:
            self.rec.adjust_for_ambient_noise(src, duration=1)

    def listen(self, timeout=None, limit=12):
        with self.mic as src:
            try:
                audio = self.rec.listen(src, timeout=timeout, phrase_time_limit=limit)
            except self.sr.WaitTimeoutError:
                return None
        try:
            return self.rec.recognize_google(audio)
        except self.sr.UnknownValueError:
            return None
        except self.sr.RequestError:
            print("Speech service unavailable (check internet).")
            return None


WAKE = "jarvis"


def next_voice_command(ears: Ears):
    """Wait for the wake word, then return the command that follows."""
    heard = ears.listen(timeout=None, limit=6)
    if not heard or WAKE not in heard.lower():
        return None
    after = heard.lower().split(WAKE, 1)[1].strip(" ,.")
    if after:
        return after
    speak("Yes, sir?")
    return ears.listen(timeout=6, limit=12)


# ---------- brain ----------

def ask_jarvis(client: OpenAI, history: list) -> str:
    """Send the conversation to the model, run any tools it requests, return final text."""
    for _ in range(6):
        resp = client.chat.completions.create(
            model=MODEL,
            max_tokens=2000,
            messages=[{"role": "system", "content": SYSTEM_PROMPT}] + history,
            tools=TOOLS,
        )
        msg = resp.choices[0].message
        calls = msg.tool_calls or []

        entry = {"role": "assistant", "content": msg.content or ""}
        if calls:
            entry["tool_calls"] = [
                {
                    "id": tc.id or f"call_{i}",
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments or "{}",
                    },
                }
                for i, tc in enumerate(calls)
            ]
        history.append(entry)

        if not calls:
            return (msg.content or "").strip() or "Done, sir."

        for i, tc in enumerate(calls):
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            out = run_tool(tc.function.name, args)
            print(f"  [action] {tc.function.name}({args}) -> {out}")
            history.append({
                "role": "tool",
                "tool_call_id": tc.id or f"call_{i}",
                "content": out,
            })
    return "I seem to be going in circles, sir. Please try again."


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--voice", action="store_true")
    args = ap.parse_args()

    key = os.environ.get("JARVIS_API_KEY")
    if not key:
        sys.exit("Set your free Gemini key first:  export JARVIS_API_KEY='your-key'")

    client = OpenAI(api_key=key, base_url=BASE_URL)
    ears = Ears() if args.voice else None
    history = []

    hello = "JARVIS online. Say my name when you need me." if ears else "JARVIS online. How may I help?"
    print("JARVIS:", hello)
    speak(hello)

    while True:
        if ears:
            text = next_voice_command(ears)
            if not text:
                continue
            print("You:", text)
        else:
            try:
                text = input("You: ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break
            if not text:
                continue

        if text.lower().strip(" .") in {"exit", "quit", "goodbye", "bye", "shut down jarvis", "stop"}:
            speak("Goodbye, sir.")
            break

        history.append({"role": "user", "content": text})
        try:
            answer = ask_jarvis(client, history)
        except openai.RateLimitError as e:
            history.pop()
            answer = "I've reached my free usage limit for now, sir. Please try again later."
            print("  [error]", e)
        except openai.AuthenticationError as e:
            history.pop()
            answer = "My API key was rejected, sir. Please check it."
            print("  [error]", e)
        except openai.OpenAIError as e:
            history.pop()
            answer = "I'm having trouble reaching my servers, sir."
            print("  [error]", e)

        # keep memory short so it stays fast
        if len(history) > 24:
            history = history[-24:]
            while history and not (history[0]["role"] == "user" and isinstance(history[0]["content"], str)):
                history.pop(0)

        print("JARVIS:", answer)
        speak(answer)


if __name__ == "__main__":
    main()
