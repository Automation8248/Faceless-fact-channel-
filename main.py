import os
import json
import random
import shutil
import asyncio
import requests
import traceback
import numpy as np
from datetime import datetime
from bs4 import BeautifulSoup
import edge_tts
from PIL import Image, ImageDraw, ImageFont
from moviepy.editor import ImageClip, AudioFileClip, CompositeVideoClip, CompositeAudioClip, ColorClip

# --- Updated Environment Variables ---
TELEGRAM_SUCCESS_BOT_TOKEN = os.environ.get('TELEGRAM_SUCCESS_BOT_TOKEN')
TELEGRAM_ERROR_BOT_TOKEN = os.environ.get('TELEGRAM_ERROR_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')
WEBHOOK_URL = os.environ.get('WEBHOOK_URL')

AUTOMATION_NAME = "Premium Fact Shorts Auto-Gen"
SOCIAL_MEDIA_NAME = "Facebook, Instagram, YouTube"

# --- STATE MANAGEMENT (Cooling 1 Year) ---
def load_state(filepath="state.json"):
    if os.path.exists(filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"used_facts": {}, "last_voice": "female"}

def save_state(state, filepath="state.json"):
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=4)

def get_usable_facts(state, filepath="facts.txt"):
    usable_facts = []
    now = datetime.now()
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            if "|" in line:
                fact, keyword = line.split("|", 1)
                fact, keyword = fact.strip(), keyword.strip()
                if fact in state["used_facts"]:
                    last_used = datetime.fromisoformat(state["used_facts"][fact])
                    if (now - last_used).days < 365: # 1 YEAR COOLING
                        continue
                usable_facts.append({"text": fact, "keyword": keyword})
    return usable_facts

# --- NATURAL AI VOICE (Edge-TTS) ---
async def generate_voiceover(text, filename, voice_type):
    voice = 'en-US-ChristopherNeural' if voice_type == 'male' else 'en-US-AriaNeural'
    communicate = edge_tts.Communicate(text, voice, rate="+5%")
    await communicate.save(filename)

# --- IMAGE FETCHING & LOCAL FOLDER MANAGEMENT ---
def search_searxng(keyword):
    try:
        r = requests.get(f"https://searx.be/search?q={keyword}&categories=images&format=json", timeout=10)
        if r.status_code == 200 and r.json().get('results'):
            return r.json()['results'][0]['img_src']
    except: pass
    return None

def get_categorized_image(keyword, filename):
    cat_folder = os.path.join("downloaded_images", keyword.replace(" ", "_"))
    os.makedirs(cat_folder, exist_ok=True)
    existing_files = [f for f in os.listdir(cat_folder) if f.endswith(('.jpg', '.png'))]
    
    img_url = search_searxng(keyword)
    save_path = os.path.join(cat_folder, filename)
    
    if img_url and len(existing_files) < 15:
        try:
            r = requests.get(img_url, timeout=10)
            if r.status_code == 200:
                with open(save_path, 'wb') as f: f.write(r.content)
                return save_path
        except: pass
        
    if existing_files:
        chosen = random.choice(existing_files)
        shutil.copy(os.path.join(cat_folder, chosen), save_path)
        return save_path
    return None

# --- BACKGROUND MUSIC ---
def get_bgm():
    os.makedirs("local_bgm", exist_ok=True)
    existing_bgm = [f for f in os.listdir("local_bgm") if f.endswith('.mp3')]
    save_path = os.path.join("local_bgm", "bgm.mp3")
    
    try:
        r = requests.get("https://api.openverse.org/v1/audio/?q=ambient&length=short", timeout=10)
        if r.status_code == 200 and r.json().get('results'):
            audio_url = r.json()['results'][0]['url']
            r_audio = requests.get(audio_url, timeout=10)
            with open(save_path, 'wb') as f: f.write(r_audio.content)
            return save_path
    except: pass
    
    if existing_bgm: return os.path.join("local_bgm", random.choice(existing_bgm))
    return None

# --- DYNAMIC CAPTIONS ---
def create_caption_clips(text, duration, max_width=900):
    font_path = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
    try: font = ImageFont.truetype(font_path, 60)
    except: font = ImageFont.load_default()
        
    words = text.split()
    chunk_size = 3 
    chunks = [" ".join(words[i:i+chunk_size]) for i in range(0, len(words), chunk_size)]
    time_per_chunk = duration / len(chunks)
    clips = []
    colors = ['white', 'yellow']
    
    for i, chunk in enumerate(chunks):
        img = Image.new('RGBA', (max_width, 150), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        w, h = draw.textsize(chunk, font=font)
        x, y = (max_width - w) / 2, 20
        
        stroke = 3
        for dx in [-stroke, 0, stroke]:
            for dy in [-stroke, 0, stroke]:
                draw.text((x+dx, y+dy), chunk, font=font, fill='black')
                
        current_color = colors[i % 2]
        draw.text((x, y), chunk, font=font, fill=current_color)
        
        img_np = np.array(img)
        txt_clip = ImageClip(img_np[:, :, :3]).set_duration(time_per_chunk)
        mask = ImageClip(img_np[:, :, 3] / 255.0, ismask=True).set_duration(time_per_chunk)
        txt_clip = txt_clip.set_mask(mask).set_position(('center', 1150)).set_start(i * time_per_chunk)
        clips.append(txt_clip)
        
    return clips

# --- METADATA FOLDER LOGIC (Title & Hashtags) ---
def get_random_text_from_folder(folder_path, default_text="Awesome Facts!"):
    os.makedirs(folder_path, exist_ok=True)
    files = [f for f in os.listdir(folder_path) if f.endswith('.txt')]
    
    if not files:
        dummy_path = os.path.join(folder_path, "default.txt")
        with open(dummy_path, "w", encoding="utf-8") as f:
            f.write(default_text)
        return default_text

    chosen = random.choice(files)
    with open(os.path.join(folder_path, chosen), "r", encoding="utf-8") as f:
        return f.read().strip()

# --- MULTI-SERVER UPLOAD LOGIC ---
def get_headers():
    return {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}

def upload_video_to_servers(video_path):
    filename = os.path.basename(video_path)
    servers = [
        ("Catbox", lambda: requests.post("https://catbox.moe/user/api.php", data={'reqtype': 'fileupload'}, files={'fileToUpload': open(video_path, 'rb')}, headers=get_headers(), timeout=30)),
        ("Litterbox", lambda: requests.post("https://litterbox.catbox.moe/resources/internals/api.php", data={'reqtype': 'fileupload', 'time': '72h'}, files={'fileToUpload': open(video_path, 'rb')}, headers=get_headers(), timeout=30)),
        ("0x0.st", lambda: requests.post("https://0x0.st", files={'file': open(video_path, 'rb')}, headers=get_headers(), timeout=30)),
        ("Transfer.sh", lambda: requests.put(f"https://transfer.sh/{filename}", data=open(video_path, 'rb'), headers=get_headers(), timeout=30)),
        ("Uguu.se", lambda: requests.post("https://uguu.se/upload.php", files={'files[]': open(video_path, 'rb')}, headers=get_headers(), timeout=30)),
        ("Tmpfiles.org", lambda: requests.post("https://tmpfiles.org/api/v1/upload", files={'file': open(video_path, 'rb')}, headers=get_headers(), timeout=30)),
        ("Pomf.lain.la", lambda: requests.post("https://pomf.lain.la/upload.php", files={'files[]': open(video_path, 'rb')}, headers=get_headers(), timeout=30)),
        ("File.io", lambda: requests.post("https://file.io", files={'file': open(video_path, 'rb')}, headers=get_headers(), timeout=30))
    ]
    
    for name, uploader in servers:
        try:
            print(f"Uploading to {name}...")
            response = uploader()
            if response.status_code in [200, 201]:
                url = response.text.strip()
                if 'file.io' in name.lower():
                    url = response.json().get('link', url)
                elif 'tmpfiles.org' in name.lower():
                    raw_url = response.json().get('data', {}).get('url', '')
                    url = raw_url.replace('tmpfiles.org/', 'tmpfiles.org/dl/') if raw_url else raw_url
                print(f"✅ Successfully uploaded to {name}!")
                return url
        except Exception as e:
            print(f"❌ {name} upload failed: {e}")
            continue
            
    raise Exception("All video upload servers failed!")

# --- DUAL TELEGRAM NOTIFICATION SYSTEM (Updated) ---
def send_telegram_success(video_url):
    if not TELEGRAM_CHAT_ID or not TELEGRAM_SUCCESS_BOT_TOKEN: return
    text = f"✅ **SUCCESSFUL AUTOMATION**\n\n🤖 **Automation:** {AUTOMATION_NAME}\n📱 **Social Media:** {SOCIAL_MEDIA_NAME}\n\n🎬 **Video URL:** {video_url}\n🎉 Status: Ready for Webhook processing!"
    url = f"https://api.telegram.org/bot{TELEGRAM_SUCCESS_BOT_TOKEN}/sendMessage"
    requests.post(url, data={'chat_id': TELEGRAM_CHAT_ID, 'text': text, 'parse_mode': 'Markdown'})

def send_telegram_error(error_msg):
    if not TELEGRAM_CHAT_ID or not TELEGRAM_ERROR_BOT_TOKEN: return
    text = f"❌ **AUTOMATION FAILED!**\n\n🤖 **Automation:** {AUTOMATION_NAME}\n📱 **Social Media:** {SOCIAL_MEDIA_NAME}\n\n⚠️ **Error Details:**\n`{error_msg}`"
    url = f"https://api.telegram.org/bot{TELEGRAM_ERROR_BOT_TOKEN}/sendMessage"
    requests.post(url, data={'chat_id': TELEGRAM_CHAT_ID, 'text': text, 'parse_mode': 'Markdown'})

# --- MAIN AUTOMATION ---
async def async_main():
    try:
        state = load_state()
        usable_facts = get_usable_facts(state)
        
        if len(usable_facts) < 3:
            raise Exception("Not enough fresh facts available! Wait for cooling period or add more facts in facts.txt.")
            
        selected_facts = random.sample(usable_facts, 3)
        current_voice = 'male' if state.get("last_voice") == 'female' else 'female'
        state["last_voice"] = current_voice
        
        bgm_path = get_bgm()
        final_clips = []
        current_start_time = 0
        w, h = 1080, 1920
        transition_duration = 0.4 
        base_bg = ColorClip(size=(w, h), color=(0, 0, 0))

        for index, fact in enumerate(selected_facts):
            audio_path = f"audio_{index}.mp3"
            img_name = f"image_{index}.jpg"
            
            await generate_voiceover(fact['text'], audio_path, current_voice)
            img_path = get_categorized_image(fact['keyword'], img_name)
            if not img_path: raise Exception(f"Image fetching completely failed for keyword: {fact['keyword']}")
                
            voice_clip = AudioFileClip(audio_path).volumex(0.75)
            duration = voice_clip.duration
            
            if bgm_path:
                bgm_clip = AudioFileClip(bgm_path).volumex(0.25).set_duration(duration)
                final_audio = CompositeAudioClip([bgm_clip, voice_clip])
            else:
                final_audio = voice_clip
                
            img_clip = ImageClip(img_path).set_duration(duration)
            min_dim = min(img_clip.w, img_clip.h)
            img_clip = img_clip.crop(x_center=img_clip.w/2, y_center=img_clip.h/2, width=min_dim, height=min_dim).resize(width=1000, height=1000)
            img_clip = img_clip.set_position(('center', 350))
            
            fact_bg_clip = CompositeVideoClip([base_bg.set_duration(duration), img_clip])
            caption_clips = create_caption_clips(fact['text'], duration)
            fact_clip = CompositeVideoClip([fact_bg_clip] + caption_clips).set_audio(final_audio)
            
            if index == 0:
                fact_clip = fact_clip.set_start(current_start_time)
                current_start_time += fact_clip.duration
            else:
                current_start_time -= transition_duration 
                fact_clip = fact_clip.set_start(current_start_time)
                t_options = ['slide_left', 'slide_left', 'slide_right', 'slide_right', 'fade', 'zoom_in', 'zoom_out']
                trans_type = random.choice(t_options)
                
                if trans_type == 'slide_left': fact_clip = fact_clip.set_position(lambda t: (int(w - (w/transition_duration)*t) if t < transition_duration else 'center', 'center'))
                elif trans_type == 'slide_right': fact_clip = fact_clip.set_position(lambda t: (int(-w + (w/transition_duration)*t) if t < transition_duration else 'center', 'center'))
                elif trans_type == 'zoom_in': fact_clip = fact_clip.resize(lambda t: 1 + 0.1 * min(t/transition_duration, 1))
                elif trans_type == 'zoom_out': fact_clip = fact_clip.resize(lambda t: 1.1 - 0.1 * min(t/transition_duration, 1))
                elif trans_type == 'fade': fact_clip = fact_clip.crossfadein(transition_duration)
                    
                current_start_time += fact_clip.duration
                
            final_clips.append(fact_clip)
            state["used_facts"][fact['text']] = datetime.now().isoformat()
            
        if final_clips:
            print("\nRendering final video...")
            final_video = CompositeVideoClip(final_clips, size=(w, h))
            output_file = "final_shorts.mp4"
            final_video.write_videofile(output_file, fps=24, codec="libx264", audio_codec="aac")
            
            # Upload Video to External Servers
            uploaded_video_url = upload_video_to_servers(output_file)
            
            # Metadata Fetching
            title = get_random_text_from_folder("metadata/titles", "Did you know this amazing fact? 🤯")
            fb_tags = get_random_text_from_folder("metadata/hashtags/facebook", "#facts #facebook")
            ig_tags = get_random_text_from_folder("metadata/hashtags/instagram", "#instafacts #reels")
            yt_tags = get_random_text_from_folder("metadata/hashtags/youtube", "#shorts #youtubeshorts")
            
            # Send to Webhook
            if WEBHOOK_URL:
                payload = {
                    "status": "success",
                    "title": title,
                    "hashtags": {"facebook": fb_tags, "instagram": ig_tags, "youtube": yt_tags},
                    "video_url": uploaded_video_url
                }
                requests.post(WEBHOOK_URL, json=payload)
                
            # Send Success Alert to Telegram
            send_telegram_success(uploaded_video_url)
            save_state(state)
            
    except Exception as e:
        # Send Error Alert to Telegram
        error_details = traceback.format_exc()
        print(f"AUTOMATION CRASHED:\n{error_details}")
        send_telegram_error(str(e))

def main():
    asyncio.run(async_main())

if __name__ == "__main__":
    main()
