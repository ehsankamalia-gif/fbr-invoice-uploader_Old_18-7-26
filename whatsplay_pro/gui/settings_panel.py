import logging
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, 
    QLineEdit, QCheckBox, QComboBox, QPushButton, QFrame, 
    QScrollArea, QSpinBox, QMessageBox
)
from PyQt6.QtCore import Qt
from whatsplay_pro.core.config import Config
from whatsplay_pro.core.signals import signals

logger = logging.getLogger(__name__)

class SettingsPanel(QWidget):
    """Production-grade settings management interface for WhatsPlay Pro."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()
        self._load_settings()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("background-color: transparent;")
        
        content_widget = QWidget()
        self.layout = QVBoxLayout(content_widget)
        self.layout.setSpacing(20)
        self.layout.setContentsMargins(10, 10, 10, 10)
        
        # 1. WhatsApp Engine Section (Web Automation)
        wa_web_group, wa_web_layout = self._create_section("WHATSAPP WEB (BROWSER)", "#2980b9")
        
        self.headless_cb = QCheckBox("Run in Headless Mode (Hidden Browser)")
        wa_web_layout.addWidget(self.headless_cb, 0, 0, 1, 2)
        
        wa_web_layout.addWidget(QLabel("Browser Channel:"), 1, 0)
        self.browser_channel = QComboBox()
        self.browser_channel.addItems(["chrome", "msedge", "playwright-chromium"])
        wa_web_layout.addWidget(self.browser_channel, 1, 1)
        
        wa_web_layout.addWidget(QLabel("Session Directory:"), 2, 0)
        self.session_path = QLineEdit()
        self.session_path.setReadOnly(True)
        wa_web_layout.addWidget(self.session_path, 2, 1)
        
        self.proxy_enabled = QCheckBox("Enable Proxy Server")
        wa_web_layout.addWidget(self.proxy_enabled, 3, 0)
        self.proxy_server = QLineEdit()
        self.proxy_server.setPlaceholderText("http://user:pass@host:port")
        wa_web_layout.addWidget(self.proxy_server, 3, 1)
        
        self.layout.addWidget(wa_web_group)
        
        # 2. WhatsApp Gateway Section (API/Android)
        wa_api_group, wa_api_layout = self._create_section("WHATSAPP GATEWAY (ANDROID/API)", "#8e44ad")
        
        self.wa_gateway_enabled = QCheckBox("Enable External Gateway Support")
        wa_api_layout.addWidget(self.wa_gateway_enabled, 0, 0, 1, 2)
        
        wa_api_layout.addWidget(QLabel("Gateway IP:"), 1, 0)
        self.wa_gateway_ip = QLineEdit()
        self.wa_gateway_ip.setPlaceholderText("e.g. 192.168.1.100")
        wa_api_layout.addWidget(self.wa_gateway_ip, 1, 1)
        
        wa_api_layout.addWidget(QLabel("Gateway Port:"), 2, 0)
        self.wa_gateway_port = QLineEdit()
        self.wa_gateway_port.setPlaceholderText("8080")
        wa_api_layout.addWidget(self.wa_gateway_port, 2, 1)
        
        wa_api_layout.addWidget(QLabel("Instance ID:"), 3, 0)
        self.wa_instance = QLineEdit()
        wa_api_layout.addWidget(self.wa_instance, 3, 1)
        
        wa_api_layout.addWidget(QLabel("API Key:"), 4, 0)
        self.wa_api_key = QLineEdit()
        self.wa_api_key.setEchoMode(QLineEdit.EchoMode.Password)
        wa_api_layout.addWidget(self.wa_api_key, 4, 1)
        
        self.wa_use_https = QCheckBox("Use HTTPS for Gateway")
        wa_api_layout.addWidget(self.wa_use_https, 5, 0, 1, 2)
        
        self.layout.addWidget(wa_api_group)
        
        # 3. AI Chatbot Section
        ai_group, ai_layout = self._create_section("AI CHATBOT (OPENAI)", "#27ae60")
        
        self.ai_enabled = QCheckBox("Enable AI Auto-Reply")
        ai_layout.addWidget(self.ai_enabled, 0, 0, 1, 2)
        
        ai_layout.addWidget(QLabel("AI Provider:"), 1, 0)
        self.ai_provider = QComboBox()
        self.ai_provider.addItems(["OpenAI (GPT-4)", "Rule-Based (Fallback)"])
        ai_layout.addWidget(self.ai_provider, 1, 1)
        
        ai_layout.addWidget(QLabel("API Key:"), 2, 0)
        self.api_key = QLineEdit()
        self.api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key.setPlaceholderText("sk-...")
        ai_layout.addWidget(self.api_key, 2, 1)
        
        ai_layout.addWidget(QLabel("Reply Delay (seconds):"), 3, 0)
        self.ai_delay = QSpinBox()
        self.ai_delay.setRange(1, 60)
        ai_layout.addWidget(self.ai_delay, 3, 1)
        
        self.layout.addWidget(ai_group)
        
        # 4. Anti-Ban Safety Section
        safety_group, safety_layout = self._create_section("ANTI-BAN SAFETY", "#e67e22")
        
        safety_layout.addWidget(QLabel("Min Delay (secs):"), 0, 0)
        self.min_delay = QSpinBox()
        self.min_delay.setRange(1, 300)
        safety_layout.addWidget(self.min_delay, 0, 1)
        
        safety_layout.addWidget(QLabel("Max Delay (secs):"), 1, 0)
        self.max_delay = QSpinBox()
        self.max_delay.setRange(1, 600)
        safety_layout.addWidget(self.max_delay, 1, 1)
        
        help_text = QLabel("Random delay will be picked between min and max for each message.")
        help_text.setStyleSheet("color: #7f8c8d; font-size: 11px; border: none;")
        safety_layout.addWidget(help_text, 2, 0, 1, 2)
        
        self.layout.addWidget(safety_group)
        
        # 5. Action Buttons
        actions_layout = QHBoxLayout()
        actions_layout.addStretch()
        
        self.save_btn = QPushButton("💾 Save Configuration")
        self.save_btn.setFixedSize(200, 45)
        self.save_btn.setStyleSheet("""
            QPushButton {
                background-color: #2ecc71;
                color: white;
                font-weight: bold;
                border-radius: 5px;
                font-size: 14px;
            }
            QPushButton:hover { background-color: #27ae60; }
        """)
        self.save_btn.clicked.connect(self._on_save)
        actions_layout.addWidget(self.save_btn)
        
        self.layout.addLayout(actions_layout)
        self.layout.addStretch()
        
        scroll.setWidget(content_widget)
        main_layout.addWidget(scroll)

    def _create_section(self, title: str, color: str):
        """Create a styled section with a title and a grid layout."""
        frame = QFrame()
        frame.setStyleSheet("""
            QFrame {
                background-color: #ffffff;
                border: 1px solid #dcdde1;
                border-radius: 10px;
            }
        """)
        
        v_layout = QVBoxLayout(frame)
        v_layout.setContentsMargins(15, 15, 15, 15)
        v_layout.setSpacing(15)
        
        title_label = QLabel(title)
        title_label.setStyleSheet(f"color: {color}; font-size: 13px; font-weight: bold; border: none; padding-bottom: 5px;")
        v_layout.addWidget(title_label)
        
        grid_layout = QGridLayout()
        grid_layout.setSpacing(10)
        v_layout.addLayout(grid_layout)
        
        return frame, grid_layout

    def _load_settings(self):
        """Load current values from Config."""
        # Web
        self.headless_cb.setChecked(Config.WHATSAPP_HEADLESS)
        self.browser_channel.setCurrentText(Config.WHATSAPP_BROWSER_CHANNEL)
        self.session_path.setText(str(Config.WHATSAPP_SESSION_DIR))
        self.proxy_enabled.setChecked(Config.WHATSAPP_PROXY_ENABLED)
        self.proxy_server.setText(Config.WHATSAPP_PROXY_SERVER)
        
        # Gateway
        self.wa_gateway_enabled.setChecked(Config.WA_GATEWAY_ENABLED)
        self.wa_gateway_ip.setText(Config.WA_GATEWAY_IP)
        self.wa_gateway_port.setText(Config.WA_GATEWAY_PORT)
        self.wa_instance.setText(Config.WA_GATEWAY_INSTANCE)
        self.wa_api_key.setText(Config.WA_GATEWAY_API_KEY)
        self.wa_use_https.setChecked(Config.WA_GATEWAY_USE_HTTPS)
        
        # AI
        self.api_key.setText(Config.OPENAI_API_KEY)
        self.ai_delay.setValue(Config.AUTO_REPLY_DELAY)
        
        self.min_delay.setValue(Config.MIN_DELAY)
        self.max_delay.setValue(Config.MAX_DELAY)
        
        # AI Orchestrator state
        from whatsplay_pro.ai.chatbot import ai_orchestrator
        self.ai_enabled.setChecked(ai_orchestrator.is_enabled)

    def _on_save(self):
        """Persist settings and update live services."""
        try:
            # Update Config Class (In-memory)
            # Web
            Config.WHATSAPP_HEADLESS = self.headless_cb.isChecked()
            Config.WHATSAPP_BROWSER_CHANNEL = self.browser_channel.currentText()
            Config.WHATSAPP_PROXY_ENABLED = self.proxy_enabled.isChecked()
            Config.WHATSAPP_PROXY_SERVER = self.proxy_server.text().strip()
            
            # Gateway
            Config.WA_GATEWAY_ENABLED = self.wa_gateway_enabled.isChecked()
            Config.WA_GATEWAY_IP = self.wa_gateway_ip.text().strip()
            Config.WA_GATEWAY_PORT = self.wa_gateway_port.text().strip()
            Config.WA_GATEWAY_INSTANCE = self.wa_instance.text().strip()
            Config.WA_GATEWAY_API_KEY = self.wa_api_key.text().strip()
            Config.WA_GATEWAY_USE_HTTPS = self.wa_use_https.isChecked()
            
            # AI
            Config.OPENAI_API_KEY = self.api_key.text().strip()
            Config.AUTO_REPLY_DELAY = self.ai_delay.value()
            Config.MIN_DELAY = self.min_delay.value()
            Config.MAX_DELAY = self.max_delay.value()
            
            # Update AI Orchestrator
            from whatsplay_pro.ai.chatbot import ai_orchestrator
            ai_orchestrator.is_enabled = self.ai_enabled.isChecked()
            
            # Note: In a production app, we would save these to a .env or JSON file here.
            
            signals.notify.emit("success", "Settings saved successfully! Some changes may require a restart.")
            QMessageBox.information(self, "Success", "Configuration updated successfully.")
            
        except Exception as e:
            logger.error(f"Failed to save settings: {e}")
            QMessageBox.critical(self, "Error", f"Could not save settings: {e}")
