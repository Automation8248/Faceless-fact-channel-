import os
import random
import requests
from bs4 import BeautifulSoup
from gtts import gTTS
from moviepy.editor import ImageClip, AudioFileClip, TextClip, CompositeVideoClip

# GitHub Secrets / Environment Variables
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')
WEBHOOK_URL = os.environ.get('WEBHOOK_URL')

def load_websites(filepath="websites.txt"):
    try:
        with open(filepath, "r") as f:
            return [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        return []

def scrape_facts(url):
    print(f"Scraping facts from: {url}")
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        response = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')
        facts_data = []
        articles = soup.find_all('div', class_='fact-item') # Update tags based on your website
        
        for article in articles:
            if len(facts_data) >= 3:
                break
            text_element = article.find('p', class_='fact-text')
            img_element = article.find('img')
            
            if text_element and img_element:
                img_url = img_element['src']
                if img_url.startswith('/'):
                    from urllib.parse import urlparse
                    parsed_url = urlparse(url)
                    img_url = f"{parsed_url.scheme}://{parsed_url.netloc}{img_url}"
                facts_data.append({"text": text_element.text.strip(), "image_url": img_url})
        return facts_data
    except Exception as e:
        print(f"Failed to scrape: {e}")
        return []

def download_image(url, filename):
    response = requests.get(url)
    with open(filename, 'wb') as f:
        f.write(response.content)

def send_to_telegram(video_path):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendVideo"
    with open(video_path, 'rb') as video:
        files = {'video': video}
        data = {'chat_id': TELEGRAM_CHAT_ID, 'caption': "🌟 Top 3 Facts of the Day! #Shorts #Facts"}
        requests.post(url, files=files, data=data)

def send_to_webhook(facts_data):
    if WEBHOOK_URL:
        payload = {"status": "success", "facts": facts_data}
        requests.post(WEBHOOK_URL, json=payload)

def main():
    websites = load_websites("websites.txt")
    if not websites:
        print("No websites found in websites.txt")
        return
        
    random.shuffle(websites)
    facts = []
    for site in websites:
        facts = scrape_facts(site)
        if len(facts) >= 3:
            break
            
    if len(facts) < 3:
        print("Not enough facts found.")
        return

    # --- VIDEO CREATION TIMELINE ---
    final_clips = []
    current_start_time = 0
    w, h = 1080, 1920
    transition_duration = 0.4 # 0.4 seconds ka motion

    for index, fact in enumerate(facts):
        print(f"Processing Fact {index + 1}...")
        
        # 1. Audio and Image
        audio_path, img_path = f"audio_{index}.mp3", f"image_{index}.jpg"
        gTTS(text=fact['text'], lang='en', slow=False).save(audio_path)
        download_image(fact['image_url'], img_path)
        
        audio = AudioFileClip(audio_path)
        duration = audio.duration
        
        # Resize image for 9:16 Shorts
        img_clip = ImageClip(img_path).set_duration(duration)
        img_clip = img_clip.resize(height=h).crop(x_center=img_clip.w/2, y_center=img_clip.h/2, width=w, height=h)
        
        # 2. Caption Setup (Center ke just niche)
        # Height 1920 hai, Center 960 hai. Y position 1100 matlab thoda sa niche.
        txt_clip = TextClip(fact['text'], fontsize=65, color='white', font='Arial-Bold', 
                            bg_color='rgba(0,0,0,0.6)', size=(900, None), method='caption')
        txt_clip = txt_clip.set_position(('center', 1100)).set_duration(duration)
        
        # Merge Image, Text and Audio for this specific fact
        fact_clip = CompositeVideoClip([img_clip, txt_clip]).set_audio(audio)
        
        # 3. Apply Timeline & Motions
        if index == 0:
            # Pehla fact bina motion ke start hoga
            fact_clip = fact_clip.set_start(current_start_time)
            current_start_time += fact_clip.duration
        else:
            # Jaise hi dusra/teesra fact aaye, 0.4s ka overlap/motion ho
            current_start_time -= transition_duration 
            fact_clip = fact_clip.set_start(current_start_time)
            
            # Random Motion Select Karna
            trans_type = random.choice(['slide_left', 'slide_right', 'fade'])
            
            if trans_type == 'slide_left':
                # Right se aakar center mein set hoga
                fact_clip = fact_clip.set_position(lambda t: (int(w - (w/transition_duration)*t) if t < transition_duration else 'center', 'center'))
            
            elif trans_type == 'slide_right':
                # Left se aakar center mein set hoga
                fact_clip = fact_clip.set_position(lambda t: (int(-w + (w/transition_duration)*t) if t < transition_duration else 'center', 'center'))
            
            elif trans_type == 'fade':
                # Crossfade effect
                fact_clip = fact_clip.crossfadein(transition_duration)
                
            current_start_time += fact_clip.duration
            
        final_clips.append(fact_clip)
        
    print("Rendering final video with motions...")
    # CompositeVideoClip ko use karke saare overlap motion render karenge
    final_video = CompositeVideoClip(final_clips, size=(w, h))
    output_filename = "final_shorts_video.mp4"
    
    final_video.write_videofile(output_filename, fps=24, codec="libx264", audio_codec="aac")
    
    send_to_telegram(output_filename)
    send_to_webhook(facts)

if __name__ == "__main__":
    main()
