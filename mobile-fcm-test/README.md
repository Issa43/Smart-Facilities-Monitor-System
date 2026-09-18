# SFLMS real FCM E2E harness

This is an isolated Android/Kotlin verification app. It initializes Firebase,
obtains an FCM registration token, registers that token with the existing SFLMS
human-authenticated device endpoint, and displays safely limited notification
metadata. It is not a production SFLMS mobile application.

## Security boundaries

- `app/google-services.json` and `local.properties` are Git-ignored.
- Firebase Admin credentials never belong in this directory.
- FCM tokens and human JWTs must not be printed, logged, committed, or persisted.
- The JWT field is password-masked and remains only in the activity process.
- Cleartext HTTP is accepted only by the client validator for loopback addresses,
  intended for `adb reverse`; non-loopback endpoints must use HTTPS.

## Local verification

Set `JAVA_HOME`, `ANDROID_HOME`, and optionally `GRADLE_USER_HOME`, then run:

```powershell
.\gradlew.bat testDebugUnitTest assembleDebug lintDebug
.\gradlew.bat connectedDebugAndroidTest
```

With one authorized physical device attached:

```powershell
adb reverse tcp:8000 tcp:8000
adb install -r app\build\outputs\apk\debug\app-debug.apk
```

Open the app, allow notifications, enter a valid existing SFLMS human access
token, and register. The app never displays the FCM registration token.
