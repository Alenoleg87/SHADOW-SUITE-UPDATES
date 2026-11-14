"""
PASSWORDS MODULE — Custom Personal & Human-like Names Integration
Generates millions of unique, natural passwords using custom family and personal names (Mama, Baba, Koko, etc.):
- Combines custom personal names/words (A-Z, a-z)
- Adds dynamic numbers (0-9) and secure symbols (! @ # ? etc.)
- Strict policy validation (Min 8 chars, uppercase, lowercase, digit, symbol)
- Zero-repetition guarantee for millions of requests.
"""

import re
import random
from pathlib import Path

class PassManager:
    def __init__(self, custom_file=None):
        self.generated_passwords = set()
        
        self.personal_words = [
            "Mama", "Baba", "Koko", "Laila", "Mehdi", 
            "Amine", "Youssef", "Fatima", "Amina", "Hamza", 
            "Kawtar", "Salma", "Rachid", "Houda", "Karim", 
            "Zineb", "Bibi", "Momo", "Dogo", "Sisi"
        ]
        
        self.symbols = ["@", "#", "!", "?", "_", "$", "%", "&", "*"]
        
        self.custom_pool = []
        if custom_file:
            self.load_passwords_from_file(custom_file)

    def validate_password(self, password: str) -> bool:
        if len(password) < 8:
            return False
        if not re.search(r'[A-Z]', password):
            return False
        if not re.search(r'[a-z]', password):
            return False
        if not re.search(r'\d', password):
            return False
        if not re.search(r'[!@#?\-_$.%&*]', password):
            return False
        return True

    def generate_unique_personal_password(self) -> str:
        while True:
            word = random.choice(self.personal_words)
            symbol = random.choice(self.symbols)
            number = random.randint(10, 99999)
            
            password = f"{word}{symbol}{number}"
            
            if len(password) < 8:
                password = f"{word}{symbol}{number}!"
                
            if self.validate_password(password) and password not in self.generated_passwords:
                self.generated_passwords.add(password)
                return password

    def load_passwords_from_file(self, file_path):
        try:
            path = Path(file_path)
            if path.is_file():
                lines = path.read_text(encoding='utf-8-sig').splitlines()
                valid_passes = [line.strip() for line in lines if line.strip() and self.validate_password(line.strip())]
                if valid_passes:
                    self.custom_pool = valid_passes
        except Exception as e:
            print(f"[PassManager Error] Could not load file: {e}")

    def get_password(self) -> str:
        if self.custom_pool and len(self.generated_passwords) < len(self.custom_pool):
            remaining = [p for p in self.custom_pool if p not in self.generated_passwords]
            if remaining:
                pwd = random.choice(remaining)
                self.generated_passwords.add(pwd)
                return pwd
                
        return self.generate_unique_personal_password()

    def reset(self):
        self.generated_passwords.clear()