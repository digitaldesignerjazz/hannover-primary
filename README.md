# hannover-primary

Dieses Repository macht eine Maschine zum Knoten **hannover-primary** im [Yggdrasil](https://yggdrasil-network.github.io)-Mesh. Gedacht ist es für **Onyx** in Hannover: Windows 11 Pro mit WSL2 Ubuntu und aktiviertem systemd. Dieselbe Installation gilt für Debian und Ubuntu mit systemd.

Der private Schlüssel entsteht auf der Maschine. Er liegt nicht in Git.

## Schnellstart auf Onyx (WSL Ubuntu)

Das Repository ist privat. GitHub nimmt dafür kein Account-Passwort an. In der Ubuntu-Distribution einmalig die GitHub-CLI anmelden, danach klonen:

```bash
sudo apt-get update
sudo apt-get install -y gh
gh auth login
gh repo clone digitaldesignerjazz/hannover-primary
cd hannover-primary
sudo ./scripts/install.sh
sudo ./scripts/status.sh
```

Bei `gh auth login`: GitHub.com, Protokoll HTTPS, im Browser anmelden. Den Einmalcode aus dem Terminal auf [github.com/login/device](https://github.com/login/device) eingeben. Als Passwort für `git` oder `gh` nie das GitHub-Passwort verwenden.

Fehlt das Paket `gh` in den Ubuntu-Quellen, die [Installationsanleitung der GitHub-CLI](https://github.com/cli/cli/blob/trunk/docs/install_linux.md) nutzen und die Befehle ab `gh auth login` wiederholen.

Alternativ per SSH, nachdem der öffentliche Schlüssel unter [GitHub SSH-Keys](https://github.com/settings/keys) liegt:

```bash
git clone git@github.com:digitaldesignerjazz/hannover-primary.git
cd hannover-primary
sudo ./scripts/install.sh
sudo ./scripts/status.sh
```

`install.sh` ist wiederholbar. Ein zweiter Lauf bringt Paket, Schlüssel und Konfiguration auf denselben Stand, ohne die IPv6-Adresse zu wechseln.

`status.sh` endet mit Exit 0, wenn der Knoten läuft und mindestens ein Peer verbunden ist. Exit 1 heißt, der Knoten ist down. Exit 2 heißt, der Prozess antwortet, aber kein Peer ist verbunden.

## Voraussetzungen

- Debian oder Ubuntu, auch unter WSL2, mit systemd als PID 1.
- Root-Rechte über `sudo`.
- Ausgehender Zugriff auf das offizielle APT-Repository und auf die öffentlichen Peers.

Unter WSL muss systemd schon an sein. Prüfen:

```bash
ps -p 1 -o comm=
```

Die Ausgabe ist `systemd`. Falls nicht, in `/etc/wsl.conf`:

```ini
[boot]
systemd=true
```

Danach in PowerShell auf dem Windows-Host `wsl --shutdown` ausführen und Ubuntu neu öffnen.

## Installation

```bash
sudo ./scripts/install.sh
```

Das Skript folgt der [Debian/Ubuntu-Anleitung](https://yggdrasil-network.github.io/installation-linux-deb.html):

1. Es lädt den Repository-Schlüssel von `https://neilalexander.s3.dualstack.eu-west-2.amazonaws.com/deb/key.txt`.
2. Es akzeptiert nur den Fingerabdruck `1C5162E133015D81A811239D1840CDAC6011C5EA` (Schlüssel-ID `1840CDAC6011C5EA`, veröffentlicht am 2025-11-11).
3. Es trägt die signierte APT-Quelle ein, per HTTPS, wie es dieselbe Anleitung erlaubt.
4. Es installiert das Paket `yggdrasil` (nicht `yggdrasil-develop`) und bevorzugt diese Quelle gegenüber einem älteren Distributionspaket.
5. Es schreibt die Knotenkonfiguration und aktiviert den systemd-Dienst `yggdrasil`.

Geprüft gegen Yggdrasil **0.5.14**. Das Paket legt den Dienst so an:

- Konfiguration: `/etc/yggdrasil/yggdrasil.conf`
- Admin-Socket: `unix:///var/run/yggdrasil/yggdrasil.sock`
- Gruppe: `yggdrasil`
- TUN-Schnittstelle über `ExecStartPre=modprobe tun`

Die Website nennt noch `/etc/yggdrasil.conf`. Das Paket 0.5.14 verwendet das Verzeichnis `/etc/yggdrasil/`. Die Skripte folgen dem Paket.

Der installierende Benutzer wird der Gruppe `yggdrasil` hinzugefügt. Die Mitgliedschaft gilt nach einer neuen Anmeldung. Bis dahin `sudo ./scripts/status.sh` verwenden.

## Konfiguration

Öffentliche Einstellungen stehen in [`config/overlay.json`](config/overlay.json). Die Peers stehen in [`config/peers.txt`](config/peers.txt). Beides darf in Git.

| Feld | Wert | Bedeutung |
| --- | --- | --- |
| `NodeInfo.name` | `hannover-primary` | Name, den andere Knoten abfragen können |
| `NodeInfo.location` | `Hannover/DE` | Standort im NodeInfo |
| `IfName` | `ygg0` | Fester Name der TUN-Schnittstelle |
| `IfMTU` | `65535` | Linux-Standard der aktuellen Version |
| `Listen` | leer | Nur ausgehende Peerings, kein offener Clearnet-Port |
| `AdminListen` | `unix:///var/run/yggdrasil/yggdrasil.sock` | Socket für `yggdrasilctl`, passend zum Paket und zur systemd-Unit |
| `AllowedPublicKeys` | leer | Eingehende Peerings sind nicht auf einzelne Schlüssel beschränkt |
| `MulticastInterfaces` | alle Schnittstellen | Link-lokale Erkennung, wie der Linux-Standard |

`AllowedPublicKeys` ist keine Firewall. Wer die Adresse kennt, erreicht Dienste auf dem Knoten, wenn sie auf der Mesh-Adresse lauschen. Siehe unten.

Anwenden nach einer Änderung an Overlay oder Peers:

```bash
sudo ./scripts/configure.sh
```

Ablauf:

1. Fehlt `/etc/yggdrasil/yggdrasil.conf`, erzeugt `yggdrasil -genconf` ein neues Schlüsselpaar auf dieser Maschine.
2. Sonst bleibt `PrivateKey` (oder `PrivateKeyPath`) aus der bestehenden Datei erhalten.
3. Overlay und `peers.txt` überschreiben die öffentlichen Felder. Die Peer-Liste in der Live-Datei kommt immer aus `config/peers.txt`.
4. Die Datei gehört `root:yggdrasil` und ist für die Gruppe lesbar (`0640`).
5. Nur bei einer echten Änderung wird der Dienst neu gestartet. Die vorherige Datei liegt dann unter `/var/backups/`. Diese Kopie enthält den privaten Schlüssel und bleibt auf der Maschine.

Ein Listener für eingehende Peerings ist absichtlich aus. Onyx hängt hinter NAT und WSL2. Für einen öffentlichen Listener in `config/overlay.json` zum Beispiel:

```json
"Listen": ["tls://[::]:4242"]
```

Danach `sudo ./scripts/configure.sh`, den Port am Router weiterleiten und in der Firewall auf der Clearnet-Schnittstelle freigeben. Unter WSL2 reicht das nicht; der Windows-Host muss den Port zusätzlich in die Distribution reichen.

Skripte verweigern das Schreiben einer Konfiguration in den Repository-Baum. Ein Lauf wie `./scripts/configure.sh --conf /pfad/zum/repo/yggdrasil.conf` endet mit einem Fehler.

## Peers

Die Voreinstellung sind drei TLS-Peers in Deutschland, mit veröffentlichtem Schlüssel-Pin, von verschiedenen Betreibern. Die Quelle ist [yggdrasil-network/public-peers](https://github.com/yggdrasil-network/public-peers), Datei `europe/germany.md`, Stand 2026-09-27. Yggdrasil empfiehlt zwei oder drei nahe Peers, nicht eine lange Liste.

```bash
./scripts/peers.sh list
./scripts/peers.sh check
./scripts/peers.sh refresh
./scripts/peers.sh select
./scripts/peers.sh select --write
sudo ./scripts/configure.sh
```

- `refresh` lädt Deutschland und benachbartes EU (NL, AT, CZ, LU, PL, CH, FR) nach `config/peers.candidates.txt`. Diese Datei ist lokal und steht in `.gitignore`.
- `select` bevorzugt TLS, dann Deutschland, dann die Nachbarländer. Einträge, deren Beschreibung im Upstream „residential“ enthält, rutschen nach hinten. Danach zählen ein `?key=`-Pin, ein Hostname und Port 443. Pro Host nur eine URI. Standard sind drei Treffer. Die Datei `config/peers.txt` im Repository ist eine gesichtete Auswahl und nicht jedes Mal das wörtliche Ergebnis von `select`.
- `select --write` ersetzt `config/peers.txt`. Die Datei vorher ansehen und bei Bedarf committen. Sie enthält keine Schlüssel dieses Knotens.

Nicht jeder Eintrag im Upstream ist online. Die [Public-Peers-Seite](https://publicpeers.neilalexander.dev/) zeigt, was gerade erreichbar ist.

## Status

```bash
sudo ./scripts/status.sh
```

Die Ausgabe nennt IPv6-Adresse, geroutetes `/64`-Subnetz, öffentlichen Schlüssel und die verbundenen Peers. Die Daten kommen von `yggdrasilctl getSelf` und `getPeers` am Admin-Socket.

`yggdrasilctl` selbst liefert auch bei einem toten Socket oft Exit 0 und schreibt den Fehler auf stdout. `status.sh` wertet deshalb das JSON aus und setzt den Exit-Code selbst.

| Exit | Bedeutung |
| --- | --- |
| 0 | Knoten läuft, mindestens ein Peer ist verbunden |
| 1 | Knoten ist down oder `yggdrasilctl` fehlt |
| 2 | Knoten läuft, kein Peer verbunden |

Journal, wenn der Dienst nicht startet:

```bash
systemctl status yggdrasil
journalctl -u yggdrasil -e
```

## Firewall

Eingehende Mesh-Verbindungen sind kein Ersatz für eine Firewall auf `ygg0`.

- Ausgehende Peerings brauchen keine Portfreigabe.
- `Listen` ist leer, deshalb ist auf der Clearnet-Schnittstelle nichts für Yggdrasil zu öffnen.
- Auf `ygg0` neue eingehende Verbindungen ablehnen, wenn dort keine Dienste angeboten werden. SSH auf der normalen Schnittstelle nicht mit dieser Regel erfassen.
- Beispiel, nur als Einordnung, wenn bereits eine Firewall existiert: Verkehr mit Eingangsschnittstelle `ygg0` verwerfen, außer den Diensten, die im Mesh erreichbar sein sollen.

Unter Windows gilt das für die native Installation zusätzlich: die Firewall-Abfrage für `yggdrasil.exe` erlauben, sonst kommen keine Peerings zustande. Den Adapter `Yggdrasil` als öffentliches Netz behandeln und SMB, RPC und RDP dort nicht freigeben. Das entspricht der [Windows-Anleitung](https://yggdrasil-network.github.io/installation-windows.html).

## WSL2

- TUN liegt unter `/dev/net/tun`. Die Unit lädt das Modul mit `modprobe tun`. Fehlt das Gerät, bricht der Dienst ab; `journalctl -u yggdrasil` zeigt den Grund.
- Die Schnittstelle heißt `ygg0` und existiert nur im Linux-Netz von WSL. Windows sieht sie nicht als Adapter.
- Programme unter Windows erreichen die Yggdrasil-Adresse damit nicht. Dafür den Windows-Pfad unten verwenden.
- Aus Ubuntu heraus ist der Knoten normal benutzbar.
- `wsl --shutdown` auf dem Host beendet den Knoten, bis die Distribution wieder startet.
- Multicast auf allen Schnittstellen ist der Linux-Standard. In WSL erzeugt das manchmal nur Logzeilen. Dann in `config/overlay.json` für `MulticastInterfaces` `Beacon` und `Listen` auf `false` setzen und `sudo ./scripts/configure.sh` ausführen.
- WSL2-NAT nimmt eingehende Clearnet-Verbindungen nicht von selbst an. Die leere `Listen`-Liste passt dazu.

## Windows (zweiter Weg)

Der Windows-Port ist beim Projekt [best effort](https://yggdrasil-network.github.io/installation-windows.html). Für Onyx ist WSL der primäre Weg. Nativ sieht der Adapter unter Windows so aus:

PowerShell als Administrator, im geklonten Repository:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\windows\Install-YggdrasilNode.ps1 -Action Install
.\windows\Install-YggdrasilNode.ps1 -Action Status
```

Das Skript lädt das aktuelle `yggdrasil-*-x64.msi` aus den [GitHub-Releases](https://github.com/yggdrasil-network/yggdrasil-go/releases), installiert es und schreibt `%ProgramData%\Yggdrasil\yggdrasil.conf`. Der private Schlüssel kommt vom Installer bzw. von `yggdrasil.exe -genconf` auf diesem PC.

Abweichend vom Linux-Overlay setzt Windows:

- `AdminListen` auf `tcp://localhost:9001` (Standard der Windows-Build)
- `IfName` auf `Yggdrasil` (Wintun-Adapter)

NodeInfo und Peers sind dieselben Dateien wie unter Linux. `-Action Configure` schreibt die Konfiguration neu und startet den Dienst, ohne das MSI noch einmal zu installieren.

## Deinstallation

Linux, Paket und APT-Quelle entfernen, Schlüssel behalten:

```bash
sudo ./scripts/uninstall.sh
```

Identität mitlöschen (IPv6-Adresse geht verloren, auch die Kopien unter `/var/backups`):

```bash
sudo ./scripts/uninstall.sh --remove-config
```

Windows, likewise als Administrator:

```powershell
.\windows\Install-YggdrasilNode.ps1 -Action Uninstall
.\windows\Install-YggdrasilNode.ps1 -Action Uninstall -RemoveConfig
```

## Aufbau

| Pfad | Inhalt |
| --- | --- |
| `scripts/install.sh` | APT-Repository, Paket, Konfiguration, Dienst |
| `scripts/configure.sh` | Schlüssel behalten, Overlay und Peers anwenden |
| `scripts/peers.sh` | Peers listen, prüfen, aktualisieren, auswählen |
| `scripts/status.sh` | Adresse, Subnetz, öffentlicher Schlüssel, Peers |
| `scripts/uninstall.sh` | Paket entfernen |
| `scripts/validate-config.sh` | Vorlage gegen das Yggdrasil-Binary 0.5.14 prüfen |
| `scripts/check-no-secrets.sh` | Arbeitsbaum auf privaten Schlüssel prüfen |
| `config/overlay.json` | Öffentliche Knotenwerte |
| `config/peers.txt` | Aktive öffentliche Peers |
| `windows/Install-YggdrasilNode.ps1` | MSI, Konfiguration, Status, Deinstallation |

## CI

GitHub Actions auf `ubuntu-latest` führt ShellCheck, die Python-Tests, `validate-config.sh`, die Geheimnisprüfung und PSScriptAnalyzer aus. Es gibt keine self-hosted Runner.
