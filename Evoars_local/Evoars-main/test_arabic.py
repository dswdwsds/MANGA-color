from PIL import Image, ImageDraw, ImageFont
import os
import arabic_reshaper
from bidi.algorithm import get_display

def test_arabic():
    text = "مرحبا بكم في عالم المانجا"
    print(f"Original: {text}")

    # Test Reshaping
    try:
        reshaped = arabic_reshaper.reshape(text)
        print("Reshaping: Success")
        # print(f"Reshaped: {reshaped}")
    except Exception as e:
        print(f"Reshaping Failed: {e}")
        return

    # Test Bidi
    try:
        bidi_text = get_display(reshaped)
        print("Bidi: Success")
        # print(f"Bidi: {bidi_text}")
    except Exception as e:
        print(f"Bidi Failed: {e}")
        return

    # Test Font
    font_paths = [
        "fonts/Arial.ttf",
        "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/tahoma.ttf",
        "C:/Windows/Fonts/segoeui.ttf"
    ]
    
    valid_font = None
    for fp in font_paths:
        if os.path.exists(fp):
            try:
                font = ImageFont.truetype(fp, 20)
                # Try to get mask or something to check support?
                # Pillow doesn't easily throw on missing glyphs, it just draws rectangles.
                print(f"Font found and loaded: {fp}")
                valid_font = fp
                # break # Keep checking all just to see
            except Exception as e:
                print(f"Font failed {fp}: {e}")
        else:
            print(f"Font not found: {fp}")

    if not valid_font:
        print("No valid Arabic font found!")
        return

    # Create image
    img = Image.new('RGB', (400, 100), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    font = ImageFont.truetype(valid_font, 24)
    
    # Draw logic from main code
    try:
        w = draw.textlength(bidi_text, font=font)
    except:
        w = draw.textsize(bidi_text, font=font)[0]
        
    draw.text(((400-w)/2, 30), bidi_text, font=font, fill=(0,0,0))
    img.save("test_arabic_output.png")
    print("Image saved to test_arabic_output.png")

if __name__ == "__main__":
    test_arabic()
