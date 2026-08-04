
```mermaid
erDiagram
    POOL ||--|{ FLOWCELL_LANE : "is sequenced on"
    FLOWCELL ||--|{ FLOWCELL_LANE : "contains"

    POOL ||--|{ LIBRARY_POOLING : "is produced by"
    LIBRARY ||--|{ LIBRARY_POOLING : "is used in"

    LIBRARY ||--|{ SEQUENCING : "is sequencing by"
    FLOWCELL_LANE ||--|{ SEQUENCING : "is used in"

    SEQUENCING ||--|{ RAW_FASTQ_FILE : "produces"

    PIPELINE ||--|{ PIPELINE_RUN : "executes / is executed by"

    PIPELINE_RUN ||--|{ PIPELINE_MODULE : "executes / is executed by"
    PIPELINE_RUN }|--|| CONFIG : "is configured by / configures"
    
    RAW_FASTQ_FILE ||--|| RESULT_FILE : "is"
    
    RESULT_FILE ||--|{ FILE_PROCESSING : "output for"
    RESULT_FILE ||--|{ FILE_PROCESSING : "input to"


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
        string lane "1,2,3,4.. collapsed"
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

    RESULT_FILE {
        int file_id PK
        string path UK
        string produced_by FK "e.g sequencing, trimming, merge_lanes"
        string read_type "e.g. collapsed, singleton, R1, R2, discarded, collapsedtruncated"
    }

    MODULE_EXECUTION {
        string pipeline PK, FK
        string module PK, FK
    }

    PIPELINE_MODULE {
        string name PK "e.g derep, taxon_prefilter, prefilter"
    }

    PIPELINE_TOOLS {
        string name PK "e.g. seqkit, merge_lanes"
    }

    TOOL_EXECUTION {
        string tool PK, FK
        string module PK, FK
    }

    FILE_PROCESSING {
        string tool_execution PK, FK
        string input_file PK, FK
        string output_file PK, FK
    }



```

NOTE: A pipeline is defined by a run of a single file. However a subprocess
More normalization: A general process table that can keep information of everything that has one or more inputs and produces one or more outputs. Inp