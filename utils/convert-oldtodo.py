#!/usr/bin/env python3
"""
md_timespan_promoter.py

Transforms a Markdown backlog where each timespan uses Heading 1 (e.g., "# Short term")
and contains top-level bullet items. For every top-level bullet under a Heading 1,
this script creates a new Heading 1 from that bullet's text and adds a
"* Timespan: <original H1>" bullet beneath it. Sub-bullets are preserved.

Example (input fragment):

# Short term
* Add virtual keyboard support to QtWebEngine sites
* Low power / eco mode
    * Attempts to save battery life by telling the system to do less
        * Slow down background task ticks

Becomes (output fragment):

# Add virtual keyboard support to QtWebEngine sites
* Timespan: Short term

# Low power / eco mode
* Timespan: Short term
* Attempts to save battery life by telling the system to do less
    * Slow down background task ticks

Usage:
    python md_timespan_promoter.py input.md output.md
"""

import argparse
import re
from typing import List, Tuple, Optional


H1_RE = re.compile(r'^\s{0,3}#\s+(.*)\s*$')  # capture text after single '# '
BULLET_RE = re.compile(r'^(\s*)([*-])\s+(.*\S)\s*$')  # indent, marker, text


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Promote top-level bullets under H1 to new H1s and add a timespan bullet.")
    p.add_argument("input", help="Path to input Markdown file")
    p.add_argument("output", help="Path to output Markdown file")
    p.add_argument("--keep-empty-sections", action="store_true",
                   help="If set, sections with no top-level bullets emit a comment placeholder.")
    return p.parse_args()


def is_h1(line: str) -> Optional[str]:
    m = H1_RE.match(line)
    if not m:
        return None
    # Ensure it's exactly one '#' (not ## or ###)
    # Our regex already targets '#' + space. But "## " would also match if we don't guard.
    # So we confirm the original starts with exactly one '# ' (no second '#').
    stripped = line.lstrip()
    if stripped.startswith("# ") and not stripped.startswith("##"):
        return m.group(1).strip()
    return None


def is_bullet(line: str) -> Optional[Tuple[int, str, str]]:
    """Return (indent_spaces, marker, text) if bullet; else None."""
    m = BULLET_RE.match(line)
    if not m:
        return None
    indent = len(m.group(1).replace("\t", "    "))  # normalize tabs as 4 spaces for safety
    marker = m.group(2)
    text = m.group(3).rstrip()
    return indent, marker, text


def collect_blocks(lines: List[str]) -> List[str]:
    """
    Transform the document per the rules described.
    We scan by H1 sections; within each, for each top-level bullet (indent == 0),
    we create a new H1 with the bullet text and add a timespan bullet.
    Sub-content is preserved beneath, with indentation normalized to start at 0.
    """
    out: List[str] = []
    i = 0
    n = len(lines)

    current_h1: Optional[str] = None
    saw_any_blocks_in_section = False

    def flush_empty_section_placeholder():
        if current_h1 is not None:
            out.append(f"<!-- Section '{current_h1}' had no top-level items to promote -->\n")

    while i < n:
        line = lines[i]
        h1_text = is_h1(line)

        if h1_text is not None:
            # Starting a new H1 section
            if current_h1 is not None and not saw_any_blocks_in_section:
                # Optionally record a placeholder for empty sections
                pass
            current_h1 = h1_text
            saw_any_blocks_in_section = False
            i += 1
            continue

        # If we are inside an H1 section, look for top-level bullets
        if current_h1 is not None:
            binfo = is_bullet(line)
            if binfo and binfo[0] == 0:
                # Start collecting this bullet block: the bullet line, and all subsequent lines
                # that are part of this block (i.e., until next top-level bullet or next H1).
                block_lines = [line]
                i += 1

                # Collect block continuation lines
                while i < n:
                    next_line = lines[i]
                    if is_h1(next_line) is not None:
                        break
                    nbinfo = is_bullet(next_line)
                    if nbinfo and nbinfo[0] == 0:
                        # Next top-level bullet begins -> current block ends
                        break
                    block_lines.append(next_line)
                    i += 1

                # Transform the collected block
                new_section = transform_block_to_h1(block_lines, current_h1)
                # Separate sections by a blank line unless file start
                if out and (out[-1].strip() != ""):
                    out.append("\n")
                out.extend(new_section)
                saw_any_blocks_in_section = True
                continue

        # Default: just move along. We do not copy unrelated lines to output,
        # because output is supposed to be the promoted structure only.
        i += 1

    return out


def transform_block_to_h1(block_lines: List[str], current_h1: str) -> List[str]:
    """
    Convert a single top-level bullet block into a new H1 section:
        # <bullet text>
        * Timespan: <current_h1>
        <preserved sub-content>
    """
    assert block_lines, "Empty block passed to transform"

    # First line must be the top-level bullet
    binfo = is_bullet(block_lines[0])
    if not binfo or binfo[0] != 0:
        # Fallback: just return as-is with timespan at top
        header = block_lines[0].strip() if block_lines else "Untitled"
        title = header
    else:
        _, _, title = binfo

    out: List[str] = []
    out.append(f"# {title}\n")

    # Remaining lines are sub-content. Normalize indentation so that the smallest
    # non-zero indent becomes zero (outdented), preserving bullet hierarchy.
    sub_content = block_lines[1:]

    # Compute minimal indent among non-empty lines (in spaces), ignoring blank lines
    min_indent = None
    for ln in sub_content:
        if ln.strip() == "":
            continue
        # measure leading spaces (tabs treated as 4 spaces)
        leading = len(ln.replace("\t", "    ")) - len(ln.replace("\t", "    ").lstrip(" "))
        if min_indent is None or (leading < min_indent and ln.strip() != ""):
            min_indent = leading

    if min_indent is None:
        # No sub-content
        return out

    # Outdent subcontent
    for ln in sub_content:
        if ln.strip() == "":
            out.append(ln)
        else:
            # Safely outdent
            normalized = ln.replace("\t", "    ")
            out.append(normalized[min_indent:])

    return out


def main():
    args = parse_args()
    with open(args.input, "r", encoding="utf-8") as f:
        lines = f.readlines()

    transformed = collect_blocks(lines)

    with open(args.output, "w", encoding="utf-8") as f:
        f.writelines(transformed)

    print(f"✅ Wrote transformed file to: {args.output}")


if __name__ == "__main__":
    main()