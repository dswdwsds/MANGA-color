import os
import time
import json
import re
import io
import zipfile
import shutil
import cloudscraper
import subprocess
import requests
import sys
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

def process_batch(batch, batch_idx, base_url, process_url, output_dir, valid_extensions):
    """
    معالجة دفعة واحدة من الصور: رفع، انتظار، تحميل، وفك ضغط.
    """
    scraper = cloudscraper.create_scraper()
    print(f"\n--- [Thread] بدء معالجة الدفعة {batch_idx} ({len(batch)} صور) ---")
    
    data = {'operation': 'colorize'}
    success = False
    
    # محاولة 5 مرات مع انتظار تصاعدي
    max_retries = 5
    for attempt in range(max_retries):
        files = []
        try:
            for img_path in batch:
                files.append(('images', (os.path.basename(img_path), open(img_path, 'rb'), 'image/jpeg')))
            
            if attempt > 0:
                print(f"[Thread] إعادة محاولة الدفعة {batch_idx} (محاولة {attempt + 1}/{max_retries})...")

            response = scraper.post(process_url, data=data, files=files, timeout=600)
            
            # إغلاق الملفات
            for _, file_info in files:
                file_info[1].close()

            if response.status_code == 200:
                result = response.json()
                download_url = result.get('zip_download_url') or result.get('download_url')
                if download_url:
                    if not download_url.startswith('http'):
                        download_url = f"{base_url}{download_url}"
                    
                    print(f"[Thread] تم تلوين الدفعة {batch_idx} بنجاح! جاري التحميل...")
                    r_download = scraper.get(download_url)
                    
                    # فك الضغط
                    with zipfile.ZipFile(io.BytesIO(r_download.content)) as z:
                        for member in z.infolist():
                            if member.filename.lower().endswith(valid_extensions):
                                filename = os.path.basename(member.filename)
                                source = z.open(member)
                                target_path = os.path.join(output_dir, filename)
                                with open(target_path, "wb") as target:
                                    shutil.copyfileobj(source, target)
                    print(f"✅ [Thread] تم حفظ صور الدفعة {batch_idx}.")
                    success = True
                    break 
                else:
                    print(f"⚠️ [Thread] فشل الدفعة {batch_idx}: لا يوجد رابط تحميل.")
            else:
                print(f"⚠️ [Thread] فشل الدفعة {batch_idx} بكود: {response.status_code}")
            
        except Exception as e:
            print(f"❌ [Thread] خطأ في الدفعة {batch_idx} (محاولة {attempt + 1}): {e}")
            # التأكد من إغلاق الملفات
            for _, file_info in files:
                if not file_info[1].closed:
                    file_info[1].close()
        
        if attempt < max_retries - 1:
            wait_time = 30 * (attempt + 1)  # انتظار 30، 60، 90، 120 ثانية...
            print(f"[Thread] انتظار {wait_time} ثانية قبل إعادة المحاولة للدفعة {batch_idx}...")
            time.sleep(wait_time)

    return success

import threading

HISTORY_FILE = "history.json"
history_lock = threading.Lock()

def load_history():
    if not os.path.exists(HISTORY_FILE):
        return {"scraped": [], "colored": []}
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {"scraped": [], "colored": []}

def save_history(history):
    with history_lock:
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=4)

def add_to_history(category, item):
    """
    category: 'scraped' or 'colored'
    item: identifier (e.g. folder name or path)
    """
    with history_lock:
        history = load_history()
        if item not in history.get(category, []):
            if category not in history:
                history[category] = []
            history[category].append(item)
            # حفظ بدون القفل الداخلي لأننا بالفعل داخل قفل (save_history لها قفل أيضاً، لذا نكتب مباشرة)
            # لتجنب Deadlock، سنكرر كود الحفظ هنا أو نعدل save_history
            # الحل الأبسط: نسخ كود الحفظ هنا مباشرة لتجنب التداخل
            with open(HISTORY_FILE, "w", encoding="utf-8") as f:
                json.dump(history, f, ensure_ascii=False, indent=4)

def is_in_history(category, item):
    history = load_history()
    return item in history.get(category, [])

def ensure_server_running():
    """
    يتأكد من أن سيرفر الموديل المحلي يعمل، وإذا لم يكن يعمل يقوم بتشغيله.
    """
    server_url = "http://127.0.0.1:7860"
    
    # تحديد مسار المجلد الأساسي للمشروع بشكل ديناميكي
    current_script_dir = os.path.dirname(os.path.abspath(__file__))
    working_dir = os.path.join(current_script_dir, "Evoars_local", "Evoars-main")
    
    # التأكد من صحة المسار في بيئات Linux
    if not os.path.exists(working_dir):
        # محاولة أخرى إذا كان المجلد في نفس مستوى السكربت مباشرة
        working_dir = os.path.join(current_script_dir, "Evoars-main")
        
    try:
        # محاولة الاتصال بالسيرفر
        response = requests.get(server_url, timeout=2)
        if response.status_code == 200:
            print("✅ السيرفر يعمل بالفعل.")
            return True
    except:
        print("🚀 السيرفر لا يعمل. جاري تشغيله الآن...")
        
    # تشغيل السيرفر في خلفية جديدة مع تسجيل الأخطاء
    try:
        log_file_path = os.path.join(current_script_dir, "server_log.txt")
        log_file = open(log_file_path, "a", encoding="utf-8")
        log_file.write(f"\n--- بدء محاولة التشغيل: {datetime.now()} ---\n")
        
        # نستخدم sys.executable لضمان تشغيل السيرفر بنفس نسخة بايثون الحالية
        if os.name == 'nt': # Windows
            subprocess.Popen([sys.executable, "app.py"], cwd=working_dir, creationflags=subprocess.CREATE_NEW_CONSOLE)
        else: # Linux / Codespaces
            subprocess.Popen([sys.executable, "app.py"], cwd=working_dir, stdout=log_file, stderr=log_file)
        
        # الانتظار حتى يعمل السيرفر
        print(f"⏳ في انتظار استجابة السيرفر... (يمكنك مراجعة {os.path.basename(log_file_path)} للتفاصيل)")
        max_wait = 30 # 30 محاولة * 5 ثواني = 150 ثانية
        for i in range(max_wait):
            time.sleep(5)
            try:
                if requests.get(server_url, timeout=2).status_code == 200:
                    print("✅ تم تشغيل السيرفر بنجاح!")
                    return True
            except:
                print(f"[{i+1}/{max_wait}] في انتظار السيرفر...")
        
        print("❌ فشل تشغيل السيرفر تلقائياً.")
        return False
    except Exception as e:
        print(f"❌ خطأ عند تشغيل السيرفر: {e}")
        return False

def colorize_chapter(source_dir, output_dir):
    """
    تقوم هذه الدالة برفع الصور من مجلد معين لتلوينها بشكل متوازي.
    تستفيد من history.json لتخطي ما تم إنجازه.
    """
    # التأكد من تشغيل السيرفر أولاً
    ensure_server_running()
    
    chapter_name = os.path.basename(source_dir)
    # مفتاح التاريخ يمكن أن يكون المسار الكامل أو اسم الفصل فقط.
    # لنتفق على استخدام "اسم المجلد" ليكون محمولاً، أو المسار النسبي.
    # بما أن المسارات قد تتغير، اسم الفصل "Jujutsu Kaisen/فصل رقم X" هو الأفضل.
    # لكن source_dir قد يكون مطلقاً. سنستخدم "اسم المجلد الأب/اسم الفصل".
    
    try:
        parent = os.path.basename(os.path.dirname(source_dir))
        identifier = f"{parent}/{chapter_name}"
    except:
        identifier = chapter_name

    if is_in_history("colored", identifier):
        print(f"⏩ [تخطي] الفصل {identifier} تم تلوينه سابقاً حسب السجل.")
        return True

    if not os.path.exists(source_dir):
        print(f"خطأ: المجلد {source_dir} غير موجود.")
        return False
    
    # ... التحقق من output_dir
    if not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)
    
    valid_extensions = ('.jpg', '.jpeg', '.png', '.webp')
    image_files = [os.path.join(source_dir, f) for f in os.listdir(source_dir) if f.lower().endswith(valid_extensions)]
    
    if not image_files:
        print(f"تحذير: لم يتم العثور على أي صور في {source_dir}")
        return False

    # التحقق من وجود الملفات مسبقاً (Fallback System)
    # إذا كانت المجلد يحتوي على صور، نعتبره مكتملاً لتوفير الوقت
    if os.path.exists(output_dir):
        existing_colored_images = [f for f in os.listdir(output_dir) if f.lower().endswith(valid_extensions)]
        # إذا كان عدد الصور الملونة يساوي أو أكبر من الصور الأصلية (أو قريب منها)
        if len(existing_colored_images) >= len(image_files):
            print(f"⏩ [تخطي] الفصل {identifier} موجود بالفعل على القرص ({len(existing_colored_images)} صورة).")
            # نضيفه للسجل للمستقبل
            add_to_history("colored", identifier)
            return True
        elif len(existing_colored_images) > 0:
             print(f"⚠️ الفصل {identifier} موجود جزئياً ({len(existing_colored_images)}/{len(image_files)}). سيتم استكماله...")
             # هنا يمكننا تصفية image_files لاستبعاد ما تم تلوينه
             image_files = [f for f in image_files if os.path.basename(f) not in existing_colored_images]
             if not image_files:
                 print(f"⏩ [تخطي] جميع ملفات الفصل {identifier} موجودة.")
                 add_to_history("colored", identifier)
                 return True

    # سنمضي في التلوين.

    # فرز الصور
    image_files.sort(key=lambda x: int(re.search(r'(\d+)', os.path.basename(x)).group(1)) if re.search(r'(\d+)', os.path.basename(x)) else 0)
    
    # تقسيم الصور
    batch_size = 3
    batches = [image_files[i:i + batch_size] for i in range(0, len(image_files), batch_size)]
    
    print(f"[{datetime.now().strftime('%H:%M:%S')}] تلوين الفصل: {identifier}")
    print(f"🚀 بدء المعالجة المتسلسلة (خط واحد) لضمان أقصى استقرار للسيرفر...")

    base_url = "http://127.0.0.1:7860"
    process_url = f"{base_url}/process"
    
    success_all = True
    
    # 1 worker only to prevent server overload
    with ThreadPoolExecutor(max_workers=1) as executor:
        futures = {executor.submit(process_batch, batch, idx, base_url, process_url, output_dir, valid_extensions): idx for idx, batch in enumerate(batches, 1)}
        
        for future in as_completed(futures):
            batch_idx = futures[future]
            try:
                if not future.result():
                    success_all = False
                    print(f"❌ فشلت معالجة الدفعة {batch_idx} نهائياً.")
            except Exception as exc:
                print(f"❌ حدث استثناء غير متوقع في الدفعة {batch_idx}: {exc}")
                success_all = False

    if success_all:
        print(f"\n✅ اكتمل تلوين كافة الدفعات بنجاح في: {output_dir}")
        # إضافة إلى التاريخ عند النجاح الكامل فقط
        add_to_history("colored", identifier)
    else:
        print(f"\n⚠️ انتهت العملية مع وجود بعض الأخطاء، لن يتم الحفظ في السجل.")
        
    return success_all

if __name__ == "__main__":
    src = r"C:\Users\abdob\Desktop\mang\source_images"
    out = r"C:\Users\abdob\Desktop\mang\results"
    colorize_chapter(src, out)

