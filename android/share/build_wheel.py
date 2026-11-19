"""Packs the ytmpd_share Flet extension into android/wheels/ytmpd_share-<version>-py3-none-any.whl.

The wheel installs the Python side as `ytmpd_share` and the Dart side as `flutter/ytmpd_share` at the root of
site-packages, which is where Flet's packaging looks for Flutter packages to add to the app.
Run from the repo root: python android/share/build_wheel.py
"""

import base64
import hashlib
import re
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "wheels"
VERSION = re.search(r"^version: (\S+)", (HERE / "flutter/ytmpd_share/pubspec.yaml").read_text(), re.M).group(1)
DATE = (2026, 1, 1, 0, 0, 0)  # fixed, so the same sources give the same wheel


def main():
    files = {p.relative_to(HERE).as_posix(): p.read_bytes()
             for p in sorted(HERE.rglob("*")) if p.is_file() and p.name != "build_wheel.py" and "__pycache__" not in p.parts}
    dist = f"ytmpd_share-{VERSION}.dist-info"
    files[f"{dist}/METADATA"] = (f"Metadata-Version: 2.4\nName: ytmpd-share\nVersion: {VERSION}\n"
                                 "Summary: Flet extension: text shared to the app from Android's Share menu\n").encode()
    files[f"{dist}/WHEEL"] = b"Wheel-Version: 1.0\nGenerator: ytmpd\nRoot-Is-Purelib: true\nTag: py3-none-any\n"

    def digest(data):
        return "sha256=" + base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()

    record = "".join(f"{path},{digest(data)},{len(data)}\n" for path, data in files.items()) + f"{dist}/RECORD,,\n"
    OUT.mkdir(exist_ok=True)
    wheel = OUT / f"ytmpd_share-{VERSION}-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w", zipfile.ZIP_DEFLATED) as z:
        for path, data in [*files.items(), (f"{dist}/RECORD", record.encode())]:
            z.writestr(zipfile.ZipInfo(path, date_time=DATE), data, zipfile.ZIP_DEFLATED)
    print(wheel)


if __name__ == "__main__":
    main()
