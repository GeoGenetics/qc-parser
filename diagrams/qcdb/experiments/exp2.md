
```mermaid
erDiagram
    POOL ||--|{ FLOWCELL_LANE : "is sequenced on"
    FLOWCELL ||--|{ FLOWCELL_LANE : "contains"

    POOL ||--|{ LIBRARY_POOLING : "is produced by"
    LIBRARY ||--|{ LIBRARY_POOLING : "is used in"

    LIBRARY ||--|{ SEQUENCING : "is sequencing by"
    FLOWCELL_LANE ||--|{ SEQUENCING : "is used in"

    SEQUENCING ||--|| RAW_FASTQ_FILE : "produces"

    PIPELINE ||--|{ PIPELINE_RUN : "executes / is executed by"

    OUTPUT_FILE }|--|| SUBPROCESS : "generates"
    PIPELINE_RUN ||--|{ PIPELINE_MODULE : "executes / is executed by"
    PIPELINE_RUN }|--|| CONFIG : "is configured by / configures"
    


    RAW_FASTQ_FILE ||--|| FILE : ""


    LIBRARY {
        string library_id PK
    }

    POOL {
        string pool_id PK
    }

    FLOWCELL {
        string flowcell_id PK
    }

    FLOWCELL_LANE {
        string flowcell_lane_id PK
        string pool_id FK
        string flowcell_id FK
        string lane
    }

    SEQUENCING {
        string library_id PK, FK
        string flowcell_lane_id PK, FK
    }

    LIBRARY_POOLING {
        string library_id PK
        string pool_id PK
    }

    RAW_FASTQ_FILE {
        int sequencing_id PK, FK
        string sequencing_direction PK "R1 or R2"
    }

    CONFIG { 
        string config_hash PK
        json config
    }

    PIPELINE {
        string version PK
    }

    PIPELINE_RUN {
        string pipeline_version PK, FK
        string config_hash PK, FK
    }

    RESULTS_FILE {
        int file_id PK
        string path UK
        string produced_by FK
        string read_type "e.g. collapsed, singleton, R1, R2"
        string lane "e.g. 1, 2, 3, collapsed"
    }

    FILE_PROCESSING {
        int id PK
        string file_id FK
        string pipeline_module_id FK
        string tool FK
    }

    PIPELINE_MODULE {
        string name PK "e.g derep, taxon_prefilter, prefilter"
    }

    PIPELINE_TOOLS {
        string name PK "e.g. seqkit, merge_lanes"
    }

    PIPELINE_TOOL_EXECUTION {
        string 
    }

    PROCESSED_FASTQ {
        string output_file_id PK

    }



```

NOTE: A pipeline is defined by a run of a single file. However a subprocess 