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
"""Manage the Chinese help-page overlay.

Ghidra's help pages live inside each module (``<module>/src/main/help/help/...``) and upstream
edits them constantly, so translating them in place would put every release merge into conflict.
Instead the translations live in a parallel tree under ``GhidraChinese/help-zh/`` whose paths
mirror the originals, and this script moves content between the two worlds:

``check``
    Compare each translated page against the upstream page it was made from, using the recorded
    git blob hash.  Reports pages whose English original has changed (translation needs review)
    and pages that exist upstream but have no translation yet.  Read-only.

``apply``
    Copy the overlay over the working tree so a build picks it up.  The upstream files are
    modified on disk but never committed; ``apply --revert`` puts them back.  This has to run
    before Gradle's ``indexHelp``/``buildModuleHelp`` tasks, which read from ``src/main/help``.

    Use ``--revert`` rather than a blanket ``git checkout -- .``, which would also discard the
    L10N source hooks and anything else uncommitted in the tree.

``adopt``
    Record the current upstream blob hashes for pages already in the overlay, which is how a
    translation is marked as up to date after review.

Manifest format (``GhidraChinese/help-zh/manifest.tsv``): ``<relative path>\\t<blob hash>``.
"""

import argparse
import hashlib
import shutil
import subprocess
import sys
from pathlib import Path

# This script reports in Chinese, but Python on Windows encodes stdout with the system locale
# (cp1252 on a GitHub runner), which cannot represent those characters and raises part-way
# through printing - after the files have already been copied. Ask for UTF-8 explicitly.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

REPO_ROOT = Path(__file__).resolve().parent.parent
OVERLAY_ROOT = REPO_ROOT / "GhidraChinese" / "help-zh"
MANIFEST = OVERLAY_ROOT / "manifest.tsv"
HELP_GLOB = "Ghidra/**/src/main/help/help/**/*"
HELP_SUFFIXES = {".htm", ".html", ".xml"}


def git_blob_hash(path: Path) -> str:
    """Return the git blob hash of a file, matching `git hash-object`."""
    data = path.read_bytes()
    header = b"blob %d\0" % len(data)
    return hashlib.sha1(header + data).hexdigest()


def read_manifest() -> dict[str, str]:
    if not MANIFEST.exists():
        return {}
    entries = {}
    for line in MANIFEST.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        rel, _, blob = line.partition("\t")
        entries[rel] = blob
    return entries


def write_manifest(entries: dict[str, str]) -> None:
    OVERLAY_ROOT.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Chinese help overlay: upstream blob hash each translation was made from.",
        "# Regenerate after reviewing a translation with: tools/help_zh.py adopt",
        "",
    ]
    lines += [f"{rel}\t{blob}" for rel, blob in sorted(entries.items())]
    MANIFEST.write_text("\n".join(lines) + "\n", encoding="utf-8")


def translated_pages() -> list[str]:
    """Overlay-relative paths of every translated page."""
    if not OVERLAY_ROOT.exists():
        return []
    return sorted(
        str(p.relative_to(OVERLAY_ROOT)).replace("\\", "/")
        for p in OVERLAY_ROOT.rglob("*")
        if p.is_file() and p.suffix.lower() in HELP_SUFFIXES
    )


def upstream_pages() -> list[str]:
    """Repo-relative paths of every upstream help page."""
    out = subprocess.run(
        ["git", "ls-files", "--", HELP_GLOB],
        cwd=REPO_ROOT, capture_output=True, text=True, check=True,
    ).stdout
    return sorted(
        p for p in out.splitlines() if Path(p).suffix.lower() in HELP_SUFFIXES
    )


def cmd_check(args) -> int:
    manifest = read_manifest()
    translated = translated_pages()
    upstream = set(upstream_pages())

    stale, orphaned, unrecorded = [], [], []
    for rel in translated:
        source = REPO_ROOT / rel
        if not source.exists():
            orphaned.append(rel)
            continue
        recorded = manifest.get(rel)
        if recorded is None:
            unrecorded.append(rel)
        elif recorded != git_blob_hash(source):
            stale.append(rel)

    print(f"translated pages: {len(translated)}    upstream pages: {len(upstream)}")

    for label, items in (
        ("原文已变，译文需复核", stale),
        ("译文无对应上游文件（上游已删除或改名）", orphaned),
        ("译文未登记基线哈希（跑一次 adopt）", unrecorded),
    ):
        if items:
            print(f"\n{label} ({len(items)}):")
            for rel in items:
                print(f"  {rel}")

    if args.show_untranslated:
        missing = sorted(upstream - set(translated))
        print(f"\n尚未翻译的上游页面 ({len(missing)}):")
        for rel in missing:
            print(f"  {rel}")

    if not (stale or orphaned or unrecorded):
        print("\n所有译文均与上游原文同步。")
        return 0
    # Deliberately non-fatal: staleness is a review prompt, not a build failure.
    return 0


def cmd_apply(args) -> int:
    translated = translated_pages()
    if not translated:
        print("译文目录为空，无需叠加。")
        return 0

    targets = [rel for rel in translated if (REPO_ROOT / rel).exists()]
    skipped = [rel for rel in translated if rel not in set(targets)]

    if args.revert:
        # restore only the help pages this script touches, never the whole tree
        if not args.dry_run and targets:
            # chunked: Windows caps a command line at ~8k characters
            for i in range(0, len(targets), 100):
                subprocess.run(["git", "checkout", "--"] + targets[i:i + 100],
                               cwd=REPO_ROOT, check=True)
        print(f"{'将还原' if args.dry_run else '已还原'} {len(targets)} 个上游帮助文件。")
        return 0

    if not args.dry_run:
        for rel in targets:
            shutil.copyfile(OVERLAY_ROOT / rel, REPO_ROOT / rel)

    print(f"{'将叠加' if args.dry_run else '已叠加'} {len(targets)} 个中文帮助页面到工作树。")
    if skipped:
        print(f"跳过 {len(skipped)} 个没有对应上游文件的页面:")
        for rel in skipped:
            print(f"  {rel}")
    if not args.dry_run:
        print("构建结束后用 `tools/help_zh.py apply --revert` 还原上游文件。")
    return 0


def cmd_adopt(args) -> int:
    manifest = read_manifest()
    updated = 0
    for rel in translated_pages():
        source = REPO_ROOT / rel
        if not source.exists():
            continue
        blob = git_blob_hash(source)
        if manifest.get(rel) != blob:
            manifest[rel] = blob
            updated += 1
    write_manifest(manifest)
    print(f"已登记 {updated} 个页面的上游基线哈希，共 {len(manifest)} 条。")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    p_check = sub.add_parser("check", help="报告需复核或尚未翻译的帮助页")
    p_check.add_argument("--show-untranslated", action="store_true",
                         help="同时列出所有尚未翻译的上游页面")
    p_check.set_defaults(func=cmd_check)

    p_apply = sub.add_parser("apply", help="把译文叠加到工作树（构建前执行）")
    p_apply.add_argument("--dry-run", action="store_true", help="只显示将要覆盖的文件")
    p_apply.add_argument("--revert", action="store_true",
                         help="只还原被叠加过的上游帮助文件（不影响其他改动）")
    p_apply.set_defaults(func=cmd_apply)

    p_adopt = sub.add_parser("adopt", help="登记当前上游原文哈希为译文基线")
    p_adopt.set_defaults(func=cmd_adopt)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
