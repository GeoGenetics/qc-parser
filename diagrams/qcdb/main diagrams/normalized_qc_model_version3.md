# Normalized `qc` model proposal

This proposal starts from the repeated identifying columns found across the
current schema:

- `library_id`
- `flowcell_id`
- `lane`
- `pipeline_version`
- `pipeline_hash`

The core normalization idea is to lift those columns into one shared parent
entity and let downstream QC result tables reference that parent by a single
surrogate key.

## 1. New shared key

Create one parent table that represents the exact processing context for a QC
result row.

### `qc_run`

```text
qc_run_id          bigint PK
library_id         varchar not null
flowcell_id        varchar not null
lane               varchar not null
pipeline_version   varchar not null
pipeline_hash      text    not null

UNIQUE (library_id, flowcell_id, lane, pipeline_version, pipeline_hash)
```

This gives us one stable key:

```text
qc_run_id
```

instead of repeating the five-column natural key in many child tables.

## 2. Recommended parent hierarchy

The repeated columns actually mix two different concepts:

1. the library/run identity
2. the pipeline execution identity

So the cleanest normalized design is a small hierarchy instead of only one
table.

### `libid`

```text
libid_id           bigint PK
libid              varchar not null unique
```

This table is intentionally minimal: one surrogate key and one business key.

### `flowcell`

```text
flowcell_id        bigint PK
flowcell_name      varchar not null unique
flowcell_type      varchar not null
layout_type        varchar not null
cycle_count        integer not null
```

Suggested meaning:

- `flowcell_name`: the actual flowcell identifier
- `flowcell_type`: for example `S1`, `S2`, `S4`
- `layout_type`: `PE` or `SE`
- `cycle_count`: total sequencing cycles

Suggested constraints:

```text
CHECK (layout_type IN ('PE', 'SE'))
CHECK (cycle_count > 0)
```

### `seq_run`

This table represents a sequencing instrument run.

```text
seq_run_id         bigint PK
seqmachine         varchar not null
runnr              varchar not null
flowcell_name      varchar not null FK -> flowcell.flowcell_name
run_date           date    not null
```

Suggested meaning:

- `seqmachine`: sequencing instrument identifier or name
- `runnr`: run number from the instrument
- `flowcell_name`: flowcell identifier recorded for the sequencing run
- `run_date`: date of the sequencing run

### `pipeline`

This should stay simple unless you later need richer release metadata.

```text
pipeline_id        bigint PK
pipeline_version   varchar not null
pipeline_hash      text    not null

UNIQUE (pipeline_version, pipeline_hash)
```

This means one row per distinct pipeline build, for example:

```text
pipeline_id = 7
pipeline_version = 1.4.2
pipeline_hash = a1b2c3d4
```

That is enough if you expect only a limited number of versions and hashes.

### `qc_run`

```text
qc_run_id          bigint PK
libid_id           bigint not null FK -> libid.libid_id
flowcell_id        bigint not null FK -> flowcell.flowcell_id
pipeline_id        bigint not null FK -> pipeline.pipeline_id
lane               varchar null
lane_scope         varchar not null

UNIQUE (libid_id, flowcell_id, pipeline_id, lane, lane_scope)
```

Suggested constraints:

```text
CHECK (lane_scope IN ('single_lane', 'all_lanes'))
CHECK (
    (lane_scope = 'single_lane' AND lane IS NOT NULL) OR
    (lane_scope = 'all_lanes' AND lane IS NULL)
)
```

This version is more normalized than a single wide parent because:

- libid information lives once
- flowcell metadata lives once
- pipeline information lives once
- the combination between sample context and pipeline is explicit
- the lane semantics are explicit without inventing fake lane values

If you want the smallest possible migration step, you can start with the
single-table `qc_run` design and split it later.

## 3. Where input distinctions belong

Input-specific distinctions should not be forced into `qc_run`.

Recommended rule:

- keep `lane` in `qc_run`, but make it nullable
- add `lane_scope` so we can distinguish single-lane from all-lanes rows
- use `input_type_id` in stats tables to describe whether a run was on
  `rawR1`, `trimPair`, `collapsed`, `bam`, and so on
- use explicit tool-specific stats tables as the target design

The important change from version 2 is this:

- `metrics_json` is no longer the intended end state
- it is only a transitional placeholder if migration has to happen in phases
- the real target is one explicit table per QC tool, with concrete metric
  columns

That keeps `qc_run` stable while still letting the tool-level tables capture
what they actually ran on.

## 4. Suggested normalized result tables

Below is the structural target model.

The main QC tool tables are keyed by `qc_run_id` and `input_type_id`, while
`seq_stats` is a separate parallel track keyed by `seq_run_id` together with
sample- and lane-specific context.

In all cases, the target is explicit metric columns rather than a generic JSON
field.

### `input_type`

```text
input_type_id      bigint PK
input_type_code    varchar not null unique
```

### `seq_stats`

```text
seq_stats_id                   bigint PK
seq_run_id                     bigint not null FK -> seq_run.seq_run_id
lane                           varchar not null
libid_id                       bigint not null FK -> libid.libid_id
index_id                       bigint null
read_count                     bigint null
perfect_index_read_count       bigint null
one_mismatch_index_read_count  bigint null
two_mismatch_index_read_count  bigint null
read_pct                       numeric null
perfect_index_read_pct         numeric null
one_mismatch_index_read_pct    numeric null
two_mismatch_index_read_pct    numeric null
```

Notes:

- `sample_project` is intentionally omitted
- `index_id` is expected to refer to the Xihan index definition, but that
  table is not modeled in this document yet
- `lane` is kept directly in `seq_stats` because the row is lane-specific
- `libid_id` is the normalized replacement for `SampleID`

### `bbduk_stats`

```text
bbduk_stats_id     bigint PK
qc_run_id          bigint not null FK -> qc_run.qc_run_id
input_type_id      bigint not null FK -> input_type.input_type_id

UNIQUE (qc_run_id, input_type_id)
```

Concrete metric columns should live in `bbduk_stats` itself.

### `derep_stats`

```text
derep_stats_id     bigint PK
qc_run_id          bigint not null FK -> qc_run.qc_run_id
input_type_id      bigint not null FK -> input_type.input_type_id

UNIQUE (qc_run_id, input_type_id)
```

Concrete metric columns should live in `derep_stats` itself.

### `nonpareil_stats`

```text
nonpareil_stats_id bigint PK
qc_run_id          bigint not null FK -> qc_run.qc_run_id
input_type_id      bigint not null FK -> input_type.input_type_id

UNIQUE (qc_run_id, input_type_id)
```

Concrete metric columns should live in `nonpareil_stats` itself.

### `samtools_stats`

```text
samtools_stats_id  bigint PK
qc_run_id          bigint not null FK -> qc_run.qc_run_id
input_type_id      bigint not null FK -> input_type.input_type_id

UNIQUE (qc_run_id, input_type_id)
```

Concrete metric columns should live in `samtools_stats` itself.

### `fastqc_stats`

```text
fastqc_stats_id    bigint PK
qc_run_id          bigint not null FK -> qc_run.qc_run_id
input_type_id      bigint not null FK -> input_type.input_type_id

UNIQUE (qc_run_id, input_type_id)
```

The FastQC detail tables stay structurally the same, but continue to reference
only `fastqc_stats_id`.

### `adapter_removal_settings`

```text
adapter_removal_settings_id bigint PK
qc_run_id                   bigint not null FK -> qc_run.qc_run_id
input_type_id               bigint not null FK -> input_type.input_type_id

UNIQUE (qc_run_id, input_type_id)
```

### `adapter_removal_length_distribution`

```text
adapter_removal_length_distribution_id bigint PK
adapter_removal_settings_id            bigint not null
                                       FK -> adapter_removal_settings.adapter_removal_settings_id
length                                 integer not null

UNIQUE (adapter_removal_settings_id, length)
```

## 5. Mermaid sketch

```mermaid
erDiagram
    LIBID {
        bigint libid_id PK
        varchar libid
    }

    FLOWCELL {
        bigint flowcell_id PK
        varchar flowcell_name
        varchar flowcell_type
        varchar layout_type
        integer cycle_count
    }

    PIPELINE {
        bigint pipeline_id PK
        varchar pipeline_version
        text pipeline_hash
    }

    SEQ_RUN {
        bigint seq_run_id PK
        varchar seqmachine
        varchar runnr
        varchar flowcell_name
        date run_date
    }

    QC_RUN {
        bigint qc_run_id PK
        bigint libid_id FK
        bigint flowcell_id FK
        bigint pipeline_id FK
        varchar lane
        varchar lane_scope
    }

    SEQ_STATS {
        bigint seq_stats_id PK
        bigint seq_run_id FK
        varchar lane
        bigint libid_id FK
        bigint index_id
    }

    INPUT_TYPE {
        bigint input_type_id PK
        varchar input_type_code
    }

    FASTQC_STATS {
        bigint fastqc_stats_id PK
        bigint qc_run_id FK
        bigint input_type_id FK
    }

    BBDUK_STATS {
        bigint bbduk_stats_id PK
        bigint qc_run_id FK
        bigint input_type_id FK
    }

    DEREP_STATS {
        bigint derep_stats_id PK
        bigint qc_run_id FK
        bigint input_type_id FK
    }

    NONPAREIL_STATS {
        bigint nonpareil_stats_id PK
        bigint qc_run_id FK
        bigint input_type_id FK
    }

    SAMTOOLS_STATS {
        bigint samtools_stats_id PK
        bigint qc_run_id FK
        bigint input_type_id FK
    }

    ADAPTER_REMOVAL_SETTINGS {
        bigint adapter_removal_settings_id PK
        bigint qc_run_id FK
        bigint input_type_id FK
    }

    ADAPTER_REMOVAL_LENGTH_DISTRIBUTION {
        bigint adapter_removal_length_distribution_id PK
        bigint adapter_removal_settings_id FK
    }

    FASTQC_MODULE_STATUS {
        bigint id PK
        bigint fastqc_stats_id FK
    }

    LIBID ||--o{ QC_RUN : libid_id
    LIBID ||--o{ SEQ_STATS : libid_id
    FLOWCELL ||--o{ QC_RUN : flowcell_id
    FLOWCELL ||--o{ SEQ_RUN : flowcell_name
    SEQ_RUN ||--o{ SEQ_STATS : seq_run_id
    PIPELINE ||--o{ QC_RUN : pipeline_id

    QC_RUN ||--o{ FASTQC_STATS : qc_run_id
    QC_RUN ||--o{ BBDUK_STATS : qc_run_id
    QC_RUN ||--o{ DEREP_STATS : qc_run_id
    QC_RUN ||--o{ NONPAREIL_STATS : qc_run_id
    QC_RUN ||--o{ SAMTOOLS_STATS : qc_run_id
    QC_RUN ||--o{ ADAPTER_REMOVAL_SETTINGS : qc_run_id

    INPUT_TYPE ||--o{ FASTQC_STATS : input_type_id
    INPUT_TYPE ||--o{ BBDUK_STATS : input_type_id
    INPUT_TYPE ||--o{ DEREP_STATS : input_type_id
    INPUT_TYPE ||--o{ NONPAREIL_STATS : input_type_id
    INPUT_TYPE ||--o{ SAMTOOLS_STATS : input_type_id
    INPUT_TYPE ||--o{ ADAPTER_REMOVAL_SETTINGS : input_type_id

    ADAPTER_REMOVAL_SETTINGS ||--o{ ADAPTER_REMOVAL_LENGTH_DISTRIBUTION : adapter_removal_settings_id
    FASTQC_STATS ||--o{ FASTQC_MODULE_STATUS : fastqc_stats_id
```

## 5b. Change overview

This diagram focuses specifically on the structural change:

- before: many QC tables repeat the same identifying columns
- after: those columns move into shared parent tables, while QC tool tables
  point to `qc_run_id` and sequencing-run statistics live in the separate
  `seq_stats` track

```mermaid
flowchart LR
    subgraph BEFORE["Before"]
        OLDKEY["Repeated key columns\nlibrary_id\nflowcell_id\nlane\npipeline_version\npipeline_hash"]
        OLDFASTQC["fastqc_stats"]
        OLDBBDUK["bbduk_stats"]
        OLDDEREP["derep_stats"]
        OLDNONP["nonpareil_stats"]
        OLDSAM["samtools_stats"]
        OLDADAPT["adapter_removal_settings"]

        OLDFASTQC --- OLDKEY
        OLDBBDUK --- OLDKEY
        OLDDEREP --- OLDKEY
        OLDNONP --- OLDKEY
        OLDSAM --- OLDKEY
        OLDADAPT --- OLDKEY
    end

    subgraph AFTER["After"]
        LIB["libid"]
        FC["flowcell"]
        SR["seq_run"]
        PIPE["pipeline"]
        IT["input_type"]
        RUN["qc_run\nqc_run_id"]
        SEQ["seq_stats\nfk: seq_run_id + libid_id"]

        NEWFASTQC["fastqc_stats\nfk: qc_run_id + input_type_id"]
        NEWBBDUK["bbduk_stats\nfk: qc_run_id + input_type_id"]
        NEWDEREP["derep_stats\nfk: qc_run_id + input_type_id"]
        NEWNONP["nonpareil_stats\nfk: qc_run_id + input_type_id"]
        NEWSAM["samtools_stats\nfk: qc_run_id + input_type_id"]
        NEWADAPT["adapter_removal_settings\nfk: qc_run_id + input_type_id"]

        LIB --> RUN
        FC --> RUN
        PIPE --> RUN

        SR --> SEQ
        LIB --> SEQ
        RUN --> NEWFASTQC
        RUN --> NEWBBDUK
        RUN --> NEWDEREP
        RUN --> NEWNONP
        RUN --> NEWSAM
        RUN --> NEWADAPT

        IT --> NEWFASTQC
        IT --> NEWBBDUK
        IT --> NEWDEREP
        IT --> NEWNONP
        IT --> NEWSAM
        IT --> NEWADAPT
    end
```

## 6. Tool-specific stats tables

This section is intentionally not a relationship diagram.

The tables below are shown as standalone boxes with no keys and no lines.
They are included as the concrete metric targets that should replace
`metrics_json` in the final model.

```mermaid
erDiagram
    BBDUK_STATS {
        text bbduk_version
        numeric entropy
        integer entropy_window
        integer entropy_k
        bigint input_reads
        bigint input_bases
        bigint contaminant_reads
        numeric contaminant_reads_pct
        bigint contaminant_bases
        numeric contaminant_bases_pct
        bigint low_entropy_reads
        numeric low_entropy_reads_pct
        bigint low_entropy_bases
        numeric low_entropy_bases_pct
        bigint total_removed_reads
        numeric total_removed_reads_pct
        bigint total_removed_bases
        numeric total_removed_bases_pct
        bigint result_reads
        numeric result_reads_pct
        bigint result_bases
        numeric result_bases_pct
        numeric processing_time_seconds
        text ref
        timestamp_with_time_zone smdb_insert_at
        varchar flowcell_position
    }

    DEREP_STATS {
        bigint duplicated_records_removed
        text source_file
        timestamp_with_time_zone smdb_insert_at
        varchar data_type
    }

    FASTQC_STATS {
        text filename
        text file_type
        text encoding
        bigint total_sequences
        text total_bases
        bigint poor_quality_sequences
        text sequence_length
        integer gc_percent
        text fastqc_version
        timestamp_with_time_zone smdb_insert_at
    }

    NONPAREIL_STATS {
        numeric kappa
        numeric c
        numeric lr
        numeric model_r
        numeric lr_star
        numeric diversity
        text source_file
        timestamp_with_time_zone smdb_insert_at
    }

    SAMTOOLS_STATS {
        text source_file
        text samtools_version
        text command_line
        bigint raw_total_sequences
        bigint filtered_sequences
        bigint sequences
        integer is_sorted
        bigint first_fragments
        bigint last_fragments
        bigint reads_mapped
        bigint reads_mapped_and_paired
        bigint reads_unmapped
        bigint reads_properly_paired
        bigint reads_paired
        bigint reads_duplicated
        bigint reads_mq0
        bigint reads_qc_failed
        bigint non_primary_alignments
        bigint supplementary_alignments
        bigint total_length
        bigint total_first_fragment_length
        bigint total_last_fragment_length
        bigint bases_mapped
        bigint bases_mapped_cigar
        bigint bases_trimmed
        bigint bases_duplicated
        bigint mismatches
        numeric error_rate
        numeric average_length
        numeric average_first_fragment_length
        numeric average_last_fragment_length
        bigint maximum_length
        bigint maximum_first_fragment_length
        bigint maximum_last_fragment_length
        numeric average_quality
        numeric insert_size_average
        numeric insert_size_standard_deviation
        bigint inward_oriented_pairs
        bigint outward_oriented_pairs
        bigint pairs_with_other_orientation
        bigint pairs_on_different_chromosomes
        numeric percentage_of_properly_paired_reads_pct
        timestamp_with_time_zone smdb_insert_at
    }

    ADAPTER_REMOVAL_SETTINGS {
        text source_file
        text adapter_removal_version
        text mode
        text adapter1_1
        text adapter2_1
        text rng_seed
        integer alignment_shift_value
        numeric global_mismatch_threshold
        text quality_format_input
        integer quality_score_max_input
        text quality_format_output
        integer quality_score_max_output
        text mate_number_separator_input
        integer trimming_5p
        integer trimming_3p
        boolean trimming_ns
        boolean trimming_phred_scores_le_2
        boolean trimming_using_sliding_windows
        integer minimum_genomic_length
        bigint maximum_genomic_length
        boolean collapse_overlapping_reads
        boolean deterministic_collapse
        boolean conservative_collapse
        integer minimum_overlap_in_case_of_collapse
        bigint total_number_of_read_pairs
        bigint number_of_unaligned_read_pairs
        bigint number_of_well_aligned_read_pairs
        bigint number_of_discarded_mate_1_reads
        bigint number_of_singleton_mate_1_reads
        bigint number_of_discarded_mate_2_reads
        bigint number_of_singleton_mate_2_reads
        bigint number_of_reads_with_adapters_1
        bigint number_of_full_length_collapsed_pairs
        bigint number_of_truncated_collapsed_pairs
        bigint number_of_retained_reads
        bigint number_of_retained_nucleotides
        numeric average_length_of_retained_reads
    }

    ADAPTER_REMOVAL_LENGTH_DISTRIBUTION {
        bigint mate1
        bigint mate2
        bigint singleton
        bigint collapsed
        bigint collapsed_truncated
        bigint discarded
        bigint all_reads
    }
```

## 7. FastQC detail tables

These remain separate child tables under `fastqc_stats`, but they are shown
here without keys and without relationship lines because the purpose of this
section is only to expose the concrete metric columns.

```mermaid
erDiagram
    FASTQC_ADAPTER_CONTENT {
        numeric illumina_universal
        numeric illumina_small_rna_3
        numeric illumina_small_rna_5
        numeric nextera_transposase
        numeric poly_a
        numeric poly_g
        timestamp_with_time_zone smdb_insert_at
    }

    FASTQC_KMER_CONTENT {
        bigint count
        numeric obs_exp_max
        text obs_exp_max_at
        timestamp_with_time_zone smdb_insert_at
    }

    FASTQC_MODULE_STATUS {
        text status
        timestamp_with_time_zone smdb_insert_at
    }

    FASTQC_OVERREPRESENTED_SEQUENCES {
        bigint count
        numeric percentage
        text source
        timestamp_with_time_zone smdb_insert_at
    }

    FASTQC_PER_BASE_N_CONTENT {
        numeric n_count
        timestamp_with_time_zone smdb_insert_at
    }

    FASTQC_PER_BASE_QUALITY {
        numeric mean
        numeric median
        numeric lower_quartile
        numeric upper_quartile
        numeric percentile_10
        numeric percentile_90
        timestamp_with_time_zone smdb_insert_at
    }

    FASTQC_PER_BASE_SEQUENCE_CONTENT {
        numeric g
        numeric a
        numeric t
        numeric c
        timestamp_with_time_zone smdb_insert_at
    }

    FASTQC_PER_SEQUENCE_GC_CONTENT {
        numeric count
        timestamp_with_time_zone smdb_insert_at
    }

    FASTQC_PER_SEQUENCE_QUALITY {
        numeric count
        timestamp_with_time_zone smdb_insert_at
    }

    FASTQC_PER_TILE_QUALITY {
        numeric mean
        timestamp_with_time_zone smdb_insert_at
    }

    FASTQC_SEQUENCE_DUPLICATION_LEVELS {
        numeric total_deduplicated_pct
        numeric percentage_of_total
        timestamp_with_time_zone smdb_insert_at
    }

    FASTQC_SEQUENCE_LENGTH_DISTRIBUTION {
        numeric count
        timestamp_with_time_zone smdb_insert_at
        double_precision length_midpoint
    }
```
