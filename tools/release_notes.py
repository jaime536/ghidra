#!/usr/bin/env python3
# ###
#  IP: GHIDRA
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
#
"""Write release notes describing which platform packages a release actually contains.

Each build leg runs independently (fail-fast is off), so a release can legitimately ship with a
platform missing.  That must be stated on the release rather than left for someone to notice
after downloading, so this reads the packages that were actually collected and names both what
is present and what is not.

Platform detection needs no extra metadata: buildGhidra names each archive after the platform it
was built on (gradle/root/distribution.gradle, archiveFileName), giving
`ghidra_<version>_<date>_<platform>.zip`.

Exits non-zero when no package was collected at all, so an empty release is never published.

Usage:  tools/release_notes.py <dist-dir> <output.md>
"""

import sys
from pathlib import Path

# Ask for UTF-8 explicitly; Windows would otherwise encode stdout with the system locale.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

# Platform token as it appears in the archive name -> how to describe it to a reader.
# Keep in step with the build matrix in .github/workflows/build-ghidra.yml.
PLATFORMS = {
    "linux_x86_64": "Linux (x86_64)",
    "win_x86_64": "Windows (x86_64)",
    "mac_arm_64": "macOS (Apple Silicon)",
}


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__)
        return 2

    dist_dir, out_file = Path(sys.argv[1]), Path(sys.argv[2])
    zips = sorted(dist_dir.glob("*.zip")) if dist_dir.is_dir() else []

    if not zips:
        # GitHub Actions renders this as an error annotation on the job.
        print("::error::没有任何平台产出安装包，拒绝发布空 Release。")
        return 1

    found = {}
    extras = []
    for path in zips:
        for token, label in PLATFORMS.items():
            if token in path.name:
                found[token] = path
                break
        else:
            extras.append(path)

    missing = [token for token in PLATFORMS if token not in found]

    lines = ["## 安装包", ""]
    for token, label in PLATFORMS.items():
        if token in found:
            size = found[token].stat().st_size / (1024 * 1024)
            lines.append(f"- **{label}** — `{found[token].name}` ({size:.0f} MB)")
    for path in extras:
        size = path.stat().st_size / (1024 * 1024)
        lines.append(f"- `{path.name}` ({size:.0f} MB)")

    if missing:
        lines += ["", "> [!WARNING]", "> **本次发布缺少以下平台的安装包**（对应平台构建失败）:", ">"]
        lines += [f"> - {PLATFORMS[token]}" for token in missing]
        lines += [">", "> 缺失的平台可在对应构建修复后重新打 tag 发布。"]

    lines += [
        "",
        "## 使用",
        "",
        "解压后运行 `ghidraRun`（Windows 为 `ghidraRun.bat`）。界面默认是英文，",
        "加上开关即为中文：",
        "",
        "```",
        "ghidraRun -Dghidra.i18n=zh_CN",
        "```",
        "",
    ]

    out_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"收集到 {len(zips)} 个安装包，覆盖 {len(found)}/{len(PLATFORMS)} 个平台。")
    for token in PLATFORMS:
        print(f"  {'✓' if token in found else '✗'} {PLATFORMS[token]}")
    if missing:
        # A warning annotation, not an error: a partial release is allowed, just labelled.
        print(f"::warning::缺少 {len(missing)} 个平台的安装包: {', '.join(missing)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
