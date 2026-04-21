# -*- coding: utf-8 -*-
"""
Utilities for exploring PySpark metadata scan outputs in Jupyter.

Typical usage:

    from 查看扫库结果 import open_scan_output

    viewer = open_scan_output("/data02/linjunhao290/scan_table/output")
    viewer.overview()
    viewer.search_tables("user")
    viewer.search_columns("dt", table_name="dwd_user_info")
    viewer.view_table("dw", "dwd_user_info")
    viewer.search_errors("ClassNotFound")
"""

from __future__ import annotations

import io
import json
import os
import re
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Sequence

try:
    import pandas as pd
except ImportError as exc:  # pragma: no cover
    pd = None
    PANDAS_IMPORT_ERROR = exc
else:
    PANDAS_IMPORT_ERROR = None


SCAN_SCRIPT_NAME = "pyspark_扫库.py"
OUTPUT_DIR_ENV_VAR = "SCAN_TABLE_OUTPUT_DIR"

INVENTORY_CONFIG = {
    "table_inventory": {
        "dir_name": "table_inventory",
        "columns": [
            "scan_ts",
            "db_name",
            "table_name",
            "table_type",
            "is_temporary",
            "status",
            "source_method",
            "column_count",
            "error_type",
            "error_message",
        ],
        "search_fields": ["db_name", "table_name", "status", "source_method", "error_message"],
    },
    "column_inventory": {
        "dir_name": "column_inventory",
        "columns": [
            "scan_ts",
            "db_name",
            "table_name",
            "table_type",
            "is_temporary",
            "column_index",
            "column_name",
            "data_type",
            "nullable",
            "is_partition",
            "is_bucket",
            "description",
        ],
        "search_fields": ["db_name", "table_name", "column_name", "data_type", "description"],
    },
    "error_inventory": {
        "dir_name": "error_inventory",
        "columns": [
            "scan_ts",
            "level",
            "db_name",
            "table_name",
            "error_type",
            "error_message",
            "traceback",
        ],
        "search_fields": ["level", "db_name", "table_name", "error_type", "error_message", "traceback"],
    },
    "skip_inventory": {
        "dir_name": "skip_inventory",
        "columns": [
            "scan_ts",
            "level",
            "db_name",
            "table_name",
            "reason",
            "matched_pattern",
        ],
        "search_fields": ["level", "db_name", "table_name", "reason", "matched_pattern"],
    },
    "class_not_found_inventory": {
        "dir_name": "class_not_found_inventory",
        "columns": [
            "scan_ts",
            "level",
            "db_name",
            "table_name",
            "missing_class_name",
            "error_type",
            "error_message",
        ],
        "search_fields": ["level", "db_name", "table_name", "missing_class_name", "error_type", "error_message"],
    },
}

INVENTORY_ALIASES = {
    "table": "table_inventory",
    "tables": "table_inventory",
    "column": "column_inventory",
    "columns": "column_inventory",
    "error": "error_inventory",
    "errors": "error_inventory",
    "skip": "skip_inventory",
    "skips": "skip_inventory",
    "class": "class_not_found_inventory",
    "class_not_found": "class_not_found_inventory",
    "missing_class": "class_not_found_inventory",
}


def ensure_pandas() -> None:
    if pd is None:  # pragma: no cover
        raise ImportError(
            "pandas is required for this script. Please install pandas first."
        ) from PANDAS_IMPORT_ERROR


def read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    with io.open(path, "r", encoding="utf-8") as fp:
        return json.load(fp)


def iter_jsonl(path: Path) -> Iterator[Dict[str, Any]]:
    with io.open(path, "r", encoding="utf-8") as fp:
        for line_no, line in enumerate(fp, 1):
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except Exception as exc:
                yield {
                    "__parse_error__": True,
                    "__line_no__": line_no,
                    "error_message": f"{exc.__class__.__name__}: {exc}",
                }


def to_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def text_match(value: Any, pattern: str, regex: bool = False, ignore_case: bool = True) -> bool:
    text = to_text(value)
    if regex:
        flags = re.IGNORECASE if ignore_case else 0
        return re.search(pattern, text, flags) is not None

    if ignore_case:
        return pattern.lower() in text.lower()
    return pattern in text


def infer_output_dir() -> Optional[Path]:
    candidates: List[Path] = []

    env_path = os.environ.get(OUTPUT_DIR_ENV_VAR, "").strip()
    if env_path:
        candidates.append(Path(env_path).expanduser())

    current_file = Path(__file__).resolve()
    scan_script_path = current_file.with_name(SCAN_SCRIPT_NAME)
    if scan_script_path.exists():
        content = scan_script_path.read_text(encoding="utf-8")
        matched = re.search(r'OUTPUT_DIR\s*=\s*["\'](.+?)["\']', content)
        if matched:
            candidates.append(Path(matched.group(1)).expanduser())

    for path in candidates:
        if (path / "jsonl").exists() or (path / "_meta").exists():
            return path

    return candidates[0] if candidates else None


class ScanResultViewer(object):
    def __init__(self, output_dir: Optional[str] = None):
        ensure_pandas()

        resolved_dir = Path(output_dir).expanduser() if output_dir else infer_output_dir()
        if resolved_dir is None:
            raise FileNotFoundError(
                "Could not infer the scan output directory. Please pass output_dir explicitly."
            )

        self.output_dir = resolved_dir.resolve()
        self.meta_dir = self.output_dir / "_meta"
        self.jsonl_root_dir = self.output_dir / "jsonl"
        self.excel_root_dir = self.output_dir / "excel"

        if not self.output_dir.exists():
            raise FileNotFoundError(
                f"Scan output directory does not exist: {self.output_dir}"
            )

    def normalize_inventory_name(self, inventory: str) -> str:
        inventory = inventory.strip()
        inventory = INVENTORY_ALIASES.get(inventory, inventory)
        if inventory not in INVENTORY_CONFIG:
            raise ValueError(f"Unsupported inventory: {inventory}")
        return inventory

    def inventory_dir(self, inventory: str) -> Path:
        inventory = self.normalize_inventory_name(inventory)
        return self.jsonl_root_dir / INVENTORY_CONFIG[inventory]["dir_name"]

    def inventory_files(self, inventory: str) -> List[Path]:
        inventory_dir = self.inventory_dir(inventory)
        if not inventory_dir.exists():
            return []
        return sorted(inventory_dir.glob("part_*.jsonl"))

    def build_dataframe(
        self,
        rows: List[Dict[str, Any]],
        columns: Optional[Sequence[str]] = None,
    ):
        if not rows:
            return pd.DataFrame(columns=list(columns or []))

        df = pd.DataFrame(rows)
        if columns:
            ordered = [col for col in columns if col in df.columns]
            extra = [col for col in df.columns if col not in ordered]
            df = df[ordered + extra]
        return df

    def filter_inventory(
        self,
        inventory: str,
        *,
        exact_filters: Optional[Dict[str, Any]] = None,
        contains_filters: Optional[Dict[str, str]] = None,
        keyword: Optional[str] = None,
        keyword_fields: Optional[Sequence[str]] = None,
        regex: bool = False,
        limit: Optional[int] = 200,
        columns: Optional[Sequence[str]] = None,
    ):
        inventory = self.normalize_inventory_name(inventory)
        rows: List[Dict[str, Any]] = []

        for file_path in self.inventory_files(inventory):
            for record in iter_jsonl(file_path):
                if record.get("__parse_error__"):
                    continue

                if exact_filters:
                    is_match = True
                    for key, expected in exact_filters.items():
                        if expected is None or expected == "":
                            continue
                        if record.get(key) != expected:
                            is_match = False
                            break
                    if not is_match:
                        continue

                if contains_filters:
                    is_match = True
                    for key, pattern in contains_filters.items():
                        if not pattern:
                            continue
                        if not text_match(record.get(key), pattern, regex=regex):
                            is_match = False
                            break
                    if not is_match:
                        continue

                if keyword:
                    fields = list(keyword_fields or INVENTORY_CONFIG[inventory]["search_fields"])
                    if not any(text_match(record.get(field), keyword, regex=regex) for field in fields):
                        continue

                rows.append(record)
                if limit is not None and len(rows) >= limit:
                    return self.build_dataframe(rows, columns)

        return self.build_dataframe(rows, columns)

    def list_inventories(self):
        rows = []
        for inventory in INVENTORY_CONFIG:
            inventory_dir = self.inventory_dir(inventory)
            rows.append(
                {
                    "inventory": inventory,
                    "exists": inventory_dir.exists(),
                    "part_file_count": len(self.inventory_files(inventory)),
                    "jsonl_dir": str(inventory_dir),
                }
            )
        return self.build_dataframe(rows, ["inventory", "exists", "part_file_count", "jsonl_dir"])

    def overview(self):
        run_summary = read_json(self.meta_dir / "run_summary.json")
        export_summary = read_json(self.meta_dir / "export_summary.json")
        config_snapshot = read_json(self.meta_dir / "config_snapshot.json")

        rows = [
            {"group": "path", "metric": "output_dir", "value": str(self.output_dir)},
            {"group": "path", "metric": "meta_dir", "value": str(self.meta_dir)},
            {"group": "path", "metric": "jsonl_root_dir", "value": str(self.jsonl_root_dir)},
            {"group": "path", "metric": "excel_root_dir", "value": str(self.excel_root_dir)},
        ]

        if run_summary:
            rows.append({"group": "run", "metric": "finish_ts", "value": run_summary.get("finish_ts", "")})
            for key, value in run_summary.get("counts", {}).items():
                rows.append({"group": "count", "metric": key, "value": value})
            for key, value in run_summary.get("jsonl_part_counts", {}).items():
                rows.append({"group": "jsonl_parts", "metric": key, "value": value})

        if export_summary:
            rows.append({"group": "export", "metric": "export_ts", "value": export_summary.get("export_ts", "")})
            rows.append({"group": "export", "metric": "excel_file_count", "value": len(export_summary.get("results", []))})

        if config_snapshot:
            rows.append({"group": "config", "metric": "SKIP_PROCESSED", "value": config_snapshot.get("SKIP_PROCESSED", "")})
            rows.append({"group": "config", "metric": "INCLUDE_TEMP_VIEWS", "value": config_snapshot.get("INCLUDE_TEMP_VIEWS", "")})

        for inventory in INVENTORY_CONFIG:
            rows.append(
                {
                    "group": "actual_parts",
                    "metric": inventory,
                    "value": len(self.inventory_files(inventory)),
                }
            )

        return self.build_dataframe(rows, ["group", "metric", "value"])

    def preview_inventory(self, inventory: str, n: int = 20):
        inventory = self.normalize_inventory_name(inventory)
        return self.filter_inventory(
            inventory,
            limit=n,
            columns=INVENTORY_CONFIG[inventory]["columns"],
        )

    def load_inventory(self, inventory: str, limit: Optional[int] = None):
        inventory = self.normalize_inventory_name(inventory)
        df = self.filter_inventory(
            inventory,
            limit=limit,
            columns=INVENTORY_CONFIG[inventory]["columns"],
        )
        if "scan_ts" in df.columns and not df.empty:
            sort_columns = ["scan_ts"]
            if "db_name" in df.columns:
                sort_columns.append("db_name")
            if "table_name" in df.columns:
                sort_columns.append("table_name")
            df = df.sort_values(sort_columns, ascending=[False] + [True] * (len(sort_columns) - 1))
        return df.reset_index(drop=True)

    def summarize_table_status(self):
        df = self.load_inventory("table_inventory")
        if df.empty:
            return pd.DataFrame(columns=["status", "source_method", "table_count"])

        return (
            df.fillna("")
            .groupby(["status", "source_method"], dropna=False)
            .size()
            .reset_index(name="table_count")
            .sort_values(["table_count", "status", "source_method"], ascending=[False, True, True])
            .reset_index(drop=True)
        )

    def summarize_skip_reasons(self):
        df = self.load_inventory("skip_inventory")
        if df.empty:
            return pd.DataFrame(columns=["level", "reason", "matched_pattern", "count"])

        return (
            df.fillna("")
            .groupby(["level", "reason", "matched_pattern"], dropna=False)
            .size()
            .reset_index(name="count")
            .sort_values(["count", "level", "reason"], ascending=[False, True, True])
            .reset_index(drop=True)
        )

    def summarize_missing_classes(self):
        df = self.load_inventory("class_not_found_inventory")
        if df.empty:
            return pd.DataFrame(columns=["missing_class_name", "count"])

        return (
            df.fillna("")
            .groupby(["missing_class_name"], dropna=False)
            .size()
            .reset_index(name="count")
            .sort_values(["count", "missing_class_name"], ascending=[False, True])
            .reset_index(drop=True)
        )

    def search_tables(
        self,
        keyword: Optional[str] = None,
        *,
        db_name: Optional[str] = None,
        table_name: Optional[str] = None,
        status: Optional[str] = None,
        source_method: Optional[str] = None,
        regex: bool = False,
        limit: Optional[int] = 200,
    ):
        df = self.filter_inventory(
            "table_inventory",
            exact_filters={"status": status},
            contains_filters={
                "db_name": db_name or "",
                "table_name": table_name or "",
                "source_method": source_method or "",
            },
            keyword=keyword,
            regex=regex,
            limit=limit,
            columns=INVENTORY_CONFIG["table_inventory"]["columns"],
        )
        if "scan_ts" in df.columns and not df.empty:
            df = df.sort_values(["scan_ts", "db_name", "table_name"], ascending=[False, True, True])
        return df.reset_index(drop=True)

    def search_columns(
        self,
        keyword: Optional[str] = None,
        *,
        db_name: Optional[str] = None,
        table_name: Optional[str] = None,
        column_name: Optional[str] = None,
        data_type: Optional[str] = None,
        regex: bool = False,
        limit: Optional[int] = 200,
    ):
        df = self.filter_inventory(
            "column_inventory",
            contains_filters={
                "db_name": db_name or "",
                "table_name": table_name or "",
                "column_name": column_name or "",
                "data_type": data_type or "",
            },
            keyword=keyword,
            regex=regex,
            limit=limit,
            columns=INVENTORY_CONFIG["column_inventory"]["columns"],
        )
        if "scan_ts" in df.columns and not df.empty:
            df = df.sort_values(
                ["scan_ts", "db_name", "table_name", "column_index"],
                ascending=[False, True, True, True],
            )
        return df.reset_index(drop=True)

    def search_errors(
        self,
        keyword: Optional[str] = None,
        *,
        db_name: Optional[str] = None,
        table_name: Optional[str] = None,
        level: Optional[str] = None,
        error_type: Optional[str] = None,
        regex: bool = False,
        limit: Optional[int] = 200,
    ):
        df = self.filter_inventory(
            "error_inventory",
            exact_filters={"level": level},
            contains_filters={
                "db_name": db_name or "",
                "table_name": table_name or "",
                "error_type": error_type or "",
            },
            keyword=keyword,
            regex=regex,
            limit=limit,
            columns=INVENTORY_CONFIG["error_inventory"]["columns"],
        )
        if "scan_ts" in df.columns and not df.empty:
            df = df.sort_values(["scan_ts", "level", "db_name", "table_name"], ascending=[False, True, True, True])
        return df.reset_index(drop=True)

    def search_skips(
        self,
        keyword: Optional[str] = None,
        *,
        db_name: Optional[str] = None,
        table_name: Optional[str] = None,
        level: Optional[str] = None,
        regex: bool = False,
        limit: Optional[int] = 200,
    ):
        df = self.filter_inventory(
            "skip_inventory",
            exact_filters={"level": level},
            contains_filters={
                "db_name": db_name or "",
                "table_name": table_name or "",
            },
            keyword=keyword,
            regex=regex,
            limit=limit,
            columns=INVENTORY_CONFIG["skip_inventory"]["columns"],
        )
        if "scan_ts" in df.columns and not df.empty:
            df = df.sort_values(["scan_ts", "level", "db_name", "table_name"], ascending=[False, True, True, True])
        return df.reset_index(drop=True)

    def search_missing_classes(
        self,
        keyword: Optional[str] = None,
        *,
        missing_class_name: Optional[str] = None,
        db_name: Optional[str] = None,
        table_name: Optional[str] = None,
        level: Optional[str] = None,
        regex: bool = False,
        limit: Optional[int] = 200,
    ):
        df = self.filter_inventory(
            "class_not_found_inventory",
            exact_filters={"level": level},
            contains_filters={
                "missing_class_name": missing_class_name or "",
                "db_name": db_name or "",
                "table_name": table_name or "",
            },
            keyword=keyword,
            regex=regex,
            limit=limit,
            columns=INVENTORY_CONFIG["class_not_found_inventory"]["columns"],
        )
        if "scan_ts" in df.columns and not df.empty:
            df = df.sort_values(["scan_ts", "level", "db_name", "table_name"], ascending=[False, True, True, True])
        return df.reset_index(drop=True)

    def view_table(
        self,
        db_name: str,
        table_name: str,
        *,
        column_limit: Optional[int] = None,
        error_limit: int = 200,
    ) -> Dict[str, Any]:
        table_df = self.filter_inventory(
            "table_inventory",
            exact_filters={"db_name": db_name, "table_name": table_name},
            limit=None,
            columns=INVENTORY_CONFIG["table_inventory"]["columns"],
        )
        if table_df.empty:
            raise ValueError(f"Table not found: {db_name}.{table_name}")

        table_df = table_df.sort_values(["scan_ts"], ascending=[False]).reset_index(drop=True)
        latest_scan_ts = table_df.iloc[0]["scan_ts"] if "scan_ts" in table_df.columns else None

        column_df = self.filter_inventory(
            "column_inventory",
            exact_filters={"db_name": db_name, "table_name": table_name},
            limit=column_limit,
            columns=INVENTORY_CONFIG["column_inventory"]["columns"],
        )
        if latest_scan_ts and not column_df.empty and "scan_ts" in column_df.columns:
            latest_column_df = column_df[column_df["scan_ts"] == latest_scan_ts]
            if not latest_column_df.empty:
                column_df = latest_column_df
        if "column_index" in column_df.columns and not column_df.empty:
            column_df = column_df.sort_values(["column_index"], ascending=[True]).reset_index(drop=True)
        else:
            column_df = column_df.reset_index(drop=True)

        error_df = self.filter_inventory(
            "error_inventory",
            exact_filters={"db_name": db_name, "table_name": table_name},
            limit=error_limit,
            columns=INVENTORY_CONFIG["error_inventory"]["columns"],
        )
        if latest_scan_ts and not error_df.empty and "scan_ts" in error_df.columns:
            latest_error_df = error_df[error_df["scan_ts"] == latest_scan_ts]
            if not latest_error_df.empty:
                error_df = latest_error_df
        error_df = error_df.reset_index(drop=True)

        return {
            "table": table_df,
            "columns": column_df,
            "errors": error_df,
        }

    def search_all(
        self,
        keyword: str,
        *,
        inventories: Optional[Sequence[str]] = None,
        limit_per_inventory: int = 50,
        regex: bool = False,
    ) -> Dict[str, Any]:
        inventory_names = inventories or ["table_inventory", "column_inventory", "error_inventory"]
        results: Dict[str, Any] = {}

        for inventory in inventory_names:
            normalized_inventory = self.normalize_inventory_name(inventory)
            df = self.filter_inventory(
                normalized_inventory,
                keyword=keyword,
                regex=regex,
                limit=limit_per_inventory,
                columns=INVENTORY_CONFIG[normalized_inventory]["columns"],
            )
            if "scan_ts" in df.columns and not df.empty:
                df = df.sort_values(["scan_ts"], ascending=[False])
            results[normalized_inventory] = df.reset_index(drop=True)

        return results

    def usage_examples(self) -> str:
        examples = [
            "viewer = open_scan_output('/data02/linjunhao290/scan_table/output')",
            "viewer.overview()",
            "viewer.preview_inventory('table')",
            "table_df = viewer.load_inventory('table')",
            "viewer.summarize_table_status()",
            "viewer.search_tables('user')",
            "viewer.search_columns('dt', table_name='dwd_user_info')",
            "viewer.search_errors('ClassNotFound')",
            "viewer.search_skips('already_processed')",
            "viewer.summarize_skip_reasons()",
            "viewer.search_missing_classes(missing_class_name='com.xxx.serde.YourSerde')",
            "viewer.summarize_missing_classes()",
            "viewer.view_table('dw', 'dwd_user_info')",
            "viewer.search_all('user_id')",
        ]
        return "\n".join(examples)


def open_scan_output(output_dir: Optional[str] = None) -> ScanResultViewer:
    return ScanResultViewer(output_dir=output_dir)


if __name__ == "__main__":
    try:
        viewer = open_scan_output()
        print(viewer.overview().to_string(index=False))
        print()
        print("Jupyter examples:")
        print(viewer.usage_examples())
    except Exception as exc:
        print(f"Could not open scan output: {exc}")
        print("Pass output_dir explicitly, for example:")
        print("viewer = open_scan_output('/data02/linjunhao290/scan_table/output')")
