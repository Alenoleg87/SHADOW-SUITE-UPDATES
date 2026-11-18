"""
Contact Manager — Reads mobile phone and secondary email from Contact.txt
"""

from pathlib import Path

class ContactManager:
    def __init__(self):
        self.contact_file = Path(__file__).resolve().parent / "Contact.txt"

    def get_contact(self):
        try:
            if self.contact_file.is_file():
                content = self.contact_file.read_text(encoding="utf-8-sig").strip()
                lines = [line.strip() for line in content.splitlines() if line.strip() and not line.startswith("#")]
                if lines:
                    parts = lines[0].split(":", 1)
                    if len(parts) == 2:
                        phone = parts[0].strip()
                        email = parts[1].strip()
                        return phone, email
        except Exception:
            pass
        
        # Fallback احتياطي برقم يبدأ بـ 0
        return "0600000000", "default_secondary@gmail.com"