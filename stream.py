import os
import time
import threading
import subprocess
import requests
import random
from collections import Counter
import pytchat
from PIL import Image, ImageDraw, ImageFont

# --- SYSTEM CONFIG ---
START_TIME = time.time()
MAX_DURATION = (5 * 3600) + (45 * 60) # 5h 45m handoff
GITHUB_REPO = os.getenv("GITHUB_REPOSITORY")
GH_PAT = os.getenv("GH_PAT")

# --- BROADCAST SPECS ---
WIDTH, HEIGHT = 1280, 720
FPS = 30
STREAM_KEY = os.getenv("STREAM_KEY")
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")
CHANNEL_ID = os.getenv("CHANNEL_ID")
FONT_BOLD = "Montserrat-Bold.ttf"
AUDIO_FILE = "audio.mp3"

# --- GAME STATE ---
game_state = {
    "score": 0,
    "high_score": 0,
    "player_lane": 2, # Lanes: 1 (Left), 2 (Center), 3 (Right)
    "obstacles": [],  # List of dicts: {"lane": int, "y": float}
    "speed": 6.0,
    "crashed": False,
    "crash_time": 0,
    "recent_votes": [],
    "live_video_id": None
}

# --- 1. FETCH LIVE VIDEO ID (For Chat) ---
def get_live_video_id():
    """Finds the currently active live stream for the channel."""
    while not game_state["live_video_id"]:
        try:
            url = f"https://www.googleapis.com/youtube/v3/search?part=id&channelId={CHANNEL_ID}&eventType=live&type=video&key={YOUTUBE_API_KEY}"
            response = requests.get(url).json()
            if "items" in response and len(response["items"]) > 0:
                game_state["live_video_id"] = response["items"][0]["id"]["videoId"]
                print(f"Live Stream Found! Video ID: {game_state['live_video_id']}")
                break
        except Exception as e:
            print(f"Waiting for stream to go live to attach chat... ({e})")
        time.sleep(30) # Check every 30 secs to save API quota

# --- 2. LIVE CHAT READER THREAD ---
def read_live_chat():
    """Connects to YouTube chat and reads movement commands."""
    while not game_state["live_video_id"]:
        time.sleep(5)
        
    chat = pytchat.create(video_id=game_state["live_video_id"])
    print("Chat listener connected!")
    
    while chat.is_alive():
        for c in chat.get().sync_items():
            msg = c.message.strip()
            # If user types 1, 2, or 3, register the vote
            if msg in ["1", "2", "3"]:
                game_state["recent_votes"].append(int(msg))
        time.sleep(0.5)

# --- 3. VOTE PROCESSOR THREAD ---
def process_votes():
    """Checks chat votes every 1.5 seconds and moves the player."""
    while True:
        if game_state["recent_votes"] and not game_state["crashed"]:
            # Find the most voted lane
            vote_counts = Counter(game_state["recent_votes"])
            winning_lane = vote_counts.most_common(1)[0][0]
            game_state["player_lane"] = winning_lane
            game_state["recent_votes"] = [] # Clear votes for next round
        time.sleep(1.5) # Gives audience 1.5 seconds to decide

# --- 4. GAME LOGIC & RENDERING ---
def render_game_frame(font_main, font_small):
    frame = Image.new('RGB', (WIDTH, HEIGHT), (10, 10, 15))
    draw = ImageDraw.Draw(frame)
    
    # Grid Logic (Retro moving background)
    t = time.time()
    offset = int((t * 200) % 100)
    for y in range(0, HEIGHT, 100):
        draw.line([(0, y + offset), (WIDTH, y + offset)], fill=(20, 20, 35), width=2)
    
    # Draw Lanes (X coordinates: 340, 640, 940)
    lanes_x = {1: 340, 2: 640, 3: 940}
    draw.line([(490, 0), (490, HEIGHT)], fill=(0, 255, 150), width=3) # Left divider
    draw.line([(790, 0), (790, HEIGHT)], fill=(0, 255, 150), width=3) # Right divider

    if game_state["crashed"]:
        # Crash Screen Effect
        if (t * 10) % 2 > 1: # Flashing effect
            draw.rectangle([0, 0, WIDTH, HEIGHT], fill=(150, 0, 0))
        draw.text((WIDTH//2 - 200, HEIGHT//2 - 50), "CRASHED!", font=font_main, fill=(255, 255, 255))
        draw.text((WIDTH//2 - 180, HEIGHT//2 + 50), "Rebooting Systems...", font=font_small, fill=(255, 255, 255))
        
        # Reset Logic after 3 seconds
        if t - game_state["crash_time"] > 3:
            game_state["crashed"] = False
            game_state["obstacles"] = []
            game_state["score"] = 0
            game_state["speed"] = 6.0
    else:
        # 1. Update & Draw Score
        game_state["score"] += 1
        if game_state["score"] > game_state["high_score"]:
            game_state["high_score"] = game_state["score"]
            
        # UI Top Bar
        draw.rectangle([0, 0, WIDTH, 80], fill=(20, 20, 30))
        draw.text((30, 20), f"SCORE: {game_state['score']}", font=font_main, fill=(0, 255, 200))
        draw.text((WIDTH - 400, 20), f"HIGH SCORE: {game_state['high_score']}", font=font_main, fill=(255, 200, 0))
        
        # 2. Draw Instructions for Chat
        draw.rectangle([0, HEIGHT - 60, WIDTH, HEIGHT], fill=(20, 20, 30))
        draw.text((250, HEIGHT - 45), "TYPE IN CHAT TO STEER:   [1] LEFT   |   [2] CENTER   |   [3] RIGHT", font=font_small, fill=(255, 255, 255))

        # 3. Handle Obstacles
        if random.random() < 0.02 + (game_state["speed"] / 1000): # Spawn rate increases with speed
            game_state["obstacles"].append({"lane": random.choice([1, 2, 3]), "y": 80})
            
        for obs in game_state["obstacles"]:
            obs["y"] += game_state["speed"]
            obs_x = lanes_x[obs["lane"]]
            
            # Draw Obstacle (Red Block)
            draw.rectangle([obs_x - 70, obs["y"] - 30, obs_x + 70, obs["y"] + 30], fill=(255, 50, 50), outline=(255, 100, 100), width=4)
            
            # Collision Detection
            player_y = HEIGHT - 150
            if obs["lane"] == game_state["player_lane"] and abs(obs["y"] - player_y) < 60:
                game_state["crashed"] = True
                game_state["crash_time"] = t
                break
                
        # Remove off-screen obstacles
        game_state["obstacles"] = [obs for obs in game_state["obstacles"] if obs["y"] < HEIGHT]
        
        # Increase speed slightly over time
        game_state["speed"] += 0.002

        # 4. Draw Player (Neon Blue Ship)
        px = lanes_x[game_state["player_lane"]]
        py = HEIGHT - 150
        draw.polygon([(px, py - 40), (px - 40, py + 40), (px + 40, py + 40)], fill=(0, 200, 255), outline=(255, 255, 255), width=3)
        # Engine Glow
        glow_size = random.randint(10, 30)
        draw.ellipse([px - 15, py + 40, px + 15, py + 40 + glow_size], fill=(0, 255, 255))

    return frame.tobytes()

# --- 5. STREAM PIPELINE ---
def trigger_next_run():
    if not GH_PAT or not GITHUB_REPO: return
    url = f"https://api.github.com/repos/{GITHUB_REPO}/dispatches"
    headers = {"Authorization": f"token {GH_PAT}", "Accept": "application/vnd.github.v3+json"}
    requests.post(url, json={"event_type": "restart_stream"}, headers=headers)
    os._exit(0)

def start_stream():
    try:
        font_main = ImageFont.truetype(FONT_BOLD, 45)
        font_small = ImageFont.truetype(FONT_BOLD, 25)
    except:
        font_main = font_small = ImageFont.load_default()

    ffmpeg_cmd = [
        'ffmpeg', '-y', '-f', 'rawvideo', '-vcodec', 'rawvideo', '-s', f'{WIDTH}x{HEIGHT}', 
        '-pix_fmt', 'rgb24', '-r', str(FPS), '-i', '-', '-stream_loop', '-1', '-i', AUDIO_FILE, 
        '-c:v', 'libx264', '-preset', 'ultrafast', '-tune', 'zerolatency', 
        '-b:v', '2500k', '-maxrate', '2500k', '-bufsize', '5000k',
        '-pix_fmt', 'yuv420p', '-g', '60',
        '-c:a', 'aac', '-b:a', '128k', '-ar', '44100',
        '-f', 'flv', f"rtmp://a.rtmp.youtube.com/live2/{STREAM_KEY}"
    ]
    
    process = subprocess.Popen(ffmpeg_cmd, stdin=subprocess.PIPE)
    
    while True:
        if time.time() - START_TIME > MAX_DURATION:
            trigger_next_run()
            
        frame_data = render_game_frame(font_main, font_small)
        try:
            process.stdin.write(frame_data)
        except Exception as e:
            print(f"Pipeline broken: {e}")
            break
        time.sleep(1/FPS)

if __name__ == "__main__":
    # Start all background operations
    threading.Thread(target=get_live_video_id, daemon=True).start()
    threading.Thread(target=read_live_chat, daemon=True).start()
    threading.Thread(target=process_votes, daemon=True).start()
    
    # Keep stream alive
    while True:
        start_stream()
        time.sleep(3)
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
