"""
Patch for the HJS / Weikav keyboard software (e.g. "AL75_3M Keyboard"): makes the Non-US Backslash
(HID 0x64, ISO key <>|) assignable.

The software translates K-codes into HID codes via a table (backend/others/SupportData.js).
NUBS is missing from that table. This patch redirects the entry K44 ("Benchmark", actually
"Browser Favorites", HID 0xAD) to HID 0x64 and renames the button in all UI languages to "ISO-Key <>|".
Both changes keep the original length, so the app.asar archive does not need to be rebuilt.

Usage:
    python nubs_patch.py "<path>\\resources\\app.asar"           # apply patch
    python nubs_patch.py "<path>\\resources\\app.asar" --revert  # undo patch
"""
import json
import struct
import sys

PATCHES = [
    ("/backend/others/SupportData.js", "'hid':0xad,", "'hid':0x64,"),
    ("/components/i18n_Localization.js",
     'BROWSERCOLLECT:{EN:"Benchmark",CH:"瀏覽器收藏",CN:"浏览器收藏",IT:"Riferimento",ES:"Punto de referencia"}',
     'BROWSERCOLLECT:{EN:"ISO-Key <>|",CH:"ISO鍵 <>|",CN:"ISO键 <>|",IT:"Tasto ISO <>|",ES:"Tecla ISO <>|"}'),
]


def encode(orig, new):
    orig, new = orig.encode(), new.encode()
    if len(new) > len(orig):
        raise ValueError(f"replacement longer than original: {new!r}")
    # Pad with spaces before the last character (whitespace inside the JS code), so the length stays the same.
    return orig, new[:-1] + b" " * (len(orig) - len(new)) + new[-1:]


def read_index(f):
    f.seek(0)
    _, header_size = struct.unpack("<II", f.read(8))
    header = f.read(header_size)
    json_len = struct.unpack("<I", header[4:8])[0]
    return json.loads(header[8:8 + json_len]), 8 + header_size


def locate(index, base, path):
    node = index
    for part in path.strip("/").split("/"):
        node = node["files"][part]
    return base + int(node["offset"]), node["size"]


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    asar, revert = sys.argv[1], "--revert" in sys.argv[2:]
    with open(asar, "r+b") as f:
        index, base = read_index(f)
        plan = []
        for path, *texts in PATCHES:
            orig, new = encode(*texts)
            old, rep = (new, orig) if revert else (orig, new)
            offset, size = locate(index, base, path)
            f.seek(offset)
            data = f.read(size)
            if data.count(rep) == 1 and data.count(old) == 0:
                print(f"{path}: already done")
                continue
            if data.count(old) != 1:
                sys.exit(f"{path}: pattern {old!r} not found exactly once - different software version? Aborting, nothing was changed.")
            plan.append((path, offset + data.index(old), rep))
        for path, pos, rep in plan:
            f.seek(pos)
            f.write(rep)
            print(f"{path}: {'reverted' if revert else 'patched'} @ {pos}")
    print("Done.")


if __name__ == "__main__":
    main()
