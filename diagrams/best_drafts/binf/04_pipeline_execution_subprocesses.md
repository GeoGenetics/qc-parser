# Pipeline execution and subprocesses

```mermaid
erDiagram
    PIPELINE ||--|{ PIPELINE_RUN : "executes / is executed by"

    FASTQ_FILE ||--|{ PIPELINE_RUN : ""

    PIPELINE_RUN ||--|{ SUBPROCESS : "executes / is executed by"
    PIPELINE_RUN }|--|| CONFIG : "is configured by / configures"
    

    SUBPROCESS }|--|{ OUTPUT_FILE : "produced / is produced by"

    CONFIG { 
        string config_hash PK
        json config
    }

    PIPELINE {
        string version PK
    }

    PIPELINE_RUN {
        string pipeline_version PK, FK
        string file_id PK, FK
        string config_hash PK, FK
    }

    FASTQ_FILE {
        string file_id PK
    }

    SUBPROCESS {
        string subprocess_id PK
        string pipeline_run_id FK
    }

    OUTPUT_FILE {
        string output_file_id PK
    }
```



Question: Do we want to split up subprocess into specific process tables or keep it abstract?
Not sure if we should make a dataset table? A dataset is  all the fastq IDs from one library. Filipe says that this is what each pipeline run is processing.
