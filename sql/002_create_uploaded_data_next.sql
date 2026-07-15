BEGIN ISOLATION LEVEL REPEATABLE READ;

CREATE SCHEMA uploaded_data_next AUTHORIZATION postgres;

-- -------------------------------------------------------------------------
-- Libraries
-- -------------------------------------------------------------------------

CREATE TABLE uploaded_data_next.library (
    library_id uploaded_data.citext PRIMARY KEY,
    created_at timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT library_id_not_empty
        CHECK (btrim(library_id::text) <> '')
);

-- -------------------------------------------------------------------------
-- Flowcells
-- -------------------------------------------------------------------------

CREATE TABLE uploaded_data_next.flowcell (
    flowcell_id uploaded_data.citext PRIMARY KEY,
    sequencing_date date,
    flowcell_position uploaded_data.citext,
    sequencing_machine uploaded_data.citext,
    sequencing_run_number text,
    sequencing_run_id text,
    created_at timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT flowcell_id_not_empty
        CHECK (btrim(flowcell_id::text) <> '')
);

-- -------------------------------------------------------------------------
-- Physical flowcell lanes
-- -------------------------------------------------------------------------

CREATE TABLE uploaded_data_next.flowcell_lane (
    flowcell_lane_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    flowcell_id uploaded_data.citext NOT NULL,
    lane_number smallint NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT flowcell_lane_flowcell_fk
        FOREIGN KEY (flowcell_id)
        REFERENCES uploaded_data_next.flowcell(flowcell_id)
        ON UPDATE CASCADE
        ON DELETE RESTRICT,

    CONSTRAINT flowcell_lane_number_positive
        CHECK (lane_number > 0),

    CONSTRAINT flowcell_lane_unique
        UNIQUE (flowcell_id, lane_number)
);

-- -------------------------------------------------------------------------
-- Many-to-many relationship between libraries and lanes
-- -------------------------------------------------------------------------

CREATE TABLE uploaded_data_next.library_lane_assignment (
    assignment_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    library_id uploaded_data.citext NOT NULL,
    flowcell_lane_id bigint NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT library_lane_assignment_library_fk
        FOREIGN KEY (library_id)
        REFERENCES uploaded_data_next.library(library_id)
        ON UPDATE CASCADE
        ON DELETE RESTRICT,

    CONSTRAINT library_lane_assignment_lane_fk
        FOREIGN KEY (flowcell_lane_id)
        REFERENCES uploaded_data_next.flowcell_lane(flowcell_lane_id)
        ON UPDATE CASCADE
        ON DELETE RESTRICT,

    CONSTRAINT library_lane_assignment_unique
        UNIQUE (library_id, flowcell_lane_id)
);

CREATE INDEX flowcell_lane_flowcell_idx
    ON uploaded_data_next.flowcell_lane(flowcell_id);

CREATE INDEX library_lane_assignment_lane_idx
    ON uploaded_data_next.library_lane_assignment(flowcell_lane_id);

-- -------------------------------------------------------------------------
-- Populate libraries
-- -------------------------------------------------------------------------

INSERT INTO uploaded_data_next.library (library_id)
SELECT DISTINCT library_id
FROM uploaded_data.edna_wetlab_report
WHERE library_id IS NOT NULL;

-- -------------------------------------------------------------------------
-- Populate flowcells
--
-- The aggregate selects the one non-null value for each metadata field.
-- The live-data checks found no flowcell with conflicting metadata.
-- -------------------------------------------------------------------------

INSERT INTO uploaded_data_next.flowcell (
    flowcell_id,
    sequencing_date,
    flowcell_position,
    sequencing_machine,
    sequencing_run_number,
    sequencing_run_id
)
SELECT
    flowcell_id,
    min(sequencing_date),
    min(flowcell_position::text)::uploaded_data.citext,
    min(sequencing_machine::text)::uploaded_data.citext,
    min(sequencing_run_number::text),
    min(sequencing_run_id)
FROM uploaded_data.flowcell
WHERE flowcell_id IS NOT NULL
GROUP BY flowcell_id;

-- -------------------------------------------------------------------------
-- Populate lanes
-- -------------------------------------------------------------------------

INSERT INTO uploaded_data_next.flowcell_lane (
    flowcell_id,
    lane_number
)
SELECT DISTINCT
    flowcell_id,
    flowcell_lane
FROM uploaded_data.flowcell
WHERE flowcell_id IS NOT NULL
  AND flowcell_lane IS NOT NULL;

-- -------------------------------------------------------------------------
-- Populate library/lane assignments
--
-- Use fastq_tube_id when it exists on both sides. Otherwise fall back to
-- the composite (fastq_file_id, seqc_tube_tag) relationship.
-- -------------------------------------------------------------------------

-- Keep the two relationship strategies in separate equality joins so that
-- PostgreSQL can use efficient hash/index join plans. A CASE expression in
-- the JOIN condition causes a very expensive plan for these source tables.
CREATE TEMPORARY TABLE normalized_assignment_source
ON COMMIT DROP
AS
SELECT DISTINCT
    wetlab.library_id,
    source_flowcell.flowcell_id,
    source_flowcell.flowcell_lane AS lane_number
FROM uploaded_data.edna_wetlab_report AS wetlab
JOIN uploaded_data.flowcell AS source_flowcell
  ON source_flowcell.fastq_tube_id = wetlab.fastq_tube_id
WHERE wetlab.fastq_tube_id IS NOT NULL
  AND source_flowcell.fastq_tube_id IS NOT NULL
  AND wetlab.library_id IS NOT NULL
  AND source_flowcell.flowcell_id IS NOT NULL
  AND source_flowcell.flowcell_lane IS NOT NULL

UNION

SELECT DISTINCT
    wetlab.library_id,
    source_flowcell.flowcell_id,
    source_flowcell.flowcell_lane AS lane_number
FROM uploaded_data.edna_wetlab_report AS wetlab
JOIN uploaded_data.flowcell AS source_flowcell
  ON source_flowcell.fastq_file_id = wetlab.fastq_file_id
 AND source_flowcell.seqc_tube_tag = wetlab.seqc_tube_tag
WHERE (
        wetlab.fastq_tube_id IS NULL
        OR source_flowcell.fastq_tube_id IS NULL
      )
  AND wetlab.fastq_file_id IS NOT NULL
  AND wetlab.seqc_tube_tag IS NOT NULL
  AND wetlab.library_id IS NOT NULL
  AND source_flowcell.flowcell_id IS NOT NULL
  AND source_flowcell.flowcell_lane IS NOT NULL;

CREATE UNIQUE INDEX normalized_assignment_source_unique
    ON normalized_assignment_source (
        library_id,
        flowcell_id,
        lane_number
    );

ANALYZE normalized_assignment_source;

INSERT INTO uploaded_data_next.library_lane_assignment (
    library_id,
    flowcell_lane_id
)
SELECT
    source_assignment.library_id,
    normalized_lane.flowcell_lane_id
FROM normalized_assignment_source AS source_assignment
JOIN uploaded_data_next.flowcell_lane AS normalized_lane
  ON normalized_lane.flowcell_id = source_assignment.flowcell_id
 AND normalized_lane.lane_number = source_assignment.lane_number
ON CONFLICT (library_id, flowcell_lane_id) DO NOTHING;

-- -------------------------------------------------------------------------
-- Validate target counts against the same source snapshot
-- -------------------------------------------------------------------------

DO $validation$
DECLARE
    source_count bigint;
    target_count bigint;
BEGIN
    SELECT count(DISTINCT library_id)
    INTO source_count
    FROM uploaded_data.edna_wetlab_report
    WHERE library_id IS NOT NULL;

    SELECT count(*)
    INTO target_count
    FROM uploaded_data_next.library;

    IF source_count <> target_count THEN
        RAISE EXCEPTION
            'Library count mismatch: source %, target %',
            source_count,
            target_count;
    END IF;

    SELECT count(DISTINCT flowcell_id)
    INTO source_count
    FROM uploaded_data.flowcell
    WHERE flowcell_id IS NOT NULL;

    SELECT count(*)
    INTO target_count
    FROM uploaded_data_next.flowcell;

    IF source_count <> target_count THEN
        RAISE EXCEPTION
            'Flowcell count mismatch: source %, target %',
            source_count,
            target_count;
    END IF;

    SELECT count(*)
    INTO source_count
    FROM (
        SELECT DISTINCT flowcell_id, flowcell_lane
        FROM uploaded_data.flowcell
        WHERE flowcell_id IS NOT NULL
          AND flowcell_lane IS NOT NULL
    ) AS source_lanes;

    SELECT count(*)
    INTO target_count
    FROM uploaded_data_next.flowcell_lane;

    IF source_count <> target_count THEN
        RAISE EXCEPTION
            'Flowcell-lane count mismatch: source %, target %',
            source_count,
            target_count;
    END IF;

    SELECT count(*)
    INTO source_count
    FROM normalized_assignment_source;

    SELECT count(*)
    INTO target_count
    FROM uploaded_data_next.library_lane_assignment;

    IF source_count <> target_count THEN
        RAISE EXCEPTION
            'Library-lane assignment count mismatch: source %, target %',
            source_count,
            target_count;
    END IF;
END
$validation$;

-- -------------------------------------------------------------------------
-- Read permissions
--
-- qc_writer only needs to read these master-data tables.
-- -------------------------------------------------------------------------

GRANT USAGE ON SCHEMA uploaded_data_next
    TO ai_readonly, backup_role, qc_writer;

GRANT SELECT ON ALL TABLES IN SCHEMA uploaded_data_next
    TO ai_readonly, backup_role, qc_writer;

ANALYZE uploaded_data_next.library;
ANALYZE uploaded_data_next.flowcell;
ANALYZE uploaded_data_next.flowcell_lane;
ANALYZE uploaded_data_next.library_lane_assignment;

COMMIT;
