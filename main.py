import os
import random
import shutil
import requests
from bs4 import BeautifulSoup
from gtts import gTTS
from moviepy.editor import ImageClip, AudioFileClip, TextClip, CompositeVideoClip

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
        url = f"https://api.openverse.org/v1/images/?q={keyword}"
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            results = response.json().get('results', [])
            if results:
                return results[0]['url']
    except Exception as e:
        print(f"Openverse failed: {e}")
    return None

def search_wikimedia(keyword):
    print(f"Trying Wikimedia Commons for: {keyword}...")
    try:
        url = "https://commons.wikimedia.org/w/api.php"
        params = {
            "action": "query", "format": "json", "generator": "search",
            "gsrsearch": f"{keyword} type:bitmap", "gsrnamespace": 6, "gsrlimit": 1,
            "prop": "imageinfo", "iiprop": "url"
        }
        response = requests.get(url, params=params, timeout=10)
        data = response.json()
        pages = data.get("query", {}).get("pages", {})
        for page_id in pages:
            image_info = pages[page_id].get("imageinfo", [])
            if image_info:
                return image_info[0]["url"]
    except Exception as e:
        print(f"Wikimedia failed: {e}")
    return None

def search_pxhere(keyword):
    print(f"Trying PxHere for: {keyword}...")
    try:
        url = f"https://pxhere.com/en/photos?q={keyword}"
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')
        img_tag = soup.find('img') 
        if img_tag and img_tag.get('src'):
            img_url = img_tag['src']
            if img_url.startswith('//'):
                img_url = "https:" + img_url
            return img_url
    except Exception as e:
        print(f"PxHere failed: {e}")
    return None

def get_local_fallback(filename):
    print("All websites failed. Using Local Image fallback...")
    local_dir = "local_images" 
    if os.path.exists(local_dir):
        images = [f for f in os.listdir(local_dir) if f.endswith(('.jpg', '.png', '.jpeg'))]
        if images:
            chosen_image = random.choice(images)
            source_path = os.path.join(local_dir, chosen_image)
            shutil.copy(source_path, filename)
            print(f"✅ Copied local image: {chosen_image}")
            return True
    print("❌ Local folder 'local_images' missing or empty!")
    return False

def try_download_image(keyword, filename):
    img_url = search_openverse(keyword) or search_wikimedia(keyword) or search_pxhere(keyword)
    
    if img_url:
        try:
            print(f"Downloading from URL: {img_url}")
            r = requests.get(img_url, timeout=10)
            if r.status_code == 200:
                with open(filename, 'wb') as f:
                    f.write(r.content)
                print("✅ Image downloaded successfully!")
                return True
        except Exception as e:
            print(f"Error downloading image file: {e}")
            
    return get_local_fallback(filename)

# --- TELEGRAM & WEBHOOK ---

def send_to_telegram(video_path):
    print("Sending video to Telegram...")
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendVideo"
    with open(video_path, 'rb') as video:
        files = {'video': video}
        data = {'chat_id': TELEGRAM_CHAT_ID, 'caption': "🌟 Top 3 Facts of the Day! #Shorts"}
        requests.post(url, files=files, data=data)

def send_to_webhook(facts_data):
    if WEBHOOK_URL:
        requests.post(WEBHOOK_URL, json={"status": "success", "facts": facts_data})

# --- MAIN EXECUTION ---

def main():
    if not all([TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID]):
        print("Error: Missing Telegram Environment Variables!")
        return

    all_facts = load_facts("facts.txt")
    if len(all_facts) < 3:
        print("Need at least 3 facts in facts.txt.")
        return
        
    selected_facts = random.sample(all_facts, 3)

    final_clips = []
    current_start_time = 0
    w, h = 1080, 1920
    transition_duration = 0.4 

    for index, fact in enumerate(selected_facts):
        print(f"\n--- Processing Fact {index + 1}: {fact['keyword']} ---")
        audio_path, img_path = f"audio_{index}.mp3", f"image_{index}.jpg"
        
        gTTS(text=fact['text'], lang='en', slow=False).save(audio_path)
        
        success = try_download_image(fact['keyword'], img_path)
        if not success:
            print("Skipping fact. Image mechanism completely failed.")
            continue
            
        audio = AudioFileClip(audio_path)
        duration = audio.duration
        
        img_clip = ImageClip(img_path).set_duration(duration)
        img_clip = img_clip.resize(height=h).crop(x_center=img_clip.w/2, y_center=img_clip.h/2, width=w, height=h)
        
        # FIX IS HERE: strictly utilizing the downloaded font file.
        txt_clip = TextClip(fact['text'], fontsize=60, color='white', font='./Roboto-Bold.ttf', 
                            bg_color='rgba(0,0,0,0.6)', size=(900, None), method='caption')
        txt_clip = txt_clip.set_position(('center', 1100)).set_duration(duration)
        
        fact_clip = CompositeVideoClip([img_clip, txt_clip]).set_audio(audio)
        
        if index == 0:
            fact_clip = fact_clip.set_start(current_start_time)
            current_start_time += fact_clip.duration
        else:
            current_start_time -= transition_duration 
            fact_clip = fact_clip.set_start(current_start_time)
            trans_type = random.choice(['slide_left', 'slide_right', 'fade'])
            if trans_type == 'slide_left':
                fact_clip = fact_clip.set_position(lambda t: (int(w - (w/transition_duration)*t) if t < transition_duration else 'center', 'center'))
            elif trans_type == 'slide_right':
                fact_clip = fact_clip.set_position(lambda t: (int(-w + (w/transition_duration)*t) if t < transition_duration else 'center', 'center'))
            elif trans_type == 'fade':
                fact_clip = fact_clip.crossfadein(transition_duration)
            current_start_time += fact_clip.duration
            
        final_clips.append(fact_clip)
        
    if not final_clips:
        print("No clips generated.")
        return

    print("\nRendering final video...")
    final_video = CompositeVideoClip(final_clips, size=(w, h))
    output_filename = "final_shorts_video.mp4"
    final_video.write_videofile(output_filename, fps=24, codec="libx264", audio_codec="aac")
    
    send_to_telegram(output_filename)
    send_to_webhook(selected_facts)

if __name__ == "__main__":
    main()
