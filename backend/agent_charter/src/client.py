"""
Database Client supporting both Aurora Data API and PostgreSQL RDS
Provides a unified interface for database operations
"""

import boto3
import json
import os
import sqlalchemy as sa
from sqlalchemy import text, MetaData
from typing import List, Dict, Any, Optional, Tuple
from datetime import date, datetime
from decimal import Decimal
from botocore.exceptions import ClientError
from contextlib import contextmanager
import logging

# Try to load .env file if it exists
try:
    from dotenv import load_dotenv
    load_dotenv(override=True)
except ImportError:
    pass  # dotenv not installed, continue without it

logger = logging.getLogger(__name__)


class DataAPIClient:
    """Database client supporting both Aurora Data API and PostgreSQL RDS"""

    def __init__(
        self,
        db_backend: str = None,
        cluster_arn: str = None,
        secret_arn: str = None,
        database: str = None,
        region: str = None,
        database_uri: str = None,
        schema: str = "alex",
    ):
        """
        Initialize database client based on backend type

        Args:
            db_backend: Backend type - 'aurora' or 'postgres' (or from env DB_BACKEND)
            cluster_arn: Aurora cluster ARN (or from env AURORA_CLUSTER_ARN)
            secret_arn: Secrets Manager ARN (or from env AURORA_SECRET_ARN)
            database: Database name (or from env AURORA_DATABASE)
            region: AWS region (or from env AWS_REGION)
            database_uri: PostgreSQL connection string (or from env SQLALCHEMY_DATABASE_URI)
            schema: Schema name for PostgreSQL (defaults to 'alex')
        """
        self.db_backend = (db_backend or os.environ.get("DB_BACKEND", "aurora")).lower()
        self.schema = schema
        
        if self.db_backend == 'aurora':
            self.cluster_arn = cluster_arn or os.environ.get("AURORA_CLUSTER_ARN")
            self.secret_arn = secret_arn or os.environ.get("AURORA_SECRET_ARN")
            self.database = database or os.environ.get("AURORA_DATABASE", "alex")

            if not self.cluster_arn or not self.secret_arn:
                raise ValueError(
                    "Missing required Aurora configuration. "
                    "Set AURORA_CLUSTER_ARN and AURORA_SECRET_ARN environment variables."
                )

            self.region = os.environ.get("DEFAULT_AWS_REGION", "us-east-1")
            self.client = boto3.client("rds-data", region_name=self.region)
            
            # Check if Aurora is using PostgreSQL engine
            self._uses_postgres_syntax = self._check_aurora_engine()
            
        elif self.db_backend == 'postgres':
            self.database_uri = database_uri or os.environ.get("SQLALCHEMY_DATABASE_URI")

            if not self.database_uri:
                raise ValueError(
                    "Missing required PostgreSQL configuration. "
                    "Set SQLALCHEMY_DATABASE_URI environment variable."
                )

            # Create SQLAlchemy engine
            self.engine = sa.create_engine(self.database_uri)
            self.metadata = MetaData(schema=self.schema)
            self._uses_postgres_syntax = True
            
        else:
            raise ValueError("Unsupported DB_BACKEND. Use 'aurora' or 'postgres'.")

    def _check_aurora_engine(self) -> bool:
        """Check if Aurora cluster is using PostgreSQL engine"""
        try:
            # Try to execute a PostgreSQL-specific query to test the engine
            response = self.client.execute_statement(
                resourceArn=self.cluster_arn,
                secretArn=self.secret_arn,
                database=self.database,
                sql="SELECT version()"
            )
            if response.get('records'):
                version_info = response['records'][0][0].get('stringValue', '')
                return 'PostgreSQL' in version_info
        except Exception:
            pass
        return False

    def execute(self, sql: str, parameters: List[Dict] = None) -> Dict:
        """
        Execute a SQL statement

        Args:
            sql: SQL statement to execute
            parameters: Optional list of parameters for prepared statement

        Returns:
            Response dict with records and metadata (compatible with Data API format)
        """
        if self.db_backend == 'aurora':
            return self._execute_aurora(sql, parameters)
        elif self.db_backend == 'postgres':
            return self._execute_postgres(sql, parameters)
    
    def _execute_aurora(self, sql: str, parameters: List[Dict] = None) -> Dict:
        """Execute SQL using Aurora Data API"""
        try:
            kwargs = {
                "resourceArn": self.cluster_arn,
                "secretArn": self.secret_arn,
                "database": self.database,
                "sql": sql,
                "includeResultMetadata": True,  # Include column names
            }

            if parameters:
                kwargs["parameters"] = parameters

            response = self.client.execute_statement(**kwargs)
            return response

        except ClientError as e:
            logger.error(f"Database error: {e}")
            raise
    
    def _execute_postgres(self, sql: str, parameters: List[Dict] = None) -> Dict:
        """Execute SQL using PostgreSQL with SQLAlchemy"""
        # Add schema prefix to table names if not present
        sql = self._add_schema_prefix(sql)
        
        try:
            with self.engine.connect() as conn:
                with conn.begin():  # Explicitly use a transaction
                    # Convert parameter format from Data API format if needed
                    if parameters and isinstance(parameters, list):
                        # Convert from Data API format to simple dict
                        param_dict = {}
                        for param in parameters:
                            name = param.get("name")
                            value = self._extract_data_api_value(param.get("value", {}))
                            param_dict[name] = value
                        parameters = param_dict

                    # Execute with text() for SQLAlchemy 2.0 compatibility
                    result = conn.execute(text(sql), parameters or {})
                    
                    # Format response to match Data API format
                    response = {"records": [], "columnMetadata": []}
                    
                    if result.returns_rows:
                        # Get column metadata
                        columns = list(result.keys())
                        response["columnMetadata"] = [{"name": col} for col in columns]
                        
                        # Get records
                        rows = result.fetchall()
                        for row in rows:
                            record = []
                            for value in row:
                                record.append(self._format_value_for_data_api(value))
                            response["records"].append(record)
                    else:
                        response["numberOfRecordsUpdated"] = result.rowcount

                    return response

        except Exception as e:
            logger.error(f"Database error: {e}")
            raise

    def query(self, sql: str, parameters: List[Dict] = None) -> List[Dict]:
        """
        Execute a SELECT query and return results as list of dicts

        Args:
            sql: SELECT statement
            parameters: Optional parameters

        Returns:
            List of dictionaries with column names as keys
        """
        response = self.execute(sql, parameters)

        if "records" not in response:
            return []

        # Extract column names
        columns = [col["name"] for col in response.get("columnMetadata", [])]

        # Convert records to dictionaries
        results = []
        for record in response["records"]:
            row = {}
            for i, col in enumerate(columns):
                value = self._extract_value(record[i])
                row[col] = value
            results.append(row)

        return results

    def query_one(self, sql: str, parameters: List[Dict] = None) -> Optional[Dict]:
        """
        Execute a SELECT query and return first result

        Args:
            sql: SELECT statement
            parameters: Optional parameters

        Returns:
            Dictionary with column names as keys, or None if no results
        """
        results = self.query(sql, parameters)
        return results[0] if results else None

    def insert(self, table: str, data: Dict, returning: str = None) -> str:
        """
        Insert a record into a table

        Args:
            table: Table name (will be prefixed with schema for PostgreSQL)
            data: Dictionary of column names and values
            returning: Column to return (e.g., 'id', 'clerk_user_id')

        Returns:
            Value of returning column if specified
        """
        # Map of tables to their JSONB columns (needed for proper casting)
        jsonb_columns = {
            "instruments": {"allocation_regions", "allocation_sectors", "allocation_asset_class"},
            "users": {"asset_class_targets", "region_targets"},
            "jobs": {"request_payload", "report_payload", "charts_payload", "retirement_payload", "summary_payload"},
            # Add other tables with JSONB columns as needed
        }
        table_jsonb_cols = jsonb_columns.get(table, set())
        
        if self.db_backend == 'postgres':
            # Add schema prefix to table name for PostgreSQL
            full_table = f"{self.schema}.{table}"
            # Convert dict values to JSON strings for JSONB columns
            processed_data = self._process_jsonb_params(table, data)
            columns = list(processed_data.keys())
            placeholders = []
            # Use CAST syntax for PostgreSQL with SQLAlchemy
            for col in columns:
                if col in table_jsonb_cols:
                    # This column should be cast as JSONB (it's now a JSON string after processing)
                    placeholders.append(f"CAST(:{col} AS jsonb)")
                elif isinstance(processed_data[col], Decimal):
                    placeholders.append(f"CAST(:{col} AS numeric)")
                elif isinstance(processed_data[col], date) and not isinstance(processed_data[col], datetime):
                    placeholders.append(f"CAST(:{col} AS date)")
                elif isinstance(processed_data[col], datetime):
                    placeholders.append(f"CAST(:{col} AS timestamp)")
                else:
                    placeholders.append(f":{col}")
        else:
            # Aurora doesn't use schema prefix but still needs JSONB processing
            full_table = table
            processed_data = self._process_jsonb_params(table, data)
            columns = list(processed_data.keys())
            placeholders = []
            # Check if columns need type casting for Aurora (uses :: syntax)
            for col in columns:
                if col in table_jsonb_cols:
                    # This column should be cast as JSONB (it's now a JSON string after processing)
                    placeholders.append(f":{col}::jsonb")
                elif isinstance(processed_data[col], Decimal):
                    placeholders.append(f":{col}::numeric")
                elif isinstance(processed_data[col], date) and not isinstance(processed_data[col], datetime):
                    placeholders.append(f":{col}::date")
                elif isinstance(processed_data[col], datetime):
                    placeholders.append(f":{col}::timestamp")
                else:
                    placeholders.append(f":{col}")

        sql = f"""
            INSERT INTO {full_table} ({", ".join(columns)})
            VALUES ({", ".join(placeholders)})
        """

        # Add RETURNING clause if specified
        if returning:
            sql += f" RETURNING {returning}"

        if self.db_backend == 'aurora':
            parameters = self._build_parameters(processed_data)
        else:
            parameters = processed_data

        response = self.execute(sql, parameters)

        # Return value if RETURNING was used
        if returning and response.get("records"):
            return self._extract_value(response["records"][0][0])
        return None

    def update(self, table: str, data: Dict, where: str, where_params: Dict = None) -> int:
        """
        Update records in a table

        Args:
            table: Table name
            data: Dictionary of columns to update
            where: WHERE clause (without WHERE keyword)
            where_params: Parameters for WHERE clause

        Returns:
            Number of affected rows
        """
        # Always process JSONB parameters for both PostgreSQL and Aurora (which uses PostgreSQL engine)
        print(f"🔧 DATABASE DEBUG: Original data: {data}")
        
        # Map of tables to their JSONB columns (needed for proper casting)
        jsonb_columns = {
            "instruments": {"allocation_regions", "allocation_sectors", "allocation_asset_class"},
            "users": {"asset_class_targets", "region_targets"},
            "jobs": {"request_payload", "report_payload", "charts_payload", "retirement_payload", "summary_payload"},
            # Add other tables with JSONB columns as needed
        }
        table_jsonb_cols = jsonb_columns.get(table, set())
        
        data = self._process_jsonb_params(table, data)
        print(f"🔧 DATABASE DEBUG: After JSONB processing: {data}")
        
        if self._uses_postgres_syntax:
            # Build SET clause with type casting where needed
            set_parts = []
            for col, val in data.items():
                if col in table_jsonb_cols:
                    # This column should be cast as JSONB (it's now a JSON string after processing)
                    set_parts.append(f"{col} = CAST(:{col} AS jsonb)")
                elif isinstance(val, Decimal):
                    set_parts.append(f"{col} = CAST(:{col} AS numeric)")
                elif isinstance(val, date) and not isinstance(val, datetime):
                    set_parts.append(f"{col} = CAST(:{col} AS date)")
                elif isinstance(val, datetime):
                    set_parts.append(f"{col} = CAST(:{col} AS timestamp)")
                else:
                    set_parts.append(f"{col} = :{col}")

            set_clause = ", ".join(set_parts)
            
            # Only add schema prefix for standalone PostgreSQL, not Aurora
            if self.db_backend == 'postgres':
                table_with_schema = f"{self.schema}.{table}"
                sql = f"""
                    UPDATE {table_with_schema}
                    SET {set_clause}
                    WHERE {where}
                """
                # Add schema prefix to WHERE clause if needed
                sql = self._add_schema_prefix(sql)
            else:
                # Aurora with PostgreSQL engine
                sql = f"""
                    UPDATE {table}
                    SET {set_clause}
                    WHERE {where}
                """
            
        else:  # Aurora
            # Build SET clause (Aurora doesn't need type casting)
            set_parts = []
            for col in data.keys():
                set_parts.append(f"{col} = :{col}")

            set_clause = ", ".join(set_parts)

            sql = f"""
                UPDATE {table}
                SET {set_clause}
                WHERE {where}
            """

        # Combine data and where parameters
        all_params = {**data, **(where_params or {})}
        parameters = self._build_parameters(all_params)

        response = self.execute(sql, parameters)
        return response.get("numberOfRecordsUpdated", 0)

    def delete(self, table: str, where: str, where_params: Dict = None) -> int:
        """
        Delete records from a table

        Args:
            table: Table name
            where: WHERE clause (without WHERE keyword)
            where_params: Parameters for WHERE clause

        Returns:
            Number of deleted rows
        """
        if self.db_backend == 'postgres':
            # Add schema prefix for standalone PostgreSQL only
            table_with_schema = f"{self.schema}.{table}"
            sql = f"DELETE FROM {table_with_schema} WHERE {where}"
            # Add schema prefix to WHERE clause if needed
            sql = self._add_schema_prefix(sql)
        else:  # Aurora (with or without PostgreSQL engine)
            sql = f"DELETE FROM {table} WHERE {where}"
            
        parameters = self._build_parameters(where_params) if where_params else None

        response = self.execute(sql, parameters)
        return response.get("numberOfRecordsUpdated", 0)

    def begin_transaction(self) -> str:
        """Begin a database transaction"""
        if self._uses_postgres_syntax:
            # PostgreSQL uses SQLAlchemy transactions
            # Return a dummy transaction ID for compatibility
            return "postgres_transaction"
        else:  # Aurora
            response = self.client.begin_transaction(
                resourceArn=self.cluster_arn, secretArn=self.secret_arn, database=self.database
            )
            return response["transactionId"]

    def commit_transaction(self, transaction_id: str):
        """Commit a database transaction"""
        if self._uses_postgres_syntax:
            # PostgreSQL transactions are handled by SQLAlchemy connection
            # This is a no-op for compatibility
            pass
        else:  # Aurora
            self.client.commit_transaction(
                resourceArn=self.cluster_arn, secretArn=self.secret_arn, transactionId=transaction_id
            )

    def rollback_transaction(self, transaction_id: str):
        """Rollback a database transaction"""
        if self._uses_postgres_syntax:
            # PostgreSQL transactions are handled by SQLAlchemy connection
            # This is a no-op for compatibility
            pass
        else:  # Aurora
            self.client.rollback_transaction(
                resourceArn=self.cluster_arn, secretArn=self.secret_arn, transactionId=transaction_id
            )

    def _build_parameters(self, data: Dict) -> List[Dict]:
        """Convert dictionary to Data API parameter format"""
        if not data:
            return []

        parameters = []
        for key, value in data.items():
            param = {"name": key}

            if value is None:
                param["value"] = {"isNull": True}
            elif isinstance(value, bool):
                param["value"] = {"booleanValue": value}
            elif isinstance(value, int):
                param["value"] = {"longValue": value}
            elif isinstance(value, float):
                param["value"] = {"doubleValue": value}
            elif isinstance(value, Decimal):
                param["value"] = {"stringValue": str(value)}
            elif isinstance(value, (date, datetime)):
                param["value"] = {"stringValue": value.isoformat()}
            elif isinstance(value, dict):
                param["value"] = {"stringValue": json.dumps(value)}
            elif isinstance(value, list):
                param["value"] = {"stringValue": json.dumps(value)}
            else:
                param["value"] = {"stringValue": str(value)}

            parameters.append(param)

        return parameters

    def _add_schema_prefix(self, sql: str) -> str:
        """Add schema prefix to table names in SQL if not already present"""
        # Only add schema prefix for PostgreSQL backend
        if self.db_backend != 'postgres':
            return sql
            
        # This is a simple implementation - for production you might want a more sophisticated parser
        table_names = ["users", "instruments", "accounts", "positions", "jobs"]
        
        for table in table_names:
            # Skip if table already has schema prefix
            if f"{self.schema}.{table}" in sql:
                continue
                
            # Replace various SQL patterns
            sql = sql.replace(f" {table} ", f" {self.schema}.{table} ")
            sql = sql.replace(f" {table}(", f" {self.schema}.{table}(")
            sql = sql.replace(f"FROM {table}", f"FROM {self.schema}.{table}")
            sql = sql.replace(f"UPDATE {table}", f"UPDATE {self.schema}.{table}")
            sql = sql.replace(f"INSERT INTO {table}", f"INSERT INTO {self.schema}.{table}")
            sql = sql.replace(f"DELETE FROM {table}", f"DELETE FROM {self.schema}.{table}")
            sql = sql.replace(f"DROP TABLE IF EXISTS {table}", f"DROP TABLE IF EXISTS {self.schema}.{table}")
            sql = sql.replace(f"DROP TABLE {table}", f"DROP TABLE {self.schema}.{table}")
            sql = sql.replace(f"ALTER TABLE {table}", f"ALTER TABLE {self.schema}.{table}")
            sql = sql.replace(f"TRUNCATE {table}", f"TRUNCATE {self.schema}.{table}")
            sql = sql.replace(f"JOIN {table}", f"JOIN {self.schema}.{table}")
            sql = sql.replace(f"INNER JOIN {table}", f"INNER JOIN {self.schema}.{table}")
            sql = sql.replace(f"LEFT JOIN {table}", f"LEFT JOIN {self.schema}.{table}")
            sql = sql.replace(f"RIGHT JOIN {table}", f"RIGHT JOIN {self.schema}.{table}")
            sql = sql.replace(f"FULL JOIN {table}", f"FULL JOIN {self.schema}.{table}")
            # Handle table names at the end of statements
            sql = sql.replace(f" {table};", f" {self.schema}.{table};")
            sql = sql.replace(f" {table}\n", f" {self.schema}.{table}\n")
            
        return sql

    def _process_jsonb_params(self, table: str, data: Dict) -> Dict:
        """Convert dictionary values to JSON strings for JSONB columns"""
        try:
            # print(f"🔧 JSONB DEBUG: Processing table '{table}' with data keys: {list(data.keys())}")
            
            # Map of tables to their JSONB columns
            jsonb_columns = {
                "instruments": {"allocation_regions", "allocation_sectors", "allocation_asset_class"},
                "users": {"asset_class_targets", "region_targets"},
                "jobs": {"request_payload", "report_payload", "charts_payload", "retirement_payload", "summary_payload"},
                # Add other tables with JSONB columns as needed
            }
            
            processed_data = {}
            table_jsonb_cols = jsonb_columns.get(table, set())
            # print(f"🔧 JSONB DEBUG: JSONB columns for table '{table}': {table_jsonb_cols}")
            
            for key, value in data.items():
                try:
                    if key in table_jsonb_cols and isinstance(value, dict):
                        # Convert dict to JSON string for JSONB columns
                        json_string = json.dumps(value)
                        processed_data[key] = json_string
                    else:
                        processed_data[key] = value
                 
                except Exception as e:
                 
                    processed_data[key] = value  # Fallback to original value
                    
            
            return processed_data
            
        except Exception as e:
            print(f"🔧 JSONB DEBUG: Fatal error in _process_jsonb_params: {e}")
            return data  # Return original data as fallback

    def _extract_data_api_value(self, field: Dict) -> Any:
        """Extract value from Data API parameter format"""
        if field.get("isNull"):
            return None
        elif "booleanValue" in field:
            return field["booleanValue"]
        elif "longValue" in field:
            return field["longValue"]
        elif "doubleValue" in field:
            return field["doubleValue"]
        elif "stringValue" in field:
            return field["stringValue"]
        else:
            return None

    def _format_value_for_data_api(self, value: Any) -> Dict:
        """Format value to match Data API response format"""
        if value is None:
            return {"isNull": True}
        elif isinstance(value, bool):
            return {"booleanValue": value}
        elif isinstance(value, int):
            return {"longValue": value}
        elif isinstance(value, float):
            return {"doubleValue": value}
        elif isinstance(value, Decimal):
            return {"stringValue": str(value)}
        elif isinstance(value, (date, datetime)):
            return {"stringValue": value.isoformat()}
        elif isinstance(value, (dict, list)):
            return {"stringValue": json.dumps(value)}
        else:
            return {"stringValue": str(value)}

    def _extract_value(self, field: Dict) -> Any:
        """Extract value from Data API field response"""
        if field.get("isNull"):
            return None
        elif "booleanValue" in field:
            return field["booleanValue"]
        elif "longValue" in field:
            return field["longValue"]
        elif "doubleValue" in field:
            return field["doubleValue"]
        elif "stringValue" in field:
            value = field["stringValue"]
            # Try to parse JSON if it looks like JSON
            if value and value[0] in ["{", "["]:
                try:
                    return json.loads(value)
                except json.JSONDecodeError:
                    pass
            return value
        elif "blobValue" in field:
            return field["blobValue"]
        else:
            return None
