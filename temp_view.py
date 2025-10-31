from pathlib import Path
text=Path('app/agentic_script_agent.py').read_text()
start=text.index('  private resolveDataValue')
print(text[start:start+200])
