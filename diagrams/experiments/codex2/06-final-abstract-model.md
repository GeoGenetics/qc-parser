# 6. Final abstract domain model

This is the recommended conceptual model. It omits junction-table implementation details and focuses on domain relationships.

```mermaid
erDiagram
    LIBRARY }o--o{ POOL : belongs_to

    FLOWCELL ||--|{ LANE : contains
    POOL ||--|{ LANE : sequenced_on

    LIBRARY ||--o{ SEQUENCE_DATASET : produces
    LANE ||--o{ SEQUENCE_DATASET : produces

    SEQUENCE_DATASET ||--o{ PROCESSING : processed_in
    PIPELINE_VERSION ||--o{ PROCESSING : uses
    PIPELINE_CONFIG ||--o{ PROCESSING : uses

    PROCESSING ||--o{ QC_RESULT : generates
```

The three essential associative relationships are:

```mermaid
flowchart TD
    subgraph Pooling
        L["Library"] --> PM["Pool membership"]
        P["Pool"] --> PM
    end

    subgraph Sequencing
        L2["Library"] --> S["Sequence dataset"]
        LN["Flowcell lane"] --> S
    end

    subgraph Processing
        S2["Sequence dataset"] --> R["Processing"]
        V["Pipeline version"] --> R
        C["Pipeline configuration"] --> R
    end
```

