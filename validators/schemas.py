"""Expected schemas for each source in the landing zone.

Each schema declares:
  - format:   "parquet" (tabular) or "json" (one record per file)
  - columns:  expected field -> expected type
                * parquet: pandas dtype string (e.g. "object", "float64")
                * json:    logical type name ("str", "float", "int", "dict", "list")
  - required: fields that must be present AND non-null

Note: "payments" are not a separate source — payment activity lives in the
`billing` transactions (see transaction_type / payment_method).
"""

SCHEMAS = {
    "customers": {
        "format": "parquet",
        "columns": {
            "customer_id": "object",
            "first_name": "object",
            "last_name": "object",
            "dob": "object",
            "email": "object",
            "phone": "object",
            "address": "object",
            "city": "object",
            "state": "object",
            "zip_code": "object",
            "created_at": "datetime64[ns]",
        },
        "required": ["customer_id", "created_at"],
    },
    "agents": {
        "format": "parquet",
        "columns": {
            "agent_id": "object",
            "agent_name": "object",
            "territory": "object",
            "hire_date": "object",
            "license_number": "object",
        },
        "required": ["agent_id"],
    },
    "policies": {
        "format": "parquet",
        "columns": {
            "policy_id": "object",
            "customer_id": "object",
            "agent_id": "object",
            "policy_number": "object",
            "coverage_type": "object",
            "start_date": "object",
            "end_date": "object",
            "premium_amount": "float64",
            "status": "object",
            "created_at": "datetime64[ns]",
        },
        "required": ["policy_id", "customer_id", "agent_id"],
    },
    "coverages": {
        "format": "parquet",
        "columns": {
            "coverage_id": "object",
            "policy_id": "object",
            "coverage_code": "object",
            "coverage_limit": "int64",
            "deductible": "int64",
        },
        "required": ["coverage_id", "policy_id"],
    },
    "billing": {
        "format": "parquet",
        "columns": {
            "transaction_id": "object",
            "policy_id": "object",
            "customer_id": "object",
            "transaction_date": "datetime64[ns]",
            "transaction_type": "object",
            "amount": "float64",
            "payment_method": "object",
            "status": "object",
        },
        "required": [
            "transaction_id",
            "policy_id",
            "customer_id",
            "transaction_date",
        ],
    },
    "weather": {
        "format": "parquet",
        "columns": {
            "weather_date": "object",
            "zip_code": "object",
            "max_temp_c": "float64",
            "min_temp_c": "float64",
            "precipitation_mm": "float64",
            "max_wind_kmh": "float64",
            "weather_code": "int64",
        },
        "required": ["weather_date", "zip_code"],
    },
    "claims": {
        "format": "json",
        "columns": {
            "claim_id": "str",
            "policy_id": "str",
            "customer_id": "str",
            "incident_date": "str",
            "report_date": "str",
            "incident_location": "dict",
            "incident_type": "str",
            "description": "str",
            "status": "str",
            "claim_amount": "float",
            "approved_amount": "float",
            "created_at": "str",
            "events": "list",
        },
        "required": [
            "claim_id",
            "policy_id",
            "customer_id",
            "incident_date",
            "status",
        ],
    },
}
