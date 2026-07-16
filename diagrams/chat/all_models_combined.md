# DNA lab workflow Mermaid models


# High-level sequencing model

```mermaid
flowchart TD
    RUN[Sequencing run]
    FC[Flowcell]
    LANE[Flowcell lane]
    LIB[Library]
    LLS[Library-lane sequencing]
    FASTQ[Raw FASTQ file]

    RUN -->|contains one or more| FC
    FC -->|contains one or more| LANE

    LIB -->|participates in| LLS
    LANE -->|participates in| LLS

    LLS -->|generates one or two| FASTQ
```


---


# Library-lane many-to-many relationship

```mermaid
erDiagram
    LIBRARY ||--o{ LIBRARY_LANE_SEQUENCING : "is sequenced through"
    FLOWCELL_LANE ||--o{ LIBRARY_LANE_SEQUENCING : "contains library"

    LIBRARY {
        text library_id PK
    }

    FLOWCELL_LANE {
        bigint flowcell_lane_id PK
        bigint flowcell_id FK
        smallint lane_number
    }

    LIBRARY_LANE_SEQUENCING {
        bigint library_lane_sequencing_id PK
        text library_id FK
        bigint flowcell_lane_id FK
        text index_i7
        text index_i5
    }
```


---


# Sequencing and raw FASTQ model

```mermaid
erDiagram
    SEQUENCING_RUN ||--o{ FLOWCELL : contains
    FLOWCELL ||--|{ FLOWCELL_LANE : contains

    LIBRARY ||--o{ LIBRARY_LANE_SEQUENCING : "is sequenced through"
    FLOWCELL_LANE ||--o{ LIBRARY_LANE_SEQUENCING : "sequences"

    LIBRARY_LANE_SEQUENCING ||--|{ RAW_FASTQ_FILE : generates

    SEQUENCING_RUN {
        bigint sequencing_run_id PK
        text run_name UK
        date sequencing_date
        text read_layout
        integer read1_cycles
        integer read2_cycles
    }

    FLOWCELL {
        bigint flowcell_id PK
        bigint sequencing_run_id FK
        text flowcell_barcode UK
    }

    FLOWCELL_LANE {
        bigint flowcell_lane_id PK
        bigint flowcell_id FK
        smallint lane_number
    }

    LIBRARY {
        text library_id PK
    }

    LIBRARY_LANE_SEQUENCING {
        bigint library_lane_sequencing_id PK
        text library_id FK
        bigint flowcell_lane_id FK
        text index_i7
        text index_i5
    }

    RAW_FASTQ_FILE {
        bigint raw_fastq_file_id PK
        bigint library_lane_sequencing_id FK
        smallint read_number
        integer chunk_number
        text file_path
        bigint file_size_bytes
        text checksum_sha256
        timestamp created_at
    }
```


---


# FASTQ generation by sequencing method

```mermaid
flowchart LR
    LLS[Library-lane sequencing]

    METHOD{Read layout}

    R1[Read 1 FASTQ<br/>R1.fastq.gz]
    R2[Read 2 FASTQ<br/>R2.fastq.gz]

    LLS --> METHOD

    METHOD -->|Single-end| R1
    METHOD -->|Paired-end| R1
    METHOD -->|Paired-end| R2
```


---


# Independent pipeline version and configuration model

```mermaid
erDiagram
    PIPELINE ||--|{ PIPELINE_VERSION : has
    PIPELINE ||--|{ PIPELINE_CONFIG : has

    PIPELINE_VERSION ||--o{ PIPELINE_EXECUTION : "selected for"
    PIPELINE_CONFIG ||--o{ PIPELINE_EXECUTION : "selected for"

    PIPELINE {
        bigint pipeline_id PK
        text pipeline_name UK
    }

    PIPELINE_VERSION {
        bigint pipeline_id PK, FK
        text version PK
        text git_commit
        text container_digest
    }

    PIPELINE_CONFIG {
        bigint pipeline_id PK, FK
        text pipeline_hash PK
        text config_content
        text hash_algorithm
    }

    PIPELINE_EXECUTION {
        bigint pipeline_execution_id PK
        bigint pipeline_id FK
        text version FK
        text pipeline_hash FK
        timestamp started_at
        timestamp finished_at
        text status
    }
```

```mermaid
flowchart LR
    V1[Pipeline version 1.0.8]
    V2[Pipeline version 1.0.9]

    C1[Configuration hash AAA]
    C2[Configuration hash BBB]
    C3[Configuration hash CCC]

    E1[Execution]
    E2[Execution]
    E3[Execution]
    E4[Execution]

    V1 --> E1
    C1 --> E1

    V1 --> E2
    C2 --> E2

    V2 --> E3
    C1 --> E3

    V2 --> E4
    C3 --> E4
```


---


# Pipeline input many-to-many relationship

```mermaid
erDiagram
    RAW_FASTQ_FILE ||--o{ PIPELINE_EXECUTION_INPUT : "is input to"
    PIPELINE_EXECUTION ||--|{ PIPELINE_EXECUTION_INPUT : consumes

    RAW_FASTQ_FILE {
        bigint raw_fastq_file_id PK
        bigint library_lane_sequencing_id FK
        smallint read_number
        integer chunk_number
        text file_path
    }

    PIPELINE_EXECUTION {
        bigint pipeline_execution_id PK
        bigint pipeline_id FK
        text version FK
        text pipeline_hash FK
        text status
    }

    PIPELINE_EXECUTION_INPUT {
        bigint pipeline_execution_id PK, FK
        bigint raw_fastq_file_id PK, FK
    }
```


---


# Complete normalized entity-relationship model

```mermaid
erDiagram
    LIBRARY {
        text library_id PK
    }

    SEQUENCING_RUN {
        bigint sequencing_run_id PK
        text run_name UK
        date sequencing_date
        text read_layout
        integer read1_cycles
        integer read2_cycles
    }

    FLOWCELL {
        bigint flowcell_id PK
        bigint sequencing_run_id FK
        text flowcell_barcode UK
    }

    FLOWCELL_LANE {
        bigint flowcell_lane_id PK
        bigint flowcell_id FK
        smallint lane_number
    }

    LIBRARY_LANE_SEQUENCING {
        bigint library_lane_sequencing_id PK
        text library_id FK
        bigint flowcell_lane_id FK
        text index_i7
        text index_i5
    }

    RAW_FASTQ_FILE {
        bigint raw_fastq_file_id PK
        bigint library_lane_sequencing_id FK
        smallint read_number
        integer chunk_number
        text file_path
        bigint file_size_bytes
        text checksum_sha256
        timestamp created_at
    }

    PIPELINE {
        bigint pipeline_id PK
        text pipeline_name UK
    }

    PIPELINE_VERSION {
        bigint pipeline_id PK, FK
        text version PK
        text git_commit
        text container_digest
    }

    PIPELINE_CONFIG {
        bigint pipeline_id PK, FK
        text pipeline_hash PK
        text config_content
        text hash_algorithm
    }

    PIPELINE_EXECUTION {
        bigint pipeline_execution_id PK
        bigint pipeline_id FK
        text version FK
        text pipeline_hash FK
        timestamp started_at
        timestamp finished_at
        text status
        text execution_host
        text working_directory
    }

    PIPELINE_EXECUTION_INPUT {
        bigint pipeline_execution_id PK, FK
        bigint raw_fastq_file_id PK, FK
    }

    PIPELINE_OUTPUT_FILE {
        bigint pipeline_output_file_id PK
        bigint pipeline_execution_id FK
        text output_type
        text file_path
        bigint file_size_bytes
        text checksum_sha256
        timestamp created_at
    }

    SEQUENCING_RUN ||--o{ FLOWCELL : contains
    FLOWCELL ||--|{ FLOWCELL_LANE : contains

    LIBRARY ||--o{ LIBRARY_LANE_SEQUENCING : "is sequenced through"
    FLOWCELL_LANE ||--o{ LIBRARY_LANE_SEQUENCING : sequences

    LIBRARY_LANE_SEQUENCING ||--|{ RAW_FASTQ_FILE : generates

    PIPELINE ||--|{ PIPELINE_VERSION : has
    PIPELINE ||--|{ PIPELINE_CONFIG : has

    PIPELINE_VERSION ||--o{ PIPELINE_EXECUTION : "is used by"
    PIPELINE_CONFIG ||--o{ PIPELINE_EXECUTION : "is used by"

    PIPELINE_EXECUTION ||--|{ PIPELINE_EXECUTION_INPUT : consumes
    RAW_FASTQ_FILE ||--o{ PIPELINE_EXECUTION_INPUT : "is input to"

    PIPELINE_EXECUTION ||--o{ PIPELINE_OUTPUT_FILE : generates
```


---


# Complete end-to-end data lineage

```mermaid
flowchart LR
    RUN[Sequencing run]
    FC[Flowcell]
    LANE[Flowcell lane]
    LIB[DNA library]

    LLS[Library-lane sequencing]

    R1[R1 FASTQ]
    R2[R2 FASTQ]

    PIPE[Pipeline]
    VER[Pipeline version]
    CFG[Pipeline configuration<br/>pipeline_hash]

    EXEC[Pipeline execution]
    INPUT[Execution input association]
    OUTPUT[Pipeline output file]

    RUN --> FC
    FC --> LANE

    LIB --> LLS
    LANE --> LLS

    LLS --> R1
    LLS -. paired-end only .-> R2

    PIPE --> VER
    PIPE --> CFG

    VER --> EXEC
    CFG --> EXEC

    R1 --> INPUT
    R2 -. paired-end input .-> INPUT
    INPUT --> EXEC

    EXEC --> OUTPUT
```


---


# Compact provenance model

```mermaid
flowchart LR
    LIB[Library]
    PLACEMENT[Library sequenced on lane]
    RAW[Raw FASTQ file]
    EXEC[Pipeline execution]
    RESULT[Pipeline output]

    LIB --> PLACEMENT
    PLACEMENT --> RAW
    RAW --> EXEC
    EXEC --> RESULT
```


---


# Paired-end library sequenced on eight lanes

```mermaid
flowchart LR
    LIB[Library LIB001]

    L1[Flowcell A<br/>Lane 1]
    L2[Flowcell A<br/>Lane 2]
    L3[Flowcell A<br/>Lane 3]
    L4[Flowcell A<br/>Lane 4]
    L5[Flowcell B<br/>Lane 1]
    L6[Flowcell B<br/>Lane 2]
    L7[Flowcell B<br/>Lane 3]
    L8[Flowcell B<br/>Lane 4]

    LIB --> L1
    LIB --> L2
    LIB --> L3
    LIB --> L4
    LIB --> L5
    LIB --> L6
    LIB --> L7
    LIB --> L8

    L1 --> L1R1[Lane 1 R1]
    L1 --> L1R2[Lane 1 R2]

    L2 --> L2R1[Lane 2 R1]
    L2 --> L2R2[Lane 2 R2]

    L3 --> L3R1[Lane 3 R1]
    L3 --> L3R2[Lane 3 R2]

    L4 --> L4R1[Lane 4 R1]
    L4 --> L4R2[Lane 4 R2]

    L5 --> L5R1[Lane 5 R1]
    L5 --> L5R2[Lane 5 R2]

    L6 --> L6R1[Lane 6 R1]
    L6 --> L6R2[Lane 6 R2]

    L7 --> L7R1[Lane 7 R1]
    L7 --> L7R2[Lane 7 R2]

    L8 --> L8R1[Lane 8 R1]
    L8 --> L8R2[Lane 8 R2]
```


---


# Paired-end eight-lane file count

```mermaid
flowchart TD
    LIB[One paired-end library]

    LANES[8 library-lane sequencing records]

    R1[8 R1 FASTQ files]
    R2[8 R2 FASTQ files]

    TOTAL[16 raw FASTQ files]

    LIB --> LANES
    LANES --> R1
    LANES --> R2

    R1 --> TOTAL
    R2 --> TOTAL
```


---


# Processing each lane independently

```mermaid
flowchart LR
    L1R1[Lane 1 R1]
    L1R2[Lane 1 R2]
    L2R1[Lane 2 R1]
    L2R2[Lane 2 R2]

    V[Pipeline version]
    C[Pipeline configuration]

    E1[Lane 1 pipeline execution]
    E2[Lane 2 pipeline execution]

    O1[Lane 1 outputs]
    O2[Lane 2 outputs]

    L1R1 --> E1
    L1R2 --> E1

    L2R1 --> E2
    L2R2 --> E2

    V --> E1
    C --> E1

    V --> E2
    C --> E2

    E1 --> O1
    E2 --> O2
```


---


# Processing all lanes together

```mermaid
flowchart LR
    L1[Lane 1 R1 and R2]
    L2[Lane 2 R1 and R2]
    L3[Lane 3 R1 and R2]
    MORE[...]
    L8[Lane 8 R1 and R2]

    V[Pipeline version]
    C[Pipeline configuration]

    EXEC[Library-level pipeline execution]
    OUT[Combined pipeline outputs]

    L1 --> EXEC
    L2 --> EXEC
    L3 --> EXEC
    MORE --> EXEC
    L8 --> EXEC

    V --> EXEC
    C --> EXEC

    EXEC --> OUT
```


---


# Same FASTQ files processed multiple ways

```mermaid
flowchart LR
    FASTQ[16 FASTQ files<br/>for LIB001]

    V1[Version 1.0.8]
    V2[Version 1.0.9]

    C1[Config hash AAA]
    C2[Config hash BBB]

    E1[Execution 1]
    E2[Execution 2]
    E3[Execution 3]

    FASTQ --> E1
    FASTQ --> E2
    FASTQ --> E3

    V1 --> E1
    C1 --> E1

    V1 --> E2
    C2 --> E2

    V2 --> E3
    C1 --> E3

    E1 --> O1[Output set 1]
    E2 --> O2[Output set 2]
    E3 --> O3[Output set 3]
```


---
