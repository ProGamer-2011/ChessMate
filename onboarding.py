from PySide6.QtWidgets import (
    QWidget,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QLineEdit,
    QStackedWidget,
    QHBoxLayout,
    QComboBox,
    QFrame
)

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices

from player_profile.profile_manager import (
    load_profile,
    save_profile
)


PERSONALITY_PRESETS = {
    "Wildcard": {
        "intuition": 82,
        "calculation": 48,
        "attacking": 74,
        "positional": 54,
        "calm": 38,
        "emotional": 66,
        "playful": 84,
        "studious": 42
    },
    "Anaconda": {
        "intuition": 58,
        "calculation": 66,
        "attacking": 46,
        "positional": 84,
        "calm": 78,
        "emotional": 22,
        "playful": 30,
        "studious": 76
    },
    "Artist": {
        "intuition": 88,
        "calculation": 54,
        "attacking": 72,
        "positional": 44,
        "calm": 42,
        "emotional": 58,
        "playful": 90,
        "studious": 48
    },
    "Assassin": {
        "intuition": 60,
        "calculation": 88,
        "attacking": 86,
        "positional": 58,
        "calm": 82,
        "emotional": 18,
        "playful": 28,
        "studious": 82
    },
    "Caveman": {
        "intuition": 66,
        "calculation": 38,
        "attacking": 92,
        "positional": 22,
        "calm": 24,
        "emotional": 76,
        "playful": 40,
        "studious": 18
    },
    "Grappler": {
        "intuition": 52,
        "calculation": 62,
        "attacking": 42,
        "positional": 88,
        "calm": 74,
        "emotional": 26,
        "playful": 36,
        "studious": 80
    },
    "Inventor": {
        "intuition": 86,
        "calculation": 66,
        "attacking": 68,
        "positional": 56,
        "calm": 44,
        "emotional": 56,
        "playful": 86,
        "studious": 58
    },
    "Jester": {
        "intuition": 78,
        "calculation": 44,
        "attacking": 60,
        "positional": 46,
        "calm": 34,
        "emotional": 66,
        "playful": 94,
        "studious": 34
    },
    "Machine": {
        "intuition": 40,
        "calculation": 92,
        "attacking": 78,
        "positional": 68,
        "calm": 84,
        "emotional": 16,
        "playful": 18,
        "studious": 90
    },
    "Mad Scientist": {
        "intuition": 80,
        "calculation": 60,
        "attacking": 78,
        "positional": 40,
        "calm": 28,
        "emotional": 72,
        "playful": 86,
        "studious": 52
    },
    "Magician": {
        "intuition": 84,
        "calculation": 58,
        "attacking": 88,
        "positional": 34,
        "calm": 30,
        "emotional": 70,
        "playful": 88,
        "studious": 46
    },
    "Mastermind": {
        "intuition": 48,
        "calculation": 90,
        "attacking": 52,
        "positional": 82,
        "calm": 76,
        "emotional": 24,
        "playful": 22,
        "studious": 92
    },
    "Professor": {
        "intuition": 42,
        "calculation": 84,
        "attacking": 34,
        "positional": 90,
        "calm": 78,
        "emotional": 22,
        "playful": 26,
        "studious": 94
    },
    "Romantic": {
        "intuition": 90,
        "calculation": 52,
        "attacking": 86,
        "positional": 30,
        "calm": 26,
        "emotional": 74,
        "playful": 84,
        "studious": 36
    },
    "Technician": {
        "intuition": 50,
        "calculation": 94,
        "attacking": 62,
        "positional": 88,
        "calm": 82,
        "emotional": 18,
        "playful": 20,
        "studious": 88
    }
}


class OnboardingWindow(QWidget):

    finished = Signal()

    def __init__(self):
        super().__init__()

        self.profile = load_profile()
        self.current_rating = None
        self.current_personality = None

        self.setup_ui()

    def setup_ui(self):

        self.setWindowTitle("ChessMate")
        self.resize(1100, 700)

        self.setStyleSheet("""
        QWidget{
            background-color:#0d1117;
            color:white;
            font-family:"Segoe UI";
        }

        QLabel{
            color:white;
            background:transparent;
        }

        QLineEdit,QComboBox{
            background-color:#161b22;
            border:2px solid #30363d;
            border-radius:14px;
            padding:14px;
            font-size:18px;
            color:white;
        }

        QLineEdit:focus,
        QComboBox:focus{
            border:2px solid #3b82f6;
        }

        QPushButton{
            background-color:#2563eb;
            border:none;
            border-radius:14px;
            padding:16px;
            font-size:17px;
            font-weight:700;
            color:white;
        }

        QPushButton:hover{
            background-color:#3b82f6;
        }

        QPushButton:pressed{
            background-color:#1d4ed8;
        }
        """)

        root = QVBoxLayout()

        root.setContentsMargins(
            80,
            40,
            80,
            40
        )

        root.setSpacing(20)

        header_layout = QHBoxLayout()

        self.progress_label = QLabel(
            "Step 1 of 3"
        )

        self.progress_label.setStyleSheet("""
        font-size:15px;
        font-weight:600;
        color:#8b949e;
        """)

        logo = QLabel(
            "Welcome To ChessMate"
        )

        logo.setAlignment(
            Qt.AlignCenter
        )

        logo.setStyleSheet("""
        font-size:28px;
        font-weight:900;
        """)

        header_layout.addWidget(
            self.progress_label
        )

        header_layout.addStretch()

        header_layout.addWidget(
            logo
        )

        header_layout.addStretch()

        header_layout.addSpacing(80)

        self.pages = QStackedWidget()

        self.pages.addWidget(
            self.build_name_page()
        )

        self.pages.addWidget(
            self.build_rating_page()
        )

        self.pages.addWidget(
            self.build_personality_page()
        )

        root.addLayout(
            header_layout
        )

        root.addWidget(
            self.pages
        )

        self.setLayout(root)

    def build_card(self):
        card = QFrame()
        card.setObjectName("Card")
        return card

    def build_name_page(self):
        page = self.build_card()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(70, 60, 70, 60)
        layout.setSpacing(22)

        layout.addStretch()

        subtitle = QLabel("What should we call you?")
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setStyleSheet("font-size:22px; color:#8b949e;")

        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Enter your name")

        next_btn = QPushButton("Continue")
        next_btn.clicked.connect(self.go_to_rating_page)

        layout.addWidget(subtitle)
        layout.addSpacing(10)
        layout.addWidget(self.name_input)
        layout.addWidget(next_btn)

        layout.addStretch()
        return page

    def build_rating_page(self):
        page = self.build_card()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(70, 60, 70, 60)
        layout.setSpacing(18)

        layout.addStretch()

        title = QLabel("What's your current Elo rating?")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size:38px; font-weight:900;")

        subtitle = QLabel("We'll use this to personalize coaching.")
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setStyleSheet("font-size:18px; color:#a5acb8;")

        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addSpacing(8)

        options = [
            ("Beginner (<800)", 600),
            ("Intermediate (800-1400)", 1100),
            ("Advanced (1400-1800)", 1600),
            ("Expert (1800+)", 2000),
            ("Unsure", 1000)
        ]

        for label, value in options:
            btn = QPushButton(label)
            btn.clicked.connect(lambda checked=False, r=value: self.select_rating(r))
            layout.addWidget(btn)

        layout.addStretch()
        return page

    def build_personality_page(self):
        page = self.build_card()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(70, 60, 70, 60)
        layout.setSpacing(18)

        layout.addStretch()

        title = QLabel("Chess Personality")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size:38px; font-weight:900;")

        subtitle = QLabel("Take the Chess Personality quiz or select your result.")
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setStyleSheet("font-size:18px; color:#a5acb8;")

        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addSpacing(8)

        open_site_btn = QPushButton("Open Chess Personality Quiz")
        open_site_btn.clicked.connect(self.open_personality_site)
        layout.addWidget(open_site_btn)

        self.personality_combo = QComboBox()
        self.personality_combo.addItem("Select your result...", "")

        for name in PERSONALITY_PRESETS.keys():
            self.personality_combo.addItem(name, name)

        layout.addWidget(self.personality_combo)

        finish_btn = QPushButton("Finish Setup")
        finish_btn.clicked.connect(self.finish_onboarding)
        layout.addWidget(finish_btn)

        layout.addStretch()
        return page

    def go_to_rating_page(self):

        name = self.name_input.text().strip()

        if not name:
            return

        self.profile["name"] = name

        self.progress_label.setText(
            "Step 2 of 3"
        )

        self.pages.setCurrentIndex(1)

    def select_rating(self, rating):

        self.current_rating = rating

        self.progress_label.setText(
            "Step 3 of 3"
        )

        self.pages.setCurrentIndex(2)

    def open_personality_site(self):
        QDesktopServices.openUrl(QUrl("https://www.chesspersonality.com/quiz"))

    def finish_onboarding(self):
        personality_name = self.personality_combo.currentData()
        if not personality_name:
            personality_name = "Wildcard"

        preset = PERSONALITY_PRESETS.get(personality_name, PERSONALITY_PRESETS["Wildcard"])

        self.profile["rating"] = self.current_rating if self.current_rating is not None else 1000
        self.profile["personality_name"] = personality_name
        self.profile["style_name"] = personality_name

        self.profile.update(preset)
        self.profile["confidence"] = 20

        save_profile(self.profile)

        self.finished.emit()

        self.close()
