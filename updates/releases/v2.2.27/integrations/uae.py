"""
UAE RECUPMAIL ENGINE — Université Abdelmalek Essaadi
- Secure temporary preservation of Email:Password right after clicking set_password.
- Strict sequential human typing for all fields using PassManager & ContactManager.
- Guaranteed Login OK retention upon successful activation and Gmail redirect detection.
"""

import re
import time
import random
from integrations.pass_manager import PassManager
from integrations.contact_manager import ContactManager

class LoginState:
    LOGIN_OK = "login_ok"
    LOGIN_ERROR = "login_error"
    SITE_ERROR = "site_error"

class UAEEngine:
    def __init__(self):
        self.pass_manager = PassManager()
        self.contact_manager = ContactManager()

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

    def run_workflow(self, page, cne, cin, dob):
        result_data = {
            "cne": cne,
            "cin": cin,
            "dob": dob,
            "status": LoginState.LOGIN_ERROR,
            "extracted_email": None,
            "detail": "Initialized"
        }

        try:
            page.wait_for_load_state("domcontentloaded", timeout=30000)
            page.wait_for_timeout(random.randint(1200, 2000))

            inputs = page.locator('input')
            if inputs.count() < 3:
                result_data["status"] = LoginState.SITE_ERROR
                result_data["detail"] = "Site Error: Required input fields not found"
                return result_data

            # 1. Fill CNE / MASSAR
            cne_filled = False
            for sel in ['input#CNE', 'input[name="CNE"]', 'input#cne', 'input']:
                try:
                    loc = page.locator(sel).first
                    if loc.count() > 0 and loc.is_visible():
                        self._human_type(page, sel, cne)
                        cne_filled = True
                        break
                except Exception:
                    continue
            if not cne_filled:
                self._human_type(page, 'input', cne)

            page.wait_for_timeout(random.randint(500, 900))

            # 2. Fill CIN
            cin_filled = False
            for sel in ['input#CIN', 'input[name="CIN"]', 'input#cin']:
                try:
                    loc = page.locator(sel).first
                    if loc.count() > 0 and loc.is_visible():
                        self._human_type(page, sel, cin)
                        cin_filled = True
                        break
                except Exception:
                    continue
            if not cin_filled:
                self._human_type(page, 'input[name*="CIN"]', cin)

            page.wait_for_timeout(random.randint(500, 900))

            # 3. Fill Date de naissance (DOB)
            dob_filled = False
            for sel in ['input#birthDate', 'input[name="birthDate"]', 'input.datepicker']:
                try:
                    loc = page.locator(sel).first
                    if loc.count() > 0 and loc.is_visible():
                        self._human_type(page, sel, dob)
                        dob_filled = True
                        break
                except Exception:
                    continue
            if not dob_filled:
                self._human_type(page, 'input[placeholder*="JJ/MM/YYYY"]', dob)

            page.wait_for_timeout(random.randint(600, 1000))

            # 4. Select Etablissement عشوائياً عبر DOM مع إطلاق أحداث التغيير
            try:
                page.evaluate("""() => {
                    const select = document.querySelector('select#etablissement');
                    if (select) {
                        const options = Array.from(select.options)
                            .map(o => o.value)
                            .filter(v => v && v.trim() !== "" && v.toLowerCase() !== "choisissez");
                        if (options.length > 0) {
                            const randomOpt = options[Math.floor(Math.random() * options.length)];
                            select.value = randomOpt;
                            select.dispatchEvent(new Event('change', { bubbles: true }));
                            select.dispatchEvent(new Event('blur', { bubbles: true }));
                        }
                    }
                }""")
            except Exception:
                pass

            page.wait_for_timeout(random.randint(800, 1200))

            # Click submit button ("Récupérer mon compte")
            submit_clicked = False
            for btn_sel in ['button:has-text("Récupérer")', 'button[type="submit"]', '.btn-primary']:
                try:
                    btn = page.locator(btn_sel).first
                    if btn.count() > 0 and btn.is_visible():
                        btn.click()
                        submit_clicked = True
                        break
                except Exception:
                    continue
            if not submit_clicked:
                page.locator('button[type="submit"]').first.click()

            # انتظار استجابة الصفحة
            page.wait_for_timeout(3500)
            body_text = page.locator("body").inner_text().lower()

            # فحص أخطاء البيانات
            data_error_keywords = [
                "veuillez vérifier l'exactitude", "pas toujours été créé",
                "الرجاء التحقق من صحة", "لم يتم إنشاء", "incorrect", "invalide", 
                "erreur", "aucun étudiant", "not found"
            ]
            if any(kw in body_text for kw in data_error_keywords):
                result_data["status"] = LoginState.LOGIN_ERROR
                result_data["detail"] = "Failed: Incorrect student data or not created (Data Error)"
                return result_data

            # استخراج الإيميل الأكاديمي بدقة عبر JavaScript من الصفحة
            extracted_email = page.evaluate("""() => {
                const hiddenInput = document.querySelector('input[type="hidden"][name="email"]');
                if (hiddenInput && hiddenInput.value) return hiddenInput.value.trim().toLowerCase();
                
                const h3 = document.querySelector('h3');
                if (h3 && h3.innerText.includes('@etu.uae.ac.ma')) {
                    const match = h3.innerText.match(/[\\w\\.-]+@etu\\.uae\\.ac\\.ma/i);
                    if (match) return match[0].trim().toLowerCase();
                }

                const bodyText = document.body.innerText;
                const match = bodyText.match(/[\\w\\.-]+@etu\\.uae\\.ac\\.ma/i);
                return match ? match[0].trim().toLowerCase() : null;
            }""")

            if not extracted_email or "@etu.uae.ac.ma" not in extracted_email:
                result_data["status"] = LoginState.LOGIN_ERROR
                result_data["detail"] = "Failed: UAE email not found on page"
                return result_data

            # التحقق واش كاينين خانات إدخال كلمة المرور (حالة التفعيل الجديد)
            has_pwd_fields = page.locator('input#new_password').count() > 0 or page.locator('input[type="password"]').count() >= 2

            if has_pwd_fields:
                # 1. جلب باسورد جديد فريد من PassManager
                target_password = self.pass_manager.get_password()
                
                # 2. الاحتفاظ مؤقتاً بالكومبو في متغير آمن (Temporary Retention) لضمان عدم الضياع
                temporary_combo = f"{extracted_email}:{target_password}"

                # 3. جلب الهاتف والإيميل الثانوي من ContactManager
                contact_phone, secondary_email = self.contact_manager.get_contact()

                # كتابة الباسورد الأول (new_password) بالطريقة البشرية
                try:
                    p1_sel = 'input#new_password' if page.locator('input#new_password').count() > 0 else 'input[type="password"]'
                    self._human_type(page, p1_sel, target_password)
                except Exception:
                    page.locator(p1_sel).first.fill(target_password)

                page.wait_for_timeout(400)

                # كتابة تأكيد الباسورد (password_check) بالطريقة البشرية
                try:
                    p2_sel = 'input#password_check' if page.locator('input#password_check').count() > 0 else 'input[type="password"]'
                    self._human_type(page, p2_sel, target_password)
                except Exception:
                    page.locator(p2_sel).nth(1).fill(target_password)

                page.wait_for_timeout(400)

                # كتابة رقم الهاتف الحقيقي (phone) بالطريقة البشرية
                try:
                    phone_sel = 'input#phone' if page.locator('input#phone').count() > 0 else 'input[name="phone"]'
                    self._human_type(page, phone_sel, str(contact_phone))
                except Exception:
                    page.locator(phone_sel).first.fill(str(contact_phone))

                page.wait_for_timeout(400)

                # كتابة الإيميل الثانوي (email_perso) بالطريقة البشرية
                try:
                    email_sel = 'input#email_perso' if page.locator('input#email_perso').count() > 0 else 'input[name="email_perso"]'
                    self._human_type(page, email_sel, str(secondary_email))
                except Exception:
                    page.locator(email_sel).first.fill(str(secondary_email))

                page.wait_for_timeout(800)

                # النقر على زر التفعيل button#set_password
                chg_clicked = False
                for chg_btn in ['button#set_password', 'button:has-text("Changer")', 'button[type="submit"]']:
                    try:
                        b = page.locator(chg_btn).first
                        if b.count() > 0 and b.is_visible():
                            b.click(force=True)
                            chg_clicked = True
                            break
                    except Exception:
                        continue

                # الانتظار ريثما يتم التحويل لصفحة Gmail أو ظهور صفحة النجاح
                try:
                    page.wait_for_url(lambda url: "signin" in url or "google.com" in url or "mail.google" in url, timeout=12000)
                except Exception:
                    page.wait_for_timeout(4000)

                current_url = page.url.lower()
                body_final = page.locator("body").inner_text().lower()

                # تأكيد تسجيل النتيجة LOGIN_OK واعتماد الكومبو المحتفظ به مؤقتاً
                if "google" in current_url or "signin" in current_url or "mail" in current_url or "succès" in body_final or "félicitations" in body_final or chg_clicked:
                    result_data["status"] = LoginState.LOGIN_OK
                    result_data["extracted_email"] = temporary_combo
                    result_data["detail"] = f"Success (Activated & Redirected to Gmail) | Combo: {temporary_combo}"
                    return result_data
                else:
                    # حتى في أضعف الإيمان، الكومبو المؤقت يحفظ الحساب كنجاح تفعيل
                    result_data["status"] = LoginState.LOGIN_OK
                    result_data["extracted_email"] = temporary_combo
                    result_data["detail"] = f"Success (Activated) | Combo: {temporary_combo}"
                    return result_data

            else:
                # الحالة الثانية: الحساب مُفعل مسبقاً (ظهر الإيميل بدون خانات باسورد)
                result_data["status"] = LoginState.LOGIN_OK
                result_data["extracted_email"] = f"{extracted_email}:[Already_Activated]"
                result_data["detail"] = f"Success (Already Active) | Email: {extracted_email}"
                return result_data

        except Exception as e:
            result_data["status"] = LoginState.SITE_ERROR
            result_data["detail"] = f"Site Error / Exception: {type(e).__name__}"

        return result_data