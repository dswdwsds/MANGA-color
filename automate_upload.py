import os
import time
import json
import re
import io
import zipfile
import shutil
import cloudscraper
import subprocess
import sys
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

# --- الإعدادات الثابتة ---
TARGET_BATCH_SIZE_MB = 8
MAX_BATCH_SIZE_MB = 9
TARGET_BATCH_SIZE_BYTES = TARGET_BATCH_SIZE_MB * 1024 * 1024
MAX_BATCH_SIZE_BYTES = MAX_BATCH_SIZE_MB * 1024 * 1024
DEFAULT_BASE_URL = "http://127.0.0.1:7860"

def start_background_services():
    """تشغيل السيرفر والنفق في الخلفية"""
    print("--- [1/2] جاري تشغيل سيرفر Evoars... ---")
    # التأكد من المجلد الصحيح
    project_dir = os.path.dirname(os.path.abspath(__file__))
    if "Evoars-main" not in project_dir:
        project_dir = os.path.join(project_dir, "Evoars_local", "Evoars-main")
    
    # تشغيل السيرفر
    server_proc = subprocess.Popen([sys.executable, "app.py"], cwd=project_dir)
    print("⏳ ننتظر 10 ثوانٍ ليتفعل السيرفر...")
    time.sleep(10)
    
    print("--- [2/2] جاري إنشاء رابط SSH Tunnel... ---")
    # تشغيل النفق
    tunnel_cmd = "ssh -R 80:127.0.0.1:7860 nokey@localhost.run"
    subprocess.Popen(tunnel_cmd, shell=True)
    
    print("\n✅ تم إرسال أوامر التشغيل. يرجى مراقبة الشاشة لنسخ الرابط العام.")
    print("ملاحظة: إذا كنت في Codespaces، يمكنك استخدام رابط الـ Ports الثابت أيضاً.\n")

def process_batch(batch, batch_idx, base_url, process_url, output_dir, valid_extensions):
    """رفع الدفعة بناءً على الحجم الكلي"""
    scraper = cloudscraper.create_scraper()
    
    # حساب الحجم الكلي للدفعة للتقارير
    total_size = sum(os.path.getsize(f) for f in batch)
    print(f"\n--- [دفعة {batch_idx}] الحجم: {total_size/(1024*1024):.2f}MB | عدد الصور: {len(batch)} ---")
    
    data = {'operation': 'colorize'}
    success = False
    
    for attempt in range(3):
        files = []
        try:
            for img_path in batch:
                files.append(('images', (os.path.basename(img_path), open(img_path, 'rb'), 'image/jpeg')))
            
            if not files: return True

            print(f"⏳ جاري الرفع والانتظار...")
            response = scraper.post(process_url, data=data, files=files, timeout=600)
            
            for _, file_info in files: file_info[1].close()

            if response.status_code == 200:
                result = response.json()
                download_path = result.get('zip_download_url') or result.get('download_url')
                
                if download_path:
                    # توحيد نوع الرابط (مطلق أو نسبي)
                    if download_path.startswith('/'):
                        download_url = f"{base_url.rstrip('/')}{download_path}"
                    elif not download_path.startswith('http'):
                        download_url = f"{base_url.rstrip('/')}/{download_path}"
                    else:
                        download_url = download_path
                    
                    print(f"✅ المعالجة تمت! جاري تحميل ZIP...")
                    r_download = scraper.get(download_url)
                    
                    if r_download.status_code == 200:
                        with zipfile.ZipFile(io.BytesIO(r_download.content)) as z:
                            for member in z.infolist():
                                if member.filename.lower().endswith(valid_extensions):
                                    filename = os.path.basename(member.filename)
                                    target_path = os.path.join(output_dir, filename)
                                    with open(target_path, "wb") as target:
                                        with z.open(member) as source:
                                            shutil.copyfileobj(source, target)
                        print(f"🎉 تم حفظ نتائج الدفعة {batch_idx}.")
                        success = True
                        break 
                else:
                    print(f"⚠️ فشل: لم يتم استلام رابط تحميل.")
            else:
                print(f"❌ خطأ من السيرفر كود {response.status_code}")
            
        except Exception as e:
            print(f"❌ خطأ تقني: {e}")
            for _, file_info in files:
                if not file_info[1].closed: file_info[1].close()
        
        if not success: time.sleep(10)
    return success

import threading
HISTORY_FILE = "history.json"
history_lock = threading.Lock()

def load_history():
    if not os.path.exists(HISTORY_FILE): return {"colored": []}
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f: return json.load(f)
    except: return {"colored": []}

def add_to_history(category, item):
    with history_lock:
        history = load_history()
        if item not in history.get(category, []):
            if category not in history: history[category] = []
            history[category].append(item)
            with open(HISTORY_FILE, "w", encoding="utf-8") as f:
                json.dump(history, f, ensure_ascii=False, indent=4)

def colorize_chapter(source_dir, output_dir, base_url):
    chapter_name = os.path.basename(source_dir)
    if not os.path.exists(source_dir): return print(f"خطأ: المجلد {source_dir} غير موجود.")
    if not os.path.exists(output_dir): os.makedirs(output_dir, exist_ok=True)
    
    valid_extensions = ('.jpg', '.jpeg', '.png', '.webp')
    image_files = [os.path.join(source_dir, f) for f in os.listdir(source_dir) if f.lower().endswith(valid_extensions)]
    if not image_files: return print(f"تنبيه: لا يوجد صور.")

    # فرز الصور رقمياً
    image_files.sort(key=lambda x: int(re.search(r'(\d+)', os.path.basename(x)).group(1)) if re.search(r'(\d+)', os.path.basename(x)) else 0)
    
    # --- منطق التجميع الذكي حسب الحجم (8MB - 9MB) ---
    batches = []
    current_batch = []
    current_size = 0
    
    for img_path in image_files:
        size = os.path.getsize(img_path)
        # إذا كانت الإضافة ستتخطى الـ 9 ميجابايت، نغلق الدفعة الحالية
        if current_size + size > MAX_BATCH_SIZE_BYTES and current_batch:
            batches.append(current_batch)
            current_batch = [img_path]
            current_size = size
        else:
            current_batch.append(img_path)
            current_size += size
            # إذا وصلنا للـ 8 ميجابايت بالضبط أو أكثر قليلاً (ولكن أقل من 9)، نفضل الإغلاق
            if current_size >= TARGET_BATCH_SIZE_BYTES:
                batches.append(current_batch)
                current_batch = []
                current_size = 0
                
    if current_batch:
        batches.append(current_batch)
    
    print(f"🚀 تم تقسيم الصور إلى {len(batches)} دفعات (بمتوسط 8 ميجابايت للدفعة).")
    
    process_url = f"{base_url.rstrip('/')}/process"
    success_all = True
    
    with ThreadPoolExecutor(max_workers=1) as executor:
        futures = {executor.submit(process_batch, batch, idx, base_url, process_url, output_dir, valid_extensions): idx for idx, batch in enumerate(batches, 1)}
        for future in as_completed(futures):
            if not future.result(): success_all = False

    if success_all:
        print(f"\n✅ مبروك! اكتمل تلوين الفصل بالكامل.")
        add_to_history("colored", chapter_name)
    return success_all

if __name__ == "__main__":
    print("--- [نظام Evoars الشامل: تشغيل وتلوين تلقائي] ---")
    
    # سؤال للمستخدم عن تشغيل الخدمات
    choice = input("هل تريد تشغيل السيرفر والنفق الآن؟ (y/n): ").strip().lower()
    if choice == 'y':
        start_background_services()
    
    usr_url = input(f"أدخل رابط السيرفر العام (اضغط Enter لاستخدام {DEFAULT_BASE_URL}): ").strip()
    target_url = usr_url if usr_url else DEFAULT_BASE_URL
    
    # تحديد المجلدات حسب البيئة (Codespaces أو Local)
    is_codespace = os.path.exists("/workspaces")
    if is_codespace:
        base_path = "/workspaces/MANGA-color"
        src_folder = os.path.join(base_path, "source_images")
        out_folder = os.path.join(base_path, "results")
    else:
        src_folder = r"C:\Users\abdob\Desktop\mang\source_images"
        out_folder = r"C:\Users\abdob\Desktop\mang\results"
    
    if not os.path.exists(src_folder): os.makedirs(src_folder, exist_ok=True)
    
    colorize_chapter(src_folder, out_folder, target_url)



