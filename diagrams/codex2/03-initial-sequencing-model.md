# 3. Initial sequencing and processing model

This version models the many-to-many relationship between libraries and flowcells before pooling was introduced. It was superseded by the pool and lane model.

```mermaid
erDiagram
    LIBRARY ||--o{ SEQUENCING_UNIT : participates_in
    FLOWCELL ||--o{ SEQUENCING_UNIT : used_by

    SEQUENCING_UNIT ||--o{ SEQUENCE_DATASET : produces

    SEQUENCE_DATASET ||--o{ PROCESSING_RUN : processed_in
    PIPELINE_RELEASE ||--o{ PROCESSING_RUN : used_by

    PROCESSING_RUN ||--o| FASTQC_STATS : produces
    PROCESSING_RUN ||--o| SAMTOOLS_STATS : produces
    PROCESSING_RUN ||--o| BBDUK_LOW_COMPLEXITY : produces
    PROCESSING_RUN ||--o| NON_PAREIL : produces
    PROCESSING_RUN ||--o| DEREPLICATION_RESULT : produces
```

