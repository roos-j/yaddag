#!/usr/bin/env python3
r"""Assign basic LaTeX section and theorem numbers without compiling LaTeX.

The supported counter model intentionally covers the common declaration forms:
``\newtheorem{env}{Caption}``, ``\newtheorem{env}{Caption}[section]``, and
``\newtheorem{env}[shared]{Caption}``.  It also numbers the standard heading
commands and simple ``equation`` environments.  It does not evaluate arbitrary
LaTeX counter macros or package-specific numbering customizations.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


@dataclass(frozen=True)
class TheoremEnvironment:
    """The counter used by one theorem-like environment, if it is numbered."""

    counter: str | None


def strip_comments(text: str) -> str:
    """Remove TeX comments while retaining newlines and character positions."""
    chars = list(text)
    index = 0
    while index < len(chars):
        if chars[index] != "%":
            index += 1
            continue
        slash_count = 0
        previous = index - 1
        while previous >= 0 and chars[previous] == "\\":
            slash_count += 1
            previous -= 1
        if slash_count % 2:
            index += 1
            continue
        while index < len(chars) and chars[index] not in "\r\n":
            chars[index] = " "
            index += 1
    return "".join(chars)


def skip_space(text: str, position: int) -> int:
    while position < len(text) and text[position].isspace():
        position += 1
    return position


def read_balanced(text: str, position: int, opener: str = "{", closer: str = "}") -> tuple[str, int]:
    if position >= len(text) or text[position] != opener:
        raise ValueError(f"expected {opener!r} at offset {position}")
    depth = 0
    start = position + 1
    index = position
    while index < len(text):
        character = text[index]
        if character == "\\":
            index += 2
            continue
        if character == opener:
            depth += 1
        elif character == closer:
            depth -= 1
            if depth == 0:
                return text[start:index], index + 1
        index += 1
    raise ValueError(f"unterminated {opener}{closer} group at offset {position}")


def read_command(text: str, position: int) -> tuple[str, int] | None:
    if position >= len(text) or text[position] != "\\":
        return None
    if position + 1 >= len(text):
        return "", position + 1
    if text[position + 1].isalpha() or text[position + 1] == "@":
        end = position + 2
        while end < len(text) and (text[end].isalpha() or text[end] == "@"):
            end += 1
        return text[position + 1 : end], end
    return text[position + 1], position + 2


def read_required_group(text: str, position: int, opener: str = "{", closer: str = "}") -> tuple[str, int] | None:
    position = skip_space(text, position)
    if position >= len(text) or text[position] != opener:
        return None
    try:
        return read_balanced(text, position, opener, closer)
    except ValueError:
        return None


def labels_in(text: str) -> list[str]:
    """Extract simple labels from already-delimited heading titles."""
    labels: list[str] = []
    position = 0
    while position < len(text):
        if text[position] != "\\":
            position += 1
            continue
        command = read_command(text, position)
        if command is None:
            position += 1
            continue
        name, end = command
        if name != "label":
            position = end
            continue
        group = read_required_group(text, end)
        if group is None:
            position = end
            continue
        label, position = group
        label = label.strip()
        if label:
            labels.append(label)
    return labels


def _parse_newtheorem(text: str, position: int) -> tuple[str, TheoremEnvironment, str | None, int] | None:
    """Parse a newtheorem declaration immediately following its command name."""
    position = skip_space(text, position)
    starred = position < len(text) and text[position] == "*"
    if starred:
        position = skip_space(text, position + 1)
    environment_group = read_required_group(text, position)
    if environment_group is None:
        return None
    environment, position = environment_group
    environment = environment.strip()
    if not environment:
        return None

    shared_counter: str | None = None
    shared_group = read_required_group(text, position, "[", "]")
    if shared_group is not None:
        shared_counter, position = shared_group
        shared_counter = shared_counter.strip() or None

    caption_group = read_required_group(text, position)
    if caption_group is None:
        return None
    _, position = caption_group

    within_counter: str | None = None
    if not starred and shared_counter is None:
        within_group = read_required_group(text, position, "[", "]")
        if within_group is not None:
            within_counter, position = within_group
            within_counter = within_counter.strip() or None

    counter = None if starred else (shared_counter or environment)
    return environment, TheoremEnvironment(counter), within_counter, position


def parse_numbering_declarations(text: str) -> tuple[dict[str, TheoremEnvironment], dict[str, str | None]]:
    """Read theorem declarations and basic counter-reset declarations."""
    environments: dict[str, TheoremEnvironment] = {}
    within: dict[str, str | None] = {}
    position = 0
    while position < len(text):
        if text[position] != "\\":
            position += 1
            continue
        command = read_command(text, position)
        if command is None:
            position += 1
            continue
        name, end = command
        if name == "newtheorem":
            declaration = _parse_newtheorem(text, end)
            if declaration is None:
                position = end
                continue
            environment, definition, within_counter, position = declaration
            environments[environment] = definition
            if definition.counter == environment:
                within[environment] = within_counter
            continue
        if name in {"counterwithin", "numberwithin"}:
            cursor = skip_space(text, end)
            if cursor < len(text) and text[cursor] == "*":
                cursor = skip_space(text, cursor + 1)
            counter_group = read_required_group(text, cursor)
            if counter_group is None:
                position = end
                continue
            counter, cursor = counter_group
            within_group = read_required_group(text, cursor)
            if within_group is None:
                position = cursor
                continue
            parent, position = within_group
            counter = counter.strip()
            parent = parent.strip()
            if counter and parent:
                within[counter] = parent
            continue
        position = end
    return environments, within


class CounterMachine:
    """A small counter model for standard LaTeX headings and theorem counters."""

    def __init__(self, *, book_class: bool, counter_within: dict[str, str | None]) -> None:
        heading_parents: dict[str, str | None] = {
            "part": None,
            "chapter": "part" if book_class else None,
            "section": "chapter" if book_class else None,
            "subsection": "section",
            "subsubsection": "subsection",
        }
        self.parents = {**heading_parents, **counter_within}
        self.values: defaultdict[str, int] = defaultdict(int)
        self.children: defaultdict[str, set[str]] = defaultdict(set)
        for counter, parent in self.parents.items():
            if parent:
                self.children[parent].add(counter)

    def reset(self, counter: str) -> None:
        self.values[counter] = 0
        for child in self.children[counter]:
            self.reset(child)

    def step(self, counter: str) -> None:
        self.values[counter] += 1
        for child in self.children[counter]:
            self.reset(child)

    def set(self, counter: str, value: int) -> None:
        self.values[counter] = value
        for child in self.children[counter]:
            self.reset(child)

    def add(self, counter: str, value: int) -> None:
        self.values[counter] += value
        for child in self.children[counter]:
            self.reset(child)

    def display(self, counter: str) -> str:
        parent = self.parents.get(counter)
        if parent:
            return f"{self.display(parent)}.{self.values[counter]}"
        return str(self.values[counter])


def document_uses_book_numbering(text: str) -> bool:
    match = re.search(r"\\documentclass(?:\s*\[[^\]]*\])?\s*\{([^{}]+)\}", text)
    if not match:
        return False
    return match.group(1).strip().lower() in {"book", "report", "memoir", "scrbook", "scrreprt"}


def _set_heading_number(labels: dict[str, str], title: str, number: str) -> None:
    for label in labels_in(title):
        labels[label] = number


def _integer_group(text: str, position: int) -> tuple[int, int] | None:
    group = read_required_group(text, position)
    if group is None:
        return None
    value, position = group
    try:
        return int(value.strip()), position
    except ValueError:
        return None


def build_label_numbers(latex_text: str) -> dict[str, str]:
    """Return the assigned display number for every ``\\label`` in ``latex_text``.

    Labels with no active numbered counter are represented by an empty string.
    """
    text = strip_comments(latex_text)
    environments, counter_within = parse_numbering_declarations(text)
    counter_within.setdefault("equation", None)
    machine = CounterMachine(book_class=document_uses_book_numbering(text), counter_within=counter_within)
    labels: dict[str, str] = {}
    current_number: str | None = None

    document_match = re.search(r"\\begin\s*\{\s*document\s*\}", text)
    position = document_match.end() if document_match else 0
    while position < len(text):
        if text[position] != "\\":
            position += 1
            continue
        command = read_command(text, position)
        if command is None:
            position += 1
            continue
        name, end = command

        if name in {"part", "chapter", "section", "subsection", "subsubsection"}:
            cursor = skip_space(text, end)
            starred = cursor < len(text) and text[cursor] == "*"
            if starred:
                cursor = skip_space(text, cursor + 1)
            short_title = read_required_group(text, cursor, "[", "]")
            if short_title is not None:
                _, cursor = short_title
            title = read_required_group(text, cursor)
            if title is None:
                position = end
                continue
            title_text, position = title
            if starred:
                current_number = None
                _set_heading_number(labels, title_text, "")
            else:
                machine.step(name)
                current_number = machine.display(name)
                _set_heading_number(labels, title_text, current_number)
            continue

        if name == "begin":
            environment_group = read_required_group(text, end)
            if environment_group is None:
                position = end
                continue
            environment, position = environment_group
            environment = environment.strip()
            theorem = environments.get(environment)
            if theorem is not None:
                if theorem.counter is None:
                    current_number = None
                else:
                    machine.step(theorem.counter)
                    current_number = machine.display(theorem.counter)
                continue
            if environment == "equation":
                machine.step("equation")
                current_number = machine.display("equation")
            elif environment == "equation*":
                current_number = None
            continue

        if name == "label":
            group = read_required_group(text, end)
            if group is None:
                position = end
                continue
            label, position = group
            label = label.strip()
            if label:
                labels[label] = current_number or ""
            continue

        if name in {"refstepcounter", "stepcounter"}:
            counter_group = read_required_group(text, end)
            if counter_group is None:
                position = end
                continue
            counter, position = counter_group
            counter = counter.strip()
            if counter:
                machine.step(counter)
                if name == "refstepcounter":
                    current_number = machine.display(counter)
            continue

        if name in {"setcounter", "addtocounter"}:
            counter_group = read_required_group(text, end)
            if counter_group is None:
                position = end
                continue
            counter, cursor = counter_group
            integer = _integer_group(text, cursor)
            if integer is None:
                position = cursor
                continue
            value, position = integer
            counter = counter.strip()
            if counter:
                if name == "setcounter":
                    machine.set(counter, value)
                else:
                    machine.add(counter, value)
            continue

        position = end
    return labels


def build_label_numbers_from_file(latex_path: Path) -> dict[str, str]:
    return build_label_numbers(latex_path.read_text(encoding="utf-8"))


def parse_aux_label_numbers(aux_text: str) -> dict[str, str]:
    """Read basic label numbers from an auxiliary file for regression tests."""
    labels: dict[str, str] = {}
    marker = "\\newlabel"
    position = 0
    while True:
        index = aux_text.find(marker, position)
        if index < 0:
            return labels
        label_group = read_required_group(aux_text, index + len(marker))
        if label_group is None:
            position = index + len(marker)
            continue
        label, cursor = label_group
        fields_group = read_required_group(aux_text, cursor)
        if fields_group is None:
            position = cursor
            continue
        fields, position = fields_group
        number_group = read_required_group(fields, 0)
        if number_group is None:
            continue
        number, _ = number_group
        label = label.strip()
        if label:
            labels[label] = number.strip()


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("latex", type=Path, help="input LaTeX file")
    parser.add_argument("output", type=Path, help="output JSON label-to-number mapping")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if not args.latex.is_file():
        print(f"error: LaTeX file not found: {args.latex}", file=sys.stderr)
        return 2
    try:
        labels = build_label_numbers_from_file(args.latex)
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(labels, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {args.output}: {len(labels)} labels")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
