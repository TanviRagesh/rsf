import sys, os
# Ensure backend directory is on sys.path so config.py (top-level import) is found
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
# Importing this module runs the listing script
from backend.scripts import list_webservices_routes
