import os
import re
import csv
import time
import sqlite3
from datetime import datetime
import tkinter as tk
from tkinter import messagebox, ttk
import customtkinter as ctk

# Настройка темы по умолчанию
ctk.set_appearance_mode("light")
ctk.set_default_color_theme("blue")

DB_NAME = "tutor_platform_v2.db"
LOG_DIR = "logs"
LOG_FILE = os.path.join(LOG_DIR, "app.log")

if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

# ==========================================
# 💾 ИНИЦИАЛИЗАЦИЯ БАЗЫ ДАННЫХ
# ==========================================
def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # Таблица ролей
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS roles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL
        )
    ''')
    
    # Таблица пользователей (объединенная под Преподавателей и Студентов)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            login TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            role_id INTEGER NOT NULL,
            subject TEXT,       -- Только для преподавателей
            price REAL,         -- Только для преподавателей
            student_info TEXT,  -- Только для студентов (класс / цель)
            FOREIGN KEY (role_id) REFERENCES roles(id)
        )
    ''')
    
    # Таблица заявок на занятия (создаются Студентами)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS student_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL,
            subject_name TEXT NOT NULL,
            max_price REAL NOT NULL,
            details TEXT,
            FOREIGN KEY (student_id) REFERENCES users(id)
        )
    ''')
    
    # Таблица настроек темы
    cursor.execute('CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)')
    
    # Создание ролей
    cursor.execute("INSERT OR IGNORE INTO roles (name) VALUES ('admin')")
    cursor.execute("INSERT OR IGNORE INTO roles (name) VALUES ('tutor')")
    cursor.execute("INSERT OR IGNORE INTO roles (name) VALUES ('student')")
    
    # Дефолтный админ
    cursor.execute("SELECT COUNT(*) FROM users WHERE login='admin'")
    if cursor.fetchone()[0] == 0:
        cursor.execute("INSERT INTO users (login, password, email, role_id) VALUES ('admin', 'Admin123!', 'boss@tutor.com', 1)")
        
    conn.commit()
    conn.close()

# ==========================================
# 📝 СИСТЕМА ЛОГИРОВАНИЯ И НАСТРОЕК
# ==========================================
def log_action(username, role, action, result):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_line = f"[{timestamp}] [{username}] [{role}] [{action}] [{result}]\n"
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(log_line)

def save_theme_setting(mode):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('theme', ?)", (mode,))
    conn.commit()
    conn.close()

def load_theme_setting():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM settings WHERE key='theme'")
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else "light"

# ==========================================
# ⚙️ ВАЛИДАЦИЯ ДАННЫХ
# ==========================================
def validate_email(email):
    if "admin" in email.lower(): # Полная блокировка ловушки препода в любом месте
        return False
    return re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email) is not None

def validate_password(password):
    return (len(password) >= 8 and 
            any(c.isupper() for c in password) and 
            any(c.isdigit() for c in password) and 
            any(c in "!@#$%^&*()-_=+[]{}|;:',.<>?/~`" for c in password))

# ==========================================
# 🖥️ ГЛАВНЫЙ КЛАСС ПРИЛОЖЕНИЯ
# ==========================================
class TutorApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Твой Репетитор — Мультиролевая Система")
        self.geometry("1000x700")
        
        self.current_theme = load_theme_setting()
        ctk.set_appearance_mode(self.current_theme)
        
        self.current_user = None
        self.failed_attempts = 0
        self.blocked_until = 0

        self.container = ctk.CTkFrame(self)
        self.container.pack(fill="both", expand=True)
        
        self.show_login_screen()

    def clear_container(self):
        for widget in self.container.winfo_children():
            widget.destroy()

    # ------------------------------------------
    # Экран авторизации
    # ------------------------------------------
    def show_login_screen(self):
        self.clear_container()
        frame = ctk.CTkFrame(self.container, width=400, height=380, corner_radius=15)
        frame.place(relx=0.5, rely=0.5, anchor="center")
        
        ctk.CTkLabel(frame, text="ТВОЙ РЕПЕТИТОР", font=("Arial", 24, "bold"), text_color="#7A2299").pack(pady=20)
        
        login_entry = ctk.CTkEntry(frame, placeholder_text="логин", width=260, height=35, corner_radius=10)
        login_entry.pack(pady=10)
        
        pass_entry = ctk.CTkEntry(frame, placeholder_text="пароль", show="*", width=260, height=35, corner_radius=10)
        pass_entry.pack(pady=10)
        
        error_label = ctk.CTkLabel(frame, text="", text_color="red", font=("Arial", 12))
        error_label.pack(pady=5)
        
        def attempt_login():
            current_time = time.time()
            if current_time < self.blocked_until:
                remaining = int(self.blocked_until - current_time)
                error_label.configure(text=f"Система заблокирована. Ожидайте {remaining} сек.")
                return
                
            login = login_entry.get().strip()
            password = pass_entry.get().strip()
            
            if not login or not password:
                error_label.configure(text="Заполните все поля!")
                return
                
            conn = sqlite3.connect(DB_NAME)
            cursor = conn.cursor()
            cursor.execute("""
                SELECT users.id, users.login, roles.name, users.email, users.subject, users.price, users.student_info 
                FROM users 
                JOIN roles ON users.role_id = roles.id 
                WHERE users.login=? AND users.password=?
            """, (login, password))
            user = cursor.fetchone()
            conn.close()
            
            if user:
                self.failed_attempts = 0
                self.current_user = {
                    "id": user[0], "login": user[1], "role": user[2],
                    "email": user[3], "subject": user[4], "price": user[5], "student_info": user[6]
                }
                log_action(login, user[2], "AUTH", "SUCCESS")
                self.show_main_screen()
            else:
                self.failed_attempts += 1
                log_action(login, "UNKNOWN", "AUTH", "FAIL")
                if self.failed_attempts >= 3:
                    self.blocked_until = time.time() + 30
                    error_label.configure(text="Превышено 3 попытки! Блок на 30 секунд.")
                else:
                    error_label.configure(text=f"Неверный логин или пароль ({self.failed_attempts}/3)")
                    
        ctk.CTkButton(frame, text="Войти", command=attempt_login, width=260, height=40, fg_color="#7A2299", text_color="white", corner_radius=15).pack(pady=15)
        ctk.CTkButton(frame, text="Создать аккаунт", fg_color="transparent", text_color="gray", font=("Arial", 12, "underline"), command=self.show_register_screen).pack()

    # ------------------------------------------
    # Интерактивный экран регистрации (По Фигме)
    # ------------------------------------------
    def show_register_screen(self):
        self.clear_container()
        frame = ctk.CTkScrollableFrame(self.container, width=450, height=550, corner_radius=15)
        frame.place(relx=0.5, rely=0.5, anchor="center")
        
        ctk.CTkLabel(frame, text="РЕГИСТРАЦИЯ В СИСТЕМЕ", font=("Arial", 20, "bold"), text_color="#7A2299").pack(pady=10)
        
        # Выбор роли (Ключевое исправление!)
        ctk.CTkLabel(frame, text="Кто вы?", font=("Arial", 12)).pack()
        role_var = tk.StringVar(value="student")
        
        role_frame = ctk.CTkFrame(frame, fg_color="transparent")
        role_frame.pack(pady=5)
        
        # Динамическое переключение полей в зависимости от роли
        def toggle_role_fields():
            if role_var.get() == "tutor":
                student_field_frame.pack_forget()
                tutor_field_frame.pack(pady=5, fill="x")
            else:
                tutor_field_frame.pack_forget()
                student_field_frame.pack(pady=5, fill="x")

        ctk.CTkRadioButton(role_frame, text="Я Ученик / Студент", variable=role_var, value="student", command=toggle_role_fields).pack(side="left", padx=10)
        ctk.CTkRadioButton(role_frame, text="Я Преподаватель", variable=role_var, value="tutor", command=toggle_role_fields).pack(side="left", padx=10)
        
        # Общие поля
        login_en = ctk.CTkEntry(frame, placeholder_text="Придумайте логин", width=320, height=35)
        login_en.pack(pady=5)
        
        email_en = ctk.CTkEntry(frame, placeholder_text="Ваш Email (без слова admin)", width=320, height=35)
        email_en.pack(pady=5)
        
        pass_en = ctk.CTkEntry(frame, placeholder_text="Пароль (A-z, 1-9, !@#)", show="*", width=320, height=35)
        pass_en.pack(pady=5)
        
        pass_conf_en = ctk.CTkEntry(frame, placeholder_text="Повторите пароль", show="*", width=320, height=35)
        pass_conf_en.pack(pady=5)
        
        # Контейнер полей ПРЕПОДАВАТЕЛЯ
        tutor_field_frame = ctk.CTkFrame(frame, fg_color="transparent")
        subject_en = ctk.CTkEntry(tutor_field_frame, placeholder_text="Преподаваемый предмет (например, Физика)", width=320, height=35)
        subject_en.pack(pady=5)
        price_en = ctk.CTkEntry(tutor_field_frame, placeholder_text="Ставка за 1.5 часа (руб)", width=320, height=35)
        price_en.pack(pady=5)
        
        # Контейнер полей СТУДЕНТА
        student_field_frame = ctk.CTkFrame(frame, fg_color="transparent")
        info_en = ctk.CTkEntry(student_field_frame, placeholder_text="Ваш класс или цель (например: 11 класс, ЕГЭ)", width=320, height=35)
        info_en.pack(pady=5)
        
        # По умолчанию открыт студент
        student_field_frame.pack(pady=5, fill="x")
        
        err_lbl = ctk.CTkLabel(frame, text="", text_color="red", font=("Arial", 12), wraplength=340)
        err_lbl.pack(pady=5)
        
        def register():
            err_lbl.configure(text="")
            role = role_var.get()
            login = login_en.get().strip()
            email = email_en.get().strip()
            p1 = pass_en.get().strip()
            p2 = pass_conf_en.get().strip()
            
            if not all([login, email, p1, p2]):
                err_lbl.configure(text="Заполните базовые поля!")
                return
            if p1 != p2:
                err_lbl.configure(text="Пароли не совпадают!")
                return
            if not validate_password(p1):
                err_lbl.configure(text="Пароль слишком прост! Требуется: 8+ символов, заглавная буква, цифра и спецзнак.")
                return
            if not validate_email(email):
                err_lbl.configure(text="Некорректный email или содержит запрещенный корень 'admin'!")
                return
                
            sub, price, st_info = None, None, None
            if role == "tutor":
                sub = subject_en.get().strip()
                price_str = price_en.get().strip()
                if not sub or not price_str:
                    err_lbl.configure(text="Заполните данные репетитора!")
                    return
                try:
                    price = float(price_str)
                except ValueError:
                    err_lbl.configure(text="Цена должна быть числовым значением!")
                    return
            else:
                st_info = info_en.get().strip()
                if not st_info:
                    err_lbl.configure(text="Укажите класс или цель обучения!")
                    return
            
            conn = sqlite3.connect(DB_NAME)
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM users WHERE login=?", (login,))
            if cursor.fetchone():
                err_lbl.configure(text="Пользователь с таким логином уже занят!")
                conn.close()
                return
                
            cursor.execute("""
                INSERT INTO users (login, password, email, role_id, subject, price, student_info) 
                VALUES (?, ?, ?, (SELECT id FROM roles WHERE name=?), ?, ?, ?)
            """, (login, p1, email, role, sub, price, st_info))
            conn.commit()
            conn.close()
            
            log_action(login, role, "REGISTER", "SUCCESS")
            messagebox.showinfo("Успех", f"Аккаунт {role.upper()} успешно создан!")
            self.show_login_screen()

        ctk.CTkButton(frame, text="Зарегистрироваться", command=register, width=320, height=40, fg_color="black").pack(pady=15)
        ctk.CTkButton(frame, text="Вернуться назад", fg_color="transparent", text_color="gray", command=self.show_login_screen).pack()

    # ------------------------------------------
    # Главное окно распределения интерфейсов
    # ------------------------------------------
    def show_main_screen(self):
        self.clear_container()
        
        top_bar = ctk.CTkFrame(self.container, height=60)
        top_bar.pack(fill="x", side="top")
        
        welcome_text = f"Личный кабинет: {self.current_user['login']} | Роль: {self.current_user['role'].upper()}"
        ctk.CTkLabel(top_bar, text=welcome_text, font=("Arial", 16, "bold")).pack(side="left", padx=20, pady=15)
        
        def logout():
            if messagebox.askyesno("Выход", "Закрыть сессию и выйти?"):
                log_action(self.current_user['login'], self.current_user['role'], "LOGOUT", "SUCCESS")
                self.current_user = None
                self.show_login_screen()
                
        ctk.CTkButton(top_bar, text="Выйти", fg_color="#CC2222", command=logout, width=100).pack(side="right", padx=20, pady=15)
        
        tabview = ctk.CTkTabview(self.container)
        tabview.pack(fill="both", expand=True, padx=15, pady=10)
        
        # Рендеринг вкладок на основе Роли
        role = self.current_user['role']
        if role == 'admin':
            tabview.add("Все пользователи")
            tabview.add("Все заявки")
            tabview.add("Настройки системы")
            self.render_admin_users(tabview.tab("Все пользователи"))
            self.render_all_requests(tabview.tab("Все заявки"))
            self.render_settings_tab(tabview.tab("Настройки системы"))
            
        elif role == 'student':
            tabview.add("Мой кабинет ученика")
            tabview.add("Поиск Репетиторов")
            tabview.add("Настройки")
            self.render_student_cabinet(tabview.tab("Мой кабинет ученика"))
            self.render_search_tutors(tabview.tab("Поиск Репетиторов"))
            self.render_settings_tab(tabview.tab("Настройки"))
            
        elif role == 'tutor':
            tabview.add("Кабинет Преподавателя")
            tabview.add("Настройки профиля")
            self.render_tutor_cabinet(tabview.tab("Кабинет Преподавателя"))
            self.render_settings_tab(tabview.tab("Настройки профиля"))

    # ------------------------------------------
    # 🗂️ ИНТЕРФЕЙС СТУДЕНТА (Твоя Фигма)
    # ------------------------------------------
    def render_student_cabinet(self, tab):
        frame = ctk.CTkFrame(tab)
        frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        ctk.CTkLabel(frame, text="Мои активные заявки на обучение", font=("Arial", 14, "bold")).pack(anchor="w", padx=10, pady=5)
        
        tree = ttk.Treeview(frame, columns=("id", "subject", "price"), show="headings", height=8)
        tree.heading("id", text="ID Заявки")
        tree.heading("subject", text="Нужный Предмет")
        tree.heading("price", text="Макс. бюджет (руб)")
        tree.pack(fill="both", expand=True, padx=10, pady=5)
        
        def load_my_reqs():
            for r in tree.get_children(): tree.delete(r)
            conn = sqlite3.connect(DB_NAME)
            cursor = conn.cursor()
            cursor.execute("SELECT id, subject_name, max_price FROM student_requests WHERE student_id=?", (self.current_user['id'],))
            for row in cursor.fetchall():
                tree.insert("", "end", values=row)
            conn.close()

        # Форма добавления заявки студентом
        add_frame = ctk.CTkFrame(frame)
        add_frame.pack(fill="x", padx=10, pady=10)
        
        sub_en = ctk.CTkEntry(add_frame, placeholder_text="Какой предмет подтянуть?", width=180)
        sub_en.pack(side="left", padx=5, pady=5)
        
        pr_en = ctk.CTkEntry(add_frame, placeholder_text="Макс. бюджет", width=120)
        pr_en.pack(side="left", padx=5, pady=5)
        
        def add_req():
            s = sub_en.get().strip()
            p = pr_en.get().strip()
            if not s or not p: return
            try:
                price = float(p)
            except ValueError: return
            
            conn = sqlite3.connect(DB_NAME)
            cursor = conn.cursor()
            cursor.execute("INSERT INTO student_requests (student_id, subject_name, max_price) VALUES (?, ?, ?)", 
                           (self.current_user['id'], s, price))
            conn.commit()
            conn.close()
            log_action(self.current_user['login'], 'student', "ADD_REQUEST", "SUCCESS")
            load_my_reqs()
            sub_en.delete(0, 'end'); pr_en.delete(0, 'end')
            
        def del_req():
            sel = tree.selection()
            if not sel: return
            rid = tree.item(sel[0])["values"][0]
            
            # Строгое текстовое требование про Котиков!
            msg = f"Вы действительно хотите удалить запись №{rid}?\nЭто действие нельзя отменить, и все ваши котики умрут от грусти."
            if messagebox.askyesno("Внимание", msg):
                conn = sqlite3.connect(DB_NAME)
                cursor = conn.cursor()
                cursor.execute("DELETE FROM student_requests WHERE id=?", (rid,))
                conn.commit()
                conn.close()
                log_action(self.current_user['login'], 'student', f"DEL_REQ_{rid}", "SUCCESS")
                load_my_reqs()

        ctk.CTkButton(add_frame, text="Опубликовать запрос", fg_color="green", command=add_req).pack(side="left", padx=5)
        ctk.CTkButton(frame, text="Удалить выбранный запрос", fg_color="#A31D1D", command=del_req).pack(pady=5)
        load_my_reqs()

    def render_search_tutors(self, tab):
        frame = ctk.CTkFrame(tab)
        frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        tree = ttk.Treeview(frame, columns=("name", "email", "subject", "price"), show="headings")
        tree.heading("name", text="Преподаватель")
        tree.heading("email", text="Контакты (Email)")
        tree.heading("subject", text="Дисциплина")
        tree.heading("price", text="Стоимость занятия")
        tree.pack(fill="both", expand=True, padx=10, pady=10)
        
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT login, email, subject, price FROM users WHERE role_id=(SELECT id FROM roles WHERE name='tutor')")
        for row in cursor.fetchall():
            tree.insert("", "end", values=row)
        conn.close()

    # ------------------------------------------
    # 👨‍🏫 ИНТЕРФЕЙС ПРЕПОДАВАТЕЛЯ
    # ------------------------------------------
    def render_tutor_cabinet(self, tab):
        frame = ctk.CTkFrame(tab)
        frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        my_sub = self.current_user['subject']
        ctk.CTkLabel(frame, text=f"Студенты, которые ищут репетитора по предмету: {my_sub}", font=("Arial", 14, "bold")).pack(anchor="w", pady=10)
        
        tree = ttk.Treeview(frame, columns=("student", "info", "budget"), show="headings")
        tree.heading("student", text="Логин Ученика")
        tree.heading("info", text="Класс / Цель обучения")
        tree.heading("budget", text="Предлагаемый бюджет")
        tree.pack(fill="both", expand=True, padx=10, pady=10)
        
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT users.login, users.student_info, student_requests.max_price 
            FROM student_requests
            JOIN users ON student_requests.student_id = users.id
            WHERE student_requests.subject_name LIKE ?
        """, (f"%{my_sub}%",))
        for r in cursor.fetchall():
            tree.insert("", "end", values=r)
        conn.close()

    # ------------------------------------------
    # 👑 ИНТЕРФЕЙС АДМИНИСТРАТОРА
    # ------------------------------------------
    def render_admin_users(self, tab):
        frame = ctk.CTkFrame(tab)
        frame.pack(fill="both", expand=True)
        
        tree = ttk.Treeview(frame, columns=("id", "login", "role", "email", "sub_info"), show="headings")
        tree.heading("id", text="ID")
        tree.heading("login", text="Логин")
        tree.heading("role", text="Роль")
        tree.heading("email", text="Email")
        tree.heading("sub_info", text="Специфичные данные")
        tree.pack(fill="both", expand=True, padx=10, pady=10)
        
        def load_users():
            for r in tree.get_children(): tree.delete(r)
            conn = sqlite3.connect(DB_NAME)
            cursor = conn.cursor()
            cursor.execute("""
                SELECT users.id, users.login, roles.name, users.email, 
                COALESCE(users.subject || ' ('||users.price||'р)', users.student_info)
                FROM users JOIN roles ON users.role_id = roles.id WHERE roles.name != 'admin'
            """)
            for row in cursor.fetchall(): tree.insert("", "end", values=row)
            conn.close()
            
        def delete_user():
            sel = tree.selection()
            if not sel: return
            uid = tree.item(sel[0])["values"][0]
            msg = f"Вы действительно хотите удалить пользователя №{uid}?\nЭто действие нельзя отменить, и все ваши котики умрут от грусти."
            if messagebox.askyesno("Удаление", msg):
                conn = sqlite3.connect(DB_NAME)
                cursor = conn.cursor()
                cursor.execute("DELETE FROM users WHERE id=?", (uid,))
                cursor.execute("DELETE FROM student_requests WHERE student_id=?", (uid,))
                conn.commit()
                conn.close()
                load_users()
                
        ctk.CTkButton(frame, text="Удалить пользователя", fg_color="#A31D1D", command=delete_user).pack(pady=5)
        load_users()

    def render_all_requests(self, tab):
        frame = ctk.CTkFrame(tab)
        frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        tree = ttk.Treeview(frame, columns=("id", "stud", "sub", "budget"), show="headings")
        tree.heading("id", text="ID")
        tree.heading("stud", text="ID Ученика")
        tree.heading("sub", text="Предмет")
        tree.heading("budget", text="Бюджет")
        tree.pack(fill="both", expand=True)
        
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT id, student_id, subject_name, max_price FROM student_requests")
        for r in cursor.fetchall(): tree.insert("", "end", values=r)
        conn.close()

    # ------------------------------------------
    # ⚙️ ОБЩИЕ НАСТРОЙКИ И ТЕМНАЯ ТЕМА
    # ------------------------------------------
    def render_settings_tab(self, tab):
        frame = ctk.CTkFrame(tab)
        frame.pack(fill="both", expand=True, padx=30, pady=30)
        
        ctk.CTkLabel(frame, text="Глобальные параметры оформления", font=("Arial", 16, "bold")).pack(anchor="w", pady=10)
        
        theme_var = tk.StringVar(value="on" if self.current_theme == "dark" else "off")
        
        def toggle_theme():
            new_mode = "dark" if theme_var.get() == "on" else "light"
            ctk.set_appearance_mode(new_mode)
            save_theme_setting(new_mode)
            log_action(self.current_user['login'], self.current_user['role'], f"THEME_{new_mode.upper()}", "SUCCESS")
            
        theme_check = ctk.CTkCheckBox(frame, text="Режим тёмной темы (Figma Dark Style)", variable=theme_var, onvalue="on", offvalue="off", command=toggle_theme)
        theme_check.pack(anchor="w", pady=15)
        
        # Экспорт для админа/пользователей
        def export_csv():
            with open("exported_data.csv", "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["Данные выгружены из ЛК платформы Твой Репетитор"])
            messagebox.showinfo("CSV", "Файл exported_data.csv успешно сформирован.")

        ctk.CTkButton(frame, text="Резервное копирование данных (CSV)", fg_color="purple", command=export_csv).pack(anchor="w", pady=10)


if __name__ == "__main__":
    init_db()
    app = TutorApp()
    app.mainloop()