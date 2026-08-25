
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
        bool has_material 
    }

    UPLOAD_BATCH {
        int uploader_id FK
        int receipt_sent_to FK
        int data_filler FK
        timestamp uploaded_at
        uuid upload_batch_id PK
        text upload_template_version 
        text upload_file_path
        text upload_comment
    }

    SAMPLE_SET {
        text set_name PK "e.g. IcelandLakeCores24"
        text set_parent_name PK, FK "e.g. IcelandLakeCores"
        bool is_leaf 
    }

    SUB_FIELD_SAMPLE {
        int sample_id PK, FK
        text biggest_format_in_storage
        text organic_content
        text surface_exposed
    }


    ORIGINAL_FIELD_SAMPLE {
        int sample_id PK, FK
        int sampling_location_id FK
        int field_trip_id FK
        text present_day_environmental_context_id 
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

    SUB_SAMPLING {
        int source_sample_id PK,FK
        int derived_sample_id PK,FK
        text sub_sampling_order_id FK
        text sub_sampling_order_remarks
        text type "composite | non-rep subsam | rep subsam "
    }

    STORAGE_LOCATION {
        ing location_parent FK, PK
        text location_name PK "e.g. Øster voldgade 5"
        text location_barcode PK "e.g. LVL500291685"
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
        text full_name UK 
        text ku_id UK
        text initials UK
        bool is_principal_investigator
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

    DNA_SAMPLE {
        int sample_id PK, FK
        int volumne_ul
        text dna_sample_type "e.g. lysate | clean | library"
    }

    LIBRARY {
        int sample_id PK, FK
        int ct
        date qpcr_performed_at
        date indexing_pcr_performed_at
        int index_number
        date cleanup_performed_at
        date start_at
        decimal concentration_nm
        int library_peak
        date qc_performed_at
        text qc_result
        decimal proportion_in_pool
        bool stop_pool
        decimal dna_pooled
        int expected_sequencing_data_size_mb

    }

    CLEAN_DNA_SAMPLE {
        int sample_id PK, FK
        decimal total_dna_concentration_ng_ul
        int short_dna_concentration_ng_ul
        text binding_buffer
    }

    ORDER {
        int order_id PK
        int customer FK
        date order_date
        text order_type
    }

    SERVICE {
        text service_name "e.g. sub-sampling, dna extraction, library prep, pooling, sequencing"
    }

    SAMPLE ||--o| ORIGINAL_FIELD_SAMPLE : ""
    SAMPLE ||--o{ DEPTH_MEASUREMENT : ""

    SAMPLE ||--o{ AGE_ESTIMATE : ""
    SAMPLE_SET ||--|{ ORIGINAL_FIELD_SAMPLE : ""
    SAMPLE_SET ||--|{ SAMPLE_SET : ""
    SUB_SAMPLING }|--|| ORDER : ""
    SERVICE }|--|{ ORDER : ""
    PERSON ||--o{ ORDER : ""
    
    SAMPLE }|--|| PROJECT : "" 
    PROJECT ||--o{ PROJECT : "has subproject"

    SAMPLE ||--o{ SUB_SAMPLING : ""
    SAMPLE ||--o{ SUB_SAMPLING : ""
    SAMPLE ||--|| DNA_SAMPLE : ""
    DNA_SAMPLE ||--o| CLEAN_DNA_SAMPLE : ""
    DNA_SAMPLE ||--o| LIBRARY : ""

    STORAGE_LOCATION ||--|{ SAMPLE : ""
    STORAGE_LOCATION ||--|{ STORAGE_LOCATION : "has sub-storage location"

    FIELD_TRIP ||--|{ ORIGINAL_FIELD_SAMPLE : ""

    SAMPLE_ALIASES }o--|| SAMPLE : ""
    SAMPLING_LOCATION ||--|{ ORIGINAL_FIELD_SAMPLE : ""
    GEOGRAPHICAL_LOCATION_TAGS ||--|{ FIELD_TRIP : ""
    ORIGINAL_FIELD_SAMPLE ||--|| ENVIRONMENT : ""
    ORIGINAL_FIELD_SAMPLE ||--|| MEDIUM : ""
    ORIGINAL_FIELD_SAMPLE }|--|{ DEPOSITIONAL_ENVIRONMENT: ""

    GEOGRAPHICAL_LOCATION_TAGS }|--|| SAMPLING_LOCATION : ""
    FIELD_TRIP }|--|{ PERSON : ""
    PERSON ||--|{ AGE_ESTIMATE : "" 
    PERSON }|--|{ SAMPLE : "is contact person for" 
    PERSON ||--|{ SAMPLE : "is responsible for" 

    RAW_TEMPLATE_RECORD ||--|| SAMPLE : "" 

    SUB_FIELD_SAMPLE |o--|| SAMPLE : "" 

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
5. Controlled vocabs are missing.
6. SAMPLE_SET could replace PROJECT and be a way to easily identify a set of samples by Kurt for example. Might not be needed  though.
7. The difference between an ORDER and a SAMPLE_SET is that a sample might be part of many orders but only part of 1 sample set. 


NEEDS CLARIFICATION:
1. Can all samples get age estimates?
2. Can a sub project be part of many master projects?
3. Rename SAMPLING_LOCATION to SAMPLE_ORIGIN?
4. Move water_depth? To a sampling context?
5. How to get information about the responsible instittion/organisation i.e. who the sampling responsible is taking the sample on behalf of?
6. How to define a field trip? How to make sure the field trip attributes are provided?
7. Should it be allowed for a sampling location to have more than 1 environment?
8. Where should principal investigator be an attribute?
9. What is archive sample number?
10. How to log updates, inserts and deletions? 
11. How to get archive sample storage info?
12. Does archive_sample_material_left indicate parent material left or archive material left?
13. what is archive sample serial_id?
14. Could the number of person columns be reduced?
15. What is wet_lab_no in wetlab report?
16. What is the cardinality between DNA_LYSATE and DNA_CLEAN and how to track provenance?
17. Do library dates relate to other dna samples?
18. What is Pool and what is library data?