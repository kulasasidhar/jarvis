#!/bin/bash
# Builds JARVIS.app and JARVIS.dmg on your Mac.
# Usage:  bash build_dmg.sh     (run inside the folder with jarvis_mac.py and jarvis_app.py)
set -e
cd "$(dirname "$0")"

APP_NAME="JARVIS"

if ! command -v brew >/dev/null 2>&1; then
  echo "Homebrew is required first. Install it from https://brew.sh"; exit 1
fi

echo "==> Installing audio library (portaudio)..."
brew list portaudio >/dev/null 2>&1 || brew install portaudio

echo "==> Creating build environment..."
python3 -m venv build_env
source build_env/bin/activate
pip install --upgrade pip
pip install openai SpeechRecognition pyinstaller
CFLAGS="-I$(brew --prefix)/include" LDFLAGS="-L$(brew --prefix)/lib" pip install pyaudio

echo "==> Building $APP_NAME.app..."
rm -rf build dist
pyinstaller --noconfirm --windowed --name "$APP_NAME" \
  --osx-bundle-identifier com.jarvis.assistant \
  --collect-all openai --collect-all speech_recognition --collect-all certifi \
  --hidden-import jarvis_mac \
  jarvis_app.py

echo "==> Adding microphone permission text..."
PLIST="dist/$APP_NAME.app/Contents/Info.plist"
plutil -replace NSMicrophoneUsageDescription -string "JARVIS needs the microphone to hear your commands." "$PLIST"
plutil -replace NSAppleEventsUsageDescription -string "JARVIS controls apps like Music and Notes for you." "$PLIST"

echo "==> Signing app (local signature)..."
codesign --force --deep --sign - "dist/$APP_NAME.app"

echo "==> Creating DMG..."
STAGE="dist/dmg_stage"
rm -rf "$STAGE"
mkdir -p "$STAGE"
cp -R "dist/$APP_NAME.app" "$STAGE/"
ln -s /Applications "$STAGE/Applications"
hdiutil create -volname "$APP_NAME" -srcfolder "$STAGE" -ov -format UDZO "dist/$APP_NAME.dmg"
rm -rf "$STAGE"

echo ""
echo "Done! Your installer is at: $(pwd)/dist/$APP_NAME.dmg"
open dist || true
