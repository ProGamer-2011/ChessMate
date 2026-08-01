from PySide6.QtWidgets import (
    QApplication,
    QWidget,
    QPushButton,
    QLabel,
    QVBoxLayout,
    QGraphicsOpacityEffect,
    QGraphicsDropShadowEffect,
    QLineEdit
)
from PySide6.QtCore import (
    Qt,
    QPoint,
    QPropertyAnimation,
    QEasingCurve,
    QTimer,
    QThread,
    QObject,
    Signal,
    Slot
)
from player_profile.profile_manager import (
    profile_exists,
    load_profile,
    save_profile
)
import ctypes
import os
import time
import json
import faulthandler
import traceback
import sys
from updater.updater import Updater

faulthandler.enable()

thinking_timer = QTimer()
thinking_step = 0
status_base_text = ""
status_dots = 0
status_dot_timer = QTimer()
toast_visible = False
pending_status = ""
home_page = None
onboarding_window = None
model = None
engine = None
loader_thread = None
_analysis_thread = None
_analysis_worker = None
last_analysis_bundle = None

BASE_DIR = os.path.dirname(
    os.path.abspath(__file__)
)

stockfish_path = os.path.join(
    BASE_DIR,
    "engine",
    "stockfish.exe"
)

YOLO_model_path = os.path.join(
    BASE_DIR,
    "vision_model",
    "Chess.pt"
)

ICON_PATH = os.path.join(
    BASE_DIR,
    "assets",
    "ChessMate.png"
)

myappid = "ChessMate.Desktop.App"
ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
    myappid
)

class ChessMateLoaderThread(QThread):

    status_update = Signal(str)

    finished_loading = Signal(
        object,
        object
    )

    def run(self):

        self.status_update.emit(
            "Loading Vision Model..."
        )

        from ultralytics import YOLO

        model = YOLO(
            YOLO_model_path
        )

        self.status_update.emit(
            "Starting Stockfish..."
        )

        import chess.engine

        engine = chess.engine.SimpleEngine.popen_uci(
            stockfish_path,
            timeout=40.0
        )

        self.finished_loading.emit(
            model,
            engine
        )

class SignalBus(QObject):

    fen_ready = Signal(str)

    move_ready = Signal(str, object, str)

    status_ready = Signal(str)

    start_game_required = Signal()

    choose_side_required = Signal()

    player_move_submitted = Signal(str)

bus = SignalBus()

def animate_status_dots():
    global status_dots, status_base_text

    dots = "." * (status_dots % 4)
    toast_label.setText(f"{status_base_text}{dots}")

    status_dots += 1

def show_long_wait():

    global status_base_text

    status_base_text = (
        "Taking longer than expected"
    )

    toast.show()

    status_dot_timer.start()

status_watchdog = QTimer()
status_watchdog.setSingleShot(True)
status_watchdog.timeout.connect(
    show_long_wait
)

updater = Updater()

print("ChessMate Version:", updater.get_version())
print("Build:", updater.get_build())

from PySide6.QtGui import QIcon

app = QApplication([])
app.processEvents()

app.setWindowIcon(
    QIcon(ICON_PATH)
)

screen = app.primaryScreen()

geo = screen.availableGeometry()

toast = QWidget()
toast.setAttribute(Qt.WA_TranslucentBackground)

toast.setWindowFlags(
    Qt.FramelessWindowHint |
    Qt.WindowStaysOnTopHint |
    Qt.Tool
)

toast.resize(420, 50)

toast_panel = QWidget(toast)

toast_panel.setGeometry(
    0,
    0,
    420,
    50
)

shadow = QGraphicsDropShadowEffect()
shadow.setBlurRadius(25)
shadow.setOffset(0, 4)

toast_panel.setGraphicsEffect(shadow)

toast_panel.setStyleSheet("""
background-color:#0f1115;
border:1px solid #23262d;
border-radius:10px;
""")

toast_label = QLabel(
    "",
    toast_panel
)

toast_label.setAlignment(
    Qt.AlignCenter
)

toast_label.setStyleSheet("""
color:white;
font-size:15px;
font-weight:600;
""")

toast_label.setGeometry(
    0,
    0,
    420,
    50
)

toast.move(
    geo.x() + (geo.width() - 420)//2,
    geo.y() + geo.height() - 90
)

toast_anim = QPropertyAnimation(
    toast,
    b"pos"
)

toast_anim.setDuration(250)

toast_anim.setEasingCurve(
    QEasingCurve.OutBack
)

opacity = QGraphicsOpacityEffect()

toast.setGraphicsEffect(opacity)

def show_status(text):

    global status_base_text
    global status_dots
    global toast_visible
    global pending_status

    status_dot_timer.stop()

    status_dots = 0
    status_base_text = text
    pending_status = text

    status_watchdog.stop()
    status_watchdog.start(10000)

    if toast_visible:

        pending_status = text
        status_base_text = text

        toast_label.setText(text)

        return

    toast_visible = True

    final_x = geo.x() + (geo.width() - 420) // 2
    final_y = geo.y() + geo.height() - 90

    start_y = final_y + 60

    toast_anim.stop()

    toast.move(
        final_x,
        start_y
    )

    toast_label.setText(text)
    
    toast.show()

    toast_anim.setEasingCurve(
        QEasingCurve.OutBack
    )

    toast_anim.setStartValue(
        QPoint(final_x, start_y)
    )

    toast_anim.setEndValue(
        QPoint(final_x, final_y)
    )

    toast_anim.start()

status_dot_timer.timeout.connect(animate_status_dots)
status_dot_timer.setInterval(400)

def hide_status():

    global toast_visible

    toast_visible = False

    status_watchdog.stop()
    status_dot_timer.stop()

    toast_anim.stop()

    toast_anim.setEasingCurve(
        QEasingCurve.InBack
    )

    toast_anim.setStartValue(
        toast.pos()
    )

    toast_anim.setEndValue(
        QPoint(
            toast.x(),
            toast.y() + 60
        )
    )

    toast_anim.start()

    QTimer.singleShot(
        300,
        toast.hide
    )
    
def refresh_window_size():

    panel.adjustSize()

    size = panel.sizeHint()

    window.resize(
        max(size.width(), 320),
        max(size.height(), 350)
    )

    panel.setGeometry(
        0,
        0,
        window.width(),
        window.height()
    )

    close_btn.move(
        window.width() - 40,
        10
    )

def animate_thinking():

    global thinking_step

    frames = [
        "Thinking",
        "Thinking.",
        "Thinking..",
        "Thinking..."
    ]

    best_move_label.setText(
        f"Best Move: {frames[thinking_step]}"
    )

    thinking_step = (
        thinking_step + 1
    ) % len(frames)

thinking_timer.timeout.connect(
    animate_thinking
)

thinking_timer.setInterval(500)

def ui_update(
    move=None,
    evaluation=None,
    status_text=None
):
    if move == "Thinking":

        if not thinking_timer.isActive():

            thinking_timer.start()

    elif move is not None:

        thinking_timer.stop()

        best_move_label.setText(
            f"Best Move: {move}"
        )
    
    if evaluation is not None:
        eval_label.setText(
            f"Evaluation: {evaluation}"
        )

    if status_text is not None:
        status.setText(
            status_text
        )

window = QWidget()
window.setWindowOpacity(1)
window.setWindowIcon(
    QIcon(ICON_PATH)
)

panel = QWidget(window)
panel.setObjectName("MainPanel")

panel.setGeometry(
    0,
    0,
    window.width(),
    window.height()
)

def resizeEvent(event):

    panel.setGeometry(
        0,
        0,
        window.width(),
        window.height()
    )

    close_btn.move(
        window.width() - 40,
        10
    )

window.resizeEvent = resizeEvent

window.setAttribute(
    Qt.WA_TranslucentBackground
)

fade = QPropertyAnimation(
    opacity,
    b"opacity"
)

fade.setDuration(350)

fade.setEasingCurve(
    QEasingCurve.OutCubic
)

window.setWindowFlags(
    Qt.FramelessWindowHint |
    Qt.Window
)

def show_home_page():
    
    hide_status()

    from home_page import HomePage
    global home_page

    home_page = HomePage()

    home_page.start_requested.connect(
        show_chessmate_window
    )

    home_page.analysis_requested.connect(
        open_analysis_page
    )

    home_page.review_requested.connect(
        open_review_page
    )

    home_page.profile_requested.connect(
        open_profile_page
    )

    home_page.show()

def show_chessmate_window():

    global model
    global engine
    global loader_thread

    if model is not None and engine is not None:

        window.show()

        coach_btn.show()
        win_btn.show()

        best_move_label.hide()
        eval_label.hide()

        status.setText(
            "Choose a mode"
        )

        return

    show_status(
        "Loading ChessMate..."
    )

    loader_thread = (
        ChessMateLoaderThread()
    )

    loader_thread.finished_loading.connect(
        chessmate_loaded
    )

    loader_thread.status_update.connect(
        show_status
    )
    
    loader_thread.start()

def chessmate_loaded(
    loaded_model,
    loaded_engine
):

    global model
    global engine

    model = loaded_model
    engine = loaded_engine

    hide_status()

    window.show()

    coach_btn.show()
    win_btn.show()

    best_move_label.hide()
    eval_label.hide()

    status.setText(
        "Choose a mode"
    )

class AnalysisWorker(QObject):
    status_changed = Signal(str)
    finished = Signal(dict)
    failed = Signal(str)

    @Slot()
    def run(self):
        from chesscom_sync.chesscom_sync import sync_chesscom_profile
        from chesscom_sync.game_analyzer import analyze_games
        from chesscom_sync.engine_analyzer import analyze_games as engine_analyze
        from chesscom_sync.profile_builder import print_profile_bundle

        try:
            self.status_changed.emit("Syncing Chess.com games...")

            profile = load_profile()
            username = (profile.get("chesscom_username", "") or "").strip()

            games = sync_chesscom_profile(username)

            self.status_changed.emit("Running Game analysis...")

            result_one = analyze_games(games, username)

            self.status_changed.emit("Running Engine analysis...")

            result_two = engine_analyze(games, username)

            self.status_changed.emit("Building profile...")

            bundle = print_profile_bundle(
                profile=profile,
                game_result=result_one,
                engine_result=result_two,
            )

            self.finished.emit(bundle)

        except Exception:
            error_text = traceback.format_exc()

            print(error_text)

            self.failed.emit(error_text)

        except Exception:
            traceback.print_exc()
            self.failed.emit(traceback.format_exc())


def open_analysis_page():
    global _analysis_thread
    global _analysis_worker

    if _analysis_thread is not None:
        if _analysis_thread.isRunning():
            return

    show_status("Syncing Chess.com games...")

    _analysis_thread = QThread()

    _analysis_worker = AnalysisWorker()
    _analysis_worker.moveToThread(_analysis_thread)

    _analysis_thread.started.connect(_analysis_worker.run)

    _analysis_worker.status_changed.connect(show_status)

    _analysis_worker.finished.connect(_on_analysis_finished)
    _analysis_worker.failed.connect(_on_analysis_failed)

    _analysis_worker.finished.connect(_analysis_thread.quit)
    _analysis_worker.failed.connect(_analysis_thread.quit)

    _analysis_thread.finished.connect(_analysis_worker.deleteLater)
    _analysis_thread.finished.connect(_analysis_thread.deleteLater)

    _analysis_thread.start()


def _on_analysis_finished(bundle):
    global _analysis_thread
    global _analysis_worker
    global last_analysis_bundle

    hide_status()

    last_analysis_bundle = bundle

    print(json.dumps(bundle, indent=2, ensure_ascii=False, default=str))

    _analysis_thread = None
    _analysis_worker = None


def _on_analysis_failed(message):
    global _analysis_thread
    global _analysis_worker

    hide_status()

    print(f"Analysis failed: {message}")

    _analysis_thread = None
    _analysis_worker = None

def open_review_page():
    print("Review Games")

def open_profile_page():
    print("Player Profile")
    
def show_onboarding():

    global onboarding_window

    hide_status()

    onboarding_window = OnboardingWindow()

    onboarding_window.finished.connect(
        show_home_page
    )

    onboarding_window.show()

def startup_finished(
    loaded_model,
    loaded_engine
):

    global model
    global engine
    global engine_thread

    model = loaded_model
    engine = loaded_engine

    bus.move_ready.connect(
        ui_update
    )

    hide_status()

    window.hide()

    profile = load_profile()

    if not profile["name"]:

        show_onboarding()

    else:

        show_home_page()

drag_pos = QPoint()

window.setWindowTitle("ChessMate")

def close_chessmate_panel():

    global win_thread
    global coach_thread

    if "win_thread" in globals():

        if win_thread.isRunning():

            win_thread.stop()
            win_thread.wait()

    if "coach_thread" in globals():

        if coach_thread.isRunning():

            coach_thread.stop()
            coach_thread.wait()

    thinking_timer.stop()

    window.hide()

    coach_btn.show()
    win_btn.show()

    best_move_label.hide()
    eval_label.hide()

    move_input.hide()
    submit_move_btn.hide()

    status.setText(
        "Choose a mode"
    )
    
def close_everything():
    global engine
    global coach_thread
    global win_thread

    if "engine" in globals():
        engine.quit()

    if "win_thread" in globals():
        win_thread.stop()
        win_thread.wait()

    if "coach_thread" in globals():

        if coach_thread.isRunning():

            coach_thread.stop()
            coach_thread.wait()
        
    app.quit()

close_btn = QPushButton("✕", window)
close_btn.clicked.connect(close_chessmate_panel)

close_btn.setFixedSize(32, 32)

close_btn.setObjectName("CloseButton")

close_btn.setStyleSheet("""
#CloseButton{
    background-color:#1f2328;
    color:white;
    border:none;
    padding:0px;
    border-radius:10px;
    font-size:16px;
    font-weight:600;
}

#CloseButton:hover{
    background-color:#c62828;
}

#CloseButton:pressed{
    background-color:#9f1f1f;
}
""")

window.resize(320, 350)

close_btn.move(
    window.width() - 40,
    10
)

def show_start_game_button():

    start_game_btn.show()

    white_btn.hide()
    black_btn.hide()

    status.setText(
        "Press Start Game"
    )


def show_side_selection():

    start_game_btn.show()

    white_btn.show()
    black_btn.show()

    status.setText(
        "Choose Your Side"
    )

    refresh_window_size()
    
def start_game_clicked():

    white_btn.hide()
    black_btn.hide()
    
    global win_thread

    if "win_thread" in globals():

        if hasattr(
            win_thread,
            "tracker"
        ):

            win_thread.tracker.start_game()

def white_clicked():

    global win_thread

    if "win_thread" in globals():

        if hasattr(
            win_thread,
            "tracker"
        ):

            win_thread.tracker.set_user_color(
                "w"
            )

    white_btn.hide()
    black_btn.hide()


def black_clicked():

    global win_thread

    if "win_thread" in globals():

        if hasattr(
            win_thread,
            "tracker"
        ):

            win_thread.tracker.set_user_color(
                "b"
            )

    white_btn.hide()
    black_btn.hide()

bus.start_game_required.connect(
    show_start_game_button
)

bus.choose_side_required.connect(
    show_side_selection
)

window.move(
    geo.width() - 340,
    geo.height() // 2 - 120
)

window.setStyleSheet("""
#MainPanel{
    background-color:#101114;
    border:1px solid #26292d;
    border-radius:10px;
    font-family:"Segoe UI";
}

QLabel{
    color:#ffffff;
}

QPushButton{
    background-color:#1c1f24;
    border:1px solid #2c3137;
    border-radius:10px;
    padding:12px;
    font-size:15px;
    font-weight:600;
    color:white;
}

QPushButton:hover{
    background-color:#252a31;
    border:1px solid #3c434c;
}

QPushButton:pressed{
    background-color:#15181c;
}
""")

window.setObjectName("MainPanel")

def mousePressEvent(event):

    global drag_pos

    drag_pos = event.globalPosition().toPoint()

window.mousePressEvent = mousePressEvent

def mouseMoveEvent(event):

    global drag_pos

    if event.buttons() & Qt.LeftButton:

        window.move(
            window.pos() +
            event.globalPosition().toPoint()
            - drag_pos
        )

        drag_pos = (
            event.globalPosition().toPoint()
        )

window.mouseMoveEvent = mouseMoveEvent

layout = QVBoxLayout()

layout.setContentsMargins(30,30,30,30)
layout.setSpacing(10)

title = QLabel("ChessMate")
title.setAlignment(Qt.AlignCenter)

title.setStyleSheet("""
color:white;
font-size:34px;
font-weight:800;
letter-spacing:1px;
""")

best_move_label = QLabel("Best Move: --")
best_move_label.setAlignment(Qt.AlignCenter)

eval_label = QLabel("Evaluation: --")
eval_label.setAlignment(Qt.AlignCenter)

best_move_label.setStyleSheet("""
font-size:20px;
font-weight:700;
color:#ffffff;
""")

eval_label.setStyleSheet("""
font-size:18px;
font-weight:600;
color:#67e480;
""")

status = QLabel("Starting...")
status.setAlignment(Qt.AlignCenter)

status.setStyleSheet("""
font-size:14px;
color:#8f98a3;
font-weight:500;
""")

coach_btn = QPushButton("Coach Mode")
win_btn = QPushButton("Win Mode")
start_game_btn = QPushButton("Start Game")
white_btn = QPushButton("Play White")
black_btn = QPushButton("Play Black")
move_input = QLineEdit()
move_input.setPlaceholderText(
    "Enter your move"
)

submit_move_btn = QPushButton(
    "Submit Move"
)

start_game_btn.hide()
white_btn.hide()
black_btn.hide()
coach_btn.hide()
win_btn.hide()
move_input.hide()
submit_move_btn.hide()

layout.addWidget(title)
layout.addWidget(status)
layout.addSpacing(10)
layout.addWidget(coach_btn)
layout.addWidget(win_btn)
layout.addWidget(start_game_btn)
layout.addWidget(white_btn)
layout.addWidget(black_btn)
layout.addWidget(best_move_label)
layout.addWidget(eval_label)
layout.addWidget(move_input)
layout.addWidget(submit_move_btn)

best_move_label.hide()
eval_label.hide()

panel.setLayout(layout)
refresh_window_size()

app.processEvents()

window.hide()

title.setText("ChessMate")

app.processEvents()

start_game_btn.clicked.connect(
    start_game_clicked
)

white_btn.clicked.connect(
    white_clicked
)

black_btn.clicked.connect(
    black_clicked
)

def submit_player_move():

    move_text = (
        move_input.text()
        .strip()
    )

    if not move_text:
        return

    bus.player_move_submitted.emit(
        move_text
    )

    move_input.clear()

submit_move_btn.clicked.connect(
    submit_player_move
)

class CoachModeThread(QThread):

    update_signal = Signal(object, object, object)

    def __init__(self):
        super().__init__()
        self.running = True

    def stop(self):
        self.running = False

    def run(self):

        from coach_mode import start_coach_mode

        start_coach_mode(
            model,
            engine,
            ui_callback=self.emit_update,
            bus=bus,
            is_running=lambda: self.running
        )

    def emit_update(
        self,
        move=None,
        evaluation=None,
        status_text=None
    ):
        self.update_signal.emit(
            move,
            evaluation,
            status_text
        )

def launch_coach():

    coach_btn.hide()
    win_btn.hide()

    best_move_label.show()
    eval_label.show()

    start_game_btn.show()
    move_input.show()
    submit_move_btn.show()

    refresh_window_size()

    status.setText(
        "Coach Mode"
    )

    global coach_thread

    coach_thread = CoachModeThread()

    coach_thread.update_signal.connect(
        ui_update
    )

    coach_thread.start()

class WinModeThread(QThread):

    update_signal = Signal(
        object,
        object,
        object
    )

    def __init__(self):
        super().__init__()
        self.running = True

    def stop(self):
        self.running = False
    
    def run(self):

        from win_mode import start_win_mode
        from board_system.board_tracker import BoardTracker

        self.tracker = BoardTracker(
            model
        )

        start_win_mode(
            self.tracker,
            engine,
            self.emit_update,
            bus,
            lambda: self.running
        )

    def emit_update(
        self,
        move=None,
        evaluation=None,
        status_text=None
    ):

        self.update_signal.emit(
            move,
            evaluation,
            status_text
        )

def launch_win():

    best_move_label.show()
    eval_label.show()

    coach_btn.hide()
    win_btn.hide()

    start_game_btn.show()
    white_btn.hide()
    black_btn.hide()
    
    status.setText("Win Mode")
    
    global win_thread

    win_thread = WinModeThread()

    win_thread.update_signal.connect(
        ui_update
    )
    
    win_thread.start()

coach_btn.clicked.connect(
    launch_coach
)

win_btn.clicked.connect(
    launch_win
 )

profile = load_profile()

if not profile["name"]:

    from onboarding import OnboardingWindow

    show_onboarding()

else:

    show_home_page()

app.exec()
