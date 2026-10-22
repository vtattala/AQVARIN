# Raspberry Pi 4 + Camera Module 3

The Pi sends camera frames into AQVARIN's **Live** tab over the local network.
Choose preview-only to see the camera without loading any AI models. To analyze
it, AQVARIN forwards fresh frames to the existing analysis server selected in
Settings. This setup does not run the detection models on the Pi.

```
Camera Module 3 → Pi 4 camera service → AQVARIN Live preview
                                      ↓ when analysis is started
                              Existing analysis computer → results in AQVARIN
```

## First boot without a monitor: SSH from a Mac

1. Power off before touching the camera ribbon cable or inserting/removing the
   microSD card. Pi 4 uses the standard 15-pin camera connector, not the Pi 5
   mini connector. Follow the official camera installation guide linked below.
2. Insert the microSD card into a reader attached to the Mac. In Raspberry Pi
   Imager choose Pi 4 and Raspberry Pi OS Lite (64-bit), then the correct card.
   Writing the OS erases that selected card.
3. Set a hostname (these examples use `aqvarin-pi`), username (`brian` here),
   your own password, location, and Wi-Fi credentials. Enable SSH password
   authentication under Remote access. Raspberry Pi Connect is optional and
   is not needed for this setup.
4. For a beach setup, a phone hotspot can provide the shared network. Enter
   its exact SSID/password and connect the Mac to that hotspot too. Test local
   device-to-device connectivity before leaving: some hotspots isolate clients.
   Keep the hotspot enabled. Home Wi-Fi also works if both devices join it.
5. Finish writing, eject the card, insert it into the powered-off Pi, and power
   on. Allow a few minutes for first boot. Open Terminal **on the Mac**:

```sh
ssh brian@aqvarin-pi.local
```

Use the username/hostname chosen in Imager if different. Enter the Pi password
locally when prompted; SSH shows no characters while you type. Once logged in,
the following commands run **on the Pi**, inside that SSH terminal.

## Install the camera packages on the Pi

Use Raspberry Pi OS system Python. Do not install the full ML requirements on
the Pi just to stream the camera. Picamera2 and libcamera should come from apt.

```sh
sudo apt update
sudo apt install -y python3-picamera2 rpicam-apps-lite curl
rpicam-hello --list-cameras
```

The camera list should identify Camera Module 3's IMX708 sensor. If it finds no
camera, shut down, disconnect power, check cable orientation/seating using the
official guide, reconnect and repeat the camera list. Close other camera apps.
The legacy `picamera` stack and `cv2.VideoCapture(0)` are not used here.

## Start the AQVARIN Pi camera service

You can download only the small camera script instead of the model repository:

```sh
mkdir -p ~/aqvarin-camera
cd ~/aqvarin-camera
curl -fL https://raw.githubusercontent.com/vtattala/AQVARIN/brian-branch/scripts/pi_camera.py -o pi_camera.py
python3 pi_camera.py --token-file ./camera-token.local
```

Alternatively, from a full repository checkout run `python3 scripts/pi_camera.py`.
The service prints **Pi camera ready** and a camera token. Keep that terminal
running. Copy the token into the app's camera-token field. It is retained in a
local file with mode 0600 and reused after restarts; it is not a Git-tracked
configuration. The app does not persist the token across Live-screen unmounts.
Ctrl+C stops the service and releases the hardware camera.

In a second Mac Terminal window, SSH in again and run `hostname -I` if you need
the Pi's numeric Wi-Fi address. The camera address is usually:

```
http://aqvarin-pi.local:8001
```

or `http://PI_WIFI_IP:8001`. Use the Pi address, not the Mac's or phone's address.

## See it in the app

1. Open **Live** in the current web preview or a rebuilt native app.
2. Choose **Raspberry Pi camera** under Camera source.
3. Enter the camera address above and the token printed by the Pi.
4. Tap **Test Pi connection**. It should report the camera size and capture FPS.
5. Tap **Preview Pi camera without analysis** to verify the actual camera image.
   This mode sends no frames to an analysis server and performs no detection.
6. Stop preview. For AI results, start the existing Python analysis server on
   the analysis computer and set its network-reachable port-8000 URL in the
   app's Settings. Then return to Live and tap **Start live camera**.

The Pi, app device and analysis computer must be mutually reachable. For beach
use with the current architecture, bring the analysis computer and connect it
to the same hotspot. The Pi and phone alone can provide the camera preview, but
this change does not provide standalone Pi/phone AI inference. Download/install
packages and models before leaving. Power the Pi with a suitable stable supply.
No internet service is needed for the local camera transport once installed;
Discover's remote maps and forecasts still need internet.

## Controls and limits

The default is 1280×720 at 10 capture FPS, hardware MJPEG encoding on Pi 4, and
continuous autofocus when the camera advertises it. For a fixed distant view,
try `--focus infinity` (manual lens position 0); check sharpness in the preview.
Use `--rotation 180` for an upside-down installation. Use `--width 640 --height
480 --fps 5` if the network struggles. Capture FPS is not analyzed FPS: model
speed, image size and Wi-Fi determine the actual detection rate. No physical
Pi 4 latency/accuracy benchmark is asserted.

Only the latest JPEG is retained in Pi memory. App preview polls about three
times per second and requests fresh frames for analysis; there is one request
at a time per app camera source and one model frame in flight per session.
Sequence headers, JPEG validation, a 2 MB cap and a two-second age check reject
repeated/stale/invalid frames. A disconnected camera reports unavailable rather
than continuing to present its last image as live. Preview and analyzed frames
remain separate so boxes belong to the exact analyzed frame.

The service requires a bearer token and allows local app origins. It has no
public hosting, recording, audio, SSH management or remote camera-control API.
Use it on a trusted LAN/hotspot, not through public port forwarding. HTTP
transports the feed on that LAN; HTTPS deployments require an appropriate TLS
proxy/certificate. An HTTPS webpage may block an HTTP camera; use the native
app or localhost web preview. Approve local-network access if the browser/phone
asks. iOS local-network permission text is included and needs a native rebuild.
Old APKs do not gain the Pi camera option without rebuilding.

Stopping the app preview stops requests and analysis sessions. The Pi service
continues capturing until Ctrl+C or process shutdown; its retained frame is
memory-only. Leaving Live/backgrounding the app aborts its requests. No images
or tokens are added to analysis jobs. Existing device-camera and upload modes
are preserved.

## Validation and hardware acceptance

Protocol tests run without Picamera2 or heavy ML dependencies:

```sh
python3 -m unittest discover -s tests -p test_pi_camera.py -v
cd mobile
npm run test:discover
npm run typecheck
```

These cover token enforcement, local CORS/preflight, fresh-frame sequencing,
stopped/stale feeds, JPEG validation, byte limits and client errors. The
web/Android/iOS JavaScript exports are checked. A simulated JPEG service can
verify app transport/preview, but is not physical-camera validation.

The remaining hardware acceptance check is on the user's Pi: detect IMX708,
start the service, preview a real scene, test focus/rotation, unplug/reconnect
only after power-off, and then check end-to-end analysis with the existing
server. Camera focus, power stability, outdoor visibility, hotspot routing and
actual model performance still require that check.

Official references:

- https://www.raspberrypi.com/software/
- https://www.raspberrypi.com/documentation/computers/getting-started.html
- https://www.raspberrypi.com/documentation/accessories/camera.html
- https://www.raspberrypi.com/documentation/computers/camera_software.html
- https://datasheets.raspberrypi.com/camera/picamera2-manual.pdf
