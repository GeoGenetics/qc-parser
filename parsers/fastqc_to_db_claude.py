import io
import re
import glob
import logging
import argparse
import zipfile
from datetime import datetime
from pathlib import Path

import psycopg2
from psycopg2.extras import execute_values

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Path metadata extraction
# ---------------------------------------------------------------------------

def extract_path_metadata(zip_path: str) -> dict:
    """
    Expected structure:
    /datasets/caeg_production/libraires/lv7/008/003/{libid}/{date}_{fc}/{version}/{hash}/
        stats/reads/fastqc/{data_type}/{filename}_fastqc.zip

    parts[0]  = '/'
    parts[1]  = 'datasets'
    parts[2]  = 'caeg_production'
    parts[3]  = 'libraires'
    parts[4]  = 'lv7'    \
    parts[5]  = '008'     } sharding dirs — ignored
    parts[6]  = '003'    /
    parts[7]  = libid
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
            "libid": None, "run_date": None, "flowcell": None,
            "pipeline_version": None, "pipeline_hash": None,
            "data_type": None, "lane": None, "read_type": None
        }

    libid            = parts[7]
    date_fc          = parts[8]
    pipeline_version = parts[9]
    pipeline_hash    = parts[10]
    data_type        = parts[14]
    filename         = parts[15]

    # Split 'date_fc' on the FIRST underscore only,
    # since flowcell IDs can also contain underscores
    date_str, _, flowcell = date_fc.partition("_")
    try:
        run_date = datetime.strptime(date_str, "%Y%m%d").date()
    except ValueError:
        log.warning(f"Could not parse date from '{date_str}' in path: {zip_path}")
        run_date = None

    # Parse filename: Lib_{libid}_{lane}_{read_type}_fastqc.zip
    fname_match = re.match(
        r"^Lib_(?P<lib>[^_]+)_(?:(?P<lane>L\d+)_)?(?P<read_type>R1|R2|collapsed|collapsedtrunc|singleton)_fastqc\.zip$",
        filename
    )
    if fname_match:
        fname_libid = fname_match.group("lib")
        if fname_libid != libid:
            log.warning(
                f"LibID mismatch between path and filename: path={libid}, filename={fname_libid} ({zip_path})"
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
            f"'Lib_{{libid}}_[{{lane}}_]{{read_type}}_fastqc.zip' "
            f"(valid read_type: R1, R2, collapsed, collapsedtrunc, singleton): {filename}"
        )
        lane      = None
        read_type = None

    return {
        "libid":            libid,
        "run_date":         run_date,
        "flowcell":         flowcell,
        "pipeline_version": pipeline_version,
        "pipeline_hash":    pipeline_hash,
        "data_type":        data_type,
        "lane":             lane,
        "read_type":        read_type,
    }


def extract_log_path_metadata(log_path: str) -> dict:
    """
    Expected structure (15 parts):
    /datasets/caeg_production/libraires/lv7/008/003/{libid}/{date}_{fc}/{version}/{hash}/
        logs/reads/low_complexity/{filename}.log

    parts[7]  = libid
    parts[8]  = date_fc   e.g. '20231015_HV3TWDSX7'
    parts[9]  = version   e.g. 'v1.08'
    parts[10] = hash
    parts[14] = filename  e.g. 'Lib_LV7008891944_collapsed.log'
    """
    parts = Path(log_path).parts

    if len(parts) != 15:
        log.warning(f"Log path does not match expected depth (=15, got {len(parts)}): {log_path}")
        return {
            "libid": None, "run_date": None, "flowcell": None,
            "pipeline_version": None, "pipeline_hash": None,
            "read_type": None,
        }

    libid            = parts[7]
    date_fc          = parts[8]
    pipeline_version = parts[9]
    pipeline_hash    = parts[10]
    filename         = parts[14]

    date_str, _, flowcell = date_fc.partition("_")
    try:
        run_date = datetime.strptime(date_str, "%Y%m%d").date()
    except ValueError:
        log.warning(f"Could not parse date from '{date_str}' in path: {log_path}")
        run_date = None

    fname_match = re.match(
        r"^Lib_(?P<lib>[^_]+)_(?:(?P<lane>L\d+)_)?(?P<read_type>R1|R2|collapsed|collapsedtrunc|singleton)\.log$",
        filename,
    )
    if fname_match:
        fname_libid = fname_match.group("lib")
        if fname_libid != libid:
            log.warning(
                f"LibID mismatch between path and filename: path={libid}, filename={fname_libid} ({log_path})"
            )
        read_type = fname_match.group("read_type")
    else:
        log.warning(
            f"Log filename does not follow expected format "
            f"'Lib_{{libid}}_[{{lane}}_]{{read_type}}.log' "
            f"(valid read_type: R1, R2, collapsed, collapsedtrunc, singleton): {filename}"
        )
        read_type = None

    return {
        "libid":            libid,
        "run_date":         run_date,
        "flowcell":         flowcell,
        "pipeline_version": pipeline_version,
        "pipeline_hash":    pipeline_hash,
        "read_type":        read_type,
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


# ---------------------------------------------------------------------------
# Database loading
# ---------------------------------------------------------------------------

def load_to_db(conn, data: dict) -> None:
    bs = data["basic_statistics"]

    with conn.cursor() as cur:

        # Insert file-level record (basic stats + path metadata)
        cur.execute(
    """
    INSERT INTO fastqc_files
    (filename, source_file, file_type, encoding, total_sequences,
     total_bases, poor_quality_sequences, sequence_length, gc_percent,
     libid, run_date, flowcell, pipeline_version, pipeline_hash,
     data_type, lane, read_type, fastqc_version)
VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
    ON CONFLICT (source_file) DO NOTHING
    RETURNING id
    """,
            (
                bs.get("Filename"),
                data["source_file"],
                bs.get("File type"),
                bs.get("Encoding"),
                int(bs["Total Sequences"]) if "Total Sequences" in bs else None,
                bs.get("Total Bases"),
                int(bs["Sequences flagged as poor quality"]) if "Sequences flagged as poor quality" in bs else None,
                bs.get("Sequence length"),
                int(bs["%GC"]) if "%GC" in bs else None,
                data.get("libid"),
                data.get("run_date"),
                data.get("flowcell"),
                data.get("pipeline_version"),
                data.get("pipeline_hash"),
                data.get("data_type"),
                data.get("lane"),
                data.get("read_type"),
                data.get("fastqc_version"),
            ),
        )
        result = cur.fetchone()
        if result is None:
            log.warning(f"Skipping duplicate: {data['source_file']}")
            conn.rollback()
            return
        file_id = result[0]

        # Module statuses
        if data["module_statuses"]:
            execute_values(
                cur,
                "INSERT INTO fastqc_module_status (file_id, module_name, status) VALUES %s",
                [(file_id, k, v) for k, v in data["module_statuses"].items()],
            )

        # Per-base quality
        if data["per_base_quality"]:
            execute_values(
                cur,
                """INSERT INTO fastqc_per_base_quality
                   (file_id, base, mean, median, lower_quartile, upper_quartile,
                    percentile_10, percentile_90) VALUES %s""",
                [(file_id, r["base"], r["mean"], r["median"], r["lower_quartile"],
                  r["upper_quartile"], r["percentile_10"], r["percentile_90"])
                 for r in data["per_base_quality"]],
            )

        # Per-tile quality
        if data["per_tile_quality"]:
            execute_values(
                cur,
                "INSERT INTO fastqc_per_tile_quality (file_id, tile, base, mean) VALUES %s",
                [(file_id, r["tile"], r["base"], r["mean"])
                 for r in data["per_tile_quality"]],
            )

        # Per-sequence quality scores
        if data["per_sequence_quality"]:
            execute_values(
                cur,
                "INSERT INTO fastqc_per_sequence_quality (file_id, quality, count) VALUES %s",
                [(file_id, r["quality"], r["count"])
                 for r in data["per_sequence_quality"]],
            )

        # Per-base sequence content
        if data["per_base_sequence_content"]:
            execute_values(
                cur,
                """INSERT INTO fastqc_per_base_sequence_content
                   (file_id, base, g, a, t, c) VALUES %s""",
                [(file_id, r["base"], r["g"], r["a"], r["t"], r["c"])
                 for r in data["per_base_sequence_content"]],
            )

        # Per-sequence GC content
        if data["per_sequence_gc_content"]:
            execute_values(
                cur,
                """INSERT INTO fastqc_per_sequence_gc_content
                   (file_id, gc_content, count) VALUES %s""",
                [(file_id, r["gc_content"], r["count"])
                 for r in data["per_sequence_gc_content"]],
            )

        # Per-base N content
        if data["per_base_n_content"]:
            execute_values(
                cur,
                "INSERT INTO fastqc_per_base_n_content (file_id, base, n_count) VALUES %s",
                [(file_id, r["base"], r["n_count"])
                 for r in data["per_base_n_content"]],
            )

        # Sequence length distribution
        if data["sequence_length_distribution"]:
            execute_values(
                cur,
                """INSERT INTO fastqc_sequence_length_distribution
                   (file_id, length, count) VALUES %s""",
                [(file_id, r["length"], r["count"])
                 for r in data["sequence_length_distribution"]],
            )

        # Sequence duplication levels
        dup = data["sequence_duplication_levels"]
        if dup["rows"]:
            execute_values(
                cur,
                """INSERT INTO fastqc_sequence_duplication_levels
                   (file_id, total_deduplicated_pct, duplication_level, percentage_of_total)
                   VALUES %s""",
                [(file_id, dup["total_deduplicated_pct"],
                  r["duplication_level"], r["percentage_of_total"])
                 for r in dup["rows"]],
            )

        # Adapter content
        # Overrepresented sequences
        if data["overrepresented_sequences"]:
            execute_values(
                cur,
                """INSERT INTO fastqc_overrepresented_sequences
                   (file_id, sequence, count, percentage, source)
                   VALUES %s""",
                [(file_id, r["sequence"], r["count"], r["percentage"], r["source"])
                 for r in data["overrepresented_sequences"]],
            )

        # Kmer content
        if data["kmer_content"]:
            execute_values(
                cur,
                """INSERT INTO fastqc_kmer_content
                   (file_id, sequence, count, obs_exp_max, obs_exp_max_at)
                   VALUES %s""",
                [(file_id, r["sequence"], r["count"], r["obs_exp_max"], r["obs_exp_max_at"])
                 for r in data["kmer_content"]],
            )

        # Adapter content
        if data["adapter_content"]:
            execute_values(
                cur,
                """INSERT INTO fastqc_adapter_content
                   (file_id, position, illumina_universal, illumina_small_rna_3,
                    illumina_small_rna_5, nextera_transposase, poly_a, poly_g)
                   VALUES %s""",
                [(file_id, r["position"], r["illumina_universal"],
                  r["illumina_small_rna_3"], r["illumina_small_rna_5"],
                  r["nextera_transposase"], r["poly_a"], r["poly_g"])
                 for r in data["adapter_content"]],
            )

    conn.commit()
    log.info(f"Loaded as file_id={file_id}")


def load_bbduk_to_db(conn, data: dict) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO bbduk_low_complexity (
                source_file, libid, run_date, flowcell, pipeline_version, pipeline_hash,
                read_type, bbduk_version, entropy, entropy_window, entropy_k,
                input_reads, input_bases,
                contaminant_reads, contaminant_reads_pct, contaminant_bases, contaminant_bases_pct,
                low_entropy_reads, low_entropy_reads_pct, low_entropy_bases, low_entropy_bases_pct,
                total_removed_reads, total_removed_reads_pct, total_removed_bases, total_removed_bases_pct,
                result_reads, result_reads_pct, result_bases, result_bases_pct,
                processing_time_seconds
            ) VALUES (
                %s,%s,%s,%s,%s,%s,
                %s,%s,%s,%s,%s,
                %s,%s,
                %s,%s,%s,%s,
                %s,%s,%s,%s,
                %s,%s,%s,%s,
                %s,%s,%s,%s,
                %s
            )
            ON CONFLICT (source_file) DO NOTHING
            RETURNING id
            """,
            (
                data["source_file"],
                data.get("libid"),
                data.get("run_date"),
                data.get("flowcell"),
                data.get("pipeline_version"),
                data.get("pipeline_hash"),
                data.get("read_type"),
                data.get("bbduk_version"),
                data.get("entropy"),
                data.get("entropy_window"),
                data.get("entropy_k"),
                data.get("input_reads"),
                data.get("input_bases"),
                data.get("contaminant_reads"),
                data.get("contaminant_reads_pct"),
                data.get("contaminant_bases"),
                data.get("contaminant_bases_pct"),
                data.get("low_entropy_reads"),
                data.get("low_entropy_reads_pct"),
                data.get("low_entropy_bases"),
                data.get("low_entropy_bases_pct"),
                data.get("total_removed_reads"),
                data.get("total_removed_reads_pct"),
                data.get("total_removed_bases"),
                data.get("total_removed_bases_pct"),
                data.get("result_reads"),
                data.get("result_reads_pct"),
                data.get("result_bases"),
                data.get("result_bases_pct"),
                data.get("processing_time_seconds"),
            ),
        )
        result = cur.fetchone()
        if result is None:
            log.warning(f"Skipping duplicate BBDuk log: {data['source_file']}")
            conn.rollback()
            return
        row_id = result[0]

    conn.commit()
    log.info(f"BBDuk log loaded as id={row_id}: {data['source_file']}")


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def mother(conn, librootfolder: str) -> None:
    """
    Orchestrate parsing and loading for all FastQC zip files and BBDuk
    low-complexity log files under a given library root folder.
    """
    # --- FastQC zips ---
    pattern = str(Path(librootfolder) / "stats/reads/fastqc/*/*fastqc.zip")
    files   = glob.glob(pattern, recursive=True)

    if not files:
        log.warning(f"No FastQC zip files found under: {librootfolder}")
    else:
        log.info(f"Found {len(files)} FastQC file(s) under {librootfolder}")

        for zip_path in files:
            log.info(f"Processing FastQC: {zip_path}")
            try:
                # 1. Extract metadata from the path
                meta = extract_path_metadata(zip_path)

                # 2. Parse the file contents
                fh   = open_fastqc_zip(zip_path)
                data = parse_fastqc_file(fh)

                # 3. Merge — path metadata wins on conflict (e.g. libid)
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
                load_to_db(conn, data)

            except StopIteration:
                log.error(f"No fastqc_data.txt found inside zip: {zip_path}")
                conn.rollback()
            except Exception as e:
                log.error(f"Failed to process {zip_path}: {e}")
                conn.rollback()

    # --- BBDuk low-complexity logs ---
    log_pattern = str(Path(librootfolder) / "logs/reads/low_complexity/*.log")
    log_files   = glob.glob(log_pattern)

    if not log_files:
        log.warning(f"No BBDuk low-complexity log files found under: {librootfolder}")
    else:
        log.info(f"Found {len(log_files)} BBDuk log file(s) under {librootfolder}")

        for log_path in log_files:
            log.info(f"Processing BBDuk log: {log_path}")
            try:
                meta = extract_log_path_metadata(log_path)

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

                load_bbduk_to_db(conn, data)

            except Exception as e:
                log.error(f"Failed to process BBDuk log {log_path}: {e}")
                conn.rollback()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Load FastQC zip files into PostgreSQL, "
                    "either from a single library root folder or a glob pattern."
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--librootfolder",
        help="Path to a single library root folder "
             "(e.g. /datasets/caeg_production/libraires/lv7/008/003/libid/date_fc/v1.08/hash/)"
    )
    group.add_argument(
        "--pattern",
        help="Glob pattern to match multiple library root folders "
             "(e.g. '/datasets/caeg_production/libraires/lv7/*/*/*/*/*/*/*/')"
    )
    parser.add_argument("--host",     default="localhost")
    parser.add_argument("--port",     type=int, default=5432)
    parser.add_argument("--dbname",   required=True)
    parser.add_argument("--user",     required=True)
    parser.add_argument("--password", default="")
    args = parser.parse_args()

    conn = psycopg2.connect(
        host=args.host, port=args.port,
        dbname=args.dbname, user=args.user, password=args.password,
    )

    try:
        if args.librootfolder:
            mother(conn, args.librootfolder)
        else:
            folders = glob.glob(args.pattern, recursive=True)
            if not folders:
                log.warning(f"No folders matched pattern: {args.pattern}")
                return
            log.info(f"Found {len(folders)} library root folder(s)")
            for folder in folders:
                mother(conn, folder)
    finally:
        conn.close()


if __name__ == "__main__":
    main()