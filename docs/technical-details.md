# Technical details

Background for [`keymap_patch.py`](../keymap_patch.py). You do not need any of this to use the patch; see the [README](../README.md) for that.

## The software

All supported programs share one code base; only the name, the keyboard layouts and some details differ. They are Electron apps (Electron 4.0.0). The JavaScript and HTML are packed into `resources\app.asar`, and parts of the JavaScript are obfuscated (javascript-obfuscator string arrays). The UI is Angular 2.4 and loads its HTML templates at runtime. The "3M" versions of the AL75, AL65 Wireless, AL70, Lucky65, D75 and SK65 all talk to the USB device ID `0603:0351`.

The Womier SK65 software is a copy of the Lucky65 V1 software: the same function table, and the same key list except the Insert key, where the SK65 has a knob. It only offers the ANSI layout; the Lucky65 software also has ISO and split space bar layouts.

An asar archive is a JSON index (name, offset and size of every file) followed by the file contents. The script reads the index, locates the files it needs and replaces byte patterns inside them. Every replacement has exactly the same length as the original, so no offset changes and the archive does not need to be rebuilt. Where a replacement is shorter, it is padded with spaces at a place where whitespace has no effect.

Safety checks:

- A part of a patch is only written if its original occurs exactly once in its file and its replacement does not occur at all. It counts as applied if it is the other way round. Anything else makes the patch "not available in this software".
- Without a patch option, the script only reads the file and shows the status.
- If an explicitly selected patch is not available, the script stops before writing anything. With `--all`, it skips that patch, and it stops with an error if no patch fits at all, e.g. for the wrong file.
- Right before writing, the script reads every position again and stops if the file has changed in the meantime.
- If a write fails, the script restores the bytes it has already written, so a patch is never left half-applied.
- Wrong paths, folders, files that are not asar archives, read-only files and files locked by the running software get a plain message instead of a Python traceback.

## `--iso`: ISO key

The software stores key assignments as internal codes (`K1`, `K2`, …). The table `AllFunctionMapping` in `backend/others/SupportData.js` maps them to the codes sent to the keyboard. There is no entry for the Non-US Backslash (USB HID usage `0x64`). Editing a saved profile (`.KeyAssign` file) therefore does not help either.

The patch repurposes the function button "Benchmark" (`K44`). Despite its English label, it is "Browser Favorites" (Chinese: 瀏覽器收藏); the label is a translation error.

| File | Before | After |
|---|---|---|
| `backend/others/SupportData.js` | `'hid':0xad,` (Browser Favorites) | `'hid':0x64,` (Non-US Backslash) |
| `components/i18n_Localization.js`, entry `BROWSERCOLLECT` | EN `Benchmark`, CH `瀏覽器收藏`, CN `浏览器收藏`, IT `Riferimento`, ES `Punto de referencia` | EN `ISO-Key <>\|`, CH `ISO鍵 <>\|`, CN `ISO键 <>\|`, IT `Tasto ISO <>\|`, ES `Tecla ISO <>\|` |

The new labels are shorter; the rest is filled with spaces inside the JavaScript code, outside the quotes.

Side effect: Browser Favorites is no longer available while the patch is applied. Windows passes it on to the active browser, and most browsers ignore it. After a software update, the unpatched software sends `0xAD` again for that key as soon as you change any assignment.

## `--fn-key`: Fn key

In `components/app.component.html`, the clickable areas over the keyboard picture have this binding:

```
[style.pointer-events]="item === 'Custom_Fnkey'?'none':'auto'"
```

The patch changes `'none'` to `'auto'`. The firmware treats Fn as an ordinary code in the keymap: the factory keymap has `0xFE` at the Fn position, and the software's "Fn" button (`K189`) sends the same `0xFE` ("Fn2", `K190`, sends `0xFF`). The software already handles a key assigned to Fn: it puts it on the base layer and on the Fn layer.

Only the AL75 V2 and Lucky65 V1 builds contain this lock. In the other programs, the Fn key has a normal clickable area and no lock.

## `--fn-layers`: Fn layers

The layer buttons Fn and Fn2 above the keyboard picture have this binding:

```
[style.pointer-events]="KeyBoardManager.getTarget().fnBtnStatus[i] ? 'auto' : 'none'"
```

`fnBtnStatus` is only set when Fn or Fn2 is assigned to a key in the software. The factory Fn key does not count, although it is already Fn in the firmware. The patch changes `'none'` to `'auto'`.

The lock is a UI decision only. When saving, the software always sends all three layers (base, Fn1, Fn2) in one feature report (`07 03`). Each matrix position has two bytes: `0x00` + code means "firmware default", `0x80` + code means "custom code".

The software saves the selected layer with the profile and reopens it on the next start. Without the patch, it can therefore get stuck on an Fn layer whose button is locked (see the FAQ in the README). `checkFnStatus()` also has a bug: its `.some()` callback has no `return`, so it always returns `false`, and removing one Fn assignment locks both layer buttons.

The AL65 Wired and Sugar65 programs have no layer buttons (they are commented out in the template).

## Hidden developer mode

If the file `%APPDATA%\GSPYTEST.TEST` exists when the software starts, two things change. Its content does not matter.

1. **Ctrl+I** opens and closes the Chromium DevTools of the main window (`electron.js`).
2. Log entries of level DEBUG are also written to `%APPDATA%\<Name>_3M_Series\logs\YYYYMMDD.log`, e.g. `AL75_3M_Series` or `Lucky65_3M_Series`. Without the file, logging starts at INFO.

**Side effect:** Ctrl+I is registered as a *global* shortcut and only released when the software quits. While the software runs, including in the tray, no other program receives Ctrl+I (e.g. italic in Word). Delete the file when you are done:

```
type nul > "%APPDATA%\GSPYTEST.TEST"
del "%APPDATA%\GSPYTEST.TEST"
```

A second file, `%APPDATA%\GSPYTESTServer.TEST`, would switch the update URL to a test server, but only if `BuildCode` in `package.json` is not 0. It is 0 in all programs, so this file has no effect. The update URLs point to "Glorious Core", which hints at where the code base comes from.

With the DevTools you can try the Fn patches without changing any file. In the console, on the Keyboard Setting page:

```js
// Fn key clickable (until you switch pages)
document.querySelectorAll('.KeyAssignUIStyle').forEach(e => e.style.pointerEvents = 'auto')
// Fn layer buttons clickable
setInterval(() => document.querySelectorAll('#fnModel img').forEach(e => e.style.pointerEvents = 'auto'), 300)
```

The layer buttons need `setInterval`: Angular recreates them on every layer switch, and a recreated button is locked again. Without it, you can switch to an Fn layer but not back.

## Media keys, Mute and Calculator

For media and system functions, the software does not send USB usages but 8-bit codes from `0xA0` upwards. The keyboard firmware translates them. The Lucky65 firmware (version 2024-06-12 from Weikav's updater) does this with a chain of comparisons:

| Software button | Code sent | Firmware sends (consumer usage) |
|---|---|---|
| Media Player | `A0` | `0x183` |
| Play/Pause | `A1` | `0xCD` |
| Mute (hidden in the software) | `A2` | – not translated |
| Volume Up | `A3` | `0xE9` |
| Volume Down | `A4` | `0xEA` |
| Stop | `A5` | `0xB7` |
| Previous | `A6` | `0xB6` |
| Next | `A7` | `0xB5` |
| Homepage | `A8` | `0x223` |
| Refresh Page | `A9` | `0x227` |
| Page Back | `AB` | `0x224` |
| Page Forward | `AC` | `0x225` |
| Benchmark (Browser Favorites) | `AD` | `0x22A` |
| My Computer | `AF` | `0x194` |
| Email | `B1` | `0x18A` |
| Calculator (not in the software) | `B0` | – not translated |

Codes between `A0` and `B1` that are not in the chain are passed on unchanged as consumer usage. Mute therefore arrives as `0x00A2` instead of `0x00E2`, and Calculator as `0x00B0` instead of `0x0192`, and Windows ignores both.

Custom key entries cannot reach these usages in another way either. The firmware stores the two bytes per key unchanged as a 16-bit value (first byte × 256 + second byte):

- On the base layer and the Fn layer, it only uses a value with the custom flag `0x80` in the first byte. For anything else it falls back to its factory keymap.
- Values with the custom flag always go through the chain above. If the first byte has additional bits, they count as modifiers, so `83 E2` becomes Ctrl+Shift+Left Alt.
- The Fn2 layer takes every value as it is, but also sends it through the same translation, because the Fn key is not held.

The firmware's own internal format (see below), where `03E2` means Mute, is only used for factory values while Fn is held.

Tests confirmed this: a Mute button made visible in the software did nothing on the Lucky65, and a Calculator code did nothing on the AL75. The firmware itself does know Mute, but only in its built-in Fn layers. In the Fn+F1…F12 table from the manual, Fn+F10 is Mute.

How the firmware was read: the updater `lucky65_3M_Keyboard_20240612.exe` carries the firmware appended to the end of the executable, after a 128-byte header with the file name. The image is XOR-encoded with `0x55`, and the result is ARM Thumb code. Keymap entries in the firmware are 16-bit values:

| Value | Meaning |
|---|---|
| `00xx` | Keyboard usage (e.g. `0064` = ISO key, `00FE` = Fn) |
| `01xx` / `02xx` | Consumer usage itself (e.g. `0192` = Calculator) |
| `03xx` | Consumer usage `xx` (e.g. `03E2` = Mute) |
| `40xx` / `50xx` | Lighting and Bluetooth functions |
| `8000` + code | Custom entry from the software |
