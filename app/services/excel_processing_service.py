from typing import List, Dict, Tuple, Any
import pandas as pd

class ExcelProcessingService:
    def get_sheet_names(self, file_path: str) -> List[str]:
        """Reads an Excel file and returns a list of all sheet names."""
        try:
            xls = pd.ExcelFile(file_path)
            return xls.sheet_names
        except Exception as e:
            # Consider logging the error
            raise ValueError(f"Could not read sheet names from {file_path}: {e}")

    def read_excel(self, file_path: str, sheet_name: str | None = None) -> Tuple[List[Dict[str, Any]], List[str]]:
        """Reads a specific sheet from an Excel file and returns data and headers."""
        try:
            # If no sheet_name is provided, default to the first sheet
            df = pd.read_excel(file_path, sheet_name=sheet_name)
            
            # Sanitize headers: convert to lowercase, replace spaces with underscores
            df.columns = [str(col).strip().lower().replace(' ', '_') for col in df.columns]
            
            # Convert DataFrame to list of dictionaries
            data = df.to_dict(orient='records')
            headers = list(df.columns)
            
            return data, headers
        except Exception as e:
            raise ValueError(f"Failed to read Excel sheet '{sheet_name or 'default'}': {e}")

    def validate_data(self, data: List[Dict[str, Any]], headers: List[str]) -> Dict[str, Any]:
        """Validates the data, looking for a 'phone' or 'number' column."""
        phone_column = None
        for col in ['phone', 'number', 'cell', 'mobile']:
            if col in headers:
                phone_column = col
                break
        
        if not phone_column:
            return {
                "success": False,
                "error": "Missing required column: 'phone', 'number', 'cell', or 'mobile'.",
                "valid_count": 0,
                "invalid_count": len(data),
                "valid_data": []
            }

        valid_data = []
        invalid_count = 0
        
        for row in data:
            phone_val = row.get(phone_column)
            if phone_val and isinstance(phone_val, (str, int)):
                # Basic normalization of phone number
                phone_str = str(phone_val).strip()
                if phone_str.isdigit() and len(phone_str) >= 10:
                    valid_data.append(row)
                    continue
            
            invalid_count += 1

        return {
            "success": True,
            "valid_count": len(valid_data),
            "invalid_count": invalid_count,
            "valid_data": valid_data
        }

excel_processing_service = ExcelProcessingService()