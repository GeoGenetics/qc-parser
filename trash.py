
def load_to_db(conn, data: dict) -> None:
    bs = data["basic_statistics"]

    with conn.cursor() as cur:

        # Insert file-level record (basic stats + path metadata)
        cur.execute(
    """
    INSERT INTO fastqc_files
    (filename, source_file, file_type, encoding, total_sequences,
     total_bases, poor_quality_sequences, sequence_length, gc_percent,
     library_id, sequencing_date, flowcell_id, pipeline_version, pipeline_hash,
     data_type, lane, read_type, fastqc_version, flowcell_position)
VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
    ON CONFLICT (library_id, flowcell_id, pipeline_version, pipeline_hash) DO NOTHING
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
                data.get("library_id"),
                data.get("sequencing_date"),
                data.get("flowcell_id"),
                data.get("pipeline_version"),
                data.get("pipeline_hash"),
                data.get("data_type"),
                data.get("lane"),
                data.get("read_type"),
                data.get("fastqc_version"),
                data.get("flowcell_position")
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
                source_file, library_id, sequencing_date, flowcell_id, pipeline_version, pipeline_hash,
                read_type, bbduk_version, entropy, entropy_window, entropy_k, ref,
                input_reads, input_bases,
                contaminant_reads, contaminant_reads_pct, contaminant_bases, contaminant_bases_pct,
                low_entropy_reads, low_entropy_reads_pct, low_entropy_bases, low_entropy_bases_pct,
                total_removed_reads, total_removed_reads_pct, total_removed_bases, total_removed_bases_pct,
                result_reads, result_reads_pct, result_bases, result_bases_pct,
                processing_time_seconds
            ) VALUES (
                %s,%s,%s,%s,%s,%s,
                %s,%s,%s,%s,%s,%s,
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
                data.get("library_id"),
                data.get("sequencing_date"),
                data.get("flowcell_id"),
                data.get("pipeline_version"),
                data.get("pipeline_hash"),
                data.get("read_type"),
                data.get("bbduk_version"),
                data.get("entropy"),
                data.get("entropy_window"),
                data.get("entropy_k"),
                data.get("ref"),
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

def load_path_metadata_to_db(conn, data: dict, overwrite: bool = False) -> None:
    with conn.cursor() as cur:

        # Insert file-level record (basic stats + path metadata)
        cur.execute(
    """
    INSERT INTO meta_data
    (source_path, library_id, sequencing_date, flowcell_position, flowcell_id, pipeline_version, pipeline_hash, smdb_upload_uuid)
VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
    ON CONFLICT (source_path) DO NOTHING
    RETURNING id
    """,
            (
                data["source_path"],
                data["library_id"],
                data["sequencing_date"],
                data["flowcell_position"],
                data["flowcell_id"],
                data["pipeline_version"],
                data["pipeline_hash"],
                data["smdb_upload_uuid"]
            ),
        )

        result = cur.fetchone()
        if result is None:
            conn.rollback()
            return None

        meta_data_id = result[0]
            
        if meta_data_id is None:
            log.warning("Skipping duplicate or invalid root metadata")

    conn.commit()

    return meta_data_id
