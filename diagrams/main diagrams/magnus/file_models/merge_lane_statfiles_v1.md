NOTE:
 1. An executor of a tool can either be a binf pipeline or sequencing pipeline. Binf pipeline has its own table because it has specific fields defining it. Seq pipeline does not as far as I am aware.
 2. A file can either be of merge or lane type. Each of these types are slightly different. A merge type references a FLOWCELL, because we only know that it came from multiple lanes of a FLOWCELL and a lane type references a lane because we know which lane it came from. We can figure out which lanes the merge type file is made from by using the POOL_LIBRARY_MAPPING, POOL and LANE tables, but its not that easy. A more natural way would be to make a lane group (see lane_group_v1.md).
```mermaid

---
config:
  layout: elk
  er:
    layoutDirection: LR
    nodeSpacing: 190
    rankSpacing: 130
    entityPadding: 9
    minEntityWidth: 80
    minEntityHeight: 50
    fontSize: 11
    diagramPadding: 20
    useMaxWidth: false
---
erDiagram
    PIPELINE_VERSION ||--|{ PIPELINE : ""
    PIPELINE_CONFIG ||--|{ PIPELINE : ""
    PIPELINE ||--|| EXECUTOR : ""
    EXECUTOR ||--|{ TOOL_EXECUTION : ""
    FILE ||--o| FILE_LANE : ""
    TOOL ||--|{ TOOL_EXECUTION : ""
    FILE ||--o| FILE_MERGE : ""
    LIBRARY ||--|{ POOL_LIBRARY_MAPPING : ""
    LIBRARY ||--o{ FILE : ""
    FILE }|--|| TOOL_EXECUTION : ""
    LANE ||--o{ FILE_LANE : ""
    LANE }|--|| FLOWCELL : ""
    FLOWCELL ||--o{ FILE_MERGE : ""
    LANE }|--|| POOL : ""
    POOL_LIBRARY_MAPPING ||--|| XIHAN : ""
    POOL ||--|{ POOL_LIBRARY_MAPPING : ""
    
    LIBRARY {
        int lv_id PK
        text lv UK
    }

    FLOWCELL {
        int flowcell_id PK
        text flowcell_label UK
    }


    POOL {
        int pool_id PK
        text pool_label UK
    }

    POOL_LIBRARY_MAPPING {
        int plm_id PK
        int pool_id FK 
        int lv_id FK      
}

    PIPELINE_VERSION {
        int pv_id PK
        text pv UK
    }

    PIPELINE_CONFIG {
        int config_id PK
        text config_hash UK
        json config
    }

    PIPELINE {
        int executor_id PK, FK
        int config_id FK
        int pv_id FK
    }

    EXECUTOR {
        int executor_id PK
        string executor_name "binf_pipeline OR demux"
    }

    TOOL {
        int tool_id PK
        string tool_name UK
        string tool_version UK
        string tool_category 
    }

    TOOL_EXECUTION {
        int execution_id PK
        int executor_id FK
        int tool_id FK
    }

    FILE {
        int file_id PK
        int lv_id FK
        string read_type "R1, R2, collapsed, singleton"  
        int execution_id FK
    }

    FILE_MERGE {
        int file_id PK, FK
        int flowcell_id FK
    }

    FILE_LANE {
        int file_id PK, FK
        int lane_id FK
    }


    LANE {
        int lane_id PK
        int flowcell_id FK
        int pool_id FK
    }

  






```
