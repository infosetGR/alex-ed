"""
SQLAlchemy-based database client
Provides a simple interface for database operations using PostgreSQL
"""

import os
import json
import sqlalchemy as sa
from sqlalchemy import text, MetaData
from typing import List, Dict, Any, Optional, Tuple
from datetime import date, datetime
from decimal import Decimal
from contextlib import contextmanager
import logging

# Try to load .env file if it exists
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv not installed, continue without it

logger = logging.getLogger(__name__)


class DataAPIClient:
    """SQLAlchemy-based client to replace AWS RDS Data API"""

    def __init__(
        self,
        database_uri: str = None,
        schema: str = "alex",
    ):
        """
        Initialize SQLAlchemy client

        Args:
            database_uri: Database connection string (or from env SQLALCHEMY_DATABASE_URI)
            schema: Schema name to use (defaults to 'alex')
        """
        self.database_uri = database_uri or os.environ.get("SQLALCHEMY_DATABASE_URI")
        self.schema = schema

        if not self.database_uri:
            raise ValueError(
                "Missing required database configuration. "
                "Set SQLALCHEMY_DATABASE_URI environment variable."
            )

        # Create SQLAlchemy engine
        self.engine = sa.create_engine(self.database_uri)
        self.metadata = MetaData(schema=self.schema)

    def execute(self, sql: str, parameters: Dict = None) -> Dict:
        """
        Execute a SQL statement

        Args:
            sql: SQL statement to execute
            parameters: Optional dictionary of parameters for prepared statement

        Returns:
            Response dict with records and metadata (compatible with Data API format)
        """
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

    def query(self, sql: str, parameters: Dict = None) -> List[Dict]:
        """
        Execute a SELECT query and return results as list of dicts

        Args:
            sql: SELECT statement  
            parameters: Optional parameters

        Returns:
            List of dictionaries with column names as keys
        """
        # Add schema prefix to table names if not present
        sql = self._add_schema_prefix(sql)
        
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

    def query_one(self, sql: str, parameters: Dict = None) -> Optional[Dict]:
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
            table: Table name (will be prefixed with schema)
            data: Dictionary of column names and values
            returning: Column to return (e.g., 'id', 'clerk_user_id')

        Returns:
            Value of returning column if specified
        """
        # Add schema prefix to table name
        full_table = f"{self.schema}.{table}"
        
        # Convert dict values to JSON strings for JSONB columns
        processed_data = self._process_jsonb_params(table, data)
        
        columns = list(processed_data.keys())
        placeholders = [f":{col}" for col in columns]

        sql = f"""
            INSERT INTO {full_table} ({", ".join(columns)})
            VALUES ({", ".join(placeholders)})
        """

        # Add RETURNING clause if specified
        if returning:
            sql += f" RETURNING {returning}"

        response = self.execute(sql, processed_data)

        # Return value if RETURNING was used
        if returning and response.get("records"):
            return self._extract_value(response["records"][0][0])
        return None

    def update(self, table: str, data: Dict, where: str, where_params: Dict = None) -> int:
        """
        Update records in a table

        Args:
            table: Table name (will be prefixed with schema)
            data: Dictionary of columns to update
            where: WHERE clause (without WHERE keyword)
            where_params: Parameters for WHERE clause

        Returns:
            Number of affected rows
        """
        # Add schema prefix to table name
        full_table = f"{self.schema}.{table}"
        
        # Convert dict values to JSON strings for JSONB columns
        processed_data = self._process_jsonb_params(table, data)
        
        # Build SET clause
        set_parts = [f"{col} = :{col}" for col in processed_data.keys()]
        set_clause = ", ".join(set_parts)

        sql = f"""
            UPDATE {full_table}
            SET {set_clause}
            WHERE {where}
        """

        # Combine data and where parameters
        all_params = {**processed_data, **(where_params or {})}

        response = self.execute(sql, all_params)
        return response.get("numberOfRecordsUpdated", 0)

    def delete(self, table: str, where: str, where_params: Dict = None) -> int:
        """
        Delete records from a table

        Args:
            table: Table name (will be prefixed with schema)
            where: WHERE clause (without WHERE keyword)
            where_params: Parameters for WHERE clause

        Returns:
            Number of deleted rows
        """
        # Add schema prefix to table name
        full_table = f"{self.schema}.{table}"
        
        sql = f"DELETE FROM {full_table} WHERE {where}"

        response = self.execute(sql, where_params)
        return response.get("numberOfRecordsUpdated", 0)

    @contextmanager
    def transaction(self):
        """Context manager for database transactions"""
        with self.engine.connect() as conn:
            trans = conn.begin()
            try:
                # Temporarily override execute to use this connection
                old_execute = self.execute
                
                def execute_in_transaction(sql: str, parameters: Dict = None):
                    if parameters and isinstance(parameters, list):
                        # Convert from Data API format to simple dict
                        param_dict = {}
                        for param in parameters:
                            name = param.get("name")
                            value = self._extract_data_api_value(param.get("value", {}))
                            param_dict[name] = value
                        parameters = param_dict

                    result = conn.execute(text(sql), parameters or {})
                    
                    response = {"records": [], "columnMetadata": []}
                    
                    if result.returns_rows:
                        columns = list(result.keys())
                        response["columnMetadata"] = [{"name": col} for col in columns]
                        
                        rows = result.fetchall()
                        for row in rows:
                            record = []
                            for value in row:
                                record.append(self._format_value_for_data_api(value))
                            response["records"].append(record)
                    else:
                        response["numberOfRecordsUpdated"] = result.rowcount

                    return response
                
                self.execute = execute_in_transaction
                yield conn
                trans.commit()
            except Exception:
                trans.rollback()
                raise
            finally:
                self.execute = old_execute

    def begin_transaction(self) -> str:
        """Begin a database transaction (compatibility method)"""
        # Return a dummy transaction ID for compatibility
        return "transaction_id"

    def commit_transaction(self, transaction_id: str):
        """Commit a database transaction (compatibility method)"""
        # No-op in SQLAlchemy mode - use transaction() context manager instead
        pass

    def rollback_transaction(self, transaction_id: str):
        """Rollback a database transaction (compatibility method)"""
        # No-op in SQLAlchemy mode - use transaction() context manager instead
        pass

    def _add_schema_prefix(self, sql: str) -> str:
        """Add schema prefix to table names in SQL if not already present"""
        # This is a simple implementation - for production you might want a more sophisticated parser
        table_names = ["users", "instruments", "accounts", "positions", "jobs"]
        
        for table in table_names:
            # Only add schema if table name appears without schema prefix
            sql = sql.replace(f" {table} ", f" {self.schema}.{table} ")
            sql = sql.replace(f" {table}(", f" {self.schema}.{table}(")
            sql = sql.replace(f"FROM {table}", f"FROM {self.schema}.{table}")
            sql = sql.replace(f"UPDATE {table}", f"UPDATE {self.schema}.{table}")
            sql = sql.replace(f"INSERT INTO {table}", f"INSERT INTO {self.schema}.{table}")
            sql = sql.replace(f"DELETE FROM {table}", f"DELETE FROM {self.schema}.{table}")
            sql = sql.replace(f"JOIN {table}", f"JOIN {self.schema}.{table}")
            sql = sql.replace(f"INNER JOIN {table}", f"INNER JOIN {self.schema}.{table}")
            sql = sql.replace(f"LEFT JOIN {table}", f"LEFT JOIN {self.schema}.{table}")
            sql = sql.replace(f"RIGHT JOIN {table}", f"RIGHT JOIN {self.schema}.{table}")
            sql = sql.replace(f"FULL JOIN {table}", f"FULL JOIN {self.schema}.{table}")
            
        return sql

    def _process_jsonb_params(self, table: str, data: Dict) -> Dict:
        """Convert dictionary values to JSON strings for JSONB columns"""
        # Map of tables to their JSONB columns
        jsonb_columns = {
            "instruments": {"allocation_regions", "allocation_sectors", "allocation_asset_class"},
            "users": {"region_targets"},
            "jobs": {"request_payload", "report_payload", "charts_payload", "retirement_payload", "summary_payload"},
            # Add other tables with JSONB columns as needed
        }
        
        processed_data = {}
        table_jsonb_cols = jsonb_columns.get(table, set())
        
        for key, value in data.items():
            if key in table_jsonb_cols and isinstance(value, dict):
                # Convert dict to JSON string for JSONB columns
                processed_data[key] = json.dumps(value)
            else:
                processed_data[key] = value
                
        return processed_data

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