"""Split ordinary MySQL schema SQL; not a DELIMITER/stored-routine runner."""
from __future__ import annotations

from typing import Iterator


def split_sql_statements(sql: str) -> Iterator[str]:
    start = index = 0
    quote: str | None = None
    comment: str | None = None
    while index < len(sql):
        char = sql[index]
        pair = sql[index:index + 2]
        if comment == "line":
            if char in "\r\n":
                comment = None
        elif comment == "block":
            if pair == "*/":
                comment = None
                index += 1
        elif quote:
            if char == "\\" and quote != "`":
                index += 1
            elif char == quote:
                if index + 1 < len(sql) and sql[index + 1] == quote:
                    index += 1
                else:
                    quote = None
        elif char in "'\"`":
            quote = char
        elif char == "#" or (pair == "--" and
                (index + 2 == len(sql) or sql[index + 2].isspace())):
            comment = "line"
        elif pair == "/*":
            comment = "block"
            index += 1
        elif char == ";":
            statement = sql[start:index].strip()
            if statement:
                yield statement
            start = index + 1
        index += 1
    if quote or comment == "block":
        raise ValueError("Unterminated quote or block comment in schema SQL")
    statement = sql[start:].strip()
    if statement:
        yield statement
