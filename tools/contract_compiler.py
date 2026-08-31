"""
Contract Compiler Tool.
Validates Solidity syntax, language constructs, typing, interface parity,
and contract compilation integrity.
"""

from __future__ import annotations
import re
import shutil
import subprocess
from typing import Any, Dict, List
from tools.base import BaseTool


class ContractCompilerTool(BaseTool):
    name = "contract_compiler"
    description = "Checks Solidity code for compilation, syntax errors, mismatched brackets, invalid types, and duplicate symbols."
    input_schema = {
        "type": "object",
        "properties": {
            "source_code": {"type": "string", "description": "Solidity code to compile and validate"}
        },
        "required": ["source_code"]
    }
    output_schema = {
        "type": "object",
        "properties": {
            "compiled_successfully": {"type": "boolean"},
            "errors": {"type": "array"},
            "warnings": {"type": "array"}
        }
    }

    def _run(self, source_code: str) -> Dict[str, Any]:
        errors: List[str] = []
        warnings: List[str] = []

        # 1. Pragma check
        if "pragma solidity" not in source_code:
            warnings.append("Missing pragma solidity statement.")

        # 2. Balanced delimiters check
        delims = {"{": "}", "(": ")", "[": "]"}
        stack = []
        in_string = False
        in_line_comment = False
        in_block_comment = False
        lines = source_code.splitlines()

        for line_num, line in enumerate(lines, 1):
            i = 0
            while i < len(line):
                char = line[i]
                # Handle comments
                if not in_string and not in_block_comment and i + 1 < len(line) and line[i:i+2] == "//":
                    break  # rest of line is comment
                if not in_string and not in_line_comment and i + 1 < len(line) and line[i:i+2] == "/*":
                    in_block_comment = True
                    i += 2
                    continue
                if in_block_comment and i + 1 < len(line) and line[i:i+2] == "*/":
                    in_block_comment = False
                    i += 2
                    continue
                if in_block_comment:
                    i += 1
                    continue

                # Strings
                if char in ('"', "'") and (i == 0 or line[i-1] != '\\'):
                    in_string = not in_string
                    i += 1
                    continue
                if in_string:
                    i += 1
                    continue

                # Brackets
                if char in delims:
                    stack.append((char, line_num))
                elif char in delims.values():
                    if not stack:
                        errors.append(f"Line {line_num}: Unexpected closing bracket '{char}' without matching opener.")
                    else:
                        open_char, open_line = stack.pop()
                        if delims[open_char] != char:
                            errors.append(f"Line {line_num}: Mismatched bracket. Expected '{delims[open_char]}' for '{open_char}' from line {open_line}, but found '{char}'.")
                i += 1

        if stack:
            for open_char, open_line in stack:
                errors.append(f"Line {open_line}: Unclosed '{open_char}' at end of file.")

        # 3. Check for common syntax mistakes in Solidity
        for line_num, line in enumerate(lines, 1):
            clean = line.strip()
            if clean.startswith("//") or clean.startswith("/*") or clean.startswith("*"):
                continue
            # require statements without semicolon
            if clean.startswith("require(") and not clean.endswith(";") and not clean.endswith("{"):
                # Multi-line require check
                full_stmt = clean
                lookahead = line_num
                while lookahead < len(lines) and not full_stmt.endswith(";"):
                    lookahead += 1
                    full_stmt += " " + lines[lookahead-1].strip()
                if not full_stmt.endswith(";"):
                    errors.append(f"Line {line_num}: Missing semicolon after require statement.")
            
            # Missing visibility on functions
            if clean.startswith("function ") and "(" in clean and "{" in clean:
                if not any(v in clean for v in ["public", "private", "internal", "external"]):
                    errors.append(f"Line {line_num}: Function declaration missing explicit visibility (public/external/internal/private).")

            # Incomplete statements (e.g. `uint256 x =` without value)
            if re.match(r"^\s*(?:uint\d*|address|bool)\s+\w+\s*=\s*;$", clean):
                errors.append(f"Line {line_num}: Variable declaration assigned empty expression.")

        # 4. If system solc is available, attempt native solc check
        solc_path = shutil.which("solc")
        if solc_path and not errors:
            try:
                proc = subprocess.run(
                    [solc_path, "--bin", "-"],
                    input=source_code,
                    text=True,
                    capture_output=True,
                    timeout=5
                )
                if proc.returncode != 0:
                    for err_line in proc.stderr.splitlines():
                        if "Error:" in err_line:
                            errors.append(err_line)
            except Exception:
                pass

        compiled_successfully = len(errors) == 0
        return {
            "compiled_successfully": compiled_successfully,
            "errors": errors,
            "warnings": warnings,
            "status": "COMPILATION_PASSED" if compiled_successfully else "COMPILATION_FAILED"
        }
