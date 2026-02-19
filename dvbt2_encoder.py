import os
import random
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import zmq
import threading
import time
import shlex
import re
import sys
import socket
import queue
from collections import deque
from collections import OrderedDict
import subprocess
import json
import http.server
import socketserver
import webbrowser
from http.server import SimpleHTTPRequestHandler
import psutil
import xmlrpc.client
from pathlib import Path
import signal
# Добавьте эти импорты для работы с ярлыками Windows
try:
    import pythoncom
    from win32com.client import Dispatch
    HAS_WIN32COM = True
except ImportError:
    HAS_WIN32COM = False
    print("win32com not available, .lnk shortcut resolution disabled")

# =============================================================================
# DVBTTipsWindow - Independent window with DVB-T2 tips and recommendations
# =============================================================================

class DVBTTipsWindow:
    """Independent window with DVB-T2 tips and recommendations"""
    
    def __init__(self, parent):
        self.parent = parent
        self.window = None
        self.current_language = "English"  # По умолчанию английский
        
    def show(self):
        """Show the tips window"""
        try:
            if self.window and self.window.winfo_exists():
                self.window.lift()
                self.window.focus_force()
                return
                
            self.window = tk.Toplevel(self.parent.root)
            self.window.title("DVB-T2 Info & Recommendations")
            self.window.geometry("1200x700+50+50")  # Увеличиваем размер окна
            self.window.configure(bg='white')
            self.window.resizable(True, True)
            
            # Make window stay on top but not blocking
            self.window.attributes('-topmost', True)
            self.window.transient(self.parent.root)
            
            self.create_content()
            
        except Exception as e:
            print(f"Error creating tips window: {e}")
            
    def on_language_change(self, event=None):
        """Handle language change"""
        try:
            self.current_language = self.language_var.get()
            # Обновляем все содержимое окна
            self.create_content()
            # Обновляем анализ с новым языком
            self.update_analysis()
        except Exception as e:
            print(f"Error changing language: {e}")            
        
    def create_content(self):
        """Create window content with better layout"""
        try:
            # Clear existing content if any
            for widget in self.window.winfo_children():
                widget.destroy()
            
            # Main frame with paned window for better space usage
            main_paned = ttk.PanedWindow(self.window, orient=tk.HORIZONTAL)
            main_paned.pack(fill='both', expand=True, padx=10, pady=10)
            
            # Left pane - Analysis and Quick Tips
            left_frame = ttk.Frame(main_paned)
            main_paned.add(left_frame, weight=1)
            
            # Right pane - Detailed Guides
            right_frame = ttk.Frame(main_paned)
            main_paned.add(right_frame, weight=1)
            
            # Left content
            self.create_left_content(left_frame)
            
            # Right content
            self.create_right_content(right_frame)
            
        except Exception as e:
            print(f"Error creating content: {e}")
        
    def create_left_content(self, parent):
        """Create left pane content - Analysis and Quick Tips"""
        # Language selection frame - НОВЫЙ!
        lang_frame = ttk.Frame(parent)
        lang_frame.pack(fill='x', pady=(0, 5))
        
        ttk.Label(lang_frame, text="Language:", font=('Arial', 9)).pack(side='left', padx=(0, 5))
        
        self.language_var = tk.StringVar(value=self.current_language)
        language_combo = ttk.Combobox(lang_frame, textvariable=self.language_var,
                                     values=["English", "Russian"], state="readonly",
                                     width=10)
        language_combo.pack(side='left')
        language_combo.bind('<<ComboboxSelected>>', self.on_language_change)
        
        # Current Status
        status_frame = ttk.LabelFrame(parent, text="🔍 Current Configuration Analysis" if self.current_language == "English" else "🔍 Анализ текущей конфигурации", padding="10")
        status_frame.pack(fill='x', pady=(0, 10))
                
        # Status labels в две колонки
        status_grid = ttk.Frame(status_frame)
        status_grid.pack(fill='x')
        
        # Колонка 1
        col1 = ttk.Frame(status_grid)
        col1.pack(side='left', fill='x', expand=True, padx=(0, 10))
        
        self.tf_label = tk.Label(col1, text="Frame Time: --", 
                                font=('Arial', 9, 'bold'), fg='black', justify='left')
        self.tf_label.pack(anchor='w', pady=2)
        
        self.dummy_label = tk.Label(col1, text="Dummy Cells: --", 
                                   font=('Arial', 9, 'bold'), fg='black', justify='left')
        self.dummy_label.pack(anchor='w', pady=2)
        
        # Колонка 2
        col2 = ttk.Frame(status_grid)
        col2.pack(side='left', fill='x', expand=True)
        
        self.efficiency_label = tk.Label(col2, text="Efficiency: --", 
                                       font=('Arial', 9), fg='black', justify='left')
        self.efficiency_label.pack(anchor='w', pady=2)
        
        self.robustness_label = tk.Label(col2, text="Robustness: --", 
                                       font=('Arial', 9), fg='black', justify='left')
        self.robustness_label.pack(anchor='w', pady=2)
        
        # Update button frame с языком
        button_frame = ttk.Frame(status_frame)
        button_frame.pack(fill='x', pady=(10, 0))
        
        # Кнопка Update Analysis
        self.update_btn = ttk.Button(button_frame, text="🔄 Update Analysis" if self.current_language == "English" else "🔄 Обновить анализ", 
                                     command=self.update_analysis)
        self.update_btn.pack(side='left')
        
        # Метка с текущим языком (опционально)
        ttk.Label(button_frame, text=f"({self.current_language})", font=('Arial', 8)).pack(side='right', padx=(5, 0))
        
        # Recommendations - более компактно
        rec_frame = ttk.LabelFrame(parent, text="🎯 Key Recommendations" if self.current_language == "English" else "🎯 Ключевые рекомендации", padding="8")
        rec_frame.pack(fill='x', pady=(0, 10))
        
        rec_text = """• Frame Time: 150-220 ms (optimal)
• Dummy Cells: Must be positive
• FFT Size: 32K for best performance  
• Guard Interval: 1/8 for most scenarios
• Balance bitrate vs robustness"""
        
        rec_label = tk.Label(rec_frame, text=rec_text, font=('Arial', 9), 
                           justify='left', bg='#F8F9FA', wraplength=500)
        rec_label.pack(fill='x', padx=5, pady=5)
        
        # Quick Tips - более компактно
        tips_frame = ttk.LabelFrame(parent, text="💡 Quick Templates", padding="8")
        tips_frame.pack(fill='x', pady=(0, 10))
        
        tips_content = """
🚀 Max Range: QPSK 1/2 | 32K FFT | GI 1/4
⚡ Balanced: 16QAM 2/3 | 32K FFT | GI 1/8  
🏎️ High Speed: 64QAM 3/4 | 32K FFT | GI 1/16
🌆 Urban: 16QAM 3/4 | 8K FFT | GI 1/8
🚗 Mobile: QPSK 3/5 | 4K FFT | GI 1/4
"""
        tips_text = tk.Text(tips_frame, wrap=tk.WORD, font=('Courier', 8), 
                          height=6, bg='#F8F9FA', relief='flat')
        tips_text.insert('1.0', tips_content)
        tips_text.config(state='disabled')
        tips_text.pack(fill='x', padx=5, pady=5)
        
        # Validation Rules
        rules_frame = ttk.LabelFrame(parent, text="✅ Validation Rules", padding="8")
        rules_frame.pack(fill='x')
        
        rules_text = """1. Frame Time (TF) < 250 ms
2. Dummy Cells ≥ 0
3. Valid DVB-T2 parameter combination"""
        
        rules_label = tk.Label(rules_frame, text=rules_text, font=('Arial', 9),
                             justify='left', bg='#F0F8FF')
        rules_label.pack(fill='x', padx=5, pady=5)
    
    def create_right_content(self, parent):
        """Create right pane content with language support"""
        # Create notebook for detailed guides
        notebook = ttk.Notebook(parent)
        notebook.pack(fill='both', expand=True)
        
        if self.current_language == "English":
            self._create_english_tabs(notebook)
        else:
            self._create_russian_tabs(notebook)
    
    def _create_english_tabs(self, notebook):
        """Create tabs in English"""
        # Tab 1: Modulation Guide
        mod_frame = ttk.Frame(notebook, padding="10")
        notebook.add(mod_frame, text="Modulation")
        
        mod_content = """
🔸 QPSK (Quadrature Phase-Shift Keying)
   • Bits per symbol: 2
   • Required SNR: Low (6-10 dB)
   • Use case: Maximum range, weak signals
   • Best for: Rural areas, long distance

🔸 16QAM (16 Quadrature Amplitude Modulation)  
   • Bits per symbol: 4
   • Required SNR: Medium (12-16 dB)
   • Use case: Balanced performance
   • Best for: Most applications

🔸 64QAM (64 Quadrature Amplitude Modulation)
   • Bits per symbol: 6
   • Required SNR: High (18-22 dB)
   • Use case: High speed
   • Best for: Strong signal areas

🔸 256QAM+ (Higher Order Modulation)
   • Bits per symbol: 8+
   • Required SNR: Very high (24+ dB)
   • Use case: Maximum speed
   • Best for: Excellent conditions
"""
        self._add_text_to_frame(mod_frame, mod_content)
        
        # Tab 2: FFT & GI Guide
        fft_frame = ttk.Frame(notebook, padding="10")
        notebook.add(fft_frame, text="FFT & GI")
        
        fft_content = """
📏 FFT SIZE (Fast Fourier Transform)

• 1K (1024 points)
  - Best for: Mobile reception
  - Pros: Fast channel changes
  - Cons: Poor multipath resistance

• 2K-8K (2048-8192 points)  
  - Best for: Standard fixed reception
  - Pros: Good balance
  - Cons: Moderate multipath resistance

• 16K-32K (16384-32768 points)
  - Best for: Challenging environments
  - Pros: Excellent multipath resistance
  - Cons: Slower channel changes

🛡️ GUARD INTERVAL (Cyclic Prefix)

• 1/32 (3.125% overhead)
  - Protection: Minimum
  - Use: Strong signal areas
  - Max delay: ~3 μs

• 1/16 (6.25% overhead)
  - Protection: Low
  - Use: Good conditions
  - Max delay: ~6 μs

• 1/8 (12.5% overhead)
  - Protection: Good
  - Use: Most scenarios (recommended)
  - Max delay: ~12 μs

• 1/4 (25% overhead)
  - Protection: Maximum
  - Use: Challenging conditions
  - Max delay: ~25 μs
"""
        self._add_text_to_frame(fft_frame, fft_content)
        
        # Tab 3: Code Rates
        code_frame = ttk.Frame(notebook, padding="10")
        notebook.add(code_frame, text="Code Rates")
        
        code_content = """
📊 FORWARD ERROR CORRECTION (FEC)

Code Rate = Data Bits / Total Bits
(Lower rate = More protection = Lower speed)

🔸 1/2 Code Rate (50% efficiency)
   • Protection: Maximum
   • Overhead: 100%
   • Use: Weak signals, maximum range
   • Required SNR: Lowest

🔸 2/3 Code Rate (67% efficiency)  
   • Protection: High
   • Overhead: 50%
   • Use: Good balance
   • Required SNR: Low

🔸 3/4 Code Rate (75% efficiency)
   • Protection: Medium
   • Overhead: 33%
   • Use: Standard conditions
   • Required SNR: Medium

🔸 5/6 Code Rate (83% efficiency)
   • Protection: Low
   • Overhead: 20%
   • Use: Strong signals
   • Required SNR: High

🔸 7/8 Code Rate (87% efficiency)
   • Protection: Minimum
   • Overhead: 14%
   • Use: Excellent conditions
   • Required SNR: Highest

🎯 RECOMMENDED COMBINATIONS:

• Maximum Range: QPSK + 1/2 FEC
• Balanced: 16QAM + 2/3 FEC  
• High Speed: 64QAM + 3/4 FEC
• Urban: 16QAM + 3/4 FEC
• Mobile: QPSK + 2/3 FEC
"""
        self._add_text_to_frame(code_frame, code_content)
        
        # Tab 4: Frame Structure
        frame_frame = ttk.Frame(notebook, padding="10")
        notebook.add(frame_frame, text="Frame Structure")
        
        frame_content = """
⏱️ FRAME TIME (TF) OPTIMIZATION

• Maximum Limit: 250 ms (DVB-T2 standard)
• Optimal Range: 150-220 ms
• Minimum Practical: ~80 ms

📦 DATA SYMBOLS IMPACT:

More Symbols → 
  • Longer frame time
  • Better error correction  
  • Lower bitrate
  • More robust

Fewer Symbols →
  • Shorter frame time
  • Higher bitrate
  • Less robust
  • Faster channel changes

⚖️ PRACTICAL GUIDELINES:

• Urban Areas: 120-180 ms
  - More interference
  - Shorter frames better

• Rural Areas: 180-220 ms  
  - Cleaner signals
  - Longer frames OK

• Mobile Reception: 100-150 ms
  - Fast changing conditions
  - Need quick adaptation

• Fixed Reception: 150-220 ms
  - Stable conditions
  - Maximize robustness

🎯 CALCULATION TIPS:

1. Start with target Frame Time (180 ms)
2. Adjust Data Symbols to achieve it
3. Check Dummy Cells are positive
4. Verify total bitrate meets needs
5. Test different FEC combinations
"""
        self._add_text_to_frame(frame_frame, frame_content)
        
        # Tab 5: DVB-T2 Specifications
        spec_frame = ttk.Frame(notebook, padding="10")
        notebook.add(spec_frame, text="DVB-T2 Specifications")
        
        spec_content = """
🚫 DVB-T2 MANDATORY RESTRICTIONS
📚 Source: ETSI EN 302 755 (official DVB-T2 standard)
📊 Data verified against Keysight Technologies DVB-T2 X-parameters measurement guide

📊 FFT SIZE COMPATIBILITY:

• 1K FFT: 
  - NOT supported: PP6, PP7, PP8
  - Max Data Symbols: 256
  - Guard Interval: 1/4, 1/8, 1/16
  - Note: 1/32, 1/128, 19/256, 19/128 not available

• 2K FFT:
  - NOT supported: PP6, PP8  
  - Max Data Symbols: 512
  - Guard Interval: 1/4, 1/8, 1/16, 1/32
  - Note: 1/128, 19/256, 19/128 not available

• 4K FFT:
  - NOT supported: PP6, PP8
  - Max Data Symbols: 1024
  - Guard Interval: 1/4, 1/8, 1/16, 1/32
  - Note: 1/128, 19/256, 19/128 not available

• 8K FFT:
  - Supports all PP (1-8)
  - Max Data Symbols: 2048
  - Guard Interval: all (including 1/128, 19/128, 19/256)

• 16K FFT:
  - Supports all PP (1-8)
  - Max Data Symbols: 4096
  - Guard Interval: all (including 1/128, 19/128, 19/256)

• 32K FFT:
  - Supports all PP (1-8)
  - Max Data Symbols: 8192
  - Guard Interval: all (including 1/128, 19/128, 19/256)

🛡️ PILOT PATTERN RESTRICTIONS (ETSI EN 302 755 Table 39):

PP1: All FFT, all GI (except 1/128)
PP2: All FFT, GI: 1/8, 1/4, 19/128 for 8K/16K/32K
PP3: All FFT, GI: 1/8, 19/128 for 8K/16K/32K
PP4: All FFT, GI: 1/16, 1/32, 19/256
PP5: All FFT, GI: 1/16, 19/256
PP6: Only 8K/16K/32K FFT, GI: 1/32
PP7: Only 8K/16K/32K FFT, GI: 1/128
PP8: Only 8K/16K/32K FFT, GI: 1/4, 1/8, 1/16, 19/128, 19/256

✅ STANDARD COMPLIANT COMBINATIONS:

32K FFT:
• GI 1/128 → PP7
• GI 1/32 → PP4, PP6
• GI 1/16 → PP2, PP8
• GI 19/256 → PP2, PP8
• GI 1/8 → PP2, PP8
• GI 19/128 → PP2, PP8
• GI 1/4 → PP2, PP8

16K FFT:
• GI 1/128 → PP7
• GI 1/32 → PP7, PP4, PP6
• GI 1/16 → PP2, PP8, PP4, PP5
• GI 19/256 → PP2, PP8, PP4, PP5
• GI 1/8 → PP2, PP3, PP8
• GI 19/128 → PP2, PP3, PP8
• GI 1/4 → PP1, PP8

8K FFT:
• GI 1/128 → PP7
• GI 1/32 → PP7, PP4
• GI 1/16 → PP8, PP4, PP5
• GI 19/256 → PP8, PP4, PP5
• GI 1/8 → PP2, PP3, PP8
• GI 19/128 → PP2, PP3, PP8
• GI 1/4 → PP1, PP8

⚠️ CRITICAL RULES FROM STANDARD:

1. Frame Time (TF) < 250 ms (EN 302 755 Section 9.4)
2. Dummy Cells ≥ 0 (must be positive for valid configuration)
3. OBW ≤ Channel Bandwidth (occupied bandwidth must fit in channel)
4. T_G ≤ T_E (guard interval must not exceed pilot pattern capability)
"""
        self._add_text_to_frame(spec_frame, spec_content)
        
        # Tab 6: Mathematical Framework
        math_frame = ttk.Frame(notebook, padding="10")
        notebook.add(math_frame, text="DVB-T2 Math")
        
        math_content = """
🎯 DVB-T2 MATHEMATICAL FRAMEWORK

📊 BASIC FORMULAS & CONSTANTS

Elementary Period (T) - Bandwidth Dependent:
• 1.7 MHz: T = 71/131 μs ≈ 0.542 μs
• 5 MHz:  T = 7/40 μs = 0.175 μs  
• 6 MHz:  T = 7/48 μs ≈ 0.1458 μs
• 7 MHz:  T = 1/8 μs = 0.125 μs
• 8 MHz:  T = 7/64 μs ≈ 0.1094 μs
• 10 MHz: T = 7/80 μs = 0.0875 μs

Useful Symbol Duration (T_U):
T_U = N × T
where N = FFT Size (1024, 2048, 4096, 8192, 16384, 32768)

Guard Interval Duration (T_G):
T_G = T_U × GI
where GI = Guard Interval fraction

Total Symbol Duration (T_S):
T_S = T_U + T_G

Carrier Spacing (Δf):
Δf = 1 / T_U

📡 OCCUPIED BANDWIDTH CONSTRAINT

Active Carriers (K_active) by FFT Size:
FFT     Normal    Extended*
1K      853       -
2K      1705      - 
4K      3409      -
8K      6817      6913
16K     13633     13921
32K     27265     27841
*Extended mode only for 8K/16K/32K in 5-10 MHz

Occupied Bandwidth:
OBW ≈ K_active × Δf

VALIDATION: OBW ≤ Channel Bandwidth

🎪 PILOT PATTERN NYQUIST LIMIT

Pilot Patterns determine channel estimation capability:

PP   D_x  D_y  Nyquist Limit  T_E (57/64)
PP1   3    4    1/3 T_U       ~0.297 × T_U
PP2   6    2    1/6 T_U       ~0.148 × T_U  
PP3   6    4    1/6 T_U       ~0.148 × T_U
PP4   12   2    1/12 T_U      ~0.074 × T_U
PP5   12   4    1/12 T_U      ~0.074 × T_U
PP6   24   2    1/24 T_U      ~0.037 × T_U
PP7   24   4    1/24 T_U      ~0.037 × T_U
PP8   6    16   1/6 T_U       ~0.148 × T_U

CRITICAL RULE: T_G ≤ T_E
For stable SFN operation, Guard Interval must be covered by Pilot Pattern capability

🔧 PRACTICAL DESIGN ALGORITHM

1. Choose Bandwidth & FFT Size
2. Calculate OBW = K_active × Δf
3. Verify OBW ≤ Channel Bandwidth
4. Select GI based on network requirements
5. Calculate T_G = GI × T_U  
6. Find PP where T_E ≥ T_G
7. If no PP satisfies → Combination INVALID

✅ The calculator automatically validates these constraints!
"""
        self._add_text_to_frame(math_frame, math_content)
    
    def _create_russian_tabs(self, notebook):
        """Create tabs in Russian"""
        # Вкладка 1: Модуляция
        mod_frame = ttk.Frame(notebook, padding="10")
        notebook.add(mod_frame, text="Модуляция")
        
        mod_content = """
🔸 QPSK (Квадратурная фазовая манипуляция)
   • Бит на символ: 2
   • Требуемое ОСШ: Низкое (6-10 дБ)
   • Применение: Максимальная дальность, слабые сигналы
   • Лучше всего: Сельская местность, большое расстояние

🔸 16QAM (16-позиционная квадратурная амплитудная модуляция)
   • Бит на символ: 4
   • Требуемое ОСШ: Среднее (12-16 дБ)
   • Применение: Сбалансированная производительность
   • Лучше всего: Большинство применений

🔸 64QAM (64-позиционная квадратурная амплитудная модуляция)
   • Бит на символ: 6
   • Требуемое ОСШ: Высокое (18-22 дБ)
   • Применение: Высокая скорость
   • Лучше всего: Зоны с сильным сигналом

🔸 256QAM+ (Модуляция высокого порядка)
   • Бит на символ: 8+
   • Требуемое ОСШ: Очень высокое (24+ дБ)
   • Применение: Максимальная скорость
   • Лучше всего: Отличные условия приема
"""
        self._add_text_to_frame(mod_frame, mod_content)
        
        # Вкладка 2: FFT и Защитный интервал
        fft_frame = ttk.Frame(notebook, padding="10")
        notebook.add(fft_frame, text="FFT и ЗИ")
        
        fft_content = """
📏 РАЗМЕР FFT (Быстрое преобразование Фурье)

• 1K (1024 точки)
  - Лучше всего: Мобильный прием
  - Плюсы: Быстрая адаптация к изменениям канала
  - Минусы: Слабая устойчивость к многолучевости

• 2K-8K (2048-8192 точки)
  - Лучше всего: Стандартный стационарный прием
  - Плюсы: Хороший баланс
  - Минусы: Средняя устойчивость к многолучевости

• 16K-32K (16384-32768 точки)
  - Лучше всего: Сложные условия приема
  - Плюсы: Отличная устойчивость к многолучевости
  - Минусы: Медленная адаптация к изменениям канала

🛡️ ЗАЩИТНЫЙ ИНТЕРВАЛ (Циклический префикс)

• 1/32 (3.125% служебных данных)
  - Защита: Минимальная
  - Применение: Зоны с сильным сигналом
  - Макс. задержка: ~3 мкс

• 1/16 (6.25% служебных данных)
  - Защита: Низкая
  - Применение: Хорошие условия
  - Макс. задержка: ~6 мкс

• 1/8 (12.5% служебных данных)
  - Защита: Хорошая
  - Применение: Большинство сценариев (рекомендуется)
  - Макс. задержка: ~12 мкс

• 1/4 (25% служебных данных)
  - Защита: Максимальная
  - Применение: Сложные условия
  - Макс. задержка: ~25 мкс
"""
        self._add_text_to_frame(fft_frame, fft_content)
        
        # Вкладка 3: Кодовые скорости
        code_frame = ttk.Frame(notebook, padding="10")
        notebook.add(code_frame, text="Кодовые скорости")
        
        code_content = """
📊 КОРРЕКЦИЯ ОШИБОК (FEC)

Кодовая скорость = Биты данных / Всего битов
(Меньше скорость = Больше защиты = Меньше скорость передачи)

🔸 1/2 (эффективность 50%)
   • Защита: Максимальная
   • Служебные данные: 100%
   • Применение: Слабые сигналы, максимальная дальность
   • Требуемое ОСШ: Наименьшее

🔸 2/3 (эффективность 67%)
   • Защита: Высокая
   • Служебные данные: 50%
   • Применение: Хороший баланс
   • Требуемое ОСШ: Низкое

🔸 3/4 (эффективность 75%)
   • Защита: Средняя
   • Служебные данные: 33%
   • Применение: Стандартные условия
   • Требуемое ОСШ: Среднее

🔸 5/6 (эффективность 83%)
   • Защита: Низкая
   • Служебные данные: 20%
   • Применение: Сильные сигналы
   • Требуемое ОСШ: Высокое

🔸 7/8 (эффективность 87%)
   • Защита: Минимальная
   • Служебные данные: 14%
   • Применение: Отличные условия
   • Требуемое ОСШ: Наивысшее

🎯 РЕКОМЕНДУЕМЫЕ КОМБИНАЦИИ:

• Максимальная дальность: QPSK + 1/2 FEC
• Сбалансированная: 16QAM + 2/3 FEC
• Высокая скорость: 64QAM + 3/4 FEC
• Город: 16QAM + 3/4 FEC
• Мобильная: QPSK + 2/3 FEC
"""
        self._add_text_to_frame(code_frame, code_content)
        
        # Вкладка 4: Структура кадра
        frame_frame = ttk.Frame(notebook, padding="10")
        notebook.add(frame_frame, text="Структура кадра")
        
        frame_content = """
⏱️ ОПТИМИЗАЦИЯ ВРЕМЕНИ КАДРА (TF)

• Максимальный лимит: 250 мс (стандарт DVB-T2)
• Оптимальный диапазон: 150-220 мс
• Минимальный практический: ~80 мс

📦 ВЛИЯНИЕ СИМВОЛОВ ДАННЫХ:

Больше символов →
  • Дольше время кадра
  • Лучше коррекция ошибок
  • Меньше битрейт
  • Выше устойчивость

Меньше символов →
  • Короче время кадра
  • Выше битрейт
  • Меньше устойчивость
  • Быстрее адаптация к изменениям

⚖️ ПРАКТИЧЕСКИЕ РЕКОМЕНДАЦИИ:

• Городские зоны: 120-180 мс
  - Больше помех
  - Лучше короткие кадры

• Сельские зоны: 180-220 мс
  - Чище сигнал
  - Длинные кадры допустимы

• Мобильный прием: 100-150 мс
  - Быстро меняющиеся условия
  - Нужна быстрая адаптация

• Стационарный прием: 150-220 мс
  - Стабильные условия
  - Максимальная устойчивость

🎯 СОВЕТЫ ПО РАСЧЕТУ:

1. Начните с целевого времени кадра (180 мс)
2. Регулируйте символы данных для его достижения
3. Проверьте положительность Dummy Cells
4. Убедитесь, что битрейт соответствует требованиям
5. Тестируйте разные комбинации FEC
"""
        self._add_text_to_frame(frame_frame, frame_content)
        
        # Вкладка 5: Спецификации DVB-T2
        spec_frame = ttk.Frame(notebook, padding="10")
        notebook.add(spec_frame, text="Спецификации DVB-T2")
        
        spec_content = """
🚫 ОБЯЗАТЕЛЬНЫЕ ОГРАНИЧЕНИЯ DVB-T2
📚 Источник: ETSI EN 302 755 (официальный стандарт DVB-T2)
📊 Данные верифицированы по Keysight Technologies DVB-T2 X-parameters measurement guide

📊 СОВМЕСТИМОСТЬ РАЗМЕРА FFT:

• 1K FFT: 
  - НЕ поддерживает: PP6, PP7, PP8
  - Макс. символов данных: 256
  - Защитный интервал: 1/4, 1/8, 1/16
  - Примечание: 1/32, 1/128, 19/256, 19/128 недоступны

• 2K FFT:
  - НЕ поддерживает: PP6, PP8  
  - Макс. символов данных: 512
  - Защитный интервал: 1/4, 1/8, 1/16, 1/32
  - Примечание: 1/128, 19/256, 19/128 недоступны

• 4K FFT:
  - НЕ поддерживает: PP6, PP8
  - Макс. символов данных: 1024
  - Защитный интервал: 1/4, 1/8, 1/16, 1/32
  - Примечание: 1/128, 19/256, 19/128 недоступны

• 8K FFT:
  - Поддерживает все PP (1-8)
  - Макс. символов данных: 2048
  - Защитный интервал: все (включая 1/128, 19/128, 19/256)

• 16K FFT:
  - Поддерживает все PP (1-8)
  - Макс. символов данных: 4096
  - Защитный интервал: все (включая 1/128, 19/128, 19/256)

• 32K FFT:
  - Поддерживает все PP (1-8)
  - Макс. символов данных: 8192
  - Защитный интервал: все (включая 1/128, 19/128, 19/256)

🛡️ ОГРАНИЧЕНИЯ ПИЛОТ-СИГНАЛОВ (ETSI EN 302 755 Таблица 39):

PP1: Все FFT, все ЗИ (кроме 1/128)
PP2: Все FFT, ЗИ: 1/8, 1/4, 19/128 для 8K/16K/32K
PP3: Все FFT, ЗИ: 1/8, 19/128 для 8K/16K/32K
PP4: Все FFT, ЗИ: 1/16, 1/32, 19/256
PP5: Все FFT, ЗИ: 1/16, 19/256
PP6: Только 8K/16K/32K FFT, ЗИ: 1/32
PP7: Только 8K/16K/32K FFT, ЗИ: 1/128
PP8: Только 8K/16K/32K FFT, ЗИ: 1/4, 1/8, 1/16, 19/128, 19/256

✅ СООТВЕТСТВУЮЩИЕ СТАНДАРТУ КОМБИНАЦИИ:

32K FFT:
• ЗИ 1/128 → PP7
• ЗИ 1/32 → PP4, PP6
• ЗИ 1/16 → PP2, PP8
• ЗИ 19/256 → PP2, PP8
• ЗИ 1/8 → PP2, PP8
• ЗИ 19/128 → PP2, PP8
• ЗИ 1/4 → PP2, PP8

16K FFT:
• ЗИ 1/128 → PP7
• ЗИ 1/32 → PP7, PP4, PP6
• ЗИ 1/16 → PP2, PP8, PP4, PP5
• ЗИ 19/256 → PP2, PP8, PP4, PP5
• ЗИ 1/8 → PP2, PP3, PP8
• ЗИ 19/128 → PP2, PP3, PP8
• ЗИ 1/4 → PP1, PP8

8K FFT:
• ЗИ 1/128 → PP7
• ЗИ 1/32 → PP7, PP4
• ЗИ 1/16 → PP8, PP4, PP5
• ЗИ 19/256 → PP8, PP4, PP5
• ЗИ 1/8 → PP2, PP3, PP8
• ЗИ 19/128 → PP2, PP3, PP8
• ЗИ 1/4 → PP1, PP8

⚠️ КРИТИЧЕСКИЕ ПРАВИЛА ИЗ СТАНДАРТА:

1. Время кадра (TF) < 250 мс (EN 302 755 Раздел 9.4)
2. Dummy Cells ≥ 0 (должны быть положительными для валидной конфигурации)
3. OBW ≤ Полоса канала (занимаемая полоса не должна превышать полосу канала)
4. T_G ≤ T_E (защитный интервал не должен превышать возможности пилот-сигналов)
"""
        self._add_text_to_frame(spec_frame, spec_content)
        
        # Вкладка 6: Математика DVB-T2
        math_frame = ttk.Frame(notebook, padding="10")
        notebook.add(math_frame, text="Математика DVB-T2")
        
        math_content = """
🎯 МАТЕМАТИЧЕСКАЯ МОДЕЛЬ DVB-T2

📊 БАЗОВЫЕ ФОРМУЛЫ И КОНСТАНТЫ

Элементарный период (T) - зависит от полосы:
• 1.7 МГц: T = 71/131 мкс ≈ 0.542 мкс
• 5 МГц:  T = 7/40 мкс = 0.175 мкс
• 6 МГц:  T = 7/48 мкс ≈ 0.1458 мкс
• 7 МГц:  T = 1/8 мкс = 0.125 мкс
• 8 МГц:  T = 7/64 мкс ≈ 0.1094 мкс
• 10 МГц: T = 7/80 мкс = 0.0875 мкс

Длительность полезного символа (T_U):
T_U = N × T
где N = размер FFT (1024, 2048, 4096, 8192, 16384, 32768)

Длительность защитного интервала (T_G):
T_G = T_U × ЗИ
где ЗИ = дробь защитного интервала

Полная длительность символа (T_S):
T_S = T_U + T_G

Шаг несущих (Δf):
Δf = 1 / T_U

📡 ОГРАНИЧЕНИЕ ЗАНИМАЕМОЙ ПОЛОСЫ

Активные несущие (K_active) по размеру FFT:
FFT     Обычный    Расширенный*
1K      853        -
2K      1705       - 
4K      3409       -
8K      6817       6913
16K     13633      13921
32K     27265      27841
*Расширенный режим только для 8K/16K/32K в полосах 5-10 МГц

Занимаемая полоса:
OBW ≈ K_active × Δf

ПРОВЕРКА: OBW ≤ Полоса канала

🎪 ОГРАНИЧЕНИЕ ПИЛОТ-СИГНАЛОВ ПО НАЙКВИСТУ

Пилот-сигналы определяют возможность оценки канала:

PP   D_x  D_y  Предел Найквиста  T_E (57/64)
PP1   3    4    1/3 T_U           ~0.297 × T_U
PP2   6    2    1/6 T_U           ~0.148 × T_U
PP3   6    4    1/6 T_U           ~0.148 × T_U
PP4   12   2    1/12 T_U          ~0.074 × T_U
PP5   12   4    1/12 T_U          ~0.074 × T_U
PP6   24   2    1/24 T_U          ~0.037 × T_U
PP7   24   4    1/24 T_U          ~0.037 × T_U
PP8   6    16   1/6 T_U           ~0.148 × T_U

КРИТИЧЕСКОЕ ПРАВИЛО: T_G ≤ T_E
Для стабильной работы SFN защитный интервал должен покрываться возможностями пилот-сигналов

🔧 ПРАКТИЧЕСКИЙ АЛГОРИТМ ПРОЕКТИРОВАНИЯ

1. Выберите полосу и размер FFT
2. Рассчитайте OBW = K_active × Δf
3. Проверьте OBW ≤ Полоса канала
4. Выберите ЗИ исходя из требований сети
5. Рассчитайте T_G = ЗИ × T_U
6. Найдите PP где T_E ≥ T_G
7. Если PP не найдено → Комбинация НЕДЕЙСТВИТЕЛЬНА

✅ Калькулятор автоматически проверяет эти ограничения!
"""
        self._add_text_to_frame(math_frame, math_content)
    
    def _add_text_to_frame(self, frame, content):
        """Helper method to add text widget to frame"""
        text_widget = tk.Text(frame, wrap=tk.WORD, font=('Courier' if 'Math' in content[:50] else 'Arial', 8), 
                             height=25, bg='white', fg='black')
        text_widget.insert('1.0', content)
        text_widget.config(state='disabled')
        text_widget.pack(fill='both', expand=True)
        
    def update_analysis(self):
        """Update analysis based on current calculator state"""
        try:
            if not hasattr(self.parent.calculator, 'calculation_results'):
                return
                
            results = self.parent.calculator.calculation_results
            if not results:
                return
            
            # Frame Time analysis
            frame_time = results.get('frame_time_ms', 0)
            if frame_time > 0:
                if frame_time > 250:
                    text = "❌ Frame Time: {:.1f} ms (EXCEEDS LIMIT!)" if self.current_language == "English" else "❌ Время кадра: {:.1f} мс (ПРЕВЫШАЕТ ЛИМИТ!)"
                    self.tf_label.config(text=text.format(frame_time), fg='red')
                elif frame_time >= 200:
                    text = "✅ Frame Time: {:.1f} ms (Good)" if self.current_language == "English" else "✅ Время кадра: {:.1f} мс (Хорошо)"
                    self.tf_label.config(text=text.format(frame_time), fg='green')
                elif frame_time >= 150:
                    text = "⚠️ Frame Time: {:.1f} ms (Optimal)" if self.current_language == "English" else "⚠️ Время кадра: {:.1f} мс (Оптимально)"
                    self.tf_label.config(text=text.format(frame_time), fg='orange')
                elif frame_time >= 100:
                    text = "⚠️ Frame Time: {:.1f} ms (Short)" if self.current_language == "English" else "⚠️ Время кадра: {:.1f} мс (Короткое)"
                    self.tf_label.config(text=text.format(frame_time), fg='orange')
                else:
                    text = "❌ Frame Time: {:.1f} ms (Too Short)" if self.current_language == "English" else "❌ Время кадра: {:.1f} мс (Слишком короткое)"
                    self.tf_label.config(text=text.format(frame_time), fg='red')
            
            # Dummy cells analysis
            dummy_cells = results.get('dummy_cells', 0)
            if dummy_cells >= 0:
                text = "✅ Dummy Cells: {:,} (Valid)" if self.current_language == "English" else "✅ Фиктивные ячейки: {:,} (Допустимо)"
                self.dummy_label.config(text=text.format(dummy_cells), fg='green')
            else:
                text = "❌ Dummy Cells: {:,} (INVALID!)" if self.current_language == "English" else "❌ Фиктивные ячейки: {:,} (НЕДОПУСТИМО!)"
                self.dummy_label.config(text=text.format(dummy_cells), fg='red')
            
            # Efficiency analysis
            bitrate = results.get('bitrate_normal', 0)
            if self.current_language == "English":
                if bitrate > 2000000:
                    self.efficiency_label.config(text=f"📈 Efficiency: High ({bitrate/1000000:.1f} Mbps)")
                elif bitrate > 1000000:
                    self.efficiency_label.config(text=f"⚖️ Efficiency: Medium ({bitrate/1000000:.1f} Mbps)")
                else:
                    self.efficiency_label.config(text=f"📉 Efficiency: Low ({bitrate/1000000:.1f} Mbps)")
            else:
                if bitrate > 2000000:
                    self.efficiency_label.config(text=f"📈 Эффективность: Высокая ({bitrate/1000000:.1f} Мбит/с)")
                elif bitrate > 1000000:
                    self.efficiency_label.config(text=f"⚖️ Эффективность: Средняя ({bitrate/1000000:.1f} Мбит/с)")
                else:
                    self.efficiency_label.config(text=f"📉 Эффективность: Низкая ({bitrate/1000000:.1f} Мбит/с)")
            
            # Robustness analysis based on modulation
            modulation = self.parent.calculator.modulation_var.get()
            code_rate = self.parent.calculator.code_rate_var.get()
            
            if self.current_language == "English":
                if modulation == "QPSK" and code_rate in ["1/2", "3/5"]:
                    self.robustness_label.config(text="🛡️ Robustness: Maximum")
                elif modulation == "QPSK" or (modulation == "16QAM" and code_rate in ["1/2", "2/3"]):
                    self.robustness_label.config(text="🛡️ Robustness: High")
                elif modulation == "16QAM" or modulation == "64QAM":
                    self.robustness_label.config(text="🛡️ Robustness: Medium")
                else:
                    self.robustness_label.config(text="🛡️ Robustness: Low")
            else:
                if modulation == "QPSK" and code_rate in ["1/2", "3/5"]:
                    self.robustness_label.config(text="🛡️ Устойчивость: Максимальная")
                elif modulation == "QPSK" or (modulation == "16QAM" and code_rate in ["1/2", "2/3"]):
                    self.robustness_label.config(text="🛡️ Устойчивость: Высокая")
                elif modulation == "16QAM" or modulation == "64QAM":
                    self.robustness_label.config(text="🛡️ Устойчивость: Средняя")
                else:
                    self.robustness_label.config(text="🛡️ Устойчивость: Низкая")
                
        except Exception as e:
            print(f"Error updating analysis: {e}")        

# =============================================================================
# DVBTCalculatorTab - Calculator functionality
# =============================================================================

class DVBTCalculatorTab:
    def __init__(self, parent):
        self.parent = parent
        self.setup_calculator_variables()
        self.setup_calculator_ui_variables()

    def setup_calculator_ui_variables(self):
        """Initialize calculator UI variables"""
        # Создаем переменные для UI до создания интерфейса
        self.bandwidth_var = tk.StringVar(value="1.7 MHz")
        self.fft_size_var = tk.StringVar(value="1K")
        self.gi_var = tk.StringVar(value="1/4")
        self.data_symbols_var = tk.StringVar(value="342")
        self.fec_blocks_var = tk.StringVar(value="8")
        self.code_rate_var = tk.StringVar(value="1/2")
        self.modulation_var = tk.StringVar(value="QPSK")
        self.frame_size_var = tk.StringVar(value="Normal")
        self.carrier_mode_var = tk.StringVar(value="Normal")
        self.pilot_pattern_var = tk.StringVar(value="PP2")
        self.l1_modulation_var = tk.StringVar(value="QPSK")

        # Теперь можно настроить авто-калькуляцию
        self.setup_auto_calculation()

    def setup_auto_calculation(self):
        """Setup automatic calculation when parameters change"""
        self.auto_calculate = True  # Флаг для предотвращения рекурсии

        # Список переменных для отслеживания изменений
        self.calc_vars = [
            self.bandwidth_var, self.fft_size_var, self.gi_var,
            self.data_symbols_var, self.fec_blocks_var, self.code_rate_var,
            self.modulation_var, self.frame_size_var, self.carrier_mode_var,
            self.pilot_pattern_var, self.l1_modulation_var
        ]

        # Назначаем обработчики изменений
        for var in self.calc_vars:
            var.trace_add('write', self.on_parameter_change)

    def on_parameter_change(self, *args):
        """Handle parameter changes and trigger automatic calculation"""
        if self.auto_calculate:
            # Задержка для предотвращения множественных вызовов при быстром изменении
            if hasattr(self, '_calc_timer'):
                self.parent.root.after_cancel(self._calc_timer)
            self._calc_timer = self.parent.root.after(500, self.calculate)

    def sync_with_current_preset(self):
        """Sync calculator parameters with currently selected preset in main GUI"""
        try:
            current_preset = self.parent.modulator_preset.get()
            if current_preset and current_preset in self.parent.modulator_presets:
                success = self.load_preset_parameters(current_preset)
                if success:
                    # Автоматически пересчитываем
                    self.calculate()
                    self.parent.log_message(f"✅ Calculator synced with preset: {current_preset}", "buffer")
                else:
                    self.parent.log_message(f"⚠️ Calculator sync failed for: {current_preset}", "buffer")
            else:
                self.parent.log_message("❌ No preset selected for calculator sync", "buffer")
        except Exception as e:
            self.parent.log_message(f"❌ Error syncing calculator with preset: {e}", "buffer")        
       
    def load_preset_parameters(self, preset_name):
        """Load parameters from selected preset into calculator from JSON file"""
        try:
            if not preset_name or preset_name not in self.parent.modulator_presets:
                self.parent.log_message(f"❌ Preset '{preset_name}' not found", "buffer")
                return False
            
            self.parent.log_message(f"🔄 Loading preset parameters: {preset_name}", "buffer")
            
            preset_info = self.parent.modulator_presets[preset_name]
            
            # Пытаемся загрузить из JSON
            json_file = preset_info.get('json_file')
            if json_file and os.path.exists(json_file):
                try:
                    with open(json_file, 'r', encoding='utf-8') as f:
                        scheme_data = json.load(f)
                    
                    if 'parameters' in scheme_data:
                        params = scheme_data['parameters']
                        
                        # Устанавливаем параметры из JSON в калькулятор
                        self.set_calculator_parameters(params)
                        self.parent.log_message(f"✅ Parameters loaded from JSON for: {preset_name}", "buffer")
                        return True
                        
                except Exception as e:
                    self.parent.log_message(f"❌ Error loading JSON for {preset_name}: {e}", "buffer")
                    # Покажем подробности ошибки
                    import traceback
                    self.parent.log_message(f"❌ Traceback: {traceback.format_exc()}", "buffer")
            
            # Если JSON не загрузился, парсим из имени файла (старый метод)
            self.parent.log_message(f"ℹ️ Falling back to filename parsing for: {preset_name}", "buffer")
            self.load_preset_parameters_from_filename(preset_name)
            return False
            
        except Exception as e:
            self.parent.log_message(f"❌ Error loading preset parameters: {e}", "buffer")
            import traceback
            self.parent.log_message(f"❌ Traceback: {traceback.format_exc()}", "buffer")
            return False

    def load_preset_parameters_from_filename(self, preset_name):
        """Load parameters from preset filename (fallback method)"""
        try:
            # Простая логика парсинга имени файла
            parts = preset_name.split('_')
            
            # Пытаемся извлечь параметры из имени файла
            for part in parts:
                if part in self.BANDWIDTH:
                    self.bandwidth_var.set(part)
                elif part in self.FFT_SIZE:
                    self.fft_size_var.set(part)
                elif part in self.MODULATION:
                    self.modulation_var.set(part)
                elif '/' in part:
                    self.code_rate_var.set(part)
            
            self.parent.log_message(f"ℹ️ Parameters loaded from filename for: {preset_name}", "buffer")
            
        except Exception as e:
            self.parent.log_message(f"❌ Error loading parameters from filename: {e}", "buffer")

    def create_calculator_tab(self, parent):
        """Create calculator tab interface"""
        calculator_frame = ttk.Frame(parent, padding="8")
        
        # Main layout with left parameters and right results
        main_paned = ttk.PanedWindow(calculator_frame, orient=tk.HORIZONTAL)
        main_paned.pack(fill='both', expand=True, pady=5)
        
        # Left frame - parameters
        left_frame = ttk.Frame(main_paned, padding="5")
        main_paned.add(left_frame, weight=1)
        
        # Right frame - results
        right_frame = ttk.Frame(main_paned, padding="5")
        main_paned.add(right_frame, weight=2)
        
        # Parameters frame
        params_frame = ttk.LabelFrame(left_frame, text="DVB-T2 Parameters", padding="5")
        params_frame.pack(fill='both', expand=True, pady=(0, 5))
        
        # Bandwidth - используем уже созданные переменные
        ttk.Label(params_frame, text="Channel Bandwidth:").grid(row=0, column=0, sticky=tk.W, pady=1)
        self.bandwidth_combo = ttk.Combobox(params_frame, textvariable=self.bandwidth_var, 
                                           values=list(self.BANDWIDTH.keys()), state="readonly", width=15)
        self.bandwidth_combo.grid(row=0, column=1, sticky=(tk.W, tk.E), pady=1, padx=(5,0))
        
        # FFT Size
        ttk.Label(params_frame, text="FFT Size:").grid(row=1, column=0, sticky=tk.W, pady=1)
        self.fft_size_combo = ttk.Combobox(params_frame, textvariable=self.fft_size_var, 
                                          values=list(self.FFT_SIZE.keys()), state="readonly", width=15)
        self.fft_size_combo.grid(row=1, column=1, sticky=(tk.W, tk.E), pady=1, padx=(5,0))
        self.fft_size_combo.bind('<<ComboboxSelected>>', self.on_fft_size_change)
        
        # Guard Interval
        ttk.Label(params_frame, text="Guard Interval:").grid(row=2, column=0, sticky=tk.W, pady=1)
        self.gi_combo = ttk.Combobox(params_frame, textvariable=self.gi_var, 
                                    values=list(self.GUARD_INTERVAL.keys()), state="readonly", width=15)
        self.gi_combo.grid(row=2, column=1, sticky=(tk.W, tk.E), pady=1, padx=(5,0))
        self.gi_combo.bind('<<ComboboxSelected>>', self.on_gi_change)
        
        # Data Symbols - ЗАМЕНА НА COMBOBOX
        ttk.Label(params_frame, text="Data Symbols:").grid(row=3, column=0, sticky=tk.W, pady=1)
        self.data_symbols_combo = ttk.Combobox(params_frame, textvariable=self.data_symbols_var, 
                                              width=18, state="normal")
        self.data_symbols_combo.grid(row=3, column=1, sticky=(tk.W, tk.E), pady=1, padx=(5,0))
        # Устанавливаем начальные значения
        self.data_symbols_combo['values'] = list(range(1, 1000))
        
        # FEC Blocks - ЗАМЕНА НА COMBOBOX
        ttk.Label(params_frame, text="FEC Blocks:").grid(row=4, column=0, sticky=tk.W, pady=1)
        self.fec_blocks_combo = ttk.Combobox(params_frame, textvariable=self.fec_blocks_var, 
                                            width=18, state="normal")
        self.fec_blocks_combo.grid(row=4, column=1, sticky=(tk.W, tk.E), pady=1, padx=(5,0))
        # Устанавливаем начальные значения
        self.fec_blocks_combo['values'] = [str(x) for x in range(1, 169)]
        
        # Code Rate
        ttk.Label(params_frame, text="Code Rate:").grid(row=5, column=0, sticky=tk.W, pady=1)
        self.code_rate_combo = ttk.Combobox(params_frame, textvariable=self.code_rate_var, 
                                           values=list(self.CODE_RATES.keys()), state="readonly", width=15)
        self.code_rate_combo.grid(row=5, column=1, sticky=(tk.W, tk.E), pady=1, padx=(5,0))
        
        # Modulation
        ttk.Label(params_frame, text="Modulation:").grid(row=6, column=0, sticky=tk.W, pady=1)
        self.modulation_combo = ttk.Combobox(params_frame, textvariable=self.modulation_var, 
                                            values=list(self.MODULATION.keys()), state="readonly", width=15)
        self.modulation_combo.grid(row=6, column=1, sticky=(tk.W, tk.E), pady=1, padx=(5,0))
        
        # Frame Size
        ttk.Label(params_frame, text="Frame Size:").grid(row=7, column=0, sticky=tk.W, pady=1)
        self.frame_size_combo = ttk.Combobox(params_frame, textvariable=self.frame_size_var, 
                                            values=list(self.FRAME_SIZE.keys()), state="readonly", width=15)
        self.frame_size_combo.grid(row=7, column=1, sticky=(tk.W, tk.E), pady=1, padx=(5,0))
        
        # Carrier Mode
        ttk.Label(params_frame, text="Carrier Mode:").grid(row=8, column=0, sticky=tk.W, pady=1)
        self.carrier_mode_combo = ttk.Combobox(params_frame, textvariable=self.carrier_mode_var, 
                                              values=list(self.CARRIER_MODE.keys()), state="readonly", width=15)
        self.carrier_mode_combo.grid(row=8, column=1, sticky=(tk.W, tk.E), pady=1, padx=(5,0))
        
        # Pilot Pattern - ДОБАВЛЯЕМ ОГРАНИЧЕНИЯ ВЫБОРА
        ttk.Label(params_frame, text="Pilot Pattern:").grid(row=9, column=0, sticky=tk.W, pady=1)
        self.pilot_pattern_combo = ttk.Combobox(params_frame, textvariable=self.pilot_pattern_var, 
                                               values=list(self.PILOT_PATTERNS.keys()), state="readonly", width=15)
        self.pilot_pattern_combo.grid(row=9, column=1, sticky=(tk.W, tk.E), pady=1, padx=(5,0))
        
        # L1 Modulation
        ttk.Label(params_frame, text="L1 Modulation:").grid(row=10, column=0, sticky=tk.W, pady=1)
        self.l1_modulation_combo = ttk.Combobox(params_frame, textvariable=self.l1_modulation_var, 
                                               values=list(self.L1_MODULATION.keys()), state="readonly", width=15)
        self.l1_modulation_combo.grid(row=10, column=1, sticky=(tk.W, tk.E), pady=1, padx=(5,0))
        
        # Кнопка T2 INFO
        ttk.Button(params_frame, text="📚 T2 Info", 
                  command=self.show_tips_window, width=12).grid(row=11, column=0, columnspan=2, pady=(10, 5))
        
        # DVB-T2 Standard Compliance Status Display
        self.compliance_label = ttk.Label(params_frame, text="Select parameters...", 
                                         font=('Arial', 9), foreground='blue')
        self.compliance_label.grid(row=12, column=0, columnspan=2, pady=(5, 5), sticky='w')
        
        # Add trace callbacks to update limits when parameters change
        self.bandwidth_var.trace_add('write', lambda *args: self.update_parameter_limits_based_on_standard())
        self.fft_size_var.trace_add('write', lambda *args: self.update_parameter_limits_based_on_standard())
        self.gi_var.trace_add('write', lambda *args: self.update_parameter_limits_based_on_standard())
        
        # Rules frame
        rules_frame = ttk.LabelFrame(left_frame, text="DVB-T2 Validation Rules", padding="5")
        rules_frame.pack(fill='x', pady=(5, 0))

        header_label = ttk.Label(rules_frame, text="Note that a valid configuration must fulfill two rules:",
                                font=('Arial', 7), justify=tk.LEFT)
        header_label.pack(fill='x', pady=(0, 5))

        rule1_label = ttk.Label(rules_frame, text="• TF must be less than 250 milliseconds",
                               font=('Arial', 9), justify=tk.LEFT)
        rule1_label.pack(fill='x')

        rule2_label = ttk.Label(rules_frame, text="• dummy cells must be positive",
                               font=('Arial', 9), justify=tk.LEFT)
        rule2_label.pack(fill='x')
        
        # Buttons frame
        buttons_frame = ttk.Frame(left_frame)
        buttons_frame.pack(fill='x', pady=(8, 0))
        
        self.calculate_btn = ttk.Button(buttons_frame, text="Calculate", command=self.calculate, width=12)
        self.calculate_btn.pack(side='top', pady=2)
        
        self.sync_btn = ttk.Button(buttons_frame, text="Sync with Preset", 
                                  command=self.sync_with_current_preset, width=12)
        self.sync_btn.pack(side='top', pady=2)
        
        self.save_preset_btn = ttk.Button(buttons_frame, text="Save Preset", command=self.save_preset, width=12)
        self.save_preset_btn.pack(side='top', pady=2)
        
        # Results frame
        results_frame = ttk.LabelFrame(right_frame, text="Calculation Results", padding="5")
        results_frame.pack(fill='both', expand=True)
        
        self.results_text = tk.Text(results_frame, height=20, width=60, font=('Courier', 9))
        self.results_text.pack(fill='both', expand=True)
        
        scrollbar = ttk.Scrollbar(results_frame, orient="vertical", command=self.results_text.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.results_text.configure(yscrollcommand=scrollbar.set)
        
        # Configure grid weights
        params_frame.columnconfigure(1, weight=1)
        calculator_frame.columnconfigure(0, weight=1)
        calculator_frame.rowconfigure(0, weight=1)
        
        # Initialize parameter limits based on standard
        self.parent.root.after(500, self.update_parameter_limits_based_on_standard)
        
        return calculator_frame

    def show_tips_window(self):
        """Show DVB-T2 tips window from parent"""
        try:
            if hasattr(self.parent, 'show_tips_window'):
                self.parent.show_tips_window()
            else:
                # Fallback: создаем окно напрямую
                if not hasattr(self, 'tips_window') or self.tips_window is None:
                    self.tips_window = DVBTTipsWindow(self.parent)
                self.tips_window.show()
                self.tips_window.update_analysis()
        except Exception as e:
            print(f"Error showing tips window: {e}")
            messagebox.showerror("Error", f"Could not open tips window: {e}")

    def set_calculator_parameters(self, params):
        """Set calculator parameters from dictionary"""
        try:
            # Bandwidth
            if 'channel_bandwidth' in params and params['channel_bandwidth'] in self.BANDWIDTH:
                self.bandwidth_var.set(params['channel_bandwidth'])
            
            # FFT Size
            if 'fft_size' in params and params['fft_size'] in self.FFT_SIZE:
                self.fft_size_var.set(params['fft_size'])
            
            # Guard Interval
            if 'guard_interval' in params and params['guard_interval'] in self.GUARD_INTERVAL:
                self.gi_var.set(params['guard_interval'])
            
            # Data Symbols - преобразуем в int
            if 'data_symbols' in params:
                data_symbols = params['data_symbols']
                if isinstance(data_symbols, float):
                    data_symbols = int(data_symbols)
                self.data_symbols_var.set(str(data_symbols))
            
            # FEC Blocks - преобразуем в int (исправление ошибки)
            if 'fec_blocks' in params:
                fec_blocks = params['fec_blocks']
                if isinstance(fec_blocks, float):
                    fec_blocks = int(fec_blocks)
                self.fec_blocks_var.set(str(fec_blocks))
            
            # Code Rate
            if 'code_rate' in params and params['code_rate'] in self.CODE_RATES:
                self.code_rate_var.set(params['code_rate'])
            
            # Modulation
            if 'modulation' in params and params['modulation'] in self.MODULATION:
                self.modulation_var.set(params['modulation'])
            
            # Frame Size
            if 'frame_size' in params and params['frame_size'] in self.FRAME_SIZE:
                self.frame_size_var.set(params['frame_size'])
            
            # Carrier Mode
            if 'carrier_mode' in params and params['carrier_mode'] in self.CARRIER_MODE:
                self.carrier_mode_var.set(params['carrier_mode'])
            
            # Pilot Pattern
            if 'pilot_pattern' in params and params['pilot_pattern'] in self.PILOT_PATTERNS:
                self.pilot_pattern_var.set(params['pilot_pattern'])
            
            # L1 Modulation
            if 'l1_modulation' in params and params['l1_modulation'] in self.L1_MODULATION:
                self.l1_modulation_var.set(params['l1_modulation'])
                
            self.parent.log_message("✅ Calculator parameters updated from preset", "buffer")
            
        except Exception as e:
            self.parent.log_message(f"❌ Error setting calculator parameters: {e}", "buffer")       
        
    def setup_calculator_variables(self):
        """Initialize calculator variables"""
        # Define constants
        self.CODE_RATES = {
            "1/2": 1, "3/5": 2, "2/3": 3, "3/4": 4, 
            "4/5": 5, "5/6": 6, "1/3": 7, "2/5": 8
        }
        
        self.MODULATION = {
            "QPSK": 1, "16QAM": 2, "64QAM": 3, 
            "256QAM": 4
        }
        
        self.L1_MODULATION = {
            "BPSK": 0, "QPSK": 1, "16QAM": 2, "64QAM": 3
        }
        
        self.FRAME_SIZE = {"Normal": 0, "Short": 1}
        self.CARRIER_MODE = {"Normal": 0, "Extended": 1}
        
        self.GUARD_INTERVAL = {
            "1/32": 0, "1/16": 1, "1/8": 2, "1/4": 3,
            "1/128": 4, "19/128": 5, "19/256": 6
        }
        
        self.FFT_SIZE = {"1K": 1, "2K": 2, "4K": 4, "8K": 8, "16K": 16, "32K": 32}
        
        self.PILOT_PATTERNS = {
            "PP1": 1, "PP2": 2, "PP3": 3, "PP4": 4,
            "PP5": 5, "PP6": 6, "PP7": 7, "PP8": 8
        }
        
        self.BANDWIDTH = {"1.7 MHz": 0, "5 MHz": 5, "6 MHz": 6, "7 MHz": 7, "8 MHz": 8, "10 MHz": 10}
        
        # DVB-T2 Standard Compliance Tables based on ETSI EN 302 755
        # Source: Keysight Technologies - DVB-T2 X-parameters measurement guide
        # All combinations verified against official standard
        self.DVB_T2_STANDARD_COMBINATIONS = {
            # Format: {fft_size: {gi: [allowed_pp]}}
            "32K": {
                "1/128": ["PP7"],
                "1/32": ["PP4", "PP6"],
                "1/16": ["PP2", "PP8"],
                "19/256": ["PP2", "PP8"],
                "1/8": ["PP2", "PP8"],
                "19/128": ["PP2", "PP8"],
                "1/4": ["PP2", "PP8"]
            },
            "16K": {
                "1/128": ["PP7"],
                "1/32": ["PP7", "PP4", "PP6"],
                "1/16": ["PP2", "PP8", "PP4", "PP5"],
                "19/256": ["PP2", "PP8", "PP4", "PP5"],
                "1/8": ["PP2", "PP3", "PP8"],
                "19/128": ["PP2", "PP3", "PP8"],
                "1/4": ["PP1", "PP8"]
            },
            "8K": {
                "1/128": ["PP7"],
                "1/32": ["PP7", "PP4"],
                "1/16": ["PP8", "PP4", "PP5"],
                "19/256": ["PP8", "PP4", "PP5"],
                "1/8": ["PP2", "PP3", "PP8"],
                "19/128": ["PP2", "PP3", "PP8"],
                "1/4": ["PP1", "PP8"]
            },
            "4K": {
                "1/32": ["PP7", "PP4"],
                "1/16": ["PP4", "PP5"],
                "1/8": ["PP2", "PP3"],
                "1/4": ["PP1"]
                # Note: 1/128, 19/256, 19/128 not available for 4K
            },
            "2K": {
                "1/32": ["PP7", "PP4"],
                "1/16": ["PP4", "PP5"],
                "1/8": ["PP2", "PP3"],
                "1/4": ["PP1"]
                # Note: 1/128, 19/256, 19/128 not available for 2K
            },
            "1K": {
                "1/16": ["PP4", "PP5"],
                "1/8": ["PP2", "PP3"],
                "1/4": ["PP1"]
                # Note: 1/32, 1/128, 19/256, 19/128 not available for 1K
            }
        }

        # Bandwidth limitations
        self.BANDWIDTH_LIMITATIONS = {
            "1.7 MHz": {
                "allowed_fft": ["1K", "2K", "4K", "8K"],
                "carrier_mode": ["Normal"]
            },
            "5 MHz": {
                "allowed_fft": ["1K", "2K", "4K", "8K", "16K", "32K"],
                "carrier_mode": ["Normal", "Extended"]
            },
            "6 MHz": {
                "allowed_fft": ["1K", "2K", "4K", "8K", "16K", "32K"],
                "carrier_mode": ["Normal", "Extended"]
            },
            "7 MHz": {
                "allowed_fft": ["1K", "2K", "4K", "8K", "16K", "32K"],
                "carrier_mode": ["Normal", "Extended"]
            },
            "8 MHz": {
                "allowed_fft": ["1K", "2K", "4K", "8K", "16K", "32K"],
                "carrier_mode": ["Normal", "Extended"]
            },
            "10 MHz": {
                "allowed_fft": ["1K", "2K", "4K", "8K", "16K", "32K"],
                "carrier_mode": ["Normal", "Extended"]
            }
        }
        
        # GNU Radio constants mapping
        self.GR_CONSTELLATION = {
            "QPSK": "dtv.MOD_QPSK", "16QAM": "dtv.MOD_16QAM", "64QAM": "dtv.MOD_64QAM",
            "256QAM": "dtv.MOD_256QAM"
        }

        # GNU Radio constants mapping (дополнить существующие)
        self.GR_CODE_RATE = {
            "1/2": "dtv.C1_2", "3/5": "dtv.C3_5", "2/3": "dtv.C2_3", "3/4": "dtv.C3_4",
            "4/5": "dtv.C4_5", "5/6": "dtv.C5_6", "1/3": "dtv.C1_3", "2/5": "dtv.C2_5"
        }

        self.GR_GUARD_INTERVAL = {
            "1/32": "dtv.GI_1_32", "1/16": "dtv.GI_1_16", "1/8": "dtv.GI_1_8", 
            "1/4": "dtv.GI_1_4", "1/128": "dtv.GI_1_128", "19/128": "dtv.GI_19_128", 
            "19/256": "dtv.GI_19_256"
        }

        self.GR_FFT_SIZE = {
            "1K": "dtv.FFTSIZE_1K", "2K": "dtv.FFTSIZE_2K", "4K": "dtv.FFTSIZE_4K",
            "8K": "dtv.FFTSIZE_8K", "16K": "dtv.FFTSIZE_16K", "32K": "dtv.FFTSIZE_32K"
        }

        self.GR_PILOT_PATTERN = {
            "PP1": "dtv.PILOT_PP1", "PP2": "dtv.PILOT_PP2", "PP3": "dtv.PILOT_PP3",
            "PP4": "dtv.PILOT_PP4", "PP5": "dtv.PILOT_PP5", "PP6": "dtv.PILOT_PP6",
            "PP7": "dtv.PILOT_PP7", "PP8": "dtv.PILOT_PP8"
        }

        self.GR_CARRIER_MODE = {
            "Normal": "dtv.CARRIERS_NORMAL", "Extended": "dtv.CARRIERS_EXTENDED"
        }

        self.GR_FRAME_SIZE = {
            "Normal": "dtv.FECFRAME_NORMAL", "Short": "dtv.FECFRAME_SHORT"
        }

        self.GR_L1_MODULATION = {
            "BPSK": "dtv.L1_MOD_BPSK", "QPSK": "dtv.L1_MOD_QPSK", 
            "16QAM": "dtv.L1_MOD_16QAM", "64QAM": "dtv.L1_MOD_64QAM"
        }        
        
        # Store calculation results
        self.calculation_results = {}
        
        # Create directories if they don't exist
        self.create_directories()
        
    def create_directories(self):
        """Create necessary directories for saving schemes"""
        base_dir = os.path.dirname(os.path.abspath(__file__))
        self.modulator_presets_dir = os.path.join(base_dir, "gnu_modulator_presets")
        self.saved_schemes_dir = os.path.join(base_dir, "saved_schemes")
        # Создаем директории
        os.makedirs(self.saved_schemes_dir, exist_ok=True)
        os.makedirs(self.modulator_presets_dir, exist_ok=True)
        
        # Логируем ТОЛЬКО если parent полностью инициализирован и имеет метод log_message
        try:
            if hasattr(self.parent, 'log_message'):
                self.parent.log_message(f"📁 Modulator presets dir: {self.modulator_presets_dir}", "buffer")
                self.parent.log_message(f"📁 Schemes dir: {self.saved_schemes_dir}", "buffer")
            else:
                # Если нет log_message, просто печатаем
                print(f"📁 Modulator presets dir: {self.modulator_presets_dir}")
                print(f"📁 Schemes dir: {self.saved_schemes_dir}")
        except:
            # Если произошла ошибка, просто печатаем
            print(f"📁 Modulator presets dir: {self.modulator_presets_dir}")
            print(f"📁 Schemes dir: {self.saved_schemes_dir}")
        
    def validate_dvb_t2_standard_compliance(self, fft_size, gi, pilot_pattern, bandwidth, carrier_mode):
        """Validate parameters against DVB-T2 standard tables"""
        compliance_status = {
            "is_standard_compliant": False,
            "message": "",
            "details": []
        }
        
        try:
            # Check bandwidth limitations
            if bandwidth not in self.BANDWIDTH_LIMITATIONS:
                compliance_status["message"] = "❌ Invalid bandwidth"
                return compliance_status
                
            bw_limits = self.BANDWIDTH_LIMITATIONS[bandwidth]
            
            # Check FFT size for bandwidth
            if fft_size not in bw_limits["allowed_fft"]:
                compliance_status["details"].append(f"❌ {fft_size} not allowed for {bandwidth}")
            
            # Check carrier mode for bandwidth
            if carrier_mode not in bw_limits["carrier_mode"]:
                compliance_status["details"].append(f"❌ {carrier_mode} carrier mode not allowed for {bandwidth}")
            
            # Check standard combinations
            if fft_size in self.DVB_T2_STANDARD_COMBINATIONS:
                fft_combinations = self.DVB_T2_STANDARD_COMBINATIONS[fft_size]
                
                if gi in fft_combinations:
                    allowed_pp = fft_combinations[gi]
                    if pilot_pattern in allowed_pp:
                        compliance_status["is_standard_compliant"] = True
                        compliance_status["message"] = "✅ DVB-T2 STANDARD COMPLIANT"
                        compliance_status["details"].append(f"✓ Valid combination: {fft_size}, {gi}, {pilot_pattern}")
                    else:
                        compliance_status["message"] = "⚠️ NON-STANDARD COMBINATION"
                        compliance_status["details"].append(f"❌ {pilot_pattern} not allowed with {fft_size}, {gi}")
                        compliance_status["details"].append(f"✓ Allowed PP: {', '.join(allowed_pp)}")
                else:
                    compliance_status["message"] = "❌ INVALID GUARD INTERVAL"
                    compliance_status["details"].append(f"❌ {gi} not allowed for {fft_size}")
            else:
                compliance_status["message"] = "❌ INVALID FFT SIZE"
        
        except Exception as e:
            compliance_status["message"] = f"❌ Validation error: {str(e)}"
        
        return compliance_status        
        
    def update_parameter_limits_based_on_standard(self):
        """Update available parameters based on DVB-T2 standard"""
        try:
            current_bandwidth = self.bandwidth_var.get()
            current_fft = self.fft_size_var.get()
            current_gi = self.gi_var.get()
            
            # Update FFT sizes based on bandwidth
            if current_bandwidth in self.BANDWIDTH_LIMITATIONS:
                allowed_fft = self.BANDWIDTH_LIMITATIONS[current_bandwidth]["allowed_fft"]
                # Keep all FFT sizes available but show compliance status
                self.fft_size_combo['values'] = list(self.FFT_SIZE.keys())
                
                # If current FFT is not allowed, show warning but don't change
                if current_fft not in allowed_fft and allowed_fft:
                    self.parent.log_message(f"⚠️ {current_fft} not standard for {current_bandwidth}", "buffer")
            
            # Update GI based on FFT size - show all but indicate compliance
            if current_fft in self.DVB_T2_STANDARD_COMBINATIONS:
                allowed_gi = list(self.DVB_T2_STANDARD_COMBINATIONS[current_fft].keys())
                # Keep all GI available but show compliance status
                self.gi_combo['values'] = list(self.GUARD_INTERVAL.keys())
                
                # If current GI is not allowed, show warning but don't change
                if current_gi not in allowed_gi and allowed_gi:
                    self.parent.log_message(f"⚠️ {current_gi} not standard for {current_fft}", "buffer")
            
            # Update PP based on FFT and GI - show all but indicate compliance
            if (current_fft in self.DVB_T2_STANDARD_COMBINATIONS and 
                current_gi in self.DVB_T2_STANDARD_COMBINATIONS[current_fft]):
                allowed_pp = self.DVB_T2_STANDARD_COMBINATIONS[current_fft][current_gi]
                # Keep all PP available but show compliance status
                self.pilot_pattern_combo['values'] = list(self.PILOT_PATTERNS.keys())
            
            # Update carrier mode based on bandwidth - show all but indicate compliance
            if current_bandwidth in self.BANDWIDTH_LIMITATIONS:
                allowed_modes = self.BANDWIDTH_LIMITATIONS[current_bandwidth]["carrier_mode"]
                # Keep all carrier modes available but show compliance status
                self.carrier_mode_combo['values'] = list(self.CARRIER_MODE.keys())
                
            # Update compliance display
            self.update_compliance_display()
            
        except Exception as e:
            self.parent.log_message(f"Error updating parameter limits: {e}", "buffer")        
        
    def update_compliance_display(self):
        """Update the compliance status display below T2 Info button"""
        try:
            if not hasattr(self, 'compliance_label'):
                return
                
            fft_size = self.fft_size_var.get()
            gi = self.gi_var.get()
            pp = self.pilot_pattern_var.get()
            bandwidth = self.bandwidth_var.get()
            carrier_mode = self.carrier_mode_var.get()
            
            compliance = self.validate_dvb_t2_standard_compliance(fft_size, gi, pp, bandwidth, carrier_mode)
            
            # Update label with compliance status
            if compliance["is_standard_compliant"]:
                self.compliance_label.config(
                    text=compliance["message"],
                    foreground='green',
                    font=('Arial', 9, 'bold')
                )
            else:
                self.compliance_label.config(
                    text=compliance["message"],
                    foreground='orange' if "NON-STANDARD" in compliance["message"] else 'red',
                    font=('Arial', 9, 'bold')
                )
                
        except Exception as e:
            print(f"Error updating compliance display: {e}")        
        
    def validate_with_mathematical_framework(self, bandwidth, fft_size, gi, pilot_pattern):
        """Validate parameters using DVB-T2 mathematical framework"""
        try:
            # 1. Basic constants for bandwidth
            t_periods = {
                "1.7 MHz": 71/131,
                "5 MHz": 7/40,
                "6 MHz": 7/48, 
                "7 MHz": 1/8,
                "8 MHz": 7/64,
                "10 MHz": 7/80
            }
            
            # 2. FFT sizes
            fft_points = {
                "1K": 1024, "2K": 2048, "4K": 4096,
                "8K": 8192, "16K": 16384, "32K": 32768
            }
            
            # 3. Active carriers (Normal mode)
            active_carriers = {
                "1K": 853, "2K": 1705, "4K": 3409,
                "8K": 6817, "16K": 13633, "32K": 27265
            }
            
            # 4. Pilot Pattern parameters
            pp_parameters = {
                "PP1": {"dx": 3, "dy": 4},
                "PP2": {"dx": 6, "dy": 2},
                "PP3": {"dx": 6, "dy": 4},
                "PP4": {"dx": 12, "dy": 2},
                "PP5": {"dx": 12, "dy": 4},
                "PP6": {"dx": 24, "dy": 2},
                "PP7": {"dx": 24, "dy": 4},
                "PP8": {"dx": 6, "dy": 16}
            }
            
            # 5. Guard Interval fractions
            gi_fractions = {
                "1/128": 1/128, "1/32": 1/32, "1/16": 1/16,
                "19/256": 19/256, "1/8": 1/8, "19/128": 19/128, "1/4": 1/4
            }
            
            # CALCULATIONS
            T = t_periods[bandwidth]
            N = fft_points[fft_size]
            K_active = active_carriers[fft_size]
            GI_frac = gi_fractions[gi]
            
            # Useful symbol duration
            T_U = N * T  # microseconds
            
            # Carrier spacing
            delta_f = 1 / T_U  # MHz (since T_U in microseconds)
            
            # Occupied bandwidth
            OBW = K_active * delta_f  # MHz
            
            # Guard interval duration  
            T_G = T_U * GI_frac
            
            # Pilot Pattern Nyquist limit
            pp_params = pp_parameters[pilot_pattern]
            T_Nyquist = T_U * (pp_params["dx"] * pp_params["dy"] - 1) / (pp_params["dx"] * pp_params["dy"])
            T_E = T_Nyquist * (57/64)  # Practical equalizer limit
            
            # VALIDATION CHECKS
            bandwidth_value = float(bandwidth.split()[0])  # Extract numeric value
            
            # Check 1: Occupied bandwidth constraint
            if OBW > bandwidth_value:
                return False, f"OBW {OBW:.3f} MHz > Bandwidth {bandwidth_value} MHz"
            
            # Check 2: Pilot Pattern coverage
            if T_G > T_E:
                return False, f"Guard Interval {T_G:.3f}μs > PP limit {T_E:.3f}μs"
            
            return True, f"Valid: OBW={OBW:.3f}MHz, T_G={T_G:.3f}μs, T_E={T_E:.3f}μs"
            
        except Exception as e:
            return False, f"Math validation error: {str(e)}"         

    def calculate(self):
        """Main calculation function using dvbt2rate.exe with mathematical validation"""
        # УБИРАЕМ блокировку при нестандартных комбинациях
        # Validation first - without popup messages
        is_valid, validation_msg = self.validate_parameters()
        if not is_valid:
            self.parent.log_message(f"⚠️ Basic Validation Warning: {validation_msg}", "buffer")
            # НЕ возвращаемся, продолжаем расчет!
            # return
        
        # NEW: Mathematical framework validation
        math_valid, math_msg = self.validate_with_mathematical_framework(
            self.bandwidth_var.get(),
            self.fft_size_var.get(), 
            self.gi_var.get(),
            self.pilot_pattern_var.get()
        )
        
        if not math_valid:
            self.parent.log_message(f"⚠️ Mathematical Validation Warning: {math_msg}", "buffer")
            # НЕ возвращаемся, продолжаем расчет!
            # return
        else:
            self.parent.log_message(f"✅ Mathematical Validation: {math_msg}", "buffer")
        
        try:
            # Get the directory where the script is located
            script_dir = os.path.dirname(os.path.abspath(__file__))
            exe_path = os.path.join(script_dir, "dvbt2rate.exe")
            
            # Check if original calculator exists with absolute path
            if not os.path.exists(exe_path):
                self.parent.log_message(f"❌ dvbt2rate.exe not found at: {exe_path}", "buffer")
                return
            
            # Prepare parameters for original calculator
            params = {
                'bandwidth': self.BANDWIDTH[self.bandwidth_var.get()],
                'fft_size': self.FFT_SIZE[self.fft_size_var.get()],
                'guard_interval': self.GUARD_INTERVAL[self.gi_var.get()],
                'data_symbols': int(float(self.data_symbols_var.get())),
                'fec_blocks': float(self.fec_blocks_var.get()),
                'code_rate': self.CODE_RATES[self.code_rate_var.get()],
                'modulation': self.MODULATION[self.modulation_var.get()],
                'frame_size': self.FRAME_SIZE[self.frame_size_var.get()],
                'carrier_mode': self.CARRIER_MODE[self.carrier_mode_var.get()],
                'pilot_pattern': self.PILOT_PATTERNS[self.pilot_pattern_var.get()],
                'l1_modulation': self.L1_MODULATION[self.l1_modulation_var.get()]
            }
            
            self.parent.log_message("🔄 Running original DVB-T2 calculator...", "buffer")
            
            # Run original calculator with absolute path
            cmd = [
                exe_path,
                str(params['bandwidth']),
                str(params['fft_size']),
                str(params['guard_interval']),
                str(params['data_symbols']),
                str(params['fec_blocks']),
                str(params['code_rate']),
                str(params['modulation']),
                str(params['frame_size']),
                str(params['carrier_mode']),
                str(params['pilot_pattern']),
                str(params['l1_modulation'])
            ]
            
            self.parent.log_message(f"🔍 Calculator command: {' '.join(cmd)}", "buffer")
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10, 
                                  cwd=script_dir)  # Запускаем из директории скрипта
            
            # ДОБАВЛЕНО: Детальный вывод для отладки
            self.parent.log_message("🔍 FULL CALCULATOR OUTPUT:", "buffer")
            self.parent.log_message(result.stdout, "buffer")
            if result.stderr:
                self.parent.log_message("🔍 CALCULATOR ERRORS:", "buffer")
                self.parent.log_message(result.stderr, "buffer")
            
            if result.returncode != 0:
                raise Exception(f"Calculator returned error: {result.stderr}")
            
            # Parse results
            original_results = self.parse_original_output(result.stdout)
            
            if not original_results:
                raise Exception("Failed to parse calculator output")
            
            # Store results
            self.calculation_results = {
                **params,
                **original_results
            }
            
            # Update parameter limits based on calculator results
            self.update_parameter_limits(original_results)
            
            # Update muxrate in main application
            bitrate_normal = original_results.get('bitrate_normal', 0)
            self.parent.muxrate.set(f"{bitrate_normal:.6f}")
            
            # Display results
            self.display_original_results(original_results, params)
            
            self.parent.log_message("✅ Calculation completed using original dvbt2rate.exe", "buffer")
            
        except subprocess.TimeoutExpired:
            self.parent.log_message("❌ Original calculator timed out", "buffer")
        except Exception as e:
            self.parent.log_message(f"❌ Error during calculation: {str(e)}", "buffer")
            import traceback
            self.parent.log_message(f"❌ Calculation error details: {traceback.format_exc()}", "buffer")

    def parse_original_output(self, output):
        """Parse output from original dvbt2rate calculator"""
        try:
            lines = output.split('\n')
            results = {}
            cells_parsed = False
            
            for line in lines:
                line = line.strip()
                
                # Parse clock rate и TF из одной строки
                if "clock rate =" in line and "TF =" in line:
                    try:
                        clock_part = line.split('clock rate =')[1].split(',')[0].strip()
                        results['clock_rate'] = float(clock_part)
                        self.parent.log_message(f"✅ Parsed clock rate: {results['clock_rate']} Hz", "buffer")
                        
                        tf_part = line.split('TF =')[1].split('ms')[0].strip()
                        results['frame_time_ms'] = float(tf_part)
                        self.parent.log_message(f"✅ Parsed frame time: {results['frame_time_ms']} ms", "buffer")
                    except Exception as e:
                        self.parent.log_message(f"⚠️ Error parsing clock rate/TF: {e}", "buffer")
                        pass
                
                # Parse Normal mode bitrate
                elif "Normal mode bitrate =" in line:
                    try:
                        value = float(line.split('=')[1].strip())
                        results['bitrate_normal'] = value
                        self.parent.log_message(f"✅ Parsed normal bitrate: {results['bitrate_normal']} bps", "buffer")
                    except Exception as e:
                        self.parent.log_message(f"⚠️ Error parsing normal bitrate: {e}", "buffer")
                        pass
                
                # Parse High Efficiency bitrate  
                elif "High Efficiency mode bitrate =" in line:
                    try:
                        value = float(line.split('=')[1].strip())
                        results['bitrate_he'] = value
                        self.parent.log_message(f"✅ Parsed HE bitrate: {results['bitrate_he']} bps", "buffer")
                    except Exception as e:
                        self.parent.log_message(f"⚠️ Error parsing HE bitrate: {e}", "buffer")
                        pass
                
                # Parse max symbols and max blocks
                elif "max symbols =" in line and "max blocks =" in line and "PAPR" not in line:
                    try:
                        # Формат: "max symbols = 360, max blocks = 8"
                        import re
                        numbers = re.findall(r'\d+', line)
                        if len(numbers) >= 2:
                            results['max_symbols'] = int(numbers[0])
                            results['max_blocks'] = int(numbers[1])
                            self.parent.log_message(f"✅ Parsed limits: max_symbols={results['max_symbols']}, max_blocks={results['max_blocks']}", "buffer")
                    except Exception as e:
                        self.parent.log_message(f"⚠️ Error parsing max symbols/blocks: {e}", "buffer")
                        pass
                
                # Parse cells calculation
                elif "cells =" in line and "stream =" in line and not cells_parsed and "PAPR" not in line:
                    try:
                        # Буквально парсим строку как она есть
                        parts = line.split(',')
                        
                        for part in parts:
                            part = part.strip()
                            if "cells =" in part:
                                results['total_cells'] = int(part.split('=')[1].strip())
                            elif "stream =" in part:
                                results['useful_cells'] = int(part.split('=')[1].strip())
                            elif "L1 =" in part:
                                results['l1_cells'] = int(part.split('=')[1].strip())
                            elif "dummy =" in part:
                                results['dummy_cells'] = int(part.split('=')[1].strip())
                            elif "unmodulated =" in part:
                                results['unmodulated_cells'] = int(part.split('=')[1].strip())
                        
                        self.parent.log_message(f"✅ Parsed cells: total={results.get('total_cells', 0)}, useful={results.get('useful_cells', 0)}, L1={results.get('l1_cells', 0)}, dummy={results.get('dummy_cells', 0)}, unmodulated={results.get('unmodulated_cells', 0)}", "buffer")
                        cells_parsed = True
                            
                    except Exception as e:
                        self.parent.log_message(f"⚠️ Error parsing cells: {e}", "buffer")
                        self.parent.log_message(f"⚠️ Problematic line: {line}", "buffer")
                        pass
            
            # Добавляем отладочную информацию
            self.parent.log_message(f"🔍 Final parser results:", "buffer")
            for key, value in results.items():
                self.parent.log_message(f"   {key}: {value}", "buffer")
            
            return results
            
        except Exception as e:
            self.parent.log_message(f"❌ Error parsing original output: {e}", "buffer")
            import traceback
            self.parent.log_message(f"❌ Traceback: {traceback.format_exc()}", "buffer")
            return {}
            
    def display_original_results(self, results, params):
        """Display results from original calculator with limits information"""
        try:
            output_lines = []
            output_lines.append("=== DVB-T2 CALCULATION RESULTS (dvbt2rate.exe) ===")
            output_lines.append(f"Bandwidth: {self.bandwidth_var.get()}")
            output_lines.append(f"FFT Size: {self.fft_size_var.get()}")
            output_lines.append(f"Guard Interval: {self.gi_var.get()}")
            output_lines.append(f"Data Symbols: {params['data_symbols']}")
            output_lines.append(f"FEC Blocks: {params['fec_blocks']}")
            output_lines.append(f"Code Rate: {self.code_rate_var.get()}")
            output_lines.append(f"Modulation: {self.modulation_var.get()}")
            output_lines.append(f"Frame Size: {self.frame_size_var.get()}")
            output_lines.append(f"Carrier Mode: {self.carrier_mode_var.get()}")
            output_lines.append(f"Pilot Pattern: {self.pilot_pattern_var.get()}")
            output_lines.append(f"L1 Modulation: {self.l1_modulation_var.get()}")
            output_lines.append("")
            
            # DVB-T2 Standard Compliance
            compliance = self.validate_dvb_t2_standard_compliance(
                self.fft_size_var.get(),
                self.gi_var.get(), 
                self.pilot_pattern_var.get(),
                self.bandwidth_var.get(),
                self.carrier_mode_var.get()
            )

            output_lines.append("=== DVB-T2 STANDARD COMPLIANCE ===")
            output_lines.append(compliance["message"])
            for detail in compliance["details"]:
                output_lines.append(f"  {detail}")

            # Mathematical Framework Validation
            math_valid, math_msg = self.validate_with_mathematical_framework(
                self.bandwidth_var.get(),
                self.fft_size_var.get(),
                self.gi_var.get(), 
                self.pilot_pattern_var.get()
            )

            output_lines.append("")
            output_lines.append("=== MATHEMATICAL VALIDATION ===")
            output_lines.append("✅ VALID" if math_valid else "❌ INVALID")
            output_lines.append(f"Details: {math_msg}")
            output_lines.append("")
            
            # Добавляем информацию о реальных лимитах из калькулятора
            if 'max_symbols' in results:
                output_lines.append(f"Maximum Symbols: {results['max_symbols']}")
            if 'max_blocks' in results:
                output_lines.append(f"Maximum Blocks: {results['max_blocks']}")
            if 'max_data_symbols_display' in results:
                output_lines.append(f"Maximum Data Symbols: {results['max_data_symbols_display']}")
            if 'max_blocks_display' in results:
                output_lines.append(f"Maximum FEC Blocks: {results['max_blocks_display']}")
            output_lines.append("")
            
            # Bitrate results
            bitrate_normal = results.get('bitrate_normal', 0)
            output_lines.append(f"Normal Mode Bitrate: {bitrate_normal:.6f} bps")
            output_lines.append(f"Normal Mode Bitrate: {bitrate_normal/1000:.6f} kbps")
            output_lines.append(f"Normal Mode Bitrate: {bitrate_normal/1000000:.6f} Mbps")
            
            bitrate_he = results.get('bitrate_he', 0)
            if bitrate_he > 0:
                output_lines.append(f"High Efficiency Bitrate: {bitrate_he:.6f} bps")
                output_lines.append(f"High Efficiency Bitrate: {bitrate_he/1000:.6f} kbps")
            
            output_lines.append("")
            
            # Cells calculation - УБЕДИТЕСЬ ЧТО ИСПОЛЬЗУЕТСЯ results, А НЕ params
            output_lines.append("=== CELLS CALCULATION ===")
            total_cells = results.get('total_cells', 0)  # ← ДОЛЖНО БЫТЬ results.get()
            useful_cells = results.get('useful_cells', 0)  # ← ДОЛЖНО БЫТЬ results.get()
            dummy_cells = results.get('dummy_cells', 0)  # ← ДОЛЖНО БЫТЬ results.get()
            
            output_lines.append(f"Total Cells: {total_cells:,}")
            output_lines.append(f"Useful Cells: {useful_cells:,}")
            output_lines.append(f"Dummy Cells: {dummy_cells:,}")
            output_lines.append("")
            
            # Validation
            output_lines.append("=== VALIDATION RESULTS ===")
            
            frame_time_ms = results.get('frame_time_ms', 0)
            rule1_ok = frame_time_ms < 250
            output_lines.append(f"Frame Time: {frame_time_ms:.2f} ms {'✅' if rule1_ok else '❌'} {'< 250 ms' if rule1_ok else '> 250 ms'}")
            
            dummy_cells = results.get('dummy_cells', 0)  # ← ДОЛЖНО БЫТЬ results.get()
            rule2_ok = dummy_cells >= 0
            output_lines.append(f"Dummy Cells: {dummy_cells:,} {'✅ POSITIVE' if rule2_ok else '❌ NEGATIVE'}")
            
            validation_ok = rule1_ok and rule2_ok
            output_lines.append("")
            output_lines.append(f"CONFIGURATION: {'✅ VALID' if validation_ok else '❌ INVALID'}")
            
            # Detailed parameters
            output_lines.append("")
            output_lines.append("=== DETAILED PARAMETERS ===")
            clock_rate = results.get('clock_rate', 0)
            output_lines.append(f"Clock Rate: {clock_rate:.6f} Hz")
            output_lines.append(f"Clock Rate: {clock_rate/1000000:.6f} MHz")
            output_lines.append(f"Frame Time: {results.get('frame_time_ms', 0):.2f} ms")
            
            # Update results text
            self.results_text.delete(1.0, tk.END)
            self.results_text.insert(1.0, "\n".join(output_lines))
            
        except Exception as e:
            self.parent.log_message(f"❌ Error displaying results: {e}", "buffer")
            
    def update_compatibility_based_on_math(self):
        """Update parameter compatibility based on mathematical framework"""
        try:
            bandwidth = self.bandwidth_var.get()
            fft_size = self.fft_size_var.get()
            gi = self.gi_var.get()
            
            # Calculate T_U and T_G
            t_periods = {"1.7 MHz": 71/131, "5 MHz": 7/40, "6 MHz": 7/48, 
                        "7 MHz": 1/8, "8 MHz": 7/64, "10 MHz": 7/80}
            fft_points = {"1K": 1024, "2K": 2048, "4K": 4096,
                         "8K": 8192, "16K": 16384, "32K": 32768}
            gi_fractions = {"1/128": 1/128, "1/32": 1/32, "1/16": 1/16,
                           "19/256": 19/256, "1/8": 1/8, "19/128": 19/128, "1/4": 1/4}
            
            T = t_periods.get(bandwidth, 71/131)
            N = fft_points.get(fft_size, 8192)
            GI_frac = gi_fractions.get(gi, 1/8)
            
            T_U = N * T
            T_G = T_U * GI_frac
            
            # Filter Pilot Patterns based on T_E >= T_G
            pp_limits = {
                "PP1": 0.297, "PP2": 0.148, "PP3": 0.148, "PP4": 0.074,
                "PP5": 0.074, "PP6": 0.037, "PP7": 0.037, "PP8": 0.148
            }
            
            available_pp = []
            for pp, t_e_factor in pp_limits.items():
                T_E = T_U * t_e_factor
                if T_E >= T_G:
                    available_pp.append(pp)
            
            # Update PP combobox
            current_pp = self.pilot_pattern_var.get()
            self.pilot_pattern_combo['values'] = available_pp
            
            if current_pp not in available_pp and available_pp:
                self.parent.log_message(f"⚠️ Current PP {current_pp} cannot cover GI {gi}", "buffer")
                self.parent.log_message(f"⚠️ Available PP: {', '.join(available_pp)}", "buffer")
                
        except Exception as e:
            self.parent.log_message(f"⚠️ Math compatibility update error: {e}", "buffer")             
            
    def update_parameter_limits(self, results):
        """Update parameter limits based on calculator results"""
        try:
            if 'max_symbols' in results and 'max_blocks' in results:
                max_symbols = results['max_symbols']
                max_blocks = results['max_blocks']
                
                # Определяем смещение для data symbols в зависимости от FFT size
                fft_size = self.fft_size_var.get()
                offset_map = {
                    "1K": 16,
                    "2K": 8, 
                    "4K": 4,
                    "8K": 2,
                    "16K": 1,
                    "32K": 1
                }
                offset = offset_map.get(fft_size, 16)
                
                # Максимальное значение для Data Symbols из расчета калькулятора
                max_data_symbols = max_symbols - offset
                
                # Обновляем выпадающие списки с реальными лимитами из калькулятора
                self.update_data_symbols_combo(max_data_symbols)
                self.update_fec_blocks_combo(max_blocks)
                
                # Сохраняем для отображения в результатах
                results['max_data_symbols_display'] = max_data_symbols
                results['max_blocks_display'] = max_blocks
                
                self.parent.log_message(f"🔧 Updated limits from calculator: Data Symbols ≤ {max_data_symbols}, FEC Blocks ≤ {max_blocks}", "buffer")
                
        except Exception as e:
            self.parent.log_message(f"⚠️ Error updating parameter limits: {e}", "buffer")

    def update_parameter_limits_display(self, results):
        """Update parameter limits display in results"""
        try:
            if 'max_symbols' in results and 'max_blocks' in results:
                max_symbols = results['max_symbols']
                max_blocks = results['max_blocks']
                
                # Определяем смещение для data symbols
                fft_size = self.fft_size_var.get()
                offset_map = {
                    "1K": 16, "2K": 8, "4K": 4, "8K": 2, "16K": 1, "32K": 1
                }
                offset = offset_map.get(fft_size, 16)
                max_data_symbols = max_symbols - offset
                
                # Обновляем выпадающие списки
                self.update_data_symbols_combo(max_data_symbols)
                self.update_fec_blocks_combo(max_blocks)
                
                return max_data_symbols, max_blocks
        except Exception as e:
            self.parent.log_message(f"⚠️ Error updating parameter limits display: {e}", "buffer")
        return None, None

    def validate_data_symbols(self, value, max_value):
        """Validate Data Symbols input"""
        if value == "":
            return True
        try:
            val = int(value)
            return 1 <= val <= int(max_value)
        except:
            return False

    def validate_fec_blocks(self, value, max_value):
        """Validate FEC Blocks input"""
        if value == "":
            return True
        try:
            val = float(value)
            return 1 <= val <= int(max_value)
        except:
            return False

    def on_fft_size_change(self, event=None):
        """Update pilot pattern options when FFT size changes"""
        try:
            fft_size = self.FFT_SIZE[self.fft_size_var.get()]
            gi = self.GUARD_INTERVAL[self.gi_var.get()]
            self.update_pilot_pattern_options(fft_size, gi)
        except Exception as e:
            self.parent.log_message(f"⚠️ Error in FFT size change: {e}", "buffer")

    def on_gi_change(self, event=None):
        """Update pilot pattern options when Guard Interval changes"""
        try:
            fft_size = self.FFT_SIZE[self.fft_size_var.get()]
            gi = self.GUARD_INTERVAL[self.gi_var.get()]
            self.update_pilot_pattern_options(fft_size, gi)
        except Exception as e:
            self.parent.log_message(f"⚠️ Error in GI change: {e}", "buffer")

    def update_data_symbols_combo(self, max_value):
        """Update Data Symbols combobox with limited range из расчета калькулятора"""
        try:
            current_value = int(float(self.data_symbols_var.get()))
            min_value = 1
            
            # Создаем диапазон значений на основе реального максимума из калькулятора
            if max_value <= 50:
                values = list(range(min_value, max_value + 1))
            else:
                # Если диапазон большой, показываем текущее значение ±25
                start = max(min_value, current_value - 25)
                end = min(max_value, current_value + 25)
                values = list(range(start, end + 1))
                
                # Добавляем границы если они не входят в диапазон
                if start > min_value:
                    values = [min_value] + values
                if end < max_value:
                    values = values + [max_value]
            
            self.data_symbols_combo['values'] = values
            self.data_symbols_combo.config(state="readonly")
            
            self.parent.log_message(f"🔧 Data Symbols combo updated: {min_value} to {max_value}", "buffer")
            
        except Exception as e:
            self.parent.log_message(f"⚠️ Error updating data symbols combo: {e}", "buffer")

    def update_fec_blocks_combo(self, max_value):
        """Update FEC Blocks combobox with limited range из расчета калькулятора"""
        try:
            current_value = float(self.fec_blocks_var.get())
            min_value = 1
            
            # Создаем диапазон значений на основе реального максимума из калькулятора
            if max_value <= 50:
                values = [str(x) for x in range(min_value, int(max_value) + 1)]
            else:
                # Если диапазон большой, показываем текущее значение ±25
                start = max(min_value, int(current_value) - 25)
                end = min(max_value, int(current_value) + 25)
                values = [str(x) for x in range(start, end + 1)]
                
                # Добавляем границы если они не входят в диапазон
                if start > min_value:
                    values = [str(min_value)] + values
                if end < max_value:
                    values = values + [str(int(max_value))]
            
            self.fec_blocks_combo['values'] = values
            self.fec_blocks_combo.config(state="readonly")
            
            self.parent.log_message(f"🔧 FEC Blocks combo updated: {min_value} to {max_value}", "buffer")
            
        except Exception as e:
            self.parent.log_message(f"⚠️ Error updating FEC blocks combo: {e}", "buffer")
            
    def validate_parameters(self):
        """
        Validate parameter combinations according to DVB-T2 standard
        Returns (is_valid, message) - but doesn't block calculation
        """
        try:
            # Basic type validation
            data_symbols_str = self.data_symbols_var.get()
            fec_blocks_str = self.fec_blocks_var.get()
            
            try:
                data_symbols = float(data_symbols_str)
                fec_blocks = float(fec_blocks_str)
            except ValueError:
                return False, "Data symbols and FEC blocks must be valid numbers"
            
            if data_symbols <= 0 or fec_blocks <= 0:
                return False, "Data symbols and FEC blocks must be positive numbers"
            
            # Get string values for validation
            fft_str = self.fft_size_var.get()
            gi_str = self.gi_var.get()
            pp_str = self.pilot_pattern_var.get()
            bandwidth_str = self.bandwidth_var.get()
            carrier_mode_str = self.carrier_mode_var.get()
            
            # Check FFT size against bandwidth limitations
            if bandwidth_str in self.BANDWIDTH_LIMITATIONS:
                allowed_fft = self.BANDWIDTH_LIMITATIONS[bandwidth_str]["allowed_fft"]
                if fft_str not in allowed_fft:
                    self.parent.log_message(
                        f"⚠️ {fft_str} FFT is not standard for {bandwidth_str} bandwidth",
                        "buffer"
                    )
            
            # Check carrier mode against bandwidth
            if bandwidth_str in self.BANDWIDTH_LIMITATIONS:
                allowed_modes = self.BANDWIDTH_LIMITATIONS[bandwidth_str]["carrier_mode"]
                if carrier_mode_str not in allowed_modes:
                    self.parent.log_message(
                        f"⚠️ {carrier_mode_str} carrier mode is not standard for {bandwidth_str}",
                        "buffer"
                    )
            
            # Check FFT + GI + PP compatibility using standard table
            if (fft_str in self.DVB_T2_STANDARD_COMBINATIONS and 
                gi_str in self.DVB_T2_STANDARD_COMBINATIONS[fft_str]):
                
                allowed_pp = self.DVB_T2_STANDARD_COMBINATIONS[fft_str][gi_str]
                if pp_str not in allowed_pp:
                    self.parent.log_message(
                        f"⚠️ {pp_str} is not compatible with {fft_str} FFT and GI {gi_str} "
                        f"per ETSI EN 302 755",
                        "buffer"
                    )
                    self.parent.log_message(
                        f"✓ Allowed patterns: {', '.join(allowed_pp)}",
                        "buffer"
                    )
            else:
                # Combination not found in standard - warn but don't block
                self.parent.log_message(
                    f"⚠️ Combination {fft_str} FFT + GI {gi_str} is not defined in ETSI EN 302 755",
                    "buffer"
                )
            
            return True, "Parameters validated (warnings in log)"
            
        except Exception as e:
            return False, f"Validation error: {str(e)}"
       
    def update_pilot_pattern_options(self, fft_size, gi):
        """
        Update available pilot pattern options based on FFT size and GI
        Uses ETSI EN 302 755 compatibility tables
        """
        try:
            # Get string values for dictionary lookup
            fft_str = self.fft_size_var.get()
            gi_str = self.gi_var.get()
            
            # Check if we have compatibility data for this combination
            if (fft_str in self.DVB_T2_STANDARD_COMBINATIONS and 
                gi_str in self.DVB_T2_STANDARD_COMBINATIONS[fft_str]):
                
                # Get allowed patterns from standard
                allowed_pp = self.DVB_T2_STANDARD_COMBINATIONS[fft_str][gi_str]
                
                # Update combobox with only allowed patterns
                self.pilot_pattern_combo['values'] = allowed_pp
                
                # Check if current selection is still valid
                current_pp = self.pilot_pattern_var.get()
                if current_pp not in allowed_pp and allowed_pp:
                    # Don't auto-change, just warn
                    self.parent.log_message(
                        f"⚠️ Pilot Pattern {current_pp} is not compatible with "
                        f"{fft_str} FFT and GI {gi_str} per ETSI EN 302 755", 
                        "buffer"
                    )
                    self.parent.log_message(
                        f"✓ Allowed patterns: {', '.join(allowed_pp)}", 
                        "buffer"
                    )
            else:
                # If no data in standard, this combination might be invalid
                self.parent.log_message(
                    f"⚠️ No standard compatibility data for {fft_str} FFT with GI {gi_str}", 
                    "buffer"
                )
                
        except Exception as e:
            self.parent.log_message(f"⚠️ Error updating pilot pattern options: {e}", "buffer")

    def save_preset(self):
        """Save current parameters as GNU Radio preset with JSON scheme"""
        if not self.calculation_results:
            self.parent.log_message("❌ Please calculate bitrate first!", "buffer")
            return
        
        try:
            self.parent.log_message("🔄 Starting preset save process...", "buffer")
            
            # Получаем строковые значения из переменных интерфейса
            bandwidth_clean = self.bandwidth_var.get().replace(' ', '_').replace('.', '_')
            modulation_clean = self.modulation_var.get()
            code_rate_clean = self.code_rate_var.get().replace('/', '_')
            fft_size_clean = self.fft_size_var.get()
            gi_clean = self.gi_var.get().replace('/', '_')
            pp_clean = self.pilot_pattern_var.get()
            
            # Безопасное получение bitrate
            bitrate_normal = self.calculation_results.get('bitrate_normal', 0)
            bitrate_kbps = round(bitrate_normal / 1000)
            
            self.parent.log_message(f"📝 Parameters: {bandwidth_clean}, {modulation_clean}, {code_rate_clean}", "buffer")
            
            # ОДИНАКОВОЕ имя для Python и JSON файлов
            base_filename = f"{bandwidth_clean}_{modulation_clean}_{code_rate_clean}_{fft_size_clean}_{gi_clean}_{pp_clean}_{bitrate_kbps}kbps"
            
            # Убираем проблемные символы
            import re
            base_filename = re.sub(r'[^\w\.-]', '_', base_filename)
            
            # Полные пути
            python_file_path = os.path.join(self.modulator_presets_dir, base_filename + ".py")
            json_file_path = os.path.join(self.saved_schemes_dir, base_filename + ".json")
            
            self.parent.log_message(f"📁 File paths: {python_file_path}, {json_file_path}", "buffer")
            
            # Генерируем валидное имя класса
            class_name = base_filename
            if class_name[0].isdigit():
                class_name = "DVB_" + class_name
            
            # СОХРАНЯЕМ JSON С ПАРАМЕТРАМИ - используем безопасное извлечение значений
            save_data = {
                'parameters': {
                    'channel_bandwidth': self.bandwidth_var.get(),
                    'fft_size': self.fft_size_var.get(),
                    'guard_interval': self.gi_var.get(),
                    'data_symbols': int(float(self.data_symbols_var.get())),
                    'fec_blocks': float(self.fec_blocks_var.get()),
                    'code_rate': self.code_rate_var.get(),
                    'modulation': self.modulation_var.get(),
                    'frame_size': self.frame_size_var.get(),
                    'carrier_mode': self.carrier_mode_var.get(),
                    'pilot_pattern': self.pilot_pattern_var.get(),
                    'l1_modulation': self.l1_modulation_var.get()
                },
                'results': {
                    'normal_bitrate_bps': bitrate_normal,
                    'normal_bitrate_kbps': bitrate_normal / 1000,
                    'normal_bitrate_mbps': bitrate_normal / 1000000,
                    'high_efficiency_bitrate_bps': self.calculation_results.get('bitrate_he', 0),
                    'high_efficiency_bitrate_kbps': self.calculation_results.get('bitrate_he', 0) / 1000,
                    'high_efficiency_bitrate_mbps': self.calculation_results.get('bitrate_he', 0) / 1000000,
                    'frame_time_ms': self.calculation_results.get('frame_time_ms', 0),
                    'clock_rate': self.calculation_results.get('clock_rate', 0)
                }
            }
            
            # Добавляем дополнительные параметры из calculation_results, если они существуют
            additional_params = ['total_cells', 'dummy_cells', 'kbch', 'cell_size', 'useful_cells']
            for param in additional_params:
                if param in self.calculation_results:
                    save_data['parameters'][param] = self.calculation_results[param]
            
            self.parent.log_message("💾 Saving JSON file...", "buffer")
            with open(json_file_path, 'w') as f:
                json.dump(save_data, f, indent=4)
            
            self.parent.log_message("📄 Generating GNU Radio script...", "buffer")
            # Генерируем скрипт GNU Radio
            script_content = self.generate_gnuradio_script(base_filename + ".py", class_name)
            
            self.parent.log_message("💾 Saving Python script...", "buffer")
            # Сохраняем скрипт
            with open(python_file_path, 'w') as f:
                f.write(script_content)
            
            self.parent.log_message("🔄 Updating modulator presets...", "buffer")
            # Обновляем пресеты в основном приложении
            self.parent.update_modulator_presets()
            
            self.parent.log_message("✅ Preset saved successfully!", "buffer")
            
        except Exception as e:
            self.parent.log_message(f"❌ Error saving preset: {str(e)}", "buffer")
            # Более подробная информация об ошибке
            import traceback
            error_details = traceback.format_exc()
            self.parent.log_message(f"❌ Error details: {error_details}", "buffer")

    def generate_gnuradio_script(self, filename, class_name):
        """Generate GNU Radio Python script with calculated parameters"""
        try:
            # Безопасное получение всех значений из интерфейса
            modulation = self.modulation_var.get()
            code_rate = self.code_rate_var.get()
            guard_interval = self.gi_var.get()
            fft_size = self.fft_size_var.get()
            pilot_pattern = self.pilot_pattern_var.get()
            carrier_mode = self.carrier_mode_var.get()
            frame_size = self.frame_size_var.get()
            l1_modulation = self.l1_modulation_var.get()
            bandwidth = self.bandwidth_var.get()
            
            # Безопасное получение числовых значений
            try:
                data_symbols = int(float(self.data_symbols_var.get()))
            except:
                data_symbols = 342
                
            try:
                fec_blocks = int(float(self.fec_blocks_var.get()))
            except:
                fec_blocks = 8
                
            try:
                bitrate_normal = int(self.calculation_results.get('bitrate_normal', 1030284))
            except:
                bitrate_normal = 1030284
                
            # Clock rate из расчета или по умолчанию
            try:
                clock_rate = round(self.calculation_results.get('clock_rate', 0))
                if clock_rate == 0:
                    # Если clock_rate не рассчитан, используем значение на основе bandwidth
                    bandwidth_map = {
                        "1.7 MHz": 1845070,
                        "5 MHz": 5714285, 
                        "6 MHz": 6857142,
                        "7 MHz": 8000000,
                        "8 MHz": 9142857,
                        "10 MHz": 11428571
                    }
                    clock_rate = bandwidth_map.get(bandwidth, 20000000)
            except:
                clock_rate = 20000000
            
            # Получаем настройки устройства из основного приложения
            selected_device = self.parent.selected_device.get()
            device_config = self.parent.device_configs[selected_device]
            device_args = self.parent.get_device_arguments()
            rf_gain = self.parent.rf_gain.get()  # Значение уже в dB/attenuation для устройства
            use_iio = device_config.get('use_iio', False)  # Флаг для PlutoSDR IIO блока
            
            # Получаем частоту из основного приложения
            frequency = int(self.parent.frequency.get())
            
            # Получаем ZMQ порт из основного приложения
            zmq_port = self.parent.udp_output_port.get()
            zmq_address = f"tcp://{self.parent.output_ip.get()}:{zmq_port}"
            
            # Преобразование значений в формат GNU Radio констант
            # Frame size
            if frame_size == "Normal":
                gr_frame_size = "dtv.FECFRAME_NORMAL"
            else:  # Short
                gr_frame_size = "dtv.FECFRAME_SHORT"
            
            # Carrier mode
            if carrier_mode == "Normal":
                gr_carrier_mode = "dtv.CARRIERS_NORMAL"
            else:  # Extended
                gr_carrier_mode = "dtv.CARRIERS_EXTENDED"
            
            # FFT size
            fft_size_map = {
                "1K": "dtv.FFTSIZE_1K",
                "2K": "dtv.FFTSIZE_2K", 
                "4K": "dtv.FFTSIZE_4K",
                "8K": "dtv.FFTSIZE_8K",
                "16K": "dtv.FFTSIZE_16K",
                "32K": "dtv.FFTSIZE_32K"
            }
            gr_fft_size = fft_size_map.get(fft_size, "dtv.FFTSIZE_1K")
            
            # Guard interval
            gi_map = {
                "1/32": "dtv.GI_1_32",
                "1/16": "dtv.GI_1_16",
                "1/8": "dtv.GI_1_8",
                "1/4": "dtv.GI_1_4",
                "1/128": "dtv.GI_1_128",
                "19/128": "dtv.GI_19_128",
                "19/256": "dtv.GI_19_256"
            }
            gr_guard_interval = gi_map.get(guard_interval, "dtv.GI_1_4")
            
            # L1 modulation
            l1_mod_map = {
                "BPSK": "dtv.L1_MOD_BPSK",
                "QPSK": "dtv.L1_MOD_QPSK",
                "16QAM": "dtv.L1_MOD_16QAM", 
                "64QAM": "dtv.L1_MOD_64QAM"
            }
            gr_l1_modulation = l1_mod_map.get(l1_modulation, "dtv.L1_MOD_QPSK")
            
            # Pilot pattern
            pp_map = {
                "PP1": "dtv.PILOT_PP1",
                "PP2": "dtv.PILOT_PP2",
                "PP3": "dtv.PILOT_PP3",
                "PP4": "dtv.PILOT_PP4",
                "PP5": "dtv.PILOT_PP5",
                "PP6": "dtv.PILOT_PP6",
                "PP7": "dtv.PILOT_PP7",
                "PP8": "dtv.PILOT_PP8"
            }
            gr_pilot_pattern = pp_map.get(pilot_pattern, "dtv.PILOT_PP2")
            
            # Code rate
            code_rate_map = {
                "1/2": "dtv.C1_2",
                "3/5": "dtv.C3_5",
                "2/3": "dtv.C2_3",
                "3/4": "dtv.C3_4",
                "4/5": "dtv.C4_5",
                "5/6": "dtv.C5_6",
                "1/3": "dtv.C1_3",
                "2/5": "dtv.C2_5"
            }
            gr_code_rate = code_rate_map.get(code_rate, "dtv.C1_2")
            
            # Modulation
            modulation_map = {
                "QPSK": "dtv.MOD_QPSK",
                "16QAM": "dtv.MOD_16QAM",
                "64QAM": "dtv.MOD_64QAM",
                "256QAM": "dtv.MOD_256QAM"
            }
            gr_modulation = modulation_map.get(modulation, "dtv.MOD_QPSK")
            
            # Bandwidth
            bandwidth_map = {
                "1.7 MHz": "dtv.BANDWIDTH_1_7_MHZ",
                "5 MHz": "dtv.BANDWIDTH_5_0_MHZ",
                "6 MHz": "dtv.BANDWIDTH_6_0_MHZ",
                "7 MHz": "dtv.BANDWIDTH_7_0_MHZ", 
                "8 MHz": "dtv.BANDWIDTH_8_0_MHZ",
                "10 MHz": "dtv.BANDWIDTH_10_0_MHZ"
            }
            gr_bandwidth = bandwidth_map.get(bandwidth, "dtv.BANDWIDTH_1_7_MHZ")
            
            # Calculate parameters для GNU Radio blocks
            fft_points_map = {
                "1K": 1024, 
                "2K": 2048, 
                "4K": 4096, 
                "8K": 8192, 
                "16K": 16384, 
                "32K": 32768
            }
            fft_points = fft_points_map.get(fft_size, 1024)
            
            # Расчет cyclic prefix в нужном формате без упрощения
            gi_parts_map = {
                "1/32": (1, 32),
                "1/16": (1, 16),
                "1/8": (1, 8),
                "1/4": (1, 4),
                "1/128": (1, 128),
                "19/128": (19, 128),
                "19/256": (19, 256)
            }
            
            gi_numerator, gi_denominator = gi_parts_map.get(guard_interval, (1, 4))
            
            # Формируем строку cyclic prefix в нужном формате
            cyclic_prefix_str = f"{fft_points} + ({fft_points} * {gi_numerator}) // {gi_denominator}"
            
            # Bandwidth в Hz для устройства
            bandwidth_hz_map = {
                "1.7 MHz": 1845070,
                "5 MHz": 5714285,
                "6 MHz": 6857142,
                "7 MHz": 8000000,
                "8 MHz": 9142857,
                "10 MHz": 11428571
            }
            device_bandwidth = bandwidth_hz_map.get(bandwidth, 1845070)
            
            # Определяем минимальный и максимальный RF gain для устройства
            min_gain, max_gain = device_config['gain_range']
            
            # Имя блока sink
            sink_name = device_config['sink_name']
            
            # Определяем, нужно ли добавлять rational resampler для HackRF
            add_resampler = (selected_device == 'hackrf')
            
            # Импорт для filter если нужно
            filter_import = "from gnuradio import filter" if add_resampler else ""
            # ГЕНЕРАЦИЯ БЛОКА SINK В ЗАВИСИМОСТИ ОТ УСТРОЙСТВА
            if use_iio:
                # PlutoSDR с IIO блоком
                sink_block = f"""
        self.{sink_name} = iio.fmcomms2_sink_fc32(pluto_ip if pluto_ip else iio.get_pluto_uri(), [True, True], 32768, False)
        self.{sink_name}.set_len_tag_key('')
        self.{sink_name}.set_bandwidth(bandwidth)
        self.{sink_name}.set_frequency(frequency)
        self.{sink_name}.set_samplerate(sample)
        self.{sink_name}.set_filter_params('Auto', '', 0, 0)"""
                
                # Импорты для IIO
                import_line = "from gnuradio import iio"
                
                # Переменная pluto_ip вместо device_args
                variable_line = f'        self.pluto_ip = pluto_ip = "{device_args}"'
                
                # Gain setup для PlutoSDR attenuation
                gain_setup = f"self.{sink_name}.set_attenuation(0, self.rf_gain)"
                hackrf_gain_init = f"        self.{sink_name}.set_attenuation(0, rf_gain)"
                freq_correction = ""
                
            else:
                # Soapy блок для остальных устройств
                sink_block = f"""
        self.{sink_name} = None
        dev = 'driver={selected_device}'
        stream_args = ''
        tune_args = ['']
        settings = ['']

        self.{sink_name} = soapy.sink(dev, "fc32", 1, device_args,
                                      stream_args, tune_args, settings)
        self.{sink_name}.set_sample_rate(0, sample)
        self.{sink_name}.set_bandwidth(0, bandwidth)
        self.{sink_name}.set_frequency(0, frequency)"""
                
                # Импорты для Soapy
                import_line = "from gnuradio import soapy"
                
                # Переменная device_args
                variable_line = f'        self.device_args = device_args = "{device_args}"'
                
                # Gain setup в зависимости от устройства
                if selected_device == 'hackrf':
                    gain_setup = f"""
        self.{sink_name}.set_gain(0, 'AMP', False)
        self.{sink_name}.set_gain(0, 'VGA', min(max(self.rf_gain, {min_gain}), {max_gain}))"""
                    hackrf_gain_init = f"""
        self.{sink_name}.set_gain(0, 'AMP', False)
        self.{sink_name}.set_gain(0, 'VGA', min(max(rf_gain, {min_gain}), {max_gain}))"""

                else:
                    gain_setup = f"self.{sink_name}.set_gain(0, min(max(self.rf_gain, {min_gain}), {max_gain}))"
                    hackrf_gain_init = f"self.{sink_name}.set_gain(0, min(max(rf_gain, {min_gain}), {max_gain}))"
                
                # Frequency correction для LimeSDR
                if selected_device == 'limesdr':
                    freq_correction = f"""
        self.{sink_name}.set_frequency_correction(0, 0)"""
                else:
                    freq_correction = ""            
            # Генерация блока rational resampler если нужно
            resampler_block = ""
            resampler_connection = ""
            hackrf_sample_rate = clock_rate  # По умолчанию используем clock_rate
            
            if add_resampler:
                # Для HackRF устанавливаем фиксированные коэффициенты в зависимости от bandwidth
                bandwidth_to_interpolation = {
                    "1.7 MHz": (3000000, 1845070),
                    "5 MHz": (9000000, 5714285),
                    "6 MHz": (10000000, 6857142),
                    "7 MHz": (11000000, 8000000),
                    "8 MHz": (12000000, 9142857),
                    "10 MHz": (14000000, 11428571)
                }
                
                # Получаем interpolation и decimation из таблицы
                interpolation, decimation = bandwidth_to_interpolation.get(bandwidth, (clock_rate, device_bandwidth))
                hackrf_sample_rate = interpolation  # Для HackRF используем interpolation как sample rate
                
                # Упрощаем дробь
                from math import gcd
                g = gcd(interpolation, decimation)
                interp = interpolation // g
                decim = decimation // g
                
                # Ограничиваем коэффициенты разумными значениями
                # while interp > 100 or decim > 100:
                    # g *= 2
                    # interp = interpolation // g
                    # decim = decimation // g
                
                resampler_block = f"""
        self.rational_resampler_xxx_0 = filter.rational_resampler_ccc(
            interpolation={interp},
            decimation={decim},
            taps=[],
            fractional_bw=0.45)"""
                
                # Соединение с ресемплером
                resampler_connection = f"""
        self.connect((self.blocks_multiply_const_xx_0, 0), (self.rational_resampler_xxx_0, 0))
        self.connect((self.rational_resampler_xxx_0, 0), (self.{sink_name}, 0))"""
            else:
                # Без ресемплера
                resampler_connection = f"""
        self.connect((self.blocks_multiply_const_xx_0, 0), (self.{sink_name}, 0))"""
            
            # В шаблоне используем hackrf_sample_rate для HackRF, иначе clock_rate
            sample_rate_value = hackrf_sample_rate if add_resampler else clock_rate
            
            # Создаем шаблон скрипта с правильной табуляцией
            script_template = f'''#!/usr/bin/env python3
# -*- coding: utf-8 -*-

#
# SPDX-License-Identifier: GPL-3.0
#
# GNU Radio Python Flow Graph
# Title: DVB-T2 {bandwidth} {modulation} {code_rate}
# Author: DVB-T2 Calculator
# GNU Radio version: 3.10.10.0

from PyQt5 import Qt
from gnuradio import qtgui
from gnuradio import blocks
from gnuradio import digital
from gnuradio import dtv
from gnuradio import gr
from gnuradio.filter import firdes
from gnuradio.fft import window
import sys
import signal
from PyQt5 import Qt
from argparse import ArgumentParser
from gnuradio.eng_arg import eng_float, intx
from gnuradio import eng_notation
{import_line}
{filter_import}
from gnuradio import zeromq
from xmlrpc.server import SimpleXMLRPCServer
import threading

class {class_name}(gr.top_block, Qt.QWidget):

    def __init__(self):
        gr.top_block.__init__(self, "DVB-T2 Modulator", catch_exceptions=True)
        Qt.QWidget.__init__(self)
        self.setWindowTitle("DVB-T2 Modulator")
        qtgui.util.check_set_qss()
        try:
            self.setWindowIcon(Qt.QIcon.fromTheme('gnuradio-grc'))
        except BaseException as exc:
            print(f"Qt GUI: Could not set Icon: {{str(exc)}}", file=sys.stderr)
        self.top_scroll_layout = Qt.QVBoxLayout()
        self.setLayout(self.top_scroll_layout)
        self.top_scroll = Qt.QScrollArea()
        self.top_scroll.setFrameStyle(Qt.QFrame.NoFrame)
        self.top_scroll_layout.addWidget(self.top_scroll)
        self.top_scroll.setWidgetResizable(True)
        self.top_widget = Qt.QWidget()
        self.top_scroll.setWidget(self.top_widget)
        self.top_layout = Qt.QVBoxLayout(self.top_widget)
        self.top_grid_layout = Qt.QGridLayout()
        self.top_layout.addLayout(self.top_grid_layout)

        self.settings = Qt.QSettings("GNU Radio", "{class_name}")

        try:
            geometry = self.settings.value("geometry")
            if geometry:
                self.restoreGeometry(geometry)
        except BaseException as exc:
            print(f"Qt GUI: Could not restore geometry: {{str(exc)}}", file=sys.stderr)

        ##################################################
        # Variables
        ##################################################
    
        self.zmq_address = zmq_address = "{zmq_address}"
        self.sample = sample = {sample_rate_value}
        self.rf_gain = rf_gain = {rf_gain}
        
{variable_line}
        self.frequency = frequency = {frequency}
        self.bandwidth = bandwidth = {device_bandwidth}
        
        

        ##################################################
        # Blocks
        ##################################################

        self.xmlrpc_server_0 = SimpleXMLRPCServer(('localhost', 8001), allow_none=True)
        self.xmlrpc_server_0.register_instance(self)        
        self.xmlrpc_server_0_thread = threading.Thread(target=self.xmlrpc_server_0.serve_forever)
        self.xmlrpc_server_0_thread.daemon = True
        self.xmlrpc_server_0_thread.start()
        
        # ZMQ SUB source 
        self.zeromq_sub_source_0 = zeromq.sub_source(gr.sizeof_char, 1, zmq_address, 500, False, (-1), '', False )
{sink_block}{freq_correction}
{hackrf_gain_init}
        


        # DVB-T2 blocks
        self.dtv_dvbt2_pilotgenerator_cc_0 = dtv.dvbt2_pilotgenerator_cc(
            {gr_carrier_mode},
            {gr_fft_size},
            {gr_pilot_pattern},
            {gr_guard_interval},
            {data_symbols},
            dtv.PAPR_OFF,
            dtv.VERSION_131,
            dtv.PREAMBLE_T2_SISO,
            dtv.MISO_TX1,
            dtv.EQUALIZATION_OFF,
            {gr_bandwidth},
            {fft_points}
            )
        self.dtv_dvbt2_p1insertion_cc_0 = dtv.dvbt2_p1insertion_cc(
            {gr_carrier_mode},
            {gr_fft_size},
            {gr_guard_interval},
            {data_symbols},
            dtv.PREAMBLE_T2_SISO,
            dtv.SHOWLEVELS_OFF,
            3.3
            )
        self.dtv_dvbt2_modulator_bc_0 = dtv.dvbt2_modulator_bc({gr_frame_size}, {gr_modulation}, dtv.ROTATION_ON)
        self.dtv_dvbt2_interleaver_bb_0 = dtv.dvbt2_interleaver_bb({gr_frame_size}, {gr_code_rate}, {gr_modulation})
        self.dtv_dvbt2_freqinterleaver_cc_0 = dtv.dvbt2_freqinterleaver_cc(
            {gr_carrier_mode},
            {gr_fft_size},
            {gr_pilot_pattern},
            {gr_guard_interval},
            {data_symbols},
            dtv.PAPR_OFF,
            dtv.VERSION_131,
            dtv.PREAMBLE_T2_SISO
            )
        self.dtv_dvbt2_framemapper_cc_0 = dtv.dvbt2_framemapper_cc(
            {gr_frame_size},
            {gr_code_rate},
            {gr_modulation},
            dtv.ROTATION_ON,
            {fec_blocks},
            3,
            {gr_carrier_mode},
            {gr_fft_size},
            {gr_guard_interval},
            {gr_l1_modulation},
            {gr_pilot_pattern},
            2,
            {data_symbols},
            dtv.PAPR_OFF,
            dtv.VERSION_131,
            dtv.PREAMBLE_T2_SISO,
            dtv.INPUTMODE_NORMAL,
            dtv.RESERVED_OFF,
            dtv.L1_SCRAMBLED_OFF,
            dtv.INBAND_ON)
        self.dtv_dvbt2_cellinterleaver_cc_0 = dtv.dvbt2_cellinterleaver_cc({gr_frame_size}, {gr_modulation}, {fec_blocks}, 3)
        self.dtv_dvb_ldpc_bb_0 = dtv.dvb_ldpc_bb(
            dtv.STANDARD_DVBT2,
            {gr_frame_size},
            {gr_code_rate},
            dtv.MOD_OTHER)
        self.dtv_dvb_bch_bb_0 = dtv.dvb_bch_bb(
            dtv.STANDARD_DVBT2,
            {gr_frame_size},
            {gr_code_rate}
            )
        self.dtv_dvb_bbscrambler_bb_0 = dtv.dvb_bbscrambler_bb(
            dtv.STANDARD_DVBT2,
            {gr_frame_size},
            {gr_code_rate}
            )
        self.dtv_dvb_bbheader_bb_0 = dtv.dvb_bbheader_bb(
        dtv.STANDARD_DVBT2,
        {gr_frame_size},
        {gr_code_rate},
        dtv.RO_0_35,
        dtv.INPUTMODE_NORMAL,
        dtv.INBAND_ON,
        {fec_blocks},
        {bitrate_normal})
        self.digital_ofdm_cyclic_prefixer_0 = digital.ofdm_cyclic_prefixer(
            {fft_points},
            {cyclic_prefix_str},
            0,
            '')
        self.blocks_multiply_const_xx_0 = blocks.multiply_const_cc(0.3, 1)
{resampler_block}


        ##################################################
        # Connections
        ##################################################
{resampler_connection}
        self.connect((self.digital_ofdm_cyclic_prefixer_0, 0), (self.dtv_dvbt2_p1insertion_cc_0, 0))
        self.connect((self.dtv_dvb_bbheader_bb_0, 0), (self.dtv_dvb_bbscrambler_bb_0, 0))
        self.connect((self.dtv_dvb_bbscrambler_bb_0, 0), (self.dtv_dvb_bch_bb_0, 0))
        self.connect((self.dtv_dvb_bch_bb_0, 0), (self.dtv_dvb_ldpc_bb_0, 0))
        self.connect((self.dtv_dvb_ldpc_bb_0, 0), (self.dtv_dvbt2_interleaver_bb_0, 0))
        self.connect((self.dtv_dvbt2_cellinterleaver_cc_0, 0), (self.dtv_dvbt2_framemapper_cc_0, 0))
        self.connect((self.dtv_dvbt2_framemapper_cc_0, 0), (self.dtv_dvbt2_freqinterleaver_cc_0, 0))
        self.connect((self.dtv_dvbt2_freqinterleaver_cc_0, 0), (self.dtv_dvbt2_pilotgenerator_cc_0, 0))
        self.connect((self.dtv_dvbt2_interleaver_bb_0, 0), (self.dtv_dvbt2_modulator_bc_0, 0))
        self.connect((self.dtv_dvbt2_modulator_bc_0, 0), (self.dtv_dvbt2_cellinterleaver_cc_0, 0))
        self.connect((self.dtv_dvbt2_p1insertion_cc_0, 0), (self.blocks_multiply_const_xx_0, 0))
        self.connect((self.dtv_dvbt2_pilotgenerator_cc_0, 0), (self.digital_ofdm_cyclic_prefixer_0, 0))
        self.connect((self.zeromq_sub_source_0, 0), (self.dtv_dvb_bbheader_bb_0, 0))



    def closeEvent(self, event):
        self.settings = Qt.QSettings("GNU Radio", "{class_name}")
        self.settings.setValue("geometry", self.saveGeometry())
        self.stop()
        self.wait()

        event.accept()




    # После существующих XML-RPC методов:

    def get_rf_gain(self):
        return self.rf_gain

    def set_rf_gain(self, rf_gain):
        self.rf_gain = rf_gain
        {gain_setup}

    def get_frequency(self):
        return self.frequency

    def set_frequency(self, frequency):
        self.frequency = frequency
        self.{sink_name}.set_frequency({'self.frequency' if use_iio else '0, self.frequency'})

    # ДОБАВЬТЕ ЭТИ ДВА МЕТОДА:
    def stop_transmission(self):
        """Stop the modulator gracefully"""
        print("[INFO] Stop command received via XML-RPC")
        self.stop()
        self.wait()
        Qt.QApplication.quit()
        return "Stopped successfully"
    
    def quit_application(self):
        """Quit the application"""
        print("[INFO] Quit command received")
        self.stop()
        self.wait()
        Qt.QApplication.quit()
        return "Application quit"


def main(top_block_cls={class_name}, options=None):

    qapp = Qt.QApplication(sys.argv)

    tb = top_block_cls()

    tb.start()

    tb.show()

    def sig_handler(sig=None, frame=None):
        tb.stop()
        tb.wait()

        Qt.QApplication.quit()

    signal.signal(signal.SIGINT, sig_handler)
    signal.signal(signal.SIGTERM, sig_handler)

    timer = Qt.QTimer()
    timer.start(500)
    timer.timeout.connect(lambda: None)

    qapp.exec_()

if __name__ == '__main__':
    main()
'''
            return script_template
            
        except Exception as e:
            self.parent.log_message(f"❌ Error generating GNU Radio script: {str(e)}", "buffer")
            import traceback
            self.parent.log_message(f"❌ Traceback: {traceback.format_exc()}", "buffer")
            return f"# Error generating script: {str(e)}\n# Traceback: {traceback.format_exc()}"
            
class MPCPlaylistManager:
    def __init__(self, parent):
        self.parent = parent
        self.setup_playlist_variables()
        
    def setup_playlist_variables(self):
        # Playlist variables
        self.media_folders = []
        self.bumper_files = []
        self.playlist_output_dir = tk.StringVar(value=os.getcwd())
        self.playlist_name = tk.StringVar(value="my_playlist.mpcpl")
        self.playlist_randomize = tk.BooleanVar(value=True)
        self.playlist_auto_start = tk.BooleanVar(value=False)
        self.mpc_player_path = tk.StringVar(value="mpc-hc64.exe")
        
    def create_playlist_tab(self, parent):
        """Create MPC Playlist tab"""
        playlist_frame = ttk.Frame(parent, padding="8")
        
        # Media folders section
        ttk.Label(playlist_frame, text="Media Folders:", font=('Arial', 10, 'bold')).grid(row=0, column=0, sticky='w', pady=(0, 5))
        
        self.media_listbox = tk.Listbox(playlist_frame, height=6, font=('Arial', 9))
        self.media_listbox.grid(row=1, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(0, 5))
        
        media_buttons_frame = ttk.Frame(playlist_frame)
        media_buttons_frame.grid(row=2, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(0, 10))
        
        ttk.Button(media_buttons_frame, text="Add Folder", 
                  command=self.add_media_folder, width=12).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(media_buttons_frame, text="Remove Selected", 
                  command=self.remove_media_folder, width=14).pack(side=tk.LEFT)
        
        # Bumper files section
        ttk.Label(playlist_frame, text="Bumper Files (inserted between media):", font=('Arial', 10, 'bold')).grid(row=3, column=0, sticky='w', pady=(10, 5))
        
        self.bumper_frame = ttk.Frame(playlist_frame)
        self.bumper_frame.grid(row=4, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(0, 5))
        
        self.bumper_widgets = []
        self.add_bumper_row()  # Add first bumper row by default
        
        ttk.Button(playlist_frame, text="Add Bumper", 
                  command=self.add_bumper_row, width=12).grid(row=5, column=0, sticky='w', pady=(0, 10))
        
        # Output settings
        ttk.Label(playlist_frame, text="Playlist Name:", font=('Arial', 10)).grid(row=6, column=0, sticky='w', pady=(10, 5))
        
        ttk.Entry(playlist_frame, textvariable=self.playlist_name, width=30, font=('Arial', 9)).grid(row=6, column=1, sticky='w', padx=5, pady=(10, 5))
        
        # MPC Player path
        ttk.Label(playlist_frame, text="MPC-HC Player Path:", font=('Arial', 10)).grid(row=7, column=0, sticky='w', pady=5)
        
        player_frame = ttk.Frame(playlist_frame)
        player_frame.grid(row=7, column=1, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        
        ttk.Entry(player_frame, textvariable=self.mpc_player_path, width=30, font=('Arial', 9)).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 3))
        ttk.Button(player_frame, text="Browse", 
                  command=self.browse_mpc_player, width=8).pack(side=tk.RIGHT)
        
        # Options
        options_frame = ttk.Frame(playlist_frame)
        options_frame.grid(row=8, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(0, 10))
        
        ttk.Checkbutton(options_frame, text="Randomize Playback Order", 
                       variable=self.playlist_randomize, 
                       command=self.parent.save_config).pack(side=tk.LEFT, padx=(0, 15))
        
        ttk.Checkbutton(options_frame, text="Auto-start Playlist", 
                       variable=self.playlist_auto_start, 
                       command=self.parent.save_config).pack(side=tk.LEFT)
        
        # Action buttons
        action_frame = ttk.Frame(playlist_frame)
        action_frame.grid(row=9, column=0, columnspan=3, pady=15)
        
        ttk.Button(action_frame, text="Create Playlist", 
                  command=self.create_playlist, width=15).pack(side=tk.LEFT, padx=(0, 10))
        
        ttk.Button(action_frame, text="Start Playback", 
                  command=self.start_playlist_playback, width=15).pack(side=tk.LEFT, padx=(0, 10))
        
        ttk.Button(action_frame, text="Randomize Now", 
                  command=self.randomize_files, width=15).pack(side=tk.LEFT)
        
        # Status
        self.playlist_status_var = tk.StringVar(value="Ready to create playlist")
        ttk.Label(playlist_frame, textvariable=self.playlist_status_var, 
                 font=('Arial', 9)).grid(row=10, column=0, columnspan=3, sticky='w', pady=(10, 0))
        
        # Configure grid weights
        playlist_frame.columnconfigure(1, weight=1)
        
        return playlist_frame

    def add_bumper_row(self):
        row_index = len(self.bumper_widgets)
        row_frame = ttk.Frame(self.bumper_frame)
        row_frame.grid(row=row_index, column=0, sticky=(tk.W, tk.E), pady=2)
        
        ttk.Label(row_frame, text=f"Bumper {row_index + 1}:", font=('Arial', 9)).pack(side=tk.LEFT)
        
        file_var = tk.StringVar()
        entry = ttk.Entry(row_frame, textvariable=file_var, width=50, font=('Arial', 9))
        entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(5, 5))
        
        ttk.Button(row_frame, text="Browse", 
                  command=lambda: self.browse_bumper_file(entry, file_var), width=8).pack(side=tk.RIGHT)
        
        if row_index > 0:  # Add remove button for additional bumpers
            ttk.Button(row_frame, text="Remove", 
                      command=lambda: self.remove_bumper_row(row_frame, file_var), width=8).pack(side=tk.RIGHT, padx=(5, 0))
        
        self.bumper_widgets.append((row_frame, file_var))
        
    def remove_bumper_row(self, row_frame, file_var):
        row_frame.destroy()
        self.bumper_widgets = [(f, v) for f, v in self.bumper_widgets if f != row_frame]
        self.update_bumper_numbers()
        
    def update_bumper_numbers(self):
        for i, (row_frame, file_var) in enumerate(self.bumper_widgets):
            for widget in row_frame.winfo_children():
                if isinstance(widget, ttk.Label):
                    widget.config(text=f"Bumper {i + 1}:")
        
    def browse_bumper_file(self, entry, file_var):
        filename = filedialog.askopenfilename(
            title="Select Bumper Video File",
            filetypes=[("Video files", "*.mp4 *.avi *.mkv *.mov *.wmv"), ("All files", "*.*")]
        )
        if filename:
            file_var.set(filename)
            
    def add_media_folder(self):
        folder = filedialog.askdirectory(title="Select Media Folder")
        if folder and folder not in self.media_folders:
            self.media_folders.append(folder)
            self.update_media_listbox()
            
    def remove_media_folder(self):
        selection = self.media_listbox.curselection()
        if selection:
            index = selection[0]
            self.media_folders.pop(index)
            self.update_media_listbox()
            
    def update_media_listbox(self):
        self.media_listbox.delete(0, tk.END)
        for folder in self.media_folders:
            self.media_listbox.insert(tk.END, folder)
            
    def browse_mpc_player(self):
        filename = filedialog.askopenfilename(
            title="Select MPC-HC Player",
            filetypes=[("Executable files", "*.exe"), ("All files", "*.*")]
        )
        if filename:
            self.mpc_player_path.set(filename)
            self.parent.save_config()
            
    def randomize_files(self):
        self.playlist_status_var.set("Files will be randomized when creating playlist")
        
    def get_video_files(self, folders):
        """Get all video files from specified folders recursively"""
        video_extensions = {'.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm', '.m4v', '.3gp'}
        video_files = []
        
        for folder in folders:
            for root, dirs, files in os.walk(folder):
                for file in files:
                    if Path(file).suffix.lower() in video_extensions:
                        video_files.append(os.path.join(root, file))
                        
        return video_files
    
    def get_bumper_files(self):
        """Get valid bumper files from the bumper widgets"""
        bumper_files = []
        for _, file_var in self.bumper_widgets:
            file_path = file_var.get().strip()
            if file_path and os.path.isfile(file_path):
                bumper_files.append(file_path)
        return bumper_files
    
    def create_playlist_content(self, video_files, bumper_files):
        """Create playlist content with proper structure"""
        playlist_content = ["MPCPLAYLIST"]
        
        entry_number = 1
        media_index = 0
        bumper_index = 0
        
        while media_index < len(video_files):
            # Add bumper if available
            if bumper_files and bumper_index < len(bumper_files):
                playlist_content.extend([
                    f"{entry_number},type,0",
                    f"{entry_number},filename,{bumper_files[bumper_index]}"
                ])
                entry_number += 1
                bumper_index += 1
                # Reset bumper index if we've used all bumpers
                if bumper_index >= len(bumper_files):
                    bumper_index = 0
            
            # Add media file
            playlist_content.extend([
                f"{entry_number},type,0", 
                f"{entry_number},filename,{video_files[media_index]}"
            ])
            entry_number += 1
            media_index += 1
        
        return playlist_content
    
    def create_playlist(self):
        try:
            if not self.media_folders:
                messagebox.showerror("Error", "Please add at least one media folder")
                return
                
            # Get all video files
            video_files = self.get_video_files(self.media_folders)
            if not video_files:
                messagebox.showerror("Error", "No video files found in the specified folders")
                return
                
            # Get bumper files
            bumper_files = self.get_bumper_files()
            
            # Randomize if requested
            if self.playlist_randomize.get():
                random.shuffle(video_files)
                
            # Create playlist content
            playlist_content = self.create_playlist_content(video_files, bumper_files)
            
            # Save playlist file in current directory
            output_path = os.path.join(os.getcwd(), self.playlist_name.get())
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write('\n'.join(playlist_content))
                
            self.playlist_status_var.set(f"Playlist created: {self.playlist_name.get()}")
            messagebox.showinfo("Success", 
                              f"Playlist created successfully!\n"
                              f"Files: {len(video_files)}\n"
                              f"Bumpers: {len(bumper_files)}\n"
                              f"Location: {output_path}")
            
            # Auto-start playback if enabled
            if self.playlist_auto_start.get():
                self.parent.root.after(2000, self.start_playlist_playback)
            
        except Exception as e:
            error_msg = f"Error creating playlist: {str(e)}"
            self.playlist_status_var.set(error_msg)
            messagebox.showerror("Error", error_msg)
            print(f"Playlist Error: {e}")
    
    def start_playlist_playback(self):
        """Start playback of the created playlist"""
        try:
            playlist_path = os.path.join(os.getcwd(), self.playlist_name.get())
            if not os.path.exists(playlist_path):
                messagebox.showerror("Error", "Playlist file doesn't exist. Please create it first.")
                return
            
            # Check if MPC player exists
            mpc_path = self.mpc_player_path.get()
            if not os.path.exists(mpc_path):
                # Try to open with default association
                self.parent.log_message(f"MPC player not found at {mpc_path}, trying default association", "buffer")
                subprocess.Popen([playlist_path], shell=True)
            else:
                # Open with specified MPC player
                subprocess.Popen([mpc_path, playlist_path])
            
            self.playlist_status_var.set("Playback started")
            self.parent.log_message(f"Started playlist playback: {self.playlist_name.get()}", "buffer")
            
        except Exception as e:
            error_msg = f"Error starting playback: {str(e)}"
            self.playlist_status_var.set(error_msg)
            messagebox.showerror("Error", error_msg)
            print(f"Playback Error: {e}")

class DVBT2EncoderGUI:

    def __init__(self, root):
        self.root = root
        self.root.title("R6WAX DVB-T2")
        # self.root.attributes('-alpha', 0.99)
        
        # # Настройка стиля
        # style = ttk.Style()
        # style.theme_use('clam')
        
        # # Основная цветовая схема
        # bg_color = '#2d2d2d'           # темно-серый фон
        # fg_color = '#e0e0e0'           # светло-серый текст
        # select_bg = '#404040'           # серый для выделенных полей
        # entry_bg = '#3a3a3a'            # фон полей ввода
        # button_bg = '#3c3c3c'           # фон кнопок
        # button_active = '#4a4a4a'       # кнопка при наведении
        # border_color = '#4a4a4a'        # цвет границ
        
        # # Общие настройки
        # style.configure('.', 
                       # background=bg_color,
                       # foreground=fg_color,
                       # fieldbackground=entry_bg,
                       # troughcolor=select_bg,
                       # selectbackground=select_bg,
                       # selectforeground=fg_color)
        
        # # Frame
        # style.configure('TFrame', background=bg_color)
        # style.configure('TLabelFrame', 
                       # background=bg_color,
                       # foreground=fg_color,
                       # bordercolor=border_color,
                       # lightcolor=border_color,
                       # darkcolor=border_color)
        
        # # Label
        # style.configure('TLabel', 
                       # background=bg_color,
                       # foreground=fg_color)
        
        # # Button
        # style.configure('TButton',
                       # background=button_bg,
                       # foreground=fg_color,
                       # bordercolor=border_color,
                       # focuscolor='none',
                       # lightcolor=button_bg,
                       # darkcolor=button_bg)
        # style.map('TButton',
                 # background=[('active', button_active),
                            # ('pressed', button_active),
                            # ('disabled', bg_color)],
                 # foreground=[('disabled', '#808080')])
        
        # # Entry
        # style.configure('TEntry',
                       # fieldbackground=entry_bg,
                       # foreground=fg_color,
                       # bordercolor=border_color,
                       # lightcolor=border_color,
                       # darkcolor=border_color)
        
        # # Combobox
        # style.configure('TCombobox',
                       # fieldbackground=entry_bg,
                       # foreground=fg_color,
                       # selectbackground=select_bg,
                       # selectforeground=fg_color,
                       # bordercolor=border_color,
                       # arrowcolor=fg_color)
        # style.map('TCombobox',
                 # fieldbackground=[('readonly', entry_bg)],
                 # selectbackground=[('readonly', select_bg)])
        
        # # Checkbutton
        # style.configure('TCheckbutton',
                       # background=bg_color,
                       # foreground=fg_color,
                       # focuscolor='none')
        # style.map('TCheckbutton',
                 # background=[('active', bg_color)],
                 # foreground=[('active', fg_color)])
        
        # # Scale (ползунок)
        # style.configure('TScale',
                       # background=bg_color,
                       # troughcolor=select_bg,
                       # bordercolor=border_color,
                       # lightcolor=border_color,
                       # darkcolor=border_color)
        
        # # Notebook (вкладки)
        # style.configure('TNotebook',
                       # background=bg_color,
                       # bordercolor=border_color,
                       # lightcolor=border_color,
                       # darkcolor=border_color)
        # style.configure('TNotebook.Tab',
                       # background=button_bg,
                       # foreground=fg_color,
                       # bordercolor=border_color,
                       # lightcolor=border_color,
                       # darkcolor=border_color)
        # style.map('TNotebook.Tab',
                 # background=[('selected', bg_color),
                            # ('active', button_active)],
                 # foreground=[('selected', fg_color)])
        
        # # Scrollbar
        # style.configure('TScrollbar',
                       # background=button_bg,
                       # bordercolor=border_color,
                       # arrowcolor=fg_color,
                       # troughcolor=bg_color)
        
        # # Прогрессбар
        # style.configure('TProgressbar',
                       # background=select_bg,
                       # troughcolor=bg_color,
                       # bordercolor=border_color)
        
        # # Дополнительно: настройка корневого окна
        # self.root.configure(bg=bg_color)       
        
        # Временные переменные для предотвращения ошибок
        self.emergency_file_path = tk.StringVar(value="")
        
        # Configuration file in script directory
        script_dir = os.path.dirname(os.path.abspath(__file__))
        self.config_file = os.path.join(script_dir, "dvbt2_encoder_config.json")
        print(f"🎯 Config will be saved to: {self.config_file}")        

        # Python paths
        self.gnuradio_python_path = tk.StringVar(value="")
        self.portable_python_path = os.path.join(os.path.dirname(__file__), "python_portable", "python.exe")
        self.obs_path = tk.StringVar(value="")
        
        # System paths from conf.cfg 
        self.ffmpeg_path_from_config = "ffmpeg.exe"  # значение по умолчанию
        self.dvbt2rate_path = "dvbt2rate.exe"
        self.conda_base_path = ""
                
        # системные пути из conf.cfg
        self.system_config_file = os.path.join(script_dir, "conf.cfg")
        self.load_system_paths_from_config()
        
        # Config autosave timer
        self._save_timer = None
        
        # Preset update timer
        self._preset_update_timer = None
                           
        # Initialize playlist manager
        self.playlist_manager = MPCPlaylistManager(self)
        
        # Initialize tips window
        self.tips_window = None
        
        # Initialize calculator
        self.calculator = DVBTCalculatorTab(self)
        
        # XML-RPC сервер GNU Radio
        self.server_url = "http://localhost:8001"
        self.connected = False
        self.server = None
        self.connection_status_var = tk.StringVar(value="❌ Disconnected")
        
        # Default window size
        self.default_geometry = "800x600"
        
        # Save window size setting
        self.save_window_size = tk.BooleanVar(value=False)
        
        # ZMQ СТАТИСТИКА
        self.bitrate_deviation = tk.StringVar(value="0.0%")
        self.real_zmq_output_rate = tk.StringVar(value="0.0")
                
        # Processes
        self.buffer_running = False
        self.buffer_thread = None
        self.is_streaming = False
        self.modulator_process = None
        self.modulator_running = False
        
        # Auto-start setting
        self.auto_start = tk.BooleanVar(value=False)
        self.streaming_auto_start = tk.BooleanVar(value=False)  # Эта должна быть
        
        # OBS Studio settings
        self.obs_auto_start = tk.BooleanVar(value=False)
        self.obs_process = None
        self.obs_running = False
        self.obs_status = tk.StringVar(value="Stopped")
        
        # Status variables
        self.encoder_status = tk.StringVar(value="Stopped")
        self.buffer_status = tk.StringVar(value="Stopped")
        self.modulator_status = tk.StringVar(value="Stopped")
        self.on_air_status = tk.StringVar(value="OFF AIR")
        self.overlay_status = tk.StringVar(value="Stopped")
        
        # Network settings - СО ЗНАЧЕНИЯМИ ПО УМОЛЧАНИЮ
        self.localhost_ip = tk.StringVar(value="127.0.0.1")
        self.output_ip = tk.StringVar(value="127.0.0.1")
        self.udp_input_port = tk.StringVar(value="3005")
        self.udp_output_port = tk.StringVar(value="8002")
        self.muxrate = tk.StringVar(value="8388080.355572")
        
        # RF Modulator settings - БЕЗ ЗНАЧЕНИЙ ПО УМОЛЧАНИЮ
        self.modulator_preset = tk.StringVar(value="1_7_MHz_256QAM_5_6_1K_1_16_PP1_8388kbps")
        self.modulator_auto_start = tk.BooleanVar(value=False)
        self.pluto_ip = tk.StringVar(value="192.168.80.70")
        self.frequency = tk.StringVar(value="431000000")
        self.frequency_mhz_var = tk.StringVar(value="431")
        self.rf_gain = tk.IntVar()
        self.rf_gain_percent = tk.IntVar(value="100")
        
        # НОВЫЕ ПЕРЕМЕННЫЕ ДЛЯ ВЫБОРА УСТРОЙСТВА
        self.selected_device = tk.StringVar(value="plutosdr")
        self.device_arguments = tk.StringVar()  # Текстовое поле для device args
        self.device_mode = tk.StringVar(value="uri=ip")  # Режим для pluto
                
        # Конфигурация устройств
        self.device_configs = {
            'plutosdr': {
                'name': 'PlutoSDR',
                'modes': ['ip:'],  # Только IP режим для PlutoSDR
                'default_ip': '192.168.80.70',
                'default_mode': 'ip:',
                'sink_name': 'iio_pluto_sink_0_0',
                'sink_type': 'pluto',  # Тип блока: 'pluto' или 'soapy'
                'gain_range': (0, 25),  # Для PlutoSDR attenuation: 0 dB (макс мощность) до 10 dB (мин мощность)
                'gain_setup': 'self.iio_pluto_sink_0_0.set_attenuation(0, self.rf_gain)',
                'freq_correction': False,
                'use_iio': True  # Флаг для использования IIO блока вместо Soapy
            },
            'limesdr': {
                'name': 'LimeSDR',
                'modes': ['soapy=0,driver=lime'],
                'default_ip': '',
                'default_mode': 'soapy=0,driver=lime',
                'sink_name': 'soapy_limesdr_sink_0',
                'sink_type': 'soapy',
                'gain_range': (30, 64),
                'gain_setup': 'self.soapy_limesdr_sink_0.set_gain(0, min(max(rf_gain, {min}), {max}))',
                'freq_correction': True,
                'freq_correction_line': 'self.soapy_limesdr_sink_0.set_frequency_correction(0, 0)',
                'use_iio': False
            },
            'hackrf': {
                'name': 'HackRF',
                'modes': ['soapy=0,driver=hackrf'],
                'default_ip': '',
                'default_mode': 'soapy=0,driver=hackrf',
                'sink_name': 'soapy_hackrf_sink_0',
                'sink_type': 'soapy',
                'gain_range': (30, 47),
                'gain_setup': '''self.soapy_hackrf_sink_0.set_gain(0, 'AMP', False)
            self.soapy_hackrf_sink_0.set_gain(0, 'VGA', min(max(rf_gain, {min}), {max}))''',
                'freq_correction': False,
                'use_iio': False
            },
            'usrp': {
                'name': 'USRP',
                'modes': ['None'],
                'default_ip': '',
                'default_mode': 'None',
                'sink_name': 'soapy_usrp_sink_0',
                'sink_type': 'soapy',
                'gain_range': (30, 50),
                'gain_setup': 'self.soapy_usrp_sink_0.set_gain(0, min(max(rf_gain, {min}), {max}))',
                'freq_correction': False,
                'use_iio': False
            }
        }        
        
        # RF Gain control variables
        self.rf_gain_timer = None
        self.frequency_timer = None
        
        # Buffer calculation variable
        self.buffer_divider = tk.IntVar(value=1)
        
        # Buffer statistics
        self.buffer_input_bitrate = tk.StringVar(value="0")
        self.buffer_output_bitrate = tk.StringVar(value="0")
        self.buffer_fill = tk.StringVar(value="0/0")
        self.buffer_dropped = tk.StringVar(value="0")
        self.buffer_received = tk.StringVar(value="0")
        self.buffer_sent = tk.StringVar(value="0")
        self.buffer_overflow = tk.StringVar(value="0")
        self.buffer_target = tk.StringVar(value="0")
        
        # Encoder statistics
        self.encoder_speed = tk.StringVar(value="---")
        self.encoder_bitrate = tk.StringVar(value="---")
        self.encoder_quality = tk.StringVar(value="---")
        self.stream_time = tk.StringVar(value="---")
        
        # Channel statistics storage
        self.channel_speed = {}  # {channel_num: StringVar}
        self.channel_bitrate = {}  # {channel_num: StringVar}
        self.channel_speed_labels = {}  # {channel_num: Label}
        self.channel_bitrate_labels = {}  # {channel_num: Label}
        self.channel_last_speed = {}  # {channel_num: float}
        self.channels_stats_container = None  # Будет создан в create_stats_tab
        self.channel_emergency_labels = {}  # {channel_num: Label} 
        
        # CPU statistics
        self.cpu_load = tk.StringVar(value="0%")
        
        # UDP Buffer settings
        self.target_buffer = tk.IntVar(value=8000)
        self.min_buffer = tk.IntVar(value=2000)
        self.max_buffer = tk.IntVar(value=100000)
        self.calibration_packets = tk.IntVar(value=8000)
        self.calibration_time = tk.DoubleVar(value=20)
        
        # Video settings - СО ЗНАЧЕНИЯМИ ПО УМОЛЧАНИЮ
        self.video_resolution = tk.StringVar(value="1920x1080")
        self.video_fps = tk.StringVar(value="30")
        self.video_gop = tk.StringVar(value="90")
        self.video_codec = tk.StringVar(value="libx265")
        self.video_bitrate = tk.StringVar(value="6662")
        self.video_bufsize = tk.StringVar(value="3331")
        self.video_preset = tk.StringVar(value="ultrafast")
        self.video_tune = tk.StringVar(value="animation")
        self.custom_options = tk.StringVar(value=" ")
        
        # Audio settings - СО ЗНАЧЕНИЯМИ ПО УМОЛЧАНИЮ
        self.audio_codec = tk.StringVar(value="aac")
        self.audio_bitrate = tk.StringVar(value="128k")
        self.audio_sample_rate = tk.StringVar(value="48000")
        self.audio_channels = tk.StringVar(value="stereo")

        # Window capture settings (НОВОЕ)
        self.available_windows = []  # список доступных окон
        
        # Input devices
        self.video_input_device = tk.StringVar(value="OBS Virtual Camera")
        self.audio_input_device = tk.StringVar(value="CABLE Output (VB-Audio Virtual Cable)")
        self.available_video_devices = []
        self.available_audio_devices = []
        
        # Metadata - СО ЗНАЧЕНИЯМИ ПО УМОЛЧАНИЮ
        self.service_name = tk.StringVar(value="CallSign")
        self.service_provider = tk.StringVar(value="DVB-T2 DATV")
        
        # Overlay settings
        self.overlay_enabled = tk.BooleanVar(value=False)
        self.overlay_auto_start = tk.BooleanVar(value=False)
        self.overlay_server = None
        self.overlay_thread = None
        
        # GUI elements that need to be initialized
        self.video_preset_combo = None
        self.overlay_start_btn = None
        self.overlay_stop_btn = None
        self.audio_channels_combo = None
        
        # Overlay display options
        self.overlay_stream_time = tk.BooleanVar(value=False)
        self.overlay_ts_bitrate = tk.BooleanVar(value=True)
        self.overlay_video_bitrate = tk.BooleanVar(value=True)
        self.overlay_speed = tk.BooleanVar(value=True)
        self.overlay_quality = tk.BooleanVar(value=True)
        self.overlay_cpu_load = tk.BooleanVar(value=True)
        self.overlay_video_codec = tk.BooleanVar(value=True)
        self.overlay_preset = tk.BooleanVar(value=True)
        self.overlay_audio_codec = tk.BooleanVar(value=True)
        self.overlay_audio_bitrate = tk.BooleanVar(value=True)
        self.overlay_buffer_input = tk.BooleanVar(value=True)
        self.overlay_buffer_output = tk.BooleanVar(value=True)
        self.overlay_buffer_fill = tk.BooleanVar(value=False)
        self.overlay_modulation = tk.BooleanVar(value=True)
        
        # Codec presets and tunes
        self.codec_presets = {
            "libx265": ["ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow", "slower", "veryslow"],
            "hevc_nvenc": ["p1", "p2", "p3", "p4", "p5", "p6", "p7"],
            "h264_nvenc": ["p1", "p2", "p3", "p4", "p5", "p6", "p7"],
            "h264_amf": ["speed", "balanced", "quality"],
            "hevc_amf": ["speed", "balanced", "quality"]
        }
        
        self.codec_tunes = {
            "libx265": ["animation", "film", "grain", "fastdecode", "zerolatency", "psnr", "ssim"],
            "hevc_nvenc": ["hq", "ll", "ull", "lossless"],
            "h264_nvenc": ["hq", "ll", "ull", "lossless"],
            "h264_amf": [],
            "hevc_amf": []
        }
        
        # Audio codec settings
        self.audio_codecs = ["aac", "ac3", "mp2", "mp3", "eac3"]
        self.audio_bitrates = ["32k", "48k", "64k", "96k", "128k", "192k", "256k", "320k"]
        self.audio_sample_rates = ["48000", "44100", "32000", "22050"]
        self.audio_channels_options = {
            "aac": ["mono", "stereo", "5.1"],
            "ac3": ["mono", "stereo", "5.1"],
            "eac3": ["mono", "stereo", "5.1"],
            "mp2": ["mono", "stereo"],
            "mp3": ["mono", "stereo"]
        }
        
        # Modulator presets - ПУСТОЙ СЛОВАРЬ
        self.modulator_presets = {}
        
        # Buffer variables
        self.stats = {
            'received': 0,
            'sent': 0,
            'dropped': 0,
            'buffer_overflow': 0,
            'last_check': time.time(),
            'input_bitrate': 0,
            'output_bitrate': 0
        }
                
        # Multiplex settings
        self.multiplex_channels = OrderedDict()  # Хранит данные о каналах
        self.max_channels = 10        
        
        # Multiplex mode
        self.multiplex_mode = tk.BooleanVar(value=False)  # НОВАЯ ПЕРЕМЕННАЯ        
        self.multiplex_mode.trace_add('write', self.on_multiplex_mode_changed)
        
        # Load saved configuration
        self.load_config()
        
        # После load_config()
        print(f"DEBUG: emergency_file_path after load: '{self.emergency_file_path.get()}'")
        
        self.create_gui()        
                
        # Load multiplex channels after GUI is created
        self.root.after(500, self.load_multiplex_channels)
        
        # Инициализация UI статистики после загрузки каналов
        self.root.after(1000, self.init_channels_stats_ui)
        
        # После создания GUI добавляем обработчик переключения вкладок
        self.root.bind('<<NotebookTabChanged>>', self.on_tab_changed)
        
        self.root.after(500, self.sync_calculator_with_preset)        
       
        # Setup config autosave
        self.setup_config_autosave()      
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)        

        # ⚡ ДОБАВЛЕНО: Проверяем статус OBS Studio при запуске
        if self.is_obs_running_system():
            self.obs_running = True
            self.obs_status.set("Running")
            self.obs_start_btn.config(state='disabled')
            self.obs_stop_btn.config(state='normal')

        # after load_config()
        if not self.obs_path.get():
            self.auto_find_obs()

        self.root.bind('<Configure>', self.on_window_configure)        
            
        self.root.after(100, self.finish_playlist_setup)
                
        # Инициализируем переменные для отслеживания метаданных
        for i in range(1, 5):
            setattr(self, f'last_metadata_ch{i}', "") 
            
        # Состояния канала
        self.CHANNEL_STATE_ACTIVE = 'active'      # Работает оригинальный процесс
        self.CHANNEL_STATE_FAILED = 'failed'      # Упал, играет заставка

        # Данные каналов
        self.channel_states = {}  # {channel_num: state}
        self.channel_fail_time = {}  # {channel_num: timestamp}
        self.channel_individual_emergency = {}  # {channel_num: process}
        self.channel_check_timers = {}          # {channel_num: timer_id}
        self.channel_recovery_count = {}        # {channel_num: success_count}
        self.channel_fail_count = {}        # {channel_num: count}
        self.channel_long_check = {}        # {channel_num: bool}
        self.channel_long_results = {}  # {channel_num: [bool, bool, bool, bool, bool]}
        self.channel_long_cooldown = {}  # {channel_num: bool}

        # Window recovery tracking (НОВОЕ)
        self.window_search_state = {}  # {channel_num: {'attempts': int, 'last_search': time, 'original_title': str}}
        self.window_search_intervals = [10, 30, 60, 120, 300]  # интервалы между попытками (секунд)
        
        # Speed monitoring for auto-restart (НОВЫЕ ПЕРЕМЕННЫЕ)
        self.main_speed_history = []  # история скоростей основного мультиплексора
        self.speed_restart_threshold = 0.950  # порог для перезапуска
        self.speed_restart_count = 8  # сколько раз подряд ниже порога для перезапуска
        self.speed_restart_cooldown = 0  # время последнего перезапуска
        self.speed_restart_cooldown_seconds = 30  # не перезапускать чаще чем раз в 30 секунд
                         
        # Для отслеживания порядка фильтров
        self.channel_filter_indices = {}  # {channel_num: filter_index} 
        
        # Multi-process system variables
        self.channel_processes = {}  # {channel_num: {'process': subprocess, 'pid': int, 'stdin': pipe, 'port': int, 'is_radio': bool, 'is_emergency': bool}}
        self.emergency_process = None  # Emergency stream process
        self.emergency_stream_url = "udp://@238.0.0.1:3033"  # Fixed emergency port
        self.base_multicast_port = 3020  # Starting port for channels
        self.main_multiplexer_process = None  # Main multiplexer process 
        
        # Start OBS monitoring
        self.check_obs_status()
        
        # Auto-start if enabled with delay
        if self.auto_start.get():
            self.root.after(3000, self.delayed_start)
            
    def on_device_change(self, event=None):
        """Handle device selection change"""
        device = self.selected_device.get()
        config = self.device_configs[device]
        
        # Скрываем Mode combo (он нам не нужен)
        if hasattr(self, 'device_mode_label'):
            self.device_mode_label.grid_remove()
        if hasattr(self, 'device_mode_combo'):
            self.device_mode_combo.grid_remove()
        
        # Для PlutoSDR показываем ip:адрес в Device Args
        if device == 'plutosdr':
            pluto_ip = self.pluto_ip.get() if self.pluto_ip.get() else config['default_ip']
            self.device_arguments.set(f'ip:{pluto_ip}')
        else:
            # Для других устройств - стандартные аргументы
            self.device_arguments.set(config['default_mode'])
        
        # Обновляем RF Gain диапазон
        self.update_rf_gain_range()
        
        self.save_config()
        self.update_preset_script()
        self.on_preset_change()

    def update_rf_gain_range(self):
        """Update RF gain range based on selected device"""
        device = self.selected_device.get()
        config = self.device_configs[device]
        
        # Можно обновить отображение диапазона на GUI
        min_gain, max_gain = config['gain_range']
        self.log_message(f"Device {device} gain range: {min_gain} to {max_gain} dB", "buffer")            
            
    def get_device_arguments(self):
        """Get formatted device arguments based on selected device and mode"""
        device = self.selected_device.get()
        config = self.device_configs[device]
        
        if device == 'plutosdr':
            # Извлекаем IP из device_arguments (формат: ip:192.168.80.70)
            args = self.device_arguments.get().strip()
            if args.startswith('ip:'):
                ip_part = args[3:].strip()  # Убираем "ip:" и берем адрес
                if ip_part:
                    self.pluto_ip.set(ip_part)  # Синхронизируем с pluto_ip
                    return args
            # Fallback
            pluto_ip = self.pluto_ip.get().strip()
            return f'ip:{pluto_ip}' if pluto_ip else f'ip:{config["default_ip"]}'
        else:
            # Для других устройств - возвращаем device_arguments как есть
            args = self.device_arguments.get().strip()
            return args if args else config['default_mode']

    def update_preset_script(self):
        """Update all Python preset files with current values"""
        try:
            # Получаем текущие значения из GUI
            script_path = None  # Будет использоваться для каждого файла
            frequency = int(self.frequency.get())
            rf_gain = self.convert_rf_gain_to_modulator(self.rf_gain_percent.get())
            device_args = self.get_device_arguments()
            
            # ПУТЬ К ПАПКЕ С ПРЕСЕТАМИ
            script_dir = os.path.dirname(os.path.abspath(__file__))
            preset_dir = os.path.join(script_dir, "gnu_modulator_presets")
            
            if not os.path.exists(preset_dir):
                self.log_message(f"❌ Directory not found: {preset_dir}", "buffer")
                return
                
            # Находим все .py файлы
            py_files = []
            for file in os.listdir(preset_dir):
                if file.endswith('.py'):
                    py_files.append(os.path.join(preset_dir, file))
                    
            if not py_files:
                self.log_message(f"⚠️ No .py files found in {preset_dir}", "buffer")
                return
                
            self.log_message(f"🔄 Updating {len(py_files)} presets:", "buffer")
            self.log_message(f"  Device: {self.selected_device.get()}", "buffer")
            self.log_message(f"  Frequency: {frequency} Hz", "buffer")
            self.log_message(f"  RF Gain: {rf_gain} dB", "buffer")
            
            updated_count = 0
            for py_file in py_files:
                try:
                    preset_name = os.path.basename(py_file)
                    self.log_message(f"  📝 Updating: {preset_name}", "buffer")
                    
                    # Вызываем оригинальную функцию с 4 аргументами
                    self.update_preset_script_internal(py_file, frequency, rf_gain, device_args)
                    updated_count += 1
                except Exception as e:
                    self.log_message(f"  ❌ Error updating {preset_name}: {e}", "buffer")
                    
            self.log_message(f"✅ Updated {updated_count}/{len(py_files)} presets", "buffer")
            
        except Exception as e:
            self.log_message(f"❌ Error in update_preset_script: {e}", "buffer")

    def update_preset_script_internal(self, script_path, frequency, rf_gain, device_args):
        """Update frequency, gain and device args in a Python preset script"""
        try:
            with open(script_path, 'rb') as f:
                content = f.read()
            
            text = content.decode('utf-8', errors='ignore')
            lines = text.split('\n')
            
            updated = False
            device = self.selected_device.get()
            config = self.device_configs[device]
            use_iio = config.get('use_iio', False)
            sink_name = config['sink_name']
            min_gain, max_gain = config['gain_range']
            
            # Определяем, нужно ли добавлять rational resampler для HackRF
            add_resampler = (device == 'hackrf')
            
            # ЗАМЕНА ИМПОРТОВ
            for i, line in enumerate(lines):
                if 'from gnuradio import soapy' in line and use_iio:
                    lines[i] = 'from gnuradio import iio'
                    updated = True
                elif 'from gnuradio import iio' in line and not use_iio:
                    lines[i] = 'from gnuradio import soapy'
                    updated = True
                    
            # УПРАВЛЕНИЕ ИМПОРТОМ FILTER
            # Находим строку с импортом filter
            filter_import_index = -1
            for i, line in enumerate(lines):
                if 'from gnuradio import filter' in line:
                    filter_import_index = i
                    break
            
            if add_resampler:
                # Добавляем импорт filter если нужен и его нет
                if filter_import_index == -1:
                    # Находим строку с импортом soapy/iio и добавляем после нее
                    for i, line in enumerate(lines):
                        if 'from gnuradio import soapy' in line or 'from gnuradio import iio' in line:
                            lines.insert(i+1, 'from gnuradio import filter')
                            updated = True
                            break
            else:
                # Удаляем импорт filter если не нужен
                if filter_import_index != -1:
                    del lines[filter_import_index]
                    updated = True
            
            # ОБНОВЛЕНИЕ ПЕРЕМЕННЫХ sample rate
            # Получаем bandwidth из скрипта
            device_bandwidth = 8000000  # Значение по умолчанию
            for i, line in enumerate(lines):
                if 'self.bandwidth = bandwidth =' in line:
                    try:
                        parts = line.split('=')
                        if len(parts) >= 3:
                            device_bandwidth = int(parts[2].strip())
                    except:
                        pass
            
            # Обновляем sample rate для HackRF
            if add_resampler:
                bandwidth_to_sample_rate = {
                    1845070: 3000000,   # 1.7 MHz
                    5714285: 9000000,   # 5 MHz
                    6857142: 10000000,  # 6 MHz
                    8000000: 11000000,  # 7 MHz
                    9142857: 12000000,  # 8 MHz
                    11428571: 14000000  # 10 MHz
                }
                
                hackrf_sample_rate = bandwidth_to_sample_rate.get(device_bandwidth, 11000000)
            
            # ОБНОВЛЕНИЕ ПЕРЕМЕННЫХ
            for i, line in enumerate(lines):
                # Обновляем RF gain
                if 'self.rf_gain = rf_gain =' in line:
                    lines[i] = f"        self.rf_gain = rf_gain = {rf_gain}"
                    updated = True
                
                # Обновляем device arguments / pluto_ip
                elif 'self.pluto_ip = pluto_ip =' in line or 'self.device_args = device_args =' in line:
                    if use_iio:
                        lines[i] = f'        self.pluto_ip = pluto_ip = "{device_args}"'
                    else:
                        lines[i] = f'        self.device_args = device_args = "{device_args}"'
                    updated = True
                
                # Обновляем частоту
                elif 'self.frequency = frequency =' in line:
                    lines[i] = f"        self.frequency = frequency = {frequency}"
                    updated = True
                
                # Обновляем sample rate для HackRF
                elif 'self.sample = sample =' in line and add_resampler:
                    lines[i] = f"        self.sample = sample = {hackrf_sample_rate}"
                    updated = True
                elif 'self.sample = sample =' in line and not add_resampler:
                    # Восстанавливаем оригинальный sample rate
                    bandwidth_to_clock_rate = {
                        1845070: 1845070,   # 1.7 MHz
                        5714285: 5714285,   # 5 MHz
                        6857142: 6857142,   # 6 MHz
                        8000000: 8000000,   # 7 MHz
                        9142857: 9142857,   # 8 MHz
                        11428571: 11428571  # 10 MHz
                    }
                    clock_rate = bandwidth_to_clock_rate.get(device_bandwidth, 8000000)
                    lines[i] = f"        self.sample = sample = {clock_rate}"
                    updated = True
            
            # УПРАВЛЕНИЕ БЛОКОМ RATIONAL RESAMPLER            
            # УПРАВЛЕНИЕ БЛОКОМ RATIONAL RESAMPLER
            # Находим блок rational resampler
            resampler_start = -1
            resampler_end = -1
            
            for i, line in enumerate(lines):
                if 'self.rational_resampler_xxx_0' in line and 'filter.rational_resampler_ccc' in line:
                    resampler_start = i
                    # Ищем конец блока (ищем закрывающую скобку)
                    for j in range(i, min(i+10, len(lines))):
                        if ')' in lines[j] and lines[j].strip().endswith(')'):
                            resampler_end = j + 1
                            break
                    if resampler_end == -1:
                        resampler_end = i + 5
                    break
            
            # Если нужно добавить блок rational resampler для HackRF
            if add_resampler:
                # Расчет коэффициентов для resampler
                bandwidth_to_interpolation = {
                    1845070: (3000000, 1845070),   # 1.7 MHz
                    5714285: (9000000, 5714285),   # 5 MHz
                    6857142: (10000000, 6857142),  # 6 MHz
                    8000000: (11000000, 8000000),  # 7 MHz
                    9142857: (12000000, 9142857),  # 8 MHz
                    11428571: (14000000, 11428571) # 10 MHz
                }
                
                interpolation, decimation = bandwidth_to_interpolation.get(device_bandwidth, (11000000, 8000000))
                
                from math import gcd
                g = gcd(interpolation, decimation)
                interp = interpolation // g
                decim = decimation // g
                
                # Ограничиваем коэффициенты разумными значениями
                #while interp > 100 or decim > 100:
                   # g *= 2
                    #interp = interpolation // g
                    #decim = decimation // g
                
                if resampler_start != -1:
                    # Заменяем существующий блок
                    new_resampler_block = [
                        f"        self.rational_resampler_xxx_0 = filter.rational_resampler_ccc(",
                        f"            interpolation={interp},",
                        f"            decimation={decim},",
                        f"            taps=[],",
                        f"            fractional_bw=0.45)"
                        
                    ]
                    
                    del lines[resampler_start:resampler_end]
                    for j, new_line in enumerate(new_resampler_block):
                        lines.insert(resampler_start + j, new_line)
                else:
                    # Добавляем новый блок после blocks_multiply_const_xx_0
                    for i, line in enumerate(lines):
                        if 'self.blocks_multiply_const_xx_0 =' in line:
                            insert_pos = i + 1
                            
                            new_resampler_block = [
                                f"",
                                f"        self.rational_resampler_xxx_0 = filter.rational_resampler_ccc(",
                                f"            interpolation={interp},",
                                f"            decimation={decim},",
                                f"            taps=[],",
                                f"            fractional_bw=0.45)",
                                
                            ]
                            
                            for j, new_line in enumerate(new_resampler_block):
                                lines.insert(insert_pos + j, new_line)
                            break
                
                updated = True
            elif resampler_start != -1:
                # Удаляем блок rational resampler если не нужен (для не-HackRF устройств)
                # Находим все связанные строки
                start_idx = resampler_start
                end_idx = resampler_end
                
                # Расширяем вверх, чтобы захватить пустые строки перед блоком
                while start_idx > 0 and lines[start_idx - 1].strip() == '':
                    start_idx -= 1
                
                # Расширяем вниз, чтобы захватить пустые строки после блока
                while end_idx < len(lines) and (lines[end_idx].strip() == '' or 
                       'rational_resampler_xxx_0' in lines[end_idx]):
                    end_idx += 1
                
                # Удаляем весь блок с окружающими пустыми строками
                del lines[start_idx:end_idx]
                updated = True
            
            # ОБНОВЛЕНИЕ СОЕДИНЕНИЙ ДЛЯ RESAMPLER

            # ПРОСТОЙ ВАРИАНТ - ПОЛНАЯ ПЕРЕЗАПИСЬ СЕКЦИИ СОЕДИНЕНИЙ
            # Находим и полностью удаляем старую секцию Connections
            start_idx = -1
            end_idx = -1
            
            for i in range(len(lines)):
                if '##################################################' in lines[i] and i+1 < len(lines) and '# Connections' in lines[i+1]:
                    start_idx = i
                    # Ищем где заканчивается метод closeEvent или начинается новый def
                    for j in range(i, len(lines)):
                        if lines[j].strip().startswith('def ') or lines[j].strip().startswith('class '):
                            # Проверяем, не является ли это концом секции
                            if j > i + 5:  # Секция должна быть хотя бы из 5 строк
                                end_idx = j
                                break
                    
                    if end_idx == -1:
                        # Ищем до следующего заголовка с решетками
                        for j in range(i+3, len(lines)):
                            if '##################################################' in lines[j]:
                                # Проверяем, что после этого идет не просто еще один заголовок
                                if j+1 < len(lines) and not '##################################################' in lines[j+1]:
                                    end_idx = j
                                    break
                    
                    if end_idx == -1:
                        end_idx = len(lines)
                    
                    break
            
            # Если нашли секцию, полностью перезаписываем
            if start_idx != -1:
                # Сохраняем строки до и после секции
                before_section = lines[:start_idx]
                after_section = lines[end_idx:] if end_idx != -1 else []
                
                # СОЗДАЕМ НОВУЮ СЕКЦИЮ
                new_section = []
                
                # Заголовок
                new_section.append("        ##################################################")
                new_section.append("        # Connections")
                new_section.append("        ##################################################")
                new_section.append("")
                
                # Основные соединения
                if add_resampler:
                    new_section.append("        self.connect((self.blocks_multiply_const_xx_0, 0), (self.rational_resampler_xxx_0, 0))")
                    new_section.append("        self.connect((self.rational_resampler_xxx_0, 0), (self.{sink_name}, 0))".format(sink_name=sink_name))
                else:
                    new_section.append("        self.connect((self.blocks_multiply_const_xx_0, 0), (self.{sink_name}, 0))".format(sink_name=sink_name))
                
                # Стандартные соединения DVB-T2 (заранее известные)
                standard_connections = [
                    "        self.connect((self.digital_ofdm_cyclic_prefixer_0, 0), (self.dtv_dvbt2_p1insertion_cc_0, 0))",
                    "        self.connect((self.dtv_dvb_bbheader_bb_0, 0), (self.dtv_dvb_bbscrambler_bb_0, 0))",
                    "        self.connect((self.dtv_dvb_bbscrambler_bb_0, 0), (self.dtv_dvb_bch_bb_0, 0))",
                    "        self.connect((self.dtv_dvb_bch_bb_0, 0), (self.dtv_dvb_ldpc_bb_0, 0))",
                    "        self.connect((self.dtv_dvb_ldpc_bb_0, 0), (self.dtv_dvbt2_interleaver_bb_0, 0))",
                    "        self.connect((self.dtv_dvbt2_cellinterleaver_cc_0, 0), (self.dtv_dvbt2_framemapper_cc_0, 0))",
                    "        self.connect((self.dtv_dvbt2_framemapper_cc_0, 0), (self.dtv_dvbt2_freqinterleaver_cc_0, 0))",
                    "        self.connect((self.dtv_dvbt2_freqinterleaver_cc_0, 0), (self.dtv_dvbt2_pilotgenerator_cc_0, 0))",
                    "        self.connect((self.dtv_dvbt2_interleaver_bb_0, 0), (self.dtv_dvbt2_modulator_bc_0, 0))",
                    "        self.connect((self.dtv_dvbt2_modulator_bc_0, 0), (self.dtv_dvbt2_cellinterleaver_cc_0, 0))",
                    "        self.connect((self.dtv_dvbt2_p1insertion_cc_0, 0), (self.blocks_multiply_const_xx_0, 0))",
                    "        self.connect((self.dtv_dvbt2_pilotgenerator_cc_0, 0), (self.digital_ofdm_cyclic_prefixer_0, 0))",
                    "        self.connect((self.zeromq_sub_source_0, 0), (self.dtv_dvb_bbheader_bb_0, 0))"
                ]
                
                # Добавляем стандартные соединения
                for conn in standard_connections:
                    new_section.append(conn)
                
                # Собираем файл заново
                lines = before_section + new_section + after_section
                updated = True
            
            
            # ПОЛНАЯ ЗАМЕНА БЛОКА SINK
            # Находим ВСЕ блоки sink и удаляем их
            sink_blocks_to_remove = []
            
            # Ищем все блоки sink в файле
            i = 0
            while i < len(lines):
                line = lines[i]
                if (('self.iio_pluto_sink' in line or 
                     'self.soapy_' in line and '_sink' in line) and 
                    '=' in line and 'self.' in line):
                    
                    # Находим начало блока
                    block_start = i
                    block_end = -1
                    
                    # Ищем конец блока sink (до следующего self. или пустой строки)
                    for j in range(i+1, min(i+20, len(lines))):
                        current_line = lines[j]
                        # Конец блока - когда начинается следующий блок или секция
                        if (current_line.strip().startswith('self.') and 
                            not ('self.iio_pluto_sink' in current_line or 
                                 'self.soapy_' in current_line and '_sink' in current_line)):
                            block_end = j
                            break
                        # Или если начинается секция Connections
                        elif '# Connections' in current_line:
                            block_end = j
                            break
                        # Или если пустая строка с последующим началом другого блока
                        elif current_line.strip() == '' and j+1 < len(lines):
                            next_line = lines[j+1]
                            if (next_line.strip().startswith('self.') and 
                                not ('self.iio_pluto_sink' in next_line or 
                                     'self.soapy_' in next_line and '_sink' in next_line)):
                                block_end = j
                                break
                    
                    if block_end == -1:
                        block_end = min(i + 20, len(lines))
                    
                    sink_blocks_to_remove.append((block_start, block_end))
                    i = block_end  # Пропускаем обработанный блок
                else:
                    i += 1
            
            # Удаляем все найденные sink блоки (в обратном порядке)
            for start, end in sorted(sink_blocks_to_remove, reverse=True):
                del lines[start:end]
                updated = True
            
            # Теперь добавляем ТОЛЬКО ОДИН правильный блок sink
            insert_position = -1
            for i, line in enumerate(lines):
                if 'self.zeromq_sub_source_0 =' in line:
                    # Вставляем после ZMQ source
                    insert_position = i + 1
                    # Ищем конец блока zeromq
                    for j in range(i+1, len(lines)):
                        if lines[j].strip() == '' or lines[j].strip().startswith('self.'):
                            insert_position = j
                            break
                    break
            
            if insert_position == -1:
                # Если не нашли ZMQ, ищем после XML-RPC блока
                for i, line in enumerate(lines):
                    if 'self.xmlrpc_server_0_thread.start()' in line:
                        insert_position = i + 1
                        break
            
            if insert_position == -1:
                insert_position = len(lines)
            
            # Создаем новый sink блок
            if use_iio:
                # PlutoSDR IIO блок
                new_sink_block = [
                    "",
                    f"        self.{sink_name} = iio.fmcomms2_sink_fc32(pluto_ip if pluto_ip else iio.get_pluto_uri(), [True, True], 32768, False)",
                    f"        self.{sink_name}.set_len_tag_key('')",
                    f"        self.{sink_name}.set_bandwidth(bandwidth)",
                    f"        self.{sink_name}.set_frequency(frequency)",
                    f"        self.{sink_name}.set_samplerate(sample)",
                    f"        self.{sink_name}.set_attenuation(0, rf_gain)",
                    f"        self.{sink_name}.set_filter_params('Auto', '', 0, 0)",
                    ""
                ]
            else:
                # Soapy блок
                new_sink_block = [
                    "",
                    f"        self.{sink_name} = None",
                    f"        dev = 'driver={device}'",
                    f"        stream_args = ''",
                    f"        tune_args = ['']",
                    f"        settings = ['']",
                    f"",
                    f"        self.{sink_name} = soapy.sink(dev, \"fc32\", 1, device_args,",
                    f"                                         stream_args, tune_args, settings)",
                    f"        self.{sink_name}.set_sample_rate(0, sample)",
                    f"        self.{sink_name}.set_bandwidth(0, bandwidth)",
                    f"        self.{sink_name}.set_frequency(0, frequency)"
                ]
                
                # Добавляем frequency correction для LimeSDR
                if device == 'limesdr':
                    new_sink_block.append(f"        self.{sink_name}.set_frequency_correction(0, 0)")
                
                # Добавляем gain init
                if device == 'hackrf':
                    new_sink_block.extend([
                        f"        self.{sink_name}.set_gain(0, 'AMP', False)",
                        f"        self.{sink_name}.set_gain(0, 'VGA', min(max(rf_gain, {min_gain}), {max_gain}))"
                    ])
                else:
                    new_sink_block.append(f"        self.{sink_name}.set_gain(0, min(max(rf_gain, {min_gain}), {max_gain}))")
                
                new_sink_block.append("")
            
            # Вставляем новый sink блок
            for j, new_line in enumerate(new_sink_block):
                lines.insert(insert_position + j, new_line)
            
            updated = True
            # УДАЛЕНИЕ СТАРЫХ СТРОК GAIN SETUP, КОТОРЫЕ МОГЛИ ОСТАТЬСЯ
            # Эти строки могут остаться после смены устройства
            gain_lines_to_remove = []
            for i, line in enumerate(lines):
                # Ищем строки с set_gain которые не относятся к текущему sink
                if '.set_gain' in line or '.set_attenuation' in line:
                    # Проверяем, относится ли строка к текущему sink
                    if sink_name not in line:
                        gain_lines_to_remove.append(i)
            
            # Удаляем в обратном порядке
            for idx in sorted(gain_lines_to_remove, reverse=True):
                # Проверяем соседние строки на пустоту и удаляем их тоже
                start_del = idx
                end_del = idx + 1
                
                # Проверяем пустую строку перед
                if start_del > 0 and lines[start_del - 1].strip() == '':
                    start_del -= 1
                
                # Проверяем пустую строку после
                if end_del < len(lines) and lines[end_del].strip() == '':
                    end_del += 1
                
                del lines[start_del:end_del]
                updated = True
                print(f"DEBUG: Removed old gain line at {idx}")            
            # ОБНОВЛЕНИЕ XML-RPC МЕТОДОВ set_rf_gain и set_frequency
            for i, line in enumerate(lines):
                if 'def set_rf_gain(self, rf_gain):' in line:
                    # Находим тело метода (до следующего def или пустой строки с отступом)
                    method_start = i
                    method_end = -1
                    
                    for j in range(i+1, len(lines)):
                        if lines[j].strip().startswith('def ') or (lines[j].strip() == '' and j+1 < len(lines) and lines[j+1].strip().startswith('def ')):
                            method_end = j
                            break
                    
                    if method_end == -1:
                        method_end = len(lines)
                    
                    # Полностью заменяем метод
                    if use_iio:
                        new_method = [
                            "    def set_rf_gain(self, rf_gain):",
                            f"        self.rf_gain = rf_gain",
                            f"        self.{sink_name}.set_attenuation(0, self.rf_gain)"
                        ]
                    elif device == 'hackrf':
                        new_method = [
                            "    def set_rf_gain(self, rf_gain):",
                            f"        self.rf_gain = rf_gain",
                            f"        self.{sink_name}.set_gain(0, 'AMP', False)",
                            f"        self.{sink_name}.set_gain(0, 'VGA', min(max(self.rf_gain, {min_gain}), {max_gain}))"
                        ]
                    else:
                        new_method = [
                            "    def set_rf_gain(self, rf_gain):",
                            f"        self.rf_gain = rf_gain",
                            f"        self.{sink_name}.set_gain(0, min(max(self.rf_gain, {min_gain}), {max_gain}))"
                        ]
                    
                    # Удаляем старый метод и вставляем новый
                    del lines[method_start:method_end]
                    for j, new_line in enumerate(new_method):
                        lines.insert(method_start + j, new_line)
                    
                    updated = True
                
                elif 'def set_frequency(self, frequency):' in line:
                    # Находим тело метода
                    method_start = i
                    method_end = -1
                    
                    for j in range(i+1, len(lines)):
                        if lines[j].strip().startswith('def ') or (lines[j].strip() == '' and j+1 < len(lines) and lines[j+1].strip().startswith('def ')):
                            method_end = j
                            break
                    
                    if method_end == -1:
                        method_end = len(lines)
                    
                    # Полностью заменяем метод
                    if use_iio:
                        new_method = [
                            "    def set_frequency(self, frequency):",
                            f"        self.frequency = frequency",
                            f"        self.{sink_name}.set_frequency(self.frequency)"
                        ]
                    else:
                        new_method = [
                            "    def set_frequency(self, frequency):",
                            f"        self.frequency = frequency",
                            f"        self.{sink_name}.set_frequency(0, self.frequency)"
                        ]
                    
                    # Удаляем старый метод и вставляем новый
                    del lines[method_start:method_end]
                    for j, new_line in enumerate(new_method):
                        lines.insert(method_start + j, new_line)
                    
                    updated = True
            # ДОПОЛНИТЕЛЬНАЯ ОЧИСТКА: УДАЛЯЕМ ЛИШНИЕ СОЕДИНЕНИЯ С MULTIPLY_CONST И RESAMPLER
            # После всех изменений проверяем, нет ли дубликатов
            multiply_const_count = 0
            resampler_count = 0
            sink_connection_count = 0
            
            for i, line in enumerate(lines):
                if 'self.connect((self.blocks_multiply_const_xx_0, 0),' in line:
                    multiply_const_count += 1
                if 'rational_resampler_xxx_0' in line and 'self.connect' in line:
                    resampler_count += 1
                if sink_name in line and 'self.connect' in line and 'self.blocks_multiply_const_xx_0' in line:
                    sink_connection_count += 1
            
            print(f"DEBUG: Final counts - multiply_const: {multiply_const_count}, resampler: {resampler_count}, sink: {sink_connection_count}")
            
            # Если есть дубликаты, удаляем лишние
            if multiply_const_count > 1 or resampler_count > 2 or sink_connection_count > 1:
                print(f"DEBUG: Removing duplicates")
                # Находим секцию Connections еще раз
                conn_start = -1
                conn_end = -1
                for i, line in enumerate(lines):
                    if '##################################################' in line and i+1 < len(lines) and '# Connections' in lines[i+1]:
                        conn_start = i
                        for j in range(i+1, len(lines)):
                            if lines[j].strip().startswith('def '):
                                conn_end = j
                                break
                        if conn_end == -1:
                            conn_end = len(lines)
                        break
                
                if conn_start != -1 and conn_end != -1:
                    # Собираем все соединения и удаляем дубликаты
                    unique_connections = []
                    seen = set()
                    
                    for i in range(conn_start, conn_end):
                        line = lines[i]
                        if 'self.connect' in line:
                            if line.strip() not in seen:
                                unique_connections.append(line)
                                seen.add(line.strip())
                        else:
                            unique_connections.append(line)
                    
                    # Заменяем секцию
                    del lines[conn_start:conn_end]
                    for j, line in enumerate(unique_connections):
                        lines.insert(conn_start + j, line)                    
            
            if updated:
                with open(script_path, 'wb') as f:
                    f.write('\n'.join(lines).encode('utf-8'))
                self.log_message(f"    ✅ {os.path.basename(script_path)} updated", "buffer")
                    
        except Exception as e:
            self.log_message(f"❌ Error updating script {os.path.basename(script_path)}: {e}", "buffer")

    def debounced_save_and_update_presets(self):
        """Save config AND update presets with debounce"""
        self.cancel_save_timer()
        self._save_timer = self.root.after(2000, self.save_config_and_update_presets)

    def save_config_and_update_presets(self):
        """Save config and update all presets"""
        # Сначала сохраняем основной конфиг
        self.save_config()
            
    def setup_config_autosave(self):
        """Setup auto-save triggers for all settings"""
        # Привязка к изменению текстовых полей
        text_variables = [
            self.service_name, 
            self.service_provider, self.localhost_ip, self.output_ip,
        # FFmpeg custom options
            self.custom_options,
        ]
        
        for var in text_variables:
            var.trace_add('write', lambda *args: self.debounced_save())
        
        # ⭐⭐⭐ ДОБАВЛЕНО: ОТДЕЛЬНЫЕ ОБРАБОТЧИКИ ДЛЯ КЛЮЧЕВЫХ ПОЛЕЙ ⭐⭐⭐
        # Для частоты - с задержкой больше, чтобы не обновлять слишком часто
        self.frequency.trace_add('write', lambda *args: self.debounced_save_and_update_presets())
        
        # Для RF gain
        self.rf_gain.trace_add('write', lambda *args: self.debounced_save_and_update_presets())
        
        # Для Pluto IP
        self.pluto_ip.trace_add('write', lambda *args: self.debounced_save_and_update_presets())
        # ⭐⭐⭐ КОНЕЦ ДОБАВЛЕНИЯ ⭐⭐⭐

        # Привязка к изменению числовых полей
        numeric_variables = [
            self.udp_input_port, self.udp_output_port, self.muxrate,
            self.video_bitrate, self.video_bufsize, self.video_gop,
            self.target_buffer, self.min_buffer, self.max_buffer
        ]
        
        for var in numeric_variables:
            var.trace_add('write', lambda *args: self.debounced_save())
        
        # Привязка к комбобоксам (после создания GUI)
        if hasattr(self, 'video_codec_combo'):
            comboboxes = [
                self.video_codec_combo, self.video_preset_combo, self.video_tune_combo,
                self.video_resolution_combo, self.video_fps_combo, self.audio_codec_combo,
                self.audio_bitrate_combo, self.audio_sample_rate_combo, self.audio_channels_combo,
                self.modulator_preset_combo
            ]
            
            for combo in comboboxes:
                if combo:
                    combo.bind('<<ComboboxSelected>>', lambda e: self.debounced_save())
        
        # Привязка к чекбоксам
        checkboxes = [
            self.auto_start, self.save_window_size, self.streaming_auto_start,
            self.obs_auto_start, self.modulator_auto_start, self.overlay_auto_start
        ]
        
        for cb in checkboxes:
            cb.trace_add('write', lambda *args: self.debounced_save())

    def cancel_save_timer(self):
        """Safely cancel all save timers"""
        if hasattr(self, '_save_timer') and self._save_timer is not None:
            try:
                self.root.after_cancel(self._save_timer)
                self._save_timer = None
            except (ValueError, tk.TclError):
                self._save_timer = None
        
        if hasattr(self, '_preset_update_timer') and self._preset_update_timer is not None:
            try:
                self.root.after_cancel(self._preset_update_timer)
                self._preset_update_timer = None
            except (ValueError, tk.TclError):
                self._preset_update_timer = None

    def debounced_save(self):
        """Save config with debounce"""
        self.cancel_save_timer()
        self._save_timer = self.root.after(2000, self.save_config_and_update_presets)

    def on_closing(self):
        """Handle application closing"""
        self.cancel_save_timer()  # Отменить ожидающее сохранение
        self.save_config()  # Сохранить при закрытии
        self.root.destroy()

    def is_obs_running_system(self):
        """Check if OBS Studio is running as a system process"""
        try:
            for process in psutil.process_iter(['name']):
                try:
                    process_name = process.info['name'].lower()
                    if process_name in ['obs64.exe', 'obs32.exe', 'obs.exe']:
                        return True
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            return False
        except Exception:
            return False  
            
    def find_ffmpeg(self):
        """Find FFmpeg executable using path from conf.cfg"""
        # Используем путь из конфига
        if hasattr(self, 'ffmpeg_path_from_config') and self.ffmpeg_path_from_config:
            # Если это просто "ffmpeg.exe", возвращаем как есть (надеемся что в PATH)
            if self.ffmpeg_path_from_config == "ffmpeg.exe":
                return "ffmpeg.exe"
            
            # Если это полный путь, проверяем существование
            if os.path.exists(self.ffmpeg_path_from_config):
                return self.ffmpeg_path_from_config
            else:
                self.log_message(f"⚠️ FFmpeg not found at: {self.ffmpeg_path_from_config}", "buffer")
        
        # Если нет в конфиге, возвращаем значение по умолчанию
        return "ffmpeg.exe"
                       
    def get_preset_display_name(self, preset_name):
        """Get readable preset name for overlay display"""
        try:
            if not preset_name or preset_name == "":
                return "No Preset"
            
            # Используем новое форматирование из JSON
            formatted = self.format_modulation_scheme(preset_name)
            if formatted != "No Preset":
                return formatted
                
            # Fallback к старому парсингу из имени файла
            parts = preset_name.split('_')
            modulation = None
            code_rate = None
            
            for part in parts:
                if part in ['QPSK', '16QAM', '64QAM', '256QAM']:
                    modulation = part
                elif '/' in part and any(c.isdigit() for c in part):
                    code_rate = part.replace('_', '/')
                elif part.isdigit() and len(part) == 2:
                    code_rate = f"{part[0]}/{part[1]}"
            
            if modulation and code_rate:
                return f"{modulation} {code_rate}"
            else:
                return preset_name
                
        except Exception as e:
            self.log_message(f"Error parsing preset name: {e}", "overlay")
            return preset_name

    def find_gnuradio_python(self):
        """Get GNU Radio Python path from conf.cfg"""
        # Просто возвращаем путь, который уже загружен из конфига
        path = self.gnuradio_python_path.get()
        if path and os.path.exists(path):
            return path
        
        # Если путь пустой или не существует, возвращаем пустую строку
        return ""
            
    def sync_calculator_with_preset(self):
        """Sync calculator with current preset after GUI is fully loaded"""
        try:
            if hasattr(self, 'calculator') and self.modulator_preset.get():
                preset_name = self.modulator_preset.get()
                self.log_message(f"🔄 Syncing calculator with preset: {preset_name}", "buffer")
                
                # Load parameters into calculator
                self.calculator.load_preset_parameters(preset_name)
                
                # Force calculation to update results
                if hasattr(self.calculator, 'calculate'):
                    self.calculator.calculate()
                    
                self.log_message(f"✅ Calculator synced with preset: {preset_name}", "buffer")
        except Exception as e:
            self.log_message(f"❌ Error syncing calculator: {e}", "buffer")            
            
    def calculate_video_settings_from_preset(self, preset_name):
        """Calculate optimal video settings based on selected modulator preset"""
        self.get_channel_bitrates()
                                            
    def on_tab_changed(self, event):
        """При переключении вкладок убираем фокус со всех полей ввода"""
        # Переключаем фокус на основное окно
        self.root.focus_set()     

    def on_multiplex_mode_changed(self, *args):
        """Обработчик изменения режима мультиплекса"""
        self.update_channels_visibility()
            
    def on_window_configure(self, event=None):
        """Handle window resize/move and save geometry if enabled"""
        if hasattr(self, 'save_window_size') and self.save_window_size.get() and hasattr(self, 'config_file'):
            if hasattr(self, '_geometry_timer'):
                self.root.after_cancel(self._geometry_timer)
            self._geometry_timer = self.root.after(2000, self.save_config)

    def show_tips_window(self):
        """Show DVB-T2 tips window"""
        # Убедимся, что окно создано
        if not hasattr(self, 'tips_window') or self.tips_window is None:
            self.tips_window = DVBTTipsWindow(self)
        
        # Показываем окно
        self.tips_window.show()
        
        # Автоматически обновляем анализ при открытии окна
        self.tips_window.update_analysis()         
    
    def delayed_start(self):
        """Delayed start for all components"""
        # Overlay первый
        if self.overlay_auto_start.get():
            self.start_overlay()
        
        # OBS второй (через 3 секунды)
        if self.obs_auto_start.get() and self.obs_path.get() and not self.obs_running:
            self.root.after(6000, self.start_obs)
        
        # Остальное без изменений
        if self.modulator_auto_start.get():
            self.root.after(4000, self.start_modulator)
        if self.streaming_auto_start.get():
            self.root.after(10000, self.start_streaming)        
        if self.playlist_manager.playlist_auto_start.get():
            self.root.after(15000, self.playlist_manager.start_playlist_playback)
            
    def finish_playlist_setup(self):
        """Finish playlist setup after GUI is created"""
        # Update media listbox with loaded folders
        if hasattr(self.playlist_manager, 'media_listbox'):
            self.playlist_manager.update_media_listbox()
        
        # Update bumper numbers
        if hasattr(self.playlist_manager, 'bumper_widgets') and self.playlist_manager.bumper_widgets:
            self.playlist_manager.update_bumper_numbers()
            
    def on_rf_gain_mouse_wheel(self, event):
        """Изменение RF Level колесиком мыши с шагом 1%"""
        # Определяем направление прокрутки (Windows: event.delta, Linux: event.num)
        delta = 0
        if event.delta:  # Windows
            delta = event.delta
        elif event.num:  # Linux
            delta = 1 if event.num == 4 else -1
        
        # Шаг изменения - 1% за клик
        step = 1
        
        # Определяем направление
        if delta > 0:
            new_value = min(100, self.rf_gain_percent.get() + step)
        else:
            new_value = max(0, self.rf_gain_percent.get() - step)
        
        # Устанавливаем новое значение
        self.rf_gain_percent.set(new_value)
        
        # Триггерим изменение (имитируем движение слайдера)
        self.on_rf_gain_change(new_value)
        
    def on_rf_gain_change(self, value):
        """Handle RF gain change with delay and send to GNU Radio"""
        if not self.modulator_running:
            return
            
        if self.rf_gain_timer:
            self.root.after_cancel(self.rf_gain_timer)
        
        # Округляем до целого числа
        percent = int(round(float(value)))
        self.rf_gain_percent.set(percent)
        
        modulator_gain = self.convert_rf_gain_to_modulator(percent)
        self.rf_gain.set(modulator_gain)
        
        self.rf_gain_timer = self.root.after(500, self.send_rf_gain_update)
            
    def send_rf_gain_update(self):
        """Send RF gain update to GNU Radio"""
        # ДОБАВЬТЕ ПОДРОБНОЕ ЛОГИРОВАНИЕ ДЛЯ ДЕБАГА
        gui_percent = self.rf_gain_percent.get()
        current_rf_gain = self.rf_gain.get()
        expected_conversion = self.convert_rf_gain_to_modulator(gui_percent)
        
        self.log_message(f"🔧 RF Gain Debug: GUI={gui_percent}% -> Current RF={current_rf_gain} dB", "buffer")
        self.log_message(f"🔧 Expected conversion: {gui_percent}% -> {expected_conversion} dB", "buffer")
        
        # Проверяем соответствие
        if current_rf_gain != expected_conversion:
            self.log_message(f"⚠️ WARNING: Current RF gain ({current_rf_gain} dB) doesn't match expected ({expected_conversion} dB)", "buffer")
        
        self.set_gnuradio_variable("rf_gain", current_rf_gain)
        self.save_config()
        self.rf_gain_timer = None        
        
    def connect_to_gnuradio(self):
        """Connect to GNU Radio XML-RPC server with retry - called after modulator starts"""
        def connect_thread():
            max_retries = 5
            retry_delay = 3
            
            for attempt in range(max_retries):
                try:
                    self.log_message(f"Attempting to connect to GNU Radio (attempt {attempt+1}/{max_retries})...", "buffer")
                    self.root.after(200, lambda: self.connection_status_var.set(f"🔄 Connecting... ({attempt+1}/{max_retries})"))
                    
                    self.server = xmlrpc.client.ServerProxy(self.server_url, allow_none=True)
                    
                    # Test connection
                    self.server.get_rf_gain()
                    
                    self.connected = True
                    self.root.after(300, lambda: self.connection_status_var.set("✅ Connected"))
                    self.root.after(500, lambda: self.connection_indicator.config(foreground='green'))
                    self.log_message("✅ Connected to GNU Radio XML-RPC server", "buffer")
                    
                    # Send current values to GNU Radio
                    #self.root.after(500, self.send_current_values_to_gnuradio())
                    #self.send_current_values_to_gnuradio()
                    
                    # Get current values from GNU Radio
                    self.get_gnuradio_values()
                    return
                    
                except Exception as e:
                    if attempt < max_retries - 1:
                        self.root.after(1500, lambda: self.connection_status_var.set(f"🔄 Retrying... ({attempt+1}/{max_retries})"))
                        self.log_message(f"⚠ Connection attempt {attempt+1}/{max_retries} failed: {e}", "buffer")
                        self.log_message(f"⚠ Retrying in {retry_delay}s...", "buffer")
                        time.sleep(retry_delay)
                    else:
                        self.connected = False
                        self.root.after(0, lambda: self.connection_status_var.set("❌ Disconnected"))
                        self.root.after(0, lambda: self.connection_indicator.config(foreground='red'))
                        self.log_message(f"❌ Failed to connect to GNU Radio after {max_retries} attempts: {e}", "buffer")
                        self.log_message("💡 Make sure GNU Radio script is running with XML-RPC server on port 8001", "buffer")
        
        threading.Thread(target=connect_thread, daemon=True).start()
        
    def convert_rf_gain_to_modulator(self, gui_percent):
        """Convert GUI RF gain percentage (0-100) to device-specific value"""
        device = self.selected_device.get()
        config = self.device_configs[device]
        min_gain, max_gain = config['gain_range']
        
        if device == 'plutosdr' and config.get('use_iio', False):
            # PlutoSDR с IIO блоком: РЕВЕРСИВНАЯ логика
            # GUI 0% = 10 dB attenuation (минимальная мощность)
            # GUI 100% = 0 dB attenuation (максимальная мощность)
            attenuation = max_gain - (gui_percent / 100) * (max_gain - min_gain)
            return int(max(min_gain, min(max_gain, attenuation)))
        else:
            # Soapy блоки: прямая логика
            # GUI 0% = минимальный gain
            # GUI 100% = максимальный gain
            gain = min_gain + (gui_percent / 100) * (max_gain - min_gain)
            return int(max(min_gain, min(max_gain, gain)))

    def convert_rf_gain_to_gui(self, modulator_gain):
        """Convert device-specific value to GUI percentage (0-100)"""
        device = self.selected_device.get()
        config = self.device_configs[device]
        min_gain, max_gain = config['gain_range']
        
        if device == 'plutosdr' and config.get('use_iio', False):
            # PlutoSDR с IIO блоком: РЕВЕРСИВНАЯ логика
            # 10 dB attenuation = 0% GUI
            # 0 dB attenuation = 100% GUI
            gui_percent = ((max_gain - modulator_gain) / (max_gain - min_gain)) * 100
            return int(max(0, min(100, gui_percent)))
        else:
            # Soapy блоки: прямая логика
            gui_percent = ((modulator_gain - min_gain) / (max_gain - min_gain)) * 100
            return int(max(0, min(100, gui_percent)))    
    
    def reconnect_gnuradio(self):
        """Manual reconnection to GNU Radio"""
        if self.connected:
            self.log_message("Already connected to GNU Radio", "buffer")
            return
            
        self.log_message("Attempting to reconnect to GNU Radio...", "buffer")
        self.connect_to_gnuradio()
    
    def set_gnuradio_variable(self, var_name, value):
        """Set variable in GNU Radio via XML-RPC"""
        # ⚡ ИЗМЕНЕНИЕ: Проверяем, что модулятор запущен
        if not self.modulator_running:
            self.log_message(f"⚠ Modulator not running, skipping {var_name} set", "buffer")
            return
            
        if not self.connected:
            self.log_message(f"⚠ Not connected to GNU Radio, skipping {var_name} set", "buffer")
            return
            
        def set_thread():
            try:
 
                    
                method_name = f"set_{var_name}"
                
                # Convert value to proper type
                if var_name in ["rf_gain", "frequency"]:  # ⚡ УБРАТЬ zmq_port
                    value_to_set = int(value)
                else:
                    value_to_set = str(value)
                    
                # Call XML-RPC method
                result = getattr(self.server, method_name)(value_to_set)
                self.log_message(f"✅ GNU Radio {var_name} set to {value_to_set}", "buffer")
                
            except Exception as e:
                self.log_message(f"❌ Error setting GNU Radio {var_name}: {e}", "buffer")
                
        threading.Thread(target=set_thread, daemon=True).start()

    def send_current_values_to_gnuradio(self):
        """Send current values from GUI to GNU Radio after connection"""
        if not self.connected:
            return
            
        try:
            # Send frequency from GUI
            frequency_hz = int(self.frequency.get())
            self.set_gnuradio_variable("frequency", frequency_hz)
            
            # Send RF gain from GUI
            rf_gain_modulator = self.convert_rf_gain_to_modulator(self.rf_gain_percent.get())
            self.set_gnuradio_variable("rf_gain", rf_gain_modulator)
            
            # Send device arguments (если GNU Radio поддерживает)
            #device_args = self.get_device_arguments()
            #self.set_gnuradio_variable("device_args", device_args)  # если нужно
            
            self.log_message(f"📤 Sent to GNU Radio: Freq={frequency_hz} Hz, RF={rf_gain_modulator} dB", "buffer")
                        
        except Exception as e:
            self.log_message(f"❌ Error sending values to GNU Radio: {e}", "buffer")

    def get_gnuradio_values(self):
        """Get current values from GNU Radio"""
        if not self.connected:
            return
            
        def get_thread():
            try:
                # Get RF gain - ТОЛЬКО для логгирования, НЕ перезаписываем GUI
                rf_gain = self.server.get_rf_gain()
                # Convert to GUI percentage
                rf_percent = self.convert_rf_gain_to_gui(rf_gain)
                self.log_message(f"🔧 Got from GNU Radio: RF={rf_gain} dB -> GUI={rf_percent}%", "buffer")
                
                # НЕ ОБНОВЛЯЕМ GUI ЗНАЧЕНИЯ ИЗ GNU RADIO!
                # Оставляем значения, установленные пользователем в GUI
                # self.root.after(0, self.rf_gain_percent.set, rf_percent)  # ← УДАЛИТЬ
                # self.root.after(0, self.rf_gain.set, rf_gain)             # ← УДАЛИТЬ
                
                # # Get frequency - тоже НЕ перезаписываем если не нужно
                # frequency = self.server.get_frequency()
                # self.root.after(0, self.frequency.set, str(frequency))
                
                self.log_message("✅ Retrieved current values from GNU Radio", "buffer")
                
            except Exception as e:
                self.log_message(f"❌ Error getting GNU Radio values: {e}", "buffer")
    
    def create_gui(self):
        """Create the main GUI layout"""
        main_frame = ttk.Frame(self.root, padding="8")
        main_frame.pack(fill='both', expand=True)
        
        # Header with status
        header_frame = ttk.Frame(main_frame)
        header_frame.pack(fill='x', pady=(0, 8))
        
        # DVB icon and title
        title_frame = ttk.Frame(header_frame)
        title_frame.pack(side='left')
        
        # DVB icon (using text symbol as placeholder)
        ttk.Label(title_frame, text="📺", font=('Arial', 16)).pack(side='left', padx=(0, 5))
        
        # Styled title with rounded font and dark gray color
        title_label = tk.Label(title_frame, text="R6WAX DVB-T2\nDATV Broadcast\nSystem", 
                              font=('Segoe UI', 13, 'bold'), fg='#404040')
        title_label.pack(side='left')
        
        # Status indicators with colored labels - компактное расположение ближе к названию
        status_frame = ttk.Frame(header_frame)
        status_frame.pack(side='left', padx=(20, 0))
        
        # Первая строка: GNU Radio и RF Mod статусы
        first_row_frame = ttk.Frame(status_frame)
        first_row_frame.pack(side='top', fill='x', pady=2)
        
        # XML-RPC connection status
        ttk.Label(first_row_frame, text="GNU Radio:", font=('Arial', 9)).pack(side='left')
        self.connection_indicator = tk.Label(first_row_frame, textvariable=self.connection_status_var, 
                                           font=('Arial', 9, 'bold'), foreground='red')
        self.connection_indicator.pack(side='left', padx=5)
        
        # RF Mod status - ПЕРЕМЕЩЕНО НА ПЕРВУЮ СТРОКУ
        ttk.Label(first_row_frame, text="RF Mod:", font=('Arial', 9)).pack(side='left', padx=(15,0))
        self.modulator_status_label = tk.Label(first_row_frame, textvariable=self.modulator_status,
                                              font=('Arial', 9, 'bold'))
        self.modulator_status_label.pack(side='left', padx=5)
        
        # Вторая строка: OBS Studio и ON AIR статусы
        second_row_frame = ttk.Frame(status_frame)
        second_row_frame.pack(side='top', fill='x', pady=2)
        
        # OBS Studio status
        ttk.Label(second_row_frame, text="OBS Studio:", font=('Arial', 9)).pack(side='left')
        self.obs_status_label = tk.Label(second_row_frame, textvariable=self.obs_status,
                                       font=('Arial', 9, 'bold'), foreground='red')
        self.obs_status_label.pack(side='left', padx=5)
        
        # ON AIR status with green/red color
        ttk.Label(second_row_frame, text="Status:", font=('Arial', 9)).pack(side='left', padx=(15,0))
        self.on_air_label = tk.Label(second_row_frame, textvariable=self.on_air_status,
                                   font=('Arial', 9, 'bold'), foreground='red')
        self.on_air_label.pack(side='left', padx=5)
        
        # Current modulation scheme
        # ttk.Label(second_row_frame, text="Modulation:", font=('Arial', 9)).pack(side='left', padx=(15,0))
        # self.modulation_label = tk.Label(second_row_frame, textvariable=self.modulator_preset,
                                       # font=('Arial', 9, 'bold'))
        # self.modulation_label.pack(side='left', padx=5)
        
        # Process status frame (третья строка)
        process_frame = ttk.Frame(status_frame)
        process_frame.pack(side='top', fill='x', pady=2)
        
        ttk.Label(process_frame, text="FFmpeg:", font=('Arial', 9)).pack(side='left')
        self.encoder_status_label = ttk.Label(process_frame, textvariable=self.encoder_status, 
                                            font=('Arial', 9, 'bold'))
        self.encoder_status_label.pack(side='left', padx=2)
        
        ttk.Label(process_frame, text="Buffer:", font=('Arial', 9)).pack(side='left', padx=(10,0))
        self.buffer_status_label = ttk.Label(process_frame, textvariable=self.buffer_status, 
                                           font=('Arial', 9, 'bold'))
        self.buffer_status_label.pack(side='left', padx=2)
        
        ttk.Label(process_frame, text="Overlay:", font=('Arial', 9)).pack(side='left', padx=(10,0))
        self.overlay_status_label = tk.Label(process_frame, textvariable=self.overlay_status,
                                           font=('Arial', 9, 'bold'), foreground='red')
        self.overlay_status_label.pack(side='left', padx=2)
        
        # Initialize status colors
        self.update_status_colors()
        
        # Create notebook for tabs
        notebook = ttk.Notebook(main_frame)
        notebook.pack(fill='both', expand=True)
        
        # Statistics Tab (now first)
        stats_frame = ttk.Frame(notebook, padding="8")
        notebook.add(stats_frame, text="Main")
        
        # Settings Tab
        settings_frame = ttk.Frame(notebook, padding="8")
        notebook.add(settings_frame, text="Settings")
        
        # MPC Playlist Tab
        playlist_frame = self.playlist_manager.create_playlist_tab(notebook)
        notebook.add(playlist_frame, text="MPC Playlist")

        # Multiplex Tab (НОВАЯ ВКЛАДКА)
        multiplex_frame = ttk.Frame(notebook, padding="8")
        notebook.add(multiplex_frame, text="Multiplex")
        
        # GNU T2 Calculator Tab
        calculator_frame = self.calculator.create_calculator_tab(notebook)
        notebook.add(calculator_frame, text="GNU T2 Calculator")        
        
        # Overlay Tab
        overlay_frame = ttk.Frame(notebook, padding="8")
        notebook.add(overlay_frame, text="Overlay")
        
        # Logs Tab
        logs_frame = ttk.Frame(notebook, padding="8")
        notebook.add(logs_frame, text="Logs")
        
        self.create_stats_tab(stats_frame)
        self.create_settings_tab(settings_frame)
        self.create_multiplex_tab(multiplex_frame)  # НОВЫЙ МЕТОД
        self.create_overlay_tab(overlay_frame)
        self.create_logs_tab(logs_frame)
        self.setup_config_autosave()
        
    def create_multiplex_tab(self, parent):
        """Create multiplex configuration tab"""
        main_frame = ttk.Frame(parent)
        main_frame.pack(fill='both', expand=True)
        
        # # Header with description - более компактный
        # header_frame = ttk.LabelFrame(main_frame, text="Multiplex Configuration", padding="4")
        # header_frame.pack(fill='x', pady=(0, 6))
        
        # ttk.Label(header_frame, text="Add up to 10 channels to multiplex into single DVB-T2 stream", 
                  # font=('Arial', 9)).pack(pady=2)
        # ttk.Label(header_frame, text="Video bitrate is automatically divided between active channels",
                  # font=('Arial', 8), foreground='blue').pack(pady=1)

        # Emergency stream file
        emergency_frame = ttk.LabelFrame(main_frame, text="Emergency Stream", padding="4")
        emergency_frame.pack(fill='x', pady=(0, 6))

        row_frame = ttk.Frame(emergency_frame)
        row_frame.pack(fill='x', pady=2)

        ttk.Label(row_frame, text="Emergency File:", font=('Arial', 8), width=13).pack(side='left')
        emergency_entry = ttk.Entry(row_frame, textvariable=self.emergency_file_path, 
                                   width=30, font=('Arial', 8))
        emergency_entry.pack(side='left', padx=2, fill='x', expand=True)

        ttk.Button(row_frame, text="Browse", width=8,
                  command=self.browse_emergency_file).pack(side='left', padx=2)
        
        # Scrollable area for channels
        canvas_frame = ttk.Frame(main_frame)
        canvas_frame.pack(fill='both', expand=True)
        
        canvas = tk.Canvas(canvas_frame)
        scrollbar = ttk.Scrollbar(canvas_frame, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        # Channel container
        self.channels_container = ttk.Frame(scrollable_frame)
        self.channels_container.pack(fill='x', pady=(0, 6))
        
        # НЕ создаем CH1 здесь - он будет создан в load_multiplex_channels
        
        # Add channel button
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill='x', pady=(3, 0))
        
        self.add_ch_btn = ttk.Button(btn_frame, text="Add Channel", 
                                     command=self.add_channel, width=15)
        self.add_ch_btn.pack(side='left', padx=2)
        
        # Оставим только одну кнопку FFmpeg Command
        ttk.Button(btn_frame, text="FFmpeg Command", 
                  command=self.show_multiplex_ffmpeg_command, width=17).pack(side='left', padx=2)
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # Setup auto-save
        self.setup_multiplex_autosave()
        
        # Update add button state
        self.update_add_button_state()

    def get_available_windows(self):
        """Получение списка доступных окон через PowerShell"""
        try:
            # PowerShell команда для получения окон с заголовками
            ps_command = "Get-Process | Where-Object {$_.MainWindowTitle -ne ''} | Select-Object -ExpandProperty MainWindowTitle"
            
            result = subprocess.run(
                ['powershell', '-Command', ps_command],
                capture_output=True,
                text=True,
                timeout=5,
                encoding='utf-8',
                errors='ignore'
            )
            
            if result.returncode != 0:
                self.log_message("PowerShell command failed", "buffer")
                return []
            
            # Разбираем вывод (каждая строка - название окна)
            windows = []
            for line in result.stdout.split('\n'):
                line = line.strip()
                if line and not line.startswith('MainWindowTitle') and not line.startswith('---'):
                    windows.append(line)
            
            # Убираем дубликаты, но сохраняем порядок
            seen = set()
            unique_windows = []
            for window in windows:
                if window not in seen:
                    seen.add(window)
                    unique_windows.append(window)
            
            self.log_message(f"Found {len(unique_windows)} windows for capture", "buffer")
            return unique_windows
            
        except subprocess.TimeoutExpired:
            self.log_message("Timeout getting windows list", "buffer")
            return []
        except Exception as e:
            self.log_message(f"Error getting windows: {e}", "buffer")
            return []

    def refresh_channel_windows(self, channel_num):
        """Обновление списка доступных окон для канала"""
        if channel_num not in self.multiplex_channels:
            return
        
        channel_data = self.multiplex_channels[channel_num]
        
        # Получаем актуальный список окон
        windows = self.get_available_windows()
        self.available_windows = windows
        
        if 'window_combo' in channel_data and channel_data['window_combo']:
            combo = channel_data['window_combo']
            current_value = channel_data['window_title'].get()
            
            # Обновляем список значений
            combo['values'] = windows if windows else ['No windows found']
            
            # Пытаемся сохранить выбранное окно, если оно еще существует
            if current_value and current_value in windows:
                # Окно все еще доступно - оставляем
                pass
            elif current_value:
                # Ищем похожее окно
                similar = self.find_similar_window(current_value, windows)
                if similar:
                    channel_data['window_title'].set(similar)
                    self.log_message(f"CH{channel_num}: Found similar window: {similar[:50]}...", "buffer")
                elif windows:
                    # Берем первое доступное
                    channel_data['window_title'].set(windows[0])
                    self.log_message(f"CH{channel_num}: Using first available window", "buffer")
            elif windows:
                # Нет выбранного - берем первое
                channel_data['window_title'].set(windows[0])

    def find_similar_window(self, old_title, available_windows):
        """Поиск похожего окна среди доступных"""
        if not old_title or not available_windows:
            return None
        
        import re
        
        # Логируем для отладки
        self.log_message(f"Looking for window similar to: '{old_title[:50]}...'", "buffer")
        
        # 1. Сначала ищем точное совпадение (на всякий случай)
        if old_title in available_windows:
            return old_title
        
        # 2. Извлекаем основу названия (первые слова до версии и спецсимволов)
        # Например: "Java FRN_Client V 5.03.2 - [R6WAX, Tagir]" -> "Java FRN_Client"
        base_pattern = re.match(r'^([A-Za-z0-9_\-\.\s]+?)(?:\s+[Vv]\d+|\s*[-\[]|$)', old_title)
        if base_pattern:
            base_name = base_pattern.group(1).strip()
            self.log_message(f"Base name extracted: '{base_name}'", "buffer")
            
            # Ищем окна, содержащие эту основу
            for window in available_windows:
                if base_name in window:
                    self.log_message(f"Found window containing base name: '{window[:50]}...'", "buffer")
                    return window
        
        # 3. Если не нашли, ищем по ключевым словам (берем первые 2-3 слова)
        words = re.findall(r'[A-Za-z0-9_]+', old_title)
        if len(words) >= 2:
            # Берем первые 2-3 слова как ключевые
            key_words = words[:3]
            self.log_message(f"Key words: {key_words}", "buffer")
            
            best_match = None
            best_score = 0
            
            for window in available_windows:
                score = 0
                window_lower = window.lower()
                for word in key_words:
                    if word.lower() in window_lower:
                        score += 1
                
                if score > best_score:
                    best_score = score
                    best_match = window
            
            if best_score >= 2:  # Нашли хотя бы 2 совпадения
                self.log_message(f"Best match with score {best_score}: '{best_match[:50]}...'", "buffer")
                return best_match
        
        # 4. Если ничего не нашли, возвращаем None
        self.log_message("No similar window found", "buffer")
        return None
        
    def create_default_channel_1(self):
        """Create default CH1 with values from main settings"""
        try:
            self.log_message("Creating default CH1...", "buffer")
            
            # Создаем CH1
            channel_data = self.add_channel_widget(1)
            
            # Устанавливаем значения из основных настроек
            def set_default_values():
                try:
                    # Базовые значения
                    channel_data['enabled'].set(True)
                    
                    # Имя канала = Service Name или "Channel_1"
                    ch_name = self.service_name.get() if self.service_name.get() else "Channel_1"
                    channel_data['name'].set(ch_name)
                    
                    # Тип источника
                    channel_data['source_type'].set("input_devices")
                    
                    # Обновляем контент
                    self.create_channel_content(1, skip_refresh=True)
                    
                    # Устройства из основных настроек
                    video_device = self.video_input_device.get()
                    audio_device = self.audio_input_device.get()
                    
                    if video_device:
                        channel_data['video_device'].set(video_device)
                    
                    if audio_device:
                        channel_data['audio_device'].set(audio_device)
                    
                    # Путь к медиа пустой
                    channel_data['media_path'].set("")
                    channel_data['randomize'].set(False)
                    
                    self.log_message(f"  ✓ Default CH1 created: '{ch_name}'", "buffer")
                    
                    # Обновляем списки устройств с задержкой
                    self.root.after(300, lambda: self.populate_channel_device_lists(1))
                    
                    # Автоматически ищем устройства если еще не найдены
                    self.root.after(500, self.refresh_multiplex_devices)
                    
                except Exception as e:
                    self.log_message(f"  ✗ Error creating default CH1: {e}", "buffer")
            
            # Устанавливаем значения с задержкой
            self.root.after(100, set_default_values)
            
            # Обновляем состояние кнопки
            self.root.after(500, self.update_add_button_state)
            
        except Exception as e:
            self.log_message(f"Error creating default CH1: {e}", "buffer")
            import traceback
            traceback.print_exc()

    def add_channel_widget(self, channel_num):
        """Create widget for a single channel - компактная версия"""
        # Проверяем не существует ли уже канал
        if channel_num in self.multiplex_channels:
            self.log_message(f"Channel {channel_num} already exists, skipping", "buffer")
            return self.multiplex_channels[channel_num]
        
        frame = ttk.LabelFrame(self.channels_container, text=f"CH{channel_num}", padding="4")
        frame.pack(fill='x', pady=2)
        
        # Store references
        channel_data = {
            'frame': frame,
            'enabled': tk.BooleanVar(),
            'name': tk.StringVar(),
            'source_type': tk.StringVar(),
            'video_device': tk.StringVar(),
            'audio_device': tk.StringVar(),
            'window_title': tk.StringVar(),  # НОВОЕ
            'window_combo': None,  # НОВОЕ            
            'media_path': tk.StringVar(),
            'randomize': tk.BooleanVar(),
            'udp_url': tk.StringVar(),
            'url_input': tk.StringVar(),  # ← ДОБАВЬТЕ ЭТУ СТРОКУ
            'selected_program': tk.StringVar(), 
            'available_programs': [],
            'video_devices_combo': None,
            'audio_devices_combo': None,
            'content_frame': None,
            'udp_url_entry': None,
            'url_input_entry': None,  # ← ДОБАВЬТЕ ЭТУ СТРОКУ
            'saved_video_pid': '', 
            'saved_audio_pid': '',
            'is_radio': tk.BooleanVar(value=False),
            'radio_bg_type': tk.StringVar(value='Color'),  # Color или Picture
            'radio_bg_color': tk.StringVar(value='black'),
            'radio_bg_picture': tk.StringVar(value=''),
            'radio_text': tk.StringVar(value='Radio Station'),
            'radio_show_time': tk.BooleanVar(value=True),
            'radio_text_color': tk.StringVar(value='magenta'),
            'radio_text_size': tk.IntVar(value=60),
            'radio_time_color': tk.StringVar(value='cyan'),
            'radio_time_size': tk.IntVar(value=50), 
            'show_metadata': tk.BooleanVar(value=True),
            'metadata_size': tk.IntVar(value=40),
            'metadata_color': tk.StringVar(value='violet'),
            'metadata_position': tk.IntVar(value=120),
            'emergency_file_path': tk.StringVar(value="")
        }
        
        self.multiplex_channels[channel_num] = channel_data
        
        # Top row: Checkbox, Name, Source Type - более компактная
        top_frame = ttk.Frame(frame)
        top_frame.pack(fill='x', pady=(0, 3))
        
        # Enable checkbox
        chk = ttk.Checkbutton(top_frame, variable=channel_data['enabled'], 
                             command=lambda ch=channel_num: self.on_channel_toggle(ch))
        chk.pack(side='left', padx=(0, 5))
        
        # Channel name - компактное поле
        ttk.Label(top_frame, text="Name:", font=('Arial', 8), width=6).pack(side='left')
        name_entry = ttk.Entry(top_frame, textvariable=channel_data['name'], 
                              width=16, font=('Arial', 8))
        name_entry.pack(side='left', padx=(0, 10))
        
        # Source type - компактный комбобокс
        ttk.Label(top_frame, text="Source:", font=('Arial', 8), width=6).pack(side='left')
        source_combo = ttk.Combobox(top_frame, textvariable=channel_data['source_type'],
                                   values=["input_devices", "media_folder", "UDP_MPTS", "URL_Input", "grab_window"], 
                                   width=12, font=('Arial', 8), state="readonly")
        source_combo.pack(side='left', padx=(0, 5))
        source_combo.bind('<<ComboboxSelected>>', 
                         lambda e, ch=channel_num: self.on_source_type_change(ch))
        
        # Remove button (only for CH2+) - компактная кнопка
        if channel_num > 1:
            ttk.Button(top_frame, text="Remove Channel", width=17,
                      command=lambda ch=channel_num: self.remove_channel(ch)).pack(side='right')
        
        # Content frame (будет заполнен позже)
        content_frame = ttk.Frame(frame)
        content_frame.pack(fill='x')
        channel_data['content_frame'] = content_frame

        # Добавляем автосохранение
        def add_autosave():
            channel_data['enabled'].trace_add('write', lambda *args: self.debounced_save())
            channel_data['name'].trace_add('write', lambda *args: self.debounced_save())
            channel_data['source_type'].trace_add('write', lambda *args: self.debounced_save())
            channel_data['video_device'].trace_add('write', lambda *args: self.debounced_save())
            channel_data['audio_device'].trace_add('write', lambda *args: self.debounced_save())
            channel_data['media_path'].trace_add('write', lambda *args: self.debounced_save())
            channel_data['randomize'].trace_add('write', lambda *args: self.debounced_save())
            channel_data['url_input'].trace_add('write', lambda *args: self.debounced_save())
            channel_data['udp_url'].trace_add('write', lambda *args: self.debounced_save())
            channel_data['selected_program'].trace_add('write', lambda *args: self.debounced_save())
            channel_data['is_radio'].trace_add('write', lambda *args: self.debounced_save())
            channel_data['radio_bg_type'].trace_add('write', lambda *args: self.debounced_save())
            channel_data['radio_bg_color'].trace_add('write', lambda *args: self.debounced_save())
            channel_data['radio_bg_picture'].trace_add('write', lambda *args: self.debounced_save())
            channel_data['radio_text'].trace_add('write', lambda *args: self.debounced_save())
            channel_data['radio_show_time'].trace_add('write', lambda *args: self.debounced_save())
            channel_data['radio_text_color'].trace_add('write', lambda *args: self.debounced_save())
            channel_data['radio_text_size'].trace_add('write', lambda *args: self.debounced_save())
            channel_data['radio_time_color'].trace_add('write', lambda *args: self.debounced_save())
            channel_data['radio_time_size'].trace_add('write', lambda *args: self.debounced_save())
            channel_data['show_metadata'].trace_add('write', lambda *args: self.debounced_save())
            channel_data['metadata_size'].trace_add('write', lambda *args: self.debounced_save())
            channel_data['metadata_color'].trace_add('write', lambda *args: self.debounced_save())
            channel_data['metadata_position'].trace_add('write', lambda *args: self.debounced_save()) 
       
        self.root.after(150, add_autosave)
        
        return channel_data
                       
    def create_channel_content(self, channel_num, skip_refresh=False):
        """Create content for channel based on source type"""
        channel_data = self.multiplex_channels[channel_num]
        content_frame = channel_data['content_frame']
        
        # Clear previous content
        for widget in content_frame.winfo_children():
            widget.destroy()
        
        # Clear combobox references
        if 'video_devices_combo' in channel_data:
            channel_data['video_devices_combo'] = None
        if 'audio_devices_combo' in channel_data:
            channel_data['audio_devices_combo'] = None
        if 'udp_url_entry' in channel_data:
            channel_data['udp_url_entry'] = None
        if 'streams_combo' in channel_data:
            channel_data['streams_combo'] = None
        
        source_type = channel_data['source_type'].get()
        
        if source_type == "input_devices":
            # Input devices selection - компактные подписи
            row_frame = ttk.Frame(content_frame)
            row_frame.pack(fill='x', pady=1)
            
            ttk.Label(row_frame, text="Video:", font=('Arial', 8), width=6).pack(side='left')
            
            video_combo = ttk.Combobox(row_frame, textvariable=channel_data['video_device'],
                                      width=32, font=('Arial', 8), state="readonly")
            video_combo.pack(side='left', padx=(2, 10))
            channel_data['video_devices_combo'] = video_combo
            # video_combo.bind('<<ComboboxSelected>>', 
                 # lambda e, ch=channel_num: self.on_input_device_selected(ch, 'video'))
            
            ttk.Label(row_frame, text="Audio:", font=('Arial', 8), width=6).pack(side='left')
            
            audio_combo = ttk.Combobox(row_frame, textvariable=channel_data['audio_device'],
                                      width=32, font=('Arial', 8), state="readonly")
            audio_combo.pack(side='left', padx=2)
            channel_data['audio_devices_combo'] = audio_combo
            # audio_combo.bind('<<ComboboxSelected>>', 
                 # lambda e, ch=channel_num: self.on_input_device_selected(ch, 'audio'))
            
            # Автоматически обновляем список устройств
            if not skip_refresh:
                self.root.after(100, self.find_video_devices)
                self.root.after(150, self.find_audio_devices)
                self.root.after(200, lambda: self.populate_channel_device_lists(channel_num))           
            
        elif source_type == "media_folder":
            # Media file/folder selection
            row_frame = ttk.Frame(content_frame)
            row_frame.pack(fill='x', pady=1)
            
            ttk.Label(row_frame, text="Path:", font=('Arial', 8), width=6).pack(side='left')
            
            path_entry = ttk.Entry(row_frame, textvariable=channel_data['media_path'], 
                                  width=45, font=('Arial', 8))
            path_entry.pack(side='left', padx=(2, 5))
            
            ttk.Button(row_frame, text="Browse", width=8,
                      command=lambda: self.browse_media_path(channel_num)).pack(side='left', padx=(0, 5))
            
            # Randomize checkbox (only for folders)
            randomize_chk = ttk.Checkbutton(row_frame, text="Randomize",
                                           variable=channel_data['randomize'])
            randomize_chk.pack(side='left')
            
        elif source_type == "UDP_MPTS":
            # UDP Source configuration
            row1 = ttk.Frame(content_frame)
            row1.pack(fill='x', pady=1)
            
            ttk.Label(row1, text="URL:", font=('Arial', 8), width=6).pack(side='left')
            
            # Поле ввода URL с возможностью вставки
            url_entry = ttk.Entry(row1, textvariable=channel_data['udp_url'], 
                                 width=50, font=('Arial', 8))
            url_entry.pack(side='left', padx=(2, 5), fill='x', expand=True)
            
            # Включаем вставку из буфера обмена
            def paste_url(event):
                try:
                    clipboard_text = self.root.clipboard_get()
                    if clipboard_text:
                        channel_data['udp_url'].set(clipboard_text)
                except:
                    pass
            
            url_entry.bind('<Control-v>', paste_url)
            url_entry.bind('<Button-3>', lambda e: url_entry.event_generate('<<Paste>>'))
            channel_data['udp_url_entry'] = url_entry

            # Кнопка Get Info
            ttk.Button(row1, text="Get Info", width=8,
                      command=lambda ch=channel_num: self.get_udp_stream_info(ch)).pack(side='left')
                      
            # Строка для выбора программы
            row2 = ttk.Frame(content_frame)
            row2.pack(fill='x', pady=1)
            
            ttk.Label(row2, text="Program:", font=('Arial', 8), width=10).pack(side='left')
            program_combo = ttk.Combobox(row2, textvariable=channel_data['selected_program'],
                                        width=35, font=('Arial', 8), state="readonly")
            program_combo.pack(side='left', padx=(2, 0), fill='x', expand=True)
            
            # Привязка события выбора программы
            program_combo.bind('<<ComboboxSelected>>', 
                              lambda e, ch=channel_num: self.on_udp_program_select(ch))
            
            # Обновляем список программ если они уже есть
            if channel_data.get('available_programs'):
                self.root.after(100, lambda ch=channel_num: self.update_udp_program_lists(ch))                      

        elif source_type == "URL_Input":
            # URL Input configuration - КОМПАКТНЫЙ ВИД
            row1 = ttk.Frame(content_frame)
            row1.pack(fill='x', pady=1)
            
            # URL поле
            ttk.Label(row1, text="URL:", font=('Arial', 8), width=4).pack(side='left')
            
            url_entry = ttk.Entry(row1, textvariable=channel_data['url_input'],
                                 width=38, font=('Arial', 8))
            url_entry.pack(side='left', padx=(2, 5), fill='x', expand=True)
            
            # Включаем вставку из буфера обмена
            def paste_url(event):
                try:
                    clipboard_text = self.root.clipboard_get()
                    if clipboard_text:
                        channel_data['url_input'].set(clipboard_text)
                except:
                    pass
            
            url_entry.bind('<Control-v>', paste_url)
            url_entry.bind('<Button-3>', lambda e: url_entry.event_generate('<<Paste>>'))
            channel_data['url_input_entry'] = url_entry
            
            # Чекбокс "Radio" справа - ПОКАЗЫВАТЬ ТОЛЬКО ДЛЯ URL_Input
            radio_check = ttk.Checkbutton(row1, text="Radio",
                                         variable=channel_data['is_radio'],
                                         command=lambda: self.on_url_input_type_change(channel_num))
            radio_check.pack(side='right', padx=(5, 0))
            
            if channel_data['is_radio'].get():
                self.create_radio_settings(channel_data, content_frame)

        elif source_type == "grab_window":
            # Window capture configuration
            channel_data['is_radio'].set(False)
            row_frame = ttk.Frame(content_frame)
            row_frame.pack(fill='x', pady=1)
            
            ttk.Label(row_frame, text="Window:", font=('Arial', 8), width=6).pack(side='left')
            
            # Комбобокс для выбора окна (с возможностью ручного ввода)
            window_combo = ttk.Combobox(row_frame, textvariable=channel_data['window_title'],
                                       width=45, font=('Arial', 8))
            window_combo.pack(side='left', padx=2, fill='x', expand=True)
            channel_data['window_combo'] = window_combo
            
            # Кнопка обновления списка окон
            ttk.Button(row_frame, text="Refresh", width=8,
                      command=lambda ch=channel_num: self.refresh_channel_windows(ch)).pack(side='left', padx=2)
            
            # Audio device selection
            audio_frame = ttk.Frame(content_frame)
            audio_frame.pack(fill='x', pady=1)
            
            ttk.Label(audio_frame, text="Audio:", font=('Arial', 8), width=6).pack(side='left')
            
            audio_combo = ttk.Combobox(audio_frame, textvariable=channel_data['audio_device'],
                                      width=45, font=('Arial', 8), state="readonly")
            audio_combo.pack(side='left', padx=2, fill='x', expand=True)
            channel_data['audio_devices_combo'] = audio_combo
            
            # Обновляем списки
            self.root.after(100, lambda: self.refresh_channel_windows(channel_num))
            self.root.after(200, self.find_audio_devices)
            self.root.after(300, lambda: self.populate_channel_device_lists(channel_num))

    def on_radio_bg_type_change_by_data(self, channel_data):
        """Handle radio background type change - пересоздаем настройки"""
        # Находим номер канала
        for ch_num, ch_data in self.multiplex_channels.items():
            if ch_data is channel_data:
                # Пересоздаем контент канала
                self.create_channel_content(ch_num)
                self.save_config()
                break

    def create_radio_settings(self, channel_data, parent_frame):
        """Create radio settings controls with live update via stdin"""
        try:
            # Первая строка настроек радио
            row2 = ttk.Frame(parent_frame)
            row2.pack(fill='x', pady=1)
            
            # Тип фона
            ttk.Label(row2, text="Background:", font=('Arial', 8), width=10).pack(side='left')
            
            bg_type_combo = ttk.Combobox(row2, textvariable=channel_data['radio_bg_type'],
                                        values=['Color', 'Picture'], 
                                        width=8, font=('Arial', 8), state="readonly")
            bg_type_combo.pack(side='left', padx=2)
            
            # НАЙДЕМ НОМЕР КАНАЛА для этого channel_data
            channel_num = None
            for ch_num, ch_data in self.multiplex_channels.items():
                if ch_data is channel_data:
                    channel_num = ch_num
                    break
            
            if channel_num:
                # Привязка для обновления через stdin
                def update_bg_settings(*args):
                    self.update_radio_gui_settings(channel_num)
                    self.save_config()
                
                # Привязываем изменение типа фона
                channel_data['radio_bg_type'].trace_add('write', lambda *args: self.on_radio_bg_type_change_by_data(channel_data))
            
            # Цвет фона (показывается когда выбран Color)
            if channel_data['radio_bg_type'].get() == 'Color':
                ttk.Label(row2, text="Color:", font=('Arial', 8), width=5).pack(side='left', padx=(5,0))
                
                bg_color_combo = ttk.Combobox(row2, textvariable=channel_data['radio_bg_color'],
                                             values=['black', 'blue', 'darkblue', 'navy', 'darkgreen', 
                                                    'darkred', 'purple', 'violet', 'darkgray', 'gray', 'magenta',
                                                    'cyan', 'green', 'red', 'yellow', 'white'],
                                             width=10, font=('Arial', 8), state="readonly")
                bg_color_combo.pack(side='left', padx=2)
                
                if channel_num:
                    # Привязка для обновления цвета фона
                    channel_data['radio_bg_color'].trace_add('write', lambda *args: self.update_radio_gui_settings(channel_num))
            
            # Картинка (показывается когда выбран Picture)
            else:  # Picture
                bg_picture_entry = ttk.Entry(row2, textvariable=channel_data['radio_bg_picture'],
                                            width=20, font=('Arial', 8))
                bg_picture_entry.pack(side='left', padx=(5, 2))
                
                ttk.Button(row2, text="Browse", width=8,
                          command=lambda: self.browse_radio_picture_by_data(channel_data)).pack(side='left', padx=2)
                
                if channel_num:
                    # Привязка для обновления при изменении пути к картинке
                    def debounced_gui_update(ch_num):
                        if hasattr(self, '_gui_update_timer'):
                            self.root.after_cancel(self._gui_update_timer)
                        self._gui_update_timer = self.root.after(500, lambda: self.update_radio_gui_settings(ch_num))

                    # Привязка:
                    channel_data['radio_text'].trace_add('write', lambda *args: debounced_gui_update(channel_num))
            
            # Вторая строка - основной текст радио
            row3 = ttk.Frame(parent_frame)
            row3.pack(fill='x', pady=1)
            
            ttk.Label(row3, text="Text:", font=('Arial', 8), width=10).pack(side='left')
            
            text_entry = ttk.Entry(row3, textvariable=channel_data['radio_text'],
                                  width=15, font=('Arial', 8))
            text_entry.pack(side='left', padx=2)
            
            if channel_num:
                # Привязка для обновления текста радио через stdin
                channel_data['radio_text'].trace_add('write', lambda *args: self.update_radio_gui_settings(channel_num))
            
            ttk.Label(row3, text="Color:", font=('Arial', 8), width=5).pack(side='left', padx=(5,0))
            
            text_color_combo = ttk.Combobox(row3, textvariable=channel_data['radio_text_color'],
                                           values=['white', 'yellow', 'cyan', 'magenta', 'green',
                                                  'red', 'blue', 'violet', 'orange', 'pink', 'lime'],
                                           width=8, font=('Arial', 8), state="readonly")
            text_color_combo.pack(side='left', padx=2)
            
            if channel_num:
                # Привязка для обновления цвета текста
                channel_data['radio_text_color'].trace_add('write', lambda *args: self.update_radio_gui_settings(channel_num))
            
            ttk.Label(row3, text="Size:", font=('Arial', 8), width=4).pack(side='left', padx=(5,0))
            
            text_size_spin = ttk.Spinbox(row3, from_=10, to=200, 
                                        textvariable=channel_data['radio_text_size'], 
                                        width=5, font=('Arial', 8))
            text_size_spin.pack(side='left', padx=2)
            
            if channel_num:
                # Привязка для обновления размера текста
                channel_data['radio_text_size'].trace_add('write', lambda *args: self.update_radio_gui_settings(channel_num))
            
            # Третья строка - время
            row4 = ttk.Frame(parent_frame)
            row4.pack(fill='x', pady=1)
            
            time_check = ttk.Checkbutton(row4, text="Show time",
                                        variable=channel_data['radio_show_time'])
            time_check.pack(side='left')
            
            if channel_num:
                # Привязка для включения/отключения времени
                channel_data['radio_show_time'].trace_add('write', lambda *args: self.update_radio_gui_settings(channel_num))
            
            ttk.Label(row4, text="Color:", font=('Arial', 8), width=5).pack(side='left', padx=(10,0))
            
            time_color_combo = ttk.Combobox(row4, textvariable=channel_data['radio_time_color'],
                                           values=['yellow', 'white', 'cyan', 'magenta', 'green',
                                                  'red', 'blue', 'violet', 'orange', 'pink', 'lime'],
                                           width=8, font=('Arial', 8), state="readonly")
            time_color_combo.pack(side='left', padx=2)
            
            if channel_num:
                # Привязка для обновления цвета времени
                channel_data['radio_time_color'].trace_add('write', lambda *args: self.update_radio_gui_settings(channel_num))
            
            ttk.Label(row4, text="Size:", font=('Arial', 8), width=4).pack(side='left', padx=(5,0))
            
            time_size_spin = ttk.Spinbox(row4, from_=10, to=200, 
                                        textvariable=channel_data['radio_time_size'], 
                                        width=5, font=('Arial', 8))
            time_size_spin.pack(side='left', padx=2)
            
            if channel_num:
                # Привязка для обновления размера времени
                channel_data['radio_time_size'].trace_add('write', lambda *args: self.update_radio_gui_settings(channel_num))
            
            # Четвертая строка - метаданные
            row5 = ttk.Frame(parent_frame)
            row5.pack(fill='x', pady=1)
            
            # Чекбокс для включения метаданных
            metadata_check = ttk.Checkbutton(row5, text="Show metadata",
                                             variable=channel_data['show_metadata'])
            metadata_check.pack(side='left')
            
            if channel_num:
                # Привязка для включения/отключения метаданных
                channel_data['show_metadata'].trace_add('write', lambda *args: self.update_radio_gui_settings(channel_num))
            
            ttk.Label(row5, text="Size:", font=('Arial', 8), width=4).pack(side='left', padx=(10,0))
            
            metadata_size_spin = ttk.Spinbox(row5, from_=10, to=200, 
                                            textvariable=channel_data['metadata_size'], 
                                            width=5, font=('Arial', 8))
            metadata_size_spin.pack(side='left', padx=2)
            
            if channel_num:
                # Привязка для обновления размера метаданных
                channel_data['metadata_size'].trace_add('write', lambda *args: self.update_radio_gui_settings(channel_num))
            
            ttk.Label(row5, text="Color:", font=('Arial', 8), width=5).pack(side='left', padx=(5,0))
            
            metadata_color_combo = ttk.Combobox(row5, textvariable=channel_data['metadata_color'],
                                               values=['yellow', 'white', 'cyan', 'magenta', 'green',
                                                      'red', 'blue', 'orange', 'violet', 'pink', 'lime'],
                                               width=8, font=('Arial', 8), state="readonly")
            metadata_color_combo.pack(side='left', padx=2)
            
            if channel_num:
                # Привязка для обновления цвета метаданных
                channel_data['metadata_color'].trace_add('write', lambda *args: self.update_radio_gui_settings(channel_num))
            
            ttk.Label(row5, text="Offset:", font=('Arial', 8), width=5).pack(side='left', padx=(5,0))
            
            metadata_offset_spin = ttk.Spinbox(row5, from_=0, to=500, 
                                              textvariable=channel_data['metadata_position'], 
                                              width=5, font=('Arial', 8))
            metadata_offset_spin.pack(side='left', padx=2)
            
            if channel_num:
                # Привязка для обновления позиции метаданных
                channel_data['metadata_position'].trace_add('write', lambda *args: self.update_radio_gui_settings(channel_num))
            
            # Автосохранение конфига при любых изменениях
            if channel_num:
                # Дополнительная привязка для автосохранения
                def trigger_autosave(*args):
                    self.debounced_save()
                
                # Привязываем все переменные к автосохранению
                for key in ['radio_text', 'radio_text_color', 'radio_text_size', 
                           'radio_time_color', 'radio_time_size', 'radio_show_time',
                           'show_metadata', 'metadata_size', 'metadata_color', 'metadata_position']:
                    if key in channel_data:
                        channel_data[key].trace_add('write', trigger_autosave)
            
            self.log_message(f"Created radio settings for CH{channel_num} with stdin updates", "buffer")
            
        except Exception as e:
            self.log_message(f"Error creating radio settings: {e}", "buffer")
            import traceback
            traceback.print_exc()

    def on_url_input_type_change(self, channel_num):
        """Handle URL Input type change (normal/radio)"""
        if channel_num in self.multiplex_channels:
            # Просто пересоздаем контент канала
            self.create_channel_content(channel_num)
            self.save_config()
                                                    
    def on_udp_program_select(self, channel_num):
        """Handle UDP program selection - save PID"""
        channel_data = self.multiplex_channels[channel_num]
        selected_program_name = channel_data['selected_program'].get()
        
        if not selected_program_name or selected_program_name == 'no programs found':
            return
        
        # Находим выбранную программу и сохраняем PID
        for program in channel_data.get('available_programs', []):
            if program['name'] == selected_program_name:
                # Обновляем имя канала
                channel_data['name'].set(program['name'])
                
                # Сохраняем PID для быстрой загрузки
                channel_data['saved_video_pid'] = program.get('video_pid', '')
                channel_data['saved_audio_pid'] = program.get('audio_pid', '')
                
                self.log_message(f"Saved PID for CH{channel_num}:", "buffer")
                self.log_message(f"  Video PID: {program.get('video_pid', 'N/A')}", "buffer")
                self.log_message(f"  Audio PID: {program.get('audio_pid', 'N/A')}", "buffer")
                
                self.save_config()
                break

    def get_udp_stream_info(self, channel_num, validate_only=False):
        """Get program information from UDP source with validation"""
        channel_data = self.multiplex_channels[channel_num]
        url = channel_data['udp_url'].get().strip()
        
        if not url:
            if not validate_only:
                self.log_message(f"❌ No URL specified for CH{channel_num}", "buffer")
                messagebox.showerror("Error", f"Please enter URL for CH{channel_num}")
            return False
        
        ffmpeg_path = self.find_ffmpeg()
        
        try:
            # ВСЕГДА логируем начало анализа
            self.log_message(f"🔍 Analyzing UDP source CH{channel_num}: {url[:80]}...", "buffer")
            
            # Команда для анализа (2 секунды достаточно)
            cmd = [ffmpeg_path, '-i', url, '-t', '2', '-f', 'null', '-']
            
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding='utf-8',
                errors='ignore'
            )
            
            stdout, stderr = process.communicate(timeout=7)
            
            # ⭐ ВАЛИДАЦИЯ: проверяем есть ли поток ⭐
            is_valid = 'Input #0' in stderr and 'Stream #' in stderr
            
            if not is_valid:
                self.log_message(f"❌ CH{channel_num} UDP stream not responding: {url[:50]}...", "buffer")
                return False
            
            # Если только валидация - возвращаем успех
            if validate_only:
                self.log_message(f"✅ CH{channel_num} UDP stream OK: {url[:50]}...", "buffer")
                return True
            
            # ⭐ ПАРСИНГ ПРОГРАММ (даже если validate_only=False, мы все равно парсим) ⭐
            programs = self.parse_ffmpeg_output(stderr)
            
            # ВАЖНО: сохраняем программы ДАЖЕ если их нет
            channel_data['available_programs'] = programs
            
            # Очищаем сохраненные PID если программы не найдены
            if not programs:
                if 'saved_video_pid' in channel_data:
                    channel_data['saved_video_pid'] = ''
                if 'saved_audio_pid' in channel_data:
                    channel_data['saved_audio_pid'] = ''
            
            # Обновляем GUI
            self.root.after(0, lambda ch=channel_num: self.update_udp_program_lists(ch))
            
            # Автоматически выбираем первую программу если есть
            if programs:
                self.root.after(100, lambda: channel_data['selected_program'].set(programs[0]['name']))
                self.log_message(f"✅ Found {len(programs)} programs in CH{channel_num}", "buffer")
            else:
                self.log_message(f"⚠️ No programs found in CH{channel_num}", "buffer")
            
            self.save_config()
            return True
                
        except subprocess.TimeoutExpired:
            self.log_message(f"❌ CH{channel_num} UDP stream timeout (no response)", "buffer")
            return False
        except Exception as e:
            self.log_message(f"❌ Error analyzing UDP source CH{channel_num}: {str(e)[:100]}", "buffer")
            return False

    def parse_ffmpeg_output(self, output):
        """Parse ffmpeg output to extract program information with PIDs"""
        programs = []
        
        lines = output.split('\n')
        current_program = None
        
        for line in lines:
            line = line.strip()
            
            # Ищем программу
            if line.startswith('Program '):
                # Сохраняем предыдущую программу
                if current_program:
                    programs.append(current_program)
                
                # Создаем новую
                match = re.search(r'Program\s+(\d+)', line)
                if match:
                    program_num = int(match.group(1))
                    current_program = {
                        'program_num': program_num,
                        'name': f'Program {program_num}',
                        'video_pid': None,
                        'audio_pid': None,
                        'video_map': None,
                        'audio_map': None
                    }
            
            # Ищем service_name
            elif current_program and 'service_name' in line:
                match = re.search(r'service_name\s*:\s*(.+)', line)
                if match:
                    current_program['name'] = match.group(1).strip()
            
            # Ищем потоки с PID
            elif current_program and line.startswith('Stream #'):
                # Извлекаем PID из квадратных скобок
                pid_match = re.search(r'\[(0x[0-9a-fA-F]+)\]', line)
                if pid_match:
                    pid = pid_match.group(1)
                    
                    # Извлекаем stream map для отладки
                    map_match = re.search(r'Stream #(\d+):(\d+)', line)
                    stream_map = f"{map_match.group(1)}:{map_match.group(2)}" if map_match else None
                    
                    # Определяем тип потока
                    if 'Video:' in line:
                        current_program['video_pid'] = pid
                        current_program['video_map'] = stream_map
                    elif 'Audio:' in line:
                        current_program['audio_pid'] = pid
                        current_program['audio_map'] = stream_map
        
        # Добавляем последнюю программу
        if current_program:
            programs.append(current_program)
        
        # Логируем найденные программы
        self.log_message(f"Parsed {len(programs)} programs:", "buffer")
        for program in programs:
            self.log_message(f"  {program['name']}: Video PID={program['video_pid']}, Audio PID={program['audio_pid']}", "buffer")
        
        return programs
                
    def update_udp_program_lists(self, channel_num):
        """Update program selection combobox for UDP source"""
        channel_data = self.multiplex_channels[channel_num]
        
        if not channel_data.get('available_programs'):
            return
        
        # Находим combobox в content_frame
        for widget in channel_data['content_frame'].winfo_children():
            if isinstance(widget, ttk.Frame):
                for child in widget.winfo_children():
                    if isinstance(child, ttk.Combobox):
                        # Проверяем соседний label
                        siblings = widget.winfo_children()
                        for sibling in siblings:
                            if isinstance(sibling, (ttk.Label, tk.Label)):
                                label_text = sibling.cget('text')
                                if 'Program:' in label_text:
                                    # Заполняем список
                                    program_names = [p['name'] for p in channel_data['available_programs']]
                                    child['values'] = program_names if program_names else ['no programs found']
                                    
                                    if not channel_data['selected_program'].get() and program_names:
                                        channel_data['selected_program'].set(program_names[0])
                                    break
                        
    def populate_channel_device_lists(self, channel_num):
        """Populate device lists for a channel, excluding already used devices"""
        channel_data = self.multiplex_channels[channel_num]
        source_type = channel_data['source_type'].get()
        
        # Разрешенные типы источников
        if source_type not in ["input_devices", "grab_window"]:
            return
        
        # Если устройства еще не найдены, ищем их
        if not self.available_video_devices:
            self.find_video_devices()
        if not self.available_audio_devices:
            self.find_audio_devices()
        
        # Получаем все устройства
        all_video_devices = self.available_video_devices.copy()
        all_audio_devices = self.available_audio_devices.copy()
        
        # Убираем устройства, уже используемые другими каналами
        used_video_devices = set()
        used_audio_devices = set()
        
        for ch_num, ch_data in self.multiplex_channels.items():
            if ch_num == channel_num:
                continue
            if ch_data['source_type'].get() in ["input_devices", "grab_window"] and ch_data['enabled'].get():
                if ch_data['video_device'].get():
                    used_video_devices.add(ch_data['video_device'].get())
                if ch_data['audio_device'].get():
                    used_audio_devices.add(ch_data['audio_device'].get())
        
        # Фильтруем доступные устройства
        available_video = [d for d in all_video_devices if d not in used_video_devices]
        available_audio = [d for d in all_audio_devices if d not in used_audio_devices]
        
        # Обновляем комбобоксы (без лишних условий)
        try:
            # Для input_devices обновляем и видео, и аудио
            if source_type == "input_devices":
                if channel_data.get('video_devices_combo'):
                    channel_data['video_devices_combo']['values'] = available_video
                    if not channel_data['video_device'].get() and available_video:
                        channel_data['video_device'].set(available_video[0])
            
            # Для всех типов обновляем аудио (если есть комбобокс)
            if channel_data.get('audio_devices_combo'):
                channel_data['audio_devices_combo']['values'] = available_audio
                if not channel_data['audio_device'].get() and available_audio:
                    channel_data['audio_device'].set(available_audio[0])
                        
        except Exception as e:
            self.log_message(f"Error updating device lists for CH{channel_num}: {e}", "buffer")
                     
    def refresh_multiplex_devices(self):
        """Refresh device lists for all channels"""
        # Находим устройства (автоматически при первом создании канала)
        if not self.available_video_devices:
            self.find_video_devices()
        if not self.available_audio_devices:
            self.find_audio_devices()
        
        # Update all channels with input devices
        for channel_num, channel_data in self.multiplex_channels.items():
            if channel_data['source_type'].get() == "input_devices":
                self.populate_channel_device_lists(channel_num)
                               
    def on_source_type_change(self, channel_num):
        """Handle source type change with automatic device refresh"""
        # Убедимся что канал существует
        if channel_num not in self.multiplex_channels:
            self.log_message(f"Error: Channel {channel_num} not found when changing source type", "buffer")
            return
        
        channel_data = self.multiplex_channels[channel_num]
        source_type = channel_data['source_type'].get()
        
        # Обновляем контент канала
        self.create_channel_content(channel_num)
        
        if source_type == "URL_Input":
            # Для URL Input очищаем другие настройки
            channel_data['video_device'].set('')
            channel_data['audio_device'].set('')
            channel_data['media_path'].set('')
            channel_data['randomize'].set(False)
            channel_data['selected_program'].set('')
            channel_data['available_programs'] = []
            channel_data['window_title'].set('')  # НОВОЕ
            
        elif source_type == "UDP_MPTS":
            # Для UDP source очищаем выбранные устройства и медиа файлы
            channel_data['video_device'].set('')
            channel_data['audio_device'].set('')
            channel_data['media_path'].set('')
            channel_data['randomize'].set(False)
            channel_data['window_title'].set('')  # НОВОЕ
            channel_data['is_radio'].set(False)
            
        elif source_type == "input_devices":
            # Для input_devices очищаем UDP настройки и медиа файлы
            channel_data['media_path'].set('')
            channel_data['randomize'].set(False)
            channel_data['selected_program'].set('')
            channel_data['available_programs'] = []
            channel_data['window_title'].set('')  # НОВОЕ
            channel_data['is_radio'].set(False)
            # ⭐ Добавляем поиск устройств
            self.root.after(100, self.find_video_devices)
            self.root.after(150, self.find_audio_devices)
            self.root.after(200, lambda: self.populate_channel_device_lists(channel_num))           
            
        elif source_type == "grab_window":  # НОВОЕ
            # Для захвата окна очищаем остальное
            channel_data['video_device'].set('')
            channel_data['media_path'].set('')
            channel_data['randomize'].set(False)
            channel_data['selected_program'].set('')
            channel_data['available_programs'] = []
            channel_data['is_radio'].set(False)
            # Принудительно обновляем список окон
            self.root.after(100, lambda: self.refresh_channel_windows(channel_num))
            self.root.after(200, self.find_audio_devices)
            self.root.after(300, lambda: self.populate_channel_device_lists(channel_num))
            
        else:  # media_folder
            # Для media_folder очищаем выбранные устройства и UDP настройки
            channel_data['video_device'].set('')
            channel_data['audio_device'].set('')
            channel_data['selected_program'].set('')
            channel_data['available_programs'] = []
            channel_data['window_title'].set('')  # НОВОЕ
            channel_data['is_radio'].set(False)
        
        # Обновляем списки устройств для других каналов
        for ch_num in self.multiplex_channels:
            if (ch_num != channel_num and 
                self.multiplex_channels[ch_num]['source_type'].get() == "input_devices"):
                self.populate_channel_device_lists(ch_num)
        
        self.save_config()
        
    def browse_radio_picture_by_data(self, channel_data):
        """Browse for radio background picture using channel_data instead of channel_num"""
        try:
            filename = filedialog.askopenfilename(
                title="Select background picture for radio",
                filetypes=[
                    ("Image files", "*.png *.jpg *.jpeg *.bmp *.gif"),
                    ("All files", "*.*")
                ]
            )
            
            if filename:
                channel_data['radio_bg_picture'].set(filename)
                # Сохраняем конфиг
                self.save_config()
                
                # Обновляем только контент этого канала
                # Находим номер канала по данным
                for ch_num, ch_data in self.multiplex_channels.items():
                    if ch_data is channel_data:
                        self.log_message(f"Set background picture for CH{ch_num}: {filename}", "buffer")
                        # Сохраняем конфиг
                        self.save_config()
                        break
                        
        except Exception as e:
            self.log_message(f"Error browsing for picture: {e}", "buffer")  
            
    def update_radio_gui_settings(self, channel_num):
        """Update GUI settings (color/size/text) via stdin to specific channel process"""
        if not self.is_streaming:
            return
        
        # Получаем данные канала
        channel_data = self.multiplex_channels.get(channel_num)
        if not channel_data:
            return
        
        # Только для радио-каналов URL_Input
        if not (channel_data['source_type'].get() == "URL_Input" and 
               channel_data['is_radio'].get()):
            return
        
        # Находим процесс канала
        if channel_num not in self.channel_processes:
            self.log_message(f"GUI ERROR: CH{channel_num} process not found", "buffer")
            return
        
        process_info = self.channel_processes[channel_num]
        if not process_info.get('stdin'):
            self.log_message(f"GUI ERROR: CH{channel_num} no stdin", "buffer")
            return
        
        stdin = process_info['stdin']
        
        # Проверяем, что процесс жив
        process = process_info.get('process')
        if process and process.poll() is not None:
            self.log_message(f"GUI ERROR: CH{channel_num} process dead", "buffer")
            return
        
        # Получаем индексы фильтров из данных канала
        filter_indices = channel_data.get('filter_indices', {})
        if not filter_indices:
            self.log_message(f"GUI ERROR: CH{channel_num} no filter indices", "buffer")
            return
        
        try:
            # 1. Основной текст радио
            if 'text' in filter_indices:
                text_idx = filter_indices['text']
                radio_text = channel_data['radio_text'].get()
                radio_text_safe = radio_text.replace("'", "'\\''").replace(':', '\\:')
                radio_text_size = channel_data['radio_text_size'].get()
                radio_text_color = channel_data['radio_text_color'].get()
                
                # Проверяем, изменился ли текст
                last_text_key = f"last_gui_text_ch{channel_num}"
                last_text = getattr(self, last_text_key, "")
                if radio_text != last_text:
                    text_cmd = f"CParsed_drawtext_{text_idx} 0.0 reinit text='{radio_text_safe}'\n"
                    stdin.write(text_cmd)
                    stdin.flush()
                    setattr(self, last_text_key, radio_text)
                    self.log_message(f"GUI: CH{channel_num} main text updated", "buffer")
                
                # Проверяем, изменились ли размер/цвет
                last_size_key = f"last_gui_text_size_ch{channel_num}"
                last_color_key = f"last_gui_text_color_ch{channel_num}"
                last_size = getattr(self, last_size_key, None)
                last_color = getattr(self, last_color_key, "")
                
                if last_size != radio_text_size or last_color != radio_text_color:
                    size_color_cmd = f"CParsed_drawtext_{text_idx} 0.0 reinit fontsize={radio_text_size}:fontcolor={radio_text_color}\n"
                    stdin.write(size_color_cmd)
                    stdin.flush()
                    setattr(self, last_size_key, radio_text_size)
                    setattr(self, last_color_key, radio_text_color)
                    self.log_message(f"GUI: CH{channel_num} text size/color updated", "buffer")
            
            # 2. Метаданные (только если были включены при запуске)
            metadata_enabled = channel_data.get('metadata_enabled_at_start', False)
            if 'metadata' in filter_indices and metadata_enabled:
                metadata_idx = filter_indices['metadata']
                metadata_color = channel_data['metadata_color'].get()
                metadata_size = channel_data['metadata_size'].get()
                metadata_position = channel_data['metadata_position'].get()
                
                # Проверяем, изменились ли параметры
                last_mcolor_key = f"last_gui_mcolor_ch{channel_num}"
                last_msize_key = f"last_gui_msize_ch{channel_num}"
                last_mpos_key = f"last_gui_mpos_ch{channel_num}"
                
                last_mcolor = getattr(self, last_mcolor_key, "")
                last_msize = getattr(self, last_msize_key, None)
                last_mpos = getattr(self, last_mpos_key, None)
                
                if (last_mcolor != metadata_color or 
                    last_msize != metadata_size or 
                    last_mpos != metadata_position):
                    
                    metadata_params_cmd = f"CParsed_drawtext_{metadata_idx} 0.0 reinit fontsize={metadata_size}:fontcolor={metadata_color}:y=h/2+{metadata_position}\n"
                    stdin.write(metadata_params_cmd)
                    stdin.flush()
                    
                    setattr(self, last_mcolor_key, metadata_color)
                    setattr(self, last_msize_key, metadata_size)
                    setattr(self, last_mpos_key, metadata_position)
                    self.log_message(f"GUI: CH{channel_num} metadata params updated", "buffer")
            
            # 3. Время (только если было включено при запуске)
            time_enabled = channel_data.get('time_enabled_at_start', False)
            if 'time' in filter_indices and time_enabled:
                time_idx = filter_indices['time']
                time_color = channel_data['radio_time_color'].get()
                time_size = channel_data['radio_time_size'].get()
                
                # Проверяем, изменились ли параметры
                last_tcolor_key = f"last_gui_tcolor_ch{channel_num}"
                last_tsize_key = f"last_gui_tsize_ch{channel_num}"
                
                last_tcolor = getattr(self, last_tcolor_key, "")
                last_tsize = getattr(self, last_tsize_key, None)
                
                if last_tcolor != time_color or last_tsize != time_size:
                    time_params_cmd = f"CParsed_drawtext_{time_idx} 0.0 reinit fontsize={time_size}:fontcolor={time_color}\n"
                    stdin.write(time_params_cmd)
                    stdin.flush()
                    
                    setattr(self, last_tcolor_key, time_color)
                    setattr(self, last_tsize_key, time_size)
                    self.log_message(f"GUI: CH{channel_num} time params updated", "buffer")
                    
            # 4. Фон (цвет или картинка)
            bg_type = channel_data['radio_bg_type'].get()
            if bg_type == "Color":
                bg_color = channel_data['radio_bg_color'].get()
                last_bg_key = f"last_gui_bgcolor_ch{channel_num}"
                last_bg = getattr(self, last_bg_key, "")
                
                if last_bg != bg_color:
                    # Для изменения фона цвета нужно перезапустить входной источник
                    # Это сложнее, можно просто залогировать
                    self.log_message(f"GUI: CH{channel_num} background color changed to {bg_color} (requires stream restart)", "buffer")
                    setattr(self, last_bg_key, bg_color)
            else:
                # Для картинки - просто логируем
                bg_picture = channel_data['radio_bg_picture'].get()
                last_pic_key = f"last_gui_bgpicture_ch{channel_num}"
                last_pic = getattr(self, last_pic_key, "")
                
                if last_pic != bg_picture:
                    self.log_message(f"GUI: CH{channel_num} background picture changed (requires stream restart)", "buffer")
                    setattr(self, last_pic_key, bg_picture)
                    
            # Сохраняем конфиг при изменениях
            self.save_config()
            
        except BrokenPipeError:
            self.log_message(f"GUI ERROR: CH{channel_num} pipe broken", "buffer")
        except Exception as e:
            error_msg = str(e)
            if "I/O operation on closed file" in error_msg:
                self.log_message(f"GUI ERROR: CH{channel_num} stdin closed", "buffer")
            else:
                self.log_message(f"GUI ERROR: CH{channel_num} {error_msg[:80]}", "buffer")          
                      
    def get_active_channels(self):
        """Get list of active (enabled) channels"""
        active_channels = []
        if hasattr(self, 'multiplex_channels'):
            for ch_num, channel_data in self.multiplex_channels.items():
                if channel_data['enabled'].get():
                    active_channels.append((ch_num, channel_data))
        return active_channels                    

    def get_all_filter_indices_for_channel(self, channel_num):
        """Calculate filter indices for ALL filters (text, metadata, time) of a channel"""
        try:
            # Получаем активные каналы
            active_channels = []
            if hasattr(self, 'multiplex_channels'):
                for ch_num, ch_data in self.multiplex_channels.items():
                    if ch_data['enabled'].get():
                        active_channels.append((ch_num, ch_data))
            
            # Фильтруем только радио-каналы
            radio_channels = []
            for ch_num, channel_data in active_channels:
                if (channel_data['source_type'].get() == "URL_Input" and 
                    channel_data['is_radio'].get()):
                    radio_channels.append((ch_num, channel_data))
            
            if not radio_channels:
                return None
            
            # Сортируем по номеру канала
            radio_channels.sort(key=lambda x: x[0])
            
            # Находим позицию нашего канала
            base_index = 0
            for i, (ch, ch_data) in enumerate(radio_channels):
                if ch == channel_num:
                    # Вычисляем индексы для всех возможных фильтров этого канала
                    filter_indices = {}
                    
                    # Основной текст радио - всегда первый фильтр
                    filter_indices['text'] = base_index
                    
                    # Проверяем, был ли параметр включен при запуске
                    if ch_data.get('metadata_enabled_at_start', False):
                        filter_indices['metadata'] = base_index + 1
                        if ch_data.get('time_enabled_at_start', False):
                            filter_indices['time'] = base_index + 2
                    elif ch_data.get('time_enabled_at_start', False):
                        filter_indices['time'] = base_index + 1
                    
                    self.log_message(f"CH{channel_num} filter indices: {filter_indices}", "buffer")
                    return filter_indices
                
                # Увеличиваем base_index для следующего канала
                metadata_enabled = ch_data.get('metadata_enabled_at_start', False)
                time_enabled = ch_data.get('time_enabled_at_start', False)
                
                if metadata_enabled and time_enabled:
                    base_index += 3  # текст + метаданные + время
                elif metadata_enabled or time_enabled:
                    base_index += 2  # текст + метаданные ИЛИ текст + время
                else:
                    base_index += 1  # только текст
            
            return None
            
        except Exception as e:
            self.log_message(f"Error calculating filter indices: {e}", "buffer")
            return None
                       
    def parse_metadata_from_url(self, url):
        """Parse metadata from URL and return (station_name, track_name)"""
        try:
            ffmpeg_path = self.find_ffmpeg()
            
            cmd = [
                ffmpeg_path,
                '-user_agent', 'Mozilla/5.0',
                '-timeout', '2000000',
                '-i', url,
                '-t', '1',
                '-vn', '-an',
                '-f', 'null',
                '-'
            ]
            
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding='utf-8',
                errors='ignore'
            )
            
            stdout, stderr = process.communicate(timeout=7)
            
            station_name = "Radio Station"
            track_name = ""
            
            for line in (stdout + stderr).split('\n'):
                line = line.strip()
                
                if 'icy-name' in line.lower():
                    match = re.search(r'icy-name\s*[:=]\s*(.+)', line, re.IGNORECASE)
                    if match:
                        station_name = match.group(1).strip()
                
                elif 'streamtitle' in line.lower():
                    match = re.search(r'StreamTitle\s*[:=]\s*(.+)', line, re.IGNORECASE)
                    if match:
                        track_name = match.group(1).strip()
                        break  # Нашли трек - выходим
            
            return station_name, track_name
            
        except:
            return "Radio Station", ""
            
    def on_udp_stream_select(self, channel_num, stream_type):
        """Handle UDP stream selection - update channel name"""
        channel_data = self.multiplex_channels[channel_num]
        
        if stream_type == 'video':
            selected = channel_data['video_stream'].get()
        else:
            selected = channel_data['audio_stream'].get()
        
        # Находим имя канала в выбранном потоке
        for stream in channel_data['available_streams']:
            if stream['display'] == selected and 'name' in stream:
                # Обновляем имя канала если оно еще не установлено вручную
                if not channel_data['name'].get() or channel_data['name'].get().startswith('Channel_'):
                    channel_data['name'].set(stream['name'])
                    self.save_config()
                break
        
        # Сохраняем конфигурацию при изменении выбора потока
        self.save_config()

    def on_channel_toggle(self, channel_num):
        """Handle channel enable/disable"""
        # Убедимся что канал существует
        if channel_num not in self.multiplex_channels:
            self.log_message(f"Error: Channel {channel_num} not found when toggling", "buffer")
            return
        
        self.save_config()
        
        # Обновляем UI статистики при изменении активных каналов
        if self.multiplex_mode.get() and hasattr(self, 'channels_stats_container'):
            self.root.after(100, self.init_channels_stats_ui)
        
        # Refresh device lists only for input device channels
        for ch_num in self.multiplex_channels:
            if ch_num in self.multiplex_channels and self.multiplex_channels[ch_num]['source_type'].get() == "input_devices":
                self.populate_channel_device_lists(ch_num)

    def add_channel(self):
        """Add a new channel"""
        # Проверяем что multiplex_channels существует
        if not hasattr(self, 'multiplex_channels'):
            self.multiplex_channels = OrderedDict()
        
        # Если словарь пуст, начинаем с 1
        if not self.multiplex_channels:
            new_channel_num = 1
        else:
            # Ищем максимальный номер канала
            existing_nums = list(self.multiplex_channels.keys())
            if existing_nums:
                new_channel_num = max(existing_nums) + 1
            else:
                new_channel_num = 1
        
        if new_channel_num > self.max_channels:
            messagebox.showwarning("Limit Reached", f"Maximum {self.max_channels} channels allowed")
            return

        self.add_channel_widget(new_channel_num)
        self.update_add_button_state()
        self.save_config()
        
        # Обновляем UI статистики
        if self.multiplex_mode.get() and hasattr(self, 'channels_stats_container'):
            self.root.after(100, self.init_channels_stats_ui)

    def update_add_button_state(self):
        """Enable/disable add button based on channel count"""
        if len(self.multiplex_channels) >= self.max_channels:
            self.add_ch_btn.config(state='disabled')
        else:
            self.add_ch_btn.config(state='normal')            
            
    def browse_media_path(self, channel_num):
        """Browse for media folder ONLY"""
        # Убедимся что канал существует
        if channel_num not in self.multiplex_channels:
            self.log_message(f"Error: Channel {channel_num} not found in multiplex_channels", "buffer")
            return
        
        channel_data = self.multiplex_channels[channel_num]
        
        # Открываем только выбор папки
        path = filedialog.askdirectory(
            title=f"Select media folder for CH{channel_num}"
        )
        
        if path:
            channel_data['media_path'].set(path)
            self.save_config()
            
            # Создаем плейлист для папки
            self.create_media_playlist(channel_num, path)

    def create_media_playlist(self, channel_num, folder_path):
        """Create media list file for ffmpeg input"""
        # Убедимся что channel_num существует в multiplex_channels
        if channel_num not in self.multiplex_channels:
            self.log_message(f"Error: Channel {channel_num} not found in multiplex_channels", "buffer")
            return None
        
        channel_data = self.multiplex_channels[channel_num]
        list_name = f"multiplex_ch{channel_num}_playlist.txt"
        
        # Абсолютный путь
        list_path = os.path.abspath(list_name)
        
        # Получаем медиа файлы
        media_extensions = ['.mp4', '.avi', '.mkv', '.mov', '.flv', '.wmv', '.mpg', '.mpeg', '.ts', '.m2ts', '.m4v']
        media_files = []
        
        try:
            if not os.path.exists(folder_path):
                self.log_message(f"Folder does not exist: {folder_path}", "buffer")
                return None
            
            for root, dirs, files in os.walk(folder_path):
                for file in sorted(files):
                    if any(file.lower().endswith(ext) for ext in media_extensions):
                        media_files.append(os.path.join(root, file))
        except Exception as e:
            self.log_message(f"Error scanning folder {folder_path}: {e}", "buffer")
            return None
        
        if not media_files:
            self.log_message(f"Warning: No media files found in {folder_path}", "buffer")
            # Все равно создаем пустой файл плейлиста
            try:
                with open(list_path, 'w', encoding='utf-8') as f:
                    f.write("# Empty playlist - no media files found\n")
                self.log_message(f"Created empty playlist for CH{channel_num}: {list_path}", "buffer")
                return list_path
            except Exception as e:
                self.log_message(f"Error creating empty playlist: {e}", "buffer")
                return None
        
        # Случайный порядок если нужно
        if channel_data['randomize'].get():
            random.shuffle(media_files)
        
        # Создаем файл списка для ffmpeg
        try:
            with open(list_path, 'w', encoding='utf-8') as f:
                for file_path in media_files:
                    # Абсолютный путь и экранирование
                    abs_path = os.path.abspath(file_path)
                    # Заменяем обратные слеши на прямые для Windows
                    safe_path = abs_path.replace("\\", "/").replace("'", "'\\''")
                    f.write(f"file '{safe_path}'\n")
            
            self.log_message(f"Created playlist for CH{channel_num}: {list_path} ({len(media_files)} files)", "buffer")
            return list_path
            
        except Exception as e:
            self.log_message(f"Error creating playlist {list_path}: {e}", "buffer")
            return None

    def load_multiplex_channels(self):
        """Load multiplex channels from saved config - основной метод"""
        try:
            # Уже загружены?
            if hasattr(self, 'multiplex_channels_loaded') and self.multiplex_channels_loaded:
                return
                
            self.log_message("Loading multiplex channels from stored config...", "buffer")
            
            # Проверяем, есть ли сохраненный конфиг
            if hasattr(self, 'multiplex_config_from_file') and self.multiplex_config_from_file:
                channels_config = self.multiplex_config_from_file
                
                # Сортируем по номеру канала
                sorted_items = sorted(channels_config.items(), key=lambda x: int(x[0]))
                
                for ch_num_str, ch_config in sorted_items:
                    ch_num = int(ch_num_str)
                    
                    # Создаем виджет канала если его нет
                    if ch_num not in self.multiplex_channels:
                        self.add_channel_widget(ch_num)
                    
                    if ch_num in self.multiplex_channels:
                        channel_data = self.multiplex_channels[ch_num]
                        
                        # Основные настройки
                        channel_data['enabled'].set(bool(ch_config.get('enabled', True if ch_num == 1 else False)))
                        channel_data['name'].set(str(ch_config.get('name', f'Channel_{ch_num}')))
                        channel_data['source_type'].set(str(ch_config.get('source_type', 'input_devices')))
                        channel_data['video_device'].set(str(ch_config.get('video_device', '')))
                        channel_data['audio_device'].set(str(ch_config.get('audio_device', '')))
                        channel_data['window_title'].set(str(ch_config.get('window_title', '')))
                        channel_data['media_path'].set(str(ch_config.get('media_path', '')))
                        channel_data['randomize'].set(bool(ch_config.get('randomize', False)))
                        channel_data['udp_url'].set(str(ch_config.get('udp_url', '')))
                        channel_data['url_input'].set(str(ch_config.get('url_input', '')))
                        channel_data['is_radio'].set(bool(ch_config.get('is_radio', False)))
                        channel_data['radio_bg_type'].set(str(ch_config.get('radio_bg_type', 'Color')))
                        channel_data['radio_bg_color'].set(str(ch_config.get('radio_bg_color', 'black')))
                        channel_data['radio_bg_picture'].set(str(ch_config.get('radio_bg_picture', '')))
                        channel_data['radio_text'].set(str(ch_config.get('radio_text', 'Radio Station')))
                        channel_data['radio_show_time'].set(bool(ch_config.get('radio_show_time', True)))
                        channel_data['radio_text_color'].set(str(ch_config.get('radio_text_color', 'white')))
                        channel_data['radio_text_size'].set(int(ch_config.get('radio_text_size', 120)))
                        channel_data['radio_time_color'].set(str(ch_config.get('radio_time_color', 'yellow')))
                        channel_data['radio_time_size'].set(int(ch_config.get('radio_time_size', 50)))
                        channel_data['show_metadata'].set(bool(ch_config.get('show_metadata', True)))
                        channel_data['metadata_size'].set(int(ch_config.get('metadata_size', 40)))
                        channel_data['metadata_color'].set(str(ch_config.get('metadata_color', 'violet')))
                        channel_data['metadata_position'].set(int(ch_config.get('metadata_position', 120)))                        
                                                
                        # Сохраняем PID если есть
                        if 'video_pid' in ch_config:
                            channel_data['saved_video_pid'] = str(ch_config['video_pid'])
                        if 'audio_pid' in ch_config:
                            channel_data['saved_audio_pid'] = str(ch_config['audio_pid'])
                        if 'audio_device' in ch_config:
                            channel_data['audio_device'].set(ch_config['audio_device'])                        
                        # Обновляем контент
                        self.create_channel_content(ch_num, skip_refresh=True)
                        
                        # Если это input_devices, обновляем списки устройств
                        if channel_data['source_type'].get() == "input_devices":
                            self.root.after(300, lambda n=ch_num: self.populate_channel_device_lists(n))
                        
                        self.log_message(f"  ✓ CH{ch_num}: '{channel_data['name'].get()}'", "buffer")
                
                self.log_message(f"Loaded {len(sorted_items)} channels from config", "buffer")
                
            else:
                # Если нет сохраненного конфига, создаем CH1 по умолчанию
                if not self.multiplex_channels:
                    self.create_default_channel_1()
            
            self.multiplex_channels_loaded = True
            
            # Обновляем состояние кнопки
            self.update_add_button_state()
            
        except Exception as e:
            self.log_message(f"Error loading multiplex channels: {e}", "buffer")
            import traceback
            traceback.print_exc()
                
    def create_stats_tab(self, parent):
        """Create statistics tab as the main tab"""
        
        # Control Buttons - ДОБАВИТЬ ЭТУ КНОПКУ
        control_frame = ttk.Frame(parent)
        control_frame.pack(fill='x', pady=6)
        
        # OBS Studio Control - новый блок
        obs_frame = ttk.LabelFrame(parent, text="OBS Studio Control", padding="6")
        obs_frame.pack(fill='x', pady=(0, 6))
        
        # СКРЫТАЯ СТРОКА С ПУТЕМ (но занимает место для правильного расположения)
        # ttk.Label(obs_frame, text="OBS Path:", font=('Arial', 9)).grid(row=0, column=0, sticky='w', pady=2)
        # obs_path_entry = ttk.Entry(obs_frame, textvariable=self.obs_path, width=40, font=('Arial', 9))
        # obs_path_entry.grid(row=0, column=1, padx=5, pady=2, columnspan=2)
        # ttk.Button(obs_frame, text="Browse", 
                  # command=self.browse_obs_path, width=8).grid(row=0, column=3, padx=2, pady=2)
        
        # Заполнитель для сохранения структуры grid
        ttk.Frame(obs_frame, height=1).grid(row=0, column=0, columnspan=4, pady=0)

        # OBS control buttons
        obs_btn_frame = ttk.Frame(obs_frame)
        obs_btn_frame.grid(row=1, column=0, columnspan=2, sticky='w', pady=(5, 2))
        
        self.obs_start_btn = ttk.Button(obs_btn_frame, text="▶ Run OBS Studio", 
                                       command=self.start_obs, width=18)
        self.obs_start_btn.pack(side='left', padx=2)
        
        self.obs_stop_btn = ttk.Button(obs_btn_frame, text="⏹ Stop OBS", 
                                      command=self.stop_obs, state='disabled', width=12)
        self.obs_stop_btn.pack(side='left', padx=2)
        
        ttk.Checkbutton(obs_btn_frame, text="Auto-start", 
                       variable=self.obs_auto_start, 
                       command=self.save_config).pack(side='left', padx=8)
        
        # Playlist playback button next to OBS controls
        playlist_btn_frame = ttk.Frame(obs_frame)
        playlist_btn_frame.grid(row=1, column=2, columnspan=2, sticky='e', pady=(5, 2))
        
        ttk.Button(playlist_btn_frame, text="🎵 Start Playlist Playback", 
                  command=self.playlist_manager.start_playlist_playback, width=23).pack(side='right', padx=2)
        
        ttk.Checkbutton(playlist_btn_frame, text="Auto-start", 
                       variable=self.playlist_manager.playlist_auto_start, 
                       command=self.save_config).pack(side='right', padx=8)
        
        # RF Modulator Status
        rf_frame = ttk.LabelFrame(parent, text="RF Modulator Status", padding="6")
        rf_frame.pack(fill='x', pady=(0, 6))
        rf_frame.columnconfigure(1, weight=1)  # Пресет займет все свободное пространство
        rf_frame.columnconfigure(2, weight=0)  # Frequency фиксированная
        rf_frame.columnconfigure(3, weight=0)  # Кнопка фиксированная
        
        
        # Current preset and frequency - ИЗМЕНЕНО: шире комбобокс и сдвиг frequency
        ttk.Label(rf_frame, text="Preset:", font=('Arial', 10)).grid(row=0, column=0, sticky='w', pady=2)
        self.mod_preset_combo = ttk.Combobox(rf_frame, textvariable=self.modulator_preset,
                                       values=list(self.modulator_presets.keys()),
                                       width=25, font=('Arial', 10), state='readonly')  # ИЗМЕНЕНО: width=25
        self.mod_preset_combo.grid(row=0, column=1, padx=5, pady=2, sticky='ew')
        self.mod_preset_combo.bind('<<ComboboxSelected>>', self.on_preset_change)

        ttk.Label(rf_frame, text="Frequency:", font=('Arial', 10)).grid(row=0, column=2, sticky='w', pady=2, padx=(10,0))

        # Создаем объединенный фрейм для поля ввода и текста
        frequency_frame = ttk.Frame(rf_frame)
        frequency_frame.grid(row=0, column=3, padx=2, pady=2, sticky='w')

        frequency_entry = ttk.Entry(frequency_frame, textvariable=self.frequency_mhz_var, width=5, font=('Arial', 10))
        frequency_entry.pack(side='left')

        # Текст "MHz" сразу после поля ввода
        ttk.Label(frequency_frame, text="MHz", font=('Arial', 10)).pack(side='left', padx=(2, 0))

        # Confirm button остается в той же колонке
        ttk.Button(rf_frame, text="Confirm", 
                  command=self.confirm_frequency, width=8).grid(row=0, column=4, padx=(5, 0), pady=2)
        
        # RF Gain control (привязано к XML-RPC) - реверсивный
        ttk.Label(rf_frame, text="RF Level:", font=('Arial', 10)).grid(row=1, column=0, sticky='w', pady=2)

        # Создаем фрейм для объединения слайдера и значения
        rf_gain_frame = ttk.Frame(rf_frame)
        rf_gain_frame.grid(row=1, column=1, padx=5, pady=2, sticky='w')

        # Слайдер с настройкой для целых значений
        rf_gain_scale = ttk.Scale(rf_gain_frame, from_=0, to=100, variable=self.rf_gain_percent,
                                 orient='horizontal', length=240, command=self.on_rf_gain_change)

        # Принудительно устанавливаем начальное целое значение
        self.rf_gain_percent.set(int(self.rf_gain_percent.get()))

        # Добавляем поддержку колесика мыши
        rf_gain_scale.bind('<Enter>', lambda e: rf_gain_scale.focus_set())
        rf_gain_scale.bind('<MouseWheel>', self.on_rf_gain_mouse_wheel)

        # ДОБАВЛЯЕМ: принудительное обновление значения
        def update_rf_value(event):
            percent = int(round(float(self.rf_gain_percent.get())))
            self.rf_gain_percent.set(percent)

        rf_gain_scale.bind('<ButtonRelease-1>', update_rf_value)  # при отпускании мыши
        rf_gain_scale.bind('<Leave>', update_rf_value)            # при уходе курсора

        rf_gain_scale.pack(side='left')

        # Значение процентов сразу после слайдера
        rf_gain_value_label = ttk.Label(rf_gain_frame, textvariable=self.rf_gain_percent, 
                                       font=('Arial', 10, 'bold'), width=3)
        rf_gain_value_label.pack(side='left', padx=(8, 2))

        # Символ процента
        ttk.Label(rf_gain_frame, text="%", font=('Arial', 10)).pack(side='left')

        # Modulator control buttons остается в той же колонке
        modulator_btn_frame = ttk.Frame(rf_frame)
        modulator_btn_frame.grid(row=1, column=2, columnspan=3, sticky='e', pady=2)

        self.modulator_start_btn = ttk.Button(modulator_btn_frame, text="▶ Start Broadcast", 
                                            command=self.start_modulator, width=18)
        self.modulator_start_btn.pack(side='left', padx=2)

        self.modulator_stop_btn = ttk.Button(modulator_btn_frame, text="⏹ Stop Broadcast", 
                                           command=self.stop_modulator, state='disabled', width=18)
        self.modulator_stop_btn.pack(side='left', padx=2)
        
        # Encoder Statistics
        # Encoder Statistics
        enc_frame = ttk.LabelFrame(parent, text="Encoder Statistics", padding="6")
        enc_frame.pack(fill='x', pady=(0, 6))
        
        # Основной контейнер
        stats_container = ttk.Frame(enc_frame)
        stats_container.pack(fill='x')
        
        # ===== ЛЕВАЯ КОЛОНКА: ОСНОВНОЙ ЭНКОДЕР =====
        main_frame = ttk.Frame(stats_container)
        main_frame.pack(side='left', padx=(0, 15))
        
        # Заголовок MAIN заменили на Multiplex
        ttk.Label(main_frame, text="Multiplex", font=('Arial', 8, 'bold')).pack(anchor='w')
        
        # Speed (S:) - компактно, но сохраняем подпись Speed
        speed_frame = ttk.Frame(main_frame)
        speed_frame.pack(anchor='w', pady=(2, 0))
        ttk.Label(speed_frame, text="Speed:", font=('Arial', 8, 'bold')).pack(side='left')
        self.speed_label = ttk.Label(speed_frame, textvariable=self.encoder_speed, 
                                   font=('Arial', 11, 'bold'))
        self.speed_label.pack(side='left', padx=(2, 0))
        
        # Bitrate (B:) - сохраняем подпись Bitrate
        bitrate_frame = ttk.Frame(main_frame)
        bitrate_frame.pack(anchor='w', pady=(2, 0))
        ttk.Label(bitrate_frame, text="Bitrate:", font=('Arial', 8, 'bold')).pack(side='left')
        self.bitrate_label = ttk.Label(bitrate_frame, textvariable=self.encoder_bitrate, 
                                     foreground='blue', font=('Arial', 11, 'bold'))
        self.bitrate_label.pack(side='left', padx=(2, 0))
        ttk.Label(bitrate_frame, text="k", font=('Arial', 8)).pack(side='left')
        
        # ===== ПРАВАЯ КОЛОНКА: КАНАЛЫ =====
        self.channels_frame = ttk.Frame(stats_container)
        
        if self.multiplex_mode.get():
            self.channels_frame.pack(side='left', fill='x', expand=True)
            self.channels_stats_container = ttk.Frame(self.channels_frame)
            self.channels_stats_container.pack(fill='x')
            # Создаем UI один раз
            # self.init_channels_stats_ui()
        
        # Buffer Statistics
        buf_frame = ttk.LabelFrame(parent, text="UDP Buffer Statistics", padding="6")
        buf_frame.pack(fill='x', pady=(0, 6))
        
        # Первая строка - битрейты
        ttk.Label(buf_frame, text="UDP Input:", font=('Arial', 9)).grid(row=0, column=0, sticky='w', pady=1)
        self.input_bitrate_label = ttk.Label(buf_frame, textvariable=self.buffer_input_bitrate, 
                 font=('Arial', 10, 'bold'))
        self.input_bitrate_label.grid(row=0, column=1, sticky='w', padx=2, pady=1)
        ttk.Label(buf_frame, text="kbps", font=('Arial', 9)).grid(row=0, column=2, sticky='w', pady=1)
        
        ttk.Label(buf_frame, text="ZMQ Output:", font=('Arial', 9, 'bold')).grid(row=0, column=3, sticky='w', pady=1, padx=(8,0))
        self.zmq_output_label = ttk.Label(buf_frame, textvariable=self.buffer_output_bitrate, 
                 font=('Arial', 10, 'bold'), foreground='blue')
        self.zmq_output_label.grid(row=0, column=4, sticky='w', padx=2, pady=1)
        ttk.Label(buf_frame, text="kbps", font=('Arial', 9)).grid(row=0, column=5, sticky='w', pady=1)
        
        ttk.Label(buf_frame, text="Target:", font=('Arial', 9)).grid(row=0, column=6, sticky='w', pady=1, padx=(8,0))
        ttk.Label(buf_frame, textvariable=self.buffer_target, 
                 font=('Arial', 9)).grid(row=0, column=7, sticky='w', padx=2, pady=1)
        ttk.Label(buf_frame, text="kbps", font=('Arial', 9)).grid(row=0, column=8, sticky='w', pady=1)
        
        # Вторая строка - статистика и отклонение
        ttk.Label(buf_frame, text="Buffer:", font=('Arial', 9)).grid(row=1, column=0, sticky='w', pady=1)
        self.buffer_fill_label = ttk.Label(buf_frame, textvariable=self.buffer_fill, 
                 font=('Arial', 9, 'bold'))
        self.buffer_fill_label.grid(row=1, column=1, sticky='w', padx=2, pady=1, columnspan=2)
        
        ttk.Label(buf_frame, text="Deviation:", font=('Arial', 9)).grid(row=1, column=3, sticky='w', pady=1, padx=(8,0))
        self.deviation_label = ttk.Label(buf_frame, textvariable=self.bitrate_deviation, 
                 font=('Arial', 9))
        self.deviation_label.grid(row=1, column=4, sticky='w', padx=2, pady=1)
        
        ttk.Label(buf_frame, text="Recv:", font=('Arial', 9)).grid(row=1, column=5, sticky='w', pady=1, padx=(8,0))
        ttk.Label(buf_frame, textvariable=self.buffer_received, 
                 font=('Arial', 9)).grid(row=1, column=6, sticky='w', padx=2, pady=1)
        
        ttk.Label(buf_frame, text="Sent:", font=('Arial', 9)).grid(row=1, column=7, sticky='w', pady=1, padx=(8,0))
        ttk.Label(buf_frame, textvariable=self.buffer_sent, 
                 font=('Arial', 9)).grid(row=1, column=8, sticky='w', padx=2, pady=1)
        
        ttk.Label(buf_frame, text="Drop:", font=('Arial', 9)).grid(row=1, column=9, sticky='w', pady=1, padx=(8,0))
        ttk.Label(buf_frame, textvariable=self.buffer_dropped, 
                 foreground='red', font=('Arial', 9)).grid(row=1, column=10, sticky='w', padx=2, pady=1)
        
        # Control Buttons
        control_frame = ttk.Frame(parent)
        control_frame.pack(fill='x', pady=6)
        
        self.start_btn = ttk.Button(control_frame, text="▶ Start", 
                                   command=self.start_streaming, width=10)
        self.start_btn.pack(side='left', padx=2)
        
        self.stop_btn = ttk.Button(control_frame, text="⏹ Stop", 
                                  command=self.stop_streaming, state='disabled', width=10)
        self.stop_btn.pack(side='left', padx=8)
        
        # Auto-start checkboxes
        ttk.Checkbutton(control_frame, text="Auto-start", 
                       variable=self.auto_start, 
                       command=self.save_config).pack(side='left', padx=8)
        
        ttk.Checkbutton(control_frame, text="Auto Broadcast", 
                       variable=self.modulator_auto_start, 
                       command=self.save_config).pack(side='left', padx=8)
        
        ttk.Checkbutton(control_frame, text="Auto Overlay", 
                       variable=self.overlay_auto_start, 
                       command=self.save_config).pack(side='left', padx=8)
        
        # Overlay button that syncs with overlay tab
        
        ttk.Button(control_frame, text="❌ Exit", 
                  command=self.quit_app, width=8).pack(side='right', padx=2)
                                
    def format_modulation_scheme(self, preset_name):
        """Format modulation scheme for overlay display from JSON parameters"""
        try:
            if not preset_name or preset_name not in self.modulator_presets:
                return "No Preset"
            
            preset_info = self.modulator_presets[preset_name]
            json_file = preset_info.get('json_file')
            
            if json_file and os.path.exists(json_file):
                with open(json_file, 'r', encoding='utf-8') as f:
                    scheme_data = json.load(f)
                
                if 'parameters' in scheme_data:
                    params = scheme_data['parameters']
                    
                    # Извлекаем нужные параметры
                    modulation = params.get('modulation', '')
                    code_rate = params.get('code_rate', '')
                    fft_size = params.get('fft_size', '')
                    guard_interval = params.get('guard_interval', '')
                    pilot_pattern = params.get('pilot_pattern', '')
                    
                    # Форматируем в красивый вид
                    parts = []
                    if modulation:
                        parts.append(modulation)
                    if code_rate:
                        parts.append(code_rate)
                    if fft_size:
                        # Убираем 'K' если есть для более компактного вида
                        fft_display = fft_size.replace('K', '') + 'K'
                        parts.append(fft_display)
                    if guard_interval:
                        parts.append(guard_interval)
                    if pilot_pattern:
                        parts.append(pilot_pattern)
                    
                    if parts:
                        return ' '.join(parts)
            
            # Fallback: если JSON нет, используем старый метод
            return self.get_preset_display_name(preset_name)
            
        except Exception as e:
            self.log_message(f"Error formatting modulation scheme: {e}", "overlay")
            return self.get_preset_display_name(preset_name)

    def update_modulator_presets(self):
        """Update modulator presets from gnu_modulator_presets directory"""
        base_dir = os.path.dirname(os.path.abspath(__file__))
        presets_dir = os.path.join(base_dir, "gnu_modulator_presets")
        schemes_dir = os.path.join(base_dir, "saved_schemes")
        
        # Создаем папки если их нет
        os.makedirs(presets_dir, exist_ok=True)
        os.makedirs(schemes_dir, exist_ok=True)
        
        if os.path.exists(presets_dir):
            # Get all .py files in presets directory
            preset_files = [f for f in os.listdir(presets_dir) if f.endswith('.py')]
            
            # Create preset mapping
            self.modulator_presets = {}
            for preset_file in preset_files:
                preset_name = preset_file.replace('.py', '')
                full_script_path = os.path.join(presets_dir, preset_file)
                
                # JSON файл с ТАКИМ ЖЕ именем
                json_file_path = os.path.join(schemes_dir, preset_file.replace('.py', '.json'))
                
                muxrate = "1030284.040170"  # значение по умолчанию
                description = f"Custom preset: {preset_name}"
                
                if os.path.exists(json_file_path):
                    try:
                        with open(json_file_path, 'r') as f:
                            scheme_data = json.load(f)
                        
                        # Берем битрейт из JSON
                        if 'results' in scheme_data and 'normal_bitrate_bps' in scheme_data['results']:
                            muxrate = f"{scheme_data['results']['normal_bitrate_bps']:.6f}"
                        
                        # Формируем описание из параметров
                        if 'parameters' in scheme_data:
                            params = scheme_data['parameters']
                            description = (f"{params.get('modulation', '')} {params.get('code_rate', '')} | "
                                         f"{params.get('fft_size', '')} | GI: {params.get('guard_interval', '')}")
                        
                        self.log_message(f"✅ Loaded parameters from JSON for: {preset_name}", "buffer")
                        
                    except Exception as e:
                        self.log_message(f"⚠️ Error loading JSON for {preset_name}: {e}", "buffer")
                        # Если JSON не загрузился, парсим из имени файла
                        bitrate_match = re.search(r'(\d+)kbps', preset_name)
                        if bitrate_match:
                            muxrate = f"{int(bitrate_match.group(1)) * 1000:.6f}"
                else:
                    # Если JSON нет, парсим из имени файла
                    bitrate_match = re.search(r'(\d+)kbps', preset_name)
                    if bitrate_match:
                        muxrate = f"{int(bitrate_match.group(1)) * 1000:.6f}"
                    self.log_message(f"ℹ️ No JSON found for {preset_name}, using filename parsing", "buffer")
                    
                self.modulator_presets[preset_name] = {
                    'script': full_script_path,
                    'muxrate': muxrate,
                    'description': description,
                    'json_file': json_file_path if os.path.exists(json_file_path) else None
                }
        
        # Update combobox
        if hasattr(self, 'mod_preset_combo'):
            self.mod_preset_combo['values'] = list(self.modulator_presets.keys())
            # Устанавливаем первый пресет если не выбран
            if not self.modulator_preset.get() and self.modulator_presets:
                first_preset = list(self.modulator_presets.keys())[0]
                self.modulator_preset.set(first_preset)
                # Рассчитываем настройки для первого пресета
                self.calculate_video_settings_from_preset(first_preset)
        
        self.save_config()
             
    def create_settings_tab(self, parent):
        
        # RF Modulator Settings - новый блок с выбором устройства
        rf_frame = ttk.LabelFrame(parent, text="RF Modulator Settings", padding="6")
        rf_frame.pack(fill='x', pady=(0, 6))
                              
        # Выбор устройства
        ttk.Label(rf_frame, text="Device:", font=('Arial', 10)).grid(row=0, column=0, sticky='w', pady=2)
        
        # Выпадающий список устройств
        device_combo = ttk.Combobox(rf_frame, textvariable=self.selected_device,
                                   values=['plutosdr', 'limesdr', 'hackrf', 'usrp'],
                                   width=10, font=('Arial', 10), state='readonly')
        device_combo.grid(row=0, column=1, padx=5, pady=2, sticky='w')
        device_combo.bind('<<ComboboxSelected>>', self.on_device_change)
        
        # Device Arguments (универсальное поле для всех устройств)
        ttk.Label(rf_frame, text="Device Args:", font=('Arial', 10)).grid(row=1, column=0, sticky='w', pady=2)
        self.device_args_entry = ttk.Entry(rf_frame, textvariable=self.device_arguments, 
                                          width=40, font=('Arial', 10))
        self.device_args_entry.grid(row=1, column=1, padx=5, pady=2, columnspan=2, sticky='ew')
        
        # GNU Radio control button
        ttk.Button(rf_frame, text="🔄 Reconnect GNU Radio", 
                  command=self.reconnect_gnuradio, width=24).grid(row=0, column=2, sticky='e', padx=2)

        # Инициализация выбора устройства
        self.on_device_change()          
                                              
        ttk.Button(rf_frame, text="FFmpeg Command", 
                  command=self.show_multiplex_ffmpeg_command, width=17).grid(row=0, column=3, sticky='e', padx=2)
        
        # Input Devices Frame - компактная версия
        input_frame = ttk.LabelFrame(parent, text="Input Devices", padding="6")
        input_frame.pack(fill='x', pady=(0, 6))
        
        # Video input device - компактная строка
        video_frame = ttk.Frame(input_frame)
        video_frame.pack(fill='x', pady=2)
        
        ttk.Label(video_frame, text="Video:", font=('Arial', 9), width=6).pack(side='left')
        self.video_device_combo = ttk.Combobox(video_frame, textvariable=self.video_input_device, 
                                              width=30, font=('Arial', 9))
        self.video_device_combo.pack(side='left', padx=2, pady=2, fill='x', expand=True)
        
        # Кнопка Find - компактная
        ttk.Button(video_frame, text="Find", 
                  command=self.find_video_devices, width=6).pack(side='left', padx=2)
        
        # Audio input device - компактная строка
        audio_frame = ttk.Frame(input_frame)
        audio_frame.pack(fill='x', pady=2)
        
        ttk.Label(audio_frame, text="Audio:", font=('Arial', 9), width=6).pack(side='left')
        self.audio_device_combo = ttk.Combobox(audio_frame, textvariable=self.audio_input_device, 
                                              width=30, font=('Arial', 9))
        self.audio_device_combo.pack(side='left', padx=2, pady=2, fill='x', expand=True)
        
        # Кнопка Find - компактная
        ttk.Button(audio_frame, text="Find", 
                  command=self.find_audio_devices, width=6).pack(side='left', padx=2)
        
        # Multiplex Mode Checkbox - справа в том же боксе
        multiplex_check_frame = ttk.Frame(input_frame)
        multiplex_check_frame.pack(fill='x', pady=(5, 0))
        
        # Чекбокс для включения режима multiplex
        multiplex_check = ttk.Checkbutton(multiplex_check_frame, 
                                         text="Multiplex Mode (use channels from Multiplex tab)",
                                         variable=self.multiplex_mode,
                                         command=self.save_config)
        multiplex_check.pack(anchor='w', padx=2)
        
        # Top frame for Network and Buffer settings
        top_frame = ttk.Frame(parent)
        top_frame.pack(fill='x', pady=(0, 6))
        
        # Network Settings - слева
        net_frame = ttk.LabelFrame(top_frame, text="Network Settings", padding="6")
        net_frame.pack(side='left', fill='both', expand=True, padx=(0, 3))
        
        ttk.Label(net_frame, text="Input:", font=('Arial', 9)).grid(row=0, column=0, sticky='w', pady=1)
        ttk.Entry(net_frame, textvariable=self.localhost_ip, width=12, font=('Arial', 9)).grid(row=0, column=1, padx=2, pady=1)
        ttk.Label(net_frame, text=":", font=('Arial', 9)).grid(row=0, column=2, sticky='w', pady=1)
        ttk.Entry(net_frame, textvariable=self.udp_input_port, width=6, font=('Arial', 9)).grid(row=0, column=3, padx=2, pady=1)
        ttk.Label(net_frame, text="(UDP)", font=('Arial', 9)).grid(row=0, column=4, sticky='w', pady=1, padx=2)
        
        ttk.Label(net_frame, text="Output:", font=('Arial', 9)).grid(row=1, column=0, sticky='w', pady=1)
        ttk.Entry(net_frame, textvariable=self.output_ip, width=12, font=('Arial', 9)).grid(row=1, column=1, padx=2, pady=1)
        ttk.Label(net_frame, text=":", font=('Arial', 9)).grid(row=1, column=2, sticky='w', pady=1)
        udp_output_entry = ttk.Entry(net_frame, textvariable=self.udp_output_port, width=6, font=('Arial', 9))
        udp_output_entry.grid(row=1, column=3, padx=2, pady=1)
        # # ⚡ ИЗМЕНЕНИЕ: zmq_port вместо udp_port
        udp_output_entry.bind('<FocusOut>', lambda e: self.set_gnuradio_variable("zmq_port", self.udp_output_port.get()))
        ttk.Label(net_frame, text="(ZMQ)", font=('Arial', 9)).grid(row=1, column=4, sticky='w', pady=1, padx=2)
        
        ttk.Label(net_frame, text="Muxrate:", font=('Arial', 9)).grid(row=2, column=0, sticky='w', pady=1)
        ttk.Entry(net_frame, textvariable=self.muxrate, width=15, font=('Arial', 9)).grid(row=2, column=1, padx=2, pady=1, columnspan=2)
        ttk.Label(net_frame, text="bps", font=('Arial', 9)).grid(row=2, column=3, sticky='w', pady=1)
        
        # UDP Buffer Settings - справа
        buf_frame = ttk.LabelFrame(top_frame, text="UDP ZMQ Buffer Set", padding="6")
        buf_frame.pack(side='right', fill='both', expand=True, padx=(3, 0))
        
        ttk.Label(buf_frame, text="Target:", font=('Arial', 9)).grid(row=0, column=0, sticky='w', pady=1)
        ttk.Spinbox(buf_frame, from_=10, to=8000, textvariable=self.target_buffer, width=8, font=('Arial', 9)).grid(row=0, column=1, padx=2, pady=1)
        
        ttk.Label(buf_frame, text="Min:", font=('Arial', 9)).grid(row=0, column=2, sticky='w', pady=1, padx=(8,0))
        ttk.Spinbox(buf_frame, from_=10, to=4000, textvariable=self.min_buffer, width=8, font=('Arial', 9)).grid(row=0, column=3, padx=2, pady=1)
        
        ttk.Label(buf_frame, text="Max:", font=('Arial', 9)).grid(row=1, column=0, sticky='w', pady=1)
        ttk.Spinbox(buf_frame, from_=100, to=100000, textvariable=self.max_buffer, width=8, font=('Arial', 9)).grid(row=1, column=1, padx=2, pady=1)
        
        ttk.Label(buf_frame, text="Calib Pkts:", font=('Arial', 9)).grid(row=1, column=2, sticky='w', pady=1, padx=(8,0))
        ttk.Spinbox(buf_frame, from_=10, to=8000, textvariable=self.calibration_packets, width=8, font=('Arial', 9)).grid(row=1, column=3, padx=2, pady=1)
        
        ttk.Label(buf_frame, text="Calib Time:", font=('Arial', 9)).grid(row=2, column=0, sticky='w', pady=1)
        ttk.Spinbox(buf_frame, from_=1, to=50.0, increment=1, textvariable=self.calibration_time, width=8, font=('Arial', 9)).grid(row=2, column=1, padx=2, pady=1)
        
        ttk.Label(buf_frame, text="Buffer Divider:", font=('Arial', 9)).grid(row=2, column=2, sticky='w', pady=1, padx=(8,0))
        ttk.Spinbox(buf_frame, from_=1, to=16, textvariable=self.buffer_divider, width=8, font=('Arial', 9)).grid(row=2, column=3, padx=2, pady=1)
        
        # Middle frame for Video, Audio and Metadata
        middle_frame = ttk.Frame(parent)
        middle_frame.pack(fill='x', pady=(0, 6))
        
        # Video Settings
        vid_frame = ttk.LabelFrame(middle_frame, text="Video Settings", padding="6")
        vid_frame.pack(fill='x', pady=(0, 6))
        
        # Первая строка - Resolution, FPS, GOP
        ttk.Label(vid_frame, text="Resolution:", font=('Arial', 9)).grid(row=0, column=0, sticky='w', pady=1)
        self.resolution_combo = ttk.Combobox(vid_frame, textvariable=self.video_resolution, 
                    values=["3840x2160", "2560x1440", "1920x1080", "1280x720", "1024x576", "854x480", "768x432", "640x360"], 
                    width=10, font=('Arial', 9))
        self.resolution_combo.grid(row=0, column=1, padx=2, pady=1)
        
        ttk.Label(vid_frame, text="FPS:", font=('Arial', 9)).grid(row=0, column=2, sticky='w', pady=1, padx=(8,0))
        self.fps_combo = ttk.Combobox(vid_frame, textvariable=self.video_fps,
                    values=["24", "25", "30", "50", "60"], width=6, font=('Arial', 9))
        self.fps_combo.grid(row=0, column=3, padx=2, pady=1)
        
        ttk.Label(vid_frame, text="GOP:", font=('Arial', 9)).grid(row=0, column=4, sticky='w', pady=1, padx=(8,0))
        self.gop_entry = ttk.Entry(vid_frame, textvariable=self.video_gop, width=6, font=('Arial', 9))
        self.gop_entry.grid(row=0, column=5, padx=2, pady=1)
        
        # Custom FFmpeg codec arguments
        #ttk.Label(vid_frame, text="custom", font=('Arial', 9)).grid(row=0, column=6, sticky='w', pady=1, padx=(8,0))
        #ttk.Label(vid_frame, text="options:", font=('Arial', 9)).grid(row=1, column=6, sticky='w', pady=1, padx=(8,0))
        self.gop_entry = ttk.Entry(vid_frame, textvariable=self.custom_options, width=10, font=('Arial', 9))
        self.gop_entry.grid(row=2, column=6, padx=2, pady=1)
        
        # Вторая строка - Codec, Preset, Tune
        ttk.Label(vid_frame, text="Codec:", font=('Arial', 9)).grid(row=1, column=0, sticky='w', pady=1)
        self.codec_combo = ttk.Combobox(vid_frame, textvariable=self.video_codec,
                    values=["libx265", "hevc_nvenc", "h264_nvenc", "h264_amf", "hevc_amf"], 
                    width=12, font=('Arial', 9))
        self.codec_combo.grid(row=1, column=1, padx=2, pady=1)
        self.codec_combo.bind('<<ComboboxSelected>>', self.on_codec_change)
        
        ttk.Label(vid_frame, text="Preset:", font=('Arial', 9)).grid(row=1, column=2, sticky='w', pady=1, padx=(8,0))
        self.video_preset_combo = ttk.Combobox(vid_frame, textvariable=self.video_preset, width=10, font=('Arial', 9))
        self.video_preset_combo.grid(row=1, column=3, padx=2, pady=1)
        
        ttk.Label(vid_frame, text="Tune:", font=('Arial', 9)).grid(row=1, column=4, sticky='w', pady=1, padx=(8,0))
        self.tune_combo = ttk.Combobox(vid_frame, textvariable=self.video_tune, width=12, font=('Arial', 9))
        self.tune_combo.grid(row=1, column=5, padx=2, pady=1)
        
        # Третья строка - Bitrate, Bufsize (автоматически связаны)
        ttk.Label(vid_frame, text="Bitrate:", font=('Arial', 9)).grid(row=2, column=0, sticky='w', pady=1)
        self.video_bitrate_spinbox = ttk.Spinbox(vid_frame, from_=100, to=100000, textvariable=self.video_bitrate, 
                                               width=8, font=('Arial', 9), command=self.on_video_bitrate_change)
        self.video_bitrate_spinbox.grid(row=2, column=1, padx=2, pady=1)
        ttk.Label(vid_frame, text="kbps", font=('Arial', 9)).grid(row=2, column=2, sticky='w', pady=1)
        
        ttk.Label(vid_frame, text="Bufsize:", font=('Arial', 9)).grid(row=2, column=3, sticky='w', pady=1, padx=(8,0))
        self.video_bufsize_spinbox = ttk.Spinbox(vid_frame, from_=50, to=50000, textvariable=self.video_bufsize, 
                                               width=8, font=('Arial', 9), command=self.on_video_bufsize_change)
        self.video_bufsize_spinbox.grid(row=2, column=4, padx=2, pady=1)
        ttk.Label(vid_frame, text="custom_options:", font=('Arial', 9)).grid(row=2, column=5, sticky='w', pady=1)
        
        # Initialize codec-dependent settings
        self.update_codec_settings()
        
        # Audio and Metadata frame
        audio_meta_frame = ttk.Frame(middle_frame)
        audio_meta_frame.pack(fill='x', pady=(0, 6))
        
        # Audio Settings
        audio_frame = ttk.LabelFrame(audio_meta_frame, text="Audio Settings", padding="6")
        audio_frame.pack(side='left', fill='both', expand=True, padx=(0, 3))
        
        ttk.Label(audio_frame, text="Codec:", font=('Arial', 9)).grid(row=0, column=0, sticky='w', pady=1)
        self.audio_codec_combo = ttk.Combobox(audio_frame, textvariable=self.audio_codec,
                    values=self.audio_codecs, width=8, font=('Arial', 9))
        self.audio_codec_combo.grid(row=0, column=1, padx=2, pady=1)
        self.audio_codec_combo.bind('<<ComboboxSelected>>', self.on_audio_codec_change)
        
        ttk.Label(audio_frame, text="Bitrate:", font=('Arial', 9)).grid(row=0, column=2, sticky='w', pady=1, padx=(8,0))
        self.audio_bitrate_combo = ttk.Combobox(audio_frame, textvariable=self.audio_bitrate,
                    values=self.audio_bitrates, width=8, font=('Arial', 9))
        self.audio_bitrate_combo.grid(row=0, column=3, padx=2, pady=1)
        self.audio_bitrate_combo.bind('<<ComboboxSelected>>', self.on_audio_bitrate_change)
        
        ttk.Label(audio_frame, text="Channels:", font=('Arial', 9)).grid(row=1, column=0, sticky='w', pady=1)
        self.audio_channels_combo = ttk.Combobox(audio_frame, textvariable=self.audio_channels,
                    width=8, font=('Arial', 9))
        self.audio_channels_combo.grid(row=1, column=1, padx=2, pady=1)
        
        ttk.Label(audio_frame, text="Sample Rate:", font=('Arial', 9)).grid(row=1, column=2, sticky='w', pady=1, padx=(8,0))
        self.audio_sample_rate_combo = ttk.Combobox(audio_frame, textvariable=self.audio_sample_rate,
                    values=self.audio_sample_rates, width=8, font=('Arial', 9))
        self.audio_sample_rate_combo.grid(row=1, column=3, padx=2, pady=1)
        
        # Initialize audio settings
        self.update_audio_settings()
        
        # Metadata
        meta_frame = ttk.LabelFrame(audio_meta_frame, text="Metadata", padding="6")
        meta_frame.pack(side='right', fill='both', expand=True, padx=(3, 0))
        
        ttk.Label(meta_frame, text="Service Name:", font=('Arial', 9)).grid(row=0, column=0, sticky='w', pady=1)
        ttk.Entry(meta_frame, textvariable=self.service_name, width=20, font=('Arial', 9)).grid(row=0, column=1, padx=2, pady=1, columnspan=3)
        
        ttk.Label(meta_frame, text="Provider:", font=('Arial', 9)).grid(row=1, column=0, sticky='w', pady=1)
        ttk.Entry(meta_frame, textvariable=self.service_provider, width=20, font=('Arial', 9)).grid(row=1, column=1, padx=2, pady=1, columnspan=3)

    def create_overlay_tab(self, parent):
        """Create overlay settings tab"""
        # Overlay Control
        control_frame = ttk.LabelFrame(parent, text="Overlay Control", padding="6")
        control_frame.pack(fill='x', pady=(0, 6))
        
        # Start/Stop overlay buttons
        btn_frame = ttk.Frame(control_frame)
        btn_frame.pack(fill='x', pady=4)
        
        self.overlay_start_btn = ttk.Button(btn_frame, text="▶ Start Overlay", 
                                          command=self.start_overlay, width=15)
        self.overlay_start_btn.pack(side='left', padx=2)
        
        self.overlay_stop_btn = ttk.Button(btn_frame, text="⏹ Stop Overlay", 
                                         command=self.stop_overlay, state='disabled', width=15)
        self.overlay_stop_btn.pack(side='left', padx=8)
        
        ttk.Button(btn_frame, text="Open Overlay", 
                  command=self.open_overlay, width=12).pack(side='left', padx=2)
        
        # Save window size checkbox moved to overlay tab
        save_size_frame = ttk.Frame(control_frame)
        save_size_frame.pack(fill='x', pady=(8, 0))
        
        ttk.Checkbutton(save_size_frame, text="Save window size and position", 
                       variable=self.save_window_size, 
                       command=self.save_config).pack(side='left')
        
        # Overlay Display Options
        options_frame = ttk.LabelFrame(parent, text="Display Options", padding="6")
        options_frame.pack(fill='both', expand=True, pady=(0, 6))
        
        # Create scrollable frame for options
        canvas = tk.Canvas(options_frame, height=200)
        scrollbar = ttk.Scrollbar(options_frame, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        # First column - Encoder stats
        col1 = ttk.Frame(scrollable_frame)
        col1.pack(side='left', fill='both', expand=True, padx=4)
        
        ttk.Label(col1, text="Encoder Statistics:", font=('Arial', 10, 'bold')).pack(anchor='w', pady=(0, 4))
        
        ttk.Checkbutton(col1, text="Stream Time", variable=self.overlay_stream_time, 
                       command=self.save_config).pack(anchor='w', pady=1)
        ttk.Checkbutton(col1, text="TS Bitrate", variable=self.overlay_ts_bitrate, 
                       command=self.save_config).pack(anchor='w', pady=1)
        ttk.Checkbutton(col1, text="Video Bitrate (v:b)", variable=self.overlay_video_bitrate, 
                       command=self.save_config).pack(anchor='w', pady=1)
        ttk.Checkbutton(col1, text="Speed", variable=self.overlay_speed, 
                       command=self.save_config).pack(anchor='w', pady=1)
        ttk.Checkbutton(col1, text="Quality", variable=self.overlay_quality, 
                       command=self.save_config).pack(anchor='w', pady=1)
        ttk.Checkbutton(col1, text="Video Codec (c:v)", variable=self.overlay_video_codec, 
                       command=self.save_config).pack(anchor='w', pady=1)
        ttk.Checkbutton(col1, text="Preset", variable=self.overlay_preset, 
                       command=self.save_config).pack(anchor='w', pady=1)
        ttk.Checkbutton(col1, text="Audio Codec (c:a)", variable=self.overlay_audio_codec, 
                       command=self.save_config).pack(anchor='w', pady=1)
        ttk.Checkbutton(col1, text="Audio Bitrate (b:a)", variable=self.overlay_audio_bitrate, 
                       command=self.save_config).pack(anchor='w', pady=1)
        
        # Second column - System and Buffer stats
        col2 = ttk.Frame(scrollable_frame)
        col2.pack(side='left', fill='both', expand=True, padx=4)
        
        ttk.Label(col2, text="System & Buffer:", font=('Arial', 10, 'bold')).pack(anchor='w', pady=(0, 4))
        
        ttk.Checkbutton(col2, text="CPU Load", variable=self.overlay_cpu_load, 
                       command=self.save_config).pack(anchor='w', pady=1)
        ttk.Checkbutton(col2, text="Buffer Input Bitrate", variable=self.overlay_buffer_input, 
                       command=self.save_config).pack(anchor='w', pady=1)
        ttk.Checkbutton(col2, text="Buffer Output Bitrate", variable=self.overlay_buffer_output, 
                       command=self.save_config).pack(anchor='w', pady=1)
        ttk.Checkbutton(col2, text="Buffer Fill", variable=self.overlay_buffer_fill, 
                       command=self.save_config).pack(anchor='w', pady=1)
        ttk.Checkbutton(col2, text="Modulation Scheme", variable=self.overlay_modulation, 
                       command=self.save_config).pack(anchor='w', pady=1)
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

    def create_logs_tab(self, parent):
        """Create logs tab with 4 panes"""
        log_frame = ttk.LabelFrame(parent, text="Log Output", padding="6")
        log_frame.pack(fill='both', expand=True)
        
        # Create paned window for split view
        top_paned = ttk.PanedWindow(log_frame, orient=tk.HORIZONTAL)
        top_paned.pack(fill='both', expand=True)
        
        # Left pane - FFmpeg log
        ffmpeg_frame = ttk.LabelFrame(top_paned, text="FFmpeg", padding="3")
        top_paned.add(ffmpeg_frame, weight=1)
        
        # FFmpeg log area
        ffmpeg_text_frame = ttk.Frame(ffmpeg_frame)
        ffmpeg_text_frame.pack(fill='both', expand=True)
        
        self.ffmpeg_log_text = tk.Text(ffmpeg_text_frame, wrap=tk.WORD, height=4, font=('Courier', 9))
        ffmpeg_scrollbar = ttk.Scrollbar(ffmpeg_text_frame, orient='vertical', command=self.ffmpeg_log_text.yview)
        self.ffmpeg_log_text.configure(yscrollcommand=ffmpeg_scrollbar.set)
        
        self.ffmpeg_log_text.pack(side='left', fill='both', expand=True)
        ffmpeg_scrollbar.pack(side='right', fill='y')
        
        # Right pane - GNU Radio log
        gnuradio_frame = ttk.LabelFrame(top_paned, text="GNU Radio", padding="3")
        top_paned.add(gnuradio_frame, weight=1)
        
        # GNU Radio log area
        gnuradio_text_frame = ttk.Frame(gnuradio_frame)
        gnuradio_text_frame.pack(fill='both', expand=True)
        
        self.gnuradio_log_text = tk.Text(gnuradio_text_frame, wrap=tk.WORD, height=4, font=('Courier', 9))
        gnuradio_scrollbar = ttk.Scrollbar(gnuradio_text_frame, orient='vertical', command=self.gnuradio_log_text.yview)
        self.gnuradio_log_text.configure(yscrollcommand=gnuradio_scrollbar.set)
        
        self.gnuradio_log_text.pack(side='left', fill='both', expand=True)
        gnuradio_scrollbar.pack(side='right', fill='y')
        
        # Create paned window for bottom split view
        bottom_paned = ttk.PanedWindow(log_frame, orient=tk.HORIZONTAL)
        bottom_paned.pack(fill='both', expand=True)
        
        # Left pane - Buffer log
        buffer_frame = ttk.LabelFrame(bottom_paned, text="Buffer", padding="3")
        bottom_paned.add(buffer_frame, weight=1)
        
        # Buffer log area
        buffer_text_frame = ttk.Frame(buffer_frame)
        buffer_text_frame.pack(fill='both', expand=True)
        
        self.buffer_log_text = tk.Text(buffer_text_frame, wrap=tk.WORD, height=4, font=('Courier', 9))
        buffer_scrollbar = ttk.Scrollbar(buffer_text_frame, orient='vertical', command=self.buffer_log_text.yview)
        self.buffer_log_text.configure(yscrollcommand=buffer_scrollbar.set)
        
        self.buffer_log_text.pack(side='left', fill='both', expand=True)
        buffer_scrollbar.pack(side='right', fill='y')
        
        # Right pane - Overlay log
        overlay_frame = ttk.LabelFrame(bottom_paned, text="Overlay", padding="3")
        bottom_paned.add(overlay_frame, weight=1)
        
        # Overlay log area
        overlay_text_frame = ttk.Frame(overlay_frame)
        overlay_text_frame.pack(fill='both', expand=True)
        
        self.overlay_log_text = tk.Text(overlay_text_frame, wrap=tk.WORD, height=4, font=('Courier', 9))
        overlay_scrollbar = ttk.Scrollbar(overlay_text_frame, orient='vertical', command=self.overlay_log_text.yview)
        self.overlay_log_text.configure(yscrollcommand=overlay_scrollbar.set)
        
        self.overlay_log_text.pack(side='left', fill='both', expand=True)
        overlay_scrollbar.pack(side='right', fill='y')
        
        # Clear all logs button
        clear_frame = ttk.Frame(log_frame)
        clear_frame.pack(fill='x', pady=(5, 0))
        
        ttk.Button(clear_frame, text="Clear All Logs", 
                  command=self.clear_all_logs, width=12).pack(side='left', padx=2)
    
    def clear_all_logs(self):
        """Clear all log windows"""
        self.ffmpeg_log_text.delete(1.0, tk.END)
        self.gnuradio_log_text.delete(1.0, tk.END)
        self.buffer_log_text.delete(1.0, tk.END)
        self.overlay_log_text.delete(1.0, tk.END)
        
    def auto_find_obs(self):
        """Check OBS Studio path from conf.cfg"""
        # Просто возвращаем то, что уже загружено из конфига
        if hasattr(self, 'obs_path') and self.obs_path.get():
            if os.path.exists(self.obs_path.get()):
                return self.obs_path.get()
        
        return ""
        
    def check_obs_status(self):
        """Check if OBS Studio is running and update status"""
        # Проверяем как наш процесс, так и системные процессы
        obs_running = False
        
        # Проверяем наш собственный процесс
        if self.obs_process and self.obs_process.poll() is None:
            obs_running = True
        else:
            # Проверяем системные процессы
            obs_running = self.is_obs_running_system()
        
        if obs_running and not self.obs_running:
            # OBS запущен
            self.obs_running = True
            self.obs_status.set("Running")
            self.obs_status_label.config(foreground='green')
            self.obs_start_btn.config(state='disabled')
            self.obs_stop_btn.config(state='normal')
            if not self.obs_process:
                self.log_message("OBS Studio detected (already running on system)", "buffer")
            
        elif not obs_running and self.obs_running:
            # OBS остановлен
            self.obs_running = False
            self.obs_status.set("Stopped")
            self.obs_status_label.config(foreground='red')
            self.obs_start_btn.config(state='normal')
            self.obs_stop_btn.config(state='disabled')
            self.obs_process = None
            self.log_message("OBS Studio stopped", "buffer")
    
        # Check again after 2 seconds
        self.root.after(2000, self.check_obs_status)     
       
    def start_obs(self):
        """Start OBS Studio"""
        # ⚡ ПРОВЕРКА: Если OBS уже запущен в системе, не пытаемся запустить снова
        if self.obs_running or self.is_obs_running_system():
            self.log_message("OBS Studio is already running", "buffer")
            return
            
        if not self.obs_path.get():
            self.log_message("OBS Studio path not set", "buffer")
            return
        
        if self.obs_running or not self.obs_path.get():
            return
        
        try:
            original_path = self.obs_path.get()
            if not os.path.exists(original_path):
                self.log_message(f"OBS Studio executable not found: {original_path}", "buffer")
                return
            
            obs_path = original_path
            working_dir = None
            
            # Handle .lnk shortcuts
            if obs_path.lower().endswith('.lnk'):
                if HAS_WIN32COM:
                    try:
                        pythoncom.CoInitialize()
                        shell = Dispatch("WScript.Shell")
                        shortcut = shell.CreateShortCut(obs_path)
                        obs_path = shortcut.Targetpath
                        working_dir = shortcut.WorkingDirectory
                        
                        self.log_message(f"Resolved shortcut to: {obs_path}", "buffer")
                        if working_dir:
                            self.log_message(f"Working directory: {working_dir}", "buffer")
                            
                    except Exception as e:
                        self.log_message(f"❌ Error resolving shortcut: {e}", "buffer")
                        return
                else:
                    self.log_message("⚠ win32com module not available, cannot resolve .lnk shortcut", "buffer")
                    return
            
            # Check if resolved path exists
            if not os.path.exists(obs_path):
                self.log_message(f"Resolved OBS Studio executable not found: {obs_path}", "buffer")
                return
            
            # Determine the best working directory
            if not working_dir:
                # For direct .exe path, use the directory containing the executable
                working_dir = os.path.dirname(obs_path)
            
            # Additional check for OBS Studio specific directories
            obs_data_dir = os.path.join(working_dir, "data")
            obs_locale_dir = os.path.join(working_dir, "data", "obs-plugins", "frontend-tools", "locale")
            
            # If the standard data directory doesn't exist, try parent directory (for portable OBS)
            if not os.path.exists(obs_data_dir):
                parent_dir = os.path.dirname(working_dir)
                parent_obs_data_dir = os.path.join(parent_dir, "data")
                if os.path.exists(parent_obs_data_dir):
                    working_dir = parent_dir
                    self.log_message(f"Using parent directory as working directory: {working_dir}", "buffer")
            
            self.log_message(f"Starting OBS Studio: {obs_path}", "buffer")
            self.log_message(f"Working directory: {working_dir}", "buffer")
            
            # Set environment variables for OBS Studio
            env = os.environ.copy()
            env["OBS_STUDIO_PORTABLE"] = "1"  # Force portable mode if needed
            
            # Start process with proper working directory and environment
            self.obs_process = subprocess.Popen(
                [obs_path, "--disable-shutdown-check"],
                cwd=working_dir,
                env=env
            )
                
            self.obs_running = True
            self.obs_status.set("Running")
            self.obs_status_label.config(foreground='green')
            self.obs_start_btn.config(state='disabled')
            self.obs_stop_btn.config(state='normal')
            self.log_message("OBS Studio started successfully", "buffer")
            
        except Exception as e:
            self.log_message(f"Error starting OBS Studio: {e}", "buffer")
    
    def stop_obs(self):
        """Stop OBS Studio"""
        if not self.obs_running:
            return
        
        try:
            # Если это наш процесс - останавливаем его
            if self.obs_process:
                self.obs_process.terminate()
                try:
                    self.obs_process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.obs_process.kill()
                    self.obs_process.wait()
            else:
                # Если OBS запущен как системный процесс - пытаемся найти и завершить
                self.log_message("Attempting to stop system OBS Studio process...", "buffer")
                self.kill_system_obs()
                
        except Exception as e:
            self.log_message(f"Error stopping OBS Studio: {e}", "buffer")
        
        self.obs_running = False
        self.obs_status.set("Stopped")
        self.obs_status_label.config(foreground='red')
        self.obs_start_btn.config(state='normal')
        self.obs_stop_btn.config(state='disabled')
        self.obs_process = None
        self.log_message("OBS Studio stopped", "buffer")
        
    def kill_system_obs(self):
        """Kill OBS Studio system processes"""
        try:
            killed = False
            for process in psutil.process_iter(['pid', 'name']):
                try:
                    process_name = process.info['name'].lower()
                    if process_name in ['obs64.exe', 'obs32.exe', 'obs.exe']:
                        pid = process.info['pid']
                        psutil.Process(pid).terminate()
                        self.log_message(f"Terminated OBS Studio process (PID: {pid})", "buffer")
                        killed = True
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            
            if not killed:
                self.log_message("No OBS Studio processes found to terminate", "buffer")
                
        except Exception as e:
            self.log_message(f"Error killing system OBS: {e}", "buffer")      
    
    def confirm_frequency(self):
        """Confirm frequency change and send to GNU Radio"""
        try:
            frequency_mhz = float(self.frequency_mhz_var.get())
            
            # ПРОВЕРКА: частота не может быть 0 или отрицательной
            if frequency_mhz <= 0:
                self.log_message("❌ Error: Frequency must be greater than 0 MHz", "buffer")
                messagebox.showerror("Frequency Error", "Frequency must be greater than 0 MHz!")
                return
                
            frequency_hz = int(frequency_mhz * 1000000)
            
            # ДОПОЛНИТЕЛЬНАЯ ПРОВЕРКА ДИАПАЗОНА
            if frequency_hz < 70000000 or frequency_hz > 6000000000:
                self.log_message(f"❌ Error: Frequency {frequency_mhz} MHz is outside PlutoSDR range (70-6000 MHz)", "buffer")
                messagebox.showerror("Frequency Error", 
                                   f"Frequency {frequency_mhz} MHz is outside PlutoSDR range!\n"
                                   f"Valid range: 70 MHz - 6000 MHz")
                return
            
            self.frequency.set(str(frequency_hz))
            
            if self.modulator_running:
                self.set_gnuradio_variable("frequency", frequency_hz)
                
            self.save_config()
            self.update_preset_script()
            self.log_message(f"✅ Frequency confirmed: {frequency_mhz} MHz", "buffer")
            
        except ValueError:
            self.log_message("❌ Invalid frequency value", "buffer")
            messagebox.showerror("Frequency Error", "Please enter a valid frequency number!")
    
    def find_video_devices(self):
        """Find available video input devices using FFmpeg"""
        ffmpeg_path = self.find_ffmpeg()
        
        try:
            result = subprocess.run(
                [ffmpeg_path, '-list_devices', 'true', '-f', 'dshow', '-i', 'dummy'],
                capture_output=True, text=True, timeout=10,
                encoding='utf-8', errors='ignore'
            )
            
            # Более надежная проверка вывода
            output_text = result.stderr or ""
            if not output_text.strip():
                self.log_message("No output from FFmpeg when searching for video devices", "buffer")
                return
                
            # Parse output for video devices
            lines = output_text.split('\n')
            video_devices = []
            
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                    
                # Ищем строки с видео устройствами по шаблону: "имя устройства" (video)
                if '"' in line and '(video)' in line:
                    # Используем регулярное выражение для точного извлечения имени устройства
                    import re
                    match = re.search(r'\"(.+?)\"\s+\(video\)', line)
                    if match:
                        device_name = match.group(1).strip()
                        if device_name and device_name not in video_devices:
                            video_devices.append(device_name)
            
            self.available_video_devices = video_devices
            if self.video_device_combo:
                self.video_device_combo['values'] = video_devices
            
            if video_devices:
                self.log_message(f"Found {len(video_devices)} video devices", "buffer")
            else:
                self.log_message("No video devices found", "buffer")
                
        except subprocess.TimeoutExpired:
            self.log_message("Timeout while searching for video devices", "buffer")
        except Exception as e:
            self.log_message(f"Error finding video devices: {str(e)}", "buffer")
    
    def find_audio_devices(self):
        """Find available audio input devices using FFmpeg"""
        ffmpeg_path = self.find_ffmpeg()
        
        try:
            result = subprocess.run(
                [ffmpeg_path, '-list_devices', 'true', '-f', 'dshow', '-i', 'dummy'],
                capture_output=True, text=True, timeout=10,
                encoding='utf-8', errors='ignore'
            )

            # Более надежная проверка вывода
            output_text = result.stderr or ""
            if not output_text.strip():
                self.log_message("No output from FFmpeg when searching for audio devices", "buffer")
                return
                
            # Parse output for audio devices
            lines = output_text.split('\n')
            audio_devices = []
            
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                    
                # Ищем строки с видео устройствами по шаблону: "имя устройства" (audio)
                if '"' in line and '(audio)' in line:
                    # Используем регулярное выражение для точного извлечения имени устройства
                    import re
                    match = re.search(r'\"(.+?)\"\s+\(audio\)', line)
                    if match:
                        device_name = match.group(1).strip()
                        if device_name and device_name not in audio_devices:
                            audio_devices.append(device_name)
            
            self.available_audio_devices = audio_devices
            if self.audio_device_combo:
                self.audio_device_combo['values'] = audio_devices
            
            if audio_devices:
                self.log_message(f"Found {len(audio_devices)} audio devices", "buffer")
            else:
                self.log_message("No audio devices found", "buffer")
                
        except subprocess.TimeoutExpired:
            self.log_message("Timeout while searching for audio devices", "buffer")
        except Exception as e:
            self.log_message(f"Error finding audio devices: {str(e)}", "buffer")
    
    def on_preset_change(self, event=None):
        """Handle modulator preset change"""
        preset = self.modulator_preset.get()
        if preset in self.modulator_presets:
            # Update muxrate based on selected preset
            self.muxrate.set(self.modulator_presets[preset]["muxrate"])
            
            # Update buffer settings based on muxrate
            self.update_buffer_settings()
            
            # Рассчитываем видео настройки на основе пресета
            self.calculate_video_settings_from_preset(preset)
            
            # ОБНОВЛЯЕМ КАЛЬКУЛЯТОР ПАРАМЕТРАМИ ПРЕСЕТА И ПЕРЕСЧИТЫВАЕМ
            if hasattr(self, 'calculator'):
                self.calculator.load_preset_parameters(preset)
                # Автоматически пересчитываем
                self.calculator.calculate()
            
            # Save config when preset changes
            self.save_config()
            
            # If streaming or modulator is running, restart everything
            if self.is_streaming or self.modulator_running:
                self.log_message(f"Changing modulator preset to {preset} - restarting all processes", "buffer")
                self.stop_all_processes()
                # Restart after 2 seconds delay
                self.root.after(2000, self.restart_all_processes)
            
            # Автопроверка UDP потоков при смене пресета
            if self.multiplex_mode.get():
                for ch_num, channel_data in self.multiplex_channels.items():
                    if (channel_data['enabled'].get() and 
                        channel_data['source_type'].get() == "UDP_MPTS"):
                        url = channel_data['udp_url'].get().strip()
                        if url:
                            self.root.after(1000, lambda ch=ch_num, u=url: self.check_udp_stream(ch, u))            
           
    def update_buffer_settings(self):
        """Update buffer settings based on muxrate"""
        try:
            muxrate_kbps = float(self.muxrate.get()) / 1000
            # Calculate target buffer based on muxrate and divider
            target_buffer = int(muxrate_kbps / self.buffer_divider.get())
            self.target_buffer.set(max(10, min(4000, target_buffer)))
            
            # Update max buffer based on video buffer size
            try:
                video_bufsize = int(self.video_bufsize.get())
                self.max_buffer.set(max(100, min(100000, video_bufsize * 5)))
            except:
                pass
                
        except (ValueError, ZeroDivisionError):
            pass
    
    def stop_all_processes(self):
        """Stop all running processes"""
        self.stop_streaming()
        self.stop_modulator()

    def restart_all_processes(self):
        """Restart all processes with new settings"""
        if self.streaming_auto_start.get():
            self.start_streaming()
        if self.modulator_auto_start.get():
            self.root.after(3000, self.start_modulator)

    def start_modulator(self):
        """Start the selected RF modulator"""
        if self.modulator_running:
            return

        # ПРОВЕРКА ЧАСТОТЫ ПЕРЕД ЗАПУСКОМ
        try:
            frequency_hz = int(self.frequency.get())
            if frequency_hz <= 0 or frequency_hz < 70000000:
                self.log_message("❌ Error: Invalid frequency. Please set frequency to 70-6000 MHz", "buffer")
                messagebox.showerror("Frequency Error",
                                   "Invalid frequency detected!\n"
                                   "Please set frequency to 70-6000 MHz before starting modulator.")
                return
        except:
            self.log_message("❌ Error: Invalid frequency format", "buffer")
            messagebox.showerror("Frequency Error", "Invalid frequency format!")
            return
                       
        preset = self.modulator_preset.get()
        if preset not in self.modulator_presets:
            self.log_message(f"Error: Unknown modulator preset {preset}", "buffer")
            return
        
        script_file = self.modulator_presets[preset]["script"]
        
        # ПРОВЕРКА ПУТИ К СКРИПТУ
        if not os.path.exists(script_file):
            self.log_message(f"Error: Modulator script not found: {script_file}", "buffer")
            return

        # ⭐ ИЗМЕНЕНО: Получаем Python путь ТОЛЬКО из conf.cfg
        python_path = self.gnuradio_python_path.get()
        
        # Проверяем, что путь существует
        if not python_path:
            self.log_message("❌ RADIOCONDA_PATH not found in conf.cfg!", "buffer")
            messagebox.showerror("Ошибка", 
                               "Путь к Python GNU Radio не найден в conf.cfg!\n\n"
                               "Убедитесь, что файл conf.cfg существует и содержит строку:\n"
                               "RADIOCONDA_PATH=путь_к_python.exe")
            return
        
        if not os.path.exists(python_path):
            self.log_message(f"❌ Python not found at: {python_path}", "buffer")
            messagebox.showerror("Ошибка", 
                               f"Python не найден по пути:\n{python_path}\n\n"
                               "Проверьте правильность пути в файле conf.cfg")
            return
        
        try:
            # Запускаем скрипт через Python GNU Radio
            cmd = [python_path, script_file]
            
            self.log_message(f"Starting RF modulator: {preset}", "buffer")
            self.log_message(f"Using Python: {python_path}", "buffer")
            frequency_mhz = int(self.frequency.get()) // 1000000
            
            # Логируем начальные значения из GUI
            self.log_message(f"GUI Values: Freq={frequency_mhz} MHz, RF Level={self.rf_gain_percent.get()}%", "buffer")
            self.log_message(f"Will send to GNU Radio: RF={self.convert_rf_gain_to_modulator(self.rf_gain_percent.get())} dB", "buffer")
            
            self.modulator_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True
            )
            
            self.modulator_running = True
            self.modulator_status.set("Running")
            self.on_air_status.set("ON AIR")
            self.update_status_colors()
            
            self.modulator_start_btn.config(state='disabled')
            self.modulator_stop_btn.config(state='normal')
            
            # Start monitoring thread
            threading.Thread(target=self.monitor_modulator, daemon=True).start()
            
            self.log_message(f"RF modulator {preset} started successfully", "buffer")
            
            # Запускаем подключение к XML-RPC через 3 секунды после запуска модулятора
            self.root.after(5000, self.connect_to_gnuradio)
            
        except Exception as e:
            self.log_message(f"Error starting modulator: {e}", "buffer")
            import traceback
            self.log_message(f"Traceback: {traceback.format_exc()}", "buffer")
            self.stop_modulator()

    def stop_modulator(self):
        """Stop the RF modulator gracefully"""
        if not self.modulator_process or not self.modulator_running:
            return
        
        try:
            self.log_message("Stopping RF modulator...", "buffer")
            self.modulator_status.set("Stopping")
            
            # Пробуем XML-RPC остановку
            try:
                import xmlrpc.client
                client = xmlrpc.client.ServerProxy('http://localhost:8001')
                result = client.stop_transmission()  # или client.stop_modulator()
                self.log_message(f"XML-RPC: {result}", "buffer")
            except:
                self.log_message("XML-RPC недоступен, используем альтернативные методы", "buffer")
                            
            # Очистка
            self.modulator_running = False
            self.modulator_process = None
            self.modulator_status.set("Stopped")
            self.on_air_status.set("OFF AIR")
            self.update_status_colors()
            
            self.modulator_start_btn.config(state='normal')
            self.modulator_stop_btn.config(state='disabled')
            
            self.log_message("RF modulator stopped", "buffer")
            
        except Exception as e:
            self.log_message(f"Error in stop_modulator: {e}", "buffer")
            # Гарантированная очистка
            try:
                if self.modulator_process:
                    self.modulator_process.kill()
            except:
                pass
            finally:
                self.modulator_running = False
                self.modulator_process = None
                self.modulator_status.set("Stopped")
                self.on_air_status.set("OFF AIR")
                self.update_status_colors()
                self.modulator_start_btn.config(state='normal')
                self.modulator_stop_btn.config(state='disabled')
        
                 # ⚡ ИЗМЕНЕНИЕ: Отключаем XML-RPC при остановке модулятора
                self.connected = False
                self.root.after(0, lambda: self.connection_status_var.set("❌ Disconnected"))
                self.root.after(0, lambda: self.connection_indicator.config(foreground='red'))                

    def monitor_modulator(self):
        """Monitor modulator process output"""
        while self.modulator_process and self.modulator_process.poll() is None:
            try:
                line = self.modulator_process.stdout.readline()
                if line:
                    line = line.strip()
                    if line:
                        self.log_message(f"MOD: {line}", "gnuradio")
            except Exception as e:
                if "I/O operation on closed file" not in str(e):
                    break
            time.sleep(0.01)

    def update_status_colors(self):
        """Update status label colors based on streaming state"""
        # XML-RPC connection status
        if self.connected:
            self.connection_indicator.config(foreground='green')
        else:
            self.connection_indicator.config(foreground='red')
        
        # OBS Studio status
        if self.obs_running:
            self.obs_status_label.config(foreground='green')
        else:
            self.obs_status_label.config(foreground='red')
        
        # FFmpeg status
        if self.is_streaming:
            self.encoder_status_label.configure(foreground='green')
        else:
            self.encoder_status_label.configure(foreground='red')
        
        # Buffer status  
        if self.buffer_running:
            self.buffer_status_label.configure(foreground='green')
        else:
            self.buffer_status_label.configure(foreground='red')
        
        # Modulator status
        if self.modulator_running:
            self.modulator_status_label.configure(foreground='green')
            self.on_air_label.configure(foreground='green')
        else:
            self.modulator_status_label.configure(foreground='red') 
            self.on_air_label.configure(foreground='red')
        
        # Overlay status
        if self.overlay_enabled.get():
            self.overlay_status_label.configure(foreground='green')
            if self.overlay_start_btn:
                self.overlay_start_btn.config(state='disabled')
            if self.overlay_stop_btn:
                self.overlay_stop_btn.config(state='normal')
        else:
            self.overlay_status_label.configure(foreground='red')
            if self.overlay_start_btn:
                self.overlay_start_btn.config(state='normal')
            if self.overlay_stop_btn:
                self.overlay_stop_btn.config(state='disabled')

    def on_codec_change(self, event=None):
        """Update preset and tune options when codec changes"""
        self.update_codec_settings()
        self.save_config()

    def update_codec_settings(self):
        """Update preset and tune comboboxes based on selected codec"""
        codec = self.video_codec.get()
        
        # Update presets
        if codec in self.codec_presets:
            if self.video_preset_combo:
                self.video_preset_combo['values'] = self.codec_presets[codec]
                if self.video_preset.get() not in self.codec_presets[codec]:
                    self.video_preset.set(self.codec_presets[codec][0])
        
        # Update tunes
        if codec in self.codec_tunes:
            if self.tune_combo:
                self.tune_combo['values'] = self.codec_tunes[codec]
                if self.video_tune.get() not in self.codec_tunes[codec]:
                    self.video_tune.set(self.codec_tunes[codec][0] if self.codec_tunes[codec] else "")

    def on_audio_codec_change(self, event=None):
        """Update audio settings when audio codec changes"""
        self.update_audio_settings()
        self.save_config()

    def update_audio_settings(self):
        """Update audio channels based on selected audio codec"""
        codec = self.audio_codec.get()
        
        # Update channels
        if codec in self.audio_channels_options:
            if self.audio_channels_combo:
                self.audio_channels_combo['values'] = self.audio_channels_options[codec]
                if self.audio_channels.get() not in self.audio_channels_options[codec]:
                    self.audio_channels.set(self.audio_channels_options[codec][0])

    def on_audio_bitrate_change(self, event=None):
        """Recalculate video bitrate when audio bitrate changes"""
        self.get_channel_bitrates()
        self.save_config()
            
    def on_video_bitrate_change(self):
        """Update video bufsize when video bitrate changes (bufsize = bitrate / 2)"""
        try:
            bitrate = int(self.video_bitrate.get())
            bufsize = max(50, bitrate // 2)
            self.video_bufsize.set(str(bufsize))
            # Update buffer settings
            self.update_buffer_settings()
            self.save_config()
        except:
            pass

    def on_video_bufsize_change(self):
        """Update video bitrate when bufsize changes (bitrate = bufsize * 2)"""
        try:
            bufsize = int(self.video_bufsize.get())
            bitrate = bufsize * 2
            self.video_bitrate.set(str(bitrate))
            # Update buffer settings
            self.update_buffer_settings()
            #self.save_config()
        except:
            pass            

    def update_speed_color(self):
        """Update encoder speed color based on value"""
        try:
            speed = float(self.encoder_speed.get())
            if speed >= 1.0:
                self.speed_label.configure(foreground='green')
            elif speed >= 0.990:
                self.speed_label.configure(foreground='orange')
            else:
                self.speed_label.configure(foreground='red')
        except:
            self.speed_label.configure(foreground='black')

    def update_buffer_colors(self):
        """Update buffer statistics colors with focus on ZMQ output"""
        try:
            # ЦВЕТ ДЛЯ ZMQ ВЫХОДА НА ОСНОВЕ ОТКЛОНЕНИЯ ОТ ЦЕЛИ
            zmq_output_text = self.buffer_output_bitrate.get()
            target_text = self.buffer_target.get()
            
            if zmq_output_text and target_text:
                zmq_output = float(zmq_output_text)
                target = float(target_text)
                deviation_pct = abs(zmq_output - target) / target * 100
                
                if deviation_pct <= 1.0:
                    self.zmq_output_label.configure(foreground='green')
                    self.bitrate_deviation.set(f"{deviation_pct:.1f}%")
                elif deviation_pct <= 3.0:
                    self.zmq_output_label.configure(foreground='orange') 
                    self.bitrate_deviation.set(f"{deviation_pct:.1f}%")
                else:
                    self.zmq_output_label.configure(foreground='red')
                    self.bitrate_deviation.set(f"{deviation_pct:.1f}%")
                    
            # ЦВЕТ ДЛЯ UDP ВХОДА
            input_text = self.buffer_input_bitrate.get()
            if input_text and target_text:
                input_rate = float(input_text)
                target = float(target_text)
                input_deviation = abs(input_rate - target) / target * 100
                
                if input_deviation <= 10:
                    self.input_bitrate_label.configure(foreground='black')
                elif input_deviation <= 20:
                    self.input_bitrate_label.configure(foreground='orange')
                else:
                    self.input_bitrate_label.configure(foreground='red')
                    
            # ЦВЕТ ДЛЯ ЗАПОЛНЕНИЯ БУФЕРА
            buffer_fill_text = self.buffer_fill.get()
            if '/' in buffer_fill_text:
                current, max_buffer = buffer_fill_text.split('/')
                current = int(current.strip())
                max_buffer = int(max_buffer.strip())
                fill_percentage = (current / max_buffer) * 100
                
                if fill_percentage >= 80:
                    self.buffer_fill_label.configure(foreground='red')
                elif fill_percentage >= 60:
                    self.buffer_fill_label.configure(foreground='orange')
                else:
                    self.buffer_fill_label.configure(foreground='black')
                    
        except (ValueError, ZeroDivisionError):
            # Reset colors if values are invalid
            self.buffer_fill_label.configure(foreground='black')
            self.input_bitrate_label.configure(foreground='black')
            self.zmq_output_label.configure(foreground='black')
            self.bitrate_deviation.set("0.0%")

    def log_message(self, message, log_type="buffer"):
        """Add message to appropriate log"""
        timestamp = time.strftime("%H:%M:%S")
        log_msg = f"[{timestamp}] {message}\n"
        print(log_msg, end='')
        
        # Защита от вызова до инициализации GUI элементов
        if not hasattr(self, 'buffer_log_text'):
            return
            
        if log_type == "ffmpeg":
            self.ffmpeg_log_text.insert(tk.END, log_msg)
            self.ffmpeg_log_text.see(tk.END)
        elif log_type == "gnuradio":
            self.gnuradio_log_text.insert(tk.END, log_msg)
            self.gnuradio_log_text.see(tk.END)
        elif log_type == "overlay":
            self.overlay_log_text.insert(tk.END, log_msg)
            self.overlay_log_text.see(tk.END)
        else:
            self.buffer_log_text.insert(tk.END, log_msg)
            self.buffer_log_text.see(tk.END)

    def load_system_paths_from_config(self):
        """Загружает пути к системным программам из conf.cfg (созданного setup.bat)"""
        try:
            if os.path.exists(self.system_config_file):
                with open(self.system_config_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith('#'):
                            continue
                        
                        # Разбираем строку вида "KEY=value"
                        if '=' in line:
                            key, value = line.split('=', 1)
                            key = key.strip()
                            value = value.strip()
                            
                            # Сохраняем в соответствующие переменные
                            if key == 'RADIOCONDA_PATH':
                                self.gnuradio_python_path.set(value)
                                print(f"📂 Loaded GNU Radio path: {value}")
                            
                            elif key == 'FFMPEG_PATH':
                                self.ffmpeg_path_from_config = value
                                print(f"📂 Loaded FFmpeg path: {value}")
                            
                            elif key == 'OBS_STUDIO_PATH':
                                self.obs_path.set(value)
                                print(f"📂 Loaded OBS path: {value}")
                            
                            elif key == 'DVB_RATE_PATH':
                                self.dvbt2rate_path = value
                                print(f"📂 Loaded dvbt2rate path: {value}")
                            
                            elif key == 'CONDA_BASE':
                                self.conda_base_path = value
                                print(f"📂 Loaded Conda base: {value}")
                
                self.log_message(f"✅ System paths loaded from {self.system_config_file}", "buffer")
                
                # Проверяем, загрузился ли путь
                if not self.gnuradio_python_path.get():
                    self.log_message("⚠️ RADIOCONDA_PATH not found in conf.cfg", "buffer")
                    
            else:
                self.log_message(f"⚠️ System config file not found: {self.system_config_file}", "buffer")
                self.log_message(f"⚠️ Please run setup.bat first", "buffer")
                
                # Значения по умолчанию
                self.gnuradio_python_path.set("")
                self.obs_path.set("")
                self.ffmpeg_path_from_config = "ffmpeg.exe"
                self.dvbt2rate_path = "dvbt2rate.exe"
                
        except Exception as e:
            print(f"❌ Error loading system config: {e}")
            self.log_message(f"❌ Failed to load system paths", "buffer")

    def load_config(self):
        """Load configuration from file"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r') as f:
                    config = json.load(f)
                
                print(f"📂 Loading config with {len(config)} parameters")
                
                # ⭐ ЗАГРУЖАЕМ GNU Radio Python path
                if 'gnuradio_python_path' in config:
                    self.gnuradio_python_path.set(config['gnuradio_python_path'])
                    print(f"📂 Loaded gnuradio_python_path: {config['gnuradio_python_path']}")
                
                # Load playlist settings MPCPLAYLIST
                if 'playlist_auto_start' in config:
                    self.playlist_manager.playlist_auto_start.set(config['playlist_auto_start'])
                if 'mpc_player_path' in config:
                    self.playlist_manager.mpc_player_path.set(config['mpc_player_path'])
                if 'playlist_name' in config:
                    self.playlist_manager.playlist_name.set(config['playlist_name'])
                if 'playlist_randomize' in config:
                    self.playlist_manager.playlist_randomize.set(config['playlist_randomize'])
                
                # Load media folders MPCPLAYLIST
                if 'media_folders' in config:
                    self.playlist_manager.media_folders = config['media_folders']
                    # Отложить обновление списка до создания GUI
                    if hasattr(self.playlist_manager, 'media_listbox'):
                        self.playlist_manager.update_media_listbox()
                
                # Load bumper files
                if 'bumper_files' in config:
                    # Отложить создание bumper виджетов до создания GUI
                    if hasattr(self.playlist_manager, 'bumper_widgets'):
                        # Clear existing bumper widgets
                        for row_frame, _ in self.playlist_manager.bumper_widgets[1:]:
                            row_frame.destroy()
                        self.playlist_manager.bumper_widgets = self.playlist_manager.bumper_widgets[:1]
                        
                        # Load bumper files
                        for i, bumper_path in enumerate(config['bumper_files']):
                            if i >= len(self.playlist_manager.bumper_widgets):
                                self.playlist_manager.add_bumper_row()
                            if i < len(self.playlist_manager.bumper_widgets):
                                _, file_var = self.playlist_manager.bumper_widgets[i]
                                file_var.set(bumper_path)
                        
                        self.playlist_manager.update_bumper_numbers()
                                        
                # Load auto-start setting
                if 'auto_start' in config:
                    self.auto_start.set(config['auto_start'])
                
                # Load save window size setting
                if 'save_window_size' in config:
                    self.save_window_size.set(config['save_window_size'])
                
                # Load window geometry if save is enabled
                if self.save_window_size.get() and 'window_geometry' in config:
                    self.root.geometry(config['window_geometry'])
                else:
                    self.root.geometry(self.default_geometry)
                    
                # Streaming autostart settings
                if 'streaming_auto_start' in config:
                    self.streaming_auto_start.set(config['streaming_auto_start'])
                
                # Load OBS settings
                if 'obs_path' in config:
                    self.obs_path.set(config['obs_path'])
                if 'obs_auto_start' in config:
                    self.obs_auto_start.set(config['obs_auto_start'])
                
                # Video settings
                if 'video_codec' in config:
                    self.video_codec.set(config['video_codec'])
                if 'video_preset' in config:
                    self.video_preset.set(config['video_preset'])
                if 'video_tune' in config:
                    self.video_tune.set(config['video_tune'])
                if 'video_bitrate' in config:
                    self.video_bitrate.set(config['video_bitrate'])
                if 'video_bufsize' in config:
                    self.video_bufsize.set(config['video_bufsize'])
                if 'video_resolution' in config:
                    self.video_resolution.set(config['video_resolution'])
                if 'video_fps' in config:
                    self.video_fps.set(config['video_fps'])
                if 'video_gop' in config:
                    self.video_gop.set(config['video_gop'])           
                
                # Audio settings
                if 'audio_codec' in config:
                    self.audio_codec.set(config['audio_codec'])
                if 'audio_bitrate' in config:
                    self.audio_bitrate.set(config['audio_bitrate'])
                if 'audio_sample_rate' in config:
                    self.audio_sample_rate.set(config['audio_sample_rate'])
                if 'audio_channels' in config:
                    self.audio_channels.set(config['audio_channels'])
                
                # Load input devices
                if 'video_input_device' in config:
                    self.video_input_device.set(config['video_input_device'])
                if 'audio_input_device' in config:
                    self.audio_input_device.set(config['audio_input_device'])
                
                # ⭐ ВАЖНО: Перезаписываем значения переменных ⭐
                # Load network settings - ПРЯМОЕ ПРИСВАИВАНИЕ
                if 'localhost_ip' in config:
                    self.localhost_ip.set(config['localhost_ip'])  # set(), не value=
                if 'output_ip' in config:
                    self.output_ip.set(config['output_ip'])
                if 'udp_input_port' in config:
                    self.udp_input_port.set(config['udp_input_port'])
                if 'udp_output_port' in config:
                    self.udp_output_port.set(config['udp_output_port'])
                if 'muxrate' in config:
                    self.muxrate.set(config['muxrate'])
                
                # Load buffer settings
                if 'target_buffer' in config:
                    self.target_buffer.set(config['target_buffer'])
                if 'min_buffer' in config:
                    self.min_buffer.set(config['min_buffer'])
                if 'max_buffer' in config:
                    self.max_buffer.set(config['max_buffer'])
                if 'calibration_packets' in config:
                    self.calibration_packets.set(config['calibration_packets'])
                if 'calibration_time' in config:
                    self.calibration_time.set(config['calibration_time'])
                if 'buffer_divider' in config:
                    self.buffer_divider.set(config['buffer_divider'])
                
                # Load metadata
                if 'service_name' in config:
                    self.service_name.set(config['service_name'])
                if 'service_provider' in config:
                    self.service_provider.set(config['service_provider'])
                
                # Load overlay settings
                if 'overlay_auto_start' in config:
                    self.overlay_auto_start.set(config['overlay_auto_start'])
                if 'overlay_stream_time' in config:
                    self.overlay_stream_time.set(config['overlay_stream_time'])
                if 'overlay_ts_bitrate' in config:
                    self.overlay_ts_bitrate.set(config['overlay_ts_bitrate'])
                if 'overlay_video_bitrate' in config:
                    self.overlay_video_bitrate.set(config['overlay_video_bitrate'])
                if 'overlay_speed' in config:
                    self.overlay_speed.set(config['overlay_speed'])
                if 'overlay_quality' in config:
                    self.overlay_quality.set(config['overlay_quality'])
                if 'overlay_cpu_load' in config:
                    self.overlay_cpu_load.set(config['overlay_cpu_load'])
                if 'overlay_video_codec' in config:
                    self.overlay_video_codec.set(config['overlay_video_codec'])
                if 'overlay_preset' in config:
                    self.overlay_preset.set(config['overlay_preset'])
                if 'overlay_audio_codec' in config:
                    self.overlay_audio_codec.set(config['overlay_audio_codec'])
                if 'overlay_audio_bitrate' in config:
                    self.overlay_audio_bitrate.set(config['overlay_audio_bitrate'])
                if 'overlay_buffer_input' in config:
                    self.overlay_buffer_input.set(config['overlay_buffer_input'])
                if 'overlay_buffer_output' in config:
                    self.overlay_buffer_output.set(config['overlay_buffer_output'])
                if 'overlay_buffer_fill' in config:
                    self.overlay_buffer_fill.set(config['overlay_buffer_fill'])
                if 'overlay_modulation' in config:
                    self.overlay_modulation.set(config['overlay_modulation'])
                
                # Load RF modulator settings
                if 'modulator_preset' in config:
                    self.modulator_preset.set(config['modulator_preset'])
                if 'modulator_auto_start' in config:
                    self.modulator_auto_start.set(config['modulator_auto_start'])                
                if 'pluto_ip' in config:
                    self.pluto_ip.set(config['pluto_ip'])
                if 'frequency' in config:
                    self.frequency.set(config['frequency'])
                    # Обновляем MHz представление
                    try:
                        frequency_mhz = str(int(config['frequency']) // 1000000)
                        self.frequency_mhz_var.set(frequency_mhz)
                    except:
                        pass
                # ⭐ ИСПРАВЛЕНИЕ ДЛЯ rf_gain ⭐
                if 'rf_gain_percent' in config:
                    # Новый формат: сохраняем GUI проценты
                    self.rf_gain_percent.set(config['rf_gain_percent'])
                    
                    # Конвертируем в модуляторное значение
                    modulator_gain = self.convert_rf_gain_to_modulator(self.rf_gain_percent.get())
                    self.rf_gain.set(modulator_gain)
                    
                elif 'rf_gain' in config:  # Совместимость со старыми конфигами
                    # Старый формат: модуляторное значение
                    self.rf_gain.set(config['rf_gain'])
                    
                    # Конвертируем в GUI проценты
                    rf_percent = self.convert_rf_gain_to_gui(self.rf_gain.get())
                    self.rf_gain_percent.set(rf_percent)
                else:
                    # Значение по умолчанию
                    self.rf_gain_percent.set(50)
                    modulator_gain = self.convert_rf_gain_to_modulator(50)
                    self.rf_gain.set(modulator_gain)
                    
                # Load device settings
                if 'selected_device' in config:
                    self.selected_device.set(config['selected_device'])
                if 'device_arguments' in config:
                    self.device_arguments.set(config['device_arguments'])
                if 'device_mode' in config:
                    self.device_mode.set(config['device_mode'])    
                    
                # Update codec-dependent settings after loading
                if self.video_preset_combo:
                    self.update_codec_settings()
                if self.audio_channels_combo:
                    self.update_audio_settings()
                # Update buffer settings
                self.update_buffer_settings()
                # Recalculate video bitrate based on loaded muxrate
                self.get_channel_bitrates()
            
                # КРИТИЧЕСКОЕ ИЗМЕНЕНИЕ: Сохраняем конфиг мультиплекса отдельно
                # Load multiplex mode
                if 'multiplex_mode' in config:
                    self.multiplex_mode.set(config['multiplex_mode'])
                
                # Load multiplex channels
                if 'multiplex_channels' in config:
                    self.multiplex_config_from_file = config['multiplex_channels']
                    print(f"  ✅ Loaded multiplex config with {len(self.multiplex_config_from_file)} channels")
                if 'emergency_file_path' in config:
                    self.emergency_file_path.set(config.get('emergency_file_path', ''))    
                    # Загрузка каналов будет выполнена после создания GUI
                    # в load_multiplex_channels()
            
            # После загрузки конфига, если есть выбранный пресет - пересчитываем настройки
            if hasattr(self, 'modulator_preset') and self.modulator_preset.get():
                self.calculate_video_settings_from_preset(self.modulator_preset.get())                
                
                # Update presets from directory - ДОБАВЛЕНО
                self.update_modulator_presets()
                    
        except Exception as e:
            print(f"Error loading config: {e}")
            
            # Все равно обновляем пресеты
            self.update_modulator_presets()
            self.multiplex_config_from_file = {}
            import traceback
            traceback.print_exc()
            
    def save_config(self):
        """Save configuration to file"""
        try:
            # Создаем базовый config с проверками
            config = {
                # GNU Radio Python path
                'gnuradio_python_path': self.gnuradio_python_path.get() if hasattr(self, 'gnuradio_python_path') else "",
                
                # Playlist settings - С ПРОВЕРКАМИ
                'playlist_auto_start': self.playlist_manager.playlist_auto_start.get() if hasattr(self, 'playlist_manager') else False,
                'mpc_player_path': self.playlist_manager.mpc_player_path.get() if hasattr(self, 'playlist_manager') else "mpc-hc64.exe",
                'playlist_name': self.playlist_manager.playlist_name.get() if hasattr(self, 'playlist_manager') else "my_playlist.mpcpl",
                'playlist_randomize': self.playlist_manager.playlist_randomize.get() if hasattr(self, 'playlist_manager') else True,
                'media_folders': self.playlist_manager.media_folders if hasattr(self, 'playlist_manager') else [],
                'bumper_files': [file_var.get() for _, file_var in getattr(self.playlist_manager, 'bumper_widgets', [])] if hasattr(self, 'playlist_manager') else [],
                             
                # OBS settings
                'obs_path': self.obs_path.get(),
                'obs_auto_start': self.obs_auto_start.get(),
                
                # Video settings
                'video_codec': self.video_codec.get(),
                'video_preset': self.video_preset.get(),
                'video_tune': self.video_tune.get(),
                'video_bitrate': self.video_bitrate.get(),
                'video_bufsize': self.video_bufsize.get(),
                'video_resolution': self.video_resolution.get(),
                'video_fps': self.video_fps.get(),
                'video_gop': self.video_gop.get(),
                
                # Audio settings
                'audio_codec': self.audio_codec.get(),
                'audio_bitrate': self.audio_bitrate.get(),
                'audio_sample_rate': self.audio_sample_rate.get(),
                'audio_channels': self.audio_channels.get(),
                
                # Input devices
                'video_input_device': self.video_input_device.get(),
                'audio_input_device': self.audio_input_device.get(),
                
                # Network settings
                'muxrate': self.muxrate.get(),
                'localhost_ip': self.localhost_ip.get(),
                'output_ip': self.output_ip.get(),
                'udp_input_port': self.udp_input_port.get(),
                'udp_output_port': self.udp_output_port.get(),
                
                # Buffer settings
                'target_buffer': self.target_buffer.get(),
                'min_buffer': self.min_buffer.get(),
                'max_buffer': self.max_buffer.get(),
                'calibration_packets': self.calibration_packets.get(),
                'calibration_time': self.calibration_time.get(),
                'buffer_divider': self.buffer_divider.get(),
                
                # Metadata
                'service_name': self.service_name.get(),
                'service_provider': self.service_provider.get(),
                
                # Overlay settings
                'overlay_auto_start': self.overlay_auto_start.get(), 
                'overlay_stream_time': self.overlay_stream_time.get(),
                'overlay_ts_bitrate': self.overlay_ts_bitrate.get(),
                'overlay_video_bitrate': self.overlay_video_bitrate.get(),
                'overlay_speed': self.overlay_speed.get(),
                'overlay_quality': self.overlay_quality.get(),
                'overlay_cpu_load': self.overlay_cpu_load.get(),
                'overlay_video_codec': self.overlay_video_codec.get(),
                'overlay_preset': self.overlay_preset.get(),
                'overlay_audio_codec': self.overlay_audio_codec.get(),
                'overlay_audio_bitrate': self.overlay_audio_bitrate.get(),
                'overlay_buffer_input': self.overlay_buffer_input.get(),
                'overlay_buffer_output': self.overlay_buffer_output.get(),
                'overlay_buffer_fill': self.overlay_buffer_fill.get(),
                'overlay_modulation': self.overlay_modulation.get(),
                
                # Autostart settings
                'auto_start': self.auto_start.get(),
                'save_window_size': self.save_window_size.get(),
                'streaming_auto_start': self.streaming_auto_start.get(),
                            
                # RF modulator settings
                'modulator_preset': self.modulator_preset.get(),
                'modulator_auto_start': self.modulator_auto_start.get(),
                'pluto_ip': self.pluto_ip.get(),
                'frequency': self.frequency.get(),
                'rf_gain_percent': self.rf_gain_percent.get(),
                
                # Device settings
                'selected_device': self.selected_device.get(),
                'device_arguments': self.device_arguments.get(),
                'device_mode': self.device_mode.get(),
                              
            }
            # Add multiplex channels - ВАЖНО: сохраняем в порядке номеров каналов
            multiplex_config = OrderedDict()
            # Сортируем по номеру канала
            sorted_channels = sorted(self.multiplex_channels.items(), key=lambda x: x[0])
            
            for ch_num, channel_data in sorted_channels:
                # В save_config:
                # В цикле сохранения multiplex_channels
                multiplex_config[str(ch_num)] = {
                    'enabled': channel_data['enabled'].get(),
                    'name': channel_data['name'].get(),
                    'source_type': channel_data['source_type'].get(),
                    'video_device': channel_data['video_device'].get(),
                    'audio_device': channel_data['audio_device'].get(),
                    'window_title': channel_data['window_title'].get(),  # НОВОЕ
                    'media_path': channel_data['media_path'].get(),
                    'randomize': channel_data['randomize'].get(),
                    'udp_url': channel_data['udp_url'].get(),
                    'url_input': channel_data['url_input'].get(),
                    'selected_program': channel_data['selected_program'].get(),
                    'video_pid': channel_data.get('saved_video_pid', ''),
                    'audio_pid': channel_data.get('saved_audio_pid', ''),
                    'is_radio': channel_data['is_radio'].get(),
                    'radio_bg_type': channel_data['radio_bg_type'].get(),
                    'radio_bg_color': channel_data['radio_bg_color'].get(),
                    'radio_bg_picture': channel_data['radio_bg_picture'].get(),
                    'radio_text': channel_data['radio_text'].get(),
                    'radio_show_time': channel_data['radio_show_time'].get(),
                    'radio_text_color': channel_data['radio_text_color'].get(),
                    'radio_text_size': channel_data['radio_text_size'].get(),
                    'radio_time_color': channel_data['radio_time_color'].get(),
                    'radio_time_size': channel_data['radio_time_size'].get(),
                    'show_metadata': channel_data['show_metadata'].get(),
                    'metadata_size': channel_data['metadata_size'].get(),
                    'metadata_color': channel_data['metadata_color'].get(),
                    'metadata_position': channel_data['metadata_position'].get(),                    
                    
                    'position': ch_num
                }
            config['emergency_file_path'] = self.emergency_file_path.get()
            config['multiplex_channels'] = multiplex_config
            config['multiplex_mode'] = self.multiplex_mode.get()         
            # Save window geometry if save is enabled
            if self.save_window_size.get():
                config['window_geometry'] = self.root.geometry()  # ← ДОБАВЬТЕ ЭТУ СТРОКУ
            else:
                # Если сохранение отключено, удаляем геометрию из конфига
                config.pop('window_geometry', None)            
            with open(self.config_file, 'w') as f:
                json.dump(config, f, indent=4)
                
            # print#(f"✅ Config saved successfully with {len(config)} parameters")
                                 
        except Exception as e:
            print(f"❌ Error saving config: {e}")
            import traceback
            traceback.print_exc()
                                
    def renumber_channels(self):
        """Renumber channels after removal"""
        if not hasattr(self, 'multiplex_channels') or not self.multiplex_channels:
            return
        
        channels = list(self.multiplex_channels.items())
        self.multiplex_channels.clear()
        
        for i, (old_num, data) in enumerate(sorted(channels, key=lambda x: x[0]), 1):
            data['frame'].config(text=f"CH{i}")
            self.multiplex_channels[i] = data 
            
    def remove_channel(self, channel_num):
        """Remove a channel"""
        if not hasattr(self, 'multiplex_channels'):
            return
        
        if channel_num == 1:
            messagebox.showwarning("Cannot Remove", "CH1 cannot be removed")
            return
        
        if channel_num in self.multiplex_channels:
            channel_data = self.multiplex_channels[channel_num]
            channel_data['frame'].destroy()
            del self.multiplex_channels[channel_num]
            
            # Renumber remaining channels
            self.renumber_channels()
            self.update_add_button_state()
            self.save_config()
            
            # Обновляем UI статистики
            if self.multiplex_mode.get() and hasattr(self, 'channels_stats_container'):
                self.root.after(100, self.init_channels_stats_ui)
            
    def update_add_button_state(self):
        """Enable/disable add button based on channel count"""
        # Убедимся что multiplex_channels существует
        if not hasattr(self, 'multiplex_channels') or not hasattr(self, 'add_ch_btn'):
            return
        
        if not self.multiplex_channels:
            channel_count = 0
        else:
            channel_count = len(self.multiplex_channels)
        
        if channel_count >= self.max_channels:
            if self.add_ch_btn:
                self.add_ch_btn.config(state='disabled')
        else:
            if self.add_ch_btn:
                self.add_ch_btn.config(state='normal')            
            
    def setup_multiplex_autosave(self):
        """Setup auto-save for multiplex settings"""
        # Для каждого существующего канала добавляем отслеживание изменений
        if hasattr(self, 'multiplex_channels'):
            for ch_num, channel_data in self.multiplex_channels.items():
                # Отслеживаем изменения переменных
                channel_data['enabled'].trace_add('write', lambda *args: self.debounced_save())
                channel_data['name'].trace_add('write', lambda *args: self.debounced_save())
                channel_data['source_type'].trace_add('write', lambda *args: self.debounced_save())
                channel_data['video_device'].trace_add('write', lambda *args: self.debounced_save())
                channel_data['audio_device'].trace_add('write', lambda *args: self.debounced_save())
                channel_data['window_title'].set(str(ch_config.get('window_title', '')))
                channel_data['media_path'].trace_add('write', lambda *args: self.debounced_save())
                channel_data['randomize'].trace_add('write', lambda *args: self.debounced_save())
                channel_data['url_input'].trace_add('write', lambda *args: self.debounced_save())
                channel_data['udp_url'].trace_add('write', lambda *args: self.debounced_save())
                channel_data['selected_program'].trace_add('write', lambda *args: self.debounced_save())
                channel_data['is_radio'].trace_add('write', lambda *args: self.debounced_save())
                channel_data['radio_bg_type'].trace_add('write', lambda *args: self.debounced_save())
                channel_data['radio_bg_color'].trace_add('write', lambda *args: self.debounced_save())
                channel_data['radio_bg_picture'].trace_add('write', lambda *args: self.debounced_save())
                channel_data['radio_text'].trace_add('write', lambda *args: self.debounced_save())
                channel_data['radio_show_time'].trace_add('write', lambda *args: self.debounced_save())
                channel_data['radio_text_color'].trace_add('write', lambda *args: self.debounced_save())
                channel_data['radio_text_size'].trace_add('write', lambda *args: self.debounced_save())
                channel_data['radio_time_color'].trace_add('write', lambda *args: self.debounced_save())
                channel_data['radio_time_size'].trace_add('write', lambda *args: self.debounced_save())
                channel_data['show_metadata'].trace_add('write', lambda *args: self.debounced_save())
                channel_data['metadata_size'].trace_add('write', lambda *args: self.debounced_save())
                channel_data['metadata_color'].trace_add('write', lambda *args: self.debounced_save())
                channel_data['metadata_position'].trace_add('write', lambda *args: self.debounced_save())                
        
        self.log_message("Multiplex auto-save setup complete", "buffer")            
        
    def start_overlay(self):
        """Start the overlay web server"""
        if self.overlay_enabled.get():
            self.log_message("Overlay already running", "overlay")
            return
            
        try:
            # Проверяем, не занят ли порт
            try:
                test_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                test_socket.bind(("localhost", 8000))
                test_socket.close()
            except OSError:
                self.log_message("❌ Port 8000 is already in use", "overlay")
                messagebox.showerror("Port Error", "Port 8000 is already in use!\nPlease close other applications using this port.")
                return
            
            # Создаем overlay HTML файл
            self.create_overlay_html()
            
            # Запускаем веб-сервер в отдельном потоке
            self.overlay_enabled.set(True)
            self.overlay_thread = threading.Thread(target=self.run_overlay_server, daemon=True)
            self.overlay_thread.start()
            
            # Обновляем GUI
            if self.overlay_start_btn:
                self.overlay_start_btn.config(state='disabled')
            if self.overlay_stop_btn:
                self.overlay_stop_btn.config(state='normal')
            self.overlay_status.set("Running")
            self.overlay_status_label.config(foreground='green')
            
            self.log_message("✅ Overlay server started successfully", "overlay")
            
        except Exception as e:
            self.log_message(f"❌ Error starting overlay: {e}", "overlay")
            self.overlay_enabled.set(False)
                
    def stop_overlay(self):
        """Stop the overlay web server"""
        self.overlay_enabled.set(False)
        
        if self.overlay_server:
            try:
                self.log_message("Stopping overlay server...", "overlay")
                
                def shutdown_server():
                    try:
                        self.overlay_server.shutdown()
                        self.overlay_server.server_close()
                        self.log_message("Overlay server stopped safely", "overlay")
                    except Exception as e:
                        self.log_message(f"Error during server shutdown: {e}", "overlay")
                
                shutdown_thread = threading.Thread(target=shutdown_server, daemon=True)
                shutdown_thread.start()
                shutdown_thread.join(timeout=3)
                
            except Exception as e:
                self.log_message(f"Error stopping overlay server: {e}", "overlay")
        
        # ОБНОВЛЯЕМ ВСЕ КНОПКИ - ГЛАВНУЮ И НА ВКЛАДКЕ OVERLAY
        if self.overlay_start_btn:
            self.overlay_start_btn.config(state='normal')
        if self.overlay_stop_btn:
            self.overlay_stop_btn.config(state='disabled')     
        self.overlay_status.set("Stopped")
        self.overlay_status_label.config(foreground='red')
        
        self.log_message("Overlay server stopped", "overlay")
    
    def open_overlay(self):
        """Open overlay in web browser"""
        try:
            webbrowser.open("http://localhost:8000/encoder_overlay.html")
        except Exception as e:
            self.log_message(f"Error opening overlay: {e}", "overlay")
    
    def run_overlay_server(self):
        """Run the overlay web server"""
        class OverlayHandler(SimpleHTTPRequestHandler):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, directory=os.getcwd(), **kwargs)
            
            def log_message(self, format, *args):
                pass
        
        try:
            self.overlay_server = socketserver.TCPServer(("", 8000), OverlayHandler)
            self.overlay_server.allow_reuse_address = True
            self.overlay_server.timeout = 1  # Таймаут для периодической проверки
            
            self.log_message("Overlay server started on http://localhost:8000", "overlay")
            
            # Обновление данных оверлея в отдельном потоке
            def update_overlay_data():
                while self.overlay_enabled.get():
                    try:
                        # Обновляем CPU статистику
                        self.update_cpu_stats()
                        # Создаем/обновляем JSON файл с данными
                        overlay_data = self.get_overlay_data()
                        with open("overlay_data.json", "w") as f:
                            json.dump(overlay_data, f)
                        time.sleep(1)  # Обновление каждую секунду
                    except Exception as e:
                        self.log_message(f"Overlay data update error: {e}", "overlay")
                        time.sleep(2)
            
            # Запускаем обновление данных
            data_thread = threading.Thread(target=update_overlay_data, daemon=True)
            data_thread.start()
            
            # Основной цикл сервера
            while self.overlay_enabled.get():
                self.overlay_server.handle_request()
                
        except Exception as e:
            if "Address already in use" in str(e):
                self.log_message("Overlay server already running on port 8000", "overlay")
            else:
                self.log_message(f"Overlay server error: {e}", "overlay")
        finally:
            self.overlay_enabled.set(False)
            try:
                if self.overlay_server:
                    self.overlay_server.server_close()
            except:
                pass
    
    def create_overlay_html(self):
        """Create the overlay HTML file"""
        html_content = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Encoder Overlay</title>
    <style>
        body {
            margin: 0;
            padding: 0;
            background: transparent;
            font-family: 'Courier New', monospace;
            font-size: 14px;
            color: white;
            overflow: hidden;
        }
        #overlay-container {
            background: rgba(0, 0, 0, 0.6);
            padding: 8px 15px;
            border-radius: 5px;
            display: flex;
            align-items: center;
            gap: 20px;
            flex-wrap: wrap;
        }
        .stat-item {
            display: flex;
            align-items: center;
            gap: 5px;
        }
        .stat-label {
            font-weight: bold;
            color: #cccccc;
        }
        .stat-value {
            font-weight: bold;
        }
        .green { color: #00ff00; }
        .yellow { color: #ffff00; }
        .red { color: #ff0000; }
        .orange { color: #ffa500; }
    </style>
</head>
<body>
    <div id="overlay-container">
        <!-- Stats will be populated by JavaScript -->
    </div>
    
    <script>
        function updateOverlay() {
            fetch('/overlay_data.json?t=' + new Date().getTime())
                .then(response => response.json())
                .then(data => {
                    const container = document.getElementById('overlay-container');
                    container.innerHTML = '';
                    
                    // Add each enabled stat to the overlay
                    Object.keys(data.stats).forEach(statKey => {
                        if (data.enabled[statKey]) {
                            const stat = data.stats[statKey];
                            const statElement = document.createElement('div');
                            statElement.className = 'stat-item';
                            
                            statElement.innerHTML = `
                                <span class="stat-label">${stat.label}:</span>
                                <span class="stat-value ${stat.color}">${stat.value}</span>
                            `;
                            
                            container.appendChild(statElement);
                        }
                    });
                })
                .catch(error => console.error('Error fetching overlay data:', error));
        }
        
        // Update every second
        setInterval(updateOverlay, 500);
        
        // Initial update
        updateOverlay();
    </script>
</body>
</html>
        """
        
        with open("encoder_overlay.html", "w") as f:
            f.write(html_content)
    
    def update_cpu_stats(self):
        """Update CPU statistics"""
        try:
            # CPU load
            cpu_percent = psutil.cpu_percent(interval=0.1)
            self.cpu_load.set(f"{int(cpu_percent)}%")
            
        except Exception as e:
            print(f"Error updating CPU stats: {e}")
    
    def get_overlay_data(self):
        """Get current data for overlay"""
        def get_speed_color(speed):
            try:
                speed_val = float(speed)
                if speed_val >= 1.0:
                    return "green"
                elif speed_val >= 0.990:
                    return "yellow"
                else:
                    return "red"
            except:
                return ""
        
        def get_cpu_color(load):
            try:
                load_val = float(load.replace('%', ''))
                
                if load_val <= 25:
                    return "green"
                elif load_val <= 40:
                    return "yellow"
                else:
                    return "red"
            except:
                return ""
        
        def get_buffer_color(value, target=None):
            try:
                if target and '/' in value:
                    current, max_buffer = value.split('/')
                    current = int(current.strip())
                    max_buffer = int(max_buffer.strip())
                    fill_percentage = (current / max_buffer) * 100
                    
                    if fill_percentage >= 80:
                        return "red"
                    elif fill_percentage >= 60:
                        return "yellow"
                    else:
                        return "green"
                else:
                    return ""
            except:
                return ""
        
        def get_bitrate_color(value, target):
            try:
                value_val = float(value)
                target_val = float(target)
                diff_pct = (value_val - target_val) / target_val * 100
                
                if abs(diff_pct) <= 1:
                    return "green"
                elif abs(diff_pct) <= 5:
                    return "yellow"
                else:
                    return "red"
            except:
                return ""
                
        # ДОБАВЬТЕ ПРОВЕРКУ
        preset_display = self.get_preset_display_name(self.modulator_preset.get())
        #self.log_message(f"🔧 Overlay Debug: Preset='{self.modulator_preset.get()}', Display='{preset_display}'", "overlay")
        
        data = {
            "stats": {
                "stream_time": {
                    "label": "Stream Time",
                    "value": self.stream_time.get(),
                    "color": "green"
                },
                "ts_bitrate": {
                    "label": "TS Bitrate",
                    "value": f"{self.encoder_bitrate.get()} kbps",
                    "color": get_bitrate_color(self.encoder_bitrate.get(), self.buffer_target.get())
                },
                "video_bitrate": {
                    "label": "v:b",
                    "value": f"{self.video_bitrate.get()} kbps",
                    "color": "green"
                },
                "speed": {
                    "label": "Speed",
                    "value": f"{self.encoder_speed.get()}x",
                    "color": get_speed_color(self.encoder_speed.get())
                },
                "quality": {
                    "label": "Quality",
                    "value": self.encoder_quality.get(),
                    "color": "green"
                },
                "cpu_load": {
                    "label": "CPU Load",
                    "value": self.cpu_load.get(),
                    "color": get_cpu_color(self.cpu_load.get())
                },
                "video_codec": {
                    "label": "c:v",
                    "value": self.video_codec.get(),
                    "color": "green"
                },
                "preset": {
                    "label": "Preset",
                    "value": self.video_preset.get(),
                    "color": "green"
                },
                "audio_codec": {
                    "label": "c:a",
                    "value": self.audio_codec.get(),
                    "color": "green"
                },
                "audio_bitrate": {
                    "label": "b:a",
                    "value": self.audio_bitrate.get(),
                    "color": "green"
                },
                "buffer_input": {
                    "label": "Buffer In",
                    "value": f"{self.buffer_input_bitrate.get()} kbps",
                    "color": get_bitrate_color(self.buffer_input_bitrate.get(), self.buffer_target.get())
                },
                "buffer_output": {
                    "label": "Buffer Out",
                    "value": f"{self.buffer_output_bitrate.get()} kbps",
                    "color": get_bitrate_color(self.buffer_output_bitrate.get(), self.buffer_target.get())
                },
                "buffer_fill": {
                    "label": "Buffer",
                    "value": self.buffer_fill.get(),
                    "color": get_buffer_color(self.buffer_fill.get())
                },
                "modulation": {
                    "label": "Modulation",
                    "value": self.get_preset_display_name(self.modulator_preset.get()),
                    "color": "green"
                }
            },
            "enabled": {
                "stream_time": self.overlay_stream_time.get(),
                "ts_bitrate": self.overlay_ts_bitrate.get(),
                "video_bitrate": self.overlay_video_bitrate.get(),
                "speed": self.overlay_speed.get(),
                "quality": self.overlay_quality.get(),
                "cpu_load": self.overlay_cpu_load.get(),
                "video_codec": self.overlay_video_codec.get(),
                "preset": self.overlay_preset.get(),
                "audio_codec": self.overlay_audio_codec.get(),
                "audio_bitrate": self.overlay_audio_bitrate.get(),
                "buffer_input": self.overlay_buffer_input.get(),
                "buffer_output": self.overlay_buffer_output.get(),
                "buffer_fill": self.overlay_buffer_fill.get(),
                "modulation": self.overlay_modulation.get(),
                "overlay_modulation": self.overlay_modulation.get()  # ДУБЛИРУЮЩАЯ ПРОВЕРКА
            }
        }
        
        return data
        
    def check_udp_stream(self, channel_num, url):
        """Check UDP stream availability"""
        try:
            ffmpeg_path = self.find_ffmpeg()
            
            # Быстрая проверка (2 секунды)
            cmd = [ffmpeg_path, '-i', url, '-t', '1', '-f', 'null', '-']
            
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding='utf-8',
                errors='ignore'
            )
            
            stdout, stderr = process.communicate(timeout=7)
            
            if 'Input #0' in stderr or 'Stream #' in stderr:
                self.log_message(f"✅ CH{channel_num} UDP stream OK: {url[:50]}...", "buffer")
                return True
            else:
                self.log_message(f"❌ CH{channel_num} UDP stream not responding: {url}", "buffer")
                return False
                
        except Exception as e:
            self.log_message(f"❌ CH{channel_num} UDP stream error: {str(e)[:100]}", "buffer")
            return False

    def check_url_stream(self, channel_num, url):
        """Check URL stream availability"""
        try:
            ffmpeg_path = self.find_ffmpeg()
            
            # Для HTTP/HTTPS добавляем user-agent и timeout
            cmd = [ffmpeg_path, '-user_agent', 'Mozilla/5.0', 
                   '-timeout', '2000000', '-i', url, '-t', '3', '-f', 'null', '-']
            
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding='utf-8',
                errors='ignore'
            )
            
            stdout, stderr = process.communicate(timeout=10)
            
            if any(x in stderr for x in ['Input #0', 'Stream #', 'Program', 'icy-name', 'Duration:']):
                self.log_message(f"✅ CH{channel_num} URL stream OK: {url[:50]}...", "buffer")
                return True
            else:
                self.log_message(f"❌ CH{channel_num} URL stream not responding: {url}", "buffer")
                return False
                
        except Exception as e:
            self.log_message(f"❌ CH{channel_num} URL stream error: {str(e)[:100]}", "buffer")
            return False  

    def monitor_channel_output(self, channel_num, process, channel_data):
        """Monitor channel process output for errors with thread-safe emergency start"""
        critical_errors = [
            'error opening input', 'failed to reload playlist', 'connection failed',
            'unable to open', 'Server returned 404', 'Invalid data found', 'Error during demuxing',
            'keepalive request failed', 'Failed to resolve hostname', 'Unable to open URL', 'http error',
            'Failed to resolve', 'invalid new backstep -1', 'Connection timed out', 'IO error: Error number -10054 occurred',
            'Server disconnected', 'Error in the pull function', 'Error number -10054 occurred', 'end of file', 'Input/output error'
        ]
        
        try:
            for line in iter(process.stdout.readline, ''):
                if line and self.is_streaming:
                    line_stripped = line.strip()
                    
                    # ⭐ НОВОЕ: Парсим статистику (speed и bitrate)
                    if "speed=" in line_stripped:
                        match = re.search(r'speed=\s*([\d.]+)x', line_stripped)
                        if match:
                            speed = float(match.group(1))
                            # Обновляем GUI в главном потоке
                            self.root.after(0, self.update_channel_stats, channel_num, 'speed', speed)
                    
                    if "bitrate=" in line_stripped:
                        match = re.search(r'bitrate=\s*([\d.]+)\s*kbits/s', line_stripped)
                        if match:
                            bitrate = match.group(1)
                            self.root.after(0, self.update_channel_stats, channel_num, 'bitrate', bitrate)
                    
                    # ⭐ Существующий код проверки ошибок (НЕ ТРОГАЕМ!)
                    error_detected = False
                    detected_error = "unknown_error"
                    
                    for error in critical_errors:
                        if error.lower() in line_stripped.lower():
                            error_detected = True
                            detected_error = line_stripped[:100]
                            break
                    
                    if error_detected:
                        self.log_message(f"CH{channel_num} ERROR: {detected_error}", "buffer")
                        
                        # Переводим канал в состояние FAILED
                        self.transition_to_failed(channel_num, "stream_error")
                        
                        return  # Выходим из монитора
                            
        except Exception as e:
            if self.is_streaming:
                self.log_message(f"CH{channel_num} monitor error: {e}", "buffer")
        
        # Проверяем завершение процесса
        if process.poll() is not None and self.is_streaming:
            return_code = process.poll()
            self.log_message(f"CH{channel_num}: Process exited with code {return_code}", "buffer")
            
            # Переводим канал в состояние FAILED
            self.transition_to_failed(channel_num, f"process_exit_{return_code}")
                
    def kill_process_fast(self, process, name=""):
        """Fast process termination (from IPTV app)"""
        if not process:
            return
        
        try:
            pid = process.pid
            
            if sys.platform == "win32":
                os.system(f'taskkill /PID {pid} /T /F')
            else:
                process.terminate()
                
            for _ in range(30):
                if process.poll() is not None:
                    break
                time.sleep(0.1)
                    
            if process.poll() is None:
                process.kill()
                
            process.wait(timeout=1)
            
            if name:
                self.log_message(f"{name} stopped", "buffer")
                
        except Exception as e:
            if name:
                self.log_message(f"Error stopping {name}: {str(e)}", "buffer")        
              
    def restart_original_channel(self, channel_num):
        """Restart original channel"""
        channel_data = self.multiplex_channels.get(channel_num, {})
        if not channel_data.get('enabled', False):
            return False
        
        # ⭐ ДЛЯ GRAB_WINDOW: проверяем и обновляем окно
        if channel_data['source_type'].get() == "grab_window":
            # Получаем актуальный список окон
            windows = self.get_available_windows()
            current_window = channel_data['window_title'].get()
            
            self.log_message(f"CH{channel_num}: Restarting with window: '{current_window[:50]}...'", "buffer")
            
            if current_window and current_window in windows:
                # Окно все еще доступно - отлично
                self.log_message(f"CH{channel_num}: Window still available", "buffer")
                pass
            elif current_window:
                # Ищем похожее
                similar = self.find_similar_window(current_window, windows)
                if similar:
                    channel_data['window_title'].set(similar)
                    self.log_message(f"CH{channel_num}: Found similar window for restart: {similar[:50]}...", "buffer")
                elif windows:
                    # Берем первое доступное
                    channel_data['window_title'].set(windows[0])
                    self.log_message(f"CH{channel_num}: Using first available window for restart: {windows[0][:50]}...", "buffer")
                else:
                    self.log_message(f"CH{channel_num}: No windows available for capture", "buffer")
                    return False
            elif windows:
                channel_data['window_title'].set(windows[0])
                self.log_message(f"CH{channel_num}: No previous window, using first available", "buffer")
        
        self.log_message(f"CH{channel_num}: Restarting original stream...", "buffer")        
        
        # Запускаем оригинальный канал
        output_port = self.base_multicast_port + channel_num - 1
        
        if channel_data['source_type'].get() == "URL_Input" and channel_data['is_radio'].get():
            cmd = self.build_radio_channel_command(channel_num, channel_data, output_port)
            use_stdin = True
        else:
            cmd = self.build_channel_ffmpeg_command(channel_num, channel_data, output_port)
            use_stdin = False
        
        if not cmd:
            return False
        
        # ⭐ ЛОГИРУЕМ ПОЛНУЮ КОМАНДУ
        # self.log_message(f"CH{channel_num} RESTART CMD: {cmd}", "buffer")
        
        # Сохраняем в файл для анализа
        # try:
            # with open(f"restart_ch{channel_num}.bat", "w", encoding='utf-8') as f:
                # f.write(f"@echo off\n")
                # f.write(f"echo Restarting CH{channel_num}\n")
                # f.write(f"cd /d \"{os.path.dirname(self.find_ffmpeg())}\"\n")
                # f.write(cmd + "\n")
                # f.write("pause\n")
            # self.log_message(f"CH{channel_num}: Command saved to restart_ch{channel_num}.bat", "buffer")
        # except Exception as e:
            # self.log_message(f"CH{channel_num}: Failed to save command file: {e}", "buffer")
        
        try:
            process = subprocess.Popen(
                cmd,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,  # ← ВАЖНО: stderr должен быть PIPE
                stdin=subprocess.PIPE if use_stdin else subprocess.DEVNULL,
                text=True,
                encoding='utf-8',
                errors='ignore',
                bufsize=1
            )
            
            threading.Thread(
                target=self.monitor_channel_output,
                args=(channel_num, process, channel_data),
                daemon=True
            ).start()            
            # # ⚡ ДОБАВИТЬ СЮДА ⚡
            # # Сохраняем stderr в файл для анализа
            # try:
                # with open(f"ch{channel_num}_stderr.log", "a", encoding='utf-8') as f:
                    # f.write(f"\n--- {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n")
                    # f.write(f"CMD: {cmd}\n\n")
            # except:
                # pass
            
            # # Запускаем поток для логирования stderr
            # def log_stderr(proc, ch):
                # for line in iter(proc.stderr.readline, ''):
                    # if line:
                        # try:
                            # with open(f"ch{ch}_stderr.log", "a", encoding='utf-8') as f:
                                # f.write(line)
                            # # Также в буфер приложения
                            # self.log_message(f"CH{ch} stderr: {line.strip()[:200]}", "ffmpeg")
                        # except:
                            # pass
            
            # threading.Thread(target=log_stderr, args=(process, channel_num), daemon=True).start()
            
            # Даем процессу время запуститься
            time.sleep(1)
            
            # Проверяем, что процесс жив
            if process.poll() is not None:
                return_code = process.poll()
                self.log_message(f"CH{channel_num}: ⚠️ Process died immediately, code {return_code}", "buffer")
                
                # Получаем вывод для диагностики
                try:
                    stdout, _ = process.communicate(timeout=1)
                    if stdout:
                        self.log_message(f"CH{channel_num}: Process output: {stdout[:500]}", "buffer")
                except:
                    pass
                
                return False
            
            self.channel_processes[channel_num] = {
                'process': process,
                'pid': process.pid,
                'stdin': process.stdin if use_stdin else None,
                'port': output_port,
                'is_radio': use_stdin,
                'is_emergency': False
            }
            
            self.root.after(5000, self.update_radio_metadata_new)
            self.log_message(f"CH{channel_num}: ✅ Original stream restarted (PID: {process.pid})", "buffer")
            return True
            
        except Exception as e:
            self.log_message(f"CH{channel_num}: ❌ Failed to restart: {e}", "buffer")
            return False

    def stop_channel_process(self, channel_num):
        """Stop individual channel process"""
       
        if channel_num in self.channel_processes:
            info = self.channel_processes[channel_num]
            process = info.get('process')
            
            if process and process.poll() is None:
                self.kill_process_fast(process, f"CH{channel_num}")
            
            del self.channel_processes[channel_num]
        
    def stop_all_channel_processes(self):
        """Stop all channel and emergency processes"""
        # Stop channel processes
        for ch_num in list(self.channel_processes.keys()):
            self.stop_channel_process(ch_num)
                
        # Stop main multiplexer
        if self.main_multiplexer_process:
            self.kill_process_fast(self.main_multiplexer_process, "Main Multiplexer")
            self.main_multiplexer_process = None
        
        # Stop emergency stream
        if self.emergency_process:
            self.kill_process_fast(self.emergency_process, "Emergency Stream")
            self.emergency_process = None
                                                                               
    def start_state_monitor(self):
        """Запуск единого монитора состояния"""
        if hasattr(self, '_state_monitor_running') and self._state_monitor_running:
            self.log_message("⚠️ State monitor already running, skipping", "buffer")
            return
        
        self.log_message("🚀 Starting state monitor", "buffer")
        self._state_monitor_running = True
        self.state_monitor_loop()

    def state_monitor_loop(self):
        """Единый монитор - вызывается каждую секунду"""
        # self.log_message(f"📊 STATE_MONITOR_LOOP: is_streaming={self.is_streaming}", "buffer")  # ← ОТЛАДКА
        
        if not self.is_streaming:
            self._state_monitor_running = False
            return
            # В начале функции, после проверки is_streaming:
            self.log_message(f"📊 Current channel_states: {self.channel_states}", "buffer")
        try:
            # 1. Проверка живых процессов
            self.check_active_processes()
                            
        except Exception as e:
            self.log_message(f"State monitor error: {e}", "buffer")
            import traceback
            self.log_message(traceback.format_exc(), "buffer")
        
        # Следующий вызов через 1 секунду
        if self.is_streaming:
            self.root.after(500, self.state_monitor_loop)
            
    def check_active_processes(self):
        """Проверка, что все ACTIVE каналы имеют живой процесс"""
        for ch_num in list(self.channel_processes.keys()):
            if self.channel_states.get(ch_num) != self.CHANNEL_STATE_ACTIVE:
                continue
                
            process_info = self.channel_processes.get(ch_num)
            if not process_info:
                self.transition_to_failed(ch_num, "no_process_info")
                continue
                
            process = process_info.get('process')
            if not process or process.poll() is not None:
                # Процесс умер, но мы не получили ошибку!
                self.log_message(f"CH{ch_num}: ⚠️ Process died silently", "buffer")
                self.transition_to_failed(ch_num, "silent_death")            
            
    def transition_to_failed(self, channel_num, reason=""):
        """Перевод канала в состояние FAILED"""
        self.log_message(f"🔥 TRANSITION_TO_FAILED: CH{channel_num}, reason={reason}", "buffer")
        self.log_message(f"   BEFORE: channel_states[{channel_num}] = {self.channel_states.get(channel_num)}", "buffer")
        
        # ⚡ НОВАЯ ЛОГИКА: если канал был ACTIVE и сразу упал
        was_active = self.channel_states.get(channel_num) == self.CHANNEL_STATE_ACTIVE
        
        # ⚠️ НЕ запускаем emergency, если стриминг уже остановлен
        if not self.is_streaming and reason != "startup_failed":
            self.log_message(f"CH{channel_num}: 🔴 FAILED ({reason}) - streaming stopped, no emergency", "buffer")
            self.stop_channel_process(channel_num)
            return
        
        if self.channel_states.get(channel_num) == self.CHANNEL_STATE_FAILED:
            return
        
        self.log_message(f"CH{channel_num}: 🔴 FAILED ({reason})", "buffer")
        
        # 1. Останавливаем процесс канала
        self.stop_channel_process(channel_num)
        
        # Останавливаем обновление метаданных для радио
        if channel_num in self.channel_processes:
            old_info = self.channel_processes.get(channel_num)
            if old_info and old_info.get('is_radio'):
                self.log_message(f"CH{channel_num}: ⏹️ Stopping metadata updates", "buffer")
                if hasattr(self, f'last_metadata_ch{channel_num}'):
                    delattr(self, f'last_metadata_ch{channel_num}')
        
        # 2. Обновляем состояние
        self.channel_states[channel_num] = self.CHANNEL_STATE_FAILED
        self.log_message(f"   AFTER: channel_states[{channel_num}] = {self.CHANNEL_STATE_FAILED}", "buffer")
        self.channel_fail_time[channel_num] = time.time()
        
        # ⭐ НОВАЯ ЛОГИКА: увеличиваем счетчик ТОЛЬКО если канал был ACTIVE
        if was_active:
            # Увеличиваем счетчик, но с верхним лимитом
            current_count = self.channel_fail_count.get(channel_num, 0)
            self.channel_fail_count[channel_num] = min(current_count + 1, 10)
            self.log_message(f"CH{channel_num}: ⚠️ Fail count increased to {current_count + 1}", "buffer")
                
        # 4. Запускаем заставку для URL, UDP и GRAB_WINDOW источников
        if self.is_streaming or reason == "startup_failed":
            channel_data = self.multiplex_channels.get(channel_num)
            if channel_data:
                source_type = channel_data['source_type'].get()
                # ⭐ ДОБАВЛЯЕМ grab_window в список
                if source_type in ["URL_Input", "UDP_MPTS", "grab_window"]:
                    self.start_individual_emergency(channel_num)
                    self.schedule_channel_check(channel_num)
                else:
                    self.log_message(f"CH{channel_num}: ⏭️ No emergency for {source_type}", "buffer")

        # ⭐ НОВОЕ: Обновляем индикатор Emergency
        self.root.after(0, self.update_channel_emergency_indicator, channel_num)
                    
        # ⭐ НОВОЕ: Сбрасываем статистику в "--"
        if channel_num in self.channel_speed:
            self.channel_speed[channel_num].set("---")
        if channel_num in self.channel_bitrate:
            self.channel_bitrate[channel_num].set("---")                    
        
        self.emergency_merged = False
        
    def schedule_channel_check(self, channel_num):
        """Запланировать проверку конкретного канала"""
        if channel_num in self.channel_check_timers:
            try:
                self.root.after_cancel(self.channel_check_timers[channel_num])
            except:
                pass
        
        channel_data = self.multiplex_channels.get(channel_num)
        if not channel_data:
            return
        
        source_type = channel_data['source_type'].get()
        fail_count = self.channel_fail_count.get(channel_num, 0)
        
        # Для grab_window используем специальную логику интервалов
        if source_type == "grab_window" and channel_num in self.window_search_state:
            attempts = self.window_search_state[channel_num]['attempts']
            interval = self.get_window_search_interval(attempts) * 1000  # в миллисекундах
            self.log_message(f"CH{channel_num}: ⏱️ Window search interval: {interval/1000}s (attempt {attempts})", "buffer")
        else:
            # ⭐ Проверяем cooldown
            if hasattr(self, 'channel_long_cooldown') and self.channel_long_cooldown.get(channel_num, False):
                interval = 180000  # 3 минуты
                self.log_message(f"CH{channel_num}: ⏱️ COOLDOWN: 3min interval", "buffer")
                self.channel_long_cooldown[channel_num] = False
            elif channel_num in self.channel_long_results:
                interval = 10000
            elif fail_count >= 3:
                interval = 180000
                self.log_message(f"CH{channel_num}: ⏱️ LONG CHECK COOLDOWN: 3min interval", "buffer")
            else:
                interval = 10000
        
        timer = self.root.after(interval, lambda: self.check_single_channel(channel_num))
        self.channel_check_timers[channel_num] = timer

    def get_window_search_interval(self, attempts):
        """Возвращает интервал проверки для окна на основе количества попыток"""
        intervals = self.window_search_intervals
        if attempts < len(intervals):
            return intervals[attempts]
        else:
            # После всех попыток проверяем раз в 5 минут
            return 300

    def check_single_channel(self, channel_num):
        """Проверить конкретный упавший канал"""
        if self.channel_states.get(channel_num) != self.CHANNEL_STATE_FAILED:
            return
        
        channel_data = self.multiplex_channels.get(channel_num)
        if not channel_data:
            return
        
        source_type = channel_data['source_type'].get()
        
        # Для grab_window проверяем наличие окон
        if source_type == "grab_window":
            windows = self.get_available_windows()
            current_window = channel_data['window_title'].get()
            original_title = channel_data.get('original_window_title', current_window)
            
            # Сохраняем оригинальное название при первом запуске
            if 'original_window_title' not in channel_data:
                channel_data['original_window_title'] = current_window
            
            self.log_message(f"CH{channel_num}: Checking grab_window recovery. Original: '{original_title[:50]}...'", "buffer")
            self.log_message(f"CH{channel_num}: Current: '{current_window[:50]}...'", "buffer")
            self.log_message(f"CH{channel_num}: Available windows: {len(windows)}", "buffer")
            
            # Состояние поиска для этого канала
            if channel_num not in self.window_search_state:
                self.window_search_state[channel_num] = {
                    'attempts': 0,
                    'last_search': time.time(),
                    'original_title': original_title
                }
            
            search_state = self.window_search_state[channel_num]
            
            # 1. Пытаемся найти оригинальное окно
            if original_title and original_title in windows:
                self.log_message(f"CH{channel_num}: ✅ Original window found!", "buffer")
                channel_data['window_title'].set(original_title)
                # Сбрасываем состояние поиска
                del self.window_search_state[channel_num]
                is_alive = True
                
            # 2. Если нет оригинального, ищем похожее
            else:
                similar = self.find_similar_window(original_title, windows) if original_title else None
                if similar:
                    self.log_message(f"CH{channel_num}: 🔍 Found similar window: '{similar[:50]}...'", "buffer")
                    channel_data['window_title'].set(similar)
                    # Сбрасываем состояние поиска
                    del self.window_search_state[channel_num]
                    is_alive = True
                    
                # 3. Если нет похожего, увеличиваем счетчик попыток и ждем дольше
                else:
                    search_state['attempts'] += 1
                    self.log_message(f"CH{channel_num}: ⏳ No suitable window found (attempt {search_state['attempts']})", "buffer")
                    
                    # Берем первое доступное окно, если оно есть, чтобы хоть что-то запустить
                    if windows and not current_window:
                        self.log_message(f"CH{channel_num}: Using first available window as temporary", "buffer")
                        channel_data['window_title'].set(windows[0])
                        is_alive = True
                    else:
                        is_alive = False
            
            url = current_window or "no window"
            
        elif source_type == "URL_Input":
            url = channel_data['url_input'].get().strip()
            is_alive = self.check_url_stream(channel_num, url)
        elif source_type == "UDP_MPTS":
            url = channel_data['udp_url'].get().strip()
            is_alive = self.check_udp_stream(channel_num, url)
        else:
            return
        
        # Пропускаем проверку если канал не должен проверяться
        if source_type not in ["URL_Input", "UDP_MPTS", "grab_window"]:
            return
        
        fail_count = self.channel_fail_count.get(channel_num, 0)
        
        # ⭐ РЕЖИМ ДЛИННЫХ ПРОВЕРОК
        if fail_count >= 3:
            if channel_num not in self.channel_long_results:
                self.channel_long_results[channel_num] = []
            
            self.channel_long_results[channel_num].append(is_alive)
            self.log_message(f"CH{channel_num}: 📊 Long check {len(self.channel_long_results[channel_num])}/7: {'✅' if is_alive else '❌'}", "buffer")
            
            if len(self.channel_long_results[channel_num]) >= 7:
                if all(self.channel_long_results[channel_num]):
                    self.log_message(f"CH{channel_num}: ✅ All 7 checks passed, restoring", "buffer")
                    del self.channel_long_results[channel_num]
                    self.restore_channel(channel_num)
                else:
                    fail_count = sum(1 for r in self.channel_long_results[channel_num] if not r)
                    self.log_message(f"CH{channel_num}: ⚠️ {fail_count} checks failed, waiting 3min", "buffer")
                    del self.channel_long_results[channel_num]
                    self.schedule_channel_check(channel_num)
            else:
                self.schedule_channel_check(channel_num)
            
            return
        
        # ⭐ ОБЫЧНЫЙ РЕЖИМ (2 ПРОВЕРКИ)
        if is_alive:
            count = self.channel_recovery_count.get(channel_num, 0) + 1
            self.channel_recovery_count[channel_num] = count
            
            if count >= 2:
                self.log_message(f"CH{channel_num}: ✅ Stream recovered (2/2)", "buffer")
                self.restore_channel(channel_num)
            else:
                self.log_message(f"CH{channel_num}: 🟡 Need one more confirmation ({count}/2)", "buffer")
                self.schedule_channel_check(channel_num)
        else:
            self.channel_recovery_count[channel_num] = 0
            # Для grab_window используем увеличивающийся интервал
            if source_type == "grab_window" and channel_num in self.window_search_state:
                attempts = self.window_search_state[channel_num]['attempts']
                interval = self.get_window_search_interval(attempts)
                self.log_message(f"CH{channel_num}: ⏱️ Next check in {interval}s (attempt {attempts})", "buffer")
                self.root.after(interval * 1000, lambda: self.check_single_channel(channel_num))
            else:
                self.schedule_channel_check(channel_num)
            
    def start_individual_emergency(self, channel_num):
        """Запуск отдельной заставки для одного канала"""
        # Останавливаем существующую индивидуальную заставку
        if channel_num in self.channel_individual_emergency:
            old_process = self.channel_individual_emergency[channel_num]
            if old_process and old_process.poll() is None:
                self.kill_process_fast(old_process, f"CH{channel_num} individual emergency")
        
        emergency_file = self.emergency_file_path.get()
        if not emergency_file or not os.path.exists(emergency_file):
            self.log_message(f"CH{channel_num}: ❌ No emergency file", "buffer")
            return
        
        ffmpeg_path = self.find_ffmpeg()
        safe_path = os.path.abspath(emergency_file).replace('\\', '/')
        output_port = self.base_multicast_port + channel_num - 1
        
        video_bitrate, audio_bitrate, _ = self.get_channel_bitrates()
        
        cmd = f'"{ffmpeg_path}" -hwaccel auto -re -stream_loop -1 '
        cmd += f'-i "{safe_path}" '
        cmd += f'-vcodec {self.video_codec.get()} -preset {self.video_preset.get()} '
        
        if self.video_codec.get() == "libx265":
            cmd += f'-x265-params "bitrate={video_bitrate}:vbv-maxrate={video_bitrate}:vbv-bufsize={video_bitrate//2}" '
        else:
            cmd += f'-b:v {video_bitrate}k -minrate {video_bitrate}k -maxrate {video_bitrate}k -bufsize {video_bitrate//2}k '
        
        cmd += f'-pix_fmt yuv420p -s {self.video_resolution.get()} -g {self.video_gop.get()} -r {self.video_fps.get()} -aspect 16:9 '
        cmd += f'-c:a {self.audio_codec.get()} -b:a {audio_bitrate} '
        cmd += f'-ar {self.audio_sample_rate.get()} -ac {self.get_audio_channels_ffmpeg()} '
        cmd += f'-metadata service_provider="EMERGENCY" '
        cmd += f'-metadata service_name="Emergency CH{channel_num}" '
        cmd += f'-f mpegts "udp://@238.0.0.1:{output_port}?pkt_size=1316&fifo_size=50000&overrun_nonfatal=1&reuse=1"'
        # self.log_message(f"CH{channel_num} Emergency CMD: {cmd}", "buffer")
        try:
            process = subprocess.Popen(
                cmd,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )
            
            # ⭐ ЗАПУСКАЕМ МОНИТОР ДЛЯ EMERGENCY
            threading.Thread(
                target=self.monitor_emergency_output,
                args=(channel_num, process),
                daemon=True
            ).start()
            
            time.sleep(1)  # Даем время на инициализацию
            
            self.channel_individual_emergency[channel_num] = process
            self.log_message(f"CH{channel_num}: 🟡 Individual emergency started (PID: {process.pid})", "buffer")
            
        except Exception as e:
            self.log_message(f"CH{channel_num}: ❌ Failed to start emergency: {e}", "buffer")

    def monitor_emergency_output(self, channel_num, process):
        """Мониторинг вывода emergency процесса с парсингом статистики"""
        try:
            for line in iter(process.stdout.readline, ''):
                if line:
                    line_stripped = line.strip()
                    
                    # ⭐ НОВОЕ: Парсим статистику (так же как в обычном канале)
                    if "speed=" in line_stripped:
                        match = re.search(r'speed=\s*([\d.]+)x', line_stripped)
                        if match:
                            speed = float(match.group(1))
                            self.root.after(0, self.update_channel_stats, channel_num, 'speed', speed)
                    
                    if "bitrate=" in line_stripped:
                        match = re.search(r'bitrate=\s*([\d.]+)\s*kbits/s', line_stripped)
                        if match:
                            bitrate = match.group(1)
                            self.root.after(0, self.update_channel_stats, channel_num, 'bitrate', bitrate)
                    
                    # ⭐ Существующий код логирования ошибок (НЕ ТРОГАЕМ)
                    if any(err in line.lower() for err in ['error', 'fail']):
                        self.log_message(f"Emergency CH{channel_num}: {line.strip()[:200]}", "buffer")
        except:
            pass         
                                                                                         
    def restore_channel(self, channel_num):
        """Восстановление канала - переключение с заставки на оригинал"""
        self.log_message(f"CH{channel_num}: 🔄 Restoring channel", "buffer")
        
        # ⚠️ ПОЛУЧАЕМ ДАННЫЕ КАНАЛА
        channel_data = self.multiplex_channels.get(channel_num)
        
        # ⭐ НОВОЕ: Очищаем состояние поиска окна
        if channel_num in self.window_search_state:
            del self.window_search_state[channel_num]        
        
        # ⭐ НОВОЕ: Сбрасываем статистику (будет обновлена новым процессом)
        if channel_num in self.channel_speed:
            self.channel_speed[channel_num].set("---")
        if channel_num in self.channel_bitrate:
            self.channel_bitrate[channel_num].set("---")        
        
        # 1. Останавливаем проверку канала
        if channel_num in self.channel_check_timers:
            try:
                self.root.after_cancel(self.channel_check_timers[channel_num])
                del self.channel_check_timers[channel_num]
                self.log_message(f"CH{channel_num}: ✅ Check timer cancelled", "buffer")
            except Exception as e:
                self.log_message(f"CH{channel_num}: ⚠️ Timer cancel error: {e}", "buffer")
        
        # 2. Очищаем счетчик восстановления
        if channel_num in self.channel_recovery_count:
            del self.channel_recovery_count[channel_num]
        
        # 3. Останавливаем индивидуальную заставку
        if channel_num in self.channel_individual_emergency:
            process = self.channel_individual_emergency[channel_num]
            if process and process.poll() is None:
                self.kill_process_fast(process, f"CH{channel_num} emergency")
            del self.channel_individual_emergency[channel_num]
            self.log_message(f"CH{channel_num}: ✅ Emergency stopped", "buffer")
        
        # 4. Возобновляем метаданные для радио
        if channel_data and channel_data.get('is_radio'):
            self.log_message(f"CH{channel_num}: ▶️ Resuming metadata updates", "buffer")
            self.root.after(10000, lambda ch=channel_num: self.update_radio_metadata_new())
        
        # 5. Запускаем оригинальный канал
        if self.restart_original_channel(channel_num):
            # Успешно запустили - обновляем состояние
            self.channel_states[channel_num] = self.CHANNEL_STATE_ACTIVE
            self.log_message(f"CH{channel_num}: ✅ Restored to ACTIVE", "buffer")
            
            # Очищаем временные данные
            if channel_num in self.channel_fail_time:
                del self.channel_fail_time[channel_num]
        
            # ⭐ НОВОЕ: Обновляем индикатор Emergency
            self.root.after(0, self.update_channel_emergency_indicator, channel_num)
    
            # # ✅ Просто уменьшаем счетчик, но не сбрасываем в 0
            # if channel_num in self.channel_fail_count:
                # current = self.channel_fail_count[channel_num]
                # self.channel_fail_count[channel_num] = max(1, current - 1)  # минимум 1
                # self.log_message(f"CH{channel_num}: Fail count reduced to {self.channel_fail_count[channel_num]}", "buffer")
        else:
            # Не удалось запустить - возвращаем в FAILED и ПРИНУДИТЕЛЬНО запускаем заставку
            self.log_message(f"CH{channel_num}: ⚠️ Restore failed, forcing emergency", "buffer")
            self.channel_states[channel_num] = self.CHANNEL_STATE_FAILED  # ← принудительно
            self.start_individual_emergency(channel_num)
            self.schedule_channel_check(channel_num)     
            
    def start_streaming(self):
        """Start multi-process streaming"""
        if self.is_streaming:
            return
        
        try:
            self.log_message("=== Starting multi-process streaming ===", "buffer")
            # ⭐ НОВОЕ: Сбрасываем значения статистики перед запуском
            
            # ⭐ СБРАСЫВАЕМ СТАТИСТИКУ ПЕРЕД ЗАПУСКОМ
            self.encoder_speed.set("---")
            self.encoder_bitrate.set("---")
            self.buffer_input_bitrate.set("0")
            self.buffer_output_bitrate.set("0")
            self.buffer_fill.set("0/0")
            
            # Сбрасываем значения каналов
            for ch_num in self.channel_speed:
                self.channel_speed[ch_num].set("---")
            for ch_num in self.channel_bitrate:
                self.channel_bitrate[ch_num].set("---")            
                      
            # 1. Start UDP/ZMQ buffer
            self.buffer_running = True
            self.buffer_thread = threading.Thread(target=self.run_zmq_buffer, daemon=True)
            self.buffer_thread.start()
            time.sleep(2)
            
            # 2. Clear old processes
            self.stop_all_channel_processes()
            self.channel_processes.clear()
            
            # 3. Start individual channel processes
            channels_started = 0
            for ch_num, channel_data in self.multiplex_channels.items():
                if not channel_data['enabled'].get():
                    continue
                
                # ⚠️ ОПРЕДЕЛЯЕМ source_type ЗДЕСЬ
                source_type = channel_data['source_type'].get()
                
                # # ✅ ПРОВЕРЯЕМ URL/UDP ПЕРЕД ЗАПУСКОМ
                # if source_type in ["URL_Input", "UDP_MPTS"]:
                    # if source_type == "URL_Input":
                        # url = channel_data['url_input'].get().strip()
                        # if url and not self.check_url_stream(ch_num, url):
                            # self.log_message(f"CH{ch_num}: ⚠️ Stream not available at startup", "buffer")
                            # self.transition_to_failed(ch_num, "startup_failed")
                            # continue
                    # else:  # UDP_MPTS
                        # url = channel_data['udp_url'].get().strip()
                        # if url and not self.check_udp_stream(ch_num, url):
                            # self.log_message(f"CH{ch_num}: ⚠️ UDP stream not available at startup", "buffer")
                            # self.transition_to_failed(ch_num, "startup_failed")
                            # continue
                
                output_port = self.base_multicast_port + ch_num - 1
                
                # if channel_data['source_type'].get() == "URL_Input" and channel_data['is_radio'].get():
                if (source_type == "URL_Input" and   # ← ИСПОЛЬЗУЕМ source_type
                    channel_data['is_radio'].get()):
                    channel_data['metadata_enabled_at_start'] = channel_data['show_metadata'].get()
                    channel_data['time_enabled_at_start'] = channel_data['radio_show_time'].get()
                    self.log_message(f"CH{ch_num}: metadata_start={channel_data['metadata_enabled_at_start']}, time_start={channel_data['time_enabled_at_start']}", "buffer")                
                    
                    cmd = self.build_radio_channel_command(ch_num, channel_data, output_port)
                    use_stdin = True
                else:
                    cmd = self.build_channel_ffmpeg_command(ch_num, channel_data, output_port)
                    use_stdin = False
                
                if not cmd:
                    continue
                
                try:
                    process = subprocess.Popen(
                        cmd,
                        shell=True,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        stdin=subprocess.PIPE if use_stdin else subprocess.DEVNULL,
                        text=True,
                        bufsize=1,
                        universal_newlines=True,
                        encoding='utf-8',
                        errors='replace'
                    )
                    
                    self.channel_processes[ch_num] = {
                        'process': process,
                        'pid': process.pid,
                        'stdin': process.stdin if use_stdin else None,
                        'port': output_port,
                        'is_radio': channel_data['is_radio'].get() if channel_data['source_type'].get() == "URL_Input" else False,  # ← ИСПРАВЬТЕ ЭТУ СТРОКУ
                        'is_emergency': False
                    }
                    
                    # Save stdin for radio
                    if use_stdin:
                        channel_data['ffmpeg_stdin'] = process.stdin
                        channel_data['ffmpeg_pid'] = process.pid
                        self.log_message(f"DEBUG: CH{ch_num} - stdin saved, PID: {process.pid}", "buffer")
                    
                    # Start monitoring
                    threading.Thread(
                        target=self.monitor_channel_output,
                        args=(ch_num, process, channel_data),
                        daemon=True
                    ).start()
                    
                    self.log_message(f"CH{ch_num}: Process started on port {output_port} (PID: {process.pid})", "buffer")
                    channels_started += 1
                    
                except Exception as e:
                    self.log_message(f"CH{ch_num}: Failed to start: {e}", "buffer")
            
            if channels_started == 0:
                self.log_message("No channels started", "buffer")
                return
                
            # Инициализация состояний
            for ch_num in self.multiplex_channels:
                if self.multiplex_channels[ch_num]['enabled'].get():
                    self.channel_states[ch_num] = self.CHANNEL_STATE_ACTIVE
                    # ⭐ НОВОЕ: Скрываем индикатор Emergency для всех активных каналов
                    self.root.after(100, self.update_channel_emergency_indicator, ch_num)

     
            # 4. Wait and start main multiplexer
            # time.sleep(1)
            self.start_main_multiplexer()                        
            self.log_message(f"=== Multi-process streaming started ({channels_started} channels) ===", "buffer")

            self.is_streaming = True
            
            # Запуск монитора
            self.start_state_monitor()                   
            
            # 6. Start radio metadata updates
            self.start_radio_metadata_updates()
                        
            self.encoder_status.set("Multi-Streaming")
            self.buffer_status.set("Running")
            self.update_status_colors()
            self.start_btn.config(state='disabled')
            self.stop_btn.config(state='normal') 
            # Auto-start overlay if enabled
            if self.overlay_auto_start.get():
                self.root.after(3000, self.start_overlay)            
            # После запуска процессов, проверяем наличие UI для каналов
            if self.multiplex_mode.get() and hasattr(self, 'channels_stats_container'):
                if not self.channels_stats_container.winfo_children():
                    self.init_channels_stats_ui()            
                    
        except Exception as e:
            self.log_message(f"Error starting streaming: {e}", "buffer")
            import traceback
            self.log_message(f"Traceback: {traceback.format_exc()}", "buffer")
            self.stop_streaming()
                          
    def stop_streaming(self):
        """Stop multi-process streaming"""
        self.log_message("Stopping multi-process streaming...", "buffer")

        # 2. Stop UDP/ZMQ buffer
        self.buffer_running = False
        if self.buffer_thread:
            self.buffer_thread.join(timeout=3)
            self.buffer_thread = None
            
        # 1. Stop all processes
        self.is_streaming = False
        self._state_monitor_running = False
        self.encoder_status.set("Stopped")
        self.buffer_status.set("Stopped")
        self.update_status_colors()        
        self.stop_all_channel_processes()
        
        # Очищаем индивидуальные заставки
        for ch_num, process in list(self.channel_individual_emergency.items()):
            self.kill_process_fast(process, f"CH{ch_num} individual emergency")
        self.channel_individual_emergency.clear()

        # 4. Очищаем состояния
        self.channel_states.clear()
        self.channel_fail_time.clear()
       
        
        # ⭐ СБРАСЫВАЕМ СТАТИСТИКУ ОСНОВНОГО ЭНКОДЕРА
        self.encoder_speed.set("---")
        self.encoder_bitrate.set("---")
        self.encoder_quality.set("---")
        self.stream_time.set("00:00:00")
        
        # ⭐ СБРАСЫВАЕМ СТАТИСТИКУ UDP БУФФЕРА
        self.buffer_input_bitrate.set("0")
        self.buffer_output_bitrate.set("0")
        self.buffer_fill.set("0/0")
        self.buffer_dropped.set("0")
        self.buffer_received.set("0")
        self.buffer_sent.set("0")
        self.buffer_overflow.set("0")
        self.bitrate_deviation.set("0.0%")
        
        # ⭐ СБРАСЫВАЕМ ИСТОРИЮ СКОРОСТИ
        self.main_speed_history.clear()
        
        # Сбрасываем значения каналов в "---"
        for ch_num in self.channel_speed:
            self.channel_speed[ch_num].set("---")
        for ch_num in self.channel_bitrate:
            self.channel_bitrate[ch_num].set("---")
        
        # Скрываем индикаторы Emergency
        for ch_num in list(self.channel_emergency_labels.keys()):
            self.root.after(0, self.update_channel_emergency_indicator, ch_num)
        
        # 4. Update buttons
        self.start_btn.config(state='normal')
        self.stop_btn.config(state='disabled')

        # 5. Clear stdin references
        for channel_data in self.multiplex_channels.values():
            if 'ffmpeg_stdin' in channel_data:
                channel_data['ffmpeg_stdin'] = None
            if 'ffmpeg_pid' in channel_data:
                channel_data['ffmpeg_pid'] = None
        
        self.log_message("Multi-process streaming stopped", "buffer")
        
        # Очищаем сохраненные метаданные
        for i in range(1, 5):
            if hasattr(self, f'last_metadata_ch{i}'):
                setattr(self, f'last_metadata_ch{i}', "")
        
        # Очищаем состояние поиска окон
        self.window_search_state.clear()
                        
    def run_zmq_buffer(self):
        """Run ZMQ buffer with guaranteed constant output bitrate"""
        IN_PORT = int(self.udp_input_port.get())
        LOCALHOST = self.localhost_ip.get()
        ZMQ_OUTPUT = f"tcp://{self.output_ip.get()}:{self.udp_output_port.get()}"
                
        # ⚡ НАСТРОЙКИ ДЛЯ СТАБИЛИЗАЦИИ
        TARGET_BUFFER = self.target_buffer.get()  # Больший буфер для лучшего сглаживания
        MIN_BUFFER = self.min_buffer.get()     # Минимальный буфер перед началом стабилизации
        MAX_BUFFER = self.max_buffer.get()    # Большой максимум для накопления
        CALIBRATION_PACKETS = self.calibration_packets.get()

        TARGET_BITRATE = float(self.muxrate.get())
        CALIBRATION_TIME = self.calibration_time.get()

        # Reset stats
        self.stats = {
            'received': 0, 'sent': 0, 'dropped': 0, 'buffer_overflow': 0,
            'last_check': time.time(), 'input_bitrate': 0, 'output_bitrate': 0

        }

        packet_buffer = queue.Queue(maxsize=MAX_BUFFER)
        input_tracker = deque(maxlen=500)
        output_tracker = deque(maxlen=500)

        # ⚡ КРИТИЧЕСКИЕ ПЕРЕМЕННЫЕ ДЛЯ СТАБИЛИЗАЦИИ
        send_interval = [0.001]
        calibrated = [False]
        last_send_time = [time.time()]
        packet_size_avg = [1316]
        total_bytes_sent = [0]
        output_start_time = [time.time()]
        buffer_health = [0]  # 0-100% здоровье буфера

        def calibrate_send_rate():
            """Точная калибровка для стабильного выхода"""
            self.log_message("🎯 Calibrating for constant output bitrate...", "buffer")
            
            # Ждем заполнения буфера до целевого уровня
            start_time = time.time()
            while packet_buffer.qsize() < TARGET_BUFFER and self.buffer_running:
                if time.time() - start_time > 10.0:  # Таймаут 10 секунд
                    self.log_message("⚠️ Calibration timeout - starting anyway", "buffer")
                    break
                time.sleep(0.01)
            
            if len(input_tracker) > 50:
                total_size = sum(size for _, size in input_tracker)
                packet_size_avg[0] = total_size / len(input_tracker)
                
                # ⚡ ТОЧНЫЙ РАСЧЕТ ДЛЯ ПОСТОЯННОГО БИТРЕЙТА
                packets_per_second = TARGET_BITRATE / (packet_size_avg[0] * 8)
                send_interval[0] = 1.0 / packets_per_second  # Точный интервал
                
                # Сбрасываем счетчики выхода
                total_bytes_sent[0] = 0
                output_start_time[0] = time.time()
                
                self.log_message("✅ Constant bitrate calibration complete!", "buffer")
                self.log_message(f"   Target: {TARGET_BITRATE/1000000:.3f} Mbps", "buffer")
                self.log_message(f"   Packets/sec: {packets_per_second:.1f}", "buffer")
                self.log_message(f"   Send interval: {send_interval[0]*1000:.3f} ms", "buffer")
                self.log_message(f"   Buffer target: {TARGET_BUFFER} packets", "buffer")
                calibrated[0] = True

        # Инициализация ZMQ
        try:
            context = zmq.Context()
            zmq_socket = context.socket(zmq.PUB)
            zmq_socket.setsockopt(zmq.SNDHWM, 100000)
            zmq_socket.setsockopt(zmq.SNDBUF, 8 * 1024 * 1024)
            zmq_socket.setsockopt(zmq.LINGER, 0)
            zmq_socket.bind(ZMQ_OUTPUT)
            #self.log_message(f"📥 UDP input: {ZMQ_OUTPUT}", "buffer")
            #self.log_message(f"✅ ZMQ ready for constant: {TARGET_BITRATE/1000000:.3f} Mbps", "buffer")
        except Exception as e:
            self.log_message(f"❌ ZMQ error: {e}", "buffer")
            return

        # UDP input
        try:
            sock_in = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock_in.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 8 * 1024 * 1024)
            sock_in.bind((LOCALHOST, IN_PORT))
            sock_in.settimeout(0.01)
            self.log_message(f"📥 UDP input: {LOCALHOST}:{IN_PORT}", "buffer")
        except Exception as e:
            self.log_message(f"❌ UDP error: {e}", "buffer")
            return

        # Receiver - стандартный
        def receiver():
            while self.buffer_running:
                try:
                    data, addr = sock_in.recvfrom(188 * 10)
                    current_time = time.time()
                    
                    if not calibrated[0] and len(input_tracker) < CALIBRATION_PACKETS:
                        input_tracker.append((current_time, len(data)))
                    
                    try:
                        packet_buffer.put_nowait(data)
                        self.stats['received'] += len(data)
                    except queue.Full:
                        self.stats['buffer_overflow'] += 1
                        self.stats['dropped'] += len(data)
                        
                except socket.timeout:
                    continue
                except Exception as e:
                    if self.buffer_running:
                        self.log_message(f"Receiver error: {e}", "buffer")
                    break

        # ⚡ SENDER С ГАРАНТИРОВАННЫМ ПОСТОЯННЫМ БИТРЕЙТОМ
        def sender():
            sequence_number = 0
            last_sequence_log = 0
            
            while self.buffer_running:
                current_time = time.time()
                current_buffer = packet_buffer.qsize()
                
                # ⚡ РАСЧЕТ ТЕКУЩЕГО ВЫХОДНОГО БИТРЕЙТА
                if calibrated[0]:
                    output_duration = current_time - output_start_time[0]
                    expected_bytes = (TARGET_BITRATE / 8) * output_duration
                    bytes_deviation = total_bytes_sent[0] - expected_bytes
                    
                    # Адаптивная коррекция скорости на основе отклонения
                    speed_correction = 1.0
                    if abs(bytes_deviation) > packet_size_avg[0] * 10:  # Значительное отклонение
                        if bytes_deviation > 0:  # Отправляем слишком быстро
                            speed_correction = 0.98  # Замедляем на 2%
                        else:  # Отправляем слишком медленно
                            speed_correction = 1.02  # Ускоряем на 2%
                
                try:
                    # ⚡ ТОЧНЫЙ КОНТРОЛЬ ВРЕМЕНИ ОТПРАВКИ
                    if calibrated[0]:
                        time_since_last = current_time - last_send_time[0]
                        target_interval = send_interval[0] * speed_correction
                        
                        if time_since_last < target_interval:
                            # Ждем точное время для постоянного битрейта
                            sleep_time = target_interval - time_since_last
                            if sleep_time > 0.00001: #10 микросекунд
                                time.sleep(sleep_time)
                                current_time = time.time()  # Обновляем время после сна
                    
                    # Получаем данные (может быть пустая очередь)
                    try:
                        data = packet_buffer.get_nowait()
                    except queue.Empty:
                        # ⚡ ЕСЛИ БУФЕР ПУСТ - ГЕНЕРИРУЕМ DUMMY DATA для поддержания битрейта
                        if calibrated[0] and current_buffer == 0:
                            # Создаем фиктивный пакет для поддержания потока
                            dummy_size = int(packet_size_avg[0])
                            data = b'\x00' * dummy_size
                            #self.log_message("⚠️ BUFFER EMPTY - generating dummy data", "buffer")
                        else:
                            time.sleep(0.001)
                            continue
                    
                    # Отправка
                    try:
                        zmq_socket.send(data, zmq.NOBLOCK)
                        self.stats['sent'] += len(data)
                        output_tracker.append((current_time, len(data)))
                        last_send_time[0] = current_time
                        total_bytes_sent[0] += len(data)
                        sequence_number += 1
                        
                        # Логируем каждые 1000 пакетов
                        if sequence_number - last_sequence_log >= 1000:
                            current_output_rate = (total_bytes_sent[0] * 8) / (current_time - output_start_time[0])
                            deviation_pct = ((current_output_rate - TARGET_BITRATE) / TARGET_BITRATE) * 100
                            last_sequence_log = sequence_number
                            
                    except zmq.Again:
                        # ZMQ buffer full - возвращаем пакет (кроме dummy)
                        if data != b'\x00' * len(data):
                            try:
                                packet_buffer.put_nowait(data)
                            except queue.Full:
                                self.stats['dropped'] += len(data)
                        time.sleep(0.0001)
                        
                except Exception as e:
                    if self.buffer_running:
                        self.log_message(f"Sender error: {e}", "buffer")

        # Statistics с акцентом на стабильность
        def statistics():
            last_stats_time = time.time()
            last_received = 0
            last_sent = 0
            
            while self.buffer_running:
                try:
                    current_time = time.time()
                    time_diff = current_time - last_stats_time
                    
                    if time_diff >= 2.0:  # 2 секунды для стабильных измерений
                        current_received = self.stats['received']
                        current_sent = self.stats['sent']
                        
                        # ⚡ РАЗДЕЛИМ СТАТИСТИКУ: вход UDP vs выход ZMQ
                        input_rate = (current_received - last_received) * 8 / time_diff / 1000  # kbps
                        zmq_output_rate = (current_sent - last_sent) * 8 / time_diff / 1000     # kbps ⚡ РЕАЛЬНЫЙ ВЫХОД ZMQ
                        
                        target_kbps = TARGET_BITRATE / 1000
                        
                        self.stats['input_bitrate'] = input_rate
                        self.stats['output_bitrate'] = zmq_output_rate
                        
                        # ⚡ ВЫЧИСЛЯЕМ ОТКЛОНЕНИЕ ДО ОБНОВЛЕНИЯ GUI
                        output_deviation = abs(zmq_output_rate - target_kbps) / target_kbps * 100
                        buffer_health = min(100, (packet_buffer.qsize() / TARGET_BUFFER) * 100)
                        
                        # ⚡ ОБНОВЛЯЕМ ВСЕ ПЕРЕМЕННЫЕ GUI
                        self.root.after(0, self.buffer_input_bitrate.set, f"{input_rate:.1f}")
                        self.root.after(0, self.buffer_output_bitrate.set, f"{zmq_output_rate:.1f}")
                        self.root.after(0, self.buffer_fill.set, f"{packet_buffer.qsize()}/{MAX_BUFFER}")
                        self.root.after(0, self.buffer_received.set, f"{current_received}")
                        self.root.after(0, self.buffer_sent.set, f"{current_sent}")
                        self.root.after(0, self.buffer_dropped.set, f"{self.stats['dropped']}")
                        self.root.after(0, self.buffer_target.set, f"{target_kbps:.1f}")
                        self.root.after(0, self.bitrate_deviation.set, f"{output_deviation:.1f}%")
                        
                        # Статус стабильности на основе ZMQ выхода
                        if output_deviation > 5:
                            stability = "🔴 UNSTABLE"
                        elif output_deviation > 2:
                            stability = "🟡 GOOD" 
                        else:
                            stability = "🟢 PERFECT"
                        
                        # Визуализация входного потока
                        input_status = "📈 HIGH" if input_rate > target_kbps * 1.2 else \
                                      "📉 LOW" if input_rate < target_kbps * 0.8 else \
                                      "📊 NORMAL"
                                                
                        # Авто-калибровка
                        if not calibrated[0] and packet_buffer.qsize() >= MIN_BUFFER:
                            calibrate_send_rate()
                        
                        last_received = current_received
                        last_sent = current_sent
                        last_stats_time = current_time
                    
                    time.sleep(1.0)
                    
                except Exception as e:
                    if self.buffer_running:
                        self.log_message(f"Statistics error: {e}", "buffer")

        # Запуск
        receiver_thread = threading.Thread(target=receiver, daemon=True)
        sender_thread = threading.Thread(target=sender, daemon=True)
        stats_thread = threading.Thread(target=statistics, daemon=True)
        
        receiver_thread.start()
        sender_thread.start()
        stats_thread.start()
        
        
        
        try:
            while self.buffer_running:
                time.sleep(0.1)
        finally:
            sock_in.close()
            zmq_socket.close()
            context.term()

    def update_channel_stats(self, channel_num, stat_type, value):
        """Обновление статистики канала (speed или bitrate)"""
        # Инициализация при первом обращении
        if channel_num not in self.channel_speed:
            self.channel_speed[channel_num] = tk.StringVar(value="0.00")
            self.channel_bitrate[channel_num] = tk.StringVar(value="0")
        
        if stat_type == 'speed':
            # Форматируем с двумя знаками после запятой
            self.channel_speed[channel_num].set(f"{value:.2f}")
            self.channel_last_speed[channel_num] = value
            # Обновляем цвет если есть метка
            if channel_num in self.channel_speed_labels:
                self.update_channel_speed_color(channel_num)
        elif stat_type == 'bitrate':
            # Битрейт как целое число
            self.channel_bitrate[channel_num].set(str(int(float(value))))
            
    def update_channel_speed_color(self, channel_num):
        """Обновление цвета скорости канала (как у основного)"""
        try:
            speed = float(self.channel_speed[channel_num].get())
            label = self.channel_speed_labels.get(channel_num)
            if label:
                if speed >= 1.0:
                    label.configure(foreground='green')
                elif speed >= 0.990:
                    label.configure(foreground='orange')
                else:
                    label.configure(foreground='red')
        except (ValueError, KeyError):
            pass            
            
    def update_channels_visibility(self):
        """Обновляет видимость каналов (вызывается при изменении multiplex_mode)"""
        if not hasattr(self, 'channels_frame'):
            return
        
        if self.multiplex_mode.get():
            self.channels_frame.pack(side='left', fill='x', expand=True)
            if not hasattr(self, 'channels_stats_container') or not self.channels_stats_container.winfo_children():
                # Создаем UI если его нет
                self.channels_stats_container = ttk.Frame(self.channels_frame)
                self.channels_stats_container.pack(fill='x')
                self.init_channels_stats_ui()
        else:
            self.channels_frame.pack_forget()  

    def update_channel_emergency_indicator(self, channel_num):
        """Обновляет видимость индикатора Emergency для канала"""
        if channel_num not in self.channel_emergency_labels:
            return
        
        emergency_label = self.channel_emergency_labels[channel_num]
        
        # Проверяем состояние канала
        if self.channel_states.get(channel_num) == self.CHANNEL_STATE_FAILED:
            # Канал в состоянии FAILED - показываем E
            emergency_label.pack(side='left', padx=(0, 2))
        else:
            # Канал работает - скрываем E
            emergency_label.pack_forget()            

    def init_channels_stats_ui(self):
        """Создает UI для статистики каналов (вызывается после загрузки каналов)"""
        if not hasattr(self, 'channels_stats_container') or not self.channels_stats_container:
            return
        
        # Проверяем, загружены ли каналы
        if not hasattr(self, 'multiplex_channels') or not self.multiplex_channels:
            self.log_message("⏳ Channels not loaded yet, postponing UI init", "buffer")
            self.root.after(500, self.init_channels_stats_ui)
            return
        
        # Очищаем контейнер
        for widget in self.channels_stats_container.winfo_children():
            widget.destroy()
        
        # Словари для хранения виджетов
        self.channel_frames = {}  # {channel_num: frame}
        self.channel_speed_labels = {}  # {channel_num: label}
        self.channel_bitrate_labels = {}  # {channel_num: label}
        self.channel_emergency_labels = {}  # {channel_num: label}
        
        # Получаем активные каналы в порядке их отображения в мультиплексе
        active_channels = []
        display_counter = 1
        
        for ch_num, channel_data in self.multiplex_channels.items():
            if channel_data['enabled'].get():
                # Сохраняем соответствие: отображаемый номер -> реальный номер канала
                active_channels.append((display_counter, ch_num, channel_data))
                display_counter += 1
        
        if not active_channels:
            ttk.Label(self.channels_stats_container, text="No active channels", 
                     font=('Arial', 8, 'italic')).pack(anchor='w')
            return
        
        self.log_message(f"Creating UI for {len(active_channels)} active channels", "buffer")
        
        # Создаем столбцы по 2 канала
        columns = []
        current_col_frame = None
        
        for i, (display_num, real_num, channel_data) in enumerate(active_channels):
            if i % 2 == 0:
                current_col_frame = ttk.Frame(self.channels_stats_container)
                current_col_frame.pack(side='left', padx=(15 if i > 0 else 0, 15))
                columns.append(current_col_frame)
            
            if current_col_frame:
                # Создаем фрейм для канала (ключ - реальный номер для связи с процессами)
                ch_frame = ttk.Frame(current_col_frame)
                ch_frame.pack(fill='x', pady=(0 if i % 2 == 0 else 8, 0))
                self.channel_frames[real_num] = ch_frame
                
                # Инициализация переменных статистики если нужно
                if real_num not in self.channel_speed:
                    self.channel_speed[real_num] = tk.StringVar(value="---")
                    self.channel_bitrate[real_num] = tk.StringVar(value="---")
                
                # ОДНА СТРОКА: CH{display_num} S: 1.02x B: 445k
                row_frame = ttk.Frame(ch_frame)
                row_frame.pack(anchor='w')
                
                # ⭐ ИСПОЛЬЗУЕМ ОТОБРАЖАЕМЫЙ НОМЕР ДЛЯ ПОЛЬЗОВАТЕЛЯ
                ttk.Label(row_frame, text=f"CH{display_num}", 
                         font=('Arial', 7, 'bold')).pack(side='left', padx=(0, 4))
                
                # Индикатор Emergency (привязан к реальному номеру)
                emergency_label = ttk.Label(row_frame, text="E", 
                                           font=('Arial', 7, 'bold'), 
                                           foreground='red')
                emergency_label.pack(side='left', padx=(0, 2))
                emergency_label.pack_forget()
                self.channel_emergency_labels[real_num] = emergency_label
                
                # S:
                ttk.Label(row_frame, text="S:", font=('Arial', 7, 'bold')).pack(side='left')
                
                speed_label = ttk.Label(row_frame, textvariable=self.channel_speed[real_num],
                                       font=('Arial', 9, 'bold'))
                speed_label.pack(side='left', padx=(2, 4))
                self.channel_speed_labels[real_num] = speed_label
                
                # B:
                ttk.Label(row_frame, text="B:", font=('Arial', 7, 'bold')).pack(side='left')
                
                bitrate_label = ttk.Label(row_frame, textvariable=self.channel_bitrate[real_num],
                                         font=('Arial', 9, 'bold'), foreground='blue')
                bitrate_label.pack(side='left', padx=(2, 2))
                
                ttk.Label(row_frame, text="k", font=('Arial', 6)).pack(side='left')
                self.channel_bitrate_labels[real_num] = bitrate_label
        
        self.log_message(f"UI created successfully for {len(active_channels)} channels", "buffer")
                        
    def check_system_speed(self, current_speed):
        """Проверка скорости основного мультиплексора и перезапуск при необходимости"""
        
        # Проверяем cooldown (не перезапускать слишком часто)
        current_time = time.time()
        if current_time - self.speed_restart_cooldown < self.speed_restart_cooldown_seconds:
            return
        
        # Добавляем текущую скорость в историю
        self.main_speed_history.append(current_speed)
        
        # Храним только последние 10 значений
        if len(self.main_speed_history) > 10:
            self.main_speed_history.pop(0)
        
        # Проверяем, достаточно ли данных
        if len(self.main_speed_history) < self.speed_restart_count:
            return
        
        # Берем последние N значений для проверки
        last_values = self.main_speed_history[-self.speed_restart_count:]
        
        # Проверяем, все ли значения ниже порога
        all_below_threshold = all(speed < self.speed_restart_threshold for speed in last_values)
        
        if all_below_threshold:
            self.log_message(f"⚠️ CRITICAL: Main multiplexer speed below {self.speed_restart_threshold:.3f}x for {self.speed_restart_count} checks", "buffer")
            self.log_message(f"   Last values: {[f'{s:.3f}x' for s in last_values]}", "buffer")
            self.log_message("🔄 Restarting entire streaming system...", "buffer")
            
            # Устанавливаем cooldown
            self.speed_restart_cooldown = current_time
            
            # Очищаем историю
            self.main_speed_history.clear()
            
            # Перезапускаем в главном потоке
            self.root.after(0, self.restart_streaming_system)

    def restart_streaming_system(self):
        """Полный перезапуск системы стриминга"""
        if not self.is_streaming:
            return
        
        self.log_message("🔄 Executing full system restart...", "buffer")
        
        # Сохраняем состояние
        was_streaming = self.is_streaming
        was_modulator = self.modulator_running
        
        # Останавливаем всё
        self.stop_streaming()
        
        # Небольшая пауза
        time.sleep(3)
        
        # Перезапускаем
        if was_streaming:
            self.start_streaming()
        
        # Перезапускаем модулятор если был включен
        if was_modulator:
            self.root.after(5000, self.start_modulator)
        
        self.log_message("✅ System restart completed", "buffer") 
    
    def get_audio_channels_ffmpeg(self):
        """Convert channel name to FFmpeg format"""
        channels_map = {
            "mono": "1",
            "stereo": "2",
            "5.1": "6"
        }
        return channels_map.get(self.audio_channels.get(), "2")
                
    def build_ffmpeg_command(self):
        """Build FFmpeg command - selects between simple and multiplex mode"""
        if self.multiplex_mode.get():
            # Return all commands for multi-process system
            return self.build_multiplex_system_command()
        else:
            # Original simple mode command
            return self.build_simple_ffmpeg_command()
    
    def build_simple_ffmpeg_command(self):
        """Build simple FFmpeg command for single channel - EXACT format"""
        codec = self.video_codec.get()
        preset = self.video_preset.get()
        tune = self.video_tune.get()
        fps = self.video_fps.get()
        gop = self.video_gop.get()
        custom_options = self.custom_options.get()
        audio_codec = self.audio_codec.get()
        audio_channels = self.get_audio_channels_ffmpeg()
        
        # Получаем путь к ffmpeg
        ffmpeg_path = self.find_ffmpeg()
        
        # Base command - ТОЧНО как в оригинале
        cmd = (
            f'"{ffmpeg_path}" -thread_queue_size 2048 -itsoffset -0.65 '
            f'-f dshow -thread_queue_size 10K -rtbufsize 400M -i "video={self.video_input_device.get()}" '
            f'-f dshow -thread_queue_size 10K -rtbufsize 400M -i "audio={self.audio_input_device.get()}" '
        )
        
        # Video codec specific parameters
        if codec == "libx265":
            cmd += (
                f'-vcodec libx265 -preset {preset} -tune {tune} {custom_options} '
                f'-x265-params "bitrate={self.video_bitrate.get()}:vbv-maxrate={self.video_bitrate.get()}:vbv-bufsize={self.video_bufsize.get()}" '
            )
        elif codec in ["hevc_nvenc", "h264_nvenc"]:
            cmd += (
                f'-vcodec {codec} -preset {preset} -tune {tune} {custom_options} '
                f'-b:v {self.video_bitrate.get()}k -minrate {self.video_bitrate.get()}k -maxrate {self.video_bitrate.get()}k -bufsize {self.video_bufsize.get()}k '
            )
        elif codec in ["h264_amf", "hevc_amf"]:
            if codec == "hevc_amf":
                cmd += (
                    f'-vcodec hevc_amf -profile_tier 1 -header_insertion_mode 1 -quality {preset} -rc cbr  {custom_options} '
                    f'-g {gop} '
                    f'-b:v {self.video_bitrate.get()}k -minrate {self.video_bitrate.get()}k -maxrate {self.video_bitrate.get()}k -bufsize {self.video_bufsize.get()}k '
                )
            else:
                cmd += (
                    f'-vcodec {codec} -quality {preset} {custom_options} '
                    f'-b:v {self.video_bitrate.get()}k -minrate {self.video_bitrate.get()}k -maxrate {self.video_bitrate.get()}k -bufsize {self.video_bufsize.get()}k '
                )
        else:
            cmd += (
                f'-vcodec libx265 -preset {preset} -tune {tune} '
                f'-x265-params "bitrate={self.video_bitrate.get()}:vbv-maxrate={self.video_bitrate.get()}:vbv-bufsize={self.video_bufsize.get()}" '
            )
        
        # Common parameters - ТОЧНО как в оригинале
        cmd += (
            f'-pix_fmt yuv420p -s {self.video_resolution.get()} -g {self.video_gop.get()} -aspect 16:9 -r {fps} '
            f'-map 0:0 -map 1:0 -c:a {audio_codec} '
            f'-b:a {self.audio_bitrate.get()} '
            f'-ar {self.audio_sample_rate.get()} '
            f'-ac {audio_channels} '
            f'-f mpegts -max_delay 300K -max_interleave_delta 4M '
            f'-muxdelay 0.1 -muxpreload 0.1 -pcr_period 40 '
            f'-pat_period 0.4 -sdt_period 0.5 '
            f'-mpegts_original_network_id 1 -mpegts_transport_stream_id 1 '
            f'-mpegts_pmt_start_pid 4096 -mpegts_start_pid 256 '
            f'-mpegts_flags system_b '
            f'-metadata service_provider="{self.service_provider.get()}" '
            f'-metadata service_name="{self.service_name.get()}" '
            f'-metadata title="{self.service_name.get()}" '
            f'-metadata artist="{self.service_name.get()}" '
            f'-flush_packets 0 -muxrate {self.muxrate.get()} '
            f'"udp://{self.localhost_ip.get()}:{self.udp_input_port.get()}?pkt_size=1316&buffer_size=500000&overrun_nonfata=1&burst_bits=1" '
            f'-flush_packets 0 '
            # self.log_message(f"CH{channel_num} Simple CMD: {cmd}", "buffer")
        )
        # self.log_message(f"CH{channel_num} Simple CMD: {cmd}", "buffer")
        return cmd

    def build_channel_ffmpeg_command(self, channel_num, channel_data, output_port):
        """Build FFmpeg command for individual channel"""
        ffmpeg_path = self.find_ffmpeg()
        
        cmd = f'"{ffmpeg_path}" -hwaccel auto '
        
        source_type = channel_data['source_type'].get()
        is_radio = (source_type == "URL_Input" and channel_data['is_radio'].get())
        
        # Add -re for media files and URLs (not for input_devices or radio)
        if source_type in ["media_folder", "URL_Input"] and not is_radio:
            cmd += '-re '
        
        # Build input based on source type
        if source_type == "input_devices":
            video_device = channel_data['video_device'].get()
            audio_device = channel_data['audio_device'].get()
            
            if video_device:
                cmd += f'-thread_queue_size 2048 -itsoffset -0.65 '
                cmd += f'-f dshow -thread_queue_size 512K -rtbufsize 400M '
                cmd += f'-i "video={video_device}" '
            
            if audio_device:
                cmd += f'-f dshow -thread_queue_size 512K -rtbufsize 400M '
                cmd += f'-i "audio={audio_device}" '
        
        elif source_type == "media_folder":
            media_path = channel_data['media_path'].get()
            if media_path and os.path.exists(media_path):
                playlist_file = self.create_media_playlist(channel_num, media_path)
                if playlist_file and os.path.exists(playlist_file):
                    safe_path = os.path.abspath(playlist_file).replace('\\', '/')
                    cmd += f' -f concat -safe 0 -stream_loop -1 -i "{safe_path}" '
                else:
                    return None
        
        elif source_type == "URL_Input":
            url = channel_data['url_input'].get().strip()
            if url:
                if is_radio:
                    # Radio mode uses separate method
                    return self.build_radio_channel_command(channel_num, channel_data, output_port)
                else:
                    cmd += f' -timeout 2000000 -reconnect 0 -i "{url}" '
                    
        elif source_type == "grab_window":
            window_title = channel_data['window_title'].get().strip()
            audio_device = channel_data['audio_device'].get().strip()
            
            if not window_title:
                self.log_message(f"CH{channel_num}: No window selected", "buffer")
                return None
            
            # Экранируем кавычки в названии окна
            safe_title = window_title.replace('"', '\\"')
            
            # Захват окна
            cmd += f'-hwaccel auto -thread_queue_size 2048 -itsoffset -0.65 '
            cmd += f'-f gdigrab -thread_queue_size 512K -rtbufsize 400M -framerate {self.video_fps.get()} '
            cmd += f'-i title="{safe_title}" '
            
            # Аудио устройство
            if audio_device:
                cmd += f'-f dshow -thread_queue_size 512K -rtbufsize 400M -i "audio={audio_device}" '
            
            # Для service_name берем первые слова из названия окна
            words = window_title.split()
            service_name = ' '.join(words[:3]) if words else f"Window_{channel_num}"
            if len(service_name) > 30:
                service_name = service_name[:27] + "..."
            
            # Сохраняем для метаданных
            channel_data['service_name_override'] = service_name                    
        
        elif source_type == "UDP_MPTS":
            url = channel_data['udp_url'].get().strip()
            if url:
                cmd += f'-timeout 2000000 -i "{url}" '
        
        # Get bitrates (already divided for multiplex mode)
        video_bitrate, audio_bitrate, _ = self.get_channel_bitrates()
        video_per_channel = video_bitrate  # Already divided in get_channel_bitrates()
        
        # Video encoding
        codec = self.video_codec.get()
        preset = self.video_preset.get()
        tune = self.video_tune.get()
        
        cmd += f'-vcodec {codec} -preset {preset} '
        if tune:
            cmd += f'-tune {tune} '
        
        if codec == "libx265":
            cmd += f'-x265-params "bitrate={video_per_channel}:vbv-maxrate={video_per_channel}:vbv-bufsize={video_per_channel//2}" '
        else:
            cmd += f'-b:v {video_per_channel}k -minrate {video_per_channel}k -maxrate {video_per_channel}k -bufsize {video_per_channel//2}k '
        
        # Common video params
        cmd += f'-pix_fmt yuv420p -s {self.video_resolution.get()} -g {self.video_gop.get()} -aspect 16:9 -r {self.video_fps.get()} '
        
        # Audio encoding
        cmd += f'-c:a {self.audio_codec.get()} -b:a {audio_bitrate} '
        cmd += f'-ar {self.audio_sample_rate.get()} -ac {self.get_audio_channels_ffmpeg()} '
        
        # Metadata
        if source_type == "grab_window" and 'service_name_override' in channel_data:
            service_name = channel_data['service_name_override']
        else:
            service_name = channel_data['name'].get() or f"Channel_{channel_num}"

        safe_name = service_name.replace('"', '\\"')
        cmd += f'-metadata service_provider="{self.service_provider.get()}" '
        cmd += f'-metadata service_name="{safe_name}" '
        
        # Output to multicast UDP
        cmd += f'-f mpegts -flush_packets 0 '
        cmd += f'"udp://@238.0.0.1:{output_port}?pkt_size=1316&fifo_size=50000&overrun_nonfatal=1"'
        # self.log_message(f"CH{channel_num} Channel CMD: {cmd}", "buffer")
        
        return cmd

    def build_main_multiplexer_command(self):
        """Build main multiplexer command (c copy only)"""
        ffmpeg_path = self.find_ffmpeg()
        
        cmd = f'"{ffmpeg_path}" -hwaccel auto -re '
        
        # Add all active channels as UDP inputs
        active_channels = []
        input_index = 0
        
        for ch_num, channel_data in self.multiplex_channels.items():
            if channel_data['enabled'].get():
                output_port = self.base_multicast_port + ch_num - 1
                cmd += f'-i "udp://@238.0.0.1:{output_port}?pkt_size=1316&fifo_size=500000" '
                active_channels.append((ch_num, channel_data, input_index))
                input_index += 1
        
        if not active_channels:
            return None
        
        # Map commands for each channel
        stream_counter = 0
        for ch_num, channel_data, input_idx in active_channels:
            # For UDP MPTS use PID filtering, for others simple map
            if channel_data['source_type'].get() == "UDP_MPTS":
                video_pid = channel_data.get('saved_video_pid', '0x100')
                audio_pid = channel_data.get('saved_audio_pid', '0x101')
                cmd += f'-map {input_idx}:i:{video_pid}? -map {input_idx}:i:{audio_pid}? '
            else:
                cmd += f'-map {input_idx}:v? -map {input_idx}:a? '
            stream_counter += 2
        
        # Programs
        stream_counter = 0
        for ch_num, channel_data, input_idx in active_channels:
            service_name = channel_data['name'].get() or f"Channel_{ch_num}"
            safe_name = service_name.replace('"', '\\"')
            cmd += f'-program title="{safe_name}":st={stream_counter}:st={stream_counter+1} '
            stream_counter += 2
        
        # Multiplexing parameters (c copy only + muxrate)
        cmd += '-c copy -movflags +faststart '
        cmd += self.get_mpegts_output_params()  # Original method with muxrate
        # self.log_message(f"CH{channel_num} Main MP CMD: {cmd}", "buffer")
        return cmd

    def build_multiplex_system_command(self):
        """Build all commands for multi-process system"""
        commands = ["=== MULTI-PROCESS FFMPEG COMMANDS ===\n"]
        
        # 1. Individual channel commands
        commands.append("=== INDIVIDUAL CHANNEL COMMANDS ===")
        for ch_num, channel_data in self.multiplex_channels.items():
            if channel_data['enabled'].get():
                output_port = self.base_multicast_port + ch_num - 1
                
                if channel_data['source_type'].get() == "URL_Input" and channel_data['is_radio'].get():
                    cmd = self.build_radio_channel_command(ch_num, channel_data, output_port)
                else:
                    cmd = self.build_channel_ffmpeg_command(ch_num, channel_data, output_port)
                
                if cmd:
                    commands.append(f"\n--- CH{ch_num} Command ---")
                    commands.append(cmd)
        
        # 2. Main multiplexer command
        commands.append("\n\n=== MAIN MULTIPLEXER COMMAND ===")
        main_cmd = self.build_main_multiplexer_command()
        if main_cmd:
            commands.append(main_cmd)
        
        return "\n".join(commands)
                
    def start_main_multiplexer(self):
        """Start main multiplexer process"""
        cmd = self.build_main_multiplexer_command()
        if not cmd:
            self.log_message("Failed to build multiplexer command", "buffer")
            return
        
        try:
            self.main_multiplexer_process = subprocess.Popen(
                cmd,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )
            
            threading.Thread(
                target=self.monitor_multiplexer_output,
                daemon=True
            ).start()
            
            self.log_message(f"Main multiplexer started (PID: {self.main_multiplexer_process.pid})", "buffer")
            
        except Exception as e:
            self.log_message(f"Failed to start multiplexer: {e}", "buffer")        
                        
    def start_radio_metadata_updates(self):
        """Start radio metadata updates"""
        if not self.is_streaming:
            return
        
        self.log_message("=== SCHEDULING METADATA UPDATES ===", "buffer")
        
        # Первое обновление через 5 секунд
        self.root.after(10000, self.update_radio_metadata_new)
        
    def build_radio_channel_command(self, channel_num, channel_data, output_port):
        """Создает команду для радио-канала с filter_complex и stdin"""
        # self.log_message(f"DEBUG: Building radio command for CH{channel_num}", "buffer")
        
        ffmpeg_path = self.find_ffmpeg()
        
        # Используем переданные параметры
        radio_text = channel_data['radio_text'].get()
        radio_text_safe = radio_text.replace("'", "'\\''").replace(':', '\\:')
        text_color = channel_data['radio_text_color'].get()
        text_size = channel_data['radio_text_size'].get()
        
        # Фон
        bg_type = channel_data['radio_bg_type'].get()
        resolution = self.video_resolution.get()
        fps = self.video_fps.get()
        
        # Создаем filter_complex
        filter_chains = []
        filter_indices = {}  # Сохраняем индексы для этого канала
        filter_counter = 0
        
        # self.log_message(f"DEBUG: CH{channel_num} - Filter setup: text='{radio_text[:30]}...'", "buffer")
        
        # 1. Основной текст радио
        text_filter = (
            f"drawtext=text='{radio_text_safe}':"
            f"fontsize={text_size}:"
            f"fontcolor={text_color}:"
            f"box=1:"
            f"boxcolor=black@0.5:"
            f"boxborderw=10:"
            f"x=(w-text_w)/2:"
            f"y=(h-text_h)/2"
        )
        filter_chains.append(text_filter)
        filter_indices['text'] = filter_counter
        filter_counter += 1
        # self.log_message(f"DEBUG: CH{channel_num} - Text filter index: {filter_indices['text']}", "buffer")
        
        # 2. Метаданные (если включены)
        if channel_data['show_metadata'].get():
            metadata_filter = (
                f"drawtext=text='Radio Station':"  # Пустой текст - будет обновляться через stdin
                f"fontsize={channel_data['metadata_size'].get()}:"
                f"fontcolor={channel_data['metadata_color'].get()}:"
                f"box=1:"
                f"boxcolor=black@0.5:"
                f"boxborderw=8:"
                f"x=(w-text_w)/2:"
                f"y=(h-text_h)/2+{channel_data['metadata_position'].get()}"
            )
            filter_chains.append(metadata_filter)
            filter_indices['metadata'] = filter_counter
            filter_counter += 1
            # self.log_message(f"DEBUG: CH{channel_num} - Metadata filter index: {filter_indices['metadata']}", "buffer")
        
        # 3. Время (если включено)
        if channel_data['radio_show_time'].get():
            time_filter = (
                f"drawtext=text='%{{localtime\\:%X}}':"
                f"fontsize={channel_data['radio_time_size'].get()}:"
                f"fontcolor={channel_data['radio_time_color'].get()}:"
                f"box=1:"
                f"boxcolor=black@0.5:"
                f"boxborderw=8:"
                f"x=w-text_w-30:"
                f"y=30"
            )
            filter_chains.append(time_filter)
            filter_indices['time'] = filter_counter
            filter_counter += 1
            # self.log_message(f"DEBUG: CH{channel_num} - Time filter index: {filter_indices['time']}", "buffer")
        
        # Сохраняем индексы в данных канала
        channel_data['filter_indices'] = filter_indices
        # self.log_message(f"DEBUG: CH{channel_num} - Filter indices saved: {filter_indices}", "buffer")
        
        # Объединяем фильтры
        filter_complex = ','.join(filter_chains)
        
        # Строим команду
        cmd = f'"{ffmpeg_path}" -hwaccel auto -re '
        
        # Видео источник (фон)
        if bg_type == "Color":
            bg_color = channel_data['radio_bg_color'].get()
            cmd += f'-f lavfi -i "color={bg_color}:s={resolution}:r={fps}" '
            # self.log_message(f"DEBUG: CH{channel_num} - Background: Color {bg_color}", "buffer")
        else:  # Picture
            bg_picture = channel_data['radio_bg_picture'].get().strip()
            if bg_picture and os.path.exists(bg_picture):
                safe_path = os.path.abspath(bg_picture).replace('\\', '/')
                cmd += f'-loop 1 -framerate {fps} -i "{safe_path}" '
                # self.log_message(f"DEBUG: CH{channel_num} - Background: Picture {os.path.basename(bg_picture)}", "buffer")
            else:
                # Fallback на черный фон
                cmd += f'-f lavfi -i "color=black:s={resolution}:r={fps}" '
                # self.log_message(f"DEBUG: CH{channel_num} - Background: Fallback to black", "buffer")
        
        # Аудио источник (URL радио)
        url = channel_data['url_input'].get().strip()
        if url:
            cmd += f'-timeout 2000000 -i "{url}" '
            # self.log_message(f"DEBUG: CH{channel_num} - Audio URL: {url[:50]}...", "buffer")
        
        # Filter complex
        cmd += f'-filter_complex "[0:v]{filter_complex}[vout]" '
        # self.log_message(f"DEBUG: CH{channel_num} - Filter complex built", "buffer")
        
        # Получаем битрейты
        video_bitrate, audio_bitrate, _ = self.get_channel_bitrates()
        
        # Параметры кодирования
        codec = self.video_codec.get()
        preset = self.video_preset.get()
        
        cmd += f'-map "[vout]" -map 1:a? '
        cmd += f'-vcodec {codec} -preset {preset} '
        
        if codec == "libx265":
            cmd += f'-x265-params "bitrate={video_bitrate}:vbv-maxrate={video_bitrate}:vbv-bufsize={video_bitrate//2}" '
        else:
            cmd += f'-b:v {video_bitrate}k -minrate {video_bitrate}k -maxrate {video_bitrate}k -bufsize {video_bitrate//2}k '
        
        # Общие параметры
        cmd += f'-pix_fmt yuv420p -s {resolution} -g {self.video_gop.get()} -aspect 16:9 -r {fps} '
        cmd += f'-c:a {self.audio_codec.get()} -b:a {audio_bitrate} '
        cmd += f'-ar {self.audio_sample_rate.get()} -ac {self.get_audio_channels_ffmpeg()} '
        
        # Метаданные
        service_name = channel_data['name'].get() or f"Radio_{channel_num}"
        safe_name = service_name.replace('"', '\\"')
        cmd += f'-metadata service_provider="Radio Station" '
        cmd += f'-metadata service_name="{safe_name}" '
        
        # Выход
        cmd += f'-f mpegts -flush_packets 0 '
        cmd += f'"udp://@238.0.0.1:{output_port}?pkt_size=1316&fifo_size=500000&overrun_nonfatal=1"'
        # self.log_message(f"CH{channel_num} Radio CMD: {cmd}", "buffer")
        # self.log_message(f"DEBUG: CH{channel_num} - Command built successfully", "buffer")
        return cmd
       
    def restart_multiplexer(self):
        """Restart main multiplexer process"""
        if not self.is_streaming:
            return
        
        self.log_message("🔄 Restarting main multiplexer...", "buffer")
        
        # Убиваем старый процесс если есть
        if self.main_multiplexer_process:
            try:
                self.kill_process_fast(self.main_multiplexer_process, "Old multiplexer")
            except:
                pass
            self.main_multiplexer_process = None
        
        # Небольшая пауза
        time.sleep(1)
        
        # Запускаем новый
        self.start_main_multiplexer()

    def monitor_multiplexer_output(self):
        """Monitor main multiplexer output"""
        if not self.main_multiplexer_process:
            return
        
        critical_errors = [
            'Error during demuxing: I/O error',
            'Could not write header', 'sample rate not set', 'timeout',
            'buffer overflow', 'Circular buffer overrun', 'muxing failed', 'Invalid argument'
        ]
        
        try:
            for line in iter(self.main_multiplexer_process.stdout.readline, ''):
                if line and self.is_streaming:
                    line_stripped = line.strip()
                    
                    # Проверка на критические ошибки
                    error_detected = False
                    for error in critical_errors:
                        if error in line_stripped.lower():
                            error_detected = True
                            self.log_message(f"[Multiplexer] CRITICAL: {line_stripped[:200]}", "buffer")
                            break
                    
                    if error_detected:
                        # Перезапускаем мультиплексор
                        self.log_message("🔄 Restarting multiplexer due to error", "buffer")
                        self.restart_multiplexer()
                        return
                    
                    # Логирование обычных ошибок
                    if any(word in line_stripped.lower() for word in ['warning', 'deprecated']):
                        self.log_message(f"[Multiplexer] {line_stripped[:100]}", "buffer")
                    
                    # Парсинг статистики
                    if "bitrate=" in line_stripped:
                        match = re.search(r'bitrate=\s*([\d.]+)\s*kbits/s', line_stripped)
                        if match:
                            self.root.after(0, self.encoder_bitrate.set, match.group(1))
                    
                    if "speed=" in line_stripped:
                        match = re.search(r'speed=\s*([\d.]+)x', line_stripped)
                        if match:
                            self.root.after(0, self.encoder_speed.set, match.group(1))
                            self.root.after(0, self.update_speed_color)
                            # ⭐ ДОЛЖЕН БЫТЬ ВЫЗОВ check_system_speed
                            try:
                                speed = float(match.group(1))
                                self.root.after(0, self.check_system_speed, speed)
                            except:
                                pass
                                
        except Exception as e:
            if self.is_streaming:
                self.log_message(f"Multiplexer monitor error: {e}", "buffer")
        
        # Проверка, не упал ли процесс
        if self.main_multiplexer_process and self.main_multiplexer_process.poll() is not None:
            return_code = self.main_multiplexer_process.poll()
            if return_code != 0 and self.is_streaming:
                self.log_message(f"Multiplexer crashed with code {return_code}, restarting...", "buffer")
                self.restart_multiplexer()
                       
    def update_radio_metadata_new(self):
        """Простая версия - только логирование и планирование"""
        if not self.is_streaming:
            self.log_message("[METADATA] Not streaming, skipping", "buffer")
            return
        
        # Просто считаем радио-каналы
        radio_count = 0
        for ch_num, info in self.channel_processes.items():
            if info.get('is_radio'):
                radio_count += 1
        
        if radio_count > 0:
            # Запускаем обновление для каждого канала
            for ch_num, info in self.channel_processes.items():
                if info.get('is_radio'):
                    # ⚠️ ДОБАВЛЕНО: проверяем что канал ACTIVE
                    if self.channel_states.get(ch_num) == self.CHANNEL_STATE_ACTIVE:
                        # Запускаем в отдельном потоке
                        threading.Thread(
                            target=self.update_channel_metadata_simple,
                            args=(ch_num,),
                            daemon=True
                        ).start()
                    else:
                        self.log_message(f"[METADATA] CH{ch_num}: skipping (state={self.channel_states.get(ch_num)})", "buffer")
        
        # Планируем следующий цикл
        if self.is_streaming:
            next_time = 20000  # 20 секунд
            self.root.after(next_time, self.update_radio_metadata_new)

    def update_channel_metadata_simple(self, channel_num):
        """Обновление метаданных с динамическим размером текста (как в старом коде)"""

        try:
            # 1. Получаем данные канала
            channel_data = self.multiplex_channels.get(channel_num)
            if not channel_data:
                return

            # ⭐ Защита: только для URL_Input с радио
            if not (channel_data['source_type'].get() == "URL_Input" and channel_data['is_radio'].get()):
                return
            
            # 2. Проверяем, включены ли метаданные
            if not channel_data.get('show_metadata', True):
                return
            
            # 3. Получаем URL
            url = channel_data['url_input'].get().strip()
            if not url:

                return
            
            # 4. Парсим метаданные
            station, track = self.parse_metadata_from_url(url)
            
            if not station:
                station = channel_data['radio_text'].get() or "Radio Station"
            if not track:
                track = "No track info"
            
            display_text = f"{station} | {track}"
            
            # 5. Проверяем изменения
            last_key = f"last_metadata_ch{channel_num}"  # ← ИСПРАВЛЕНО: last_key, а не last_text_key
            last_text = getattr(self, last_key, "")
            
            if display_text == last_text:
                return  # Данные не изменились
            
            # 6. Получаем процесс и stdin
            if channel_num not in self.channel_processes:
                return
            
            process_info = self.channel_processes[channel_num]
            stdin = process_info.get('stdin')
            if not stdin:
                return
            
            # 7. Получаем индекс фильтра
            filter_indices = channel_data.get('filter_indices', {})
            metadata_idx = filter_indices.get('metadata')
            if metadata_idx is None:
                return
            
            # ⭐ 8. ЛОГИКА ИЗ СТАРОГО КОДА: АВТОМАТИЧЕСКИЙ ПОДБОР РАЗМЕРА ШРИФТА
            
            # Базовый размер шрифта из настроек
            try:
                base_fontsize = int(channel_data['metadata_size'].get())
            except:
                base_fontsize = 40  # Значение по умолчанию
            
            # 8.1. Ограничиваем длину текста если слишком длинный
            max_chars = 100  # Максимальная длина текста
            if len(display_text) > max_chars:
                # Обрезаем и добавляем многоточие
                # Стараемся обрезать по границе слова
                cutoff = display_text[:max_chars-3].rfind(' ')
                if cutoff > max_chars // 2:  # Если нашли хорошее место
                    display_text = display_text[:cutoff] + "..."
                else:
                    display_text = display_text[:max_chars-3] + "..."
            
            # 8.2. Подбираем размер шрифта в зависимости от длины текста
            text_length = len(display_text)
            
            if text_length > 100:
                fontsize = int(base_fontsize * 0.7)    # Уменьшаем на 30%
            elif text_length > 90:
                fontsize = int(base_fontsize * 0.75)   # Уменьшаем на 25%
            elif text_length > 80:
                fontsize = int(base_fontsize * 0.8)    # Уменьшаем на 20%
            elif text_length > 70:
                fontsize = int(base_fontsize * 0.85)   # Уменьшаем на 15%
            elif text_length > 60:
                fontsize = int(base_fontsize * 0.9)    # Уменьшаем на 10%
            else:
                fontsize = base_fontsize               # Оригинальный размер
            
            # Минимальный размер шрифта
            fontsize = max(fontsize, 20)
            # Максимальный размер (не больше оригинального)
            fontsize = min(fontsize, base_fontsize)
            
            # ⭐ 9. Экранируем специальные символы (как в старом коде)
            safe_text = display_text.replace("'", "'\\''").replace(':', '\\:')
            
            # ⭐ 10. ФОРМИРУЕМ КОМАНДУ С ПРАВИЛЬНЫМ СИНТАКСИСОМ
            # Как в старом коде: text='текст':fontsize=размер
            command = f"CParsed_drawtext_{metadata_idx} 0.0 reinit text='{safe_text}':fontsize={fontsize}\n"
            
            # 11. Отправляем команду
            try:
                stdin.write(command)
                stdin.flush()
                
                # Сохраняем последний отправленный текст
                setattr(self, last_key, display_text)  # ← Используем last_key
                
                # Логируем (как в старом коде)
                # self.log_message(
                    # f"Updated CH{channel_num} (filter {metadata_idx}, font {fontsize}px): {display_text[:60]}...",
                    # "buffer"
                # )
                
            except BrokenPipeError:
                self.log_message(f"FFmpeg process pipe closed for CH{channel_num}", "buffer")
            except Exception as e:
                if "I/O operation on closed file" in str(e):
                    self.log_message(f"FFmpeg stdin closed for CH{channel_num}", "buffer")
                else:
                    self.log_message(f"Error sending command to FFmpeg CH{channel_num}: {str(e)[:80]}", "buffer")
                    
        except Exception as e:
            self.log_message(f"Metadata update error CH{channel_num}: {str(e)[:100]}", "buffer")
                                                                     
    def update_ffmpeg_command_preview(self):
        """Update FFmpeg command preview"""
        try:
            cmd = self.build_ffmpeg_command()
            
            # Создаем окно предпросмотра
            preview_window = tk.Toplevel(self.root)
            preview_window.title("FFmpeg Command Preview")
            preview_window.geometry("900x500")
            
            # Фрейм для текста
            text_frame = ttk.Frame(preview_window)
            text_frame.pack(fill='both', expand=True, padx=10, pady=10)
            
            # Текстовая область с прокруткой
            text_widget = tk.Text(text_frame, wrap=tk.WORD, font=('Courier', 8))
            scrollbar = ttk.Scrollbar(text_frame, orient='vertical', command=text_widget.yview)
            text_widget.configure(yscrollcommand=scrollbar.set)
            
            text_widget.pack(side='left', fill='both', expand=True)
            scrollbar.pack(side='right', fill='y')
            
            # Вставляем команду
            text_widget.insert(1.0, cmd)
            
            # Кнопки
            btn_frame = ttk.Frame(preview_window)
            btn_frame.pack(fill='x', padx=10, pady=(0, 10))
            
            ttk.Button(btn_frame, text="Copy to Clipboard", 
                      command=lambda: self.copy_to_clipboard(cmd)).pack(side='left', padx=5)
            
            ttk.Button(btn_frame, text="Close", 
                      command=preview_window.destroy).pack(side='right', padx=5)
            
        except Exception as e:
            self.log_message(f"Error showing command preview: {e}", "buffer")
            messagebox.showerror("Error", f"Error building FFmpeg command:\n{str(e)}")
                
    def get_channel_bitrates(self):
        """Calculate VIDEO bitrate per channel based on active channel count with audio bitrate consideration"""
        
        # ПРОВЕРКА РЕЖИМА
        if not self.multiplex_mode.get():
            # SIMPLE РЕЖИМ (1 канал)
            try:
                # Получаем muxrate в kbps
                muxrate_kbps = float(self.muxrate.get()) / 1000
                
                # Резерв 10%
                reserve_kbps = muxrate_kbps * 0.1
                
                # Доступный битрейт после резерва
                available_bitrate = muxrate_kbps - reserve_kbps
                
                # Получаем аудиобитрейт в kbps
                audio_bitrate_str = self.audio_bitrate.get()
                if audio_bitrate_str.endswith('k'):
                    audio_bitrate_str = audio_bitrate_str[:-1]
                audio_bitrate_kbps = int(audio_bitrate_str)
                
                # Расчет видеобитрейта: muxrate - 10% - аудиобитрейт
                video_bitrate_calculated = int(available_bitrate - audio_bitrate_kbps)
                
                # Ограничения: только минимальное (100 kbps)
                # УБРАЛ ограничение по original_video_bitrate
                video_bitrate_calculated = max(100, video_bitrate_calculated)
                
                # Обновляем ВСЕ видеобитрейты
                self.video_bitrate.set(str(video_bitrate_calculated))
                
                # Auto-update bufsize
                self.on_video_bitrate_change()
                
                audio_bitrate_output = f"{audio_bitrate_kbps}k"
                
                # Логируем
                self.log_message(f"SIMPLE mode: Mux={muxrate_kbps:.1f}k, Audio={audio_bitrate_kbps}k, Video={video_bitrate_calculated}k", "buffer")
                
                return video_bitrate_calculated, audio_bitrate_output, 1
                
            except Exception as e:
                self.log_message(f"SIMPLE mode calc error: {e}", "buffer")
                return 1000, "128k", 1
        
        # МУЛЬТИПЛЕКС РЕЖИМ - оригинальный код
        # Считаем активные каналы
        active_count = 0
        for channel_data in self.multiplex_channels.values():
            if channel_data['enabled'].get():
                active_count += 1
        
        if active_count == 0:
            active_count = 1  # Хотя бы один канал
        
        try:
            # Получаем оригинальный видеобитрейт из настроек (в kbps)
            total_video_bitrate = int(self.video_bitrate.get())
            
            # Получаем аудиобитрейт (в kbps)
            audio_bitrate_str = self.audio_bitrate.get()
            # Конвертируем строку аудиобитрейта в число (убираем 'k' если есть)
            if audio_bitrate_str.endswith('k'):
                audio_bitrate_str = audio_bitrate_str[:-1]
            total_audio_bitrate_kbps = int(audio_bitrate_str)
            
            # 1. Рассчитываем общий доступный битрейт для видео (с учетом резерва 10%)
            try:
                muxrate_kbps = float(self.muxrate.get()) / 1000
                reserve_kbps = muxrate_kbps * 0.1  # 10% резерв
                available_total_bitrate = muxrate_kbps - reserve_kbps
            except:
                # Если muxrate недоступен, используем сумму видео+аудио
                available_total_bitrate = total_video_bitrate + (total_audio_bitrate_kbps * active_count)
            
            # 2. Расчет 1: Общий видео битрейт с учетом аудио для всех каналов
            # Общий аудио битрейт для всех активных каналов
            total_audio_for_all_channels = total_audio_bitrate_kbps * active_count
            
            # Доступный видео битрейт после вычета всего аудио
            available_video_after_audio = available_total_bitrate - total_audio_for_all_channels
            
            # 3. Расчет 2: Видео битрейт на канал (делим доступный видео битрейт на количество каналов)
            video_per_channel = int(available_video_after_audio // active_count)
            
            # 4. Альтернативный расчет для сравнения: из исходного видео битрейта
            # Вычитаем аудио битрейт для одного канала перед делением
            video_minus_one_audio = total_video_bitrate - total_audio_bitrate_kbps
            video_per_channel_alt = int(video_minus_one_audio // active_count)
            
            # 5. Выбираем минимальное значение для безопасности
            video_per_channel = min(video_per_channel, video_per_channel_alt, total_video_bitrate)
            
            # 6. Ограничиваем минимальные и максимальные значения
            # Минимум: 100 kbps для видео
            video_per_channel = max(100, video_per_channel)
            
            # Максимум: не больше исходного видео битрейт
            video_per_channel = min(total_video_bitrate, video_per_channel)
            
            # 7. Проверяем, что общий битрейт не превышает доступный
            total_required_bitrate = (video_per_channel * active_count) + (total_audio_bitrate_kbps * active_count)
            
            if total_required_bitrate > available_total_bitrate:
                # Если превышает, уменьшаем видео битрейт пропорционально
                video_per_channel = int((available_total_bitrate - (total_audio_bitrate_kbps * active_count)) // active_count)
                video_per_channel = max(100, video_per_channel)
            
            # 8. Формируем аудио битрейт строкой (возвращаем исходный формат)
            audio_bitrate_output = f"{total_audio_bitrate_kbps}k"
            
            # Update video bitrate
            self.video_bitrate.set(f"{int(available_video_after_audio)}")
            
            # Auto-update bufsize (bufsize = bitrate / 2)
            self.on_video_bitrate_change()
            
            # Логируем расчеты для отладки
            # self.log_message(f"MULTIPLEX mode calculation:", "buffer")
            # self.log_message(f"  Active channels: {active_count}", "buffer")
            # self.log_message(f"  Original video bitrate: {total_video_bitrate}k", "buffer")
            # self.log_message(f"  Audio bitrate per channel: {total_audio_bitrate_kbps}k", "buffer")
            # self.log_message(f"  Total audio for all channels: {total_audio_for_all_channels}k", "buffer")
            
            # if 'available_total_bitrate' in locals():
                # self.log_message(f"  Available total bitrate (after 10% reserve): {available_total_bitrate:.1f}k", "buffer")
                # self.log_message(f"  Available video after audio: {available_video_after_audio:.1f}k", "buffer")
                # self.log_message(f"  Total required bitrate: {total_required_bitrate:.1f}k", "buffer")
                # self.log_message(f"  Bitrate headroom: {available_total_bitrate - total_required_bitrate:.1f}k", "buffer")
            
            self.log_message(f"  Result: Video={video_per_channel}k per channel, Audio={audio_bitrate_output} per channel", "buffer")
            
            return video_per_channel, audio_bitrate_output, active_count
            
        except Exception as e:
            self.log_message(f"MULTIPLEX mode calc error: {e}", "buffer")
            import traceback
            traceback.print_exc()
            return 1000, "128k", 1  # Значения по умолчанию
        
    def get_video_encoding_params(self, bitrate_per_channel):
        """Get video encoding parameters based on codec"""
        codec = self.video_codec.get()
        preset = self.video_preset.get()
        tune = self.video_tune.get()
        
        params = f'-vcodec {codec} -preset {preset} '
        
        if tune:
            params += f'-tune {tune} '
        
        if codec == "libx265":
            params += f'-x265-params "bitrate={bitrate_per_channel}:vbv-maxrate={bitrate_per_channel}:vbv-bufsize={bitrate_per_channel//2}" '
        else:
            params += f'-b:v {bitrate_per_channel}k -minrate {bitrate_per_channel}k -maxrate {bitrate_per_channel}k -bufsize {bitrate_per_channel//2}k '
        
        params += f'-pix_fmt yuv420p -s {self.video_resolution.get()} -g {self.video_gop.get()} -aspect 16:9 -r {self.video_fps.get()} '
        
        return params

    def get_mpegts_output_params(self):
        """Get MPEG-TS output parameters EXACTLY as in the example"""
        return (
            f'-f mpegts -max_delay 300K -max_interleave_delta 4M '
            f'-muxdelay 0.1 -muxpreload 0.1 -pcr_period 40 '
            f'-pat_period 0.4 -sdt_period 0.5 '
            f'-mpegts_original_network_id 1 -mpegts_transport_stream_id 1 '
            f'-mpegts_pmt_start_pid 4096 -mpegts_start_pid 256 '
            f'-mpegts_flags system_b '
            f'-metadata service_provider="{self.service_provider.get()}" '
            f'-metadata service_name="{self.service_name.get()}" '
            f'-flush_packets 0 -muxrate {self.muxrate.get()} '
            f'"udp://{self.localhost_ip.get()}:{self.udp_input_port.get()}?pkt_size=1316&fifo_size=500000&overrun_nonfatal=1&burst_bits=1"'
        )
        
    def show_multiplex_ffmpeg_command(self):
        """Display the multiplex FFmpeg command"""
        try:
            # Получаем основную команду
            cmd = self.build_ffmpeg_command()
            
            # Собираем полный текст
            full_text = cmd + "\n\n" + "="*80 + "\n"
            full_text += "EMERGENCY STREAM COMMAND:\n"
            full_text += "="*80 + "\n\n"
            
            # 1. Основная emergency команда
            emergency_file = self.emergency_file_path.get()
            if emergency_file and os.path.exists(emergency_file):
                # Получаем битрейты
                video_bitrate, audio_bitrate, _ = self.get_channel_bitrates()
                
                ffmpeg_path = self.find_ffmpeg()
                safe_path = os.path.abspath(emergency_file).replace('\\', '/')
                
                emergency_cmd = f'"{ffmpeg_path}" -hwaccel auto -re -stream_loop -1 '
                emergency_cmd += f'-i "{safe_path}" '
                emergency_cmd += f'-vcodec {self.video_codec.get()} -preset {self.video_preset.get()} '
                
                if self.video_codec.get() == "libx265":
                    emergency_cmd += f'-x265-params "bitrate={video_bitrate}:vbv-maxrate={video_bitrate}:vbv-bufsize={video_bitrate//2}" '
                else:
                    emergency_cmd += f'-b:v {video_bitrate}k -minrate {video_bitrate}k -maxrate {video_bitrate}k -bufsize {video_bitrate//2}k '
                
                emergency_cmd += f'-pix_fmt yuv420p -s {self.video_resolution.get()} -g {self.video_gop.get()} -aspect 16:9 -r {self.video_fps.get()} '
                emergency_cmd += f'-c:a {self.audio_codec.get()} -b:a {audio_bitrate} '
                emergency_cmd += f'-ar {self.audio_sample_rate.get()} -ac {self.get_audio_channels_ffmpeg()} '
                emergency_cmd += f'-metadata service_provider="EMERGENCY" '
                emergency_cmd += f'-metadata service_name="Emergency Stream" '
                emergency_cmd += f'-f mpegts "{self.emergency_stream_url}?pkt_size=1316&fifo_size=500000&overrun_nonfatal=1"'
                
                full_text += emergency_cmd + "\n\n"
            else:
                full_text += "No emergency file configured or file not found\n"
                full_text += f"Current path: {emergency_file}\n\n"
            
            # # 2. EMERGENCY PROXY COMMANDS для каждого активного канала
            # full_text += "="*80 + "\n"
            # full_text += "EMERGENCY PROXY COMMANDS (for channel replacement):\n"
            # full_text += "="*80 + "\n\n"
            
            ffmpeg_path = self.find_ffmpeg()
            active_channels = 0
            
            for ch_num, channel_data in self.multiplex_channels.items():
                if not channel_data['enabled'].get():
                    continue
                    
                active_channels += 1
                output_port = self.base_multicast_port + ch_num - 1
                            
            # Создаем отдельное окно с полосой прокрутки
            cmd_window = tk.Toplevel(self.root)
            cmd_window.title("FFmpeg Commands (Main + Emergency)")
            cmd_window.geometry("900x700")  # Немного больше для длинных команд
            
            # Текстовая область с прокруткой
            text_frame = ttk.Frame(cmd_window)
            text_frame.pack(fill='both', expand=True, padx=10, pady=10)
            
            text_widget = tk.Text(text_frame, wrap=tk.WORD, font=('Courier', 9))
            scrollbar = ttk.Scrollbar(text_frame, orient='vertical', command=text_widget.yview)
            text_widget.configure(yscrollcommand=scrollbar.set)
            
            text_widget.pack(side='left', fill='both', expand=True)
            scrollbar.pack(side='right', fill='y')
            
            # Вставляем команду
            text_widget.insert(1.0, full_text)
            text_widget.configure(state='disabled')  # Только для чтения
            
            # Кнопка копирования
            copy_btn = ttk.Button(cmd_window, text="Copy to Clipboard", 
                                 command=lambda: self.copy_to_clipboard(full_text))
            copy_btn.pack(pady=(0, 10))
            
        except Exception as e:
            self.log_message(f"Error showing command: {e}", "buffer")
            messagebox.showerror("Error", f"Error building FFmpeg command:\n{str(e)}") 
            
    def browse_emergency_file(self):
        """Browse for emergency video file"""
        filename = filedialog.askopenfilename(
            title="Select emergency video file",
            filetypes=[
                ("Video files", "*.mp4 *.avi *.mkv *.mov *.flv *.ts *.m2ts *.m4v"),
                ("All files", "*.*")
            ]
        )
        
        if filename:
            print(f"DEBUG: Selected file: {filename}")
            print(f"DEBUG: Before set: '{self.emergency_file_path.get()}'")
            self.emergency_file_path.set(filename)
            print(f"DEBUG: After set: '{self.emergency_file_path.get()}'")
            self.save_config()
            print(f"DEBUG: Config saved")        
        
        if filename:
            self.emergency_file_path.set(filename)
            self.save_config()            

    def copy_to_clipboard(self, text):
        """Copy text to clipboard"""
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(text)
            messagebox.showinfo("Copied", "Command copied to clipboard!")
        except Exception as e:
            messagebox.showerror("Copy Error", f"Failed to copy to clipboard:\n{e}")   
        
    def quit_app(self):
        """Quit the application"""
        self.stop_streaming()
        self.stop_modulator()
        #self.stop_obs()  # Добавьте эту строку
        self.stop_overlay()
        self.save_config()
        self.root.quit()
        
def main():
    root = tk.Tk()
    app = DVBT2EncoderGUI(root)
    root.protocol("WM_DELETE_WINDOW", app.quit_app)
    root.mainloop()

if __name__ == "__main__":
    main()
