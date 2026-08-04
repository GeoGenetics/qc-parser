# 5. Independent pipeline version and configuration model

This model treats pipeline version and pipeline configuration as independent dimensions of a processing run. This is the recommended implementation-oriented model.

```mermaid
erDiagram
    LIBRARY ||--o{ POOL_MEMBERSHIP : participates_in
    LIBRARY_POOL ||--|{ POOL_MEMBERSHIP : contains

    FLOWCELL ||--|{ FLOWCELL_LANE : contains
    LIBRARY_POOL ||--|{ FLOWCELL_LANE : sequenced_on

    FLOWCELL_LANE ||--o{ LIBRARY_SEQUENCE_DATASET : produces
    POOL_MEMBERSHIP ||--o{ LIBRARY_SEQUENCE_DATASET : demultiplexes_to

    LIBRARY_SEQUENCE_DATASET ||--o{ PROCESSING_RUN : processed_in
    PIPELINE_VERSION ||--o{ PROCESSING_RUN : uses_version
    PIPELINE_CONFIG ||--o{ PROCESSING_RUN : uses_config

    PROCESSING_RUN ||--o| FASTQC_STATS : produces
    PROCESSING_RUN ||--o| SAMTOOLS_STATS : produces
    PROCESSING_RUN ||--o| BBDUK_LOW_COMPLEXITY : produces
    PROCESSING_RUN ||--o| NON_PAREIL : produces
    PROCESSING_RUN ||--o| DEREPLICATION_RESULT : produces
```

```mermaid
flowchart LR
    D["Sequence dataset"] --> R["Processing run"]
    V["Pipeline version"] --> R
    C["Pipeline configuration"] --> R
    R --> Q["QC results"]
```

Conceptually:

```text
Processing run =
    Sequence dataset
    × Pipeline version
    × Pipeline configuration
```

