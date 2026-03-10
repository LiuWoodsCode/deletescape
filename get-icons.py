import plistlib
import base64
import os
import sys

def sanitize_filename(name: str) -> str:
    """Make a filename safe-ish."""
    return "".join(c for c in name if c.isalnum() or c in (" ", "_", "-")).rstrip()

def extract_icons(mobileconfig_path, output_dir="icons"):
    os.makedirs(output_dir, exist_ok=True)

    with open(mobileconfig_path, "rb") as f:
        plist = plistlib.load(f)

    payloads = plist.get("PayloadContent", [])
    if not isinstance(payloads, list):
        print("No PayloadContent array found")
        return

    count = 0

    for payload in payloads:
        icon_data = payload.get("Icon")
        if not icon_data:
            continue

        # Prefer Label, fall back to UUID
        label = payload.get("Label") or payload.get("PayloadUUID") or f"icon_{count}"
        label = sanitize_filename(label)

        try:
            png_bytes = icon_data
        except Exception as e:
            print(f"Failed to decode icon for {label}: {e}")
            continue

        out_path = os.path.join(output_dir, f"{label}.png")
        with open(out_path, "wb") as img:
            img.write(png_bytes)

        print(f"Extracted: {out_path}")
        count += 1

    print(f"\nDone. Extracted {count} icon(s).")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python extract_webclip_icons.py <webclip.mobileconfig> [output_dir]")
        sys.exit(1)

    input_path = sys.argv[1]
    out_dir = sys.argv[2] if len(sys.argv) > 2 else "icons"

    extract_icons(input_path, out_dir)
