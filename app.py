import streamlit as st
import chess
import chess.pgn
import chess.svg
import chess.engine
from google import genai
from streamlit_image_coordinates import streamlit_image_coordinates
import shutil
import io
import base64

# --- CONFIG ---
st.set_page_config(page_title="Gemini Chess Lab", layout="wide")

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
stockfish_path = shutil.which("stockfish")

# --- AI & ENGINE LOGIC ---
def get_ai_move(board):
    if not client: return None, "AI not connected."
    prompt = f"Play the best move for {board.turn} (White/Black). FEN: {board.fen()}. Reply ONLY with the UCI move (e.g. e2e4)."
    try:
        resp = client.models.generate_content(model="gemini-2.0-flash", contents=prompt)
        move_str = resp.text.strip().split()[-1]
        move = chess.Move.from_uci(move_str)
        if move in board.legal_moves: return move, None
        return None, "Illegal move"
    except Exception as e: return None, str(e)

def get_engine_move(board):
    if not stockfish_path: return None, "No Engine"
    engine = chess.engine.SimpleEngine.popen_uci(stockfish_path)
    res = engine.play(board, chess.engine.Limit(time=0.5))
    engine.quit()
    return res.move, None

# --- BOARD INTERACTION (THE FIX) ---
def render_interactive_board():
    board = st.session_state.board
    
    # 1. Generate SVG
    # We highlight the selected square if one is clicked
    arrows = []
    if st.session_state.last_move:
        arrows.append(chess.svg.Arrow(st.session_state.last_move.from_square, st.session_state.last_move.to_square))
        
    fill = {}
    if st.session_state.selected_square is not None:
        fill = {st.session_state.selected_square: "#ccffcc"} # Light green highlight
        
    svg = chess.svg.board(
        board=board,
        fill=fill,
        arrows=arrows,
        size=400 # Fixed pixel size for coordinate math
    )
    
    # 2. Convert SVG to Base64 for Image Component
    b64 = base64.b64encode(svg.encode('utf-8')).decode("utf-8")
    img_src = f"data:image/svg+xml;base64,{b64}"

    # 3. Capture Click
    # This component returns a dict like {'x': 120, 'y': 45} when clicked
    value = streamlit_image_coordinates(img_src, key="board_click")
    
    # 4. Handle Click Logic
    if value:
        # Calculate Square from X/Y
        # Board is 400px wide. Each square is 50px.
        col_i = value['x'] // 50
        row_i = value['y'] // 50
        
        # Convert to chess square (0-63)
        # Standard view: Row 0 is Rank 8, Row 7 is Rank 1. Col 0 is File A.
        # We need to flip logic if board is black oriented (omitted for simplicity here, assuming White bottom)
        file_idx = col_i
        rank_idx = 7 - row_i
        clicked_square = chess.square(file_idx, rank_idx)
        
        # LOGIC: Select or Move?
        if st.session_state.selected_square is None:
            # First Click: Select piece
            piece = board.piece_at(clicked_square)
            if piece and piece.color == board.turn:
                st.session_state.selected_square = clicked_square
                st.rerun()
        else:
            # Second Click: Try to move
            move = chess.Move(st.session_state.selected_square, clicked_square)
            
            # Check promotion (auto-promote to Queen for UI simplicity)
            if chess.square_rank(clicked_square) in [0, 7] and board.piece_at(st.session_state.selected_square).piece_type == chess.PAWN:
                move = chess.Move(st.session_state.selected_square, clicked_square, promotion=chess.QUEEN)

            if move in board.legal_moves:
                board.push(move)
                st.session_state.last_move = move
                st.session_state.selected_square = None
                st.rerun()
            else:
                # If invalid move (or clicked same square), deselect
                st.session_state.selected_square = None
                st.rerun()

# --- MAIN APP LAYOUT ---
col1, col2 = st.columns([1.5, 1])

with col1:
    st.subheader("Chess Board")
    render_interactive_board()
    st.caption("Tap a piece to select, then tap a square to move.")

with col2:
    st.header("Controls")
    if st.button("Reset Game"):
        st.session_state.board = chess.Board()
        st.session_state.selected_square = None
        st.rerun()
        
    st.divider()
    
    if st.button("AI Move (Gemini)"):
        with st.spinner("Thinking..."):
            m, e = get_ai_move(st.session_state.board)
            if m: 
                st.session_state.board.push(m)
                st.rerun()
            else: st.error(e)
            
    if st.button("Engine Move (Stockfish)"):
        m, e = get_engine_move(st.session_state.board)
        if m:
            st.session_state.board.push(m)
            st.rerun()
