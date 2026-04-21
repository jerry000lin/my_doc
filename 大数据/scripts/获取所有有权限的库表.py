# -*- coding: utf-8 -*-
import os
import io
import re
import json
import shlex
import subprocess
from datetime import datetime


# =========================================================
# 配置区
# =========================================================

# 当前用户
PRINCIPAL_NAME = "hduser0539"

# hive 命令
HIVE_CMD = "hive"
HIVE_SILENT = True

# 上一个扫描脚本产出的本地 JSONL 根目录
INPUT_JSONL_ROOT = "/data02/linjunhao290/scan_table/output/jsonl"

TABLE_INVENTORY_PATH = os.path.join(INPUT_JSONL_ROOT, "table_inventory")
COLUMN_INVENTORY_PATH = os.path.join(INPUT_JSONL_ROOT, "column_inventory")

# 输出根目录
OUTPUT_ROOT = "/data02/linjunhao290/scan_table/auth_expand_output_local"

RAW_GRANT_OUTPUT_FILE = os.path.join(OUTPUT_ROOT, "raw_show_grant.jsonl")
AUTHORIZED_DATABASE_OUTPUT_FILE = os.path.join(OUTPUT_ROOT, "authorized_database.jsonl")
AUTHORIZED_TABLE_OUTPUT_FILE = os.path.join(OUTPUT_ROOT, "authorized_table.jsonl")
AUTHORIZED_COLUMN_OUTPUT_FILE = os.path.join(OUTPUT_ROOT, "authorized_column.jsonl")
SUMMARY_OUTPUT_FILE = os.path.join(OUTPUT_ROOT, "summary.json")

GRANT_COLUMNS = [
    "database",
    "table_name",
    "partition",
    "column_name",
    "principal_name",
    "privilege",
    "grant_option",
    "grant_time",
    "grantor",
]

IGNORE_LINE_PATTERNS = [
    re.compile(r"^\s*$"),
    re.compile(r"^Logging initialized", re.I),
    re.compile(r"^WARNING:", re.I),
    re.compile(r"^WARN", re.I),
    re.compile(r"^INFO", re.I),
    re.compile(r"^SLF4J", re.I),
    re.compile(r"^Picked up ", re.I),
    re.compile(r"^Time taken:", re.I),
    re.compile(r"^OK$", re.I),
]


# =========================================================
# 通用工具
# =========================================================

def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def ensure_dir(path):
    if path and (not os.path.exists(path)):
        os.makedirs(path)


def normalize_text(v):
    if v is None:
        return ""
    return str(v).strip()


def parse_scan_ts(ts):
    ts = normalize_text(ts)
    if not ts:
        return ""
    try:
        return datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
    except Exception:
        return ts


def is_newer_scan_ts(new_ts, old_ts):
    if not old_ts:
        return True
    if not new_ts:
        return False
    new_v = parse_scan_ts(new_ts)
    old_v = parse_scan_ts(old_ts)
    try:
        return new_v > old_v
    except Exception:
        return str(new_ts) > str(old_ts)


def write_json_file(path, obj):
    ensure_dir(os.path.dirname(path))
    with io.open(path, "w", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False, indent=2))


def write_jsonl_file(path, records):
    ensure_dir(os.path.dirname(path))
    with io.open(path, "w", encoding="utf-8") as f:
        for obj in records:
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def list_jsonl_files(dir_path):
    if not os.path.exists(dir_path):
        return []
    files = []
    for name in os.listdir(dir_path):
        if name.endswith(".jsonl"):
            files.append(os.path.join(dir_path, name))
    files.sort()
    return files


def iter_local_jsonl_records(dir_path):
    for path in list_jsonl_files(dir_path):
        with io.open(path, "r", encoding="utf-8") as f:
            for line_no, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    yield path, line_no, json.loads(line), None
                except Exception as e:
                    yield path, line_no, None, "{}: {}".format(e.__class__.__name__, str(e))


def split_grant_line(line):
    if "\t" in line:
        return line.rstrip("\n").split("\t")
    return re.split(r"\s+", line.strip())


def looks_like_header(parts):
    if len(parts) < len(GRANT_COLUMNS):
        return False
    normalized = [normalize_text(x).lower() for x in parts[:len(GRANT_COLUMNS)]]
    return normalized == GRANT_COLUMNS


def is_noise_line(line):
    for p in IGNORE_LINE_PATTERNS:
        if p.search(line):
            return True
    return False


def add_set_value(container, key, value):
    value = normalize_text(value)
    if not value:
        return
    container.setdefault(key, set()).add(value)


def set_to_sorted_list(v):
    return sorted(list(v)) if isinstance(v, set) else v


# =========================================================
# 读取本地 inventory
# =========================================================

def load_table_inventory_local():
    if not os.path.exists(TABLE_INVENTORY_PATH):
        raise RuntimeError("table inventory path not found: {}".format(TABLE_INVENTORY_PATH))

    latest = {}
    bad_line_count = 0

    for path, line_no, obj, err in iter_local_jsonl_records(TABLE_INVENTORY_PATH):
        if err is not None:
            bad_line_count += 1
            continue

        db_name = normalize_text(obj.get("db_name"))
        table_name = normalize_text(obj.get("table_name"))
        if not db_name or not table_name:
            continue

        key = (db_name, table_name)
        scan_ts = normalize_text(obj.get("scan_ts"))

        # 尽量只取 SUCCESS；如果没有 status 或为空，也允许
        status = normalize_text(obj.get("status"))
        old = latest.get(key)

        if old is None:
            latest[key] = obj
        else:
            old_ts = normalize_text(old.get("scan_ts"))
            old_status = normalize_text(old.get("status"))

            # SUCCESS 优先
            if status == "SUCCESS" and old_status != "SUCCESS":
                latest[key] = obj
            elif status == old_status:
                if is_newer_scan_ts(scan_ts, old_ts):
                    latest[key] = obj

    result = {}
    for key, obj in latest.items():
        db_name, table_name = key
        full_table_name = normalize_text(obj.get("full_table_name"))
        if not full_table_name:
            full_table_name = "{}.{}".format(db_name, table_name)

        result[key] = {
            "scan_ts": normalize_text(obj.get("scan_ts")),
            "db_name": db_name,
            "table_name": table_name,
            "full_table_name": full_table_name,
            "table_type": normalize_text(obj.get("table_type")),
            "is_temporary": obj.get("is_temporary"),
            "status": normalize_text(obj.get("status")),
            "source_method": normalize_text(obj.get("source_method")),
            "column_count": obj.get("column_count"),
            "table_comment": normalize_text(obj.get("table_comment")),
            "owner": normalize_text(obj.get("owner")),
            "create_time": normalize_text(obj.get("create_time")),
            "last_update_time": normalize_text(obj.get("last_update_time")),
            "last_access_time": normalize_text(obj.get("last_access_time")),
            "location": normalize_text(obj.get("location")),
            "provider": normalize_text(obj.get("provider")),
            "storage_handler": normalize_text(obj.get("storage_handler")),
            "serde_library": normalize_text(obj.get("serde_library")),
            "input_format": normalize_text(obj.get("input_format")),
            "output_format": normalize_text(obj.get("output_format")),
        }

    return result, bad_line_count


def load_column_inventory_local():
    if not os.path.exists(COLUMN_INVENTORY_PATH):
        raise RuntimeError("column inventory path not found: {}".format(COLUMN_INVENTORY_PATH))

    latest = {}
    bad_line_count = 0

    for path, line_no, obj, err in iter_local_jsonl_records(COLUMN_INVENTORY_PATH):
        if err is not None:
            bad_line_count += 1
            continue

        db_name = normalize_text(obj.get("db_name"))
        table_name = normalize_text(obj.get("table_name"))
        column_name = normalize_text(obj.get("column_name"))
        if not db_name or not table_name or not column_name:
            continue

        key = (db_name, table_name, column_name)
        scan_ts = normalize_text(obj.get("scan_ts"))

        old = latest.get(key)
        if old is None:
            latest[key] = obj
        else:
            old_ts = normalize_text(old.get("scan_ts"))
            if is_newer_scan_ts(scan_ts, old_ts):
                latest[key] = obj

    result = {}
    for key, obj in latest.items():
        db_name, table_name, column_name = key
        result[key] = {
            "scan_ts": normalize_text(obj.get("scan_ts")),
            "db_name": db_name,
            "table_name": table_name,
            "column_name": column_name,
            "data_type": normalize_text(obj.get("data_type")),
            "description": normalize_text(obj.get("description")),
            "nullable": normalize_text(obj.get("nullable")),
            "is_partition": normalize_text(obj.get("is_partition")),
            "is_bucket": normalize_text(obj.get("is_bucket")),
        }

    return result, bad_line_count


# =========================================================
# SHOW GRANT
# =========================================================

def run_show_grant(principal_name):
    silent_flag = "-S " if HIVE_SILENT else ""
    sql_text = 'SHOW GRANT USER {} ON ALL'.format(principal_name)
    cmd = '{} {}-e {}'.format(
        HIVE_CMD,
        silent_flag,
        shlex.quote(sql_text)
    )

    proc = subprocess.Popen(
        ["bash", "-lc", cmd],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True
    )
    stdout_text, stderr_text = proc.communicate()

    if proc.returncode != 0:
        raise RuntimeError(
            "run SHOW GRANT failed, returncode={}, stderr={}".format(
                proc.returncode,
                stderr_text.strip()
            )
        )

    return stdout_text, stderr_text


def parse_show_grant_output(stdout_text):
    rows = []
    header_skipped = False

    for raw_line in stdout_text.splitlines():
        line = raw_line.rstrip("\n")
        if is_noise_line(line):
            continue

        parts = split_grant_line(line)

        if not header_skipped and looks_like_header(parts):
            header_skipped = True
            continue

        if len(parts) < len(GRANT_COLUMNS):
            parts = parts + [""] * (len(GRANT_COLUMNS) - len(parts))

        if len(parts) > len(GRANT_COLUMNS):
            parts = parts[:len(GRANT_COLUMNS) - 1] + [" ".join(parts[len(GRANT_COLUMNS) - 1:])]

        row = dict(zip(GRANT_COLUMNS, parts))
        row = {k: normalize_text(v) for k, v in row.items()}

        if not row["database"] and not row["table_name"] and not row["column_name"]:
            continue

        if (not row["table_name"]) and (not row["column_name"]):
            scope_level = "DATABASE"
        elif row["table_name"] and (not row["column_name"]):
            scope_level = "TABLE"
        else:
            scope_level = "COLUMN"

        row["scope_level"] = scope_level
        rows.append(row)

    return rows


# =========================================================
# 构建索引
# =========================================================

def build_indexes(table_inventory, column_inventory):
    databases = set()
    tables_by_db = {}
    columns_by_table = {}
    columns_by_db = {}

    for (db_name, table_name), table_obj in table_inventory.items():
        databases.add(db_name)
        tables_by_db.setdefault(db_name, set()).add(table_name)

    for (db_name, table_name, column_name), col_obj in column_inventory.items():
        databases.add(db_name)
        tables_by_db.setdefault(db_name, set()).add(table_name)
        columns_by_table.setdefault((db_name, table_name), set()).add(column_name)
        columns_by_db.setdefault(db_name, set()).add((table_name, column_name))

    return {
        "databases": databases,
        "tables_by_db": tables_by_db,
        "columns_by_table": columns_by_table,
        "columns_by_db": columns_by_db,
    }


# =========================================================
# 授权对象聚合器
# =========================================================

def new_db_auth(db_name):
    return {
        "db_name": db_name,
        "principal_name": PRINCIPAL_NAME,
        "grant_scopes": set(),
        "privileges": set(),
        "grant_options": set(),
        "grantors": set(),
        "max_grant_time": "",
        "raw_grant_row_count": 0,
    }


def new_table_auth(db_name, table_name, table_meta):
    base = {
        "db_name": db_name,
        "table_name": table_name,
        "full_table_name": "{}.{}".format(db_name, table_name),
        "principal_name": PRINCIPAL_NAME,
        "grant_scopes": set(),
        "privileges": set(),
        "grant_options": set(),
        "grantors": set(),
        "max_grant_time": "",
        "raw_grant_row_count": 0,
        "has_db_level_grant": False,
        "has_table_level_grant": False,
        "has_column_level_grant_on_table": False,
        "run_ts": now_str(),
    }

    if table_meta:
        base.update({
            "scan_ts": table_meta.get("scan_ts", ""),
            "table_type": table_meta.get("table_type"),
            "is_temporary": table_meta.get("is_temporary"),
            "status": table_meta.get("status"),
            "source_method": table_meta.get("source_method"),
            "column_count": table_meta.get("column_count"),
            "table_comment": table_meta.get("table_comment"),
            "owner": table_meta.get("owner"),
            "create_time": table_meta.get("create_time"),
            "last_update_time": table_meta.get("last_update_time"),
            "last_access_time": table_meta.get("last_access_time"),
            "location": table_meta.get("location"),
            "provider": table_meta.get("provider"),
            "storage_handler": table_meta.get("storage_handler"),
            "serde_library": table_meta.get("serde_library"),
            "input_format": table_meta.get("input_format"),
            "output_format": table_meta.get("output_format"),
        })
    else:
        base.update({
            "scan_ts": "",
            "table_type": None,
            "is_temporary": None,
            "status": "GRANT_ONLY_NOT_IN_INVENTORY",
            "source_method": "grant_only",
            "column_count": None,
            "table_comment": None,
            "owner": None,
            "create_time": None,
            "last_update_time": None,
            "last_access_time": None,
            "location": None,
            "provider": None,
            "storage_handler": None,
            "serde_library": None,
            "input_format": None,
            "output_format": None,
        })

    return base


def new_column_auth(db_name, table_name, column_name, col_meta):
    base = {
        "db_name": db_name,
        "table_name": table_name,
        "column_name": column_name,
        "principal_name": PRINCIPAL_NAME,
        "grant_scopes": set(),
        "privileges": set(),
        "grant_options": set(),
        "grantors": set(),
        "max_grant_time": "",
        "raw_grant_row_count": 0,
        "has_db_level_grant": False,
        "has_table_level_grant": False,
        "has_column_level_grant": False,
        "run_ts": now_str(),
    }

    if col_meta:
        base.update({
            "scan_ts": col_meta.get("scan_ts", ""),
            "data_type": col_meta.get("data_type"),
            "description": col_meta.get("description"),
            "nullable": col_meta.get("nullable"),
            "is_partition": col_meta.get("is_partition"),
            "is_bucket": col_meta.get("is_bucket"),
        })
    else:
        base.update({
            "scan_ts": "",
            "data_type": None,
            "description": None,
            "nullable": None,
            "is_partition": None,
            "is_bucket": None,
        })

    return base


def apply_grant_common(obj, grant_row, scope_level):
    obj["grant_scopes"].add(scope_level)
    add_set_value(obj, "privileges", grant_row.get("privilege"))
    add_set_value(obj, "grant_options", grant_row.get("grant_option"))
    add_set_value(obj, "grantors", grant_row.get("grantor"))
    obj["raw_grant_row_count"] += 1

    gt = normalize_text(grant_row.get("grant_time"))
    if gt and (not obj["max_grant_time"] or gt > obj["max_grant_time"]):
        obj["max_grant_time"] = gt


# =========================================================
# 主展开逻辑
# =========================================================

def build_authorized_objects(table_inventory, column_inventory, grant_rows):
    idx = build_indexes(table_inventory, column_inventory)

    db_auth = {}
    table_auth = {}
    column_auth = {}

    def get_db_obj(db_name):
        if db_name not in db_auth:
            db_auth[db_name] = new_db_auth(db_name)
        return db_auth[db_name]

    def get_table_obj(db_name, table_name):
        key = (db_name, table_name)
        if key not in table_auth:
            table_auth[key] = new_table_auth(db_name, table_name, table_inventory.get(key))
        return table_auth[key]

    def get_column_obj(db_name, table_name, column_name):
        key = (db_name, table_name, column_name)
        if key not in column_auth:
            column_auth[key] = new_column_auth(db_name, table_name, column_name, column_inventory.get(key))
        return column_auth[key]

    for row in grant_rows:
        db_name = normalize_text(row.get("database"))
        table_name = normalize_text(row.get("table_name"))
        column_name = normalize_text(row.get("column_name"))
        scope_level = normalize_text(row.get("scope_level"))

        if not db_name:
            continue

        # 数据库一定纳入
        db_obj = get_db_obj(db_name)
        apply_grant_common(db_obj, row, scope_level)

        if scope_level == "DATABASE":
            db_obj["has_db_level_grant"] = True

            # 展开到该库下所有表
            for tb in sorted(idx["tables_by_db"].get(db_name, set())):
                tb_obj = get_table_obj(db_name, tb)
                apply_grant_common(tb_obj, row, "DATABASE")
                tb_obj["has_db_level_grant"] = True

            # 展开到该库下所有字段
            for tb, col in sorted(idx["columns_by_db"].get(db_name, set())):
                col_obj = get_column_obj(db_name, tb, col)
                apply_grant_common(col_obj, row, "DATABASE")
                col_obj["has_db_level_grant"] = True

        elif scope_level == "TABLE":
            if not table_name:
                continue

            tb_obj = get_table_obj(db_name, table_name)
            apply_grant_common(tb_obj, row, "TABLE")
            tb_obj["has_table_level_grant"] = True

            # 表级展开到所有字段
            for col in sorted(idx["columns_by_table"].get((db_name, table_name), set())):
                col_obj = get_column_obj(db_name, table_name, col)
                apply_grant_common(col_obj, row, "TABLE")
                col_obj["has_table_level_grant"] = True

        elif scope_level == "COLUMN":
            if not table_name or not column_name:
                continue

            tb_obj = get_table_obj(db_name, table_name)
            apply_grant_common(tb_obj, row, "COLUMN")
            tb_obj["has_column_level_grant_on_table"] = True

            col_obj = get_column_obj(db_name, table_name, column_name)
            apply_grant_common(col_obj, row, "COLUMN")
            col_obj["has_column_level_grant"] = True

    # 后处理
    db_records = []
    for db_name in sorted(db_auth.keys()):
        obj = db_auth[db_name]
        obj["grant_scopes"] = set_to_sorted_list(obj["grant_scopes"])
        obj["privileges"] = set_to_sorted_list(obj["privileges"])
        obj["grant_options"] = set_to_sorted_list(obj["grant_options"])
        obj["grantors"] = set_to_sorted_list(obj["grantors"])
        obj["has_db_level_grant"] = "DATABASE" in obj["grant_scopes"]
        obj["has_table_level_grant"] = "TABLE" in obj["grant_scopes"]
        obj["has_column_level_grant"] = "COLUMN" in obj["grant_scopes"]
        obj["expanded_table_count"] = len(idx["tables_by_db"].get(db_name, set()))
        obj["expanded_column_count"] = len(idx["columns_by_db"].get(db_name, set()))
        obj["authorization_source"] = ",".join(obj["grant_scopes"])
        obj["run_ts"] = now_str()
        db_records.append(obj)

    table_records = []
    for key in sorted(table_auth.keys()):
        obj = table_auth[key]
        obj["grant_scopes"] = set_to_sorted_list(obj["grant_scopes"])
        obj["privileges"] = set_to_sorted_list(obj["privileges"])
        obj["grant_options"] = set_to_sorted_list(obj["grant_options"])
        obj["grantors"] = set_to_sorted_list(obj["grantors"])
        obj["authorization_source"] = ",".join(obj["grant_scopes"])
        table_records.append(obj)

    column_records = []
    for key in sorted(column_auth.keys()):
        obj = column_auth[key]
        obj["grant_scopes"] = set_to_sorted_list(obj["grant_scopes"])
        obj["privileges"] = set_to_sorted_list(obj["privileges"])
        obj["grant_options"] = set_to_sorted_list(obj["grant_options"])
        obj["grantors"] = set_to_sorted_list(obj["grantors"])
        obj["authorization_source"] = ",".join(obj["grant_scopes"])
        column_records.append(obj)

    return db_records, table_records, column_records


# =========================================================
# main
# =========================================================

def main():
    ensure_dir(OUTPUT_ROOT)

    run_ts = now_str()

    table_inventory, table_bad_line_count = load_table_inventory_local()
    column_inventory, column_bad_line_count = load_column_inventory_local()

    stdout_text, stderr_text = run_show_grant(PRINCIPAL_NAME)
    grant_rows = parse_show_grant_output(stdout_text)

    # 原始 grant 先落一份
    write_jsonl_file(RAW_GRANT_OUTPUT_FILE, grant_rows)

    authorized_db_records, authorized_table_records, authorized_column_records = build_authorized_objects(
        table_inventory=table_inventory,
        column_inventory=column_inventory,
        grant_rows=grant_rows,
    )

    write_jsonl_file(AUTHORIZED_DATABASE_OUTPUT_FILE, authorized_db_records)
    write_jsonl_file(AUTHORIZED_TABLE_OUTPUT_FILE, authorized_table_records)
    write_jsonl_file(AUTHORIZED_COLUMN_OUTPUT_FILE, authorized_column_records)

    summary = {
        "run_ts": run_ts,
        "principal_name": PRINCIPAL_NAME,
        "input": {
            "table_inventory_path": TABLE_INVENTORY_PATH,
            "column_inventory_path": COLUMN_INVENTORY_PATH,
        },
        "output": {
            "raw_show_grant_file": RAW_GRANT_OUTPUT_FILE,
            "authorized_database_file": AUTHORIZED_DATABASE_OUTPUT_FILE,
            "authorized_table_file": AUTHORIZED_TABLE_OUTPUT_FILE,
            "authorized_column_file": AUTHORIZED_COLUMN_OUTPUT_FILE,
        },
        "counts": {
            "table_inventory_count": len(table_inventory),
            "column_inventory_count": len(column_inventory),
            "raw_grant_count": len(grant_rows),
            "authorized_database_count": len(authorized_db_records),
            "authorized_table_count": len(authorized_table_records),
            "authorized_column_count": len(authorized_column_records),
            "table_inventory_bad_line_count": table_bad_line_count,
            "column_inventory_bad_line_count": column_bad_line_count,
        },
        "show_grant_stderr": stderr_text,
    }

    write_json_file(SUMMARY_OUTPUT_FILE, summary)

    print("=" * 80)
    print("[{}] finished".format(run_ts))
    print("principal_name                 = {}".format(PRINCIPAL_NAME))
    print("raw_show_grant_file            = {}".format(RAW_GRANT_OUTPUT_FILE))
    print("authorized_database_file       = {}".format(AUTHORIZED_DATABASE_OUTPUT_FILE))
    print("authorized_table_file          = {}".format(AUTHORIZED_TABLE_OUTPUT_FILE))
    print("authorized_column_file         = {}".format(AUTHORIZED_COLUMN_OUTPUT_FILE))
    print("summary_json                   = {}".format(SUMMARY_OUTPUT_FILE))
    print("table_inventory_count          = {}".format(len(table_inventory)))
    print("column_inventory_count         = {}".format(len(column_inventory)))
    print("raw_grant_count                = {}".format(len(grant_rows)))
    print("authorized_database_count      = {}".format(len(authorized_db_records)))
    print("authorized_table_count         = {}".format(len(authorized_table_records)))
    print("authorized_column_count        = {}".format(len(authorized_column_records)))


if __name__ == "__main__":
    main()