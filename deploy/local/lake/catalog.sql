SET allow_experimental_database_iceberg = 1;
CREATE DATABASE IF NOT EXISTS lake
ENGINE = DataLakeCatalog('http://lake:8181/v1', 'ledger-local', 'local-lake-only')
SETTINGS catalog_type = 'rest', warehouse = 's3://ledger-lake',
 storage_endpoint = 'http://lake:8333/ledger-lake',
 catalog_credential = 'ledger-local:local-lake-only',
 oauth_server_uri = 'http://lake:8181/v1/oauth/tokens';
