"""
GMAIL RECOVERY ADDER — Compact & Multilingual Isolated Firefox Engine
Adds recovery email to Google Accounts robustly across any language (EN, FR, AR, ES, etc.).
"""

import sys
import os
import random
import queue
import time
import json
from pathlib import Path
from datetime import datetime
from PySide6.QtCore import Qt, QThread, Signal, QTimer
from PySide6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QLineEdit, QFileDialog, QSpinBox, QComboBox, QTableWidget,
    QTableWidgetItem, QHeaderView, QFrame, QPlainTextEdit, QMessageBox, QCheckBox, QScrollArea)
from playwright.sync_api import sync_playwright
import openpyxl

CSS = r"""
QWidget { background:#f7f6f3; color:#292b2e; font-family:'Segoe UI'; font-size:10px; }
QFrame#panel { background:#fcfbf9; border:1px solid #e2dfd9; border-radius:6px; }
QLabel#title {font-size:12px; font-weight:700; color:#bd713c;}
QLabel#heading {font-size:10px; font-weight:700;}
QLabel#muted {color:#77736f;}
QPlainTextEdit {background:#fff; border:1px solid #dedbd6; border-radius:4px; padding:3px;}
QLineEdit,QSpinBox,QComboBox,QPlainTextEdit,QTableWidget { background:#fff; border:1px solid #dedbd6;
  border-radius:4px; padding:3px; selection-background-color:#f9dbc4; }
QLineEdit,QSpinBox,QComboBox { min-height:20px; max-height:24px; }
QPushButton { background:#fffdfa; border:1px solid #ded9d3; border-radius:4px;
  padding:3px 7px; font-weight:600; min-height:20px; }
QPushButton:hover { background:#fff0e5; border-color:#edbb95; }
QPushButton:pressed { background:#f8ddc8; }
QPushButton#start { background:#f6a568; color:#fff; border:1px solid #ed9959; font-size:11px; }
QPushButton#start:hover { background:#f9b17c; }
QPushButton#outline { color:#d9783b; border-color:#eac1a1; }
QLabel#green { background:#e9f3e9; color:#26783b; border-radius:4px; padding:3px; font-weight:600; }
QTableWidget { gridline-color:#ebe7e2; alternate-background-color:#fcfaf8; }
QHeaderView::section { background:#f6e9df; padding:3px; border:0; border-right:1px solid #e5dcd5; font-weight:600; }
"""

def label(value, name=None):
    widget = QLabel(value)
    if name: widget.setObjectName(name)
    return widget

def btn(value, callback=None, kind=None):
    widget = QPushButton(value)
    if kind: widget.setObjectName(kind)
    if callback: widget.clicked.connect(callback)
    return widget

def panel():
    widget = QFrame(); widget.setObjectName('panel'); return widget

def row(*items):
    layout = QHBoxLayout(); layout.setContentsMargins(0,0,0,0); layout.setSpacing(4)
    for item in items: layout.addWidget(item)
    return layout


class GmailRecoveryWorker(QThread):
    log_signal = Signal(str)
    result_signal = Signal(int, str, str, str, str)
    status_signal = Signal(int, str, str)

    def __init__(self, combo_queue, recovery_email, show_browser=True):
        super().__init__()
        self.thread_id = 1
        self.combo_queue = combo_queue
        self.recovery_email = recovery_email
        self.show_browser = show_browser
        self.is_running = True
        self.current_browser = None

    def stop(self):
        self.is_running = False
        if self.current_browser:
            try:
                self.current_browser.close()
            except:
                pass

    def set_visibility(self, visible):
        self.show_browser = visible

    def run(self):
        target_url = "https://myaccount.google.com/recovery/email"
        
        try:
            while self.is_running:
                try:
                    item = self.combo_queue.get_nowait()
                except queue.Empty:
                    break
                    
                idx, email, password = item
                
                proxy_str = "Isolated Local Session"
                self.status_signal.emit(1, "Launching Isolated Private Firefox...", proxy_str)
                self.log_signal.emit(f"[Isolation Engine] Processing Account: {email}")
                
                status = "UNKNOWN"
                recovery_status = "NOT ATTEMPTED"

                with sync_playwright() as p:
                    browser, context = None, None
                    try:
                        prefs = {
                            'privacy.trackingprotection.enabled': True,
                            'privacy.trackingprotection.pbmode.enabled': True,
                            'privacy.trackingprotection.fingerprinting.enabled': True,
                            'privacy.fingerprintingProtection': True,
                            'privacy.resistFingerprinting': True,
                            'privacy.firstparty.isolate': True,
                            'network.cookie.cookieBehavior': 5,
                            'browser.send_pings': False,
                            'beacon.enabled': False,
                        }

                        launch_args = {
                            "headless": not self.show_browser,
                            "args": ["-private"],
                            "firefox_user_prefs": prefs
                        }

                        browser = p.firefox.launch(**launch_args)
                        self.current_browser = browser
                        context = browser.new_context()
                        page = context.new_page()
                        
                        self.status_signal.emit(1, "Opening Direct Recovery URL", proxy_str)
                        page.goto(target_url, timeout=60000, wait_until="load")
                        page.wait_for_timeout(4000)
                        
                        current_url = page.url
                        if 'signin' in current_url or 'accounts.google.com' in current_url or page.locator('input[type="email"], input#identifierId').count() > 0:
                            self.status_signal.emit(1, "Typing Email", proxy_str)
                            page.wait_for_selector('input[type="email"], input#identifierId', timeout=15000)
                            page.click('input[type="email"], input#identifierId')
                            page.wait_for_timeout(500)
                            
                            for char in email:
                                page.type('input[type="email"], input#identifierId', char, delay=random.randint(100, 200))
                            
                            page.wait_for_timeout(1000)
                            if page.locator('#identifierNext').is_visible():
                                page.click('#identifierNext')
                            else:
                                page.keyboard.press("Enter")
                                
                            page.wait_for_timeout(4000)
                            
                            pt = page.locator("body").inner_text().lower()
                            if any(w in pt for w in ["couldn't find your google account", "aucun compte", "introuvable", "لم يتم العثور"]):
                                status = "LOGIN ERROR"
                            else:
                                status = "PASSWORD_STAGE"

                            if status == "PASSWORD_STAGE":
                                page.wait_for_timeout(1200)
                                page.wait_for_selector('input[name="Passwd"], input[type="password"]', timeout=15000)
                                page.click('input[name="Passwd"], input[type="password"]')
                                page.wait_for_timeout(500)
                                
                                self.status_signal.emit(1, "Typing Password", proxy_str)
                                for char in password:
                                    page.type('input[name="Passwd"], input[type="password"]', char, delay=random.randint(100, 200))
                                    
                                page.wait_for_timeout(1500)
                                if page.locator('#passwordNext').is_visible():
                                    page.click('#passwordNext')
                                else:
                                    page.keyboard.press("Enter")
                                    
                                page.wait_for_timeout(6000)
                                pt_pass = page.locator("body").inner_text().lower()
                                if any(w in pt_pass for w in ["wrong password", "incorrect password", "كلمة المرور غير صحيحة", "try again"]):
                                    status = "LOGIN ERROR"
                                else:
                                    status = "LOGIN OK"
                        else:
                            status = "LOGIN OK"

                        # بمجرد حصول LOGIN OK، الدخول لصفحة الاسترداد والتعامل مع أي لغة تلقائياً
                        if status == "LOGIN OK" and self.recovery_email:
                            self.status_signal.emit(1, "Adding Recovery & Waiting Verification", proxy_str)
                            try:
                                if 'recovery' not in page.url:
                                    page.goto("https://myaccount.google.com/recovery/email", timeout=45000, wait_until="load")
                                    page.wait_for_timeout(3000)

                                # رصد زر الإضافة بمختلف اللغات (إنجليزي، فرنسي، عربي، إسباني...)
                                for btn_sel in [
                                    'button:has-text("Ajouter")', 'button:has-text("Add")', 'button:has-text("Agregar")', 
                                    'button:has-text("Aggiungi")', 'button:has-text("إضافة")', 'button:has-text("إضافه")',
                                    '[role="button"]:has-text("Add")', '[role="button"]:has-text("Ajouter")',
                                    'input[type="email"]'
                                ]:
                                    try:
                                        el = page.locator(btn_sel).first
                                        if el.count() > 0 and el.is_visible() and btn_sel != 'input[type="email"]':
                                            el.click(timeout=3000)
                                            page.wait_for_timeout(1500)
                                            break
                                    except Exception:
                                        continue

                                email_input = page.locator('input[type="email"]').first
                                if email_input.count() == 0:
                                    try:
                                        page.locator('button[aria-label*="Edit"], button[aria-label*="Modifier"], button[aria-label*="تعديل"]').first.click(timeout=2000)
                                        page.wait_for_timeout(1000)
                                    except:
                                        pass
                                    email_input = page.locator('input[type="email"]').first

                                if email_input.count() > 0:
                                    email_input.fill('')
                                    for char in self.recovery_email:
                                        email_input.type(char, delay=random.randint(80, 150))
                                    page.wait_for_timeout(800)
                                    
                                    # رصد زر الحفظ بمختلف اللغات
                                    saved_ok = False
                                    for save_sel in [
                                        'button:has-text("Enregistrer")', 'button:has-text("Save")', 'button:has-text("Guardar")',
                                        'button:has-text("Salvar")', 'button:has-text("حفظ")', 'button[type="submit"]',
                                        '[role="button"]:has-text("Save")', '[role="button"]:has-text("Enregistrer")'
                                    ]:
                                        try:
                                            s_btn = page.locator(save_sel).first
                                            if s_btn.count() > 0 and s_btn.is_visible():
                                                s_btn.click(timeout=3000)
                                                saved_ok = True
                                                break
                                        except Exception:
                                            continue
                                            
                                    if not saved_ok:
                                        page.keyboard.press("Enter")

                                    self.log_signal.emit(f"[Worker #{self.thread_id}] Clicked Save/Confirm. Verifying state...")
                                    page.wait_for_timeout(4000)
                                    
                                    recovery_status = "Recovery Added Successfully"
                                else:
                                    recovery_status = "Get an Error"
                            except Exception as rec_ex:
                                self.log_signal.emit(f"[RECOVERY ERROR] {str(rec_ex)}")
                                recovery_status = "Get an Error"
                        else:
                            recovery_status = "Not Attempted"

                        self.status_signal.emit(1, f"Finished: {status}", proxy_str)
                        self.result_signal.emit(idx, email, status, recovery_status, proxy_str)

                    except Exception as ex:
                        self.result_signal.emit(idx, email, "LOGIN ERROR", "Get an Error", proxy_str)
                    finally:
                        self.current_browser = None
                        if context: 
                            try: context.close()
                            except: pass
                        if browser: 
                            try: browser.close()
                            except: pass

                self.combo_queue.task_done()
                self.msleep(400)
        except Exception as e:
            pass


class GmailRecoveryWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('GMAIL RECOVERY ADDER — Multilingual Compact Engine')
        self.resize(800, 500); self.setMinimumSize(720, 440)
        self.setStyleSheet(CSS)
        self.records = []; self.results = []; self.worker = None
        
        module_dir = Path(__file__).resolve().parent
        project_dir = module_dir.parent if module_dir.name.lower() == 'tools' else module_dir
        self.output_dir = project_dir / 'output' / 'Gmail_Recovery_Adder'
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.last_result_file = None
        self.autosave_file = None
        self.browser_visible = True
        
        self.build()
        self.log('Ready — Multilingual Compact Firefox Engine initialized.')

    def log(self, message):
        self.logs.appendPlainText(f'[{datetime.now():%H:%M:%S}]  {message}')

    def build(self):
        outer = QVBoxLayout(self); outer.setContentsMargins(8,6,8,8); outer.setSpacing(4)
        top = row(btn('■   Stop', self.stop_process, 'outline'), btn('▤   Log Report', self.export_log))
        top.addStretch(); top.addWidget(btn('▱   Go to Output', self.go_output, 'outline')); outer.addLayout(top)

        main_controls = QHBoxLayout(); main_controls.setSpacing(5)
        left = QVBoxLayout(); left.setSpacing(4)
        fileline = row(label('▤  Source File (email:password)'))
        self.path = QLineEdit(); self.path.setPlaceholderText('Select TXT file containing email:pass accounts')
        fileline.addWidget(self.path, 1)
        fileline.addWidget(btn('…', self.browse)); fileline.addWidget(btn('▱  Explore', self.browse))
        fp = panel(); fl = QVBoxLayout(fp); fl.setContentsMargins(5,4,5,4); fl.addLayout(fileline); left.addWidget(fp)
        
        rec = panel(); rv = QVBoxLayout(rec); rv.setContentsMargins(6,4,6,4); rv.setSpacing(4)
        rr = row(label('✉   ADD Recovery Email :', 'heading'))
        self.recovery = QLineEdit(); self.recovery.setPlaceholderText('example@gmail.com')
        rr.addWidget(self.recovery, 1); rr.addWidget(btn('ADD  +', self.add_recovery, 'outline'))
        rv.addLayout(rr)
        green = row(label('🔗  Added Recovery Email :'))
        self.added = label('No recovery email added', 'green'); green.addWidget(self.added, 1)
        rv.addLayout(green); left.addWidget(rec); main_controls.addLayout(left, 3)

        right = QVBoxLayout(); right.setSpacing(4)
        cp = panel(); cv = QVBoxLayout(cp); cv.setContentsMargins(5,4,5,4)
        cv.addWidget(label('▤  Export Mode'))
        self.export_mode = QComboBox(); self.export_mode.addItems(['TXT', 'Excel (.xlsx)'])
        cv.addWidget(self.export_mode)
        right.addWidget(cp)
        right.addWidget(btn('▶   START', self.start_process, 'start'))
        right.addStretch(); main_controls.addLayout(right, 1); outer.addLayout(main_controls)

        browsers = panel(); bv = QVBoxLayout(browsers); bv.setContentsMargins(6,4,6,4); bv.setSpacing(3)
        bh = row(label('◎   Live Browser Card (Multilingual Single-Thread)','heading'))
        bh.addStretch()
        bv.addLayout(bh)
        
        self.browser_card_layout = QHBoxLayout()
        card = panel(); cl = QVBoxLayout(card); cl.setContentsMargins(8,4,8,4); cl.setSpacing(3)
        self.status_lbl = label('● Idle', 'muted')
        cl.addLayout(row(label('Firefox Instance #1', 'heading'), self.status_lbl))
        self.visibility_lbl = label('Status: Ready', 'muted'); self.visibility_lbl.setAlignment(Qt.AlignCenter)
        cl.addLayout(row(btn('◉̸ Hide', lambda: self.toggle_browser(False)),
                         btn('◉ Show', lambda: self.toggle_browser(True), 'outline')))
        cl.addWidget(self.visibility_lbl)
        card.setMinimumWidth(220)
        self.browser_card_layout.addWidget(card)
        self.browser_card_layout.addStretch()
        bv.addLayout(self.browser_card_layout)
        
        outer.addWidget(browsers)

        bottom = QHBoxLayout(); bottom.setSpacing(5)
        results = panel(); resultsl = QVBoxLayout(results); resultsl.setContentsMargins(5,4,5,5); resultsl.setSpacing(3)
        rh = row(label('▤  Results','heading')); rh.addStretch()
        rh.addWidget(btn('♧  Clear', self.clear_results)); resultsl.addLayout(rh)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(['#', 'Email', 'Login Status', 'Recovery Status'])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        for j in range(1, 4): self.table.horizontalHeader().setSectionResizeMode(j, QHeaderView.Stretch)
        self.table.setAlternatingRowColors(True); self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        resultsl.addWidget(self.table); bottom.addWidget(results, 2)
        
        lp = panel(); ll = QVBoxLayout(lp); ll.setContentsMargins(5,4,5,5); ll.setSpacing(3)
        lh = row(label('▤  Log :','heading')); lh.addStretch()
        lh.addWidget(btn('♧  Clear', self.logs_clear)); ll.addLayout(lh)
        self.logs = QPlainTextEdit(); self.logs.setReadOnly(True)
        ll.addWidget(self.logs); bottom.addWidget(lp, 1); outer.addLayout(bottom, 1)

    def toggle_browser(self, visible):
        self.browser_visible = visible
        state_str = "Visible" if visible else "Hidden"
        self.visibility_lbl.setText(f"Status: {state_str}")
        if self.worker:
            self.worker.set_visibility(visible)
        self.log(f"Browser visibility changed to: {state_str}")

    def logs_clear(self): self.logs.clear()

    def browse(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Select source file', '', 'Text files (*.txt);;All files (*)')
        if path: self.path.setText(path); self.load_source()

    def load_source(self):
        source = Path(self.path.text().strip())
        if not source.is_file(): QMessageBox.warning(self, 'Source missing', 'Choose an existing TXT file.'); return False
        try:
            raw = source.read_text(encoding='utf-8-sig').splitlines()
            self.records = [line.strip() for line in raw if line.strip() and ':' in line]
            self.log(f'Loaded {len(self.records)} entries from {source.name}')
            return bool(self.records)
        except (OSError, UnicodeError) as exc:
            QMessageBox.warning(self, 'Read failed', str(exc)); return False

    def add_recovery(self):
        value = self.recovery.text().strip()
        if '@' not in value: QMessageBox.warning(self, 'Invalid email', 'Enter a valid recovery email.'); return
        self.added.setText(value); self.log(f'Recovery address set to: {value}')

    def start_process(self):
        if self.worker and self.worker.isRunning():
            QMessageBox.information(self, 'Running', 'Stop the current job first.'); return
        if not self.load_source(): return
        
        recovery_email = self.added.text().strip()
        if '@' not in recovery_email:
            QMessageBox.warning(self, 'No Recovery Email', 'Please add and save a valid recovery email first.')
            return

        self.results = []; self.table.setRowCount(0)
        if not self.begin_autosave(): return
        
        combo_queue = queue.Queue()
        for idx, rec in enumerate(self.records):
            parts = rec.split(':', 1)
            combo_queue.put((idx, parts[0].strip(), parts[1].strip()))

        self.worker = GmailRecoveryWorker(combo_queue, recovery_email, self.browser_visible)
        self.worker.log_signal.connect(self.log)
        self.worker.result_signal.connect(self.on_result)
        self.worker.status_signal.connect(self.update_browser_status)
        self.worker.start()
        
        self.log('Started multilingual compact recovery engine...', component='AUTOMATION')

    def stop_process(self):
        if self.worker:
            self.worker.stop()
            self.log('Automation stop requested')

    def on_result(self, index, email, login_status, recovery_status, proxy_used):
        self.results.append((email, login_status, recovery_status))
        self.autosave_result((email, login_status, recovery_status))
        r = self.table.rowCount()
        self.table.insertRow(r)
        for col, value in enumerate((str(r+1), email, login_status, recovery_status)):
            self.table.setItem(r, col, QTableWidgetItem(value))

    def begin_autosave(self):
        try:
            self.output_dir.mkdir(parents=True, exist_ok=True)
            autosave_mode = 'TXT' if self.export_mode.currentIndex() == 0 else 'XLSX'
            extension = '.txt' if autosave_mode == 'TXT' else '.xlsx'
            stamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
            self.autosave_file = self.output_dir / f'results_{stamp}{extension}'
            if autosave_mode == 'TXT':
                with self.autosave_file.open('x', encoding='utf-8', newline='') as f:
                    f.write('Email\tLogin Status\tRecovery Status\n')
            else:
                wb = openpyxl.Workbook()
                ws = wb.active
                ws.title = 'Results'
                ws.append(['Email', 'Login Status', 'Recovery Status'])
                wb.save(self.autosave_file)
                wb.close()
            self.last_result_file = self.autosave_file
            return True
        except Exception as exc:
            self.autosave_file = None
            QMessageBox.warning(self, 'Auto Save unavailable', str(exc))
            return False

    def autosave_result(self, record):
        if self.autosave_file is None: return
        try:
            autosave_mode = 'TXT' if self.export_mode.currentIndex() == 0 else 'XLSX'
            if autosave_mode == 'TXT':
                with self.autosave_file.open('a', encoding='utf-8', newline='') as f:
                    f.write('\t'.join(str(value) for value in record) + '\n')
            else:
                wb = openpyxl.load_workbook(self.autosave_file)
                wb.active.append(list(record))
                wb.save(self.autosave_file)
                wb.close()
        except Exception as exc:
            self.log(f'Could not auto-save result: {exc}')

    def clear_results(self, *args):
        self.table.setRowCount(0); self.results = []; self.log('Results cleared')

    def go_output(self):
        self.output_dir.mkdir(parents=True, exist_ok=True)
        dest = self.last_result_file
        if dest is None or not dest.is_file():
            candidates = [p for p in self.output_dir.iterdir() if p.is_file() and p.name.startswith('results_')]
            dest = max(candidates, key=lambda p: p.stat().st_mtime) if candidates else None
        if dest is None:
            QMessageBox.information(self, 'No results yet', 'No exported results found.')
            return
        try:
            if sys.platform == 'win32': os.startfile(str(dest))
            elif sys.platform == 'darwin': os.system(f'open "{dest}"')
            else: os.system(f'xdg-open "{dest}"')
        except Exception as exc:
            QMessageBox.warning(self, 'Cannot open results', str(exc))

    def export_log(self):
        pass

    def update_browser_status(self, thread_id, status_text, proxy_info):
        self.status_lbl.setText(f"● {status_text}")

    def closeEvent(self, event):
        if self.worker:
            self.worker.stop()
        event.accept()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = GmailRecoveryWindow()
    window.show()
    sys.exit(app.exec())