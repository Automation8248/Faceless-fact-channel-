import os
import random
import requests
from gtts import gTTS
from moviepy.editor import ImageClip, AudioFileClip, TextClip, CompositeVideoClip
from duckduckgo_search import DDGS # Nayi library image search ke liye

# GitHub Secrets
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')
WEBHOOK_URL = os.environ.get('WEBHOOK_URL')

def load_facts(filepath="facts.txt"):
    """ facts.txt se data read karta hai """
    facts_list = []
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                if "|" in line:
                    fact, keyword = line.split("|", 1)
                    facts_list.append({
                        "text": fact.strip(),
                        "keyword": keyword.strip()
                    })
        return facts_list
    except FileNotFoundError:
        print(f"Error: {filepath} not found!")
        return []

def download_ddg_image(keyword, filename):
    """ DuckDuckGo se keyword search karke pehli working image download karta hai """
    print(f"Searching image for: {keyword}")
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    
    with DDGS() as ddgs:
        # Top 5 results nikalenge, in case pehli link broken ho
        results = list(ddgs.images(keyword, max_results=5)) 
        
        for res in results:
            img_url = res.get('image')
            try:
                r = requests.get(img_url, headers=headers, timeout=10)
                if r.status_code == 200:
                    with open(filename, 'wb') as f:
                        f.write(r.content)
                    print(f"✅ Image downloaded: {img_url}")
                    return True
            except Exception as e:
                print(f"Skipping link due to error: {e}")
                continue
    print(f"❌ Failed to download image for keyword: {keyword}")
    return False

def send_to_telegram(video_path):
    print("Sending video to Telegram...")
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendVideo"
    with open(video_path, 'rb') as video:
        files = {'video': video}
        data = {'chat_id': TELEGRAM_CHAT_ID, 'caption': "🌟 Top 3 Facts of the Day! #Shorts #Facts"}
        response = requests.post(url, files=files, data=data)
    print("Telegram Response:", response.status_code)

def send_to_webhook(facts_data):
    if not WEBHOOK_URL: return
    print("Sending trigger to Webhook...")
    payload = {"status": "success", "facts": facts_data}
    requests.post(WEBHOOK_URL, json=payload)

def main():
    if not all([TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID]):
        print("Error: Missing Telegram Environment Variables!")
        return

    # 1. Load facts
    all_facts = load_facts("facts.txt")
    if len(all_facts) < 3:
        print("Not enough facts in facts.txt (Need at least 3).")
        return
        
    # Randomly 3 facts select karenge
    selected_facts = random.sample(all_facts, 3)

    final_clips = []
    current_start_time = 0
    w, h = 1080, 1920
    transition_duration = 0.4 # Motion timer

    # 2. Process each fact
    for index, fact in enumerate(selected_facts):
        print(f"\n--- Processing Fact {index + 1}: {fact['keyword']} ---")
        
        audio_path, img_path = f"audio_{index}.mp3", f"image_{index}.jpg"
        
        # Text to Speech
        gTTS(text=fact['text'], lang='en', slow=False).save(audio_path)
        
        # Image Search & Download
        success = download_ddg_image(fact['keyword'], img_path)
        if not success:
            print("Skipping this fact due to image download failure.")
            continue
            
        audio = AudioFileClip(audio_path)
        duration = audio.duration
        
        img_clip = ImageClip(img_path).set_duration(duration)
        img_clip = img_clip.resize(height=h).crop(x_center=img_clip.w/2, y_center=img_clip.h/2, width=w, height=h)
        
        # Caption Position (Center ke niche - Y: 1100)
        txt_clip = TextClip(fact['text'], fontsize=60, color='white', font='Arial-Bold', 
                            bg_color='rgba(0,0,0,0.6)', size=(900, None), method='caption')
        txt_clip = txt_clip.set_position(('center', 1100)).set_duration(duration)
        
        fact_clip = CompositeVideoClip([img_clip, txt_clip]).set_audio(audio)
        
        # Timeline and Motion Logic
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
        
    if len(final_clips) == 0:
        print("No clips could be processed.")
        return

    # 3. Render and Send
    print("\nRendering final video...")
    final_video = CompositeVideoClip(final_clips, size=(w, h))
    output_filename = "final_shorts_video.mp4"
    final_video.write_videofile(output_filename, fps=24, codec="libx264", audio_codec="aac")
    
    send_to_telegram(output_filename)
    send_to_webhook(selected_facts)

if __name__ == "__main__":
    main()
