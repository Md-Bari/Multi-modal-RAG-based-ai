import os
import sys
import socket
import time
import subprocess

def wait_for_db():
    print("Waiting for database...")
    db_host = os.environ.get("DATABASE_HOST", "db")
    db_port = int(os.environ.get("DATABASE_PORT", 5432))
    
    db_url = os.environ.get("DATABASE_URL")
    if db_url:
        import urllib.parse as urlparse
        try:
            url = urlparse.urlparse(db_url)
            if url.hostname:
                db_host = url.hostname
            if url.port:
                db_port = url.port
        except Exception as e:
            print(f"Warning: Could not parse DATABASE_URL: {e}")

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    for i in range(60):
        try:
            s.connect((db_host, db_port))
            s.close()
            print("Database is up and reachable!")
            return
        except socket.error:
            print(f"Database not reachable on {db_host}:{db_port} yet... (attempt {i+1}/60)")
            time.sleep(1)
    print("Error: Database not available after 60 seconds. Exiting.")
    sys.exit(1)

def run_migrations():
    print("Running Django database migrations...")
    try:
        subprocess.run(["python", "manage.py", "migrate", "--noinput"], check=True)
        print("Migrations ran successfully.")
    except subprocess.CalledProcessError as e:
        print(f"Error: Migration execution failed: {e}")
        sys.exit(e.returncode)

if __name__ == "__main__":
    wait_for_db()
    
    args = sys.argv[1:]
    is_web_server = any("runserver" in arg for arg in args) or not args
    
    if is_web_server:
        run_migrations()
        
    if args:
        print(f"Executing command: {' '.join(args)}")
        try:
            os.execvp(args[0], args)
        except FileNotFoundError:
            print(f"Error: Command '{args[0]}' not found.")
            sys.exit(127)
    else:
        print("No command specified. Running Django development server.")
        os.execvp("python", ["python", "manage.py", "runserver", "0.0.0.0:8000"])
