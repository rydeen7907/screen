"""
監視機能付きスクリーンセーバー
"""
import pygame
import random
import sys
import json
import hashlib # パスワードのハッシュ化用
import os
import colorsys # RGB<->HSV変換用
import math
import shutil # ファイルのバックアップ用
import threading
import datetime
import logging # ロギング用
import logging.handlers # ロギングのハンドラ用
import atexit # 終了時のクリーンアップ用
import cv2

# GUI表示のために早期にインポート
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog, colorchooser # 色選択ダイアログ用

from PIL import Image
import pystray # システムトレイアイコン用
if sys.platform == "win32":
    try:
        import psutil # Windowsのアイドル時間取得用
    except ImportError:
        psutil = None

    try:
        # pywin32ライブラリのコンポーネント
        import win32api
        import win32crypt
    except ImportError:
        win32api = None
        win32crypt = None

# カメラ監視のためにOpenCVをインポート
try:
    import cv2
except ImportError:
    cv2 = None

def get_base_path():
    """
    実行ファイルのパスを取得する。
    PyInstallerでexe化された場合と、スクリプト実行の場合の両方に対応。
    """
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        # PyInstallerでバンドルされた場合
        return os.path.dirname(sys.executable)
    else:
        # 通常のPythonスクリプトとして実行された場合
        return os.path.dirname(os.path.abspath(__file__))

BASE_PATH = get_base_path()

# --- 定数 ---
TRAY_QUIT_EVENT = pygame.USEREVENT + 1 # トレイアイコンからの終了専用イベント
DEFAULT_BALL_COUNT = 10
BLACK = (0, 0, 0)
MIN_BALL_RADIUS = 10
MAX_BALL_RADIUS = 50
# スクリーンセーバーに切り替わるまでの無操作時間 (ミリ秒)
DEFAULT_MAX_VELOCITY = 3  # ボールの最大速度
IDLE_TIMEOUT = 5000  # 5秒
DEFAULT_SLIDESHOW_FOLDER = ""  # 空文字列は無効なフォルダとして扱う
DEFAULT_SLIDESHOW_INTERVAL = 5  # 秒

FADE_DURATION = 1000 # スライドショーのクロスフェード時間（ミリ秒）

DEFAULT_LINE_COUNT = 15  # ラインアートの線の数
DEFAULT_LINE_SPEED = 3

# --- マトリックスモードのデフォルト値 ---
DEFAULT_MATRIX_FONT_SIZE = 18
DEFAULT_MATRIX_SPEED = 3
DEFAULT_MATRIX_FONT = "consolas" # 等幅フォントの例。見つからない場合はOSのデフォルトが使われる

# --- 時刻表示のデフォルト値 ---
DEFAULT_CLOCK_ENABLED = True
DEFAULT_CLOCK_POSITION = "bottomright" # topleft, topright, bottomleft, bottomright
DEFAULT_CLOCK_COLOR = (200, 200, 200) # 明るいグレー
DEFAULT_CLOCK_FONT_SIZE = 24

# --- プレビュー用定数 ---
PREVIEW_WIDTH = 350
PREVIEW_HEIGHT = 200
PREVIEW_BALL_COUNT = 5  # プレビュー用のボールの数
PREVIEW_LINE_COUNT = 3

# --- パスワードUIのデフォルト値 ---
DEFAULT_PASSWORD_UI_POSITION = "center" # center, top, bottom
DEFAULT_PASSWORD_UI_FONT_SIZE = 40
DEFAULT_PASSWORD_UI_PROMPT_COLOR = (255, 255, 255)
DEFAULT_PASSWORD_UI_INPUT_COLOR = (255, 255, 255)
DEFAULT_PASSWORD_UI_WARNING_COLOR = (255, 100, 100)
DEFAULT_PASSWORD_UI_INFO_COLOR = (180, 180, 180)

# --- カメラ監視のデフォルト値 ---
DEFAULT_CAMERA_ENABLED = False
DEFAULT_CAMERA_DEVICE_INDEX = 0
DEFAULT_CAMERA_CAPTURE_FOLDER = "captures"
DEFAULT_CAMERA_MOTION_THRESHOLD = 1000 # 動き検知の閾値 (面積)
DEFAULT_CAMERA_CAPTURE_RETENTION_DAYS = 7 # キャプチャ画像の保存日数
DEFAULT_AUTO_RESTART_ON_IDLE = True # 待機中に無操作で再開するか
DEFAULT_GUI_THEME = "vista" if sys.platform == "win32" else "clam"


# --- モード定義 ---
class SaverMode:
    BALLS = "balls"
    SLIDESHOW = "slideshow"
    LINE_ART = "line_art"
    MATRIX = "matrix"

DEFAULT_SAVER_MODE = SaverMode.BALLS

# --- パーティクル色モード定義 ---
class ParticleColorMode:
    LINKED = "linked"
    RAINBOW = "rainbow"

DEFAULT_PARTICLE_COLOR_MODE = ParticleColorMode.RAINBOW


# --- 設定キー定義 ---
class CfgKey:
    SAVER_MODE = "saver_mode"
    IDLE_TIMEOUT = "idle_timeout"
    BALL_COUNT = "ball_count"
    MAX_VELOCITY = "max_velocity"
    SLIDESHOW_FOLDER = "slideshow_folder"
    SLIDESHOW_INTERVAL = "slideshow_interval"
    MATRIX_FONT_SIZE = "matrix_font_size"
    MATRIX_SPEED = "matrix_speed"
    MATRIX_FONT = "matrix_font"
    LINE_COUNT = "line_count"
    LINE_SPEED = "line_speed"
    PASSWORD_ENABLED = "password_enabled"
    PASSWORD_HASH = "password_hash"
    PASSWORD_UI_POSITION = "password_ui_position"
    PASSWORD_UI_FONT_SIZE = "password_ui_font_size"
    PASSWORD_UI_PROMPT_COLOR = "password_ui_prompt_color"
    PASSWORD_UI_INPUT_COLOR = "password_ui_input_color"
    PASSWORD_UI_WARNING_COLOR = "password_ui_warning_color"
    PASSWORD_UI_INFO_COLOR = "password_ui_info_color"
    # --- 時刻表示設定 ---
    CLOCK_ENABLED = "clock_enabled"
    CLOCK_POSITION = "clock_position"
    CLOCK_COLOR = "clock_color"
    CLOCK_FONT_SIZE = "clock_font_size"
    WALL_SPARK_ENABLED = "wall_spark_enabled"
    PARTICLE_COLOR_MODE = "particle_color_mode"
    # --- カメラ監視設定 ---
    CAMERA_ENABLED = "camera_enabled"
    CAMERA_DEVICE_INDEX = "camera_device_index"
    CAMERA_CAPTURE_FOLDER = "camera_capture_folder"
    CAMERA_MOTION_THRESHOLD = "camera_motion_threshold"
    CAMERA_CAPTURE_RETENTION_DAYS = "camera_capture_retention_days"
    AUTO_RESTART_ON_IDLE = "auto_restart_on_idle"
    GUI_THEME = "gui_theme"

SETTINGS_FILE = os.path.join(BASE_PATH, "settings.json")
SETTINGS_BACKUP_FILE = SETTINGS_FILE + ".bak"

def setup_logging():
    """ロギングを設定し、ファイルとコンソールの両方に出力する"""
    log_formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
    log_file = os.path.join(BASE_PATH, 'screensaver.log')

    # ルートロガーを取得
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    # 既存のハンドラをクリアして、重複したログ出力を防ぐ
    if logger.hasHandlers():
        logger.handlers.clear()

    # ファイルハンドラ (ローテーション機能付き)
    # 1MBごとにファイルを分け、5世代までバックアップ
    try:
        file_handler = logging.handlers.RotatingFileHandler(
            log_file, maxBytes=1024*1024, backupCount=5, encoding='utf-8')
        file_handler.setFormatter(log_formatter)
        logger.addHandler(file_handler)
    except Exception as e:
        print(f"ログファイルハンドラの設定に失敗しました: {e}")

    # コンソールハンドラ
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(log_formatter)
    logger.addHandler(console_handler)


def save_settings(settings):
    """設定をファイルに保存し、成功したらバックアップを作成する。"""
    try:
        # 非Windows環境でも読みやすいようにインデントを追加
        settings_json = json.dumps(settings, indent=4)
        if sys.platform == "win32" and win32crypt:
            # Windowsの場合、DPAPIで現在のユーザーに紐づけて暗号化
            data_blob = win32crypt.CryptProtectData(settings_json.encode("utf-8"), "settings", None, None, None, 0)
            with open(SETTINGS_FILE, "wb") as f:
                f.write(data_blob)
        else:
            # Windows以外は平文で保存 (エンコーディングを明記)
            with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
                f.write(settings_json)
        
        # メインファイルの保存が成功したらバックアップを作成
        try:
            shutil.copy2(SETTINGS_FILE, SETTINGS_BACKUP_FILE)
        except Exception as e:
            # バックアップ作成の失敗は致命的ではないので、警告のみ表示
            logging.warning(f"設定ファイルのバックアップ作成に失敗しました: {e}")

    except PermissionError as e:
        raise IOError(f"設定ファイル '{SETTINGS_FILE}' への書き込み権限がありません。") from e
    except Exception as e:
        raise Exception(f"設定の保存中に予期せぬエラーが発生しました: {e}") from e

def _load_from_backup():
    """バックアップファイルから設定を読み込み、メインファイルを復元する"""
    logging.info(f"バックアップ '{SETTINGS_BACKUP_FILE}' からの復元を試みます...")
    if not os.path.exists(SETTINGS_BACKUP_FILE):
        logging.error("バックアップファイルが見つかりませんでした。")
        return {}
    try:
        # バックアップファイルを読み込む
        if sys.platform == "win32" and win32crypt:
            with open(SETTINGS_BACKUP_FILE, "rb") as f:
                data_blob = f.read()
            try:
                _, decrypted_data = win32crypt.CryptUnprotectData(data_blob, None, None, None, 0)
                settings = json.loads(decrypted_data.decode("utf-8"))
            except Exception:
                settings = json.loads(data_blob.decode("utf-8"))
        else:
            with open(SETTINGS_BACKUP_FILE, "r", encoding="utf-8") as f:
                settings = json.load(f)
        
        logging.info("バックアップからの復元に成功しました。")
        # 復元した設定でメインファイルを上書き保存する
        save_settings(settings)
        return settings
    except Exception as e:
        logging.error(f"バックアップファイル '{SETTINGS_BACKUP_FILE}' も読み込めませんでした: {e}", exc_info=True)
        return {}

def load_settings():
    """ファイルから設定を読み込む。Windowsでは内容を復号する。"""
    if not os.path.exists(SETTINGS_FILE):
        return _load_from_backup()
    try:
        if sys.platform == "win32" and win32crypt:
            with open(SETTINGS_FILE, "rb") as f:
                data_blob = f.read()
            try:
                # DPAPIでの復号を試みる
                _, decrypted_data = win32crypt.CryptUnprotectData(data_blob, None, None, None, 0)
                return json.loads(decrypted_data.decode("utf-8"))
            except Exception: # 復号失敗
                # 復号に失敗した場合、平文のJSONファイルかもしれないので、その読み込みを試みる
                # (暗号化導入前の古い設定ファイルとの互換性のため)
                try:
                    return json.loads(data_blob.decode("utf-8"))
                except Exception: # 平文としても読めない場合
                    logging.error(f"設定ファイル '{SETTINGS_FILE}' が破損しているか、読み取れない形式です。")
                    return _load_from_backup()
        else:
            # Windows以外は平文で読み込み
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        logging.error(f"設定ファイル '{SETTINGS_FILE}' の読み込みに失敗しました: {e}", exc_info=True)
        return _load_from_backup()

def force_shutdown(settings):
    """OSに応じて強制的にシャットダウンを実行し、その前に画像をキャプチャする"""
    logging.warning("3回パスワードを間違えたため、シャットダウンを開始します。")

    # --- カメラキャプチャ処理を追加 ---
    camera_enabled = settings.get(CfgKey.CAMERA_ENABLED, False)
    if camera_enabled and cv2:
        device_index = settings.get(CfgKey.CAMERA_DEVICE_INDEX, 0)
        capture_folder = settings.get(CfgKey.CAMERA_CAPTURE_FOLDER, "captures")
        if not os.path.isabs(capture_folder):
            capture_folder = os.path.join(BASE_PATH, capture_folder)

        # フォルダが存在しない場合は作成
        if not os.path.exists(capture_folder):
            try:
                os.makedirs(capture_folder)
            except OSError as e:
                logging.error(f"キャプチャ保存先フォルダの作成に失敗しました: {e}")

        cap = cv2.VideoCapture(device_index, cv2.CAP_DSHOW)
        if cap.isOpened():
            ret, frame = cap.read()
            if ret:
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_shutdown")
                filename = os.path.join(capture_folder, f"capture_{timestamp}.jpg")
                cv2.imwrite(filename, frame)
                logging.info(f"シャットダウン前に画像を保存しました: {filename}")
            cap.release()
        else:
            logging.error(f"カメラデバイス {device_index} を開けませんでした。")

    if sys.platform == "win32":
        # Windowsの場合: /s=シャットダウン, /f=強制, /t 1=1秒後
        os.system("shutdown /s /f /t 1")
    elif sys.platform in ["linux", "linux2", "darwin"]:
        # LinuxやmacOSの場合
        # 環境によってはsudo権限で実行する必要があります
        os.system("shutdown -h now")
    else:
        pass # print(f"お使いのOS ({sys.platform}) での自動シャットダウンはサポートされていません。")

def cleanup_old_captures(folder, retention_days):
    """指定された日数より古いキャプチャファイルを削除する"""
    if retention_days <= 0: # 0以下の場合は無期限として何もしない
        return
    if not os.path.isdir(folder):
        return

    now = datetime.datetime.now()
    cutoff = now - datetime.timedelta(days=retention_days)

    try:
        for filename in os.listdir(folder):
            file_path = os.path.join(folder, filename)
            if os.path.isfile(file_path):
                try:
                    file_mod_time = datetime.datetime.fromtimestamp(os.path.getmtime(file_path))
                    if file_mod_time < cutoff:
                        os.remove(file_path)
                        logging.info(f"古いファイルを削除しました: {file_path}")
                except Exception as e:
                    logging.warning(f"ファイル処理中にエラーが発生しました ({file_path}): {e}")
    except Exception as e:
        logging.error(f"キャプチャフォルダのスキャン中にエラーが発生しました ({folder}): {e}")

def exit_action(icon, item):
    """トレイアイコンの終了アクション"""
    icon.stop()
    # カスタムの終了イベントをPygameのメインループに送る
    pygame.event.post(pygame.event.Event(TRAY_QUIT_EVENT))

def setup_tray_icon():
    """システムトレイにアイコンをセットアップし、別スレッドで実行する"""
    global tray_icon
    icon_path = None
    image = None

    # まず.icoファイルを検索する
    try:
        for filename in os.listdir(BASE_PATH):
            if filename.lower().endswith('.ico'):
                icon_path = os.path.join(BASE_PATH, filename)
                break  # 最初に見つかった.icoファイルを使用
    except Exception as e:
        logging.warning(f"アイコンファイル検索中にエラーが発生しました: {e}")

    # .icoが見つからなければ.pngファイルを探す
    if not icon_path:
        try:
            for filename in os.listdir(BASE_PATH):
                if filename.lower().endswith('.png'):
                    icon_path = os.path.join(BASE_PATH, filename)
                    break  # 最初に見つかった.pngファイルを使用
        except Exception as e:
            logging.warning(f"アイコンファイル検索中にエラーが発生しました: {e}")

    # 見つかったパスから画像を読み込む
    if icon_path:
        try:
            image = Image.open(icon_path)
            logging.info(f"トレイアイコンを読み込みました: {icon_path}")
        except Exception as e:
            logging.warning(f"トレイアイコン画像の読み込み中にエラーが発生しました: {e}")

    # 画像が読み込めなかった場合、代替画像を生成
    if image is None:
        image = Image.new('RGB', (64, 64), 'blue') # アイコンが見つからない場合の代替

    menu = (pystray.MenuItem("完全に終了", exit_action),)
    tray_icon = pystray.Icon("screensaver", image, "Python Screensaver", menu)
    tray_icon.run()

def get_image_files(folder):
    """指定されたフォルダからサポートされている画像ファイルのリストを取得する"""
    supported_formats = (".png", ".jpg", ".jpeg", ".bmp", ".gif")
    try:
        if not folder or not os.path.isdir(str(folder)):
            return []
        return [os.path.join(folder, f) for f in os.listdir(folder) if f.lower().endswith(supported_formats)]
    except (PermissionError, OSError) as e:
        logging.error(f"画像フォルダのスキャン中にエラーが発生しました: {folder}, error: {e}")
        return []

def load_and_scale_image(path, screen_width, screen_height):
    """画像を読み込み、アスペクト比を維持して画面に合うようにスケーリングする"""
    try:
        img = pygame.image.load(path)
        img_rect = img.get_rect()

        # アスペクト比を維持してスケーリング係数を計算
        scale_w = screen_width / img_rect.width
        scale_h = screen_height / img_rect.height
        scale = min(scale_w, scale_h)

        new_width = int(img_rect.width * scale)
        new_height = int(img_rect.height * scale)

        # 高品質なスケーリング
        return pygame.transform.smoothscale(img, (new_width, new_height))
    except pygame.error as e:
        logging.error(f"画像の読み込みまたはスケーリングに失敗しました: {path}, error: {e}")
        return None


class Line:
    """ラインアートの線分を管理するクラス"""
    def __init__(self, max_speed, screen_width, screen_height):
        """線の初期化"""
        self.screen_width = screen_width
        self.screen_height = screen_height

        # 2つの端点が画面内に収まるように初期位置を設定
        self.x1 = random.randrange(0, self.screen_width)
        self.y1 = random.randrange(0, self.screen_height)
        self.x2 = random.randrange(0, self.screen_width)
        self.y2 = random.randrange(0, self.screen_height)

        self.color = (random.randrange(50, 256), random.randrange(50, 256), random.randrange(50, 256))
        self.width = random.randint(1, 3)

        # 0を除いた速度の選択肢を生成
        max_s = int(max_speed)
        velocity_choices = list(range(-max_s, 0)) + list(range(1, max_s + 1))
        if not velocity_choices: velocity_choices = [-1, 1]

        # 各端点の速度
        self.dx1 = random.choice(velocity_choices)
        self.dy1 = random.choice(velocity_choices)
        self.dx2 = random.choice(velocity_choices)
        self.dy2 = random.choice(velocity_choices)

    def move(self):
        """線の両端を移動させ、壁で反射させる"""
        # 端点1の移動
        self.x1 += self.dx1
        self.y1 += self.dy1
        if self.x1 <= 0 or self.x1 >= self.screen_width: self.dx1 *= -1
        if self.y1 <= 0 or self.y1 >= self.screen_height: self.dy1 *= -1

        # 端点2の移動
        self.x2 += self.dx2
        self.y2 += self.dy2
        if self.x2 <= 0 or self.x2 >= self.screen_width: self.dx2 *= -1
        if self.y2 <= 0 or self.y2 >= self.screen_height: self.dy2 *= -1

    def draw(self, screen):
        """線を画面に描画する"""
        pygame.draw.line(screen, self.color, (self.x1, self.y1), (self.x2, self.y2), self.width)


class MatrixStream:
    """マトリックス風の文字の雨を管理するクラス"""
    def __init__(self, x, font_size, speed, screen_height, font_name):
        self.x = x
        self.y = random.randint(-500, 0) # 初期Y座標は画面外の上部にランダム配置
        self.font_size = font_size 
        self.speed = speed
        self.screen_height = screen_height
        self.length = random.randint(10, 30) # 文字列の長さ
        # ASCIIの表示可能文字（スペースを除く）
        self.characters = [chr(i) for i in range(33, 127)] # '!'(33) から '~'(126) まで
        self.symbols = [random.choice(self.characters) for _ in range(self.length)] # 初期文字列
        try:
            # 指定されたフォントを読み込む
            self.font = pygame.font.SysFont(font_name, self.font_size)
        except pygame.error:
            # フォントが見つからない場合はデフォルトフォントを使用
            self.font = pygame.font.Font(None, self.font_size)

    def update(self):
        """文字の雨の位置を更新する"""
        self.y += self.speed
        # 筋全体が画面外に出たら、Y座標をリセット
        if self.y - (self.length * self.font_size) > self.screen_height:
            self.y = random.randint(-200, 0)
        # 一定の確率で文字をランダムに入れ替える
        if random.randint(1, 100) < 20: # 20%の確率で
            self.symbols[random.randint(0, self.length - 1)] = random.choice(self.characters) # ランダムな文字に置き換え

    def draw(self, screen):
        """文字の雨を描画する"""
        for i, symbol in enumerate(self.symbols):
            # 先頭の文字は白っぽく明るく、後続は緑のグラデーション
            color = (200, 255, 200) if i == len(self.symbols) - 1 else (0, 255 - (i * (255 // self.length)), 70)
            pos_y = self.y - (i * self.font_size)
            if 0 < pos_y < self.screen_height:
                symbol_surface = self.font.render(symbol, True, color)
                screen.blit(symbol_surface, (self.x, pos_y))


class Particle:
    """花火の火花を表現するパーティクルクラス"""
    def __init__(self, x, y, base_color, color_mode):
        """パーティクルの初期化"""
        self.x = x
        self.y = y

        if color_mode == ParticleColorMode.RAINBOW:
            # HSV色空間でランダムな虹色を生成し、RGBに変換
            hue = random.random()  # 0.0から1.0のランダムな色相
            saturation = 1.0       # 彩度は最大で鮮やかに
            value = 1.0            # 明度も最大で明るく
            rgb_float = colorsys.hsv_to_rgb(hue, saturation, value)
            self.color = tuple(int(c * 255) for c in rgb_float)
        else:  # デフォルトは LINKED
            # 衝突したオブジェクトの色を少し明るくして火花らしくする
            self.color = tuple(min(255, c + 40) for c in base_color)
        
        # 放射状に飛び散るランダムな速度
        angle = random.uniform(0, 2 * math.pi)
        speed = random.uniform(1, 4)
        self.dx = math.cos(angle) * speed
        self.dy = math.sin(angle) * speed

        self.lifespan = random.randint(25, 50)  # フレーム数での寿命
        self.gravity = 0.1 # 重力加速度

    def move(self):
        """パーティクルを移動させる"""
        self.dy += self.gravity # 重力の影響
        self.x += self.dx
        self.y += self.dy
        self.lifespan -= 1

    def draw(self, screen):
        """パーティクルを描画する"""
        # 寿命に応じてサイズを小さくする
        size = max(1, int(self.lifespan / 12))
        pygame.draw.circle(screen, self.color, (self.x, self.y), size)


class Ball:
    """ボールの動きや外観を管理するクラス"""
    def __init__(self, max_velocity, screen_width, screen_height):
        """ボールの初期化"""
        # ランダムな半径と色を設定
        self.radius = random.randrange(MIN_BALL_RADIUS, MAX_BALL_RADIUS)
        # 画面内に完全に収まるように、ランダムな位置を設定
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.x = random.randrange(self.radius, self.screen_width - self.radius)
        self.y = random.randrange(self.radius, self.screen_height - self.radius)
        self.mass = self.radius ** 2  # 質量は半径の2乗に比例させる
        self.color = (random.randrange(50, 256), random.randrange(50, 256), random.randrange(50, 256))
        # 0と1を除いた速度の選択肢を生成
        velocity_choices = list(range(-max_velocity, -1)) + list(range(2, max_velocity + 1))
        if not velocity_choices:  # max_velocityが2未満の場合のフォールバック
            velocity_choices = [-2, 2]
        self.dx = random.choice(velocity_choices)
        self.dy = random.choice(velocity_choices)

    def move(self):
        """ボールを移動させ、壁で反射させる。壁との衝突情報を返す。"""
        self.x += self.dx
        self.y += self.dy

        collided = False
        # 左右の壁で反射
        if self.x < self.radius or self.x > self.screen_width - self.radius:
            self.dx *= -1
            self.x = max(self.radius, min(self.x, self.screen_width - self.radius))
            collided = True
        # 上下の壁で反射
        if self.y < self.radius or self.y > self.screen_height - self.radius:
            self.dy *= -1
            self.y = max(self.radius, min(self.y, self.screen_height - self.radius))
            collided = True

        if collided:
            collision_info = (self.x, self.y, self.color)  # 衝突時の情報を保存
            # 色と半径を変更
            self.color = (random.randrange(50, 256), random.randrange(50, 256), random.randrange(50, 256))
            self.radius = random.randrange(MIN_BALL_RADIUS, MAX_BALL_RADIUS)
            # 半径が変わったので、再度壁に埋まらないように位置を調整
            self.x = max(self.radius, min(self.x, self.screen_width - self.radius))
            self.y = max(self.radius, min(self.y, self.screen_height - self.radius))
            return collision_info
        return None

    def draw(self, screen):
        """ボールを画面に描画する"""
        pygame.draw.circle(screen, self.color, (self.x, self.y), self.radius)


class CameraSurveillanceThread(threading.Thread):
    """カメラでの動きを監視し、動きを検知したら画像を保存するスレッド"""
    def __init__(self, device_index, capture_folder, motion_threshold, stop_event):
        super().__init__()
        self.device_index = device_index
        self.capture_folder = capture_folder
        self.motion_threshold = motion_threshold
        self.stop_event = stop_event
        self.daemon = True # メインスレッド終了時に自動終了

    def run(self):
        # キャプチャ保存先フォルダがなければ作成
        if not os.path.exists(self.capture_folder):
            try:
                os.makedirs(self.capture_folder)
            except OSError as e:
                logging.error(f"キャプチャ保存先フォルダの作成に失敗しました: {e}")
                return

        cap = cv2.VideoCapture(self.device_index)
        if not cap.isOpened():
            print(f"エラー: カメラデバイス {self.device_index} を開けませんでした。")
            return

        # 最初のフレームを背景として取得
        ret, prev_frame = cap.read()
        if not ret:
            logging.error("カメラからフレームを読み込めませんでした。")
            cap.release()
            return
        
        prev_gray = cv2.cvtColor(prev_frame, cv2.COLOR_BGR2GRAY)
        prev_gray = cv2.GaussianBlur(prev_gray, (21, 21), 0) # ノイズ除去のためにぼかしを適用

        while not self.stop_event.is_set():
            ret, frame = cap.read()
            if not ret:
                break

            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            gray = cv2.GaussianBlur(gray, (21, 21), 0)

            # 差分を計算し、動きがあった領域を検出
            frame_delta = cv2.absdiff(prev_gray, gray) # 前フレームとの差分を計算
            thresh = cv2.threshold(frame_delta, 25, 255, cv2.THRESH_BINARY)[1] # 二値化
            thresh = cv2.dilate(thresh, None, iterations=2) # 膨張処理でノイズを減らす
            contours, _ = cv2.findContours(thresh.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE) # 輪郭を検出

            for contour in contours:
                if cv2.contourArea(contour) > self.motion_threshold:
                    # 動きを検知したら画像を保存
                    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
                    filename = os.path.join(self.capture_folder, f"capture_{timestamp}.jpg")
                    cv2.imwrite(filename, frame)
                    logging.info(f"動きを検知し、画像を保存しました: {filename}")
                    break # 1フレームにつき1枚保存すれば十分

            # 現在のフレームを次の比較のために保存
            prev_gray = gray
            
            # CPU負荷を軽減するために少し待機
            pygame.time.wait(100) # 100ミリ秒待機

        cap.release()

# --- グローバル変数 ---
camera_thread = None
stop_camera_event = None
tray_icon = None
tray_thread = None

def cleanup_on_exit():
    """プログラム終了時に実行されるクリーンアップ処理"""
    global camera_thread, stop_camera_event, tray_icon, tray_thread
    logging.info("クリーンアップ処理を開始...")

    # トレイアイコンとスレッドの停止
    if tray_icon and tray_icon.visible:
        tray_icon.stop()
    if tray_thread and tray_thread.is_alive():
        tray_thread.join(timeout=2)

    # カメラ監視スレッドの停止
    if camera_thread and camera_thread.is_alive():
        if stop_camera_event:
            stop_camera_event.set()
        camera_thread.join(timeout=2)

    # Pygameの終了
    if pygame.get_init():
        pygame.quit()
    logging.info("...クリーンアップ処理完了")

def main(settings):
    """
    メインの処理。
    ユーザー操作によって終了した場合は True を、それ以外 (トレイからの終了など) の場合は False を返す。
    """
    # スクリーンセーバーが再開されるたびにPygameを再初期化する
    pygame.init()
    INFO = pygame.display.Info() # 画面情報をここで取得
    SCREEN_WIDTH = INFO.current_w
    SCREEN_HEIGHT = INFO.current_h

    # フルスクリーンで画面をセットアップ
    screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.FULLSCREEN)
    pygame.display.set_caption("Python Screensaver")

    # 引数で渡された設定を使用
    idle_timeout_ms = settings.get(CfgKey.IDLE_TIMEOUT, IDLE_TIMEOUT)
    ball_count = settings.get(CfgKey.BALL_COUNT, DEFAULT_BALL_COUNT)
    max_velocity = settings.get(CfgKey.MAX_VELOCITY, DEFAULT_MAX_VELOCITY)
    password_enabled = settings.get(CfgKey.PASSWORD_ENABLED, False)
    password_hash = settings.get(CfgKey.PASSWORD_HASH, None)
    password_ui_position = settings.get(CfgKey.PASSWORD_UI_POSITION, DEFAULT_PASSWORD_UI_POSITION)
    password_ui_font_size = settings.get(CfgKey.PASSWORD_UI_FONT_SIZE, DEFAULT_PASSWORD_UI_FONT_SIZE)
    password_ui_prompt_color = tuple(settings.get(CfgKey.PASSWORD_UI_PROMPT_COLOR, DEFAULT_PASSWORD_UI_PROMPT_COLOR))
    password_ui_input_color = tuple(settings.get(CfgKey.PASSWORD_UI_INPUT_COLOR, DEFAULT_PASSWORD_UI_INPUT_COLOR))
    password_ui_warning_color = tuple(settings.get(CfgKey.PASSWORD_UI_WARNING_COLOR, DEFAULT_PASSWORD_UI_WARNING_COLOR))
    password_ui_info_color = tuple(settings.get(CfgKey.PASSWORD_UI_INFO_COLOR, DEFAULT_PASSWORD_UI_INFO_COLOR))

    saver_mode = settings.get(CfgKey.SAVER_MODE, DEFAULT_SAVER_MODE)
    slideshow_folder = settings.get(CfgKey.SLIDESHOW_FOLDER, DEFAULT_SLIDESHOW_FOLDER)
    slideshow_interval_ms = settings.get(CfgKey.SLIDESHOW_INTERVAL, DEFAULT_SLIDESHOW_INTERVAL) * 1000
    line_count = settings.get(CfgKey.LINE_COUNT, DEFAULT_LINE_COUNT)
    line_speed = settings.get(CfgKey.LINE_SPEED, DEFAULT_LINE_SPEED)
    matrix_font_size = settings.get(CfgKey.MATRIX_FONT_SIZE, DEFAULT_MATRIX_FONT_SIZE)
    matrix_speed = settings.get(CfgKey.MATRIX_SPEED, DEFAULT_MATRIX_SPEED)
    matrix_font = settings.get(CfgKey.MATRIX_FONT, DEFAULT_MATRIX_FONT)
    clock_enabled = settings.get(CfgKey.CLOCK_ENABLED, DEFAULT_CLOCK_ENABLED)
    clock_position = settings.get(CfgKey.CLOCK_POSITION, DEFAULT_CLOCK_POSITION)
    clock_color_list = settings.get(CfgKey.CLOCK_COLOR, list(DEFAULT_CLOCK_COLOR))
    clock_font_size = settings.get(CfgKey.CLOCK_FONT_SIZE, DEFAULT_CLOCK_FONT_SIZE)
    wall_spark_enabled = settings.get(CfgKey.WALL_SPARK_ENABLED, True) # デフォルトは有効
    particle_color_mode = settings.get(CfgKey.PARTICLE_COLOR_MODE, DEFAULT_PARTICLE_COLOR_MODE)
    camera_enabled = settings.get(CfgKey.CAMERA_ENABLED, DEFAULT_CAMERA_ENABLED)
    camera_device_index = settings.get(CfgKey.CAMERA_DEVICE_INDEX, DEFAULT_CAMERA_DEVICE_INDEX)
    camera_capture_folder = settings.get(CfgKey.CAMERA_CAPTURE_FOLDER, DEFAULT_CAMERA_CAPTURE_FOLDER)
    camera_motion_threshold = settings.get(CfgKey.CAMERA_MOTION_THRESHOLD, DEFAULT_CAMERA_MOTION_THRESHOLD)
    camera_retention_days = settings.get(CfgKey.CAMERA_CAPTURE_RETENTION_DAYS, DEFAULT_CAMERA_CAPTURE_RETENTION_DAYS)
    if not os.path.isabs(camera_capture_folder):
        camera_capture_folder = os.path.join(BASE_PATH, camera_capture_folder)

    # 指定した数のボールオブジェクトを作成
    balls = [Ball(max_velocity=max_velocity, screen_width=SCREEN_WIDTH, screen_height=SCREEN_HEIGHT) for _ in range(ball_count)]

    # スライドショー用の変数
    image_files = []
    current_image_index = 0
    last_image_change_time = 0
    current_image_surface = None # 現在表示中の画像
    next_image_surface = None    # フェードインしてくる次の画像
    is_fading = False
    fade_start_time = 0

    # ラインアート用の変数
    lines = []
    # マトリックス用の変数
    matrix_streams = []
    # 花火用のパーティクルリスト
    particles = []

    def start_saver_active_mode():
        """セーバーをアクティブ状態に移行するための初期化処理"""
        nonlocal screen, state, image_files, current_image_index, current_image_surface, next_image_surface, is_fading, last_image_change_time, lines, matrix_streams

        # ウィンドウをフルスクリーンに戻す/設定する
        screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.FULLSCREEN)
        state = "SAVER_ACTIVE"
        pygame.mouse.set_visible(False)

        # フルスクリーン化やマウスカーソル非表示に伴う意図しないイベントを破棄
        pygame.event.clear()

        # セーバーモードに応じた初期化
        current_time = pygame.time.get_ticks()
        if saver_mode == SaverMode.SLIDESHOW:
            image_files = get_image_files(slideshow_folder)
            if image_files:
                random.shuffle(image_files)
                current_image_index = -1
                current_image_surface = None
                next_image_surface = None
                is_fading = False
                last_image_change_time = current_time - slideshow_interval_ms - 1
            else:
                logging.warning(f"スライドショーフォルダ \"{slideshow_folder}\" に画像が見つかりません。")
        elif saver_mode == SaverMode.LINE_ART:
            lines = [Line(max_speed=line_speed, screen_width=SCREEN_WIDTH, screen_height=SCREEN_HEIGHT) for _ in range(line_count)]
        elif saver_mode == SaverMode.MATRIX:
            stream_count = SCREEN_WIDTH // matrix_font_size
            matrix_streams = [MatrixStream(i * matrix_font_size, matrix_font_size, matrix_speed, SCREEN_HEIGHT, matrix_font) for i in range(stream_count)]

    # --- カメラ監視スレッドの開始 ---
    if camera_enabled and cv2:
        global camera_thread, stop_camera_event
        # スレッド開始前に古いファイルをクリーンアップ
        cleanup_old_captures(camera_capture_folder, camera_retention_days)

        stop_camera_event = threading.Event()
        camera_thread = CameraSurveillanceThread(
            device_index=camera_device_index,
            capture_folder=camera_capture_folder,
            motion_threshold=camera_motion_threshold,
            stop_event=stop_camera_event
        )
        camera_thread.start()
    elif camera_enabled and not cv2:
        logging.warning("カメラ監視が有効ですが、OpenCVライブラリが見つかりません。")
        logging.warning("`pip install opencv-python` を実行してインストールしてください。")


    clock = pygame.time.Clock()
    running = True

    # 状態管理: 'WAITING', 'SAVER_ACTIVE', 'PASSWORD_PROMPT'
    state = "SAVER_ACTIVE"
    start_saver_active_mode()
    last_activity_time = pygame.time.get_ticks()
    password_attempts = 0
    input_text = ""

    user_interrupted = False # ユーザー操作による終了フラグ
    # 日本語表示のためのフォント設定
    # Windowsでは 'meiryo' や 'msgothic' が利用可能。'meiryo' を試し、失敗したらデフォルトフォントを使用。
    try:
        prompt_font = pygame.font.SysFont("meiryo", password_ui_font_size)
        warning_font = pygame.font.SysFont("meiryo", int(password_ui_font_size / 2))
        clock_font = pygame.font.SysFont("meiryo", clock_font_size)
    except pygame.error:
        logging.warning("\"meiryo\" フォントが見つかりません。UIの日本語が文字化けする可能性があります。")
        prompt_font = pygame.font.Font(None, password_ui_font_size) # デフォルトフォント
        warning_font = pygame.font.Font(None, int(password_ui_font_size / 2))
        clock_font = pygame.font.Font(None, int(clock_font_size * 1.2)) # 代替フォントのサイズ調整

    # 起動時に発生する可能性のあるイベントを破棄
    pygame.event.clear()

    while running:
        # 現在の時刻を取得
        current_time = pygame.time.get_ticks()

        # --- イベント処理 ---
        for event in pygame.event.get():
            # トレイアイコンからのカスタム終了イベントを処理
            if event.type == TRAY_QUIT_EVENT:
                running = False
                continue
            # 通常のQUITイベント（ウィンドウの閉じるボタン、Alt+F4など）は無視する
            if event.type == pygame.QUIT:
                continue

            # パスワード入力中のキー操作を優先的に処理
            if state == "PASSWORD_PROMPT" and event.type == pygame.KEYDOWN:
                if event.key == pygame.K_RETURN:
                    # 入力されたパスワードをハッシュ化して比較
                    entered_hash = hashlib.sha256(input_text.encode()).hexdigest()
                    if entered_hash == password_hash: # パスワードが正しい場合
                        # メッセージボックスを表示してユーザーに選択させる
                        choice = messagebox.askyesno(
                            "スクリーンセーバー", # タイトル
                            "パスワードが一致しました。\nスクリーンセーバーを継続しますか？\n\"はい\"で待機状態に戻り、\"いいえ\"でプログラムを終了します。" # メッセージ
                        )
                        if choice: # 'はい'が選択された場合 (継続)
                            running = False # mainループを抜けて監視状態に戻る
                        else: # 'いいえ'が選択された場合 (終了)
                            if tray_icon:
                                exit_action(tray_icon, None) # トレイアイコンも終了させる
                            running = False
                    else:
                        # パスワードが違う場合、入力内容をクリア
                        input_text = ""
                        password_attempts += 1
                        if password_attempts >= 3:
                            force_shutdown(settings)
                            running = False # シャットダウンコマンド発行後にループを抜ける

                elif event.key == pygame.K_BACKSPACE:
                    input_text = input_text[:-1]
                else:
                    input_text += event.unicode
                # パスワード入力中もアイドルタイマーをリセット
                last_activity_time = pygame.time.get_ticks()
                continue # イベント処理完了

            # 一般的な操作（マウス移動やキー入力）の検出
            if event.type in [pygame.KEYDOWN, pygame.MOUSEMOTION]:
                last_activity_time = pygame.time.get_ticks()
                # セーバー実行中に操作があった場合
                if state == "SAVER_ACTIVE":
                    if password_enabled and password_hash:
                        # パスワードが有効なら、パスワード入力画面に移行
                        state = "PASSWORD_PROMPT"
                        password_attempts = 0 # パスワード画面移行時にリセット
                        input_text = ""
                        pygame.mouse.set_visible(True)
                    else:
                        # パスワードが無効なら、mainループを抜けて監視状態に戻る
                        user_interrupted = True # ユーザー操作による終了
                        running = False # ループを抜ける

        # --- 描画処理 ---
        screen.fill(BLACK) # 毎フレーム画面を黒でクリア

        # セーバー実行中のみ各モードの描画を行う
        if state == "SAVER_ACTIVE":
            if saver_mode == SaverMode.BALLS:
                # 全てのボールを移動
                for ball in balls:
                    wall_collision_info = ball.move()
                    if wall_spark_enabled and wall_collision_info:
                        # 壁との衝突で花火を生成
                        num_particles = random.randint(5, 10) # 少なめに
                        cx, cy, p_color = wall_collision_info
                        for _ in range(num_particles):
                            particles.append(Particle(cx, cy, p_color, particle_color_mode))

                # ボール同士の衝突判定と処理
                for i in range(len(balls)):
                    for j in range(i + 1, len(balls)):
                        ball1 = balls[i]
                        ball2 = balls[j]

                        # 衝突ベクトル
                        coll_vec_x = ball2.x - ball1.x
                        coll_vec_y = ball2.y - ball1.y
                        dist = math.sqrt(coll_vec_x**2 + coll_vec_y**2)

                        # 衝突を検出
                        if dist < ball1.radius + ball2.radius:
                            # 衝突したら両方のボールの色をランダムに変更
                            ball1.color = (random.randrange(50, 256), random.randrange(50, 256), random.randrange(50, 256))
                            ball2.color = (random.randrange(50, 256), random.randrange(50, 256), random.randrange(50, 256))

                            # --- 花火エフェクト生成 ---
                            num_particles = random.randint(10, 20)
                            collision_x = (ball1.x + ball2.x) / 2
                            collision_y = (ball1.y + ball2.y) / 2
                            # 衝突した両方のボールの色を混ぜて使う
                            particle_color = ((ball1.color[0] + ball2.color[0]) // 2,
                                              (ball1.color[1] + ball2.color[1]) // 2,
                                              (ball1.color[2] + ball2.color[2]) // 2)
                            for _ in range(num_particles):
                                particles.append(Particle(collision_x, collision_y, particle_color, particle_color_mode))

                            # --- リアルな物理演算による反発処理 ---
                            # ゼロ除算を避ける
                            if dist == 0: dist = 1

                            # 1. 単位法線ベクトルと単位接線ベクトル
                            un_x = coll_vec_x / dist
                            un_y = coll_vec_y / dist
                            ut_x = -un_y
                            ut_y = un_x

                            # 2. 速度を法線・接線方向に分解 (ドット積)
                            v1n = ball1.dx * un_x + ball1.dy * un_y
                            v1t = ball1.dx * ut_x + ball1.dy * ut_y
                            v2n = ball2.dx * un_x + ball2.dy * un_y
                            v2t = ball2.dx * ut_x + ball2.dy * ut_y

                            # 3. 法線方向の新しい速度を計算 (1次元弾性衝突の公式)
                            m1, m2 = ball1.mass, ball2.mass
                            v1n_new = (v1n * (m1 - m2) + 2 * m2 * v2n) / (m1 + m2)
                            v2n_new = (v2n * (m2 - m1) + 2 * m1 * v1n) / (m1 + m2)

                            # 4. 新しい速度ベクトルを計算し、ボールの速度を更新
                            ball1.dx = (v1n_new * un_x) + (v1t * ut_x)
                            ball1.dy = (v1n_new * un_y) + (v1t * ut_y)
                            ball2.dx = (v2n_new * un_x) + (v2t * ut_x)
                            ball2.dy = (v2n_new * un_y) + (v2t * ut_y)

                            # 5. 重なりの解消 (ボールがめり込むのを防ぐ)
                            overlap = (ball1.radius + ball2.radius) - dist
                            if overlap > 0:
                                total_mass = ball1.mass + ball2.mass
                                ball1.x -= (overlap * (ball2.mass / total_mass)) * un_x
                                ball1.y -= (overlap * (ball2.mass / total_mass)) * un_y
                                ball2.x += (overlap * (ball1.mass / total_mass)) * un_x
                                ball2.y += (overlap * (ball1.mass / total_mass)) * un_y

                # 全てのボールを描画
                for ball in balls:
                    ball.draw(screen)
            elif saver_mode == SaverMode.SLIDESHOW and image_files:
                # --- フェード開始トリガー ---
                if not is_fading and current_time - last_image_change_time > slideshow_interval_ms:
                    is_fading = True
                    fade_start_time = current_time
                    # 次の画像を読み込み準備
                    next_image_index = (current_image_index + 1) % len(image_files)
                    next_image_surface = load_and_scale_image(image_files[next_image_index], SCREEN_WIDTH, SCREEN_HEIGHT)
                    
                    # 画像読み込み失敗時はフェードを中止し、タイマーをリセットして再試行を待つ
                    if not next_image_surface:
                        is_fading = False
                        last_image_change_time = current_time

                # --- 描画とフェード処理 ---
                if is_fading:
                    fade_progress = (current_time - fade_start_time) / FADE_DURATION
                    
                    # フェードアウトする現在の画像を描画 (存在する場合)
                    if current_image_surface:
                        alpha_out = 255 * (1.0 - min(1.0, fade_progress))
                        current_image_surface.set_alpha(alpha_out)
                        rect = current_image_surface.get_rect(center=(SCREEN_WIDTH / 2, SCREEN_HEIGHT / 2))
                        screen.blit(current_image_surface, rect)

                    # フェードインする次の画像を描画 (存在する場合)
                    if next_image_surface:
                        alpha_in = 255 * min(1.0, fade_progress)
                        next_image_surface.set_alpha(alpha_in)
                        rect = next_image_surface.get_rect(center=(SCREEN_WIDTH / 2, SCREEN_HEIGHT / 2))
                        screen.blit(next_image_surface, rect)

                    # フェード完了時の状態更新
                    if fade_progress >= 1.0:
                        is_fading = False
                        current_image_surface = next_image_surface
                        next_image_surface = None
                        current_image_index = (current_image_index + 1) % len(image_files)
                        last_image_change_time = current_time
                else:
                    # フェード中でない場合、現在の画像を不透明で描画
                    if current_image_surface:
                        current_image_surface.set_alpha(255)
                        rect = current_image_surface.get_rect(center=(SCREEN_WIDTH / 2, SCREEN_HEIGHT / 2))
                        screen.blit(current_image_surface, rect)
            elif saver_mode == SaverMode.LINE_ART:
                for line in lines:
                    line.move()
                    line.draw(screen)
            elif saver_mode == SaverMode.MATRIX:
                for stream in matrix_streams:
                    stream.update()
                    stream.draw(screen)

            # --- パーティクルの更新と描画 ---
            # スライスコピー `[:]` を使ってループ中にリストから要素を安全に削除
            for p in particles[:]:
                p.move()
                p.draw(screen)
                if p.lifespan <= 0:
                    particles.remove(p)

        # パスワード入力画面のUIを描画
        if state == "PASSWORD_PROMPT":
            # 背景は黒一色で、アニメーションは描画しない

            # UIボックスのサイズと位置
            box_width, box_height = 500, 180 # 高さを広げて余裕を持たせる
            box_x = (SCREEN_WIDTH - box_width) / 2

            # 位置設定に基づいてY座標を計算
            if password_ui_position == "top":
                box_y = SCREEN_HEIGHT * 0.15 # 画面の上から15%
            elif password_ui_position == "bottom":
                box_y = SCREEN_HEIGHT - box_height - (SCREEN_HEIGHT * 0.15)
            else: # 'center' またはデフォルト
                box_y = (SCREEN_HEIGHT - box_height) / 2

            # ボックスの描画
            pygame.draw.rect(screen, (30, 30, 30), (box_x, box_y, box_width, box_height))
            pygame.draw.rect(screen, (200, 200, 200), (box_x, box_y, box_width, box_height), 2)

            # プロンプトテキスト
            prompt_surface = prompt_font.render("パスワードを入力:", True, password_ui_prompt_color)
            prompt_rect = prompt_surface.get_rect(topleft=(box_x + 25, box_y + 20))
            screen.blit(prompt_surface, prompt_rect)

            # 入力中のパスワード（アスタリスクで表示）
            input_surface = prompt_font.render("*" * len(input_text), True, password_ui_input_color)
            input_rect = input_surface.get_rect(midleft=(box_x + 25, box_y + 105))
            screen.blit(input_surface, input_rect)

            # 状況に応じたメッセージを表示
            if password_attempts > 0:
                # 警告メッセージ
                msg_text = f"失敗: {password_attempts} / 3 (3回で強制シャットダウン)"
                msg_color = password_ui_warning_color
            else:
                # 操作案内
                msg_text = "Enterで決定、Escでキャンセル"
                msg_color = password_ui_info_color
            msg_surface = warning_font.render(msg_text, True, msg_color)
            msg_rect = msg_surface.get_rect(bottomleft=(box_x + 25, box_y + box_height - 20))
            screen.blit(msg_surface, msg_rect)

        # --- 時刻の描画 ---
        # セーバーがアクティブ、またはパスワード入力中の場合に時刻を表示
        if clock_enabled and state in ["SAVER_ACTIVE", "PASSWORD_PROMPT"]:
            now = datetime.datetime.now()
            time_str = now.strftime("%H:%M:%S")
            time_surface = clock_font.render(time_str, True, tuple(clock_color_list))

            # 位置設定に基づいてrectのアンカーと座標を決定
            padding_x = 20
            padding_y = 10
            position_map = {
                "topleft": {"topleft": (padding_x, padding_y)},
                "topright": {"topright": (SCREEN_WIDTH - padding_x, padding_y)},
                "bottomleft": {"bottomleft": (padding_x, SCREEN_HEIGHT - padding_y)},
                "bottomright": {"bottomright": (SCREEN_WIDTH - padding_x, SCREEN_HEIGHT - padding_y)}
            }
            # 不正な値が設定されていた場合はデフォルト(bottomright)を使用
            rect_kwargs = position_map.get(clock_position, position_map["bottomright"])

            time_rect = time_surface.get_rect(**rect_kwargs)
            screen.blit(time_surface, time_rect)

        # --- バッテリー残量の描画 ---
        # Windowsかつpsutilが利用可能で、セーバーがアクティブまたはパスワード入力中の場合に表示
        if psutil and state in ["SAVER_ACTIVE", "PASSWORD_PROMPT"]:
            battery = psutil.sensors_battery()
            if battery:
                percent = int(battery.percent)
                power_plugged = battery.power_plugged

                # 表示する文字列を作成
                if power_plugged:
                    status = "充電完了" if percent == 100 else "充電中"
                else:
                    status = "放電中"
                battery_str = f"バッテリー: {percent}% ({status})"

                # 時刻表示と同じフォントと色を使用
                battery_surface = clock_font.render(battery_str, True, tuple(clock_color_list))

                # 描画位置を決定 (左下を基本とする)
                battery_rect = battery_surface.get_rect(bottomleft=(padding_x, SCREEN_HEIGHT - padding_y))
                if clock_enabled and clock_position == "bottomleft":
                    battery_rect.bottom = time_rect.top - 5 # 時刻表示が左下なら、その少し上に表示
                screen.blit(battery_surface, battery_rect)

        # 画面を更新
        pygame.display.flip()

        # フレームレートを60fpsに制限
        clock.tick(60)

    logging.info("スクリーンセーバーを終了し、待機/監視モードに戻ります。")
    pygame.mouse.set_visible(True) # 監視ループに戻る前にマウスカーソルを表示
    return user_interrupted

def show_password_change_dialog(parent, current_hash):
    """
    パスワードの変更・設定を行うためのカスタムダイアログを表示する。
    成功した場合は新しいハッシュを、失敗・キャンセルの場合はNoneを返す。
    """
    dialog = tk.Toplevel(parent)
    dialog.title("パスワードの変更")
    dialog.transient(parent) # 親ウィンドウの上に表示
    dialog.grab_set()      # モーダルにする

    new_hash_container = [None] # 結果を格納するためのミュータブルなコンテナ

    main_frame = ttk.Frame(dialog, padding="15")
    main_frame.pack(fill="both", expand=True)
    main_frame.columnconfigure(1, weight=1)

    # --- ウィジェットの作成 ---
    row_index = 0
    if current_hash:
        ttk.Label(main_frame, text="現在のパスワード:").grid(row=row_index, column=0, sticky=tk.W, pady=3, padx=5)
        old_pass_entry = ttk.Entry(main_frame, show="*", width=30)
        old_pass_entry.grid(row=row_index, column=1, sticky=(tk.W, tk.E), pady=3)
        row_index += 1

    ttk.Label(main_frame, text="新しいパスワード:").grid(row=row_index, column=0, sticky=tk.W, pady=3, padx=5)
    new_pass_entry1 = ttk.Entry(main_frame, show="*", width=30)
    new_pass_entry1.grid(row=row_index, column=1, sticky=(tk.W, tk.E), pady=3)
    row_index += 1

    ttk.Label(main_frame, text="新しいパスワード (確認):").grid(row=row_index, column=0, sticky=tk.W, pady=3, padx=5)
    new_pass_entry2 = ttk.Entry(main_frame, show="*", width=30)
    new_pass_entry2.grid(row=row_index, column=1, sticky=(tk.W, tk.E), pady=3)
    row_index += 1

    # --- ボタンの処理 ---
    def on_ok():
        if current_hash:
            if hashlib.sha256(old_pass_entry.get().encode()).hexdigest() != current_hash:
                messagebox.showerror("認証エラー", "現在のパスワードが違います。", parent=dialog)
                return

        new_pass1 = new_pass_entry1.get()
        new_pass2 = new_pass_entry2.get()

        if not new_pass1:
            messagebox.showwarning("入力エラー", "新しいパスワードは空にできません。", parent=dialog)
            return
        if new_pass1 != new_pass2:
            messagebox.showerror("エラー", "新しいパスワードが一致しません。", parent=dialog)
            return

        new_hash_container[0] = hashlib.sha256(new_pass1.encode()).hexdigest()
        messagebox.showinfo("成功", "パスワードが設定されました。\nメイン画面の「スクリーンセーバー開始」ボタンを押して設定を保存してください。", parent=parent)
        dialog.destroy()

    button_frame = ttk.Frame(main_frame)
    button_frame.grid(row=row_index, column=0, columnspan=2, pady=(10, 0))
    ttk.Button(button_frame, text="OK", command=on_ok).pack(side=tk.LEFT, padx=5)
    ttk.Button(button_frame, text="キャンセル", command=dialog.destroy).pack(side=tk.LEFT, padx=5)

    parent.wait_window(dialog) # ダイアログが閉じるまで待機
    return new_hash_container[0]


def open_settings_gui():
    # GUI内でプレビュー用にPygameを使用するため、最初に初期化する
    if not pygame.get_init():
        pygame.init()

    settings = load_settings()

    # この関数が返す設定値を保持する変数
    result_settings = None

    # 定数からデフォルト値を取得し、設定ファイルの値で上書き
    current_timeout_ms = settings.get(CfgKey.IDLE_TIMEOUT, IDLE_TIMEOUT)
    current_ball_count = settings.get(CfgKey.BALL_COUNT, DEFAULT_BALL_COUNT)
    current_max_velocity = settings.get(CfgKey.MAX_VELOCITY, DEFAULT_MAX_VELOCITY)
    current_password_enabled = settings.get(CfgKey.PASSWORD_ENABLED, False)
    current_password_hash = settings.get(CfgKey.PASSWORD_HASH)
    current_password_ui_position = settings.get(CfgKey.PASSWORD_UI_POSITION, DEFAULT_PASSWORD_UI_POSITION)
    current_password_ui_font_size = settings.get(CfgKey.PASSWORD_UI_FONT_SIZE, DEFAULT_PASSWORD_UI_FONT_SIZE)
    current_password_ui_prompt_color = settings.get(CfgKey.PASSWORD_UI_PROMPT_COLOR, list(DEFAULT_PASSWORD_UI_PROMPT_COLOR))
    current_password_ui_input_color = settings.get(CfgKey.PASSWORD_UI_INPUT_COLOR, list(DEFAULT_PASSWORD_UI_INPUT_COLOR))
    current_password_ui_warning_color = settings.get(CfgKey.PASSWORD_UI_WARNING_COLOR, list(DEFAULT_PASSWORD_UI_WARNING_COLOR))
    current_password_ui_info_color = settings.get(CfgKey.PASSWORD_UI_INFO_COLOR, list(DEFAULT_PASSWORD_UI_INFO_COLOR))

    current_saver_mode = settings.get(CfgKey.SAVER_MODE, DEFAULT_SAVER_MODE)
    current_slideshow_folder = settings.get(CfgKey.SLIDESHOW_FOLDER, DEFAULT_SLIDESHOW_FOLDER)
    current_slideshow_interval = settings.get(CfgKey.SLIDESHOW_INTERVAL, DEFAULT_SLIDESHOW_INTERVAL)
    current_line_count = settings.get(CfgKey.LINE_COUNT, DEFAULT_LINE_COUNT)
    current_line_speed = settings.get(CfgKey.LINE_SPEED, DEFAULT_LINE_SPEED)
    current_matrix_font_size = settings.get(CfgKey.MATRIX_FONT_SIZE, DEFAULT_MATRIX_FONT_SIZE)
    current_matrix_speed = settings.get(CfgKey.MATRIX_SPEED, DEFAULT_MATRIX_SPEED)
    current_matrix_font = settings.get(CfgKey.MATRIX_FONT, DEFAULT_MATRIX_FONT)
    current_clock_enabled = settings.get(CfgKey.CLOCK_ENABLED, DEFAULT_CLOCK_ENABLED)
    current_clock_position = settings.get(CfgKey.CLOCK_POSITION, DEFAULT_CLOCK_POSITION)
    current_clock_color = settings.get(CfgKey.CLOCK_COLOR, list(DEFAULT_CLOCK_COLOR))
    current_clock_font_size = settings.get(CfgKey.CLOCK_FONT_SIZE, DEFAULT_CLOCK_FONT_SIZE)
    current_particle_color_mode = settings.get(CfgKey.PARTICLE_COLOR_MODE, DEFAULT_PARTICLE_COLOR_MODE)
    current_wall_spark_enabled = settings.get(CfgKey.WALL_SPARK_ENABLED, True)
    current_camera_enabled = settings.get(CfgKey.CAMERA_ENABLED, DEFAULT_CAMERA_ENABLED)
    current_camera_device_index = settings.get(CfgKey.CAMERA_DEVICE_INDEX, DEFAULT_CAMERA_DEVICE_INDEX)
    current_camera_capture_folder = settings.get(CfgKey.CAMERA_CAPTURE_FOLDER, DEFAULT_CAMERA_CAPTURE_FOLDER)
    current_camera_motion_threshold = settings.get(CfgKey.CAMERA_MOTION_THRESHOLD, DEFAULT_CAMERA_MOTION_THRESHOLD)
    current_camera_retention_days = settings.get(CfgKey.CAMERA_CAPTURE_RETENTION_DAYS, DEFAULT_CAMERA_CAPTURE_RETENTION_DAYS)
    current_auto_restart_on_idle = settings.get(CfgKey.AUTO_RESTART_ON_IDLE, DEFAULT_AUTO_RESTART_ON_IDLE)
    current_gui_theme = settings.get(CfgKey.GUI_THEME, DEFAULT_GUI_THEME)

    root = tk.Tk()
    root.title("スクリーンセーバー設定")

    # ウィンドウを中央に配置
    window_width = 900 # GUIの横幅
    window_height = 620 
    screen_width = root.winfo_screenwidth()
    screen_height = root.winfo_screenheight()
    center_x = int(screen_width / 2 - window_width / 2)
    center_y = int(screen_height / 2 - window_height / 2)
    root.geometry(f'{window_width}x{window_height}+{center_x}+{center_y}')
    root.resizable(False, False)

    # --- テーマ設定 ---
    style = ttk.Style(root)
    available_themes = style.theme_names()
    # 保存されたテーマが存在し、利用可能かチェック
    if current_gui_theme in available_themes:
        style.theme_use(current_gui_theme)
    else:
        # 利用できない場合はデフォルトテーマを適用
        current_gui_theme = DEFAULT_GUI_THEME
        style.theme_use(current_gui_theme)

    main_frame = ttk.Frame(root, padding="10 10 10 10")
    main_frame.pack(fill="both", expand=True)

    # --- 左右のペインを作成 ---
    # 左ペイン(設定)は可変、右ペイン(プレビュー)は固定幅
    main_frame.columnconfigure(0, weight=1)
    main_frame.columnconfigure(1, minsize=PREVIEW_WIDTH + 40)
    main_frame.rowconfigure(0, weight=1)

    left_pane = ttk.Frame(main_frame, padding=(0,0,10,0))
    left_pane.grid(column=0, row=0, sticky="nsew")
    right_pane = ttk.Frame(main_frame)
    right_pane.grid(column=1, row=0, sticky="nsew")

    # --- 左ペイン: モード選択と設定タブ ---
    mode_frame = ttk.LabelFrame(left_pane, text="スクリーンセーバーのモード", padding="10")
    mode_frame.pack(fill="x", pady=(0, 10))
    saver_mode_var = tk.StringVar(value=current_saver_mode)

    notebook = ttk.Notebook(left_pane)
    notebook.pack(fill="both", expand=True)

    # --- タブ1: 一般設定 (レイアウト改善) ---
    general_tab = ttk.Frame(notebook, padding="10")
    notebook.add(general_tab, text="一般")

    general_tab.columnconfigure(0, weight=1)

    # --- 起動設定 ---
    startup_settings_frame = ttk.LabelFrame(general_tab, text="起動設定", padding="10")
    startup_settings_frame.grid(row=0, column=0, sticky="ew", pady=(0, 10))
    startup_settings_frame.columnconfigure(1, weight=1) # ラベルと入力欄の間のスペースを確保
    ttk.Label(startup_settings_frame, text="無操作時間（秒）:").grid(column=0, row=0, sticky=tk.W, pady=(0, 5), padx=5)
    timeout_var = tk.StringVar(value=str(current_timeout_ms / 1000))
    timeout_entry = ttk.Entry(startup_settings_frame, width=10, textvariable=timeout_var)
    timeout_entry.grid(column=1, row=0, sticky=tk.W, pady=(0, 5))
    ttk.Label(startup_settings_frame, text="（セーバーが起動するまでの時間）").grid(column=2, row=0, sticky=tk.W, pady=(0, 5), padx=5)

    auto_restart_var = tk.BooleanVar(value=current_auto_restart_on_idle)
    auto_restart_check = ttk.Checkbutton(startup_settings_frame, text="待機中に無操作で再開する (Windowsのみ)", variable=auto_restart_var)
    auto_restart_check.grid(column=0, row=1, columnspan=3, sticky=tk.W, pady=(5, 5), padx=5)
    if not win32api:
        auto_restart_check.config(state="disabled")

    # --- イベントハンドラの定義と割り当て ---
    camera_enabled_var = tk.BooleanVar(value=current_camera_enabled)

    def toggle_camera_tab_state():
        """カメラタブの表示/非表示を切り替える"""
        notebook.tab(5, state="normal" if camera_enabled_var.get() and cv2 else "disabled")

    camera_checkbutton = ttk.Checkbutton(startup_settings_frame, text="カメラ監視を有効にする (要OpenCV)", variable=camera_enabled_var, command=toggle_camera_tab_state)
    camera_checkbutton.grid(column=0, row=2, columnspan=3, sticky=tk.W, pady=(10, 0), padx=5)

    # --- GUIテーマ設定 ---
    ttk.Label(startup_settings_frame, text="GUIテーマ:").grid(column=0, row=3, sticky=tk.W, pady=(5, 0), padx=5)
    gui_theme_var = tk.StringVar(value=current_gui_theme)
    theme_combo = ttk.Combobox(startup_settings_frame, textvariable=gui_theme_var, values=available_themes, state="readonly", width=15)
    theme_combo.grid(column=1, row=3, sticky=tk.W, pady=(5, 0))

    # --- タブ2: ボール設定 (レイアウト改善) ---
    ball_tab = ttk.Frame(notebook, padding="10")
    notebook.add(ball_tab, text="ボール")

    # ボール自体の設定
    ball_props_frame = ttk.LabelFrame(ball_tab, text="ボールの動作", padding="10")
    ball_props_frame.pack(fill="x", expand=False, pady=(0, 10))
    ball_props_frame.columnconfigure(1, weight=1)
    ttk.Label(ball_props_frame, text="ボールの数:").grid(column=0, row=0, sticky=tk.W, pady=5, padx=5)
    ball_count_var = tk.StringVar(value=str(current_ball_count))
    ball_count_entry = ttk.Entry(ball_props_frame, width=10, textvariable=ball_count_var)
    ball_count_entry.grid(column=1, row=0, sticky=tk.W, pady=5, padx=5)

    ttk.Label(ball_props_frame, text="ボールの最大速度:").grid(column=0, row=1, sticky=tk.W, pady=5, padx=5)
    max_velocity_var = tk.StringVar(value=str(current_max_velocity))
    max_velocity_entry = ttk.Entry(ball_props_frame, width=10, textvariable=max_velocity_var)
    max_velocity_entry.grid(column=1, row=1, sticky=tk.W, pady=5, padx=5)
    ttk.Label(ball_props_frame, text="（2以上の整数）").grid(column=2, row=1, sticky=tk.W, pady=5, padx=5)

    # 花火エフェクトの設定
    fireworks_frame = ttk.LabelFrame(ball_tab, text="花火エフェクト", padding="10")
    fireworks_frame.pack(fill="x", expand=False)
    wall_spark_enabled_var = tk.BooleanVar(value=current_wall_spark_enabled)
    ttk.Checkbutton(fireworks_frame, text="壁衝突時に花火を出す", variable=wall_spark_enabled_var).grid(column=0, row=0, columnspan=2, sticky=tk.W, pady=5, padx=5)

    particle_color_frame = ttk.Frame(fireworks_frame)
    particle_color_frame.grid(column=0, row=1, columnspan=2, sticky=tk.W, pady=5, padx=5)
    ttk.Label(particle_color_frame, text="花火の色:").pack(side=tk.LEFT, padx=(0, 10))
    particle_color_mode_var = tk.StringVar(value=current_particle_color_mode)
    ttk.Radiobutton(particle_color_frame, text="ボールに連動", variable=particle_color_mode_var, value=ParticleColorMode.LINKED).pack(side=tk.LEFT, padx=5)
    ttk.Radiobutton(particle_color_frame, text="虹色", variable=particle_color_mode_var, value=ParticleColorMode.RAINBOW).pack(side=tk.LEFT, padx=5)

    # --- タブ3: スライドショー設定 (レイアウト改善) ---
    slideshow_tab = ttk.Frame(notebook, padding="10")
    notebook.add(slideshow_tab, text="スライドショー")
    slideshow_settings_frame = ttk.LabelFrame(slideshow_tab, text="スライドショーモードの設定", padding="10")
    slideshow_settings_frame.pack(fill="x", expand=False)
    slideshow_settings_frame.columnconfigure(1, weight=1)

    ttk.Label(slideshow_settings_frame, text="画像フォルダ:").grid(column=0, row=0, sticky=tk.W, pady=5, padx=5)
    slideshow_folder_var = tk.StringVar(value=current_slideshow_folder)
    def select_folder():
        folder_selected = filedialog.askdirectory()
        if folder_selected:
            slideshow_folder_var.set(folder_selected)
    folder_entry = ttk.Entry(slideshow_settings_frame, textvariable=slideshow_folder_var)
    folder_entry.grid(column=1, row=0, sticky=(tk.W, tk.E), pady=5, padx=5)
    ttk.Button(slideshow_settings_frame, text="選択...", command=select_folder).grid(column=2, row=0, sticky=tk.N, pady=5, padx=5)

    ttk.Label(slideshow_settings_frame, text="切り替え間隔（秒）:").grid(column=0, row=1, sticky=tk.W, pady=5, padx=5)
    slideshow_interval_var = tk.StringVar(value=str(current_slideshow_interval))
    interval_entry = ttk.Entry(slideshow_settings_frame, width=10, textvariable=slideshow_interval_var)
    interval_entry.grid(column=1, row=1, sticky=tk.W, pady=5, padx=5)

    # --- タブ4: ラインアート設定 (レイアウト改善) ---
    line_art_tab = ttk.Frame(notebook, padding="10")
    notebook.add(line_art_tab, text="ラインアート")
    line_art_settings_frame = ttk.LabelFrame(line_art_tab, text="ラインアートモードの設定", padding="10")
    line_art_settings_frame.pack(fill="x", expand=False)
    line_art_settings_frame.columnconfigure(1, weight=1)

    ttk.Label(line_art_settings_frame, text="線の数:").grid(column=0, row=0, sticky=tk.W, pady=5, padx=5)
    line_count_var = tk.StringVar(value=str(current_line_count))
    line_count_entry = ttk.Entry(line_art_settings_frame, width=10, textvariable=line_count_var)
    line_count_entry.grid(column=1, row=0, sticky=tk.W, pady=5, padx=5)

    ttk.Label(line_art_settings_frame, text="線の最大速度:").grid(column=0, row=1, sticky=tk.W, pady=5, padx=5)
    line_speed_var = tk.StringVar(value=str(current_line_speed))
    line_speed_entry = ttk.Entry(line_art_settings_frame, width=10, textvariable=line_speed_var)
    line_speed_entry.grid(column=1, row=1, sticky=tk.W, pady=5, padx=5)

    # --- タブ5: マトリックス設定 (レイアウト改善) ---
    matrix_tab = ttk.Frame(notebook, padding="10")
    notebook.add(matrix_tab, text="マトリックス")
    matrix_settings_frame = ttk.LabelFrame(matrix_tab, text="マトリックスモードの設定", padding="10")
    matrix_settings_frame.pack(fill="x", expand=False)
    matrix_settings_frame.columnconfigure(1, weight=1)

    ttk.Label(matrix_settings_frame, text="フォントサイズ:").grid(column=0, row=0, sticky=tk.W, pady=5, padx=5)
    matrix_font_size_var = tk.StringVar(value=str(current_matrix_font_size))
    matrix_font_size_entry = ttk.Entry(matrix_settings_frame, width=10, textvariable=matrix_font_size_var)
    matrix_font_size_entry.grid(column=1, row=0, sticky=tk.W, pady=5, padx=5)

    ttk.Label(matrix_settings_frame, text="落下速度:").grid(column=0, row=1, sticky=tk.W, pady=5, padx=5)
    matrix_speed_var = tk.StringVar(value=str(current_matrix_speed))
    matrix_speed_entry = ttk.Entry(matrix_settings_frame, width=10, textvariable=matrix_speed_var)
    matrix_speed_entry.grid(column=1, row=1, sticky=tk.W, pady=5, padx=5)

    ttk.Label(matrix_settings_frame, text="フォント:").grid(column=0, row=2, sticky=tk.W, pady=5, padx=5)
    available_fonts = sorted(list(set(pygame.font.get_fonts()))) # 重複を除いてソート
    matrix_font_var = tk.StringVar(value=current_matrix_font)
    matrix_font_combo = ttk.Combobox(matrix_settings_frame, textvariable=matrix_font_var, values=available_fonts, state="readonly")
    matrix_font_combo.grid(column=1, row=2, columnspan=2, sticky=(tk.W, tk.E), pady=5, padx=5)

    # --- タブ6: カメラ監視設定 (レイアウト改善) ---
    camera_tab = ttk.Frame(notebook, padding="10")
    notebook.add(camera_tab, text="カメラ監視")
    camera_settings_frame = ttk.LabelFrame(camera_tab, text="カメラ監視設定", padding="10")
    camera_settings_frame.pack(fill="x", expand=False)
    camera_settings_frame.columnconfigure(1, weight=1)

    def get_available_cameras():
        if not cv2: return []
        cameras = []
        for i in range(10): # 0から9までのデバイスを試す
            cap = cv2.VideoCapture(i, cv2.CAP_DSHOW)
            if cap.isOpened():
                cameras.append(i)
                cap.release()
        return cameras
    
    # --- イベントハンドラの定義と割り当て ---
    camera_enabled_var = tk.BooleanVar(value=current_camera_enabled)

    camera_checkbutton = ttk.Checkbutton(startup_settings_frame, text="カメラ監視を有効にする (要OpenCV)", variable=camera_enabled_var, command=toggle_camera_tab_state)
    camera_checkbutton.grid(column=0, row=2, columnspan=3, sticky=tk.W, pady=(10, 0), padx=5)
    
    available_cameras = get_available_cameras()
    ttk.Label(camera_settings_frame, text="使用カメラ:").grid(column=0, row=0, sticky=tk.W, pady=5, padx=5)
    camera_device_index_var = tk.StringVar(value=str(current_camera_device_index))
    camera_device_combo = ttk.Combobox(camera_settings_frame, textvariable=camera_device_index_var, values=available_cameras, state="readonly", width=10)
    camera_device_combo.grid(column=1, row=0, sticky=tk.W, pady=5, padx=5)

    ttk.Label(camera_settings_frame, text="キャプチャ保存先:").grid(column=0, row=1, sticky=tk.W, pady=5, padx=5)
    camera_capture_folder_var = tk.StringVar(value=current_camera_capture_folder)
    def select_capture_folder():
        folder_selected = filedialog.askdirectory(initialdir=os.getcwd())
        if folder_selected:
            camera_capture_folder_var.set(folder_selected)

    capture_folder_entry = ttk.Entry(camera_settings_frame, textvariable=camera_capture_folder_var)
    capture_folder_entry.grid(column=1, row=1, sticky=(tk.W, tk.E), pady=5, padx=5)
    capture_folder_button = ttk.Button(camera_settings_frame, text="選択...", command=select_capture_folder)
    capture_folder_button.grid(column=2, row=1, sticky=tk.W, pady=5, padx=5)

    ttk.Label(camera_settings_frame, text="動き検知の感度:").grid(column=0, row=2, sticky=tk.W, pady=5, padx=5)
    camera_motion_threshold_var = tk.StringVar(value=str(current_camera_motion_threshold))
    motion_threshold_entry = ttk.Entry(camera_settings_frame, width=10, textvariable=camera_motion_threshold_var)
    motion_threshold_entry.grid(column=1, row=2, sticky=tk.W, pady=5, padx=5)
    ttk.Label(camera_settings_frame, text="(値が小さいほど敏感)").grid(column=2, row=2, sticky=tk.W, pady=5, padx=5)

    ttk.Label(camera_settings_frame, text="画像保存日数:").grid(column=0, row=3, sticky=tk.W, pady=5, padx=5)
    camera_retention_days_var = tk.StringVar(value=str(current_camera_retention_days))
    retention_days_entry = ttk.Entry(camera_settings_frame, width=10, textvariable=camera_retention_days_var)
    retention_days_entry.grid(column=1, row=3, sticky=tk.W, pady=5, padx=5)
    ttk.Label(camera_settings_frame, text="日 (0で無期限)").grid(column=2, row=3, sticky=tk.W, pady=5, padx=5)

    def force_delete_captures():
        """キャプチャフォルダ内のすべてのファイルを強制的に削除する"""
        capture_folder_path = camera_capture_folder_var.get()
        if not os.path.isabs(capture_folder_path):
            capture_folder_path = os.path.join(BASE_PATH, capture_folder_path)

        if not os.path.isdir(capture_folder_path):
            messagebox.showwarning("警告", f"キャプチャフォルダが見つかりません:\n{capture_folder_path}", parent=root)
            return

        if not messagebox.askyesno("最終確認", f"本当にキャプチャフォルダ内のすべてのファイルを削除しますか？\n\nフォルダ: {capture_folder_path}\n\nこの操作は元に戻せません。", parent=root):
            return

        try:
            deleted_count = 0
            for filename in os.listdir(capture_folder_path):
                file_path = os.path.join(capture_folder_path, filename)
                if os.path.isfile(file_path):
                    os.remove(file_path)
                    deleted_count += 1
            logging.info(f"{deleted_count}個のキャプチャファイルを削除しました。")
            messagebox.showinfo("成功", f"{deleted_count}個のファイルを削除しました。", parent=root)
        except Exception as e:
            logging.error(f"キャプチャファイルの削除中にエラーが発生しました: {e}", exc_info=True)
            messagebox.showerror("エラー", f"ファイルの削除中にエラーが発生しました:\n{e}", parent=root)

    delete_button = ttk.Button(camera_settings_frame, text="今すぐキャプチャを全削除...", command=force_delete_captures)
    delete_button.grid(column=0, row=4, columnspan=3, sticky=tk.W, pady=(10, 0), padx=5)

    def toggle_camera_settings_state_and_tab():
        """カメラ設定UIの有効/無効を切り替える"""
        state = "normal" if camera_enabled_var.get() and cv2 else "disabled"
        camera_device_combo.config(state=state)
        capture_folder_entry.config(state=state)
        capture_folder_button.config(state=state)
        motion_threshold_entry.config(state=state)
        retention_days_entry.config(state=state)
        delete_button.config(state=state)
        # タブの表示状態も更新
        notebook.tab(5, state=state)

    def reset_preview_objects():
        """プレビュー用のオブジェクトを初期化/再初期化する"""
        nonlocal preview_balls, preview_lines, preview_slideshow_surface, preview_particles, preview_matrix_streams
        preview_particles.clear()
        preview_matrix_streams.clear()

        # ボールモード用
        max_vel = int(max_velocity_var.get()) if max_velocity_var.get().isdigit() and int(max_velocity_var.get()) >= 2 else 2
        preview_balls = [Ball(max_velocity=max_vel, screen_width=PREVIEW_WIDTH, screen_height=PREVIEW_HEIGHT) for _ in range(PREVIEW_BALL_COUNT)]

        # ラインアートモード用
        max_speed = int(line_speed_var.get()) if line_speed_var.get().isdigit() and int(line_speed_var.get()) > 0 else 2
        preview_lines = [Line(max_speed=max_speed, screen_width=PREVIEW_WIDTH, screen_height=PREVIEW_HEIGHT) for _ in range(PREVIEW_LINE_COUNT)]

        # マトリックスモード用
        font_size = int(matrix_font_size_var.get()) if matrix_font_size_var.get().isdigit() and int(matrix_font_size_var.get()) > 0 else 10
        speed = int(matrix_speed_var.get()) if matrix_speed_var.get().isdigit() and int(matrix_speed_var.get()) > 0 else 3
        font_name = matrix_font_var.get()
        stream_count = PREVIEW_WIDTH // font_size
        preview_matrix_streams = [MatrixStream(i * font_size, font_size, speed, PREVIEW_HEIGHT, font_name) for i in range(stream_count)]

        # スライドショーモード用 (静的なグラデーションで代用)
        preview_slideshow_surface.fill(BLACK)
        for i in range(PREVIEW_HEIGHT):
            color = int(i / PREVIEW_HEIGHT * 255)
            pygame.draw.line(preview_slideshow_surface, (color, color, color), (0, i), (PREVIEW_WIDTH, i))

    def toggle_settings_state():
        """ラジオボタンの選択に応じて設定項目の有効/無効を切り替える"""
        selected_mode = saver_mode_var.get()
        # タブのインデックス: 0=一般, 1=ボール, 2=スライドショー, 3=ラインアート, 4=マトリックス (0は常に有効)
        notebook.tab(1, state="normal" if selected_mode == SaverMode.BALLS else "disabled")
        notebook.tab(2, state="normal" if selected_mode == SaverMode.SLIDESHOW else "disabled")
        notebook.tab(3, state="normal" if selected_mode == SaverMode.LINE_ART else "disabled")
        notebook.tab(4, state="normal" if selected_mode == SaverMode.MATRIX else "disabled")
        reset_preview_objects()

    def apply_theme(event):
        style.theme_use(gui_theme_var.get())
    theme_combo.bind("<<ComboboxSelected>>", apply_theme)

    camera_checkbutton.config(command=toggle_camera_settings_state_and_tab)

    ttk.Radiobutton(mode_frame, text="ボール", variable=saver_mode_var, value=SaverMode.BALLS, command=toggle_settings_state).pack(side=tk.LEFT, padx=10)
    ttk.Radiobutton(mode_frame, text="スライドショー", variable=saver_mode_var, value=SaverMode.SLIDESHOW, command=toggle_settings_state).pack(side=tk.LEFT, padx=10)
    ttk.Radiobutton(mode_frame, text="ラインアート", variable=saver_mode_var, value=SaverMode.LINE_ART, command=toggle_settings_state).pack(side=tk.LEFT, padx=10)
    ttk.Radiobutton(mode_frame, text="マトリックス", variable=saver_mode_var, value=SaverMode.MATRIX, command=toggle_settings_state).pack(side=tk.LEFT, padx=10)

    # --- 右ペイン: プレビュー、その他設定、ボタン ---
    preview_container = ttk.LabelFrame(right_pane, text="プレビュー", padding="10")
    preview_container.pack(fill="x", pady=(0, 10))
    preview_frame = tk.Frame(preview_container, width=PREVIEW_WIDTH, height=PREVIEW_HEIGHT, bg="black")
    preview_frame.pack()

    # --- 時刻・バッテリー表示設定 (プレビューの下に移動) ---
    display_settings_frame = ttk.LabelFrame(right_pane, text="時刻・バッテリー表示設定", padding="10")
    display_settings_frame.pack(fill="x", pady=10)
    display_settings_frame.columnconfigure(1, weight=1)
    clock_enabled_var = tk.BooleanVar(value=current_clock_enabled)
    ttk.Checkbutton(display_settings_frame, text="時刻を表示する", variable=clock_enabled_var).grid(column=0, row=0, columnspan=3, sticky=tk.W, pady=5, padx=5)

    ttk.Label(display_settings_frame, text="表示位置:").grid(column=0, row=1, sticky=tk.W, pady=5, padx=5)
    clock_position_var = tk.StringVar(value=current_clock_position)
    position_combo = ttk.Combobox(display_settings_frame, textvariable=clock_position_var, values=["bottomright", "bottomleft", "topright", "topleft"], state="readonly")
    position_combo.grid(column=1, row=1, sticky=(tk.W, tk.E), pady=5, padx=5)

    ttk.Label(display_settings_frame, text="フォントサイズ:").grid(column=0, row=2, sticky=tk.W, pady=5, padx=5)
    clock_font_size_var = tk.StringVar(value=str(current_clock_font_size))
    clock_font_size_entry = ttk.Entry(display_settings_frame, width=10, textvariable=clock_font_size_var)
    clock_font_size_entry.grid(column=1, row=2, sticky=tk.W, pady=5, padx=5)

    ttk.Label(display_settings_frame, text="文字色:").grid(column=0, row=3, sticky=tk.W, pady=5, padx=5)
    def select_color():
        nonlocal current_clock_color
        # 初期色は現在の色(RGBタプル形式)
        initial_color_tuple = tuple(current_clock_color)
        # 色選択ダイアログを開く
        color_code = colorchooser.askcolor(title="色の選択", initialcolor=initial_color_tuple)
        if color_code[1]:  # 色が選択された場合 (color_code[1]は'#rrggbb'形式)
            current_clock_color = [int(c) for c in color_code[0]] # (R,G,B)タプルをリストに変換
            color_preview_label.config(background=color_code[1], text=color_code[1])
    hex_color = f"#{current_clock_color[0]:02x}{current_clock_color[1]:02x}{current_clock_color[2]:02x}"
    color_preview_label = ttk.Label(display_settings_frame, text=hex_color, background=hex_color, width=10, anchor="center", foreground="white")
    color_preview_label.grid(column=1, row=3, sticky=tk.W, pady=5, padx=5)
    ttk.Button(display_settings_frame, text="色を選択...", command=select_color).grid(column=2, row=3, sticky=tk.W, padx=5)

    # PygameをTkinterに埋め込むための準備
    root.update()  # ウィンドウIDを確定させる
    os.environ['SDL_WINDOWID'] = str(preview_frame.winfo_id())
    preview_screen = pygame.display.set_mode((PREVIEW_WIDTH, PREVIEW_HEIGHT))

    # プレビュー用オブジェクト
    preview_balls = []
    preview_lines = []
    preview_particles = []
    preview_matrix_streams = []
    preview_slideshow_surface = pygame.Surface((PREVIEW_WIDTH, PREVIEW_HEIGHT))

    # --- 初期状態の設定 (プレビューオブジェクト作成後) ---
    toggle_settings_state() # モードタブの有効/無効を設定
    toggle_camera_tab_state() # カメラタブの有効/無効を設定

    # --- セキュリティ設定 ---
    security_frame = ttk.LabelFrame(general_tab, text="パスワード・セキュリティ設定", padding="10")
    security_frame.grid(row=1, column=0, sticky="ew")
    security_frame.columnconfigure(1, weight=1)

    def on_change_password_click():
        new_hash = show_password_change_dialog(root, password_hash_to_save[0])
        if new_hash is not None:
            password_hash_to_save[0] = new_hash

    def toggle_password_widgets():
        state = "normal" if password_enabled_var.get() else "disabled"
        change_password_button.config(state=state)
        password_position_combo.config(state=state)

    password_enabled_var = tk.BooleanVar(value=current_password_enabled)
    # パスワードハッシュを一時的に保持する変数。ダイアログで変更された場合に更新される。
    password_hash_to_save = [current_password_hash]

    password_checkbutton = ttk.Checkbutton(security_frame, text="パスワード保護を有効にする", variable=password_enabled_var, command=toggle_password_widgets)
    password_checkbutton.grid(column=0, row=0, columnspan=3, sticky=tk.W, pady=5, padx=5)

    change_password_button = ttk.Button(security_frame, text="パスワードを設定/変更...", command=on_change_password_click)
    change_password_button.grid(column=0, row=1, columnspan=3, sticky=tk.W, pady=(0, 10), padx=5)

    ttk.Label(security_frame, text="UI表示位置:").grid(column=0, row=2, sticky=tk.W, pady=5, padx=5)
    password_ui_position_var = tk.StringVar(value=current_password_ui_position)
    password_position_combo = ttk.Combobox(security_frame, textvariable=password_ui_position_var, values=["center", "top", "bottom"], state="readonly")
    password_position_combo.grid(column=1, row=2, columnspan=2, sticky=(tk.W, tk.E), pady=5, padx=5)

    # --- パスワードUIの見た目設定 ---
    ttk.Label(security_frame, text="フォントサイズ:").grid(column=0, row=3, sticky=tk.W, pady=5, padx=5)
    password_ui_font_size_var = tk.StringVar(value=str(current_password_ui_font_size))
    password_ui_font_size_entry = ttk.Entry(security_frame, width=10, textvariable=password_ui_font_size_var)
    password_ui_font_size_entry.grid(column=1, row=3, sticky=tk.W, pady=5, padx=5)

    # 色選択のためのファクトリ関数
    def create_color_selector(parent, label_text, row, initial_color_list):
        """色選択ウィジェットのセットを作成するヘルパー関数"""
        ttk.Label(parent, text=label_text).grid(column=0, row=row, sticky=tk.W, pady=3, padx=5)
        
        # 色情報を保持するリスト (ミュータブル)
        color_list = list(initial_color_list)

        def select_color_command():
            color_code = colorchooser.askcolor(title="色の選択", initialcolor=tuple(color_list))
            if color_code[1]:
                color_list[:] = [int(c) for c in color_code[0]]
                hex_color = f"#{color_list[0]:02x}{color_list[1]:02x}{color_list[2]:02x}"
                preview_label.config(background=hex_color, text=hex_color)

        hex_color = f"#{color_list[0]:02x}{color_list[1]:02x}{color_list[2]:02x}"
        preview_label = ttk.Label(parent, text=hex_color, background=hex_color, width=10, anchor="center", foreground="white")
        preview_label.grid(column=1, row=row, sticky=tk.W, pady=3, padx=5)
        ttk.Button(parent, text="選択...", command=select_color_command).grid(column=2, row=row, sticky=tk.W, padx=5)
        return color_list # 更新された色情報を返すためにリストを返す

    prompt_color_list = create_color_selector(security_frame, "プロンプト色:", 4, current_password_ui_prompt_color)
    input_color_list = create_color_selector(security_frame, "入力テキスト色:", 5, current_password_ui_input_color)
    warning_color_list = create_color_selector(security_frame, "警告/案内メッセージ色:", 6, current_password_ui_warning_color)

    toggle_password_widgets() # 初期状態を設定

    # --- ボタンフレーム ---
    button_frame = ttk.Frame(right_pane)
    button_frame.pack(side="bottom", pady=10)

    after_id = None  # afterイベントのIDを保持する変数を追加

    def reset_to_defaults():
        """UI上のすべての設定をプログラムのデフォルト値に戻す"""
        if not messagebox.askyesno("確認", "すべての設定をデフォルト値に戻しますか？\nこの操作は元に戻せません。"):
            return

        # UI変数をデフォルト値にリセット
        saver_mode_var.set(DEFAULT_SAVER_MODE)
        timeout_var.set(str(IDLE_TIMEOUT / 1000))

        # ボール
        ball_count_var.set(str(DEFAULT_BALL_COUNT))
        max_velocity_var.set(str(DEFAULT_MAX_VELOCITY))
        wall_spark_enabled_var.set(True)
        particle_color_mode_var.set(DEFAULT_PARTICLE_COLOR_MODE)

        # スライドショー
        slideshow_folder_var.set(DEFAULT_SLIDESHOW_FOLDER)
        slideshow_interval_var.set(str(DEFAULT_SLIDESHOW_INTERVAL))

        # ラインアート
        line_count_var.set(str(DEFAULT_LINE_COUNT))
        line_speed_var.set(str(DEFAULT_LINE_SPEED))

        # マトリックス
        matrix_font_size_var.set(str(DEFAULT_MATRIX_FONT_SIZE))
        matrix_speed_var.set(str(DEFAULT_MATRIX_SPEED))
        matrix_font_var.set(DEFAULT_MATRIX_FONT)

        # 時刻・バッテリー
        clock_enabled_var.set(DEFAULT_CLOCK_ENABLED)
        clock_position_var.set(DEFAULT_CLOCK_POSITION)
        clock_font_size_var.set(str(DEFAULT_CLOCK_FONT_SIZE))
        nonlocal current_clock_color
        current_clock_color = list(DEFAULT_CLOCK_COLOR)
        hex_color = f"#{current_clock_color[0]:02x}{current_clock_color[1]:02x}{current_clock_color[2]:02x}"
        color_preview_label.config(background=hex_color, text=hex_color)

        # パスワード
        password_enabled_var.set(False)
        password_ui_position_var.set(DEFAULT_PASSWORD_UI_POSITION)
        password_ui_font_size_var.set(str(DEFAULT_PASSWORD_UI_FONT_SIZE))
        # 色設定もデフォルトに戻す (UIの更新はファクトリ関数内で完結しないため、ここでは変数のみ更新)
        prompt_color_list[:] = list(DEFAULT_PASSWORD_UI_PROMPT_COLOR)
        input_color_list[:] = list(DEFAULT_PASSWORD_UI_INPUT_COLOR)
        warning_color_list[:] = list(DEFAULT_PASSWORD_UI_WARNING_COLOR)

        # ハッシュもリセット
        nonlocal password_hash_to_save
        password_hash_to_save[0] = None
        # パスワード保護チェックボックスの状態をUIに反映
        toggle_password_widgets()

        # カメラ
        camera_enabled_var.set(DEFAULT_CAMERA_ENABLED)
        camera_device_index_var.set(str(DEFAULT_CAMERA_DEVICE_INDEX))
        camera_capture_folder_var.set(DEFAULT_CAMERA_CAPTURE_FOLDER)
        camera_motion_threshold_var.set(str(DEFAULT_CAMERA_MOTION_THRESHOLD))
        camera_retention_days_var.set(str(DEFAULT_CAMERA_CAPTURE_RETENTION_DAYS))
        auto_restart_var.set(DEFAULT_AUTO_RESTART_ON_IDLE)
        gui_theme_var.set(DEFAULT_GUI_THEME)
        toggle_password_widgets()

        # UIの状態とプレビューを更新
        toggle_settings_state()
        
    def start_and_close():
        nonlocal result_settings
        try:
            new_saver_mode = saver_mode_var.get()

            new_timeout_sec = float(timeout_var.get())
            if new_timeout_sec <= 0:
                raise ValueError("無操作時間は正の数値を入力してください。")

            if new_saver_mode == SaverMode.BALLS:
                new_ball_count = int(ball_count_var.get())
                if new_ball_count <= 0:
                    raise ValueError("ボールの数は1以上の整数を入力してください。")

                new_max_velocity = int(max_velocity_var.get())
                if new_max_velocity < 2:
                    raise ValueError("ボールの最大速度は2以上の整数を入力してください。")
            else:
                new_ball_count = current_ball_count # デフォルト値を維持
                new_max_velocity = current_max_velocity

            if new_saver_mode == SaverMode.SLIDESHOW:
                new_slideshow_folder = slideshow_folder_var.get()
                if not new_slideshow_folder or not os.path.isdir(new_slideshow_folder):
                    raise ValueError("有効な画像フォルダを選択してください。")
                new_slideshow_interval = int(slideshow_interval_var.get())
                if new_slideshow_interval <= 0:
                    raise ValueError("切り替え間隔は1以上の整数を入力してください。")
            else:
                new_slideshow_folder = current_slideshow_folder
                new_slideshow_interval = current_slideshow_interval

            if new_saver_mode == SaverMode.LINE_ART:
                new_line_count = int(line_count_var.get())
                if new_line_count <= 0:
                    raise ValueError("線の数は1以上の整数を入力してください。")
                new_line_speed = int(line_speed_var.get())
                if new_line_speed <= 0:
                    raise ValueError("線の最大速度は1以上の整数を入力してください。")
            else:
                new_line_count = current_line_count
                new_line_speed = current_line_speed
                
            if new_saver_mode == SaverMode.MATRIX:
                new_matrix_font_size = int(matrix_font_size_var.get())
                if new_matrix_font_size <= 0:
                    raise ValueError("フォントサイズは1以上の整数を入力してください。")
                new_matrix_speed = int(matrix_speed_var.get())
                if new_matrix_speed <= 0:
                    raise ValueError("落下速度は1以上の整数を入力してください。")
            else:
                new_matrix_font_size = current_matrix_font_size
                new_matrix_speed = current_matrix_speed
            new_matrix_font = matrix_font_var.get() if new_saver_mode == SaverMode.MATRIX else current_matrix_font
                
            new_clock_enabled = clock_enabled_var.get()
            new_clock_position = clock_position_var.get()
            new_clock_font_size = int(clock_font_size_var.get())
            new_clock_color = current_clock_color # 色選択ボタンで更新されたリストを使用

            new_password_enabled = password_enabled_var.get()
            saved_password_hash = password_hash_to_save[0]
            new_password_ui_position = password_ui_position_var.get()
            new_password_ui_font_size = int(password_ui_font_size_var.get())
            new_password_ui_prompt_color = prompt_color_list
            new_password_ui_input_color = input_color_list
            new_password_ui_warning_color = warning_color_list

            # パスワード保護が有効なのに、パスワードが未設定の場合にエラーを出す
            if new_password_enabled and not saved_password_hash:
                raise ValueError("パスワード保護が有効ですが、パスワードが設定されていません。\n「パスワードを設定/変更...」ボタンから設定してください。")

            new_camera_enabled = camera_enabled_var.get()
            new_camera_device_index = int(camera_device_index_var.get()) if camera_device_index_var.get() else 0
            new_camera_capture_folder = camera_capture_folder_var.get()
            new_camera_motion_threshold = int(camera_motion_threshold_var.get())
            new_camera_retention_days = int(camera_retention_days_var.get())


            new_settings = {
                CfgKey.SAVER_MODE: new_saver_mode,
                CfgKey.IDLE_TIMEOUT: int(new_timeout_sec * 1000),
                CfgKey.BALL_COUNT: new_ball_count,
                CfgKey.MAX_VELOCITY: new_max_velocity,
                CfgKey.SLIDESHOW_FOLDER: new_slideshow_folder,
                CfgKey.SLIDESHOW_INTERVAL: new_slideshow_interval,
                CfgKey.LINE_COUNT: new_line_count,
                CfgKey.LINE_SPEED: new_line_speed,
                CfgKey.MATRIX_FONT_SIZE: new_matrix_font_size,
                CfgKey.MATRIX_SPEED: new_matrix_speed,
                CfgKey.MATRIX_FONT: new_matrix_font,
                CfgKey.PASSWORD_ENABLED: new_password_enabled,
                CfgKey.PASSWORD_HASH: saved_password_hash,
                CfgKey.PASSWORD_UI_POSITION: new_password_ui_position,
                CfgKey.PASSWORD_UI_FONT_SIZE: new_password_ui_font_size,
                CfgKey.PASSWORD_UI_PROMPT_COLOR: new_password_ui_prompt_color,
                CfgKey.PASSWORD_UI_INPUT_COLOR: new_password_ui_input_color,
                CfgKey.PASSWORD_UI_WARNING_COLOR: new_password_ui_warning_color,
                CfgKey.PASSWORD_UI_INFO_COLOR: new_password_ui_warning_color, # 案内色も警告色と共有
                CfgKey.CLOCK_ENABLED: new_clock_enabled,
                CfgKey.CLOCK_POSITION: new_clock_position,
                CfgKey.CLOCK_COLOR: new_clock_color,
                CfgKey.CLOCK_FONT_SIZE: new_clock_font_size,
                CfgKey.PARTICLE_COLOR_MODE: particle_color_mode_var.get(),
                CfgKey.WALL_SPARK_ENABLED: wall_spark_enabled_var.get(),
                CfgKey.CAMERA_ENABLED: new_camera_enabled,
                CfgKey.CAMERA_DEVICE_INDEX: new_camera_device_index,
                CfgKey.CAMERA_CAPTURE_FOLDER: new_camera_capture_folder,
                CfgKey.CAMERA_MOTION_THRESHOLD: new_camera_motion_threshold,
                CfgKey.CAMERA_CAPTURE_RETENTION_DAYS: new_camera_retention_days,
                CfgKey.AUTO_RESTART_ON_IDLE: auto_restart_var.get(),
                CfgKey.GUI_THEME: gui_theme_var.get(),
            }

            # 設定を保存
            save_settings(new_settings)

            # 保存が成功したら、結果をセットしてGUIを閉じる
            result_settings = new_settings
            quit_gui(save_successful=True)

        except ValueError as e:
            messagebox.showerror("入力エラー", str(e) if str(e) else "すべての項目に有効な数値を入力してください。")
        except Exception as e:
            messagebox.showerror("保存エラー", f"設定の保存中にエラーが発生しました。\n\n詳細: {e}")

    ttk.Button(button_frame, text="スクリーンセーバー開始", command=start_and_close).pack(side=tk.LEFT, padx=5)
    ttk.Button(button_frame, text="デフォルト設定に戻す", command=reset_to_defaults).pack(side=tk.LEFT, padx=5)
    
    is_preview_running = True
    def quit_gui(save_successful=False):
        nonlocal is_preview_running, after_id
        # 保存に失敗した場合は、設定を返さないようにする
        if not save_successful:
            nonlocal result_settings
            result_settings = None

        if after_id:
            root.after_cancel(after_id) # スケジュールされたイベントをキャンセル
            after_id = None
        is_preview_running = False
        # Pygameの表示をクリーンアップしてからTkinterウィンドウを閉じる
        pygame.display.quit()
        if "SDL_WINDOWID" in os.environ:
            del os.environ['SDL_WINDOWID']
        root.destroy()

    ttk.Button(button_frame, text="終了", command=quit_gui).pack(side=tk.LEFT, padx=5)

    # プレビュー更新ループ
    def update_preview():
        nonlocal after_id

        selected_mode = saver_mode_var.get()
        preview_screen.fill(BLACK)

        if selected_mode == SaverMode.BALLS:
            # ボールを移動
            for ball in preview_balls:
                wall_collision_info = ball.move()
                if wall_spark_enabled_var.get() and wall_collision_info:
                    # 壁との衝突で花火を生成 (プレビュー用)
                    num_particles = 3 # さらに少なめに
                    cx, cy, p_color = wall_collision_info
                    for _ in range(num_particles):
                        preview_particles.append(Particle(cx, cy, p_color, particle_color_mode_var.get()))
            
            # プレビュー用の衝突判定と花火生成
            for i in range(len(preview_balls)):
                for j in range(i + 1, len(preview_balls)):
                    ball1 = preview_balls[i]
                    ball2 = preview_balls[j]
                    dx = ball1.x - ball2.x
                    dy = ball1.y - ball2.y
                    dist_sq = dx**2 + dy**2
                    if dist_sq < (ball1.radius + ball2.radius)**2:
                        # 簡易的な反発
                        ball1.dx, ball2.dx = ball2.dx, ball1.dx
                        ball1.dy, ball2.dy = ball2.dy, ball1.dy
                        # 花火生成
                        num_particles = 5 # プレビューは少なめに
                        cx = (ball1.x + ball2.x) / 2
                        cy = (ball1.y + ball2.y) / 2
                        p_color = ball1.color
                        for _ in range(num_particles):
                            preview_particles.append(Particle(cx, cy, p_color, particle_color_mode_var.get()))

            # ボールを描画
            for ball in preview_balls:
                ball.draw(preview_screen)
        elif selected_mode == SaverMode.SLIDESHOW:
            # プレビューでは静的な画像を表示
            preview_screen.blit(preview_slideshow_surface, (0, 0))
        elif selected_mode == SaverMode.LINE_ART:
            for line in preview_lines:
                line.move()
                line.draw(preview_screen)
        elif selected_mode == SaverMode.MATRIX:
            for stream in preview_matrix_streams:
                stream.update()
                stream.draw(preview_screen)
        
        # パーティクルを描画 (モードに関わらず描画し続けることで、モード切り替え後も残像が消える)
        for p in preview_particles[:]:
            p.move()
            p.draw(preview_screen)
            if p.lifespan <= 0:
                preview_particles.remove(p)
        
        pygame.display.update()
        after_id = root.after(16, update_preview)  # 約60fpsで更新し、IDを保存

    # プレビューループを開始
    update_preview()

    root.mainloop()

    return result_settings

def authenticate_with_pygame_ui(settings):
    """Pygameウィンドウを使用してパスワード認証を行う。"""
    password_hash = settings.get(CfgKey.PASSWORD_HASH)
    if not password_hash:
        return True # パスワードが設定されていなければ認証成功

    pygame.init()
    INFO = pygame.display.Info()
    SCREEN_WIDTH, SCREEN_HEIGHT = INFO.current_w, INFO.current_h
    screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.FULLSCREEN)
    pygame.display.set_caption("パスワード認証")

    try:
        font = pygame.font.SysFont("meiryo", 40)
        small_font = pygame.font.SysFont("meiryo", 20)
    except pygame.error:
        font = pygame.font.Font(None, 50)
        small_font = pygame.font.Font(None, 25)

    input_text = ""
    running = True
    authenticated = False
    error_message = ""
    clock = pygame.time.Clock()

    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                elif event.key == pygame.K_RETURN:
                    entered_hash = hashlib.sha256(input_text.encode()).hexdigest()
                    if entered_hash == password_hash:
                        authenticated = True
                        running = False
                    else:
                        error_message = "パスワードが違います。再入力してください。"
                        input_text = ""
                elif event.key == pygame.K_BACKSPACE:
                    input_text = input_text[:-1]
                    error_message = "" # エラーメッセージをクリア
                else:
                    input_text += event.unicode
                    error_message = "" # エラーメッセージをクリア

        screen.fill(BLACK)

        # UI要素の描画
        box_width, box_height = 500, 180
        box_x = (SCREEN_WIDTH - box_width) / 2
        box_y = (SCREEN_HEIGHT - box_height) / 2

        pygame.draw.rect(screen, (30, 30, 30), (box_x, box_y, box_width, box_height))
        pygame.draw.rect(screen, (200, 200, 200), (box_x, box_y, box_width, box_height), 2)

        # テキスト
        prompt_surface = font.render("パスワードを入力:", True, (255, 255, 255))
        screen.blit(prompt_surface, (box_x + 20, box_y + 20))

        # 入力中のパスワード（アスタリスクで表示）
        input_surface = font.render("*" * len(input_text), True, (255, 255, 255))
        screen.blit(input_surface, (box_x + 20, box_y + 80))

        # エラーメッセージ
        if error_message:
            error_surface = small_font.render(error_message, True, (255, 100, 100))
            screen.blit(error_surface, (box_x + 20, box_y + 140))
        else:
            # 通常の案内
            info_surface = small_font.render("Enterで決定、Escでキャンセル", True, (150, 150, 150))
            screen.blit(info_surface, (box_x + 20, box_y + 140))

        pygame.display.flip()
        clock.tick(60)

    # pygame.quit() # ここで終了すると、後続のGUIでPygameが使えなくなるためコメントアウト
    return authenticated


if __name__ == '__main__':
    # --- 必須ライブラリのインポートチェック ---
    # ... (ライブラリチェックのコードは変更なし) ...

    # ロギングを設定
    setup_logging()

    # まず設定を読み込む
    settings = load_settings()
    authenticated = True # デフォルトは認証済み

    # パスワードが設定されていれば、Pygame UIで認証を行う
    # コマンドライン引数 /c が指定された場合は認証をスキップして設定画面を開く
    is_config_mode = len(sys.argv) > 1 and sys.argv[1].lower() == '/c'

    if not is_config_mode and settings.get(CfgKey.PASSWORD_ENABLED) and settings.get(CfgKey.PASSWORD_HASH):
        # 認証UIのためにPygameを初期化
        if not pygame.get_init():
            pygame.init()
        authenticated = authenticate_with_pygame_ui(settings)
        # 認証UIで使用したPygameディスプレイを閉じる。これにより次のGUIが正しく表示される。
        pygame.display.quit()

    if authenticated:
        # 認証成功後、設定GUIを開く
        new_settings = open_settings_gui()
        
        try:
            # GUIが正常に終了し、かつ設定モードでない場合のみセーバーを開始
            if new_settings is not None and not is_config_mode:
                tray_thread = threading.Thread(target=setup_tray_icon)
                tray_thread.start()

                while True: # メインの実行ループ
                    # スクリーンセーバーを起動し、ユーザー操作で終了したかどうかの結果を受け取る
                    user_exited = main(new_settings)

                    # ユーザー操作で終了した場合、プログラム全体を終了する
                    if user_exited:
                        logging.info("ユーザー操作によりスクリーンセーバーが解除されたため、プログラムを終了します。")
                        break # メインループを抜けて finally ブロックへ

                    # トレイからの終了などで main が抜けた場合、無操作監視に入る
                    # ただし、トレイアイコンが既に終了していたらループを抜ける
                    if not tray_thread.is_alive():
                        break

                    auto_restart = new_settings.get(CfgKey.AUTO_RESTART_ON_IDLE, DEFAULT_AUTO_RESTART_ON_IDLE)
                    idle_timeout_ms = new_settings.get(CfgKey.IDLE_TIMEOUT, IDLE_TIMEOUT)

                    # Windowsかつwin32apiが利用可能で、設定が有効な場合のみ監視
                    if sys.platform == "win32" and win32api and auto_restart:
                        logging.info("無操作監視ループを開始します。")
                        while tray_thread.is_alive():
                            # Windowsのアイドル時間を取得 (ミリ秒)
                            idle_ms = win32api.GetTickCount() - win32api.GetLastInputInfo()
                            if idle_ms < 0: idle_ms = 0 # ティックカウントのリセット対策

                            if idle_ms > idle_timeout_ms:
                                logging.info(f"無操作時間が{idle_timeout_ms / 1000}秒を超えたため、セーバーを再起動します。")
                                break # 無操作監視ループを抜けて、外側のメインループの先頭に戻る
                            
                            pygame.time.wait(1000) # 1秒ごとにチェック
                    else:
                        # 無操作監視が不要な場合、トレイが終了するまで待機
                        if tray_thread.is_alive():
                            tray_thread.join()
                        break # 待機終了後、メインループを抜ける
        finally:
            # プログラムの最後に必ずクリーンアップ処理を呼び出す
            cleanup_on_exit()
            logging.info("プログラムを正常に終了しました。")
