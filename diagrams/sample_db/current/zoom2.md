```mermaid
---
config:
  layout: elk
  er:
    layoutDirection: LR
    entityPadding: 8
    diagramPadding: 15
    useMaxWidth: false
---
erDiagram
    FIELD_SAMPLE {
        citext field_sample_id PK
        citext field_sample_parent_id FK
    }

    EDNA_ARCHIVE_SAMPLE {
        citext archive_sample_id PK
        citext field_sample_id FK
    }

    EDNA_ROBOT_SAMPLE {
        citext robot_sample_id PK
        citext archive_sample_id FK
    }

    MASTER_DEPTH {
        citext depth_id PK
        citext archive_sample_id FK
    }

    AGE_DEPTH_MODEL {
        citext depth_id FK
    }

    EDNA_WETLAB_REPORT {
        citext edna_id
        citext robot_sample_id
        citext archive_sample_id
        citext fastq_file_id
    }

    FLOWCELL {
        citext flowcell_id
        citext fastq_file_id
    }

    FIELD_SAMPLE ||--o{ FIELD_SAMPLE : "field_sample_parent_id"
    FIELD_SAMPLE ||--o{ EDNA_ARCHIVE_SAMPLE : "field_sample_id"
    EDNA_ARCHIVE_SAMPLE ||--o{ EDNA_ROBOT_SAMPLE : "archive_sample_id"
    EDNA_ARCHIVE_SAMPLE ||--o{ MASTER_DEPTH : "archive_sample_id"
    MASTER_DEPTH ||--o{ AGE_DEPTH_MODEL : "depth_id"
```