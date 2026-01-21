import os
import logging
from PIL import Image, ImageDraw, ImageFont
import textwrap
import arabic_reshaper
from bidi.algorithm import get_display
import io
import requests

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s')

def download_font_if_missing(font_path, url):
    """تحميل الفونت في حال كان مفقوداً"""
    if not os.path.exists(font_path):
        logging.info(f"Downloading font to {font_path}...")
        try:
            font_dir = os.path.dirname(font_path)
            if font_dir and not os.path.exists(font_dir):
                os.makedirs(font_dir, exist_ok=True)
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            with open(font_path, 'wb') as f:
                f.write(response.content)
            logging.info("Font downloaded successfully.")
        except Exception as e:
            logging.error(f"Failed to download font: {e}")

def is_arabic_text(text):
    """التحقق من وجود أحرف عربية في النص"""
    return any('\u0600' <= char <= '\u06FF' for char in text)

def create_manga_page(text, page_width=800, page_height=1200, panel_padding=20):
    """
    إنشاء صفحة مانغا من النص المعطى
    
    Args:
        text: النص المراد تحويله لمانغا
        page_width: عرض الصفحة
        page_height: ارتفاع الصفحة
        panel_padding: المسافة بين اللوحات
    
    Returns:
        PIL Image object
    """
    # إنشاء صورة بيضاء
    img = Image.new('RGB', (page_width, page_height), color='white')
    draw = ImageDraw.Draw(img)
    
    # تحديد الفونت
    is_arabic = is_arabic_text(text)
    
    if is_arabic:
        # استخدام فونت عربي
        font_path = "fonts/Amiri-Regular.ttf"
        download_font_if_missing(font_path, "https://github.com/google/fonts/raw/main/ofl/amiri/Amiri-Regular.ttf")
        
        if not os.path.exists(font_path):
            if os.path.exists("C:/Windows/Fonts/arial.ttf"):
                font_path = "C:/Windows/Fonts/arial.ttf"
            elif os.path.exists("fonts/Arial.ttf"):
                font_path = "fonts/Arial.ttf"
            else:
                font_path = "fonts/mangat.ttf"
    else:
        font_path = "fonts/mangat.ttf"
    
    try:
        title_font = ImageFont.truetype(font_path, 40)
        text_font = ImageFont.truetype(font_path, 24)
        small_font = ImageFont.truetype(font_path, 18)
    except Exception as e:
        logging.warning(f"Could not load font from {font_path}: {e}. Using default font.")
        title_font = ImageFont.load_default()
        text_font = ImageFont.load_default()
        small_font = ImageFont.load_default()
    
    # تقسيم النص إلى جمل/فقرات
    paragraphs = [p.strip() for p in text.split('\n') if p.strip()]
    if not paragraphs:
        paragraphs = [text]
    
    # حساب عدد اللوحات المطلوبة
    num_panels = min(len(paragraphs), 6)  # حد أقصى 6 لوحات في الصفحة
    
    # تحديد تخطيط اللوحات (2 أعمدة × 3 صفوف)
    cols = 2
    rows = (num_panels + 1) // 2
    
    panel_width = (page_width - (cols + 1) * panel_padding) // cols
    panel_height = (page_height - (rows + 1) * panel_padding) // rows
    
    # رسم اللوحات
    for i, paragraph in enumerate(paragraphs[:num_panels]):
        row = i // cols
        col = i % cols
        
        # حساب موقع اللوحة
        x = panel_padding + col * (panel_width + panel_padding)
        y = panel_padding + row * (panel_height + panel_padding)
        
        # رسم إطار اللوحة
        draw.rectangle([x, y, x + panel_width, y + panel_height], 
                      outline='black', width=3)
        
        # معالجة النص العربي
        display_text = paragraph
        if is_arabic:
            try:
                reshaped = arabic_reshaper.reshape(paragraph)
                display_text = get_display(reshaped, base_dir='R')
            except Exception as e:
                logging.warning(f"Arabic reshaping error: {e}")
        
        # تقسيم النص ليتناسب مع اللوحة
        max_width = panel_width - 20
        wrapped_lines = []
        
        # حساب عدد الأحرف التقريبي في السطر
        try:
            char_width = draw.textlength("A", font=text_font)
        except:
            char_width = text_font.size * 0.6
        
        chars_per_line = int(max_width / char_width)
        wrapped_lines = textwrap.wrap(display_text, width=max(chars_per_line, 10))
        
        # حساب الارتفاع الكلي للنص
        try:
            line_height = text_font.size + 8
        except:
            line_height = 26
        
        total_text_height = len(wrapped_lines) * line_height
        
        # البدء من منتصف اللوحة
        text_y = y + (panel_height - total_text_height) // 2
        
        # رسم النص
        for line in wrapped_lines:
            try:
                line_width = draw.textlength(line, font=text_font)
            except:
                line_width = len(line) * char_width
            
            text_x = x + (panel_width - line_width) // 2
            
            # التأكد من عدم الخروج عن حدود اللوحة
            if text_y + line_height <= y + panel_height - 10:
                draw.text((text_x, text_y), line, fill='black', font=text_font)
                text_y += line_height
    
    return img

def main(in_memory_files, manga_text=None):
    """
    الدالة الرئيسية لتحويل النص إلى مانغا
    
    Args:
        in_memory_files: ملفات الإدخال (غير مستخدمة حالياً)
        manga_text: النص المراد تحويله لمانغا
    
    Returns:
        dict: قاموس يحتوي على اسم الملف والبيانات
    """
    results = {}
    
    if not manga_text:
        logging.error("No manga text provided.")
        return {"error.txt": b"No text provided for manga generation."}
    
    logging.info(f"Generating manga from text (length: {len(manga_text)} chars)")
    
    try:
        # إنشاء صفحة المانغا
        manga_page = create_manga_page(manga_text)
        
        # حفظ الصورة في الذاكرة
        img_byte_arr = io.BytesIO()
        manga_page.save(img_byte_arr, format='PNG')
        img_byte_arr = img_byte_arr.getvalue()
        
        # إضافة النتيجة
        results["manga_page.png"] = img_byte_arr
        
        logging.info("Manga page generated successfully.")
    except Exception as e:
        logging.error(f"Error generating manga: {e}", exc_info=True)
        results["error.txt"] = f"Failed to generate manga: {str(e)}".encode('utf-8')
    
    return results
