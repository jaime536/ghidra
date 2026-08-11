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
"""Lint a translation catalog before it ships.

The catalogs are hand-edited .properties files whose keys are English UI strings, so they are
full of spaces - and an unescaped space silently ends the key, turning ``Save As...=另存为...``
into the key ``Save`` with the value ``As...=另存为...``.  That failure is invisible at runtime
(the string just stays English), so it is checked here instead.

Also verifies the file is valid UTF-8, has no duplicate or empty entries, and that no value was
left untranslated.

Usage:  tools/check_catalog.py Ghidra/Extensions/zh-cn-l10n/data/i18n/zh_CN.properties
"""

import argparse
import sys
from pathlib import Path

# Reports are in Chinese; Python on Windows would otherwise encode stdout with the system locale
# (cp1252 on a GitHub runner) and raise UnicodeEncodeError instead of printing them.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

SEPARATORS = "=:"


def split_entry(line: str):
    """Split a .properties line the way java.util.Properties does.

    Returns (key, value, separator_kind) where separator_kind is 'explicit' for '='/':' or
    'whitespace' when the key was ended by an unescaped space.
    """
    key = []
    i = 0
    while i < len(line):
        c = line[i]
        if c == "\\":
            key.append(line[i:i + 2])
            i += 2
            continue
        if c in SEPARATORS:
            return "".join(key), line[i + 1:], "explicit"
        if c.isspace():
            rest = line[i:].lstrip()
            if rest[:1] in tuple(SEPARATORS):
                return "".join(key), rest[1:], "explicit"
            return "".join(key), rest, "whitespace"
        key.append(c)
        i += 1
    return "".join(key), "", "none"


def unescape(text: str) -> str:
    out, i = [], 0
    while i < len(text):
        if text[i] == "\\" and i + 1 < len(text):
            out.append({"n": "\n", "t": "\t", "r": "\r"}.get(text[i + 1], text[i + 1]))
            i += 2
        else:
            out.append(text[i])
            i += 1
    return "".join(out)


def check(path: Path) -> tuple[list[str], dict[str, int]]:
    """Returns (problems, {key: line number})."""
    problems = []
    try:
        raw = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as e:
        return [f"{path}: 不是合法的 UTF-8 文件: {e}"], {}

    seen = {}
    logical, buffer, start_line = [], "", 0
    for number, line in enumerate(raw.splitlines(), start=1):
        stripped = line.strip()
        if not buffer and (not stripped or stripped.startswith(("#", "!"))):
            continue
        if not buffer:
            start_line = number
        if stripped.endswith("\\") and not stripped.endswith("\\\\"):
            buffer += stripped[:-1]
            continue
        logical.append((start_line, buffer + stripped))
        buffer = ""

    for number, entry in logical:
        key, value, kind = split_entry(entry)
        if kind == "whitespace":
            problems.append(
                f"{path}:{number}: 键中有未转义的空格，会被截断为 '{unescape(key)}' —— "
                f"请把空格写成 '\\ '")
            continue
        if kind == "none":
            problems.append(f"{path}:{number}: 缺少 '=' 分隔符")
            continue
        plain_key = unescape(key)
        if not plain_key:
            problems.append(f"{path}:{number}: 键为空")
            continue
        if not value.strip():
            problems.append(f"{path}:{number}: '{plain_key}' 没有译文")
        if plain_key in seen:
            problems.append(
                f"{path}:{number}: 键 '{plain_key}' 重复 (首次出现于第 {seen[plain_key]} 行)")
        else:
            seen[plain_key] = number

    print(f"{path}: {len(seen)} 条词条")
    return problems, seen


def check_against_source(path: Path, keys: dict[str, int], source_file: Path) -> None:
    """Warn about keys that no longer match anything in the source.

    A key is only ever consulted by an exact lookup, so a typo - or a string upstream has since
    reworded - produces no error, just a line that silently stays English. Reported as a warning
    rather than a failure: the extractor only knows the call sites it scans for, so a legitimate
    key can sit outside its reach.
    """
    known = {line.strip() for line in
             source_file.read_text(encoding="utf-8").splitlines() if line.strip()}
    stranded = sorted(key for key in keys if key not in known)
    if not stranded:
        print(f"{path}: 全部 {len(keys)} 个键都能在源码中找到。")
        return

    print(f"\n{path}: {len(stranded)} 个键在源码中找不到对应字符串（拼写错误，"
          f"或上游已改动措辞）:")
    for key in stranded[:40]:
        print(f"  第 {keys[key]} 行: {key}")
    if len(stranded) > 40:
        print(f"  ... 另有 {len(stranded) - 40} 条")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("catalogs", nargs="+", type=Path, help="要检查的 .properties 词典")
    parser.add_argument("--source-strings", type=Path,
                        help="tools/extract_strings.py 的输出，用于校验键是否真实存在")
    args = parser.parse_args()

    problems = []
    for path in args.catalogs:
        if not path.exists():
            problems.append(f"{path}: 文件不存在")
            continue
        file_problems, keys = check(path)
        problems.extend(file_problems)
        if args.source_strings and args.source_strings.exists():
            check_against_source(path, keys, args.source_strings)

    if problems:
        print(f"\n发现 {len(problems)} 个问题:")
        for p in problems:
            print(f"  {p}")
        return 1

    print("词典检查通过。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
