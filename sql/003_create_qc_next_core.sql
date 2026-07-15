BEGIN;

-- Fail safely if the target schema from Task 2 is missing.
DO $preflight$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_namespace
        WHERE nspname = 'qc_next'
    ) THEN
        RAISE EXCEPTION 'Required schema qc_next does not exist';
    END IF;
END
$preflight$;

-- Task 3A originally made assignment_id unique through its primary key. Add
-- the explicit composite key required for library-safe cross-schema foreign
-- keys. The catalog guard keeps this script compatible with a fresh Task 3A
-- schema that already includes the constraint.
DO $assignment_key$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conrelid =
              'uploaded_data_next.library_lane_assignment'::regclass
          AND conname =
              'library_lane_assignment_id_library_unique'
    ) THEN
        ALTER TABLE uploaded_data_next.library_lane_assignment
            ADD CONSTRAINT library_lane_assignment_id_library_unique
            UNIQUE (assignment_id, library_id);
    END IF;
END
$assignment_key$;

-- -------------------------------------------------------------------------
-- Independent pipeline dimensions
-- -------------------------------------------------------------------------

CREATE TABLE qc_next.pipeline_version (
    pipeline_version_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    version text NOT NULL,
    code_commit text,
    container_digest text,
    released_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT pipeline_version_version_unique
        UNIQUE (version),

    CONSTRAINT pipeline_version_version_not_empty
        CHECK (btrim(version) <> '')
);

CREATE TABLE qc_next.pipeline_config (
    pipeline_config_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    pipeline_hash text NOT NULL,
    hash_algorithm text NOT NULL DEFAULT 'sha256',
    config jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT pipeline_config_hash_unique
        UNIQUE (hash_algorithm, pipeline_hash),

    CONSTRAINT pipeline_config_hash_not_empty
        CHECK (btrim(pipeline_hash) <> ''),

    CONSTRAINT pipeline_config_hash_algorithm_not_empty
        CHECK (btrim(hash_algorithm) <> '')
);

-- -------------------------------------------------------------------------
-- Actual pipeline executions
--
-- A processing run belongs to one library, but its input artifacts can come
-- from any number of lanes and flowcells. The exact inputs are represented
-- by processing_run_input and artifact_lane_input below.
-- -------------------------------------------------------------------------

CREATE TABLE qc_next.processing_run (
    processing_run_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    library_id uploaded_data.citext NOT NULL,
    pipeline_version_id bigint NOT NULL,
    pipeline_config_id bigint NOT NULL,
    attempt_number integer NOT NULL DEFAULT 1,
    status text NOT NULL DEFAULT 'pending',
    run_path text,
    config_source_path text,
    started_at timestamptz,
    completed_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT processing_run_library_fk
        FOREIGN KEY (library_id)
        REFERENCES uploaded_data_next.library(library_id)
        ON UPDATE CASCADE
        ON DELETE RESTRICT,

    CONSTRAINT processing_run_pipeline_version_fk
        FOREIGN KEY (pipeline_version_id)
        REFERENCES qc_next.pipeline_version(pipeline_version_id)
        ON UPDATE CASCADE
        ON DELETE RESTRICT,

    CONSTRAINT processing_run_pipeline_config_fk
        FOREIGN KEY (pipeline_config_id)
        REFERENCES qc_next.pipeline_config(pipeline_config_id)
        ON UPDATE CASCADE
        ON DELETE RESTRICT,

    CONSTRAINT processing_run_attempt_positive
        CHECK (attempt_number > 0),

    CONSTRAINT processing_run_status_valid
        CHECK (
            status IN (
                'pending',
                'running',
                'succeeded',
                'failed',
                'cancelled'
            )
        ),

    CONSTRAINT processing_run_dates_valid
        CHECK (
            completed_at IS NULL
            OR started_at IS NULL
            OR completed_at >= started_at
        ),

    CONSTRAINT processing_run_path_unique
        UNIQUE (run_path),

    -- Allows child tables to enforce that a referenced run and artifact
    -- belong to the same library.
    CONSTRAINT processing_run_id_library_unique
        UNIQUE (processing_run_id, library_id)
);

-- -------------------------------------------------------------------------
-- Files and other pipeline artifacts
--
-- Raw input files have produced_by_processing_run_id = NULL. Files produced
-- by a pipeline execution reference that execution. Lane membership is kept
-- in artifact_lane_input because an artifact may combine multiple lanes.
-- -------------------------------------------------------------------------

CREATE TABLE qc_next.file_artifact (
    artifact_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    library_id uploaded_data.citext NOT NULL,
    produced_by_processing_run_id bigint,
    artifact_type text NOT NULL,
    data_stage text NOT NULL,
    read_role text,
    file_path text NOT NULL,
    checksum text,
    checksum_algorithm text,
    file_size_bytes bigint,
    created_at timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT file_artifact_library_fk
        FOREIGN KEY (library_id)
        REFERENCES uploaded_data_next.library(library_id)
        ON UPDATE CASCADE
        ON DELETE RESTRICT,

    CONSTRAINT file_artifact_producer_library_fk
        FOREIGN KEY (produced_by_processing_run_id, library_id)
        REFERENCES qc_next.processing_run(processing_run_id, library_id)
        ON UPDATE CASCADE
        ON DELETE RESTRICT,

    CONSTRAINT file_artifact_path_unique
        UNIQUE (file_path),

    CONSTRAINT file_artifact_id_library_unique
        UNIQUE (artifact_id, library_id),

    CONSTRAINT file_artifact_type_not_empty
        CHECK (btrim(artifact_type) <> ''),

    CONSTRAINT file_artifact_stage_not_empty
        CHECK (btrim(data_stage) <> ''),

    CONSTRAINT file_artifact_path_not_empty
        CHECK (btrim(file_path) <> ''),

    CONSTRAINT file_artifact_size_valid
        CHECK (file_size_bytes IS NULL OR file_size_bytes >= 0),

    CONSTRAINT file_artifact_checksum_pair
        CHECK (
            (checksum IS NULL AND checksum_algorithm IS NULL)
            OR
            (checksum IS NOT NULL AND checksum_algorithm IS NOT NULL)
        )
);

-- -------------------------------------------------------------------------
-- Exact file inputs consumed by each processing run
--
-- library_id is intentionally repeated so composite foreign keys can prevent
-- a run for one library from consuming an artifact belonging to another.
-- -------------------------------------------------------------------------

CREATE TABLE qc_next.processing_run_input (
    processing_run_id bigint NOT NULL,
    artifact_id bigint NOT NULL,
    library_id uploaded_data.citext NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT processing_run_input_pk
        PRIMARY KEY (processing_run_id, artifact_id),

    CONSTRAINT processing_run_input_run_library_fk
        FOREIGN KEY (processing_run_id, library_id)
        REFERENCES qc_next.processing_run(processing_run_id, library_id)
        ON UPDATE CASCADE
        ON DELETE CASCADE,

    CONSTRAINT processing_run_input_artifact_library_fk
        FOREIGN KEY (artifact_id, library_id)
        REFERENCES qc_next.file_artifact(artifact_id, library_id)
        ON UPDATE CASCADE
        ON DELETE RESTRICT
);

-- -------------------------------------------------------------------------
-- Physical lane provenance for raw and generated artifacts
--
-- One raw FASTQ normally links to one assignment. A merged artifact can link
-- to several assignments, including assignments on different flowcells.
-- -------------------------------------------------------------------------

CREATE TABLE qc_next.artifact_lane_input (
    artifact_id bigint NOT NULL,
    assignment_id bigint NOT NULL,
    library_id uploaded_data.citext NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT artifact_lane_input_pk
        PRIMARY KEY (artifact_id, assignment_id),

    CONSTRAINT artifact_lane_input_artifact_library_fk
        FOREIGN KEY (artifact_id, library_id)
        REFERENCES qc_next.file_artifact(artifact_id, library_id)
        ON UPDATE CASCADE
        ON DELETE CASCADE,

    CONSTRAINT artifact_lane_input_assignment_library_fk
        FOREIGN KEY (assignment_id, library_id)
        REFERENCES uploaded_data_next.library_lane_assignment(
            assignment_id,
            library_id
        )
        ON UPDATE CASCADE
        ON DELETE RESTRICT
);

-- -------------------------------------------------------------------------
-- Supporting indexes for foreign-key joins and common access paths
-- -------------------------------------------------------------------------

CREATE INDEX processing_run_library_idx
    ON qc_next.processing_run(library_id);

CREATE INDEX processing_run_version_idx
    ON qc_next.processing_run(pipeline_version_id);

CREATE INDEX processing_run_config_idx
    ON qc_next.processing_run(pipeline_config_id);

CREATE INDEX file_artifact_library_idx
    ON qc_next.file_artifact(library_id);

CREATE INDEX file_artifact_producer_idx
    ON qc_next.file_artifact(produced_by_processing_run_id);

CREATE INDEX processing_run_input_artifact_idx
    ON qc_next.processing_run_input(artifact_id);

CREATE INDEX artifact_lane_input_assignment_idx
    ON qc_next.artifact_lane_input(assignment_id);

-- -------------------------------------------------------------------------
-- Permissions
-- -------------------------------------------------------------------------

GRANT SELECT ON ALL TABLES IN SCHEMA qc_next
    TO ai_readonly, backup_role;

GRANT SELECT, INSERT, UPDATE, DELETE
    ON ALL TABLES IN SCHEMA qc_next
    TO qc_writer;

GRANT USAGE, SELECT
    ON ALL SEQUENCES IN SCHEMA qc_next
    TO qc_writer;

ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA qc_next
    GRANT SELECT ON TABLES TO ai_readonly, backup_role;

ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA qc_next
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO qc_writer;

ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA qc_next
    GRANT USAGE, SELECT ON SEQUENCES TO qc_writer;

COMMIT;
