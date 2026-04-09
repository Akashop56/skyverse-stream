import os
import time
import json
import random
import threading
import subprocess
import requests
from PIL import Image, ImageDraw, ImageFont

# --- CLOUD & LOOP CONFIG ---
START_TIME = time.time()
MAX_DURATION = (5 * 3600) + (45 * 60) # 5h 45m handoff
GITHUB_REPO = os.getenv("GITHUB_REPOSITORY")
GH_PAT = os.getenv("GH_PAT")

# --- MASTER DUAL-FORMAT SPECS ---
WIDTH, HEIGHT = 1920, 1080 # Horizontal for PC, Center-Safe for Shorts
SAFE_W = 608 # The exact width of the Shorts Feed crop
SAFE_X = (WIDTH - SAFE_W) // 2 # 656 (Center start)
FPS = 15 # Optimized to STOP lagging on GitHub servers
STREAM_KEY = os.getenv("STREAM_KEY")
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")
CHANNEL_ID = os.getenv("CHANNEL_ID")
FONT_BOLD = "Montserrat-Bold.ttf"
AUDIO_FILE = "audio.mp3"

state = {
    "subs": 0,
    "goal": 10000,
    "current_text": "Who is the ultimate IPL Captain?\n\nA) MS Dhoni\nB) Rohit Sharma\n\nDrop your answer!",
    "rendered_text": "", # Caching variable to stop lag
    "cached_lines": [],  # Caching variable to stop lag
    "last_update": time.time(),
    "cycle_duration": 15.0 # 15 Seconds: Audience ko padhne aur type karne ka time
}

def trigger_next_run():
    if not GH_PAT or not GITHUB_REPO: return
    url = f"https://api.github.com/repos/{GITHUB_REPO}/dispatches"
    headers = {"Authorization": f"token {GH_PAT}", "Accept": "application/vnd.github.v3+json"}
    requests.post(url, json={"event_type": "restart_stream"}, headers=headers)
    os._exit(0)

def get_live_subs():
    while True:
        try:
            url = f"https://www.googleapis.com/youtube/v3/channels?part=statistics&id={CHANNEL_ID}&key={YOUTUBE_API_KEY}"
            data = requests.get(url).json()
            state["subs"] = int(data["items"][0]["statistics"]["subscriberCount"])
            if state["subs"] >= state["goal"]: state["goal"] += 5000
        except: pass
        time.sleep(60)

def update_content():
    # You MUST update content.json to have Questions! Example below.
    try:
        with open("content.json", "r", encoding="utf-8") as f: data = json.load(f)
    except:
        data = {"lines": [{"text": "Who is better?\nA) Virat\nB) Dhoni\n\nTell us below!"}]}
        
    while True:
        line = random.choice(data["lines"])
        state["current_text"] = line["text"]
        state["last_update"] = time.time()
        time.sleep(state["cycle_duration"])

def get_wrapped_text(text, font, max_width, draw):
    lines = []
    # Hum \n (newlines) ko respect karenge jo text mein hain
    paragraphs = text.split('\n')
    for p in paragraphs:
        if not p.strip():
            lines.append("")
            continue
        words = p.split()
        current_line = ""
        for word in words:
            test_line = current_line + word + " "
            w = draw.textbbox((0, 0), test_line, font=font)[2]
            if w < max_width:
                current_line = test_line
            else:
                lines.append(current_line)
                current_line = word + " "
        lines.append(current_line)
    return lines

def render_frame(font_main, font_sub, font_small):
    # 1. PC Full Background (Dark sleek look)
    frame = Image.new('RGB', (WIDTH, HEIGHT), (12, 12, 18))
    draw = ImageDraw.Draw(frame)
    
    t = time.time()
    elapsed = t - state["last_update"]
    progress = min(elapsed / state["cycle_duration"], 1.0)
    
    # 2. DRAW PC SIDE PANELS (Visible to Long Form only)
    # Left Panel
    draw.rectangle([0, 0, SAFE_X, HEIGHT], fill=(8, 8, 12))
    draw.text((100, 200), "SKYVERSE", font=font_sub, fill=(255, 255, 255))
    draw.text((100, 300), "LIVE 24/7", font=font_small, fill=(0, 200, 255))
    draw.text((100, 500), f"Current Subs: {state['subs']:,}", font=font_small, fill=(255, 255, 255))
    draw.text((100, 550), f"Goal: {state['goal']:,}", font=font_small, fill=(0, 255, 150))
    
    # Right Panel
    draw.rectangle([WIDTH - SAFE_X, 0, WIDTH, HEIGHT], fill=(8, 8, 12))
    draw.text((WIDTH - 450, 400), "HOW TO PLAY:", font=font_small, fill=(255, 200, 50))
    draw.text((WIDTH - 450, 460), "1. Read the Question", font=font_small, fill=(200, 200, 200))
    draw.text((WIDTH - 450, 510), "2. Vote in Live Chat", font=font_small, fill=(200, 200, 200))
    draw.text((WIDTH - 450, 560), "3. Subscribe! 🔥", font=font_small, fill=(200, 200, 200))

    # 3. DRAW CENTER PANEL (The "Shorts Safe Zone")
    # This is what mobile users see. PC users see it in the middle.
    draw.rectangle([SAFE_X, 0, SAFE_X + SAFE_W, HEIGHT], fill=(15, 15, 25))
    
    # Top Mobile UI
    draw.rounded_rectangle([SAFE_X + 50, 100, SAFE_X + SAFE_W - 50, 200], radius=20, fill=(30, 30, 45))
    draw.text((SAFE_X + 100, 130), f"SUBS: {state['subs']:,}  🔥", font=font_small, fill=(255, 255, 255))
    
    # --- TEXT CACHING TO FIX LAG ---
    if state["current_text"] != state["rendered_text"]:
        # Only recalculate wrapping when the text actually changes (every 15s)
        max_text_width = SAFE_W - 100
        state["cached_lines"] = get_wrapped_text(state["current_text"], font_main, max_text_width, draw)
        state["rendered_text"] = state["current_text"]

    lines = state["cached_lines"]
    
    # Smooth Fade
    alpha = 255
    if elapsed < 1.0: alpha = int(255 * (elapsed / 1.0))
    elif elapsed > (state["cycle_duration"] - 1.0): alpha = int(255 * ((state["cycle_duration"] - elapsed) / 1.0))

    line_spacing = 70
    total_text_height = len(lines) * line_spacing
    current_y = (HEIGHT // 2) - (total_text_height // 2)

    # Draw Center Text
    for line in lines:
        if line: # Skip empty lines used for spacing
            w = draw.textbbox((0, 0), line.strip(), font=font_main)[2]
            draw.text(((SAFE_X + (SAFE_W - w) // 2), current_y), line.strip(), font=font_main, fill=(255, 255, 255, alpha))
        current_y += line_spacing

    # 4. TIMER BAR (Shorts Safe Zone Only)
    # The shrinking urgency bar inside the mobile view
    bar_width = SAFE_W * (1 - progress)
    draw.rectangle([SAFE_X, HEIGHT - 20, SAFE_X + bar_width, HEIGHT], fill=(255, 60, 90))

    return frame.tobytes()

def start_stream():
    try:
        font_main = ImageFont.truetype(FONT_BOLD, 55) # Slightly smaller to fit Q&A formatting
        font_sub = ImageFont.truetype(FONT_BOLD, 80)
        font_small = ImageFont.truetype(FONT_BOLD, 40)
    except:
        font_main = font_sub = font_small = ImageFont.load_default()

    ffmpeg_cmd = [
        'ffmpeg', '-y', '-f', 'rawvideo', '-vcodec', 'rawvideo', '-s', f'{WIDTH}x{HEIGHT}', 
        '-pix_fmt', 'rgb24', '-r', str(FPS), '-i', '-', '-stream_loop', '-1', '-i', AUDIO_FILE, 
        '-c:v', 'libx264', '-preset', 'veryfast', '-tune', 'zerolatency', 
        '-b:v', '2500k', '-maxrate', '2500k', '-bufsize', '5000k', '-pix_fmt', 'yuv420p', '-g', '30',
        '-c:a', 'aac', '-b:a', '128k', '-ar', '44100',
        '-f', 'flv', f"rtmp://a.rtmp.youtube.com/live2/{STREAM_KEY}"
    ]
    
    process = subprocess.Popen(ffmpeg_cmd, stdin=subprocess.PIPE)
    
    while True:
        if time.time() - START_TIME > MAX_DURATION:
            trigger_next_run()
            
        frame_data = render_frame(font_main, font_sub, font_small)
        try:
            process.stdin.write(frame_data)
        except:
            break
        time.sleep(1.0/FPS)

if __name__ == "__main__":
    threading.Thread(target=get_live_subs, daemon=True).start()
    threading.Thread(target=update_content, daemon=True).start()
    start_stream()
