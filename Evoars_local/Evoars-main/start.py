import subprocess
import time
import sys
import threading
import os
import signal
import re

# Global process variables to ensure cleanup
app_process = None
tunnel_process = None

def signal_handler(sig, frame):
    print("\nExiting... Stopping services.")
    if tunnel_process:
        tunnel_process.terminate()
    if app_process:
        app_process.terminate()
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)

def stream_process_output(process, prefix):
    """Reads output from a process and prints it with a prefix."""
    # تتبع الرسائل المتكررة
    repeated_messages = {}
    last_message_type = None
    
    for line in iter(process.stdout.readline, ''):
        if line:
            line_stripped = line.strip()
            
            # تجاهل الرسائل الفارغة أو شبه الفارغة
            if not line_stripped or line_stripped in ['', ' ']:
                continue
            
            # اختصار رسائل GET/POST المتكررة
            if " - - [" in line_stripped and "] \"" in line_stripped:
                # رسائل HTTP access logs - نعرض فقط ملخص
                message_type = "HTTP_REQUEST"
                if message_type != last_message_type:
                    print(f"[{prefix}] 🌐 HTTP requests received...", flush=True)
                    last_message_type = message_type
                continue
            
            # تقصير الرسائل الطويلة جداً
            max_length = 100
            if len(line_stripped) > max_length:
                line_stripped = line_stripped[:max_length] + "..."
            
            # طباعة الرسالة بتنسيق ثابت
            print(f"[{prefix}] {line_stripped}", flush=True)
            last_message_type = None
            
            # Detect successful server start
            if "Running on http://" in line:
                print(f"[{prefix}] ✅ Server started successfully!", flush=True)

def start_app():
    global app_process
    print("🚀 Starting Evoars App (app.py)...")
    # Using unbuffered output (-u) to see print statements immediately
    app_process = subprocess.Popen(
        [sys.executable, "-u", "app.py"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )
    # Start a thread to print app output
    t = threading.Thread(target=stream_process_output, args=(app_process, "APP"))
    t.daemon = True
    t.start()

def start_tunnel():
    global tunnel_process
    print("🌐 Starting SSH Tunnel to localhost.run...")
    
    # The ssh command provided by the user
    ssh_command = [
        "ssh", "-o", "StrictHostKeyChecking=no", 
        "-R", "80:127.0.0.1:7860", 
        "nokey@localhost.run"
    ]
    
    tunnel_process = subprocess.Popen(
        ssh_command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )

    print("⏳ Waiting for public URL...")
    url_found = False
    
    # Read output line by line to find the URL
    for line in iter(tunnel_process.stdout.readline, ''):
        if line:
            # Simple regex to find lhr.life or localhost.run URLs
            # localhost.run output format: "tunneled with tls change, https://xyz.lhr.life"
            match = re.search(r'(https?://[a-zA-Z0-9-]+\.(?:lhr\.life|localhost\.run))', line)
            if match:
                public_url = match.group(1)
                print("\n" + "="*60)
                print(f"  ✅ YOUR PUBLIC URL: {public_url}")
                print("="*60 + "\n", flush=True)
                url_found = True
            elif "tunneled with tls change" in line and not url_found:
                 # Backup if regex fails but we see the line
                 print(f"[TUNNEL] {line.strip()[:120]}", flush=True)

def main():
    # Check if we are in the correct directory, if not try to switch or warn
    if not os.path.exists("app.py"):
        print("⚠️  Warning: app.py not found in current directory.")
        # Try to navigate specific for Codespaces if applicable
        target_dir = "/workspaces/MANGA-color/Evoars_local/Evoars-main"
        if os.path.exists(target_dir):
            print(f"Changing directory to {target_dir}")
            os.chdir(target_dir)
        else:
            print("Please run this script from the Evoars-main directory.")
            # We don't exit, just try anyway or let user handle it
            
    start_app()
    
    # Give the app a moment to initialize
    time.sleep(3)
    
    start_tunnel()
    
    # Keep the main thread alive to monitor processes
    try:
        while True:
            time.sleep(1)
            if app_process.poll() is not None:
                print("❌ App process exited unexpectedly.")
                break
            if tunnel_process.poll() is not None:
                print("❌ Tunnel process exited unexpectedly.")
                break
    except KeyboardInterrupt:
        signal_handler(None, None)

if __name__ == "__main__":
    main()
