import subprocess
import sys
import os

def main():
    if not "venv" in sys.executable:
        print("Please run using setup.bat")
        input("Press any key to exit...")
        sys.exit(1)

    if not sys.platform == 'win32':
        print("Warning: This application is only supported on Windows")
        input("Press any key to exit...")
        sys.exit(1)

    # Install requirements
    print("Installing requirements...")
    try:
        subprocess.check_call([sys.executable, '-m', 'pip', 'install', '-r', 'requirements.txt'])
    except subprocess.CalledProcessError as e:
        print(f"Error installing requirements: {e}")
        input("Press any key to exit...")
        sys.exit(1)

    # Check and install Tesseract
    try:
        import pytesseract
        pytesseract.get_tesseract_version()
        print("Tesseract already installed")
    except:
        print("Installing Tesseract...")
        if not check_winget():
            print("Winget is not installed. Please install Windows App Installer from the Microsoft Store")
            input("Press any key to exit...")
            sys.exit(1)
        
        try:
            result = subprocess.run(["winget", "install", "--id=UB-Mannheim.TesseractOCR", "-e"], 
                                  capture_output=True, 
                                  text=True)
            if result.returncode != 0:
                print(f"Error installing Tesseract: {result.stderr}")
                input("Press any key to exit...")
                sys.exit(1)
            print("Tesseract installed successfully")
        except Exception as e:
            print(f"Error running winget: {e}")
            input("Press any key to exit...")
            sys.exit(1)

def check_winget():
    try:
        result = subprocess.run(['winget', '--version'], capture_output=True, text=True)
        return result.returncode == 0
    except FileNotFoundError:
        return False

if __name__ == "__main__":
    main()