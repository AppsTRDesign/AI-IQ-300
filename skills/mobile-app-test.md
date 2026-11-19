---
name: mobile-app-test
title: Build and test a mobile app
title_tr: Mobil uygulamayı derle ve test et
title_en: Build and test a mobile app
description: Builds and tests Android / iOS apps (Flutter, React Native, Expo, Capacitor, Kotlin / Swift native) on an emulator or simulator, with UI flows, screenshots and a report; web-based apps also at phone size in a real browser.
description_tr: Android / iOS uygulamalarını (Flutter, React Native, Expo, Capacitor, Kotlin / Swift) emülatör veya simülatörde derler ve test eder; UI akışları, ekran görüntüleri ve rapor verir. Web tabanlı uygulamalar gerçek tarayıcıda telefon boyutunda da test edilir.
description_en: Builds and tests Android / iOS apps (Flutter, React Native, Expo, Capacitor, Kotlin / Swift native) on an emulator or simulator, with UI flows, screenshots and a report; web-based apps also at phone size in a real browser.
triggers: \b(android|ios|iphone|apk|ipa|flutter|react native|expo|capacitor|kotlin|swift|emülatör|emulator|simülatör|simulator)\b|mobil uygulama|mobile app
tools: mobile_env, run, start, stop, write_file, read_file, edit_file, list_dir, search_code, web_search, fetch_url, system_info, inspect_media, browser_navigate, browser_snapshot, browser_click, browser_type, browser_form, browser_check, browser_inspect, browser_screenshot, browser_batch, web_screenshot, todo
---
Goal: the app really runs and its main flows are proven with screenshots and test output. Never say "tested" without
a tool result that shows it.

## 1. Plan (todo) and the machine
`mobile_env action=status` and `system_info` once. todo: build, environment, install, flows, screenshots, report.

## 2. Scaffold right (new projects)
- Expo + TypeScript: `npx create-expo-app@latest <name> --template blank-typescript --yes` (with expo-router tabs:
  `--template tabs`). Never `--template typescript`: that downloads the TypeScript compiler package as the "app".
- Then run every command with cwd=<name> (not `cd <name> &&`), add packages with `npx expo install <pkg>` (it picks
  versions that match the SDK), web target: `npx expo install react-dom react-native-web @expo/metro-runtime`.
- zustand, axios and expo-* ship their own types: no `@types/...` for them.
- Write the screens, types and data files the request names before testing; check them with `npx tsc --noEmit`.
- Styling: StyleSheet.create with a theme file (colors, spacing, radius, shadows) works everywhere. NativeWind only
  with its full setup (`nativewind/babel` + `withNativeWind` in metro.config.js, `global.css` imported in the root
  layout, tailwind content paths): `className` without it renders as unstyled raw text on web. The screenshot check
  reports such a page as UNSTYLED - fix the styles before testing flows.
- Images: product photos via stock_photo into assets/ (or a local placeholder), never made-up URLs.

## 3. The fastest real test first
| Project | Fast check (minutes) | Full check (device) |
|---|---|---|
| Expo / React Native with web | `npx expo start --web` (start) -> browser at 390x844 | Android: `npx expo run:android` or EAS build, then emulator |
| Flutter | `flutter test`, then `flutter run -d chrome` (start) -> browser at phone size | `flutter build apk --debug` -> emulator |
| Capacitor / Ionic / PWA | `npm run dev` (start) -> browser at phone size | `npx cap sync android`, `cd android && ./gradlew assembleDebug` |
| Kotlin / Java native | `./gradlew test` | `./gradlew assembleDebug` -> app/build/outputs/apk/debug/*.apk |
| Swift / iOS | macOS only: `xcodebuild test -scheme X -destination 'platform=iOS Simulator,name=iPhone 15'` | `xcrun simctl boot`, `xcrun simctl install booted X.app`, `xcrun simctl io booted screenshot` |
In the browser (always, without being asked): browser_navigate the address the start output prints - its result lists
console errors and failed requests (a 500 on `entry.bundle` = Metro could not build: read the start output, fix the
config / import, restart with `-c`). Fix every error and reload until the page check is clean, then go through the
main flows with browser_click / browser_type (each action reports new errors too), and web_screenshot at 390 px wide.
Only one Expo server at a time: stop the earlier one before starting again (8081, 8082... pile up).

## 4. Android emulator (Windows, macOS, Linux)
Only after the fast check above passed, and only when the user asked for a device / emulator / APK test or the
project has no web target (a request that mentions an emulator / emulation / device test counts as asking). Then
install what is missing yourself - everything goes into the app's data folder, no admin:
1. `mobile_env action=status`. Java older than 17 or missing: `mobile_env action=java` (portable Temurin 17, no
   installer - never winget/MSI for it: the Windows Installer lock (1618) makes those fail).
2. No emulator yet: `mobile_env action=setup` (Android SDK, emulator, Pixel AVD and Maestro into the app's data
   folder, no admin; several GB once - tell the user it takes a while).
3. `mobile_env action=start` (headless=true on a server). It fails without CPU virtualization: say so (BIOS VT-x /
   AMD-V, Windows Hypervisor Platform) and fall back to the browser test.
4. Build the debug APK (table above), `mobile_env action=install path=...apk`, `action=launch package=<applicationId>`
   (from build.gradle / app.json).
5. `mobile_env action=screenshot path=shots/01-start.png`, then inspect_media on it to check what is on screen.

## 5. UI flows (Maestro)
Write one .yaml per main flow (login, add an item, navigate, form errors) and run `mobile_env action=flow path=...`:
```yaml
appId: com.example.app
---
- launchApp
- tapOn: "Sign in"
- inputText: "test@example.com"
- tapOn: "Password"
- inputText: "Test1234!"
- tapOn: "Log in"
- assertVisible: "Welcome"
- takeScreenshot: shots/02-after-login
```
A failing step: read its output, fix the app or the flow (a different label, wait with `- waitForAnimationToEnd`),
run again; the same failure twice means take another route (check the label in a screenshot first).

## 6. Fix loop
Build errors: read the first error, not the last line. Gradle: JDK version (17), `ANDROID_HOME` (mobile_env sets it),
missing SDK platform (`sdkmanager "platforms;android-34"` comes with setup). Metro / Expo: clear cache
(`npx expo start -c`). Flutter: `flutter doctor -v` names what is missing.

## 7. Report
Table: flow, steps, result, screenshot path, error line if any; device (AVD / simulator / browser size); how to run it
again (exact commands); what could not be tested on this machine (iOS on Windows / Linux) and how to do it.
