#!/usr/bin/env python3
"""
Wrapper script for BC3 parser that reads from stdin and writes JSON to stdout.
This allows integration with Java services.
"""
import sys
import json
import tempfile
from pathlib import Path

# Import the parser functions
from parser import bc3_to_json


def main():
    try:
        # Read BC3 content from stdin (binary)
        bc3_content = sys.stdin.buffer.read()
        
        if not bc3_content:
            error_result = {
                "success": False,
                "error": "No BC3 content received from stdin",
                "data": None
            }
            print(json.dumps(error_result, ensure_ascii=False))
            sys.exit(1)
        
        # Create a temporary file to store the BC3 content
        with tempfile.NamedTemporaryFile(mode='wb', suffix='.bc3', delete=False) as tmp_file:
            tmp_file.write(bc3_content)
            tmp_path = Path(tmp_file.name)
        
        try:
            # Parse the BC3 file
            tree = bc3_to_json(tmp_path)
            
            # Create success response
            result = {
                "success": True,
                "error": None,
                "data": tree
            }
            
            # Output JSON to stdout
            print(json.dumps(result, ensure_ascii=False))
            
        finally:
            # Clean up temporary file
            if tmp_path.exists():
                tmp_path.unlink()
                
    except Exception as e:
        # Return error as JSON
        error_result = {
            "success": False,
            "error": str(e),
            "data": None
        }
        print(json.dumps(error_result, ensure_ascii=False))
        sys.exit(1)


if __name__ == "__main__":
    main()
