import os
import sys
import json
import random
import time
import threading
import hashlib
import base64
import subprocess
import urllib.parse
from datetime import datetime
from pathlib import Path
from bs4 import BeautifulSoup

from PyQt6.QtCore import (
    Qt, QUrl, QThread, pyqtSignal, QTimer, QPropertyAnimation,
    QEasingCurve, QPoint, QRect, QEventLoop
)
from PyQt6.QtGui import QAction, QFont, QIcon, QColor, QPalette, QBrush, QRadialGradient, QPainter, QPen
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLineEdit, QStatusBar, QTabWidget, QMenu, QTextEdit,
    QLabel, QSpinBox, QMessageBox, QComboBox, QRadioButton, QDialog,
    QSlider, QCheckBox, QInputDialog, QFileDialog, QGroupBox
)
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import (
    QWebEngineProfile, QWebEngineScript, QWebEngineSettings,
    QWebEnginePage, QWebEngineUrlRequestInterceptor, QWebEngineUrlRequestInfo
)
from PyQt6.QtNetwork import QNetworkProxy, QNetworkAccessManager, QNetworkRequest, QNetworkReply

# Отключаем глобальный прокси
QNetworkProxy.setApplicationProxy(QNetworkProxy(QNetworkProxy.ProxyType.NoProxy))

# Flask + зависимости
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from deep_translator import GoogleTranslator
from ddgs import DDGS

# ---------- Шифрование паролей ---------
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend
from cryptography.fernet import Fernet
import base64

# ---------- Импорт для Safe Browsing ----------
import json as jsonlib

# ---------- Попытка импорта torch и transformers ----------
try:
    import torch
    import torch.nn as nn
    from torch.nn import functional as F
    from tokenizers import Tokenizer
    from transformers import GPT2Config, GPT2LMHeadModel, AutoTokenizer
    TORCH_AVAILABLE = True
    TRANSFORMERS_AVAILABLE = True
except ImportError as e:
    TORCH_AVAILABLE = False
    TRANSFORMERS_AVAILABLE = False
    print(f"[WARN] Не удалось импортировать PyTorch или transformers: {e}")

# ---------- resource_path ----------
def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

# ---------- ПУТИ ----------
if getattr(sys, 'frozen', False):
    CURRENT_DIR = os.path.dirname(sys.executable)
else:
    CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))

LOAD_DIR = os.path.join(CURRENT_DIR, "load")
os.makedirs(LOAD_DIR, exist_ok=True)

AI_DIR = os.path.join(CURRENT_DIR, "AI")
os.makedirs(AI_DIR, exist_ok=True)

GPT2_TOKENIZER_DIR = os.path.join(AI_DIR, "tokenizer")
GPT2_MODEL_PATH = os.path.join(AI_DIR, "micro_gpt_170m.bin")
NANOGPT_MODEL_PATH = os.path.join(AI_DIR, "micro_gpt_170m.bin")
NANOGPT_TOKENIZER_PATH = os.path.join(AI_DIR, "tokenizer")

# ---------- ПАПКА ДАННЫХ В AppData ----------
def get_data_dir():
    if sys.platform == 'win32':
        appdata = os.environ.get('APPDATA', os.path.expanduser('~'))
        data_dir = os.path.join(appdata, 'FreeSearch')
    else:
        config_home = os.environ.get('XDG_CONFIG_HOME', os.path.expanduser('~/.config'))
        data_dir = os.path.join(config_home, 'FreeSearch')
    os.makedirs(data_dir, exist_ok=True)
    return data_dir

DATA_DIR = get_data_dir()
SAVE_DIR = os.path.join(DATA_DIR, "save")
os.makedirs(SAVE_DIR, exist_ok=True)

SETTINGS_FILE = os.path.join(SAVE_DIR, "settings.json")
PASSWORD_FILE = os.path.join(SAVE_DIR, "passwords.json")
BACKGROUNDS_FILE = os.path.join(SAVE_DIR, "backgrounds.json")
WIDGETS_FILE = os.path.join(SAVE_DIR, "widgets.json")
TABS_FILE = os.path.join(SAVE_DIR, "tabs.json")
PROFILE_DIR = os.path.join(SAVE_DIR, "profiles")
os.makedirs(PROFILE_DIR, exist_ok=True)

# ---------- Статические файлы ----------
STATIC_DIR = resource_path('.')
PORT = 5000
HOME_URL = f"http://127.0.0.1:{PORT}/index.html"
PROFILE_URL = f"http://127.0.0.1:{PORT}/profile.html"

# ---------- НАСТРОЙКИ ----------
DEFAULT_SETTINGS = {"theme": "dark", "language": "ru"}

def load_settings():
    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, 'r') as f:
            return json.load(f)
    return DEFAULT_SETTINGS.copy()

def save_settings(settings):
    with open(SETTINGS_FILE, 'w') as f:
        json.dump(settings, f, indent=2)

# ================================================================
#  БЛОКИРОВЩИК РЕКЛАМЫ (на основе EasyList)
# ================================================================
class AdBlockInterceptor(QWebEngineUrlRequestInterceptor):
    def __init__(self, blocked_domains=None):
        super().__init__()
        self.blocked_domains = blocked_domains or set()
        self.load_easylist()

    def load_easylist(self):
        try:
            import requests
            url = "https://easylist.to/easylist/easylist.txt"
            resp = requests.get(url, timeout=15)
            if resp.status_code == 200:
                for line in resp.text.splitlines():
                    line = line.strip()
                    if line and not line.startswith('!'):
                        if line.startswith('||') and '^' in line:
                            domain = line[2:line.index('^')]
                            self.blocked_domains.add(domain)
                print(f"[ADBLOCK] Загружено {len(self.blocked_domains)} доменов из EasyList")
            else:
                print("[ADBLOCK] Не удалось загрузить EasyList, использую встроенный список")
                fallback = [
                    "doubleclick.net", "googleadservices.com", "googlesyndication.com",
                    "facebook.com/tr", "amazon-adsystem.com", "adnxs.com", "adsrvr.org",
                    "rubiconproject.com", "pubmatic.com", "openx.net", "criteo.com",
                    "taboola.com", "outbrain.com", "adform.net", "indexexchange.com"
                ]
                self.blocked_domains.update(fallback)
        except Exception as e:
            print(f"[ADBLOCK] Ошибка загрузки EasyList: {e}")

    def interceptRequest(self, info):
        url = info.requestUrl().toString()
        for domain in self.blocked_domains:
            if domain in url:
                info.block(True)
                return

# ================================================================
#  КЛАСС ДЛЯ GOOGLE SAFE BROWSING (Lookup API) С QNetworkAccessManager И КЕШЕМ
# ================================================================
class SafeBrowsingChecker:
    def __init__(self, api_key, parent=None):
        self.api_key = api_key
        self.api_url = "https://safebrowsing.googleapis.com/v4/threatMatches:find"
        self.enabled = self.api_key and self.api_key != "Секретный ключь я вам не покажу"
        self.nam = QNetworkAccessManager(parent)
        self.cache = {}  # {domain: (is_safe, threat_type, timestamp)}
        self.cache_ttl = 3600  # 1 час

    def check_url_sync(self, url):
        if not self.enabled:
            return True, None
        if url.startswith(("http://127.0.0.1:5000", "about:blank", "file://")):
            return True, None

        try:
            parsed = urllib.parse.urlparse(url)
            domain = parsed.netloc or parsed.path
            if not domain:
                return True, None
        except Exception:
            return True, None

        now = time.time()
        if domain in self.cache:
            is_safe, threat_type, timestamp = self.cache[domain]
            if now - timestamp < self.cache_ttl:
                return is_safe, threat_type
            else:
                del self.cache[domain]

        is_safe, threat_type = self._send_request(url)
        self.cache[domain] = (is_safe, threat_type, now)
        return is_safe, threat_type

    def _send_request(self, url):
        payload = {
            "client": {"clientId": "FreeSearch", "clientVersion": "1.16"},
            "threatInfo": {
                "threatTypes": ["MALWARE", "SOCIAL_ENGINEERING", "UNWANTED_SOFTWARE", "POTENTIALLY_HARMFUL_APPLICATION"],
                "platformTypes": ["ANY_PLATFORM"],
                "threatEntryTypes": ["URL"],
                "threatEntries": [{"url": url}]
            }
        }
        data = jsonlib.dumps(payload).encode('utf-8')

        request = QNetworkRequest(QUrl(f"{self.api_url}?key={self.api_key}"))
        request.setHeader(QNetworkRequest.KnownHeaders.ContentTypeHeader, "application/json")

        reply = self.nam.post(request, data)
        loop = QEventLoop()
        reply.finished.connect(loop.quit)
        QTimer.singleShot(5000, loop.quit)
        loop.exec()

        if reply.error() == QNetworkReply.NetworkError.NoError:
            try:
                response_data = reply.readAll().data().decode('utf-8')
                data = jsonlib.loads(response_data)
                if "matches" in data and len(data["matches"]) > 0:
                    threat_type = data["matches"][0].get("threatType", "UNKNOWN")
                    reply.deleteLater()
                    return False, threat_type
                else:
                    reply.deleteLater()
                    return True, None
            except Exception as e:
                print(f"[SafeBrowsing] Ошибка обработки ответа: {e}")
                reply.deleteLater()
                return True, None
        else:
            print(f"[SafeBrowsing] Ошибка сети: {reply.errorString()}")
            reply.deleteLater()
            return True, None

# ================================================================
#  КАСТОМНАЯ СТРАНИЦА ДЛЯ ПЕРЕХВАТА НАВИГАЦИИ С SAFE BROWSING
# ================================================================
class SafeBrowsingWebEnginePage(QWebEnginePage):
    def __init__(self, profile, browser_window, parent=None):
        super().__init__(profile, parent)
        self.browser_window = browser_window

    def acceptNavigationRequest(self, url, navigation_type, is_main_frame):
        if is_main_frame:
            url_str = url.toString()
            is_safe, threat_type = self.browser_window.safe_browsing.check_url_sync(url_str)
            if not is_safe:
                threat_names = {
                    "MALWARE": "Вредоносное ПО",
                    "SOCIAL_ENGINEERING": "Фишинг / Мошенничество",
                    "UNWANTED_SOFTWARE": "Нежелательное ПО",
                    "POTENTIALLY_HARMFUL_APPLICATION": "Потенциально опасное приложение"
                }
                threat_name = threat_names.get(threat_type, threat_type or "Неизвестная угроза")
                reply = QMessageBox.warning(
                    self.browser_window,
                    "⚠️ Опасный сайт",
                    f"<b>Google Safe Browsing</b> обнаружил угрозу: <b>{threat_name}</b>\n\n"
                    f"URL: {url_str}\n\n"
                    "Этот сайт может быть опасным. Вы уверены, что хотите продолжить?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No
                )
                if reply == QMessageBox.StandardButton.No:
                    return False
        return super().acceptNavigationRequest(url, navigation_type, is_main_frame)

# ================================================================
#  МОДЕЛЬ NANOGPT (для ответов в поиске)
# ================================================================
BLOCK_SIZE = 64
VOCAB_SIZE = 16000
N_EMBD = 192
N_HEAD = 6
N_LAYER = 4
DEVICE = 'cuda' if torch.cuda.is_available() else 'cpu'

TEMPERATURE = 0.25
TOP_K = 6
REPETITION_PENALTY = 1.3

class Head(nn.Module):
    def __init__(self, head_size):
        super().__init__()
        self.key = nn.Linear(N_EMBD, head_size, bias=False)
        self.query = nn.Linear(N_EMBD, head_size, bias=False)
        self.value = nn.Linear(N_EMBD, head_size, bias=False)
        self.register_buffer('tril', torch.tril(torch.ones(BLOCK_SIZE, BLOCK_SIZE)))
    def forward(self, x):
        B, T, C = x.shape
        k, q, v = self.key(x), self.query(x), self.value(x)
        wei = q @ k.transpose(-2, -1) * (C**-0.5)
        wei = wei.masked_fill(self.tril[:T, :T] == 0, float('-inf'))
        return F.softmax(wei, dim=-1) @ v

class MultiHeadAttention(nn.Module):
    def __init__(self, num_heads, head_size):
        super().__init__()
        self.heads = nn.ModuleList([Head(head_size) for _ in range(num_heads)])
        self.proj = nn.Linear(N_EMBD, N_EMBD)
    def forward(self, x):
        return self.proj(torch.cat([h(x) for h in self.heads], dim=-1))

class FeedFoward(nn.Module):
    def __init__(self, n_embd):
        super().__init__()
        self.net = nn.Sequential(nn.Linear(n_embd, 4 * n_embd), nn.ReLU(), nn.Linear(4 * n_embd, n_embd))
    def forward(self, x):
        return self.net(x)

class Block(nn.Module):
    def __init__(self, n_embd, n_head):
        super().__init__()
        self.sa = MultiHeadAttention(n_head, n_embd // n_head)
        self.ffwd = FeedFoward(n_embd)
        self.ln1, self.ln2 = nn.LayerNorm(n_embd), nn.LayerNorm(n_embd)
    def forward(self, x):
        x = x + self.sa(self.ln1(x))
        return x + self.ffwd(self.ln2(x))

class NanoGPT(nn.Module):
    def __init__(self):
        super().__init__()
        self.token_embedding_table = nn.Embedding(VOCAB_SIZE, N_EMBD)
        self.position_embedding_table = nn.Embedding(BLOCK_SIZE, N_EMBD)
        self.blocks = nn.Sequential(*[Block(N_EMBD, n_head=N_HEAD) for _ in range(N_LAYER)])
        self.ln_f = nn.LayerNorm(N_EMBD)
        self.lm_head = nn.Linear(N_EMBD, VOCAB_SIZE)
    def forward(self, idx):
        B, T = idx.shape
        tok_emb = self.token_embedding_table(idx)
        pos_emb = self.position_embedding_table(torch.arange(T, device=idx.device))
        x = tok_emb + pos_emb
        x = self.blocks(x)
        return self.lm_head(self.ln_f(x))

model_nano = None
tokenizer_nano = None
model_nano_loaded = False

def load_nanogpt():
    global model_nano, tokenizer_nano, model_nano_loaded
    if not TORCH_AVAILABLE:
        return False
    if not os.path.exists(GPT2_MODEL_PATH) or not os.path.exists(GPT2_TOKENIZER_DIR):
        print(f"[INFO] Файлы NanoGPT не найдены в {AI_DIR}. Модель отключена.")
        return False
    try:
        tokenizer_nano = Tokenizer.from_file(NANOGPT_TOKENIZER_PATH)
        model_nano = NanoGPT().to(DEVICE)
        model_nano.load_state_dict(torch.load(GPT2_MODEL_PATH, map_location=DEVICE))
        model_nano.eval()
        model_nano_loaded = True
        print(f"[SUCCESS] NanoGPT загружена на {DEVICE.upper()}!")
        return True
    except Exception as e:
        print(f"[ERROR] Не удалось загрузить NanoGPT: {e}")
        model_nano = None
        tokenizer_nano = None
        model_nano_loaded = False
        return False

def generate_ai_answer(query, lang='ru', context=''):
    global model_nano, tokenizer_nano, model_nano_loaded
    if not model_nano_loaded or model_nano is None or tokenizer_nano is None:
        return f"Я — локальный ИИ-помощник. Модель пока не загружена или отсутствует. Ваш вопрос: {query}"
    try:
        prompt = f"Вопрос: {query}\n"
        if context:
            prompt += context + "\n"
        prompt += "Ответ:"
        prompt_ids = tokenizer_nano.encode(prompt).ids
        context_tokens = torch.tensor([prompt_ids], dtype=torch.long, device=DEVICE)
        generated_tokens = []
        accumulated_text = ""
        with torch.no_grad():
            for i in range(BLOCK_SIZE):
                context_cond = context_tokens[:, -BLOCK_SIZE:]
                logits = model_nano(context_cond)
                logits = logits[:, -1, :] / TEMPERATURE
                if len(generated_tokens) > 0:
                    for token_id in set(generated_tokens):
                        if logits[0, token_id] > 0:
                            logits[0, token_id] /= REPETITION_PENALTY
                        else:
                            logits[0, token_id] *= REPETITION_PENALTY
                v, _ = torch.topk(logits, TOP_K)
                logits[logits < v[:, [-1]]] = float('-inf')
                probs = F.softmax(logits, dim=-1)
                next_token = torch.multinomial(probs, num_samples=1)
                generated_tokens.append(next_token.item())
                context_tokens = torch.cat((context_tokens, next_token), dim=1)
                token_text = tokenizer_nano.decode([next_token.item()])
                if not token_text:
                    continue
                if "\n" in token_text or token_text in ["[EOS]", "###"]:
                    break
                accumulated_text += " " + token_text.strip()
                if "Вопрос" in accumulated_text:
                    accumulated_text = accumulated_text.split("Вопрос")[0]
                    break
        clean_output = accumulated_text.strip()
        replacements = {" .": ".", " ,": ",", " ?": "?", " !": "!", " :": ":", " - ": "-"}
        for old, new in replacements.items():
            clean_output = clean_output.replace(old, new)
        return clean_output if clean_output else "Извините, я не смог сгенерировать ответ."
    except Exception as e:
        print(f"[ERROR] Ошибка генерации NanoGPT: {e}")
        return "Извините, произошла ошибка при генерации ответа."

# ================================================================
#  МОДЕЛЬ GPT-2 (для чата)
# ================================================================
gpt2_model = None
gpt2_tokenizer = None
gpt2_loaded = False

def load_gpt2():
    global gpt2_model, gpt2_tokenizer, gpt2_loaded
    if not TORCH_AVAILABLE or not TRANSFORMERS_AVAILABLE:
        return False
    if not os.path.exists(GPT2_TOKENIZER_DIR) or not os.path.exists(GPT2_MODEL_PATH):
        print(f"[INFO] Файлы GPT-2 не найдены в {AI_DIR}. Модель отключена.")
        return False
    try:
        gpt2_tokenizer = AutoTokenizer.from_pretrained(GPT2_TOKENIZER_DIR, clean_up_tokenization_spaces=False)
        if gpt2_tokenizer.pad_token is None:
            gpt2_tokenizer.pad_token = gpt2_tokenizer.eos_token
        config = GPT2Config(vocab_size=50257, n_positions=512, n_embd=512, n_layer=16, n_head=8)
        gpt2_model = GPT2LMHeadModel(config)
        gpt2_model.load_state_dict(torch.load(GPT2_MODEL_PATH, map_location=DEVICE))
        gpt2_model.to(DEVICE)
        gpt2_model.eval()
        gpt2_loaded = True
        print(f"[SUCCESS] GPT-2 модель загружена на {DEVICE.upper()}!")
        return True
    except Exception as e:
        print(f"[ERROR] Не удалось загрузить GPT-2: {e}")
        gpt2_model = None
        gpt2_tokenizer = None
        gpt2_loaded = False
        return False

def generate_gpt2_reply(user_text):
    global gpt2_model, gpt2_tokenizer, gpt2_loaded
    if not gpt2_loaded or gpt2_model is None or gpt2_tokenizer is None:
        return "Модель GPT-2 не загружена. Проверьте папку AI."
    try:
        bos = gpt2_tokenizer.bos_token if gpt2_tokenizer.bos_token else ""
        prompt = f"{bos}Вопрос: {user_text}\nОтвет:"
        input_ids = gpt2_tokenizer.encode(prompt, return_tensors="pt").to(DEVICE)
        with torch.no_grad():
            output_ids = gpt2_model.generate(
                input_ids,
                max_new_tokens=100,
                do_sample=True,
                temperature=0.2,
                top_k=25,
                top_p=0.85,
                repetition_penalty=1.3,
                pad_token_id=gpt2_tokenizer.pad_token_id,
                eos_token_id=gpt2_tokenizer.eos_token_id
            )
        reply = gpt2_tokenizer.decode(output_ids[0][len(input_ids[0]):], skip_special_tokens=True)
        return reply.strip() if reply.strip() else "Извините, я не смог ответить."
    except Exception as e:
        print(f"[ERROR] Ошибка генерации GPT-2: {e}")
        return "Произошла ошибка при генерации ответа."

# Загружаем модели при старте
load_gpt2()

# ================================================================
#  FLASK API
# ================================================================
app = Flask(__name__, static_folder=STATIC_DIR, template_folder=STATIC_DIR)
CORS(app)

# ---------- Профили ----------
@app.route('/api/profile/create', methods=['POST'])
def create_profile():
    user_id = ''.join(str(random.randint(0, 9)) for _ in range(16))
    profile = {
        "id": user_id,
        "nickname": f"User_{user_id[:4]}",
        "avatar": "",
        "created_at": datetime.now().isoformat(),
        "settings": {"language": "ru"}
    }
    with open(os.path.join(PROFILE_DIR, f"{user_id}.json"), 'w', encoding='utf-8') as f:
        json.dump(profile, f, ensure_ascii=False, indent=2)
    return jsonify({"success": True, "profile": profile})

@app.route('/api/profile/get', methods=['POST'])
def get_profile():
    data = request.get_json()
    user_id = data.get('id')
    if not user_id:
        return jsonify({"success": False, "error": "No id"}), 400
    filepath = os.path.join(PROFILE_DIR, f"{user_id}.json")
    if not os.path.exists(filepath):
        return jsonify({"success": False, "error": "Profile not found"}), 404
    with open(filepath, 'r', encoding='utf-8') as f:
        profile = json.load(f)
    return jsonify({"success": True, "profile": profile})

@app.route('/api/profile/update', methods=['POST'])
def update_profile():
    data = request.get_json()
    user_id = data.get('id')
    updates = data.get('updates', {})
    if not user_id:
        return jsonify({"success": False, "error": "No id"}), 400
    filepath = os.path.join(PROFILE_DIR, f"{user_id}.json")
    if not os.path.exists(filepath):
        return jsonify({"success": False, "error": "Profile not found"}), 404
    with open(filepath, 'r', encoding='utf-8') as f:
        profile = json.load(f)
    if 'nickname' in updates:
        profile['nickname'] = updates['nickname'][:30]
    if 'avatar' in updates:
        profile['avatar'] = updates['avatar']
    if 'settings' in updates and isinstance(updates['settings'], dict):
        profile['settings'].update(updates['settings'])
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(profile, f, ensure_ascii=False, indent=2)
    return jsonify({"success": True, "profile": profile})

@app.route('/api/profile/delete', methods=['POST'])
def delete_profile():
    data = request.get_json()
    user_id = data.get('id')
    if not user_id:
        return jsonify({"success": False, "error": "No id"}), 400
    filepath = os.path.join(PROFILE_DIR, f"{user_id}.json")
    if os.path.exists(filepath):
        os.remove(filepath)
    return jsonify({"success": True})

KEY = Fernet.generate_key()
cipher = Fernet(KEY)
print(f"[INFO] Создался ключ")
# ---------- Пароли ----------
def save_passwords(data):
    with open(PASSWORD_FILE, 'wb') as f:
        jsons = json.dumps(data)
        bytes_data = jsons.encode()
        encrypted_data = cipher.encrypt(bytes_data)
        f.write(encrypted_data)

def load_passwords():
    if os.path.exists(PASSWORD_FILE):
        with open(PASSWORD_FILE, 'rb') as f:
            encrypted_data = f.read()
            bytes_data = cipher.decrypt(encrypted_data)
            jsons = bytes_data.decode()
            return json.loads(jsons)
    return {}

@app.route('/api/passwords/get', methods=['POST'])
def get_passwords():
    return jsonify(load_passwords())

@app.route('/api/passwords/save', methods=['POST'])
def save_password():
    data = request.get_json()
    domain = data.get('domain')
    username = data.get('username')
    password = data.get('password')
    if not domain or not username or not password:
        return jsonify({"success": False, "error": "Missing fields"}), 400
    store = load_passwords()
    if domain not in store:
        store[domain] = []
    for entry in store[domain]:
        if entry['username'] == username:
            entry['password'] = password
            break
    else:
        store[domain].append({"username": username, "password": password})
    save_passwords(store)
    return jsonify({"success": True})

@app.route('/api/passwords/delete', methods=['POST'])
def delete_password():
    data = request.get_json()
    domain = data.get('domain')
    username = data.get('username')
    if not domain or not username:
        return jsonify({"success": False, "error": "Missing fields"}), 400
    store = load_passwords()
    if domain in store:
        store[domain] = [e for e in store[domain] if e['username'] != username]
        if not store[domain]:
            del store[domain]
        save_passwords(store)
    return jsonify({"success": True})

# ---------- Фон и виджеты ----------
def load_backgrounds():
    if os.path.exists(BACKGROUNDS_FILE):
        with open(BACKGROUNDS_FILE, 'r') as f:
            return json.load(f)
    return {"type": "color", "value": "#0a0f14"}

def save_backgrounds(data):
    with open(BACKGROUNDS_FILE, 'w') as f:
        json.dump(data, f, indent=2)

def load_widgets():
    if os.path.exists(WIDGETS_FILE):
        with open(WIDGETS_FILE, 'r') as f:
            return json.load(f)
    return [
        {"name": "Gmail", "url": "https://mail.google.com", "icon": "📧"},
        {"name": "YouTube", "url": "https://youtube.com", "icon": "🎬"},
        {"name": "ВК", "url": "https://vk.com", "icon": "💬"}
    ]

def save_widgets(data):
    with open(WIDGETS_FILE, 'w') as f:
        json.dump(data, f, indent=2)

@app.route('/api/backgrounds/get', methods=['GET'])
def get_backgrounds():
    return jsonify(load_backgrounds())

@app.route('/api/backgrounds/set', methods=['POST'])
def set_backgrounds():
    data = request.get_json()
    if 'type' not in data or 'value' not in data:
        return jsonify({"error": "Invalid data"}), 400
    save_backgrounds({"type": data['type'], "value": data['value']})
    return jsonify({"success": True})

@app.route('/api/widgets/get', methods=['GET'])
def get_widgets():
    return jsonify(load_widgets())

@app.route('/api/widgets/set', methods=['POST'])
def set_widgets():
    widgets = request.get_json()
    if not isinstance(widgets, list):
        return jsonify({"error": "Invalid data"}), 400
    save_widgets(widgets)
    return jsonify({"success": True})

# ---------- Настройки и вкладки ----------
@app.route('/api/settings/get', methods=['GET'])
def get_settings():
    return jsonify(load_settings())

@app.route('/api/settings/set', methods=['POST'])
def set_settings():
    data = request.get_json()
    settings = load_settings()
    if 'theme' in data:
        settings['theme'] = data['theme']
    if 'language' in data:
        settings['language'] = data['language']
    save_settings(settings)
    return jsonify({"success": True, "settings": settings})

@app.route('/api/tabs/get', methods=['GET'])
def get_tabs():
    if os.path.exists(TABS_FILE):
        with open(TABS_FILE, 'r', encoding='utf-8') as f:
            return jsonify(json.load(f))
    return jsonify({"tabs": [], "current_index": 0})

@app.route('/api/tabs/save', methods=['POST'])
def save_tabs():
    data = request.get_json()
    with open(TABS_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return jsonify({"success": True})

# ---------- ПОИСК ----------
def search_ddgs(query, max_results=14):
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
            formatted = []
            for r in results:
                formatted.append({
                    'title': r.get('title', ''),
                    'url': r.get('href', '#'),
                    'snippet': r.get('body', '')
                })
            return formatted
    except Exception as e:
        print(f"Ошибка DDGS: {e}")
        return []

CACHE = {}
CACHE_TTL = 300

def get_cached(query):
    if query in CACHE:
        data, timestamp = CACHE[query]
        if time.time() - timestamp < CACHE_TTL:
            return data
        else:
            del CACHE[query]
    return None

def set_cache(query, data):
    CACHE[query] = (data, time.time())

def protection(text):
    if not text:
        return ""
    import re
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'[\'";]', '', text)
    return text[:1000]

@app.route('/api/combined', methods=['POST'])
def combined():
    data = request.get_json()
    query = protection(data.get('query', ''))
    lang = data.get('lang', 'ru')
    if not query:
        return jsonify({'search_results': [], 'ai_answer': None})

    cached = get_cached(query)
    if cached is not None:
        if isinstance(cached, tuple) and len(cached) == 2:
            return jsonify({'search_results': cached[0], 'ai_answer': cached[1]})
        else:
            return jsonify({'search_results': cached, 'ai_answer': None})

    results = search_ddgs(query, max_results=14)

    if not results:
        lower = query.lower()
        keywords = ['кыргызстан', 'бишкек', 'манас', 'ош', 'иссык-куль', 'кыргыз']
        for word in keywords:
            if word in lower:
                results.append({
                    'title': '🇰🇬 Интересный факт о Кыргызстане',
                    'url': 'https://ru.wikipedia.org/wiki/Кыргызстан',
                    'snippet': 'Кыргызстан – страна гор, озёр и древних традиций.'
                })
                break

    context = ""
    if results:
        snippets = [r.get('snippet', '') for r in results[:5] if r.get('snippet')]
        if snippets:
            context = "Информация из поиска:\n" + "\n".join(snippets)

    ai_answer = generate_gpt2_reply(query)

    set_cache(query, (results, ai_answer))
    return jsonify({'search_results': results, 'ai_answer': ai_answer})

# ---------- ЧАТ С GPT-2 ----------
@app.route('/api/chat', methods=['POST'])
def chat_gpt2():
    data = request.get_json()
    user_text = data.get('message', '').strip()
    if not user_text:
        return jsonify({'reply': 'Пожалуйста, введите сообщение.'})
    reply = generate_gpt2_reply(user_text)
    return jsonify({'reply': reply})

# ---------- ПЕРЕВОД ----------
@app.route('/api/translate', methods=['POST'])
def translate_text():
    data = request.get_json()
    text = data.get('text', '')
    source = data.get('source', 'auto')
    target = data.get('target', 'ru')
    if not text:
        return jsonify({'translated': ''})
    try:
        translator = GoogleTranslator(source=source, target=target)
        translated = translator.translate(text)
        return jsonify({'translated': translated})
    except Exception as e:
        return jsonify({'translated': 'Ошибка перевода'}), 500

# ---------- СТАТИЧЕСКИЕ СТРАНИЦЫ ----------
@app.route('/')
@app.route('/index.html')
def index():
    return send_from_directory(STATIC_DIR, 'index.html')

@app.route('/profile.html')
def profile():
    return send_from_directory(STATIC_DIR, 'profile.html')

# ================================================================
#  ВИДЖЕТЫ Qt (Профиль, Инструменты, Настройки)
# ================================================================

# ---------- МОНИТОР ----------
class MonitorWorker(QThread):
    update_signal = pyqtSignal(str, str)

    def __init__(self, url, interval_minutes, parent=None):
        super().__init__(parent)
        self.url = url
        self.interval = interval_minutes * 60
        self.running = True
        self.last_hash = None

    def run(self):
        while self.running:
            try:
                import requests
                resp = requests.get(self.url, timeout=15)
                if resp.status_code == 200:
                    soup = BeautifulSoup(resp.text, 'html.parser')
                    for script in soup(["script", "style"]):
                        script.decompose()
                    text = soup.get_text(separator=' ', strip=True)
                    current_hash = hashlib.md5(text.encode('utf-8')).hexdigest()
                    if self.last_hash is None:
                        self.last_hash = current_hash
                    elif self.last_hash != current_hash:
                        self.update_signal.emit(self.url, "Содержимое страницы изменилось!")
                        self.last_hash = current_hash
                else:
                    self.update_signal.emit(self.url, f"Ошибка доступа: {resp.status_code}")
            except Exception as e:
                self.update_signal.emit(self.url, f"Ошибка проверки: {str(e)}")
            for _ in range(self.interval):
                if not self.running:
                    break
                time.sleep(1)

    def stop(self):
        self.running = False

class MonitorManager:
    def __init__(self):
        self.monitors = {}

    def add_monitor(self, url, interval, callback):
        if url in self.monitors:
            return False, "Мониторинг для этого URL уже запущен"
        thread = MonitorWorker(url, interval)
        thread.update_signal.connect(callback)
        thread.start()
        self.monitors[url] = (thread, interval)
        return True, "Мониторинг запущен"

    def remove_monitor(self, url):
        if url in self.monitors:
            thread, _ = self.monitors[url]
            thread.stop()
            thread.wait()
            del self.monitors[url]
            return True, "Мониторинг остановлен"
        return False, "Мониторинг для этого URL не найден"

# ---------- ИНСТРУМЕНТЫ ----------
class ToolsWidget(QWidget):
    def __init__(self, parent=None, browser_window=None):
        super().__init__(parent)
        self.browser_window = browser_window
        self.monitor_manager = MonitorManager()
        self.current_monitor_url = None

        layout = QVBoxLayout(self)
        self.output_area = QTextEdit()
        self.output_area.setReadOnly(True)
        self.output_area.setFont(QFont("Segoe UI", 10))
        layout.addWidget(self.output_area)

        btn_layout = QHBoxLayout()
        self.btn_monitor = QPushButton("🔔 Следить")
        self.btn_monitor.clicked.connect(self.start_monitor)
        btn_layout.addWidget(self.btn_monitor)

        self.btn_stop_monitor = QPushButton("🚫 Остановить слежку")
        self.btn_stop_monitor.clicked.connect(self.stop_monitor)
        self.btn_stop_monitor.setEnabled(False)
        btn_layout.addWidget(self.btn_stop_monitor)

        layout.addLayout(btn_layout)
        self.append_message("📢", "Мониторинг страниц. Нажмите «Следить» для текущей вкладки.")

    def append_message(self, sender, msg):
        color = "#6effaa" if sender == "📢" else "#ffffff"
        self.output_area.append(f'<b style="color:{color}">{sender}</b>: {msg}')

    def start_monitor(self):
        if not self.browser_window:
            self.append_message("⚠️", "Нет активного окна браузера")
            return
        web_view = self.browser_window.get_current_web_view()
        if not web_view:
            return
        url = web_view.url().toString()
        if not url or url == "about:blank":
            self.append_message("⚠️", "Нет URL для мониторинга.")
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("Настройка мониторинга")
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel(f"Следить за:\n{url}"))
        hbox = QHBoxLayout()
        hbox.addWidget(QLabel("Интервал (минуты):"))
        spin = QSpinBox()
        spin.setRange(5, 1440)
        spin.setValue(60)
        hbox.addWidget(spin)
        layout.addLayout(hbox)
        btn_ok = QPushButton("Запустить")
        btn_ok.clicked.connect(dialog.accept)
        btn_cancel = QPushButton("Отмена")
        btn_cancel.clicked.connect(dialog.reject)
        hbox_btns = QHBoxLayout()
        hbox_btns.addWidget(btn_ok)
        hbox_btns.addWidget(btn_cancel)
        layout.addLayout(hbox_btns)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        interval = spin.value()

        def on_update(url, message):
            if self.browser_window:
                self.browser_window.statusBar().showMessage(f"🔔 {url} – {message}")
            self.append_message("🔔", f"{url} – {message}")

        success, msg = self.monitor_manager.add_monitor(url, interval, on_update)
        self.append_message("🔔", msg)
        if success:
            self.current_monitor_url = url
            self.btn_stop_monitor.setEnabled(True)

    def stop_monitor(self):
        if self.current_monitor_url:
            success, msg = self.monitor_manager.remove_monitor(self.current_monitor_url)
            self.append_message("🔔", msg)
            if success:
                self.current_monitor_url = None
                self.btn_stop_monitor.setEnabled(False)

# ---------- ПРОФИЛЬ (вкладка) ----------
class ProfileWidget(QWidget):
    def __init__(self, parent=None, browser_window=None):
        super().__init__(parent)
        self.browser_window = browser_window
        self.settings = load_settings()

        layout = QVBoxLayout(self)

        self.tabs = QTabWidget(self)
        self.tab_profile = QWidget()
        self.tab_tools = ToolsWidget(self, browser_window)
        self.tab_settings = QWidget()
        self.tabs.addTab(self.tab_profile, "Профиль")
        self.tabs.addTab(self.tab_tools, "Инструменты")
        self.tabs.addTab(self.tab_settings, "Настройки")

        # Вкладка профиля
        profile_layout = QVBoxLayout(self.tab_profile)
        self.profile_view = QWebEngineView()
        self.profile_view.setUrl(QUrl(PROFILE_URL))
        profile_layout.addWidget(self.profile_view)

        # ---------- Вкладка НАСТРОЙКИ ----------
        settings_layout = QVBoxLayout(self.tab_settings)
        settings_layout.setSpacing(15)

        theme_group = QGroupBox("Оформление")
        theme_layout = QVBoxLayout(theme_group)
        theme_layout.addWidget(QLabel("Тема:"))
        self.theme_dark = QRadioButton("Тёмная")
        self.theme_light = QRadioButton("Светлая")
        self.theme_system = QRadioButton("Системная")
        if self.settings.get("theme") == "dark":
            self.theme_dark.setChecked(True)
        elif self.settings.get("theme") == "light":
            self.theme_light.setChecked(True)
        else:
            self.theme_system.setChecked(True)
        theme_layout.addWidget(self.theme_dark)
        theme_layout.addWidget(self.theme_light)
        theme_layout.addWidget(self.theme_system)
        settings_layout.addWidget(theme_group)

        lang_group = QGroupBox("Язык")
        lang_layout = QVBoxLayout(lang_group)
        self.lang_combo = QComboBox()
        self.lang_combo.addItems(["Русский", "English", "Кыргызча"])
        lang_map = {"ru": "Русский", "en": "English", "ky": "Кыргызча"}
        current_lang = self.settings.get("language", "ru")
        self.lang_combo.setCurrentText(lang_map.get(current_lang, "Русский"))
        lang_layout.addWidget(self.lang_combo)
        settings_layout.addWidget(lang_group)

        bg_group = QGroupBox("Фон главной страницы")
        bg_layout = QVBoxLayout(bg_group)
        color_layout = QHBoxLayout()
        color_layout.addWidget(QLabel("Цвета:"))
        colors = ["#0a0f14", "#1a2a3a", "#2d3748", "#f0f4f8", "#6effaa", "#ff6b6b"]
        self.color_buttons = []
        for c in colors:
            btn = QPushButton()
            btn.setFixedSize(40, 40)
            btn.setStyleSheet(f"background-color: {c}; border-radius: 20px; border: 2px solid transparent;")
            btn.clicked.connect(lambda checked, col=c: self.set_bg_color(col))
            color_layout.addWidget(btn)
            self.color_buttons.append(btn)
        color_layout.addStretch()
        bg_layout.addLayout(color_layout)

        image_layout = QHBoxLayout()
        image_layout.addWidget(QLabel("Изображение:"))
        self.bg_file_btn = QPushButton("Выбрать файл...")
        self.bg_file_btn.clicked.connect(self.choose_bg_image)
        image_layout.addWidget(self.bg_file_btn)
        self.bg_clear_btn = QPushButton("Сбросить фон")
        self.bg_clear_btn.clicked.connect(self.clear_bg)
        image_layout.addWidget(self.bg_clear_btn)
        image_layout.addStretch()
        bg_layout.addLayout(image_layout)
        settings_layout.addWidget(bg_group)

        widget_group = QGroupBox("Виджеты быстрого доступа")
        widget_layout = QVBoxLayout(widget_group)
        self.widget_list = QTextEdit()
        self.widget_list.setReadOnly(True)
        self.widget_list.setMaximumHeight(100)
        widget_layout.addWidget(QLabel("Текущие виджеты (имя, URL):"))
        widget_layout.addWidget(self.widget_list)

        btn_widget_layout = QHBoxLayout()
        self.add_widget_btn = QPushButton("➕ Добавить виджет")
        self.add_widget_btn.clicked.connect(self.add_widget_dialog)
        self.remove_widget_btn = QPushButton("✖ Удалить виджет (по номеру)")
        self.remove_widget_btn.clicked.connect(self.remove_widget_dialog)
        btn_widget_layout.addWidget(self.add_widget_btn)
        btn_widget_layout.addWidget(self.remove_widget_btn)
        widget_layout.addLayout(btn_widget_layout)
        settings_layout.addWidget(widget_group)

        btn_save_settings = QPushButton("Сохранить все настройки")
        btn_save_settings.clicked.connect(self.save_all_settings)
        settings_layout.addWidget(btn_save_settings)
        settings_layout.addStretch()

        layout.addWidget(self.tabs)
        self.refresh_widget_list()

    def set_bg_color(self, color):
        self._set_bg('color', color)

    def choose_bg_image(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Выберите изображение", "", "Images (*.png *.jpg *.jpeg *.bmp *.gif)")
        if file_path:
            with open(file_path, 'rb') as f:
                data = base64.b64encode(f.read()).decode('utf-8')
                ext = file_path.split('.')[-1].lower()
                mime = f"image/{ext}" if ext in ['png','jpg','jpeg','bmp','gif'] else "image/png"
                data_url = f"data:{mime};base64,{data}"
            self._set_bg('image', data_url)

    def clear_bg(self):
        self._set_bg('color', '#0a0f14')

    def _set_bg(self, bg_type, value):
        try:
            import requests
            requests.post('http://127.0.0.1:5000/api/backgrounds/set',
                          json={'type': bg_type, 'value': value})
            if self.browser_window:
                wv = self.browser_window.get_current_web_view()
                if wv:
                    wv.reload()
                    QMessageBox.information(self, "Успешно", "Фон обновлён. Страница перезагружена.")
        except Exception as e:
            QMessageBox.warning(self, "Ошибка", f"Не удалось сохранить фон: {e}")

    def refresh_widget_list(self):
        try:
            import requests
            resp = requests.get('http://127.0.0.1:5000/api/widgets/get')
            if resp.status_code == 200:
                widgets = resp.json()
                text = ""
                for i, w in enumerate(widgets):
                    text += f"{i+1}. {w.get('icon','🌐')} {w.get('name','')} – {w.get('url','')}\n"
                self.widget_list.setText(text)
            else:
                self.widget_list.setText("Ошибка загрузки виджетов")
        except Exception as e:
            self.widget_list.setText(f"Ошибка: {e}")

    def add_widget_dialog(self):
        name, ok1 = QInputDialog.getText(self, "Добавить виджет", "Название:")
        if not ok1 or not name:
            return
        url, ok2 = QInputDialog.getText(self, "Добавить виджет", "URL (с http://):")
        if not ok2 or not url:
            return
        icon, ok3 = QInputDialog.getText(self, "Добавить виджет", "Иконка (эмодзи):")
        if not ok3:
            icon = "🌐"

        try:
            import requests
            resp = requests.get('http://127.0.0.1:5000/api/widgets/get')
            if resp.status_code != 200:
                QMessageBox.warning(self, "Ошибка", "Не удалось получить виджеты")
                return
            widgets = resp.json()
            widgets.append({"name": name, "url": url, "icon": icon})
            resp2 = requests.post('http://127.0.0.1:5000/api/widgets/set', json=widgets)
            if resp2.status_code == 200:
                self.refresh_widget_list()
                if self.browser_window:
                    wv = self.browser_window.get_current_web_view()
                    if wv:
                        wv.reload()
                QMessageBox.information(self, "Успешно", "Виджет добавлен")
            else:
                QMessageBox.warning(self, "Ошибка", "Не удалось сохранить виджет")
        except Exception as e:
            QMessageBox.warning(self, "Ошибка", str(e))

    def remove_widget_dialog(self):
        index_str, ok = QInputDialog.getText(self, "Удалить виджет", "Введите номер виджета для удаления:")
        if not ok or not index_str:
            return
        try:
            index = int(index_str) - 1
            if index < 0:
                raise ValueError
            import requests
            resp = requests.get('http://127.0.0.1:5000/api/widgets/get')
            if resp.status_code != 200:
                QMessageBox.warning(self, "Ошибка", "Не удалось получить виджеты")
                return
            widgets = resp.json()
            if index >= len(widgets):
                QMessageBox.warning(self, "Ошибка", f"Номер должен быть от 1 до {len(widgets)}")
                return
            del widgets[index]
            resp2 = requests.post('http://127.0.0.1:5000/api/widgets/set', json=widgets)
            if resp2.status_code == 200:
                self.refresh_widget_list()
                if self.browser_window:
                    wv = self.browser_window.get_current_web_view()
                    if wv:
                        wv.reload()
                QMessageBox.information(self, "Успешно", "Виджет удалён")
            else:
                QMessageBox.warning(self, "Ошибка", "Не удалось сохранить изменения")
        except ValueError:
            QMessageBox.warning(self, "Ошибка", "Введите целое число")
        except Exception as e:
            QMessageBox.warning(self, "Ошибка", str(e))

    def save_all_settings(self):
        if self.theme_dark.isChecked():
            theme = "dark"
        elif self.theme_light.isChecked():
            theme = "light"
        else:
            theme = "system"
        lang_map = {"Русский": "ru", "English": "en", "Кыргызча": "ky"}
        lang = lang_map.get(self.lang_combo.currentText(), "ru")

        self.settings["theme"] = theme
        self.settings["language"] = lang
        save_settings(self.settings)

        if self.browser_window:
            self.browser_window.apply_theme(theme)
        QMessageBox.information(self, "Настройки", "Настройки сохранены и применены.")

# ================================================================
#  iOS-ПЕРЕКЛЮЧАТЕЛЬ (IOSToggle)
# ================================================================
class IOSToggle(QPushButton):
    toggled = pyqtSignal(bool)
    def __init__(self, parent=None):
        super().__init__(parent)
        self._checked = False
        self.setFixedSize(60, 32)
        self.setCheckable(False)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clicked.connect(self._toggle)
        self.anim = QPropertyAnimation(self, b"pos")
        self.anim.setDuration(200)
        self.anim.setEasingCurve(QEasingCurve.Type.OutQuad)
        self.off_color = QColor(120, 120, 128)
        self.on_color = QColor(52, 199, 89)
        self.thumb_color = QColor(255, 255, 255)
        self.thumb_radius = 12
        self.setStyleSheet("background: transparent; border: none;")
        self.update()

    def _toggle(self):
        self.set_checked(not self._checked, animate=True)

    def set_checked(self, checked, animate=True):
        if self._checked == checked:
            return
        self._checked = checked
        if animate:
            start = QPoint(2, 2) if not checked else QPoint(self.width() - self.thumb_radius*2 - 2, 2)
            end = QPoint(self.width() - self.thumb_radius*2 - 2, 2) if checked else QPoint(2, 2)
            self.anim.setStartValue(start)
            self.anim.setEndValue(end)
            self.anim.start()
        else:
            self.update()
        self.toggled.emit(self._checked)

    def is_checked(self):
        return self._checked

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect()
        track_rect = rect.adjusted(2, 2, -2, -2)
        radius = track_rect.height() // 2
        bg_color = self.on_color if self._checked else self.off_color
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(bg_color)
        painter.drawRoundedRect(track_rect, radius, radius)
        thumb_x = track_rect.left() + 2 if not self._checked else track_rect.right() - self.thumb_radius*2 - 2
        thumb_rect = QRect(thumb_x, track_rect.top() + 2, self.thumb_radius*2, self.thumb_radius*2)
        painter.setBrush(self.thumb_color)
        painter.setPen(QPen(QColor(0, 0, 0, 30), 1))
        painter.drawEllipse(thumb_rect)

    def mousePressEvent(self, event):
        self._toggle()

# ================================================================
#  ГЛАВНОЕ ОКНО БРАУЗЕРА
# ================================================================
class BrowserWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("FreeSearch")
        icon_path = resource_path("freesearch.jpeg")
        self.setWindowIcon(QIcon(icon_path))
        screen = self.setGeometry(100, 100, 1200, 800)

        font = QFont("Segoe UI", 9)
        QApplication.setFont(font)

        self.settings = load_settings()
        self.apply_theme(self.settings.get("theme", "dark"))

        # Safe Browsing
        self.safe_browsing_api_key = "AIzaSyCxIKEwIyckbHKQS4nrKQ1MMizJDyrRrxM"  # ЗАМЕНИТЕ НА РЕАЛЬНЫЙ КЛЮЧ
        self.safe_browsing = SafeBrowsingChecker(self.safe_browsing_api_key, self)

        # ByeDPI
        self.byedpi_process = None
        self.byedpi_enabled = False
        self.ciadpi_path = os.path.join(CURRENT_DIR, "ciadpi.exe")
        self.ciadpi_exists = os.path.isfile(self.ciadpi_path)
        if not self.ciadpi_exists:
            print("[WARN] ciadpi.exe не найден! Режим обхода недоступен.")

        self.create_ui()
        self.load_tabs_state()
        QTimer.singleShot(2000, self.reload_current_tab)
        self.cinema_window = None

        if not self.ciadpi_exists:
            self.byedpi_toggle.setEnabled(False)
            self.byedpi_toggle.setToolTip("Файл ciadpi.exe отсутствует в папке приложения")
            self.statusBar().showMessage("⚠️ ciadpi.exe не найден! Режим обхода недоступен.")

        self.update_proxy_ui(False)

        # Консоль логов (Ctrl+F)
        self.console = None

    def create_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        nav_bar = QWidget()
        nav_bar.setObjectName("navBar")
        nav_bar.setFixedHeight(60)
        nav_layout = QHBoxLayout(nav_bar)
        nav_layout.setContentsMargins(15, 10, 15, 10)
        nav_layout.setSpacing(8)

        # Кнопки навигации (видео-плеер удалён)
        self.btn_back = QPushButton("⬅️")
        self.btn_back.setToolTip("Назад")
        self.btn_back.clicked.connect(self.go_back)

        self.btn_forward = QPushButton("➡️")
        self.btn_forward.setToolTip("Вперёд")
        self.btn_forward.clicked.connect(self.go_forward)

        self.btn_home = QPushButton("🏠 Домой")
        self.btn_home.clicked.connect(self.go_home)

        self.btn_profile = QPushButton("👤 Профиль")
        self.btn_profile.setToolTip("Открыть профиль и инструменты")
        self.btn_profile.clicked.connect(self.open_profile_tab)

        self.btn_tabs = QPushButton("📑 Вкладки")
        self.btn_tabs.setToolTip("Управление вкладками")
        self.tabs_menu = QMenu(self)
        self.btn_tabs.setMenu(self.tabs_menu)
        self.btn_tabs.clicked.connect(self.show_tabs_menu)

        self.btn_new_tab = QPushButton("➕")
        self.btn_new_tab.setToolTip("Новая вкладка")
        self.btn_new_tab.clicked.connect(lambda: self.add_new_tab(HOME_URL))

        # ByeDPI тумблер
        self.byedpi_toggle = IOSToggle()
        self.byedpi_toggle.setToolTip("Включить/выключить обход блокировок через ByeDPI")
        self.byedpi_toggle.toggled.connect(self.toggle_byedpi)

        self.label_proxy = QLabel("🔒")
        self.label_proxy.setStyleSheet("font-size: 10pt; font-weight: normal;")

        proxy_container = QWidget()
        proxy_layout = QHBoxLayout(proxy_container)
        proxy_layout.setContentsMargins(0, 0, 0, 0)
        proxy_layout.setSpacing(6)
        proxy_layout.addWidget(self.byedpi_toggle)
        proxy_layout.addWidget(self.label_proxy)
        proxy_layout.addStretch()

        self.url_bar = QLineEdit()
        self.url_bar.setPlaceholderText("🔍 Введите URL или поисковый запрос")
        self.url_bar.returnPressed.connect(self.navigate_to_url)

        # Кнопки скачивания
        self.btn_download = QPushButton("⬇️ Скачать сайт")
        self.btn_download.setToolTip("Сохранить текущую страницу со всеми ресурсами")
        self.btn_download.clicked.connect(self.download_site)

        self.btn_load = QPushButton("📂 Скачанные")
        self.btn_load.setToolTip("Открыть список скачанных сайтов")
        self.btn_load.clicked.connect(self.open_downloaded_sites)

        nav_layout.addWidget(self.btn_back)
        nav_layout.addWidget(self.btn_forward)
        nav_layout.addWidget(self.btn_home)
        nav_layout.addWidget(self.btn_profile)
        nav_layout.addWidget(self.btn_tabs)
        nav_layout.addWidget(self.btn_new_tab)
        nav_layout.addWidget(self.btn_download)
        nav_layout.addWidget(self.btn_load)
        nav_layout.addWidget(proxy_container)
        nav_layout.addWidget(self.url_bar, 1)

        self.tab_widget = QTabWidget()
        self.tab_widget.setDocumentMode(True)
        self.tab_widget.tabBar().setVisible(False)
        self.tab_widget.currentChanged.connect(self.on_tab_changed)
        main_layout.addWidget(nav_bar)
        main_layout.addWidget(self.tab_widget, 1)

        self.statusBar().showMessage("🚀 Загрузка...")
        self.statusBar().setStyleSheet("border-top: 1px solid rgba(110, 255, 170, 0.2); padding: 5px;")

        # Профиль веб-движка
        web_profile_path = os.path.join(SAVE_DIR, "webprofile")
        os.makedirs(web_profile_path, exist_ok=True)
        self.profile = QWebEngineProfile("freesearch", self)
        self.profile.setPersistentStoragePath(web_profile_path)
        try:
            self.profile.setPasswordStoreEnabled(True)
        except AttributeError:
            pass

        settings = self.profile.settings()
        try:
            settings.setAttribute(QWebEngineSettings.WebAttribute.AutoFillEnabled, True)
        except AttributeError:
            pass

        # Блокировщик рекламы
        self.adblock_interceptor = AdBlockInterceptor()
        self.profile.setUrlRequestInterceptor(self.adblock_interceptor)

        # Скрипт для обхода Rutube
        js_code = """
        (function() {
            window.PRMCDN_DISABLED = true;
            window.rt_ad_blocked = false;
            if (!window.rutube) window.rutube = {};
            window.rutube.adPlayer = { init: function() { return true; }, play: function() { return true; } };
        })();
        """
        script = QWebEngineScript()
        script.setSourceCode(js_code)
        script.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentCreation)
        script.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
        self.profile.scripts().insert(script)

        # Создаём первую вкладку с Safe Browsing
        self.add_new_tab(HOME_URL)
        self.update_tabs_menu()
        self.update_status("Готово")

    def add_new_tab(self, url=None):
        web_view = QWebEngineView()
        page = SafeBrowsingWebEnginePage(self.profile, self, web_view)
        web_view.setPage(page)
        web_view.setUrl(QUrl(url or HOME_URL))
        web_view.urlChanged.connect(lambda qurl, wv=web_view: self.on_url_changed(wv, qurl))
        web_view.loadFinished.connect(lambda ok, wv=web_view: self.on_load_finished(wv))
        settings = web_view.settings()
        settings.setAttribute(settings.WebAttribute.JavascriptEnabled, True)
        settings.setAttribute(settings.WebAttribute.AutoLoadImages, True)
        settings.setAttribute(settings.WebAttribute.ErrorPageEnabled, False)
        settings.setAttribute(settings.WebAttribute.PluginsEnabled, False)
        settings.setAttribute(settings.WebAttribute.LocalStorageEnabled, True)

        index = self.tab_widget.addTab(web_view, "Новая вкладка")
        self.tab_widget.setCurrentIndex(index)
        self.update_tabs_menu()
        self.save_tabs_state()
        return web_view

    # ---------- НАВИГАЦИЯ ----------
    def go_back(self):
        wv = self.get_current_web_view()
        if wv and wv.history().canGoBack():
            wv.back()
        else:
            for i in range(self.tab_widget.count()):
                widget = self.tab_widget.widget(i)
                if isinstance(widget, QWebEngineView) and widget.history().canGoBack():
                    self.tab_widget.setCurrentIndex(i)
                    widget.back()
                    return

    def go_forward(self):
        wv = self.get_current_web_view()
        if wv and wv.history().canGoForward():
            wv.forward()
        else:
            for i in range(self.tab_widget.count()):
                widget = self.tab_widget.widget(i)
                if isinstance(widget, QWebEngineView) and widget.history().canGoForward():
                    self.tab_widget.setCurrentIndex(i)
                    widget.forward()
                    return

    def go_home(self):
        for i in range(self.tab_widget.count()):
            widget = self.tab_widget.widget(i)
            if isinstance(widget, QWebEngineView):
                self.tab_widget.setCurrentIndex(i)
                widget.setUrl(QUrl(HOME_URL))
                return
        self.add_new_tab(HOME_URL)

    def load_url(self, url):
        wv = self.get_current_web_view()
        if wv:
            wv.setUrl(QUrl(url))
        else:
            self.add_new_tab(url)

    def navigate_to_url(self):
        text = self.url_bar.text().strip()
        if not text:
            return
        if not text.startswith(("http://", "https://")):
            if "." in text and " " not in text:
                text = "https://" + text
            else:
                search_url = f"https://duckduckgo.com/?q={text.replace(' ', '+')}"
                self.load_url(search_url)
                return
        self.load_url(text)

    def update_nav_buttons(self, web_view):
        if web_view:
            self.btn_back.setEnabled(web_view.history().canGoBack())
            self.btn_forward.setEnabled(web_view.history().canGoForward())

    def reload_current_tab(self):
        wv = self.get_current_web_view()
        if wv:
            wv.reload()
            self.statusBar().showMessage("Страница перезагружена")

    # ---------- ВКЛАДКИ ----------
    def load_tabs_state(self):
        try:
            import requests
            resp = requests.get('http://127.0.0.1:5000/api/tabs/get', timeout=1)
            if resp.status_code == 200:
                data = resp.json()
                tabs = data.get('tabs', [])
                current_index = data.get('current_index', 0)
                if tabs:
                    while self.tab_widget.count() > 0:
                        self.tab_widget.removeTab(0)
                    for tab in tabs:
                        url = tab.get('url', HOME_URL)
                        self.add_new_tab(url)
                    if current_index < self.tab_widget.count():
                        self.tab_widget.setCurrentIndex(current_index)
                    else:
                        self.tab_widget.setCurrentIndex(0)
                    self.update_tabs_menu()
                    return
        except Exception as e:
            print(f"Ошибка загрузки вкладок: {e}")
        if self.tab_widget.count() == 0:
            self.add_new_tab(HOME_URL)

    def save_tabs_state(self):
        tabs_data = []
        for i in range(self.tab_widget.count()):
            widget = self.tab_widget.widget(i)
            if isinstance(widget, QWebEngineView):
                url = widget.url().toString()
                tabs_data.append({"url": url})
        current_index = self.tab_widget.currentIndex()
        try:
            import requests
            requests.post('http://127.0.0.1:5000/api/tabs/save',
                          json={"tabs": tabs_data, "current_index": current_index},
                          timeout=1)
        except Exception as e:
            print(f"Ошибка сохранения вкладок: {e}")

    def get_current_web_view(self):
        widget = self.tab_widget.currentWidget()
        if isinstance(widget, QWebEngineView):
            return widget
        return None

    def on_tab_changed(self, index):
        if index >= 0:
            widget = self.tab_widget.widget(index)
            if isinstance(widget, QWebEngineView):
                self.url_bar.setText(widget.url().toString())
                self.update_nav_buttons(widget)
            self.save_tabs_state()

    def on_url_changed(self, web_view, qurl):
        if web_view == self.get_current_web_view():
            self.url_bar.setText(qurl.toString())
            title = web_view.page().title() or "Новая вкладка"
            index = self.tab_widget.indexOf(web_view)
            if index >= 0:
                self.tab_widget.setTabText(index, title)
                self.update_tabs_menu()

    def on_load_finished(self, web_view):
        if web_view == self.get_current_web_view():
            self.update_nav_buttons(web_view)
        title = web_view.page().title() or "Новая вкладка"
        index = self.tab_widget.indexOf(web_view)
        if index >= 0:
            self.tab_widget.setTabText(index, title)
            self.update_tabs_menu()

    def close_current_tab(self):
        if self.tab_widget.count() <= 1:
            self.add_new_tab(HOME_URL)
        else:
            current = self.tab_widget.currentIndex()
            self.tab_widget.removeTab(current)
            self.update_tabs_menu()
            self.save_tabs_state()

    def switch_to_tab(self, index):
        if 0 <= index < self.tab_widget.count():
            self.tab_widget.setCurrentIndex(index)
            self.update_tabs_menu()

    def update_tabs_menu(self):
        self.tabs_menu.clear()
        for i in range(self.tab_widget.count()):
            widget = self.tab_widget.widget(i)
            if isinstance(widget, QWebEngineView):
                title = widget.page().title() or f"Вкладка {i+1}"
            elif isinstance(widget, ProfileWidget):
                title = "👤 Профиль"
            else:
                title = "Вкладка"
            if len(title) > 40:
                title = title[:40] + "..."
            action = QAction(title, self)
            action.setData(i)
            action.triggered.connect(lambda checked, idx=i: self.switch_to_tab(idx))
            self.tabs_menu.addAction(action)

        self.tabs_menu.addSeparator()
        new_tab_action = QAction("➕ Новая вкладка", self)
        new_tab_action.triggered.connect(lambda: self.add_new_tab(HOME_URL))
        self.tabs_menu.addAction(new_tab_action)

        close_tab_action = QAction("❌ Закрыть вкладку", self)
        close_tab_action.triggered.connect(self.close_current_tab)
        self.tabs_menu.addAction(close_tab_action)

    def show_tabs_menu(self):
        pass

    def update_status(self, msg):
        self.statusBar().showMessage(msg)

    # ---------- ПРОФИЛЬ ----------
    def open_profile_tab(self):
        for i in range(self.tab_widget.count()):
            widget = self.tab_widget.widget(i)
            if isinstance(widget, ProfileWidget):
                self.tab_widget.setCurrentIndex(i)
                return
        profile_widget = ProfileWidget(self, self)
        index = self.tab_widget.addTab(profile_widget, "👤 Профиль")
        self.tab_widget.setCurrentIndex(index)

    # ---------- ТЕМА ----------
    def apply_theme(self, theme):
        if theme == "light":
            bg = "#f0f4f8"
            text = "#1a202c"
            accent = "#2b6cb0"
            input_bg = "#ffffff"
            input_border = "#a0aec0"
        elif theme == "dark":
            bg = "#0a0f14"
            text = "#eef2ff"
            accent = "#6effaa"
            input_bg = "#1e2936"
            input_border = "#6effaa"
        else:
            bg = "#0a0f14"
            text = "#eef2ff"
            accent = "#6effaa"
            input_bg = "#1e2936"
            input_border = "#6effaa"

        self.setStyleSheet(f"""
            QMainWindow {{ background-color: {bg}; }}
            QWidget {{ background-color: {bg}; color: {text}; font-family: 'Segoe UI'; font-size: 9pt; }}
            QPushButton {{
                background: transparent; border: none; color: {accent};
                font-size: 16px; padding: 8px 14px; border-radius: 20px; font-weight: 600;
            }}
            QPushButton:hover {{ background: rgba(110, 255, 170, 0.15); color: #aaffcc; }}
            QLineEdit {{
                background: {input_bg}; border: 1px solid {input_border};
                border-radius: 30px; padding: 8px 20px; color: {text}; font-size: 14px;
                selection-background-color: {accent};
            }}
            QLineEdit:focus {{ border: 1px solid {accent}; background: {input_bg}; }}
            QTabWidget::pane {{ border: none; background: {bg}; }}
            QMenu {{ background-color: {input_bg}; color: {text}; border: 1px solid {accent}; border-radius: 12px; }}
            QMenu::item {{ padding: 8px 20px; border-radius: 8px; }}
            QMenu::item:selected {{ background: rgba(110, 255, 170, 0.2); }}
            QStatusBar {{ background-color: {bg}; color: {text}; border-top: 1px solid {accent}; padding: 5px; }}
            QWidget#navBar {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                            stop:0 #0f1724, stop:1 #1a2a3a);
                border-bottom: 2px solid {accent};
            }}
        """)

    # ---------- СКАЧИВАНИЕ САЙТОВ ----------
    def open_downloaded_sites(self):
        if not os.path.exists(LOAD_DIR) or not os.listdir(LOAD_DIR):
            QMessageBox.information(self, "Скачанные сайты", "Нет скачанных сайтов.")
            return
        sites = [d for d in os.listdir(LOAD_DIR) if os.path.isdir(os.path.join(LOAD_DIR, d))]
        if not sites:
            QMessageBox.information(self, "Скачанные сайты", "Нет скачанных сайтов.")
            return
        item, ok = QInputDialog.getItem(self, "Скачанные сайты", "Выберите сайт:", sites, 0, False)
        if ok and item:
            site_path = os.path.join(LOAD_DIR, item, "index.html")
            if os.path.exists(site_path):
                self.add_new_tab(f"file:///{site_path.replace(os.sep, '/')}")
            else:
                QMessageBox.warning(self, "Ошибка", "Файл index.html не найден в этой папке.")

    def download_site(self):
        wv = self.get_current_web_view()
        if not wv:
            self.statusBar().showMessage("❌ Нет активной вкладки")
            return
        url = wv.url().toString()
        if url.startswith("http://127.0.0.1:5000/index.html") or \
           url.startswith("http://127.0.0.1:5000/profile.html") or \
           url == "about:blank":
            QMessageBox.information(self, "Скачивание", "Это локальная страница приложения, скачивание не требуется.")
            return
        self.btn_download.setEnabled(False)
        self.btn_download.setText("⏳ Загрузка...")
        self.statusBar().showMessage("⏳ Получение HTML и ресурсов...")
        wv.page().toHtml(lambda html: self._save_site(html, url))

    def _save_site(self, html, url):
        try:
            parsed = urllib.parse.urlparse(url)
            domain = parsed.netloc or "site"
            domain = "".join(c for c in domain if c.isalnum() or c in "._-")
            site_dir = os.path.join(LOAD_DIR, domain)
            os.makedirs(site_dir, exist_ok=True)
            html_path = os.path.join(site_dir, "index.html")
            with open(html_path, 'w', encoding='utf-8') as f:
                f.write(html)
            self._download_resources(html, url, site_dir)
            self.btn_download.setEnabled(True)
            self.btn_download.setText("⬇️ Скачать сайт")
            self.statusBar().showMessage(f"✅ Сайт сохранён в {site_dir}")
            QMessageBox.information(self, "Успешно", f"Сайт сохранён в папку:\n{site_dir}")
        except Exception as e:
            self.btn_download.setEnabled(True)
            self.btn_download.setText("⬇️ Скачать сайт")
            QMessageBox.critical(self, "Ошибка", f"Не удалось сохранить сайт:\n{str(e)}")
            self.statusBar().showMessage("❌ Ошибка сохранения")

    def _download_resources(self, html, base_url, site_dir):
        soup = BeautifulSoup(html, 'html.parser')
        base_parsed = urllib.parse.urlparse(base_url)
        base_domain = f"{base_parsed.scheme}://{base_parsed.netloc}"
        css_dir = os.path.join(site_dir, "css")
        js_dir = os.path.join(site_dir, "js")
        img_dir = os.path.join(site_dir, "img")
        os.makedirs(css_dir, exist_ok=True)
        os.makedirs(js_dir, exist_ok=True)
        os.makedirs(img_dir, exist_ok=True)
        resources = []
        for link in soup.find_all('link', rel='stylesheet'):
            href = link.get('href')
            if href:
                resources.append(('css', href, link, 'href'))
        for script in soup.find_all('script', src=True):
            src = script.get('src')
            if src:
                resources.append(('js', src, script, 'src'))
        for img in soup.find_all('img', src=True):
            src = img.get('src')
            if src:
                resources.append(('img', src, img, 'src'))
        for res_type, src, tag, attr in resources:
            try:
                full_url = urllib.parse.urljoin(base_url, src)
                if not full_url.startswith(base_domain):
                    continue
                parsed = urllib.parse.urlparse(full_url)
                filename = os.path.basename(parsed.path) or "resource"
                if not filename:
                    continue
                if res_type == 'css':
                    local_path = os.path.join(css_dir, filename)
                elif res_type == 'js':
                    local_path = os.path.join(js_dir, filename)
                elif res_type == 'img':
                    local_path = os.path.join(img_dir, filename)
                else:
                    continue
                try:
                    import requests
                    resp = requests.get(full_url, timeout=10, headers={'User-Agent': 'Mozilla/5.0'})
                    if resp.status_code == 200:
                        with open(local_path, 'wb') as f:
                            f.write(resp.content)
                        relative_path = os.path.relpath(local_path, site_dir).replace('\\', '/')
                        tag[attr] = relative_path
                    else:
                        print(f"Не удалось скачать {full_url}: {resp.status_code}")
                except Exception as e:
                    print(f"Ошибка скачивания {full_url}: {e}")
            except Exception as e:
                print(f"Ошибка обработки ресурса {src}: {e}")
        with open(os.path.join(site_dir, "index.html"), 'w', encoding='utf-8') as f:
            f.write(str(soup))

    # ---------- BYEDPI ----------
    def toggle_byedpi(self, state):
        if not self.ciadpi_exists:
            self.byedpi_toggle.set_checked(False, animate=False)
            return
        if state:
            self.enable_byedpi()
        else:
            self.disable_byedpi()

    def enable_byedpi(self):
        if self.byedpi_process is not None and self.byedpi_process.poll() is None:
            return
        try:
            self.byedpi_process = subprocess.Popen(
                [self.ciadpi_path, "-i", "127.0.0.1", "-p", "1080", "-r", "1", "-e", "1"],
                creationflags=subprocess.CREATE_NO_WINDOW,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
        except Exception as e:
            self.statusBar().showMessage(f"❌ Ошибка запуска ciadpi: {e}")
            self.update_proxy_ui(False)
            return

        time.sleep(0.5)
        if self.byedpi_process.poll() is not None:
            self.statusBar().showMessage("❌ ciadpi.exe завершился сразу после запуска")
            self.update_proxy_ui(False)
            self.byedpi_process = None
            return

        self.set_proxy(True)
        self.byedpi_enabled = True
        self.update_proxy_ui(True)
        self.statusBar().showMessage("✅ ByeDPI включён, прокси SOCKS5 127.0.0.1:1080")
        self.reload_current_tab()

    def disable_byedpi(self):
        if self.byedpi_process is not None:
            try:
                self.byedpi_process.terminate()
                try:
                    self.byedpi_process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    self.byedpi_process.kill()
                    self.byedpi_process.wait()
            except Exception:
                pass
            self.byedpi_process = None

        self.set_proxy(False)
        self.byedpi_enabled = False
        self.update_proxy_ui(False)
        self.statusBar().showMessage("⛔ ByeDPI выключен, прямое соединение")
        self.reload_current_tab()

    def set_proxy(self, enable):
        if enable:
            proxy = QNetworkProxy()
            proxy.setType(QNetworkProxy.ProxyType.Socks5Proxy)
            proxy.setHostName("127.0.0.1")
            proxy.setPort(1080)
            QNetworkProxy.setApplicationProxy(proxy)
            print("Сеть перенаправлена на ByeDPI")
        else:
            QNetworkProxy.setApplicationProxy(QNetworkProxy(QNetworkProxy.ProxyType.NoProxy))
            print("Сеть возвращена в исходный режим")

    def cleanup_byedpi(self):
        if self.byedpi_process is not None:
            try:
                self.byedpi_process.terminate()
                try:
                    self.byedpi_process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    self.byedpi_process.kill()
                    self.byedpi_process.wait()
            except Exception:
                pass
            self.byedpi_process = None
            self.byedpi_enabled = False
            self.set_proxy(False)

    def update_proxy_ui(self, enabled):
        self.byedpi_toggle.set_checked(enabled, animate=True)
        if enabled:
            self.label_proxy.setText("🔓")
            self.label_proxy.setStyleSheet("color: #6effaa; font-weight: bold; font-size: 10pt;")
        else:
            self.label_proxy.setText("🔒")
            self.label_proxy.setStyleSheet("color: inherit; font-weight: normal; font-size: 10pt;")

    # ---------- КОНСОЛЬ ЛОГОВ (Ctrl+F) ----------
    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_F and event.modifiers() == Qt.KeyboardModifier.ControlModifier:
            if self.console is None:
                self.console = QWidget()
                self.console.setWindowTitle("📋 Консоль логов")
                self.console.setGeometry(200, 200, 800, 500)
                self.console.setWindowFlags(Qt.WindowType.WindowStaysOnTopHint)
                layout = QVBoxLayout(self.console)
                self.console_text = QTextEdit()
                self.console_text.setReadOnly(True)
                self.console_text.setFont(QFont("Courier New", 10))
                layout.addWidget(self.console_text)
                clear_btn = QPushButton("Очистить")
                clear_btn.clicked.connect(self.console_text.clear)
                layout.addWidget(clear_btn)
                self.console_text.append("<b>Консоль логов запущена. Логи будут собираться...</b>")
            self.console.show()
            self.console.raise_()
            event.accept()
        else:
            super().keyPressEvent(event)

    def append_log(self, message, level="INFO"):
        if self.console is not None and hasattr(self, 'console_text'):
            timestamp = datetime.now().strftime("%H:%M:%S")
            color_map = {
                "INFO": "#6effaa",
                "WARN": "#feca57",
                "ERROR": "#ff6b6b",
                "DEBUG": "#54a0ff"
            }
            color = color_map.get(level, "#ffffff")
            self.console_text.append(f'<span style="color:{color}">[{timestamp}] [{level}]</span> {message}')

    # ---------- ЗАКРЫТИЕ ----------
    def closeEvent(self, event):
        self.cleanup_byedpi()
        self.save_tabs_state()
        if self.console is not None:
            self.console.close()
        super().closeEvent(event)

# ================================================================
#  ЗАПУСК
# ================================================================
if __name__ == '__main__':
    # Запуск Flask в отдельном потоке
    def run_flask():
        try:
            app.run(host='127.0.0.1', port=PORT, debug=False, use_reloader=False)
        except Exception as e:
            print(f"Ошибка Flask: {e}")

    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    print("[LOG] Поток Flask запущен")

    # Ждём готовности Flask
    for _ in range(30):
        try:
            import requests
            requests.get(f'http://127.0.0.1:{PORT}', timeout=0.5)
            print("[LOG] Flask готов")
            break
        except:
            time.sleep(0.1)
    else:
        QMessageBox.critical(None, "Ошибка", "Не удалось запустить внутренний сервер.")
        sys.exit(1)

    app_qt = QApplication(sys.argv)
    window = BrowserWindow()
    window.show()
    sys.exit(app_qt.exec())
