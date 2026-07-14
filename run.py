import yaml
import pandas as pd
from typing import Any
from decimal import Decimal
from typing import Any, Iterable
from psycopg2.extras import RealDictCursor
from psycopg2 import sql
import hashlib
import io
import re
import glob
import logging
import argparse
import uuid
import zipfile
from datetime import datetime
from pathlib import Path
import json
import psycopg2

UPDATE = 25  # between INFO (20) and WARNING (30)

logging.addLevelName(UPDATE, "UPDATE")

def update(self, message, *args, **kwargs):
    if self.isEnabledFor(UPDATE):
        self._log(UPDATE, message, args, **kwargs)

logging.Logger.update = update

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger(__name__)

def normalize_value(value):
        if isinstance(value, float):
            return Decimal(str(value))
        return value

class QCDatabaseLoader:
    FASTQC_CHILD_TABLE_IDS = {
        "module_statuses": "fastqc.module_status",
        "per_base_quality": "fastqc.per_base_quality",
        "per_tile_quality": "fastqc.per_tile_quality",
        "per_sequence_quality": "fastqc.per_sequence_quality",
        "per_base_sequence_content": "fastqc.per_base_sequence_content",
        "per_sequence_gc_content": "fastqc.per_sequence_gc_content",
        "per_base_n_content": "fastqc.per_base_n_content",
        "sequence_length_distribution": "fastqc.sequence_length_distribution",
        "sequence_duplication_levels": "fastqc.sequence_duplication_levels",
        "overrepresented_sequences": "fastqc.overrepresented_sequences",
        "kmer_content": "fastqc.kmer_content",
        "adapter_content": "fastqc.adapter_content",
    }

    def __init__(self, conn, table_ids_path: str | Path | None = None):
        self.conn = conn
        self._constraint_cache = {}

        path = (
            Path(table_ids_path)
            if table_ids_path
            else Path(__file__).with_name("table_ids.yaml")
        )
        with path.open(encoding="utf-8") as filehandle:
            table_ids = yaml.safe_load(filehandle)["tables"]

        if len(table_ids) != len(set(table_ids.values())):
            raise ValueError(f"Table names must be unique in {path}")

        invalid_names = [
            name
            for name in table_ids.values()
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name)
        ]
        if invalid_names:
            raise ValueError(f"Invalid table name(s) in {path}: {', '.join(invalid_names)}")

        self._table_names = table_ids

    def get_table_name(self, table_id: str) -> str:
        try:
            return self._table_names[table_id]
        except KeyError as error:
            raise ValueError(f"Unknown table ID: {table_id}") from error
        
    def get_constraint_columns(
        self,
        table_name: str,
        constraint_name: str = None,
        schema_name: str = "qc",
        key_type: str = "PRIMARY KEY",
    ) -> tuple[str, ...]:

        cache_key = (schema_name, table_name, constraint_name, key_type)
        if cache_key in self._constraint_cache:
            return self._constraint_cache[cache_key]

        
        
        
        
        with self.conn.cursor() as cur:

            if constraint_name:
                query = sql.SQL("""
                    SELECT kcu.column_name
                    FROM information_schema.table_constraints tc
                    JOIN information_schema.key_column_usage kcu
                    ON tc.constraint_schema = kcu.constraint_schema
                    AND tc.constraint_name = kcu.constraint_name
                    AND tc.table_schema = kcu.table_schema
                    AND tc.table_name = kcu.table_name
                    WHERE tc.table_schema = %s
                    AND tc.table_name = %s
                    AND tc.constraint_name = %s
                    AND tc.constraint_type = %s
                    ORDER BY kcu.ordinal_position
                """)
                cur.execute(query, (schema_name, table_name, constraint_name, key_type))
                
            else:
                query = sql.SQL("""
                    SELECT kcu.column_name
                    FROM information_schema.table_constraints tc
                    JOIN information_schema.key_column_usage kcu
                    ON tc.constraint_schema = kcu.constraint_schema
                    AND tc.constraint_name = kcu.constraint_name
                    AND tc.table_schema = kcu.table_schema
                    AND tc.table_name = kcu.table_name
                    WHERE tc.table_schema = %s
                    AND tc.table_name = %s
                    AND tc.constraint_type = %s
                    ORDER BY kcu.ordinal_position
                """)
                cur.execute(query, (schema_name, table_name, key_type))
                

            columns = tuple(row[0] for row in cur.fetchall())

        if not columns:
            raise ValueError(
                f"No {key_type} constraint found: "
                f"{schema_name}.{table_name}.{constraint_name}"
            )

        self._constraint_cache[cache_key] = columns
        return columns
    
    
    def get_fk_columns(
        self,
        table_name: str,
        constraint_name: str,
        schema_name: str = "qc",
    ) -> tuple[str, ...]:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT kcu.column_name
                FROM information_schema.table_constraints tc
                JOIN information_schema.key_column_usage kcu
                ON tc.constraint_schema = kcu.constraint_schema
                AND tc.constraint_name = kcu.constraint_name
                AND tc.table_schema = kcu.table_schema
                AND tc.table_name = kcu.table_name
                WHERE tc.table_schema = %s
                AND tc.table_name = %s
                AND tc.constraint_name = %s
                AND tc.constraint_type = 'FOREIGN KEY'
                ORDER BY kcu.ordinal_position
                """,
                (schema_name, table_name, constraint_name),
            )

            columns = tuple(row[0] for row in cur.fetchall())

        if not columns:
            raise ValueError(
                f"No FOREIGN KEY constraint found: "
                f"{schema_name}.{table_name}.{constraint_name}"
            )

        return columns
    
    def diff_rows(
        self,
            old_row: dict[str, Any],
            new_row: dict[str, Any],
            ignore_columns: Iterable[str] = (),
        ) -> dict[str, dict[str, Any]]:
            ignored = set(ignore_columns)
            changes = {}

            for key, new_value in new_row.items():
                if key in ignored:
                    continue
                
                old_value = normalize_value(old_row.get(key))
                new_value = normalize_value(new_value)
                

                if isinstance(old_value, Decimal) and isinstance(new_value, Decimal):
                    if old_value.is_nan() and new_value.is_nan():
                        return changes
                

                if old_value != new_value:
                    changes[key] = {
                        "old": old_value,
                        "new": new_value,
                    }

            return changes
    
    def upsert_row(self,
        table_name: str,
        pk_columns: list[str],
        row: dict[str, Any],
        returning_columns: list[str] = None,
        log_all = True
    ) -> None:
        """
        Upsert one row into PostgreSQL.

        If row exists, compare old vs new values.
        If any non-PK values changed, log the changes and overwrite the row.
        """

        if not returning_columns:
            returning_columns = pk_columns


        if not row:
            raise ValueError("Cannot upsert an empty row")

        columns = list(row.keys())
        non_pk_columns = [col for col in columns if col not in pk_columns]

        where_pk = " AND ".join([f"{col} = %({col})s" for col in pk_columns])

        
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                f"""
                SELECT {", ".join(columns)}
                FROM {table_name}
                WHERE {where_pk}
                """,
                row,
            )
            
            existing = cur.fetchone()
            

            if existing:
                changes = self.diff_rows(existing, row, ignore_columns=pk_columns + tuple(["smdb_upload_uuid"]) + tuple(["config"]))

                if changes:
                    log.update(
                        "Updating %s: changes=%s",
                        table_name,
                        json.dumps(changes, default=str),
                    )
                else:
                    if log_all:
                        log.warning(
                            "Row is exact duplicate of row in %s, no changes made",
                            table_name
                        )

                    
            

            update_assignments = ", ".join(
                [f"{col} = EXCLUDED.{col}" for col in set(non_pk_columns) - {'smdb_upload_uuid'}]
            )

            insert_cols = ", ".join(columns)
            insert_placeholders = ", ".join([f"%({col})s" for col in columns])
            conflict_cols = ", ".join(pk_columns)
            
            sql_query = f"""
                INSERT INTO {table_name} ({insert_cols})
                VALUES ({insert_placeholders})
                ON CONFLICT ({conflict_cols})
                DO UPDATE SET {update_assignments}
                returning {", ".join(returning_columns)}
                """
                
        
            cur.execute(
                sql_query,
                row,
            )
            return cur.fetchone()
        
    def delete_metadata_record(
    self,
    library_id: str,
    flowcell_id: str,
    pipeline_version: str,
    pipeline_hash: str,
) -> bool:
        table_name = self.get_table_name("metadata")

        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    sql.SQL("""
                    DELETE FROM {}
                    WHERE library_id = %s
                    AND flowcell_id = %s
                    AND pipeline_version = %s
                    AND pipeline_hash = %s
                    """).format(sql.Identifier(table_name)),
                    (
                        library_id,
                        flowcell_id,
                        pipeline_version,
                        pipeline_hash,
                    ),
                )

                deleted = cur.rowcount

            self.conn.commit()

            if deleted == 0:
                log.warning("No matching %s record found", table_name)
                return False

            log.info("Deleted %s record and cascading child records", table_name)
            return True

        except Exception:
            self.conn.rollback()
            log.exception("Delete failed")
            return False
        
    def load_adapterremoval_settings(self, data: dict) -> int | None:
        length_distribution = data.pop("length_distribution", [])
        table_name = self.get_table_name("adapterremoval.settings")

        unique_key_columns = self.get_constraint_columns(
            table_name=table_name,
            constraint_name="adapter_removal_settings_unique",
            key_type="UNIQUE",
        )

        result = self.upsert_row(
            table_name=table_name,
            pk_columns=unique_key_columns,
            row=data,
            returning_columns=["settings_id"],
        )

        if result is None:
            self.conn.rollback()
            log.error("AdapterRemoval settings upload failed for: %s", data.get("source_file"))
            return None

        settings_id = result["settings_id"]

        child_table_name = self.get_table_name("adapterremoval.length_distribution")
        child_unique_key_columns = self.get_constraint_columns(
            table_name=child_table_name,
            constraint_name="adapter_removal_length_distribution_unique",
            key_type="UNIQUE",
        )

        for row in length_distribution:
            row["settings_id"] = settings_id

            sub_result = self.upsert_row(
                table_name=child_table_name,
                pk_columns=child_unique_key_columns,
                row=row,
                log_all=False,
            )

            if sub_result is None:
                self.conn.rollback()
                log.error(
                    "AdapterRemoval length distribution upload failed for: %s",
                    data.get("source_file"),
                )
                return None

        self.conn.commit()
        return settings_id
            
            

    def load_samtools_stats(self, data: dict) -> int | None:  
        table_name = self.get_table_name("samtools.stats")
        unique_key_columns = self.get_constraint_columns(
            table_name=table_name,
            constraint_name="samtools_stats_library_id_flowcell_id_pipeline_version_pipe_key",
            key_type="UNIQUE",
        )
                
        result = self.upsert_row(
            table_name=table_name,
            pk_columns=unique_key_columns,
            row=data,
        )
      
        if result is None:
            self.conn.rollback()

            log.error(
                "Upload failed due to unknown error for: %s",
                data["source_path"],
            )

            return None

        self.conn.commit()
        
        return result


    def load_metadata(self, data: dict) -> int | None:  
        table_name = self.get_table_name("metadata")
        unique_key_columns = self.get_constraint_columns(
            table_name=table_name,
            constraint_name="meta_data_pk",
        )
                
        result = self.upsert_row(
            table_name=table_name,
            pk_columns=unique_key_columns,
            row=data,
        )
      

        if result is None:
            self.conn.rollback()

            log.error(
                "Upload failed due to unknown error for: %s",
                data["source_path"],
            )

            return None

        self.conn.commit()
        
        return result

    def delete_fastqc_children(self, file_id: int) -> None:
        with self.conn.cursor() as cur:
            for table_id in self.FASTQC_CHILD_TABLE_IDS.values():
                table = self.get_table_name(table_id)
                cur.execute(
                    sql.SQL("DELETE FROM {} WHERE file_id = %s").format(
                        sql.Identifier(table)
                    ),
                    (file_id,),
                )
                
    def load_fastqc_data(self, data: dict) -> int | None:
        bs = data["basic_statistics"]
        table_name = self.get_table_name("fastqc.report")
        
        unique_key_columns = self.get_constraint_columns(
            table_name=table_name,
            key_type="UNIQUE",
            constraint_name="fastqc_stats_unique",
        )
        
        pk = self.get_constraint_columns(
            table_name=table_name)
        
        foreign_key_columns = self.get_constraint_columns(
            table_name=table_name,
            constraint_name="fastqc_stats_meta_data_fk",
            key_type="FOREIGN KEY"
        )
        
        meta_data = {
            "filename": bs.get("Filename"),
            "source_file": data["source_file"],
            "file_type": bs.get("File type"),
            "encoding": bs.get("Encoding"),
            "total_sequences": int(bs["Total Sequences"]) if "Total Sequences" in bs else None,
            "total_bases": bs.get("Total Bases"),
            "poor_quality_sequences": int(bs["Sequences flagged as poor quality"]) if "Sequences flagged as poor quality" in bs else None,
            "sequence_length": bs.get("Sequence length"),
            "gc_percent": int(bs["%GC"]) if "%GC" in bs else None,
            "library_id": data.get("library_id"),
            "flowcell_id": data.get("flowcell_id"),
            "pipeline_version": data.get("pipeline_version"),
            "pipeline_hash": data.get("pipeline_hash"),
            "data_type": data.get("data_type"),
            "lane": data.get("lane"),
            "read_type": data.get("read_type"),
            "fastqc_version": data.get("fastqc_version"),
        }

        result = self.upsert_row(
            row=meta_data,
            table_name=table_name,
            pk_columns=unique_key_columns,
            returning_columns=["fastqc_stats_id"],
        )
        module_statuses = data.get("module_statuses")
        module_statuses = [{'module_name': k, 'status': v} for k, v in module_statuses.items()]
        data['module_statuses'] = module_statuses

        child_data = {k: v for k, v in data.items() if k not in meta_data and k not in ["basic_statistics"]}
        
        for child_key, rows in child_data.items():
            table_id = self.FASTQC_CHILD_TABLE_IDS[child_key]
            child_table = self.get_table_name(table_id)

            constraint_name = f"{table_id.replace('.', '_')}_unique"
            
            unique_key_columns = self.get_constraint_columns(
                table_name=child_table,
                key_type="UNIQUE",
                constraint_name=constraint_name,
            )

            fk = pk
            fk_col = self.get_constraint_columns(
                table_name=child_table,
                key_type="FOREIGN KEY",
            )

            
            if len(fk) != 1 or len(fk_col) != 1:
                self.conn.rollback()

                log.error(
                    "Expected exactly one PRIMARY KEY column and one FOREIGN KEY column for child table: %s. "
                    "Got PK columns: %s, FK columns: %s",
                    child_table,
                    fk,
                    fk_col,
                )

                return None
        
            dataset = None
            if 'rows' in rows:
                    dataset = rows
                    rows = dataset.pop('rows')            

            for row in rows:
                if dataset:
                    row.update(dataset)
                
                if row.get(fk_col[0]) is not None:
                        self.conn.rollback()

                        log.error("FK not expected here")

                        return None
                row[fk_col[0]] = result[pk[0]]
                                  
                sub_result = self.upsert_row(
                    row=row,
                    table_name=child_table,
                    pk_columns=unique_key_columns,
                    log_all=False,
                )

                if sub_result is None:
                    self.conn.rollback()

                    log.error(
                        "Child table upload failed due to unknown error for: %s, table: %s",
                        data["source_path"],
                        child_table,
                    )

                    return None
            
        if result is None:
            self.conn.rollback()

            log.error(
                "Metadata upsert unexpectedly returned no id: %s",
                data["source_path"],
            )

            return None

        self.conn.commit()



        return result
    
    def load_nonpareil(self, data: list) -> int | None:
        table_name = self.get_table_name("nonpareil.summary")
        unique_key_columns = self.get_constraint_columns(
            table_name=table_name,
            constraint_name="non_pareil_unique",
            key_type="UNIQUE",
        )
        
        for row in data:
            result = self.upsert_row(
                table_name=table_name,
                pk_columns=unique_key_columns,
                row=row,
            )

            if result is None:
                self.conn.rollback()

                log.error(
                    "Upload failed due to unknown error for: %s",
                    data["source_file"],
                )

                return None

        self.conn.commit()
        
        return result
    
                
    def load_bbduk(self, data: dict) -> int | None:
        table_name = self.get_table_name("bbduk.low_complexity")
        unique_key_columns = self.get_constraint_columns(
            table_name=table_name,
            constraint_name="bbduk_low_complexity_source_file_key",
            key_type="UNIQUE",
        )
                
        result = self.upsert_row(
            table_name=table_name,
            pk_columns=unique_key_columns,
            row=data,
        )
      

        if result is None:
            self.conn.rollback()

            log.error(
                "Upload failed due to unknown error for: %s",
                data["source_path"],
            )

            return None

        self.conn.commit()
        
        return result
    
    def load_derep_log(self, data: list) -> int | None:
        table_name = self.get_table_name("derep.summary")
        unique_key_columns = self.get_constraint_columns(
            table_name=table_name,
            constraint_name="derep_unique",
            key_type="UNIQUE",
        )
        
        results = []
        for row in data:
            result = self.upsert_row(
                table_name=table_name,
                pk_columns=unique_key_columns,
                row=row,
            )

            if result is None:
                self.conn.rollback()

                log.error(
                    "Upload failed due to unknown error for: %s",
                    data["source_path"],
                )

                return None
            
            results.append(result)

        self.conn.commit()
        
        return results
    

# ---------------------------------------------------------------------------
# Path metadata extraction
# ---------------------------------------------------------------------------

def extract_fastqc_path_metadata(zip_path: str) -> dict:
    """
    Expected structure:
    /datasets/caeg_production/libraires/lv7/008/003/{library_id}/{date}_{fc}/{version}/{hash}/
        stats/reads/fastqc/{data_type}/{filename}_fastqc.zip

    parts[0]  = '/'
    parts[1]  = 'datasets'
    parts[2]  = 'caeg_production'
    parts[3]  = 'libraires'
    parts[4]  = 'lv7'    \
    parts[5]  = '008'     } sharding dirs — ignored
    parts[6]  = '003'    /
    parts[7]  = library_id
    parts[8]  = date_fc   e.g. '20231015_HV3TWDSX7'
    parts[9]  = version   e.g. 'v1.08'
    parts[10] = hash
    parts[11] = 'stats'
    parts[12] = 'reads'
    parts[13] = 'fastqc'
    parts[14] = data_type e.g. 'trim', 'raw'
    parts[15] = filename  e.g. 'Lib_LV7001856478_L004_singleton_fastqc.zip'
    """
    parts = Path(zip_path).parts

    if len(parts) != 16:
        log.warning(f"Path does not match expected depth (=16, got {len(parts)}): {zip_path}")
        return {
            "library_id": None, "sequencing_date": None, "flowcell_id": None,
            "pipeline_version": None, "pipeline_hash": None,
            "data_type": None, "lane": None, "read_type": None
        }

    library_id            = parts[7]
    date_fc          = parts[8]
    pipeline_version = parts[9]
    pipeline_hash    = parts[10]
    data_type        = parts[14]
    filename         = parts[15]

    # Split 'date_fc' on the FIRST underscore only,
    # since flowcell_id IDs can also contain underscores
    date_str, _, flowcell_id = date_fc.partition("_")
    flowcell_position = flowcell_id[0] if flowcell_id else None
    
    if not len(flowcell_id) == 10:
        log.warning(f"flowcell_id string does not match expected format (side + 9-char ID): '{flowcell_id}' in path: {zip_path}")
        
    elif not flowcell_position in ('B', 'A'):
        log.warning(f"Sequencing side is not valid (should be 'B' or 'A'): '{flowcell_position}' in path: {zip_path}")
        flowcell_position = None 
    
    else:
        flowcell_id = flowcell_id[1:]
    
    try:
        sequencing_date = datetime.strptime(date_str, "%Y%m%d").date()
    except ValueError:
        log.warning(f"Could not parse date from '{date_str}' in path: {zip_path}")
        sequencing_date = None

    # Parse filename: Lib_{library_id}_{lane}_{read_type}_fastqc.zip
    fname_match = re.match(
        r"^Lib_(?P<lib>[^_]+)_(?:(?P<lane>L\d+)_)?(?P<read_type>R1|R2|collapsed|collapsedtrunc|singleton)_fastqc\.zip$",
        filename
    )
    if fname_match:
        fname_libid = fname_match.group("lib")
        if fname_libid != library_id:
            log.warning(
                f"library_id mismatch between path and filename: path={library_id}, filename={fname_libid} ({zip_path})"
            )

        lane      = fname_match.group("lane")
        read_type = fname_match.group("read_type")
        if lane is None:
            if read_type != "collapsed":
                log.warning(
                    f"Expected 'collapsed' for lane-less file but got '{read_type}' in: {filename}"
                )
            lane = 'merged'
    else:
        log.warning(
            f"Filename does not follow expected format "
            f"'Lib_{{library_id}}_[{{lane}}_]{{read_type}}_fastqc.zip' "
            f"(valid read_type: R1, R2, collapsed, collapsedtrunc, singleton): {filename}"
        )
        lane      = None
        read_type = None

    return {
        "library_id":            library_id,
        "flowcell_id":         flowcell_id,
        "pipeline_version": pipeline_version,
        "pipeline_hash":    pipeline_hash,
        "data_type":        data_type,
        "lane":             lane,
        "read_type":        read_type,
    }
    
def validate_regex(
    value: str | None,
    pattern: str,
    field_name: str,
) -> None:
    if value is None or not re.fullmatch(pattern, value):
        log.error(f"{field_name} does not match pattern: {pattern}")
        return False
    else:
        return True

def extract_root_path_metadata(root_path: str) -> dict:
    """
    Expected structure:
    /datasets/caeg_production/libraires/LVXXX/XXX/XXX/{library_id}/{date}_{fc}/{version}/{hash}

    parts[0]  = '/'
    parts[1]  = 'datasets'
    parts[2]  = 'caeg_production'
    parts[3]  = 'libraires'
    parts[4]  = 'lv7'    \
    parts[5]  = '008'     } sharding dirs — ignored
    parts[6]  = '003'    /
    parts[7]  = library_id
    parts[8]  = date_fc   e.g. '20231015_HV3TWDSX7'
    parts[9]  = version   e.g. 'v1.08'
    parts[10] = hash
    """
    parts = Path(root_path).parts

    if len(parts) != 11:
            log.error(f"Path does not match expected depth (=11, got {len(parts)}): {root_path}")
            return {
            "library_id": None, "sequencing_date": None, "flowcell_id": None,
            "pipeline_version": None, "pipeline_hash": None,
        }

    library_id       = parts[7]
    date_fc          = parts[8]
    pipeline_version = parts[9]
    pipeline_hash    = parts[10]
        

    if not validate_regex(
        library_id,
        r"LV\d{10}",
        "library_id",
    ):
        library_id = None

    if not validate_regex(
        pipeline_version,
        r"v\d+\.\d+\.\d+",
        "pipeline_version",
    ):
        pipeline_version = None

    config_yaml = Path(root_path) / "config" / "config.yaml"
    with open(config_yaml, "rb") as f:
        test_digest = hashlib.file_digest(f, "md5").hexdigest()
    
    if test_digest != pipeline_hash:
        log.error(f"Pipeline hash does not match expected value for config.yaml: {pipeline_hash} != {test_digest}")
        pipeline_hash = None

    # Split 'date_fc' on the FIRST underscore only,
    # since flowcell_id IDs can also contain underscores
    date_str, _, flowcell_id = date_fc.partition("_")
    flowcell_position = flowcell_id[0] if flowcell_id else None
    
    if not len(flowcell_id) == 10:
        log.error(f"flowcell_id string does not match expected format (flowcell position + 9-char ID): '{flowcell_id}' in path: {root_path}")
        flowcell_id = None     
    elif not flowcell_position in ('B', 'A'):
        log.error(f"Flowcell position is not valid (should be 'B' or 'A'): '{flowcell_position}' in path: {root_path}")
        flowcell_position = None
        flowcell_id = None
    else:
        flowcell_id = flowcell_id[1:]
        
    if not validate_regex(
        flowcell_id,
        r"[A-Za-z0-9]{9}",
        "flowcell_id"
    ):
        flowcell_id = None
    
    try:
        sequencing_date = datetime.strptime(date_str, "%Y%m%d").date()
    except ValueError:
        log.warning(f"Could not parse date from '{date_str}' in path: {root_path}")
        sequencing_date = None

    return {
        "source_path": root_path,
        "library_id":            library_id,
        "sequencing_date":         sequencing_date,
        "flowcell_id":         flowcell_id,
        "pipeline_version": pipeline_version,
        "pipeline_hash":    pipeline_hash,
        "flowcell_position": flowcell_position,
    }

def extract_nonpareil_stats(tsv_path: str) -> list[dict]:
    """
    Extract Nonpareil stats from a TSV file with 'Metric' and 'Value' columns.
    """
    tsv_path = str(tsv_path)
    
    path_metadata = extract_nonpareil_path_metadata(str(tsv_path))    
    
    df = pd.read_csv(tsv_path, sep="\t")
    df = df.assign(**path_metadata)
    df = df.rename(columns={"modelR": "model_r", "LRstar": "lr_star"})
    df.columns = df.columns.str.strip().str.lower()
    
    return df.to_dict(orient="records")
    

def extract_low_complexity_log_path_metadata(log_path: str) -> dict:
    """
    Expected structure (15 parts):
    /datasets/caeg_production/libraires/lv7/008/003/{library_id}/{date}_{fc}/{version}/{hash}/
        logs/reads/low_complexity/{filename}.log

    parts[7]  = library_id
    parts[8]  = date_fc   e.g. '20231015_HV3TWDSX7'
    parts[9]  = version   e.g. 'v1.08'
    parts[10] = hash
    parts[14] = filename  e.g. 'Lib_LV7008891944_collapsed.log'
    """
    parts = Path(log_path).parts

    if len(parts) != 15:
        log.warning(f"Log path does not match expected depth (=15, got {len(parts)}): {log_path}")
        return {
            "library_id": None, "sequencing_date": None, "flowcell_id": None,
            "pipeline_version": None, "pipeline_hash": None,
            "read_type": None, "flowcell_position": None
        }

    library_id            = parts[7]
    date_fc          = parts[8]
    pipeline_version = parts[9]
    pipeline_hash    = parts[10]
    filename         = parts[14]

    date_str, _, flowcell_id = date_fc.partition("_")
    flowcell_position = flowcell_id[0] if flowcell_id else None
    
    if not len(flowcell_id) == 10:
        log.error(f"flowcell_id string does not match expected format (flowcell position + 9-char ID): '{flowcell_id}'")
        flowcell_id = None     
    elif not flowcell_position in ('B', 'A'):
        log.error(f"Flowcell position is not valid (should be 'B' or 'A'): '{flowcell_position}'")
        flowcell_position = None
        flowcell_id = None
    else:
        flowcell_id = flowcell_id[1:]

    fname_match = re.match(
        r"^Lib_(?P<lib>[^_]+)_(?:(?P<lane>L\d+)_)?(?P<read_type>R1|R2|collapsed|collapsedtrunc|singleton)\.log$",
        filename,
    )
    if fname_match:
        fname_libid = fname_match.group("lib")
        if fname_libid != library_id:
            log.warning(
                f"library_id mismatch between path and filename: path={library_id}, filename={fname_libid} ({log_path})"
            )
        read_type = fname_match.group("read_type")
    else:
        log.warning(
            f"Log filename does not follow expected format "
            f"'Lib_{{library_id}}_[{{lane}}_]{{read_type}}.log' "
            f"(valid read_type: R1, R2, collapsed, collapsedtrunc, singleton): {filename}"
        )
        read_type = None

    return {
        "library_id":            library_id,
        "flowcell_id":         flowcell_id,
        "pipeline_version": pipeline_version,
        "pipeline_hash":    pipeline_hash,
        "read_type":        read_type,
        "flowcell_position": flowcell_position,
    }


# ---------------------------------------------------------------------------
# Zip handling
# ---------------------------------------------------------------------------

def open_fastqc_zip(zip_path: str) -> io.StringIO:
    """Unzip .fastqc.zip and return fastqc_data.txt contents as a text stream."""
    try:
        with zipfile.ZipFile(zip_path) as zf:
            matches = [f for f in zf.namelist() if f.endswith("fastqc_data.txt")]
            if len(matches) == 0:
                raise ValueError(f"No fastqc_data.txt found in zip: {zip_path}")
            if len(matches) > 1:
                raise ValueError(f"Expected 1 fastqc_data.txt in zip, found {len(matches)}: {matches}")
            target = matches[0]
            try:
                return io.StringIO(zf.read(target).decode("utf-8"))
            except UnicodeDecodeError as e:
                raise ValueError(f"Could not decode {target} as UTF-8 in {zip_path}: {e}") from e
    except zipfile.BadZipFile as e:
        raise ValueError(f"Bad zip file: {zip_path}: {e}") from e
    
def delete_metadata_record(
    self,
    library_id: str,
    flowcell_id: str,
    pipeline_version: str,
    pipeline_hash: str,
) -> bool:
    table_name = self.get_table_name("metadata")

    try:
        with self.conn.cursor() as cur:
            cur.execute(
                sql.SQL("""
                DELETE FROM {}
                WHERE library_id = %s
                  AND flowcell_id = %s
                  AND pipeline_version = %s
                  AND pipeline_hash = %s
                """).format(sql.Identifier(table_name)),
                (library_id, flowcell_id, pipeline_version, pipeline_hash),
            )

            deleted = cur.rowcount

        self.conn.commit()

        if deleted == 0:
            log.warning("No matching %s record found", table_name)
            return False

        log.info("Deleted %s record and cascading children", table_name)
        return True

    except Exception:
        self.conn.rollback()
        log.exception("Delete failed")
        return False

# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

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


def parse_bbduk_log(filehandle) -> dict:
    """
    Parse a BBDuk low-complexity filtering log file
    (found at logs/reads/low_complexity/<filename>.log).
    Returns a dict with extracted statistics.
    """
    data = {
        "bbduk_version":           None,
        "entropy":                 None,
        "entropy_window":          None,
        "entropy_k":               None,
        "ref":                     None,
        "input_reads":             None,
        "input_bases":             None,
        "contaminant_reads":       None,
        "contaminant_reads_pct":   None,
        "contaminant_bases":       None,
        "contaminant_bases_pct":   None,
        "low_entropy_reads":       None,
        "low_entropy_reads_pct":   None,
        "low_entropy_bases":       None,
        "low_entropy_bases_pct":   None,
        "total_removed_reads":     None,
        "total_removed_reads_pct": None,
        "total_removed_bases":     None,
        "total_removed_bases_pct": None,
        "result_reads":            None,
        "result_reads_pct":        None,
        "result_bases":            None,
        "result_bases_pct":        None,
        "processing_time_seconds": None,
    }

    for raw_line in filehandle:
        line = raw_line.rstrip("\n").strip()

        # Strip wrapper-script timestamp prefix if present
        ts_match = re.match(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} (.+)$", line)
        content = ts_match.group(1).strip() if ts_match else line

        if not content:
            continue

        # BBDuk version line (from BBDuk stdout)
        m = re.match(r"^Version\s+(\S+)$", content)
        if m:
            data["bbduk_version"] = m.group(1)
            continue

        # Entropy parameters from wrapper "extra arguments:" line
        if content.startswith("extra arguments:"):
            extra = content[len("extra arguments:"):].strip()
            for param, field, cast in [
                ("entropy",       "entropy",       float),
                ("entropywindow", "entropy_window", int),
                ("entropyk",      "entropy_k",      int),
            ]:
                m = re.search(rf"{param}=(\S+)", extra)
                if m:
                    try:
                        data[field] = cast(m.group(1))
                    except ValueError:
                        log.warning("Could not parse %s value: %r", param, m.group(1))
            continue

        # ref databases from wrapper "parsed argument:  ref=..." line
        m = re.match(r"^parsed argument:\s+ref=(\S+)", content)
        if m:
            data["ref"] = m.group(1).strip()
            continue

        # Input
        m = re.match(r"^Input:\s+(\d+)\s+reads\s+(\d+)\s+bases", content)
        if m:
            data["input_reads"] = int(m.group(1))
            data["input_bases"] = int(m.group(2))
            continue

        # Contaminants
        m = re.match(
            r"^Contaminants:\s+(\d+)\s+reads\s+\(([\d.]+)%\)\s+(\d+)\s+bases\s+\(([\d.]+)%\)",
            content,
        )
        if m:
            data["contaminant_reads"]     = int(m.group(1))
            data["contaminant_reads_pct"] = float(m.group(2))
            data["contaminant_bases"]     = int(m.group(3))
            data["contaminant_bases_pct"] = float(m.group(4))
            continue

        # Low entropy discards
        m = re.match(
            r"^Low entropy discards:\s+(\d+)\s+reads\s+\(([\d.]+)%\)\s+(\d+)\s+bases\s+\(([\d.]+)%\)",
            content,
        )
        if m:
            data["low_entropy_reads"]     = int(m.group(1))
            data["low_entropy_reads_pct"] = float(m.group(2))
            data["low_entropy_bases"]     = int(m.group(3))
            data["low_entropy_bases_pct"] = float(m.group(4))
            continue

        # Total Removed
        m = re.match(
            r"^Total Removed:\s+(\d+)\s+reads\s+\(([\d.]+)%\)\s+(\d+)\s+bases\s+\(([\d.]+)%\)",
            content,
        )
        if m:
            data["total_removed_reads"]     = int(m.group(1))
            data["total_removed_reads_pct"] = float(m.group(2))
            data["total_removed_bases"]     = int(m.group(3))
            data["total_removed_bases_pct"] = float(m.group(4))
            continue

        # Result
        m = re.match(
            r"^Result:\s+(\d+)\s+reads\s+\(([\d.]+)%\)\s+(\d+)\s+bases\s+\(([\d.]+)%\)",
            content,
        )
        if m:
            data["result_reads"]     = int(m.group(1))
            data["result_reads_pct"] = float(m.group(2))
            data["result_bases"]     = int(m.group(3))
            data["result_bases_pct"] = float(m.group(4))
            continue

        # Processing time
        m = re.match(r"^Time:\s+([\d.]+)\s+seconds", content)
        if m:
            data["processing_time_seconds"] = float(m.group(1))
            continue

    missing = [f for f in ("input_reads", "input_bases", "total_removed_reads", "result_reads")
               if data[f] is None]
    if missing:
        log.warning("BBDuk log missing expected fields: %s", ", ".join(missing))

    return data

def validate_root_metadata(meta: dict, path: str) -> bool:
    required = (
        "library_id",
        "sequencing_date",
        "flowcell_id",
        "pipeline_version",
        "pipeline_hash",
    )

    missing = [field for field in required if meta.get(field) is None]

    if missing:
        log.error(
            "Invalid root metadata for '%s'. Missing: %s",
            path,
            ", ".join(missing),
        )
        return False

    return True


def extract_low_complexity_log_path_metadata(log_path: str) -> dict:
    """
    Expected structure (15 parts):
    /datasets/caeg_production/libraires/lv7/008/003/{library_id}/{date}_{fc}/{version}/{hash}/
        logs/reads/low_complexity/{filename}.log

    parts[7]  = library_id
    parts[8]  = date_fc   e.g. '20231015_HV3TWDSX7'
    parts[9]  = version   e.g. 'v1.08'
    parts[10] = hash
    parts[14] = filename  e.g. 'Lib_LV7008891944_collapsed.log'
    """
    parts = Path(log_path).parts

    if len(parts) != 15:
        log.warning(f"Log path does not match expected depth (=15, got {len(parts)}): {log_path}")
        return {
            "library_id": None, "sequencing_date": None, "flowcell_id": None,
            "pipeline_version": None, "pipeline_hash": None,
            "read_type": None, "flowcell_position": None
        }

    library_id            = parts[7]
    date_fc          = parts[8]
    pipeline_version = parts[9]
    pipeline_hash    = parts[10]
    filename         = parts[14]
    data_type       = parts[13]

    date_str, _, flowcell_id = date_fc.partition("_")
    flowcell_position = flowcell_id[0] if flowcell_id else None
    
    if not len(flowcell_id) == 10:
        log.error(f"flowcell_id string does not match expected format (flowcell position + 9-char ID): '{flowcell_id}'")
        flowcell_id = None     
    elif not flowcell_position in ('B', 'A'):
        log.error(f"Flowcell position is not valid (should be 'B' or 'A'): '{flowcell_position}'")
        flowcell_position = None
        flowcell_id = None
    else:
        flowcell_id = flowcell_id[1:]

    fname_match = re.match(
        r"^Lib_(?P<lib>[^_]+)_(?:(?P<lane>L\d+)_)?(?P<read_type>R1|R2|collapsed|collapsedtrunc|singleton)\.log$",
        filename,
    )
    if fname_match:
        fname_libid = fname_match.group("lib")
        lane = fname_match.group("lane")
        if fname_libid != library_id:
            log.warning(
                f"library_id mismatch between path and filename: path={library_id}, filename={fname_libid} ({log_path})"
            )
        read_type = fname_match.group("read_type")
        
        if lane is None:
            if read_type != "collapsed":
                log.warning(
                    f"Expected 'collapsed' for lane-less file but got '{read_type}' in: {filename}"
                )
            lane = 'merged'
    else:
        log.warning(
            f"Log filename does not follow expected format "
            f"'Lib_{{library_id}}_[{{lane}}_]{{read_type}}.log' "
            f"(valid read_type: R1, R2, collapsed, collapsedtrunc, singleton): {filename}"
        )
        read_type = None

    return {
        "library_id":            library_id,
        "flowcell_id":         flowcell_id,
        "pipeline_version": pipeline_version,
        "pipeline_hash":    pipeline_hash,
        "read_type":        read_type,
        "flowcell_position": flowcell_position,
        "data_type":        data_type,
        "lane":             lane,
    }
    
    
def extract_nonpareil_path_metadata(tsv_path: str) -> dict:
    """
    Expected structure (15 parts):
    /datasets/caeg_production/libraires/LXX/XXX/XXX/{library_id}/{date}_{fc}/{version}/{hash}/
        stats/reads/nonpareil/{data_type}/{filename}.tsv

    parts[7]  = library_id
    parts[8]  = date_fc   e.g. '20231015_HV3TWDSX7'
    parts[9]  = version   e.g. 'v1.08'
    parts[10] = hash
    parts[14] = filename  e.g. 'Lib_LV7008891944_collapsed.log'
    """
    parts = Path(tsv_path).parts
    
    base_parts = parts[:11]
    suffix_parts = parts[11:]

    if len(parts) != 16:
        log.warning(f"Path does not match expected depth (=16, got {len(parts)}): {tsv_path}")
        return {
            "library_id": None, "sequencing_date": None, "flowcell_id": None,
            "pipeline_version": None, "pipeline_hash": None,
            "read_type": None, "flowcell_position": None
        }
        
    root_meta_data = extract_root_path_metadata(str(Path(*base_parts)))

    library_id       = root_meta_data.get("library_id")
    flowcell_id      = root_meta_data.get("flowcell_id")
    pipeline_version = root_meta_data.get("pipeline_version")
    pipeline_hash    = root_meta_data.get("pipeline_hash")
    filename         = suffix_parts[4]
    data_type       = suffix_parts[3]
    
    fname_match = re.match(
    r"^Lib_(?P<lib>[^_]+)_(?:(?P<lane>L\d+)_)?(?P<read_type>R1|R2|collapsed|collapsedtrunc|singleton)\.tsv$",
    filename,
)

    if fname_match:
        fname_metadata = fname_match.groupdict()

        fname_libid = fname_metadata["lib"]
        lane = fname_metadata["lane"]
        read_type = fname_metadata["read_type"]

        if fname_libid != library_id:
            log.warning(
                f"library_id mismatch between path and filename: path={library_id}, filename={fname_libid} ({tsv_path})"
            )
            
        if lane is None:
            if read_type != "collapsed":
                log.warning(
                    f"Expected 'collapsed' for lane-less file but got '{read_type}' in: {filename}"
                )
            lane = 'merged'
    else:
        log.warning(
            f"Filename does not follow expected format, aborting upsert"
            f"'Lib_{{library_id}}_[{{lane}}_]{{read_type}}.tsv' "
            f"(valid read_type: R1, R2, collapsed, collapsedtrunc, singleton): {filename}"
        )
        return None

    return {
        "library_id":            library_id,
        "flowcell_id":         flowcell_id,
        "pipeline_version": pipeline_version,
        "pipeline_hash":    pipeline_hash,
        "read_type":        read_type,
        "data_type":        data_type,
        'lane':             lane,
        'source_file':     tsv_path,
        }
    
def parse_derep_log(path: str | Path) -> dict:
    
        
    parts = Path(path).parts
    
    base_parts = parts[:11]
    suffix_parts = parts[11:]

    if len(parts) != 15:
        log.warning(f"Path does not match expected depth (=16, got {len(parts)}): {path}")
        return {
            "library_id": None, "sequencing_date": None, "flowcell_id": None,
            "pipeline_version": None, "pipeline_hash": None,
            "read_type": None, "flowcell_position": None
        }
        
    root_meta_data = extract_root_path_metadata(str(Path(*base_parts)))

    library_id       = root_meta_data.get("library_id")
    flowcell_id      = root_meta_data.get("flowcell_id")
    pipeline_version = root_meta_data.get("pipeline_version")
    pipeline_hash    = root_meta_data.get("pipeline_hash")
    filename         = suffix_parts[3]
    data_type       = suffix_parts[2]
    fname_match = re.match(
    r"^Lib_(?P<lib>[^_]+)_(?:(?P<lane>L\d+)_)?(?P<read_type>R1|R2|collapsed|collapsedtrunc|singleton)\.log$",
    filename,
)

    if fname_match:
        fname_metadata = fname_match.groupdict()

        fname_libid = fname_metadata["lib"]
        lane = fname_metadata["lane"]
        read_type = fname_metadata["read_type"]

        if fname_libid != library_id:
            log.warning(
                f"library_id mismatch between path and filename: path={library_id}, filename={fname_libid} ({path})"
            )
            
        if lane is None:
            if read_type != "collapsed":
                log.warning(
                    f"Expected 'collapsed' for lane-less file but got '{read_type}' in: {filename}"
                )
            lane = 'merged'
    else:
        log.warning(
            f"Filename does not follow expected format, aborting upsert"
            f"'Lib_{{library_id}}_[{{lane}}_]{{read_type}}.tsv' "
            f"(valid read_type: R1, R2, collapsed, collapsedtrunc, singleton): {filename}"
        )
        return None
    
    with open(path) as f:
        lines = f.readlines()
        
    result = []
    for line in lines:
        parts = line.strip().split()
        if len(parts) != 5:
            log.error(f"Unexpected log format: {path}")
            
        pre_result = {"_".join(parts[2:]): int(parts[1])}
        pre_result['source_file'] = path
        pre_result['read_type'] = read_type
        pre_result['lane'] = lane
        pre_result['library_id'] = library_id
        pre_result['flowcell_id'] = flowcell_id
        pre_result['pipeline_version'] = pipeline_version
        pre_result['pipeline_hash'] = pipeline_hash
        pre_result['data_type'] = data_type
        result.append(pre_result)
    
    result = pd.DataFrame(result)
    return result

def parse_pipeline_config(path: str | Path) -> dict:
    
    '''
    Expected path: /datasets/caeg_production/libraries/LV7/008/864/LV7008864206/20250415_BHVVTHDSXC/v1.0.8/4ebe3d1488023a26ec5b50b4e6a71f6b/config/config.yaml
    
    '''
    result = {}
    yaml_path = Path(path)
    
    path_parts = yaml_path.parts
    
    base_parts = path_parts[:11]
    

    with yaml_path.open() as f:
        yaml_data = yaml.safe_load(f)
    
    yaml_data = json.dumps(yaml_data)
    
    
    result['config'] = yaml_data
    result['config_source_file'] = str(yaml_path)
    
    return result


def parse_samtools_stats(filepath):
    data = {}

    with open(filepath) as f:
        for line in f:
            if not line.startswith("SN\t"):
                continue

            _, metric, value, *_ = line.rstrip().split("\t")

            metric = metric.rstrip(":")
            metric = (
                metric.lower()
                .replace(" ", "_")
                .replace("(", "")
                .replace(")", "")
                .replace("%", "pct")
                .replace("/", "_")
                .replace("1st", "first")
                .replace('-', '_')
            )

            # remove comments
            value = value.split("#")[0].strip()

            try:
                if "." in value or "e" in value.lower():
                    value = float(value)
                else:
                    value = int(value)
            except ValueError:
                pass

            data[metric] = value

    return data

def parse_samtools_metadata(filepath):
    """
    Expected structure (15 parts):
    /datasets/caeg_production/libraries/LV7/008/864/LV7008864206/20250415_BHVVTHDSXC/v1.0.8/4ebe3d1488023a26ec5b50b4e6a71f6b
    /stats/{data_type}/samtools_stats/Lib_LV7008864206_collapsed.txt

    parts[7]  = library_id
    parts[8]  = date_fc   e.g. '20231015_HV3TWDSX7'
    parts[9]  = version   e.g. 'v1.08'
    parts[10] = hash
    parts[14] = filename  e.g. 'Lib_LV7008891944_collapsed.log'
    """
    parts = Path(filepath).parts
    
    base_parts = parts[:11]
    suffix_parts = parts[11:]

    if len(parts) != 15:
        log.warning(f"Path does not match expected depth (=15, got {len(parts)}): {filepath}")
        return {
            "library_id": None, "sequencing_date": None, "flowcell_id": None,
            "pipeline_version": None, "pipeline_hash": None,
            "read_type": None, "flowcell_position": None
        }
        
    root_meta_data = extract_root_path_metadata(str(Path(*base_parts)))

    library_id       = root_meta_data.get("library_id")
    flowcell_id      = root_meta_data.get("flowcell_id")
    pipeline_version = root_meta_data.get("pipeline_version")
    pipeline_hash    = root_meta_data.get("pipeline_hash")
    filename         = suffix_parts[3]
    data_type       = suffix_parts[1]
    
    
    if data_type not in ("prefilter_aligns", "aligns"):
        log.warning(f"Unexpected data_type '{data_type}' in path: {filepath}")
    
    fname_match = re.match(
    r"^Lib_(?P<lib>[^_]+)_(?:(?P<lane>L\d+)_)?(?P<read_type>R1|R2|collapsed|collapsedtrunc|singleton)\.txt$",
    filename,
)

    if fname_match:
        fname_metadata = fname_match.groupdict()

        fname_libid = fname_metadata["lib"]
        lane = fname_metadata["lane"]
        read_type = fname_metadata["read_type"]

        if fname_libid != library_id:
            log.warning(
                f"library_id mismatch between path and filename: path={library_id}, filename={fname_libid} ({filepath})"
            )
            
        if lane is None:
            if read_type != "collapsed":
                log.warning(
                    f"Expected 'collapsed' for lane-less file but got '{read_type}' in: {filename}"
                )
            lane = 'merged'
    else:
        log.warning(
            f"Filename does not follow expected format, aborting upsert"
            f"'Lib_{{library_id}}_[{{lane}}_]{{read_type}}.tsv' "
            f"(valid read_type: R1, R2, collapsed, collapsedtrunc, singleton): {filename}"
        )
        return None

    return {
        "library_id":            library_id,
        "flowcell_id":         flowcell_id,
        "pipeline_version": pipeline_version,
        "pipeline_hash":    pipeline_hash,
        "read_type":        read_type,
        "data_type":        data_type,
        'lane':             lane,
        'source_file':     filepath,
        }

def extract_adapterremoval_path_metadata(path: str | Path) -> dict:
    path = Path(path)

    parts = path.parts
    base_parts = parts[:11]

    if len(parts) != 15:
        log.warning(
            "AdapterRemoval settings path does not match expected depth (=15, got %s): %s",
            len(parts),
            path,
        )
        return {}

    root_meta = extract_root_path_metadata(str(Path(*base_parts)))

    filename = parts[14]
    data_type = parts[13]

    fname_match = re.match(
        r"^Lib_(?P<lib>[^_]+)_(?P<lane>L\d+)_(?P<sequencing_method>pe)\.settings$",
        filename,
    )

    if not fname_match:
        log.warning("Unexpected AdapterRemoval settings filename: %s", filename)
        return None

    fname_meta = fname_match.groupdict()

    if fname_meta["lib"] != root_meta.get("library_id"):
        log.warning(
            "library_id mismatch between path and filename: path=%s filename=%s",
            root_meta.get("library_id"),
            fname_meta["lib"],
        )

    return {
        "library_id": root_meta.get("library_id"),
        "flowcell_id": root_meta.get("flowcell_id"),
        "pipeline_version": root_meta.get("pipeline_version"),
        "pipeline_hash": root_meta.get("pipeline_hash"),
        "data_type": data_type,
        "lane": fname_meta["lane"],
        "sequencing_method": fname_meta["sequencing_method"],
        "source_file": str(path),
    }


def parse_adapterremoval_settings(path: str | Path) -> dict:
    path = Path(path)

    meta = extract_adapterremoval_path_metadata(path)

    result = {
    **meta,
    "adapter_removal_version": None,
    "mode": None,
    "length_distribution": [],
}

    section = None

    
    with path.open() as f:
        for raw_line in f:
            line = raw_line.strip()

            if not line:
                continue

            if line.startswith("AdapterRemoval ver."):
                result["adapter_removal_version"] = line.replace("AdapterRemoval ver.", "").strip()
                continue

            if line == "Trimming of paired-end reads":
                result["mode"] = "paired_end"
                continue

            if line.startswith("[") and line.endswith("]"):
                section = line.strip("[]")
                continue

            if section == "Adapter sequences":
                if ":" not in line:
                    continue

                key, value = line.split(":", 1)
                field = normalize_db_column_name(key)

                if field in result:
                    raise ValueError(
                        f"Duplicate normalized field name: {key!r} -> {field!r} "
                        f"in file {path}"
                    )

                result[field] = value.strip()

                continue

            if section in {"Adapter trimming", "Trimming statistics"}:
                if ":" not in line:
                    continue

                key, value = line.split(":", 1)
                field = normalize_db_column_name(key)

                if field in result:
                    raise ValueError(
                        f"Duplicate normalized field name: {key!r} -> {field!r} "
                        f"in file {path}"
                    )

                result[field] = parse_adapterremoval_value(value.strip())

                continue

            if section == "Length distribution":
                if line.startswith("Length"):
                    continue

                cols = line.split()
                if len(cols) != 8:
                    log.warning("Unexpected length distribution row in %s: %r", path, line)
                    continue

                result["length_distribution"].append({
                    "length": int(cols[0]),
                    "mate1": int(cols[1]),
                    "mate2": int(cols[2]),
                    "singleton": int(cols[3]),
                    "collapsed": int(cols[4]),
                    "collapsed_truncated": int(cols[5]),
                    "discarded": int(cols[6]),
                    "all_reads": int(cols[7]),
                })

    return result


def parse_adapterremoval_value(value: str):
    if value == "NA":
        return None

    if value == "Yes":
        return True

    if value == "No":
        return False

    try:
        if "." in value:
            return float(value)
        return int(value)
    except ValueError:
        return value
    
def normalize_db_column_name(key: str) -> str:
    key = key.strip().lower()

    key = key.replace("<=", " le ")
    key = key.replace(">=", " ge ")
    key = key.replace("<", " lt ")
    key = key.replace(">", " gt ")
    key = key.replace("%", " pct ")
    key = key.replace("+", " plus ")

    # Remove only the bracket/parenthesis characters, not their contents
    key = key.replace("(", " ")
    key = key.replace(")", " ")
    key = key.replace("[", " ")
    key = key.replace("]", " ")

    key = re.sub(r"[^a-z0-9]+", "_", key)
    key = re.sub(r"_+", "_", key)

    return key.strip("_")


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def mother(
    conn,
    librootfolder: str,
    include_per_tile_quality: bool = False,
) -> None:
    
    """
    Orchestrate parsing and loading for all FastQC zip files and BBDuk
    low-complexity log files under a given library root folder.
    """

    path = Path(librootfolder)

    root_path_meta = extract_root_path_metadata(librootfolder)
    upload_uuid = str(uuid.uuid4())
    log.info(f"SMDB upload ID for this batch: {upload_uuid}")
    root_path_meta["smdb_upload_uuid"] = upload_uuid

    
    if not validate_root_metadata(root_path_meta, librootfolder):
        return

    loader = QCDatabaseLoader(conn)
    log.info(f"Processing Base Directory Metadata: {librootfolder}")
    
    config_path = str(Path(librootfolder) / "config/config.yaml")

    if not config_path:
        log.warning(f"No config.yaml file found")
    else:
        log.info(f"Processing: {config_path}")

        try:
            config_data = parse_pipeline_config(config_path)
            
        except Exception as e:
            log.exception(f"Failed to process Pipeline Config: {e}")
            conn.rollback()
    
    root_path_meta.update(config_data)
    meta_data_id = loader.load_metadata(root_path_meta)
    
    
    if meta_data_id is None:
        return
    

       # --- AdapterRemoval settings ---
    path_pattern = str(Path(librootfolder) / "stats/reads/trim/*.settings")
    file_paths = glob.glob(path_pattern)

    if not file_paths:
        log.warning("No AdapterRemoval settings files found")
    else:
        if len(file_paths) > 8:
            log.warning("Expected at most 8 AdapterRemoval settings files, found %s", len(file_paths))

        log.info("Processing %s AdapterRemoval settings file(s)", len(file_paths))

        for settings_path in file_paths:
            log.info("Processing: %s", settings_path)

            try:
                data = parse_adapterremoval_settings(settings_path)

                if data is None:
                    log.warning("Skipping invalid AdapterRemoval settings file: %s", settings_path)
                    continue

                loader.load_adapterremoval_settings(data)

            except Exception as e:
                log.exception("Failed to process AdapterRemoval settings %s: %s", settings_path, e)
                conn.rollback()
    
        
    
    
    # --- FastQC zips ---
    pattern = str(Path(librootfolder) / "stats/reads/fastqc/*/*fastqc.zip")
    files   = glob.glob(pattern, recursive=True)

    if not files:
        log.warning(f"No FastQC zip files found")
    else:
        log.info(f"Processing {len(files)} FastQC file(s)")

        for zip_path in files:
            try:
                log.info(f"Processing: {zip_path}")
                # 1. Extract metadata from the path
                meta = extract_fastqc_path_metadata(zip_path)

                # 2. Parse the file contents
                fh   = open_fastqc_zip(zip_path)
                data = parse_fastqc_file(fh)
                if not include_per_tile_quality:
                    data.pop("per_tile_quality", None)
                    data["module_statuses"].pop("Per tile sequence quality", None)

                # 3. Merge — path metadata wins on conflict (e.g. library_id)
                data["source_file"] = zip_path
                data.update(meta)
                

                required_bs = {
                    "Filename",
                    "File type",
                    "Encoding",
                    "Total Sequences",
                    "Total Bases",
                    "Sequences flagged as poor quality",
                    "Sequence length",
                    "%GC"
                }

                seen_bs = set(data["basic_statistics"].keys())

                missing_required = sorted(required_bs - seen_bs)
                if missing_required:
                    log.warning("Skipping due to missing required Basic Statistics: %s", ", ".join(missing_required))
                    continue

                extra_bs = sorted(seen_bs - required_bs)
                if extra_bs:
                    log.warning("Skipping due to additional Basic Statistics fields present: %s", ", ".join(extra_bs))
                    continue

                # Optional strict policy: skip malformed filename/path metadata
                if data.get("lane") is None or data.get("read_type") is None:
                    log.warning(f"Skipping due to invalid filename metadata: {zip_path}")
                    continue

                # 4. Load to DB
                loader.load_fastqc_data(data)

            except StopIteration:
                log.error(f"No fastqc_data.txt found inside zip: {zip_path}")
                conn.rollback()
            except Exception as e:
                log.exception(f"Failed to process {zip_path}: {e}")
                conn.rollback()

    # --- BBDuk low-complexity logs ---
    log_pattern = str(Path(librootfolder) / "logs/reads/low_complexity/*.log")
    log_files   = glob.glob(log_pattern)

    if not log_files:
        log.warning(f"No BBDuk low-complexity log files found")
    else:
        log.info(f"Processing {len(log_files)} BBDuk log file(s)")

        for log_path in log_files:
            log.info(f"Processing BBDuk log: {log_path}")
            try:
                meta = extract_low_complexity_log_path_metadata(log_path)

                with open(log_path, encoding="utf-8") as fh:
                    data = parse_bbduk_log(fh)

                data["source_file"] = log_path
                data.update(meta)

                if data.get("read_type") is None:
                    log.warning(f"Skipping due to invalid filename metadata: {log_path}")
                    continue

                if data.get("input_reads") is None:
                    log.warning(f"Skipping due to missing summary stats in log: {log_path}")
                    continue

                loader.load_bbduk(data)

            except Exception as e:
                log.exception(f"Failed to process BBDuk log {log_path}: {e}")
                conn.rollback()

# --- Non pareil tsv ---
    path_pattern = str(Path(librootfolder) / "stats/reads/nonpareil/derep/*.tsv")
    file_paths   = glob.glob(path_pattern)

    if not file_paths:
        log.warning(f"No Nonpareil tsv found")
    else:
        log.info(f"Processing {len(file_paths)} nonpareil tsv file(s)")

        for ele in file_paths:
            log.info(f"Processing {ele}")
            try:
                data = extract_nonpareil_stats(ele)
                loader.load_nonpareil(data)

            except Exception as e:
                log.exception(f"Failed to process Nonpareil tsv: {e}")
                conn.rollback()
                
            
# --- Derep log ---

    path_pattern = str(Path(librootfolder) / "logs/reads/derep/*.log")
    file_paths   = glob.glob(path_pattern)

    if not file_paths:
        log.warning(f"No derep log found")
    else:
        log.info(f"Processing {len(file_paths)} derep log file(s)")

        for ele in file_paths:
            log.info(f"Processing {ele}")
            try:
                data = parse_derep_log(ele)
                
                data = data.to_dict(orient="records")
                loader.load_derep_log(data)

            except Exception as e:
                log.exception(f"Failed to process Derep log: {e}")
                conn.rollback()
                
# --- samtools ---
    ''''/datasets/caeg_production/libraries/LV7/008/864/LV7008864206/20250415_BHVVTHDSXC/v1.0.8/4ebe3d1488023a26ec5b50b4e6a71f6b/stats/aligns/samtools_stats'''

    path_pattern = str(Path(librootfolder) / "stats/*/samtools_stats/*.txt")
    file_paths   = glob.glob(path_pattern)

    if not file_paths:
        log.warning(f"No samtools stats files found")
    else:
        if len(file_paths) != 2:
            log.warning(f"Expected 2 samtools stats files, found {len(file_paths)}")

        log.info(f"Processing {len(file_paths)} samtools stats file(s)")

        for ele in file_paths:
            log.info(f"Processing: {ele}")
            try:
                meta_data = parse_samtools_metadata(ele)
                data = parse_samtools_stats(ele)
                data.update(meta_data)
                loader.load_samtools_stats(data)

            except Exception as e:
                log.exception(f"Failed to process Samtools stats: {e}")
                conn.rollback()

 
                
                    
    
                
                

def confirm_delete(librootfolder: str) -> bool:
    print()
    print("WARNING: You are about to delete database records.")
    print(f"Library root folder: {librootfolder}")
    print()
    answer = input("Type DELETE to confirm: ")

    return answer == "DELETE"

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    # Usage examples:
    #
    # Single library folder:
    #   python -m parsers.fastqc_to_db_claude \
    #       --librootfolder /datasets/caeg_production/libraries/LV7/008/891/LV7008891944/20260401_A23JH5FLT4/v1.0.8/4ebe3d1488023a26ec5b50b4e6a71f6b/ \
    #       --host dandypdb01fl --dbname smdb --user postgres --password yourpassword
    #


    parser = argparse.ArgumentParser(
        description=(
            "Parse FastQC zip files and BBDuk low-complexity logs into PostgreSQL, "
            "either from a single library root folder or a glob pattern.\n\n"
            "Example:\n"
            "  python -m parsers.fastqc_to_db_claude \\\n"
            "      --librootfolder /datasets/caeg_production/libraries/LV7/008/891/"
            "LV7008891944/20260401_A23JH5FLT4/v1.0.8/4ebe3d1488023a26ec5b50b4e6a71f6b/ \\\n"
            "      --host dandypdb01fl --dbname smdb --user postgres --password yourpassword\n\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--librootfolder",
        help="Path to a single library root folder "
             "(e.g. /datasets/caeg_production/libraries/LV7/008/891/LV7008891944/20260401_A23JH5FLT4/v1.0.8/<hash>/)"
    )
    parser.add_argument(
    "--delete",
    action="store_true",
    help="Delete records for the given --librootfolder instead of uploading them",
)
    parser.add_argument("--host",     default="localhost")
    parser.add_argument("--port",     type=int, default=5432)
    parser.add_argument("--dbname",   required=True)
    parser.add_argument("--user",     required=True)
    parser.add_argument("--password", default="")
    parser.add_argument(
    "--include-per-tile-quality",
    action="store_true",
    help="Include parsing/uploading the FastQC Per tile sequence quality module",
)

    args = parser.parse_args()

    conn = psycopg2.connect(
        host=args.host, port=args.port,
        dbname=args.dbname, user=args.user, password=args.password,
        options=f"-c search_path=qc",
    )

    try:
        loader = QCDatabaseLoader(conn)
        if args.delete:

            meta = extract_root_path_metadata(args.librootfolder)

            if validate_root_metadata(meta, args.librootfolder):
                loader.delete_metadata_record(
                    library_id=meta["library_id"],
                    flowcell_id=meta["flowcell_id"],
                    pipeline_version=meta["pipeline_version"],
                    pipeline_hash=meta["pipeline_hash"],
                )
        else:
            mother(
    conn,
    args.librootfolder,
    include_per_tile_quality=args.include_per_tile_quality,
)
    except Exception:
        log.exception("Fatal error during processing")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
