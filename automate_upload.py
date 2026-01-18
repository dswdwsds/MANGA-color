import os
import time
import json
import re
import io
import zipfile
import shutil
import cloudscraper
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
    
    # محاولة 3 مرات
    for attempt in range(3):
        files = []
        try:
            for img_path in batch:
                files.append(('images', (os.path.basename(img_path), open(img_path, 'rb'), 'image/jpeg')))
            
            if attempt > 0:
                print(f"[Thread] إعادة محاولة الدفعة {batch_idx} (محاولة {attempt + 1})...")

            response = scraper.post(process_url, data=data, files=files, timeout=600)
            
            # إغلاق الملفات
            for _, file_info in files:
                file_info[1].close()

            if response.status_code == 200:
                result = response.json()
                download_url = result.get('download_url')
                if download_url:
                    if not download_url.startswith('http'):
                        download_url = f"{base_url}{download_url}"
                    
                    print(f"[Thread] تم تلوين الدفعة {batch_idx} بنجاح! جاري التحميل...")
                    r_download = scraper.get(download_url)
                    
                    # فك الضغط مباشرة في مجلد المخرجات (Thread Safe تقريباً لأن الملفات مختلفة)
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
        
        if attempt < 2:
            time.sleep(5) # انتظار قبل الإعادة

    return success

def colorize_chapter(source_dir, output_dir):
    """
    تقوم هذه الدالة برفع الصور من مجلد معين لتلوينها بشكل متوازي (Parallel Processing).
    """
    if not os.path.exists(source_dir):
        print(f"خطأ: المجلد {source_dir} غير موجود.")
        return False

    if not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)

    valid_extensions = ('.jpg', '.jpeg', '.png', '.webp')
    image_files = [os.path.join(source_dir, f) for f in os.listdir(source_dir) if f.lower().endswith(valid_extensions)]
    
    if not image_files:
        print(f"تحذير: لم يتم العثور على أي صور في {source_dir}")
        return False

    # فرز الصور
    image_files.sort(key=lambda x: int(re.search(r'(\d+)', os.path.basename(x)).group(1)) if re.search(r'(\d+)', os.path.basename(x)) else 0)
    
    # تقسيم الصور إلى دفعات (3 صور لكل دفعة)
    batch_size = 3
    batches = [image_files[i:i + batch_size] for i in range(0, len(image_files), batch_size)]
    
    print(f"[{datetime.now().strftime('%H:%M:%S')}] تم تقسيم {len(image_files)} صورة إلى {len(batches)} دفعات.")
    print(f"🚀 بدء المعالجة المتوازية (3 دفعات في وقت واحد)...")

    base_url = "https://koesan-mangaspaces.hf.space"
    process_url = f"{base_url}/process"
    
    success_all = True
    
    # تشغيل الدفعات بشكل متوازي (بحد أقصى 3 خيوط)
    with ThreadPoolExecutor(max_workers=3) as executor:
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
    else:
        print(f"\n⚠️ انتهت العملية مع وجود بعض الأخطاء.")
        
    return success_all

if __name__ == "__main__":
    src = r"C:\Users\abdob\Desktop\mang\source_images"
    out = r"C:\Users\abdob\Desktop\mang\results"
    colorize_chapter(src, out)

