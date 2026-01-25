import sys
import os

try:
    import arabic_reshaper
    print(f"arabic_reshaper imported: {arabic_reshaper}")
    text = "تجربة"
    reshaped = arabic_reshaper.reshape(text)
    print(f"Reshaped: {repr(reshaped)}")
    for char in reshaped:
        print(f"Char: {hex(ord(char))}")
    
    from bidi.algorithm import get_display
    bidi_text = get_display(reshaped, base_dir='R')
    print(f"Bidi: {repr(bidi_text)}")
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()

try:
    from PIL import Image, ImageDraw, ImageFont
    font_path = "fonts/Amiri-Regular.ttf"
    if not os.path.exists(font_path):
        print(f"Font not found at {font_path}")
    else:
        print("Font found")
        try:
            font = ImageFont.truetype(font_path, 40)
            print("Font loaded successfully")
        except Exception as e:
            print(f"Font Load Error: {e}")
except Exception as e:
    print(f"PIL Error: {e}")
