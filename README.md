# UBA Luftqualitätsindex (LQI)

HACS-fähige Custom Integration für die Luftqualitätsdaten des Umweltbundesamts.

## Funktionen

- Einrichtung per Config Flow
- Auswahl nahegelegener Luftmessstationen über den Home-Assistant-Standort oder manuelle Koordinaten
- Hauptsensor pro Station für den **UBA Luftqualitätsindex (LQI)**
- zusätzliche Diagnose-Sensoren, standardmäßig deaktiviert:
  - numerischer LQI
  - Messbeginn / Messende
  - Entfernung
  - Datenvollständigkeit
  - Komponentensensoren für die von der API gelieferten Schadstoffe
- erweiterte Attribute am Hauptsensor mit Stationsdetails und den aktuellen Komponentenwerten

## Installation über HACS

### Variante 1: Benutzerdefiniertes Repository

1. **HACS** öffnen
2. oben rechts auf die **drei Punkte** klicken
3. **Benutzerdefinierte Repositories** wählen
4. diese URL eintragen:
   `https://github.com/Q14siX/uba_lqi/`
5. als Kategorie **Integration** auswählen
6. Repository hinzufügen
7. nach **UBA Luftqualitätsindex (LQI)** suchen und installieren
8. Home Assistant neu starten

### Variante 2: Direkt über den HACS-Store

Wenn das Repository später offiziell im HACS-Standardkatalog gelistet ist, reicht:

1. **HACS → Integrationen** öffnen
2. nach **UBA Luftqualitätsindex (LQI)** suchen
3. Integration installieren
4. Home Assistant neu starten

> Hinweis: Die direkte Suche im normalen HACS-Store funktioniert erst dann, wenn das Repository offiziell im HACS-Katalog aufgenommen wurde. Ohne diese Aufnahme funktioniert die Installation weiterhin über **Benutzerdefinierte Repositories**.

## Manuelle Installation

1. den Ordner `custom_components/uba_lqi` in deine Home-Assistant-Installation kopieren
2. Home Assistant neu starten
3. unter **Einstellungen → Geräte & Dienste → Integration hinzufügen** nach **UBA Luftqualitätsindex (LQI)** suchen

## Einrichtung

1. Integration hinzufügen
2. Standortquelle wählen:
   - **Home-Assistant-Standort verwenden** oder
   - **manuelle Koordinaten** eingeben
3. Suchradius festlegen
4. gewünschte Stationen auswählen
5. Einrichtung abschließen

## Datenquelle

- UBA Air Data API / Luftqualität
- API-Doku: `https://luftqualitaet.api.bund.dev`
- Metadaten über `/meta/json`
- aktuelle Luftqualitätsdaten über `/airquality/json`