"""
Solidity AST Parser Tool.
Extracts contract structure, functions, modifiers, state variables, external calls,
and checks-effects-interactions ordering from Solidity source code.
"""

from __future__ import annotations
import re
from typing import Any, Dict, List, Optional
from tools.base import BaseTool


class ASTParserTool(BaseTool):
    name = "ast_parser"
    description = "Parses Solidity source code into structured AST components, detecting functions, state variables, external calls, and call ordering."
    input_schema = {
        "type": "object",
        "properties": {
            "source_code": {"type": "string", "description": "Solidity source code to parse"}
        },
        "required": ["source_code"]
    }
    output_schema = {
        "type": "object",
        "properties": {
            "contracts": {"type": "array"},
            "functions": {"type": "array"},
            "state_variables": {"type": "array"},
            "external_calls": {"type": "array"},
            "modifiers": {"type": "array"},
            "cei_violations": {"type": "array"}
        }
    }

    def _run(self, source_code: str) -> Dict[str, Any]:
        lines = source_code.splitlines()
        
        # 1. Extract contract definitions
        contracts = []
        contract_matches = re.finditer(r"(?:contract|interface|library|abstract contract)\s+(\w+)(?:\s+is\s+([^{]+))?", source_code)
        for m in contract_matches:
            contracts.append({
                "name": m.group(1),
                "inheritance": [i.strip() for i in m.group(2).split(",")] if m.group(2) else []
            })
            
        # 2. Extract state variables
        state_vars = []
        var_pattern = re.compile(r"^\s*(mapping\([^)]+\)|uint\d*|int\d*|address|bool|string|bytes\d*)\s+(public|private|internal)?\s*(\w+)\s*(?:=\s*([^;]+))?;")
        for idx, line in enumerate(lines, 1):
            vm = var_pattern.match(line)
            if vm and not line.strip().startswith("//"):
                state_vars.append({
                    "line": idx,
                    "type": vm.group(1),
                    "visibility": vm.group(2) or "internal",
                    "name": vm.group(3),
                    "initial_value": vm.group(4).strip() if vm.group(4) else None
                })
                
        # 3. Extract functions and their internals
        functions = []
        fn_pattern = re.compile(r"function\s+(\w+)\s*\(([^)]*)\)\s*([^{;]*)(?:\{|;)")
        
        for m in re.finditer(fn_pattern, source_code):
            fn_name = m.group(1)
            params = m.group(2).strip()
            attributes = m.group(3).strip()
            start_pos = m.start()
            
            # Find function body if not interface
            body = ""
            brace_idx = source_code.find("{", start_pos)
            if brace_idx != -1 and (m.end() >= brace_idx or "{" in m.group(0)):
                depth = 1
                cur = brace_idx + 1
                while cur < len(source_code) and depth > 0:
                    if source_code[cur] == "{":
                        depth += 1
                    elif source_code[cur] == "}":
                        depth -= 1
                    cur += 1
                body = source_code[brace_idx+1:cur-1]
                
            # Analyze body for external calls and state updates
            external_calls = []
            state_updates = []
            
            for line_no, bline in enumerate(body.splitlines(), 1):
                clean_line = bline.strip()
                if clean_line.startswith("//"):
                    continue
                # external call patterns
                if ".call{" in clean_line or ".transfer(" in clean_line or ".send(" in clean_line or ".delegatecall(" in clean_line:
                    external_calls.append({"line_offset": line_no, "code": clean_line})
                # state update patterns: balances[x] =, count +=, owner =, etc.
                if re.search(r"(\w+(?:\[[^\]]+\])?)\s*(\+=|-=|=|\*=)\s*[^=]", clean_line):
                    state_updates.append({"line_offset": line_no, "code": clean_line})
                    
            # Check for Checks-Effects-Interactions (CEI) violations
            has_cei_violation = False
            if external_calls and state_updates:
                first_call_line = min(c["line_offset"] for c in external_calls)
                last_update_line = max(u["line_offset"] for u in state_updates)
                if first_call_line < last_update_line:
                    has_cei_violation = True
                    
            functions.append({
                "name": fn_name,
                "parameters": params,
                "attributes": attributes,
                "visibility": "public" if "public" in attributes else ("external" if "external" in attributes else ("private" if "private" in attributes else "internal")),
                "is_payable": "payable" in attributes,
                "is_view_or_pure": "view" in attributes or "pure" in attributes,
                "modifiers": [w for w in attributes.split() if w not in ["public", "external", "internal", "private", "view", "pure", "payable", "override", "virtual", "returns"] and not w.startswith("(")],
                "external_calls": external_calls,
                "state_updates": state_updates,
                "has_cei_violation": has_cei_violation
            })
            
        # 4. Modifiers
        modifiers = []
        mod_pattern = re.compile(r"modifier\s+(\w+)\s*\(([^)]*)\)")
        for m in re.finditer(mod_pattern, source_code):
            modifiers.append({"name": m.group(1), "params": m.group(2)})
            
        return {
            "contracts": contracts,
            "state_variables": state_vars,
            "functions": functions,
            "modifiers": modifiers,
            "cei_violations": [f["name"] for f in functions if f.get("has_cei_violation")]
        }
