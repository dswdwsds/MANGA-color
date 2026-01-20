import os
import io
import re
import time
import json
from bs4 import BeautifulSoup
from PIL import Image
from urllib.parse import urljoin
from datetime import datetime
from curl_cffi import requests as curlr
from concurrent.futures import ThreadPoolExecutor

# استيراد دالة التلوين
from automate_upload import colorize_chapter, is_in_history, add_to_history, DEFAULT_BASE_URL, start_background_services

def slugify(text):
    text = text.lower()
    text = re.sub(r'[^a-z0-9\s-]', '', text)
    text = re.sub(r'\s+', '-', text).strip('-')
    return text

def extract_chapter_number(text):
    match = re.search(r'(\d+)', text)
    return match.group(1) if match else None

def download_single_image(scraper, base_url, img_rel_url, i, folder_name):
    target_filename = f"{i}.webp"
    target_path = os.path.join(folder_name, target_filename)
    
    # لا نحتاج للتحقق من التاريخ هنا، لأننا نتحقق من الفصل ككل.
    if os.path.exists(target_path):
        return
    
    img_full_url = urljoin(base_url, img_rel_url)
    try:
        # 30 ثانية timeout للصورة
        img_response = scraper.get(img_full_url, impersonate="chrome110", timeout=30)
        if img_response.status_code == 200:
            img_data = Image.open(io.BytesIO(img_response.content))
            img_data.save(target_path, "WEBP")
            print(f"[صورة] تم حفظ {i}.webp في {os.path.basename(folder_name)}")
        else:
            print(f"[خطأ] فشل تحميل {i}.webp: كود {img_response.status_code}")
    except Exception as e:
        print(f"[خطأ] استثناء في {target_filename}: {e}")

# مخزن مؤقت لاسم المجلد الخاص بالمانجا لتسريع عملية التخطي دون طلبات شبكة
MANGA_NAME_CACHE = {}

def process_chapter_download(url, scraped_chapters_list):
    """
    تقوم هذه الدالة بمهام "العامل":
    1. فتح رابط الفصل لاستخراج الصور.
    2. تحميل الصور بالتوازي (Thread داخل Thread).
    """
    scraper = curlr.Session()
    
    # --- محاولة التخطي الذكي (Ultra-Fast Skip) ---
    # نحاول استخراج رقم الفصل و الـ slug من الرابط
    # الرابط المتوقع: https://mangatime.org/manga/jujutsu-kaisen/chapter-50
    try:
        match = re.search(r'/manga/([^/]+)/chapter-(\d+)', url)
        if match:
            slug, num = match.groups()
            
            # إذا كنا نعرف اسم المجلد لهذه المانجا مسبقاً (من عملية سابقة في نفس الجلسة)
            if slug in MANGA_NAME_CACHE:
                manga_folder_cached = MANGA_NAME_CACHE[slug]
                chapter_folder_cached = f"فصل رقم {num}"
                identifier_cached = f"{manga_folder_cached}/{chapter_folder_cached}"
                
                if is_in_history("scraped", identifier_cached):
                    print(f"⏩ [Worker] تخطي سريع للفصل {identifier_cached} (من الكاش والسجل).")
                    full_path = os.path.join(manga_folder_cached, chapter_folder_cached)
                    if full_path not in scraped_chapters_list:
                        scraped_chapters_list.append(full_path)
                    return
    except Exception as e:
        pass # إذا فشل التحليل المسبق، نكمل للطريقة العادية
    # -----------------------------------------------

    try:
        response = scraper.get(url, impersonate="chrome110", timeout=30)
        if response.status_code != 200:
            print(f"[Worker] فشل في جلب الصفحة {url}")
            return

        soup = BeautifulSoup(response.text, 'html.parser')
        
        # استخراج العنوان والمجلد
        title_tag = soup.find('title')
        raw_title = title_tag.text.strip() if title_tag else "Manga"
        
        title_div = soup.find('div', class_='section-title')
        if title_div and title_div.find('h4'):
            raw_title = title_div.find('h4').text.strip()
            
        if '/' in raw_title:
            parts = raw_title.split('/')
            manga_name = parts[0].strip()
            chapter_num = extract_chapter_number(parts[1]) if len(parts) > 1 else extract_chapter_number(raw_title)
        else:
            manga_name = raw_title.split('شابتر')[0].strip() if 'شابتر' in raw_title else raw_title
            chapter_num = extract_chapter_number(raw_title)
            
        manga_folder = "".join([c for c in manga_name if c.isalnum() or c in (' ', '-', '_')]).strip()
        chapter_folder = f"فصل رقم {chapter_num}" if chapter_num else "فصل غير معروف"
        
        # حفظ الاسم في الكاش للمرات القادمة
        try:
             # نحاول استخراج الـ slug من الرابط الحالي لحفظه
             match_slug = re.search(r'/manga/([^/]+)/chapter-', url)
             if match_slug:
                 slug_key = match_slug.group(1)
                 if slug_key not in MANGA_NAME_CACHE:
                     MANGA_NAME_CACHE[slug_key] = manga_folder
        except: pass

        # معرف الفصل للتاريخ: "MangaName/ChapterName"
        # نستخدم manga_folder و chapter_folder للتوافق
        identifier = f"{manga_folder}/{chapter_folder}"
        
        # التحقق من التاريخ
        if is_in_history("scraped", identifier):
            print(f"⏩ [Worker] تخطي الفصل {identifier} (موجود في السجل).")
            full_path = os.path.join(manga_folder, chapter_folder)
            if full_path not in scraped_chapters_list:
                scraped_chapters_list.append(full_path)
            return

        print(f"\n[Worker] بدء معالجة الفصل الجديد: {identifier}...")
        full_path = os.path.join(manga_folder, chapter_folder)
        
        if not os.path.exists(full_path):
            os.makedirs(full_path, exist_ok=True)
            print(f"[Worker] مجلد جديد: {chapter_folder}")
        
        # إضافة للقائمة
        if full_path not in scraped_chapters_list:
            scraped_chapters_list.append(full_path)

        # استخراج الصور
        img_urls = re.findall(r'/get_image/[a-zA-Z0-9]+', response.text)
        img_urls = list(dict.fromkeys(img_urls))
        
        if img_urls:
            print(f"[Worker] {chapter_folder}: تم العثور على {len(img_urls)} صورة. بدء التحميل...")
            base_url = "https://mangatime.org"
            
            # تحميل الصور بالتوازي
            with ThreadPoolExecutor(max_workers=5) as img_executor:
                futures = []
                for i, img_rel_url in enumerate(img_urls, 1):
                    futures.append(img_executor.submit(download_single_image, scraper, base_url, img_rel_url, i, full_path))
                
                # انتظار انتهاء صور هذا الفصل
                global_success = True # فرضية
                for f in futures:
                    f.result() # إذا حدث exception لن يوقف الكل بسبب try/catch في الدالة
            
            # نفترض النجاح إذا وصلنا هنا ولم يكن هناك exceptions قاتلة
            print(f"[Worker] ✅ تم الانتهاء من الفصل: {chapter_folder}")
            add_to_history("scraped", identifier)
            
        else:
            print(f"[Worker] لم يتم العثور على صور في {chapter_folder}")

    except Exception as e:
        print(f"[Worker] خطأ في معالجة الفصل {url}: {e}")


def crawl_and_dispatch(start_url, scraped_chapters_list):
    """
    المهمة الرئيسية:
    1. تفتح الرابط الحالي.
    2. ترسل الرابط الحالي لعمال التحميل (ThreadPool).
    3. تبحث عن الرابط القادم وتنتقل إليه فوراً.
    """
    # مجمع الخيوط للفصول (3 فصول في وقت واحد)
    chapter_executor = ThreadPoolExecutor(max_workers=3)
    
    current_url = start_url
    processed_urls = set()
    futures = []

    crawler_session = curlr.Session()

    while current_url:
        if current_url in processed_urls:
            print("[Crawler] تم اكتشاف تكرار في الرابط. إيقاف الزحف.")
            break
        
        processed_urls.add(current_url)
        
        # 1. إرسال المهمة للعمال فوراً (Fire and Forget)
        # سيقوم العامل بتحميل الصفحة مرة أخرى لتحميل الصور، هذا مقبول لعزل العمليات
        print(f"\n[Crawler] >> إرسال الفصل لقائمة الانتظار: {current_url}")
        future = chapter_executor.submit(process_chapter_download, current_url, scraped_chapters_list)
        futures.append(future)

        # 2. البحث عن الرابط التالي (Discovery)
        print(f"[Crawler] البحث عن الفصل التالي...")
        try:
            # نحتاج لقراءة الصفحة هنا أيضاً لمعرفة الرابط التالي
            # (يمكن تحسين هذا بتمرير المحتوى، لكن للتبسيط ولتجنب مشاكل الذاكرة سنفصل الطلبات)
            resp = crawler_session.get(current_url, impersonate="chrome110", timeout=20)
            if resp.status_code != 200:
                print("[Crawler] فشل الوصول للصفحة للاستكشاف.")
                break
                
            soup = BeautifulSoup(resp.text, 'html.parser')
            
            # منطق استخراج الرابط التالي (JSON-LD)
            next_url = None
            json_ld_scripts = soup.find_all('script', type='application/ld+json')
            chapter_list = []
            
            # تحديد رقم الفصل الحالي من العنوان
            title_tag = soup.find('title')
            raw_title = title_tag.text.strip() if title_tag else ""
            if '/' in raw_title:
                curr_num = extract_chapter_number(raw_title.split('/')[1])
            else:
                curr_num = extract_chapter_number(raw_title)

            for script in json_ld_scripts:
                try:
                    data = json.loads(script.string)
                    if 'hasPart' in data:
                        chapter_list = data['hasPart']
                        break
                except: continue
            
            if chapter_list and curr_num:
                for i, chapter in enumerate(chapter_list):
                    c_num = extract_chapter_number(chapter.get('name', ''))
                    if c_num == curr_num:
                        if i + 1 < len(chapter_list):
                            next_chap = chapter_list[i+1]
                            nxt_num = extract_chapter_number(next_chap.get('name', ''))
                            
                            manga_base = raw_title.split('/')[0].strip() if '/' in raw_title else raw_title.split('شابتر')[0].strip()
                            slug = slugify(manga_base)
                            next_url = f"https://mangatime.org/manga/{slug}/chapter-{nxt_num}"
                            print(f"[Crawler] تم اكتشاف الرابط التالي: .../chapter-{nxt_num}")
                            break
            
            if next_url:
                current_url = next_url
                # تأخير بسيط جداً للاستكشاف لتجنب الحظر
                time.sleep(0.5) 
            else:
                print("[Crawler] لم يتم العثور على فصل تالٍ. انتهاء الزحف.")
                break

        except Exception as e:
            print(f"[Crawler] خطأ أثناء الاستكشاف: {e}")
            break
            
    # انتظار انتهاء جميع العمال
    print("\n[Manga Scraper] تم الانتهاء من الاستكشاف. في انتظار اكتمال تحميل الفصول...")
    chapter_executor.shutdown(wait=True)
    print("[Manga Scraper] تم الانتهاء من جميع الفصول.")


if __name__ == "__main__":
    start_url = "https://mangatime.org/5howVsy"
    print("--- Manga Scraper Pro (Parallel Chapters) ---")
    
    scraped_chapters_list = []
    
    print("\n>>> بدء مرحلة السحب المتوازي (Parallel Scraping) <<<")
    crawl_and_dispatch(start_url, scraped_chapters_list)
    # سؤال للمستخدم عن تشغيل الخدمات
    choice = input("هل تريد تشغيل السيرفر والنفق الآن؟ (y/n): ").strip().lower()
    if choice == 'y':
        target_url = start_background_services()
    else:
        usr_url = input(f"أدخل رابط السيرفر العام (اضغط Enter لاستخدام {DEFAULT_BASE_URL}): ").strip()
        target_url = usr_url if usr_url else DEFAULT_BASE_URL
    
    if scraped_chapters_list:
        print("\n" + "="*50)
        print(f">>> بدء مرحلة التلوين لـ {len(scraped_chapters_list)} فصول <<<")
        print("="*50)
        
        # ترتيب القائمة لضمان التلون بالترتيب (اختياري)
        # scraped_chapters_list.sort(key=lambda x: int(extract_chapter_number(os.path.basename(x)) or 0))

        for chapter_path in scraped_chapters_list:
            manga_dir = os.path.dirname(chapter_path)
            chapter_dir_name = os.path.basename(chapter_path)
            manga_color_dir = f"{manga_dir} color"
            color_output_path = os.path.join(manga_color_dir, chapter_dir_name)
            
            print(f"\n[تلوين] معالجة: {chapter_dir_name}...")
            colorize_chapter(chapter_path, color_output_path, target_url)
        
        print("\n✅ تمت المهمة بالكامل!")
    else:
        print("\nلم يتم سحب أي فصول.")
