from deep_translator import GoogleTranslator
import whisper
from moviepy.editor import VideoFileClip 
import io
import os
import uuid
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s')

def translators(text, translator, source_lang, target_lang):
    try:
        # Google Translator expects lowercase language codes generally
        s_lang = source_lang.lower() if source_lang and source_lang.lower() != 'auto' else 'auto'
        t_lang = target_lang.lower()
        
        translator_instance = GoogleTranslator(source=s_lang, target=t_lang)
        output = translator_instance.translate(text)
        return output
    except Exception as e:
        logging.error(f"Translation error with GoogleTranslator for text '{text[:50]}...': {e}")
        return text

def extract_audio_from_video(video_path, audio_output_path):
    # Ses dosyasını yazacağımız dizinin var olduğundan emin olalım
    audio_dir = os.path.dirname(audio_output_path)
    if not os.path.exists(audio_dir):
        os.makedirs(audio_dir, exist_ok=True)
        logging.info(f"Created directory for audio output: {audio_dir}")

    video_clip = None
    audio_clip = None
    try:
        video_clip = VideoFileClip(video_path)
        audio_clip = video_clip.audio
        audio_clip.write_audiofile(audio_output_path, codec='pcm_s16le') # codec belirterek WAV uyumluluğu artırılabilir
        logging.info(f"Audio extracted successfully to: {audio_output_path}")
    except Exception as e:
        logging.error(f"Error extracting audio from {video_path}: {e}")
        raise # Hatanın yukarıya iletilmesi için
    finally:
        if audio_clip:
            audio_clip.close()
        if video_clip:
            video_clip.close()

def transcribe_audio_with_whisper(audio_path):
    cache_dir = "/tmp/whisper_cache" # Whisper modelini indireceği/cache'leyeceği dizin
    if not os.path.exists(cache_dir):
        os.makedirs(cache_dir, exist_ok=True)
        logging.info(f"Created Whisper cache directory: {cache_dir}")

    try:
        # Model seçimi: "tiny", "base", "small", "medium", "large"
        # "small" genellikle iyi bir denge sunar.
        model = whisper.load_model("small", download_root=cache_dir)
        logging.info(f"Whisper model 'small' loaded. Transcribing audio: {audio_path}")
        # fp16=False eğer CUDA ile ilgili sorunlar yaşanırsa veya CPU'da daha stabil çalışması için denenebilir.
        result = model.transcribe(audio_path, verbose=False, fp16=False) # verbose=False production için daha iyi olabilir
        logging.info(f"Transcription complete. Found {len(result['segments'])} segments.")
        return result['segments']
    except Exception as e:
        logging.error(f"Error during Whisper transcription for {audio_path}: {e}")
        raise

def format_time(seconds):

    if seconds < 0:
        seconds = 0
    
    hours = int(seconds // 3600)
    seconds %= 3600
    minutes = int(seconds // 60)
    seconds %= 60
    milliseconds = int((seconds - int(seconds)) * 1000)
    int_seconds = int(seconds)
    return f"{hours:02d}:{minutes:02d}:{int_seconds:02d},{milliseconds:03d}"

def create_srt_file(segments, translator, source_lang, target_lang):
    srt_content = io.StringIO()

    if not segments:
        logging.warning("No segments found to create SRT file.")
        return "" # Boş segmentler için boş SRT döndür

    for idx, segment in enumerate(segments):
        start_time = format_time(segment['start'])
        end_time = format_time(segment['end'])
        
        original_text = segment.get('text', '').strip() # segment'te 'text' olmayabilir
        translated_text = original_text 
        
        if original_text:

            # Google Translate logic handled inside translators function, passing raw langs
            translated_text = translators(original_text, translator, source_lang, target_lang)
        
        srt_content.write(f"{idx + 1}\n")
        srt_content.write(f"{start_time} --> {end_time}\n")
        srt_content.write(f"{translated_text}\n\n")

    return srt_content.getvalue()

def main(in_memory_files, source_lang, target_lang):
    results = {}

    # DeepL init removed
    translator = None

    if not in_memory_files:
        logging.error("No input files provided to subtitle main function.")
        return {"error.txt": b"No input video file provided."}

    video_filename = None
    video_data = None
    for fname, fdata in in_memory_files.items():
        # Basit bir kontrol: video uzantılarından birine sahip mi?
        if fname.lower().endswith(('.mp4', '.mov', '.avi', '.mkv', '.webm')):
            video_filename = fname
            video_data = fdata
            break
    
    if not video_filename or not video_data:
        logging.error("No suitable video file found in input_memory_files.")
        return {"error.txt": b"No suitable video file found for subtitle generation."}

    logging.info(f"Processing video file for subtitles: {video_filename}")

    base_name, video_ext_with_dot = os.path.splitext(video_filename)
    video_ext = video_ext_with_dot[1:] if video_ext_with_dot else "tmp" # Uzantı yoksa veya bilinmiyorsa

    session_id = uuid.uuid4().hex
    temp_processing_dir = os.path.join("/tmp", "subtitle_processing_temp", session_id)
    
    try:
        if not os.path.exists(temp_processing_dir):
            os.makedirs(temp_processing_dir, exist_ok=True)
            logging.info(f"Created temporary processing directory: {temp_processing_dir}")

        temp_video_path = os.path.join(temp_processing_dir, f"temp_video.{video_ext}")
        temp_audio_path = os.path.join(temp_processing_dir, "audio.wav")

        with open(temp_video_path, 'wb') as f:
            f.write(video_data)
        logging.info(f"Temporary video saved to: {temp_video_path}")

        extract_audio_from_video(temp_video_path, temp_audio_path)
        
        segments = transcribe_audio_with_whisper(temp_audio_path)
        
        srt_content = create_srt_file(segments, translator, source_lang, target_lang)
        output_srt_filename = f"{base_name}.srt"
        results[output_srt_filename] = srt_content.encode("utf-8-sig")
        logging.info(f"SRT file content created for: {output_srt_filename}")

    except Exception as e:
        logging.error(f"Error during subtitle main processing for {video_filename}: {e}", exc_info=True)

        results[f"error_processing_{video_filename}.txt"] = f"An error occurred: {str(e)}".encode()
    finally:

        if os.path.exists(temp_processing_dir):
            try:

                if os.path.exists(temp_video_path): os.remove(temp_video_path)
                if os.path.exists(temp_audio_path): os.remove(temp_audio_path)

                if not os.listdir(temp_processing_dir): # Dizin boşsa
                    os.rmdir(temp_processing_dir)
                logging.info(f"Cleaned up temporary files in: {temp_processing_dir}")
            except OSError as e_cleanup:
                logging.error(f"Error during cleanup of {temp_processing_dir}: {e_cleanup}")
                
    return results

def scan_for_review(in_memory_files, source_lang, target_lang):
    review_data = []
    state_data = {}
    
    video_filename = None
    video_data = None
    for fname, fdata in in_memory_files.items():
        if fname.lower().endswith(('.mp4', '.mov', '.avi', '.mkv', '.webm')):
            video_filename = fname
            video_data = fdata
            break
            
    if not video_filename:
        return [], {} # No video found
        
    base_name, video_ext_with_dot = os.path.splitext(video_filename)
    video_ext = video_ext_with_dot[1:] if video_ext_with_dot else "tmp"
    
    session_id = uuid.uuid4().hex
    temp_processing_dir = os.path.join("/tmp", "subtitle_processing_review", session_id)
    
    translator = None
    
    try:
        if not os.path.exists(temp_processing_dir):
            os.makedirs(temp_processing_dir, exist_ok=True)
            
        temp_video_path = os.path.join(temp_processing_dir, f"temp_video.{video_ext}")
        temp_audio_path = os.path.join(temp_processing_dir, "audio.wav")
        
        with open(temp_video_path, 'wb') as f:
            f.write(video_data)
            
        extract_audio_from_video(temp_video_path, temp_audio_path)
        segments = transcribe_audio_with_whisper(temp_audio_path)
        
        # Prepare review data
        for idx, segment in enumerate(segments):
            start = segment['start']
            end = segment['end']
            text = segment.get('text', '').strip()
            
            translated_text = text
            if text:
                translated_text = translators(text, translator, source_lang, target_lang)
            
            # Update segment with translation for default state
            # But for review, we want both original and translated display
            
            review_data.append({
                'id': idx,
                'image_name': video_filename + f" [{format_time(start)} --> {format_time(end)}]", # Context info
                'original': text,
                'translated': translated_text,
                'start': start,
                'end': end
            })
            
        state_data['segments'] = review_data # Store the processed review data directly as state to reuse timestamps
        state_data['filename'] = base_name
        
    except Exception as e:
        logging.error(f"Error during scan_for_review: {e}")
        raise e
    finally:
        if os.path.exists(temp_processing_dir):
            try:
                if os.path.exists(temp_video_path): os.remove(temp_video_path)
                if os.path.exists(temp_audio_path): os.remove(temp_audio_path)
                os.rmdir(temp_processing_dir)
            except: pass
            
    return review_data, state_data

def render_after_review(in_memory_files, state_data, modifications):
    # in_memory_files is not strictly needed if we have segments with timestamps in state_data
    # But for consistency with interface we keep it.
    
    segments = state_data.get('segments', [])
    base_name = state_data.get('filename', 'subtitle')
    
    mods_map = {m['index']: m['text'] for m in modifications}
    
    srt_content = io.StringIO()
    
    for idx, segment in enumerate(segments):
        start_time = format_time(segment['start'])
        end_time = format_time(segment['end'])
        
        final_text = segment['translated'] # Default
        if idx in mods_map:
            final_text = mods_map[idx]
            
        srt_content.write(f"{idx + 1}\n")
        srt_content.write(f"{start_time} --> {end_time}\n")
        srt_content.write(f"{final_text}\n\n")
        
    results = {}
    output_srt_filename = f"{base_name}.srt"
    results[output_srt_filename] = srt_content.getvalue().encode("utf-8-sig")
    
    return results