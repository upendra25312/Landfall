-- Landfall inventory schema (Azure SQL - Free offer)
-- Nullable throughout: client-supplied inventory always has gaps.
--
-- The ingestion pipeline (src/api/ingest) is the integrity check, not the database:
-- soft FKs are intentionally NOT enforced here (files arrive one table at a time and
-- out of order). Orphan app_id / server_id values are reported in the data-quality
-- report instead. Every row carries `source_file` so re-uploading a corrected export
-- replaces only its own rows.
--
-- MULTI-ENGAGEMENT (PRD E11.3): every table carries `engagement_id` ('<customer>/<project>').
-- Natural-key tables key on (engagement_id, <id>). A Row-Level Security policy filters
-- every read by SESSION_CONTEXT('engagement_id'); callers set it via
-- sp_set_session_context before querying (src/api/engagement_sql.py). With no context set,
-- the policy returns NOTHING - every reader must scope itself.

IF EXISTS (SELECT 1 FROM sys.security_policies WHERE name = 'EngagementFilter')
    DROP SECURITY POLICY dbo.EngagementFilter;
IF OBJECT_ID('dbo.fn_engagement_predicate', 'IF') IS NOT NULL
    DROP FUNCTION dbo.fn_engagement_predicate;
GO

IF OBJECT_ID('dbo.performance', 'U')  IS NOT NULL DROP TABLE dbo.performance;
IF OBJECT_ID('dbo.dependencies', 'U') IS NOT NULL DROP TABLE dbo.dependencies;
IF OBJECT_ID('dbo.storage', 'U')      IS NOT NULL DROP TABLE dbo.storage;
IF OBJECT_ID('dbo.servers', 'U')      IS NOT NULL DROP TABLE dbo.servers;
IF OBJECT_ID('dbo.applications', 'U') IS NOT NULL DROP TABLE dbo.applications;
IF OBJECT_ID('dbo.ingest_log', 'U')   IS NOT NULL DROP TABLE dbo.ingest_log;
GO

CREATE TABLE dbo.applications (
    engagement_id   NVARCHAR(120) NOT NULL,
    app_id          NVARCHAR(64)  NOT NULL,
    app_name        NVARCHAR(256) NULL,
    business_owner  NVARCHAR(256) NULL,
    criticality     TINYINT       NULL,           -- 1 (highest) .. 4
    users           INT           NULL,
    tech_stack      NVARCHAR(512) NULL,
    db_engine       NVARCHAR(128) NULL,
    internet_facing BIT           NULL,
    compliance_scope NVARCHAR(256) NULL,
    disposition     NVARCHAR(32)  NULL,           -- Rehost/Replatform/Refactor/Repurchase/Retire/Retain (agent-filled)
    complexity      NVARCHAR(8)   NULL,           -- S/M/L/XL (agent-filled)
    wave            INT           NULL,           -- (agent-filled)
    source_file     NVARCHAR(260) NULL,
    ingested_at     DATETIME2     NULL CONSTRAINT DF_applications_ingested DEFAULT SYSUTCDATETIME(),
    CONSTRAINT PK_applications PRIMARY KEY (engagement_id, app_id)
);
GO

CREATE TABLE dbo.servers (
    engagement_id       NVARCHAR(120) NOT NULL,
    server_id           NVARCHAR(64)  NOT NULL,
    hostname            NVARCHAR(256) NULL,
    env                 NVARCHAR(32)  NULL,       -- prod/nonprod/dev/dr
    os_name             NVARCHAR(128) NULL,
    os_version          NVARCHAR(64)  NULL,
    os_eol_date         DATE          NULL,
    vcpu                INT           NULL,
    ram_gb              DECIMAL(9,2)  NULL,
    provisioned_disk_gb DECIMAL(12,2) NULL,
    used_disk_gb        DECIMAL(12,2) NULL,
    cpu_avg_pct         DECIMAL(5,2)  NULL,          -- 30-day rollups (see dbo.performance for the daily series)
    cpu_peak_pct        DECIMAL(5,2)  NULL,          -- 30-day maximum
    cpu_p95_pct         DECIMAL(5,2)  NULL,          -- 95th percentile of daily averages (use this to right-size)
    ram_avg_pct         DECIMAL(5,2)  NULL,
    ram_p95_pct         DECIMAL(5,2)  NULL,
    disk_iops_avg       DECIMAL(12,2) NULL,
    disk_iops_peak      DECIMAL(12,2) NULL,
    net_in_gb_30d       DECIMAL(14,2) NULL,          -- total inbound data over the 30-day window
    net_out_gb_30d      DECIMAL(14,2) NULL,          -- total outbound (egress) data over the window
    cluster             NVARCHAR(128) NULL,
    datacenter          NVARCHAR(128) NULL,
    powerstate          NVARCHAR(32)  NULL,
    app_id              NVARCHAR(64)  NULL,       -- soft link to applications.app_id (not FK-enforced; see header)
    notes               NVARCHAR(1024) NULL,
    source_file         NVARCHAR(260) NULL,
    ingested_at         DATETIME2     NULL CONSTRAINT DF_servers_ingested DEFAULT SYSUTCDATETIME(),
    CONSTRAINT PK_servers PRIMARY KEY (engagement_id, server_id)
);
GO

CREATE TABLE dbo.dependencies (
    dep_id       INT IDENTITY(1,1) PRIMARY KEY,
    engagement_id NVARCHAR(120) NOT NULL,
    src_id       NVARCHAR(64)  NULL,
    dst_id       NVARCHAR(64)  NULL,
    port         INT           NULL,
    protocol     NVARCHAR(16)  NULL,
    direction    NVARCHAR(16)  NULL,
    confidence   NVARCHAR(16)  NULL,
    bytes_30d_gb DECIMAL(14,2) NULL,                 -- observed data volume over the 30-day window
    flows_30d    BIGINT        NULL,                 -- observed connection count over the window
    last_seen    DATE          NULL,                 -- last date the flow was observed (stale => maybe dead)
    source_file  NVARCHAR(260) NULL,
    ingested_at  DATETIME2     NULL CONSTRAINT DF_dependencies_ingested DEFAULT SYSUTCDATETIME()
);
GO
CREATE INDEX IX_dependencies_engagement ON dbo.dependencies (engagement_id);
GO

-- Daily performance samples over a ~30-day observation window (one row per server per day).
-- servers.csv carries the rollups; this table is the series behind them.
CREATE TABLE dbo.performance (
    perf_id                   INT IDENTITY(1,1) PRIMARY KEY,
    engagement_id             NVARCHAR(120) NOT NULL,
    server_id                 NVARCHAR(64)  NULL,    -- soft link to servers.server_id
    sample_date               DATE          NULL,
    cpu_avg_pct               DECIMAL(5,2)  NULL,
    cpu_peak_pct              DECIMAL(5,2)  NULL,
    cpu_p95_pct               DECIMAL(5,2)  NULL,
    mem_avg_pct               DECIMAL(5,2)  NULL,
    mem_peak_pct              DECIMAL(5,2)  NULL,
    mem_p95_pct               DECIMAL(5,2)  NULL,
    disk_iops_avg             DECIMAL(12,2) NULL,
    disk_iops_peak            DECIMAL(12,2) NULL,
    disk_read_iops_avg        DECIMAL(12,2) NULL,
    disk_write_iops_avg       DECIMAL(12,2) NULL,
    disk_throughput_mbps_avg  DECIMAL(12,2) NULL,
    net_in_gb                 DECIMAL(12,3) NULL,    -- inbound data volume that day
    net_out_gb                DECIMAL(12,3) NULL,    -- outbound (egress) data volume that day
    net_in_peak_mbps          DECIMAL(12,2) NULL,
    net_out_peak_mbps         DECIMAL(12,2) NULL,
    source_file               NVARCHAR(260) NULL,
    ingested_at               DATETIME2     NULL CONSTRAINT DF_performance_ingested DEFAULT SYSUTCDATETIME()
);
GO
CREATE INDEX IX_performance_engagement ON dbo.performance (engagement_id);
GO

CREATE TABLE dbo.storage (
    engagement_id  NVARCHAR(120) NOT NULL,
    storage_id     NVARCHAR(64)  NOT NULL,
    server_id      NVARCHAR(64)  NULL,            -- soft link to servers.server_id (not FK-enforced)
    type           NVARCHAR(16)  NULL,            -- block/file/object/db
    size_gb        DECIMAL(12,2) NULL,
    iops           INT           NULL,
    target_service NVARCHAR(128) NULL,
    source_file    NVARCHAR(260) NULL,
    ingested_at    DATETIME2     NULL CONSTRAINT DF_storage_ingested DEFAULT SYSUTCDATETIME(),
    CONSTRAINT PK_storage PRIMARY KEY (engagement_id, storage_id)
);
GO

-- One row per ingested file: what the Normalize pipeline detected, loaded, and flagged.
CREATE TABLE dbo.ingest_log (
    run_id        INT IDENTITY(1,1) PRIMARY KEY,
    engagement_id NVARCHAR(120) NOT NULL,
    file_name     NVARCHAR(260) NULL,
    profile       NVARCHAR(64)  NULL,
    target_table  NVARCHAR(64)  NULL,
    rows_in       INT           NULL,
    rows_loaded   INT           NULL,
    rows_rejected INT           NULL,
    status        NVARCHAR(64)  NULL,
    dq_json       NVARCHAR(MAX) NULL,
    ingested_at   DATETIME2     NULL CONSTRAINT DF_ingestlog_ingested DEFAULT SYSUTCDATETIME()
);
GO
CREATE INDEX IX_ingestlog_engagement ON dbo.ingest_log (engagement_id);
GO

-- ---------------------------------------------------------------------------
-- Row-Level Security: every read is scoped to SESSION_CONTEXT('engagement_id').
-- No context set  ->  the predicate returns no rows (fail closed). Callers set the
-- context with sp_set_session_context before running any SELECT (this is what makes
-- the free-form text-to-SQL in query_inventory tenant-safe regardless of the SQL the
-- model writes). INSERTs are unaffected (the loader writes engagement_id explicitly).
-- ---------------------------------------------------------------------------
CREATE FUNCTION dbo.fn_engagement_predicate(@engagement_id AS NVARCHAR(120))
    RETURNS TABLE
    WITH SCHEMABINDING
AS
    RETURN SELECT 1 AS ok
           WHERE @engagement_id =
                 CAST(SESSION_CONTEXT(N'engagement_id') AS NVARCHAR(120));
GO

CREATE SECURITY POLICY dbo.EngagementFilter
    ADD FILTER PREDICATE dbo.fn_engagement_predicate(engagement_id) ON dbo.servers,
    ADD FILTER PREDICATE dbo.fn_engagement_predicate(engagement_id) ON dbo.applications,
    ADD FILTER PREDICATE dbo.fn_engagement_predicate(engagement_id) ON dbo.dependencies,
    ADD FILTER PREDICATE dbo.fn_engagement_predicate(engagement_id) ON dbo.storage,
    ADD FILTER PREDICATE dbo.fn_engagement_predicate(engagement_id) ON dbo.performance,
    ADD FILTER PREDICATE dbo.fn_engagement_predicate(engagement_id) ON dbo.ingest_log
    WITH (STATE = ON);
GO

-- Read-only + read-write login for the workload identity is granted in scripts/apply_sql.py
-- (contained user mapped to the workload managed identity - name passed in by the script).
