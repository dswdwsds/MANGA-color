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
from automate_upload import colorize_chapter  # استيراد دالة التلوين

def slugify(text):
    """تحويل النص إلى صيغة مناسبة للروابط (slug)"""
    text = text.lower()
    text = re.sub(r'[^a-z0-9\s-]', '', text)
    text = re.sub(r'\s+', '-', text).strip('-')
    return text

def extract_chapter_number(text):
    """استخراج أول رقم يظهر في النص (رقم الفصل)"""
    match = re.search(r'(\d+)', text)
    return match.group(1) if match else None

def scrape_manga(url, auto_next=False, processed_urls=None, scraped_chapters=None):
    if processed_urls is None:
        processed_urls = set()
    
    if scraped_chapters is None:
        scraped_chapters = []

    if url in processed_urls:
        print(f"تمت معالجة هذا الرابط مسبقاً، التوقف لتجنب التكرار اللانهائي: {url}")
        return
    
    processed_urls.add(url)
    
    scraper = curlr.Session()
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] جاري جلب الصفحة: {url}...")
    
    try:
        response = scraper.get(url, impersonate="chrome110", timeout=30)
        if response.status_code != 200:
            print(f"فشل في جلب الصفحة. كود الحالة: {response.status_code}")
            return
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # 1. استخراج العنوان لإنشاء المجلدات بشكل هرمي
        title_tag = soup.find('title')
        raw_title_full = title_tag.text.strip() if title_tag else "Manga"
        
        title_div = soup.find('div', class_='section-title')
        if title_div and title_div.find('h4'):
            raw_title = title_div.find('h4').text.strip()
        else:
            raw_title = raw_title_full
        
        # تقسيم العنوان (مثل Jujutsu Kaisen / 2)
        if '/' in raw_title:
            parts = raw_title.split('/')
            manga_name = parts[0].strip()
            chapter_num = extract_chapter_number(parts[1]) if len(parts) > 1 else extract_chapter_number(raw_title)
        else:
            manga_name = raw_title.split('شابتر')[0].strip() if 'شابتر' in raw_title else raw_title
            chapter_num = extract_chapter_number(raw_title)
            
        # تنظيف الأسماء
        manga_folder = "".join([c for c in manga_name if c.isalnum() or c in (' ', '-', '_')]).strip()
        chapter_folder = f"فصل رقم {chapter_num}" if chapter_num else "فصل غير معروف"
        
        # إنشاء المسار الكامل
        full_path = os.path.join(manga_folder, chapter_folder)
        
        if not os.path.exists(full_path):
            os.makedirs(full_path, exist_ok=True)
            print(f"تم إنشاء مجلد جديد: {full_path}")
        else:
            print(f"المجلد {full_path} موجود بالفعل، سيتم التحقق من الملفات.")

        # نستخدم full_path كمكان لحفظ الصور
        folder_name = full_path
        
        # إضافة المجلد لقائمة العمل (للتلوين لاحقاً)
        if folder_name not in scraped_chapters:
            scraped_chapters.append(folder_name)

        # 2. البحث عن روابط الصور في كامل النص باستخدام Regex
        img_urls = re.findall(r'/get_image/[a-zA-Z0-9]+', response.text)
        img_urls = list(dict.fromkeys(img_urls))
        
        if not img_urls:
            print("لم يتم العثور على أي روابط صور في هذه الصفحة.")
        else:
            print(f"تم العثور على {len(img_urls)} رابط صورة.")
            
            base_url = "https://mangatime.org"
            for i, img_rel_url in enumerate(img_urls, 1):
                target_filename = f"{i}.webp"
                target_path = os.path.join(folder_name, target_filename)
                
                if os.path.exists(target_path):
                    continue
                
                img_full_url = urljoin(base_url, img_rel_url)
                try:
                    img_response = scraper.get(img_full_url, impersonate="chrome110", timeout=20)
                    if img_response.status_code == 200:
                        img_data = Image.open(io.BytesIO(img_response.content))
                        img_data.save(target_path, "WEBP")
                        print(f"تم حفظ الصفحة {i} في {folder_name}")
                except Exception as e:
                    print(f"خطأ في تحميل الصفحة {i}: {e}")

        # 3. معالجة الانتقال التلقائي للفصل التالي باستخدام JSON-LD
        if auto_next:
            next_url = None
            try:
                # البحث عن بيانات JSON-LD التي تحتوي على قائمة الفصول
                json_ld_scripts = soup.find_all('script', type='application/ld+json')
                chapter_list = []
                for script in json_ld_scripts:
                    try:
                        data = json.loads(script.string)
                        if 'hasPart' in data:
                            chapter_list = data['hasPart']
                            break
                    except:
                        continue
                
                if chapter_list:
                    # العثور على الفهرس الحالي بناءً على رقم الفصل
                    found_current = False
                    for i, chapter in enumerate(chapter_list):
                        chap_name = chapter.get('name', '')
                        chap_num = extract_chapter_number(chap_name)
                        
                        if chap_num == chapter_num:
                            # الفصل التالي موجود في المصفوفة؟
                            if i + 1 < len(chapter_list):
                                next_chapter = chapter_list[i + 1]
                                next_name = next_chapter.get('name', '')
                                next_num = extract_chapter_number(next_name)
                                
                                # بناء الرابط
                                manga_base_name = raw_title.split('/')[0].strip()
                                manga_slug = slugify(manga_base_name)
                                next_url = f"https://mangatime.org/manga/{manga_slug}/chapter-{next_num}"
                                print(f"\n[تنبيه] تم العثور على الفصل التالي: {next_name}")
                                break
                
                if next_url:
                    time.sleep(2)
                    scrape_manga(next_url, auto_next=True, processed_urls=processed_urls, scraped_chapters=scraped_chapters)
                else:
                    print("\nلم يتم العثور على فصل تالٍ في قائمة البيانات. التوقف.")
                    
            except Exception as e:
                print(f"خطأ أثناء البحث عن الفصل التالي: {e}")

    except Exception as e:
        print(f"حدث خطأ غير متوقع: {e}")

if __name__ == "__main__":
    # رابط البداية
    start_url = "https://mangatime.org/5howVsy"
    
    print("--- Manga Scraper Pro ---")
    choice = input("هل تريد الانتقال للفصل التالي تلقائياً عند الانتهاء؟ (y/n): ").lower()
    should_auto = True if choice == 'y' else False
    
    # قائمة لتخزين الفصول المسحوبة
    scraped_chapters_list = []
    
    # 1. مرحلة السحب الكامل
    print("\n>>> بدء مرحلة السحب (Scraping Phase) <<<")
    scrape_manga(start_url, auto_next=should_auto, scraped_chapters=scraped_chapters_list)
    
    # 2. مرحلة التلوين الكامل
    if scraped_chapters_list:
        print("\n" + "="*50)
        print(f">>> تم الانتهاء من السحب. بدء مرحلة التلوين لـ {len(scraped_chapters_list)} فصول <<<")
        print("="*50)
        
        for chapter_path in scraped_chapters_list:
            # حساب مسار مجلد التلوين الموازي (Jujutsu Kaisen color)
            manga_dir = os.path.dirname(chapter_path)      # Jujutsu Kaisen
            chapter_dir_name = os.path.basename(chapter_path) # فصل رقم 2
            
            manga_color_dir = f"{manga_dir} color"
            color_output_path = os.path.join(manga_color_dir, chapter_dir_name)
            
            print(f"\n[تلوين] جاري معالجة الفصل: {chapter_dir_name}...")
            colorize_chapter(chapter_path, color_output_path)
        
        print("\n✅ تمت جميع العمليات (سحب وتلوين) بنجاح!")
    else:
        print("\nلم يتم سحب أي فصول لتلوينها.")