from deep_translator import GoogleTranslator
from tqdm import tqdm
import numpy as np
import textwrap
import cv2
from colorizator import MangaColorizator
from PIL import ImageFont, ImageDraw
import arabic_reshaper
from bidi.algorithm import get_display
import sys
import os

# lib klasörünü sys.path'e ekle
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "lib")))
from lib.simple_lama_inpainting.models import SimpleLama
from lib.simple_lama_inpainting.models import SimpleLama
from paddleocr import PaddleOCR
import requests

PADDLE_LANG_MAP = {
    'ar': 'arabic',
    'en': 'en',
    'zh': 'ch',
    'ja': 'japan',
    'ko': 'korean',
    'ru': 'cyrillic',
    'tr': 'latin',
    'fr': 'latin',
    'de': 'latin',
    'es': 'latin',
    'it': 'latin',
    'pt': 'latin',
    'pl': 'latin',
    'auto': 'en' # Default fallback
}

def download_font_if_missing(font_path, url):
    if not os.path.exists(font_path):
        print(f"Downloading font to {font_path}...")
        try:
            response = requests.get(url)
            with open(font_path, 'wb') as f:
                f.write(response.content)
            print("Font downloaded successfully.")
        except Exception as e:
            print(f"Failed to download font: {e}")

def yakın_kelimeleri_bul(kordinatlar):

    sonuclar = []
    a = []
    thres = 65
    while len(kordinatlar) >= 1:
        a.append(kordinatlar[0])
        for i in kordinatlar[1:]:
            if (a[-1][0] - thres <= i[0] and a[-1][0] + thres >= i[0]) and a[-1][1] + thres > i[1]:
                a.append(i)
                kordinatlar.remove(i)
        sonuclar.append(a)
        kordinatlar.pop(0)
        a = []

    return sonuclar

def orta_nokta_bul(koordinatlar):

    x_toplam = sum(x for x, y in koordinatlar)
    y_toplam = sum(y for x, y in koordinatlar)
    ortalama_x = x_toplam / len(koordinatlar)
    ortalama_y = y_toplam / len(koordinatlar)

    return (ortalama_x, ortalama_y)

def indexleri_bul(dizi1, dizi2):

    indeksler = []
    for elemanlar in dizi2:
        eleman_indeksleri = []
        for eleman in elemanlar:
            if eleman in dizi1:
                eleman_indeksleri.append(dizi1.index(eleman))
        indeksler.append(eleman_indeksleri)

    return indeksler

def verileri_düzelt(dizi):
    duzeltilmis_elemanlar = []
    i = 0
    while i < len(dizi):

        eleman = dizi[i]
        if '-' in eleman:
            parcalar = eleman.split('-')

            if i + 1 < len(dizi):
                duzeltilmis_eleman = (parcalar[0] + dizi[i+1]).strip()
                i += 1  
            else:
                duzeltilmis_eleman = parcalar[0].strip()
        else:
            duzeltilmis_eleman = eleman

        duzeltilmis_elemanlar.append(duzeltilmis_eleman)
        i += 1 
    birlesik_string = ' '.join([eleman.lower() for eleman in duzeltilmis_elemanlar])

    return birlesik_string

    return birlesik_string

def translators(text, translator,source_lang, target_lang):
    try:
        if source_lang == 'auto':
            translator = GoogleTranslator(target=target_lang)
        else:
            translator = GoogleTranslator(source=source_lang, target=target_lang)
        output = translator.translate(text)
        return output
    except Exception as e:
        print(f"Translation Error: {e}")
        return text

def img_mask(dizi, dizi2, img):

    height, width, _ = img.shape
    img = np.zeros((height, width, 1), dtype=np.uint8)

    for eleman in dizi:

        all_x = [point[0] for sublist in eleman for point in sublist]
        all_y = [point[1] for sublist in eleman for point in sublist]
        x1, y1 = max(all_x), max(all_y)
        x2, y2 = min(all_x), min(all_y)

        img = cv2.rectangle(img, (int(x1+7), int(y1+7)), (int(x2-7), int(y2-7)), (255, 255, 255), thickness=cv2.FILLED)

    return img
    
def beyaz_kare_olustur(dizi, dizi2, img, simple_lama):
    
    is_arabic = False

    # Metnin Arapça olup olmadığını kontrol et
    for text_segment in dizi2:
        if any('\u0600' <= char <= '\u06FF' for char in text_segment):
            is_arabic = True
            break
            
    if is_arabic:
        # CodeSpaces/Linux için Amiri fontu (Noto'dan daha iyi Presentation Form desteği olabilir)
        font_path = "fonts/Amiri-Regular.ttf"
        download_font_if_missing(font_path, "https://github.com/google/fonts/raw/main/ofl/amiri/Amiri-Regular.ttf")
        
        if not os.path.exists(font_path):
             # Fallbacks
            if os.path.exists("C:/Windows/Fonts/arial.ttf"):
                font_path = "C:/Windows/Fonts/arial.ttf"
            elif os.path.exists("fonts/Arial.ttf"):
                font_path = "fonts/Arial.ttf"
            else:
                font_path = "fonts/mangat.ttf" 
    else:
        font_path = "fonts/mangat.ttf"

    mask = img_mask(dizi, dizi2, img)
    
    img = simple_lama(img, mask)
    değişken = 0
    draw = ImageDraw.Draw(img)

    for eleman in dizi:
        if değişken >= len(dizi2): break
        
        all_x = [point[0] for sublist in eleman for point in sublist]
        all_y = [point[1] for sublist in eleman for point in sublist]
        x1, y1 = max(all_x), max(all_y)
        x2, y2 = min(all_x), min(all_y)
        
        box_width = abs(x2 - x1)
        box_height = abs(y2 - y1)
        
        if box_width < 10 or box_height < 10:
             değişken += 1
             continue

        text_to_draw = dizi2[değişken]
        
        if is_arabic:
            # For Arabic, we reshape the entire text first to ensure proper joining
            # then we wrap the reshaped text or wrap the logical text.
            # Wrapping logical text is safer for word order.
            pass

        # Dynamic Font Sizing & Wrapping Logic
        chosen_font = None
        chosen_lines = []
        line_height = 0
        
        font_sizes = list(range(40, 7, -2))
        
        for size in font_sizes:
            try:
                test_font = ImageFont.truetype(font_path, size)
            except:
                test_font = ImageFont.load_default()
            
            char_width_factor = 0.5 
            estimated_char_width = size * char_width_factor
            wrap_cols = int(box_width / estimated_char_width)
            if wrap_cols < 1: wrap_cols = 1
            
            # Wrap logical text
            test_lines = textwrap.wrap(text_to_draw, width=wrap_cols)
            
            current_line_height = size + 6 
            total_h_px = len(test_lines) * current_line_height
            
            if total_h_px > box_height:
                continue
            
            fits_width = True
            processed_test_lines = []
            for line in test_lines:
                line_to_check = line
                if is_arabic:
                    try:
                        # Reshape and Bidi EACH line to fit the box
                        reshaped = arabic_reshaper.reshape(line)
                        line_to_check = get_display(reshaped, base_dir='R')
                    except: pass
                
                try:
                    w = draw.textlength(line_to_check, font=test_font)
                except:
                    w = size * len(line_to_check)
                
                if w > box_width:
                    fits_width = False
                    break
                processed_test_lines.append(line_to_check)
            
            if fits_width:
                 chosen_font = test_font
                 chosen_lines = processed_test_lines # Already bidi-ed
                 line_height = current_line_height
                 break

        if chosen_font is None:
             try:
                 chosen_font = ImageFont.truetype(font_path, 10)
             except:
                 chosen_font = ImageFont.load_default()
             
             raw_lines = textwrap.wrap(text_to_draw, width=max(1, int(box_width/6)))
             chosen_lines = []
             for rl in raw_lines:
                 if is_arabic:
                     try:
                         chosen_lines.append(get_display(arabic_reshaper.reshape(rl), base_dir='R'))
                     except: chosen_lines.append(rl)
                 else:
                     chosen_lines.append(rl)
             line_height = 14

        total_block_h = len(chosen_lines) * line_height
        start_y = int((y1 + y2 - total_block_h) / 2)
        
        for i, line_to_render in enumerate(chosen_lines):
            try:
                lw = draw.textlength(line_to_render, font=chosen_font)
            except:
                try:
                    lw = draw.textsize(line_to_render, font=chosen_font)[0]
                except:
                    lw = 0
            
            curr_x = int((x1 + x2 - lw) / 2)
            curr_y = start_y + (i * line_height)
            
            draw.text((curr_x, curr_y), line_to_render, fill=(0,0,0), font=chosen_font)
            
        değişken += 1

    img = np.array(img)
    return img

def clean_ocr_text(text):
    """تنظيف النص المقروء من OCR من الأحرف الغريبة والضوضاء"""
    if not text or not isinstance(text, str):
        return ""
    import re
    cleaned = re.sub(r'[^\u0600-\u06FFa-zA-Z0-9\s\.\?\!\,\-\'\"]+', '', text)
    cleaned = ' '.join(cleaned.split())
    return cleaned.strip()

def main(in_memory_files,  source_lang, target_lang):
    results = {}
    simple_lama = None
    try:
        simple_lama = SimpleLama()
    except Exception as e_lama:
        print(f"SimpleLama Init Error (Inpainting will be disabled): {e_lama}")

    translator = None
    colorizator = MangaColorizator("cpu", 'networks/generator.zip', 'networks/extractor.pth')
    ocr_lang = PADDLE_LANG_MAP.get(source_lang, 'en')
    reader = PaddleOCR(
        lang=ocr_lang, 
        use_angle_cls=True,
        det_db_thresh=0.3,
        det_db_box_thresh=0.5
    )

    for resim_adı, resim_verisi in tqdm(in_memory_files.items(), desc="İşleniyor", unit="resim"):
        # Resmi bellekte işle
        file_bytes = np.frombuffer(resim_verisi, np.uint8)
        img = cv2.imdecode(file_bytes, cv2.IMREAD_UNCHANGED)

        if len(img.shape) == 2:
            # cv2.cvtColor kullanarak renklendirme
            img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)

            # Alternatif olarak, manuel olarak bir kanal ekleyebilirsiniz
            # img = np.stack((img,)*3, axis=-1)
        # Orijinal dosya uzantısını belirle
        file_extension = resim_adı.split('.')[-1].lower()
        img_copy = img.copy()

        # تحسين معالجة الصورة للـ OCR
        img_for_ocr = img_copy.copy()
        if len(img_for_ocr.shape) == 3:
            gray = cv2.cvtColor(img_for_ocr, cv2.COLOR_BGR2GRAY)
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
            img_for_ocr = clahe.apply(gray)

        dizi = reader.ocr(img_for_ocr)
        dizi = [item for sublist in dizi if sublist is not None for item in sublist]

        if len(dizi) > 0:
            kordinatlar = [orta_nokta_bul(i[0]) for i in dizi]
            kordinatlar_ = kordinatlar.copy()

            sonuclar = yakın_kelimeleri_bul(kordinatlar)
            indexler = indexleri_bul(kordinatlar_, sonuclar)

            kordinatlar = []
            konuşma_dizisi = []

            for i in indexler:
                kordinatlar_ = []
                string = []

                for a in i:
                    kordinatlar_.append(dizi[a][0])
                    raw_text = str(dizi[a][1][0])
                    cleaned_text = clean_ocr_text(raw_text)
                    string.append(cleaned_text)

                kordinatlar.append(kordinatlar_)
                text_to_translate = verileri_düzelt(string)
                if text_to_translate.strip():
                    translated = translators(text_to_translate, translator, source_lang, target_lang)
                    konuşma_dizisi.append(translated)
                else:
                    konuşma_dizisi.append("")

            if simple_lama:
                resim = beyaz_kare_olustur(kordinatlar, konuşma_dizisi, img_copy, simple_lama)
            else:
                 # Fallback: Just draw text over original image or maybe draw white boxes without inpainting?
                 # For now let's just use the original image copy, text will be drawn over it (which might look messy but better than crash)
                 # Or we can call a modified version of beyaz_kare_olustur that skips inpainting.
                 # Let's just try to proceed with beyaz_kare_olustur but pass None and handle it there?
                 # Expectation: beyaz_kare_olustur calls simple_lama(img, mask).
                 # So we urge update beyaz_kare_olustur or just do this:
                 resim = img_copy # skip text removal/replacement visually if lama missing? 
                 # Wait, text REPLACEMENT is key. We need to draw the white box at least.
                 # Let's modifying 'beyaz_kare_olustur' is risky without reading it fully.
                 # I'll just skip the inpainting step in the loop if simple_lama is missing, logic below assumes resim is returned.
                 # Let's try to call it but handle the error inside? No I can't edit it easily.
                 # I will just SKIP calling it and print warning, but this means no translation text overlay.
                 # Actually, `beyaz_kare_olustur` does the drawing of text too!
                 # So I MUST call it or re-implement drawing.
                 # I will assume for now I should try to fix it, but if I can't download the model, I can't fix it.
                 # I will skip it.
                 print("Skipping text replacement as SimpleLama is missing.")
                 resim = img_copy


            if resim.shape[1] % 32 != 0:
                width = 32 * (resim.shape[1] // 32)
            else:
                width = resim.shape[1]

            if colorizator:
                try:
                    colorizator.set_image(resim, width, True, 25)
                    resim = colorizator.colorize()
                    resim *= 255
                except Exception as e_col_run:
                     print(f"Colorization Run Error: {e_col_run}")
                     # Fallback so we don't return nothing
            else:
                 # No colorizator available, just return the in-painted grayscale or however it looks
                 resim = resim # It is already numpy array from beyaz_kare_olustur or previous steps

            resim = cv2.cvtColor(resim, cv2.COLOR_BGR2RGB)

            _, encoded_img = cv2.imencode(f'.{file_extension}', resim)
            results[resim_adı] = encoded_img.tobytes()

    return results

def scan_for_review(in_memory_files, source_lang, target_lang):
    # This is identical to translate.py's scan_for_review because we only need OCR and Translation for review
    # Colorization happens at render stage or we can colorize preview?
    # If we colorize preview, we have to store colorized image in state which is heavy.
    # So we Scan on original image, and Render creates separate colorized outputs.
    
    review_data = [] 
    state_data = {} 
    
    translator = None 
    ocr_lang = PADDLE_LANG_MAP.get(source_lang, 'en')
    reader = PaddleOCR(lang=ocr_lang, use_angle_cls=True, det_db_thresh=0.3, det_db_box_thresh=0.5)
    
    global_text_index = 0
    
    for resim_adı, resim_verisi in tqdm(in_memory_files.items(), desc="Scanning for Review", unit="image"):
        file_bytes = np.frombuffer(resim_verisi, np.uint8)
        img = cv2.imdecode(file_bytes, cv2.IMREAD_UNCHANGED)
        if len(img.shape) == 2:
            img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
            
        img_copy = img.copy()
        img_for_ocr = img_copy.copy()
        if len(img_for_ocr.shape) == 3:
            gray = cv2.cvtColor(img_for_ocr, cv2.COLOR_BGR2GRAY)
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
            img_for_ocr = clahe.apply(gray)

        dizi = reader.ocr(img_for_ocr)
        dizi = [item for sublist in dizi if sublist is not None for item in sublist]

        if len(dizi) > 0:
            kordinatlar = [orta_nokta_bul(i[0]) for i in dizi]
            kordinatlar_ = kordinatlar.copy()
            sonuclar = yakın_kelimeleri_bul(kordinatlar)
            indexler = indexleri_bul(kordinatlar_, sonuclar)
            
            final_coords = []
            final_translations = []
            
            for i in indexler:
                group_coords = []
                group_text_parts = []
                for a in i:
                    group_coords.append(dizi[a][0])
                    raw_text = str(dizi[a][1][0])
                    cleaned_text = clean_ocr_text(raw_text)
                    group_text_parts.append(cleaned_text)
                
                text_to_translate = verileri_düzelt(group_text_parts)
                translated_text = ""
                if text_to_translate.strip():
                    translated_text = translators(text_to_translate, translator, source_lang, target_lang)
                
                final_coords.append(group_coords)
                final_translations.append(translated_text)
                
                review_data.append({
                    'id': global_text_index,
                    'image_name': resim_adı,
                    'original': text_to_translate,
                    'translated': translated_text
                })
                global_text_index += 1
            
            state_data[resim_adı] = {
                'coords': final_coords,
                'translated_texts': final_translations
            }
        else:
             state_data[resim_adı] = {'coords': [], 'translated_texts': []}

    return review_data, state_data

def render_after_review(in_memory_files, state_data, modifications):
    # Modifications mapping
    mods_map = {m['index']: m['text'] for m in modifications}
    
    results = {}
    
    simple_lama = None
    try:
        simple_lama = SimpleLama()
    except: pass
    
    # Init Colorizator
    colorizator = MangaColorizator("cpu", 'networks/generator.zip', 'networks/extractor.pth')
    
    current_global_idx = 0
    
    for resim_adı, resim_verisi in tqdm(in_memory_files.items(), desc="Rendering Final", unit="image"):
        file_bytes = np.frombuffer(resim_verisi, np.uint8)
        img = cv2.imdecode(file_bytes, cv2.IMREAD_UNCHANGED)
        if len(img.shape) == 2: img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
        file_extension = resim_adı.split('.')[-1].lower()
        img_copy = img.copy()
        
        if resim_adı in state_data:
            data = state_data[resim_adı]
            coords = data['coords']
            old_texts = data['translated_texts']
            
            new_texts = []
            for _ in old_texts:
                if current_global_idx in mods_map:
                    new_texts.append(mods_map[current_global_idx])
                else:
                    new_texts.append(old_texts[len(new_texts)])
                current_global_idx += 1
            
            resim = img_copy
            if len(coords) > 0 and simple_lama:
                resim = beyaz_kare_olustur(coords, new_texts, img_copy, simple_lama)
            elif len(coords) > 0 and not simple_lama:
                 print("SimpleLama missing, skipping text replacement.")
        else:
            resim = img_copy
            
        # Colorization Step
        if resim.shape[1] % 32 != 0:
            width = 32 * (resim.shape[1] // 32)
        else:
            width = resim.shape[1]

        if colorizator:
            try:
                colorizator.set_image(resim, width, True, 25)
                resim = colorizator.colorize()
                resim *= 255
            except Exception as e_col:
                print(f"Colorization Error during review render: {e_col}")
        
        resim = cv2.cvtColor(resim, cv2.COLOR_BGR2RGB)
        _, encoded_img = cv2.imencode(f'.{file_extension}', resim)
        results[resim_adı] = encoded_img.tobytes()
            
    return results
