import streamlit as st
import chess
import chess.pgn
import chess.engine
from google import genai # <--- NEW IMPORT
import shutil
import io

# --- CONFIG ---
st.set_page_config(page_title="Gemini Chess Lab", layout="wide")

# --- AUTHENTICATION (NEW SDK) ---
# The new SDK automatically looks for "GEMINI_API_KEY" in your environment/secrets.
# We initialize the client once.
try:
    if "GEMINI_API_KEY" in st.secrets:
        # standard initialization for the new SDK
        client = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])
    else:
        st.warning("⚠️ API Key missing. Please set GEMINI_API_KEY in secrets.")
        client = None
except Exception as e:
    st.warning(f"⚠️ Setup Error: {e}")
    client = None

# --- STOCKFISH SETUP ---
def get_stockfish_path():
    return shutil.which("stockfish")

stockfish_path = get_stockfish_path()

# --- SESSION STATE ---
if 'board' not in st.session_state:
    st.session_state.board = chess.Board()
if 'chat_history' not in st.session_state:
    st.session_state.chat_history = []
if 'orientation' not in st.session_state:
    st.session_state.orientation = 'white'

# --- LOGIC: AI & ENGINE ---
def get_engine_move(board, time_limit=1.0):
    if not stockfish_path:
        return None, "Stockfish not installed."
    try:
        engine = chess.engine.SimpleEngine.popen_uci(stockfish_path)
        result = engine.play(board, chess.engine.Limit(time=time_limit))
        engine.quit()
        return result.move, None
    except Exception as e:
        return None, str(e)

def get_ai_analysis(board, user_question=None):
    if not client: return "AI not connected."
    
    fen = board.fen()
    model_id = "gemini-2.0-flash" # Uses the latest fast model
    
    if user_question:
        prompt = f"""
        You are a friendly Chess Tutor. 
        Current FEN: {fen}
        User Question: "{user_question}"
        
        Explain the answer clearly. Focus on plans, weaknesses, and key squares.
        Do not just give engine lines. Explain the *reasoning*.
        """
    else:
        prompt = f"Analyze this position (FEN: {fen}). Briefly point out the biggest threat or opportunity."
    
    try:
        response = client.models.generate_content(
            model=model_id,
            contents=prompt
        )
        return response.text
    except Exception as e:
        return f"AI Error: {e}"

def get_ai_move(board):
    if not client: return None, "AI not connected."
    
    model_id = "gemini-2.0-flash"
    prompt = f"""
    You are playing Black/White. Current FEN: {board.fen()}.
    Legal Moves: {[m.uci() for m in board.legal_moves]}
    
    Pick the single best strategic move. 
    Output ONLY the move in UCI format (e.g. e2e4). No text.
    """
    try:
        response = client.models.generate_content(
            model=model_id,
            contents=prompt
        )
        move_str = response.text.strip().split()[-1] 
        move = chess.Move.from_uci(move_str)
        if move in board.legal_moves:
            return move, None
        return None, f"AI suggested illegal move: {move_str}"
    except Exception as e:
        return None, str(e)

# --- UI: SIDEBAR ---
with st.sidebar:
    st.header("🎮 Control Panel")
    
    mode = st.radio("Game Mode", ["Practice (Human vs AI)", "Analysis Board", "AI vs Engine"])
    
    st.divider()
    
    if st.button("Reset Board"):
        st.session_state.board = chess.Board()
        st.session_state.chat_history = []
        st.rerun()

    st.subheader("📂 Load Game")
    uploaded_file = st.file_uploader("Upload PGN", type="pgn")
    if uploaded_file and st.button("Load PGN"):
        stringio = io.StringIO(uploaded_file.getvalue().decode("utf-8"))
        game = chess.pgn.read_game(stringio)
        st.session_state.board = game.board()
        st.session_state.chat_history = [{"role": "assistant", "content": f"Loaded PGN: {game.headers.get('Event', 'Unknown')}"}]
        st.rerun()

    fen_input = st.text_input("Or paste FEN string")
    if st.button("Load FEN"):
        try:
            st.session_state.board = chess.Board(fen_input)
            st.rerun()
        except:
            st.error("Invalid FEN")

# --- UI: MAIN AREA ---
col1, col2 = st.columns([1.2, 1])

with col1:
    from streamlit_chessboard import chessboard
    board_data = chessboard(
        st.session_state.board,
        orientation=st.session_state.orientation,
        key="board_component"
    )
    
    if board_data:
        move_fen = board_data.get("fen")
        if move_fen and move_fen != st.session_state.board.fen():
            st.session_state.board = chess.Board(move_fen)
            st.rerun()

    # AUTOMATED MOVES
    board = st.session_state.board
    if not board.is_game_over():
        if mode == "Practice (Human vs AI)":
            # Check if it's AI's turn (Assuming AI plays Black)
            if board.turn == chess.BLACK: 
                with st.spinner("AI Tutor is thinking..."):
                    move, err = get_ai_move(board)
                    if move:
                        board.push(move)
                        st.session_state.board = board
                        st.rerun()
        
        elif mode == "AI vs Engine":
            if board.turn == chess.WHITE: # Engine
                move, err = get_engine_move(board, time_limit=0.1)
            else: # AI
                move, err = get_ai_move(board)
            
            if move:
                board.push(move)
                st.session_state.board = board
                st.rerun()

with col2:
    st.subheader("🧠 Tutor's Reasoning")
    
    for msg in st.session_state.chat_history:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    if prompt := st.chat_input("Ask about this position..."):
        st.session_state.chat_history.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)
        
        with st.spinner("Analyzing..."):
            response = get_ai_analysis(st.session_state.board, prompt)
            st.session_state.chat_history.append({"role": "assistant", "content": response})
            st.rerun()
            
    st.divider()
    if st.button("Request Hint (Stockfish)"):
        move, _ = get_engine_move(st.session_state.board)
        if move:
            st.info(f"Stockfish recommends: **{move.uci()}**")
