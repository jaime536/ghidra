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
"""List the user-visible strings that generic.i18n.L10N can translate.

The translation catalog is keyed on English source strings, so it can only ever match text that
actually reaches one of L10N's call sites. This scans for exactly those call sites, which serves
two purposes: producing the to-translate list when extending the catalog, and giving
check_catalog.py something to validate catalog keys against - a key with a typo, or one left
stranded when upstream reworded a string, is otherwise invisible at runtime (it just looks like
a missing translation).

Categories mirror the hooks in the Docking framework:

  menu    MenuItemManager / MenuManager        new MenuData(...), .menuPath(...)
  title   ComponentProvider / DialogComponentProvider   setTitle, setTabText, setCustomTitle
  label   GLabel / GDLabel / GCheckBox and the JLabel family
  tip     DockingToolBarUtils                  setToolTipText
  desc    DockingAction.getDescription         setDescription, ActionBuilder.description

Usage:
  tools/extract_strings.py                    # every category, one string per line
  tools/extract_strings.py --category menu    # just one category
  tools/extract_strings.py --counts           # prefix each line with its occurrence count
"""

import argparse
import collections
import re
import sys
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

REPO_ROOT = Path(__file__).resolve().parent.parent
SOURCE_ROOT = REPO_ROOT / "Ghidra"

STRING_LITERAL = re.compile(r'"((?:[^"\\]|\\.)*)"')

# Menu paths are frequently assembled from constants rather than literals, e.g.
#   private static final String MENU_ITEM_DELETE_TOOL = "Delete Tool";
#   new MenuData(new String[] { ToolConstants.MENU_TOOLS, MENU_ITEM_DELETE_TOOL }, ...)
# so the braces have to be read with the file's own String constants in scope, or those items
# are invisible to this scan while still being perfectly translatable at runtime.
STRING_CONSTANT = re.compile(
    r'(?:static\s+final|final\s+static)\s+String\s+(\w+)\s*=\s*"((?:[^"\\]|\\.)*)"')
IDENTIFIER_REF = re.compile(r"(?:^|[\s,{])(?:\w+\.)?([A-Z][A-Z0-9_]{2,})(?=[\s,}]|$)")

# The menu patterns capture an argument list. Every literal in it is taken, not just the leaf:
# the earlier elements are submenu names ("Data", "References") that the user reads too, and
# which frequently have no definition of their own anywhere else.
MENU_PATTERNS = [
    re.compile(r"new MenuData\(\s*new String\[\]\s*\{([^}]*)\}", re.S),
    re.compile(r"\.(?:menuPath|popupMenuPath)\(([^)]*)\)", re.S),
]

# Top-level menu names reach MenuData through constants (ToolConstants.MENU_FILE = "&File"), so
# they never appear inside a MenuData call. The embedded mnemonic marker is a reliable tell that
# a literal is a menu name - but only once HTML entities are ruled out, since "&amp;" and
# friends look identical to this pattern.
MNEMONIC_LITERAL = re.compile(r'"(&[A-Za-z][A-Za-z0-9 /.\'-]{0,28})"')
# The trailing semicolon is required: without it this also swallows ordinary words that happen
# to share an entity name, such as the menu item "Copy".
HTML_ENTITY = re.compile(r"^&?(amp|gt|lt|quot|apos|nbsp|copy|reg);", re.I)

def strip_comments(text: str) -> str:
    """Remove Java comments, leaving string literals intact.

    Comments carry prose that matches the category patterns by accident (Javadoc showing example
    markup, @deprecated notes). A regex cannot do this: a literal containing "/*" would start a
    bogus comment and swallow the real code up to the next "*/", silently dropping strings. So
    walk the text and only treat comment markers found outside literals.
    """
    out = []
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c in "\"'":
            quote = c
            out.append(c)
            i += 1
            while i < n:
                out.append(text[i])
                if text[i] == "\\":            # escape consumes the next character
                    if i + 1 < n:
                        out.append(text[i + 1])
                    i += 2
                    continue
                if text[i] == quote:
                    i += 1
                    break
                i += 1
            continue
        if c == "/" and i + 1 < n:
            if text[i + 1] == "/":
                i = text.find("\n", i)
                if i < 0:
                    break
                continue
            if text[i + 1] == "*":
                end = text.find("*/", i + 2)
                i = n if end < 0 else end + 2
                out.append(" ")
                continue
        out.append(c)
        i += 1
    return "".join(out)

# A literal handed straight to the translator is translatable by definition, so this picks up
# framework text the category patterns cannot see - the OK/Cancel/Apply/Dismiss buttons that
# DialogComponentProvider puts on every dialog, for instance. Self-maintaining: hook a new call
# site and it shows up here without touching this script.
L10N_LITERAL = re.compile(r'L10N\.tr\(\s*"((?:[^"\\]|\\.)*)"')

# Provider titles are largely passed as constructor arguments the scan below cannot attribute,
# but every one of them is also recorded in the shipped tool definitions.
TOOL_NAME = re.compile(r'NAME="([^"]+)"')
# ...alongside internal keys and fully qualified class names, which are not display text.
INTERNAL_KEY = re.compile(r"^[A-Z0-9_]+$")
CLASS_NAME = re.compile(r"[a-z]\.[a-zA-Z]")

DIRECT_PATTERNS = {
    "title": re.compile(
        r'(?:setTitle|setTabText|setCustomTitle|setSubTitle)\(\s*"((?:[^"\\]|\\.)*)"'),
    "label": re.compile(
        r'new (?:G|J|GD|GHtml|GDHtml)?(?:Label|CheckBox)\(\s*"((?:[^"\\]|\\.)*)"'),
    "tip": re.compile(r'setToolTipText\(\s*"((?:[^"\\]|\\.)*)"'),
    "desc": re.compile(r'(?:setDescription|\.description)\(\s*"((?:[^"\\]|\\.)*)"'),
}

CATEGORIES = ["menu", "title", "label", "tip", "desc"]

# Strings that are never worth translating: pure punctuation or digits (separators, address
# placeholders), and the demo text in the sample/skeleton modules.
NOISE = re.compile(r"^[\W\d_]*$")
DEMO = re.compile(r"hello|sample|dummy|\bfoo\b|\bbar\b", re.I)


def strip_mnemonic(text: str) -> str:
    """Drop mnemonic markers, matching MenuData.stripMnemonicAmp and L10N."""
    return text.replace("&&", "\x00").replace("&", "").replace("\x00", "&").strip()


# Identifier-shaped text that is never displayed: camelCase names, markup, paths, key=value.
IDENTIFIER = re.compile(r"^[a-z][A-Za-z0-9]*$")
MARKUP = re.compile(r"[<>{}]|&#|\bhttps?:")


def is_translatable(text: str) -> bool:
    return (bool(text) and len(text) > 1
            and not NOISE.match(text)
            and not DEMO.search(text)
            and not HTML_ENTITY.match(text)
            and not IDENTIFIER.match(text)
            and not MARKUP.search(text)
            and "=" not in text
            and not text.endswith("/"))


def extract() -> dict[str, collections.Counter]:
    found = {category: collections.Counter() for category in CATEGORIES}

    for path in SOURCE_ROOT.rglob("*.java"):
        # Test sources carry throwaway strings that would pollute the catalog
        if "/src/test" in path.as_posix() or "/src/test.slow" in path.as_posix():
            continue
        try:
            text = path.read_text(errors="ignore")
        except OSError:
            continue
        text = strip_comments(text)

        constants = {name: value for name, value in STRING_CONSTANT.findall(text)}

        for pattern in MENU_PATTERNS:
            for match in pattern.finditer(text):
                arguments = match.group(1)
                for literal in STRING_LITERAL.findall(arguments):
                    found["menu"][strip_mnemonic(literal)] += 1
                # Resolve constants declared in this same file; cross-file ones (ToolConstants
                # and friends) are picked up where they are declared.
                for name in IDENTIFIER_REF.findall(STRING_LITERAL.sub("", arguments)):
                    if name in constants:
                        found["menu"][strip_mnemonic(constants[name])] += 1

        for match in MNEMONIC_LITERAL.finditer(text):
            found["menu"][strip_mnemonic(match.group(1))] += 1

        for match in L10N_LITERAL.finditer(text):
            found["label"][strip_mnemonic(match.group(1))] += 1

        for category, pattern in DIRECT_PATTERNS.items():
            for match in pattern.finditer(text):
                found[category][strip_mnemonic(match.group(1))] += 1

    for path in SOURCE_ROOT.rglob("*.tool"):
        try:
            text = path.read_text(errors="ignore")
        except OSError:
            continue
        for match in TOOL_NAME.finditer(text):
            name = match.group(1).strip()
            if not INTERNAL_KEY.match(name) and not CLASS_NAME.search(name):
                found["title"][name] += 1

    for counter in found.values():
        for text in [t for t in counter if not is_translatable(t)]:
            del counter[text]
    return found


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--category", choices=CATEGORIES, action="append",
                        help="只输出指定类别（可重复），默认全部")
    parser.add_argument("--counts", action="store_true", help="每行前加上出现次数")
    parser.add_argument("--max-length", type=int, default=0,
                        help="只输出不超过该长度的字符串（0 表示不限）")
    args = parser.parse_args()

    found = extract()
    categories = args.category or CATEGORIES

    merged = collections.Counter()
    for category in categories:
        merged.update(found[category])
    if args.max_length:
        merged = collections.Counter(
            {t: n for t, n in merged.items() if len(t) <= args.max_length})

    for text in sorted(merged):
        print(f"{merged[text]}\t{text}" if args.counts else text)

    print(f"# {len(merged)} 条不重复字符串，类别: {', '.join(categories)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
