from datetime import datetime

def log(section: str, message: str):
    now = datetime.now().strftime("%H:%M:%S")
    print(f"[{now}] [{section.upper()}] {message}")
