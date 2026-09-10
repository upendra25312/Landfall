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

-- Additive schema: existing data and security objects are preserved.
IF OBJECT_ID('dbo.applications', 'U') IS NULL
BEGIN
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
END;
GO
IF COL_LENGTH('dbo.applications', 'engagement_id') IS NULL
    THROW 51001, 'Incompatible schema: applications.engagement_id requires an explicit migration', 1;
GO
IF COL_LENGTH('dbo.applications', 'app_id') IS NULL
    THROW 51001, 'Incompatible schema: applications.app_id requires an explicit migration', 1;
GO
IF COL_LENGTH('dbo.applications', 'app_name') IS NULL
    ALTER TABLE dbo.applications ADD app_name NVARCHAR(256) NULL;
GO
IF COL_LENGTH('dbo.applications', 'business_owner') IS NULL
    ALTER TABLE dbo.applications ADD business_owner NVARCHAR(256) NULL;
GO
IF COL_LENGTH('dbo.applications', 'criticality') IS NULL
    ALTER TABLE dbo.applications ADD criticality TINYINT       NULL;
GO
IF COL_LENGTH('dbo.applications', 'users') IS NULL
    ALTER TABLE dbo.applications ADD users INT           NULL;
GO
IF COL_LENGTH('dbo.applications', 'tech_stack') IS NULL
    ALTER TABLE dbo.applications ADD tech_stack NVARCHAR(512) NULL;
GO
IF COL_LENGTH('dbo.applications', 'db_engine') IS NULL
    ALTER TABLE dbo.applications ADD db_engine NVARCHAR(128) NULL;
GO
IF COL_LENGTH('dbo.applications', 'internet_facing') IS NULL
    ALTER TABLE dbo.applications ADD internet_facing BIT           NULL;
GO
IF COL_LENGTH('dbo.applications', 'compliance_scope') IS NULL
    ALTER TABLE dbo.applications ADD compliance_scope NVARCHAR(256) NULL;
GO
IF COL_LENGTH('dbo.applications', 'disposition') IS NULL
    ALTER TABLE dbo.applications ADD disposition NVARCHAR(32)  NULL;
GO
IF COL_LENGTH('dbo.applications', 'complexity') IS NULL
    ALTER TABLE dbo.applications ADD complexity NVARCHAR(8)   NULL;
GO
IF COL_LENGTH('dbo.applications', 'wave') IS NULL
    ALTER TABLE dbo.applications ADD wave INT           NULL;
GO
IF COL_LENGTH('dbo.applications', 'source_file') IS NULL
    ALTER TABLE dbo.applications ADD source_file NVARCHAR(260) NULL;
GO
IF COL_LENGTH('dbo.applications', 'ingested_at') IS NULL
    ALTER TABLE dbo.applications ADD ingested_at DATETIME2     NULL CONSTRAINT DF_applications_ingested DEFAULT SYSUTCDATETIME();
GO
GO

IF OBJECT_ID('dbo.servers', 'U') IS NULL
BEGIN
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
END;
GO
IF COL_LENGTH('dbo.servers', 'engagement_id') IS NULL
    THROW 51001, 'Incompatible schema: servers.engagement_id requires an explicit migration', 1;
GO
IF COL_LENGTH('dbo.servers', 'server_id') IS NULL
    THROW 51001, 'Incompatible schema: servers.server_id requires an explicit migration', 1;
GO
IF COL_LENGTH('dbo.servers', 'hostname') IS NULL
    ALTER TABLE dbo.servers ADD hostname NVARCHAR(256) NULL;
GO
IF COL_LENGTH('dbo.servers', 'env') IS NULL
    ALTER TABLE dbo.servers ADD env NVARCHAR(32)  NULL;
GO
IF COL_LENGTH('dbo.servers', 'os_name') IS NULL
    ALTER TABLE dbo.servers ADD os_name NVARCHAR(128) NULL;
GO
IF COL_LENGTH('dbo.servers', 'os_version') IS NULL
    ALTER TABLE dbo.servers ADD os_version NVARCHAR(64)  NULL;
GO
IF COL_LENGTH('dbo.servers', 'os_eol_date') IS NULL
    ALTER TABLE dbo.servers ADD os_eol_date DATE          NULL;
GO
IF COL_LENGTH('dbo.servers', 'vcpu') IS NULL
    ALTER TABLE dbo.servers ADD vcpu INT           NULL;
GO
IF COL_LENGTH('dbo.servers', 'ram_gb') IS NULL
    ALTER TABLE dbo.servers ADD ram_gb DECIMAL(9,2)  NULL;
GO
IF COL_LENGTH('dbo.servers', 'provisioned_disk_gb') IS NULL
    ALTER TABLE dbo.servers ADD provisioned_disk_gb DECIMAL(12,2) NULL;
GO
IF COL_LENGTH('dbo.servers', 'used_disk_gb') IS NULL
    ALTER TABLE dbo.servers ADD used_disk_gb DECIMAL(12,2) NULL;
GO
IF COL_LENGTH('dbo.servers', 'cpu_avg_pct') IS NULL
    ALTER TABLE dbo.servers ADD cpu_avg_pct DECIMAL(5,2)  NULL;
GO
IF COL_LENGTH('dbo.servers', 'cpu_peak_pct') IS NULL
    ALTER TABLE dbo.servers ADD cpu_peak_pct DECIMAL(5,2)  NULL;
GO
IF COL_LENGTH('dbo.servers', 'cpu_p95_pct') IS NULL
    ALTER TABLE dbo.servers ADD cpu_p95_pct DECIMAL(5,2)  NULL;
GO
IF COL_LENGTH('dbo.servers', 'ram_avg_pct') IS NULL
    ALTER TABLE dbo.servers ADD ram_avg_pct DECIMAL(5,2)  NULL;
GO
IF COL_LENGTH('dbo.servers', 'ram_p95_pct') IS NULL
    ALTER TABLE dbo.servers ADD ram_p95_pct DECIMAL(5,2)  NULL;
GO
IF COL_LENGTH('dbo.servers', 'disk_iops_avg') IS NULL
    ALTER TABLE dbo.servers ADD disk_iops_avg DECIMAL(12,2) NULL;
GO
IF COL_LENGTH('dbo.servers', 'disk_iops_peak') IS NULL
    ALTER TABLE dbo.servers ADD disk_iops_peak DECIMAL(12,2) NULL;
GO
IF COL_LENGTH('dbo.servers', 'net_in_gb_30d') IS NULL
    ALTER TABLE dbo.servers ADD net_in_gb_30d DECIMAL(14,2) NULL;
GO
IF COL_LENGTH('dbo.servers', 'net_out_gb_30d') IS NULL
    ALTER TABLE dbo.servers ADD net_out_gb_30d DECIMAL(14,2) NULL;
GO
IF COL_LENGTH('dbo.servers', 'cluster') IS NULL
    ALTER TABLE dbo.servers ADD cluster NVARCHAR(128) NULL;
GO
IF COL_LENGTH('dbo.servers', 'datacenter') IS NULL
    ALTER TABLE dbo.servers ADD datacenter NVARCHAR(128) NULL;
GO
IF COL_LENGTH('dbo.servers', 'powerstate') IS NULL
    ALTER TABLE dbo.servers ADD powerstate NVARCHAR(32)  NULL;
GO
IF COL_LENGTH('dbo.servers', 'app_id') IS NULL
    ALTER TABLE dbo.servers ADD app_id NVARCHAR(64)  NULL;
GO
IF COL_LENGTH('dbo.servers', 'notes') IS NULL
    ALTER TABLE dbo.servers ADD notes NVARCHAR(1024) NULL;
GO
IF COL_LENGTH('dbo.servers', 'source_file') IS NULL
    ALTER TABLE dbo.servers ADD source_file NVARCHAR(260) NULL;
GO
IF COL_LENGTH('dbo.servers', 'ingested_at') IS NULL
    ALTER TABLE dbo.servers ADD ingested_at DATETIME2     NULL CONSTRAINT DF_servers_ingested DEFAULT SYSUTCDATETIME();
GO
GO

IF OBJECT_ID('dbo.dependencies', 'U') IS NULL
BEGIN
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
END;
GO
IF COL_LENGTH('dbo.dependencies', 'dep_id') IS NULL
    THROW 51001, 'Incompatible schema: dependencies.dep_id requires an explicit migration', 1;
GO
IF COL_LENGTH('dbo.dependencies', 'engagement_id') IS NULL
    THROW 51001, 'Incompatible schema: dependencies.engagement_id requires an explicit migration', 1;
GO
IF COL_LENGTH('dbo.dependencies', 'src_id') IS NULL
    ALTER TABLE dbo.dependencies ADD src_id NVARCHAR(64)  NULL;
GO
IF COL_LENGTH('dbo.dependencies', 'dst_id') IS NULL
    ALTER TABLE dbo.dependencies ADD dst_id NVARCHAR(64)  NULL;
GO
IF COL_LENGTH('dbo.dependencies', 'port') IS NULL
    ALTER TABLE dbo.dependencies ADD port INT           NULL;
GO
IF COL_LENGTH('dbo.dependencies', 'protocol') IS NULL
    ALTER TABLE dbo.dependencies ADD protocol NVARCHAR(16)  NULL;
GO
IF COL_LENGTH('dbo.dependencies', 'direction') IS NULL
    ALTER TABLE dbo.dependencies ADD direction NVARCHAR(16)  NULL;
GO
IF COL_LENGTH('dbo.dependencies', 'confidence') IS NULL
    ALTER TABLE dbo.dependencies ADD confidence NVARCHAR(16)  NULL;
GO
IF COL_LENGTH('dbo.dependencies', 'bytes_30d_gb') IS NULL
    ALTER TABLE dbo.dependencies ADD bytes_30d_gb DECIMAL(14,2) NULL;
GO
IF COL_LENGTH('dbo.dependencies', 'flows_30d') IS NULL
    ALTER TABLE dbo.dependencies ADD flows_30d BIGINT        NULL;
GO
IF COL_LENGTH('dbo.dependencies', 'last_seen') IS NULL
    ALTER TABLE dbo.dependencies ADD last_seen DATE          NULL;
GO
IF COL_LENGTH('dbo.dependencies', 'source_file') IS NULL
    ALTER TABLE dbo.dependencies ADD source_file NVARCHAR(260) NULL;
GO
IF COL_LENGTH('dbo.dependencies', 'ingested_at') IS NULL
    ALTER TABLE dbo.dependencies ADD ingested_at DATETIME2     NULL CONSTRAINT DF_dependencies_ingested DEFAULT SYSUTCDATETIME();
GO
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id = OBJECT_ID('dbo.dependencies') AND name = 'IX_dependencies_engagement')
    CREATE INDEX IX_dependencies_engagement ON dbo.dependencies (engagement_id);
GO

-- Daily performance samples over a ~30-day observation window (one row per server per day).
-- servers.csv carries the rollups; this table is the series behind them.
IF OBJECT_ID('dbo.performance', 'U') IS NULL
BEGIN
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
END;
GO
IF COL_LENGTH('dbo.performance', 'perf_id') IS NULL
    THROW 51001, 'Incompatible schema: performance.perf_id requires an explicit migration', 1;
GO
IF COL_LENGTH('dbo.performance', 'engagement_id') IS NULL
    THROW 51001, 'Incompatible schema: performance.engagement_id requires an explicit migration', 1;
GO
IF COL_LENGTH('dbo.performance', 'server_id') IS NULL
    ALTER TABLE dbo.performance ADD server_id NVARCHAR(64)  NULL;
GO
IF COL_LENGTH('dbo.performance', 'sample_date') IS NULL
    ALTER TABLE dbo.performance ADD sample_date DATE          NULL;
GO
IF COL_LENGTH('dbo.performance', 'cpu_avg_pct') IS NULL
    ALTER TABLE dbo.performance ADD cpu_avg_pct DECIMAL(5,2)  NULL;
GO
IF COL_LENGTH('dbo.performance', 'cpu_peak_pct') IS NULL
    ALTER TABLE dbo.performance ADD cpu_peak_pct DECIMAL(5,2)  NULL;
GO
IF COL_LENGTH('dbo.performance', 'cpu_p95_pct') IS NULL
    ALTER TABLE dbo.performance ADD cpu_p95_pct DECIMAL(5,2)  NULL;
GO
IF COL_LENGTH('dbo.performance', 'mem_avg_pct') IS NULL
    ALTER TABLE dbo.performance ADD mem_avg_pct DECIMAL(5,2)  NULL;
GO
IF COL_LENGTH('dbo.performance', 'mem_peak_pct') IS NULL
    ALTER TABLE dbo.performance ADD mem_peak_pct DECIMAL(5,2)  NULL;
GO
IF COL_LENGTH('dbo.performance', 'mem_p95_pct') IS NULL
    ALTER TABLE dbo.performance ADD mem_p95_pct DECIMAL(5,2)  NULL;
GO
IF COL_LENGTH('dbo.performance', 'disk_iops_avg') IS NULL
    ALTER TABLE dbo.performance ADD disk_iops_avg DECIMAL(12,2) NULL;
GO
IF COL_LENGTH('dbo.performance', 'disk_iops_peak') IS NULL
    ALTER TABLE dbo.performance ADD disk_iops_peak DECIMAL(12,2) NULL;
GO
IF COL_LENGTH('dbo.performance', 'disk_read_iops_avg') IS NULL
    ALTER TABLE dbo.performance ADD disk_read_iops_avg DECIMAL(12,2) NULL;
GO
IF COL_LENGTH('dbo.performance', 'disk_write_iops_avg') IS NULL
    ALTER TABLE dbo.performance ADD disk_write_iops_avg DECIMAL(12,2) NULL;
GO
IF COL_LENGTH('dbo.performance', 'disk_throughput_mbps_avg') IS NULL
    ALTER TABLE dbo.performance ADD disk_throughput_mbps_avg DECIMAL(12,2) NULL;
GO
IF COL_LENGTH('dbo.performance', 'net_in_gb') IS NULL
    ALTER TABLE dbo.performance ADD net_in_gb DECIMAL(12,3) NULL;
GO
IF COL_LENGTH('dbo.performance', 'net_out_gb') IS NULL
    ALTER TABLE dbo.performance ADD net_out_gb DECIMAL(12,3) NULL;
GO
IF COL_LENGTH('dbo.performance', 'net_in_peak_mbps') IS NULL
    ALTER TABLE dbo.performance ADD net_in_peak_mbps DECIMAL(12,2) NULL;
GO
IF COL_LENGTH('dbo.performance', 'net_out_peak_mbps') IS NULL
    ALTER TABLE dbo.performance ADD net_out_peak_mbps DECIMAL(12,2) NULL;
GO
IF COL_LENGTH('dbo.performance', 'source_file') IS NULL
    ALTER TABLE dbo.performance ADD source_file NVARCHAR(260) NULL;
GO
IF COL_LENGTH('dbo.performance', 'ingested_at') IS NULL
    ALTER TABLE dbo.performance ADD ingested_at DATETIME2     NULL CONSTRAINT DF_performance_ingested DEFAULT SYSUTCDATETIME();
GO
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id = OBJECT_ID('dbo.performance') AND name = 'IX_performance_engagement')
    CREATE INDEX IX_performance_engagement ON dbo.performance (engagement_id);
GO

IF OBJECT_ID('dbo.storage', 'U') IS NULL
BEGIN
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
END;
GO
IF COL_LENGTH('dbo.storage', 'engagement_id') IS NULL
    THROW 51001, 'Incompatible schema: storage.engagement_id requires an explicit migration', 1;
GO
IF COL_LENGTH('dbo.storage', 'storage_id') IS NULL
    THROW 51001, 'Incompatible schema: storage.storage_id requires an explicit migration', 1;
GO
IF COL_LENGTH('dbo.storage', 'server_id') IS NULL
    ALTER TABLE dbo.storage ADD server_id NVARCHAR(64)  NULL;
GO
IF COL_LENGTH('dbo.storage', 'type') IS NULL
    ALTER TABLE dbo.storage ADD type NVARCHAR(16)  NULL;
GO
IF COL_LENGTH('dbo.storage', 'size_gb') IS NULL
    ALTER TABLE dbo.storage ADD size_gb DECIMAL(12,2) NULL;
GO
IF COL_LENGTH('dbo.storage', 'iops') IS NULL
    ALTER TABLE dbo.storage ADD iops INT           NULL;
GO
IF COL_LENGTH('dbo.storage', 'target_service') IS NULL
    ALTER TABLE dbo.storage ADD target_service NVARCHAR(128) NULL;
GO
IF COL_LENGTH('dbo.storage', 'source_file') IS NULL
    ALTER TABLE dbo.storage ADD source_file NVARCHAR(260) NULL;
GO
IF COL_LENGTH('dbo.storage', 'ingested_at') IS NULL
    ALTER TABLE dbo.storage ADD ingested_at DATETIME2     NULL CONSTRAINT DF_storage_ingested DEFAULT SYSUTCDATETIME();
GO
GO

-- One row per ingested file: what the Normalize pipeline detected, loaded, and flagged.
IF OBJECT_ID('dbo.ingest_log', 'U') IS NULL
BEGIN
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
END;
GO
IF COL_LENGTH('dbo.ingest_log', 'run_id') IS NULL
    THROW 51001, 'Incompatible schema: ingest_log.run_id requires an explicit migration', 1;
GO
IF COL_LENGTH('dbo.ingest_log', 'engagement_id') IS NULL
    THROW 51001, 'Incompatible schema: ingest_log.engagement_id requires an explicit migration', 1;
GO
IF COL_LENGTH('dbo.ingest_log', 'file_name') IS NULL
    ALTER TABLE dbo.ingest_log ADD file_name NVARCHAR(260) NULL;
GO
IF COL_LENGTH('dbo.ingest_log', 'profile') IS NULL
    ALTER TABLE dbo.ingest_log ADD profile NVARCHAR(64)  NULL;
GO
IF COL_LENGTH('dbo.ingest_log', 'target_table') IS NULL
    ALTER TABLE dbo.ingest_log ADD target_table NVARCHAR(64)  NULL;
GO
IF COL_LENGTH('dbo.ingest_log', 'rows_in') IS NULL
    ALTER TABLE dbo.ingest_log ADD rows_in INT           NULL;
GO
IF COL_LENGTH('dbo.ingest_log', 'rows_loaded') IS NULL
    ALTER TABLE dbo.ingest_log ADD rows_loaded INT           NULL;
GO
IF COL_LENGTH('dbo.ingest_log', 'rows_rejected') IS NULL
    ALTER TABLE dbo.ingest_log ADD rows_rejected INT           NULL;
GO
IF COL_LENGTH('dbo.ingest_log', 'status') IS NULL
    ALTER TABLE dbo.ingest_log ADD status NVARCHAR(64)  NULL;
GO
IF COL_LENGTH('dbo.ingest_log', 'dq_json') IS NULL
    ALTER TABLE dbo.ingest_log ADD dq_json NVARCHAR(MAX) NULL;
GO
IF COL_LENGTH('dbo.ingest_log', 'ingested_at') IS NULL
    ALTER TABLE dbo.ingest_log ADD ingested_at DATETIME2     NULL CONSTRAINT DF_ingestlog_ingested DEFAULT SYSUTCDATETIME();
GO
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id = OBJECT_ID('dbo.ingest_log') AND name = 'IX_ingestlog_engagement')
    CREATE INDEX IX_ingestlog_engagement ON dbo.ingest_log (engagement_id);
GO

-- ---------------------------------------------------------------------------
-- Row-Level Security: every read is scoped to SESSION_CONTEXT('engagement_id').
-- No context set  ->  the predicate returns no rows (fail closed). Callers set the
-- context with sp_set_session_context before running any SELECT (this is what makes
-- the free-form text-to-SQL in query_inventory tenant-safe regardless of the SQL the
-- model writes). INSERTs are unaffected (the loader writes engagement_id explicitly).
-- ---------------------------------------------------------------------------
IF OBJECT_ID('dbo.fn_engagement_predicate', 'IF') IS NULL
    EXEC(N'CREATE FUNCTION dbo.fn_engagement_predicate(@engagement_id AS NVARCHAR(120))
    RETURNS TABLE
    WITH SCHEMABINDING
AS
    RETURN SELECT 1 AS ok
           WHERE @engagement_id =
                 CAST(SESSION_CONTEXT(N''engagement_id'') AS NVARCHAR(120));');
GO

IF NOT EXISTS (SELECT 1 FROM sys.security_policies WHERE object_id = OBJECT_ID('dbo.EngagementFilter'))
BEGIN
CREATE SECURITY POLICY dbo.EngagementFilter
    ADD FILTER PREDICATE dbo.fn_engagement_predicate(engagement_id) ON dbo.servers,
    ADD FILTER PREDICATE dbo.fn_engagement_predicate(engagement_id) ON dbo.applications,
    ADD FILTER PREDICATE dbo.fn_engagement_predicate(engagement_id) ON dbo.dependencies,
    ADD FILTER PREDICATE dbo.fn_engagement_predicate(engagement_id) ON dbo.storage,
    ADD FILTER PREDICATE dbo.fn_engagement_predicate(engagement_id) ON dbo.performance,
    ADD FILTER PREDICATE dbo.fn_engagement_predicate(engagement_id) ON dbo.ingest_log
    WITH (STATE = ON);
END
ELSE
    ALTER SECURITY POLICY dbo.EngagementFilter WITH (STATE = ON);
GO

-- Fail closed if an existing policy was manually changed or incompletely created.
IF (SELECT COUNT(*) FROM sys.security_predicates
    WHERE object_id = OBJECT_ID('dbo.EngagementFilter') AND predicate_type = 0
      AND target_object_id IN (OBJECT_ID('dbo.servers'), OBJECT_ID('dbo.applications'),
          OBJECT_ID('dbo.dependencies'), OBJECT_ID('dbo.storage'),
          OBJECT_ID('dbo.performance'), OBJECT_ID('dbo.ingest_log'))) <> 6
    THROW 51003, 'EngagementFilter does not protect all inventory tables', 1;
GO

-- Read-only + read-write login for the workload identity is granted in scripts/apply_sql.py
-- (contained user mapped to the workload managed identity - name passed in by the script).
