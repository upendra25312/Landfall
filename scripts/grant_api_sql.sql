-- Landfall: give the workload managed identity read-only access to the inventory.
-- The `query_inventory` tool (src/api/tools.py) connects as this identity and runs
-- SELECT-only queries. Run by the postprovision hook after schema.sql:
--   sqlcmd ... -v uami="id-landfall-xxxx" uamioid="<identity object id>" -i grant_api_sql.sql
--
-- WITH OBJECT_ID avoids needing the SQL server identity to hold Directory Readers.
-- Idempotent.

IF NOT EXISTS (SELECT 1 FROM sys.database_principals WHERE name = N'$(uami)')
BEGIN
    CREATE USER [$(uami)] FROM EXTERNAL PROVIDER WITH OBJECT_ID = '$(uamioid)';
END
GO

ALTER ROLE db_datareader ADD MEMBER [$(uami)];
GO
