import sys
sys.path.insert(0, r'D:\ChisinauRouting\ingestion')
import psycopg2
from config import settings

print("Testing database connection...")
try:
    conn = psycopg2.connect(**settings.db.psycopg2_params, connect_timeout=10)
    conn.set_session(autocommit=True)
    
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM nodes")
    nodes = cur.fetchone()[0]
    
    cur.execute("SELECT COUNT(*) FROM edges")  
    edges = cur.fetchone()[0]
    
    print(f"SUCCESS!")
    print(f"Nodes: {nodes}")
    print(f"Edges: {edges}")
    
    conn.close()
except Exception as e:
    print(f"ERROR: {e}")
