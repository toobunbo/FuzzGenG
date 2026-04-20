import csv
from typing import NamedTuple

class SigRow(NamedTuple):
    name: str
    file: str
    start_line: int
    end_line: int
    param_name: str
    param_type: str

class FuncRow(NamedTuple):
    name: str
    file: str
    start_line: int
    end_line: int
    scope: str

def load_signatures(path: str) -> list[SigRow]:
    rows = []
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            rows.append(SigRow(
                name=r["name"], file=r["file"],
                start_line=int(r["start_line"]), end_line=int(r["end_line"]),
                param_name=r["param_name"], param_type=r.get("param_type", ""),
            ))
    return rows

def load_functions(path: str) -> list[FuncRow]:
    rows = []
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            rows.append(FuncRow(
                name=r["name"], file=r["file"],
                start_line=int(r["start_line"]), end_line=int(r["end_line"]),
                scope=r.get("scope", ""),
            ))
    return rows
