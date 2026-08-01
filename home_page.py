from PySide6.QtWidgets import (
    QWidget,
    QLabel,
    QVBoxLayout,
    QHBoxLayout,
    QFrame,
    QPushButton,
    QInputDialog
)

from PySide6.QtCore import Qt, Signal

from player_profile.profile_manager import (
    load_profile,
    save_profile
)

class HomePage(QWidget):

    profile_requested = Signal()
    start_requested = Signal()
    analysis_requested = Signal()
    review_requested = Signal()

    def __init__(self):
        super().__init__()

        self.profile = load_profile()

        self.setup_ui()

    def setup_ui(self):

        self.resize(
            1200,
            800
        )

        self.setWindowTitle(
            "ChessMate"
        )

        self.setStyleSheet("""
        QWidget{
            background-color:#0b0d10;
            color:white;
            font-family:"Segoe UI";
        }

        QFrame#Card{
            background-color:#14181e;
            border:2px solid #232933;
            border-radius:24px;
        }

        QFrame#Card:hover{
            border:2px solid #3b82f6;
        }

        QLabel{
            color:white;
            font-size:15px;
            background:transparent;
        }

        QPushButton{
            background-color:#2563eb;
            border:none;
            border-radius:16px;
            padding:16px;
            min-height:22px;
            font-size:15px;
            font-weight:800;
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
            50,
            35,
            50,
            35
        )

        root.setSpacing(30)

        title = QLabel(
            "ChessMate"
        )

        title.setAlignment(
            Qt.AlignCenter
        )

        title.setStyleSheet("""
        font-size:42px;
        font-weight:900;
        letter-spacing:2px;
        """)

        greeting = QLabel(
            f"Welcome back, {self.profile['name']}"
        )

        greeting.setAlignment(
            Qt.AlignCenter
        )

        greeting.setStyleSheet("""
        font-size:20px;
        font-weight:600;
        color:#9ca3af;
        """)

        root.addWidget(title)
        root.addWidget(greeting)

        cards_layout = QHBoxLayout()
        cards_layout.setSpacing(25)

        cards_layout.setContentsMargins(
            0,
            20,
            0,
            0
        )
        
        cards_layout.addWidget(
            self.create_profile_card()
        )

        cards_layout.addWidget(
            self.create_start_card()
        )

        cards_layout.addWidget(
            self.create_analysis_card()
        )

        cards_layout.addWidget(
            self.create_review_card()
        )

        wrapper = QHBoxLayout()

        wrapper.addStretch()

        wrapper.addLayout(cards_layout)

        wrapper.addStretch()

        root.addLayout(wrapper)

        self.setLayout(root)

    def connect_chesscom(self):

        profile = load_profile()

        username = profile.get("chesscom_username", "").strip()

        # CASE 1: already exists → no prompt
        if username:
            self.analysis_requested.emit()
            return

        # CASE 2: ask only if missing
        username, ok = QInputDialog.getText(
            self,
            "Chess.com Username",
            "Enter your Chess.com username:"
        )

        if not ok or not username.strip():
            return

        profile["chesscom_username"] = username.strip()

        save_profile(profile)

        self.analysis_requested.emit()

    def create_profile_card(self):

        card = QFrame()
        card.setObjectName("Card")

        card.setMinimumWidth(260)
        card.setMinimumHeight(420)

        layout = QVBoxLayout(card)

        layout.setContentsMargins(
            25,
            25,
            25,
            25
        )

        layout.setSpacing(12)

        title = QLabel("Player Profile")

        title.setStyleSheet("""
        font-size:20px;
        font-weight:600;
        color:#9ca3af;
        """)

        rating = QLabel(
            f"Rating: {self.profile['rating']}"
        )

        personality = QLabel(
            f"Style: {self.profile['personality_name']}"
        )

        confidence = QLabel(
            f"Confidence: {self.profile['confidence']}%"
        )

        button = QPushButton(
            "Open Profile"
        )

        button.clicked.connect(
            self.profile_requested.emit
        )

        layout.addWidget(title)
        layout.addSpacing(10)
        layout.addWidget(rating)
        layout.addWidget(personality)
        layout.addWidget(confidence)
        layout.addStretch()
        layout.addWidget(button)

        return card

    def create_start_card(self):

        card = QFrame()
        card.setObjectName("Card")

        card.setMinimumWidth(260)
        card.setMinimumHeight(420)

        layout = QVBoxLayout(card)

        layout.setContentsMargins(
            25,
            25,
            25,
            25
        )

        layout.setSpacing(12)

        title = QLabel("Start ChessMate")

        title.setStyleSheet("""
        font-size:20px;
        font-weight:600;
        color:#9ca3af;
        """)

        description = QLabel(
            "Launch live board detection and real-time coaching."
        )

        description.setWordWrap(True)

        button = QPushButton(
            "Start"
        )

        button.clicked.connect(
            self.start_requested.emit
        )

        layout.addWidget(title)
        layout.addSpacing(10)
        layout.addWidget(description)
        layout.addStretch()
        layout.addWidget(button)

        return card

    def create_analysis_card(self):

        card = QFrame()
        card.setObjectName("Card")

        card.setMinimumWidth(260)
        card.setMinimumHeight(420)

        layout = QVBoxLayout(card)

        layout.setContentsMargins(
            25,
            25,
            25,
            25
        )

        layout.setSpacing(12)

        title = QLabel("Connect Chess.com")

        title.setStyleSheet("""
        font-size:20px;
        font-weight:600;
        color:#9ca3af;
        """)

        description = QLabel(
            "Import your latest Chess.com games and let ChessMate learn your style."
        )

        description.setWordWrap(True)

        button = QPushButton(
            "Connect"
        )

        button.clicked.connect(
            self.connect_chesscom
        )

        layout.addWidget(title)
        layout.addSpacing(10)
        layout.addWidget(description)
        layout.addStretch()
        layout.addWidget(button)

        return card

    def create_review_card(self):

        card = QFrame()
        card.setObjectName("Card")

        card.setMinimumWidth(260)
        card.setMinimumHeight(420)

        layout = QVBoxLayout(card)

        layout.setContentsMargins(
            25,
            25,
            25,
            25
        )

        layout.setSpacing(12)

        title = QLabel("Review Games")

        title.setStyleSheet("""
        font-size:20px;
        font-weight:600;
        color:#9ca3af;
        """)

        description = QLabel(
            "Get personalized ChessMate coaching instead of generic engine comments."
        )

        description.setWordWrap(True)

        button = QPushButton(
            "Review"
        )

        button.clicked.connect(
            self.review_requested.emit
        )

        layout.addWidget(title)
        layout.addSpacing(10)
        layout.addWidget(description)
        layout.addStretch()
        layout.addWidget(button)

        return card
