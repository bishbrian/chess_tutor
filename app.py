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

# --- CONFIG ---
st.set_page_config(page_title="Gemini Chess Tutor", layout="wide")

# --- AUTHENTICATION ---
client = None
try:
    if "GEMINI_API_KEY" in st.secrets:
        client = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])
except Exception as e:
    st.warning(f"⚠️ Setup Error: {e}")

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
    # Cloud & Mac Fallbacks
    potential_paths = [
        "/usr/games/stockfish", 
        "/opt/homebrew/bin/stockfish", 
        "/usr/local/bin/stockfish"
    ]
    for p in potential_paths:
        if os.path.exists(p): return p
    return None

stockfish_path = get_stockfish_path()

# --- AI & ENGINE LOGIC ---
def get_ai_move(board):
    if not client: return None, "AI not connected."
    # We ask specifically for the UCI move to avoid chatter
    prompt = f"""
    You are playing {board.turn} (White/Black). 
    Current FEN: {board.fen()}. 
    History: {[m.uci() for m in board.move_stack[-5:]]}
    Reply ONLY with the best move in UCI format (e.g. e2e4).
    """
    try:
        resp = client.models.generate_content(model="gemini-2.0-flash", contents=prompt)
        move_str = resp.text.strip().split()[-1]
        move = chess.Move.from_uci(move_str)
        if move in board.legal_moves: return move, None
        return None, "Illegal move"
    except Exception as e: return None, str(e)

def get_engine_move(board):
    if not stockfish_path: return None, "No Engine"
    try:
        engine = chess.engine.SimpleEngine.popen_uci(stockfish_path)
        res = engine.play(board, chess.engine.Limit(time=0.5))
        engine.quit()
        return res.move, None
    except Exception as e:
        return None, str(e)

# --- BOARD RENDERING ---
def render_interactive_board():
    board = st.session_state.board
    
    arrows = []
    if st.session_state.last_move:
        arrows.append(chess.svg.Arrow(st.session_state.last_move.from_square, st.session_state.last_move.to_square))
        
    fill = {}
    if st.session_state.selected_square is not None:
        fill = {st.session_state.selected_square: "#ccffcc"} 
        
    svg_data = chess.svg.board(board=board, fill=fill, arrows=arrows, size=400)
    png_data = cairosvg.svg2png(bytestring=svg_data.encode('utf-8'))
    image = Image.open(io.BytesIO(png_data))
    
    value = streamlit_image_coordinates(image, key="board_click")
    
    if value:
        col_i = value['x'] // 50
        row_i = value['y'] // 50
        file_idx = col_i
        rank_idx = 7 - row_i
        clicked_square = chess.square(file_idx, rank_idx)
        
        if st.session_state.selected_square is None:
            piece = board.piece_at(clicked_square)
            if piece and piece.color == board.turn:
                st.session_state.selected_square = clicked_square
                st.rerun()
        else:
            move = chess.Move(st.session_state.selected_square, clicked_square)
            if chess.square_rank(clicked_square) in [0, 7] and board.piece_at(st.session_state.selected_square).piece_type == chess.PAWN:
                move = chess.Move(st.session_state.selected_square, clicked_square, promotion=chess.QUEEN)

            if move in board.legal_moves:
                board.push(move)
                st.session_state.last_move = move
                st.session_state.selected_square = None
                st.rerun()
            else:
                st.session_state.selected_square = None
                st.rerun()

# --- PGN EXPORT LOGIC ---
def get_pgn_download(white_name, black_name):
    game = chess.pgn.Game.from_board(st.session_state.board)
    game.headers["Event"] = "Gemini Chess Session"
    game.headers["White"] = white_name
    game.headers["Black"] = black_name
    
    exporter = chess.pgn.StringExporter(headers=True, variations=True, comments=True)
    return game.accept(exporter)

# --- MAIN APP LAYOUT ---
st.title("♟️ Gemini Chess Tutor")

# Sidebar Controls
with st.sidebar:
    st.header("Settings")
    white_player = st.selectbox("White Player", ["Human", "Gemini AI", "Stockfish"])
    black_player = st.selectbox("Black Player", ["Gemini AI", "Stockfish", "Human"])
    
    st.divider()
    if st.button("New Game"):
        st.session_state.board = chess.Board()
        st.session_state.chat_history = []
        st.session_state.last_move = None
        st.rerun()
    
    # Auto-Play Logic for AI vs Engine
    if white_player != "Human" and st.session_state.board.turn == chess.WHITE:
        if st.button("Trigger White Move"):
            if white_player == "Stockfish":
                m, e = get_engine_move(st.session_state.board)
            else:
                m, e = get_ai_move(st.session_state.board)
                print(f"AI move was {m}, {e}; ")
            if m:
                st.session_state.board.push(m)
                st.session_state.last_move = m
                st.rerun()
    
    if black_player != "Human" and st.session_state.board.turn == chess.BLACK:
        if st.button("Trigger Black Move"):
            if black_player == "Stockfish":
                m, e = get_engine_move(st.session_state.board)
            else:
                m, e = get_ai_move(st.session_state.board)
            if m:
                st.session_state.board.push(m)
                st.session_state.last_move = m
                st.rerun()

# Main Layout
col1, col2 = st.columns([1.5, 1])

with col1:
    render_interactive_board()

with col2:
    # --- SCORE SHEET (NEW) ---
    st.subheader("📝 Game History")
    
    # 1. Generate Move List
    move_list = []
    temp_board = chess.Board() # Replay game to get SAN (Standard Notation)
    
    # Create a list of dictionaries for the table
    history_data = []
    full_moves = []
    current_move = {}
    
    for i, move in enumerate(st.session_state.board.move_stack):
        san = temp_board.san(move)
        temp_board.push(move)
        
        if i % 2 == 0: # White's move
            current_move = {"No.": (i // 2) + 1, "White": san, "Black": ""}
        else: # Black's move
            current_move["Black"] = san
            history_data.append(current_move)
            current_move = {}
    
    # Append pending move if game is in progress (White moved, Black hasn't)
    if current_move:
        history_data.append(current_move)

    # 2. Display Table
    if history_data:
        # Create labels based on who is playing
        w_label = f"White ({white_player})"
        b_label = f"Black ({black_player})"
        
        # Simple markdown table
        md_table = f"| Move | {w_label} | {b_label} |\n| :--- | :--- | :--- |\n"
        for row in history_data:
            md_table += f"| **{row['No.']}** | {row['White']} | {row['Black']} |\n"
        
        st.markdown(md_table)
    else:
        st.info("Game hasn't started.")

    # 3. PGN Download Button
    st.divider()
    pgn_data = get_pgn_download(white_player, black_player)
    st.download_button(
        label="💾 Download PGN",
        data=pgn_data,
        file_name="gemini_chess_game.pgn",
        mime="text/plain"
    )

    # --- CHAT ---
    st.divider()
    st.subheader("💬 Chat with Tutor")
    
    if prompt := st.chat_input("Ask about the game..."):
        st.session_state.chat_history.append({"role": "user", "content": prompt})
        
        # Gemini Analysis
        with st.spinner("Tutor is thinking..."):
            fen = st.session_state.board.fen()
            pgn_str = get_pgn_download(white_player, black_player)
            full_prompt = f"Analyze this position.\nFEN: {fen}\nPGN: {pgn_str}\nUser Question: {prompt}"
            
            try:
                resp = client.models.generate_content(model="gemini-2.0-flash", contents=full_prompt)
                st.session_state.chat_history.append({"role": "assistant", "content": resp.text})
            except Exception as e:
                st.error(f"AI Error: {e}")
            st.rerun()

    for msg in st.session_state.chat_history:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
