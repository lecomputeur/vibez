# Lokaal V4-versiebeheer

Deze map is voor het beheer van de privébroncode. De openbare ingang voor helpers staat in `CONTRIBUTING.md` in de openbare VibeZ-repository.

## Eén actuele releasebeschrijving

`release.json` is de vaste bron voor het **bronversienummer**, de vereiste platformen/pakketnamen, wijzigingen en bijbehorende issues. Het onderscheid blijft expliciet:

- `version`: de versie van deze broncode;
- `installed_version`: wat lokaal is geïnstalleerd;
- `published_version`: wat testers daadwerkelijk kunnen downloaden;
- `stable_version`: de afzonderlijke stabiele 3.0.9;
- `source_revision`: `HEAD`; een snapshot legt de werkelijk gebruikte Git-commit vast.

Een lokaal geteste Alpha is nog geen openbare uitgave. `stage` is beschrijvende administratie, geen bewijs dat publicatiecontroles zijn geslaagd. De controles in `gates` moeten afzonderlijk met echte build- en testrapporten worden bewezen.

## De huidige versie controleren

Python 3.11 of nieuwer is nodig voor dit beheergereedschap.

```sh
python3 management/manage.py status
python3 management/manage.py check
python3 management/test_manage.py
```

`check` vergelijkt negen versievelden in acht bronbestanden met `release.json`, controleert de afzonderlijke V4-appidentiteit en leest alleen de goedgekeurde bronbestanden uit `source-files.json`.

## Een volgende Alpha voorbereiden

Bijvoorbeeld wanneer de bronversie Alpha 15 is:

```sh
mkdir -p ../vibez-private-release-preparation
python3 management/manage.py plan --next-version 4.0.0-alpha.16 \
  --output ../vibez-private-release-preparation/alpha16-plan
```

Dit schrijft voorgestelde versieaanpassingen en een `plan.json` **buiten deze bronmap**. De broncode zelf verandert niet. Alleen precies het volgende Alpha-nummer wordt geaccepteerd. Het geïnstalleerde en openbare versienummer worden niet vooruitgezet.

Beoordeel daarna de bestanden in `alpha16-plan/files`, neem de bedoelde wijzigingen over in de privébron, vul `changes` en `related_issues` aan en commit de wijzigingen. `check` moet opnieuw slagen voordat een nieuwe snapshot wordt gemaakt. Gebruik bestaande uitvoermappen niet opnieuw; iedere proef blijft herkenbaar.

Dit is geen automatische publicatieknop. Bouwen, platformtests, ondertekening, notarization, uploaden en het bijwerken van de openbare downloadteksten blijven de bestaande stappen totdat ze als één gecontroleerde workflow zijn aangesloten.

## Exacte bron voor een build vastleggen

Maak eerst een lokale Git-commit. Vervolgens:

```sh
python3 management/manage.py snapshot \
  --output ../vibez-private-release-preparation/alpha16-source-1
```

De uitvoer bevat:

- `snapshot.json`: de exacte commit, bestandslijst en hashes, pakketnamen en vereiste controles;
- `private-source.tar.gz`: uitsluitend de goedgekeurde bronbestanden uit die commit;
- `RELEASE-NOTES.md`: concepttekst uit dezelfde releasebeschrijving, met de benodigde pakketten en issueverwijzingen. De tekst is duidelijk als niet-gepubliceerd gemarkeerd en beweert niet dat alle platformtests al zijn geslaagd.

Dezelfde bron levert dezelfde archivehash op. Een snapshot wordt geweigerd bij niet-gecommitteerde wijzigingen, niet-gevolgde bronbestanden, afwijkende versies, symlinks, onveilige paden of herkenbaar privésleutelmateriaal. Ondertekeningssleutels, gebruikersprofielen, `artifacts`, buildmappen en afhankelijkheden horen niet in de bronlijst. Openbare verificatiesleutels die al deel zijn van de goedgekeurde bron blijven wel beschikbaar.

**Het bronarchief is privé. Zet het niet onbeveiligd in de openbare repository of release.** Een lokaal Git-archief is versiegeschiedenis, geen externe back-up. Er wordt geen externe repository aangemaakt en geen toegang verleend door dit gereedschap.

## Nieuwe bronbestanden toevoegen

De `.gitignore` laat alleen expliciet goedgekeurde bestanden toe. Voeg een nieuw bronbestand na beoordeling toe aan `management/source-files.json` én de allowlist in `.gitignore`. Gebruik niet algemeen `git add -f .`. Controleer de precieze lijst voordat je commit:

```sh
git diff --cached --name-only
git status --short
```

Pakketbijlagen bij een gepubliceerde versie worden niet vervangen. Een reparatie krijgt een volgend versienummer. De veranderlijke technische updatekanalen blijven apart van de genummerde downloads. V4 bouwt geen MSIX; 3.0.9 en zijn updatekanaal blijven afzonderlijk.

## Aanvullende beheerscripts

`maintainer-files.json` noemt de extra Linux-pakketbouwers en controlehulpmiddelen die lokaal door Git worden bijgehouden. Deze horen niet automatisch bij de goedgekeurde native bronbundel van 439 bestanden. Hun exacte bytes blijven terugvindbaar via dezelfde Git-commit. Voeg bij nieuwe beheerscripts het precieze bestand aan deze lijst en de `.gitignore`-allowlist toe.

### Release in vaste stappen

`tools/release-alpha.py` voert een Alpha-release uit in gecontroleerde stappen (`bump`, `freeze`, `ci-start`, `linux`, `ci-collect`, `feeds`, `draft`, `publish`, `status`) en stopt met een duidelijke melding als een vorige stap ontbreekt; `--dry-run` toont alleen de commando's. Geheimen gaan uitsluitend als bestandspad mee.

### MCP-versies bewaken

`tools/check-mcp-versions.py` vergelijkt de protocolversies die de engine spreekt met de gepubliceerde specificatie en legt het resultaat vast in `mcp-versions.json`. De bump-stap van de releasetool en het rapport van de live zelftest voeren hem automatisch uit.
