import subprocess
import os
import sys
import glob

def find_ffmpeg():
    print("=" * 60)
    print("FFMPEG DIAGNOSTIC TOOL")
    print("=" * 60)
    
    # Check PATH
    print("\n1. Checking if 'ffmpeg' is in PATH...")
    try:
        result = subprocess.run(
            ["ffmpeg", "-version"],
            capture_output=True,
            timeout=5,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        )
        if result.returncode == 0:
            print("   ✓ FFmpeg found in PATH!")
            print(f"   Output: {result.stdout.decode()[:200]}...")
            return True
    except Exception as e:
        print(f"   ✗ Not found in PATH: {e}")
    
    # Try 'where' command on Windows
    if os.name == 'nt':
        print("\n2. Using 'where' command to locate ffmpeg...")
        try:
            result = subprocess.run(
                ["where", "ffmpeg"],
                capture_output=True,
                check=True,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            paths = result.stdout.strip().split('\n')
            print(f"   ✓ Found {len(paths)} instance(s):")
            for path in paths:
                print(f"      - {path}")
                if os.path.exists(path):
                    print(f"        (exists: ✓)")
                else:
                    print(f"        (exists: ✗)")
            return True
        except Exception as e:
            print(f"   ✗ 'where' command failed: {e}")
    
    # Check common locations
    print("\n3. Checking common installation locations...")
    common_paths = [
        "C:\\ffmpeg\\bin\\ffmpeg.exe",
        "C:\\Program Files\\ffmpeg\\bin\\ffmpeg.exe",
        os.path.expanduser("~\\scoop\\apps\\ffmpeg\\current\\bin\\ffmpeg.exe"),
        "C:\\ProgramData\\chocolatey\\bin\\ffmpeg.exe",
    ]
    
    # Add WinGet installation paths (with wildcards)
    winget_pattern = os.path.join(
        os.environ.get('LOCALAPPDATA', ''), 
        'Microsoft', 'WinGet', 'Packages', 
        'Gyan.FFmpeg*', 'ffmpeg-*', 'bin', 'ffmpeg.exe'
    )
    common_paths.extend(glob.glob(winget_pattern))
    
    found = False
    for path in common_paths:
        if os.path.exists(path):
            print(f"   ✓ Found: {path}")
            found = True
            
            # Try to run it
            try:
                result = subprocess.run(
                    [path, "-version"],
                    capture_output=True,
                    timeout=5,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
                )
                if result.returncode == 0:
                    print(f"      Works: ✓")
                else:
                    print(f"      Works: ✗ (exit code {result.returncode})")
            except Exception as e:
                print(f"      Works: ✗ ({e})")
        else:
            print(f"   ✗ Not found: {path}")
    
    # Check Python's environment
    print("\n4. Python environment info:")
    print(f"   Python executable: {sys.executable}")
    print(f"   Python version: {sys.version}")
    print(f"   Current PATH: {os.environ.get('PATH', 'NOT SET')[:200]}...")
    
    # Recommendations
    print("\n" + "=" * 60)
    if found:
        print("RESULT: FFmpeg is installed but not in Python's PATH")
        print("\nRECOMMENDATIONS:")
        print("1. Restart your terminal/IDE completely")
        print("2. If using VSCode, reload the window (Ctrl+Shift+P -> Reload Window)")
        print("3. Or add FFmpeg to system PATH manually:")
        print("   - Open System Properties -> Environment Variables")
        print("   - Edit PATH and add FFmpeg bin directory")
        print("   - Restart all terminals")
        print("\n4. Quick fix: Update voice_stream.py to use full path")
    else:
        print("RESULT: FFmpeg not found")
        print("\nRECOMMENDATIONS:")
        print("1. Install FFmpeg:")
        print("   winget install ffmpeg")
        print("2. Or download manually:")
        print("   https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip")
        print("3. Extract to C:\\ffmpeg")
        print("4. Add C:\\ffmpeg\\bin to PATH")
    print("=" * 60)
    
    return found

if __name__ == "__main__":
    find_ffmpeg()