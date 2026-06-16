from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Iterable

import psycopg
from psycopg.rows import dict_row


logger = logging.getLogger(__name__)


def ingest_base_dir(
    base_dir: str | Path,
    db_dsn: str,
) -> None:
    """
    Parse metadata from a base directory and its relevant subdirectories/files,
    then upload parsed rows to PostgreSQL.

    On primary-key conflict:
    - existing rows are overwritten
    - changed columns are logged
    """

    base_dir = Path(base_dir).resolve()

    if not base_dir.exists() or not base_dir.is_dir():
        raise ValueError(f"Base directory does not exist or is not a directory: {base_dir}")

    with psycopg.connect(db_dsn, row_factory=dict_row) as conn:
        with conn.transaction():
            base_metadata = parse_base_dir_metadata(base_dir)

            upsert_row_with_change_log(
                conn=conn,
                table_name="base_dirs",
                pk_columns=["base_id"],
                row=base_metadata,
            )

            for sub_dir in iter_relevant_sub_dirs(base_dir):
                sub_dir_metadata = parse_sub_dir_metadata(sub_dir, base_metadata)

                upsert_row_with_change_log(
                    conn=conn,
                    table_name="sub_dirs",
                    pk_columns=["sub_dir_id"],
                    row=sub_dir_metadata,
                )

                for file_path in iter_relevant_files(sub_dir):
                    parsed_rows_by_table = parse_file(file_path, sub_dir_metadata)

                    for table_name, rows in parsed_rows_by_table.items():
                        for row in rows:
                            upsert_row_with_change_log(
                                conn=conn,
                                table_name=table_name,
                                pk_columns=get_pk_columns(table_name),
                                row=row,
                            )


def upsert_row_with_change_log(
    conn: psycopg.Connection,
    table_name: str,
    pk_columns: list[str],
    row: dict[str, Any],
) -> None:
    """
    Upsert one row into PostgreSQL.

    If row exists, compare old vs new values.
    If any non-PK values changed, log the changes and overwrite the row.
    """

    if not row:
        raise ValueError("Cannot upsert an empty row")

    columns = list(row.keys())
    non_pk_columns = [col for col in columns if col not in pk_columns]

    where_pk = " AND ".join([f"{col} = %({col})s" for col in pk_columns])

    existing = conn.execute(
        f"""
        SELECT {", ".join(columns)}
        FROM {table_name}
        WHERE {where_pk}
        """,
        row,
    ).fetchone()

    if existing:
        changes = diff_rows(existing, row, ignore_columns=pk_columns)

        if changes:
            logger.info(
                "Updating %s row pk=%s changes=%s",
                table_name,
                {pk: row[pk] for pk in pk_columns},
                json.dumps(changes, default=str),
            )

    update_assignments = ", ".join(
        [f"{col} = EXCLUDED.{col}" for col in non_pk_columns]
    )

    insert_cols = ", ".join(columns)
    insert_placeholders = ", ".join([f"%({col})s" for col in columns])
    conflict_cols = ", ".join(pk_columns)

    conn.execute(
        f"""
        INSERT INTO {table_name} ({insert_cols})
        VALUES ({insert_placeholders})
        ON CONFLICT ({conflict_cols})
        DO UPDATE SET {update_assignments}
        """,
        row,
    )


def diff_rows(
    old_row: dict[str, Any],
    new_row: dict[str, Any],
    ignore_columns: Iterable[str] = (),
) -> dict[str, dict[str, Any]]:
    ignored = set(ignore_columns)
    changes = {}

    for key, new_value in new_row.items():
        if key in ignored:
            continue

        old_value = old_row.get(key)

        if old_value != new_value:
            changes[key] = {
                "old": old_value,
                "new": new_value,
            }

    return changes


# ---------------------------------------------------------------------
# Project-specific parsing logic
# Replace these with your actual rules.
# ---------------------------------------------------------------------

def parse_base_dir_metadata(base_dir: Path) -> dict[str, Any]:
    """
    Example:
    /data/project_123/site_A/run_456
    """
    return {
        "base_id": base_dir.name,
        "base_path": str(base_dir),
    }


def iter_relevant_sub_dirs(base_dir: Path) -> Iterable[Path]:
    for path in base_dir.iterdir():
        if path.is_dir() and not path.name.startswith("."):
            yield path


def parse_sub_dir_metadata(
    sub_dir: Path,
    base_metadata: dict[str, Any],
) -> dict[str, Any]:
    return {
        "sub_dir_id": f"{base_metadata['base_id']}::{sub_dir.name}",
        "base_id": base_metadata["base_id"],
        "sub_dir_name": sub_dir.name,
        "sub_dir_path": str(sub_dir),
    }


def iter_relevant_files(sub_dir: Path) -> Iterable[Path]:
    allowed_suffixes = {".csv", ".json", ".txt"}

    for path in sub_dir.iterdir():
        if path.is_file() and path.suffix.lower() in allowed_suffixes:
            yield path


PARSERS_BY_PATTERN: list[tuple[str, Parser]] = [
    ("*_measurements.csv", parse_measurements_csv),
    ("*_samples.csv", parse_samples_csv),
    ("metadata.json", parse_metadata_json),
]


def parse_file(
    file_path: Path,
    sub_dir_metadata: dict[str, Any],
) -> dict[str, list[dict[str, Any]]]:
    for pattern, parser in PARSERS_BY_PATTERN:
        if file_path.match(pattern):
            return parser(file_path, sub_dir_metadata)

    logger.warning("No parser matched file: %s", file_path)
    return {}


def parse_fastqc_file(filehandle) -> dict:
    """
    Parse fastqc_data.txt content from a file-like object.
    Returns a structured dict of all modules.
    """
    data = {
        "fastqc_version": None,
        "basic_statistics": {},
        "module_statuses":  {},
        "per_base_quality": [],
        "per_tile_quality": [],
        "per_sequence_quality": [],
        "per_base_sequence_content": [],
        "per_sequence_gc_content": [],
        "per_base_n_content": [],
        "sequence_length_distribution": [],
        "sequence_duplication_levels": {
            "total_deduplicated_pct": None,
            "rows": []
        },
        "adapter_content": [],
        "overrepresented_sequences": [],
        "kmer_content": [],
                }

    current_module = None

    for raw_line in filehandle:
        line = raw_line.rstrip("\n")

        # Module start: >>Module Name\tstatus
        if line.startswith(">>") and not line.startswith(">>END_MODULE"):
            parts = line[2:].split("\t")
            module_name = parts[0].strip()
            status      = parts[1].strip() if len(parts) > 1 else None
            current_module = module_name
            if status:
                data["module_statuses"][module_name] = status
            else:
                log.warning("Module header line has no status field: %r", line)
            continue

        if line.startswith(">>END_MODULE"):
            if current_module is None:
                log.warning(">>END_MODULE encountered outside any module context")
            current_module = None
            continue

        # Handle comment/header lines
        if line.startswith("#"):
            # First line: ##FastQC\t{version}
            if line.startswith("##FastQC"):
                data["fastqc_version"] = line.split("\t")[1].strip()
            # Special case: Total Deduplicated Percentage sits on a #-prefixed line
            elif "Total Deduplicated Percentage" in line:
                val = line.split("\t")[1].strip()
                data["sequence_duplication_levels"]["total_deduplicated_pct"] = float(val)
            elif current_module is None:
                log.warning("Column header line encountered outside any module context: %r", line)
            # All other #-lines are column headers — skip them
            continue

        if not line.strip():
            continue
        if current_module is None:
            log.warning("Data line encountered outside any module context (no >>module header seen): %r", line)
            continue

        cols = line.split("\t")

        if current_module == "Basic Statistics":
            if len(cols) < 2:
                log.warning("Basic Statistics row has too few columns (%d < 2): %r", len(cols), line)
            else:
                data["basic_statistics"][cols[0].strip()] = cols[1].strip()

        elif current_module == "Per base sequence quality":
            if len(cols) < 7:
                log.warning("Per base sequence quality row has too few columns (%d < 7): %r", len(cols), line)
            else:
                data["per_base_quality"].append({
                    "base":            cols[0],
                    "mean":            float(cols[1]),
                    "median":          float(cols[2]),
                    "lower_quartile":  float(cols[3]),
                    "upper_quartile":  float(cols[4]),
                    "percentile_10":   float(cols[5]),
                    "percentile_90":   float(cols[6]),
                })

        elif current_module == "Per tile sequence quality":
            if len(cols) < 3:
                log.warning("Per tile sequence quality row has too few columns (%d < 3): %r", len(cols), line)
            else:
                data["per_tile_quality"].append({
                    "tile": int(cols[0]),
                    "base": cols[1],
                    "mean": float(cols[2]),
                })

        elif current_module == "Per sequence quality scores":
            if len(cols) < 2:
                log.warning("Per sequence quality scores row has too few columns (%d < 2): %r", len(cols), line)
            else:
                data["per_sequence_quality"].append({
                    "quality": int(cols[0]),
                    "count":   float(cols[1]),
                })

        elif current_module == "Per base sequence content":
            if len(cols) < 5:
                log.warning("Per base sequence content row has too few columns (%d < 5): %r", len(cols), line)
            else:
                data["per_base_sequence_content"].append({
                    "base": cols[0],
                    "g":    float(cols[1]),
                    "a":    float(cols[2]),
                    "t":    float(cols[3]),
                    "c":    float(cols[4]),
                })

        elif current_module == "Per sequence GC content":
            if len(cols) < 2:
                log.warning("Per sequence GC content row has too few columns (%d < 2): %r", len(cols), line)
            else:
                data["per_sequence_gc_content"].append({
                    "gc_content": int(cols[0]),
                    "count":      float(cols[1]),
                })

        elif current_module == "Per base N content":
            if len(cols) < 2:
                log.warning("Per base N content row has too few columns (%d < 2): %r", len(cols), line)
            else:
                data["per_base_n_content"].append({
                    "base":    cols[0],
                    "n_count": float(cols[1]),
                })

        elif current_module == "Sequence Length Distribution":
            if len(cols) < 2:
                log.warning("Sequence Length Distribution row has too few columns (%d < 2): %r", len(cols), line)
            else:
                data["sequence_length_distribution"].append({
                    "length": cols[0],
                    "count":  float(cols[1]),
                })

        elif current_module == "Sequence Duplication Levels":
            if len(cols) < 2:
                log.warning("Sequence Duplication Levels row has too few columns (%d < 2): %r", len(cols), line)
            else:
                data["sequence_duplication_levels"]["rows"].append({
                    "duplication_level":    cols[0],
                    "percentage_of_total":  float(cols[1]),
                })

        elif current_module == "Overrepresented sequences":
            if len(cols) < 4:
                log.warning("Overrepresented sequences row has too few columns (%d < 4): %r", len(cols), line)
            else:
                data["overrepresented_sequences"].append({
                    "sequence":   cols[0],
                    "count":      int(cols[1]),
                    "percentage": float(cols[2]),
                    "source":     cols[3],
                })

        elif current_module == "Kmer Content":
            if len(cols) < 4:
                log.warning("Kmer Content row has too few columns (%d < 4): %r", len(cols), line)
            else:
                data["kmer_content"].append({
                    "sequence":       cols[0],
                    "count":          int(cols[1]),
                    "obs_exp_max":    float(cols[2]),
                    "obs_exp_max_at": cols[3],
                })

        elif current_module == "Adapter Content":
            if len(cols) < 7:
                log.warning("Adapter Content row has too few columns (%d < 7): %r", len(cols), line)
            else:
                data["adapter_content"].append({
                    "position":            cols[0],
                    "illumina_universal":  float(cols[1]),
                    "illumina_small_rna_3": float(cols[2]),
                    "illumina_small_rna_5": float(cols[3]),
                    "nextera_transposase": float(cols[4]),
                    "poly_a":              float(cols[5]),
                    "poly_g":              float(cols[6]),
                })

    if current_module is not None:
        log.warning("File ended while still inside module (missing >>END_MODULE): %s", current_module)

    if data["fastqc_version"] is None:
        log.warning("FastQC version header (##FastQC) not found in file")

    EXPECTED_MODULES = {
        "Basic Statistics",
        "Per base sequence quality",
        "Per tile sequence quality",
        "Per sequence quality scores",
        "Per base sequence content",
        "Per sequence GC content",
        "Per base N content",
        "Sequence Length Distribution",
        "Sequence Duplication Levels",
        "Overrepresented sequences",
        "Adapter Content",
    }

    OPTIONAL_MODULES = {
        "Kmer Content",
    }

    seen = set(data["module_statuses"].keys())

    missing = sorted(EXPECTED_MODULES - seen)
    if missing:
        log.warning(
            "FastQC output missing expected module(s): %s",
            ", ".join(missing),
        )

    unexpected = sorted(seen - EXPECTED_MODULES - OPTIONAL_MODULES)
    if unexpected:
        log.warning(
            "FastQC output contains unexpected/unhandled module(s): %s",
            ", ".join(unexpected),
        )

    # Warn about modules that were present but produced no data rows
    MODULE_DATA_KEYS = {
        "Basic Statistics":             data["basic_statistics"],
        "Per base sequence quality":    data["per_base_quality"],
        "Per tile sequence quality":    data["per_tile_quality"],
        "Per sequence quality scores":  data["per_sequence_quality"],
        "Per base sequence content":    data["per_base_sequence_content"],
        "Per sequence GC content":      data["per_sequence_gc_content"],
        "Per base N content":           data["per_base_n_content"],
        "Sequence Length Distribution": data["sequence_length_distribution"],
        "Sequence Duplication Levels":  data["sequence_duplication_levels"]["rows"],
        "Overrepresented sequences":    data["overrepresented_sequences"],
        "Adapter Content":              data["adapter_content"],
        "Kmer Content":                 data["kmer_content"],
    }
    for module_name, rows in MODULE_DATA_KEYS.items():
        if module_name in seen and not rows:
            log.warning("Module present but contains no data rows: %s", module_name)

    return data


def get_pk_columns(table_name: str) -> list[str]:
    pk_map = {
        "base_dirs": ["base_id"],
        "sub_dirs": ["sub_dir_id"],
        "files": ["file_id"],
    }

    try:
        return pk_map[table_name]
    except KeyError:
        raise ValueError(f"No primary-key mapping defined for table: {table_name}")