#!/usr/bin/env bash
set -euo pipefail
arch="$1"
for variable in MAC_CERTIFICATE_P12_BASE64 MAC_CERTIFICATE_PASSWORD APPLE_API_KEY_P8_BASE64 APPLE_API_KEY_ID APPLE_API_ISSUER APPLE_TEAM_ID; do
  test -n "${!variable:-}" || { echo "Missing Apple signing configuration: $variable" >&2; exit 1; }
done
app="$(find desktop/src-tauri/target/release/bundle/macos -maxdepth 1 -name '*.app' -print -quit)"
test -n "$app"
mkdir -p release-assets
umask 077
python3 - <<'PY'
import base64,os,pathlib
p=pathlib.Path(os.environ['RUNNER_TEMP'])
for env,name in [('MAC_CERTIFICATE_P12_BASE64','v3-cert.p12'),('APPLE_API_KEY_P8_BASE64','v3-notary.p8')]:
 f=p/name;f.write_bytes(base64.b64decode(os.environ[env]));f.chmod(0o600)
PY
keychain="$RUNNER_TEMP/v3-signing.keychain-db"
password="$(openssl rand -hex 24)"
# Preserve the runner's search list, adding only this job's temporary keychain.
# Merely passing -k during import does not make the identity discoverable to
# subsequent Security.framework operations on every runner image.
security list-keychains -d user > "$RUNNER_TEMP/v3-original-keychains.txt"
cleanup() {
  python3 - "$RUNNER_TEMP/v3-original-keychains.txt" <<'PY'
import pathlib,shlex,subprocess,sys
p=pathlib.Path(sys.argv[1])
if p.exists():
 subprocess.run(['security','list-keychains','-d','user','-s',*shlex.split(p.read_text())],check=False)
PY
  security delete-keychain "$keychain" >/dev/null 2>&1 || true
  rm -f "$RUNNER_TEMP/v3-cert.p12" "$RUNNER_TEMP/v3-notary.p8" "$RUNNER_TEMP/v3-original-keychains.txt"
}
trap cleanup EXIT
printf '%s\n' 'SIGNING_STAGE: create isolated signing keychain'
security create-keychain -p "$password" "$keychain"
security set-keychain-settings -lut 21600 "$keychain"
security unlock-keychain -p "$password" "$keychain"
python3 - "$keychain" "$RUNNER_TEMP/v3-original-keychains.txt" <<'PY'
import pathlib,shlex,subprocess,sys
existing=shlex.split(pathlib.Path(sys.argv[2]).read_text())
subprocess.run(['security','list-keychains','-d','user','-s',sys.argv[1],*existing],check=True)
PY
printf '%s\n' 'SIGNING_STAGE: import PKCS12 identity'
security import "$RUNNER_TEMP/v3-cert.p12" -f pkcs12 -k "$keychain" -P "$MAC_CERTIFICATE_PASSWORD" -T /usr/bin/codesign
printf '%s\n' 'SIGNING_STAGE: grant Apple signing tools access to the private key'
# Match the imported private key directly instead of filtering on the optional
# can-sign attribute (-s). Scope remains ONLY the new, isolated job keychain.
# Never use -A or change the login/system keychain's key permissions.
security set-key-partition-list -S apple-tool:,apple:,codesign: -t private -k "$password" "$keychain" >/dev/null
printf '%s\n' 'SIGNING_STAGE: verify Developer ID identity is available'
identity="$(security find-identity -v -p codesigning "$keychain" | sed -n 's/.*"\(Developer ID Application:.*\)".*/\1/p' | head -1)"
test -n "$identity" || { echo 'No valid Developer ID Application identity found in temporary keychain' >&2; exit 1; }
printf '%s\n' 'SIGNING_STAGE: sign and verify native application'
codesign --force --options runtime --timestamp --keychain "$keychain" --sign "$identity" "$app/Contents/MacOS/vibez3"
codesign --force --options runtime --timestamp --entitlements desktop/src-tauri/macos/Entitlements.plist --keychain "$keychain" --sign "$identity" "$app"
codesign --verify --deep --strict --verbose=2 "$app"
codesign -dv --verbose=4 "$app" 2>&1 | grep "TeamIdentifier=$APPLE_TEAM_ID"
zip="$PWD/release-assets/VibeZ-3.0.0-macOS-$arch.zip"
ditto -c -k --sequesterRsrc --keepParent "$app" "$zip"
printf '%s\n' 'SIGNING_STAGE: notarize application'
xcrun notarytool submit "$zip" --key "$RUNNER_TEMP/v3-notary.p8" --key-id "$APPLE_API_KEY_ID" --issuer "$APPLE_API_ISSUER" --wait --timeout 40m --output-format json > "release-assets/notary-app-$arch.json"
python3 -c 'import json,sys; assert json.load(open(sys.argv[1]))["status"] == "Accepted"' "release-assets/notary-app-$arch.json"
xcrun stapler staple "$app";xcrun stapler validate "$app"
spctl --assess --type execute --verbose=4 "$app"
rm "$zip";ditto -c -k --sequesterRsrc --keepParent "$app" "$zip"
stage="$RUNNER_TEMP/v3-dmg";mkdir -p "$stage";ditto "$app" "$stage/VibeZ 3.app";ln -s /Applications "$stage/Applications"
dmg="$PWD/release-assets/VibeZ-3.0.0-macOS-$arch.dmg"
hdiutil create -volname 'VibeZ 3' -srcfolder "$stage" -ov -format UDZO "$dmg"
codesign --force --timestamp --keychain "$keychain" --sign "$identity" "$dmg"
printf '%s\n' 'SIGNING_STAGE: notarize disk image'
xcrun notarytool submit "$dmg" --key "$RUNNER_TEMP/v3-notary.p8" --key-id "$APPLE_API_KEY_ID" --issuer "$APPLE_API_ISSUER" --wait --timeout 40m --output-format json > "release-assets/notary-dmg-$arch.json"
python3 -c 'import json,sys; assert json.load(open(sys.argv[1]))["status"] == "Accepted"' "release-assets/notary-dmg-$arch.json"
xcrun stapler staple "$dmg";xcrun stapler validate "$dmg"
printf '%s\n' 'SIGNING_OK: Developer ID, notarization and stapled tickets verified'
