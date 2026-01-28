
import logging
import json
import datetime
import os
from typing import Dict, Any, List

# Create audit logger specifically
audit_logger = logging.getLogger("audit_log")
audit_logger.setLevel(logging.INFO)

# Ensure log directory exists
os.makedirs("logs", exist_ok=True)

# File Handler for Audit Logs (JSON lines)
file_handler = logging.FileHandler("logs/audit.log")
formatter = logging.Formatter('%(message)s')
file_handler.setFormatter(formatter)
audit_logger.addHandler(file_handler)

class AuditLogService:
    def log_event(self, event_type: str, file_name: str, status: str, details: Dict[str, Any] = None):
        """
        Logs a compliance/operational event.
        
        Args:
            event_type: e.g., "INGESTION", "MASKING", "AI_PROCESSING"
            file_name: Name of the file being processed
            status: "SUCCESS" or "FAILURE"
            details: Extra metadata (e.g., number of PII tokens found). 
                     CRITICAL: DO NOT INCLUDE ACTUAL PII VALUES HERE.
        """
        timestamp = datetime.datetime.utcnow().isoformat() + "Z"
        
        entry = {
            "timestamp": timestamp,
            "event_type": event_type,
            "file_name": file_name,
            "status": status,
            "details": details or {}
        }
        
        # Write to disk as JSON Line
        audit_logger.info(json.dumps(entry))
        
        # Also print to standard out for dev visibility
        if status == "FAILURE":
            logging.error(f"[AUDIT] {event_type} failed for {file_name}: {details}")
        else:
            logging.info(f"[AUDIT] {event_type} for {file_name}: {status}")

    def log_pii_masking(self, file_name: str, token_map: Dict[str, str]):
        """
        Specialized logger for Masking events.
        Records stats about what was hidden (e.g., "Masked 5 Persons")
        without revealing who they are.
        """
        # Aggregate stats
        stats = {}
        for token, original_value in token_map.items():
            # Extract type from token e.g. {{PERSON_1}} -> PERSON
            # Simple heuristic: remove {{, }}, numbers and _
            # Or simplified: All {{PERSON_X}} count as PERSON.
            
            clean_type = "UNKNOWN"
            if "PERSON" in token: clean_type = "PERSON"
            elif "COMPANY" in token: clean_type = "COMPANY"
            elif "EMAIL" in token: clean_type = "EMAIL"
            elif "IBAN" in token: clean_type = "IBAN"
            elif "PHONE" in token: clean_type = "PHONE"
            elif "ADDRESS" in token: clean_type = "ADDRESS"
            elif "HEADER_VAL" in token: clean_type = "HEADER_METADATA"
            
            stats[clean_type] = stats.get(clean_type, 0) + 1
            
        self.log_event(
            event_type="PII_MASKING",
            file_name=file_name,
            status="SUCCESS",
            details={
                "total_tokens_masked": len(token_map),
                "token_types": stats
            }
        )

# Singleton
audit_service = AuditLogService()
