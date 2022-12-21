from datetime import datetime

start_time = None

def mark_start_time():
	global start_time
	start_time = datetime.utcnow()
