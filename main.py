import os
import json
import random
import shutil
import textwrap
import requests
import numpy as np
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from gtts import gTTS
from PIL import Image, ImageDraw, ImageFont
from moviepy.editor import ImageClip, AudioFileClip, CompositeVideoClip, CompositeAudioClip
import moviepy.audio.fx.all as afx

# Environment Variables
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')
WEBHOOK_URL = os.environ.get('WEBHOOK_URL')

# --- 1. FACT COOLING SYSTEM (8 MONTHS) ---
def load_and_filter_facts(filepath="facts.txt", db_path="used_facts.json"):
    # Load history
    used_facts = {}
    if os.path.exists(db_path):
        with open(db_path, "r", encoding="utf-8") as f:
            used_facts = json.load(f)
            
    # Load all facts
    usable_facts = []
    now = datetime.now()
    
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            if "|" in line:
                fact, keyword = line.split("|", 1)
                fact, keyword = fact.strip(), keyword.strip()
                
                # Check cooling period (8 months = ~240 days)
                if fact in used_facts:
                    last_used = datetime.fromisoformat(used_facts[fact])
                    if (now - last_used).days < 240:
                        continue # Cooling period active, skip this fact
                
                usable_facts.append({"text": fact, "keyword": keyword})
    return usable_facts, used_facts

def save_used_facts(used_facts, db_path="used_facts.json"):
    with open(db_path, "w", encoding="utf-8") as f:
        json.dump(used_facts, f, indent=4)

# --- 2. OPEN-SOURCE SEARCH & CATEGORIZED SAVING ---
def search_openverse(keyword):
    try:
        r = requests.get(f"https://api.openverse.org/v1/images/?q={keyword}", timeout=10)
        if r.status_code == 200 and r.json().get('results'):
            return r.json()['results'][0]['url']
    except: pass
    return None

def search_searxng(keyword):
    # Public open-source SearXNG fallback instance
    print(f"Trying SearXNG Open Source fallback for: {keyword}...")
    try:
        url = f"https://searx.be/search?q={keyword}&categories=images&format=json"
        r = requests.get(url, timeout=10)
        if r.status_code == 200 and r.json().get('results'):
            return r.json()['results'][0]['img_src']
    except: pass
    return None

def download_image_categorized(keyword, filename):
    category_folder = os.path.join("downloaded_images", keyword.replace(" ", "_"))
    os.makedirs(category_folder, exist_ok=True)
    save_path = os.path.join(category_folder, filename)

    img_url = search_openverse(keyword) or search_searxng(keyword)
    
    if img_url:
        try:
            r = requests.get(img_url, timeout=10)
            if r.status_code == 200:
                with open(save_path, 'wb') as f: f.write(r.content)
                return save_path
        except: pass
        
    # Local Fallback
    if os.path.exists("local_images"):
        images = [f for f in os.listdir("local_images") if f.endswith(('.jpg', '.png'))]
        if images:
            chosen = random.choice(images)
            shutil.copy(os.path.join("local_images", chosen), save_path)
            return save_path
    return None

# --- 3. BACKGROUND MUSIC (OPENVERSE) ---
def get_background_music():
    try:
        print("Fetching BGM from Openverse...")
        r = requests.get("https://api.openverse.org/v1/audio/?q=ambient&length=short", timeout=10)
        if r.status_code == 200 and r.json().get('results'):
            audio_url = r.json()['results'][0]['url']
            r_audio = requests.get(audio_url, timeout=10)
            with open("bgm.mp3", 'wb') as f: f.write(r_audio.content)
            return "bgm.mp3"
    except Exception as e: print(f"BGM fetch failed: {e}")
    return None

# --- 4. DYNAMIC AUTO-CAPTIONS ---
def create_caption_clips(text, duration, max_width=900):
    """ Splits text into chunks and syncs with audio duration """
    font_path = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
    try: font = ImageFont.truetype(font_path, 60)
    except: font = ImageFont.load_default()
        
    words = text.split()
    chunk_size = 3 # Show 3 words at a time
    chunks = [" ".join(words[i:i+chunk_size]) for i in range(0, len(words), chunk_size)]
    
    time_per_chunk = duration / len(chunks)
    clips = []
    
    for i, chunk in enumerate(chunks):
        # Create image with transparent background for text
        img = Image.new('RGBA', (max_width, 150), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        w, h = draw.textsize(chunk, font=font)
        x, y = (max_width - w) / 2, 20
        
        # Black Stroke
        stroke = 3
        for dx in [-stroke, 0, stroke]:
            for dy in [-stroke, 0, stroke]:
                draw.text((x+dx, y+dy), chunk, font=font, fill='black')
        draw.text((x, y), chunk, font=font, fill='yellow') # Yellow text for better visibility
        
        img_np = np.array(img)
        txt_clip = ImageClip(img_np[:, :, :3]).set_duration(time_per_chunk)
        mask = ImageClip(img_np[:, :, 3] / 255.0, ismask=True).set_duration(time_per_chunk)
        txt_clip = txt_clip.set_mask(mask).set_position(('center', 1100)).set_start(i * time_per_chunk)
        clips.append(txt_clip)
        
    return clips

# --- TELEGRAM ---
def send_to_telegram(video_path):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendVideo"
    with open(video_path, 'rb') as video:
        requests.post(url, files={'video': video}, data={'chat_id': TELEGRAM_CHAT_ID, 'caption': "🌟 Facts of the Day! #Shorts"})

# --- MAIN EXECUTION ---
def main():
    usable_facts, used_facts = load_and_filter_facts()
    if len(usable_facts) < 3:
        print("Not enough fresh facts available! Wait for cooling period or add more.")
        return
        
    selected_facts = random.sample(usable_facts, 3)
    bgm_path = get_background_music()
    
    final_clips = []
    current_start_time = 0
    w, h = 1080, 1920

    for index, fact in enumerate(selected_facts):
        print(f"\n--- Processing: {fact['keyword']} ---")
        audio_path = f"audio_{index}.mp3"
        img_name = f"image_{index}.jpg"
        
        # Voiceover
        gTTS(text=fact['text'], lang='en', slow=False).save(audio_path)
        img_path = download_image_categorized(fact['keyword'], img_name)
        if not img_path: continue
            
        # Audio Mixing (Voice 75%, BGM 25%)
        voice_clip = AudioFileClip(audio_path).volumex(0.75)
        duration = voice_clip.duration
        
        if bgm_path:
            bgm_clip = AudioFileClip(bgm_path).volumex(0.25).set_duration(duration)
            final_audio = CompositeAudioClip([bgm_clip, voice_clip])
        else:
            final_audio = voice_clip
            
        # Background Image
        img_clip = ImageClip(img_path).set_duration(duration).resize(height=h).crop(x_center=w/2, y_center=h/2, width=w, height=h)
        
        # Auto-Captions (Disappears after being spoken)
        caption_clips = create_caption_clips(fact['text'], duration)
        
        # Compile specific fact
        fact_clip = CompositeVideoClip([img_clip] + caption_clips).set_audio(final_audio)
        fact_clip = fact_clip.set_start(current_start_time)
        
        current_start_time += fact_clip.duration
        final_clips.append(fact_clip)
        
        # Update cooling DB
        used_facts[fact['text']] = datetime.now().isoformat()
        
    if not final_clips: return

    print("\nRendering video...")
    final_video = CompositeVideoClip(final_clips, size=(w, h))
    final_video.write_videofile("final_shorts.mp4", fps=24, codec="libx264", audio_codec="aac")
    
    send_to_telegram("final_shorts.mp4")
    save_used_facts(used_facts) # Save cooling data
    
if __name__ == "__main__":
    main()
