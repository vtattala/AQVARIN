# AQVARIN on Pixel 6

## Install the prepared APK over USB

1. Connect the Pixel with a **USB data cable** and unlock it.
2. On the phone, enable **Developer options → USB debugging**. Accept **Allow
   USB debugging** for this computer when the phone asks.
3. Double-click **Install on Pixel 6.cmd** in the project root. This installs
   `outputs/android/AQVARIN-Pixel6-test.apk`, starts the computer's analysis
   server, forwards the API over USB and opens AQVARIN.
4. In AQVARIN Settings, the server address should be
   `http://127.0.0.1:8000`. Press **Check connection**.

The app has its JavaScript bundled, so it can launch without Expo Go, Metro or
an Expo account. Identification, drowning and rip-current inference still run
on this computer. Keep the computer awake and USB connected while analyzing.
The model is not running offline on the phone.

After reconnecting USB or restarting the computer, run **Connect Pixel USB.cmd**
to restore API forwarding. This does not reinstall or clear app data.

## Permissions and checks

- **Live:** press Start live camera and grant camera access when Android asks.
  Try rear and front cameras, check that analyzed-frame numbers increment,
  then Stop and confirm the camera indicator disappears.
- **Monitor:** choose a video through Android's file picker and run analysis.
  AQVARIN receives access to the selected file; it does not require access to
  the whole media library or all-files access. Verify playback and warnings.
- Camera access plus normal Internet/network-state, wake-lock and vibration
  support are packaged. Microphone, broad storage/media permissions and overlay
  permission are blocked. The final APK permission list is saved in
  `outputs/android/verification.json`.
- Start/stop, background/foreground, rotate, deny camera permission, and
  reconnect USB should all be exercised on the actual phone.

On a physical Android device, the runtime camera prompt and video picker still
need a human acceptance check. Building and inspecting an APK does not verify
camera performance on a Pixel. Analysis speed depends on the computer/server.

## Optional same-Wi-Fi testing

USB forwarding avoids Wi-Fi and firewall setup. For untethered testing, use a
server URL such as `http://COMPUTER_LAN_IP:8000` in Settings while the phone and
computer are on the same private Wi-Fi and the API port is reachable. No
Windows firewall rules or public exposure are automatically created. A native
APK can use the local HTTP API; web-camera HTTPS restrictions do not apply to
the native camera module.

## Rebuild the latest source

Double-click **Build Android APK.cmd**. It uses Android Studio's existing JDK
and SDK, stages a copy under `%USERPROFILE%\.aqvarin-build\mobile` to avoid
OneDrive/apostrophe and long-path build issues, and produces a standalone
arm64-v8a APK for the Pixel 6. Logs and SHA-256 metadata are under
`outputs/android`. The APK uses the local Android debug signing key for
private testing; this is not a Play Store production release.

Useful command-line options:

```
.venv\Scripts\python.exe scripts/build_android.py
.venv\Scripts\python.exe scripts/install_pixel.py
.venv\Scripts\python.exe scripts/install_pixel.py --connect-only
```

If more than one phone is connected, select one explicitly with `--serial`.
The installer never selects an emulator automatically. It does not enable
debugging on the phone, bypass its authorization prompt, uninstall an existing
app, grant permissions silently, or clear app data.
