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
from PIL import Image

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

# --- BOARD RENDERING (THE FIX) ---
def render_interactive_board():
    board = st.session_state.board
    
    # 1. Highlight selected square & last move
    arrows = []
    if st.session_state.last_move:
        arrows.append(chess.svg.Arrow(st.session_state.last_move.from_square, st.session_state.last_move.to_square))
        
    fill = {}
    if st.session_state.selected_square is not None:
        fill = {st.session_state.selected_square: "#ccffcc"} # Green highlight
        
    # 2. Create SVG String
    svg_data = chess.svg.board(
        board=board,
        fill=fill,
        arrows=arrows,
        size=400
    )
    
    # 3. Convert SVG -> PNG -> PIL Image
    # This fixes the "File name too long" error because we pass an Object, not a String
    png_data = cairosvg.svg2png(bytestring=svg_data.encode('utf-8'))
    image = Image.open(io.BytesIO(png_data))
    
    # 4. Render the Image Component
    # logic: returns {'x': 123, 'y': 456}
    value = streamlit_image_coordinates(image, key="board_click")
    
    # 5. Handle Clicks
    if value:
        col_i = value['x'] // 50
        row_i = value['y'] // 50
        
        # Handle Flip (if you added board orientation logic later, adjust here)
        # Assuming White at bottom for now:
        file_idx = col_i
        rank_idx = 7 - row_i
        clicked_square = chess.square(file_idx, rank_idx)
        
        if st.session_state.selected_square is None:
            # Select Piece
            piece = board.piece_at(clicked_square)
            if piece and piece.color == board.turn:
                st.session_state.selected_square = clicked_square
                st.rerun()
        else:
            # Move Piece
            move = chess.Move(st.session_state.selected_square, clicked_square)
            # Auto-promote to Queen
            if chess.square_rank(clicked_square) in [0, 7] and board.piece_at(st.session_state.selected_square).piece_type == chess.PAWN:
                move = chess.Move(st.session_state.selected_square, clicked_square, promotion=chess.QUEEN)

            if move in board.legal_moves:
                board.push(move)
                st.session_state.last_move = move
                st.session_state.selected_square = None
                st.rerun()
            else:
                # Deselect if invalid
                st.session_state.selected_square = None
                st.rerun()

# --- LAYOUT ---
col1, col2 = st.columns([1.5, 1])

with col1:
    st.subheader("Chess Board")
    render_interactive_board()
    st.caption("Tap piece -> Tap square")

with col2:
    st.header("Actions")
    if st.button("Reset"):
        st.session_state.board = chess.Board()
        st.session_state.selected_square = None
        st.rerun()
    
    if st.button("AI Move"):
        m, e = get_ai_move(st.session_state.board)
        if m: 
            st.session_state.board.push(m)
            st.rerun()
            
    if st.button("Stockfish Move"):
        m, e = get_engine_move(st.session_state.board)
        if m:
            st.session_state.board.push(m)
            st.rerun()
