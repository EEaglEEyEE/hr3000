#!/usr/bin/env bash
# Android-App „HR3000 Kiosk“ (kiosk-android/) bauen – auf dem Mac, nicht auf dem Server.
#
#   bash scripts/build-kiosk-android.sh test      Unit-Tests, Abdeckung, Lint
#   bash scripts/build-kiosk-android.sh device    Tests zusätzlich auf angeschlossenem Gerät/Emulator
#   bash scripts/build-kiosk-android.sh debug     Debug-APK (de.hr3000.kiosk.debug, erlaubt http://localhost)
#   bash scripts/build-kiosk-android.sh release   signierte APK und AAB nach kiosk-android/dist/
#   bash scripts/build-kiosk-android.sh keystore  Upload-Schlüssel einmalig anlegen
#
# Voraussetzungen: JDK 17+ (getestet mit 21), Android SDK (ANDROID_HOME), Plattform 36.
# Signierschlüssel nie im Repo: Datei unter ~/.config/hr3000-kiosk/, Passwort im macOS-Schlüsselbund
# (Dienst „hr3000-kiosk-upload-keystore“). Ohne Schlüssel ist er für Updates verloren → sichern!
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
APP="$ROOT/kiosk-android"
KEY_DIR="${HR3000_KIOSK_KEY_DIR:-$HOME/.config/hr3000-kiosk}"
KEYSTORE="$KEY_DIR/upload-keystore.p12"
KEYCHAIN_SERVICE="hr3000-kiosk-upload-keystore"
ALIAS="hr3000-kiosk"

say() { printf '\n=== %s\n' "$*"; }
fail() { printf '\nABBRUCH: %s\n' "$*" >&2; exit 1; }

# Hinter einer TLS-prüfenden Firewall kennt Java das Firmenzertifikat nicht: eigenen Truststore verwenden,
# erzeugt aus ~/ca-bundle-corp.pem (siehe docs/technik.md, „Android-App für Kiosk-Tablets“).
TRUSTSTORE="${HR3000_JAVA_TRUSTSTORE:-$HOME/.build-caches/java-truststore/corp-truststore.p12}"
if [ -f "$TRUSTSTORE" ]; then
  export JAVA_OPTS="-Djavax.net.ssl.trustStore=$TRUSTSTORE -Djavax.net.ssl.trustStorePassword=changeit -Djavax.net.ssl.trustStoreType=PKCS12"
  export GRADLE_OPTS="$JAVA_OPTS"
fi

gradle() { (cd "$APP" && ./gradlew --no-daemon -q "$@"); }

version() { sed -n 's/^ *versionName = "\(.*\)"/\1/p' "$APP/app/build.gradle.kts"; }

read_keystore_password() {
  security find-generic-password -s "$KEYCHAIN_SERVICE" -w 2>/dev/null || fail "Kein Passwort im Schlüsselbund ($KEYCHAIN_SERVICE) – erst: bash scripts/build-kiosk-android.sh keystore"
}

case "${1:-}" in
  test)
    say "Unit-Tests, Abdeckung, Lint"
    gradle testDebugUnitTest createDebugUnitTestCoverageReport lintDebug
    echo "Abdeckung: $APP/app/build/reports/coverage/test/debug/index.html"
    ;;
  device)
    say "Tests auf dem Gerät (adb devices muss eines zeigen)"
    gradle connectedDebugAndroidTest
    ;;
  debug)
    say "Debug-APK"
    gradle testDebugUnitTest assembleDebug
    echo "$APP/app/build/outputs/apk/debug/app-debug.apk"
    ;;
  keystore)
    [ -f "$KEYSTORE" ] && fail "Schlüssel existiert schon: $KEYSTORE (nie überschreiben – Updates bräuchten ihn)"
    mkdir -p "$KEY_DIR" && chmod 700 "$KEY_DIR"
    say "Upload-Schlüssel anlegen ($KEYSTORE)"
    HR3000_KIOSK_KEYSTORE_PASSWORD="$(openssl rand -hex 32)"
    export HR3000_KIOSK_KEYSTORE_PASSWORD
    # Passwort über stdin in den Schlüsselbund, nicht als Argument (wäre in der Prozessliste sichtbar)
    printf 'add-generic-password -U -s %s -a %s -w %s\n' "$KEYCHAIN_SERVICE" "$USER" "$HR3000_KIOSK_KEYSTORE_PASSWORD" | security -i >/dev/null
    keytool -genkeypair -storetype PKCS12 -keystore "$KEYSTORE" -alias "$ALIAS" -keyalg RSA -keysize 4096 \
      -validity 10000 -dname "CN=HR3000 Kiosk, O=HR3000" -storepass:env HR3000_KIOSK_KEYSTORE_PASSWORD >/dev/null
    chmod 600 "$KEYSTORE"
    echo "Fertig. Datei und Schlüsselbund-Eintrag „$KEYCHAIN_SERVICE“ zusätzlich im Passwort-Manager sichern."
    ;;
  release)
    [ -f "$KEYSTORE" ] || fail "Kein Schlüssel unter $KEYSTORE – erst: bash scripts/build-kiosk-android.sh keystore"
    HR3000_KIOSK_KEYSTORE_PASSWORD="$(read_keystore_password)"
    export HR3000_KIOSK_KEYSTORE="$KEYSTORE" HR3000_KIOSK_KEYSTORE_PASSWORD HR3000_KIOSK_KEY_ALIAS="$ALIAS"
    say "Tests und Release-Build $(version)"
    gradle testDebugUnitTest lintRelease assembleRelease bundleRelease
    mkdir -p "$APP/dist"
    cp "$APP/app/build/outputs/apk/release/app-release.apk" "$APP/dist/hr3000-kiosk-$(version).apk"
    cp "$APP/app/build/outputs/bundle/release/app-release.aab" "$APP/dist/hr3000-kiosk-$(version).aab"
    say "Signatur prüfen"
    "$ANDROID_HOME/build-tools/$(ls "$ANDROID_HOME/build-tools" | sort -V | tail -1)/apksigner" verify --print-certs "$APP/dist/hr3000-kiosk-$(version).apk" | grep -E "Signer #1 certificate (DN|SHA-256)"
    ls -l "$APP/dist/"
    ;;
  *)
    sed -n '2,12p' "$0"
    exit 1
    ;;
esac
