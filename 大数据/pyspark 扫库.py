# -*- coding: utf-8 -*-
import os
import io
import re
import json
import fnmatch
import traceback
import getpass
from datetime import datetime

from pyspark.sql import SparkSession
from openpyxl import Workbook


# =========================================================
# 配置区
# =========================================================

OUTPUT_DIR = "/data02/linjunhao290/scan_table/output"

SKIP_PROCESSED = True
INCLUDE_TEMP_VIEWS = False

PRINT_EVERY_SUCCESS = 50
PRINT_EVERY_SKIPPED = 200

ENABLE_FSYNC = False

MAX_ERROR_MSG_LEN = 4000
MAX_TRACEBACK_LEN = 12000

EXCEL_MAX_CELL_LEN = 32767
EXCEL_MAX_ROWS_PER_SHEET = 1048576
EXCEL_HEADER_ROWS = 1
EXCEL_DATA_ROWS_PER_SHEET = EXCEL_MAX_ROWS_PER_SHEET - EXCEL_HEADER_ROWS

JSONL_MAX_RECORDS_TABLE = 200000
JSONL_MAX_RECORDS_COLUMN = 500000
JSONL_MAX_RECORDS_ERROR = 100000
JSONL_MAX_RECORDS_SKIP = 100000
JSONL_MAX_RECORDS_CLASS_MISSING = 100000

WRITE_SKIP_INVENTORY = True
WRITE_CLASS_NOT_FOUND_INVENTORY = True

# 是否开启 select * limit 0 权限探测
# 开启后会更慢，但能给出“当前 user 是否能读”的实际探测结果
ENABLE_SELECT_PERMISSION_CHECK = True

# =========================================================
# 跳过规则
# =========================================================

INCLUDE_DATABASE_PATTERNS = [
    # "dw_*",
    # "dm_*",
]

SKIP_DATABASE_PATTERNS = [
    "*_ind",
]

INCLUDE_TABLE_PATTERNS = [
]

SKIP_TABLE_PATTERNS = [
]

INCLUDE_FULL_TABLE_PATTERNS = [
]

SKIP_FULL_TABLE_PATTERNS = [
]

# =========================================================
# 路径定义
# =========================================================

META_DIR = os.path.join(OUTPUT_DIR, "_meta")
JSONL_ROOT_DIR = os.path.join(OUTPUT_DIR, "jsonl")
EXCEL_ROOT_DIR = os.path.join(OUTPUT_DIR, "excel")

CHECKPOINT_FILE = os.path.join(META_DIR, "processed_tables.txt")
RUN_SUMMARY_JSON = os.path.join(META_DIR, "run_summary.json")
EXPORT_SUMMARY_JSON = os.path.join(META_DIR, "export_summary.json")
CONFIG_SNAPSHOT_JSON = os.path.join(META_DIR, "config_snapshot.json")

TABLE_JSONL_DIR = os.path.join(JSONL_ROOT_DIR, "table_inventory")
COLUMN_JSONL_DIR = os.path.join(JSONL_ROOT_DIR, "column_inventory")
ERROR_JSONL_DIR = os.path.join(JSONL_ROOT_DIR, "error_inventory")
SKIP_JSONL_DIR = os.path.join(JSONL_ROOT_DIR, "skip_inventory")
CLASS_MISSING_JSONL_DIR = os.path.join(JSONL_ROOT_DIR, "class_not_found_inventory")

TABLE_EXCEL_DIR = os.path.join(EXCEL_ROOT_DIR, "table_inventory")
COLUMN_EXCEL_DIR = os.path.join(EXCEL_ROOT_DIR, "column_inventory")
ERROR_EXCEL_DIR = os.path.join(EXCEL_ROOT_DIR, "error_inventory")
SKIP_EXCEL_DIR = os.path.join(EXCEL_ROOT_DIR, "skip_inventory")
CLASS_MISSING_EXCEL_DIR = os.path.join(EXCEL_ROOT_DIR, "class_not_found_inventory")

# =========================================================
# 列定义
# =========================================================

TABLE_COLUMNS = [
    "scan_ts",
    "run_user",
    "spark_user",
    "db_name",
    "table_name",
    "full_table_name",
    "table_type",
    "is_temporary",
    "status",
    "source_method",
    "column_count",
    "table_comment",
    "owner",
    "current_user_is_owner",
    "create_time_raw",
    "create_time",
    "last_access_time_raw",
    "last_access_time",
    "last_update_time_raw",
    "last_update_time",
    "last_update_time_source",
    "location",
    "provider",
    "storage_handler",
    "serde_library",
    "input_format",
    "output_format",
    "partition_column_count",
    "partition_columns",
    "bucket_column_count",
    "bucket_columns",
    "current_user_can_select_limit0",
    "select_check_status",
    "select_check_error_type",
    "select_check_error_message",
    "table_parameters_json",
    "storage_desc_params_json",
    "serde_params_json",
    "error_type",
    "error_message",
]

COLUMN_COLUMNS = [
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
]

ERROR_COLUMNS = [
    "scan_ts",
    "level",
    "db_name",
    "table_name",
    "error_type",
    "error_message",
    "traceback",
]

SKIP_COLUMNS = [
    "scan_ts",
    "level",
    "db_name",
    "table_name",
    "reason",
    "matched_pattern",
]

CLASS_MISSING_COLUMNS = [
    "scan_ts",
    "level",
    "db_name",
    "table_name",
    "missing_class_name",
    "error_type",
    "error_message",
]

ILLEGAL_EXCEL_CHAR_RE = re.compile(u"[\x00-\x08\x0B-\x0C\x0E-\x1F]")

CLASS_NOT_FOUND_RE_LIST = [
    re.compile(r"ClassNotFoundException[: ]+Class\s+([A-Za-z0-9_.$]+)\s+not found"),
    re.compile(r"ClassNotFoundException[: ]+([A-Za-z0-9_.$]+)"),
    re.compile(r"Cannot find class '([^']+)'"),
    re.compile(r"Class ([A-Za-z0-9_.$]+) not found"),
]

PERMISSION_DENIED_PATTERNS = [
    re.compile(r"permission denied", re.I),
    re.compile(r"access denied", re.I),
    re.compile(r"not authorized", re.I),
    re.compile(r"authorization", re.I),
    re.compile(r"insufficient privileges", re.I),
    re.compile(r"does not have privileges", re.I),
    re.compile(r"no privilege", re.I),
]

# =========================================================
# 通用函数
# =========================================================

def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def ensure_dir(path):
    if not os.path.exists(path):
        os.makedirs(path)


def truncate_text(text, max_len):
    if text is None:
        return ""
    text = str(text).replace("\r", " ").replace("\n", " ")
    if len(text) <= max_len:
        return text
    return text[:max_len] + " ...[truncated]"


def flush_fp(fp):
    fp.flush()
    if ENABLE_FSYNC:
        os.fsync(fp.fileno())


def quote_ident(name):
    return "`{}`".format(str(name).replace("`", "``"))


def safe_str(v):
    if v is None:
        return ""
    return str(v).strip()


def matches_any_pattern(name, patterns):
    if not patterns:
        return False, ""
    for pattern in patterns:
        if fnmatch.fnmatchcase(name, pattern):
            return True, pattern
    return False, ""


def sanitize_excel_sheet_name(name):
    name = re.sub(r'[\\/*?:\[\]]', "_", str(name))
    name = name.strip()
    if not name:
        name = "sheet"
    return name[:31]


def make_chunked_sheet_name(base_name, idx):
    base_name = sanitize_excel_sheet_name(base_name)
    suffix = "_{:03d}".format(idx)
    max_base_len = 31 - len(suffix)
    return base_name[:max_base_len] + suffix


def clean_excel_illegal_chars(value):
    if value is None:
        return ""
    value = str(value)
    value = ILLEGAL_EXCEL_CHAR_RE.sub("", value)
    return value


def to_excel_cell_value(v):
    if v is None:
        value = ""
    elif isinstance(v, (dict, list, tuple)):
        value = json.dumps(v, ensure_ascii=False)
    else:
        value = str(v)

    value = clean_excel_illegal_chars(value)

    if len(value) > EXCEL_MAX_CELL_LEN:
        value = value[:EXCEL_MAX_CELL_LEN - 14] + "...[truncated]"
    return value


def write_json_file(path, obj):
    with io.open(path, "w", encoding="utf-8") as fp:
        fp.write(json.dumps(obj, ensure_ascii=False, indent=2))


def list_part_files(dir_path):
    if not os.path.exists(dir_path):
        return []
    files = []
    for name in os.listdir(dir_path):
        if name.startswith("part_") and name.endswith(".jsonl"):
            files.append(os.path.join(dir_path, name))
    files.sort()
    return files


def load_processed_keys(path):
    processed = set()
    if not os.path.exists(path):
        return processed
    with io.open(path, "r", encoding="utf-8") as fp:
        for line in fp:
            key = line.strip()
            if key:
                processed.add(key)
    return processed


def append_processed_key(fp, key):
    fp.write(key + "\n")
    flush_fp(fp)


def normalize_meta_key(key):
    key = safe_str(key).rstrip(":")
    key = key.lower()
    key = re.sub(r"[ /.-]+", "_", key)
    key = re.sub(r"[^a-z0-9_]+", "", key)
    return key


def normalize_time_value(raw_value):
    raw = safe_str(raw_value)
    if not raw:
        return "", ""

    # Hive 常见 unknown / 0
    if raw.lower() in ("unknown", "null", "none", "n/a"):
        return raw, ""

    if raw.isdigit():
        try:
            iv = int(raw)
            if iv <= 0:
                return raw, ""
            # 13 位按毫秒
            if len(raw) >= 13:
                iv = int(raw[:10])
            dt = datetime.fromtimestamp(iv)
            return raw, dt.strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            return raw, raw

    return raw, raw


def first_non_empty(values):
    for v in values:
        if safe_str(v):
            return safe_str(v)
    return ""


def json_dumps_compact(obj):
    try:
        return json.dumps(obj, ensure_ascii=False, sort_keys=True)
    except Exception:
        return "{}"


def get_run_user():
    try:
        return getpass.getuser()
    except Exception:
        return safe_str(os.environ.get("USER", ""))


def get_spark_user(spark):
    try:
        return safe_str(spark.sparkContext.sparkUser())
    except Exception:
        return ""


def extract_class_not_found_names(text):
    if text is None:
        return []
    text = str(text)
    names = []
    for pattern in CLASS_NOT_FOUND_RE_LIST:
        for match in pattern.findall(text):
            if match and match not in names:
                names.append(match)
    return names


def record_missing_classes(writer, scan_ts, level, db_name, table_name, error_type, error_message, tb_text):
    if writer is None:
        return

    names = []
    names.extend(extract_class_not_found_names(error_message))
    names.extend(extract_class_not_found_names(tb_text))

    uniq = []
    for name in names:
        if name not in uniq:
            uniq.append(name)

    for name in uniq:
        writer.write({
            "scan_ts": scan_ts,
            "level": level,
            "db_name": db_name,
            "table_name": table_name,
            "missing_class_name": name,
            "error_type": error_type,
            "error_message": truncate_text(error_message, MAX_ERROR_MSG_LEN),
        })


def classify_select_permission_result(error_message):
    text = safe_str(error_message)
    if not text:
        return "UNKNOWN"
    for pattern in PERMISSION_DENIED_PATTERNS:
        if pattern.search(text):
            return "N"
    return "UNKNOWN"

# =========================================================
# JSONL 分片写入器
# =========================================================

class JsonlPartWriter(object):
    def __init__(self, dir_path, max_records_per_file):
        self.dir_path = dir_path
        self.max_records_per_file = max_records_per_file

        ensure_dir(self.dir_path)

        self.fp = None
        self.current_part_idx = self._detect_next_part_idx()
        self.current_part_record_count = 0
        self.total_record_count = 0
        self.part_count = 0

    def _detect_next_part_idx(self):
        max_idx = 0
        for name in os.listdir(self.dir_path):
            if not name.startswith("part_") or not name.endswith(".jsonl"):
                continue
            core = name[len("part_"):-len(".jsonl")]
            try:
                idx = int(core)
                if idx > max_idx:
                    max_idx = idx
            except Exception:
                pass
        return max_idx + 1

    def _open_new_part(self):
        if self.fp is not None:
            self.fp.close()

        file_name = "part_{:06d}.jsonl".format(self.current_part_idx)
        file_path = os.path.join(self.dir_path, file_name)
        self.fp = io.open(file_path, "a", encoding="utf-8")
        self.current_part_record_count = 0
        self.part_count += 1
        self.current_part_idx += 1

    def write(self, record):
        if self.fp is None or self.current_part_record_count >= self.max_records_per_file:
            self._open_new_part()

        self.fp.write(json.dumps(record, ensure_ascii=False) + "\n")
        flush_fp(self.fp)

        self.current_part_record_count += 1
        self.total_record_count += 1

    def close(self):
        if self.fp is not None:
            self.fp.close()
            self.fp = None


# =========================================================
# 过滤逻辑
# =========================================================

def should_skip_database(db_name):
    if INCLUDE_DATABASE_PATTERNS:
        matched, pattern = matches_any_pattern(db_name, INCLUDE_DATABASE_PATTERNS)
        if not matched:
            return True, "db_not_in_include_patterns", ""

    matched, pattern = matches_any_pattern(db_name, SKIP_DATABASE_PATTERNS)
    if matched:
        return True, "db_matched_skip_patterns", pattern

    return False, "", ""


def should_skip_table(db_name, table_name):
    full_name = "{}.{}".format(db_name, table_name)

    if INCLUDE_FULL_TABLE_PATTERNS:
        matched, pattern = matches_any_pattern(full_name, INCLUDE_FULL_TABLE_PATTERNS)
        if not matched:
            return True, "full_table_not_in_include_patterns", ""

    if INCLUDE_TABLE_PATTERNS:
        matched, pattern = matches_any_pattern(table_name, INCLUDE_TABLE_PATTERNS)
        if not matched:
            return True, "table_not_in_include_patterns", ""

    matched, pattern = matches_any_pattern(full_name, SKIP_FULL_TABLE_PATTERNS)
    if matched:
        return True, "full_table_matched_skip_patterns", pattern

    matched, pattern = matches_any_pattern(table_name, SKIP_TABLE_PATTERNS)
    if matched:
        return True, "table_matched_skip_patterns", pattern

    return False, "", ""


# =========================================================
# SHOW DATABASES / SHOW TABLES
# =========================================================

def get_database_names(spark):
    rows = spark.sql("SHOW DATABASES").collect()
    db_names = []
    for row in rows:
        if len(row) >= 1:
            db_names.append(row[0])
    return db_names


def get_tables_in_database(spark, db_name, include_temp_views):
    sql_text = "SHOW TABLES IN {}".format(quote_ident(db_name))
    rows = spark.sql(sql_text).collect()

    tables = []
    for row in rows:
        row_dict = row.asDict()
        table_name = row_dict.get("tableName", row[1] if len(row) > 1 else "")
        is_temporary = row_dict.get("isTemporary", row[2] if len(row) > 2 else False)

        if (not include_temp_views) and is_temporary:
            continue

        tables.append({
            "name": table_name,
            "tableType": "",
            "isTemporary": is_temporary,
        })
    return tables


# =========================================================
# DESCRIBE FORMATTED 解析
# =========================================================

def parse_describe_formatted_rows(rows):
    meta = {}
    table_params = {}
    storage_desc_params = {}
    serde_params = {}
    data_columns = []

    current_section = "base_columns"
    current_subsection = ""

    for row in rows:
        row_dict = row.asDict() if hasattr(row, "asDict") else {}
        c0 = safe_str(row_dict.get("col_name", row[0] if len(row) > 0 else ""))
        c1 = safe_str(row_dict.get("data_type", row[1] if len(row) > 1 else ""))
        c2 = safe_str(row_dict.get("comment", row[2] if len(row) > 2 else ""))

        if not c0 and not c1 and not c2:
            continue

        if c0.startswith("#"):
            marker = normalize_meta_key(c0.lstrip("#"))
            current_subsection = ""

            if "detailed_table_information" in marker:
                current_section = "detailed"
            elif "storage_information" in marker:
                current_section = "storage"
            elif "view_information" in marker:
                current_section = "view"
            elif "partition_information" in marker:
                current_section = "partition_information"
            elif "col_name" == marker:
                # 只是标题行
                pass
            else:
                current_section = marker
            continue

        # 普通字段区
        if current_section == "base_columns":
            # 避免把空字段 / 分隔行记进去
            if c0 and not c0.startswith("#"):
                data_columns.append({
                    "column_name": c0,
                    "data_type": c1,
                    "description": c2,
                })
            continue

        # 子节开头，例如 Table Parameters:
        if c0.endswith(":") and not c1 and not c2:
            current_subsection = normalize_meta_key(c0)
            continue

        # 子节内部 kv
        if current_subsection == "table_parameters":
            if c0:
                table_params[c0] = c1 if c1 else c2
            continue

        if current_subsection == "storage_desc_params":
            if c0:
                storage_desc_params[c0] = c1 if c1 else c2
            continue

        if current_subsection in ("serde_parameters", "ser_de_parameters"):
            if c0:
                serde_params[c0] = c1 if c1 else c2
            continue

        # 常规 metadata kv
        if c0.endswith(":"):
            meta[normalize_meta_key(c0)] = c1 if c1 else c2
            continue

        # 兜底：某些输出会没有冒号
        if c0:
            meta.setdefault(normalize_meta_key(c0), c1 if c1 else c2)

    return {
        "meta": meta,
        "table_params": table_params,
        "storage_desc_params": storage_desc_params,
        "serde_params": serde_params,
        "data_columns": data_columns,
    }


def get_describe_formatted_info(spark, db_name, table_name):
    sql_text = "DESCRIBE FORMATTED {}.{}".format(
        quote_ident(db_name),
        quote_ident(table_name),
    )
    rows = spark.sql(sql_text).collect()
    return parse_describe_formatted_rows(rows)


def normalize_catalog_column(col):
    return {
        "column_name": getattr(col, "name", ""),
        "data_type": getattr(col, "dataType", ""),
        "nullable": getattr(col, "nullable", ""),
        "is_partition": getattr(col, "isPartition", ""),
        "is_bucket": getattr(col, "isBucket", ""),
        "description": getattr(col, "description", ""),
    }


def normalize_schema_field(field):
    try:
        data_type = field.dataType.simpleString()
    except Exception:
        data_type = str(field.dataType)

    return {
        "column_name": getattr(field, "name", ""),
        "data_type": data_type,
        "nullable": getattr(field, "nullable", ""),
        "is_partition": "",
        "is_bucket": "",
        "description": "",
    }


def enrich_columns_with_catalog_flags(spark, db_name, table_name, columns):
    try:
        catalog_cols = spark.catalog.listColumns(table_name, db_name)
        catalog_map = {}
        for col in catalog_cols:
            item = normalize_catalog_column(col)
            catalog_map[item["column_name"]] = item

        for col in columns:
            col_name = safe_str(col.get("column_name", ""))
            if col_name in catalog_map:
                ref = catalog_map[col_name]
                if not safe_str(col.get("nullable", "")):
                    col["nullable"] = ref.get("nullable", "")
                if not safe_str(col.get("is_partition", "")):
                    col["is_partition"] = ref.get("is_partition", "")
                if not safe_str(col.get("is_bucket", "")):
                    col["is_bucket"] = ref.get("is_bucket", "")
                if not safe_str(col.get("description", "")):
                    col["description"] = ref.get("description", "")
    except Exception:
        pass

    return columns


def get_table_columns_with_fallback(spark, db_name, table_name):
    # 1. DESCRIBE FORMATTED
    try:
        desc_info = get_describe_formatted_info(spark, db_name, table_name)
        columns = []
        for item in desc_info["data_columns"]:
            col_name = safe_str(item.get("column_name", ""))
            if not col_name:
                continue
            columns.append({
                "column_name": col_name,
                "data_type": safe_str(item.get("data_type", "")),
                "nullable": "",
                "is_partition": "",
                "is_bucket": "",
                "description": safe_str(item.get("description", "")),
            })

        if columns:
            columns = enrich_columns_with_catalog_flags(spark, db_name, table_name, columns)
            return columns, "describe_formatted", desc_info
    except Exception:
        pass

    # 2. catalog.listColumns
    try:
        cols = spark.catalog.listColumns(table_name, db_name)
        columns = [normalize_catalog_column(col) for col in cols]
        return columns, "catalog.listColumns", {}
    except Exception:
        pass

    # 3. spark.table(...).schema
    full_name = "{}.{}".format(quote_ident(db_name), quote_ident(table_name))
    schema = spark.table(full_name).schema
    columns = [normalize_schema_field(field) for field in schema.fields]
    return columns, "spark.table.schema", {}


def derive_table_meta_from_desc(desc_info):
    meta = desc_info.get("meta", {}) if desc_info else {}
    table_params = desc_info.get("table_params", {}) if desc_info else {}
    storage_desc_params = desc_info.get("storage_desc_params", {}) if desc_info else {}
    serde_params = desc_info.get("serde_params", {}) if desc_info else {}

    table_comment = first_non_empty([
        meta.get("comment"),
        table_params.get("comment"),
        storage_desc_params.get("comment"),
    ])

    owner = first_non_empty([
        meta.get("owner"),
        table_params.get("owner"),
    ])

    create_time_raw, create_time = normalize_time_value(
        first_non_empty([
            meta.get("createtime"),
            table_params.get("create_time"),
            table_params.get("created_time"),
        ])
    )

    last_access_time_raw, last_access_time = normalize_time_value(
        first_non_empty([
            meta.get("lastaccesstime"),
            table_params.get("last_access_time"),
        ])
    )

    last_update_time_source = ""
    last_update_time_raw_candidate = ""

    for source_name, value in [
        ("last_modified_time", table_params.get("last_modified_time")),
        ("transient_lastDdlTime", table_params.get("transient_lastDdlTime")),
        ("transient_lastddltime", table_params.get("transient_lastddltime")),
        ("meta_last_modified_time", meta.get("last_modified_time")),
    ]:
        if safe_str(value):
            last_update_time_source = source_name
            last_update_time_raw_candidate = value
            break

    last_update_time_raw, last_update_time = normalize_time_value(last_update_time_raw_candidate)

    location = first_non_empty([
        meta.get("location"),
        table_params.get("location"),
    ])

    provider = first_non_empty([
        meta.get("provider"),
        table_params.get("spark.sql.sources.provider"),
        table_params.get("provider"),
    ])

    storage_handler = first_non_empty([
        meta.get("storage_handler"),
        table_params.get("storage_handler"),
    ])

    serde_library = first_non_empty([
        meta.get("serde_library"),
        meta.get("serdelibrary"),
        table_params.get("serde_library"),
    ])

    input_format = first_non_empty([
        meta.get("inputformat"),
        table_params.get("input_format"),
    ])

    output_format = first_non_empty([
        meta.get("outputformat"),
        table_params.get("output_format"),
    ])

    return {
        "table_comment": table_comment,
        "owner": owner,
        "create_time_raw": create_time_raw,
        "create_time": create_time,
        "last_access_time_raw": last_access_time_raw,
        "last_access_time": last_access_time,
        "last_update_time_raw": last_update_time_raw,
        "last_update_time": last_update_time,
        "last_update_time_source": last_update_time_source,
        "location": location,
        "provider": provider,
        "storage_handler": storage_handler,
        "serde_library": serde_library,
        "input_format": input_format,
        "output_format": output_format,
        "table_parameters_json": json_dumps_compact(table_params),
        "storage_desc_params_json": json_dumps_compact(storage_desc_params),
        "serde_params_json": json_dumps_compact(serde_params),
    }


def get_table_meta_best_effort(spark, db_name, table_name):
    try:
        desc_info = get_describe_formatted_info(spark, db_name, table_name)
        meta_row = derive_table_meta_from_desc(desc_info)
        meta_row["_desc_info"] = desc_info
        return meta_row, "describe_formatted"
    except Exception:
        return {
            "table_comment": "",
            "owner": "",
            "create_time_raw": "",
            "create_time": "",
            "last_access_time_raw": "",
            "last_access_time": "",
            "last_update_time_raw": "",
            "last_update_time": "",
            "last_update_time_source": "",
            "location": "",
            "provider": "",
            "storage_handler": "",
            "serde_library": "",
            "input_format": "",
            "output_format": "",
            "table_parameters_json": "{}",
            "storage_desc_params_json": "{}",
            "serde_params_json": "{}",
            "_desc_info": {},
        }, ""

# =========================================================
# 权限探测
# =========================================================

def check_select_permission(spark, db_name, table_name):
    if not ENABLE_SELECT_PERMISSION_CHECK:
        return {
            "current_user_can_select_limit0": "SKIPPED",
            "select_check_status": "SKIPPED",
            "select_check_error_type": "",
            "select_check_error_message": "",
        }

    sql_text = "SELECT * FROM {}.{} LIMIT 0".format(
        quote_ident(db_name),
        quote_ident(table_name),
    )

    try:
        spark.sql(sql_text).collect()
        return {
            "current_user_can_select_limit0": "Y",
            "select_check_status": "PASS",
            "select_check_error_type": "",
            "select_check_error_message": "",
        }
    except Exception as e:
        err_msg = truncate_text(e, MAX_ERROR_MSG_LEN)
        return {
            "current_user_can_select_limit0": classify_select_permission_result(err_msg),
            "select_check_status": "FAIL",
            "select_check_error_type": e.__class__.__name__,
            "select_check_error_message": err_msg,
        }


def calc_current_user_is_owner(run_user, spark_user, owner):
    owner = safe_str(owner)
    if not owner:
        return "UNKNOWN"

    candidates = [safe_str(run_user), safe_str(spark_user)]
    for c in candidates:
        if c and owner.lower() == c.lower():
            return "Y"
    return "N"

# =========================================================
# JSONL -> Excel
# =========================================================

def iter_jsonl_records(jsonl_path):
    with io.open(jsonl_path, "r", encoding="utf-8") as fp:
        for line_no, line in enumerate(fp, 1):
            line = line.strip()
            if not line:
                continue
            try:
                yield line_no, json.loads(line), None
            except Exception as e:
                yield line_no, None, "{}: {}".format(
                    e.__class__.__name__,
                    truncate_text(e, MAX_ERROR_MSG_LEN)
                )


def export_one_jsonl_to_excel(jsonl_path, excel_dir, base_sheet_name, columns):
    ensure_dir(excel_dir)

    file_name = os.path.basename(jsonl_path)
    excel_name = file_name[:-6] + ".xlsx"
    excel_path = os.path.join(excel_dir, excel_name)

    wb = Workbook(write_only=True)

    ws = None
    sheet_idx = 0
    current_rows = 0
    total_rows = 0
    parse_error_rows = 0

    def create_new_sheet():
        nonlocal ws, sheet_idx, current_rows
        sheet_idx += 1
        sheet_name = make_chunked_sheet_name(base_sheet_name, sheet_idx)
        ws = wb.create_sheet(title=sheet_name)
        ws.append([to_excel_cell_value(col) for col in columns])
        current_rows = 0

    create_new_sheet()

    for line_no, record, err in iter_jsonl_records(jsonl_path):
        if current_rows >= EXCEL_DATA_ROWS_PER_SHEET:
            create_new_sheet()

        if err is not None:
            parse_error_rows += 1
            row = []
            for col in columns:
                if col == "error_message":
                    row.append(to_excel_cell_value(err))
                else:
                    row.append("")
            ws.append(row)
            current_rows += 1
            total_rows += 1
            continue

        row = [to_excel_cell_value(record.get(col, "")) for col in columns]
        ws.append(row)
        current_rows += 1
        total_rows += 1

    wb.save(excel_path)

    return {
        "jsonl_path": jsonl_path,
        "excel_path": excel_path,
        "sheet_count": sheet_idx,
        "row_count": total_rows,
        "parse_error_rows": parse_error_rows,
    }


def export_all_jsonl_to_excel():
    export_results = []

    export_jobs = [
        ("table_inventory", TABLE_JSONL_DIR, TABLE_EXCEL_DIR, TABLE_COLUMNS),
        ("column_inventory", COLUMN_JSONL_DIR, COLUMN_EXCEL_DIR, COLUMN_COLUMNS),
        ("error_inventory", ERROR_JSONL_DIR, ERROR_EXCEL_DIR, ERROR_COLUMNS),
    ]

    if WRITE_SKIP_INVENTORY:
        export_jobs.append(
            ("skip_inventory", SKIP_JSONL_DIR, SKIP_EXCEL_DIR, SKIP_COLUMNS)
        )

    if WRITE_CLASS_NOT_FOUND_INVENTORY:
        export_jobs.append(
            ("class_not_found_inventory", CLASS_MISSING_JSONL_DIR, CLASS_MISSING_EXCEL_DIR, CLASS_MISSING_COLUMNS)
        )

    for base_name, jsonl_dir, excel_dir, columns in export_jobs:
        part_files = list_part_files(jsonl_dir)
        print("[{}] start excel export | {} | part_files={}".format(
            now_str(), base_name, len(part_files)
        ))

        for idx, jsonl_path in enumerate(part_files, 1):
            print("[{}] exporting {}/{} | {}".format(
                now_str(), idx, len(part_files), jsonl_path
            ))
            result = export_one_jsonl_to_excel(
                jsonl_path=jsonl_path,
                excel_dir=excel_dir,
                base_sheet_name=base_name,
                columns=columns,
            )
            export_results.append(result)

    write_json_file(EXPORT_SUMMARY_JSON, {
        "export_ts": now_str(),
        "results": export_results,
    })

    print("[{}] excel export finished | summary={}".format(
        now_str(), EXPORT_SUMMARY_JSON
    ))


# =========================================================
# 主扫描逻辑
# =========================================================

def scan_all_tables(spark):
    ensure_dir(OUTPUT_DIR)
    ensure_dir(META_DIR)
    ensure_dir(JSONL_ROOT_DIR)
    ensure_dir(EXCEL_ROOT_DIR)
    ensure_dir(TABLE_JSONL_DIR)
    ensure_dir(COLUMN_JSONL_DIR)
    ensure_dir(ERROR_JSONL_DIR)

    if WRITE_SKIP_INVENTORY:
        ensure_dir(SKIP_JSONL_DIR)
    if WRITE_CLASS_NOT_FOUND_INVENTORY:
        ensure_dir(CLASS_MISSING_JSONL_DIR)

    run_user = get_run_user()
    spark_user = get_spark_user(spark)

    table_writer = JsonlPartWriter(TABLE_JSONL_DIR, JSONL_MAX_RECORDS_TABLE)
    column_writer = JsonlPartWriter(COLUMN_JSONL_DIR, JSONL_MAX_RECORDS_COLUMN)
    error_writer = JsonlPartWriter(ERROR_JSONL_DIR, JSONL_MAX_RECORDS_ERROR)
    skip_writer = JsonlPartWriter(SKIP_JSONL_DIR, JSONL_MAX_RECORDS_SKIP) if WRITE_SKIP_INVENTORY else None
    class_missing_writer = JsonlPartWriter(CLASS_MISSING_JSONL_DIR, JSONL_MAX_RECORDS_CLASS_MISSING) if WRITE_CLASS_NOT_FOUND_INVENTORY else None

    checkpoint_fp = io.open(CHECKPOINT_FILE, "a", encoding="utf-8")
    processed_keys = load_processed_keys(CHECKPOINT_FILE) if SKIP_PROCESSED else set()

    total_db = 0
    scanned_db = 0
    skipped_db = 0

    total_table_seen = 0
    scanned_table = 0
    success_table = 0
    failed_table = 0
    skipped_table = 0
    total_column = 0

    try:
        db_names = get_database_names(spark)
        total_db = len(db_names)
        print("[{}] database count = {}".format(now_str(), total_db))

        for db_idx, db_name in enumerate(db_names, 1):
            db_skip, db_reason, db_pattern = should_skip_database(db_name)
            if db_skip:
                skipped_db += 1
                if skip_writer is not None:
                    skip_writer.write({
                        "scan_ts": now_str(),
                        "level": "DATABASE",
                        "db_name": db_name,
                        "table_name": "",
                        "reason": db_reason,
                        "matched_pattern": db_pattern,
                    })
                continue

            scanned_db += 1

            try:
                tables = get_tables_in_database(spark, db_name, INCLUDE_TEMP_VIEWS)
            except Exception as e:
                scan_ts = now_str()
                err_msg = truncate_text(e, MAX_ERROR_MSG_LEN)
                tb_text = truncate_text(traceback.format_exc(), MAX_TRACEBACK_LEN)

                error_writer.write({
                    "scan_ts": scan_ts,
                    "level": "DATABASE",
                    "db_name": db_name,
                    "table_name": "",
                    "error_type": e.__class__.__name__,
                    "error_message": err_msg,
                    "traceback": tb_text,
                })
                record_missing_classes(
                    class_missing_writer,
                    scan_ts,
                    "DATABASE",
                    db_name,
                    "",
                    e.__class__.__name__,
                    err_msg,
                    tb_text
                )

                print("[{}] failed to list tables in database: {} | {}".format(
                    now_str(), db_name, err_msg
                ))
                continue

            print("[{}] scanning database {}/{}: {} | table count = {}".format(
                now_str(), db_idx, total_db, db_name, len(tables)
            ))

            for tb in tables:
                total_table_seen += 1

                table_name = tb["name"]
                table_type = tb.get("tableType", "")
                is_temporary = tb.get("isTemporary", False)
                full_table_name = "{}.{}".format(db_name, table_name)
                table_key = full_table_name

                table_skip, table_reason, table_pattern = should_skip_table(db_name, table_name)
                if table_skip:
                    skipped_table += 1
                    if skip_writer is not None:
                        skip_writer.write({
                            "scan_ts": now_str(),
                            "level": "TABLE",
                            "db_name": db_name,
                            "table_name": table_name,
                            "reason": table_reason,
                            "matched_pattern": table_pattern,
                        })
                    if skipped_table % PRINT_EVERY_SKIPPED == 0:
                        print("[{}] skipped tables = {}".format(now_str(), skipped_table))
                    continue

                if SKIP_PROCESSED and table_key in processed_keys:
                    skipped_table += 1
                    if skip_writer is not None:
                        skip_writer.write({
                            "scan_ts": now_str(),
                            "level": "TABLE",
                            "db_name": db_name,
                            "table_name": table_name,
                            "reason": "already_processed",
                            "matched_pattern": "",
                        })
                    if skipped_table % PRINT_EVERY_SKIPPED == 0:
                        print("[{}] skipped tables = {}".format(now_str(), skipped_table))
                    continue

                scanned_table += 1
                scan_ts = now_str()

                try:
                    table_meta_row, meta_source_method = get_table_meta_best_effort(spark, db_name, table_name)
                    normalized_cols, column_source_method, desc_info_from_column = get_table_columns_with_fallback(spark, db_name, table_name)

                    if not meta_source_method and desc_info_from_column:
                        # 如果前面单独抓表级信息失败，但列扫描拿到了 describe_formatted 结果，就复用
                        table_meta_row = derive_table_meta_from_desc(desc_info_from_column)
                        table_meta_row["_desc_info"] = desc_info_from_column
                        meta_source_method = "describe_formatted"

                    partition_cols = []
                    bucket_cols = []

                    for idx, col in enumerate(normalized_cols, 1):
                        is_partition = safe_str(col.get("is_partition", ""))
                        is_bucket = safe_str(col.get("is_bucket", ""))

                        if str(is_partition).lower() == "true":
                            partition_cols.append(safe_str(col.get("column_name", "")))
                        if str(is_bucket).lower() == "true":
                            bucket_cols.append(safe_str(col.get("column_name", "")))

                        column_writer.write({
                            "scan_ts": scan_ts,
                            "db_name": db_name,
                            "table_name": table_name,
                            "table_type": table_type,
                            "is_temporary": is_temporary,
                            "column_index": idx,
                            "column_name": safe_str(col.get("column_name", "")),
                            "data_type": safe_str(col.get("data_type", "")),
                            "nullable": safe_str(col.get("nullable", "")),
                            "is_partition": safe_str(col.get("is_partition", "")),
                            "is_bucket": safe_str(col.get("is_bucket", "")),
                            "description": safe_str(col.get("description", "")),
                        })

                    permission_result = check_select_permission(spark, db_name, table_name)

                    owner = table_meta_row.get("owner", "")
                    current_user_is_owner = calc_current_user_is_owner(run_user, spark_user, owner)

                    source_method = meta_source_method
                    if source_method and column_source_method and source_method != column_source_method:
                        source_method = source_method + "|" + column_source_method
                    elif not source_method:
                        source_method = column_source_method

                    table_writer.write({
                        "scan_ts": scan_ts,
                        "run_user": run_user,
                        "spark_user": spark_user,
                        "db_name": db_name,
                        "table_name": table_name,
                        "full_table_name": full_table_name,
                        "table_type": table_type,
                        "is_temporary": is_temporary,
                        "status": "SUCCESS",
                        "source_method": source_method,
                        "column_count": len(normalized_cols),
                        "table_comment": table_meta_row.get("table_comment", ""),
                        "owner": owner,
                        "current_user_is_owner": current_user_is_owner,
                        "create_time_raw": table_meta_row.get("create_time_raw", ""),
                        "create_time": table_meta_row.get("create_time", ""),
                        "last_access_time_raw": table_meta_row.get("last_access_time_raw", ""),
                        "last_access_time": table_meta_row.get("last_access_time", ""),
                        "last_update_time_raw": table_meta_row.get("last_update_time_raw", ""),
                        "last_update_time": table_meta_row.get("last_update_time", ""),
                        "last_update_time_source": table_meta_row.get("last_update_time_source", ""),
                        "location": table_meta_row.get("location", ""),
                        "provider": table_meta_row.get("provider", ""),
                        "storage_handler": table_meta_row.get("storage_handler", ""),
                        "serde_library": table_meta_row.get("serde_library", ""),
                        "input_format": table_meta_row.get("input_format", ""),
                        "output_format": table_meta_row.get("output_format", ""),
                        "partition_column_count": len(partition_cols),
                        "partition_columns": ",".join(partition_cols),
                        "bucket_column_count": len(bucket_cols),
                        "bucket_columns": ",".join(bucket_cols),
                        "current_user_can_select_limit0": permission_result["current_user_can_select_limit0"],
                        "select_check_status": permission_result["select_check_status"],
                        "select_check_error_type": permission_result["select_check_error_type"],
                        "select_check_error_message": permission_result["select_check_error_message"],
                        "table_parameters_json": table_meta_row.get("table_parameters_json", "{}"),
                        "storage_desc_params_json": table_meta_row.get("storage_desc_params_json", "{}"),
                        "serde_params_json": table_meta_row.get("serde_params_json", "{}"),
                        "error_type": "",
                        "error_message": "",
                    })

                    append_processed_key(checkpoint_fp, table_key)
                    processed_keys.add(table_key)

                    success_table += 1
                    total_column += len(normalized_cols)

                    if success_table % PRINT_EVERY_SUCCESS == 0:
                        print("[{}] success tables = {}, total columns = {}".format(
                            now_str(), success_table, total_column
                        ))

                except Exception as e:
                    err_msg = truncate_text(e, MAX_ERROR_MSG_LEN)
                    tb_text = truncate_text(traceback.format_exc(), MAX_TRACEBACK_LEN)

                    table_writer.write({
                        "scan_ts": scan_ts,
                        "run_user": run_user,
                        "spark_user": spark_user,
                        "db_name": db_name,
                        "table_name": table_name,
                        "full_table_name": full_table_name,
                        "table_type": table_type,
                        "is_temporary": is_temporary,
                        "status": "FAILED",
                        "source_method": "",
                        "column_count": 0,
                        "table_comment": "",
                        "owner": "",
                        "current_user_is_owner": "",
                        "create_time_raw": "",
                        "create_time": "",
                        "last_access_time_raw": "",
                        "last_access_time": "",
                        "last_update_time_raw": "",
                        "last_update_time": "",
                        "last_update_time_source": "",
                        "location": "",
                        "provider": "",
                        "storage_handler": "",
                        "serde_library": "",
                        "input_format": "",
                        "output_format": "",
                        "partition_column_count": 0,
                        "partition_columns": "",
                        "bucket_column_count": 0,
                        "bucket_columns": "",
                        "current_user_can_select_limit0": "",
                        "select_check_status": "",
                        "select_check_error_type": "",
                        "select_check_error_message": "",
                        "table_parameters_json": "{}",
                        "storage_desc_params_json": "{}",
                        "serde_params_json": "{}",
                        "error_type": e.__class__.__name__,
                        "error_message": err_msg,
                    })

                    error_writer.write({
                        "scan_ts": scan_ts,
                        "level": "TABLE",
                        "db_name": db_name,
                        "table_name": table_name,
                        "error_type": e.__class__.__name__,
                        "error_message": err_msg,
                        "traceback": tb_text,
                    })

                    record_missing_classes(
                        class_missing_writer,
                        scan_ts,
                        "TABLE",
                        db_name,
                        table_name,
                        e.__class__.__name__,
                        err_msg,
                        tb_text
                    )

                    append_processed_key(checkpoint_fp, table_key)
                    processed_keys.add(table_key)

                    failed_table += 1
                    print("[{}] failed table: {}.{} | {}".format(
                        now_str(), db_name, table_name, err_msg
                    ))

    finally:
        checkpoint_fp.close()
        table_writer.close()
        column_writer.close()
        error_writer.close()

        if skip_writer is not None:
            skip_writer.close()
        if class_missing_writer is not None:
            class_missing_writer.close()

    summary = {
        "finish_ts": now_str(),
        "output_dir": OUTPUT_DIR,
        "run_user": run_user,
        "spark_user": spark_user,
        "checkpoint_file": CHECKPOINT_FILE,
        "jsonl_dirs": {
            "table_inventory": TABLE_JSONL_DIR,
            "column_inventory": COLUMN_JSONL_DIR,
            "error_inventory": ERROR_JSONL_DIR,
            "skip_inventory": SKIP_JSONL_DIR if WRITE_SKIP_INVENTORY else "",
            "class_not_found_inventory": CLASS_MISSING_JSONL_DIR if WRITE_CLASS_NOT_FOUND_INVENTORY else "",
        },
        "counts": {
            "total_db": total_db,
            "scanned_db": scanned_db,
            "skipped_db": skipped_db,
            "total_table_seen": total_table_seen,
            "scanned_table": scanned_table,
            "success_table": success_table,
            "failed_table": failed_table,
            "skipped_table": skipped_table,
            "total_column": total_column,
        },
        "jsonl_part_counts": {
            "table_inventory": len(list_part_files(TABLE_JSONL_DIR)),
            "column_inventory": len(list_part_files(COLUMN_JSONL_DIR)),
            "error_inventory": len(list_part_files(ERROR_JSONL_DIR)),
            "skip_inventory": len(list_part_files(SKIP_JSONL_DIR)) if WRITE_SKIP_INVENTORY else 0,
            "class_not_found_inventory": len(list_part_files(CLASS_MISSING_JSONL_DIR)) if WRITE_CLASS_NOT_FOUND_INVENTORY else 0,
        },
    }

    write_json_file(RUN_SUMMARY_JSON, summary)

    print("=" * 80)
    print("[{}] scan finished".format(now_str()))
    print("run_user                  = {}".format(run_user))
    print("spark_user                = {}".format(spark_user))
    print("total_db                  = {}".format(total_db))
    print("scanned_db                = {}".format(scanned_db))
    print("skipped_db                = {}".format(skipped_db))
    print("total_table_seen          = {}".format(total_table_seen))
    print("scanned_table             = {}".format(scanned_table))
    print("success_table             = {}".format(success_table))
    print("failed_table              = {}".format(failed_table))
    print("skipped_table             = {}".format(skipped_table))
    print("total_column              = {}".format(total_column))
    print("run_summary_json          = {}".format(RUN_SUMMARY_JSON))


# =========================================================
# 配置快照
# =========================================================

def dump_config_snapshot():
    config = {
        "OUTPUT_DIR": OUTPUT_DIR,
        "SKIP_PROCESSED": SKIP_PROCESSED,
        "INCLUDE_TEMP_VIEWS": INCLUDE_TEMP_VIEWS,
        "PRINT_EVERY_SUCCESS": PRINT_EVERY_SUCCESS,
        "PRINT_EVERY_SKIPPED": PRINT_EVERY_SKIPPED,
        "ENABLE_FSYNC": ENABLE_FSYNC,
        "MAX_ERROR_MSG_LEN": MAX_ERROR_MSG_LEN,
        "MAX_TRACEBACK_LEN": MAX_TRACEBACK_LEN,
        "EXCEL_MAX_CELL_LEN": EXCEL_MAX_CELL_LEN,
        "EXCEL_MAX_ROWS_PER_SHEET": EXCEL_MAX_ROWS_PER_SHEET,
        "JSONL_MAX_RECORDS_TABLE": JSONL_MAX_RECORDS_TABLE,
        "JSONL_MAX_RECORDS_COLUMN": JSONL_MAX_RECORDS_COLUMN,
        "JSONL_MAX_RECORDS_ERROR": JSONL_MAX_RECORDS_ERROR,
        "JSONL_MAX_RECORDS_SKIP": JSONL_MAX_RECORDS_SKIP,
        "JSONL_MAX_RECORDS_CLASS_MISSING": JSONL_MAX_RECORDS_CLASS_MISSING,
        "WRITE_SKIP_INVENTORY": WRITE_SKIP_INVENTORY,
        "WRITE_CLASS_NOT_FOUND_INVENTORY": WRITE_CLASS_NOT_FOUND_INVENTORY,
        "ENABLE_SELECT_PERMISSION_CHECK": ENABLE_SELECT_PERMISSION_CHECK,
        "INCLUDE_DATABASE_PATTERNS": INCLUDE_DATABASE_PATTERNS,
        "SKIP_DATABASE_PATTERNS": SKIP_DATABASE_PATTERNS,
        "INCLUDE_TABLE_PATTERNS": INCLUDE_TABLE_PATTERNS,
        "SKIP_TABLE_PATTERNS": SKIP_TABLE_PATTERNS,
        "INCLUDE_FULL_TABLE_PATTERNS": INCLUDE_FULL_TABLE_PATTERNS,
        "SKIP_FULL_TABLE_PATTERNS": SKIP_FULL_TABLE_PATTERNS,
    }
    ensure_dir(META_DIR)
    write_json_file(CONFIG_SNAPSHOT_JSON, config)


# =========================================================
# main
# =========================================================

def main():
    ensure_dir(OUTPUT_DIR)
    ensure_dir(META_DIR)
    dump_config_snapshot()

    spark = (
        SparkSession.builder
        .appName("meta_scan_jsonl_excel_enhanced")
        .enableHiveSupport()
        .getOrCreate()
    )

    try:
        scan_all_tables(spark)
    finally:
        spark.stop()

    export_all_jsonl_to_excel()


if __name__ == "__main__":
    main()