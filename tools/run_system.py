import os
import subprocess
import webbrowser
import sys
import threading
import time

def main():
    print("=" * 60)
    print("🎓 ATTENDANCE SYSTEM")
    print("=" * 60)
    
    os.makedirs('data/known_faces', exist_ok=True)
    os.makedirs('data/models', exist_ok=True)
    
    if not os.path.exists('data/models/emotion_model_v4.keras'):
        print("\n⚠️ Place emotion_model_v4.keras in data/models/")
        cont = input("Continue without emotion? (y/n): ")
        if cont.lower() != 'y':
            sys.exit(1)
    
    print("\n1. Register Students")
    print("2. Start System")
    print("3. Both")
    choice = input("Choice: ")
    
    if choice in ['1', '3']:
        subprocess.run(['python', 'register_students.py'])
    
    if choice in ['2', '3']:
        print("\n🚀 Starting dashboard...")
        print("🌐 Opening browser...")
        
        # Open browser ONCE after 2 seconds
        def open_browser():
            time.sleep(2)
            webbrowser.open('http://localhost:5000')
            print("✅ Dashboard opened in your browser!")
        
        threading.Thread(target=open_browser, daemon=True).start()
        
        # Run app.py (which will NOT open browser)
        subprocess.run(['python', 'app.py'])

if __name__ == "__main__":
    main()
