-- Landfall inventory schema (Azure SQL - Free offer)
-- Nullable throughout: client-supplied inventory always has gaps.

IF OBJECT_ID('dbo.dependencies', 'U') IS NOT NULL DROP TABLE dbo.dependencies;
IF OBJECT_ID('dbo.storage', 'U')      IS NOT NULL DROP TABLE dbo.storage;
IF OBJECT_ID('dbo.servers', 'U')      IS NOT NULL DROP TABLE dbo.servers;
IF OBJECT_ID('dbo.applications', 'U') IS NOT NULL DROP TABLE dbo.applications;
GO

CREATE TABLE dbo.applications (
    app_id          NVARCHAR(64)  NOT NULL PRIMARY KEY,
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
    wave            INT           NULL            -- (agent-filled)
);
GO

CREATE TABLE dbo.servers (
    server_id           NVARCHAR(64)  NOT NULL PRIMARY KEY,
    hostname            NVARCHAR(256) NULL,
    env                 NVARCHAR(32)  NULL,       -- prod/nonprod/dev/dr
    os_name             NVARCHAR(128) NULL,
    os_version          NVARCHAR(64)  NULL,
    os_eol_date         DATE          NULL,
    vcpu                INT           NULL,
    ram_gb              DECIMAL(9,2)  NULL,
    provisioned_disk_gb DECIMAL(12,2) NULL,
    used_disk_gb        DECIMAL(12,2) NULL,
    cpu_avg_pct         DECIMAL(5,2)  NULL,
    cpu_peak_pct        DECIMAL(5,2)  NULL,
    ram_avg_pct         DECIMAL(5,2)  NULL,
    cluster             NVARCHAR(128) NULL,
    datacenter          NVARCHAR(128) NULL,
    powerstate          NVARCHAR(32)  NULL,
    app_id              NVARCHAR(64)  NULL REFERENCES dbo.applications(app_id),
    notes               NVARCHAR(1024) NULL
);
GO

CREATE TABLE dbo.dependencies (
    dep_id      INT IDENTITY(1,1) PRIMARY KEY,
    src_id      NVARCHAR(64)  NULL,
    dst_id      NVARCHAR(64)  NULL,
    port        INT           NULL,
    protocol    NVARCHAR(16)  NULL,
    direction   NVARCHAR(16)  NULL,
    confidence  NVARCHAR(16)  NULL
);
GO

CREATE TABLE dbo.storage (
    storage_id     NVARCHAR(64)  NOT NULL PRIMARY KEY,
    server_id      NVARCHAR(64)  NULL REFERENCES dbo.servers(server_id),
    type           NVARCHAR(16)  NULL,            -- block/file/object/db
    size_gb        DECIMAL(12,2) NULL,
    iops           INT           NULL,
    target_service NVARCHAR(128) NULL
);
GO

-- Read-only login for the query_inventory tool is created here too.
-- (contained user mapped to the workload managed identity - name passed in by the script)
