
```mermaid
---
config:
  layout: elk
  er:
    layoutDirection: LR
    entityPadding: 8
    diagramPadding: 15
    useMaxWidth: false
---


erDiagram
  
    SAMPLE {
        int sample_id PK
        text sample_label UK
        int storage_location_id FK, UK
        decimal mass_g
        text description
        date sampled_at
        text sampling_method
        text taxonomy 
        JSON misc_measurements 
        int event_id FK
        text sample_type "negative control | positive control | true sample"  
        int sampling_responsible_id FK
        int sample_contact_id FK
        int sampling_institution_id FK
        text other_sampling_process_details
        text other_sample_details
        text set_name FK
        text sample_container
        text acquisition_type 
        json other_values
        text created_from "field_sampling | edna_extraction | sub sampling"
        text data_quality_comments
        text other_comments
        int data_filler FK 
        uuid batch_upload_id FK
    }

    UPLOAD_BATCH {
        int uploader_id FK
        int receipt_sent_to FK
        int data_filler FK
        timestamp uploaded_at
        uuid upload_batch_id PK
        text upload_template_version 
        text upload_file_path
    }

    SAMPLE_SET {
        text set_name PK
        text set_parent_name PK, FK
        bool is_leaf 
    }

    SUB_SAMPLE {
        text biggest_format_in_storage
    }

    FIELD_SAMPLE {
        int sample_id PK, FK
        int sampling_location_id FK
        int field_trip_id FK
        text present_day_environmental_context_id FK
        text environmental_medium_id FK
        text environmental_medium_details 
        text sampling_context_description
    }

    DEPTH_MEASUREMENT {
        int sample_id PK, FK 
        decimal depth PK
        text depth_method 
        text depth_reference PK
    }

    AGE_ESTIMATE {
        int age_estimate_id PK
        int sample_id FK 
        int age_method FK 
        decimal age
        date estimated_at
        text contact_person FK
    }

    SAMPLE_PROVENANCE {
        int source_sample_id PK,FK
        int derived_sample_id PK,FK
        text relationship_type
    }

    STORAGE_LOCATION {
        ing location_parent FK, PK
        text location_name PK "e.g. Øster voldgade 5"
        text location_type "address, room, building, rack etc."
        text other_storage_details
    }

    SAMPLING_LOCATION {
        decimal latitude PK
        decimal longitude PK
        int elevation PK
        text elevation_inference_method 
        text coordinates_inference_method
        text water_depth
        text archaeological_site_registry  
        JSON misc_measurements
        text feature_class
    }

    PROJECT {
        int project_id PK
        text project_name "aegis, rice, kapk"
        text project_type "field_project, sequencing_project"
        int principal_investigator_id FK
    }

    ENVIRONMENT {
        int envo_id PK
        int envo_parent_id FK
        text name
    }
    
    PERSON {
        email email PK
        text full_name 
    }

    MEDIUM {
        int envo_id PK
        int envo_parent_id FK
        text name
    }

    GEOGRAPHICAL_LOCATION_TAGS {
        text location_name PK "e.g. Kap K"
        text location_type PK "site, region, province, unknown, country"
        int sampling_location_id PK, FK
        text description
    }

    FIELD_TRIP {
        text field_trip_name 
        int geo_location_tag_id FK, PK
        date start_date PK
        date end_date
    }

    SAMPLE ||--o| FIELD_SAMPLE : ""
    FIELD_SAMPLE ||--o{ DEPTH_MEASUREMENT : ""

    SAMPLE ||--o{ AGE_ESTIMATE : ""
    SAMPLE_SET ||--|{ SAMPLE : ""
    
    SAMPLE }|--|| PROJECT : "" 
    PROJECT ||--o{ PROJECT : "has subproject"

    SAMPLE ||--o{ SAMPLE_PROVENANCE : ""
    SAMPLE ||--o{ SAMPLE_PROVENANCE : ""

    STORAGE_LOCATION ||--|{ SAMPLE : ""
    STORAGE_LOCATION ||--|{ STORAGE_LOCATION : "has sub-storage location"

    FIELD_TRIP ||--|{ FIELD_SAMPLE : ""

    SAMPLE_ALIASES }o--|| SAMPLE : ""
    SAMPLING_LOCATION ||--|{ FIELD_SAMPLE : ""
    GEOGRAPHICAL_LOCATION_TAGS ||--|{ FIELD_TRIP : ""
    FIELD_SAMPLE ||--|| ENVIRONMENT : ""
    FIELD_SAMPLE ||--|| MEDIUM : ""
    FIELD_SAMPLE }|--|{ DEPOSITIONAL_ENVIRONMENT: ""

    SAMPLE ||--|| SUB_SAMPLE : ""

    GEOGRAPHICAL_LOCATION_TAGS }|--|| SAMPLING_LOCATION : ""
    FIELD_TRIP }|--|{ PERSON : ""
    PERSON ||--|{ AGE_ESTIMATE : "" 
    PERSON }|--|{ SAMPLE : "is contact person for" 
    PERSON ||--|{ SAMPLE : "is responsible for" 

    RAW_TEMPLATE_RECORD ||--|| SAMPLE : "" 


    PERSON }|--|{ ORGANIZATION : "affilation"
    ORGANIZATION ||--|{ SAMPLE : ""
    ORGANIZATION ||--|{ ORGANIZATION : "has sub-organization"
    UPLOAD_BATCH ||--|{ SAMPLE : ""
    UPLOAD_BATCH }|--|| PERSON : ""

    
```

NOTE: 
1. A master sample is defined as a physical sample that has been split into many segments.
2. We might need a single column in the field sample template for geo location classification which will include all names or identifiers of the location from least local to most local? Example Africa: North Africa: Egypt: Giza: Giza Necropolis: The Great Pyramid of Giza: Area B: Trench 5: Locus 102: Layer 4 
3. Data responsible or template filler or both?
4. Use email as unique person id


NEEDS CLARIFICATION:
1. Can all samples get age estimates?
2. Can a sub project be part of many master projects?
3. Rename SAMPLING_LOCATION to SAMPLE_ORIGIN?
4. Move water_depth? To a sampling context?
5. How to get information about the responsible instittion/organisation i.e. who the sampling responsible is taking the sample on behalf of?
6. How to define a field trip? How to make sure the field trip attributes are provided?
7. Should it be allowed for a sampling location to have more than 1 environment?
8. Where should principal investigator be an attribute?