import os
import random
import shutil
import requests
import textwrap
import numpy as np
from bs4 import BeautifulSoup
from gtts import gTTS
from PIL import Image, ImageDraw, ImageFont
from moviepy.editor import ImageClip, AudioFileClip, CompositeVideoClip

# GitHub Secrets
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')
WEBHOOK_URL = os.environ.get('WEBHOOK_URL')

def load_facts(filepath="facts.txt"):
    facts_list = []
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                if "|" in line:
                    fact, keyword = line.split("|", 1)
                    facts_list.append({"text": fact.strip(), "keyword": keyword.strip()})
        return facts_list
    except FileNotFoundError:
        print(f"Error: {filepath} not found!")
        return []

# --- IMAGE SEARCH FUNCTIONS ---
def search_openverse(keyword):
    print(f"Trying Openverse for: {keyword}...")
    try:
        response = requests.get(f"https://api.openverse.org/v1/images/?q={keyword}", timeout=10)
        if response.status_code == 200:
            results = response.json().get('results', [])
            if results: return results[0]['url']
    except Exception: pass
    return None

def search_wikimedia(keyword):
    print(f"Trying Wikimedia Commons for: {keyword}...")
    try:
        params = {"action": "query", "format": "json", "generator": "search", "gsrsearch": f"{keyword} type:bitmap", "gsrnamespace": 6, "gsrlimit": 1, "prop": "imageinfo", "iiprop": "url"}
        response = requests.get("https://commons.wikimedia.org/w/api.php", params=params, timeout=10)
        pages = response.json().get("query", {}).get("pages", {})
        for page_id in pages:
            image_info = pages[page_id].get("imageinfo", [])
            if image_info: return image_info[0]["url"]
    except Exception: pass
    return None

def search_pxhere(keyword):
    print(f"Trying PxHere for: {keyword}...")
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        soup = BeautifulSoup(requests.get(f"https://pxhere.com/en/photos?q={keyword}", headers=headers, timeout=10).text, 'html.parser')
        img_tag = soup.find('img')
        if img_tag and img_tag.get('src'):
            img_url = img_tag['src']
            return "https:" + img_url if img_url.startswith('//') else img_url
    except Exception: pass
    return None

def get_local_fallback(filename):
    print("All websites failed. Using Local Image fallback...")
    local_dir = "local_images"
    if os.path.exists(local_dir):
        images = [f for f in os.listdir(local_dir) if f.endswith(('.jpg', '.png', '.jpeg'))]
        if images:
            chosen = random.choice(images)
            shutil.copy(os.path.join(local_dir, chosen), filename)
            print(f"✅ Copied local image: {chosen}")
            return True
    return False

def try_download_image(keyword, filename):
    img_url = search_openverse(keyword) or search_wikimedia(keyword) or search_pxhere(keyword)
    if img_url:
        try:
            print(f"Downloading from URL: {img_url}")
            r = requests.get(img_url, timeout=10)
            if r.status_code == 200:
                with open(filename, 'wb') as f: f.write(r.content)
                print("✅ Image downloaded successfully!")
                return True
        except Exception: pass
    return get_local_fallback(filename)

# --- CUSTOM 100% CRASH-PROOF TEXT RENDERING ---
def create_text_clip_pil(text, duration, max_width=900):
    """ Bypasses ImageMagick completely to stop 0-size array errors """
    fontsize = 60
    font_path = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
    try:
        font = ImageFont.truetype(font_path, fontsize)
    except IOError:
        font = ImageFont.load_default()
        
    # Text wrapping logic
    char_width = fontsize * 0.55
    chars_per_line = int(max_width / char_width)
    lines = textwrap.wrap(text, width=chars_per_line)
    
    line_height = fontsize * 1.2
    img_height = int(len(lines) * line_height) + 40
    
    # Create transparent image
    img = Image.new('RGBA', (max_width, img_height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    y_text = 20
    stroke_width = 3
    
    for line in lines:
        w, h = draw.textsize(line, font=font)
        x_text = (max_width - w) / 2
        
        # Draw Black Stroke
        for dx in [-stroke_width, 0, stroke_width]:
            for dy in [-stroke_width, 0, stroke_width]:
                draw.text((x_text+dx, y_text+dy), line, font=font, fill='black')
        
        # Draw White Text
        draw.text((x_text, y_text), line, font=font, fill='white')
        y_text += int(line_height)
        
    # Convert PIL Image to MoviePy Clip
    img_np = np.array(img)
    txt_clip = ImageClip(img_np[:, :, :3]).set_duration(duration)
    mask = ImageClip(img_np[:, :, 3] / 255.0, ismask=True).set_duration(duration)
    return txt_clip.set_mask(mask)

# --- TELEGRAM & WEBHOOK ---
def send_to_telegram(video_path):
    print("Sending video to Telegram...")
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendVideo"
    with open(video_path, 'rb') as video:
        response = requests.post(url, files={'video': video}, data={'chat_id': TELEGRAM_CHAT_ID, 'caption': "🌟 Top 3 Facts of the Day! #Shorts"})
        print("✅ Successfully sent to Telegram!" if response.status_code == 200 else f"❌ Failed: {response.text}")

def send_to_webhook(facts_data):
    if WEBHOOK_URL:
        requests.post(WEBHOOK_URL, json={"status": "success", "facts": facts_data})

# --- MAIN EXECUTION ---
def main():
    if not all([TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID]):
        print("Error: Missing Telegram Environment Variables!")
        return

    all_facts = load_facts("facts.txt")
    if len(all_facts) < 3: return
    selected_facts = random.sample(all_facts, 3)

    final_clips = []
    current_start_time = 0
    w, h = 1080, 1920
    transition_duration = 0.4 

    for index, fact in enumerate(selected_facts):
        print(f"\n--- Processing Fact {index + 1}: {fact['keyword']} ---")
        audio_path, img_path = f"audio_{index}.mp3", f"image_{index}.jpg"
        
        gTTS(text=fact['text'], lang='en', slow=False).save(audio_path)
        if not try_download_image(fact['keyword'], img_path): continue
            
        audio = AudioFileClip(audio_path)
        duration = audio.duration
        
        img_clip = ImageClip(img_path).set_duration(duration).resize(height=h).crop(x_center=w/2, y_center=h/2, width=w, height=h)
        
        # --- FIX: Using Custom PIL Text Clip instead of ImageMagick ---
        txt_clip = create_text_clip_pil(fact['text'], duration, max_width=900).set_position(('center', 1100))
        
        fact_clip = CompositeVideoClip([img_clip, txt_clip]).set_audio(audio)
        
        if index == 0:
            fact_clip = fact_clip.set_start(current_start_time)
            current_start_time += fact_clip.duration
        else:
            current_start_time -= transition_duration 
            fact_clip = fact_clip.set_start(current_start_time)
            
            trans_type = random.choice(['slide_left', 'slide_right', 'fade'])
            if trans_type == 'slide_left': fact_clip = fact_clip.set_position(lambda t: (int(w - (w/transition_duration)*t) if t < transition_duration else 'center', 'center'))
            elif trans_type == 'slide_right': fact_clip = fact_clip.set_position(lambda t: (int(-w + (w/transition_duration)*t) if t < transition_duration else 'center', 'center'))
            elif trans_type == 'fade': fact_clip = fact_clip.crossfadein(transition_duration)
                
            current_start_time += fact_clip.duration
            
        final_clips.append(fact_clip)
        
    if not final_clips: return

    print("\nRendering final video...")
    final_video = CompositeVideoClip(final_clips, size=(w, h))
    output_filename = "final_shorts_video.mp4"
    final_video.write_videofile(output_filename, fps=24, codec="libx264", audio_codec="aac")
    
    send_to_telegram(output_filename)
    send_to_webhook(selected_facts)
    
    for i in range(3):
        if os.path.exists(f"audio_{i}.mp3"): os.remove(f"audio_{i}.mp3")
        if os.path.exists(f"image_{i}.jpg"): os.remove(f"image_{i}.jpg")

if __name__ == "__main__":
    main()
