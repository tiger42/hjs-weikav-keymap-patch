"""
Patch for the HJS / Weikav keyboard software (e.g. "AL75_3M Keyboard", "lucky65_3M keyboard"):
unlocks keys and functions that the software does not let you assign.

--iso        The software translates K-codes into HID codes via a table (backend/others/SupportData.js).
             The Non-US Backslash (HID 0x64, ISO key <>|) is missing from that table. This patch redirects
             the entry K44 ("Benchmark", actually "Browser Favorites", HID 0xAD) to HID 0x64 and renames
             the button in all UI languages to "ISO-Key <>|".
--fn-key     The Fn key in the keyboard picture is not clickable (pointer-events: none), so it cannot be
             remapped. This patch makes it clickable.
--fn-layers  The Fn1/Fn2 layer buttons are only clickable after "Fn" was assigned to a key. This patch makes
             them always clickable, so the layers of the factory Fn key can be edited.

All changes keep the original length, so the app.asar archive does not need to be rebuilt.

Usage:
    python keymap_patch.py "<path>\\resources\\app.asar"                  # show status, change nothing
    python keymap_patch.py "<path>\\resources\\app.asar" --iso --fn-key   # apply selected patches
    python keymap_patch.py "<path>\\resources\\app.asar" --all            # apply all available patches
    python keymap_patch.py "<path>\\resources\\app.asar" --all --revert   # undo
"""
import argparse
import json
import os
import struct
import sys

PATCHES = {
    "iso": ("ISO key <>| (replaces the \"Benchmark\" function)", [
        ("/backend/others/SupportData.js", "'hid':0xad,", "'hid':0x64,"),
        ("/components/i18n_Localization.js",
         'BROWSERCOLLECT:{EN:"Benchmark",CH:"瀏覽器收藏",CN:"浏览器收藏",IT:"Riferimento",ES:"Punto de referencia"}',
         'BROWSERCOLLECT:{EN:"ISO-Key <>|",CH:"ISO鍵 <>|",CN:"ISO键 <>|",IT:"Tasto ISO <>|",ES:"Tecla ISO <>|"}'),
    ]),
    "fn-key": ("make the Fn key itself remappable", [
        ("/components/app.component.html",
         "item === 'Custom_Fnkey'?'none':'auto'",
         "item === 'Custom_Fnkey'?'auto':'auto'"),
    ]),
    "fn-layers": ("make the Fn layers editable without assigning Fn first", [
        ("/components/app.component.html",
         "fnBtnStatus[i] ? 'auto' : 'none'",
         "fnBtnStatus[i] ? 'auto' : 'auto'"),
    ]),
}

# Shown after a patch was reverted: what the user may have to fix in the software.
REVERT_NOTES = {
    "iso": "keys assigned to \"ISO-Key <>|\" send \"Benchmark\" (Browser Favorites) again as soon as you change "
           "any assignment. Give them a new function.",
    "fn-key": "the Fn key can no longer be selected in the software. If you had remapped it, apply --fn-key "
              "again, set the key back to Fn and revert afterwards.",
    "fn-layers": "if the software now opens on an Fn layer and you cannot switch back, apply --fn-layers again, "
                 "switch to the base layer and revert afterwards.",
}

NOT_THE_SOFTWARE = "None of the patches fits this file. Is it resources\\app.asar of a supported keyboard software?"


def encode(orig, new):
    pad = len(orig.encode()) - len(new.encode())
    if pad < 0:
        raise ValueError(f"replacement longer than original: {new!r}")
    # Pad with spaces before the last character (whitespace inside the JS code), so the length stays the same.
    return orig.encode(), (new[:-1] + " " * pad + new[-1:]).encode()


def read_index(f):
    file_size = os.fstat(f.fileno()).st_size
    f.seek(0)
    _, header_size = struct.unpack("<II", f.read(8))
    if header_size > file_size:
        raise ValueError("header larger than file")
    header = f.read(header_size)
    json_len = struct.unpack("<I", header[4:8])[0]
    index = json.loads(header[8:8 + json_len])
    if not isinstance(index, dict) or "files" not in index:
        raise ValueError("no asar index")
    return index, 8 + header_size


def locate(index, base, path):
    node = index
    for part in path.strip("/").split("/"):
        node = node["files"][part]
    return base + int(node["offset"]), node["size"]


def plan_patch(f, index, base, parts, revert):
    """Writes needed to apply (or revert) one patch: [] if nothing to do, None if not available here."""
    writes = []
    for path, *texts in parts:
        orig, new = encode(*texts)
        old, rep = (new, orig) if revert else (orig, new)
        try:
            offset, size = locate(index, base, path)
        except KeyError:
            return None
        f.seek(offset)
        data = f.read(size)
        if data.count(rep) == 1 and data.count(old) == 0:
            continue
        if data.count(old) != 1 or data.count(rep) != 0:
            return None
        writes.append((path, offset + data.index(old), old, rep))
    return writes


def status(f, index, base, parts):
    writes = plan_patch(f, index, base, parts, revert=False)
    if writes is None:
        return "not available in this software"
    if not writes:
        return "applied"
    return "not applied" if len(writes) == len(parts) else "partially applied"


def write_plan(asar, plan):
    """Write all planned replacements or none of them."""
    try:
        f = open(asar, "r+b", buffering=0)
    except PermissionError:
        if not os.access(asar, os.W_OK):
            sys.exit("The file is read-only. Clear the read-only attribute in its properties and try again.")
        sys.exit("No write access. Quit the keyboard software completely (including the tray icon) "
                 "and run the terminal as administrator.")
    with f:
        for name, path, pos, old, rep in plan:
            f.seek(pos)
            if f.read(len(old)) != old:
                sys.exit("The file changed while the script was running. Nothing was changed.")
        try:
            for name, path, pos, old, rep in plan:
                f.seek(pos)
                f.write(rep)
        except OSError as error:
            try:
                for name, path, pos, old, rep in plan:
                    f.seek(pos)
                    f.write(old)
            except OSError:
                sys.exit(f"Writing failed ({error.strerror or error}) and could not be undone. Run the script "
                         "without options to see the status, or reinstall the keyboard software.")
            sys.exit(f"Writing failed ({error.strerror or error}). Nothing was changed.")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("asar", help='path to "resources\\app.asar" in the installation folder of the software')
    for name, (help_text, _) in PATCHES.items():
        parser.add_argument("--" + name, action="store_true", help=help_text)
    parser.add_argument("--all", action="store_true", help="all patches available in this software")
    parser.add_argument("--revert", action="store_true", help="undo the selected patches")
    args = parser.parse_args()
    selected = [name for name in PATCHES if args.all or getattr(args, name.replace("-", "_"))]
    if args.revert and not selected:
        parser.error("--revert needs the patches to undo, e.g. --all")

    if os.path.isdir(args.asar):
        sys.exit(f"{args.asar} is a folder. Give the path to the file app.asar in its resources folder.")
    try:
        f = open(args.asar, "rb")
    except FileNotFoundError:
        sys.exit(f"File not found: {args.asar}")
    except OSError as error:
        sys.exit(f"Cannot read {args.asar}: {error.strerror or error}")
    with f:
        try:
            index, base = read_index(f)
        except (struct.error, ValueError):
            sys.exit(f"{args.asar} is not an app.asar archive.")
        if not selected:
            states = {name: status(f, index, base, parts) for name, (_, parts) in PATCHES.items()}
            for name, state in states.items():
                print(f"{name:10} {state}")
            if all(state == "not available in this software" for state in states.values()):
                sys.exit(NOT_THE_SOFTWARE)
            print("Apply with --all (or single patches, e.g. --iso). Undo with --all --revert.")
            return
        plan, unavailable = [], []
        for name in selected:
            writes = plan_patch(f, index, base, PATCHES[name][1], args.revert)
            if writes is None:
                unavailable.append(name)
                if args.all:
                    print(f"{name}: not available in this software, skipped")
            elif not writes:
                print(f"{name}: {'not applied' if args.revert else 'already applied'}")
            else:
                plan += [(name, *write) for write in writes]

    if unavailable and not args.all:
        sys.exit(f"{', '.join(unavailable)}: not available in this software (see the table in the README). "
                 "Nothing was changed.")
    if len(unavailable) == len(selected):
        sys.exit(NOT_THE_SOFTWARE + " Nothing was changed.")
    if not plan:
        print("Nothing to change.")
        return
    write_plan(args.asar, plan)
    for name, path, pos, old, rep in plan:
        print(f"{name}: {path} {'reverted' if args.revert else 'patched'} @ {pos}")
    if args.revert:
        for name in dict.fromkeys(name for name, *_ in plan):
            print(f"Note ({name}): {REVERT_NOTES[name]}")
    print("Done.")


if __name__ == "__main__":
    main()
