"""Builds the QuickJS-ng wheels the Android app depends on (`ytmpd-qjs`), into android/wheels/.

yt-dlp needs a JavaScript runtime for YouTube. Android only lets an app execute files from its native library folder,
and Flet's Python packaging copies any plain `.so` found in an installed package there. So the `qjs` executable is
shipped as `ytmpd_qjs/libqjs.so` inside a wheel tagged for each Android ABI, and ytmpd.core finds it through
ANDROID_NATIVE_LIBRARY_DIR. The app must be built with `legacy_packaging = true` so the file is extracted to disk.

Needs the Android NDK and CMake from the Android SDK. Run from the repo root:
    python android/qjs/build_wheels.py
"""

import base64
import hashlib
import io
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
import zipfile
from pathlib import Path

VERSION = "0.18.0"  # quickjs-ng release
ABIS = {"arm64-v8a": "android_24_arm64_v8a", "x86_64": "android_24_x86_64"}
API = 24
OUT = Path(__file__).resolve().parents[1] / "wheels"


def sdk_tools():
    sdk = Path(os.environ.get("ANDROID_HOME") or Path(os.environ["LOCALAPPDATA"]) / "Android" / "Sdk")
    ndk = max((sdk / "ndk").iterdir())
    cmake_bin = max((sdk / "cmake").iterdir()) / "bin"
    host = "windows-x86_64" if sys.platform == "win32" else ("darwin-x86_64" if sys.platform == "darwin" else "linux-x86_64")
    exe = ".exe" if sys.platform == "win32" else ""
    strip = ndk / "toolchains" / "llvm" / "prebuilt" / host / "bin" / f"llvm-strip{exe}"
    return ndk, cmake_bin / f"cmake{exe}", cmake_bin / f"ninja{exe}", strip


def download_source(dest: Path) -> Path:
    url = f"https://github.com/quickjs-ng/quickjs/archive/refs/tags/v{VERSION}.tar.gz"
    with urllib.request.urlopen(url) as r:
        data = r.read()
    with tarfile.open(fileobj=io.BytesIO(data)) as tar:
        tar.extractall(dest, filter="data")
    return next(dest.iterdir())


def build_qjs(src: Path, work: Path, abi: str) -> Path:
    ndk, cmake, ninja, strip = sdk_tools()
    build = work / f"build-{abi}"
    subprocess.run([
        str(cmake), "-S", str(src), "-B", str(build), "-G", "Ninja", f"-DCMAKE_MAKE_PROGRAM={ninja}",
        f"-DCMAKE_TOOLCHAIN_FILE={ndk / 'build' / 'cmake' / 'android.toolchain.cmake'}",
        f"-DANDROID_ABI={abi}", f"-DANDROID_PLATFORM=android-{API}", "-DCMAKE_BUILD_TYPE=Release",
        "-DQJS_ENABLE_INSTALL=OFF", "-DCMAKE_EXE_LINKER_FLAGS=-Wl,-z,max-page-size=16384",
    ], check=True, stdout=subprocess.DEVNULL)
    subprocess.run([str(cmake), "--build", str(build), "--target", "qjs_exe"], check=True, stdout=subprocess.DEVNULL)
    stripped = work / f"libqjs-{abi}.so"
    subprocess.run([str(strip), "-o", str(stripped), str(build / "qjs")], check=True)
    return stripped


def write_wheel(binary: Path, license_text: str, platform_tag: str) -> Path:
    name = f"ytmpd_qjs-{VERSION}-py3-none-{platform_tag}.whl"
    dist = f"ytmpd_qjs-{VERSION}.dist-info"
    files = {
        "ytmpd_qjs/__init__.py": b'"""QuickJS-ng executable for ytmpd on Android, shipped as libqjs.so."""\n',
        "ytmpd_qjs/libqjs.so": binary.read_bytes(),
        f"{dist}/licenses/LICENSE": license_text.encode(),
        f"{dist}/METADATA": (f"Metadata-Version: 2.4\nName: ytmpd-qjs\nVersion: {VERSION}\n"
                             "Summary: QuickJS-ng qjs executable for Android, for yt-dlp\n"
                             "License-Expression: MIT\nLicense-File: LICENSE\n").encode(),
        f"{dist}/WHEEL": f"Wheel-Version: 1.0\nGenerator: ytmpd\nRoot-Is-Purelib: false\nTag: py3-none-{platform_tag}\n".encode(),
    }

    def digest(data):
        return "sha256=" + base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()

    record = "".join(f"{path},{digest(data)},{len(data)}\n" for path, data in files.items()) + f"{dist}/RECORD,,\n"
    OUT.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(OUT / name, "w", zipfile.ZIP_DEFLATED) as whl:
        for path, data in files.items():
            info = zipfile.ZipInfo(path, date_time=(2026, 1, 1, 0, 0, 0))  # fixed date: same input, same wheel
            info.external_attr = (0o755 if path.endswith(".so") else 0o644) << 16
            whl.writestr(info, data, zipfile.ZIP_DEFLATED)
        whl.writestr(zipfile.ZipInfo(f"{dist}/RECORD", date_time=(2026, 1, 1, 0, 0, 0)), record)
    return OUT / name


def main():
    work = Path(tempfile.mkdtemp(prefix="ytmpd-qjs-"))
    try:
        src = download_source(work / "src")
        license_text = (src / "LICENSE").read_text(encoding="utf-8")
        for abi, tag in ABIS.items():
            print(write_wheel(build_qjs(src, work, abi), license_text, tag))
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()
