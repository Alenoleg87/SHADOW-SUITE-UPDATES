"""
PASSWORDS MODULE — Thread-Safe Custom Personal & Human-like Names Integration
Generates millions of unique, natural passwords using custom family and personal names:
- Combines custom personal names/words (A-Z, a-z) across multiple natural patterns
- Adds dynamic numbers (10-99999) and secure symbols (@, #, !, ?, _, $, %, &, *)
- Strict policy validation (Min 8 chars, uppercase, lowercase, digit, symbol)
- Zero-repetition guarantee for millions of requests.
- Thread-safe via threading.RLock for multi-browser execution.
"""

import re
import random
import threading
from pathlib import Path

class PassManager:
    def __init__(self, custom_file=None):
        self.lock = threading.RLock()
        self.generated_passwords = set()

        self.personal_words = [
            "Abdennasser", "Abdelmoula", "Allal", "Amghar", "Amimar",
            "Abbou", "Abdennour", "Amine", "Abdelaali", "Abderaouf",
            "Amjad", "Abdeladim", "Abderrafie", "Ammar", "Abdelali",
            "Abderazak", "Amrane", "Abdelaziz", "Abdessabour", "Anise",
            "Abdelbadie", "Abdessadek", "Anouar", "Abdelbaki", "Abdessafi",
            "Antar", "Abdelbasset", "Abdessalam", "Aouab", "Abdelfattah",
            "Abdessamad", "Aouiss", "Abdelghafour", "Abdessamie", "Arbi",
            "Abdelghani", "Abdessatar", "Archane", "Abdelhadi", "Abdou",
            "Aref", "Abdelhafid", "Abdourabih", "Arif", "Abdelhak",
            "Abdrabbou", "Arij", "Abdelhakim", "Abed", "Arkam",
            "Abdelhalim", "Abid", "Arsalane", "Abdelhamid", "Aboubaki",
            "Assad", "Abdelhaq", "Aboubakr", "Assil", "Abdelilah",
            "Aboud", "Assou", "Abdeljabbar", "Achour", "Atef",
            "Abdeljalil", "Achraf", "Atf", "Abdeljaouad", "Adam",
            "Atiq", "Abdelkabir", "Addi", "Atouf", "Abdelkader",
            "Adel", "Ayache", "Abdelkamel", "Adham", "Ayachi",
            "Abdelkarim", "Adib", "Ayad", "Abdelkhalek", "Adnane",
            "Ayman", "Abdelkouddous", "Afif", "Ayoub", "Abdellah",
            "Ahmed", "Azhar", "Abdellatif", "Aissa", "Azmi",
            "Abdelmalek", "Akram", "Azzam", "Abdelmoghit", "Alaeeddine",
            "Azzeddine", "Abdelmonaim", "Alami", "Azzelarab", "Abdelmouaiz",
            "Ali", "Azzouz", "Abdelmoughit", "Aliene", "Baaka",
            "Alif", "Baba", "Alilou", "Bachar", "Allali",
            "Bachir", "Allouch", "Badr", "Amara", "Badreddine",
            "Amer", "Badri", "Ameur", "Bahae", "Ameziane",
            "Bahi", "Bahssin", "Bakkar", "Bakr", "Bamou",
            "Barouk", "Bassam", "Bassou", "Belkas", "Belkassem",
            "Benaissa", "Benasser", "Bendaoud", "Benissa", "Bennacer",
            "Benyaakoub", "Bikr", "Bilal", "Bouamama", "Bouamar",
            "Bouamrou", "Bouazza", "Bouchaib", "Bouchta", "Bouekri",
            "Boughout", "Boujemaa", "Bourhim", "Bourhime", "Bousedra",
            "Bouselham", "Bouziane", "Brahim", "Chaabane", "Chaddad",
            "Chadi", "Chadli", "Chafi", "Chafik", "Chafiq",
            "Chahed", "Chaib", "Chakib", "Chakir", "Chaouki",
            "Charaf", "Charafeddine", "Chedad", "Cherqi", "Chihab",
            "Choaib", "Chouaib", "Choukri", "Dahane", "Dahbi",
            "Dahmane", "Daidai", "Daoud", "Daoui", "Darid",
            "Darous", "Diab", "Diae", "Diaeddine", "Didi",
            "Douraid", "Driss", "Ebdelkahar", "Eddaoui", "Elaid",
            "Elarbi", "Elbachir", "Elbouchtaoui", "Elchafii", "Elfatmi",
            "Elghali", "Elghaouti", "Elghazouani", "Elhabib", "Elhachemi",
            "Elhassan", "Elhouari", "Elkebir", "Elkhadiooui", "Elkhadir",
            "Elkhamar", "Elmahdi", "Elmahhi", "Elmahjoub", "Elmakki",
            "Elmouloudi", "Elouafi", "Eloualid", "Elyazid", "Essghir",
            "Ezzine", "Fadel", "Fadil", "Fadoul", "Fael",
            "Fahd", "Fahim", "Fail", "Faissal", "Faiz",
            "Fakher", "Fakhreddine", "Faouaz", "Faouzi", "Faras",
            "Fares", "Farid", "Farji", "Farouk", "Fathallah",
            "Fathelkhir", "Fathi", "Fathoune", "Fettah", "Fikri",
            "Fouad", "Frahat", "Ghafour", "Ghali", "Ghanem",
            "Ghanim", "Ghassan", "Ghazal", "Ghazi", "Ghazil",
            "Habib", "Hossam", "Habiballah", "Habika", "Houari",
            "Hachem", "Houcine", "Haddaoui", "Houd", "Haddou",
            "Houdaifa", "Hadi", "Houmad", "Hadou", "Houmam",
            "Hafid", "Houmane", "Hafs", "Hoummane", "Haidar",
            "Hourma", "Haitam", "Hajjaj", "Houssine", "Houssni",
            "Hakim", "Hsina", "Halim", "Hssina", "Hamda",
            "Hamdane", "Hamdi", "Hamid", "Hamadan", "Hamiddouche",
            "Hammadi", "Hammam", "Hammed", "Hamoud", "Hamouda",
            "Hamza", "Hanafi", "Hani", "Hanifa", "Harouch",
            "Haroun", "Harrou", "Hassan", "Hassoun", "Hatim",
            "Hazaz", "Hazem", "Hazim", "Hicham", "Hilmi",
            "Hmad", "Hmida", "Hmidane", "Hmidouch", "Hosni",
            "Iad", "Ibrahim", "Ider", "Idriss", "Ihssane",
            "Ikbal", "Ilias", "Ilyas", "Imad", "Imadeddine",
            "Imran", "Irchad", "Isaad", "Ishaq", "Ismail",
            "Issa", "Issam", "Iyad", "Jaafar", "Jabbour",
            "Jaber", "Jabir", "Jabour", "Jabrane", "Jad",
            "Jadelmoula", "Jadouane", "Jalal", "Jalaleddine", "Jalil",
            "Jaloul", "Jamae", "Jamal", "Jamaleddine", "Jamea",
            "Jamil", "Jaouad", "Jaouhar", "Jarrah", "Jbilou",
            "Jilali", "Jnina", "Joundol", "Kabbour", "Kabir",
            "Kacem", "Kadem", "Kadhem", "Kadour", "Kais",
            "Kamal", "Kandouz", "Karam", "Karim", "Kassem",
            "Kassou", "Kebour", "Khachane", "Khaireddine", "Khairi",
            "Khales", "Khalid", "Khalifa", "Khalil", "Khatib",
            "Kotb", "Kouider", "Labib", "Lahbib", "Lahcen",
            "Laite", "Laith", "Lakbir", "Lakhdar", "Larbi",
            "Latif", "Layachi", "Lokmane", "Lotfi", "Louay",
            "Loukman", "Lounis", "Loutfi", "Maamar", "Maamoun",
            "Maatallah", "Machich", "Madani", "Mahdi", "Maher",
            "Mahfoud", "Mahjoub", "Mahjoubi", "Mahmoud", "Mahraz",
            "Mahrez", "Majd", "Majid", "Makhlouf", "Malek",
            "Mali", "Mallal", "Mamdouh", "Mamoun", "Mansour",
            "Marouane", "Marzak", "Marzouk", "Masaoud", "Masrour",
            "Massoud", "Mazigh", "Mbarek", "Meziane", "Mhamed",
            "Mimoun", "Mnaouar", "Moad", "Moaouia", "Moataz",
            "Mofid", "Moflih", "Nabih", "Nabil", "Nader",
            "Nadim", "Nadir", "Nafie", "Nafis", "Nail",
            "Naim", "Najd", "Naji", "Najib", "Najmeddin",
            "Namir", "Naoufal", "Nasr", "Nasreddine", "Nassef",
            "Nassif", "Nassih", "Nassim", "Nazih", "Nezar",
            "Nizar", "Nouaman", "Noah", "Nour", "Noureddine",
            "Nouri", "Okacha", "Okba", "Omar", "Osmane",
            "Otaiba", "Othmane", "Ouadie", "Ouael", "Ouafi",
            "Ouafik", "Ouahab", "Ouahib", "Ouahid", "Ouajdi",
            "Ouajih", "Oualid", "Oualim", "Ouassim", "Ounssi",
            "Oussama", "Outaiba", "Rabbah", "Rabeh", "Rabie",
            "Rachad", "Rached", "Rachid", "Radi", "Raed",
            "Rafie", "Rafik", "Rahali", "Rahim", "Rahmoun",
            "Raif", "Ramdane", "Ramzi", "Raouad", "Raouf",
            "Rayan", "Razane", "Raza", "Razouk", "Reda",
            "Read", "Redouane", "Refki", "Reyad", "Rhassane",
            "Riad", "Rochd", "Rostom", "Rouchdi", "Saad",
            "Saadeddine", "Saadoune", "Sabih", "Sabri", "Sadik",
            "Saeb", "Safi", "Safouane", "Saghir", "Sahel",
            "Said", "Saif", "Saifeddine", "Salaheddine", "Saleh",
            "Salem", "Salmane", "Samad", "Sami", "Samih",
            "Samir", "Saudi", "Sarhane", "Sarie", "Seddik",
            "Sedki", "Seouar", "Sobhi", "Sofiane", "Sohaib",
            "Soltan", "Soubhi", "Souhaib", "Souhail", "Soulaimane",
            "Sourour", "Stela", "Tachfine", "Taha", "Taher",
            "Taib", "Taibi", "Tajeddine", "Takieddine", "Talal",
            "Talha", "Tami", "Tamime", "Taoufik", "Tareq",
            "Tarik", "Thami", "Tijani", "Tofail", "Touhami",
            "Yaakoob", "Yachou", "Yahia", "Yahya", "Yakd",
            "Yanis", "Yasser", "Yassine", "Yassir", "Yazid",
            "Younes", "Yousri", "Youssef", "Zahid", "Zahir",
            "Zaid", "Zakaria", "Zaki", "Zekri", "Zeriab",
            "Zeroual", "Zeryab", "Zidane", "Zine", "Zineddine",
            "Ziyad", "Zoubir", "Zouhir", "Aafrae", "Abida",
            "Abla", "Abouch", "Achouak", "Achoura", "Adba",
            "Adiba", "Adila", "Adrae", "Afaf", "Afifa",
            "Afnane", "Aicha", "Aida", "Ainaya", "Aissaouia",
            "Aizza", "Akida", "Alia", "Aliana", "Alou",
            "Amal", "Amane", "Amina", "Amria", "Anbar",
            "Anika", "Anissa", "Ansam", "Anssi", "Aouatif",
            "Aouich", "Aouicha", "Arbia", "Arifa", "Arije",
            "Arjouane", "Arwa", "Asmae", "Assala", "Assia",
            "Assila", "Atiba", "Atifa", "Atika", "Atouch",
            "Awicha", "Aya", "Ayacha", "Ayada", "Azhar",
            "Aziza", "Azouzia", "Azza", "Bachira", "Bada",
            "Badda", "Badia", "Badressououd", "Badra", "Badria",
            "Bahia", "Bahija", "Bahria", "Bahrya", "Bakhta",
            "Bamou", "Bardis", "Baroudia", "Basima", "Basma",
            "Batoul", "Baya", "Bouchra", "Bouchtaouia", "Boutaina",
            "Bouthaina", "Chaden", "Chadia", "Chadlia", "Chafia",
            "Chafika", "Chahbae", "Chahrazad", "Chaimae", "Chams",
            "Chamseddouha", "Charifa", "Charkia", "Chefae", "Chehabe",
            "Chihab", "Chmicha", "Chokria", "Chomeysa", "Chouhaiba",
            "Choukria", "Choumaissa", "Chourouk", "Dahbia", "Dalila",
            "Daouia", "Darifa", "Darous", "Dikra", "Dina",
            "Doha", "Dounia", "Drissia", "Elaidya", "Elamria",
            "Elazzouzia", "Elbahia", "Eldaouia", "Elissaouia", "Elkasmia",
            "Elzahia", "Ettahra", "Ettam", "Ezzahiriya", "Fada",
            "Fadila", "Fadma", "Fadoua", "Fahima", "Fairouz",
            "Faiza", "Fakhita", "Fakira", "Fanida", "Farah",
            "Farha", "Farida", "Fariha", "Fathia", "Fatima",
            "Fatimazahra", "Fatine", "Fatna", "Fatou", "Fatouch",
            "Fattouch", "Fattoum", "Fikria", "Firdaous", "Fouzia",
            "Ghada", "Ghalia", "Ghania", "Ghanima", "Ghannou",
            "Gharae", "Ghazil", "Ghenou", "Ghita", "Ghizlane",
            "Hababa", "Habbouba", "Habiba", "Hachmia", "Hachouma",
            "Hada", "Hadbae", "Hadda", "Hadhoum", "Hadia",
            "Hadifa", "Hadil", "Hafida", "Hafsa", "Haifae",
            "Hajiba", "Hajjou", "Hala", "Halima", "Hallouma",
            "Hamdaouia", "Hamida", "Hammout", "Hamou", "Hanae",
            "Hanane", "Hania", "Hanifa", "Hannou", "Hasiba",
            "Hasnae", "Hassana", "Hassna", "Haya", "Heba",
            "Hiba", "Hind", "Hinda", "Houbaba", "Houda",
            "Houria", "Ibtihaj", "Ibtihal", "Ibtissame", "Ichraf",
            "Ichrak", "Ichraq", "Ifak", "Ihssan", "Ijja",
            "Ijlal", "Ikbal", "Ikram", "Ihame", "Imane",
            "Inas", "Inaya", "Ines", "Intissar", "Irchad",
            "Irfane", "Isaad", "Issoua", "Kabira", "Kanma",
            "Kaeda", "Kaima", "Kamaria", "Kamila", "Kamilia",
            "Kamria", "Kaouakib", "Kaoukeb", "Kaoutar", "Karima",
            "Kattou", "Kelthoum", "Kenza", "Ketou", "Khaddouj",
            "Khadija", "Khadijatou", "Khadouja", "Khadra", "Khalfia",
            "Khalida", "Khalila", "Khansae", "Khaoula", "Khdrae",
            "Kheira", "Khlifia", "Khnata", "Labiba", "Lamiae",
            "Lamyae", "Lara", "Latifa", "Layla", "Leila",
            "Lina", "Lobaba", "Loubana", "Loubna", "Louiza",
            "Loujain", "Maazouza", "Madiha", "Maessa", "Maha",
            "Mahasine", "Mahdia", "Mahjouba", "Maisae", "Maisane",
            "Maissa", "Majda", "Marzouka", "Majida", "Malak",
            "Maliha", "Mamat", "Manal", "Mansoura", "Maounia",
            "Maria", "Mariem", "Marima", "Marjana", "Marjane",
            "Maroua", "Masen", "Masouda", "Mayada", "Mazouara",
            "Mbarka", "Mbirika", "Menna", "Messouda", "Mezouara",
            "Milad", "Milouda", "Mimouna", "Momtaza", "Morjana",
            "Mouada", "Moufida", "Mouina", "Moumna", "Mouna",
            "Mounia", "Mounira", "Nabaouia", "Nabiha", "Nabila",
            "Nachita", "Nachoua", "Nachwa", "Nadia", "Nadifa",
            "Nadira", "Nadoua", "Nafissa", "Naghma", "Nahed",
            "Nahid", "Nahida", "Nahila", "Nahla", "Naima",
            "Najat", "Najda", "Najia", "Najiba", "Najlae",
            "Najma", "Najoua", "Namira", "Naoual", "Naouar",
            "Naouara", "Narjis", "Nasiba", "Nasima", "Nasira",
            "Nasma", "Nasria", "Nassiba", "Nazha", "Naziha",
            "Neama", "Nehad", "Nehal", "Nihad", "Nihal",
            "Nisreen", "Nofayla", "Nora", "Nouma", "Nour",
            "Odria", "Olay", "Olfa", "Omria", "Othmana",
            "Ouadia", "Ouafae", "Ouahiba", "Ouahida", "Oualada",
            "Oualida", "Ouarda", "Ouardia", "Ouasila", "Ouasima",
            "Ouidane", "Ouijdane", "Oumelaid", "Oumelez", "Oumessaad",
            "Oumhani", "Oumama", "Oumayya", "Oumelghit", "Oumnia",
            "Ourida", "Rabab", "Rabha", "Rabia", "Rachida",
            "Rachika", "Radia", "Radoua", "Raeja", "Rafiaa",
            "Rafika", "Rahila", "Rahima", "Rahma", "Rahmouna",
            "Raida", "Raihana", "Raihane", "Rajae", "Rajia",
            "Randa", "Rania", "Raoua", "Raouane", "Rayda",
            "Rayhana", "Razika", "Rehab", "Rehame", "Rim",
            "Rkia", "Rochdia", "Rouaya", "Rouhia", "Roukaya",
            "Saadia", "Sabhia", "Sabiha", "Sabira", "Sabra",
            "Sabrina", "Sadika", "Safae", "Safia", "Safira",
            "Safoua", "Sahila", "Saila", "Sakina", "Saliha",
            "Salima", "Salma", "Saloua", "Salsabil", "Samae",
            "Samar", "Samara", "Samia", "Samiha", "Samira",
            "Samrae", "Sanae", "Sausane", "Sara", "Sarah",
            "Seddika", "Siham", "Siouar", "Smahane", "Sofia",
            "Sonia", "Soraya", "Souad", "Souhaila", "Souhir",
            "Soukaina", "Soumia", "Tahera", "Tahra", "Taimae",
            "Tama", "Tamimount", "Tamou", "Tamra", "Taoufika",
            "Tasnim", "Thouriya", "Tilila", "Tisba", "Tlaitmas",
            "Touda", "Touiba", "Wadia", "Wahida", "Wiam",
            "Widad", "Wissal", "Zahia", "Zahida", "Zahira",
            "Zahoua", "Zahra", "Zahria", "Zaima", "Zaina",
            "Zaineb", "Zakia", "Zanba", "Zannouba", "Zanou",
            "Zanouba", "Zaytounia", "Zhirou", "Zinba", "Zineb",
            "Zohra", "Zoubida", "Zouina", "Zoulika"
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
        with self.lock:
            while True:
                word1 = random.choice(self.personal_words)
                word2 = random.choice(self.personal_words)
                symbol = random.choice(self.symbols)
                number = random.randint(10, 99999)

                pattern = random.choice([
                    "word_sym_num",
                    "word_num_sym",
                    "sym_word_num",
                    "two_words_sym_num",
                ])

                if pattern == "word_sym_num":
                    password = f"{word1}{symbol}{number}"
                elif pattern == "word_num_sym":
                    password = f"{word1}{number}{symbol}"
                elif pattern == "sym_word_num":
                    password = f"{symbol}{word1}{number}"
                else:
                    password = f"{word1}{symbol}{word2.lower()}{number}"

                if len(password) < 8:
                    password = f"{password}{number}!"

                if self.validate_password(password) and password not in self.generated_passwords:
                    self.generated_passwords.add(password)
                    return password

    def load_passwords_from_file(self, file_path):
        with self.lock:
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
        with self.lock:
            if self.custom_pool and len(self.generated_passwords) < len(self.custom_pool):
                remaining = [p for p in self.custom_pool if p not in self.generated_passwords]
                if remaining:
                    pwd = random.choice(remaining)
                    self.generated_passwords.add(pwd)
                    return pwd

            return self.generate_unique_personal_password()

    def reset(self):
        with self.lock:
            self.generated_passwords.clear()