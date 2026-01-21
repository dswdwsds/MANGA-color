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
    
    # Varsayılan font
    font_path = "fonts/Arial.ttf" # Default, but checked below
    is_arabic = False

    # Metnin Arapça olup olmadığını kontrol et
    for text_segment in dizi2:
        if any('\u0600' <= char <= '\u06FF' for char in text_segment):
            is_arabic = True
            break
            
    if is_arabic:
        if os.path.exists("C:/Windows/Fonts/arial.ttf"):
            font_path = "C:/Windows/Fonts/arial.ttf"
        elif os.path.exists("fonts/Arial.ttf"):
            font_path = "fonts/Arial.ttf"
        else:
            print("Warning: Arabic font not found. Using default.")

    mask = img_mask(dizi, dizi2, img)
    
    img = simple_lama(img, mask)
    değişken = 0
    draw = ImageDraw.Draw(img)

    try:
        font = ImageFont.truetype(font_path, 14)
    except:
        font = ImageFont.load_default()

    for eleman in dizi:
        if değişken >= len(dizi2): break
        
        all_x = [point[0] for sublist in eleman for point in sublist]
        all_y = [point[1] for sublist in eleman for point in sublist]
        x1, y1 = max(all_x), max(all_y)
        x2, y2 = min(all_x), min(all_y)

        text_to_draw = dizi2[değişken]

        if is_arabic:
             try:
                 reshaped_text = arabic_reshaper.reshape(text_to_draw)
                 bidi_text = get_display(reshaped_text, base_dir='R')
                 wrapped_text = textwrap.wrap(bidi_text, width=25)
             except Exception as e:
                 print(f"Arabic processing error: {e}")
                 wrapped_text = textwrap.wrap(text_to_draw, width=25)
        else:
             wrapped_text = textwrap.wrap(text_to_draw, width=25)

        for i, line in enumerate(wrapped_text):
            y = int((y1 + y2) / 2) + i * 20
            
            try:
                text_width = draw.textlength(line, font=font)
            except:
                text_width = draw.textsize(line, font=font)[0]
                
            x = int((x1 + x2 - int(text_width)) / 2)
            draw.text((x,y-20), line, fill=(0,0,0), font=font)
        değişken += 1

    img = np.array(img)
    return img

def main(in_memory_files,  source_lang, target_lang):
    results = {}
    simple_lama = SimpleLama()
    translator = None
    colorizator = MangaColorizator("cpu", 'networks/generator.zip', 'networks/extractor.pth')
    ocr_lang = PADDLE_LANG_MAP.get(source_lang, 'en')
    reader = PaddleOCR(lang=ocr_lang)

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

        img[img >= 150] = 255

        dizi = reader.ocr(img)
        dizi = [item for sublist in dizi if sublist is not None for item in sublist]

        if len(dizi) > 1:
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
                    string.append(str(dizi[a][1][0]))

                kordinatlar.append(kordinatlar_)
                konuşma_dizisi.append(translators(verileri_düzelt(string), translator,source_lang, target_lang))

            resim = beyaz_kare_olustur(kordinatlar, konuşma_dizisi, img_copy, simple_lama)

            if resim.shape[1] % 32 != 0:
                width = 32 * (resim.shape[1] // 32)
            else:
                width = resim.shape[1]

            colorizator.set_image(resim, width, True, 25)
            resim = colorizator.colorize()
            resim *= 255
            resim = cv2.cvtColor(resim, cv2.COLOR_BGR2RGB)

            _, encoded_img = cv2.imencode(f'.{file_extension}', resim)
            results[resim_adı] = encoded_img.tobytes()

    return results
