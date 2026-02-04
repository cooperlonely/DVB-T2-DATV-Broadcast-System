import tkinter as tk
from tkinter import scrolledtext, messagebox
import subprocess
import threading
import sys
import os
import queue

class FFmpegController:
    def __init__(self, root):
        self.root = root
        self.root.title("FFMPEG Controller")
        self.root.geometry("900x700")
        
        # Переменные
        self.process = None
        self.pid = None
        self.output_queue = queue.Queue()
        self.is_running = False
        
        # Создаем интерфейс
        self.create_widgets()
        
        # Запускаем проверку очереди вывода
        self.check_output_queue()
        
    def create_widgets(self):
        # Стили
        bg_color = "#f0f0f0"
        btn_color = "#e1e1e1"
        
        # Фрейм для запуска ffmpeg
        frame_start = tk.LabelFrame(self.root, text="Запуск FFMPEG", padx=10, pady=10, bg=bg_color)
        frame_start.pack(fill="x", padx=10, pady=10)
        
        # Команда ffmpeg по умолчанию
        default_cmd = """ffmpeg -hwaccel auto -re -f lavfi -i "color=c=black:s=1920x1080:r=30" -filter_complex "[2:v]drawtext=text='Radio Station':fontsize=60:fontcolor=cyan:box=1:boxcolor=black@0.5:boxborderw=10:x=(w-text_w)/2:y=(h-text_h)/2,drawtext=text='':fontsize=40:fontcolor=violet:box=1:boxcolor=black@0.5:boxborderw=8:x=(w-text_w)/2:y=(h-text_h)/2+120,drawtext=text='%%{localtime\\:%%X}':fontsize=50:fontcolor=cyan:box=1:boxcolor=black@0.5:boxborderw=8:x=w-text_w-30:y=30[v2];[0:v]drawtext=text='Radio Station':fontsize=60:fontcolor=magenta:box=1:boxcolor=black@0.5:boxborderw=10:x=(w-text_w)/2:y=(h-text_h)/2,drawtext=text='radio_test ffmpeg ch1':fontsize=40:fontcolor=violet:box=1:boxcolor=black@0.5:boxborderw=8:x=(w-text_w)/2:y=(h-text_h)/2+120,drawtext=text='%%{localtime\\:%%X}':fontsize=50:fontcolor=cyan:box=1:boxcolor=black@0.5:boxborderw=8:x=w-text_w-30:y=30[v1]" -i "https://control1.craftradio.ru:8000/217_03e16702" -f lavfi -i "color=c=navy:s=1920x1080:r=30" -i "https://fr2.1mix.co.uk:8000/256" -map [v1]? -map 1:a? -map [v2]? -map 3:a? -vcodec hevc_nvenc -preset p1 -b:v 767k -minrate 767k -maxrate 767k -bufsize 383k -pix_fmt yuv420p -s 1920x1080 -r 30 -c:a aac -b:a 128k -ar 48000 -ac 2 -program title="Radio":st=0:st=1 -program title="1Mix Radio":st=2:st=3 -movflags +faststart -f mpegts -flush_packets 0 -muxrate 4121136.160679 "udp://127.0.0.1:3005?pkt_size=1316&fifo_size=50000000&overrun_nonfatal=1&burst_bits=1\""""
        
        # Текстовое поле для команды ffmpeg
        tk.Label(frame_start, text="Команда FFMPEG:", bg=bg_color).pack(anchor="w")
        
        self.cmd_text = scrolledtext.ScrolledText(frame_start, height=8, width=100)
        self.cmd_text.pack(fill="x", pady=(0, 10))
        self.cmd_text.insert("1.0", default_cmd)
        
        # Кнопки запуска/остановки
        btn_frame = tk.Frame(frame_start, bg=bg_color)
        btn_frame.pack(fill="x")
        
        self.start_btn = tk.Button(btn_frame, text="▶ Start FFMPEG", 
                                  command=self.start_ffmpeg, 
                                  bg="#4CAF50", fg="white",
                                  font=("Arial", 10, "bold"),
                                  width=15)
        self.start_btn.pack(side="left", padx=(0, 10))
        
        self.stop_btn = tk.Button(btn_frame, text="⏹ Stop FFMPEG", 
                                 command=self.stop_ffmpeg,
                                 bg="#f44336", fg="white",
                                 font=("Arial", 10, "bold"),
                                 width=15, state="disabled")
        self.stop_btn.pack(side="left")
        
        # Статус процесса
        self.status_label = tk.Label(frame_start, text="Статус: FFMPEG не запущен", 
                                    bg=bg_color, fg="red", font=("Arial", 10, "bold"))
        self.status_label.pack(anchor="w", pady=(10, 0))
        
        # Индикатор PID
        self.pid_label = tk.Label(frame_start, text="PID: -", 
                                 bg=bg_color, font=("Arial", 9))
        self.pid_label.pack(anchor="w")
        
        # Фрейм для отправки команд в stdin
        frame_stdin = tk.LabelFrame(self.root, text="Отправка команд в STDIN", padx=10, pady=10, bg=bg_color)
        frame_stdin.pack(fill="x", padx=10, pady=10)
        
        # Команда по умолчанию
        default_stdin_cmd = "CParsed_drawtext_1 0.0 reinit text='testenter1'\\n"
        
        tk.Label(frame_stdin, text="Команда для отправки:", bg=bg_color).pack(anchor="w")
        
        self.stdin_text = tk.Text(frame_stdin, height=3, width=100)
        self.stdin_text.pack(fill="x", pady=(0, 10))
        self.stdin_text.insert("1.0", default_stdin_cmd)
        
        # Кнопка отправки
        self.send_btn = tk.Button(frame_stdin, text="📤 Send to STDIN", 
                                 command=self.send_to_stdin,
                                 bg="#2196F3", fg="white",
                                 font=("Arial", 10, "bold"),
                                 width=15, state="disabled")
        self.send_btn.pack(anchor="w")
        
        # Фрейм для логов
        frame_logs = tk.LabelFrame(self.root, text="Логи FFMPEG", padx=10, pady=10, bg=bg_color)
        frame_logs.pack(fill="both", expand=True, padx=10, pady=10)
        
        self.log_text = scrolledtext.ScrolledText(frame_logs, height=15, width=100)
        self.log_text.pack(fill="both", expand=True)
        
        # Кнопка очистки логов
        tk.Button(frame_logs, text="Очистить логи", 
                 command=self.clear_logs, bg=btn_color).pack(anchor="e", pady=(5, 0))
        
    def check_output_queue(self):
        """Проверка очереди вывода и обновление логов"""
        try:
            while True:
                message = self.output_queue.get_nowait()
                self.log_message(message)
        except queue.Empty:
            pass
        finally:
            # Проверяем снова через 100 мс
            self.root.after(100, self.check_output_queue)
        
    def log_message(self, message):
        """Добавление сообщения в лог"""
        self.log_text.insert("end", message + "\n")
        self.log_text.see("end")
        
    def clear_logs(self):
        """Очистка логов"""
        self.log_text.delete("1.0", "end")
        
    def start_ffmpeg(self):
        """Запуск ffmpeg в отдельном потоке"""
        cmd = self.cmd_text.get("1.0", "end-1c").strip()
        
        if not cmd:
            messagebox.showerror("Ошибка", "Команда FFMPEG пуста!")
            return
            
        # Отключаем кнопку старта, включаем стоп
        self.start_btn.config(state="disabled")
        self.stop_btn.config(state="normal")
        self.status_label.config(text="Статус: Запуск FFMPEG...", fg="orange")
        
        # Запуск в отдельном потоке
        thread = threading.Thread(target=self.run_ffmpeg, args=(cmd,), daemon=True)
        thread.start()
        
    def run_ffmpeg(self, cmd):
        """Запуск ffmpeg процесса"""
        try:
            # Заменяем двойные проценты для Windows
            cmd = cmd.replace('%%{', '%{')
            
            self.output_queue.put(f"[INFO] Запуск команды: {cmd[:100]}...")
            
            # Запускаем процесс с отдельными потоками для stdout и stderr
            self.process = subprocess.Popen(
                cmd,
                shell=True,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                universal_newlines=True,
                encoding='utf-8',
                errors='replace'
            )
            
            self.pid = self.process.pid
            self.is_running = True
            
            # Обновляем GUI в основном потоке
            self.root.after(0, lambda: self.update_status_running())
            
            self.output_queue.put(f"[INFO] FFMPEG запущен с PID: {self.pid}")
            
            # Запускаем отдельные потоки для чтения stdout и stderr
            stdout_thread = threading.Thread(target=self.read_stdout, daemon=True)
            stderr_thread = threading.Thread(target=self.read_stderr, daemon=True)
            
            stdout_thread.start()
            stderr_thread.start()
            
            # Ждем завершения процесса
            self.process.wait()
            self.is_running = False
            
            # Проверяем код возврата
            return_code = self.process.returncode
            
            if return_code == 0 or return_code == 255:  # 255 - Ctrl+C
                self.output_queue.put(f"[INFO] FFMPEG завершился с кодом {return_code}")
            else:
                self.output_queue.put(f"[ERROR] FFMPEG завершился с кодом {return_code}")
                
        except Exception as e:
            self.output_queue.put(f"[ERROR] Ошибка при запуске FFMPEG: {str(e)}")
            self.is_running = False
        finally:
            # Восстанавливаем кнопки в основном потоке
            self.root.after(0, self.reset_buttons)
            self.process = None
            self.pid = None
            
    def read_stdout(self):
        """Чтение stdout процесса"""
        if self.process:
            for line in iter(self.process.stdout.readline, ''):
                if line:
                    self.output_queue.put(f"[STDOUT] {line.strip()}")
                    
    def read_stderr(self):
        """Чтение stderr процесса"""
        if self.process:
            for line in iter(self.process.stderr.readline, ''):
                if line:
                    self.output_queue.put(f"[FFMPEG] {line.strip()}")
                    
    def update_status_running(self):
        """Обновление статуса когда процесс запущен"""
        if self.is_running and self.pid:
            self.status_label.config(text=f"Статус: FFMPEG запущен (PID: {self.pid})", fg="green")
            self.pid_label.config(text=f"PID: {self.pid}")
            self.send_btn.config(state="normal")
            
    def reset_buttons(self):
        """Сброс состояния кнопок после завершения процесса"""
        self.start_btn.config(state="normal")
        self.stop_btn.config(state="disabled")
        self.send_btn.config(state="disabled")
        self.status_label.config(text="Статус: FFMPEG не запущен", fg="red")
        self.pid_label.config(text="PID: -")
        
    def stop_ffmpeg(self):
        """Остановка ffmpeg процесса"""
        if self.process and self.is_running:
            self.output_queue.put("[INFO] Остановка FFMPEG...")
            self.status_label.config(text="Статус: Остановка...", fg="orange")
            
            # Отправляем Ctrl+C
            try:
                if sys.platform == "win32":
                    import ctypes
                    ctypes.windll.kernel32.GenerateConsoleCtrlEvent(0, self.pid)
                else:
                    self.process.send_signal(subprocess.signal.SIGINT)
                    
                # Ждем завершения
                self.process.wait(timeout=5)
            except:
                # Принудительное завершение если не отвечает
                self.process.terminate()
                
    def send_to_stdin(self):
        """Отправка команды в stdin процесса"""
        if not self.process or not self.is_running:
            messagebox.showwarning("Предупреждение", "FFMPEG не запущен!")
            self.send_btn.config(state="disabled")
            return
            
        cmd = self.stdin_text.get("1.0", "end-1c").strip()
        
        if not cmd:
            messagebox.showwarning("Предупреждение", "Команда пуста!")
            return
            
        try:
            # Убираем лишние обратные слэши если есть
            cmd = cmd.replace('\\n', '\n')
            
            # Добавляем новую строку если нет
            if not cmd.endswith('\n'):
                cmd += '\n'
                
            # Отправляем команду
            self.process.stdin.write(cmd)
            self.process.stdin.flush()
            
            self.output_queue.put(f"[INFO] Отправлена команда: {cmd.strip()}")
            
        except BrokenPipeError:
            self.output_queue.put("[ERROR] Соединение с FFMPEG разорвано")
            self.reset_buttons()
        except Exception as e:
            self.output_queue.put(f"[ERROR] Не удалось отправить команду: {str(e)}")

def main():
    root = tk.Tk()
    app = FFmpegController(root)
    
    # Запуск главного цикла
    root.mainloop()

if __name__ == "__main__":
    main()