SET allow_experimental_database_iceberg = 1;
CREATE DATABASE IF NOT EXISTS probe
ENGINE = DataLakeCatalog('http://catalog:8181/catalog', 'ledger-local', 'local-lake-only')
SETTINGS catalog_type = 'rest', warehouse = 'ledger-probe',
 storage_endpoint = 'http://lake:8333/catalog-data';
SHOW TABLES FROM probe;
SELECT count() FROM probe.`probe.batches`;
