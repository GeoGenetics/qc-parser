# Library, pool, flowcell lane, and file

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

Interpretation: libraries and pools have a many-to-many relationship; each pool is sequenced on one or more lanes; each flowcell contains one or more lanes.
