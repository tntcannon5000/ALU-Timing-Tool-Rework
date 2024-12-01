import os
import sys
import subprocess


# Check if venv exists
venv_path = '.venv'
if not os.path.exists(venv_path):
    print("Virtual environment not found. Please run setup.py first.")
    sys.exit(1)

# If venv exists, activate it
if sys.platform == 'win32':
    subprocess.run(['.venv\\Scripts\\activate.bat'])
    if "venv" in sys.executable:
        print("Venv activated Successfully")
else:
    print("Aint no windows in here")



# Check if config folder exists
config_path = 'config'
if not os.path.exists(config_path):
    print("Configs not found, running initial setup...")
    
    # Initial config code goes here.


