"""
Bot licytacji Panelu wycen IB Projekt Printing — uruchamiany co 30 min przez GitHub Actions.

Dla każdego otwartego zapytania:
  1. ZAPROSZENIA   — drukarnie dodane do zapytania, które nie dostały jeszcze maila, dostają zaproszenie z linkiem.
  2. KOMUNIKAT     — na GODZINY_KOMUNIKATU (2 h) przed końcem (albo gdy klikniesz „Wyślij teraz” w panelu)
                     drukarnie, które złożyły ofertę, dostają najniższą cenę do pobicia — BEZ nazwy drukarni.
                     Od tej chwili najniższa cena jest też widoczna w panelu drukarń i aktualizowana co 30 min.
  1b. NOWA OFERTA  — gdy drukarnia złoży lub zmieni ofertę, dostajesz maila (raz na każdą zmianę, zbiorczo co 30 min).
  2b. PRZYPOMNIENIE — na 6 h przed końcem drukarnie, które NIE złożyły jeszcze oferty, dostają przypomnienie.
  3. ZAMKNIĘCIE    — po końcu: status „zakonczone”, ranking ofert i mail do Ciebie: najniższa oferta + link
                     „ustal marżę i wygeneruj PDF dla klienta”.

Wymaga sekretów (GitHub → Settings → Secrets → Actions):
  FIREBASE_SA  — cała zawartość pliku JSON klucza konta serwisowego Firebase
  SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS — skrzynka bz@ibprojekt.eu
  PANEL_URL    — adres panelu, np. https://108bart108.github.io/panel-wycen/
Uruchomienie lokalne do testu: python bot/licytacja.py --sucho   (nic nie wysyła i nie zapisuje)
"""
import argparse
import html
import json
import os
import smtplib
import ssl
import sys
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from email.utils import make_msgid

GODZINY_KOMUNIKATU = float(os.environ.get("GODZINY_KOMUNIKATU", 2))
GODZINY_PRZYPOMNIENIA = float(os.environ.get("GODZINY_PRZYPOMNIENIA", 6))
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "bz@ibprojekt.eu")
PANEL_URL = os.environ.get("PANEL_URL", "https://108bart108.github.io/panel-wycen/").rstrip("/") + "/"
DZIEKUJ_PO_KONCU = os.environ.get("DZIEKUJ_PO_KONCU", "nie").lower() in ("tak", "1", "true")
FIRMA = {"nazwa": "IB Projekt Printing", "osoba": "Bartosz Zając", "telefon": "792 331 442", "email": "bz@ibprojekt.eu"}

e = lambda s: html.escape(str(s if s is not None else ""))


def zl(v):
    return f"{v:,.2f}".replace(",", " ").replace(".", ",") + " zł"


def razem(p):
    return float(p.get("cena") or 0) + float(p.get("transport") or 0)


try:
    from zoneinfo import ZoneInfo
    STREFA = ZoneInfo("Europe/Warsaw")
except Exception:
    STREFA = timezone(timedelta(hours=1))


def fmt(dt):
    return dt.astimezone(STREFA).strftime("%d.%m.%Y %H:%M")


# ------------------------------------------------------------------ dostęp do bazy (Firestore albo atrapa w testach)

class BazaFirestore:
    def __init__(self):
        import firebase_admin
        from firebase_admin import credentials, firestore
        sa = os.environ.get("FIREBASE_SA")
        if not sa:
            sys.exit("Brak sekretu FIREBASE_SA (klucz konta serwisowego).")
        firebase_admin.initialize_app(credentials.Certificate(json.loads(sa)))
        self.db = firestore.client()

    def otwarte(self):
        return [(d.id, d.to_dict()) for d in self.db.collection("zapytania").where("status", "==", "otwarte").stream()]

    def oferty(self, zid):
        return [(d.id, d.to_dict()) for d in self.db.collection("zapytania").document(zid).collection("oferty").stream()]

    def drukarnia(self, email):
        d = self.db.collection("drukarnie").document(email).get()
        return d.to_dict() if d.exists else {}

    def klient(self, zid):
        d = self.db.collection("prywatne").document(zid).get()
        return d.to_dict() if d.exists else {}

    def aktualizuj(self, zid, dane):
        self.db.collection("zapytania").document(zid).update(dane)


# ------------------------------------------------------------------ poczta

def html_maila(tresc):
    return (f"<div style=\"font:16px/1.5 Georgia,'Times New Roman',serif;color:#111;max-width:640px\">"
            f"<div style=\"border-bottom:3px double #111;padding-bottom:6px;margin-bottom:14px;letter-spacing:.12em;font-variant:small-caps\">"
            f"{e(FIRMA['nazwa'])} · Panel wycen</div>{tresc}"
            f"<p style=\"margin-top:24px;font-size:13px;color:#666\">{e(FIRMA['osoba'])} · tel. {e(FIRMA['telefon'])} · {e(FIRMA['email'])}</p></div>")


class Poczta:
    def __init__(self, sucho=False):
        self.sucho = sucho
        self.wyslane = []

    def wyslij(self, do, temat, tresc_html):
        self.wyslane.append((do, temat))
        if self.sucho:
            print(f"  [na sucho] mail do {do}: {temat}")
            return True
        host, haslo = os.environ.get("SMTP_HOST"), os.environ.get("SMTP_PASS")
        user = os.environ.get("SMTP_USER", FIRMA["email"])
        port = int(os.environ.get("SMTP_PORT") or 465)
        if not host or not haslo:
            print(f"  ! brak SMTP_HOST/SMTP_PASS — nie wysłano: {do} | {temat}")
            return False
        m = EmailMessage()
        m["Subject"], m["From"], m["To"] = temat, f"{FIRMA['osoba']} | {FIRMA['nazwa']} <{user}>", do
        m["Reply-To"] = FIRMA["email"]
        m["Message-ID"] = make_msgid(domain=user.split("@")[-1])
        m.set_content("Wiadomość HTML — otwórz w programie pocztowym obsługującym HTML.")
        m.add_alternative(html_maila(tresc_html), subtype="html")
        try:
            kontekst = ssl.create_default_context()
            if port == 465:
                with smtplib.SMTP_SSL(host, port, context=kontekst, timeout=30) as s:
                    s.login(user, haslo); s.send_message(m)
            else:
                with smtplib.SMTP(host, port, timeout=30) as s:
                    s.starttls(context=kontekst); s.login(user, haslo); s.send_message(m)
            print(f"  ✉ {do}: {temat}")
            return True
        except Exception as ex:
            print(f"  ! błąd wysyłki do {do}: {ex}")
            return False


# ------------------------------------------------------------------ logika

def najnizsze(z, oferty):
    wynik = {}
    for n in z.get("naklady", []):
        ceny = [razem(p) for _, o in oferty for p in o.get("pozycje", []) if int(p.get("naklad", 0)) == int(n) and float(p.get("cena") or 0) > 0]
        if ceny:
            wynik[str(n)] = round(min(ceny), 2)
    return wynik


def ranking(z, oferty):
    """{nakład: [(razem, nazwa, pozycja, email), …] posortowane rosnąco}"""
    wynik = {}
    for n in z.get("naklady", []):
        l = [(razem(p), o.get("drukarnia") or em, p, em) for em, o in oferty for p in o.get("pozycje", [])
             if int(p.get("naklad", 0)) == int(n) and float(p.get("cena") or 0) > 0]
        wynik[n] = sorted(l, key=lambda x: (x[0], int(x[2].get("termin") or 999)))
    return wynik


def mail_zaproszenie(z, zid, drukarnia):
    koniec = z["koniec"]
    return (f"Nowe zapytanie ofertowe: {z['tytul']} (do {fmt(koniec)})",
            f"<p>Dzień dobry{', ' + e(drukarnia.get('nazwa')) if drukarnia.get('nazwa') else ''},</p>"
            f"<p>zapraszam do złożenia oferty na: <strong>{e(z['tytul'])}</strong>.<br>"
            f"Nakłady: <strong>{e(' / '.join(str(n) for n in z.get('naklady', [])))} egz.</strong><br>"
            f"Oferty przyjmuję do: <strong>{fmt(koniec)}</strong>.</p>"
            f"<div style=\"white-space:pre-wrap;border:1px solid #ccc;padding:10px 12px;background:#fafafa\">{e(z.get('specyfikacja', ''))}</div>"
            f"<p style=\"margin-top:16px\"><a href=\"{PANEL_URL}#/z/{zid}\" style=\"background:#111;color:#fff;padding:10px 18px;text-decoration:none\">Złóż ofertę w panelu</a></p>"
            f"<p style=\"font-size:14px;color:#555\">Ofertę można zmieniać do końca licytacji i dołączyć do niej plik (PDF). Na {int(GODZINY_KOMUNIKATU)} h przed końcem drukarnie, "
            f"które złożyły ofertę, otrzymają informację o aktualnie najniższej cenie (bez nazw drukarń).</p>")


def najnizsze_naklady(moja, najn):
    """Nakłady, w których ta oferta jest obecnie najniższa."""
    wynik = []
    for n, cena_min in najn.items():
        p = next((p for p in moja.get("pozycje", []) if str(int(p.get("naklad", 0))) == n and float(p.get("cena") or 0) > 0), None)
        if p is not None and razem(p) <= cena_min + 0.001:
            wynik.append((n, razem(p)))
    return wynik


def mail_rabat(z, zid, moja, moje_najnizsze, najn, godz_do_konca):
    """Pytanie o rabat — bez informacji, że oferta jest najniższa."""
    czas = f"około {int(round(godz_do_konca))} h" if godz_do_konca >= 1.5 else "niecałą godzinę"
    wiersze = "".join(f"<li>{e(n)} egz. — {zl(c)} netto z transportem</li>" for n, c in moje_najnizsze)
    pozostale = [(n, c) for n, c in najn.items() if n not in {x for x, _ in moje_najnizsze}
                 and any(str(int(p.get("naklad", 0))) == n and float(p.get("cena") or 0) > 0 for p in moja.get("pozycje", []))]
    dodatek = ""
    if pozostale:
        dodatek = ("<p>Dla pozostałych nakładów obecnie najniższa cena netto z transportem to: "
                   + "; ".join(f"{e(n)} egz. — <strong>{zl(c)}</strong>" for n, c in pozostale) + ".</p>")
    return (f"Pytanie o rabat — {z['tytul']}",
            f"<p>Dzień dobry,</p><p>dziękuję za ofertę na <strong>{e(z['tytul'])}</strong>. "
            f"Do końca licytacji ({fmt(z['koniec'])}) zostało {czas}.</p>"
            f"<p>Państwa oferta:</p><ul>{wiersze}</ul>"
            f"<p><strong>Czy jest możliwy jakiś rabat?</strong> Jeśli tak, wystarczy zmienić cenę w panelu do końca licytacji "
            f"(można też dołączyć plik z ofertą) albo odpowiedzieć na tego maila.</p>{dodatek}"
            f"<p><a href=\"{PANEL_URL}#/z/{zid}\" style=\"background:#111;color:#fff;padding:10px 18px;text-decoration:none\">Zmień ofertę</a></p>"
            f"<p style=\"font-size:14px;color:#555\">Jeśli rabat nie jest możliwy — nic nie trzeba robić, oferta pozostaje ważna.</p>")


def mail_komunikat(z, zid, moja, najn, godz_do_konca):
    wiersze = ""
    for n, cena_min in najn.items():
        moja_p = next((p for p in moja.get("pozycje", []) if str(int(p.get("naklad", 0))) == n and float(p.get("cena") or 0) > 0), None)
        if moja_p is None:
            stan = "<span style=\"color:#777\">nie wyceniono</span>"
        else:
            stan = f"Twoja: {zl(razem(moja_p))}"
        wiersze += f"<tr><td style=\"padding:6px 10px;border-bottom:1px solid #ddd\">{e(n)} egz.</td><td style=\"padding:6px 10px;border-bottom:1px solid #ddd;text-align:right\"><strong>{zl(cena_min)}</strong></td><td style=\"padding:6px 10px;border-bottom:1px solid #ddd\">{stan}</td></tr>"
    czas = f"około {int(round(godz_do_konca))} h" if godz_do_konca >= 1.5 else "niecałą godzinę"
    return (f"Cena do pobicia: {z['tytul']} — zostało {czas}",
            f"<p>Dzień dobry,</p><p>dziękuję za ofertę na <strong>{e(z['tytul'])}</strong>. Do końca licytacji ({fmt(z['koniec'])}) zostało {czas}.</p>"
            f"<p>Obecnie najniższa cena netto (druk + transport):</p>"
            f"<table style=\"border-collapse:collapse\"><tr><th style=\"text-align:left;padding:6px 10px\">Nakład</th><th style=\"text-align:right;padding:6px 10px\">Najniższa</th><th></th></tr>{wiersze}</table>"
            f"<p>Jeśli możecie Państwo zaproponować lepsze warunki, ofertę można zmienić w panelu do końca licytacji:</p>"
            f"<p><a href=\"{PANEL_URL}#/z/{zid}\" style=\"background:#111;color:#fff;padding:10px 18px;text-decoration:none\">Zmień ofertę</a></p>"
            f"<p style=\"font-size:14px;color:#555\">Nie podajemy nazw innych drukarń ani szczegółów ich ofert.</p>")


def mail_nowe_oferty(z, zid, zmienione, najn):
    """zmienione: [(email, oferta, czy_nowa)]"""
    bloki = ""
    for em, o, nowa in zmienione:
        poz = "".join(
            f"<li>{e(p.get('naklad'))} egz. — <strong>{zl(razem(p))}</strong> netto z transportem, {e(p.get('termin'))} dni rob."
            + (f", grzbiet {e(p.get('grzbiet'))} mm" if p.get("grzbiet") else "")
            + (" <span style=\"color:#1d6b35\">(obecnie najniższa)</span>" if najn.get(str(int(p.get('naklad', 0)))) is not None
               and razem(p) <= najn[str(int(p.get('naklad', 0)))] + 0.001 else "") + "</li>"
            for p in o.get("pozycje", []) if float(p.get("cena") or 0) > 0)
        bloki += (f"<p style=\"margin:14px 0 4px\"><strong>{e(o.get('drukarnia') or em)}</strong> — {'nowa oferta' if nowa else 'zmiana oferty'}"
                  + (f" · plik: {e(o['plik'].get('nazwa'))}" if o.get("plik") else "") + f"</p><ul style=\"margin-top:0\">{poz}</ul>"
                  + (f"<p style=\"font-size:14px;color:#555;margin-top:-6px\">Uwagi: {e(o.get('uwagi'))}</p>" if o.get("uwagi") else ""))
    nazwy = ", ".join(o.get("drukarnia") or em for em, o, _ in zmienione)
    return (f"{'Nowa oferta' if len(zmienione) == 1 else 'Nowe oferty'}: {z['tytul']} — {nazwy}",
            f"<p>Zapytanie <strong>{e(z['tytul'])}</strong> (koniec {fmt(z['koniec'])}):</p>{bloki}"
            f"<p style=\"margin-top:16px\"><a href=\"{PANEL_URL}#/z/{zid}\" style=\"background:#111;color:#fff;padding:10px 18px;text-decoration:none\">Zobacz wszystkie oferty</a></p>")


def mail_przypomnienie(z, zid, drukarnia, godz_do_konca):
    czas = f"około {int(round(godz_do_konca))} h" if godz_do_konca >= 1.5 else "niecałą godzinę"
    return (f"Przypomnienie: {z['tytul']} — do końca zostało {czas}",
            f"<p>Dzień dobry{', ' + e(drukarnia.get('nazwa')) if drukarnia.get('nazwa') else ''},</p>"
            f"<p>przypominam o zapytaniu <strong>{e(z['tytul'])}</strong> "
            f"(nakłady: {e(' / '.join(str(n) for n in z.get('naklady', [])))} egz.). "
            f"Nie mam jeszcze Państwa oferty, a licytacja kończy się <strong>{fmt(z['koniec'])}</strong> — zostało {czas}.</p>"
            f"<p><a href=\"{PANEL_URL}#/z/{zid}\" style=\"background:#111;color:#fff;padding:10px 18px;text-decoration:none\">Złóż ofertę w panelu</a></p>"
            f"<p style=\"font-size:14px;color:#555\">Jeśli tym razem nie składają Państwo oferty — proszę zignorować tę wiadomość.</p>")


def mail_podsumowanie(z, zid, oferty, rank, klient):
    sekcje = ""
    for n, l in rank.items():
        if not l:
            sekcje += f"<h3 style=\"margin:18px 0 4px\">{e(n)} egz.</h3><p style=\"color:#777\">brak ofert</p>"
            continue
        wiersze = "".join(
            f"<tr style=\"{'background:#eef6ee' if i == 0 else ''}\"><td style=\"padding:5px 8px\">{i + 1}.</td><td style=\"padding:5px 8px\">{e(nazwa)}</td>"
            f"<td style=\"padding:5px 8px;text-align:right\"><strong>{zl(r)}</strong></td><td style=\"padding:5px 8px;text-align:right\">{e(p.get('termin'))} dni</td>"
            f"<td style=\"padding:5px 8px;text-align:right\">{(str(p.get('grzbiet')) + ' mm') if p.get('grzbiet') else ''}</td></tr>"
            for i, (r, nazwa, p, _) in enumerate(l[:6]))
        sekcje += (f"<h3 style=\"margin:18px 0 4px\">{e(n)} egz.</h3>"
                   f"<table style=\"border-collapse:collapse;width:100%\">{wiersze}</table>")
    najtansze = "; ".join(f"{n} egz. — {zl(l[0][0])} ({e(l[0][1])})" for n, l in rank.items() if l)
    return (f"Licytacja zakończona: {z['tytul']} — ustal marżę",
            f"<p>Licytacja <strong>{e(z['tytul'])}</strong> zakończyła się {fmt(z['koniec'])}.</p>"
            + (f"<p>Klient: <strong>{e(klient.get('klient'))}</strong> {e(klient.get('osoba', ''))}</p>" if klient.get("klient") else "")
            + f"<p>Ofert: <strong>{len(oferty)}</strong> z {len(z.get('zaproszeni', []))} zaproszonych drukarń.<br>"
            f"Najniższe: <strong>{najtansze or 'brak ofert'}</strong></p>{sekcje}"
            + (f"<p style=\"margin-top:20px\"><a href=\"{PANEL_URL}#/oferta/{zid}\" style=\"background:#111;color:#fff;padding:12px 20px;text-decoration:none\">"
               f"Ile doliczyć marży? → przygotuj ofertę PDF</a></p>" if oferty else ""))


def przetworz(baza, poczta, teraz=None, sucho=False):
    teraz = teraz or datetime.now(timezone.utc)
    for zid, z in baza.otwarte():
        koniec = z.get("koniec")
        if not koniec:
            continue
        print(f"• {z.get('tytul')} (koniec {fmt(koniec)})")
        zmiany = {}
        oferty = baza.oferty(zid)

        # 1. zaproszenia
        powiadomieni = list(z.get("powiadomieni", []))
        if teraz < koniec:
            for em in z.get("zaproszeni", []):
                if em in powiadomieni:
                    continue
                temat, tresc = mail_zaproszenie(z, zid, baza.drukarnia(em))
                if poczta.wyslij(em, temat, tresc):
                    powiadomieni.append(em)
            if powiadomieni != list(z.get("powiadomieni", [])):
                zmiany["powiadomieni"] = powiadomieni

        if len(oferty) != z.get("liczbaOfert"):
            zmiany["liczbaOfert"] = len(oferty)

        # 1b. powiadomienie dla Ciebie o nowych / zmienionych ofertach
        znane = dict(z.get("ofertyZgloszone") or {})
        zmienione = []
        for em, o in oferty:
            zm = o.get("zmieniono")
            if not zm:
                continue
            klucz = zm.isoformat() if hasattr(zm, "isoformat") else str(zm)
            if znane.get(em) != klucz:
                zmienione.append((em, o, em not in znane))
                znane[em] = klucz
        if zmienione:
            temat, tresc = mail_nowe_oferty(z, zid, zmienione, najnizsze(z, oferty))
            if poczta.wyslij(ADMIN_EMAIL, temat, tresc):
                zmiany["ofertyZgloszone"] = znane

        # 2. komunikat „cena do pobicia”
        najn = najnizsze(z, oferty)
        do_konca_h = (koniec - teraz).total_seconds() / 3600
        czas_na_komunikat = do_konca_h <= GODZINY_KOMUNIKATU and not z.get("komunikatWyslany")
        if teraz < koniec and (czas_na_komunikat or z.get("wyslijKomunikatTeraz")):
            if najn:
                for em, o in oferty:
                    moje = najnizsze_naklady(o, najn)
                    if moje:     # drukarnia z najniższą ceną → tylko pytanie o rabat (bez informacji, że jest najniższa)
                        temat, tresc = mail_rabat(z, zid, o, moje, najn, do_konca_h)
                    else:        # pozostałe → cena do pobicia (bez nazw drukarń)
                        temat, tresc = mail_komunikat(z, zid, o, najn, do_konca_h)
                    poczta.wyslij(em, temat, tresc)
            zmiany.update({"najnizsze": najn, "wyslijKomunikatTeraz": False, "komunikatData": teraz})
            if czas_na_komunikat:
                zmiany["komunikatWyslany"] = True   # ręczny komunikat nie blokuje automatycznego 2 h przed końcem
        elif (z.get("komunikatWyslany") or z.get("najnizsze")) and najn != z.get("najnizsze") and teraz < koniec:
            zmiany["najnizsze"] = najn          # cicha aktualizacja w panelu drukarń

        # 2b. przypomnienie dla drukarń, które jeszcze nie złożyły oferty
        if teraz < koniec and do_konca_h <= GODZINY_PRZYPOMNIENIA and not z.get("przypomnienieWyslane"):
            zlozyli = {em for em, _ in oferty}
            for em in z.get("zaproszeni", []):
                if em not in zlozyli:
                    temat, tresc = mail_przypomnienie(z, zid, baza.drukarnia(em), do_konca_h)
                    poczta.wyslij(em, temat, tresc)
            zmiany["przypomnienieWyslane"] = True

        # 3. zamknięcie i podsumowanie dla Ciebie
        if teraz >= koniec:
            rank = ranking(z, oferty)
            temat, tresc = mail_podsumowanie(z, zid, oferty, rank, baza.klient(zid))
            poczta.wyslij(ADMIN_EMAIL, temat, tresc)
            zmiany.update({"status": "zakonczone", "zakonczono": teraz, "najnizsze": najn, "podsumowanieWyslane": True})
            if DZIEKUJ_PO_KONCU:
                for em, _ in oferty:
                    poczta.wyslij(em, f"Licytacja zakończona: {z['tytul']}",
                                  f"<p>Dzień dobry,</p><p>licytacja <strong>{e(z['tytul'])}</strong> została zakończona. Dziękuję za ofertę — o wyniku poinformuję mailowo.</p>")

        if zmiany:
            print(f"  zmiany: {', '.join(zmiany)}")
            if not sucho:
                baza.aktualizuj(zid, zmiany)


def main():
    ap = argparse.ArgumentParser(description="Bot licytacji Panelu wycen")
    ap.add_argument("--sucho", action="store_true", help="nic nie wysyłaj i nie zapisuj")
    args = ap.parse_args()
    baza = BazaFirestore()
    przetworz(baza, Poczta(sucho=args.sucho), sucho=args.sucho)


if __name__ == "__main__":
    main()
