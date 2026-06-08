import os
import re
from datetime import datetime
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
CALENDAR_PATH = APP_DIR / "data" / "Fall 26 - Academic Calendar.csv"
LOGIC_PATH = APP_DIR / "logic.py"

def main():
    if not CALENDAR_PATH.exists():
        return
        
    mtime = CALENDAR_PATH.stat().st_mtime
    # Format the date properly, removing leading zeros if on Windows via string manipulation
    d = datetime.fromtimestamp(mtime)
    date_str = d.strftime("%B %d, %Y").replace(" 0", " ")
    
    with open(LOGIC_PATH, "r", encoding="utf-8") as f:
        content = f.read()
        
    new_content = re.sub(
        r'(def get_bundled_calendar_date\(\) -> str:\n\s+return\s+)".*"',
        rf'\1"{date_str}"',
        content
    )
    
    if new_content != content:
        with open(LOGIC_PATH, "w", encoding="utf-8") as f:
            f.write(new_content)
        print(f"Updated logic.py with calendar date: {date_str}")

if __name__ == "__main__":
    main()
