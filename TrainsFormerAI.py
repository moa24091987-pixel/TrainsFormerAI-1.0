import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, filedialog
import warnings
import json
import os
from datetime import datetime
import threading
import queue
import sys
import difflib
import webbrowser

warnings.filterwarnings("ignore")

try:
    from transformers import OpenAIGPTTokenizer, OpenAIGPTLMHeadModel, AutoTokenizer, AutoModelForCausalLM
    import torch
    TRANSFORMERS_AVAILABLE = True
except ImportError as e:
    print(f"Ошибка импорта transformers: {e}")
    print("Установите библиотеки: pip install transformers torch")
    TRANSFORMERS_AVAILABLE = False
    
    class Stub:
        def __init__(self, *args, **kwargs):
            pass
        def from_pretrained(self, *args, **kwargs):
            return self
        def to(self, *args, **kwargs):
            return self
        def generate(self, *args, **kwargs):
            return [[1, 2, 3]]
        def encode(self, *args, **kwargs):
            return [[1, 2, 3]]
        def decode(self, *args, **kwargs):
            return "Тестовый ответ (библиотеки не установлены)"
    
    OpenAIGPTTokenizer = Stub
    OpenAIGPTLMHeadModel = Stub
    AutoTokenizer = Stub
    AutoModelForCausalLM = Stub
    torch = type('torch', (), {'device': lambda x: 'cpu', 'cuda': type('cuda', (), {'is_available': lambda: False})()})()

try:
    from googletrans import Translator
    TRANSLATOR_AVAILABLE = True
    translator = Translator()
except ImportError:
    print("Библиотека googletrans не установлена. Установите: pip install googletrans==4.0.0-rc1")
    TRANSLATOR_AVAILABLE = False
    translator = None

class KnowledgeBase:
    def __init__(self, education_dir):
        self.education_dir = education_dir
        self.data = []
        self.load_data()
    
    def load_data(self):
        """Загружает данные из ВСЕХ TXT файлов в папке education/"""
        self.data = []
        
        if not os.path.exists(self.education_dir):
            print(f"Папка {self.education_dir} не найдена. Создаю...")
            os.makedirs(self.education_dir)
            return
        
        txt_files = [f for f in os.listdir(self.education_dir) 
                    if f.endswith('.txt')]
        
        if not txt_files:
            print(f"В папке {self.education_dir} нет TXT файлов.")
            return
        
        total_loaded = 0
        for txt_file in txt_files:
            filepath = os.path.join(self.education_dir, txt_file)
            loaded = self.load_txt_file(filepath)
            total_loaded += loaded
            print(f"Загружено {loaded} записей из {txt_file}")
        
        print(f"Всего загружено {total_loaded} записей из {len(txt_files)} файлов")
    
    def load_txt_file(self, filepath):
        """Загружает данные из TXT файла ЛЮБОГО формата"""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
            
            loaded_count = 0
            
            lines = content.strip().split('\n')
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                
                if '|' in line:
                    parts = [part.strip() for part in line.split('|')]
                    if len(parts) >= 2:
                        self.data.append({
                            'russian': parts[0],
                            'english': parts[1] if len(parts) > 1 else '',
                            'context': parts[2] if len(parts) > 2 else '',
                            'source_file': os.path.basename(filepath),
                            'type': 'structured'
                        })
                        loaded_count += 1
                else:
                    self.data.append({
                        'russian': line,
                        'english': '',  # Будет переводиться автоматически
                        'context': 'text',
                        'source_file': os.path.basename(filepath),
                        'type': 'free_text'
                    })
                    loaded_count += 1
            
            return loaded_count
                
        except Exception as e:
            print(f"Ошибка загрузки файла {filepath}: {e}")
            return 0
    
    def add_data(self, russian, english, context="", source_file=""):
        """Добавляет новую запись в базу знаний"""
        self.data.append({
            'russian': russian,
            'english': english,
            'context': context,
            'source_file': source_file
        })
    
    def save_to_file(self, filename=None):
        """Сохраняет данные в talk.txt (для обратной совместимости)"""
        if not filename:
            filename = os.path.join(self.education_dir, "talk.txt")
        
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                for item in self.data:
                    line = f"{item['russian']} | {item['english']} | {item['context']}"
                    f.write(line + '\n')
            print(f"Сохранено {len(self.data)} записей в {filename}")
        except Exception as e:
            print(f"Ошибка сохранения {filename}: {e}")
    
    def find_similar(self, query, threshold=0.3):
        """Ищет похожие фразы в базе знаний"""
        if not query:
            return []
        
        query_lower = query.lower()
        results = []
        
        for item in self.data:
            russian_lower = item['russian'].lower()
            
            similarity = difflib.SequenceMatcher(None, query_lower, russian_lower).ratio()
            
            if similarity >= threshold:
                results.append({
                    'similarity': similarity,
                    'item': item
                })
        
        results.sort(key=lambda x: x['similarity'], reverse=True)
        return results
    
    def import_txt_file(self, filepath):
        """Импортирует данные из TXT файла в ЛЮБОМ формате"""
        try:
            filename = os.path.basename(filepath)
            dest_path = os.path.join(self.education_dir, filename)
            
            counter = 1
            while os.path.exists(dest_path):
                name, ext = os.path.splitext(filename)
                dest_path = os.path.join(self.education_dir, f"{name}_{counter}{ext}")
                counter += 1
            
            import shutil
            shutil.copy2(filepath, dest_path)
            
            loaded = self.load_txt_file(dest_path)
            
            if loaded > 0:
                return {
                    'success': True,
                    'loaded': loaded,
                    'filename': os.path.basename(dest_path),
                    'path': dest_path
                }
            else:
                return {
                    'success': False,
                    'message': "Файл пуст или содержит некорректные данные"
                }
                
        except Exception as e:
            print(f"Ошибка импорта файла {filepath}: {e}")
            return {
                'success': False,
                'message': str(e)
            }
    
    def get_stats(self):
        """Возвращает статистику базы знаний"""
        txt_files = []
        if os.path.exists(self.education_dir):
            txt_files = [f for f in os.listdir(self.education_dir) 
                        if f.endswith('.txt')]
        
        files_data = {}
        for item in self.data:
            source = item.get('source_file', 'unknown.txt')
            if source not in files_data:
                files_data[source] = 0
            files_data[source] += 1
        
        return {
            'total_entries': len(self.data),
            'total_files': len(txt_files),
            'files': txt_files,
            'files_data': files_data,
            'education_dir': self.education_dir,
            'exists': len(self.data) > 0
        }

class ModernGPTLauncher:
    def __init__(self, root):
        self.root = root
        self.root.title("TrainsFormer AI")
        self.root.geometry("1400x900")
        self.root.minsize(1200, 700)
        
        self.root.configure(bg='#1e293b')
        
        self.setup_logging()
        
        print("Инициализация приложения...")
        
        self.style = ttk.Style()
        self.style.theme_use('clam')
        
        self.setup_rounded_styles()
        self.setup_colors()
        self.setup_fonts()
        
        self.current_model = None
        self.current_tokenizer = None
        self.current_device = None
        self.model_type = "GPT-1"
        self.language = "Русский"
        self.chats = []
        self.current_chat_id = 0
        self.chat_data = {}
        
        self.translate_enabled = False
        self.auto_translate = False
        self.target_translate_lang = "en"
        
        self.data_dir = os.path.join(os.path.expanduser("~"), "Documents", "TrainsFormerAI")
        self.education_dir = os.path.join(self.data_dir, "education")
        self.config_file = os.path.join(self.data_dir, "config.json")
        self.data_file = os.path.join(self.data_dir, "chats_data.json")
        
        if not os.path.exists(self.data_dir):
            os.makedirs(self.data_dir)
        if not os.path.exists(self.education_dir):
            os.makedirs(self.education_dir)
        
        self.knowledge_base = KnowledgeBase(self.education_dir)
        
        self.assistant_settings = {
            'response_length': 100,
            'temperature': 0.7,
            'advanced_analysis': True
        }
        
        self.load_config()
        self.load_chats_data()
        
        self.assistant_chats = []
        self.current_assistant_chat_id = 0
        
        self.message_queue = queue.Queue()
        
        self.language_dict = {
            "Русский": {
                "title": "TrainsFormer AI",
                "new_chat": "Новый чат",
                "chats": "Чаты",
                "model": "Model",
                "settings": "Настройки",
                "language": "Язык",
                "input_placeholder": "Введите ваше сообщение...",
                "send": "Отправить",
                "copy": "Копировать",
                "delete": "Удалить",
                "clear": "Очистить",
                "length": "Длина",
                "creativity": "Креативность",
                "history": "История",
                "rename": "Переименовать",
                "load_error": "Ошибка загрузки",
                "enter_text": "Введите текст",
                "copied": "Скопировано",
                "deleted": "Удалено",
                "generating": "Генерация...",
                "select_chat": "Выберите чат",
                "delete_chat": "Удалить чат",
                "confirm_delete": "Удалить этот чат?",
                "classic_models": "Классические AI модели",
                "gpt1": "GPT-1",
                "gpt2": "GPT-2",
                "user_prefix": "Вы",
                "gpt_prefix": "LLM",
                "system_prefix": "Система",
                "chat_prefix": "Чат ",
                "ready": "Готов",
                "loading": "Загрузка...",
                "model_ready": "Модель загружена и готова к работе",
                "no_messages": "Нет сообщений",
                "model_label_gpt1": "GPT-1 (117M параметров)",
                "model_label_gpt2": "GPT-2 (1.5B параметров)",
                "export": "Экспорт",
                "import": "Импорт",
                "search": "Поиск...",
                "translate": "Перевод",
                "enable_translate": "Включить перевод",
                "auto_translate": "Автоперевод",
                "translate_to": "Переводить на",
                "translate_now": "Перевести",
                "translated": "Переведено",
                "dark_mode": "Темная тема",
                "light_mode": "Светлая тема",
                "markdown": "Markdown",
                "export_chat": "Экспорт чата",
                "import_chat": "Импорт чата",
                "save_as": "Сохранить как...",
                "open_file": "Открыть файл",
                "file_types": "JSON файлы",
                "export_success": "Чат успешно экспортирован",
                "import_success": "Чат успешно импортирован",
                "clear_chat": "Очистить чат",
                "confirm_clear": "Очистить историю чата?",
                "statistics": "Статистики",
                "chars": "символов",
                "words": "слов",
                "messages": "сообщений",
                "today": "Сегодня",
                "total": "Всего",
                "voice_input": "Голосовой ввод",
                "start_recording": "Начать запись",
                "stop_recording": "Остановить запись",
                "theme": "Тема",
                "api_settings": "Помочь в развитии",
                "save": "Сохранить",
                "cancel": "Отмена",
                "enter_api_key": "Введите API ключ",
                "smart_assistant": "Умный помощник",
                "knowledge_base": "База знаний",
                "load_txt": "Загрузить TXT",
                "stats": "Статистика",
                "entries": "записей",
                "search_knowledge": "Поиск в базе знаний...",
                "found_similar": "Найдено похожих",
                "using_knowledge": "Использую базу знаний",
                "assistant_thinking": "🤔 Ассистент думает...",
                "import_file": "Импорт файла",
                "select_txt_file": "Выберите TXT файл",
                "import_success_kb": "Импорт успешен! Добавлено",
                "import_error": "Ошибка импорта",
                "no_entries_found": "Записей не найдено",
                "format_error": "Неправильный формат файла",
                "file_types_txt": "Текстовые файлы",
                "assistant_mode": "Режим помощника",
                "chat_mode": "Режим чата",
                "education_stats": "Статистика обучения",
                "refresh": "Обновить",
                "current_kb": "Текущая база знаний",
                "total_phrases": "Всего фраз",
                "instructions_title": "💡 КАК ПОЛЬЗОВАТЬСЯ:",
                "instructions_1": "1. Киньте TXT файлы в папку education/",
                "instructions_2": "2. Формат: русский | английский | тема (или просто текст)",
                "instructions_3": "3. Спросите что-нибудь на русском",
                "instructions_4": "4. Кликните ⎘ чтобы скопировать ответ",
                "assistant_history": "История помощника",
                "copy_all_dialogue": "📋 Копировать весь диалог",
                "advanced_settings": "⚙️ Настройки помощника",
                "assistant_config": "Настройки помощника",
                "response_length_assistant": "Длина ответа помощника:",
                "apply": "Применить",
                "close": "Закрыть",
                "support_boosty": "Support on Boosty",
                "boosty_subtext": "Low cost beta tester role"
            },
            "English": {
                "title": "TrainsFormer AI",
                "new_chat": "New Chat",
                "chats": "Chats",
                "model": "Model",
                "settings": "Settings",
                "language": "Language",
                "input_placeholder": "Type your message...",
                "send": "Send",
                "copy": "Copy",
                "delete": "Delete",
                "clear": "Clear",
                "length": "Length",
                "creativity": "Creativity",
                "history": "History",
                "rename": "Rename",
                "load_error": "Load error",
                "enter_text": "Enter text",
                "copied": "Copied",
                "deleted": "Deleted",
                "generating": "Generating...",
                "select_chat": "Select chat",
                "delete_chat": "Delete chat",
                "confirm_delete": "Delete this chat?",
                "classic_models": "Classic AI Models",
                "gpt1": "GPT-1",
                "gpt2": "GPT-2",
                "user_prefix": "You",
                "gpt_prefix": "LLM",
                "system_prefix": "System",
                "chat_prefix": "Chat ",
                "ready": "Ready",
                "loading": "Loading...",
                "model_ready": "Model loaded and ready to work",
                "no_messages": "No messages",
                "model_label_gpt1": "GPT-1 (117M parameters)",
                "model_label_gpt2": "GPT-2 (1.5B parameters)",
                "export": "Export",
                "import": "Import",
                "search": "Search...",
                "translate": "Translation",
                "enable_translate": "Enable translation",
                "auto_translate": "Auto-translate",
                "translate_to": "Translate to",
                "translate_now": "Translate",
                "translated": "Translated",
                "dark_mode": "Dark theme",
                "light_mode": "Light theme",
                "markdown": "Markdown",
                "export_chat": "Export chat",
                "import_chat": "Import chat",
                "save_as": "Save as...",
                "open_file": "Open file",
                "file_types": "JSON files",
                "export_success": "Chat exported successfully",
                "import_success": "Chat imported successfully",
                "clear_chat": "Clear chat",
                "confirm_clear": "Clear chat history?",
                "statistics": "Statistics",
                "chars": "chars",
                "words": "words",
                "messages": "messages",
                "today": "Today",
                "total": "Total",
                "voice_input": "Voice input",
                "start_recording": "Start recording",
                "stop_recording": "Stop recording",
                "theme": "Theme",
                "api_settings": "Help develop the project",
                "save": "Save",
                "cancel": "Cancel",
                "enter_api_key": "Enter API key",
                "smart_assistant": "Smart Assistant",
                "knowledge_base": "Knowledge Base",
                "load_txt": "Load TXT",
                "stats": "Statistics",
                "entries": "entries",
                "search_knowledge": "Search in knowledge base...",
                "found_similar": "Found similar",
                "using_knowledge": "Using knowledge base",
                "assistant_thinking": "🤔 Assistant thinking...",
                "import_file": "Import File",
                "select_txt_file": "Select TXT file",
                "import_success_kb": "Import successful! Added",
                "import_error": "Import error",
                "no_entries_found": "No entries found",
                "format_error": "Invalid file format",
                "file_types_txt": "Text files",
                "assistant_mode": "Assistant mode",
                "chat_mode": "Chat mode",
                "education_stats": "Education statistics",
                "refresh": "Refresh",
                "current_kb": "Current knowledge base",
                "total_phrases": "Total phrases",
                "instructions_title": "💡 HOW TO USE:",
                "instructions_1": "1. Drop TXT files in education/ folder",
                "instructions_2": "2. Format: russian | english | topic (or just text)",
                "instructions_3": "3. Ask something in Russian",
                "instructions_4": "4. Click ⎘ to copy the answer",
                "assistant_history": "Assistant history",
                "copy_all_dialogue": "📋 Copy entire dialogue",
                "advanced_settings": "⚙️ Assistant settings",
                "assistant_config": "Assistant settings",
                "response_length_assistant": "Assistant response length:",
                "apply": "Apply",
                "close": "Close",
                "support_boosty": "Support on Boosty",
                "boosty_subtext": "Low cost beta tester role"
            }
        }
        
        self.translate_languages = {
            "en": "English",
            "ru": "Русский",
            "es": "Español",
            "fr": "Français",
            "de": "Deutsch",
            "zh": "中文",
            "ja": "日本語",
            "ko": "한국어",
            "ar": "العربية"
        }
        
        self.assistant_chats = []
        self.current_assistant_chat_id = 0
        
        print("Создание интерфейса...")
        try:
            self.create_widgets()
            print("Интерфейс создан успешно")
        except Exception as e:
            print(f"Ошибка при создании интерфейса: {e}")
            messagebox.showerror("Ошибка", f"Не удалось создать интерфейс: {e}")
            return
        
        if TRANSFORMERS_AVAILABLE:
            self.load_model("GPT-1")
        else:
            print("Библиотеки transformers/torch не установлены, используется режим тестирования")
            self.model_status = tk.Label(text="Тестовый режим (установите transformers)", fg='orange')
        
        if not self.chats:
            self.create_new_chat()
        elif self.chats:
            self.load_chat(self.chats[0]['id'])
        
        self.root.after(100, self.process_queue)
        
        print("Приложение запущено успешно!")
    
    def copy_entire_assistant_dialogue(self):
        """Копирует весь диалог с помощником в буфер обмена"""
        dialogue_text = ""
        
        for chat in self.assistant_chats:
            if chat['id'] == self.current_assistant_chat_id:
                if 'messages' in chat and chat['messages']:
                    for msg in chat['messages']:
                        if msg['role'] == 'user':
                            dialogue_text += f"Вы ({msg.get('timestamp', '')}): {msg['content']}\n"
                        elif msg['role'] == 'assistant':
                            dialogue_text += f"Помощник ({msg.get('timestamp', '')}): {msg['content']}"
                            if msg.get('knowledge_info'):
                                dialogue_text += f" [{msg['knowledge_info']}]"
                            dialogue_text += "\n"
                        dialogue_text += "\n"
                break
        
        if dialogue_text:
            self.root.clipboard_clear()
            self.root.clipboard_append(dialogue_text)
            
            lang = self.language_dict[self.language]
            messagebox.showinfo("Скопировано", "Весь диалог скопирован в буфер обмена!")
        else:
            lang = self.language_dict[self.language]
            messagebox.showwarning("Нет данных", "Нет сообщений для копирования")
    
    def open_assistant_settings(self):
        """Открывает окно настроек помощника"""
        settings_window = tk.Toplevel(self.root)
        settings_window.title(self.language_dict[self.language]["assistant_config"])
        settings_window.geometry("400x300")
        settings_window.configure(bg=self.theme_colors['bg'])
        settings_window.resizable(False, False)
        
        center_frame = tk.Frame(settings_window, bg=self.theme_colors['bg'])
        center_frame.pack(expand=True, fill=tk.BOTH, padx=30, pady=30)
        
        lang = self.language_dict[self.language]
        
        title_label = tk.Label(center_frame, text=lang["assistant_config"], 
                              font=self.fonts['h2'],
                              bg=self.theme_colors['bg'], fg=self.theme_colors['text'])
        title_label.pack(anchor='w', pady=(0, 20))
        
        length_frame = tk.Frame(center_frame, bg=self.theme_colors['bg'])
        length_frame.pack(fill=tk.X, pady=10)
        
        length_label = tk.Label(length_frame, text=lang["response_length_assistant"],
                              font=self.fonts['body'],
                              bg=self.theme_colors['bg'], fg=self.theme_colors['text'])
        length_label.pack(side=tk.LEFT)
        
        self.assistant_length_var = tk.IntVar(value=self.assistant_settings['response_length'])
        length_scale = tk.Scale(length_frame, from_=50, to=500,
                               variable=self.assistant_length_var,
                               orient=tk.HORIZONTAL,
                               length=200,
                               bg=self.theme_colors['bg'],
                               fg=self.theme_colors['text'],
                               highlightthickness=0)
        length_scale.pack(side=tk.RIGHT)
        
        temp_frame = tk.Frame(center_frame, bg=self.theme_colors['bg'])
        temp_frame.pack(fill=tk.X, pady=10)
        
        temp_label = tk.Label(temp_frame, text="Креативность ответа:",
                            font=self.fonts['body'],
                            bg=self.theme_colors['bg'], fg=self.theme_colors['text'])
        temp_label.pack(side=tk.LEFT)
        
        self.assistant_temp_var = tk.DoubleVar(value=self.assistant_settings['temperature'])
        temp_scale = tk.Scale(temp_frame, from_=0.1, to=1.5,
                             variable=self.assistant_temp_var,
                             orient=tk.HORIZONTAL,
                             length=200,
                             resolution=0.1,
                             bg=self.theme_colors['bg'],
                             fg=self.theme_colors['text'],
                             highlightthickness=0)
        temp_scale.pack(side=tk.RIGHT)
        
        analysis_frame = tk.Frame(center_frame, bg=self.theme_colors['bg'])
        analysis_frame.pack(fill=tk.X, pady=10)
        
        self.assistant_analysis_var = tk.BooleanVar(value=self.assistant_settings['advanced_analysis'])
        analysis_check = tk.Checkbutton(analysis_frame, text="Расширенный анализ текста",
                                      variable=self.assistant_analysis_var,
                                      font=self.fonts['body'],
                                      bg=self.theme_colors['bg'],
                                      fg=self.theme_colors['text'],
                                      selectcolor=self.theme_colors['primary'])
        analysis_check.pack(anchor='w')
        
        button_frame = tk.Frame(center_frame, bg=self.theme_colors['bg'])
        button_frame.pack(fill=tk.X, pady=(20, 0))
        
        def apply_settings():
            self.assistant_settings['response_length'] = self.assistant_length_var.get()
            self.assistant_settings['temperature'] = self.assistant_temp_var.get()
            self.assistant_settings['advanced_analysis'] = self.assistant_analysis_var.get()
            messagebox.showinfo("Сохранено", "Настройки сохранены!")
        
        apply_btn = tk.Button(button_frame, text=lang["apply"],
                            font=self.fonts['body'],
                            bg=self.theme_colors['primary'],
                            fg='white',
                            bd=0,
                            padx=20,
                            pady=10,
                            cursor='hand2',
                            command=apply_settings)
        apply_btn.pack(side=tk.RIGHT, padx=5)
        
        close_btn = tk.Button(button_frame, text=lang["close"],
                           font=self.fonts['body'],
                           bg=self.theme_colors['card'],
                           fg=self.theme_colors['text'],
                           bd=0,
                           padx=20,
                           pady=10,
                           cursor='hand2',
                           command=settings_window.destroy)
        close_btn.pack(side=tk.RIGHT, padx=5)
    
    def add_to_assistant_history(self, role, content, knowledge_info=""):
        """Добавляет сообщение в историю помощника (только в памяти)"""
        chat_exists = False
        for chat in self.assistant_chats:
            if chat['id'] == self.current_assistant_chat_id:
                chat_exists = True
                timestamp = datetime.now().strftime("%H:%M")
                message = {
                    'role': role,
                    'content': content,
                    'timestamp': timestamp,
                    'knowledge_info': knowledge_info
                }
                chat['messages'].append(message)
                chat['last_modified'] = datetime.now().isoformat()
                break
        
        if not chat_exists:
            chat_id = len(self.assistant_chats)
            timestamp = datetime.now().strftime("%d.%m %H:%M")
            chat_data = {
                'id': chat_id,
                'name': f"Помощник {chat_id + 1} • {timestamp}",
                'created_at': datetime.now().isoformat(),
                'last_modified': datetime.now().isoformat(),
                'messages': []
            }
            self.assistant_chats.append(chat_data)
            self.current_assistant_chat_id = chat_id
            self.add_to_assistant_history(role, content, knowledge_info)
    
    def load_assistant_chat_history(self):
        """Загружает историю текущего чата помощника в окно"""
        self.assistant_chat_display.config(state=tk.NORMAL)
        self.assistant_chat_display.delete('1.0', 'end')
        
        for chat in self.assistant_chats:
            if chat['id'] == self.current_assistant_chat_id:
                if 'messages' in chat and chat['messages']:
                    for msg in chat['messages']:
                        if msg['role'] == 'user':
                            self.assistant_chat_display.insert('end', f"Вы: ", 'user_header')
                            self.assistant_chat_display.insert('end', f"{msg['content']}\n", 'message')
                        elif msg['role'] == 'assistant':
                            self.assistant_chat_display.insert('end', f"Помощник: ", 'assistant_header')
                            self.assistant_chat_display.insert('end', f"{msg['content']}", 'message')
                            if msg.get('knowledge_info'):
                                self.assistant_chat_display.insert('end', f"  [{msg['knowledge_info']}]", 'knowledge_info')
                            self.assistant_chat_display.insert('end', " ⎘\n", 'copy_btn_assistant')
                        self.assistant_chat_display.insert('end', '\n')
                break
        
        self.assistant_chat_display.see('end')
        self.assistant_chat_display.config(state=tk.DISABLED)
    
    def setup_logging(self):
        log_dir = os.path.join(os.path.expanduser("~"), "Documents", "TrainsFormerAI", "logs")
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
        
        log_file = os.path.join(log_dir, f"log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt")
        
        class DualOutput:
            def __init__(self, terminal, file):
                self.terminal = terminal
                self.file = file
            
            def write(self, message):
                self.terminal.write(message)
                self.file.write(message)
            
            def flush(self):
                self.terminal.flush()
                self.file.flush()
        
        self.log_file = open(log_file, 'w', encoding='utf-8')
        sys.stdout = DualOutput(sys.stdout, self.log_file)
        sys.stderr = DualOutput(sys.stderr, self.log_file)
    
    def setup_rounded_styles(self):
        self.style.configure('Rounded.TButton', 
                           borderwidth=0,
                           relief='flat',
                           padding=10,
                           background=self.theme_colors['primary'] if hasattr(self, 'theme_colors') else '#3b82f6')
        
        self.style.configure('Rounded.TFrame', 
                           relief='flat',
                           borderwidth=2)
    
    def setup_colors(self):
        self.colors = {
            'dark': {
                'bg': '#0f172a',
                'sidebar': '#1e293b',
                'card': '#334155',
                'text': '#f1f5f9',
                'text_secondary': '#94a3b8',
                'primary': '#3b82f6',
                'success': '#10b981',
                'warning': '#f59e0b',
                'danger': '#ef4444',
                'border': '#475569',
                'hover': '#475569',
                'input_bg': '#1e293b',
                'scrollbar': '#475569'
            }
        }
        
        self.current_theme = 'dark'
        self.theme_colors = self.colors[self.current_theme]
    
    def setup_fonts(self):
        self.fonts = {
            'h1': ('Segoe UI', 24, 'bold'),
            'h2': ('Segoe UI', 18, 'bold'),
            'h3': ('Segoe UI', 16, 'bold'),
            'body': ('Segoe UI', 11),
            'small': ('Segoe UI', 10),
            'code': ('Cascadia Code', 10),
            'mono': ('Consolas', 10)
        }
    
    def load_config(self):
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    self.language = config.get('language', 'Русский')
                    self.model_type = config.get('model_type', 'GPT-1')
                    self.current_theme = config.get('theme', 'dark')
                    self.translate_enabled = config.get('translate_enabled', False)
                    self.auto_translate = config.get('auto_translate', False)
                    self.target_translate_lang = config.get('target_translate_lang', 'en')
                    self.theme_colors = self.colors[self.current_theme]
        except Exception as e:
            print(f"Ошибка загрузки конфига: {e}")
    
    def save_config(self):
        try:
            config = {
                'language': self.language,
                'model_type': self.model_type,
                'theme': self.current_theme,
                'translate_enabled': self.translate_enabled,
                'auto_translate': self.auto_translate,
                'target_translate_lang': self.target_translate_lang,
                'saved_at': datetime.now().isoformat()
            }
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Ошибка сохранения конфига: {e}")
    
    def load_chats_data(self):
        try:
            if os.path.exists(self.data_file):
                with open(self.data_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.chats = data.get('chats', [])
                    self.chat_data = data.get('chat_data', {})
        except Exception as e:
            print(f"Ошибка загрузки чатов: {e}")
            self.chats = []
            self.chat_data = {}
    
    def save_chats_data(self):
        try:
            data = {
                'chats': self.chats,
                'chat_data': self.chat_data,
                'saved_at': datetime.now().isoformat()
            }
            with open(self.data_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Ошибка сохранения чатов: {e}")
    
    def create_widgets(self):
        self.root.configure(bg=self.theme_colors['bg'])
        
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)
        
        self.chat_tab = tk.Frame(self.notebook, bg=self.theme_colors['bg'])
        self.notebook.add(self.chat_tab, text="💬 Чат")
        
        self.assistant_tab = tk.Frame(self.notebook, bg=self.theme_colors['bg'])
        self.notebook.add(self.assistant_tab, text="🤖 Умный помощник")
        
        self.create_chat_tab()
        self.create_assistant_tab()
        
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.update_ui_text()
        
        self.notebook.bind('<<NotebookTabChanged>>', self.on_tab_changed)
    
    def create_chat_tab(self):
        chat_container = tk.PanedWindow(self.chat_tab, orient=tk.HORIZONTAL, 
                                       bg=self.theme_colors['bg'], sashwidth=4)
        chat_container.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)
        
        self.create_sidebar(chat_container)
        self.create_main_content(chat_container)
        self.create_right_sidebar(chat_container)
    
    def create_assistant_tab(self):
        main_container = tk.PanedWindow(self.assistant_tab, orient=tk.HORIZONTAL,
                                       bg=self.theme_colors['bg'], sashwidth=4)
        main_container.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)
        
        self.create_assistant_sidebar(main_container)
        self.create_assistant_main_content(main_container)
        self.create_assistant_right_sidebar(main_container)
    
    def create_assistant_sidebar(self, parent):
        self.assistant_sidebar = tk.Frame(parent, bg=self.theme_colors['sidebar'], width=300)
        parent.add(self.assistant_sidebar)
        
        header_frame = tk.Frame(self.assistant_sidebar, bg=self.theme_colors['sidebar'])
        header_frame.pack(fill=tk.X, padx=20, pady=(25, 15))
        
        self.assistant_logo = tk.Label(header_frame, text="📚", font=('Segoe UI', 32),
                                      bg=self.theme_colors['sidebar'], fg=self.theme_colors['primary'])
        self.assistant_logo.pack(side=tk.LEFT)
        
        title_frame = tk.Frame(header_frame, bg=self.theme_colors['sidebar'])
        title_frame.pack(side=tk.LEFT, padx=(15, 0))
        
        self.assistant_title = tk.Label(title_frame, text="", font=self.fonts['h2'],
                                       bg=self.theme_colors['sidebar'], fg=self.theme_colors['text'])
        self.assistant_title.pack(anchor='w')
        
        self.assistant_subtitle = tk.Label(title_frame, text="База знаний", font=self.fonts['small'],
                                          bg=self.theme_colors['sidebar'], fg=self.theme_colors['text_secondary'])
        self.assistant_subtitle.pack(anchor='w')
        
        instructions_card = tk.Frame(self.assistant_sidebar, bg=self.theme_colors['card'])
        instructions_card.pack(fill=tk.X, padx=20, pady=(0, 20))
        
        self.instructions_label = tk.Label(instructions_card, text="",
                                         font=self.fonts['h3'],
                                         bg=self.theme_colors['card'], 
                                         fg=self.theme_colors['primary'])
        self.instructions_label.pack(anchor='w', padx=15, pady=(15, 10))
        
        self.instructions_frame = tk.Frame(instructions_card, bg=self.theme_colors['card'])
        self.instructions_frame.pack(fill=tk.X, padx=15, pady=(0, 15))
        
        control_card = tk.Frame(self.assistant_sidebar, bg=self.theme_colors['card'])
        control_card.pack(fill=tk.X, padx=20, pady=(0, 20))
        
        self.load_txt_btn = tk.Button(control_card, text="",
                                     font=self.fonts['body'],
                                     bg=self.theme_colors['primary'],
                                     fg='white',
                                     bd=0,
                                     padx=20,
                                     pady=12,
                                     cursor='hand2',
                                     command=self.import_knowledge_file)
        self.load_txt_btn.pack(fill=tk.X, padx=15, pady=15)
        
        refresh_btn = tk.Button(control_card, text="",
                               font=self.fonts['body'],
                               bg=self.theme_colors['card'],
                               fg=self.theme_colors['text'],
                               bd=0,
                               padx=20,
                               pady=10,
                               cursor='hand2',
                               command=self.refresh_knowledge_base)
        refresh_btn.pack(fill=tk.X, padx=15, pady=(0, 15))
        
        stats_card = tk.Frame(self.assistant_sidebar, bg=self.theme_colors['card'])
        stats_card.pack(fill=tk.X, padx=20, pady=(0, 20))
        
        stats_label = tk.Label(stats_card, text="",
                              font=self.fonts['h3'],
                              bg=self.theme_colors['card'], fg=self.theme_colors['text'])
        stats_label.pack(anchor='w', padx=15, pady=(15, 10))
        
        self.kb_stats_frame = tk.Frame(stats_card, bg=self.theme_colors['card'])
        self.kb_stats_frame.pack(fill=tk.X, padx=15, pady=(0, 15))
        
        files_card = tk.Frame(self.assistant_sidebar, bg=self.theme_colors['card'])
        files_card.pack(fill=tk.X, padx=20, pady=(0, 20))
        
        files_label = tk.Label(files_card, text="files in the knowledge base",
                             font=self.fonts['h3'],
                             bg=self.theme_colors['card'], fg=self.theme_colors['text'])
        files_label.pack(anchor='w', padx=15, pady=(15, 10))
        
        self.files_info = tk.Label(files_card, text="",
                                 font=self.fonts['small'],
                                 bg=self.theme_colors['card'], fg=self.theme_colors['text_secondary'],
                                 justify=tk.LEFT, wraplength=250)
        self.files_info.pack(anchor='w', padx=15, pady=(0, 15))
        
        format_card = tk.Frame(self.assistant_sidebar, bg=self.theme_colors['card'])
        format_card.pack(fill=tk.X, padx=20, pady=(0, 20))
        
        format_label = tk.Label(format_card, text="file format", font=self.fonts['h3'],
                               bg=self.theme_colors['card'], fg=self.theme_colors['text'])
        format_label.pack(anchor='w', padx=15, pady=(15, 10))
        
        format_text = tk.Text(format_card, height=8,
                             bg=self.theme_colors['input_bg'],
                             fg=self.theme_colors['text_secondary'],
                             font=self.fonts['code'],
                             wrap=tk.WORD,
                             relief=tk.FLAT,
                             borderwidth=5)
        format_text.pack(fill=tk.X, padx=15, pady=(0, 15))
        format_text.insert('1.0', 'All files related to .txt')
        format_text.config(state=tk.DISABLED)
    
    def create_assistant_main_content(self, parent):
        self.assistant_main = tk.Frame(parent, bg=self.theme_colors['bg'])
        parent.add(self.assistant_main)
        
        self.assistant_header = tk.Frame(self.assistant_main, bg=self.theme_colors['sidebar'], height=70)
        self.assistant_header.pack(fill=tk.X)
        self.assistant_header.pack_propagate(False)
        
        header_content = tk.Frame(self.assistant_header, bg=self.theme_colors['sidebar'])
        header_content.pack(fill=tk.BOTH, expand=True, padx=30)
        
        self.assistant_chat_title = tk.Label(header_content, text="", font=self.fonts['h2'],
                                            bg=self.theme_colors['sidebar'], fg=self.theme_colors['text'])
        self.assistant_chat_title.pack(side=tk.LEFT)
        
        header_buttons = tk.Frame(header_content, bg=self.theme_colors['sidebar'])
        header_buttons.pack(side=tk.RIGHT)
        
        self.copy_all_btn = tk.Button(header_buttons, text="",
                                     font=('Segoe UI', 14),
                                     bg=self.theme_colors['card'],
                                     fg=self.theme_colors['text_secondary'],
                                     bd=0,
                                     padx=8,
                                     pady=4,
                                     cursor='hand2',
                                     command=self.copy_entire_assistant_dialogue)
        self.copy_all_btn.pack(side=tk.LEFT, padx=(5, 0))
        
        self.settings_btn = tk.Button(header_buttons, text="",
                                     font=('Segoe UI', 14),
                                     bg=self.theme_colors['card'],
                                     fg=self.theme_colors['text_secondary'],
                                     bd=0,
                                     padx=8,
                                     pady=4,
                                     cursor='hand2',
                                     command=self.open_assistant_settings)
        self.settings_btn.pack(side=tk.LEFT, padx=(5, 0))
        
        self.assistant_chat_display = scrolledtext.ScrolledText(
            self.assistant_main,
            bg=self.theme_colors['bg'],
            fg=self.theme_colors['text'],
            font=self.fonts['body'],
            insertbackground=self.theme_colors['text'],
            wrap=tk.WORD,
            relief=tk.FLAT,
            borderwidth=0,
            padx=20,
            pady=15
        )
        self.assistant_chat_display.pack(fill=tk.BOTH, expand=True, padx=30, pady=(15, 0))
        
        self.assistant_chat_display.tag_configure('user_header', 
                                                 foreground=self.theme_colors['primary'],
                                                 font=('Segoe UI', 11, 'bold'))
        self.assistant_chat_display.tag_configure('assistant_header', 
                                                 foreground=self.theme_colors['success'],
                                                 font=('Segoe UI', 11, 'bold'))
        self.assistant_chat_display.tag_configure('system_header', 
                                                 foreground=self.theme_colors['warning'],
                                                 font=('Segoe UI', 11, 'bold'))
        self.assistant_chat_display.tag_configure('message', 
                                                 foreground=self.theme_colors['text'],
                                                 font=self.fonts['body'])
        self.assistant_chat_display.tag_configure('time', 
                                                 foreground=self.theme_colors['text_secondary'],
                                                 font=self.fonts['small'])
        self.assistant_chat_display.tag_configure('knowledge_info', 
                                                 foreground=self.theme_colors['warning'],
                                                 font=('Segoe UI', 10, 'italic'))
        self.assistant_chat_display.tag_configure('copy_btn_assistant', 
                                                 foreground=self.theme_colors['primary'],
                                                 font=('Segoe UI', 10, 'bold'))
        
        self.create_assistant_input_area()
        
        self.assistant_chat_display.bind('<Button-1>', self.on_assistant_click)
    
    def create_assistant_input_area(self):
        self.assistant_input_container = tk.Frame(self.assistant_main, bg=self.theme_colors['sidebar'])
        self.assistant_input_container.pack(fill=tk.X, padx=30, pady=(15, 30))
        
        search_frame = tk.Frame(self.assistant_input_container, bg=self.theme_colors['sidebar'])
        search_frame.pack(fill=tk.X, padx=15, pady=(15, 0))
        
        self.knowledge_search_var = tk.StringVar()
        self.knowledge_search_entry = tk.Entry(search_frame, textvariable=self.knowledge_search_var,
                                              font=self.fonts['body'], bg=self.theme_colors['input_bg'],
                                              fg=self.theme_colors['text'], insertbackground=self.theme_colors['text'],
                                              relief=tk.FLAT, bd=2)
        self.knowledge_search_entry.pack(fill=tk.X, ipady=8)
        self.knowledge_search_entry.bind('<Return>', self.search_in_knowledge_base)
        
        self.assistant_input_text = tk.Text(self.assistant_input_container,
                                           height=4,
                                           bg=self.theme_colors['input_bg'],
                                           fg=self.theme_colors['text'],
                                           font=self.fonts['body'],
                                           insertbackground=self.theme_colors['text'],
                                           wrap=tk.WORD,
                                           relief=tk.FLAT,
                                           borderwidth=8)
        self.assistant_input_text.pack(fill=tk.X, padx=15, pady=15)
        self.assistant_input_text.bind('<Return>', self.on_assistant_enter_pressed)
        
        self.set_assistant_placeholder()
        
        button_frame = tk.Frame(self.assistant_input_container, bg=self.theme_colors['sidebar'])
        button_frame.pack(fill=tk.X, padx=15, pady=(0, 15))
        
        self.assistant_send_btn = tk.Button(button_frame, text="",
                                           font=self.fonts['body'],
                                           bg=self.theme_colors['primary'],
                                           fg='white',
                                           bd=0,
                                           padx=20,
                                           pady=10,
                                           cursor='hand2',
                                           command=self.send_to_assistant)
        self.assistant_send_btn.pack(side=tk.RIGHT)
    
    def create_assistant_right_sidebar(self, parent):
        self.assistant_right_sidebar = tk.Frame(parent, bg=self.theme_colors['sidebar'], width=300)
        parent.add(self.assistant_right_sidebar)
        
        info_label = tk.Label(self.assistant_right_sidebar, text="Information", font=self.fonts['h3'],
                             bg=self.theme_colors['sidebar'], fg=self.theme_colors['text'])
        info_label.pack(anchor='w', padx=25, pady=(30, 15))
        
        info_card = tk.Frame(self.assistant_right_sidebar, bg=self.theme_colors['card'])
        info_card.pack(fill=tk.X, padx=20, pady=(0, 20))
        
        work_label = tk.Label(info_card, text="how does the assistant work", font=self.fonts['h3'],
                             bg=self.theme_colors['card'], fg=self.theme_colors['text'])
        work_label.pack(anchor='w', padx=15, pady=(15, 10))
        
        work_text = tk.Text(info_card, height=10,
                           bg=self.theme_colors['input_bg'],
                           fg=self.theme_colors['text_secondary'],
                           font=self.fonts['small'],
                           wrap=tk.WORD,
                           relief=tk.FLAT,
                           borderwidth=5)
        work_text.pack(fill=tk.X, padx=15, pady=(0, 15))
        work_text.insert('1.0', '1. You ask the question in any language (the one you train the model in, haha)\n2. The assistant searches for similar phrases in ALL TXT files. 3. Can work with ANY TXT format. 4. AI processes text. 5. The answer is saved in the history. 💡 SupportedSubject Plain text Dictionaries Any other formats')
        work_text.config(state=tk.DISABLED)
        
        search_card = tk.Frame(self.assistant_right_sidebar, bg=self.theme_colors['card'])
        search_card.pack(fill=tk.X, padx=20, pady=(0, 20))
        
        current_search_label = tk.Label(search_card, text="last search", font=self.fonts['h3'],
                                       bg=self.theme_colors['card'], fg=self.theme_colors['text'])
        current_search_label.pack(anchor='w', padx=15, pady=(15, 10))
        
        self.last_search_info = tk.Label(search_card, text="No search",
                                        font=self.fonts['small'],
                                        bg=self.theme_colors['card'], fg=self.theme_colors['text_secondary'],
                                        justify=tk.LEFT, wraplength=250)
        self.last_search_info.pack(anchor='w', padx=15, pady=(0, 15))
    
    def create_sidebar(self, parent):
        self.sidebar = tk.Frame(parent, bg=self.theme_colors['sidebar'], width=280)
        parent.add(self.sidebar)
        
        header_frame = tk.Frame(self.sidebar, bg=self.theme_colors['sidebar'])
        header_frame.pack(fill=tk.X, padx=20, pady=(25, 15))
        
        self.logo_label = tk.Label(header_frame, text="🤖", font=('Segoe UI', 32),
                                  bg=self.theme_colors['sidebar'], fg=self.theme_colors['primary'])
        self.logo_label.pack(side=tk.LEFT)
        
        title_frame = tk.Frame(header_frame, bg=self.theme_colors['sidebar'])
        title_frame.pack(side=tk.LEFT, padx=(15, 0))
        
        self.title_label = tk.Label(title_frame, text="", font=self.fonts['h2'],
                                   bg=self.theme_colors['sidebar'], fg=self.theme_colors['text'])
        self.title_label.pack(anchor='w')
        
        self.subtitle_label = tk.Label(title_frame, text="", font=self.fonts['small'],
                                      bg=self.theme_colors['sidebar'], fg=self.theme_colors['text_secondary'])
        self.subtitle_label.pack(anchor='w')
        
        self.search_frame = tk.Frame(self.sidebar, bg=self.theme_colors['sidebar'])
        self.search_frame.pack(fill=tk.X, padx=20, pady=(0, 20))
        
        self.search_var = tk.StringVar()
        self.search_entry = tk.Entry(self.search_frame, textvariable=self.search_var,
                                    font=self.fonts['body'], bg=self.theme_colors['input_bg'],
                                    fg=self.theme_colors['text'], insertbackground=self.theme_colors['text'],
                                    relief=tk.FLAT, bd=2)
        self.search_entry.pack(fill=tk.X, ipady=8)
        self.search_entry.bind('<KeyRelease>', self.search_chats)
        
        lang = self.language_dict[self.language]
        self.search_entry.insert(0, lang["search"])
        self.search_entry.configure(fg=self.theme_colors['text_secondary'])
        self.search_entry.bind('<FocusIn>', lambda e: self.clear_search_placeholder())
        self.search_entry.bind('<FocusOut>', lambda e: self.restore_search_placeholder())
        
        self.new_chat_btn = tk.Button(self.sidebar, text="", 
                                     font=self.fonts['body'],
                                     bg=self.theme_colors['primary'],
                                     fg='white',
                                     bd=0,
                                     padx=20,
                                     pady=10,
                                     cursor='hand2',
                                     command=self.create_new_chat)
        self.new_chat_btn.pack(fill=tk.X, padx=20, pady=(0, 25))
        
        self.chats_label = tk.Label(self.sidebar, text="", font=self.fonts['h3'],
                                   bg=self.theme_colors['sidebar'], fg=self.theme_colors['text'])
        self.chats_label.pack(anchor='w', padx=20, pady=(0, 10))
        
        self.create_chats_scrollable_area()
        
        bottom_frame = tk.Frame(self.sidebar, bg=self.theme_colors['sidebar'])
        bottom_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=20, pady=20)
        
        stats_btn = tk.Button(bottom_frame, text="Статистика", 
                             font=self.fonts['body'],
                             bg=self.theme_colors['card'],
                             fg=self.theme_colors['text'],
                             bd=0,
                             padx=20,
                             pady=10,
                             cursor='hand2',
                             command=self.show_statistics)
        stats_btn.pack(fill=tk.X, pady=(0, 10))
        
        settings_btn = tk.Button(bottom_frame, text="Настройки API", 
                                font=self.fonts['body'],
                                bg=self.theme_colors['card'],
                                fg=self.theme_colors['text'],
                                bd=0,
                                padx=20,
                                pady=10,
                                cursor='hand2',
                                command=self.open_settings)
        settings_btn.pack(fill=tk.X)

        
        lang = self.language_dict[self.language]

        boosty_btn = tk.Button(bottom_frame, text=lang["support_boosty"],
                              font=self.fonts['body'],
                              bg=self.theme_colors['primary'],
                              fg='white',
                              bd=0,
                              padx=20,
                              pady=10,
                              cursor='hand2',
                              command=lambda: webbrowser.open("https://boosty.to/trainsformerai"))
        boosty_btn.pack(fill=tk.X, pady=(10, 2))

        boosty_sub = tk.Label(bottom_frame,
                              text=lang["boosty_subtext"],
                              font=self.fonts['small'],
                              bg=self.theme_colors['sidebar'],
                              fg=self.theme_colors['text_secondary'])
        boosty_sub.pack(fill=tk.X)
    
    def create_chats_scrollable_area(self):
        self.chats_container = tk.Frame(self.sidebar, bg=self.theme_colors['sidebar'])
        self.chats_container.pack(fill=tk.BOTH, expand=True, padx=15)
        
        self.chats_canvas = tk.Canvas(self.chats_container, bg=self.theme_colors['sidebar'], 
                                     highlightthickness=0)
        self.chats_scrollbar = ttk.Scrollbar(self.chats_container, orient=tk.VERTICAL, 
                                           command=self.chats_canvas.yview)
        self.chats_scrollable_frame = tk.Frame(self.chats_canvas, bg=self.theme_colors['sidebar'])
        
        self.chats_scrollable_frame.bind(
            "<Configure>",
            lambda e: self.chats_canvas.configure(scrollregion=self.chats_canvas.bbox("all"))
        )
        
        self.chats_canvas.create_window((0, 0), window=self.chats_scrollable_frame, anchor="nw")
        self.chats_canvas.configure(yscrollcommand=self.chats_scrollbar.set)
        
        self.chats_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.chats_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
    
    def create_main_content(self, parent):
        self.main_content = tk.Frame(parent, bg=self.theme_colors['bg'])
        parent.add(self.main_content)
        
        self.create_chat_header()
        self.create_chat_display()
        self.create_input_area()
    
    def create_chat_header(self):
        self.chat_header = tk.Frame(self.main_content, bg=self.theme_colors['sidebar'], height=70)
        self.chat_header.pack(fill=tk.X)
        self.chat_header.pack_propagate(False)
        
        header_content = tk.Frame(self.chat_header, bg=self.theme_colors['sidebar'])
        header_content.pack(fill=tk.BOTH, expand=True, padx=30)
        
        self.chat_title = tk.Label(header_content, text="", font=self.fonts['h2'],
                                  bg=self.theme_colors['sidebar'], fg=self.theme_colors['text'])
        self.chat_title.pack(side=tk.LEFT)
        
        header_buttons = tk.Frame(header_content, bg=self.theme_colors['sidebar'])
        header_buttons.pack(side=tk.RIGHT)
        
        self.export_btn = tk.Button(header_buttons, text="📤", 
                                   font=('Segoe UI', 14),
                                   bg=self.theme_colors['card'],
                                   fg=self.theme_colors['text_secondary'],
                                   bd=0,
                                   padx=8,
                                   pady=4,
                                   cursor='hand2',
                                   command=self.export_chat)
        self.export_btn.pack(side=tk.LEFT, padx=(5, 0))
        
        self.import_btn = tk.Button(header_buttons, text="📥", 
                                   font=('Segoe UI', 14),
                                   bg=self.theme_colors['card'],
                                   fg=self.theme_colors['text_secondary'],
                                   bd=0,
                                   padx=8,
                                   pady=4,
                                   cursor='hand2',
                                   command=self.import_chat)
        self.import_btn.pack(side=tk.LEFT, padx=(5, 0))
        
        self.clear_btn = tk.Button(header_buttons, text="🗑️", 
                                  font=('Segoe UI', 14),
                                  bg=self.theme_colors['card'],
                                  fg=self.theme_colors['text_secondary'],
                                  bd=0,
                                  padx=8,
                                  pady=4,
                                  cursor='hand2',
                                  command=self.clear_current_chat)
        self.clear_btn.pack(side=tk.LEFT, padx=(5, 0))
        
        self.translate_btn = tk.Button(header_buttons, text="🌐", 
                                      font=('Segoe UI', 14),
                                      bg=self.theme_colors['card'],
                                      fg=self.theme_colors['text_secondary'],
                                      bd=0,
                                      padx=8,
                                      pady=4,
                                      cursor='hand2',
                                      command=self.translate_current_message)
        self.translate_btn.pack(side=tk.LEFT, padx=(5, 0))
        
        self.model_status = tk.Label(header_content, text="", font=self.fonts['small'],
                                    bg=self.theme_colors['sidebar'], fg=self.theme_colors['success'])
        self.model_status.pack(side=tk.RIGHT, padx=(0, 20))
    
    def create_chat_display(self):
        self.chat_display = scrolledtext.ScrolledText(
            self.main_content,
            bg=self.theme_colors['bg'],
            fg=self.theme_colors['text'],
            font=self.fonts['body'],
            insertbackground=self.theme_colors['text'],
            wrap=tk.WORD,
            relief=tk.FLAT,
            borderwidth=0,
            padx=20,
            pady=15
        )
        self.chat_display.pack(fill=tk.BOTH, expand=True, padx=30, pady=(15, 0))
        
        self.setup_text_tags()
        self.chat_display.bind('<Button-1>', self.on_chat_click)
    
    def setup_text_tags(self):
        self.chat_display.tag_configure('user_header', 
                                       foreground=self.theme_colors['primary'],
                                       font=('Segoe UI', 11, 'bold'))
        self.chat_display.tag_configure('gpt_header', 
                                       foreground=self.theme_colors['success'],
                                       font=('Segoe UI', 11, 'bold'))
        self.chat_display.tag_configure('system_header', 
                                       foreground=self.theme_colors['warning'],
                                       font=('Segoe UI', 11, 'bold'))
        self.chat_display.tag_configure('message', 
                                       foreground=self.theme_colors['text'],
                                       font=self.fonts['body'])
        self.chat_display.tag_configure('time', 
                                       foreground=self.theme_colors['text_secondary'],
                                       font=self.fonts['small'])
        self.chat_display.tag_configure('copy_btn', 
                                       foreground=self.theme_colors['primary'],
                                       font=('Segoe UI', 10, 'bold'))
        self.chat_display.tag_configure('translate_btn', 
                                       foreground=self.theme_colors['warning'],
                                       font=('Segoe UI', 10, 'bold'))
    
    def create_input_area(self):
        self.input_container = tk.Frame(self.main_content, bg=self.theme_colors['sidebar'])
        self.input_container.pack(fill=tk.X, padx=30, pady=(15, 30))
        
        controls_frame = tk.Frame(self.input_container, bg=self.theme_colors['sidebar'])
        controls_frame.pack(fill=tk.X, padx=15, pady=(15, 0))
        
        self.params_frame = tk.Frame(controls_frame, bg=self.theme_colors['sidebar'])
        self.params_frame.pack(side=tk.LEFT)
        
        self.length_label = tk.Label(self.params_frame, text="",
                                    bg=self.theme_colors['sidebar'], fg=self.theme_colors['text_secondary'],
                                    font=self.fonts['small'])
        self.length_label.pack(side=tk.LEFT, padx=(0, 5))
        
        self.length_var = tk.IntVar(value=100)
        self.length_scale = tk.Scale(self.params_frame, from_=20, to=500,
                                    variable=self.length_var,
                                    orient=tk.HORIZONTAL,
                                    length=120,
                                    bg=self.theme_colors['sidebar'],
                                    fg=self.theme_colors['text'],
                                    highlightthickness=0,
                                    sliderrelief='flat')
        self.length_scale.pack(side=tk.LEFT, padx=(0, 20))
        
        self.temp_label = tk.Label(self.params_frame, text="",
                                  bg=self.theme_colors['sidebar'], fg=self.theme_colors['text_secondary'],
                                  font=self.fonts['small'])
        self.temp_label.pack(side=tk.LEFT, padx=(0, 5))
        
        self.temp_var = tk.DoubleVar(value=0.7)
        self.temp_scale = tk.Scale(self.params_frame, from_=0.1, to=1.5,
                                  variable=self.temp_var,
                                  orient=tk.HORIZONTAL,
                                  length=120,
                                  bg=self.theme_colors['sidebar'],
                                  fg=self.theme_colors['text'],
                                  highlightthickness=0,
                                  sliderrelief='flat')
        self.temp_scale.pack(side=tk.LEFT)
        
        self.input_text = tk.Text(self.input_container,
                                 height=4,
                                 bg=self.theme_colors['input_bg'],
                                 fg=self.theme_colors['text'],
                                 font=self.fonts['body'],
                                 insertbackground=self.theme_colors['text'],
                                 wrap=tk.WORD,
                                 relief=tk.FLAT,
                                 borderwidth=8)
        self.input_text.pack(fill=tk.X, padx=15, pady=15)
        self.input_text.bind('<FocusIn>', self.clear_placeholder)
        self.input_text.bind('<FocusOut>', self.restore_placeholder)
        self.input_text.bind('<Return>', self.on_enter_pressed)
        
        self.restore_placeholder(None)
        
        button_frame = tk.Frame(self.input_container, bg=self.theme_colors['sidebar'])
        button_frame.pack(fill=tk.X, padx=15, pady=(0, 15))
        
        self.send_btn = tk.Button(button_frame, text="", 
                                 font=self.fonts['body'],
                                 bg=self.theme_colors['primary'],
                                 fg='white',
                                 bd=0,
                                 padx=20,
                                 pady=10,
                                 cursor='hand2',
                                 command=self.send_message)
        self.send_btn.pack(side=tk.RIGHT)
    
    def create_right_sidebar(self, parent):
        self.right_sidebar = tk.Frame(parent, bg=self.theme_colors['sidebar'], width=300)
        parent.add(self.right_sidebar)
        
        settings_label = tk.Label(self.right_sidebar, text="Настройки", font=self.fonts['h3'],
                                 bg=self.theme_colors['sidebar'], fg=self.theme_colors['text'])
        settings_label.pack(anchor='w', padx=25, pady=(30, 15))
        
        card = tk.Frame(self.right_sidebar, bg=self.theme_colors['card'])
        card.pack(fill=tk.X, padx=20, pady=(0, 20))
        
        model_label = tk.Label(card, text="Модель", font=self.fonts['h3'],
                              bg=self.theme_colors['card'], fg=self.theme_colors['text'])
        model_label.pack(anchor='w', padx=15, pady=(15, 10))
        
        self.model_var = tk.StringVar(value=self.model_type)
        
        self.gpt1_radio = tk.Radiobutton(card, text="",
                                        variable=self.model_var, value="GPT-1",
                                        font=self.fonts['body'],
                                        bg=self.theme_colors['card'],
                                        fg=self.theme_colors['text'],
                                        selectcolor=self.theme_colors['primary'],
                                        command=lambda: self.load_model("GPT-1"))
        self.gpt1_radio.pack(anchor='w', padx=15, pady=5)
        
        self.gpt2_radio = tk.Radiobutton(card, text="",
                                        variable=self.model_var, value="GPT-2",
                                        font=self.fonts['body'],
                                        bg=self.theme_colors['card'],
                                        fg=self.theme_colors['text'],
                                        selectcolor=self.theme_colors['primary'],
                                        command=lambda: self.load_model("GPT-2"))
        self.gpt2_radio.pack(anchor='w', padx=15, pady=5)
        
        lang_card = tk.Frame(self.right_sidebar, bg=self.theme_colors['card'])
        lang_card.pack(fill=tk.X, padx=20, pady=(0, 20))
        
        lang_label = tk.Label(lang_card, text="Язык интерфейса",
                             font=self.fonts['h3'],
                             bg=self.theme_colors['card'], fg=self.theme_colors['text'])
        lang_label.pack(anchor='w', padx=15, pady=(15, 10))
        
        self.lang_var = tk.StringVar(value=self.language)
        self.lang_combo = ttk.Combobox(lang_card, textvariable=self.lang_var,
                                      values=["Русский", "English"], state="readonly",
                                      font=self.fonts['body'])
        self.lang_combo.pack(fill=tk.X, padx=15, pady=(0, 15))
        self.lang_combo.bind('<<ComboboxSelected>>', self.change_language)
        
        translate_card = tk.Frame(self.right_sidebar, bg=self.theme_colors['card'])
        translate_card.pack(fill=tk.X, padx=20, pady=(0, 20))
        
        translate_label = tk.Label(translate_card, text="Перевод",
                                  font=self.fonts['h3'],
                                  bg=self.theme_colors['card'], fg=self.theme_colors['text'])
        translate_label.pack(anchor='w', padx=15, pady=(15, 10))
        
        self.translate_enable_var = tk.BooleanVar(value=self.translate_enabled)
        self.translate_check = tk.Checkbutton(translate_card, text="",
                                             variable=self.translate_enable_var,
                                             command=self.toggle_translate,
                                             font=self.fonts['body'],
                                             bg=self.theme_colors['card'],
                                             fg=self.theme_colors['text'],
                                             selectcolor=self.theme_colors['primary'])
        self.translate_check.pack(anchor='w', padx=15, pady=5)
        
        self.auto_translate_var = tk.BooleanVar(value=self.auto_translate)
        self.auto_translate_check = tk.Checkbutton(translate_card, text="",
                                                  variable=self.auto_translate_var,
                                                  command=self.toggle_auto_translate,
                                                  font=self.fonts['body'],
                                             bg=self.theme_colors['card'],
                                             fg=self.theme_colors['text'],
                                             selectcolor=self.theme_colors['primary'])
        self.auto_translate_check.pack(anchor='w', padx=15, pady=5)
        
        lang_frame = tk.Frame(translate_card, bg=self.theme_colors['card'])
        lang_frame.pack(fill=tk.X, padx=15, pady=(10, 15))
        
        lang_select_label = tk.Label(lang_frame, text="Язык перевода:",
                                    font=self.fonts['body'],
                                    bg=self.theme_colors['card'], fg=self.theme_colors['text'])
        lang_select_label.pack(side=tk.LEFT)
        
        self.translate_lang_var = tk.StringVar(value=self.target_translate_lang)
        self.translate_lang_combo = ttk.Combobox(lang_frame, 
                                                textvariable=self.translate_lang_var,
                                                values=list(self.translate_languages.keys()),
                                                state="readonly",
                                                font=self.fonts['body'],
                                                width=10)
        self.translate_lang_combo.pack(side=tk.RIGHT)
    
    def process_queue(self):
        try:
            while True:
                func, args = self.message_queue.get_nowait()
                func(*args)
        except queue.Empty:
            pass
        finally:
            self.root.after(100, self.process_queue)
    
    def update_ui_text(self):
        """Обновляет текст интерфейса на выбранном языке"""
        lang = self.language_dict[self.language]
        
        self.root.title(lang["title"])
        
        self.notebook.tab(0, text=f"💬 {lang['chats']}")
        self.notebook.tab(1, text=f"🤖 {lang['smart_assistant']}")
        
        self.title_label.config(text=lang["title"])
        self.subtitle_label.config(text=lang["classic_models"])
        self.new_chat_btn.config(text=f"+ {lang['new_chat']}")
        self.chats_label.config(text=lang["chats"])
        
        self.search_entry.delete(0, tk.END)
        self.search_entry.insert(0, lang["search"])
        self.search_entry.configure(fg=self.theme_colors['text_secondary'])
        
        self.gpt1_radio.config(text=lang["model_label_gpt1"])
        self.gpt2_radio.config(text=lang["model_label_gpt2"])
        
        self.length_label.config(text=f"{lang['length']}:")
        self.temp_label.config(text=f"{lang['creativity']}:")
        
        self.translate_check.config(text=lang["enable_translate"])
        self.auto_translate_check.config(text=lang["auto_translate"])
        
        self.send_btn.config(text=f"↗️ {lang['send']}")
        
        self.assistant_title.config(text=lang["smart_assistant"])
        self.assistant_chat_title.config(text=lang["smart_assistant"])
        
        self.load_txt_btn.config(text=f"📁 {lang['load_txt']}")
        
        self.assistant_send_btn.config(text=f"↗️ {lang['send']}")
        
        if hasattr(self, 'copy_all_btn'):
            self.copy_all_btn.config(text=lang["copy_all_dialogue"])
        if hasattr(self, 'settings_btn'):
            self.settings_btn.config(text=lang["advanced_settings"])
        
        self.knowledge_search_entry.delete(0, tk.END)
        self.knowledge_search_entry.insert(0, lang["search_knowledge"])
        self.knowledge_search_entry.configure(fg=self.theme_colors['text_secondary'])
        
        self.instructions_label.config(text=lang["instructions_title"])
        
        for widget in self.instructions_frame.winfo_children():
            widget.destroy()
        
        instructions = [
            lang["instructions_1"],
            lang["instructions_2"], 
            lang["instructions_3"],
            lang["instructions_4"]
        ]
        
        for i, instruction in enumerate(instructions):
            label = tk.Label(self.instructions_frame, 
                           text=instruction,
                           font=self.fonts['small'],
                           bg=self.theme_colors['card'],
                           fg=self.theme_colors['text_secondary'],
                           justify=tk.LEFT,
                           anchor='w')
            label.pack(anchor='w', pady=2)
        
        self.update_knowledge_stats()
        self.update_chat_list()
        
        if self.current_chat_id is not None:
            for chat in self.chats:
                if chat['id'] == self.current_chat_id:
                    self.update_chat_title(chat['name'])
                    break
        
        if self.current_chat_id is not None:
            self.load_chat(self.current_chat_id)
        
        self.set_assistant_placeholder()
    
    def update_knowledge_stats(self):
        """Обновляет статистику базы знаний"""
        stats = self.knowledge_base.get_stats()
        lang = self.language_dict[self.language]
        
        for widget in self.kb_stats_frame.winfo_children():
            widget.destroy()
        
        if stats['exists']:
            stats_label = tk.Label(self.kb_stats_frame, 
                                 text=f"{lang['total_phrases']}: {stats['total_entries']}",
                                 font=self.fonts['body'],
                                 bg=self.theme_colors['card'], 
                                 fg=self.theme_colors['success'])
            stats_label.pack(anchor='w', pady=2)
            
            files_label = tk.Label(self.kb_stats_frame,
                                text=f"Файлов: {stats['total_files']}",
                                font=self.fonts['small'],
                                bg=self.theme_colors['card'],
                                fg=self.theme_colors['text_secondary'])
            files_label.pack(anchor='w', pady=2)
        else:
            no_data_label = tk.Label(self.kb_stats_frame,
                                   text=f"{lang['no_entries_found']}",
                                   font=self.fonts['body'],
                                   bg=self.theme_colors['card'],
                                   fg=self.theme_colors['warning'])
            no_data_label.pack(anchor='w', pady=2)
        
        files_text = ""
        if stats['files']:
            files_text = "📁 Загружены файлы:\n"
            for file in stats['files'][:5]:
                entries = stats['files_data'].get(file, 0)
                files_text += f"• {file} ({entries} зап.)\n"
            if len(stats['files']) > 5:
                files_text += f"• ... и еще {len(stats['files']) - 5} файлов"
        else:
            files_text = "📁 No files"
        
        self.files_info.config(text=files_text)
    
    def set_assistant_placeholder(self):
        """Устанавливает плейсхолдер для поля ввода помощника"""
        lang = self.language_dict[self.language]
        current_text = self.assistant_input_text.get('1.0', 'end-1c')
        
        if not current_text.strip():
            self.assistant_input_text.delete('1.0', 'end')
            self.assistant_input_text.insert('1.0', lang["input_placeholder"])
            self.assistant_input_text.configure(fg=self.theme_colors['text_secondary'])
    
    def clear_assistant_placeholder(self):
        """Очищает плейсхолдер при фокусе"""
        lang = self.language_dict[self.language]
        current_text = self.assistant_input_text.get('1.0', 'end-1c')
        if current_text.strip() == lang["input_placeholder"]:
            self.assistant_input_text.delete('1.0', 'end')
            self.assistant_input_text.configure(fg=self.theme_colors['text'])
    
    def send_to_assistant(self):
        if not TRANSFORMERS_AVAILABLE:
            messagebox.showwarning("Ошибка", "Установите библиотеки transformers и torch")
            return
            
        if not self.current_model:
            messagebox.showwarning("Ошибка", "Модель не загружена")
            return
        
        lang = self.language_dict[self.language]
        user_message = self.assistant_input_text.get('1.0', 'end-1c').strip()
        
        if not user_message or user_message == lang["input_placeholder"]:
            messagebox.showwarning(lang["enter_text"], lang["enter_text"])
            return
        
        timestamp = datetime.now().strftime("%H:%M")
        
        self.add_to_assistant_history('user', user_message)
        
        self.assistant_chat_display.config(state=tk.NORMAL)
        self.assistant_chat_display.insert('end', f"Вы: ", 'user_header')
        self.assistant_chat_display.insert('end', f"{user_message}\n", 'message')
        self.assistant_chat_display.see('end')
        self.assistant_chat_display.config(state=tk.DISABLED)
        
        self.assistant_input_text.delete('1.0', 'end')
        self.set_assistant_placeholder()
        
        self.assistant_chat_display.config(state=tk.NORMAL)
        self.assistant_chat_display.insert('end', f"{lang['assistant_thinking']}\n", 'knowledge_info')
        self.assistant_chat_display.see('end')
        self.assistant_chat_display.config(state=tk.DISABLED)
        
        self.assistant_send_btn.config(text=f" {lang['generating']}", state=tk.DISABLED)
        
        def process_with_knowledge():
            try:
                similar_results = self.knowledge_base.find_similar(user_message, threshold=0.3)
                
                context_parts = []
                if similar_results:
                    for result in similar_results[:3]:
                        item = result['item']
                        if item.get('english'):
                            context_parts.append(f"Russian: {item['russian']}")
                            context_parts.append(f"English: {item['english']}")
                        else:
                            context_parts.append(f"Text: {item['russian']}")
                        if item.get('context'):
                            context_parts.append(f"Context: {item['context']}")
                
                if context_parts:
                    context_text = "\n".join(context_parts)
                    prompt = f"Based on this knowledge:\n{context_text}\n\nQuestion: {user_message}\nAnswer in English:"
                else:
                    prompt = f"Question: {user_message}\nAnswer in English:"
                
                if TRANSLATOR_AVAILABLE:
                    try:
                        translation = translator.translate(prompt, dest='en')
                        english_prompt = translation.text
                    except:
                        english_prompt = prompt
                else:
                    english_prompt = prompt
                
                input_ids = self.current_tokenizer.encode(english_prompt, return_tensors="pt").to(self.current_device)
                
                with torch.no_grad():
                    output = self.current_model.generate(
                        input_ids,
                        max_new_tokens=self.assistant_settings['response_length'],  # Используем настройку длины
                        temperature=self.assistant_settings['temperature'],  # Используем настройку креативности
                        do_sample=True,
                        top_p=0.9,
                        repetition_penalty=1.1,
                        pad_token_id=self.current_tokenizer.pad_token_id if hasattr(self.current_tokenizer, 'pad_token_id') else None,
                        eos_token_id=self.current_tokenizer.eos_token_id if hasattr(self.current_tokenizer, 'eos_token_id') else None
                    )
                
                english_response = self.current_tokenizer.decode(output[0], skip_special_tokens=True)
                
                if english_response.startswith(english_prompt):
                    english_response = english_response[len(english_prompt):].strip()
                
                if TRANSLATOR_AVAILABLE:
                    try:
                        translation_back = translator.translate(english_response, dest='ru')
                        russian_response = translation_back.text
                    except:
                        russian_response = english_response
                else:
                    russian_response = english_response
                
                knowledge_info = ""
                if similar_results:
                    knowledge_info = f"📚 {lang['using_knowledge']}: {len(similar_results)} {lang['found_similar'].lower()}"
                
                self.message_queue.put((self._finish_assistant_response, 
                                      (russian_response, knowledge_info, timestamp)))
                
            except Exception as e:
                error_msg = f"Ошибка: {str(e)}" if self.language == "Русский" else f"Error: {str(e)}"
                self.message_queue.put((self._show_assistant_error, (error_msg, timestamp)))
        
        thread = threading.Thread(target=process_with_knowledge, daemon=True)
        thread.start()
    
    def _finish_assistant_response(self, russian_response, knowledge_info, timestamp):
        """Завершает обработку ответа помощника"""
        self.add_to_assistant_history('assistant', russian_response, knowledge_info)
        
        self.assistant_chat_display.config(state=tk.NORMAL)
        
        self.assistant_chat_display.delete('end-1l linestart', 'end')
        
        self.assistant_chat_display.insert('end', f"Помощник: ", 'assistant_header')
        self.assistant_chat_display.insert('end', f"{russian_response}", 'message')
        
        if knowledge_info:
            self.assistant_chat_display.insert('end', f"  [{knowledge_info}]", 'knowledge_info')
        
        self.assistant_chat_display.insert('end', f" ⎘", 'copy_btn_assistant')
        
        self.assistant_chat_display.insert('end', f"\n\n")
        self.assistant_chat_display.see('end')
        self.assistant_chat_display.config(state=tk.DISABLED)
        
        lang = self.language_dict[self.language]
        self.assistant_send_btn.config(text=f" {lang['send']}", state=tk.NORMAL)
    
    def on_assistant_click(self, event):
        """Обрабатывает клик в чате помощника для копирования"""
        index = self.assistant_chat_display.index(f"@{event.x},{event.y}")
        tags = self.assistant_chat_display.tag_names(index)
        
        if "copy_btn_assistant" in tags:
            line_start = index.split('.')[0] + '.0'
            
            line_text = self.assistant_chat_display.get(line_start, index)
            
            if "Помощник: " in line_text:
                message = line_text.split("Помощник: ")[1]
                message = message.split(" ⎘")[0].strip()
            else:
                message = line_text.split(" ⎘")[0].strip()
            
            self.root.clipboard_clear()
            self.root.clipboard_append(message)
            
            lang = self.language_dict[self.language]
            messagebox.showinfo(lang["copied"], lang["copied"])
    
    def _show_assistant_error(self, error_msg, timestamp):
        """Показывает ошибку помощника"""
        self.add_to_assistant_history('system', error_msg)
        
        self.assistant_chat_display.config(state=tk.NORMAL)
        
        self.assistant_chat_display.delete('end-1l linestart', 'end')
        
        self.assistant_chat_display.insert('end', f"Система: {error_msg}\n\n", 'system_header')
        
        self.assistant_chat_display.see('end')
        self.assistant_chat_display.config(state=tk.DISABLED)
        
        lang = self.language_dict[self.language]
        self.assistant_send_btn.config(text=f" {lang['send']}", state=tk.NORMAL)
    
    def on_assistant_enter_pressed(self, event):
        """Обрабатывает нажатие Enter в поле ввода помощника"""
        if event.state & 0x4:
            return
        self.send_to_assistant()
        return 'break'
    
    def on_tab_changed(self, event):
        """Обрабатывает переключение вкладок"""
        current_tab = self.notebook.index(self.notebook.select())
        
        if current_tab == 1:
            self.update_knowledge_stats()
            self.load_assistant_chat_history()
    
    def clear_search_placeholder(self):
        lang = self.language_dict[self.language]
        if self.search_entry.get() == lang["search"]:
            self.search_entry.delete(0, tk.END)
            self.search_entry.configure(fg=self.theme_colors['text'])
    
    def restore_search_placeholder(self):
        if not self.search_entry.get().strip():
            lang = self.language_dict[self.language]
            self.search_entry.delete(0, tk.END)
            self.search_entry.insert(0, lang["search"])
            self.search_entry.configure(fg=self.theme_colors['text_secondary'])
    
    def search_chats(self, event=None):
        search_term = self.search_var.get().lower()
        lang = self.language_dict[self.language]
        
        if search_term == lang["search"].lower() or not search_term.strip():
            self.update_chat_list()
            return
        
        for widget in self.chats_scrollable_frame.winfo_children():
            widget.destroy()
        
        for chat in self.chats:
            if search_term in chat['name'].lower():
                self.create_chat_widget(chat)
    
    def create_chat_widget(self, chat):
        chat_frame = tk.Frame(self.chats_scrollable_frame, bg=self.theme_colors['sidebar'])
        chat_frame.pack(fill=tk.X, pady=2)
        
        btn_bg = self.theme_colors['primary'] if chat['id'] == self.current_chat_id else self.theme_colors['card']
        btn_fg = 'white' if chat['id'] == self.current_chat_id else self.theme_colors['text']
        
        chat_btn = tk.Button(chat_frame,
                            text=chat['name'],
                            font=self.fonts['body'],
                            bg=btn_bg,
                            fg=btn_fg,
                            bd=0,
                            padx=15,
                            pady=12,
                            anchor='w',
                            cursor='hand2',
                            command=lambda cid=chat['id']: self.load_chat(cid))
        chat_btn.pack(fill=tk.X)
    
    def update_chat_list(self):
        for widget in self.chats_scrollable_frame.winfo_children():
            widget.destroy()
        
        for chat in self.chats:
            self.create_chat_widget(chat)
    
    def update_chat_title(self, title):
        self.chat_title.config(text=title)
    
    def on_closing(self):
        print("Закрытие приложения...")
        self.save_chats_data()
        self.save_config()  # Сохраняем только конфиг, историю помощника не сохраняем
        if hasattr(self, 'log_file'):
            self.log_file.close()
        self.root.destroy()
    
    def clear_placeholder(self, event):
        lang = self.language_dict[self.language]
        current_text = self.input_text.get('1.0', 'end-1c')
        if current_text.strip() == lang["input_placeholder"]:
            self.input_text.delete('1.0', 'end')
            self.input_text.configure(fg=self.theme_colors['text'])
    
    def restore_placeholder(self, event):
        if not self.input_text.get('1.0', 'end-1c').strip():
            lang = self.language_dict[self.language]
            self.input_text.delete('1.0', 'end')
            self.input_text.insert('1.0', lang["input_placeholder"])
            self.input_text.configure(fg=self.theme_colors['text_secondary'])
    
    def on_enter_pressed(self, event):
        if event.state & 0x4:
            return
        self.send_message()
        return 'break'
    
    def load_model(self, model_name):
        if not TRANSFORMERS_AVAILABLE:
            print("Библиотеки transformers/torch не установлены")
            lang = self.language_dict[self.language]
            self.model_status.config(text="Тестовый режим (установите transformers)", 
                                   fg=self.theme_colors['warning'])
            return
            
        self.model_type = model_name
        self.model_var.set(model_name)
        lang = self.language_dict[self.language]
        
        def load_model_thread():
            try:
                print(f"Загрузка модели {model_name}...")
                if model_name == "GPT-1":
                    tokenizer = OpenAIGPTTokenizer.from_pretrained("openai-community/openai-gpt")
                    model = OpenAIGPTLMHeadModel.from_pretrained("openai-community/openai-gpt")
                else:
                    tokenizer = AutoTokenizer.from_pretrained("openai-community/gpt2")
                    model = AutoModelForCausalLM.from_pretrained("openai-community/gpt2")
                    if tokenizer.pad_token is None:
                        tokenizer.pad_token = tokenizer.eos_token
                
                device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
                model = model.to(device)
                
                self.message_queue.put((self._finish_model_load, 
                                      (model_name, tokenizer, model, device, lang)))
                print(f"Модель {model_name} загружена успешно")
                
            except Exception as e:
                print(f"Ошибка загрузки модели: {e}")
                self.message_queue.put((self._show_model_error, (model_name, lang, str(e))))
        
        thread = threading.Thread(target=load_model_thread, daemon=True)
        thread.start()
        
        self.model_status.config(text=f"{model_name} ● {lang['loading']}", fg=self.theme_colors['warning'])
    
    def _finish_model_load(self, model_name, tokenizer, model, device, lang):
        self.current_tokenizer = tokenizer
        self.current_model = model
        self.current_device = device
        self.model_type = model_name
        
        device_type = "GPU" if torch.cuda.is_available() else "CPU"
        self.model_status.config(text=f"{model_name} ● {lang['ready']} ({device_type})", 
                               fg=self.theme_colors['success'])
        
        self.save_config()
    
    def _show_model_error(self, model_name, lang, error):
        self.model_status.config(text=f"{lang['load_error']}", fg=self.theme_colors['danger'])
        messagebox.showerror(lang["load_error"], str(error))
    
    def change_language(self, event=None):
        self.language = self.lang_var.get()
        self.update_ui_text()
        self.save_config()
    
    def create_new_chat(self):
        chat_id = len(self.chats)
        timestamp = datetime.now().strftime("%d.%m %H:%M")
        lang = self.language_dict[self.language]
        chat_name = f"{lang['chat_prefix']}{len(self.chats) + 1} • {timestamp}"
        
        chat_data = {
            'id': chat_id,
            'name': chat_name,
            'created_at': datetime.now().isoformat(),
            'last_modified': datetime.now().isoformat(),
            'model': self.model_type,
            'messages': []
        }
        
        self.chats.append(chat_data)
        self.current_chat_id = chat_id
        self.update_chat_list()
        self.load_chat(chat_id)
        self.save_chats_data()
    
    def load_chat(self, chat_id):
        self.current_chat_id = chat_id
        
        for chat in self.chats:
            if chat['id'] == chat_id:
                self.update_chat_title(chat['name'])
                chat['last_modified'] = datetime.now().isoformat()
                break
        
        self.chat_display.config(state=tk.NORMAL)
        self.chat_display.delete('1.0', 'end')
        
        chat_found = False
        for chat in self.chats:
            if chat['id'] == chat_id:
                chat_found = True
                if 'messages' in chat and chat['messages']:
                    for msg in chat['messages']:
                        self.display_message(msg['role'], msg['content'], 
                                           msg.get('timestamp', ''),
                                           msg.get('translated', None))
                else:
                    lang = self.language_dict[self.language]
                    welcome_msg = lang["model_ready"]
                    self.display_message("system", welcome_msg, datetime.now().strftime("%H:%M"))
                break
        
        if not chat_found:
            lang = self.language_dict[self.language]
            self.display_message("system", lang["model_ready"], datetime.now().strftime("%H:%M"))
        
        self.chat_display.config(state=tk.DISABLED)
        self.update_chat_list()
    
    def send_message(self):
        if not TRANSFORMERS_AVAILABLE:
            print("Режим тестирования - отправка сообщения")
            lang = self.language_dict[self.language]
            user_message = self.input_text.get('1.0', 'end-1c').strip()
            
            if not user_message or user_message == lang["input_placeholder"]:
                messagebox.showwarning(lang["enter_text"], lang["enter_text"])
                return
            
            timestamp = datetime.now().strftime("%H:%M")
            
            for chat in self.chats:
                if chat['id'] == self.current_chat_id:
                    chat['messages'].append({
                        'role': 'user',
                        'content': user_message,
                        'timestamp': timestamp
                    })
                    break
            
            self.display_message("user", user_message, timestamp)
            self.input_text.delete('1.0', 'end')
            self.input_text.configure(fg=self.theme_colors['text'])
            
            response = "Это тестовый ответ. Для работы с реальными моделями GPT установите библиотеки: pip install transformers torch"
            
            for chat in self.chats:
                if chat['id'] == self.current_chat_id:
                    chat['messages'].append({
                        'role': 'assistant',
                        'content': response,
                        'timestamp': timestamp
                    })
                    break
            
            self.display_message("assistant", response, timestamp)
            self.save_chats_data()
            return
            
        if not self.current_model:
            return
        
        lang = self.language_dict[self.language]
        user_message = self.input_text.get('1.0', 'end-1c').strip()
        
        if not user_message or user_message == lang["input_placeholder"]:
            messagebox.showwarning(lang["enter_text"], lang["enter_text"])
            return
        
        timestamp = datetime.now().strftime("%H:%M")
        
        for chat in self.chats:
            if chat['id'] == self.current_chat_id:
                chat['messages'].append({
                    'role': 'user',
                    'content': user_message,
                    'timestamp': timestamp
                })
                break
        
        self.display_message("user", user_message, timestamp)
        self.input_text.delete('1.0', 'end')
        self.input_text.configure(fg=self.theme_colors['text'])
        
        self.send_btn.config(text=f" {lang['generating']}", state=tk.DISABLED)
        
        def generate_response():
            try:
                input_ids = self.current_tokenizer.encode(user_message, return_tensors="pt").to(self.current_device)
                
                with torch.no_grad():
                    if self.model_type == "GPT-1":
                        output = self.current_model.generate(
                            input_ids,
                            max_new_tokens=self.length_var.get(),
                            do_sample=True,
                            temperature=self.temp_var.get(),
                            top_p=0.9,
                            repetition_penalty=1.1
                        )
                    else:
                        output = self.current_model.generate(
                            input_ids,
                            max_new_tokens=self.length_var.get(),
                            temperature=self.temp_var.get(),
                            do_sample=True,
                            top_p=0.9,
                            repetition_penalty=1.1,
                            no_repeat_ngram_size=2,
                            pad_token_id=self.current_tokenizer.pad_token_id,
                            eos_token_id=self.current_tokenizer.eos_token_id
                        )
                
                generated_text = self.current_tokenizer.decode(output[0], skip_special_tokens=True)
                
                if self.model_type == "GPT-2" and generated_text.startswith(user_message):
                    generated_text = generated_text[len(user_message):].strip()
                
                translated_text = None
                if self.translate_enabled and self.auto_translate:
                    translated_text = self.translate_text(generated_text, 
                                                         self.target_translate_lang)
                
                self.message_queue.put((self._finish_response, 
                                      (generated_text, timestamp, translated_text)))
                
            except Exception as e:
                error_msg = f"Ошибка: {str(e)}" if self.language == "Русский" else f"Error: {str(e)}"
                self.message_queue.put((self._show_error, (error_msg, timestamp)))
        
        thread = threading.Thread(target=generate_response, daemon=True)
        thread.start()
    
    def _finish_response(self, generated_text, timestamp, translated_text=None):
        for chat in self.chats:
            if chat['id'] == self.current_chat_id:
                message_data = {
                    'role': 'assistant',
                    'content': generated_text,
                    'timestamp': timestamp
                }
                if translated_text:
                    message_data['translated'] = translated_text
                chat['messages'].append(message_data)
                break
        
        self.display_message("assistant", generated_text, timestamp, translated_text)
        
        lang = self.language_dict[self.language]
        self.send_btn.config(text=f" {lang['send']}", state=tk.NORMAL)
        
        for chat in self.chats:
            if chat['id'] == self.current_chat_id:
                chat['last_modified'] = datetime.now().isoformat()
                break
        
        self.save_chats_data()
    
    def _show_error(self, error_msg, timestamp):
        for chat in self.chats:
            if chat['id'] == self.current_chat_id:
                chat['messages'].append({
                    'role': 'system',
                    'content': error_msg,
                    'timestamp': timestamp
                })
                break
        
        self.display_message("system", error_msg, timestamp)
        
        lang = self.language_dict[self.language]
        self.send_btn.config(text=f" {lang['send']}", state=tk.NORMAL)
    
    def display_message(self, role, content, timestamp="", translated=None):
        self.chat_display.config(state=tk.NORMAL)
        
        lang = self.language_dict[self.language]
        
        if role == "user":
            prefix = f"{lang['user_prefix']}: "
            tag = 'user_header'
        elif role == "assistant":
            prefix = f"{lang['gpt_prefix']}: "
            tag = 'gpt_header'
        else:
            prefix = f"{lang['system_prefix']}: "
            tag = 'system_header'
        
        self.chat_display.insert('end', prefix, tag)
        self.chat_display.insert('end', content, 'message')
        
        if timestamp:
            self.chat_display.insert('end', f"  [{timestamp}]", 'time')
        
        copy_symbol = " ⎘"
        self.chat_display.insert('end', copy_symbol, 'copy_btn')
        
        if translated:
            self.chat_display.insert('end', "\n")
            translate_symbol = " 🌐 "
            self.chat_display.insert('end', translate_symbol, 'translate_btn')
            self.chat_display.insert('end', f"{translated}")
        
        self.chat_display.insert('end', "\n\n")
        self.chat_display.see('end')
        self.chat_display.config(state=tk.DISABLED)
    
    def on_chat_click(self, event):
        index = self.chat_display.index(f"@{event.x},{event.y}")
        tags = self.chat_display.tag_names(index)
        
        if "copy_btn" in tags:
            line_start = index.split('.')[0] + '.0'
            line_end = index.split('.')[0] + '.end'
            
            line_text = self.chat_display.get(line_start, line_end)
            
            lang = self.language_dict[self.language]
            
            prefixes = [f"{lang['user_prefix']}: ", f"{lang['gpt_prefix']}: ", f"{lang['system_prefix']}: "]
            
            message = line_text
            for prefix in prefixes:
                if prefix in message:
                    message = message.split(prefix)[1]
                    break
            
            message = message.split("  [")[0].split(" ⎘")[0].split(" 🌐 ")[0].strip()
            
            self.root.clipboard_clear()
            self.root.clipboard_append(message)
            
            messagebox.showinfo(lang["copied"], lang["copied"])
    
    def toggle_translate(self):
        self.translate_enabled = self.translate_enable_var.get()
        self.save_config()
    
    def toggle_auto_translate(self):
        self.auto_translate = self.auto_translate_var.get()
        self.save_config()
    
    def translate_text(self, text, target_lang):
        if not TRANSLATOR_AVAILABLE:
            print("Переводчик не доступен. Установите: pip install googletrans==4.0.0-rc1")
            return None
        
        try:
            translation = translator.translate(text, dest=target_lang)
            return translation.text
        except Exception as e:
            print(f"Ошибка перевода: {e}")
            return None
    
    def translate_current_message(self):
        lang = self.language_dict[self.language]
        
        selected_text = self.chat_display.get(tk.SEL_FIRST, tk.SEL_LAST) if self.chat_display.tag_ranges(tk.SEL) else None
        
        if not selected_text:
            messagebox.showwarning(lang["enter_text"], lang["enter_text"])
            return
        
        if not TRANSLATOR_AVAILABLE:
            messagebox.showwarning("Ошибка", "Переводчик не установлен. Установите: pip install googletrans==4.0.0-rc1")
            return
        
        translated = self.translate_text(selected_text, self.target_translate_lang)
        
        if translated:
            self.chat_display.insert(tk.INSERT, f"\n\n🌐 {lang['translated']}: {translated}")
    
    def export_chat(self):
        lang = self.language_dict[self.language]
        
        for chat in self.chats:
            if chat['id'] == self.current_chat_id:
                file_path = filedialog.asksaveasfilename(
                    defaultextension=".json",
                    filetypes=[(lang["file_types"], "*.json")],
                    initialfile=f"chat_{chat['id']}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                )
                
                if file_path:
                    try:
                        with open(file_path, 'w', encoding='utf-8') as f:
                            json.dump(chat, f, ensure_ascii=False, indent=2)
                        
                        messagebox.showinfo(lang["export_success"], lang["export_success"])
                    except Exception as e:
                        messagebox.showerror("Error", str(e))
                break
    
    def import_chat(self):
        lang = self.language_dict[self.language]
        
        file_path = filedialog.askopenfilename(
            filetypes=[(lang["file_types"], "*.json")]
        )
        
        if file_path:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    chat_data = json.load(f)
                
                chat_id = len(self.chats)
                chat_data['id'] = chat_id
                chat_data['imported_at'] = datetime.now().isoformat()
                
                if 'name' not in chat_data:
                    timestamp = datetime.now().strftime("%d.%m %H:%M")
                    chat_data['name'] = f"{lang['chat_prefix']}{len(self.chats) + 1} • {timestamp} (импорт)"
                
                self.chats.append(chat_data)
                self.current_chat_id = chat_id
                self.update_chat_list()
                self.load_chat(chat_id)
                self.save_chats_data()
                
                messagebox.showinfo(lang["import_success"], lang["import_success"])
                
            except Exception as e:
                messagebox.showerror("Error", str(e))
    
    def clear_current_chat(self):
        lang = self.language_dict[self.language]
        
        if messagebox.askyesno(lang["clear_chat"], lang["confirm_clear"]):
            for chat in self.chats:
                if chat['id'] == self.current_chat_id:
                    chat['messages'] = []
                    break
            
            self.load_chat(self.current_chat_id)
            self.save_chats_data()
    
    def show_statistics(self):
        stats_window = tk.Toplevel(self.root)
        stats_window.title(self.language_dict[self.language]["statistics"])
        stats_window.geometry("500x400")
        stats_window.configure(bg=self.theme_colors['bg'])
        stats_window.resizable(False, False)
        
        center_frame = tk.Frame(stats_window, bg=self.theme_colors['bg'])
        center_frame.pack(expand=True, fill=tk.BOTH, padx=50, pady=50)
        
        total_messages = 0
        total_chars = 0
        total_words = 0
        
        for chat in self.chats:
            if 'messages' in chat:
                total_messages += len(chat['messages'])
                for msg in chat['messages']:
                    content = msg.get('content', '')
                    total_chars += len(content)
                    total_words += len(content.split())
        
        lang = self.language_dict[self.language]
        
        stats = [
            (f"📊 {lang['total']} {lang['messages']}:", f"{total_messages}"),
            (f"📝 {lang['total']} {lang['chars']}:", f"{total_chars}"),
            (f"📖 {lang['total']} {lang['words']}:", f"{total_words}"),
            (f"💬 {lang['chats']}:", f"{len(self.chats)}")
        ]
        
        for i, (label, value) in enumerate(stats):
            row = tk.Frame(center_frame, bg=self.theme_colors['bg'])
            row.pack(fill=tk.X, pady=10)
            
            label_widget = tk.Label(row, text=label, font=self.fonts['h3'],
                                   bg=self.theme_colors['bg'], fg=self.theme_colors['text'])
            label_widget.pack(side=tk.LEFT)
            
            value_widget = tk.Label(row, text=value, font=self.fonts['h2'],
                                   bg=self.theme_colors['bg'], fg=self.theme_colors['primary'])
            value_widget.pack(side=tk.RIGHT)
    
    def open_settings(self):
        settings_window = tk.Toplevel(self.root)
        settings_window.title(self.language_dict[self.language]["api_settings"])
        settings_window.geometry("500x300")
        settings_window.configure(bg=self.theme_colors['bg'])
        settings_window.resizable(False, False)
        
        center_frame = tk.Frame(settings_window, bg=self.theme_colors['bg'])
        center_frame.pack(expand=True, fill=tk.BOTH, padx=40, pady=40)
        
        lang = self.language_dict[self.language]
        
        api_label = tk.Label(center_frame, text="Настройки приложения", font=self.fonts['h3'],
                            bg=self.theme_colors['bg'], fg=self.theme_colors['text'])
        api_label.pack(anchor='w', pady=(0, 20))
        
        note_label = tk.Label(center_frame, text="Для работы перевода установите:\npip install googletrans==4.0.0-rc1", 
                             font=self.fonts['small'],
                             bg=self.theme_colors['bg'], fg=self.theme_colors['text_secondary'],
                             justify=tk.LEFT)
        note_label.pack(anchor='w', pady=(0, 20))
        
        button_frame = tk.Frame(center_frame, bg=self.theme_colors['bg'])
        button_frame.pack(fill=tk.X, pady=(20, 0))
        
        close_btn = tk.Button(button_frame, text="Закрыть", 
                              font=self.fonts['body'],
                              bg=self.theme_colors['primary'],
                              fg='white',
                              bd=0,
                              padx=20,
                              pady=10,
                              cursor='hand2',
                              command=settings_window.destroy)
        close_btn.pack(side=tk.RIGHT)
    
    def import_knowledge_file(self):
        """Импортирует TXT файл в базу знаний"""
        lang = self.language_dict[self.language]
        
        file_path = filedialog.askopenfilename(
            title=lang["select_txt_file"],
            filetypes=[(lang["file_types_txt"], "*.txt"), ("Все файлы", "*.*")]
        )
        
        if file_path:
            result = self.knowledge_base.import_txt_file(filepath=file_path)
            
            if result['success']:
                messagebox.showinfo(lang["import_success_kb"], 
                                  f"{lang['import_success_kb']}: {result['loaded']} {lang['entries']}\nФайл: {result['filename']}")
                
                self.knowledge_base.load_data()
                self.update_knowledge_stats()
                self.load_assistant_chat_history()
            else:
                messagebox.showerror(lang["import_error"], result['message'])
    
    def refresh_knowledge_base(self):
        """Обновляет базу знаний"""
        self.knowledge_base.load_data()
        self.update_knowledge_stats()
        
        lang = self.language_dict[self.language]
        stats = self.knowledge_base.get_stats()
        
        if stats['exists'] and stats['total_entries'] > 0:
            messagebox.showinfo("Обновлено", 
                              f"База знаний обновлена.\nЗаписей: {stats['total_entries']}\nФайлов: {stats['total_files']}")
            self.load_assistant_chat_history()
        else:
            messagebox.showwarning("Внимание", "База знаний пуста")
    
    def search_in_knowledge_base(self, event=None):
        """Ищет в базе знаний"""
        search_query = self.knowledge_search_var.get().strip()
        if not search_query:
            return
        
        results = self.knowledge_base.find_similar(search_query)
        
        self.assistant_chat_display.config(state=tk.NORMAL)
        self.assistant_chat_display.delete('1.0', 'end')
        
        lang = self.language_dict[self.language]
        
        if results:
            header = f"🔍 {lang['found_similar']}: {len(results)}\n"
            self.assistant_chat_display.insert('end', header, 'system_header')
            
            for i, result in enumerate(results[:5], 1):
                item = result['item']
                similarity = result['similarity']
                
                entry = f"\n{i}. [{similarity:.0%}] {item['russian']}\n"
                entry += f"   → {item['english']}" if item['english'] else ""
                if item['context']:
                    entry += f"\n   📝 {item['context']}"
                if 'source_file' in item:
                    entry += f"\n   📁 {item['source_file']}"
                
                self.assistant_chat_display.insert('end', entry + '\n', 'message')
        else:
            no_results = f"🔍 {lang['search']}: '{search_query}'\n\n"
            no_results += "Похожих записей не найдено."
            self.assistant_chat_display.insert('end', no_results, 'system_header')
        
        self.assistant_chat_display.config(state=tk.DISABLED)
        
        if results:
            self.last_search_info.config(
                text=f"Найдено: {len(results)} записей\nЗапрос: '{search_query}'"
            )
        else:
            self.last_search_info.config(
                text=f"Ничего не найдено\nЗапрос: '{search_query}'"
            )

def main():
    try:
        print("=" * 50)
        print("Запуск TrainsFormer AI...")
        print("=" * 50)
        
        root = tk.Tk()
        app = ModernGPTLauncher(root)
        
        print("\nПриложение успешно запущено!")
        print("Если возникнут проблемы, проверьте файл лога в:")
        print(f"{os.path.join(os.path.expanduser('~'), 'Documents', 'TrainsFormerAI', 'logs')}")
        print("=" * 50)
        
        root.mainloop()
        
    except Exception as e:
        print(f"\nКритическая ошибка: {e}")
        print("Трассировка ошибки:")
        import traceback
        traceback.print_exc()
        
        input("\nНажмите Enter для выхода...")

if __name__ == "__main__":
    main()