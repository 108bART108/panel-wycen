# Panel wycen IB Projekt Printing — licytacja ofert drukarń

**Jak to działa**

1. Tworzysz w panelu zapytanie: tytuł roboczy (bez nazwy klienta), specyfikację, nakłady, link do plików, **koniec licytacji (timer)**, zaznaczasz drukarnie. Dane klienta wpisujesz w osobnej sekcji — drukarnie ich nie widzą.
2. **Bot** (GitHub Actions, co 30 min) wysyła zaproszenia mailem. Drukarnie logują się i składają oferty (cena, transport, termin, grzbiet, wykrojnik). Do końca mogą je zmieniać.
3. **12 h przed końcem** bot wysyła drukarniom, które złożyły ofertę, **najniższą cenę do pobicia** (netto z transportem, **bez nazwy drukarni**), a każda dowiaduje się, czy jej oferta jest najniższa. Ta cena jest też widoczna w ich panelu. Możesz to zrobić wcześniej przyciskiem „Wyślij teraz najniższą cenę”.
4. **6 h przed końcem** drukarnie, które **jeszcze nie złożyły oferty**, dostają przypomnienie z linkiem do panelu.
5. **Po końcu** bot zamyka licytację i wysyła Ci mail: ranking ofert + przycisk **„Ile doliczyć marży? → przygotuj ofertę PDF”**.
6. W panelu: najniższa oferta jest wybrana dla każdego nakładu (możesz zmienić), wpisujesz **marżę** (% albo zł), VAT, zapas terminu → podgląd z Twoim zyskiem → **„Generuj ofertę PDF”** (numer OF/rok/miesiąc/nr, bez nazw drukarń). Opcjonalnie otwiera się gotowy mail do klienta.

Pliki: `index.html` (panel), `firestore.rules` (bezpieczeństwo), `bot/licytacja.py` + `.github/workflows/licytacja.yml` (bot).

---

## Wdrożenie krok po kroku (ok. 30–40 min)

### Krok 1. Projekt Firebase
1. https://console.firebase.google.com → **Dodaj projekt** → nazwa np. `panel-wycen-ibprojekt` (Analytics niepotrzebne).
2. **Build → Authentication → Rozpocznij → E-mail/hasło → Włącz → Zapisz.**
3. Authentication → **Settings → Authorized domains → Add domain:** `108bart108.github.io`.
4. (Opcjonalnie) Authentication → **Templates** → język szablonów: polski.
5. **Build → Firestore Database → Utwórz bazę** → lokalizacja `eur3 (europe-west)` → tryb produkcyjny.
6. Firestore → **Reguły** → wklej całą zawartość `firestore.rules` → **Opublikuj**.
7. ⚙ **Ustawienia projektu → Ogólne → Twoje aplikacje → ikona `</>`** → nazwa „panel” → skopiuj obiekt `firebaseConfig`.

### Krok 2. Uzupełnij `index.html`
Na górze pliku, w `KONFIG.firebase`, wklej wartości z `firebaseConfig` (apiKey, authDomain, projectId, …).
Jeśli administrator ma mieć inny adres niż `bz@ibprojekt.eu` — zmień go w `KONFIG.admini` **i** w `firestore.rules`.

### Krok 3. Repozytorium na GitHubie
1. Na koncie **108bART108** → New repository → nazwa **`panel-wycen`** → **Public** (GitHub Pages i darmowy bot wymagają publicznego repo; dane są w Firebase, chronione regułami — w repo nie ma żadnych danych klientów ani haseł).
2. Wgraj wszystkie pliki z tego folderu (razem z ukrytym `.github/workflows/licytacja.yml`).
3. **Settings → Pages → Branch: main / root → Save.** Po minucie panel działa pod `https://108bart108.github.io/panel-wycen/`.

### Krok 4. Klucz dla bota (konto serwisowe)
1. Firebase → ⚙ Ustawienia projektu → **Konta usługi → Wygeneruj nowy klucz prywatny** → pobierze się plik JSON. **Nie wgrywaj go do repo!**
2. GitHub → repo `panel-wycen` → **Settings → Secrets and variables → Actions**:
   - **Secrets** → New repository secret:
     - `FIREBASE_SA` — wklej **całą zawartość** pliku JSON,
     - `SMTP_HOST` — serwer poczty z panelu hostingu (np. Hostido), `SMTP_PORT` — `465`,
     - `SMTP_USER` — `bz@ibprojekt.eu`, `SMTP_PASS` — hasło do skrzynki.
   - **Variables** → New repository variable: `PANEL_URL` = `https://108bart108.github.io/panel-wycen/`
3. Zakładka **Actions** → włącz workflows → „Bot licytacji” → **Run workflow** (test — w logu powinno być bez błędów).

### Krok 5. Twoje konto administratora
1. Wejdź na panel → wpisz `bz@ibprojekt.eu` i hasło (min. 8 znaków) → **„Pierwsze logowanie — utwórz hasło”**.
2. Kliknij link w mailu od Firebase → odśwież panel → jesteś w panelu administratora.

### Krok 6. Drukarnie
1. Zakładka **Drukarnie** → dodaj każdą: nazwa, e-mail (to będzie jej login), telefon, specjalizacje (np. `książki, offset`).
2. Wyślij drukarni link do panelu i krótką informację: *„Przy pierwszym wejściu kliknij »Pierwsze logowanie — utwórz hasło« na adresie, który Pan/Pani podał(a), i potwierdź go linkiem z maila.”*
3. Drukarnia widzi tylko zapytania, do których ją zaprosisz, i tylko swoją ofertę.

### Krok 7. Pierwsza licytacja — test
Dodaj siebie jako drukarnię na drugim adresie (np. prywatnym), utwórz zapytanie z końcem za 13 h, złóż ofertę z drugiego konta i obserwuj maile od bota.

---

## Na czas testów (skrzynka bz@ibprojekt.eu jeszcze nieaktywna)
- Administratorem jest też **bartosz.zaj@gmail.com** (wpisany w `firestore.rules` i `KONFIG.admini`). Po uruchomieniu firmowej skrzynki usuń go z obu miejsc.
- Bot wysyła maile przez **Gmail**: `SMTP_HOST` = `smtp.gmail.com`, `SMTP_PORT` = `587`, `SMTP_USER` = `bartosz.zaj@gmail.com`, `SMTP_PASS` = **hasło aplikacji** Google (konto Google → Bezpieczeństwo → weryfikacja dwuetapowa musi być włączona → „Hasła do aplikacji” → utwórz → 16 znaków). Zwykłe hasło do Gmaila nie zadziała.
- Zmienna (Variables) `ADMIN_EMAIL` = `bartosz.zaj@gmail.com` — tam przychodzą podsumowania licytacji.
- Gmail pozwala wysłać kilkaset maili dziennie — na testy i pierwsze licytacje w zupełności wystarczy.
- Po przejściu na firmową skrzynkę zmień te 4 sekrety + `ADMIN_EMAIL`, nic więcej.

## Dobrze wiedzieć
- **Bot działa co 30 min** — zaproszenia, komunikat i podsumowanie mogą przyjść z opóźnieniem do pół godziny. Drukarnie widzą zapytanie w panelu od razu.
- Zablokowanie składania ofert po czasie pilnują **reguły Firestore** (dokładnie co do sekundy), nie bot.
- **Przedłużenie** (+24 h) lub zmiana końca w edycji powoduje, że komunikat „cena do pobicia” (12 h) i przypomnienie dla spóźnionych (6 h) zostaną wysłane ponownie względem nowego końca.
- Porównanie ofert to **cena netto druku + transport**. W komunikacie drukarnie widzą tylko kwotę — bez nazwy drukarni i terminu.
- **GitHub wyłącza zaplanowane akcje po 60 dniach bez zmian w repozytorium** — dostaniesz maila; wystarczy w Actions kliknąć „Enable workflow” albo zrobić dowolny commit.
- **Wygląd oferty PDF** nawiązuje do strony www: kroje EB Garamond i Cormorant (folder `fonty/`, licencja OFL — pliki licencji dołączone), podwójne linie, romby, rozdziały I–III, ramki, karta „Twój opiekun zlecenia”, czarna stopka z rokiem w zapisie rzymskim. **Logo i rycinę prasy** wgraj do `grafika/` jako `logo.png` i `prasa.png` (szczegóły w `grafika/WSTAW-TU-GRAFIKI.txt`) — bez nich w nagłówku jest pieczęć z monogramem IB.
- Dane w ofercie, warunki, domyślna marża i VAT — w `KONFIG` na górze `index.html`.
- Warto dopisać w regulaminie współpracy z drukarniami, że na końcu licytacji informujesz anonimowo o najniższej cenie.
