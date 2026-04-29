import os
import re

base_dir = r"c:\Users\venka\Downloads\AgentScope"
files_to_update = [
    "backend/anomaly/detector.py",
    "backend/evaluation/llm_judge.py",
    "backend/agents/demo_agent.py",
    "backend/redteam/engine.py",
    "backend/redteam/evolution.py",
    "backend/api/traces.py",
    "backend/replay/engine.py"
]

for filepath in files_to_update:
    path = os.path.join(base_dir, filepath)
    if not os.path.exists(path): 
        print(f"Not found: {path}")
        continue
        
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
        
    original = content
        
    # Add import if not there
    if "SemanticAttributes" not in content:
        if "from core.models import" in content:
            # Inject into existing import
            content = re.sub(
                r'(from core\.models import\s*\()', 
                r'\1\n    SemanticAttributes,', 
                content
            )
            # Or if it's on one line
            content = re.sub(
                r'(from core\.models import )((?!.*SemanticAttributes).*)$', 
                r'\1SemanticAttributes, \2', 
                content,
                flags=re.MULTILINE
            )
        else:
            # Just add to top after future
            content = content.replace("from __future__ import annotations", "from __future__ import annotations\nfrom core.models import SemanticAttributes")
        
    # Replace getters
    content = content.replace('.get("tool"', '.get(SemanticAttributes.TOOL_NAME')
    content = content.replace("['tool']", "[SemanticAttributes.TOOL_NAME]")
    content = content.replace('["tool"]', '[SemanticAttributes.TOOL_NAME]')
    
    content = content.replace('.get("input_params"', '.get(SemanticAttributes.INPUT_PARAMS')
    content = content.replace("['input_params']", "[SemanticAttributes.INPUT_PARAMS]")
    content = content.replace('["input_params"]', '[SemanticAttributes.INPUT_PARAMS]')
    
    content = content.replace('.get("output"', '.get(SemanticAttributes.OUTPUT')
    content = content.replace("['output']", "[SemanticAttributes.OUTPUT]")
    content = content.replace('["output"]', '[SemanticAttributes.OUTPUT]')

    # For dictionary construction in demo_agent.py
    content = content.replace('{"tool":', '{SemanticAttributes.TOOL_NAME:')
    content = content.replace('"input_params":', 'SemanticAttributes.INPUT_PARAMS:')
    content = content.replace('"output":', 'SemanticAttributes.OUTPUT:')

    if content != original:
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"Updated {filepath}")
    else:
        print(f"No changes needed in {filepath}")
