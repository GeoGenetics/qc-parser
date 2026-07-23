# Current `uploaded_data_next` and proposed `qc_next` model

This diagram represents the populated `uploaded_data_next` schema and the
core `qc_next` model proposed in `sql/003_create_qc_next_core.sql`.

```mermaid
erDiagram
    LIBRARY {
        citext library_id PK
        timestamptz created_at
    }

    FLOWCELL {
        citext flowcell_id PK
        date sequencing_date
        citext flowcell_position
        citext sequencing_machine
        text sequencing_run_number
        text sequencing_run_id
    }

    FLOWCELL_LANE {
        bigint flowcell_lane_id PK
        citext flowcell_id FK
        smallint lane_number
    }

    LIBRARY_LANE_ASSIGNMENT {
        bigint assignment_id PK
        citext library_id FK
        bigint flowcell_lane_id FK
    }

    PIPELINE_VERSION {
        bigint pipeline_version_id PK
        text version UK
        text code_commit
        text container_digest
    }

    PIPELINE_CONFIG {
        bigint pipeline_config_id PK
        text pipeline_hash UK
        text hash_algorithm
        jsonb config
    }

    PROCESSING_RUN {
        bigint processing_run_id PK
        citext library_id FK
        bigint pipeline_version_id FK
        bigint pipeline_config_id FK
        integer attempt_number
        text status
        text run_path UK
        timestamptz started_at
        timestamptz completed_at
    }

    FILE_ARTIFACT {
        bigint artifact_id PK
        citext library_id FK
        bigint produced_by_processing_run_id FK
        text artifact_type
        text data_stage
        text read_role
        text file_path UK
        text checksum
    }

    PROCESSING_RUN_INPUT {
        bigint processing_run_id PK,FK
        bigint artifact_id PK,FK
        citext library_id FK
    }

    ARTIFACT_LANE_INPUT {
        bigint artifact_id PK,FK
        bigint assignment_id PK,FK
        citext library_id FK
    }

    LIBRARY ||--o{ LIBRARY_LANE_ASSIGNMENT : "is assigned to"
    FLOWCELL ||--|{ FLOWCELL_LANE : contains
    FLOWCELL_LANE ||--o{ LIBRARY_LANE_ASSIGNMENT : sequences

    LIBRARY ||--o{ PROCESSING_RUN : processed_by
    PIPELINE_VERSION ||--o{ PROCESSING_RUN : uses
    PIPELINE_CONFIG ||--o{ PROCESSING_RUN : uses

    LIBRARY ||--o{ FILE_ARTIFACT : owns
    PROCESSING_RUN o|--o{ FILE_ARTIFACT : produces

    PROCESSING_RUN ||--o{ PROCESSING_RUN_INPUT : has
    FILE_ARTIFACT ||--o{ PROCESSING_RUN_INPUT : consumed_as

    FILE_ARTIFACT ||--o{ ARTIFACT_LANE_INPUT : derived_from
    LIBRARY_LANE_ASSIGNMENT ||--o{ ARTIFACT_LANE_INPUT : contributes_to
```

