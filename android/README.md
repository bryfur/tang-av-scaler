# The Android app

The board's web page as an app: every setting (the same names, defaults and resets), the status,
a screen capture saved to the phone's pictures, and the board's maintenance (Wi-Fi, firmware
update, the scaler's tables, the logs). Three pages, swiped between: Settings, Status, Board.

It reaches the board either way, whichever works:

- **Wi-Fi**: the board's HTTP API, found by mDNS (`_http._tcp` with `board=tang-av-scaler`:
  `firmware/xiao-wifi/main/wifi.c`), or at an address typed in.
- **Bluetooth LE**: an L2CAP channel (LE credit-based, PSM 0x81) that the firmware passes to its own
  web server (`firmware/xiao-wifi/main/ble.c`), so the requests are the same bytes as over Wi-Fi.
  No pairing.

Wi-Fi first; Bluetooth when the network does not reach the board; when the board stops answering it
looks again both ways. The chip under the title says which, and choosing another board or way is a
tap on it.

Kotlin and Jetpack Compose; Android 10 (API 29: `createInsecureL2capChannel`) or later, built for
API 37. On Android 17 it asks for local network access (else the system asks which device, each
time) and for Bluetooth's nearby-devices permission (not location).

## Building

The toolchain is a container (`tools/android-container`: JDK 21, the SDK parts AGP asks for):

    tools/android-container/build.sh                        # once, on the Docker host
    cd android && ../tools/android-container/androidrun ./gradlew assembleDebug
    ../tools/android-container/androidrun adb install -r app/build/outputs/apk/debug/app-debug.apk

`assembleRelease` builds the minified release; without the signing key (below) it comes out unsigned.

## Releases

A tag `app-vX.Y.Z` pushed to GitHub builds the signed APK and publishes it as a GitHub release
(`.github/workflows/android.yml`; every push to `android/` builds it too, unsigned). The version name
is the tag's, the version code the workflow's run number.

    git tag app-v0.1.0 && git push origin app-v0.1.0

The signing key never enters the repository. The workflow takes it from four repository secrets
(Settings → Secrets and variables → Actions):

| Secret | Value |
|---|---|
| `TANGAV_KEYSTORE_BASE64` | the PKCS #12 keystore, base64 (`base64 -w0 release.jks`) |
| `TANGAV_STORE_PASSWORD` | its password |
| `TANGAV_KEY_ALIAS` | `tangav` |
| `TANGAV_KEY_PASSWORD` | the key's password (the same as the store's) |

The certificate (CN=Tang AV Scaler), SHA-256
`2ece5e4f0af86d15719d0fc2fcb70736f52004c0001c97776f862ce1a3f27cd9`. Keep the keystore safe: an update
signed with any other key will not install over the app.
