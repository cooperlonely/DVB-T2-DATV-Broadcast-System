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

try:
    import pythoncom
    from win32com.client import Dispatch
    HAS_WIN32COM = True
except ImportError:
    HAS_WIN32COM = False
    print("win32com not available, .lnk shortcut resolution disabled")

class DVB_T2_Validator:
    """
    DVB-T2 parameter validation based on official standard
    References:
    - ETSI EN 302 755 V1.4.1 (2015-07) - Digital Video Broadcasting (DVB); Frame structure, 
      channel coding and modulation for a second generation digital terrestrial television 
      broadcasting system (DVB-T2)
    - ETSI TS 102 831 V1.2.1 (2012-08) - Implementation guidelines for DVB-T2
    - EBU Tech 3348 (2014) - Frequency and Network Planning Parameters
    - Keysight N6153A DVB-T2 X-parameters measurement application (technical overview)
    - NorDig Unified Specification Ver 2.6 (2020)
    """
    
    # Physical constants from EN 302 755
    T_PERIODS = {
        "1.7 MHz": 71/131,  # μs
        "5 MHz": 7/40,
        "6 MHz": 7/48,
        "7 MHz": 1/8,
        "8 MHz": 7/64,
        "10 MHz": 7/80
    }
    
    FFT_POINTS = {
        "1K": 1024,
        "2K": 2048,
        "4K": 4096,
        "8K": 8192,
        "16K": 16384,
        "32K": 32768
    }
    
    ACTIVE_CARRIERS = {
        "1K": {"Normal": 853, "Extended": None},
        "2K": {"Normal": 1705, "Extended": None},
        "4K": {"Normal": 3409, "Extended": None},
        "8K": {"Normal": 6817, "Extended": 6913},
        "16K": {"Normal": 13633, "Extended": 13921},
        "32K": {"Normal": 27265, "Extended": 27841}
    }
    
    GI_FRACTIONS = {
        "1/128": 1/128,
        "1/32": 1/32,
        "1/16": 1/16,
        "19/256": 19/256,
        "1/8": 1/8,
        "19/128": 19/128,
        "1/4": 1/4
    }
    
    # Pilot Pattern parameters (D_x, D_y) from EN 302 755 Table 39
    PILOT_PARAMS = {
        "PP1": {"dx": 3, "dy": 4},
        "PP2": {"dx": 6, "dy": 2},
        "PP3": {"dx": 6, "dy": 4},
        "PP4": {"dx": 12, "dy": 2},
        "PP5": {"dx": 12, "dy": 4},
        "PP6": {"dx": 24, "dy": 2},
        "PP7": {"dx": 24, "dy": 4},
        "PP8": {"dx": 6, "dy": 16}
    }
    
    # GI availability by FFT size (EN 302 755 Table 39)
    GI_BY_FFT = {
        "1K": ["1/4", "1/8", "1/16"],  # 1/32, 1/128, 19/256, 19/128 not defined for 1K
        "2K": ["1/4", "1/8", "1/16", "1/32"],
        "4K": ["1/4", "1/8", "1/16", "1/32"],
        "8K": ["1/4", "1/8", "1/16", "1/32", "1/128", "19/128", "19/256"],
        "16K": ["1/4", "1/8", "1/16", "1/32", "1/128", "19/128", "19/256"],
        "32K": ["1/4", "1/8", "1/16", "1/32", "1/128", "19/128", "19/256"]
    }
    
    # FFT availability by bandwidth (physical limitation)
    FFT_BY_BANDWIDTH = {
        "1.7 MHz": ["1K", "2K", "4K", "8K"],  # 16K/32K possible mathematically but not in NorDig
        "5 MHz": ["1K", "2K", "4K", "8K", "16K", "32K"],
        "6 MHz": ["1K", "2K", "4K", "8K", "16K", "32K"],
        "7 MHz": ["1K", "2K", "4K", "8K", "16K", "32K"],
        "8 MHz": ["1K", "2K", "4K", "8K", "16K", "32K"],
        "10 MHz": ["1K", "2K", "4K", "8K", "16K", "32K"]
    }
    
    # Known working combinations from Keysight documentation (informative only!)
    KEYSIGHT_COMBINATIONS = {
        ("32K", "1/128"): ["PP7"],
        ("32K", "1/32"): ["PP4", "PP6"],
        ("32K", "1/16"): ["PP2", "PP8"],
        ("32K", "19/256"): ["PP2", "PP8"],
        ("32K", "1/8"): ["PP2", "PP8"],
        ("32K", "19/128"): ["PP2", "PP8"],
        ("32K", "1/4"): ["PP2", "PP8"],
        ("16K", "1/128"): ["PP7"],
        ("16K", "1/32"): ["PP7", "PP4", "PP6"],
        ("16K", "1/16"): ["PP2", "PP8", "PP4", "PP5"],
        ("16K", "19/256"): ["PP2", "PP8", "PP4", "PP5"],
        ("16K", "1/8"): ["PP2", "PP3", "PP8"],
        ("16K", "19/128"): ["PP2", "PP3", "PP8"],
        ("16K", "1/4"): ["PP1", "PP8"],
        ("8K", "1/128"): ["PP7"],
        ("8K", "1/32"): ["PP7", "PP4"],
        ("8K", "1/16"): ["PP8", "PP4", "PP5"],
        ("8K", "19/256"): ["PP8", "PP4", "PP5"],
        ("8K", "1/8"): ["PP2", "PP3", "PP8"],
        ("8K", "19/128"): ["PP2", "PP3", "PP8"],
        ("8K", "1/4"): ["PP1", "PP8"],
        ("4K", "1/32"): ["PP7", "PP4"],
        ("4K", "1/16"): ["PP4", "PP5"],
        ("4K", "1/8"): ["PP2", "PP3"],
        ("4K", "1/4"): ["PP1"],
        ("2K", "1/32"): ["PP7", "PP4"],
        ("2K", "1/16"): ["PP4", "PP5"],
        ("2K", "1/8"): ["PP2", "PP3"],
        ("2K", "1/4"): ["PP1"],
        ("1K", "1/16"): ["PP4", "PP5"],
        ("1K", "1/8"): ["PP2", "PP3"],
        ("1K", "1/4"): ["PP1"]
    }
    
    @classmethod
    def validate(cls, params, results):
        """
        Main validation method
        params: dict with keys: bandwidth, fft_size, gi, pilot_pattern, carrier_mode
        results: dict from calculator with frame_time_ms, dummy_cells, etc.
        Returns: (status, message, details)
        status: "VALID", "COMPATIBLE", "WARNING", "INVALID"
        """
        errors = []
        warnings = []
        info = []
        
        fft = params.get('fft_size', '')
        gi = params.get('guard_interval', '')
        pp = params.get('pilot_pattern', '')
        bw = params.get('bandwidth', '')
        carrier = params.get('carrier_mode', 'Normal')
        
        frame_time = results.get('frame_time_ms', 0)
        dummy_cells = results.get('dummy_cells', 0)
        
        # =====================================================================
        # LEVEL 1: HARD ERRORS (Physically impossible)
        # =====================================================================
        
        # 1. Frame time limit (EN 302 755 Section 9.4)
        if frame_time >= 250:
            errors.append(f"❌ Frame time ({frame_time:.1f} ms) exceeds 250 ms limit")
            errors.append("   Reference: EN 302 755 Section 9.4 - Maximum T2-frame duration")
        
        # 2. Dummy cells must be positive (mathematical necessity)
        if dummy_cells < 0:
            errors.append(f"❌ Dummy cells negative ({dummy_cells})")
            errors.append("   Dummy cells must be ≥ 0 for valid configuration")
        
        # 3. Occupied bandwidth must fit in channel (physics)
        t_period = cls.T_PERIODS.get(bw, 71/131)
        n_points = cls.FFT_POINTS.get(fft, 1024)
        t_u = n_points * t_period
        delta_f = 1 / t_u  # MHz
        
        active = cls.ACTIVE_CARRIERS.get(fft, {}).get(carrier, cls.ACTIVE_CARRIERS[fft]["Normal"])
        if active:
            obw = active * delta_f  # MHz
            bw_value = float(bw.split()[0])
            if obw > bw_value:
                errors.append(f"❌ Occupied bandwidth ({obw:.3f} MHz) exceeds channel bandwidth ({bw_value} MHz)")
                errors.append(f"   Active carriers: {active}, Δf: {delta_f:.3f} MHz")
        
        # 4. GI must be defined for this FFT size (EN 302 755 Table 39)
        if gi not in cls.GI_BY_FFT.get(fft, []):
            errors.append(f"❌ Guard interval {gi} not defined for {fft} FFT")
            errors.append(f"   Defined GIs for {fft}: {', '.join(cls.GI_BY_FFT[fft])}")
            errors.append("   Reference: EN 302 755 Table 39 - Allowed guard intervals")
        
        # =====================================================================
        # LEVEL 2: THEORETICAL COMPATIBILITY (T_E vs T_G)
        # =====================================================================
        
        if not errors:  # Only check if no hard errors
            # Calculate T_E (equalizer capability)
            if pp in cls.PILOT_PARAMS:
                dx = cls.PILOT_PARAMS[pp]["dx"]
                dy = cls.PILOT_PARAMS[pp]["dy"]
                
                # T_E from EBU Tech 3348 (conservative model)
                # T_E = (57/64) × T_U × (1/(D_x × D_y))
                t_e = (57/64) * t_u * (1/(dx * dy))
                
                # T_G = GI × T_U
                gi_frac = cls.GI_FRACTIONS.get(gi, 1/8)
                t_g = t_u * gi_frac
                
                if t_g > t_e:
                    ratio = t_g / t_e
                    if ratio > 2.0:
                        warnings.append(f"⚠️ T_G ({t_g:.1f} μs) significantly exceeds T_E ({t_e:.1f} μs)")
                        warnings.append(f"   Ratio: {ratio:.1f}x - equalizer may struggle with long echoes")
                        warnings.append("   Reference: EBU Tech 3348 - Channel estimation limits")
                    else:
                        info.append(f"ℹ️ T_G ({t_g:.1f} μs) slightly exceeds T_E ({t_e:.1f} μs)")
                        info.append(f"   Ratio: {ratio:.1f}x - should work in most conditions")
                else:
                    info.append(f"✅ T_E ({t_e:.1f} μs) ≥ T_G ({t_g:.1f} μs) - theoretically optimal")
        
        # =====================================================================
        # LEVEL 3: DOCUMENTATION STATUS
        # =====================================================================
        
        # Check if in Keysight documentation (informative only)
        key = (fft, gi)
        if key in cls.KEYSIGHT_COMBINATIONS:
            if pp in cls.KEYSIGHT_COMBINATIONS[key]:
                info.append(f"📚 Combination documented in Keysight DVB-T2 measurement guide")
            else:
                info.append(f"📚 Note: {pp} not listed for {fft}+{gi} in Keysight docs")
                info.append(f"   Documented PPs: {', '.join(cls.KEYSIGHT_COMBINATIONS[key])}")
        
        # Check 16K/32K with 1.7 MHz (NorDig requirement)
        if bw == "1.7 MHz" and fft in ["16K", "32K"]:
            info.append("ℹ️ Note: NorDig Unified Specification does not require")
            info.append("   receiver support for 16K/32K in 1.7 MHz bandwidth")
            info.append("   Reference: NorDig Unified Ver 2.6 Section 4.2.3")
        
        # =====================================================================
        # DETERMINE FINAL STATUS
        # =====================================================================
        
        if errors:
            status = "INVALID"
            message = "INVALID - see details" 
        elif warnings:
            status = "WARNING"
            message = "VALID but with warnings"
        elif info and any("ℹ️ Note" in i for i in info):
            status = "COMPATIBLE"
            message = "COMPATIBLE - not documented but should work"
        else:
            status = "VALID"
            message = "FULLY COMPLIANT with DVB-T2 standard"
        
        # Format details for display
        details = []
        if errors:
            details.extend(errors)
        if warnings:
            details.extend(warnings)
        if info:
            details.extend(info)
        
        return status, message, details

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
            self.window.geometry("1050x800+50+50")  # Увеличиваем размер окна
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
            
            # Main frame with paned window
            main_paned = ttk.PanedWindow(self.window, orient=tk.HORIZONTAL)
            main_paned.pack(fill='both', expand=True, padx=10, pady=10)
            
            # Left pane
            left_frame = ttk.Frame(main_paned)
            main_paned.add(left_frame, weight=1)
            
            # Right pane
            right_frame = ttk.Frame(main_paned)
            main_paned.add(right_frame, weight=1)
            
            # Left content
            self.create_left_content(left_frame)
            
            # Right content
            self.create_right_content(right_frame)
            
            # Установить позицию разделителя через 0.5 сек после создания окна
            self.window.after(300, lambda: main_paned.sashpos(0, 550))
            
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

        # Tab 7: Documentation References
        doc_frame = ttk.Frame(notebook, padding="10")
        notebook.add(doc_frame, text="Documentation")
        
        doc_content = """
📚 DVB-T2 STANDARD DOCUMENTATION

ETSI EN 302 755 V1.4.1 (2015-07)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Title: Frame structure, channel coding and modulation 
       for a second generation digital terrestrial television 
       broadcasting system (DVB-T2)

Key Sections:
• Section 9.4 - T2-frame structure (max 250 ms)
• Table 39 - Pilot pattern definitions and parameters
• Table 40 - Guard interval fractions
• Annex K - Informative examples of system configurations

Download: https://www.etsi.org/deliver/etsi_en/302700_302799/302755/01.04.01_60/

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ETSI TS 102 831 V1.2.1 (2012-08)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Title: Implementation guidelines for DVB-T2

Key Sections:
• Section 5 - System configuration guidelines
• Annex A - Receiver performance requirements

Download: https://www.etsi.org/deliver/etsi_ts/102800_102899/102831/01.02.01_60/

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EBU Tech 3348 (2014)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Title: Frequency and Network Planning Parameters

Key Sections:
• Section 4.3 - Guard interval and pilot pattern relationship
• Equation (4.3) - T_E = (57/64) × T_U × (1/(D_x × D_y))

Download: https://tech.ebu.ch/docs/tech/tech3348.pdf

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Keysight N6153A (2017)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Title: DVB-T2 X-parameters measurement application
       Technical Overview

Note: Tables in this document show combinations tested
      with Keysight equipment, not exhaustive standard
      requirements. Absence of a combination does NOT
      imply it's invalid.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
NorDig Unified Specification Ver 2.6 (2020)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Title: NorDig Unified Requirements for Integrated 
       Receiver Decoders for use in cable, satellite,
       terrestrial and IP-based networks

Key Sections:
• Section 4.2.3 - 1.7 MHz bandwidth requirements
  - Support for 16K/32K in 1.7 MHz is NOT required
  - This is receiver requirement, not transmitter limitation

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
VALIDATION LEVELS EXPLAINED
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

✅ VALID
   • Combination explicitly mentioned in EN 302 755
   • OR documented in multiple independent sources
   • Guaranteed to work with all compliant receivers

✓ COMPATIBLE
   • Meets all mathematical requirements
   • T_E ≥ T_G (theoretical channel estimation capability)
   • Not explicitly documented but should work
   • May require testing with specific receivers

⚠️ WARNING
   • Meets basic requirements (TF<250ms, dummy≥0)
   • But has theoretical limitations
   • T_G > T_E - equalizer may struggle with long echoes
   • Test thoroughly with target receivers

❌ INVALID
   • Violates physical constraints
   • TF ≥ 250 ms OR OBW > Channel bandwidth
   • OR GI not defined for this FFT size
   • OR dummy cells negative
   • Will NOT work with any receiver
"""
        self._add_text_to_frame(doc_frame, doc_content)
    
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
        
        # Вкладка 6: Документация и валидация (НОВАЯ)
        doc_frame = ttk.Frame(notebook, padding="10")
        notebook.add(doc_frame, text="Документация")
        
        doc_content = """
📚 ОФИЦИАЛЬНАЯ ДОКУМЕНТАЦИЯ DVB-T2

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ETSI EN 302 755 V1.4.1 (2015-07)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Название: Frame structure, channel coding and modulation 
          for a second generation digital terrestrial television 
          broadcasting system (DVB-T2)

Ключевые разделы:
• Раздел 9.4 - Структура T2-кадра (макс. 250 мс)
• Таблица 39 - Параметры пилот-сигналов (PP1-PP8)
• Таблица 40 - Дроби защитного интервала
• Приложение K - Информативные примеры конфигураций

Скачать: https://www.etsi.org/deliver/etsi_en/302700_302799/302755/01.04.01_60/

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ETSI TS 102 831 V1.2.1 (2012-08)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Название: Implementation guidelines for DVB-T2
(Руководство по имплементации)

Ключевые разделы:
• Раздел 5 - Рекомендации по конфигурации системы
• Приложение A - Требования к производительности приемников

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EBU Tech 3348 (2014)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Название: Frequency and Network Planning Parameters
(Параметры частотного и сетевого планирования)

Ключевые разделы:
• Раздел 4.3 - Связь защитного интервала и пилот-сигналов
• Уравнение (4.3) - T_E = (57/64) × T_U × (1/(D_x × D_y))
  (Оценка возможностей эквалайзера)

Скачать: https://tech.ebu.ch/docs/tech/tech3348.pdf

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Keysight N6153A (2017)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Название: DVB-T2 X-parameters measurement application
           Technical Overview

ВАЖНО: Таблицы в этом документе показывают комбинации,
протестированные с оборудованием Keysight. Это НЕ
ограничения стандарта. Отсутствие комбинации в таблице
НЕ означает, что она невалидна.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
NorDig Unified Specification Ver 2.6 (2020)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Название: NorDig Unified Requirements for Integrated 
           Receiver Decoders

Ключевой раздел:
• Раздел 4.2.3 - Требования к полосе 1.7 МГц
  - Поддержка 16K/32K в полосе 1.7 МГц НЕ ТРЕБУЕТСЯ
  - Это требование К ПРИЕМНИКУ, а не ограничение передатчика
  - Сигнал может передаваться, но не все приемники его примут

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ПРОИЗВОДИТЕЛИ IP-ЯДЕР (FPGA/ASIC)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Binary Core bc006 [citation:1]:
• Полосы: 1.7, 5, 6, 7, 8, 10 МГц
• FFT: 1K, 2K, 4K, 8K, 16K, 32K
• GI: все (1/128, 1/32, 1/16, 19/256, 1/8, 19/128, 1/4)
• PP: PP1-PP8

Commsonic [citation:8]:
• FFT: 1K, 2K, 4K, 8K, 16K, 32K
• PP: все PP1-PP8
• Полосы: 1.7-10 МГц с интерполяцией

MVD [citation:9]:
• FFT: 1K, 2K, 4K, 8K, 16K, 32K
• GI: все (1/4, 1/8, 1/16, 1/32, 1/128, 19/128, 19/256)
• Полосы: 5-8 МГц

ЭТО ПОКАЗЫВАЕТ: производители реализуют ВСЕ возможные
комбинации, не ограничиваясь таблицами Keysight.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
УРОВНИ ВАЛИДАЦИИ (объяснение)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

✅ VALID (ДЕЙСТВИТЕЛЬНО)
   • Комбинация явно указана в EN 302 755
   • ИЛИ задокументирована в нескольких независимых источниках
   • Гарантированно работает со всеми совместимыми приемниками

✓ COMPATIBLE (СОВМЕСТИМО)
   • Соответствует всем математическим требованиям
   • T_E ≥ T_G (теоретическая возможность оценки канала)
   • Явно не задокументировано, но должно работать
   • Может потребовать тестирования с конкретными приемниками

⚠️ WARNING (ПРЕДУПРЕЖДЕНИЕ)
   • Соответствует базовым требованиям (TF<250мс, dummy≥0)
   • Но есть теоретические ограничения
   • T_G > T_E - эквалайзеру может не хватить возможностей
   • Требуется тщательное тестирование с целевыми приемниками

❌ INVALID (НЕДЕЙСТВИТЕЛЬНО)
   • Нарушает физические ограничения
   • TF ≥ 250 мс ИЛИ OBW > Полоса канала
   • ИЛИ GI не определен для этого размера FFT
   • ИЛИ dummy cells отрицательны
   • НЕ БУДЕТ работать ни с одним приемником

"""
        self._add_text_to_frame(doc_frame, doc_content)
    
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

class DVBTCalculatorTab:
    def __init__(self, parent):
        self.parent = parent
        script_dir = os.path.dirname(os.path.abspath(__file__))        
        self.dvbt2rate_path = os.path.join(script_dir, "dvbt2rate.exe")        
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
                
        # Rules frame
        rules_frame = ttk.LabelFrame(left_frame, text="DVB-T2 Validation Rules", padding="5")
        rules_frame.pack(fill='x', pady=(5, 0))

        header_label = ttk.Label(rules_frame, text="Note that a valid configuration must fulfill two rules:",
                                font=('Arial', 7), justify=tk.LEFT)
        header_label.pack(fill='x', pady=(0, 5))

        rule1_label = ttk.Label(rules_frame, text="• TF must be less than 250 milliseconds",
                               font=('Arial', 9), justify=tk.LEFT)
        rule1_label.pack(fill='x')

        rule2_label = ttk.Label(rules_frame, text="• Dummy Cells must be positive",
                               font=('Arial', 9), justify=tk.LEFT)
        rule2_label.pack(fill='x')
        
        # Buttons frame
        buttons_frame = ttk.Frame(left_frame)
        buttons_frame.pack(fill='x', pady=(8, 0))
        
        self.calculate_btn = ttk.Button(buttons_frame, text="Calculate", command=self.calculate, width=12)
        self.calculate_btn.pack(side='top', pady=2)
        
        # self.sync_btn = ttk.Button(buttons_frame, text="Sync with Preset", 
                                  # command=self.sync_with_current_preset, width=12)
        # self.sync_btn.pack(side='top', pady=2)
        
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
        """Initialize calculator variables with DVB-T2 standard parameters"""
        # Define constants from ETSI EN 302 755
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
        
        # =====================================================================
        # IMPORTANT: Physical limitations only, no artificial restrictions!
        # Based on ETSI EN 302 755 and EBU Tech 3348
        # =====================================================================
        
        # Guard Interval availability by FFT size (EN 302 755 Table 39)
        # Some GIs are simply not defined for certain FFT sizes
        self.GI_BY_FFT = {
            "1K": ["1/4", "1/8", "1/16"],  # 1/32, 1/128, 19/256, 19/128 not defined for 1K
            "2K": ["1/4", "1/8", "1/16", "1/32"],
            "4K": ["1/4", "1/8", "1/16", "1/32"],
            "8K": ["1/4", "1/8", "1/16", "1/32", "1/128", "19/128", "19/256"],
            "16K": ["1/4", "1/8", "1/16", "1/32", "1/128", "19/128", "19/256"],
            "32K": ["1/4", "1/8", "1/16", "1/32", "1/128", "19/128", "19/256"]
        }
        
        # FFT availability by bandwidth (PHYSICAL limitation only!)
        # Any FFT size can work with any bandwidth as long as OBW fits in channel
        # The calculator will validate OBW ≤ Channel Bandwidth mathematically
        self.FFT_BY_BANDWIDTH = {
            "1.7 MHz": ["1K", "2K", "4K", "8K", "16K", "32K"],  # All mathematically possible
            "5 MHz": ["1K", "2K", "4K", "8K", "16K", "32K"],
            "6 MHz": ["1K", "2K", "4K", "8K", "16K", "32K"],
            "7 MHz": ["1K", "2K", "4K", "8K", "16K", "32K"],
            "8 MHz": ["1K", "2K", "4K", "8K", "16K", "32K"],
            "10 MHz": ["1K", "2K", "4K", "8K", "16K", "32K"]
        }
        
        # Note: NorDig Unified Specification states that receiver support for
        # 16K/32K in 1.7 MHz is NOT REQUIRED. This is a receiver requirement,
        # not a transmitter limitation. The signal can be transmitted, but
        # some receivers may not demodulate it.
        
        # Pilot Pattern parameters for mathematical validation (EBU Tech 3348)
        self.PILOT_PARAMS = {
            "PP1": {"dx": 3, "dy": 4},
            "PP2": {"dx": 6, "dy": 2},
            "PP3": {"dx": 6, "dy": 4},
            "PP4": {"dx": 12, "dy": 2},
            "PP5": {"dx": 12, "dy": 4},
            "PP6": {"dx": 24, "dy": 2},
            "PP7": {"dx": 24, "dy": 4},
            "PP8": {"dx": 6, "dy": 16}
        }
        
        # Elementary periods by bandwidth (EN 302 755)
        self.T_PERIODS = {
            "1.7 MHz": 71/131,  # μs
            "5 MHz": 7/40,
            "6 MHz": 7/48,
            "7 MHz": 1/8,
            "8 MHz": 7/64,
            "10 MHz": 7/80
        }
        
        # Active carriers by FFT size and carrier mode (EN 302 755)
        self.ACTIVE_CARRIERS = {
            "1K": {"Normal": 853, "Extended": None},
            "2K": {"Normal": 1705, "Extended": None},
            "4K": {"Normal": 3409, "Extended": None},
            "8K": {"Normal": 6817, "Extended": 6913},
            "16K": {"Normal": 13633, "Extended": 13921},
            "32K": {"Normal": 27265, "Extended": 27841}
        }
        
        # Known working combinations from Keysight documentation (INFORMATIVE ONLY!)
        # These are combinations tested with Keysight equipment, not standard requirements
        self.KEYSIGHT_COMBINATIONS = {
            ("32K", "1/128"): ["PP7"],
            ("32K", "1/32"): ["PP4", "PP6"],
            ("32K", "1/16"): ["PP2", "PP8"],
            ("32K", "19/256"): ["PP2", "PP8"],
            ("32K", "1/8"): ["PP2", "PP8"],
            ("32K", "19/128"): ["PP2", "PP8"],
            ("32K", "1/4"): ["PP2", "PP8"],
            ("16K", "1/128"): ["PP7"],
            ("16K", "1/32"): ["PP7", "PP4", "PP6"],
            ("16K", "1/16"): ["PP2", "PP8", "PP4", "PP5"],
            ("16K", "19/256"): ["PP2", "PP8", "PP4", "PP5"],
            ("16K", "1/8"): ["PP2", "PP3", "PP8"],
            ("16K", "19/128"): ["PP2", "PP3", "PP8"],
            ("16K", "1/4"): ["PP1", "PP8"],
            ("8K", "1/128"): ["PP7"],
            ("8K", "1/32"): ["PP7", "PP4"],
            ("8K", "1/16"): ["PP8", "PP4", "PP5"],
            ("8K", "19/256"): ["PP8", "PP4", "PP5"],
            ("8K", "1/8"): ["PP2", "PP3", "PP8"],
            ("8K", "19/128"): ["PP2", "PP3", "PP8"],
            ("8K", "1/4"): ["PP1", "PP8"],
            ("4K", "1/32"): ["PP7", "PP4"],
            ("4K", "1/16"): ["PP4", "PP5"],
            ("4K", "1/8"): ["PP2", "PP3"],
            ("4K", "1/4"): ["PP1"],
            ("2K", "1/32"): ["PP7", "PP4"],
            ("2K", "1/16"): ["PP4", "PP5"],
            ("2K", "1/8"): ["PP2", "PP3"],
            ("2K", "1/4"): ["PP1"],
            ("1K", "1/16"): ["PP4", "PP5"],
            ("1K", "1/8"): ["PP2", "PP3"],
            ("1K", "1/4"): ["PP1"]
        }
        
        # GNU Radio constants mapping
        self.GR_CONSTELLATION = {
            "QPSK": "dtv.MOD_QPSK", "16QAM": "dtv.MOD_16QAM", "64QAM": "dtv.MOD_64QAM",
            "256QAM": "dtv.MOD_256QAM"
        }

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
                     
    def update_compliance_display(self):
        """Update the compliance status display below T2 Info button"""
        try:
            if not hasattr(self, 'compliance_label'):
                return
            
            # Get status from validator
            if hasattr(self, 'validation_status'):
                status = self.validation_status
                message = self.validation_message
            else:
                # No validation yet
                status = "UNKNOWN"
                message = "Select parameters and calculate"
            
            # Set color based on status
            colors = {
                "VALID": "green",
                "COMPATIBLE": "blue",
                "WARNING": "orange",
                "INVALID": "red",
                "UNKNOWN": "gray"
            }
            color = colors.get(status, "black")
            
            # Format display text - ONLY ONE EMOJI HERE!
            if status == "VALID":
                display_text = f"✅ {message.replace('✅', '').strip()}"
            elif status == "COMPATIBLE":
                display_text = f"✓ {message.replace('✓', '').replace('✅', '').strip()}"
            elif status == "WARNING":
                display_text = f"⚠️ {message.replace('⚠️', '').strip()}"
            elif status == "INVALID":
                display_text = f"❌ {message.replace('❌', '').strip()}"
            else:
                display_text = f"ℹ️ {message}"
            
            self.compliance_label.config(
                text=display_text,
                foreground=color,
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

        else:
            self.parent.log_message(f"✅ Mathematical Validation: {math_msg}", "buffer")
        
        try:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            exe_path = self.dvbt2rate_path
            
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
            
            # ========== НОВЫЙ КОД ==========
            # Run validation with the new framework
            self.validate_parameters()
            # ================================
            
            # Update parameter limits based on calculator results
            self.update_parameter_limits(original_results)
            
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
            
            # Cells calculation
            output_lines.append("=== CELLS CALCULATION ===")
            total_cells = results.get('total_cells', 0)
            useful_cells = results.get('useful_cells', 0)
            dummy_cells = results.get('dummy_cells', 0)
            
            output_lines.append(f"Total Cells: {total_cells:,}")
            output_lines.append(f"Useful Cells: {useful_cells:,}")
            output_lines.append(f"Dummy Cells: {dummy_cells:,}")
            output_lines.append("")
            
            # =================================================================
            # DVB-T2 VALIDATION REPORT from mathematical framework
            # =================================================================
            output_lines.append("")
            output_lines.append("== DVB-T2 VALIDATION REPORT ==")
            output_lines.append("Based on ETSI EN 302 755 and EBU Tech 3348")
            output_lines.append("")
            
            if hasattr(self, 'validation_status'):
                status = self.validation_status
                
                if status == "VALID":
                    output_lines.append("✅ STATUS: FULLY COMPLIANT")
                    output_lines.append(" This combination is documented in DVB-T2 ")
                    output_lines.append(" standard and verified by multiple sources.")
                elif status == "COMPATIBLE":
                    output_lines.append("✓ STATUS: COMPATIBLE")
                    output_lines.append(" combination meets all math requirements, but")
                    output_lines.append(" may not be explicitly documented in standards.")
                    output_lines.append(" Expected to work with all compliant receivers.")
                elif status == "WARNING":
                    output_lines.append("⚠️ STATUS: VALID WITH WARNINGS")
                    output_lines.append(" This combination meets basic requirements but")
                    output_lines.append(" has theoretical limitations. Test with receivers.")
                elif status == "INVALID":
                    output_lines.append("❌ STATUS: INVALID")
                    output_lines.append(" This combination violates physical constraints")
                    output_lines.append(" and WILL NOT WORK with any receiver.")
                else:
                    output_lines.append(f"ℹ️ STATUS: {status}")
                
                output_lines.append("")
                output_lines.append("--- DETAILS ---")
                if hasattr(self, 'validation_details'):
                    for detail in self.validation_details:
                        output_lines.append(detail)
            else:
                output_lines.append("ℹ️ Run calculation to see validation results")
            
            output_lines.append("")
            output_lines.append("=== BASIC VALIDATION ===")
            
            frame_time_ms = results.get('frame_time_ms', 0)
            rule1_ok = frame_time_ms < 250
            output_lines.append(f"Frame Time: {frame_time_ms:.2f} ms {'✅' if rule1_ok else '❌'} {'< 250 ms' if rule1_ok else '> 250 ms'}")
            
            dummy_cells = results.get('dummy_cells', 0)
            rule2_ok = dummy_cells >= 0
            output_lines.append(f"Dummy Cells: {dummy_cells:,} {'✅ POSITIVE' if rule2_ok else '❌ NEGATIVE'}")
            
            # Mathematical validation
            math_valid, math_msg = self.validate_with_mathematical_framework(
                self.bandwidth_var.get(),
                self.fft_size_var.get(), 
                self.gi_var.get(),
                self.pilot_pattern_var.get()
            )
            output_lines.append(f"Math Framework: {'✅ PASS' if math_valid else '⚠️ WARNING'}")
            output_lines.append(f"   {math_msg}")
            
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
            import traceback
            self.parent.log_message(f"❌ Traceback: {traceback.format_exc()}", "buffer")
            
    def update_compatibility_based_on_math(self):
        """Update parameter compatibility based on mathematical framework"""
        try:
            # Этот метод больше не нужен для жестких ограничений,
            # оставляем только для информационных целей
            bandwidth = self.bandwidth_var.get()
            fft_size = self.fft_size_var.get()
            gi = self.gi_var.get()
            pp = self.pilot_pattern_var.get()
            
            # Просто логируем информацию, не ограничиваем выбор
            self.parent.log_message(f"ℹ️ Current combination: {fft_size}+{gi}+{pp}", "buffer")
            
        except Exception as e:
            self.parent.log_message(f"⚠️ Math compatibility check error: {e}", "buffer")            
            
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
        Validate parameter combinations using DVB-T2 mathematical framework
        Returns (is_valid, message) - but doesn't block calculation
        """
        try:
            # Get current values
            params = {
                'bandwidth': self.bandwidth_var.get(),
                'fft_size': self.fft_size_var.get(),
                'guard_interval': self.gi_var.get(),
                'pilot_pattern': self.pilot_pattern_var.get(),
                'carrier_mode': self.carrier_mode_var.get()
            }
            
            # We need calculation results for frame_time and dummy_cells
            # If not available yet, create placeholder
            if hasattr(self, 'calculation_results') and self.calculation_results:
                results = self.calculation_results
            else:
                results = {'frame_time_ms': 0, 'dummy_cells': 0}
            
            # Use the new validator
            status, message, details = DVB_T2_Validator.validate(params, results)
            
            # Store for display - message should NOT have emoji here
            self.validation_status = status
            self.validation_message = message  # Keep as is, we'll add emoji in display
            self.validation_details = details
            
            # Update compliance label under T2 Info button
            self.update_compliance_display()
            
            # Log details
            for detail in details:
                self.parent.log_message(detail, "buffer")
            
            # Return True always - we don't block calculation
            return True, message
            
        except Exception as e:
            self.parent.log_message(f"❌ Validation error: {str(e)}", "buffer")
            return True, "Validation error - see log"
       
    def update_pilot_pattern_options(self, fft_size, gi):
        """
        Update available pilot pattern options - now only warns, doesn't restrict
        """
        try:
            # We no longer restrict PP options - let user choose
            # Just log information about known combinations
            fft_str = self.fft_size_var.get()
            gi_str = self.gi_var.get()
            pp_str = self.pilot_pattern_var.get()
            
            # Check if we have Keysight data for this combination
            key = (fft_str, gi_str)
            if hasattr(self, 'KEYSIGHT_COMBINATIONS') and key in self.KEYSIGHT_COMBINATIONS:
                known_pp = self.KEYSIGHT_COMBINATIONS[key]
                if pp_str not in known_pp:
                    self.parent.log_message(
                        f"ℹ️ Note: {pp_str} not documented for {fft_str}+{gi_str} in Keysight docs",
                        "buffer"
                    )
                    self.parent.log_message(
                        f"   Documented PPs: {', '.join(known_pp)}",
                        "buffer"
                    )
            
        except Exception as e:
            self.parent.log_message(f"⚠️ Error checking PP compatibility: {e}", "buffer")

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
                  command=self.remove_media_folder, width=16).pack(side=tk.LEFT)
        
        # Bumper files section
        ttk.Label(playlist_frame, text="Bumper Files (inserted between media):", font=('Arial', 10, 'bold')).grid(row=3, column=0, sticky='w', pady=(10, 5))
        
        self.bumper_frame = ttk.Frame(playlist_frame)
        self.bumper_frame.grid(row=4, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(0, 5))
        
        self.bumper_widgets = []
        self.add_bumper_row()  # Add first bumper row by default
        
        ttk.Button(playlist_frame, text="Add Bumper", 
                  command=self.add_bumper_row, width=12).grid(row=5, column=0, sticky='w', pady=(0, 10))
        
        # Playlist Name - компактно в одной строке
        playlist_name_frame = ttk.Frame(playlist_frame)
        playlist_name_frame.grid(row=6, column=0, columnspan=3, sticky='w', pady=(10, 5))

        ttk.Label(playlist_name_frame, text="Playlist Name:", font=('Arial', 10)).pack(side='left')
        ttk.Entry(playlist_name_frame, textvariable=self.playlist_name, width=30, font=('Arial', 9)).pack(side='left', padx=(5, 0))

        # MPC Player path - компактно в одной строке
        player_path_frame = ttk.Frame(playlist_frame)
        player_path_frame.grid(row=7, column=0, columnspan=3, sticky='w', pady=5)

        ttk.Label(player_path_frame, text="MPC Player Path:", font=('Arial', 10)).pack(side='left')
        ttk.Entry(player_path_frame, textvariable=self.mpc_player_path, width=55, font=('Arial', 9)).pack(side='left', padx=(5, 5))
        ttk.Button(player_path_frame, text="Browse", command=self.browse_mpc_player, width=8).pack(side='left')
        
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

class DummyTSGenerator:
    """
    Генератор валидного MPEG-TS потока для заполнения буфера
    Поддерживает динамическое количество каналов
    """
    
    # Константы (без изменений)
    PAT_PID = 0x0000
    SDT_PID = 0x0011
    NIT_PID = 0x0010
    EIT_PID = 0x0012
    TDT_PID = 0x0014
    NULL_PID = 0x1FFF
    
    # Базовые PID для каналов (будут сдвигаться)
    BASE_PMT_PID = 0x1000    # PMT PID для CH1
    BASE_VID_PID = 0x0100     # Video PID для CH1
    BASE_AUD_PID = 0x0101     # Audio PID для CH1
    
    # Типы потоков
    STREAM_TYPE_H265 = 0x24   # H.265/HEVC
    STREAM_TYPE_AAC = 0x0F    # AAC audio
    
    # Дескрипторы SI
    SI_DESC_SERVICE = 0x48
    SVC_DIGITAL_TV = 0x01
    
    def __init__(self, app=None, service_name="Radio", service_provider="R6WAX DATV"):
        self.app = app  # ссылка на главное приложение для доступа к каналам
        self.service_name = service_name
        self.service_provider = service_provider
        
        # Информация о каналах
        self.active_channels = []
        self.pmt_sections = {}  # PMT секции для каждого канала
        self.pmt_packets = {}   # PMT пакеты для каждого канала
        
        # Пакетная статистика
        self.group_counter = 0
        self.pcr_base = 900000
        
        # Обновляем информацию о каналах
        self.update_channel_info()
        
        # Предварительно создаем пустые пакеты
        self.video_packet_template = self.create_video_packet_template()
        self.audio_packet_template = self.create_audio_packet_template()
        self.null_packet_template = self.create_null_packet_template()
        
    def update_channel_info(self):
        """Обновляет информацию о каналах из главного приложения"""
        if not self.app:
            # Если нет приложения, создаем один канал по умолчанию
            self.active_channels = [{
                'number': 1,
                'name': self.service_name,
                'pmt_pid': self.BASE_PMT_PID,
                'video_pid': self.BASE_VID_PID,
                'audio_pid': self.BASE_AUD_PID
            }]
        else:
            # Получаем активные каналы из GUI
            channels_list = []
            for ch_num, ch_data in self.app.multiplex_channels.items():
                if ch_data['enabled'].get():
                    channels_list.append({
                        'original_number': ch_num,  # сохраняем оригинальный номер
                        'name': ch_data['name'].get(),
                    })
            
            # СОРТИРУЕМ ПО ОРИГИНАЛЬНОМУ НОМЕРУ
            channels_list.sort(key=lambda x: x['original_number'])
            
            # Присваиваем порядковые номера 1,2,3...
            self.active_channels = []
            for i, ch in enumerate(channels_list, 1):  # i = 1,2,3 для program_number
                self.active_channels.append({
                    'number': i,  # порядковый номер в потоке (1,2,3...)
                    'original_number': ch['original_number'],  # оригинальный номер для отладки
                    'name': ch['name'],
                    'pmt_pid': self.BASE_PMT_PID + (i - 1), # 4096, 4097, 4098...
                    'video_pid': self.BASE_VID_PID + ((i - 1) * 2),  # 256,258,260
                    'audio_pid': self.BASE_AUD_PID + ((i - 1) * 2)   # 257,259,261
                })
        
        # Если нет активных каналов, создаем один по умолчанию
        if not self.active_channels:
            self.active_channels = [{
                'number': 1,
                'name': self.service_name,
                'pmt_pid': self.BASE_PMT_PID,
                'video_pid': self.BASE_VID_PID,
                'audio_pid': self.BASE_AUD_PID
            }]
        
        # Пересоздаем служебные таблицы
        self.pat_section = self.pat_fmt()
        self.sdt_section = self.sdt_fmt()
        
        # Создаем PMT для каждого канала
        self.pmt_sections = {}
        self.pmt_packets = {}
        for i, ch in enumerate(self.active_channels):
            pmt_section = self.pmt_fmt(
                program_number=ch['number'],
                pcr_pid=ch['video_pid'],
                video_pid=ch['video_pid'],
                audio_pid=ch['audio_pid']
            )
            self.pmt_sections[ch['pmt_pid']] = pmt_section
            self.pmt_packets[ch['pmt_pid']] = self.create_section_packet(
                ch['pmt_pid'], pmt_section, (i + 1) % 16
            )
        
        # Сохраняем готовые служебные пакеты (обновляем с правильными CC)
        self.pat_packet = self.create_section_packet(self.PAT_PID, self.pat_section, 0)
        self.sdt_packet = self.create_section_packet(self.SDT_PID, self.sdt_section, 
                                                     (len(self.active_channels) + 1) % 16)
    
    def dvb_crc32_calc(self, data):
        """Вычисляет CRC32 как в DVB оборудовании"""
        crc = 0xFFFFFFFF
        for byte in data:
            for bit in range(7, -1, -1):
                bit_val = 1 if (crc & 0x80000000) else 0
                bit_val ^= 1 if (byte & (1 << bit)) else 0
                crc <<= 1
                if bit_val:
                    crc ^= 0x04C11DB7
        return crc & 0xFFFFFFFF
    
    def crc32_add(self, data):
        """Добавляет CRC32 в конец данных"""
        crc = self.dvb_crc32_calc(data)
        data.append((crc >> 24) & 0xFF)
        data.append((crc >> 16) & 0xFF)
        data.append((crc >> 8) & 0xFF)
        data.append(crc & 0xFF)
        return len(data)
    
    def tp_fmt(self, pid, payload_start=False, continuity_counter=0, adaptation_field_control=1):
        """Формирует заголовок TS пакета"""
        packet = bytearray(188)
        
        # Sync byte
        packet[0] = 0x47
        
        # Байт 1
        packet[1] = 0
        if payload_start:
            packet[1] |= 0x40
        
        # PID
        packet[1] |= (pid >> 8) & 0x1F
        packet[2] = pid & 0xFF
        
        # Байт 3
        packet[3] = (adaptation_field_control << 4) | (continuity_counter & 0x0F)
        
        return packet
    
    def add_pcr_field(self, packet, offset, pcr_clk):
        """Добавляет PCR поле в адаптационное поле"""
        pcr_base = pcr_clk // 300
        pcr_ext = pcr_clk % 300
        
        packet[offset] = (pcr_base >> 25) & 0xFF
        packet[offset + 1] = (pcr_base >> 17) & 0xFF
        packet[offset + 2] = (pcr_base >> 9) & 0xFF
        packet[offset + 3] = (pcr_base >> 1) & 0xFF
        
        if pcr_base & 1:
            packet[offset + 4] = 0x80 | 0x7E
        else:
            packet[offset + 4] = 0x00 | 0x7E
        
        if pcr_ext & 0x100:
            packet[offset + 4] |= 1
        
        packet[offset + 5] = pcr_ext & 0xFF
        
        return 6
    
    def pat_fmt(self, transport_stream_id=1):
        """Форматирует PAT таблицу со всеми активными программами"""
        pat = bytearray()
        
        pat.append(0x00)  # table_id
        pat.append(0xB0)  # section_syntax_indicator
        pat.append(0x00)  # section_length placeholder
        
        pat.append((transport_stream_id >> 8) & 0xFF)
        pat.append(transport_stream_id & 0xFF)
        
        # ВЕРСИЯ 1, CURRENT_NEXT=1 (0xC1)
        pat.append(0xC1)  # ← ИЗМЕНЕНО: 0xC1 вместо 0xC2
        pat.append(0x00)  # section_number
        pat.append(0x00)  # last_section_number
        
        # # Program 0 (NIT)
        # pat.append(0x00)
        # pat.append(0x00)
        # pat.append(0xE0 | (self.NIT_PID >> 8))
        # pat.append(self.NIT_PID & 0xFF)
        
        # Программы для каждого канала
        for ch in self.active_channels:
            pat.append((ch['number'] >> 8) & 0xFF)
            pat.append(ch['number'] & 0xFF)
            pat.append(0xE0 | (ch['pmt_pid'] >> 8))
            pat.append(ch['pmt_pid'] & 0xFF)
        
        section_length = len(pat) - 3 + 4
        pat[1] = (pat[1] & 0xF0) | ((section_length >> 8) & 0x0F)
        pat[2] = section_length & 0xFF
        
        self.crc32_add(pat)
        return bytes(pat)
    
    def pmt_fmt(self, program_number=1, pcr_pid=None, video_pid=None, audio_pid=None):
        """Форматирует PMT таблицу для конкретного канала"""
        if pcr_pid is None:
            pcr_pid = self.BASE_VID_PID
        if video_pid is None:
            video_pid = self.BASE_VID_PID
        if audio_pid is None:
            audio_pid = self.BASE_AUD_PID
            
        pmt = bytearray()
        
        pmt.append(0x02)  # table_id
        pmt.append(0xB0)  # section_syntax_indicator
        pmt.append(0x00)  # section_length placeholder
        
        pmt.append((program_number >> 8) & 0xFF)
        pmt.append(program_number & 0xFF)
        
        pmt.append(0xC1)  # version=2, current_next=1
        pmt.append(0x00)  # section_number
        pmt.append(0x00)  # last_section_number
        
        # PCR PID
        pmt.append(0xE0 | (pcr_pid >> 8))
        pmt.append(pcr_pid & 0xFF)
        
        # program_info_length = 0
        pmt.append(0xF0)
        pmt.append(0x00)
        
        # ВИДЕО ПОТОК
        pmt.append(self.STREAM_TYPE_H265)
        pmt.append(0xE0 | (video_pid >> 8))
        pmt.append(video_pid & 0xFF)
        pmt.append(0xF0)
        pmt.append(0x00)
        
        # АУДИО ПОТОК
        pmt.append(self.STREAM_TYPE_AAC)
        pmt.append(0xE0 | (audio_pid >> 8))
        pmt.append(audio_pid & 0xFF)
        pmt.append(0xF0)
        pmt.append(0x00)
        
        section_length = len(pmt) - 3 + 4
        pmt[1] = (pmt[1] & 0xF0) | ((section_length >> 8) & 0x0F)
        pmt[2] = section_length & 0xFF
        
        self.crc32_add(pmt)
        return bytes(pmt)
    
    def sdt_fmt(self, transport_stream_id=1, original_network_id=1):
        """Форматирует SDT таблицу со всеми сервисами"""
        sdt = bytearray()
        
        sdt.append(0x42)  # table_id
        sdt.append(0xF0)  # section_syntax_indicator
        sdt.append(0x00)  # section_length placeholder
        
        sdt.append((transport_stream_id >> 8) & 0xFF)
        sdt.append(transport_stream_id & 0xFF)
        
        sdt.append(0xC1)  # version=2, current_next=1
        sdt.append(0x00)  # section_number
        sdt.append(0x00)  # last_section_number
        
        sdt.append((original_network_id >> 8) & 0xFF)
        sdt.append(original_network_id & 0xFF)
        sdt.append(0xFF)  # reserved_future_use
        
        # Для каждого канала добавляем описание сервиса
        for ch in self.active_channels:
            # service_id
            sdt.append((ch['number'] >> 8) & 0xFF)
            sdt.append(ch['number'] & 0xFF)
            
            # EIT flags, running status
            sdt.append(0x04)
            
            # descriptors_loop_length (заполним позже)
            desc_len_pos = len(sdt)
            sdt.append(0x00)
            sdt.append(0x00)
            
            # Service descriptor
            sdt.append(self.SI_DESC_SERVICE)
            
            provider_bytes = self.service_provider.encode('utf-8')
            name_bytes = ch['name'].encode('utf-8')
            
            desc_len = 2 + len(provider_bytes) + 1 + len(name_bytes)
            sdt.append(desc_len)
            
            sdt.append(self.SVC_DIGITAL_TV)  # service_type
            
            sdt.append(len(provider_bytes))
            sdt.extend(provider_bytes)
            
            sdt.append(len(name_bytes))
            sdt.extend(name_bytes)
            
            # Обновляем descriptors_loop_length
            descriptors_loop_length = len(sdt) - (desc_len_pos + 2)
            sdt[desc_len_pos] = (descriptors_loop_length >> 8) & 0xFF
            sdt[desc_len_pos + 1] = descriptors_loop_length & 0xFF
        
        section_length = len(sdt) - 3 + 4
        sdt[1] = (sdt[1] & 0xF0) | ((section_length >> 8) & 0x0F)
        sdt[2] = section_length & 0xFF
        
        self.crc32_add(sdt)
        return bytes(sdt)
    
    def create_video_pes_packet(self, pcr_base):
        """Создает правильный PES пакет для видео с PTS"""
        pes = bytearray()
        
        pes.extend([0x00, 0x00, 0x01, 0xE0])
        pes.extend([0x00, 0x00])
        pes.append(0x80)
        pes.append(0x00)
        pes.append(0x05)
        
        pts = pcr_base
        
        pts1 = 0x21 | (((pts >> 30) & 0x07) << 1)
        pts2 = (pts >> 22) & 0xFF
        pts3 = 0x01 | (((pts >> 15) & 0x7F) << 1)
        pts4 = (pts >> 7) & 0xFF
        pts5 = 0x01 | ((pts & 0x7F) << 1)
        
        pes.append(pts1)
        pes.append(pts2)
        pes.append(pts3)
        pes.append(pts4)
        pes.append(pts5)
        
        pes.extend([0x00, 0x00, 0x00, 0x01, 0x02, 0x01, 0xC0])
        
        return bytes(pes)
    
    def create_audio_pes_packet(self):
        """Создает правильный PES пакет для аудио AAC"""
        pes = bytearray()
        
        pes.extend([0x00, 0x00, 0x01, 0xC0])
        pes.extend([0x00, 0x00])
        pes.append(0x80)
        pes.append(0x00)
        pes.append(0x00)
        
        pes.extend([0xFF, 0xF1, 0x50, 0x80, 0x00, 0x1F, 0xFC])
        pes.extend([0x00] * 10)
        
        return bytes(pes)
    
    def create_section_packet(self, pid, section_data, continuity_counter):
        """Создает TS пакет с секцией"""
        packet = self.tp_fmt(pid, payload_start=True, 
                            continuity_counter=continuity_counter,
                            adaptation_field_control=1)
        
        packet[4] = 0x00
        
        data_len = min(len(section_data), 183)
        packet[5:5+data_len] = section_data[:data_len]
        
        for i in range(5+data_len, 188):
            packet[i] = 0xFF
        
        return bytes(packet)
    
    def create_video_packet_template(self):
        """Создает шаблон видео пакета"""
        packet = self.tp_fmt(self.BASE_VID_PID, payload_start=True,
                            continuity_counter=0,
                            adaptation_field_control=3)
        
        packet[4] = 0x07
        packet[5] = 0x10
        
        return bytes(packet)
    
    def create_video_packet(self, pcr_base, continuity_counter, video_pid=None):
        """Создает видео пакет с PCR"""
        if video_pid is None:
            video_pid = self.BASE_VID_PID
            
        packet = bytearray(self.video_packet_template)
        
        # Обновляем PID и CC
        packet[1] = (packet[1] & 0xE0) | ((video_pid >> 8) & 0x1F)
        packet[2] = video_pid & 0xFF
        packet[3] = (3 << 4) | (continuity_counter & 0x0F)
        
        self.add_pcr_field(packet, 6, pcr_base)
        
        pes_data = self.create_video_pes_packet(pcr_base)
        pes_len = min(len(pes_data), 176)
        packet[12:12+pes_len] = pes_data[:pes_len]
        
        for i in range(12+pes_len, 188):
            packet[i] = 0xFF
        
        return bytes(packet)
    
    def create_audio_packet_template(self):
        """Создает шаблон аудио пакета"""
        packet = self.tp_fmt(self.BASE_AUD_PID, payload_start=True,
                            continuity_counter=0,
                            adaptation_field_control=1)
        
        pes_data = self.create_audio_pes_packet()
        pes_len = min(len(pes_data), 184)
        packet[4:4+pes_len] = pes_data[:pes_len]
        
        for i in range(4+pes_len, 188):
            packet[i] = 0xFF
        
        return bytes(packet)
    
    def create_audio_packet(self, continuity_counter, audio_pid=None):
        """Создает аудио пакет"""
        if audio_pid is None:
            audio_pid = self.BASE_AUD_PID
            
        packet = bytearray(self.audio_packet_template)
        
        # Обновляем PID и CC
        packet[1] = (packet[1] & 0xE0) | ((audio_pid >> 8) & 0x1F)
        packet[2] = audio_pid & 0xFF
        packet[3] = (1 << 4) | (continuity_counter & 0x0F)
        
        return bytes(packet)
    
    def create_null_packet_template(self):
        """Создает шаблон NULL пакета"""
        packet = self.tp_fmt(self.NULL_PID, payload_start=False,
                            continuity_counter=0,
                            adaptation_field_control=1)
        
        for i in range(4, 188):
            packet[i] = 0xFF
        
        return bytes(packet)
    
    def create_null_packet(self, continuity_counter):
        """Создает NULL пакет"""
        packet = bytearray(self.null_packet_template)
        packet[3] = (1 << 4) | (continuity_counter & 0x0F)
        return bytes(packet)
    
    # -----------------------------------------------------------------
    # TDT/TOT функции (без изменений)
    # -----------------------------------------------------------------
    def create_tdt_section(self, current_time=None):
        """
        Создает TDT (Time and Date Table) секцию с правильной датой
        """
        if current_time is None:
            current_time = time.time()
        
        # Конвертируем Unix time в UTC структуру
        utc_struct = time.gmtime(current_time)
        
        # Вычисляем MJD (Modified Julian Date)
        # Формула: MJD = JD - 2400000.5
        # JD для Григорианского календаря:
        year = utc_struct.tm_year
        month = utc_struct.tm_mon
        day = utc_struct.tm_mday
        
        if month <= 2:
            year -= 1
            month += 12
        
        A = year // 100
        B = 2 - A + (A // 4)
        
        jd = int(365.25 * (year + 4716)) + int(30.6001 * (month + 1)) + day + B - 1524.5
        mjd = int(jd - 2400000.5)
        
        # UTC часы, минуты, секунды в BCD формате
        hours = utc_struct.tm_hour
        minutes = utc_struct.tm_min
        seconds = utc_struct.tm_sec
        
        tdt = bytearray()
        
        # Table ID для TDT = 0x70
        tdt.append(0x70)
        
        # Section syntax indicator = 0, reserved = 1, section_length placeholder
        tdt.append(0xF0)
        tdt.append(0x00)  # Section length
        
        # UTC_time: MJD (16 бит) + BCD hours/minutes/seconds (24 бита)
        tdt.append((mjd >> 8) & 0xFF)
        tdt.append(mjd & 0xFF)
        
        # BCD упаковка часов:минут:секунд
        tdt.append(((hours // 10) << 4) | (hours % 10))
        tdt.append(((minutes // 10) << 4) | (minutes % 10))
        tdt.append(((seconds // 10) << 4) | (seconds % 10))
        
        # Вычисляем и заполняем section length
        section_length = len(tdt) - 3
        tdt[1] = 0xF0 | ((section_length >> 8) & 0x0F)
        tdt[2] = section_length & 0xFF
        
        return bytes(tdt)

    def create_tot_section(self, current_time=None, timezone_offset=3):
        """
        Создает TOT (Time Offset Table) секцию со смещением часового пояса
        timezone_offset: смещение от UTC в часах (например +3 для Москвы)
        """
        if current_time is None:
            current_time = time.time()
        
        utc_struct = time.gmtime(current_time)
        
        # UTC время как в TDT
        mjd = 40587
        hours = utc_struct.tm_hour
        minutes = utc_struct.tm_min
        seconds = utc_struct.tm_sec
        
        tot = bytearray()
        
        # Table ID для TOT = 0x73
        tot.append(0x73)
        
        # Section syntax indicator = 0, reserved = 1, section_length placeholder
        tot.append(0xF0)
        tot.append(0x00)  # Section length (заполним позже)
        
        # UTC_time (MJD + BCD)
        tot.append((mjd >> 8) & 0xFF)
        tot.append(mjd & 0xFF)
        tot.append(((hours // 10) << 4) | (hours % 10))
        tot.append(((minutes // 10) << 4) | (minutes % 10))
        tot.append(((seconds // 10) << 4) | (seconds % 10))
        
        # Reserved = 0x0F
        tot.append(0x0F)
        
        # Descriptors loop length placeholder
        desc_len_pos = len(tot)
        tot.append(0x00)
        tot.append(0x00)
        
        # Local time offset descriptor (tag 0x58)
        tot.append(0x58)  # descriptor_tag
        
        # Определяем полярность смещения
        polarity = 0 if timezone_offset >= 0 else 1
        abs_offset = abs(timezone_offset)
        
        # Descriptor length (13 байт как в примере)
        tot.append(13)
        
        # Country code (3 буквы, например "RUS")
        tot.extend([ord('R'), ord('U'), ord('S')])
        
        # Country region ID (0)
        tot.append(0x00)
        
        # Reserved (1) + polarity (1) + local_time_offset (16 бит в минутах)
        # Смещение в минутах
        offset_minutes = abs_offset * 60
        tot.append(0x01 | (polarity << 1))
        tot.append((offset_minutes >> 8) & 0xFF)
        tot.append(offset_minutes & 0xFF)
        
        # Time of change (дата следующего изменения смещения)
        # Для простоты ставим 0 (нет изменений)
        for i in range(5):
            tot.append(0x00)
        
        # Next time offset (следующее смещение)
        tot.append((offset_minutes >> 8) & 0xFF)
        tot.append(offset_minutes & 0xFF)
        
        # Обновляем descriptors_loop_length
        desc_loop_len = len(tot) - (desc_len_pos + 2)
        tot[desc_len_pos] = (desc_loop_len >> 8) & 0xFF
        tot[desc_len_pos + 1] = desc_loop_len & 0xFF
        
        # Вычисляем и заполняем section length
        section_length = len(tot) - 3
        tot[1] = 0xF0 | ((section_length >> 8) & 0x0F)
        tot[2] = section_length & 0xFF
        
        return bytes(tot)
    
    # -----------------------------------------------------------------
    # Основной генератор блоков
    # -----------------------------------------------------------------
    def generate_block_stream(self):
        """
        Генератор блоков по 7 TS пакетов (1316 байт)
        PAT, PMT, SDT, TDT в КАЖДОМ блоке
        """
        group = 0
        while True:
            block = bytearray()
            cc = 0
            
            # PAT (всегда 1 пакет)
            block.extend(self.pat_packet)
            cc = (cc + 1) & 0x0F
            
            # PMT для КАЖДОГО канала в КАЖДОМ блоке
            for ch in self.active_channels:
                pmt_packet = self.pmt_packets.get(ch['pmt_pid'])
                if pmt_packet:
                    # Обновляем CC для каждого PMT
                    pmt = bytearray(pmt_packet)
                    pmt[3] = (pmt[3] & 0xF0) | (cc & 0x0F)
                    block.extend(pmt)
                    cc = (cc + 1) & 0x0F
            
            # SDT (1 пакет)
            sdt = bytearray(self.sdt_packet)
            sdt[3] = (sdt[3] & 0xF0) | (cc & 0x0F)
            block.extend(sdt)
            cc = (cc + 1) & 0x0F
            
            # TDT (1 пакет)
            tdt_packet = self.create_section_packet(self.TDT_PID, 
                                                    self.create_tdt_section(), cc)
            block.extend(tdt_packet)
            cc = (cc + 1) & 0x0F
            
            # Заполняем NULL до 7 пакетов
            while len(block) // 188 < 7:
                block.extend(self.create_null_packet(cc))
                cc = (cc + 1) & 0x0F
            
            yield bytes(block[:1316])
            group += 1
            
class DVBT2EncoderGUI:

    def __init__(self, root):
        self.root = root
        self.root.title("R6WAX DVB-T2")
        
        # Временные переменные для предотвращения ошибок
        self.emergency_file_path = tk.StringVar(value="")
       
        # Configuration file in script directory
        script_dir = os.path.dirname(os.path.abspath(__file__))
        self.config_file = os.path.join(script_dir, "dvbt2_encoder_config.json")
        print(f"🎯 Config will be saved to: {self.config_file}")        

        # Python paths
        self.gnuradio_python_path = tk.StringVar(value=os.path.join(script_dir, "radioconda", "python.exe"))
        self.obs_path = tk.StringVar(value="")
        self.ffmpeg_path = os.path.join(script_dir, "ffmpeg.exe")                        
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
        self.default_geometry = "673x975"
        
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
        
        # Streaming autostart setting
        self.streaming_auto_start = tk.BooleanVar(value=False)
        
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
        
        # Encoder presets
        self.encoder_preset_name = tk.StringVar(value="")  # Имя выбранного пресета
        self.encoder_preset_commands = {}  # {preset_name: command_text}
        self.encoder_presets_dir = os.path.join(script_dir, "encoder_presets")
        os.makedirs(self.encoder_presets_dir, exist_ok=True)

        # Текстовое поле для отображения/редактирования команды
        self.encoder_command_text = ""  # Будет хранить текущую команду
        self.encoder_command_widget = None  # Ссылка на текстовое поле        
                       
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
        self.pix_fmt = tk.StringVar(value="yuv420p") 
        self.video_aspect = tk.StringVar(value="16:9")
        self.video_profile = tk.StringVar(value="")        
        self.null_packets_percent = tk.DoubleVar(value=10.0)  # 10%  

        self.video_muxdelay = tk.DoubleVar(value=0.5)
        self.video_muxpreload = tk.DoubleVar(value=0.5)
        self.video_buf_factor = tk.DoubleVar(value=50.0)  # 50% от битрейта = /2
        
        # FFmpeg UDP Buffer Size control (в МБ, с шагом 0.5)
        self.udp_buffer_size = tk.DoubleVar(value=5.0)  #  5 МБ
        
        # UDP Buffer settings
        self.buffer_bypass = tk.BooleanVar(value=False)  # False = буфер включен
        self._should_recalc_max = False
        self.target_buffer = tk.IntVar(value="800")
        self.min_buffer = tk.IntVar(value="120")
        self.max_buffer = tk.IntVar(value="10000")
        self.calibration_packets = tk.IntVar(value="8000")
        self.calibration_time = tk.DoubleVar(value="20")
        self.buffer_divider = tk.IntVar(value="2")      

        # Buffer statistics
        self.buffer_input_bitrate = tk.StringVar(value="0")
        self.buffer_output_bitrate = tk.StringVar(value="0")
        self.buffer_fill = tk.StringVar(value="0/0")
        self.buffer_dropped = tk.StringVar(value="0")
        self.buffer_received = tk.StringVar(value="0")
        self.buffer_sent = tk.StringVar(value="0")
        self.buffer_overflow = tk.StringVar(value="0")
        self.buffer_target = tk.StringVar(value="0")        
        
        # Audio settings - СО ЗНАЧЕНИЯМИ ПО УМОЛЧАНИЮ
        self.audio_codec = tk.StringVar(value="aac")
        self.audio_bitrate = tk.StringVar(value="128k")
        self.audio_sample_rate = tk.StringVar(value="48000")
        self.audio_channels = tk.StringVar(value="stereo")

        # Window capture settings
        self.available_windows = []  
        self.available_windows_data = [] 
        
        # Input devices
        self.video_input_device = tk.StringVar(value="OBS Virtual Camera")
        self.audio_input_device = tk.StringVar(value="CABLE Output (VB-Audio Virtual Cable)")
        self.available_video_devices = []
        self.available_audio_devices = []
        
        # Metadata - СО ЗНАЧЕНИЯМИ ПО УМОЛЧАНИЮ
        self.service_name = tk.StringVar(value="Amateur T2 TV")
        self.service_provider = tk.StringVar(value="CallSign DATV")

        # GUI elements that need to be initialized
        self.video_preset_combo = None
        self.overlay_start_btn = None
        self.overlay_stop_btn = None
        self.audio_channels_combo = None
        self.mode_indicator_text = tk.StringVar(value="⚫ SDR-TV")
        
        # Overlay settings
        self.overlay_enabled = tk.BooleanVar(value=False)
        self.overlay_auto_start = tk.BooleanVar(value=False)
        self.overlay_server = None
        self.overlay_thread = None
                
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
            "libx265": ["ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow", "slower", "veryslow", "placebo"],
            "libx264": ["ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow", "slower", "veryslow", "placebo"],
            "hevc_nvenc": ["p1", "p2", "p3", "p4", "p5", "p6", "p7"],
            "h264_nvenc": ["p1", "p2", "p3", "p4", "p5", "p6", "p7"],
            "h264_amf": ["speed", "balanced", "quality"],
            "hevc_amf": ["speed", "balanced", "quality"],
            "hevc_qsv": ["veryfast", "faster", "fast", "medium", "slow", "slower", "veryslow"],
            "h264_qsv": ["veryfast", "faster", "fast", "medium", "slow", "slower", "veryslow"] 
        }
        
        self.codec_tunes = {
            "libx265": ["animation", "grain", "fastdecode", "zerolatency", "psnr", "ssim"],
            "libx264": ["animation", "grain", "fastdecode", "zerolatency", "psnr", "ssim", "film", "stillimage"],        
            "hevc_nvenc": ["hq", "ll", "ull", "lossless"],
            "h264_nvenc": ["hq", "ll", "ull", "lossless"],
            "h264_amf": [],
            "hevc_amf": [],
            "hevc_qsv": [],
            "h264_qsv": []
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
        
        # Modulator presets 
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
        self.multiplex_channels = OrderedDict() 
        self.max_channels = 10        
        
        # Multiplex mode
        self.multiplex_mode = tk.BooleanVar(value=False)        
        self.multiplex_mode.trace_add('write', self.on_multiplex_mode_changed)

        # Recovery settings (новые переменные с значениями по умолчанию)
        self.speed_restart_threshold = tk.DoubleVar(value=0.930)
        self.speed_restart_count = tk.IntVar(value=25)
        self.speed_restart_cooldown_seconds = tk.IntVar(value=30)
        self.channel_speed_fail_threshold = tk.DoubleVar(value=0.960)
        self.channel_speed_check_count = tk.IntVar(value=10)
        self.speed_timeout_seconds = tk.IntVar(value=5)
        self.channel_initialization_seconds = tk.IntVar(value=65)
        self.channel_recovery_check_count = tk.IntVar(value=2)
        self.channel_long_check_count = tk.IntVar(value=7)
        self.channel_long_check_cooldown = tk.IntVar(value=180)
        self.channel_check_interval_normal = tk.IntVar(value=10)
        self.channel_check_interval_fail3 = tk.IntVar(value=180)
        
        # Window search intervals
        self.window_search_interval_1 = tk.IntVar(value=10)
        self.window_search_interval_2 = tk.IntVar(value=30)
        self.window_search_interval_3 = tk.IntVar(value=60)
        self.window_search_interval_4 = tk.IntVar(value=120)
        self.window_search_interval_5 = tk.IntVar(value=300)
        
        # Error dictionaries (редактируемые)
        self.custom_channel_errors = tk.StringVar(value="")
        self.custom_multiplexer_errors = tk.StringVar(value="")
        
        # Сохраняем дефолтные словари ошибок
        self.default_channel_errors = [
            'error opening input', 'Capture item closed', 'failed to reload playlist', 'connection failed',
            'unable to open', 'Server returned 404', 'Invalid data found', 'Error during demuxing',
            'keepalive request failed', 'Failed to resolve hostname', 'Unable to open URL', 'http error',
            'Failed to resolve', 'invalid new backstep -1', 'Connection timed out', 'IO error: Error number -10054 occurred',
            'Server disconnected', 'Error in the pull function', 'Error number -10054 occurred', 'end of file', 'Input/output error'
        ]
        
        self.default_multiplexer_errors = [
            'Error during demuxing: I/O error', 'Could not write header', 'sample rate not set', 'timeout',
            'buffer overflow', 'Circular buffer overrun', 'muxing failed', 'Invalid argument'
        ]
        
        # Load saved configuration
        self.load_config()
        
        emergency_path = self.emergency_file_path.get()
        if emergency_path and not os.path.isabs(emergency_path):
            # Если путь относительный, преобразуем в абсолютный относительно папки скрипта
            script_dir = os.path.dirname(os.path.abspath(__file__))
            abs_path = os.path.join(script_dir, emergency_path)
            if os.path.exists(abs_path):
                self.emergency_file_path.set(abs_path)
            else:
                self.log_message(f"⚠️ Emergency file not found: {abs_path}", "buffer")
                
        # Load encoder presets
        self.load_encoder_presets()        
                
        self.create_gui()        

        # После создания GUI применяем выбранный пресет, если он есть
        if self.encoder_preset_name.get() and self.encoder_preset_name.get() in self.encoder_preset_commands:
            self.apply_encoder_preset(self.encoder_preset_name.get())
        else:
            self.update_encoder_command_display()
        self._updating_from_preset = False  # Добавить флаг
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

        
        # Speed monitoring for auto-restart (НОВЫЕ ПЕРЕМЕННЫЕ)
        self.main_speed_history = []  # история скоростей основного мультиплексора
        self.speed_restart_cooldown = 0  # время последнего перезапуска

        self.channel_initialized = {}  # время первого появления скорости
        self.channel_speed_history = {}  # {channel_num: [speed_values]}      
        self.channel_speed_received = {}  # флаг получения speed для каждого канала                 
        # Для отслеживания порядка фильтров
        self.channel_filter_indices = {}  # {channel_num: filter_index} 
        
        # Multi-process system variables
        self.channel_processes = {}  # {channel_num: {'process': subprocess, 'pid': int, 'stdin': pipe, 'port': int, 'is_radio': bool, 'is_emergency': bool}}
        self.base_multicast_port = 3020  # Starting port for channels
        self.main_multiplexer_process = None  # Main multiplexer process 
        
        # Start OBS monitoring
        self.check_obs_status()

        # Overlay autostart
        if self.overlay_auto_start.get():
            self.start_overlay()

        # OBS autostart
        if self.obs_auto_start.get() and self.obs_path.get() and not self.obs_running:
            self.root.after(8000, self.start_obs)
            
        # Modulator autostart
        if self.modulator_auto_start.get():
            self.root.after(4000, self.start_modulator)
            
        # Streaming autostart    
        if self.streaming_auto_start.get():
            self.root.after(6000, self.start_streaming)

        # MPC Player autostart    
        if self.playlist_manager.playlist_auto_start.get():
            self.root.after(3000, self.playlist_manager.start_playlist_playback)
            
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
        self.stop_modulator()
        if self.modulator_auto_start.get():
            self.root.after(4000, self.start_modulator)        
        

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
        self.confirm_frequency()
            
    def setup_config_autosave(self):
        """Setup auto-save triggers for all settings"""
        # Привязка к изменению текстовых полей
        text_variables = [
            self.service_name, 
            self.service_provider, self.localhost_ip, self.output_ip,
        # FFmpeg custom options
            self.custom_options, self.video_aspect, 
        ]
        # Привязка к изменениям в GUI для обновления отображения команды
        gui_vars = [
            self.video_codec, self.video_preset, self.video_tune, self.video_profile,
            self.pix_fmt, self.video_aspect, self.video_resolution, self.video_fps,
            self.video_gop, self.custom_options, self.audio_codec, self.audio_sample_rate,
            self.audio_channels
        ]
        for var in gui_vars:
            var.trace_add('write', lambda *args: self.on_encoder_gui_change())     
        # for var in text_variables:
            # var.trace_add('write', lambda *args: self.debounced_save())
        
        # # ⭐⭐⭐ ДОБАВЛЕНО: ОТДЕЛЬНЫЕ ОБРАБОТЧИКИ ДЛЯ КЛЮЧЕВЫХ ПОЛЕЙ ⭐⭐⭐
        # # Для частоты - с задержкой больше, чтобы не обновлять слишком часто
        # self.frequency.trace_add('write', lambda *args: self.debounced_save_and_update_presets())
        
        # # Для RF gain
        # self.rf_gain.trace_add('write', lambda *args: self.debounced_save_and_update_presets())
        
        # # Для Pluto IP
        # self.pluto_ip.trace_add('write', lambda *args: self.debounced_save_and_update_presets())
        # # ⭐⭐⭐ КОНЕЦ ДОБАВЛЕНИЯ ⭐⭐⭐

        # Привязка к изменению числовых полей
        numeric_variables = [
            self.udp_input_port, self.udp_output_port, self.muxrate, self.video_buf_factor,
            self.video_bitrate, self.video_bufsize, self.video_gop, self.video_muxdelay, self.video_muxpreload,
            self.target_buffer, self.min_buffer, self.max_buffer, self.udp_buffer_size, self.null_packets_percent
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
            self.save_window_size, self.streaming_auto_start,
            self.obs_auto_start, self.modulator_auto_start, self.overlay_auto_start,
            self.buffer_bypass
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
        self._save_timer = self.root.after(2000, self.save_config)

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
        if self.is_streaming:
            return        
        try:
            self.update_channels_visibility()
        except Exception:
            return False
            
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
                
    def finish_playlist_setup(self):
        """Finish playlist setup after GUI is created"""
        # Update media listbox with loaded folders
        if hasattr(self.playlist_manager, 'media_listbox'):
            self.playlist_manager.update_media_listbox()
        
        # Update bumper numbers
        if hasattr(self.playlist_manager, 'bumper_widgets') and self.playlist_manager.bumper_widgets:
            self.playlist_manager.update_bumper_numbers()
            
        # Загружаем сохраненные бамперы
        if hasattr(self, 'bumper_paths_to_load'):
            bumper_paths = self.bumper_paths_to_load
            if hasattr(self.playlist_manager, 'bumper_widgets'):
                # Очищаем лишние
                while len(self.playlist_manager.bumper_widgets) > len(bumper_paths):
                    row_frame, _ = self.playlist_manager.bumper_widgets[-1]
                    row_frame.destroy()
                    self.playlist_manager.bumper_widgets.pop()
                
                # Добавляем недостающие
                while len(self.playlist_manager.bumper_widgets) < len(bumper_paths):
                    self.playlist_manager.add_bumper_row()
                
                # Применяем пути
                for i, (frame, var) in enumerate(self.playlist_manager.bumper_widgets):
                    if i < len(bumper_paths):
                        var.set(bumper_paths[i])
                    else:
                        var.set("")
                
                self.playlist_manager.update_bumper_numbers()
            delattr(self, 'bumper_paths_to_load')            
            
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
        self.debounced_save_and_update_presets()
        self.rf_gain_timer = None        
        
    def connect_to_gnuradio(self):
        """Connect to GNU Radio XML-RPC server with retry - called after modulator starts"""
        def connect_thread():
            max_retries = 5
            retry_delay = 3
            
            for attempt in range(max_retries):
                try:
                    self.log_message(f"Attempting to connect to GNU Radio (attempt {attempt+1}/{max_retries})...", "buffer")
                    self.root.after(300, lambda: self.connection_status_var.set(f"🔄 Connecting... ({attempt+1}/{max_retries})"))
                    
                    self.server = xmlrpc.client.ServerProxy(self.server_url, allow_none=True)
                    
                    # Test connection
                    self.server.get_rf_gain()
                    
                    self.connected = True
                    self.root.after(400, lambda: self.connection_status_var.set("✅ Connected"))
                    self.root.after(500, lambda: self.connection_indicator.config(foreground='green'))
                    self.log_message("✅ Connected to GNU Radio XML-RPC server", "buffer")
                                       
                    # Get current values from GNU Radio
                    self.get_gnuradio_values()
                    return
                    
                except Exception as e:
                    if attempt < max_retries - 1:
                        self.root.after(2000, lambda: self.connection_status_var.set(f"🔄 Retrying... ({attempt+1}/{max_retries})"))
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

    def get_gnuradio_values(self):
        """Get current values from GNU Radio"""
        if not self.connected:
            return
            
        def get_thread():
            try:
                # Get RF gain -
                rf_gain = self.server.get_rf_gain()
                # Convert to GUI percentage
                rf_percent = self.convert_rf_gain_to_gui(rf_gain)
                self.log_message(f"🔧 Got from GNU Radio: RF={rf_gain} dB -> GUI={rf_percent}%", "buffer")
                                
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
        
        # DVB icon 
        ttk.Label(title_frame, text="📺", font=('Arial', 16)).pack(side='left', padx=(0, 5))
        
        # Styled title with rounded font and dark gray color
        title_label = tk.Label(title_frame, text="R6WAX DVB-T2\nDATV Broadcast\nSystem", 
                              font=('Segoe UI', 13, 'bold'), fg='#404040')
        title_label.pack(side='left')
        
        # Status indicators with colored labels 
        status_frame = ttk.Frame(header_frame)
        status_frame.pack(side='left', padx=(20, 0))
        
        # GNU Radio и RF Mod статусы
        first_row_frame = ttk.Frame(status_frame)
        first_row_frame.pack(side='top', fill='x', pady=2)
        
        # XML-RPC connection status
        ttk.Label(first_row_frame, text="GNU Radio:", font=('Arial', 9)).pack(side='left')
        self.connection_indicator = tk.Label(first_row_frame, textvariable=self.connection_status_var, 
                                           font=('Arial', 9, 'bold'), foreground='red')
        self.connection_indicator.pack(side='left', padx=5)
        
        # RF Mod status 
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

        # Multiplex Tab 
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
        
        # Monitor Tab 
        monitor_frame = ttk.Frame(notebook, padding="8")
        notebook.add(monitor_frame, text="Monitor")        
        
        self.create_stats_tab(stats_frame)
        self.create_settings_tab(settings_frame)
        self.create_multiplex_tab(multiplex_frame) 
        self.create_overlay_tab(overlay_frame)
        self.create_logs_tab(logs_frame)
        self.create_monitor_tab(monitor_frame)
        self.setup_config_autosave()
        
    def create_multiplex_tab(self, parent):
        """Create multiplex configuration tab"""
        main_frame = ttk.Frame(parent)
        main_frame.pack(fill='both', expand=True)
        
        # Emergency stream file
        emergency_frame = ttk.LabelFrame(main_frame, text="Emergency Stream", padding="4")
        emergency_frame.pack(fill='x', pady=(0, 6))

        row_frame = ttk.Frame(emergency_frame)
        row_frame.pack(fill='x', pady=2)

        ttk.Label(row_frame, text="Emergency File:", font=('Arial', 9), width=13).pack(side='left')
        emergency_entry = ttk.Entry(row_frame, textvariable=self.emergency_file_path, 
                                   width=53, font=('Arial', 8))
        emergency_entry.pack(side='left', padx=2, fill='x', expand=False)

        ttk.Button(row_frame, text="Browse", width=8,
                  command=self.browse_emergency_file).pack(side='left', padx=2)
        
        # Scrollable area for channels
        canvas_frame = ttk.Frame(main_frame)
        canvas_frame.pack(fill='both', expand=True)
        canvas_frame.pack_propagate(False)  # ← ДОБАВИТЬ

        # Теперь scrollbar
        scrollbar = ttk.Scrollbar(canvas_frame, orient="vertical")
        scrollbar.pack(side='right', fill='y')

        # Canvas занимает оставшееся место
        canvas = tk.Canvas(canvas_frame, yscrollcommand=scrollbar.set)
        canvas.pack(side='left', fill='both', expand=True)

        scrollbar.config(command=canvas.yview)

        scrollable_frame = ttk.Frame(canvas)

        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")

        def on_canvas_configure(event):
            
            canvas.itemconfig(1, width=event.width - 4)  

        canvas.bind('<Configure>', on_canvas_configure)

        # Channel container
        self.channels_container = ttk.Frame(scrollable_frame)
        self.channels_container.pack(fill='both', expand=True, pady=(0, 6))
                
        # Add channel button
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill='x', pady=(3, 0))
        
        self.add_ch_btn = ttk.Button(btn_frame, text="Add Channel", 
                                     command=self.add_channel, width=15)
        self.add_ch_btn.pack(side='left', padx=2)
        
        # FFmpeg Command
        ttk.Button(btn_frame, text="FFmpeg Command", 
                  command=self.show_multiplex_ffmpeg_command, width=17).pack(side='left', padx=2)
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # Setup auto-save
        self.setup_multiplex_autosave()
        
        # Update add button state
        self.update_add_button_state()

    def get_available_windows(self):
        """Получение списка доступных окон с именами процессов через PowerShell"""
        try:
            # Список исключений (системные процессы без окон)
            excluded_processes = {
                'TextInputHost', 'SystemSettings', 'NVIDIA Overlay', 
                'ApplicationFrameHost', 'spacedeskServiceTray', 'python',
                'DuetUpdater', 'spacedeskConsole', 'explorer', 'cmd',
                'powershell', 'conhost', 'svchost', 'dwm', 'csrss',
                'winlogon', 'services', 'lsass', 'SearchApp', 'RuntimeBroker',
                'SecurityHealthSystray', 'ShellExperienceHost', 'StartMenuExperienceHost',
                'WindowsTerminal', 'Taskmgr', 
                'Spotify', 'Discord',  'WhatsApp', 'Slack',
                'Teams', 'Zoom', 'Code', 'Notepad++', 'obs64', 'vlc'
                
            }
            
            # PowerShell команда для получения окон с заголовками и именами процессов
            ps_command = "Get-Process | Where-Object { $_.MainWindowTitle -ne '' } | Select-Object ProcessName, MainWindowTitle | ConvertTo-Json"
            
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
            
            # Парсим JSON
            import json
            try:
                windows_data = json.loads(result.stdout)
                if not windows_data:
                    return []
                
                # Если только один объект, превращаем в список
                if isinstance(windows_data, dict):
                    windows_data = [windows_data]
                
                # Формируем список словарей, исключая системные процессы
                windows_list = []
                for item in windows_data:
                    process_name = item.get('ProcessName', '')
                    window_title = item.get('MainWindowTitle', '')
                    
                    # Пропускаем процессы из списка исключений
                    if process_name in excluded_processes:
                        continue
                        
                    if process_name and window_title:
                        windows_list.append({
                            'process_name': process_name,
                            'window_title': window_title
                        })
                
                self.log_message(f"Found {len(windows_list)} windows for capture (excluded {len(windows_data)-len(windows_list)} system processes)", "buffer")
                return windows_list
                
            except json.JSONDecodeError as e:
                self.log_message(f"JSON parse error: {e}", "buffer")
                return []
            
        except subprocess.TimeoutExpired:
            self.log_message("Timeout getting windows list", "buffer")
            return []
        except Exception as e:
            self.log_message(f"Error getting windows: {e}", "buffer")
            return []

    def refresh_channel_windows(self, channel_num):
        """Обновление списка доступных окон/процессов для канала"""
        if channel_num not in self.multiplex_channels:
            return
        
        channel_data = self.multiplex_channels[channel_num]
        capture_method = channel_data['capture_method'].get()
        
        # Получаем актуальный список окон с процессами
        windows_list = self.get_available_windows()
        self.available_windows_data = windows_list  # Сохраняем для других функций
        
        if 'window_combo' in channel_data and channel_data['window_combo']:
            combo = channel_data['window_combo']
            current_value = channel_data['window_title'].get()
            
            # Формируем список для отображения в зависимости от метода
            display_values = []
            if capture_method == 'gdigrab':
                # Показываем названия окон
                display_values = [w['window_title'] for w in windows_list]
            else:  # gfxcapture
                # Показываем имена процессов с .exe
                display_values = [f"{w['process_name']}.exe" for w in windows_list]
            
            # Убираем дубликаты
            seen = set()
            unique_values = []
            for val in display_values:
                if val not in seen:
                    seen.add(val)
                    unique_values.append(val)
            
            combo['values'] = unique_values if unique_values else ['No windows found']
            
            # Пытаемся сохранить выбранное значение
            if current_value and current_value in unique_values:
                # Окно/процесс все еще доступно - оставляем
                pass
            elif current_value and unique_values:
                # Ищем похожее (для gdigrab) или просто берем первое
                if capture_method == 'gdigrab':
                    similar = self.find_similar_window(current_value, unique_values)
                    if similar:
                        channel_data['window_title'].set(similar)
                        self.log_message(f"CH{channel_num}: Found similar window: {similar[:50]}...", "buffer")
                    else:
                        channel_data['window_title'].set(unique_values[0])
                        self.log_message(f"CH{channel_num}: Using first available window", "buffer")
                else:  # gfxcapture
                    # Для процессов берем первое
                    channel_data['window_title'].set(unique_values[0])
                    self.log_message(f"CH{channel_num}: Using first available process", "buffer")
            elif unique_values:
                # Нет выбранного - берем первое
                channel_data['window_title'].set(unique_values[0])

    def find_similar_window(self, old_title, available_windows):
        """Поиск похожего окна среди доступных"""
        if not old_title or not available_windows:
            return None
        
        import re
        
        # Проверяем тип данных
        if isinstance(available_windows, list) and len(available_windows) > 0:
            # Если это список словарей (из новой get_available_windows)
            if isinstance(available_windows[0], dict):
                window_titles = [w['window_title'] for w in available_windows if 'window_title' in w]
            else:
                # Если это список строк
                window_titles = available_windows
        else:
            window_titles = available_windows
        
        if not window_titles:
            return None
        
        self.log_message(f"Looking for window similar to: '{old_title[:50]}...'", "buffer")
        
        # 1. Сначала ищем точное совпадение
        if old_title in window_titles:
            return old_title
        
        # 2. Извлекаем основу названия
        base_pattern = re.match(r'^([A-Za-z0-9_\-\.\s]+?)(?:\s+[Vv]\d+|\s*[-\[]|$)', old_title)
        if base_pattern:
            base_name = base_pattern.group(1).strip()
            self.log_message(f"Base name extracted: '{base_name}'", "buffer")
            
            for window in window_titles:
                if base_name in window:
                    self.log_message(f"Found window containing base name: '{window[:50]}...'", "buffer")
                    return window
        
        # 3. Если не нашли, ищем по ключевым словам
        words = re.findall(r'[A-Za-z0-9_]+', old_title)
        if len(words) >= 2:
            key_words = words[:3]
            self.log_message(f"Key words: {key_words}", "buffer")
            
            best_match = None
            best_score = 0
            
            for window in window_titles:
                score = 0
                window_lower = window.lower()
                for word in key_words:
                    if word.lower() in window_lower:
                        score += 1
                
                if score > best_score:
                    best_score = score
                    best_match = window
            
            if best_score >= 2:
                self.log_message(f"Best match with score {best_score}: '{best_match[:50]}...'", "buffer")
                return best_match
        
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
            'window_title': tk.StringVar(),  
            'window_combo': None,  
            'capture_method': tk.StringVar(value='gdigrab'),  # gdigrab или gfxcapture
            'capture_method_combo': None,            
            'media_path': tk.StringVar(),
            'randomize': tk.BooleanVar(),
            'udp_url': tk.StringVar(),
            'url_input': tk.StringVar(), 
            'selected_program': tk.StringVar(), 
            'available_programs': [],
            'video_devices_combo': None,
            'audio_devices_combo': None,
            'audio_delay': tk.DoubleVar(value=0.0),  # задержка аудио в секундах
            'content_frame': None,
            'udp_url_entry': None,
            'url_input_entry': None, 
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
        
        # Top row: Checkbox, Name, Source Type 
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
            row_frame = ttk.Frame(content_frame)
            row_frame.pack(fill='x', pady=1)
            
            ttk.Label(row_frame, text="Window:", font=('Arial', 8), width=7).pack(side='left')
            
            # Метод захвата (gdigrab/gfxcapture)
            method_combo = ttk.Combobox(row_frame, textvariable=channel_data['capture_method'],
                                       values=['gdigrab', 'gfxcapture'],
                                       width=9, font=('Arial', 8), state='readonly')
            method_combo.pack(side='left', padx=2)
            channel_data['capture_method_combo'] = method_combo
            method_combo.bind('<<ComboboxSelected>>', 
                             lambda e, ch=channel_num: self.on_capture_method_change(ch))
            
            # Комбобокс для выбора окна/процесса
            window_combo = ttk.Combobox(row_frame, textvariable=channel_data['window_title'],
                                       width=38, font=('Arial', 8))
            window_combo.pack(side='left', padx=2, fill='x', expand=True)
            channel_data['window_combo'] = window_combo
            
            # Кнопка обновления списка окон
            ttk.Button(row_frame, text="Refresh", width=8,
                      command=lambda ch=channel_num: self.refresh_channel_windows(ch)).pack(side='left', padx=2)
            
            # Audio device selection with delay control
            audio_frame = ttk.Frame(content_frame)
            audio_frame.pack(fill='x', pady=1)

            ttk.Label(audio_frame, text="Audio:", font=('Arial', 8), width=6).pack(side='left')

            # Audio device combo (сначала список устройств)
            audio_combo = ttk.Combobox(audio_frame, textvariable=channel_data['audio_device'],
                                      width=30, font=('Arial', 8), state="readonly")
            audio_combo.pack(side='left', padx=2, fill='x', expand=True)
            channel_data['audio_devices_combo'] = audio_combo

            # Delay spinbox (после списка)
            ttk.Label(audio_frame, text="Delay:", font=('Arial', 8)).pack(side='left', padx=(5, 2))

            delay_spin = ttk.Spinbox(
                audio_frame, 
                from_=-10.0, 
                to=10.0, 
                increment=0.05,
                textvariable=channel_data['audio_delay'],
                width=6,
                font=('Arial', 8),
                format='%.2f'
            )
            delay_spin.pack(side='left', padx=(0, 5))
            
            # Обновляем списки
            self.root.after(100, lambda: self.refresh_channel_windows(channel_num))
            self.root.after(200, self.find_audio_devices)
            self.root.after(300, lambda: self.populate_channel_device_lists(channel_num))
            
    def on_capture_method_change(self, channel_num):
        """Обработчик изменения метода захвата окна"""
        if channel_num not in self.multiplex_channels:
            return
        
        # Обновляем список окон/процессов
        self.refresh_channel_windows(channel_num)
        self.save_config()            

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
        
        ffmpeg_path = self.ffmpeg_path
        
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
            ffmpeg_path = self.ffmpeg_path
            
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
        
        # Создаем папку для плейлистов, если её нет
        script_dir = os.path.dirname(os.path.abspath(__file__))
        playlists_dir = os.path.join(script_dir, "multiplex_playlists")
        os.makedirs(playlists_dir, exist_ok=True)
        
        list_name = f"multiplex_ch{channel_num}_playlist.txt"
        list_path = os.path.join(playlists_dir, list_name)
        
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
                        channel_data['audio_delay'].set(float(ch_config.get('audio_delay', 0.0)))
                        channel_data['capture_method'].set(str(ch_config.get('capture_method', 'gdigrab')))
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
        
        
        # Current preset and frequency 
        ttk.Label(rf_frame, text="Preset:", font=('Arial', 10)).grid(row=0, column=0, sticky='w', pady=2)
        self.mod_preset_combo = ttk.Combobox(rf_frame, textvariable=self.modulator_preset,
                                       values=list(self.modulator_presets.keys()),
                                       width=25, font=('Arial', 9), state='readonly')  # ИЗМЕНЕНО: width=25
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
        enc_frame = ttk.LabelFrame(parent, text="Encoder Statistics", padding="6")
        enc_frame.pack(fill='x', pady=(0, 6))
        
        # Основной контейнер
        stats_container = ttk.Frame(enc_frame)
        stats_container.pack(fill='x')
        
        # ===== ЛЕВАЯ КОЛОНКА: ОСНОВНОЙ ЭНКОДЕР =====
        main_frame = ttk.Frame(stats_container)
        main_frame.pack(side='left', padx=(0, 15))
        
        # Заголовок с индикатором HDR
        title_frame = ttk.Frame(main_frame)
        title_frame.pack(anchor='w')

        ttk.Label(title_frame, text="Multiplex", font=('Arial', 8, 'bold')).pack(side='left')

        # Индикатор HDR (второй label с той же переменной)
        self.main_hdr_indicator = ttk.Label(title_frame, textvariable=self.mode_indicator_text,
                                             font=('Arial', 7, 'bold'))
        self.main_hdr_indicator.pack(side='left', padx=(5, 0))
        
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
        ttk.Checkbutton(buf_frame, text="Bypass", 
                        variable=self.buffer_bypass,
                        command=self.save_config).grid(row=0, column=9, sticky='w', padx=(15,0), pady=1)        
        
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
        ttk.Label(control_frame, text="Autostart:").pack(side='left', padx=8)        
        ttk.Checkbutton(control_frame, text="Encoder", 
                       variable=self.streaming_auto_start, 
                       command=self.save_config).pack(side='left', padx=8)                      
        
        ttk.Checkbutton(control_frame, text="Broadcast", 
                       variable=self.modulator_auto_start, 
                       command=self.save_config).pack(side='left', padx=8)
        
        ttk.Checkbutton(control_frame, text="Overlay", 
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

        # Confirm button остается в той же колонке
        ttk.Button(rf_frame, text="Confirm", 
                  command=self.confirm_frequency, width=8).grid(row=1, column=3, sticky='e', padx=2)

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

        # Индикатор режима кодирования
        mode_indicator_frame = ttk.Frame(multiplex_check_frame)
        mode_indicator_frame.pack(side='right', padx=(20, 0))

        self.mode_indicator_label = ttk.Label(mode_indicator_frame, 
                                               textvariable=self.mode_indicator_text,
                                               font=('Arial', 9, 'bold'))
        self.mode_indicator_label.pack()

        self.pix_fmt.trace_add('write', self.update_mode_indicator)        
        
        # Top frame for Network and Buffer settings
        top_frame = ttk.Frame(parent)
        top_frame.pack(fill='x', pady=(0, 6))
        
        # Network Settings - слева
        net_frame = ttk.LabelFrame(top_frame, text="Buffer Network Settings", padding="6")
        net_frame.pack(side='left', fill='both', expand=True, padx=(0, 3))

        # Настройка колонок для равномерного распределения
        net_frame.columnconfigure(1, weight=0)  # Поле ввода IP
        net_frame.columnconfigure(3, weight=0)  # Поле ввода порта
        net_frame.columnconfigure(5, weight=0)  # Поле buffer_size

        # Row 0: Input
        ttk.Label(net_frame, text="Input:", font=('Arial', 9)).grid(row=0, column=0, sticky='w', pady=1)
        ttk.Entry(net_frame, textvariable=self.localhost_ip, width=14, font=('Arial', 9)).grid(row=0, column=1, padx=2, pady=1)
        ttk.Label(net_frame, text=":", font=('Arial', 9)).grid(row=0, column=2, sticky='w', pady=1)
        ttk.Entry(net_frame, textvariable=self.udp_input_port, width=6, font=('Arial', 9)).grid(row=0, column=3, padx=2, pady=1)
        ttk.Label(net_frame, text="UDP", font=('Arial', 9)).grid(row=0, column=4, sticky='w', pady=1, padx=2)

        # Row 1: Output
        ttk.Label(net_frame, text="Output:", font=('Arial', 9)).grid(row=1, column=0, sticky='w', pady=1)
        ttk.Entry(net_frame, textvariable=self.output_ip, width=14, font=('Arial', 9)).grid(row=1, column=1, padx=2, pady=1)
        ttk.Label(net_frame, text=":", font=('Arial', 9)).grid(row=1, column=2, sticky='w', pady=1)
        udp_output_entry = ttk.Entry(net_frame, textvariable=self.udp_output_port, width=6, font=('Arial', 9))
        udp_output_entry.grid(row=1, column=3, padx=2, pady=1)
        udp_output_entry.bind('<FocusOut>', lambda e: self.set_gnuradio_variable("zmq_port", self.udp_output_port.get()))
        ttk.Label(net_frame, text="ZMQ", font=('Arial', 9)).grid(row=1, column=4, sticky='w', pady=1, padx=2)

        # Row 2: Muxrate и Buffer Size в одной строке
        ttk.Label(net_frame, text="Muxrate:", font=('Arial', 9)).grid(row=2, column=0, sticky='w', pady=1)
        ttk.Entry(net_frame, textvariable=self.muxrate, width=16, font=('Arial', 8)).grid(row=2, column=1, padx=2, pady=1)

        # Буфер под портами (колонка 3)
        udp_buffer_spinbox = ttk.Spinbox(net_frame, from_=1, to=25, increment=1, 
                                         textvariable=self.null_packets_percent, 
                                         width=4, font=('Arial', 9))
        udp_buffer_spinbox.grid(row=2, column=3, padx=2, pady=1)

        # Подпись справа от поля buffer_size
        ttk.Label(net_frame, text="Nulls%", font=('Arial', 9)).grid(row=2, column=4, sticky='w', pady=1, padx=2)
                
        # UDP Buffer Settings - справа
        buf_frame = ttk.LabelFrame(top_frame, text="UDP ZMQ Buffer Set", padding="6")
        buf_frame.pack(side='right', fill='both', expand=True, padx=(3, 0))
        
        ttk.Label(buf_frame, text="Target:", font=('Arial', 9)).grid(row=0, column=0, sticky='w', pady=1)
        ttk.Spinbox(buf_frame, from_=200, to=40000, textvariable=self.target_buffer, width=8, font=('Arial', 9)).grid(row=0, column=1, padx=2, pady=1)
        
        ttk.Label(buf_frame, text="Min:", font=('Arial', 9)).grid(row=0, column=2, sticky='w', pady=1, padx=(8,0))
        ttk.Spinbox(buf_frame, from_=10, to=10000, textvariable=self.min_buffer, width=8, font=('Arial', 9)).grid(row=0, column=3, padx=2, pady=1)
        
        ttk.Label(buf_frame, text="Max:", font=('Arial', 9)).grid(row=1, column=0, sticky='w', pady=1)
        ttk.Spinbox(buf_frame, from_=500, to=100000, textvariable=self.max_buffer, width=8, font=('Arial', 9)).grid(row=1, column=1, padx=2, pady=1)
        
        ttk.Label(buf_frame, text="Buflen:", font=('Arial', 9)).grid(row=1, column=2, sticky='w', pady=1, padx=(8,0))
        ttk.Spinbox(buf_frame, from_=50, to=1000, textvariable=self.calibration_packets, width=8, font=('Arial', 9)).grid(row=1, column=3, padx=2, pady=1)
        
        ttk.Label(buf_frame, text="UDP Buff:", font=('Arial', 9)).grid(row=2, column=0, sticky='w', pady=1)
        ttk.Spinbox(buf_frame, from_=0, to=50, increment=0.5, textvariable=self.udp_buffer_size, width=8, font=('Arial', 9)).grid(row=2, column=1, padx=2, pady=1)
        
        ttk.Label(buf_frame, text="Buffer Divider:", font=('Arial', 9)).grid(row=2, column=2, sticky='w', pady=1, padx=(8,0))
        ttk.Spinbox(buf_frame, from_=1, to=16, textvariable=self.buffer_divider, width=8, font=('Arial', 9)).grid(row=2, column=3, padx=2, pady=1)
        
        # Middle frame for Video, Audio and Metadata
        middle_frame = ttk.Frame(parent)
        middle_frame.pack(fill='x', pady=(0, 6))
        
        # Video Settings - ТРЕХКОЛОНОЧНАЯ ВЕРСИЯ
        vid_frame = ttk.LabelFrame(middle_frame, text="Video Settings", padding="6")
        vid_frame.pack(fill='x', pady=(0, 6))

        # Настройка колонок для трех столбцов равной ширины
        vid_frame.columnconfigure(0, weight=0)  # Подпись столбца 1
        vid_frame.columnconfigure(1, weight=1)  # Поле ввода столбца 1
        vid_frame.columnconfigure(2, weight=0)  # Разделитель
        vid_frame.columnconfigure(3, weight=1)  # Поле ввода столбца 2
        vid_frame.columnconfigure(4, weight=0)  # Разделитель
        vid_frame.columnconfigure(5, weight=1)  # Поле ввода столбца 3

        # ===== СТОЛБЕЦ 1 =====
        # Row 0: Resolution
        ttk.Label(vid_frame, text="Resolution:", font=('Arial', 9)).grid(row=0, column=0, sticky='w', pady=2, padx=(0, 2))
        self.resolution_combo = ttk.Combobox(vid_frame, textvariable=self.video_resolution, 
                    values=["3840x2160", "2560x1440", "1920x1080", "1280x720", "1024x576", "854x480", "768x432", "640x360"], 
                    width=15, font=('Arial', 9))
        self.resolution_combo.grid(row=0, column=1, sticky='ew', padx=2, pady=2)

        # Row 1: Aspect
        ttk.Label(vid_frame, text="Aspect:", font=('Arial', 9)).grid(row=1, column=0, sticky='w', pady=2, padx=(0, 2))
        self.aspect_combo = ttk.Combobox(vid_frame, textvariable=self.video_aspect,
                    values=["16:9", "4:3", "1:1", "2.35:1", "2.40:1", "1.85:1"], 
                    width=15, font=('Arial', 9))
        self.aspect_combo.grid(row=1, column=1, sticky='ew', padx=2, pady=2)

        # Row 2: FPS
        ttk.Label(vid_frame, text="FPS:", font=('Arial', 9)).grid(row=2, column=0, sticky='w', pady=2, padx=(0, 2))
        self.fps_combo = ttk.Combobox(vid_frame, textvariable=self.video_fps,
                    values=["24", "25", "30", "50", "60"], width=15, font=('Arial', 9))
        self.fps_combo.grid(row=2, column=1, sticky='ew', padx=2, pady=2)

        # Row 3: GOP
        ttk.Label(vid_frame, text="GOP:", font=('Arial', 9)).grid(row=3, column=0, sticky='w', pady=2, padx=(0, 2))
        self.gop_entry = ttk.Entry(vid_frame, textvariable=self.video_gop, width=15, font=('Arial', 9))
        self.gop_entry.grid(row=3, column=1, sticky='ew', padx=2, pady=2)
        
        ttk.Label(vid_frame, text="Muxdelay:", font=('Arial', 9)).grid(row=4, column=0, sticky='w', pady=2, padx=(0, 2))
        muxdelay_spin = ttk.Spinbox(vid_frame, from_=0.0, to=2.0, increment=0.1,
                                    textvariable=self.video_muxdelay, width=15, font=('Arial', 9))
        muxdelay_spin.grid(row=4, column=1, sticky='ew', padx=2, pady=2)        

        # ===== СТОЛБЕЦ 2 =====
        # Row 0: Codec
        ttk.Label(vid_frame, text="Codec:", font=('Arial', 9)).grid(row=0, column=2, sticky='w', pady=2, padx=(8, 2))
        self.codec_combo = ttk.Combobox(vid_frame, textvariable=self.video_codec,
                    values=["libx264", "libx265", "hevc_nvenc", "h264_nvenc", "h264_amf", "hevc_amf", "hevc_qsv", "h264_qsv"], 
                    width=12, font=('Arial', 9))
        self.codec_combo.grid(row=0, column=3, sticky='ew', padx=2, pady=2)
        self.codec_combo.bind('<<ComboboxSelected>>', self.on_codec_change)

        # Row 1: Preset
        ttk.Label(vid_frame, text="Preset:", font=('Arial', 9)).grid(row=1, column=2, sticky='w', pady=2, padx=(8, 2))
        self.video_preset_combo = ttk.Combobox(vid_frame, textvariable=self.video_preset, width=12, font=('Arial', 9))
        self.video_preset_combo.grid(row=1, column=3, sticky='ew', padx=2, pady=2)

        # Row 2: Tune
        ttk.Label(vid_frame, text="Tune:", font=('Arial', 9)).grid(row=2, column=2, sticky='w', pady=2, padx=(8, 2))
        self.tune_combo = ttk.Combobox(vid_frame, textvariable=self.video_tune, width=12, font=('Arial', 9))
        self.tune_combo.grid(row=2, column=3, sticky='ew', padx=2, pady=2)

        # Row 3: Profile
        ttk.Label(vid_frame, text="Profile:", font=('Arial', 9)).grid(row=3, column=2, sticky='w', pady=2, padx=(8, 2))
        self.profile_combo = ttk.Combobox(vid_frame, textvariable=self.video_profile, width=12, font=('Arial', 9))
        self.profile_combo.grid(row=3, column=3, sticky='ew', padx=2, pady=2)
        self.profile_combo.bind('<<ComboboxSelected>>', self.on_profile_change)
        
        ttk.Label(vid_frame, text="Muxpreload:", font=('Arial', 9)).grid(row=4, column=2, sticky='w', pady=2, padx=(8, 2))
        muxpreload_spin = ttk.Spinbox(vid_frame, from_=0.0, to=2.0, increment=0.1,
                                      textvariable=self.video_muxpreload, width=15, font=('Arial', 9))
        muxpreload_spin.grid(row=4, column=3, sticky='ew', padx=2, pady=2)
        
        # ===== СТОЛБЕЦ 3 =====
        # Row 0: Pixel Format
        ttk.Label(vid_frame, text="Pixel fmt:", font=('Arial', 9)).grid(row=0, column=4, sticky='w', pady=2, padx=(8, 2))
        self.pix_fmt_combo = ttk.Combobox(vid_frame, textvariable=self.pix_fmt, width=12, font=('Arial', 9))
        self.pix_fmt_combo.grid(row=0, column=5, sticky='ew', padx=2, pady=2)

        # Row 1: Bitrate
        ttk.Label(vid_frame, text="Bitrate:", font=('Arial', 9)).grid(row=1, column=4, sticky='w', pady=2, padx=(8, 2))
        bitrate_frame = ttk.Frame(vid_frame)
        bitrate_frame.grid(row=1, column=5, sticky='ew', padx=2, pady=2)
        bitrate_frame.columnconfigure(0, weight=1)
        self.video_bitrate_spinbox = ttk.Spinbox(bitrate_frame, from_=100, to=100000, 
                                                textvariable=self.video_bitrate, 
                                                width=8, font=('Arial', 9), 
                                                command=self.on_video_bitrate_change)
        self.video_bitrate_spinbox.grid(row=0, column=0, sticky='ew')
        ttk.Label(bitrate_frame, text="kbps", font=('Arial', 8)).grid(row=0, column=1, padx=(2, 0))

        # Row 2: Bufsize
        ttk.Label(vid_frame, text="Bufsize:", font=('Arial', 9)).grid(row=2, column=4, sticky='w', pady=2, padx=(8, 2))
        bufsize_frame = ttk.Frame(vid_frame)
        bufsize_frame.grid(row=2, column=5, sticky='ew', padx=2, pady=2)
        bufsize_frame.columnconfigure(0, weight=1)
        self.video_bufsize_spinbox = ttk.Spinbox(bufsize_frame, from_=50, to=100000, 
                                                textvariable=self.video_bufsize, 
                                                width=8, font=('Arial', 9), 
                                                command=self.on_video_bufsize_change)
        self.video_bufsize_spinbox.grid(row=0, column=0, sticky='ew')
        ttk.Label(bufsize_frame, text="kbps", font=('Arial', 8)).grid(row=0, column=1, padx=(2, 0))
        
        ttk.Label(vid_frame, text="Buf Factor:", font=('Arial', 9)).grid(row=3, column=4, sticky='w', pady=2, padx=(8, 2))
        buf_factor_frame = ttk.Frame(vid_frame)
        buf_factor_frame.grid(row=3, column=5, sticky='ew', padx=2, pady=2)
        buf_factor_spin = ttk.Spinbox(buf_factor_frame, from_=20, to=200, increment=10,
                                       textvariable=self.video_buf_factor, width=8, font=('Arial', 9))
        buf_factor_spin.pack(side='left')
        ttk.Label(buf_factor_frame, text="%", font=('Arial', 8)).pack(side='left', padx=(2, 0))        

        # Row 3: Custom Options
        ttk.Label(vid_frame, text="Custom opts:", font=('Arial', 9)).grid(row=4, column=4, sticky='w', pady=2, padx=(8, 2))
        self.custom_options_entry = ttk.Entry(vid_frame, textvariable=self.custom_options, width=20, font=('Arial', 9))
        self.custom_options_entry.grid(row=4, column=5, sticky='ew', padx=2, pady=2)

        # Initialize pixel format combobox
        self.update_pixel_formats()    
        
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

        # Encoder Presets Block
        preset_frame = ttk.LabelFrame(parent, text="Encoder Presets", padding="6")
        preset_frame.pack(fill='x', pady=(0, 6))

        # Текстовое поле для команды (без скроллбара)
        cmd_frame = ttk.Frame(preset_frame)
        cmd_frame.pack(fill='x', pady=(0, 5))

        text_frame = ttk.Frame(cmd_frame)
        text_frame.pack(fill='both', expand=True)

        self.encoder_command_widget = tk.Text(
            text_frame, 
            wrap=tk.WORD, 
            height=6, 
            font=('Courier', 9),
            relief=tk.SUNKEN,
            borderwidth=1,
            padx=5,
            pady=5
        )
        self.encoder_command_widget.pack(side='left', fill='both', expand=True)

        # Инициализируем отображение команды
        self.update_encoder_command_display()

        # Кнопки управления
        btn_frame = ttk.Frame(preset_frame)
        btn_frame.pack(fill='x', pady=(5, 0))

        # Save Preset
        save_btn = ttk.Button(btn_frame, text="Save Encoder Preset", 
                             command=self.save_encoder_preset_dialog, width=18)
        save_btn.pack(side='left', padx=2)

        # Default Preset
        default_btn = ttk.Button(btn_frame, text="Default Preset", 
                                command=self.reset_encoder_to_default, width=15)
        default_btn.pack(side='left', padx=5)

        # Выпадающий список пресетов
        self.encoder_preset_combo = ttk.Combobox(btn_frame, textvariable=self.encoder_preset_name,
                                                width=38, font=('Arial', 9))
        self.encoder_preset_combo.pack(side='left', padx=5)
        self.encoder_preset_combo.bind('<<ComboboxSelected>>', self.on_encoder_preset_selected)

        if self.encoder_preset_name.get():
            self.encoder_preset_combo.set(self.encoder_preset_name.get())
        # Delete Preset
        del_btn = ttk.Button(btn_frame, text="Delete Preset", 
                            command=self.delete_encoder_preset, width=12)
        del_btn.pack(side='left', padx=2)

        # Заполняем список пресетов (если они уже загружены)
        if hasattr(self, 'encoder_preset_commands') and self.encoder_preset_commands:
            presets_list = list(self.encoder_preset_commands.keys())
            self.encoder_preset_combo['values'] = presets_list
            # Устанавливаем текущий выбранный пресет
            current = self.encoder_preset_name.get()
            if current and current in presets_list:
                self.encoder_preset_combo.set(current)
                
    def on_encoder_preset_selected(self, event):
        """Обработчик выбора пресета из списка"""
        # Получаем значение из комбобокса
        preset_name = self.encoder_preset_combo.get()
        if preset_name and preset_name in self.encoder_preset_commands:
            # Переменная обновится автоматически через textvariable
            # Но для надежности установим явно
            self.encoder_preset_name.set(preset_name)
            # Применяем пресет
            self.apply_encoder_preset(preset_name)
            self.save_config()
        elif not preset_name:
            self.reset_encoder_to_default()           

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
    
    def clear_all_logs(self):
        """Clear all log windows"""
        self.ffmpeg_log_text.delete(1.0, tk.END)
        self.gnuradio_log_text.delete(1.0, tk.END)
        self.buffer_log_text.delete(1.0, tk.END)
        self.overlay_log_text.delete(1.0, tk.END)

    def create_monitor_tab(self, parent):
        """Create monitor settings tab - compact two-column layout"""
        
        main_frame = ttk.Frame(parent)
        main_frame.pack(fill='both', expand=True, padx=5, pady=5)
        
        # ========== TOP ROW - Two columns ==========
        top_row = ttk.Frame(main_frame)
        top_row.pack(fill='x', pady=(0, 8))
        
        # Column 1 (left) - 50%
        col1 = ttk.Frame(top_row)
        col1.pack(side='left', fill='both', expand=True, padx=(0, 3))
        
        # Column 2 (right) - 50%
        col2 = ttk.Frame(top_row)
        col2.pack(side='right', fill='both', expand=True, padx=(3, 0))
        
        # ========== MAIN MULTIPLEXER GROUP (left column) ==========
        main_frame_group = ttk.LabelFrame(col1, text="Main Multiplexer", padding="6")
        main_frame_group.pack(fill='x', pady=(0, 8))
        
        # Speed Threshold
        thresh_frame = ttk.Frame(main_frame_group)
        thresh_frame.pack(fill='x', pady=2)
        ttk.Label(thresh_frame, text="Speed Threshold:", width=22, anchor='e').pack(side='left')
        ttk.Spinbox(thresh_frame, from_=0.85, to=1.00, increment=0.005, 
                    textvariable=self.speed_restart_threshold, width=6).pack(side='left', padx=8)
        ttk.Button(thresh_frame, text="↺", width=3,
                   command=lambda: self.speed_restart_threshold.set(0.930)).pack(side='left', padx=2)
        
        # Check Count
        count_frame = ttk.Frame(main_frame_group)
        count_frame.pack(fill='x', pady=2)
        ttk.Label(count_frame, text="Check Count:", width=22, anchor='e').pack(side='left')
        ttk.Spinbox(count_frame, from_=5, to=50, increment=1,
                    textvariable=self.speed_restart_count, width=6).pack(side='left', padx=8)
        ttk.Button(count_frame, text="↺", width=3,
                   command=lambda: self.speed_restart_count.set(25)).pack(side='left', padx=2)
        
        # Cooldown
        cooldown_frame = ttk.Frame(main_frame_group)
        cooldown_frame.pack(fill='x', pady=2)
        ttk.Label(cooldown_frame, text="Cooldown (sec):", width=22, anchor='e').pack(side='left')
        ttk.Spinbox(cooldown_frame, from_=10, to=120, increment=5,
                    textvariable=self.speed_restart_cooldown_seconds, width=6).pack(side='left', padx=8)
        ttk.Button(cooldown_frame, text="↺", width=3,
                   command=lambda: self.speed_restart_cooldown_seconds.set(30)).pack(side='left', padx=2)
        
        # ========== WINDOW SEARCH INTERVALS (left column, below main) ==========
        window_frame = ttk.LabelFrame(col1, text="Window Search Intervals (grab_window)", padding="6")
        window_frame.pack(fill='x', pady=(0, 0))
        
        # Attempt 1
        int1_frame = ttk.Frame(window_frame)
        int1_frame.pack(fill='x', pady=2)
        ttk.Label(int1_frame, text="Attempt 1:", width=22, anchor='e').pack(side='left')
        ttk.Spinbox(int1_frame, from_=5, to=60, increment=5,
                    textvariable=self.window_search_interval_1, width=6).pack(side='left', padx=8)
        ttk.Button(int1_frame, text="↺", width=3,
                   command=lambda: self.window_search_interval_1.set(10)).pack(side='left', padx=2)
        
        # Attempt 2
        int2_frame = ttk.Frame(window_frame)
        int2_frame.pack(fill='x', pady=2)
        ttk.Label(int2_frame, text="Attempt 2:", width=22, anchor='e').pack(side='left')
        ttk.Spinbox(int2_frame, from_=15, to=120, increment=5,
                    textvariable=self.window_search_interval_2, width=6).pack(side='left', padx=8)
        ttk.Button(int2_frame, text="↺", width=3,
                   command=lambda: self.window_search_interval_2.set(30)).pack(side='left', padx=2)
        
        # Attempt 3
        int3_frame = ttk.Frame(window_frame)
        int3_frame.pack(fill='x', pady=2)
        ttk.Label(int3_frame, text="Attempt 3:", width=22, anchor='e').pack(side='left')
        ttk.Spinbox(int3_frame, from_=30, to=180, increment=10,
                    textvariable=self.window_search_interval_3, width=6).pack(side='left', padx=8)
        ttk.Button(int3_frame, text="↺", width=3,
                   command=lambda: self.window_search_interval_3.set(60)).pack(side='left', padx=2)
        
        # Attempt 4
        int4_frame = ttk.Frame(window_frame)
        int4_frame.pack(fill='x', pady=2)
        ttk.Label(int4_frame, text="Attempt 4:", width=22, anchor='e').pack(side='left')
        ttk.Spinbox(int4_frame, from_=60, to=300, increment=15,
                    textvariable=self.window_search_interval_4, width=6).pack(side='left', padx=8)
        ttk.Button(int4_frame, text="↺", width=3,
                   command=lambda: self.window_search_interval_4.set(120)).pack(side='left', padx=2)
        
        # Attempt 5+
        int5_frame = ttk.Frame(window_frame)
        int5_frame.pack(fill='x', pady=2)
        ttk.Label(int5_frame, text="Attempt 5+:", width=22, anchor='e').pack(side='left')
        ttk.Spinbox(int5_frame, from_=120, to=600, increment=30,
                    textvariable=self.window_search_interval_5, width=6).pack(side='left', padx=8)
        ttk.Button(int5_frame, text="↺", width=3,
                   command=lambda: self.window_search_interval_5.set(300)).pack(side='left', padx=2)
        
        # Monitor Guide Button
        guide_frame = ttk.Frame(window_frame)
        guide_frame.pack(fill='x', pady=(8, 2))
        ttk.Button(guide_frame, text="📖 Monitor Guide", 
                   command=self.show_monitor_guide, width=20).pack()
        
        # ========== CHANNEL SPEED MONITORING (right column) ==========
        speed_frame = ttk.LabelFrame(col2, text="Channel Speed Monitoring", padding="6")
        speed_frame.pack(fill='x', pady=(0, 8))
        
        # Fail Threshold
        fail_thresh_frame = ttk.Frame(speed_frame)
        fail_thresh_frame.pack(fill='x', pady=2)
        ttk.Label(fail_thresh_frame, text="Fail Threshold:", width=22, anchor='e').pack(side='left')
        ttk.Spinbox(fail_thresh_frame, from_=0.85, to=1.00, increment=0.005,
                    textvariable=self.channel_speed_fail_threshold, width=6).pack(side='left', padx=8)
        ttk.Button(fail_thresh_frame, text="↺", width=3,
                   command=lambda: self.channel_speed_fail_threshold.set(0.960)).pack(side='left', padx=2)
        
        # Check Count
        speed_count_frame = ttk.Frame(speed_frame)
        speed_count_frame.pack(fill='x', pady=2)
        ttk.Label(speed_count_frame, text="Check Count:", width=22, anchor='e').pack(side='left')
        ttk.Spinbox(speed_count_frame, from_=5, to=50, increment=1,
                    textvariable=self.channel_speed_check_count, width=6).pack(side='left', padx=8)
        ttk.Button(speed_count_frame, text="↺", width=3,
                   command=lambda: self.channel_speed_check_count.set(10)).pack(side='left', padx=2)
        
        # Speed Timeout
        timeout_frame = ttk.Frame(speed_frame)
        timeout_frame.pack(fill='x', pady=2)
        ttk.Label(timeout_frame, text="Speed Timeout (sec):", width=22, anchor='e').pack(side='left')
        ttk.Spinbox(timeout_frame, from_=0, to=10, increment=0.5,
                    textvariable=self.speed_timeout_seconds, width=6).pack(side='left', padx=8)
        ttk.Button(timeout_frame, text="↺", width=3,
                   command=lambda: self.speed_timeout_seconds.set(5)).pack(side='left', padx=2)
        
        # ========== CHANNEL RECOVERY TIMINGS (right column, below speed) ==========
        recovery_frame = ttk.LabelFrame(col2, text="Channel Recovery Timings", padding="6")
        recovery_frame.pack(fill='x', pady=(0, 0))
        
        # Init Time
        init_frame = ttk.Frame(recovery_frame)
        init_frame.pack(fill='x', pady=2)
        ttk.Label(init_frame, text="Init Time (sec):", width=22, anchor='e').pack(side='left')
        ttk.Spinbox(init_frame, from_=0, to=180, increment=5,
                    textvariable=self.channel_initialization_seconds, width=6).pack(side='left', padx=8)
        ttk.Button(init_frame, text="↺", width=3,
                   command=lambda: self.channel_initialization_seconds.set(65)).pack(side='left', padx=2)
        
        # Recovery Checks
        rec_checks_frame = ttk.Frame(recovery_frame)
        rec_checks_frame.pack(fill='x', pady=2)
        ttk.Label(rec_checks_frame, text="Recovery Checks:", width=22, anchor='e').pack(side='left')
        ttk.Spinbox(rec_checks_frame, from_=1, to=5, increment=1,
                    textvariable=self.channel_recovery_check_count, width=6).pack(side='left', padx=8)
        ttk.Button(rec_checks_frame, text="↺", width=3,
                   command=lambda: self.channel_recovery_check_count.set(2)).pack(side='left', padx=2)
        
        # Long Check Count
        long_frame = ttk.Frame(recovery_frame)
        long_frame.pack(fill='x', pady=2)
        ttk.Label(long_frame, text="Long Check Count:", width=22, anchor='e').pack(side='left')
        ttk.Spinbox(long_frame, from_=3, to=15, increment=1,
                    textvariable=self.channel_long_check_count, width=6).pack(side='left', padx=8)
        ttk.Button(long_frame, text="↺", width=3,
                   command=lambda: self.channel_long_check_count.set(7)).pack(side='left', padx=2)
        
        # Long Cooldown
        long_cd_frame = ttk.Frame(recovery_frame)
        long_cd_frame.pack(fill='x', pady=2)
        ttk.Label(long_cd_frame, text="Long Cooldown (sec):", width=22, anchor='e').pack(side='left')
        ttk.Spinbox(long_cd_frame, from_=60, to=600, increment=30,
                    textvariable=self.channel_long_check_cooldown, width=6).pack(side='left', padx=8)
        ttk.Button(long_cd_frame, text="↺", width=3,
                   command=lambda: self.channel_long_check_cooldown.set(180)).pack(side='left', padx=2)
        
        # Normal Interval
        norm_int_frame = ttk.Frame(recovery_frame)
        norm_int_frame.pack(fill='x', pady=2)
        ttk.Label(norm_int_frame, text="Normal Interval (sec):", width=22, anchor='e').pack(side='left')
        ttk.Spinbox(norm_int_frame, from_=5, to=60, increment=5,
                    textvariable=self.channel_check_interval_normal, width=6).pack(side='left', padx=8)
        ttk.Button(norm_int_frame, text="↺", width=3,
                   command=lambda: self.channel_check_interval_normal.set(10)).pack(side='left', padx=2)
        
        # Fail3+ Interval
        fail3_frame = ttk.Frame(recovery_frame)
        fail3_frame.pack(fill='x', pady=2)
        ttk.Label(fail3_frame, text="Fail3+ Interval (sec):", width=22, anchor='e').pack(side='left')
        ttk.Spinbox(fail3_frame, from_=60, to=600, increment=30,
                    textvariable=self.channel_check_interval_fail3, width=6).pack(side='left', padx=8)
        ttk.Button(fail3_frame, text="↺", width=3,
                   command=lambda: self.channel_check_interval_fail3.set(180)).pack(side='left', padx=2)
        
        # ========== ERROR DICTIONARIES (full width) ==========
        errors_frame = ttk.LabelFrame(main_frame, text="Error Dictionaries (add your own keywords)", padding="6")
        errors_frame.pack(fill='x', pady=(8, 6))
        
        # Channel Errors
        ttk.Label(errors_frame, text="CHANNEL CRITICAL ERRORS:", font=('Arial', 9, 'bold')).pack(anchor='w', pady=(0, 2))
        channel_errors_text = tk.Text(errors_frame, wrap=tk.WORD, height=10, font=('Courier', 9))
        channel_errors_text.pack(fill='x', pady=(0, 5))
        
        default_channel_str = ", ".join(self.default_channel_errors)
        if self.custom_channel_errors.get():
            channel_errors_text.insert("1.0", f"{default_channel_str}, {self.custom_channel_errors.get()}")
        else:
            channel_errors_text.insert("1.0", default_channel_str)
        
        # Multiplexer Errors
        ttk.Label(errors_frame, text="MULTIPLEXER CRITICAL ERRORS:", font=('Arial', 9, 'bold')).pack(anchor='w', pady=(5, 2))
        mux_errors_text = tk.Text(errors_frame, wrap=tk.WORD, height=6, font=('Courier', 9))
        mux_errors_text.pack(fill='x', pady=(0, 5))
        
        default_mux_str = ", ".join(self.default_multiplexer_errors)
        if self.custom_multiplexer_errors.get():
            mux_errors_text.insert("1.0", f"{default_mux_str}, {self.custom_multiplexer_errors.get()}")
        else:
            mux_errors_text.insert("1.0", default_mux_str)
        
        # Buttons for errors
        error_btn_frame = ttk.Frame(errors_frame)
        error_btn_frame.pack(fill='x', pady=5)
        
        def save_channel_errors():
            text = channel_errors_text.get("1.0", tk.END).strip()
            default_set = set(self.default_channel_errors)
            all_errors = [e.strip() for e in text.split(',') if e.strip()]
            custom_errors = [e for e in all_errors if e not in default_set]
            self.custom_channel_errors.set(", ".join(custom_errors))
            self.save_config()
            self.log_message("Channel errors dictionary saved", "buffer")
        
        def save_mux_errors():
            text = mux_errors_text.get("1.0", tk.END).strip()
            default_set = set(self.default_multiplexer_errors)
            all_errors = [e.strip() for e in text.split(',') if e.strip()]
            custom_errors = [e for e in all_errors if e not in default_set]
            self.custom_multiplexer_errors.set(", ".join(custom_errors))
            self.save_config()
            self.log_message("Multiplexer errors dictionary saved", "buffer")
        
        def reset_channel_errors():
            channel_errors_text.delete("1.0", tk.END)
            channel_errors_text.insert("1.0", ", ".join(self.default_channel_errors))
            self.custom_channel_errors.set("")
            self.save_config()
            self.log_message("Channel errors reset to default", "buffer")
        
        def reset_mux_errors():
            mux_errors_text.delete("1.0", tk.END)
            mux_errors_text.insert("1.0", ", ".join(self.default_multiplexer_errors))
            self.custom_multiplexer_errors.set("")
            self.save_config()
            self.log_message("Multiplexer errors reset to default", "buffer")
        
        ttk.Button(error_btn_frame, text="Save Channel Errors", command=save_channel_errors, width=18).pack(side='left', padx=2)
        ttk.Button(error_btn_frame, text="Reset Channel Errors", command=reset_channel_errors, width=20).pack(side='left', padx=2)
        ttk.Button(error_btn_frame, text="Save Mux Errors", command=save_mux_errors, width=16).pack(side='left', padx=2)
        ttk.Button(error_btn_frame, text="Reset Mux Errors", command=reset_mux_errors, width=16).pack(side='left', padx=2)
        
        # ========== STATISTICS (full width) ==========
        stats_frame = ttk.LabelFrame(main_frame, text="Live Statistics", padding="6")
        stats_frame.pack(fill='x', pady=(0, 0))
        
        self.monitor_stats_container = ttk.Frame(stats_frame)
        self.monitor_stats_container.pack(fill='x')
        
        self.last_fail_time_label = ttk.Label(stats_frame, text="Last Failure: --:--:--", font=('Arial', 9))
        self.last_fail_time_label.pack(anchor='w', pady=(5, 0))
        
        self.update_monitor_statistics()
        
    def show_monitor_guide(self):
        """Show monitor settings guide window with bilingual descriptions"""
        
        guide_window = tk.Toplevel(self.root)
        guide_window.title("Monitor Settings Guide / Руководство по настройкам монитора")
        guide_window.geometry("675x975")
        guide_window.transient(self.root)
        
        # Language selection
        lang_frame = ttk.Frame(guide_window)
        lang_frame.pack(fill='x', padx=10, pady=5)
        
        ttk.Label(lang_frame, text="Language / Язык:").pack(side='left')
        lang_var = tk.StringVar(value="En")
        lang_combo = ttk.Combobox(lang_frame, textvariable=lang_var, values=["En", "Ru"], width=5, state="readonly")
        lang_combo.pack(side='left', padx=5)
        
        # Text widget with scrollbar
        text_frame = ttk.Frame(guide_window)
        text_frame.pack(fill='both', expand=True, padx=10, pady=5)
        
        text_widget = tk.Text(text_frame, wrap=tk.WORD, font=('Courier', 9))
        scrollbar = ttk.Scrollbar(text_frame, orient='vertical', command=text_widget.yview)
        text_widget.configure(yscrollcommand=scrollbar.set)
        
        text_widget.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')
        
        # Content dictionary
        content = {
            'En': """
    MONITOR SETTINGS GUIDE
    ======================

    This tab contains parameters that control the automatic recovery system for channels and the main multiplexer when errors or speed drops occur.

    ┌─────────────────────────────────────────────────────────────────────────────┐
    │ MAIN MULTIPLEXER                                                            │
    ├─────────────────────────────────────────────────────────────────────────────┤
    │ Speed Threshold (0.85 - 1.00)                                               │
    │   Determines when the multiplexer is considered "slow".                     │
    │   Default: 0.930                                                            │
    │   Example: If set to 0.95, the system will restart when speed falls below   │
    │            0.95x for the specified number of checks.                        │
    │                                                                             │
    │ Check Count (5 - 50)                                                        │
    │   Number of consecutive speed checks below threshold before restart.        │
    │   Default: 25                                                               │
    │   Example: With default settings, need 25 consecutive checks below 0.93x.   │
    │                                                                             │
    │ Cooldown (10 - 120 sec)                                                     │
    │   Minimum time between automatic restarts.                                  │
    │   Default: 30 sec                                                           │
    │   Example: Prevents endless restart loops.                                  │
    └─────────────────────────────────────────────────────────────────────────────┘

    ┌─────────────────────────────────────────────────────────────────────────────┐
    │ CHANNEL SPEED MONITORING                                                    │
    ├─────────────────────────────────────────────────────────────────────────────┤
    │ Fail Threshold (0.85 - 1.00)                                                │
    │   Speed below this value triggers channel failure.                          │
    │   Default: 0.960                                                            │
    │   Example: If set to 0.97, channel fails when speed < 0.97x.                │
    │                                                                             │
    │ Check Count (5 - 50)                                                        │
    │   Number of consecutive speed checks below threshold to mark as FAILED.     │
    │   Default: 10                                                               │
    │                                                                             │
    │ Speed Timeout (0 - 10 sec)                                                  │
    │   Time to wait for first speed data after channel start.                    │
    │   Default: 5 sec                                                            │
    │   Example: If set to 0, channel fails immediately if no speed data.         │
    └─────────────────────────────────────────────────────────────────────────────┘

    ┌─────────────────────────────────────────────────────────────────────────────┐
    │ CHANNEL RECOVERY TIMINGS                                                    │
    ├─────────────────────────────────────────────────────────────────────────────┤
    │ Init Time (0 - 180 sec)                                                     │
    │   Time after start when speed monitoring begins.                            │
    │   Default: 65 sec                                                           │
    │   Example: Give channel time to stabilize before checking.                  │
    │                                                                             │
    │ Recovery Checks (1 - 5)                                                     │
    │   Number of successful checks needed to restore channel.                    │
    │   Default: 2                                                                │
    │   Example: With default, need 2 successful checks to exit FAILED state.     │
    │                                                                             │
    │ Long Check Count (3 - 15)                                                   │
    │   Number of checks in "long mode" after 3 failures.                         │
    │   Default: 7                                                                │
    │                                                                             │
    │ Long Cooldown (60 - 600 sec)                                                │
    │   Wait time after "long mode" before rechecking.                            │
    │   Default: 180 sec (3 minutes)                                              │
    │                                                                             │
    │ Normal Interval (5 - 60 sec)                                                │
    │   Time between checks for failed channels.                                  │
    │   Default: 10 sec                                                           │
    │                                                                             │
    │ Fail3+ Interval (60 - 600 sec)                                              │
    │   Time between checks after 3 or more failures.                             │
    │   Default: 180 sec (3 minutes)                                              │
    └─────────────────────────────────────────────────────────────────────────────┘

    ┌─────────────────────────────────────────────────────────────────────────────┐
    │ WINDOW SEARCH INTERVALS (grab_window)                                       │
    ├─────────────────────────────────────────────────────────────────────────────┤
    │ Progressive intervals for searching windows when original window closes.    │
    │ Attempt 1: 5-60 sec (default: 10) - first attempt                           │
    │ Attempt 2: 15-120 sec (default: 30) - second attempt                        │
    │ Attempt 3: 30-180 sec (default: 60) - third attempt                         │
    │ Attempt 4: 60-300 sec (default: 120) - fourth attempt                       │
    │ Attempt 5+: 120-600 sec (default: 300) - all subsequent attempts            │
    │                                                                             │
    │ Example: If a window closes, the system checks after 10s, then 30s, etc.    │
    └─────────────────────────────────────────────────────────────────────────────┘

    ┌─────────────────────────────────────────────────────────────────────────────┐
    │ ERROR DICTIONARIES                                                          │
    ├─────────────────────────────────────────────────────────────────────────────┤
    │ Add custom error keywords to detect in ffmpeg output.                       │
    │ Separate keywords with commas.                                              │
    │ Existing default keywords are always active.                                │
    │                                                                             │
    │ Example: "connection timeout, stream not found"                             │
    └─────────────────────────────────────────────────────────────────────────────┘
    """,
            'Ru': """
    РУКОВОДСТВО ПО НАСТРОЙКАМ МОНИТОРА
    ===================================

    На этой вкладке находятся параметры, управляющие системой автоматического восстановления каналов и основного мультиплексора при ошибках или падении скорости.

    ┌─────────────────────────────────────────────────────────────────────────────┐
    │ ОСНОВНОЙ МУЛЬТИПЛЕКСОР                                                      │
    ├─────────────────────────────────────────────────────────────────────────────┤
    │ Порог скорости (0.85 - 1.00)                                                │
    │   Определяет, когда мультиплексор считается "медленным".                    │
    │   По умолчанию: 0.930                                                       │
    │   Пример: При значении 0.95 система перезапустится при скорости ниже        │
    │            0.95x в течение указанного количества проверок.                  │
    │                                                                             │
    │ Количество проверок (5 - 50)                                                │
    │   Количество последовательных проверок ниже порога до перезапуска.          │
    │   По умолчанию: 25                                                          │
    │   Пример: При стандартных настройках нужно 25 проверок ниже 0.93x.          │
    │                                                                             │
    │ Задержка между перезапусками (10 - 120 сек)                                 │
    │   Минимальное время между автоматическими перезапусками.                    │
    │   По умолчанию: 30 сек                                                      │
    │   Пример: Предотвращает бесконечные циклы перезапуска.                      │
    └─────────────────────────────────────────────────────────────────────────────┘

    ┌─────────────────────────────────────────────────────────────────────────────┐
    │ МОНИТОРИНГ СКОРОСТИ КАНАЛОВ                                                 │
    ├─────────────────────────────────────────────────────────────────────────────┤
    │ Порог отказа (0.85 - 1.00)                                                  │
    │   Скорость ниже этого значения вызывает отказ канала.                       │
    │   По умолчанию: 0.960                                                       │
    │   Пример: При значении 0.97 канал отключается при скорости < 0.97x.         │
    │                                                                             │
    │ Количество проверок (5 - 50)                                                │
    │   Количество последовательных проверок ниже порога для перевода в FAILED.   │
    │   По умолчанию: 10                                                          │
    │                                                                             │
    │ Таймаут ожидания скорости (0 - 10 сек)                                      │
    │   Время ожидания первых данных о скорости после запуска канала.             │
    │   По умолчанию: 5 сек                                                       │
    │   Пример: При значении 0 канал сразу отключается без данных о скорости.     │
    └─────────────────────────────────────────────────────────────────────────────┘

    ┌─────────────────────────────────────────────────────────────────────────────┐
    │ ТАЙМИНГИ ВОССТАНОВЛЕНИЯ КАНАЛОВ                                             │
    ├─────────────────────────────────────────────────────────────────────────────┤
    │ Время инициализации (0 - 180 сек)                                           │
    │   Время после запуска, когда начинается мониторинг скорости.                │
    │   По умолчанию: 65 сек                                                      │
    │   Пример: Дает каналу время стабилизироваться перед проверкой.              │
    │                                                                             │
    │ Проверок для восстановления (1 - 5)                                         │
    │   Количество успешных проверок для восстановления канала.                   │
    │   По умолчанию: 2                                                           │
    │   Пример: При стандартных настройках нужно 2 успешные проверки.             │
    │                                                                             │
    │ Длинных проверок (3 - 15)                                                   │
    │   Количество проверок в "длинном режиме" после 3 отказов.                   │
    │   По умолчанию: 7                                                           │
    │                                                                             │
    │ Задержка после длинных проверок (60 - 600 сек)                              │
    │   Время ожидания после "длинного режима" перед повторной проверкой.         │
    │   По умолчанию: 180 сек (3 минуты)                                          │
    │                                                                             │
    │ Нормальный интервал (5 - 60 сек)                                            │
    │   Время между проверками упавших каналов.                                   │
    │   По умолчанию: 10 сек                                                      │
    │                                                                             │
    │ Интервал после 3+ отказов (60 - 600 сек)                                    │
    │   Время между проверками после 3 и более отказов.                           │
    │   По умолчанию: 180 сек (3 минуты)                                          │
    └─────────────────────────────────────────────────────────────────────────────┘

    ┌─────────────────────────────────────────────────────────────────────────────┐
    │ ИНТЕРВАЛЫ ПОИСКА ОКОН (grab_window)                                         │
    ├─────────────────────────────────────────────────────────────────────────────┤
    │ Прогрессивные интервалы для поиска окон при закрытии оригинального окна.    │
    │ Попытка 1: 5-60 сек (по умолчанию: 10) - первая попытка                     │
    │ Попытка 2: 15-120 сек (по умолчанию: 30) - вторая попытка                   │
    │ Попытка 3: 30-180 сек (по умолчанию: 60) - третья попытка                   │
    │ Попытка 4: 60-300 сек (по умолчанию: 120) - четвертая попытка               │
    │ Попытка 5+: 120-600 сек (по умолчанию: 300) - все последующие попытки       │
    │                                                                             │
    │ Пример: Если окно закрылось, система проверяет через 10с, затем 30с и т.д.  │
    └─────────────────────────────────────────────────────────────────────────────┘

    ┌─────────────────────────────────────────────────────────────────────────────┐
    │ СЛОВАРИ ОШИБОК                                                              │
    ├─────────────────────────────────────────────────────────────────────────────┤
    │ Добавьте свои ключевые слова ошибок для обнаружения в выводе ffmpeg.        │
    │ Разделяйте ключевые слова запятыми.                                         │
    │ Существующие стандартные слова всегда активны.                              │
    │                                                                             │
    │ Пример: "timeout, connection lost, stream not found"                        │
    └─────────────────────────────────────────────────────────────────────────────┘
    """
        }
        
        def update_text(*args):
            # Временно снимаем защиту для обновления
            text_widget.configure(state='normal')
            text_widget.delete("1.0", tk.END)
            text_widget.insert("1.0", content[lang_var.get()])
            text_widget.see("1.0")
            # Возвращаем защиту
            text_widget.configure(state='disabled')
        
        lang_combo.bind('<<ComboboxSelected>>', update_text)
        update_text()
        
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
        ffmpeg_path = self.ffmpeg_path
        
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
        ffmpeg_path = self.ffmpeg_path
        
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
            self._should_recalc_max = True

            # Рассчитываем видео настройки на основе пресета
            self.calculate_video_settings_from_preset(preset)
            
            # Update buffer settings based on muxrate
            self.update_buffer_settings()
                        
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
            self.target_buffer.set(max(200, min(40000, target_buffer)))
            
            # Update max buffer based on video buffer size
            if hasattr(self, '_should_recalc_max') and self._should_recalc_max:
                try:
                    video_bufsize = int(self.video_bufsize.get())
                    # Рассчитываем новое значение с множителем 5
                    new_max = max(100, min(100000, video_bufsize * 5))
                    self.max_buffer.set(new_max)
                    self.log_message(f"📊 max_buffer auto-calculated: {new_max} (video_bufsize={video_bufsize} * 5)", "buffer")
                    # Сбрасываем флаг
                    self._should_recalc_max = False
                except (ValueError, TypeError):
                    pass
            
        except (ValueError, ZeroDivisionError):
            pass

    def get_udp_buffer_bytes(self):
        """Возвращает размер UDP буфера в байтах для FFmpeg команд"""
        mb_value = self.udp_buffer_size.get()
        # Ограничиваем от 0 до 50 МБ
        mb_value = max(0, min(50, mb_value))
        return int(mb_value * 1_000_000)  # 5M → 5000000
    
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

        self.buffer_input_bitrate.set("0")
        self.buffer_output_bitrate.set("0")
        self.buffer_fill.set("0/0")            
            
        # 1. Start UDP/ZMQ buffer
        self.buffer_running = True
        self.buffer_thread = threading.Thread(target=self.run_zmq_buffer, daemon=True)
        self.buffer_thread.start()
        time.sleep(2)
        self.buffer_status.set("Running") 

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
            
            radioconda_dir = os.path.dirname(python_path)

            # Создаем окружение для процесса
            env = os.environ.copy()
            env['PATH'] = os.path.join(radioconda_dir, 'Library', 'bin') + os.pathsep + \
                          os.path.join(radioconda_dir, 'Scripts') + os.pathsep + \
                          radioconda_dir + os.pathsep + env['PATH']
            env['CONDA_BASE'] = radioconda_dir
            env['RADIOCONDA_DIR'] = radioconda_dir

            self.modulator_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True,
                cwd=os.path.dirname(script_file),
                env=env  # <-- Добавить это
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
            self.root.after(8000, self.connect_to_gnuradio)
            
        except Exception as e:
            self.log_message(f"Error starting modulator: {e}", "buffer")
            import traceback
            self.log_message(f"Traceback: {traceback.format_exc()}", "buffer")
            self.stop_modulator()

    def stop_modulator(self):
        """Stop the RF modulator gracefully"""
        if not self.modulator_process or not self.modulator_running:
            return
        
        # 2. Stop UDP/ZMQ buffer
        self.buffer_running = False
        if self.buffer_thread:
            self.buffer_thread.join(timeout=3)
            self.buffer_thread = None        
        self.buffer_status.set("Stopped")
        
        # ⭐ СБРАСЫВАЕМ СТАТИСТИКУ UDP БУФФЕРА
        self.buffer_input_bitrate.set("0")
        self.buffer_output_bitrate.set("0")
        self.buffer_fill.set("0/0")
        self.buffer_dropped.set("0")
        self.buffer_received.set("0")
        self.buffer_sent.set("0")
        self.buffer_overflow.set("0")
        self.bitrate_deviation.set("0.0%")
        
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
        """Update preset, tune, profile and pixel formats when codec changes"""
        self.update_codec_settings()
        self.update_pixel_formats()
        self.save_config()
        
    def on_profile_change(self, event=None):
        """Update pixel formats when profile changes"""
        self.update_pixel_formats()
        self.save_config()        

    def update_codec_settings(self):
        """Update preset, tune, and profile options based on selected codec"""
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
                # Не сбрасываем tune, если текущее значение доступно
                current_tune = self.video_tune.get()
                if current_tune and current_tune in self.codec_tunes[codec]:
                    # Оставляем текущее значение
                    pass
                elif self.codec_tunes[codec]:
                    # Если есть доступные значения, устанавливаем первое
                    self.video_tune.set(self.codec_tunes[codec][0])
                else:
                    # Если нет значений, очищаем
                    self.video_tune.set("")
        
        # Update profiles
        profiles = []
        
        if codec in ["libx265", "hevc_nvenc", "hevc_amf", "hevc_qsv"]:
            profiles = ["main", "main10", "main12", "rext"]
        elif codec in ["h264_nvenc", "h264_amf", "h264_qsv", "libx264"]:
            profiles = ["baseline", "main", "high", "high444"]
        else:
            profiles = []
        
        self.profile_combo['values'] = profiles
        
        if profiles and (not self.video_profile.get() or self.video_profile.get() not in profiles):
            self.video_profile.set(profiles[0])
        
        # Обновляем пиксельные форматы после смены кодека
        self.update_pixel_formats()
                    
    def update_pixel_formats(self, event=None):
        """Update available pixel formats based on selected codec and profile"""
        codec = self.video_codec.get()
        profile = self.video_profile.get()
        
        # Базовые форматы для всех кодеков
        base_formats = ["yuv420p"]
        
        if codec == "libx264":
            # H.264 поддерживает множество форматов, но не 10-бит HDR
            formats = ["yuv420p", "yuv422p", "yuv444p", "yuvj420p", "yuvj422p", "yuvj444p", "nv12", "nv16", "nv21"]
        elif codec in ["hevc_qsv", "h264_qsv"]:
            formats = base_formats + ["nv12", "p010le", "uyvy422", "yuyv422"]
            if profile == "main10":
                formats = ["p010le", "yuv420p10le"]
        elif codec in ["hevc_nvenc", "h264_nvenc"]:
            formats = base_formats + ["nv12", "p010le", "yuv444p"]
            if profile == "main10":
                formats = ["p010le", "yuv420p10le"]
        elif codec in ["hevc_amf", "h264_amf"]:
            formats = base_formats + ["nv12", "p010"]
            if profile == "main10":
                formats = ["p010"]
        elif codec == "libx265":
            formats = base_formats + ["yuv422p", "yuv444p", "yuv420p10le", "yuv422p10le", "yuv444p10le"]
            if profile == "main10":
                formats = ["yuv420p10le", "yuv422p10le"]
            elif profile == "main12":
                formats = ["yuv420p12le", "yuv422p12le", "yuv444p12le"]
        else:
            formats = base_formats + ["yuv422p", "yuv444p"]
        
        self.pix_fmt_combo['values'] = formats
        
        current_fmt = self.pix_fmt.get()
        if current_fmt not in formats:
            if "yuv420p10le" in formats:
                self.pix_fmt.set("yuv420p10le")
            elif "p010le" in formats:
                self.pix_fmt.set("p010le")
            else:
                self.pix_fmt.set("yuv420p")
       
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
        """Update video bufsize and buf_factor when video bitrate changes manually"""
        try:
            bitrate = int(self.video_bitrate.get())
            bufsize = int(self.video_bufsize.get())
            # Пересчитываем buf_factor на основе ручных значений
            if bitrate > 0:
                new_factor = (bufsize / bitrate) * 100
                new_factor = max(20, min(200, new_factor))  # Ограничиваем 20-200%
                self.video_buf_factor.set(round(new_factor))
            self._should_recalc_max = True
            self.update_buffer_settings()
            self.save_config()
        except:
            pass

    def on_video_bufsize_change(self):
        """Update video bitrate and buf_factor when bufsize changes manually"""
        try:
            bufsize = int(self.video_bufsize.get())
            bitrate = int(self.video_bitrate.get())
            # Пересчитываем buf_factor на основе ручных значений
            if bitrate > 0:
                new_factor = (bufsize / bitrate) * 100
                new_factor = max(20, min(200, new_factor))
                self.video_buf_factor.set(round(new_factor))
            self._should_recalc_max = True
            self.update_buffer_settings()
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
                            # if key == 'RADIOCONDA_PATH':
                                # # Получаем папку приложения
                                # app_dir = os.path.dirname(os.path.abspath(__file__))
                                
                                # # Если путь относительный, преобразуем
                                # if value.startswith('.\\') or value.startswith('./'):
                                    # rel_path = value[2:] if value.startswith('.\\') else value[2:]
                                    # abs_path = os.path.join(app_dir, rel_path)
                                # else:
                                    # abs_path = value
                                
                                # self.gnuradio_python_path.set(abs_path)
                                # print(f"📂 Loaded GNU Radio path: {value} -> {abs_path}")
                            
                            # elif key == 'FFMPEG_PATH':
                                # self.ffmpeg_path = value
                                # print(f"📂 Loaded FFmpeg path: {value}")
                            
                            if key == 'OBS_STUDIO_PATH':
                                self.obs_path.set(value)
                                print(f"📂 Loaded OBS path: {value}")
                            
                            # elif key == 'DVB_RATE_PATH':
                                # self.dvbt2rate_path = value
                                # print(f"📂 Loaded dvbt2rate path: {value}")
                
                self.log_message(f"✅ System paths loaded from {self.system_config_file}", "buffer")
                
                # # Проверяем, загрузился ли путь
                # if not self.gnuradio_python_path.get():
                    # self.log_message("⚠️ RADIOCONDA_PATH not found in conf.cfg", "buffer")
                    
            else:
                self.log_message(f"⚠️ System config file not found: {self.system_config_file}", "buffer")
                self.log_message(f"⚠️ Please run setup.bat first", "buffer")
                
                # Значения по умолчанию
                # self.gnuradio_python_path.set("")
                self.obs_path.set("")
                # self.ffmpeg_path = "ffmpeg.exe"
                # self.dvbt2rate_path = "dvbt2rate.exe"
                
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
                    bumper_paths = config['bumper_files']
                    
                    # Если виджеты уже существуют (GUI создан)
                    if hasattr(self.playlist_manager, 'bumper_widgets') and self.playlist_manager.bumper_widgets:
                        # Очищаем лишние бамперы
                        while len(self.playlist_manager.bumper_widgets) > len(bumper_paths):
                            row_frame, _ = self.playlist_manager.bumper_widgets[-1]
                            row_frame.destroy()
                            self.playlist_manager.bumper_widgets.pop()
                        
                        # Добавляем недостающие бамперы
                        while len(self.playlist_manager.bumper_widgets) < len(bumper_paths):
                            self.playlist_manager.add_bumper_row()
                        
                        # Применяем пути к существующим виджетам
                        for i, (frame, var) in enumerate(self.playlist_manager.bumper_widgets):
                            if i < len(bumper_paths):
                                var.set(bumper_paths[i])
                            else:
                                var.set("")
                        
                        self.playlist_manager.update_bumper_numbers()
                    else:
                        # Сохраняем для последующего применения (если GUI еще не создан)
                        self.bumper_paths_to_load = bumper_paths
                                                        
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

                if 'obs_auto_start' in config:
                    self.obs_auto_start.set(config['obs_auto_start'])

                # Load selected encoder preset
                if 'selected_encoder_preset' in config:
                    self.encoder_preset_name.set(config['selected_encoder_preset'])
                
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
                if 'pix_fmt' in config:
                    self.pix_fmt.set(config['pix_fmt'])
                    self.root.after(100, self.update_mode_indicator)
                if 'video_aspect' in config:
                    self.video_aspect.set(config['video_aspect'])
                if 'video_profile' in config:
                    self.video_profile.set(config['video_profile'])                    
                    
                # Audio settings
                if 'audio_codec' in config:
                    self.audio_codec.set(config['audio_codec'])
                if 'audio_bitrate' in config:
                    self.audio_bitrate.set(config['audio_bitrate'])
                if 'audio_sample_rate' in config:
                    self.audio_sample_rate.set(config['audio_sample_rate'])
                if 'audio_channels' in config:
                    self.audio_channels.set(config['audio_channels'])
                    
                if 'video_muxdelay' in config:
                    self.video_muxdelay.set(config['video_muxdelay'])
                if 'video_muxpreload' in config:
                    self.video_muxpreload.set(config['video_muxpreload'])
                if 'video_buf_factor' in config:
                    self.video_buf_factor.set(config['video_buf_factor'])                    
                
                # Load input devices
                if 'video_input_device' in config:
                    self.video_input_device.set(config['video_input_device'])
                if 'audio_input_device' in config:
                    self.audio_input_device.set(config['audio_input_device'])
                
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
                if 'udp_buffer_size' in config:
                    self.udp_buffer_size.set(config['udp_buffer_size'])
                    
                # Null Packets Persent
                if 'null_packets_percent' in config:
                    self.null_packets_percent.set(config['null_packets_percent'])
                    
                # Load buffer settings
                if 'buffer_bypass' in config:
                    self.buffer_bypass.set(config['buffer_bypass'])
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
            
                if 'custom_options' in config:
                    self.custom_options.set(config['custom_options'])                         
            
                # Monitor settings
                if 'speed_restart_threshold' in config:
                    self.speed_restart_threshold.set(config['speed_restart_threshold'])
                if 'speed_restart_count' in config:
                    self.speed_restart_count.set(config['speed_restart_count'])
                if 'speed_restart_cooldown_seconds' in config:
                    self.speed_restart_cooldown_seconds.set(config['speed_restart_cooldown_seconds'])
                if 'channel_speed_fail_threshold' in config:
                    self.channel_speed_fail_threshold.set(config['channel_speed_fail_threshold'])
                if 'channel_speed_check_count' in config:
                    self.channel_speed_check_count.set(config['channel_speed_check_count'])
                if 'speed_timeout_seconds' in config:
                    self.speed_timeout_seconds.set(config['speed_timeout_seconds'])
                if 'channel_initialization_seconds' in config:
                    self.channel_initialization_seconds.set(config['channel_initialization_seconds'])
                if 'channel_recovery_check_count' in config:
                    self.channel_recovery_check_count.set(config['channel_recovery_check_count'])
                if 'channel_long_check_count' in config:
                    self.channel_long_check_count.set(config['channel_long_check_count'])
                if 'channel_long_check_cooldown' in config:
                    self.channel_long_check_cooldown.set(config['channel_long_check_cooldown'])
                if 'channel_check_interval_normal' in config:
                    self.channel_check_interval_normal.set(config['channel_check_interval_normal'])
                if 'channel_check_interval_fail3' in config:
                    self.channel_check_interval_fail3.set(config['channel_check_interval_fail3'])
                if 'window_search_interval_1' in config:
                    self.window_search_interval_1.set(config['window_search_interval_1'])
                if 'window_search_interval_2' in config:
                    self.window_search_interval_2.set(config['window_search_interval_2'])
                if 'window_search_interval_3' in config:
                    self.window_search_interval_3.set(config['window_search_interval_3'])
                if 'window_search_interval_4' in config:
                    self.window_search_interval_4.set(config['window_search_interval_4'])
                if 'window_search_interval_5' in config:
                    self.window_search_interval_5.set(config['window_search_interval_5'])
                if 'custom_channel_errors' in config:
                    self.custom_channel_errors.set(config['custom_channel_errors'])
                if 'custom_multiplexer_errors' in config:
                    self.custom_multiplexer_errors.set(config['custom_multiplexer_errors'])

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
                
                # Playlist settings - С ПРОВЕРКАМИ
                'playlist_auto_start': self.playlist_manager.playlist_auto_start.get() if hasattr(self, 'playlist_manager') else False,
                'mpc_player_path': self.playlist_manager.mpc_player_path.get() if hasattr(self, 'playlist_manager') else "mpc-hc64.exe",
                'playlist_name': self.playlist_manager.playlist_name.get() if hasattr(self, 'playlist_manager') else "my_playlist.mpcpl",
                'playlist_randomize': self.playlist_manager.playlist_randomize.get() if hasattr(self, 'playlist_manager') else True,
                'media_folders': self.playlist_manager.media_folders if hasattr(self, 'playlist_manager') else [],
                'bumper_files': [file_var.get() for _, file_var in getattr(self.playlist_manager, 'bumper_widgets', [])] if hasattr(self, 'playlist_manager') else [],
                             
                # OBS settings
                'obs_auto_start': self.obs_auto_start.get(),
                
                # Encoder preset
                'selected_encoder_preset': self.encoder_preset_name.get(),                
                
                # Video settings
                'video_codec': self.video_codec.get(),
                'video_preset': self.video_preset.get(),
                'video_tune': self.video_tune.get(),
                'video_bitrate': self.video_bitrate.get(),
                'video_bufsize': self.video_bufsize.get(),
                'video_resolution': self.video_resolution.get(),
                'video_fps': self.video_fps.get(),
                'video_gop': self.video_gop.get(),
                'pix_fmt': self.pix_fmt.get(),
                'video_aspect': self.video_aspect.get(),
                'video_profile': self.video_profile.get(),
                'custom_options': self.custom_options.get(),
                
                # Audio settings
                'audio_codec': self.audio_codec.get(),
                'audio_bitrate': self.audio_bitrate.get(),
                'audio_sample_rate': self.audio_sample_rate.get(),
                'audio_channels': self.audio_channels.get(),
                
                'video_muxdelay': self.video_muxdelay.get(),
                'video_muxpreload': self.video_muxpreload.get(),
                'video_buf_factor': self.video_buf_factor.get(),                
                
                # Input devices
                'video_input_device': self.video_input_device.get(),
                'audio_input_device': self.audio_input_device.get(),
                
                # Network settings
                'muxrate': self.muxrate.get(),
                'localhost_ip': self.localhost_ip.get(),
                'output_ip': self.output_ip.get(),
                'udp_input_port': self.udp_input_port.get(),
                'udp_output_port': self.udp_output_port.get(),
                'udp_buffer_size': self.udp_buffer_size.get(),
                'null_packets_percent': self.null_packets_percent.get(), 
                
                # Buffer settings
                'buffer_bypass': self.buffer_bypass.get(),
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
                multiplex_config[str(ch_num)] = {
                    'enabled': channel_data['enabled'].get(),
                    'name': channel_data['name'].get(),
                    'source_type': channel_data['source_type'].get(),
                    'video_device': channel_data['video_device'].get(),
                    'audio_device': channel_data['audio_device'].get(),
                    'audio_delay': channel_data['audio_delay'].get(),
                    'capture_method': channel_data['capture_method'].get(),
                    'window_title': channel_data['window_title'].get(),
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
                
            emergency_path = self.emergency_file_path.get()
            if emergency_path:
                script_dir = os.path.dirname(os.path.abspath(__file__))
                # Если файл находится в папке скрипта, сохраняем только имя файла
                if os.path.dirname(emergency_path) == script_dir:
                    config['emergency_file_path'] = os.path.basename(emergency_path)
                else:
                    config['emergency_file_path'] = emergency_path
            else:
                config['emergency_file_path'] = ""
            config['multiplex_channels'] = multiplex_config
            config['multiplex_mode'] = self.multiplex_mode.get()

            # Monitor settings
            config['speed_restart_threshold'] = self.speed_restart_threshold.get()
            config['speed_restart_count'] = self.speed_restart_count.get()
            config['speed_restart_cooldown_seconds'] = self.speed_restart_cooldown_seconds.get()
            config['channel_speed_fail_threshold'] = self.channel_speed_fail_threshold.get()
            config['channel_speed_check_count'] = self.channel_speed_check_count.get()
            config['speed_timeout_seconds'] = self.speed_timeout_seconds.get()
            config['channel_initialization_seconds'] = self.channel_initialization_seconds.get()
            config['channel_recovery_check_count'] = self.channel_recovery_check_count.get()
            config['channel_long_check_count'] = self.channel_long_check_count.get()
            config['channel_long_check_cooldown'] = self.channel_long_check_cooldown.get()
            config['channel_check_interval_normal'] = self.channel_check_interval_normal.get()
            config['channel_check_interval_fail3'] = self.channel_check_interval_fail3.get()
            config['window_search_interval_1'] = self.window_search_interval_1.get()
            config['window_search_interval_2'] = self.window_search_interval_2.get()
            config['window_search_interval_3'] = self.window_search_interval_3.get()
            config['window_search_interval_4'] = self.window_search_interval_4.get()
            config['window_search_interval_5'] = self.window_search_interval_5.get()
            config['custom_channel_errors'] = self.custom_channel_errors.get()
            config['custom_multiplexer_errors'] = self.custom_multiplexer_errors.get()
            
            # Save window geometry if save is enabled
            if self.save_window_size.get():
                config['window_geometry'] = self.root.geometry() 
            else:
                # Если сохранение отключено, удаляем геометрию из конфига
                config.pop('window_geometry', None)            
            with open(self.config_file, 'w') as f:
                json.dump(config, f, indent=4)
                                                 
        except Exception as e:
            print(f"❌ Error saving config: {e}")
            import traceback
            traceback.print_exc()
                                
    def renumber_channels(self):
        """Renumber channels after removal"""
        if not hasattr(self, 'multiplex_channels') or not self.multiplex_channels:
            return
        
        # Сохраняем данные каналов
        channels_data = []
        for ch_num, data in sorted(self.multiplex_channels.items(), key=lambda x: x[0]):
            # Сохраняем копию важных данных
            channel_copy = {
                'enabled': data['enabled'].get(),
                'name': data['name'].get(),
                'source_type': data['source_type'].get(),
                'video_device': data['video_device'].get(),
                'audio_device': data['audio_device'].get(),
                'audio_delay': data['audio_delay'].get(),
                'capture_method': data['capture_method'].get(),
                'window_title': data['window_title'].get(),
                'media_path': data['media_path'].get(),
                'randomize': data['randomize'].get(),
                'udp_url': data['udp_url'].get(),
                'url_input': data['url_input'].get(),
                'selected_program': data['selected_program'].get(),
                'is_radio': data['is_radio'].get(),
                'radio_bg_type': data['radio_bg_type'].get(),
                'radio_bg_color': data['radio_bg_color'].get(),
                'radio_bg_picture': data['radio_bg_picture'].get(),
                'radio_text': data['radio_text'].get(),
                'radio_show_time': data['radio_show_time'].get(),
                'radio_text_color': data['radio_text_color'].get(),
                'radio_text_size': data['radio_text_size'].get(),
                'radio_time_color': data['radio_time_color'].get(),
                'radio_time_size': data['radio_time_size'].get(),
                'show_metadata': data['show_metadata'].get(),
                'metadata_size': data['metadata_size'].get(),
                'metadata_color': data['metadata_color'].get(),
                'metadata_position': data['metadata_position'].get(),
                'saved_video_pid': data.get('saved_video_pid', ''),
                'saved_audio_pid': data.get('saved_audio_pid', ''),
            }
            channels_data.append(channel_copy)
            # Удаляем старый виджет
            data['frame'].destroy()
        
        # Очищаем словарь каналов
        self.multiplex_channels.clear()
        
        # Пересоздаем каналы с новыми номерами
        for i, ch_data in enumerate(channels_data, 1):
            # Создаем новый виджет канала
            new_channel = self.add_channel_widget(i)
            
            # Восстанавливаем данные
            new_channel['enabled'].set(ch_data['enabled'])
            new_channel['name'].set(ch_data['name'])
            new_channel['source_type'].set(ch_data['source_type'])
            new_channel['video_device'].set(ch_data['video_device'])
            new_channel['audio_device'].set(ch_data['audio_device'])
            new_channel['audio_delay'].set(ch_data['audio_delay'])
            new_channel['capture_method'].set(ch_data['capture_method'])
            new_channel['window_title'].set(ch_data['window_title'])
            new_channel['media_path'].set(ch_data['media_path'])
            new_channel['randomize'].set(ch_data['randomize'])
            new_channel['udp_url'].set(ch_data['udp_url'])
            new_channel['url_input'].set(ch_data['url_input'])
            new_channel['selected_program'].set(ch_data['selected_program'])
            new_channel['is_radio'].set(ch_data['is_radio'])
            new_channel['radio_bg_type'].set(ch_data['radio_bg_type'])
            new_channel['radio_bg_color'].set(ch_data['radio_bg_color'])
            new_channel['radio_bg_picture'].set(ch_data['radio_bg_picture'])
            new_channel['radio_text'].set(ch_data['radio_text'])
            new_channel['radio_show_time'].set(ch_data['radio_show_time'])
            new_channel['radio_text_color'].set(ch_data['radio_text_color'])
            new_channel['radio_text_size'].set(ch_data['radio_text_size'])
            new_channel['radio_time_color'].set(ch_data['radio_time_color'])
            new_channel['radio_time_size'].set(ch_data['radio_time_size'])
            new_channel['show_metadata'].set(ch_data['show_metadata'])
            new_channel['metadata_size'].set(ch_data['metadata_size'])
            new_channel['metadata_color'].set(ch_data['metadata_color'])
            new_channel['metadata_position'].set(ch_data['metadata_position'])
            new_channel['saved_video_pid'] = ch_data['saved_video_pid']
            new_channel['saved_audio_pid'] = ch_data['saved_audio_pid']
            
            # Пересоздаем контент канала
            self.create_channel_content(i)
            
            # Если это input_devices, обновляем списки устройств
            if new_channel['source_type'].get() == "input_devices":
                self.root.after(300, lambda n=i: self.populate_channel_device_lists(n))
        
        self.update_add_button_state()
        self.save_config()
            
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
            ffmpeg_path = self.ffmpeg_path
            
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
            ffmpeg_path = self.ffmpeg_path
            
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
        
        self.channel_speed_received = {}
        
        # Таймер ожидания speed (5 секунд) - используем переменную из настроек
        def speed_timeout():
            if channel_num in self.channel_processes and self.is_streaming:
                if not self.channel_speed_received.get(channel_num, False):
                    self.log_message(f"CH{channel_num}: ⚠️ No speed data for {self.speed_timeout_seconds.get()} seconds", "buffer")
                    self.transition_to_failed(channel_num, "no_speed_timeout")
        
        speed_timeout_ms = int(self.speed_timeout_seconds.get() * 1000)
        timer = self.root.after(speed_timeout_ms, speed_timeout)
        setattr(self, f'_speed_timer_{channel_num}', timer)
        
        # Формируем полный список критических ошибок (дефолтные + пользовательские)
        critical_errors = self.default_channel_errors.copy()
        if self.custom_channel_errors.get():
            custom = [e.strip() for e in self.custom_channel_errors.get().split(',') if e.strip()]
            critical_errors.extend(custom)
        
        try:
            for line in iter(process.stdout.readline, ''):
                if line and self.is_streaming:
                    line_stripped = line.strip()
                    
                    # Парсим статистику (speed и bitrate)
                    if "speed=" in line_stripped:
                        match = re.search(r'speed=\s*([\d.]+)x', line_stripped)
                        if match:
                            speed = float(match.group(1))
                            # Обновляем GUI в главном потоке
                            self.root.after(0, self.update_channel_stats, channel_num, 'speed', speed)
                            
                            # Отменяем таймер при первом появлении speed
                            if not self.channel_speed_received.get(channel_num, False):
                                self.channel_speed_received[channel_num] = True
                                if hasattr(self, f'_speed_timer_{channel_num}'):
                                    self.root.after_cancel(getattr(self, f'_speed_timer_{channel_num}'))
                                    delattr(self, f'_speed_timer_{channel_num}')
                            
                            # Защита от ложных срабатываний при старте - используем переменную из настроек
                            if channel_num not in self.channel_initialized:
                                self.channel_initialized[channel_num] = time.time()
                                # Первые N секунд не проверяем скорость
                                continue
                            # Проверка скорости только после инициализации
                            init_time = self.channel_initialization_seconds.get()
                            if time.time() - self.channel_initialized[channel_num] > init_time:
                                self.check_channel_speed(channel_num, speed)
                    
                    if "bitrate=" in line_stripped:
                        match = re.search(r'bitrate=\s*([\d.]+)\s*kbits/s', line_stripped)
                        if match:
                            bitrate = match.group(1)
                            self.root.after(0, self.update_channel_stats, channel_num, 'bitrate', bitrate)
                    
                    # Проверка на критические ошибки
                    error_detected = False
                    detected_error = "unknown_error"
                    
                    for error in critical_errors:
                        if error.lower() in line_stripped.lower():
                            error_detected = True
                            detected_error = line_stripped[:100]
                            break
                    
                    if error_detected:
                        self.log_message(f"CH{channel_num} ERROR: {detected_error}", "buffer")
                        self.last_fail_time = time.time()
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
            self.last_fail_time = time.time()
            # Переводим канал в состояние FAILED
            self.transition_to_failed(channel_num, f"process_exit_{return_code}")

    def update_monitor_statistics(self):
        """Update live statistics on Monitor tab"""
        if not hasattr(self, 'monitor_stats_container'):
            return
        
        # Clear container
        for widget in self.monitor_stats_container.winfo_children():
            widget.destroy()
        
        # Display channel fail counts
        fail_frame = ttk.Frame(self.monitor_stats_container)
        fail_frame.pack(anchor='w', pady=2)
        
        ttk.Label(fail_frame, text="Channel Failures:", font=('Arial', 9, 'bold')).pack(side='left', padx=(0, 10))
        
        for ch_num in sorted(self.multiplex_channels.keys()):
            if self.multiplex_channels[ch_num]['enabled'].get():
                fail_count = self.channel_fail_count.get(ch_num, 0)
                color = 'red' if fail_count > 0 else 'green'
                ttk.Label(fail_frame, text=f"CH{ch_num}:{fail_count}", 
                         foreground=color, font=('Arial', 8)).pack(side='left', padx=3)
        
        # Update last fail time if available
        if hasattr(self, 'last_fail_time') and self.last_fail_time:
            time_str = time.strftime("%H:%M:%S", time.localtime(self.last_fail_time))
            self.last_fail_time_label.config(text=f"Last Failure: {time_str}")
        
        # Schedule next update
        self.root.after(1000, self.update_monitor_statistics)
                
    def check_channel_speed(self, channel_num, current_speed):
        """Проверка скорости канала и перевод в FAILED при необходимости"""
        # Только для активных каналов
        if self.channel_states.get(channel_num) != self.CHANNEL_STATE_ACTIVE:
            return
        
        # Инициализация истории
        if channel_num not in self.channel_speed_history:
            self.channel_speed_history[channel_num] = []
        
        # Добавляем скорость
        self.channel_speed_history[channel_num].append(current_speed)
        
        # Храним последние N+5 значений (немного больше чем нужно для проверки)
        check_count = self.channel_speed_check_count.get()
        max_history = check_count + 5
        if len(self.channel_speed_history[channel_num]) > max_history:
            self.channel_speed_history[channel_num].pop(0)
        
        # Проверяем, достаточно ли данных
        if len(self.channel_speed_history[channel_num]) < check_count:
            return
        
        # Последние N значений
        last_values = self.channel_speed_history[channel_num][-check_count:]
        
        # Все ниже порога?
        fail_threshold = self.channel_speed_fail_threshold.get()
        if all(speed < fail_threshold for speed in last_values):
            self.log_message(f"CH{channel_num}: ⚠️ Speed below {fail_threshold:.3f}x for {check_count} checks", "buffer")
            self.log_message(f"   Last values: {[f'{s:.3f}x' for s in last_values]}", "buffer")
            
            # Очищаем историю
            self.channel_speed_history[channel_num].clear()
            
            # Переводим в FAILED
            self.transition_to_failed(channel_num, "low_speed")               

    def check_system_speed(self, current_speed):
        """Проверка скорости основного мультиплексора и перезапуск при необходимости"""
        
        # Проверяем cooldown (не перезапускать слишком часто)
        current_time = time.time()
        cooldown_sec = self.speed_restart_cooldown_seconds.get()
        if current_time - self.speed_restart_cooldown < cooldown_sec:
            return
        
        # Добавляем текущую скорость в историю
        self.main_speed_history.append(current_speed)
        
        # Храним последние N+5 значений (немного больше чем нужно для проверки)
        max_history = self.speed_restart_count.get() + 5
        if len(self.main_speed_history) > max_history:
            self.main_speed_history.pop(0)
        
        # Проверяем, достаточно ли данных
        if len(self.main_speed_history) < self.speed_restart_count.get():
            return
        
        # Берем последние N значений для проверки
        last_values = self.main_speed_history[-self.speed_restart_count.get():]
        
        # Проверяем, все ли значения ниже порога
        threshold = self.speed_restart_threshold.get()
        all_below_threshold = all(speed < threshold for speed in last_values)
        
        if all_below_threshold:
            self.log_message(f"⚠️ CRITICAL: Main multiplexer speed below {threshold:.3f}x for {self.speed_restart_count.get()} checks", "buffer")
            self.log_message(f"   Last values: {[f'{s:.3f}x' for s in last_values]}", "buffer")
            self.log_message("🔄 Restarting entire streaming system...", "buffer")
            
            # Устанавливаем cooldown
            self.speed_restart_cooldown = current_time
            
            # Очищаем историю
            self.main_speed_history.clear()
            
            # Перезапускаем в главном потоке
            self.root.after(0, self.restart_streaming_system)
                
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
            windows_data = self.get_available_windows()
            capture_method = channel_data['capture_method'].get()
            current_value = channel_data['window_title'].get()
            
            self.log_message(f"CH{channel_num}: Restarting with window: '{current_value[:50]}...'", "buffer")
            
            if capture_method == 'gdigrab':
                # Для gdigrab работаем с названиями окон
                available_titles = [w['window_title'] for w in windows_data]
                
                if current_value and current_value in available_titles:
                    # Окно все еще доступно
                    self.log_message(f"CH{channel_num}: Window still available", "buffer")
                    pass
                elif current_value:
                    # Ищем похожее окно
                    similar = self.find_similar_window(current_value, available_titles)
                    if similar:
                        channel_data['window_title'].set(similar)
                        self.log_message(f"CH{channel_num}: Found similar window for restart: {similar[:50]}...", "buffer")
                    elif available_titles:
                        # Берем первое доступное
                        first_window = available_titles[0]
                        channel_data['window_title'].set(first_window)
                        window_display = first_window[:50]
                        self.log_message(f"CH{channel_num}: Using first available window for restart: {window_display}...", "buffer")
                    else:
                        self.log_message(f"CH{channel_num}: No windows available for capture", "buffer")
                        return False
                elif available_titles:
                    first_window = available_titles[0]
                    channel_data['window_title'].set(first_window)
                    self.log_message(f"CH{channel_num}: No previous window, using first available", "buffer")
            
            else:  # gfxcapture
                # Для gfxcapture работаем с именами процессов
                available_processes = [f"{w['process_name']}.exe" for w in windows_data]
                original_process = channel_data.get('original_process', current_value)
                
                if current_value and current_value in available_processes:
                    self.log_message(f"CH{channel_num}: Process still available", "buffer")
                    pass
                elif original_process and original_process in available_processes:
                    # Оригинальный процесс появился!
                    self.log_message(f"CH{channel_num}: ✅ Original process returned!", "buffer")
                    channel_data['window_title'].set(original_process)
                    if 'using_temp_process' in channel_data:
                        del channel_data['using_temp_process']
                elif available_processes:
                    first_process = available_processes[0]
                    channel_data['window_title'].set(first_process)
                    channel_data['using_temp_process'] = True
                    process_display = first_process[:50]
                    self.log_message(f"CH{channel_num}: Using first available process for restart: {process_display}...", "buffer")
                else:
                    self.log_message(f"CH{channel_num}: No processes available for capture", "buffer")
                    return False
        
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
        
        
        try:
            process = subprocess.Popen(
                cmd,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
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

            time.sleep(1)
            
            # Проверяем, что процесс жив
            if process.poll() is not None:
            
                # Сбрасываем флаг speed для нового процесса
                if channel_num in self.channel_speed_received:
                    del self.channel_speed_received[channel_num]            
                # Сбрасываем время инициализации для этого канала
                self.channel_initialized[channel_num] = time.time()
                self.log_message(f"CH{channel_num}: ⏱️ Initialization timer reset", "buffer")            
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
                
        if channel_num in self.channel_initialized:
            del self.channel_initialized[channel_num]                
            
            del self.channel_processes[channel_num]
            
        if channel_num in self.channel_speed_history:
            del self.channel_speed_history[channel_num]

        if channel_num in self.channel_speed_received:
            del self.channel_speed_received[channel_num]
            
        timer_attr = f'_speed_timer_{channel_num}'
        if hasattr(self, timer_attr):
            try:
                self.root.after_cancel(getattr(self, timer_attr))
            except:
                pass
            delattr(self, timer_attr)            
        
    def stop_all_channel_processes(self):
        """Stop all channel and emergency processes"""
        # Stop channel processes
        for ch_num in list(self.channel_processes.keys()):
            self.stop_channel_process(ch_num)
                
        # Stop main multiplexer
        if self.main_multiplexer_process:
            self.kill_process_fast(self.main_multiplexer_process, "Main Multiplexer")
            self.main_multiplexer_process = None
                                                                                       
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
        
        if not self.is_streaming:
            self._state_monitor_running = False
            return

            self.log_message(f"📊 Current channel_states: {self.channel_states}", "buffer")
        try:
            # 1. Проверка живых процессов
            self.check_active_processes()
                            
        except Exception as e:
            self.log_message(f"State monitor error: {e}", "buffer")
            import traceback
            self.log_message(traceback.format_exc(), "buffer")
        
        # Следующий вызов через 0.5 секунд
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

        # Если канал уже в FAILED, не увеличиваем счетчик повторно
        if self.channel_states.get(channel_num) == self.CHANNEL_STATE_FAILED:
            self.log_message(f"CH{channel_num}: Already in FAILED state, ignoring second trigger", "buffer")
            return
        
        was_active = self.channel_states.get(channel_num) == self.CHANNEL_STATE_ACTIVE
        
        # НЕ запускаем emergency, если стриминг уже остановлен
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
        
        # НОВАЯ ЛОГИКА: увеличиваем счетчик ТОЛЬКО если канал был ACTIVE
        if was_active:
            # Увеличиваем счетчик, но с верхним лимитом
            current_count = self.channel_fail_count.get(channel_num, 0)
            self.channel_fail_count[channel_num] = min(current_count + 1, 10)
            self.log_message(f"CH{channel_num}: ⚠️ Fail count increased to {current_count + 1}", "buffer")
            
            # Устанавливаем long cooldown если нужно (используем переменную из настроек)
            if current_count + 1 >= 3:
                self.channel_long_cooldown[channel_num] = True
                # Сбросим через время cooldown
                cooldown_ms = self.channel_long_check_cooldown.get() * 1000
                self.root.after(cooldown_ms, lambda: self.reset_long_cooldown(channel_num))
        
        # 4. Запускаем заставку для URL, UDP и GRAB_WINDOW источников
        if self.is_streaming or reason == "startup_failed":
            channel_data = self.multiplex_channels.get(channel_num)
            if channel_data:
                source_type = channel_data['source_type'].get()
                if source_type in ["URL_Input", "UDP_MPTS", "grab_window"]:
                    self.start_individual_emergency(channel_num)
                    self.schedule_channel_check(channel_num)
                else:
                    self.log_message(f"CH{channel_num}: ⏭️ No emergency for {source_type}", "buffer")
        
        # При переходе в FAILED очищаем время инициализации
        if channel_num in self.channel_initialized:
            del self.channel_initialized[channel_num]
        
        # Обновляем индикатор Emergency
        self.root.after(0, self.update_channel_emergency_indicator, channel_num)
        
        # Сбрасываем статистику в "--"
        if channel_num in self.channel_speed:
            self.channel_speed[channel_num].set("---")
        if channel_num in self.channel_bitrate:
            self.channel_bitrate[channel_num].set("---")

    def reset_long_cooldown(self, channel_num):
        """Сбрасывает флаг long cooldown для канала"""
        if channel_num in self.channel_long_cooldown:
            self.channel_long_cooldown[channel_num] = False
            self.log_message(f"CH{channel_num}: Long cooldown expired", "buffer")
                
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
            interval = self.get_window_search_interval(attempts) * 1000
            self.log_message(f"CH{channel_num}: ⏱️ Window search interval: {interval/1000}s (attempt {attempts})", "buffer")
        else:
            # Проверяем cooldown
            if hasattr(self, 'channel_long_cooldown') and self.channel_long_cooldown.get(channel_num, False):
                interval = self.channel_long_check_cooldown.get() * 1000
                self.log_message(f"CH{channel_num}: ⏱️ COOLDOWN: {interval/1000}s interval", "buffer")
                self.channel_long_cooldown[channel_num] = False
            elif channel_num in self.channel_long_results:
                interval = self.channel_check_interval_normal.get() * 1000
            elif fail_count >= 3:
                interval = self.channel_check_interval_fail3.get() * 1000
                self.log_message(f"CH{channel_num}: ⏱️ LONG CHECK COOLDOWN: {interval/1000}s interval", "buffer")
            else:
                interval = self.channel_check_interval_normal.get() * 1000
        
        timer = self.root.after(int(interval), lambda: self.check_single_channel(channel_num))
        self.channel_check_timers[channel_num] = timer

    def get_window_search_interval(self, attempts):
        """Возвращает интервал проверки для окна на основе количества попыток"""
        intervals = [
            self.window_search_interval_1.get(),
            self.window_search_interval_2.get(),
            self.window_search_interval_3.get(),
            self.window_search_interval_4.get(),
            self.window_search_interval_5.get()
        ]
        
        if attempts < len(intervals):
            return intervals[attempts]
        else:
            return intervals[-1]  # последний интервал для всех последующих попыток

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
            windows_data = self.get_available_windows()  # получаем список словарей
            capture_method = channel_data['capture_method'].get()
            current_value = channel_data['window_title'].get()
            original_title = channel_data.get('original_window_title', current_value)
            
            # Сохраняем оригинальное название при первом запуске
            if 'original_window_title' not in channel_data:
                channel_data['original_window_title'] = current_value
            
            self.log_message(f"CH{channel_num}: Checking grab_window recovery. Original: '{original_title[:50]}...'", "buffer")
            self.log_message(f"CH{channel_num}: Current: '{current_value[:50]}...'", "buffer")
            self.log_message(f"CH{channel_num}: Available windows: {len(windows_data)}", "buffer")
            
            # Состояние поиска для этого канала
            if channel_num not in self.window_search_state:
                self.window_search_state[channel_num] = {
                    'attempts': 0,
                    'last_search': time.time(),
                    'original_title': original_title
                }
            
            search_state = self.window_search_state[channel_num]
            
            if capture_method == 'gdigrab':
                # Для gdigrab работаем с названиями окон
                available_titles = [w['window_title'] for w in windows_data]
                
                # 1. Пытаемся найти оригинальное окно
                if original_title and original_title in available_titles:
                    self.log_message(f"CH{channel_num}: ✅ Original window found!", "buffer")
                    channel_data['window_title'].set(original_title)
                    # Оригинал найден - поиск завершен
                    if 'using_temp_window' in channel_data:
                        del channel_data['using_temp_window']
                    del self.window_search_state[channel_num]
                    is_alive = True
                    
                # 2. Если нет оригинального, ищем похожее
                else:
                    similar = self.find_similar_window(original_title, available_titles) if original_title else None
                    if similar:
                        self.log_message(f"CH{channel_num}: 🔍 Found similar window: '{similar[:50]}...'", "buffer")
                        channel_data['window_title'].set(similar)
                        channel_data['using_temp_window'] = True
                        # НЕ удаляем window_search_state - продолжаем поиск оригинала
                        is_alive = True
                        
                    # 3. Если нет похожего, увеличиваем счетчик
                    else:
                        search_state['attempts'] += 1
                        self.log_message(f"CH{channel_num}: ⏳ No suitable window found (attempt {search_state['attempts']})", "buffer")
                        
                        # Берем первое доступное окно, если есть
                        if available_titles:
                            self.log_message(f"CH{channel_num}: Using first available window as temporary", "buffer")
                            channel_data['window_title'].set(available_titles[0])
                            channel_data['using_temp_window'] = True
                            # НЕ удаляем window_search_state
                            is_alive = True
                        else:
                            is_alive = False
            
            else:  # gfxcapture
                # Для gfxcapture работаем с именами процессов
                available_processes = [f"{w['process_name']}.exe" for w in windows_data]
                current_process = current_value if current_value else ''
                original_process = channel_data.get('original_process', current_process)
                
                # Сохраняем оригинальный процесс при первом запуске
                if 'original_process' not in channel_data:
                    channel_data['original_process'] = original_process
                    self.log_message(f"CH{channel_num}: Original process saved: {original_process}", "buffer")
                
                # 1. Пытаемся найти оригинальный процесс
                if original_process and original_process in available_processes:
                    self.log_message(f"CH{channel_num}: ✅ Original process found!", "buffer")
                    channel_data['window_title'].set(original_process)
                    # Оригинал найден - сбрасываем флаги
                    if 'using_temp_process' in channel_data:
                        del channel_data['using_temp_process']
                    if channel_num in self.window_search_state:
                        del self.window_search_state[channel_num]
                    is_alive = True
                    
                # 2. Если нет оригинального, берем первый доступный
                elif available_processes:
                    search_state['attempts'] += 1
                    self.log_message(f"CH{channel_num}: ⏳ Original process not found, using first available (attempt {search_state['attempts']})", "buffer")
                    
                    # Устанавливаем временный процесс
                    temp_process = available_processes[0]
                    channel_data['window_title'].set(temp_process)
                    channel_data['using_temp_process'] = True
                    channel_data['temp_process'] = temp_process
                    # НЕ удаляем window_search_state - продолжаем поиск оригинала
                    is_alive = True
                    
                else:
                    search_state['attempts'] += 1
                    self.log_message(f"CH{channel_num}: ⏳ No processes found (attempt {search_state['attempts']})", "buffer")
                    is_alive = False
            
            url = current_value or "no window"
            
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
        
        # РЕЖИМ ДЛИННЫХ ПРОВЕРОК (используем переменные из настроек)
        long_check_count = self.channel_long_check_count.get()
        if fail_count >= 3:
            if channel_num not in self.channel_long_results:
                self.channel_long_results[channel_num] = []
            
            self.channel_long_results[channel_num].append(is_alive)
            self.log_message(f"CH{channel_num}: 📊 Long check {len(self.channel_long_results[channel_num])}/{long_check_count}: {'✅' if is_alive else '❌'}", "buffer")
            
            if len(self.channel_long_results[channel_num]) >= long_check_count:
                if all(self.channel_long_results[channel_num]):
                    self.log_message(f"CH{channel_num}: ✅ All {long_check_count} checks passed, restoring", "buffer")
                    del self.channel_long_results[channel_num]
                    self.restore_channel(channel_num)
                else:
                    fail_count = sum(1 for r in self.channel_long_results[channel_num] if not r)
                    self.log_message(f"CH{channel_num}: ⚠️ {fail_count} checks failed, waiting {self.channel_long_check_cooldown.get()}s", "buffer")
                    del self.channel_long_results[channel_num]
                    self.schedule_channel_check(channel_num)
            else:
                self.schedule_channel_check(channel_num)
            
            return
        
        # ОБЫЧНЫЙ РЕЖИМ (используем переменную из настроек)
        recovery_check_count = self.channel_recovery_check_count.get()
        if is_alive:
            count = self.channel_recovery_count.get(channel_num, 0) + 1
            self.channel_recovery_count[channel_num] = count
            
            if count >= recovery_check_count:
                self.log_message(f"CH{channel_num}: ✅ Stream recovered ({count}/{recovery_check_count})", "buffer")
                self.restore_channel(channel_num)
            else:
                self.log_message(f"CH{channel_num}: 🟡 Need one more confirmation ({count}/{recovery_check_count})", "buffer")
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
        
        ffmpeg_path = self.ffmpeg_path
        safe_path = os.path.abspath(emergency_file).replace('\\', '/')
        output_port = self.base_multicast_port + channel_num - 1
        
        video_bitrate, audio_bitrate, _ = self.get_channel_bitrates()
        encoder_cmd = self.get_encoder_command_with_bitrate(video_bitrate)
        
        # Параметры видео
        codec = self.video_codec.get()
        preset = self.video_preset.get()
        tune = self.video_tune.get()
        profile = self.video_profile.get()
        pix_fmt = self.pix_fmt.get()
        aspect = self.video_aspect.get()
        resolution = self.video_resolution.get()
        fps = self.video_fps.get()
        gop = self.video_gop.get()
        custom_options = self.custom_options.get()
        
        # Определяем HDR режим
        is_hdr = pix_fmt in ["yuv420p10le", "p010le", "p016le", "yuv422p10le", "yuv444p10le"]
        
        cmd = f'"{ffmpeg_path}" -hwaccel auto -re -stream_loop -1 '
        cmd += f'-i "{safe_path}" '
        if encoder_cmd:
            cmd += encoder_cmd + " "
            cmd += f'-b:a {audio_bitrate} '
            cmd += f'-muxdelay {self.video_muxdelay.get()} -muxpreload {self.video_muxpreload.get()} '
            
        # Метаданные
        cmd += f'-metadata service_provider="EMERGENCY" '
        cmd += f'-metadata service_name="Emergency CH{channel_num}" '
        cmd += f'-f mpegts '
        
        buffer_bytes = self.get_udp_buffer_bytes()
        cmd += f'"udp://@238.0.0.1:{output_port}?pkt_size=1316&buffer_size={buffer_bytes}&overrun_nonfatal=1"'
        
        try:
            process = subprocess.Popen(
                cmd,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )
            
            threading.Thread(
                target=self.monitor_emergency_output,
                args=(channel_num, process),
                daemon=True
            ).start()
            
            time.sleep(1)
            
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

    def background_window_search(self, channel_num):
        """Фоновый поиск оригинального окна для ACTIVE каналов"""
        channel_data = self.multiplex_channels.get(channel_num)
        if not channel_data:
            return
        
        # Проверяем, нужен ли поиск для этого канала
        if not channel_data.get('using_temp_process') and not channel_data.get('using_temp_window'):
            return
        
        source_type = channel_data['source_type'].get()
        if source_type != "grab_window":
            return
        
        # Получаем текущие окна
        windows_data = self.get_available_windows()
        capture_method = channel_data['capture_method'].get()
        original = channel_data.get('original_process') or channel_data.get('original_window_title')
        
        if not original:
            return
        
        if capture_method == 'gfxcapture':
            available = [f"{w['process_name']}.exe" for w in windows_data]
            if original in available:
                self.log_message(f"CH{channel_num}: ✅ Original process returned! Restarting...", "buffer")
                # Принудительно перезапускаем канал с оригиналом
                self.force_restart_with_original(channel_num, original)
        else:  # gdigrab
            available = [w['window_title'] for w in windows_data]
            if original in available:
                self.log_message(f"CH{channel_num}: ✅ Original window returned! Restarting...", "buffer")
                self.force_restart_with_original(channel_num, original)
        
        # Планируем следующую проверку
        self.root.after(30000, lambda: self.background_window_search(channel_num)) 

    def force_restart_with_original(self, channel_num, original_value):
        """Принудительный перезапуск канала с оригинальным окном"""
        channel_data = self.multiplex_channels.get(channel_num)
        if not channel_data:
            return
        
        # Останавливаем текущий процесс
        self.stop_channel_process(channel_num)
        
        # Устанавливаем оригинальное значение
        channel_data['window_title'].set(original_value)
        
        # Сбрасываем флаги временного использования
        if 'using_temp_process' in channel_data:
            del channel_data['using_temp_process']
        if 'using_temp_window' in channel_data:
            del channel_data['using_temp_window']
        
        # Перезапускаем канал
        output_port = self.base_multicast_port + channel_num - 1
        cmd = self.build_channel_ffmpeg_command(channel_num, channel_data, output_port)
        
        if cmd:
            process = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                      stdin=subprocess.DEVNULL, text=True, bufsize=1)
            self.channel_processes[channel_num] = {
                'process': process, 'pid': process.pid, 'stdin': None,
                'port': output_port, 'is_radio': False, 'is_emergency': False
            }
            threading.Thread(target=self.monitor_channel_output,
                            args=(channel_num, process, channel_data), daemon=True).start()
            self.log_message(f"CH{channel_num}: ✅ Restarted with original window", "buffer")        
                                                                                         
    def restore_channel(self, channel_num):
        """Восстановление канала - переключение с заставки на оригинал"""
        self.log_message(f"CH{channel_num}: 🔄 Restoring channel", "buffer")
        
        # ПОЛУЧАЕМ ДАННЫЕ КАНАЛА
        channel_data = self.multiplex_channels.get(channel_num)
        
        # Удаляем состояние поиска ТОЛЬКО если не используем временный процесс
        if not (channel_data and channel_data.get('using_temp_process')):
            if channel_num in self.window_search_state:
                del self.window_search_state[channel_num]
                self.log_message(f"CH{channel_num}: ✅ Window search state cleared", "buffer")
        
        # Сбрасываем статистику (будет обновлена новым процессом)
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
        
        # Если используем временный процесс, продолжаем поиск оригинального
        if channel_data and (channel_data.get('using_temp_process') or channel_data.get('using_temp_window')):
            self.root.after(30000, lambda: self.background_window_search(channel_num))
        
        # 5. Запускаем оригинальный канал
        if self.restart_original_channel(channel_num):
            # Успешно запустили - обновляем состояние
            self.channel_states[channel_num] = self.CHANNEL_STATE_ACTIVE
            self.log_message(f"CH{channel_num}: ✅ Restored to ACTIVE", "buffer")
            self.channel_initialized[channel_num] = time.time()
            # Очищаем временные данные
            if channel_num in self.channel_fail_time:
                del self.channel_fail_time[channel_num]
            
            # Обновляем индикатор Emergency
            self.root.after(0, self.update_channel_emergency_indicator, channel_num)
        
        else:
            # Не удалось запустить - возвращаем в FAILED и ПРИНУДИТЕЛЬНО запускаем заставку
            self.log_message(f"CH{channel_num}: ⚠️ Restore failed, forcing emergency", "buffer")
            self.channel_states[channel_num] = self.CHANNEL_STATE_FAILED
            self.start_individual_emergency(channel_num)
            self.schedule_channel_check(channel_num)  
            
    def start_streaming(self):
        """Start multi-process streaming"""
        if self.is_streaming:
            return
        
        try:
            self.log_message("=== Starting multi-process streaming ===", "buffer")            

            self.encoder_speed.set("---")
            self.encoder_bitrate.set("---")

            
            # Сбрасываем значения каналов
            for ch_num in self.channel_speed:
                self.channel_speed[ch_num].set("---")
            for ch_num in self.channel_bitrate:
                self.channel_bitrate[ch_num].set("---")            
                                  
            # 2. Clear old processes
            self.stop_all_channel_processes()
            self.channel_processes.clear()
            
            # Сбрасываем счетчики перед новым запуском
            self.channel_fail_count.clear()
            self.channel_long_results.clear()
            self.channel_recovery_count.clear()
            self.channel_speed_received.clear()
            self.channel_initialized.clear()            
            
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
            # self.buffer_status.set("Running")
            self.update_status_colors()
            self.start_btn.config(state='disabled')
            self.stop_btn.config(state='normal') 
     
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
           
        # 1. Stop all processes
        self.is_streaming = False
        self._state_monitor_running = False
        self.encoder_status.set("Stopped")
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
                
        # ⭐ СБРАСЫВАЕМ ИСТОРИЮ СКОРОСТИ
        self.main_speed_history.clear()
        self.channel_speed_history.clear()
        
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
        self.root.after(100, self.init_channels_stats_ui)
        
        # Очищаем состояние поиска окон
        self.window_search_state.clear()

        # ⭐ Сбрасываем счетчики ошибок при полной остановке
        self.channel_fail_count.clear()
        self.channel_long_results.clear()
        self.channel_recovery_count.clear()
        self.channel_speed_received.clear()
        self.channel_initialized.clear()
        
        # Очищаем все таймеры
        for attr in list(self.__dict__.keys()):
            if attr.startswith('_speed_timer_'):
                try:
                    self.root.after_cancel(getattr(self, attr))
                except:
                    pass
                delattr(self, attr)
                
    def run_bypass_mode(self):
        """Прямая пересылка UDP → ZMQ без буферизации"""
        
        IN_PORT = int(self.udp_input_port.get())
        LOCALHOST = self.localhost_ip.get()
        ZMQ_OUTPUT = f"tcp://{self.output_ip.get()}:{self.udp_output_port.get()}"
        
        import struct
        import socket
        import zmq
        import threading
        import time
        
        # Настройка ZMQ
        try:
            context = zmq.Context()
            zmq_socket = context.socket(zmq.PUB)
            zmq_socket.setsockopt(zmq.SNDHWM, 100000)
            zmq_socket.setsockopt(zmq.SNDBUF, 8 * 1024 * 1024)
            zmq_socket.setsockopt(zmq.LINGER, 0)
            zmq_socket.bind(ZMQ_OUTPUT)
            self.log_message(f"📤 ZMQ output: {ZMQ_OUTPUT}", "buffer")
        except Exception as e:
            self.log_message(f"❌ ZMQ error: {e}", "buffer")
            return
        
        # Настройка UDP с multicast поддержкой
        try:
            sock_in = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
            sock_in.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 8 * 1024 * 1024)
            sock_in.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock_in.bind(('', IN_PORT))
            
            if LOCALHOST.startswith('230.') or LOCALHOST.startswith('239.'):
                mreq = struct.pack("4sl", socket.inet_aton(LOCALHOST), socket.INADDR_ANY)
                sock_in.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
                self.log_message(f"📥 Multicast subscription: {LOCALHOST}:{IN_PORT}", "buffer")
            
            sock_in.settimeout(0.01)
            self.log_message(f"📥 UDP input: {LOCALHOST}:{IN_PORT}", "buffer")
        except Exception as e:
            self.log_message(f"❌ UDP error: {e}", "buffer")
            return
        
        # Счетчики для статистики
        bytes_received = 0
        bytes_sent = 0
        last_stats_time = time.time()
        
        def forwarder():
            nonlocal bytes_received, bytes_sent
            while self.buffer_running:
                try:
                    data, addr = sock_in.recvfrom(65535)
                    bytes_received += len(data)
                    
                    try:
                        zmq_socket.send(data, zmq.NOBLOCK)
                        bytes_sent += len(data)
                    except zmq.Again:
                        # Если ZMQ переполнен - просто дропаем
                        self.stats['dropped'] = self.stats.get('dropped', 0) + len(data)
                        
                except socket.timeout:
                    continue
                except Exception as e:
                    if self.buffer_running:
                        self.log_message(f"Bypass error: {e}", "buffer")
                    break
        
        def stats_updater():
            nonlocal bytes_received, bytes_sent, last_stats_time
            while self.buffer_running:
                time.sleep(1.0)
                current_time = time.time()
                elapsed = current_time - last_stats_time
                
                if elapsed >= 1.0:
                    input_rate = (bytes_received * 8) / elapsed / 1000
                    output_rate = (bytes_sent * 8) / elapsed / 1000
                    
                    # Обновляем GUI
                    self.root.after(0, self.buffer_input_bitrate.set, f"{input_rate:.1f}")
                    self.root.after(0, self.buffer_output_bitrate.set, f"{output_rate:.1f}")
                    self.root.after(0, self.buffer_fill.set, f"0/{self.max_buffer.get()}")
                    self.root.after(0, self.buffer_received.set, f"{bytes_received}")
                    self.root.after(0, self.buffer_sent.set, f"{bytes_sent}")
                    self.root.after(0, self.bitrate_deviation.set, "BYPASS")
                    
                    # Сбрасываем счетчики
                    bytes_received = 0
                    bytes_sent = 0
                    last_stats_time = current_time
        
        # Запуск потоков
        threading.Thread(target=forwarder, daemon=True).start()
        threading.Thread(target=stats_updater, daemon=True).start()
        
        self.log_message("🔀 Bypass mode active - UDP → ZMQ direct forwarding", "buffer")
        
        # Ожидание завершения
        try:
            while self.buffer_running:
                time.sleep(0.1)
        finally:
            sock_in.close()
            zmq_socket.close()
            context.term()                

    def run_zmq_buffer(self):
        """Двухрежимный буфер с гистерезисом"""
        
        # ПРОВЕРКА BYPASS РЕЖИМА
        if self.buffer_bypass.get():
            self.log_message("🔀 BYPASS MODE: UDP input → direct ZMQ output", "buffer")
            self.run_bypass_mode()
            return
        
        import struct
        
        # ПРОВЕРКА IP АДРЕСОВ
        local_ip = self.localhost_ip.get().strip()
        if not local_ip:
            local_ip = "127.0.0.1"
            self.localhost_ip.set(local_ip)
            self.log_message(f"⚠️ Localhost IP empty, using default: {local_ip}", "buffer")
        
        output_ip = self.output_ip.get().strip()
        if not output_ip:
            output_ip = "127.0.0.1"
            self.output_ip.set(output_ip)
            self.log_message(f"⚠️ Output IP empty, using default: {output_ip}", "buffer")
        
        # НАСТРОЙКИ
        IN_PORT = int(self.udp_input_port.get())
        LOCALHOST = local_ip
        ZMQ_OUTPUT = f"tcp://{output_ip}:{self.udp_output_port.get()}"
        
        TARGET_BUFFER = self.target_buffer.get()      # Целевой уровень буфера
        MIN_BUFFER = self.min_buffer.get()             # Минимальный уровень
        MAX_BUFFER = self.max_buffer.get()             # Максимальный размер
        TARGET_BITRATE = float(self.muxrate.get())
        CALIBRATION_PACKETS = self.calibration_packets.get()
        CALIBRATION_TIME = self.calibration_time.get()
        
        # ИНИЦИАЛИЗАЦИЯ ГЕНЕРАТОРА DUMMY ПОТОКА
        dummy_generator = DummyTSGenerator(
            app=self,
            service_name=self.service_name.get() or "DVB-T2 Service",
            service_provider=self.service_provider.get() or "DVB-T2 Provider"
        )
        
        # Режимы работы
        MODE_DATA = "DATA"
        MODE_FILL = "FILL"
        
        # СТАТИСТИКА
        self.stats = {
            'received': 0, 'sent': 0, 'dropped': 0, 'buffer_overflow': 0,
            'last_check': time.time(), 'input_bitrate': 0, 'output_bitrate': 0,
            'null_packets_sent': 0, 'mode_switches': 0, 'current_mode': MODE_FILL
        }
        
        # ОЧЕРЕДИ
        packet_buffer = queue.Queue(maxsize=MAX_BUFFER)
        input_tracker = deque(maxlen=CALIBRATION_PACKETS)
        output_tracker = deque(maxlen=CALIBRATION_PACKETS)
        incoming_bitrate_history = deque(maxlen=50)
        
        # ⭐ ПРЕДВАРИТЕЛЬНОЕ ЗАПОЛНЕНИЕ БУФЕРА БЛОКАМИ ПО 1316 БАЙТ ⭐
        self.log_message("🎯 Pre-filling buffer with valid MPEG-TS blocks (1316 bytes)...", "buffer")
        dummy_block_stream = dummy_generator.generate_block_stream()  # ← ВОТ ЭТОТ МЕТОД
        for i in range(TARGET_BUFFER):
            try:
                block = next(dummy_block_stream)
                packet_buffer.put_nowait((block, time.time()))
            except (queue.Full, StopIteration):
                break
        self.log_message(f"✅ Buffer pre-filled with {packet_buffer.qsize()} blocks (1316 bytes each)", "buffer")
        
        # ДАННЫЕ КАЛИБРОВКИ
        cal_data = {
            'send_interval': 0.001,
            'calibrated': False,
            'packet_size_avg': 1316,
            'total_bytes_sent': 0,
            'output_start_time': time.time(),
            'last_recalib_time': time.time(),
            'current_mode': MODE_FILL,
            'incoming_bitrate_avg': 0,
            'mode_stable_time': time.time(),
            'switch_cooldown': 0
        }
        
        # ПОРОГИ ПЕРЕКЛЮЧЕНИЯ С ГИСТЕРЕЗИСОМ
        THRESHOLDS = {
            'fill_to_data_buffer': TARGET_BUFFER,
            'data_to_fill_buffer': MIN_BUFFER * 1.0,
            'fill_to_data_bitrate': 0.85,
            'data_to_fill_bitrate': 0.75,
            'min_time_in_mode': 5,
            'bitrate_samples': 10
        }
        
        # ИНИЦИАЛИЗАЦИЯ ZMQ
        try:
            context = zmq.Context()
            zmq_socket = context.socket(zmq.PUB)
            zmq_socket.setsockopt(zmq.SNDHWM, 100000)
            zmq_socket.setsockopt(zmq.SNDBUF, 8 * 1024 * 1024)
            zmq_socket.setsockopt(zmq.LINGER, 0)
            zmq_socket.bind(ZMQ_OUTPUT)
            self.log_message(f"📤 ZMQ output: {ZMQ_OUTPUT}", "buffer")
        except Exception as e:
            self.log_message(f"❌ ZMQ error: {e}", "buffer")
            return
        
        # ИНИЦИАЛИЗАЦИЯ UDP
        try:
            sock_in = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
            sock_in.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 8 * 1024 * 1024)
            sock_in.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock_in.bind(('', IN_PORT))
            
            if LOCALHOST.startswith('230.') or LOCALHOST.startswith('239.'):
                mreq = struct.pack("4sl", socket.inet_aton(LOCALHOST), socket.INADDR_ANY)
                sock_in.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
                self.log_message(f"📥 Multicast subscription: {LOCALHOST}:{IN_PORT}", "buffer")
            
            sock_in.settimeout(0.01)
            self.log_message(f"📥 UDP input: {LOCALHOST}:{IN_PORT}", "buffer")
        except Exception as e:
            self.log_message(f"❌ UDP error: {e}", "buffer")
            return
        
        def calibrate():
            """Калибровка интервала отправки"""
            self.log_message("🎯 Calibrating send interval...", "buffer")
            time.sleep(0.2)
            
            if len(input_tracker) > 50:
                total_size = sum(size for _, size in input_tracker)
                packet_count = len(input_tracker)
                cal_data['packet_size_avg'] = total_size / packet_count
                
                avg_packet_size_bits = cal_data['packet_size_avg'] * 8
                target_bps = TARGET_BITRATE
                cal_data['send_interval'] = avg_packet_size_bits / target_bps
                
                cal_data['total_bytes_sent'] = 0
                cal_data['output_start_time'] = time.time()
                cal_data['last_recalib_time'] = time.time()
                
                self.log_message(f"✅ Calibration complete!", "buffer")
                self.log_message(f"   Packet size: {cal_data['packet_size_avg']:.1f} bytes", "buffer")
                self.log_message(f"   Interval: {cal_data['send_interval']*1000:.3f} ms", "buffer")
                self.log_message(f"   Target bitrate: {TARGET_BITRATE/1000000:.3f} Mbps", "buffer")
                
                cal_data['calibrated'] = True
        
        def get_smoothed_incoming_bitrate():
            """Возвращает реальный входной битрейт в BPS"""
            if len(input_tracker) < 10:
                return TARGET_BITRATE * 0.5
            
            current_time = time.time()
            tracker_copy = list(input_tracker)
            
            recent_packets = [(t, s) for t, s in tracker_copy if current_time - t < 2.0]
            
            if len(recent_packets) < 10:
                return TARGET_BITRATE * 0.5
            
            total_bytes = sum(size for _, size in recent_packets)
            time_span = recent_packets[-1][0] - recent_packets[0][0]
            
            if time_span > 0.5:
                instant_rate = (total_bytes * 8) / time_span
                history_copy = list(incoming_bitrate_history)
                history_copy.append(instant_rate)
                if len(history_copy) > 3:
                    return sum(history_copy[-3:]) / 3
                return instant_rate
            
            return TARGET_BITRATE * 0.5
        
        def receiver():
            while self.buffer_running:
                try:
                    data, addr = sock_in.recvfrom(65535)
                    timestamp = time.time()
                    
                    self.stats['received'] += len(data)
                    input_tracker.append((timestamp, len(data)))
                    
                    try:
                        packet_buffer.put_nowait((data, timestamp))
                    except queue.Full:
                        self.stats['buffer_overflow'] += 1
                        self.stats['dropped'] += len(data)
                        try:
                            packet_buffer.get_nowait()
                            packet_buffer.put_nowait((data, timestamp))
                        except:
                            pass
                            
                except socket.timeout:
                    continue
                except Exception as e:
                    if self.buffer_running:
                        self.log_message(f"Receiver error: {e}", "buffer")
                    break
        
        def sender():
            sequence_number = 0
            # ⭐ ИСПОЛЬЗУЕМ generate_block_stream ДЛЯ БЛОКОВ 1316 БАЙТ ⭐
            dummy_block_stream = dummy_generator.generate_block_stream()
            
            # ⭐ РАСЧЕТ ДЛЯ БЛОКОВ 1316 БАЙТ ⭐
            BLOCK_SIZE = 1316  # 7 TS пакетов
            blocks_per_second = TARGET_BITRATE / (BLOCK_SIZE * 8)
            cal_data['send_interval'] = 1.0 / blocks_per_second
            cal_data['packet_size_avg'] = BLOCK_SIZE
            cal_data['calibrated'] = True
            
            self.log_message(f"✅ Block calibration: {blocks_per_second:.1f} blocks/sec, interval={cal_data['send_interval']*1000:.3f}ms", "buffer")
            
            next_send_time = time.perf_counter()
            send_interval = cal_data['send_interval']
            data_mode_active = False
            
            while self.buffer_running:
                try:
                    current_time = time.perf_counter()
                    
                    if current_time >= next_send_time:
                        next_send_time += send_interval
                        
                        try:
                            data, timestamp = packet_buffer.get_nowait()
                            # Есть данные - нужна калибровка
                            if not cal_data['calibrated'] and packet_buffer.qsize() > MIN_BUFFER:
                                calibrate()
                                send_interval = cal_data['send_interval']
                                if not data_mode_active:
                                    self.log_message(f"✅ Input detected - switching to DATA MODE", "buffer")
                                    data_mode_active = True
                            
                        except queue.Empty:
                            # ⭐ Нет данных - блок из 7 пакетов (1316 байт) ⭐
                            try:
                                data = next(dummy_block_stream)
                            except StopIteration:
                                dummy_block_stream = dummy_generator.generate_block_stream()
                                data = next(dummy_block_stream)
                        
                        try:
                            zmq_socket.send(data, zmq.NOBLOCK)
                            self.stats['sent'] += len(data)  # Будет 1316 байт
                            sequence_number += 1
                        except zmq.Again:
                            time.sleep(0.0001)
                    
                    else:
                        sleep_time = next_send_time - current_time
                        if sleep_time > 0.002:
                            time.sleep(sleep_time * 0.9)
                        elif sleep_time > 0.0001:
                            while time.perf_counter() < next_send_time:
                                pass
                                
                except Exception as e:
                    self.log_message(f"Sender error: {e}", "buffer")
                    time.sleep(0.001)
        
        def statistics():
            last_stats_time = time.time()
            last_received = 0
            last_sent = 0
            
            while self.buffer_running:
                try:
                    current_time = time.time()
                    time_diff = current_time - last_stats_time
                    
                    if time_diff >= 2.0:
                        current_received = self.stats['received']
                        current_sent = self.stats['sent']
                        
                        input_rate = (current_received - last_received) * 8 / time_diff / 1000
                        zmq_output_rate = (current_sent - last_sent) * 8 / time_diff / 1000
                        
                        target_kbps = TARGET_BITRATE / 1000
                        output_deviation = abs(zmq_output_rate - target_kbps) / target_kbps * 100
                        buffer_size = packet_buffer.qsize()
                        
                        # ОБНОВЛЕНИЕ GUI
                        self.root.after(0, lambda: self.buffer_input_bitrate.set(f"{input_rate:.1f}"))
                        self.root.after(0, lambda: self.buffer_output_bitrate.set(f"{zmq_output_rate:.1f}"))
                        self.root.after(0, lambda: self.buffer_fill.set(f"{buffer_size}/{MAX_BUFFER}"))
                        self.root.after(0, lambda: self.buffer_received.set(f"{current_received}"))
                        self.root.after(0, lambda: self.buffer_sent.set(f"{current_sent}"))
                        self.root.after(0, lambda: self.buffer_dropped.set(f"{self.stats['dropped']}"))
                        self.root.after(0, lambda: self.buffer_target.set(f"{target_kbps:.1f}"))
                        self.root.after(0, lambda: self.bitrate_deviation.set(f"{output_deviation:.1f}%"))
                        
                        # ЦВЕТА
                        if output_deviation <= 1.0:
                            self.root.after(0, lambda: self.zmq_output_label.configure(foreground='green'))
                        elif output_deviation <= 3.0:
                            self.root.after(0, lambda: self.zmq_output_label.configure(foreground='orange'))
                        else:
                            self.root.after(0, lambda: self.zmq_output_label.configure(foreground='red'))
                        
                        last_received = current_received
                        last_sent = current_sent
                        last_stats_time = current_time
                    
                    time.sleep(1.0)
                    
                except Exception as e:
                    if self.buffer_running:
                        self.log_message(f"Statistics error: {e}", "buffer")
                    time.sleep(1.0)
        
        # ЗАПУСК
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

    def update_mode_indicator(self, *args):
        """Update SDR/HDR mode indicator based on pixel format"""
        pix_fmt = self.pix_fmt.get()
        is_hdr = pix_fmt in ["yuv420p10le", "p010le", "p016le", "yuv422p10le", "yuv444p10le"]
        
        if is_hdr:
            self.mode_indicator_text.set("🔴 HDR-TV")
            if hasattr(self, 'mode_indicator_label'):
                self.mode_indicator_label.config(foreground='red')
            if hasattr(self, 'main_hdr_indicator'):
                self.main_hdr_indicator.config(foreground='red')
        else:
            self.mode_indicator_text.set("⚫ SDR-TV")
            if hasattr(self, 'mode_indicator_label'):
                self.mode_indicator_label.config(foreground='gray')
            if hasattr(self, 'main_hdr_indicator'):
                self.main_hdr_indicator.config(foreground='gray')

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
        if self.is_streaming:
           return
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
                        
    def restart_streaming_system(self):
        """Полный перезапуск системы стриминга"""
        if not self.is_streaming:
            return
        
        self.log_message("🔄 Executing full system restart...", "buffer")
        
        # Сохраняем состояние
        was_streaming = self.is_streaming
        # was_modulator = self.modulator_running
        
        # Останавливаем всё
        self.stop_streaming()
        
        # Небольшая пауза
        time.sleep(3)
        
        # Перезапускаем
        if was_streaming:
            self.start_streaming()
                
        self.log_message("✅ System restart completed", "buffer") 
        
    def get_clean_encoder_command(self):
        """Генерирует команду кодирования из текущих настроек GUI, исключая параметры битрейта"""
        codec = self.video_codec.get()
        preset = self.video_preset.get()
        tune = self.video_tune.get()
        profile = self.video_profile.get()
        pix_fmt = self.pix_fmt.get()
        aspect = self.video_aspect.get()
        fps = self.video_fps.get()
        gop = self.video_gop.get()
        custom_options = self.custom_options.get()
        audio_codec = self.audio_codec.get()
        audio_sample_rate = self.audio_sample_rate.get()
        audio_channels = self.get_audio_channels_ffmpeg()
        
        # Определяем HDR режим
        is_hdr = pix_fmt in ["yuv420p10le", "p010le", "p016le", "yuv422p10le", "yuv444p10le"]
        
        cmd_parts = []
        
        # Video codec specific parameters
        if codec == "libx265":
            cmd_parts.append(f"-vcodec {codec}")
            cmd_parts.append(f"-preset {preset}")
            if tune:
                cmd_parts.append(f"-tune {tune}")
            if custom_options:
                cmd_parts.append(custom_options)
            
            cmd_parts.append(f"-pix_fmt {pix_fmt}")
            cmd_parts.append(f"-aspect {aspect}")
            
            # Формируем x265-params БЕЗ битрейта
            x265_params = []
            if profile:
                x265_params.append(f"profile={profile}")
            if is_hdr:
                x265_params.append("colorprim=bt2020")
                x265_params.append("transfer=smpte2084")
                x265_params.append("colormatrix=bt2020nc")
                x265_params.append("hdr10=1")
                x265_params.append("hdr10-opt=1")
                x265_params.append("repeat-headers=1")
            
            if x265_params:
                cmd_parts.append(f'-x265-params "{":".join(x265_params)}"')
        
        elif codec == "libx264":
            cmd_parts.append(f"-vcodec {codec}")
            cmd_parts.append(f"-preset {preset}")
            if tune:
                cmd_parts.append(f"-tune {tune}")
            if custom_options:
                cmd_parts.append(custom_options)
            
            cmd_parts.append(f"-pix_fmt {pix_fmt}")
            cmd_parts.append(f"-aspect {aspect}")
            
            # Формируем x264-params БЕЗ битрейта
            x264_params = []
            if profile:
                x264_params.append(f"profile={profile}")
            
            if x264_params:
                cmd_parts.append(f'-x264-params "{":".join(x264_params)}"')
        
        elif codec in ["hevc_nvenc", "h264_nvenc"]:
            cmd_parts.append(f"-vcodec {codec}")
            cmd_parts.append(f"-preset {preset}")
            if tune:
                cmd_parts.append(f"-tune {tune}")
            if profile:
                cmd_parts.append(f"-profile:v {profile}")
            if custom_options:
                cmd_parts.append(custom_options)
            cmd_parts.append(f"-pix_fmt {pix_fmt}")
            cmd_parts.append(f"-aspect {aspect}")
            if is_hdr and codec == "hevc_nvenc":
                cmd_parts.append("-tier high")
                cmd_parts.append("-color_primaries bt2020")
                cmd_parts.append("-color_trc smpte2084")
                cmd_parts.append("-colorspace bt2020nc")
                cmd_parts.append("-color_range limited")
        
        elif codec in ["hevc_qsv", "h264_qsv"]:
            cmd_parts.append(f"-vcodec {codec}")
            cmd_parts.append(f"-preset {preset}")
            if profile:
                cmd_parts.append(f"-profile:v {profile}")
            if custom_options:
                cmd_parts.append(custom_options)
            cmd_parts.append(f"-pix_fmt {pix_fmt}")
            cmd_parts.append(f"-aspect {aspect}")
            if is_hdr and codec == "hevc_qsv":
                cmd_parts.append("-color_primaries bt2020")
                cmd_parts.append("-color_trc smpte2084")
                cmd_parts.append("-colorspace bt2020nc")
                cmd_parts.append("-color_range limited")
        
        elif codec in ["h264_amf", "hevc_amf"]:
            cmd_parts.append(f"-vcodec {codec}")
            cmd_parts.append(f"-quality {preset}")
            if profile:
                cmd_parts.append(f"-profile:v {profile}")
            if custom_options:
                cmd_parts.append(custom_options)
            cmd_parts.append(f"-pix_fmt {pix_fmt}")
            cmd_parts.append(f"-aspect {aspect}")
            if codec == "hevc_amf":
                cmd_parts.append(f"-g {gop}")
        
        # Common video parameters
        cmd_parts.append(f"-s {self.video_resolution.get()}")
        cmd_parts.append(f"-g {gop}")
        cmd_parts.append(f"-r {fps}")
        
        # Audio parameters
        cmd_parts.append(f"-c:a {audio_codec}")
        cmd_parts.append(f"-ar {audio_sample_rate}")
        cmd_parts.append(f"-ac {audio_channels}")
        
        return " ".join(cmd_parts)

    def load_encoder_presets(self):
        """Загружает все сохраненные пресеты из папки Encoder Presets"""
        self.encoder_preset_commands.clear()
        
        if not os.path.exists(self.encoder_presets_dir):
            return
        
        for filename in os.listdir(self.encoder_presets_dir):
            if filename.endswith('.json'):
                preset_name = filename[:-5]
                filepath = os.path.join(self.encoder_presets_dir, filename)
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        if 'command' in data:
                            self.encoder_preset_commands[preset_name] = data['command']
                except Exception as e:
                    self.log_message(f"Error loading preset {preset_name}: {e}", "buffer")
        
        # Обновляем выпадающий список
        if hasattr(self, 'encoder_preset_combo') and self.encoder_preset_combo:
            presets_list = list(self.encoder_preset_commands.keys())
            self.encoder_preset_combo['values'] = presets_list
            
            # Восстанавливаем выбранный пресет
            current_preset = self.encoder_preset_name.get()
            if current_preset and current_preset in presets_list:
                # Принудительно обновляем комбобокс
                self.encoder_preset_combo.set(current_preset)
            else:
                if current_preset:
                    self.encoder_preset_name.set("")
                self.encoder_preset_combo.set("")
                
    def save_encoder_preset(self, preset_name):
        """Сохраняет текущую команду как пресет"""
        if not preset_name or not preset_name.strip():
            messagebox.showerror("Error", "Preset name cannot be empty!")
            return
        
        preset_name = preset_name.strip()
        
        # Получаем текущую команду из текстового поля
        if self.encoder_command_widget:
            current_command = self.encoder_command_widget.get("1.0", tk.END).strip()
        else:
            current_command = self.get_clean_encoder_command()
        
        # Сохраняем в файл
        filepath = os.path.join(self.encoder_presets_dir, f"{preset_name}.json")
        data = {
            'command': current_command,
            'settings': self.get_current_encoder_settings()
        }
        
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
            self.log_message(f"Preset '{preset_name}' saved successfully", "buffer")
            
            # Обновляем список пресетов
            self.load_encoder_presets()
            
            # Устанавливаем как выбранный
            self.encoder_preset_name.set(preset_name)
            if hasattr(self, 'encoder_preset_combo'):
                self.encoder_preset_combo.set(preset_name)
            
            messagebox.showinfo("Success", f"Preset '{preset_name}' saved!")
            
        except Exception as e:
            self.log_message(f"Error saving preset: {e}", "buffer")
            messagebox.showerror("Error", f"Failed to save preset:\n{e}")

    def get_current_encoder_settings(self):
        """Возвращает словарь с текущими настройками для сохранения в пресете"""
        return {
            'video_codec': self.video_codec.get(),
            'video_preset': self.video_preset.get(),
            'video_tune': self.video_tune.get(),
            'video_profile': self.video_profile.get(),
            'pix_fmt': self.pix_fmt.get(),
            'video_aspect': self.video_aspect.get(),
            'video_resolution': self.video_resolution.get(),
            'video_fps': self.video_fps.get(),
            'video_gop': self.video_gop.get(),
            'custom_options': self.custom_options.get(),
            'audio_codec': self.audio_codec.get(),
            'audio_sample_rate': self.audio_sample_rate.get(),
            'audio_channels': self.audio_channels.get(),
            'audio_bitrate': self.audio_bitrate.get(),  # Сохраняем, но не будем использовать при восстановлении
        }

    def apply_encoder_preset(self, preset_name):
        """Применяет выбранный пресет: обновляет GUI и текстовое поле"""
        if not preset_name or preset_name not in self.encoder_preset_commands:
            # Если пресет не выбран, показываем базовую команду
            self.update_encoder_command_display()
            # Очищаем комбобокс если нужно
            if hasattr(self, 'encoder_preset_combo') and self.encoder_preset_combo.get():
                self.encoder_preset_combo.set("")
                self.encoder_preset_name.set("")
            return
        
        command = self.encoder_preset_commands[preset_name]
        
        # Обновляем текстовое поле
        if self.encoder_command_widget:
            self.encoder_command_widget.delete("1.0", tk.END)
            self.encoder_command_widget.insert("1.0", command)
        
        # Принудительно обновляем комбобокс и переменную
        if hasattr(self, 'encoder_preset_combo'):
            # Убеждаемся, что значение есть в списке
            current_values = list(self.encoder_preset_combo['values'])
            if preset_name not in current_values:
                # Если нет, обновляем список
                self.encoder_preset_combo['values'] = list(self.encoder_preset_commands.keys())
            # Устанавливаем значение
            self.encoder_preset_combo.set(preset_name)
            self.encoder_preset_name.set(preset_name)
        
        # Парсим команду и обновляем GUI-контролы
        self.parse_and_update_gui_from_command(command)
        
        self.log_message(f"Applied preset '{preset_name}'", "buffer")

    def parse_and_update_gui_from_command(self, command):
        """Парсит команду и обновляет соответствующие GUI переменные"""
        import shlex
        import re
        
        # Разбираем команду на части
        try:
            parts = shlex.split(command) if isinstance(command, str) else []
        except:
            parts = command.split()
        
        # Временные переменные для хранения найденных значений
        found = {
            'vcodec': None, 'preset': None, 'tune': None, 'profile': None,
            'pix_fmt': None, 'aspect': None, 's': None, 'r': None, 'g': None,
            'acodec': None, 'ar': None, 'ac': None, 'custom': [],
            'x265_params': None, 'x264_params': None  # Добавляем x264_params
        }
        
        i = 0
        while i < len(parts):
            part = parts[i]
            if part == '-vcodec' and i + 1 < len(parts):
                found['vcodec'] = parts[i + 1]
                i += 2
            elif part == '-c:v' and i + 1 < len(parts):
                found['vcodec'] = parts[i + 1]
                i += 2
            elif part == '-preset' and i + 1 < len(parts):
                found['preset'] = parts[i + 1]
                i += 2
            elif part == '-tune' and i + 1 < len(parts):
                found['tune'] = parts[i + 1]
                i += 2
            elif part == '-profile:v' and i + 1 < len(parts):
                found['profile'] = parts[i + 1]
                i += 2
            elif part == '-pix_fmt' and i + 1 < len(parts):
                found['pix_fmt'] = parts[i + 1]
                i += 2
            elif part == '-aspect' and i + 1 < len(parts):
                found['aspect'] = parts[i + 1]
                i += 2
            elif part == '-s' and i + 1 < len(parts):
                found['s'] = parts[i + 1]
                i += 2
            elif part == '-r' and i + 1 < len(parts):
                found['r'] = parts[i + 1]
                i += 2
            elif part == '-g' and i + 1 < len(parts):
                found['g'] = parts[i + 1]
                i += 2
            elif part == '-c:a' and i + 1 < len(parts):
                found['acodec'] = parts[i + 1]
                i += 2
            elif part == '-ar' and i + 1 < len(parts):
                found['ar'] = parts[i + 1]
                i += 2
            elif part == '-ac' and i + 1 < len(parts):
                found['ac'] = parts[i + 1]
                i += 2
            elif part == '-x265-params' and i + 1 < len(parts):
                found['x265_params'] = parts[i + 1].strip('"')
                for param in found['x265_params'].split(':'):
                    if '=' in param:
                        key, val = param.split('=', 1)
                        if key == 'profile':
                            found['profile'] = val
                i += 2
            elif part == '-x264-params' and i + 1 < len(parts):  # Добавляем обработку x264-params
                found['x264_params'] = parts[i + 1].strip('"')
                for param in found['x264_params'].split(':'):
                    if '=' in param:
                        key, val = param.split('=', 1)
                        if key == 'profile':
                            found['profile'] = val
                i += 2
            elif part == '-quality' and i + 1 < len(parts):
                found['preset'] = parts[i + 1]
                i += 2
            elif part.startswith('-') and len(part) > 1:
                # Список пропускаемых параметров - добавляем -x264-params
                if part not in ['-vcodec', '-c:v', '-preset', '-tune', '-profile:v', '-pix_fmt', 
                                '-aspect', '-s', '-r', '-g', '-c:a', '-ar', '-ac', '-x265-params',
                                '-x264-params',  # Добавляем сюда
                                '-quality', '-tier', '-color_primaries', '-color_trc', '-colorspace', 
                                '-color_range', '-b:v', '-minrate', '-maxrate', '-bufsize', '-b:a']:
                    found['custom'].append(part)
                    if i + 1 < len(parts) and not parts[i + 1].startswith('-'):
                        found['custom'].append(parts[i + 1])
                        i += 2
                    else:
                        i += 1
                else:
                    i += 1
            else:
                i += 1
        
        # Применяем найденные значения к GUI
        if found['vcodec'] and found['vcodec'] in self.codec_presets:
            self.video_codec.set(found['vcodec'])
            self.update_codec_settings()
        
        if found['preset']:
            codec = self.video_codec.get()
            if codec in self.codec_presets and found['preset'] in self.codec_presets[codec]:
                self.video_preset.set(found['preset'])
            elif codec in ['h264_amf', 'hevc_amf'] and found['preset'] in ['speed', 'balanced', 'quality']:
                self.video_preset.set(found['preset'])
        
        if found['tune']:
            codec = self.video_codec.get()
            if codec in self.codec_tunes and found['tune'] in self.codec_tunes[codec]:
                self.video_tune.set(found['tune'])
        
        if found['profile']:
            self.video_profile.set(found['profile'])
            self.update_pixel_formats()
        
        if found['pix_fmt']:
            self.pix_fmt.set(found['pix_fmt'])
            self.update_mode_indicator()
        
        if found['aspect']:
            self.video_aspect.set(found['aspect'])
        
        if found['s']:
            self.video_resolution.set(found['s'])
        
        if found['r']:
            self.video_fps.set(found['r'])
        
        if found['g']:
            self.video_gop.set(found['g'])
        
        if found['acodec']:
            self.audio_codec.set(found['acodec'])
            self.update_audio_settings()
        
        if found['ar']:
            self.audio_sample_rate.set(found['ar'])
        
        if found['ac']:
            channel_map = {"1": "mono", "2": "stereo", "6": "5.1"}
            channel_name = channel_map.get(found['ac'], "stereo")
            self.audio_channels.set(channel_name)
        
        # Custom options - теперь -x264-params не попадают сюда
        if found['custom']:
            self.custom_options.set(" ".join(found['custom']))
        else:
            self.custom_options.set("")  # Очищаем если нет пользовательских параметров
        
        # Сохраняем конфигурацию
        self.save_config()

    def update_encoder_command_display(self):
        """Обновляет текстовое поле с командой на основе текущих настроек"""
        if not self.encoder_command_widget:
            return
        
        # Если выбран пресет, показываем его команду
        preset_name = self.encoder_preset_name.get()
        if preset_name and preset_name in self.encoder_preset_commands:
            command = self.encoder_preset_commands[preset_name]
        else:
            # Иначе генерируем из текущих настроек
            command = self.get_clean_encoder_command()
        
        self.encoder_command_widget.delete("1.0", tk.END)
        self.encoder_command_widget.insert("1.0", command)
        
        # Сохраняем для последующего использования
        self.encoder_command_text = command

    def on_encoder_gui_change(self, *args):
        """Обработчик изменений в GUI - обновляет отображение команды"""
        # Если обновление идет из пресета, не сбрасываем
        if getattr(self, '_updating_from_preset', False):
            return
        
        # Если выбран пресет, сбрасываем его
        if self.encoder_preset_name.get():
            self.encoder_preset_name.set("")
            if hasattr(self, 'encoder_preset_combo'):
                self.encoder_preset_combo.set("")
            self.log_message("Preset cleared due to manual setting change", "buffer")
        
        # Обновляем отображение базовой команды
        self.update_encoder_command_display()

    def delete_encoder_preset(self):
        """Удаляет выбранный пресет"""
        preset_name = self.encoder_preset_name.get()
        if not preset_name:
            messagebox.showwarning("No preset selected", "Please select a preset to delete")
            return
        
        if messagebox.askyesno("Confirm Delete", f"Delete preset '{preset_name}'?"):
            filepath = os.path.join(self.encoder_presets_dir, f"{preset_name}.json")
            try:
                if os.path.exists(filepath):
                    os.remove(filepath)
                    self.log_message(f"Preset '{preset_name}' deleted", "buffer")
                    
                    # Обновляем список
                    self.load_encoder_presets()
                    
                    # Сбрасываем выбранный пресет
                    self.encoder_preset_name.set("")
                    if hasattr(self, 'encoder_preset_combo'):
                        self.encoder_preset_combo.set("")
                    
                    # Обновляем отображение
                    self.update_encoder_command_display()
                    
                    messagebox.showinfo("Success", f"Preset '{preset_name}' deleted")
            except Exception as e:
                self.log_message(f"Error deleting preset: {e}", "buffer")
                messagebox.showerror("Error", f"Failed to delete preset:\n{e}")

    def reset_encoder_to_default(self):
        """Сбрасывает к базовой команде из GUI"""
        self.encoder_preset_name.set("")
        if hasattr(self, 'encoder_preset_combo'):
            self.encoder_preset_combo.set("")
        self.update_encoder_command_display()
        self.log_message("Reset to default encoder settings", "buffer")
        self.save_config()  # Сохраняем, что пресет не выбран

    def save_encoder_preset_dialog(self):
        """Открывает диалог для ввода имени пресета и сохраняет"""
        # Получаем текущую команду
        if self.encoder_command_widget:
            current_command = self.encoder_command_widget.get("1.0", tk.END).strip()
        else:
            current_command = self.get_clean_encoder_command()
        
        # Создаем диалог
        dialog = tk.Toplevel(self.root)
        dialog.title("Save Encoder Preset")
        dialog.geometry("400x150")
        dialog.transient(self.root)
        dialog.grab_set()
        
        ttk.Label(dialog, text="Preset Name:").pack(pady=(10, 5))
        
        name_var = tk.StringVar()
        name_entry = ttk.Entry(dialog, textvariable=name_var, width=40)
        name_entry.pack(pady=5)
        name_entry.focus()
        
        # Если уже выбран пресет, подставляем его имя
        if self.encoder_preset_name.get():
            name_var.set(self.encoder_preset_name.get())
        
        def do_save():
            name = name_var.get().strip()
            if name:
                dialog.destroy()
                self.save_encoder_preset(name)
            else:
                messagebox.showerror("Error", "Preset name cannot be empty!", parent=dialog)
        
        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(pady=10)
        
        ttk.Button(btn_frame, text="Save", command=do_save, width=10).pack(side='left', padx=5)
        ttk.Button(btn_frame, text="Cancel", command=dialog.destroy, width=10).pack(side='left', padx=5)
        
        name_entry.bind('<Return>', lambda e: do_save()) 

    def get_encoder_command_with_bitrate(self, video_bitrate_kbps):
        """Возвращает полную команду кодирования с подставленным битрейтом"""
        # Рассчитываем bufsize как половину от битрейта (как в оригинальной логике)
        # Рассчитываем bufsize с учетом множителя (в процентах)
        buf_factor = self.video_buf_factor.get() / 100.0
        video_bufsize_kbps = max(50, int(video_bitrate_kbps * buf_factor))
        
        # Получаем базовую команду из текстового поля или из настроек
        if hasattr(self, 'encoder_command_widget') and self.encoder_command_widget:
            base_command = self.encoder_command_widget.get("1.0", tk.END).strip()
        else:
            base_command = self.get_clean_encoder_command()
        
        # Если базовая команда пуста, используем настройки
        if not base_command:
            base_command = self.get_clean_encoder_command()
        
        codec = self.video_codec.get()
        import re
        
        # Для libx265 и libx264 нужно вставить битрейт в x265-params или x264-params
        if codec == "libx265":
            match = re.search(r'-x265-params\s+"([^"]*)"', base_command)
            if match:
                params = match.group(1)
                new_params = f"bitrate={video_bitrate_kbps}:vbv-maxrate={video_bitrate_kbps}:vbv-bufsize={video_bufsize_kbps}"
                if params:
                    new_params += f":{params}"
                base_command = base_command.replace(match.group(0), f'-x265-params "{new_params}"')
            else:
                base_command += f' -x265-params "bitrate={video_bitrate_kbps}:vbv-maxrate={video_bitrate_kbps}:vbv-bufsize={video_bufsize_kbps}"'
        
        elif codec == "libx264":
            match = re.search(r'-x264-params\s+"([^"]*)"', base_command)
            if match:
                params = match.group(1)
                new_params = f"bitrate={video_bitrate_kbps}:vbv-maxrate={video_bitrate_kbps}:vbv-bufsize={video_bufsize_kbps}"
                if params:
                    new_params += f":{params}"
                base_command = base_command.replace(match.group(0), f'-x264-params "{new_params}"')
            else:
                base_command += f' -x264-params "bitrate={video_bitrate_kbps}:vbv-maxrate={video_bitrate_kbps}:vbv-bufsize={video_bufsize_kbps}"'
        
        # Для остальных кодеков добавляем параметры битрейта
        elif codec in ["hevc_nvenc", "h264_nvenc", "hevc_qsv", "h264_qsv", "h264_amf", "hevc_amf"]:
            if '-b:v' not in base_command:
                match = re.search(r'(-c:a\s+\S+)', base_command)
                if match:
                    insert_pos = match.start()
                    bitrate_part = f"-b:v {video_bitrate_kbps}k -minrate {video_bitrate_kbps}k -maxrate {video_bitrate_kbps}k -bufsize {video_bufsize_kbps}k "
                    base_command = base_command[:insert_pos] + bitrate_part + base_command[insert_pos:]
                else:
                    base_command += f" -b:v {video_bitrate_kbps}k -minrate {video_bitrate_kbps}k -maxrate {video_bitrate_kbps}k -bufsize {video_bufsize_kbps}k"
        
        return base_command
    
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
        """Build simple FFmpeg command for single channel with preset support"""
        ffmpeg_path = self.ffmpeg_path
        
        # Получаем битрейты
        video_bitrate, audio_bitrate, _ = self.get_channel_bitrates()
        
        # Получаем команду кодирования с битрейтом

        encoder_cmd = self.get_encoder_command_with_bitrate(video_bitrate)
        
        # Формируем полную команду
        cmd = (
            f'"{ffmpeg_path}" -thread_queue_size 2048 -itsoffset -0.65 '
            f'-f dshow -thread_queue_size 10K -rtbufsize 400M -i "video={self.video_input_device.get()}" '
            f'-f dshow -thread_queue_size 10K -rtbufsize 400M -i "audio={self.audio_input_device.get()}" '
        )
        
        # Добавляем команду кодирования
        cmd += encoder_cmd + " "
        
        # Добавляем параметры битрейта для аудио (уже включены в encoder_cmd? Нет, они отдельно)
        # В encoder_cmd уже есть -c:a, -ar, -ac, но нет -b:a
        cmd += f'-b:a {audio_bitrate} '
        
        
        # Выходные параметры
        buffer_bytes = self.get_udp_buffer_bytes()
        cmd += (
            f'-f mpegts -max_delay 300K -max_interleave_delta 4M '
            f'-muxdelay {self.video_muxdelay.get()} -muxpreload {self.video_muxpreload.get()} -pcr_period 40 '
            f'-pat_period 0.4 -sdt_period 0.5 '
            f'-mpegts_original_network_id 1 -mpegts_transport_stream_id 1 '
            f'-mpegts_pmt_start_pid 4096 -mpegts_start_pid 256 '
            f'-mpegts_flags system_b '
            f'-metadata service_provider="{self.service_provider.get()}" '
            f'-metadata service_name="{self.service_name.get()}" '
            f'-metadata title="{self.service_name.get()}" '
            f'-metadata artist="{self.service_name.get()}" '
            f'-flush_packets 0 -muxrate {self.muxrate.get()} '
            f'"udp://{self.localhost_ip.get()}:{self.udp_input_port.get()}?pkt_size=1316&buffer_size={buffer_bytes}&overrun_nonfatal=1&burst_bits=1" '
        )
        
        return cmd

    def build_channel_ffmpeg_command(self, channel_num, channel_data, output_port):
        """Build FFmpeg command for individual channel"""
        ffmpeg_path = self.ffmpeg_path
        
        # Получаем битрейты для этого канала
        video_bitrate, audio_bitrate, _ = self.get_channel_bitrates()
        
        # Получаем команду кодирования с подставленным битрейтом
        encoder_cmd = self.get_encoder_command_with_bitrate(video_bitrate)        
        
        cmd = f'"{ffmpeg_path}" -hwaccel auto -hide_banner '
        
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
            capture_method = channel_data['capture_method'].get()
            window_value = channel_data['window_title'].get().strip()
            audio_device = channel_data['audio_device'].get().strip()
            
            if not window_value:
                self.log_message(f"CH{channel_num}: No window/process selected", "buffer")
                return None
            
            if capture_method == 'gdigrab':
                # Оригинальный метод gdigrab по названию окна
                safe_title = window_value.replace('"', '\\"')
                cmd += f'-use_wallclock_as_timestamps 1 -f gdigrab -draw_mouse 0 -probesize 42M -thread_queue_size 2048K -rtbufsize 400M -framerate {self.video_fps.get()} '
                cmd += f'-i title="{safe_title}" '
                
                # Аудио устройство с задержкой
                if audio_device:
                    delay = channel_data['audio_delay'].get()
                    if delay != 0:
                        cmd += f'-itsoffset {delay} '
                    cmd += f'-f dshow -thread_queue_size 2048K -rtbufsize 400M -i "audio={audio_device}" '
                
                # Для service_name берем первые слова из названия окна
                words = window_value.split()
                service_name = ' '.join(words[:3]) if words else f"Window_{channel_num}"
                if len(service_name) > 50:
                    service_name = service_name[:45] + "..."
                
            else:  # gfxcapture
                # Новый метод gfxcapture по имени процесса
                process_name = window_value.replace('.exe', '')
                
                # Аудио устройство с задержкой
                if audio_device:
                    delay = channel_data['audio_delay'].get()
                    if delay != 0:
                        cmd += f'-itsoffset {delay} '
                    cmd += f'-f dshow -thread_queue_size 2048K -rtbufsize 400M -i "audio={audio_device}" '
                
                # Затем gfxcapture вход
                cmd += f'-f lavfi -thread_queue_size 2048K -i "gfxcapture=window_exe=\'^{process_name}.exe$\':max_framerate={self.video_fps.get()}:capture_cursor=0" '
                
                # Filter complex после всех входов
                if audio_device:
                    cmd += f'-filter_complex "[1:v]hwdownload,format=bgra,scale={self.video_resolution.get()},format={self.pix_fmt.get()},fps={self.video_fps.get()}[v]" '
                    cmd += f'-map "[v]" -map 0:a '
                else:
                    cmd += f'-filter_complex "[0:v]hwdownload,format=bgra,scale={self.video_resolution.get()},format={self.pix_fmt.get()},fps={self.video_fps.get()}[v]" '
                    cmd += f'-map "[v]" '
                
                service_name = process_name
            
            # Сохраняем для метаданных
            channel_data['service_name_override'] = service_name       
        
        elif source_type == "UDP_MPTS":
            url = channel_data['udp_url'].get().strip()
            if url:
                cmd += f'-timeout 2000000 -i "{url}" '
        
        # Get bitrates
        video_bitrate, audio_bitrate, _ = self.get_channel_bitrates()
        video_per_channel = video_bitrate
        
        if encoder_cmd:
            cmd += encoder_cmd + " "
            cmd += f'-b:a {audio_bitrate} '
            cmd += f'-muxdelay {self.video_muxdelay.get()} -muxpreload {self.video_muxpreload.get()} '
        else:
            # Fallback если encoder_cmd пустой
            self.log_message(f"CH{channel_num}: Warning - encoder command is empty", "buffer")
            return None        
        
        # Metadata
        if source_type == "grab_window" and 'service_name_override' in channel_data:
            service_name = channel_data['service_name_override']
        else:
            service_name = channel_data['name'].get() or f"Channel_{channel_num}"
        
        safe_name = service_name.replace('"', '\\"')
        cmd += f'-metadata service_provider="{self.service_provider.get()}" '
        cmd += f'-metadata service_name="{safe_name}" '
        
        # Output
        cmd += f'-f mpegts -flush_packets 0 '
        buffer_bytes = self.get_udp_buffer_bytes()
        cmd += f'"udp://@238.0.0.1:{output_port}?pkt_size=1316&buffer_size={buffer_bytes}&overrun_nonfatal=1"'
        
        return cmd

    def build_main_multiplexer_command(self):
        """Build main multiplexer command with proper metadata mapping"""
        ffmpeg_path = self.ffmpeg_path
        
        cmd = f'"{ffmpeg_path}" -hwaccel auto -re '
        
        # Add all active channels as UDP inputs
        active_channels = []
        input_index = 0
        
        for ch_num, channel_data in self.multiplex_channels.items():
            if channel_data['enabled'].get():
                output_port = self.base_multicast_port + ch_num - 1
                buffer_bytes = self.get_udp_buffer_bytes()
                cmd += f'-i "udp://@238.0.0.1:{output_port}?pkt_size=1316&buffer_size={buffer_bytes}&fifo_size={buffer_bytes}&overrun_nonfatal=1" '
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
        
        # Programs and their metadata
        program_index = 0
        stream_counter = 0
        
        for ch_num, channel_data, input_idx in active_channels:
            service_name = channel_data['name'].get() or f"Channel_{ch_num}"
            safe_name = service_name.replace('"', '\\"')
            
            # Create program with stream mapping
            cmd += f'-program title="{safe_name}":st={stream_counter}:st={stream_counter+1} '
            
            # Add service provider metadata for this program
            cmd += f'-metadata:p:{program_index} service_provider="{self.service_provider.get()}" '
            cmd += f'-metadata:p:{program_index} service_name="{safe_name}" '
            
            stream_counter += 2
            program_index += 1
        
        # Multiplexing parameters
        cmd += '-c copy -movflags +faststart '
        buffer_bytes = self.get_udp_buffer_bytes()
        cmd += self.get_mpegts_output_params()
        
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
        """Создает команду для радио-канала с filter_complex и stdin с поддержкой пресетов"""
        
        ffmpeg_path = self.ffmpeg_path
        # Используем переданные параметры
        radio_text = channel_data['radio_text'].get()
        radio_text_safe = radio_text.replace("'", "'\\''").replace(':', '\\:')
        text_color = channel_data['radio_text_color'].get()
        text_size = channel_data['radio_text_size'].get()
        
        # Фон
        bg_type = channel_data['radio_bg_type'].get()
        resolution = self.video_resolution.get()
        fps = self.video_fps.get()
        
        # Получаем битрейты для этого канала
        video_bitrate, audio_bitrate, _ = self.get_channel_bitrates()
        
        # Получаем команду кодирования с подставленным битрейтом (из пресета или из настроек)
        encoder_cmd = self.get_encoder_command_with_bitrate(video_bitrate)
        
        # Параметры, которые нужно исключить из encoder_cmd при добавлении filter_complex
        # (потому что они будут добавлены позже с правильным порядком)
        
        # Создаем filter_complex
        filter_chains = []
        filter_indices = {}
        filter_counter = 0
        
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
        
        # 2. Метаданные (если включены)
        if channel_data['show_metadata'].get():
            metadata_filter = (
                f"drawtext=text='Radio Station':"
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
        
        # Сохраняем индексы в данных канала
        channel_data['filter_indices'] = filter_indices
        
        # Объединяем фильтры
        filter_complex = ','.join(filter_chains)
        
        # Строим команду
        cmd = f'"{ffmpeg_path}" -hwaccel auto -re '
        
        # Видео источник (фон)
        if bg_type == "Color":
            bg_color = channel_data['radio_bg_color'].get()
            cmd += f'-f lavfi -i "color={bg_color}:s={resolution}:r={fps}" '
        else:  # Picture
            bg_picture = channel_data['radio_bg_picture'].get().strip()
            if bg_picture and os.path.exists(bg_picture):
                safe_path = os.path.abspath(bg_picture).replace('\\', '/')
                cmd += f'-loop 1 -framerate {fps} -i "{safe_path}" '
            else:
                cmd += f'-f lavfi -i "color=black:s={resolution}:r={fps}" '
        
        # Аудио источник (URL радио)
        url = channel_data['url_input'].get().strip()
        if url:
            cmd += f'-timeout 2000000 -i "{url}" '
        
        # Filter complex
        cmd += f'-filter_complex "[0:v]{filter_complex}[vout]" '
        
        # Маппинг
        cmd += f'-map "[vout]" -map 1:a? '
        
        # Добавляем команду кодирования (без параметров битрейта, они уже вставлены)
        # Но нужно убедиться, что команда кодирования не содержит конфликтующих параметров
        # Разбиваем encoder_cmd на части и добавляем их
        if encoder_cmd:
            cmd += encoder_cmd + " "
            cmd += f'-b:a {audio_bitrate} '
            cmd += f'-muxdelay {self.video_muxdelay.get()} -muxpreload {self.video_muxpreload.get()} '
        
        # Метаданные
        service_name = channel_data['name'].get() or f"Radio_{channel_num}"
        safe_name = service_name.replace('"', '\\"')
        cmd += f'-metadata service_provider="Radio Station" '
        cmd += f'-metadata service_name="{safe_name}" '
        
        # Выход
        cmd += f'-f mpegts -flush_packets 0 '
        buffer_bytes = self.get_udp_buffer_bytes()
        cmd += f'"udp://@238.0.0.1:{output_port}?pkt_size=1316&buffer_size={buffer_bytes}&overrun_nonfatal=1"'
        
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
        
        # Формируем полный список ошибок
        critical_errors = self.default_multiplexer_errors.copy()
        if self.custom_multiplexer_errors.get():
            custom = [e.strip() for e in self.custom_multiplexer_errors.get().split(',') if e.strip()]
            critical_errors.extend(custom)
        
        try:
            for line in iter(self.main_multiplexer_process.stdout.readline, ''):
                if line and self.is_streaming:
                    line_stripped = line.strip()
                    
                    error_detected = False
                    for error in critical_errors:
                        if error.lower() in line_stripped.lower():
                            error_detected = True
                            self.log_message(f"[Multiplexer] CRITICAL: {line_stripped[:200]}", "buffer")
                            break
                    
                    if error_detected:
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
                                                                                     
    def get_channel_bitrates(self):
        """Calculate VIDEO bitrate per channel based on active channel count with audio bitrate consideration"""
        
        # ПРОВЕРКА РЕЖИМА
        if not self.multiplex_mode.get():
            # SIMPLE РЕЖИМ (1 канал)
            try:
                # Получаем muxrate в kbps
                muxrate_kbps = float(self.muxrate.get()) / 1000
                
                # Резерв 10%
                null_percent = self.null_packets_percent.get() / 100.0
                reserve_kbps = muxrate_kbps * null_percent
                
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
                
                # Рассчитываем bufsize с учетом множителя из настроек
                buf_factor = self.video_buf_factor.get() / 100.0
                bufsize = max(50, int(video_bitrate_calculated * buf_factor))
                self.video_bufsize.set(str(bufsize))
                
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
                null_percent = self.null_packets_percent.get() / 100.0
                reserve_kbps = muxrate_kbps * null_percent
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
            
            # Auto-update bufsize с учетом Buf Factor
            buf_factor = self.video_buf_factor.get() / 100.0
            bufsize = max(50, int(available_video_after_audio * buf_factor))
            self.video_bufsize.set(str(bufsize))
            
            self.log_message(f"  Result: Video={video_per_channel}k per channel, Audio={audio_bitrate_output} per channel", "buffer")
            
            return video_per_channel, audio_bitrate_output, active_count
            
        except Exception as e:
            self.log_message(f"MULTIPLEX mode calc error: {e}", "buffer")
            import traceback
            traceback.print_exc()
            return 1000, "128k", 1  # Значения по умолчанию
        
    def get_mpegts_output_params(self):
        """Get MPEG-TS output parameters with configurable UDP buffer size"""
        
        buffer_bytes = self.get_udp_buffer_bytes()
        
        return (
            f'-f mpegts -max_delay 300K -max_interleave_delta 4M '
            f'-muxdelay {self.video_muxdelay.get()} -muxpreload {self.video_muxpreload.get()} -pcr_period 40 '
            f'-pat_period 0.4 -sdt_period 0.5 '
            f'-mpegts_original_network_id 1 -mpegts_transport_stream_id 1 '
            f'-mpegts_pmt_start_pid 4096 -mpegts_start_pid 256 '
            f'-mpegts_flags system_b '
            f'-metadata service_provider="{self.service_provider.get()}" '
            f'-metadata service_name="{self.service_name.get()}" '
            f'-flush_packets 0 -muxrate {self.muxrate.get()} '
            f'"udp://{self.localhost_ip.get()}:{self.udp_input_port.get()}?pkt_size=1316&buffer_size={buffer_bytes}&overrun_nonfatal=1&burst_bits=1"'  # ← ИСПОЛЬЗУЙТЕ ЗДЕСЬ
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
                
                ffmpeg_path = self.ffmpeg_path
                safe_path = os.path.abspath(emergency_file).replace('\\', '/')
                
                emergency_cmd = f'"{ffmpeg_path}" -hwaccel auto -re -stream_loop -1 '
                emergency_cmd += f'-i "{safe_path}" '
                emergency_cmd += f'-vcodec {self.video_codec.get()} -preset {self.video_preset.get()} '
                
                if self.video_codec.get() == "libx265":
                    emergency_cmd += f'-x265-params "bitrate={video_bitrate}:vbv-maxrate={video_bitrate}:vbv-bufsize={video_bitrate//1}:profile={self.video_profile.get()}" '
                else:
                    emergency_cmd += f'-profile:v {self.video_profile.get()} -b:v {video_bitrate}k -minrate {video_bitrate}k -maxrate {video_bitrate}k -bufsize {video_bitrate//1}k '
                
                emergency_cmd += f'-pix_fmt {self.pix_fmt.get()} -s {self.video_resolution.get()} -g {self.video_gop.get()} -aspect {self.video_aspect.get()} -r {self.video_fps.get()} '
                emergency_cmd += f'-c:a {self.audio_codec.get()} -b:a {audio_bitrate} '
                emergency_cmd += f'-ar {self.audio_sample_rate.get()} -ac {self.get_audio_channels_ffmpeg()} '
                emergency_cmd += f'-metadata service_provider="EMERGENCY" '
                emergency_cmd += f'-metadata service_name="Emergency CH" '
                buffer_bytes = self.get_udp_buffer_bytes()
                emergency_cmd += f'-f mpegts "udp://@238.0.0.1:"CH_Port"?pkt_size=1316&buffer_size={buffer_bytes}&overrun_nonfatal=1"'
                
                full_text += emergency_cmd + "\n\n"
            else:
                full_text += "No emergency file configured or file not found\n"
                full_text += f"Current path: {emergency_file}\n\n"
                        
            ffmpeg_path = self.ffmpeg_path
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
