import streamlit as st
import chess
import chess.pgn
import chess.svg
import chess.engine
from google import genai
from streamlit_image_coordinates import streamlit_image_coordinates
import shutil
import io
import cairosvg
import base64
from PIL import Image
import os
import time
import re

# --- CONFIG ---
st.set_page_config(page_title="Gemini Chess Tutor", layout="wide")

# --- HELPER: ON-SCREEN LOGGER ---
if 'debug_logs' not in st.session_state:
    st.session_state.debug_logs = []

def log_msg(msg):
    """Adds a timestamped message to the on-screen debug console."""
    timestamp = time.strftime('%H:%M:%S')
    st.session_state.debug_logs.append(f"[{timestamp}] {msg}")
    # Keep log manageable (last 50 lines)
    if len(st.session_state.debug_logs) > 50:
        st.session_state.debug_logs.pop(0)

# --- AUTHENTICATION ---
client = None
try:
    if "GEMINI_API_KEY" in st.secrets:
        client = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])
    else:
        log_msg("⚠️ API Key not found in secrets.")
except Exception as e:
    log_msg(f"⚠️ Setup Error: {e}")

# --- SESSION STATE ---
if 'board' not in st.session_state:
    st.session_state.board = chess.Board()
if 'chat_history' not in st.session_state:
    st.session_state.chat_history = []
if 'selected_square' not in st.session_state:
    st.session_state.selected_square = None
if 'last_move' not in st.session_state:
    st.session_state.last_move = None

# --- STOCKFISH SETUP ---
def get_stockfish_path():
    path = shutil.which("stockfish")
    if path: return path
    potential_paths = [
        "/usr/games/stockfish", 
        "/opt/homebrew/bin/stockfish", 
        "/usr/local/bin/stockfish"
    ]
    for p in potential_paths:
        if os.path.exists(p): return p
    return None

stockfish_path = get_stockfish_path()
if stockfish_path:
    pass # detected silently
else:
    log_msg("Stockfish binary not found.")

# --- AI & ENGINE LOGIC ---
def get_ai_move(board):
    if not client: 
        log_msg("AI Call failed: Client not initialized.")
        return None, "AI not connected."
    
    log_msg(f"🤖 Gemini thinking for {board.turn}...")
    
    prompt = f"""
    You are playing {board.turn} (White/Black). 
    Current FEN: {board.fen()}. 
    History: {[m.uci() for m in board.move_stack[-5:]]}
    Reply ONLY with the best move in UCI format (e.g. e2e4). Do not add explanations.
    """
    try:
        resp = client.models.generate_content(model="gemini-2.0-flash", contents=prompt)
        raw_text = resp.text
        log_msg(f"AI Raw Response: '{raw_text}'")
        
        # ROBUST PARSING: Find the move using Regex
        # Looks for pattern like "e2e4" or "a7a8q" (promotion)
        match = re.search(r'([a-h][1-8][a-h][1-8][qrbn]?)', raw_text)
        
        if match:
            move_str = match.group(1)
            log_msg(f"Parsed Move: {move_str}")
            move = chess.Move.from_uci(move_str)
            
            if move in board.legal_moves: 
                return move, None
            else:
                log_msg(f"❌ Illegal move attempted: {move_str}")
                return None, f"Illegal move: {move_str}"
        else:
            log_msg("❌ Could not find UCI move in response.")
            return None, "No move found in response"

    except Exception as e:
        log_msg(f"🔥 AI Exception: {e}")
        return None, str(e)

def get_engine_move(board):
    if not stockfish_path: 
        log_msg("Engine Call failed: Path not found.")
        return None,
