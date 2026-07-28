NOTE:
 1. An executor of a tool can either be a binf pipeline or sequencing pipeline. Binf pipeline has its own table because it has specific fields defining it. Seq pipeline does not as far as I am aware.
 2. A lane group is simply a helper table. A lane group is defined as a group of lanes. A group of lanes can consist of 1 or many lanes. The lane grouping table defines which lanes are part of which group. This makes it possible for a statfile to refer to single lanes (single lane files) and multiple lanes (merged files).
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
    TOOL ||--|{ TOOL_EXECUTION : ""
    FILE }|--|| TOOL_EXECUTION : ""
    LIBRARY ||--|{ POOL_LIBRARY_MAPPING : ""
    POOL ||--|{ POOL_LIBRARY_MAPPING : ""
    LANE_GROUP ||--|{ LANE_GROUPING : ""
    LANE ||--o{ LANE_GROUPING : ""
    LIBRARY ||--o{ FILE : ""
    POOL_LIBRARY_MAPPING ||--|| XIHAN : ""
    FILE }|--|| LANE_GROUP : ""
    LANE }|--|| FLOWCELL : ""
    LANE }|--|| POOL : ""
    
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
        int lane_group_id FK
        string read_type "R1, R2, collapsed, singleton"  
        int execution_id FK
    }

    LANE_GROUP {
        int lane_group_id PK
        string type "UK1: full merge | partial merge | single" 
    }

    LANE_GROUPING {
        int lane_grouping_id PK
        int lane_group_id FK "UK1"
        int lane_id FK "UK1"
    }

    LANE {
        int lane_id PK
        int flowcell_id FK
        int pool_id FK
    }

  






```
