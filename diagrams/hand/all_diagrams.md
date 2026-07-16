# All Mermaid ERD diagrams

## 1. Library, flowcell lane, sequencing read, and FASTQ file

```mermaid
erDiagram
    POOL ||--|{ FLOWCELL_LANE : "is sequenced on"

    LIBRARY ||--|{ LIBRARY_FLOWCELL_LANE : "has"
    FLOWCELL_LANE ||--|{ LIBRARY_FLOWCELL_LANE : "contains"

    LIBRARY_FLOWCELL_LANE ||--|{ SEQUENCING_READ : "produces"
    SEQUENCING_READ ||--|| FASTQ_FILE : "is stored as"

    LIBRARY {
        string library_id PK
    }

    POOL {
        string pool_id PK
    }

    FLOWCELL_LANE {
        string flowcell_lane_id PK
        string pool_id FK
    }

    LIBRARY_FLOWCELL_LANE {
        string library_id PK, FK
        string flowcell_lane_id PK, FK
    }

    SEQUENCING_READ {
        string sequencing_read_id PK
        string library_id FK
        string flowcell_lane_id FK
        string read_direction "R1 or R2"
    }

    FASTQ_FILE {
        string fastq_file_id PK
        string sequencing_read_id FK
        string file_path
    }
```

## 2. File, process, and output file — conceptual model

```mermaid
erDiagram
    FILE }|--|{ PROCESS : "is input to"
    PROCESS }|--|{ OUTPUT_FILE : "produces"

    FILE {
        string file_id PK
    }

    PROCESS {
        string process_id PK
    }

    OUTPUT_FILE {
        string output_file_id PK
    }
```

## 3. File, process, and output file — relational implementation

```mermaid
erDiagram
    FILE ||--|{ PROCESS_INPUT : "is used as"
    PROCESS ||--|{ PROCESS_INPUT : "receives"

    PROCESS ||--|{ PROCESS_OUTPUT : "generates"
    OUTPUT_FILE ||--|{ PROCESS_OUTPUT : "is registered as"

    FILE {
        string file_id PK
    }

    PROCESS {
        string process_id PK
    }

    OUTPUT_FILE {
        string output_file_id PK
    }

    PROCESS_INPUT {
        string process_id PK, FK
        string file_id PK, FK
    }

    PROCESS_OUTPUT {
        string process_id PK, FK
        string output_file_id PK, FK
    }
```

## 4. Pipeline execution and subprocesses

```mermaid
erDiagram
    PIPELINE ||--|{ PIPELINE_EXECUTION : "is executed as"

    FILE }|--|{ PIPELINE_EXECUTION : "is input to"

    PIPELINE_EXECUTION ||--|{ SUBPROCESS : "contains"

    SUBPROCESS }|--|{ OUTPUT_FILE : "produces"

    PIPELINE {
        string pipeline_id PK
    }

    PIPELINE_EXECUTION {
        string pipeline_execution_id PK
        string pipeline_id FK
    }

    FILE {
        string file_id PK
    }

    SUBPROCESS {
        string subprocess_id PK
        string pipeline_execution_id FK
    }

    OUTPUT_FILE {
        string output_file_id PK
    }
```

## 5. Pipeline input and output files

```mermaid
erDiagram
    FILE }|--|{ PIPELINE : "is input to"
    PIPELINE ||--|{ OUTPUT_FILE : "produces"

    FILE {
        string file_id PK
    }

    PIPELINE {
        string pipeline_id PK
    }

    OUTPUT_FILE {
        string output_file_id PK
        string pipeline_id FK
    }
```

## 6. Library, pool, flowcell lane, and file

```mermaid
erDiagram
    LIBRARY ||--|{ FILE : "has"

    LIBRARY }|--|{ POOL : "is included in"

    POOL ||--|{ FLOWCELL_LANE : "is sequenced on"

    FLOWCELL ||--|{ FLOWCELL_LANE : "contains"

    LIBRARY {
        string library_id PK
    }

    FILE {
        string file_id PK
        string library_id FK
    }

    POOL {
        string pool_id PK
    }

    FLOWCELL {
        string flowcell_id PK
    }

    FLOWCELL_LANE {
        string flowcell_lane_id PK
        string flowcell_id FK
        string pool_id FK
    }
```
