# Sky Towers on Windows

Two ways to run the system on Windows 10/11.

## A. The installer (normal use — no command line)

1. Download the newest installer: <https://github.com/Stingcompiler/hotel-mg/releases/latest/download/SkyTowers-Setup.exe>
   (no GitHub account needed; every release is also listed at <https://github.com/Stingcompiler/hotel-mg/releases>).
2. Run it. The installer is not signed with a commercial certificate, so Windows may show
   «Windows protected your PC»: click **More info → Run anyway**. Accept the administrator prompt.
3. The installer asks **no question** (1.1). It:
   - writes `%ProgramData%\SkyTowers\config.json` once (a new hotel id; an upgrade keeps the existing file);
   - lets only Administrators and the service account write `%ProgramData%\SkyTowers`;
   - adds a Microsoft Defender exclusion for the program and data folders;
   - installs and starts the Windows service **Sky Towers Server** (`SkyTowersServer`, automatic
     start, restarts on failure) on `http://127.0.0.1:8471`;
   - installs the desktop app, which starts with Windows in the tray.
4. Open **Sky Towers** from the Start menu. Closing the window keeps the app in the tray
   (فتح · نسخة احتياطية الآن · خروج).

### First run

The app opens on the **login page**. On first start the service created the owner account **`admin`**, password
and PIN **`123456`**; the login page shows them (with «تعبئة الحقول») until the password is changed, and after
signing in a reminder offers «تغيير الآن» (الإعدادات › المستخدمون). One login page serves every role — the account
decides what opens: the owner gets «لوحة المالك» and every screen, a manager the room board and settings, reception
staff the daily screens. Then, in الإعدادات: أنواع الغرف والأسعار → الغرف → المستخدمون (each with a login, a password
and a PIN) → بيانات الفندق. Open a shift in «الصندوق» and start checking guests in.

The demo hotel is for development checkouts only (section B): `seed_demo` refuses the installed program's folder.
### Owner PC, or replacing a reception PC (1.1)

Backups need no key setup: the reception PC makes the **hotel key** on its first start and encrypts every backup to
it. Each backup also carries that key locked with the password of every active owner and manager (never the
default `123456`); so on another PC the owner opens it with **his own username and password**, and that PC keeps the
key for later imports.

1. On the reception PC: change the default owner password (الإعدادات › المستخدمون), then **نسخة احتياطية الآن**;
   copy the `.age` file from `%ProgramData%\SkyTowers\backups` to a USB stick (or link Drive).
2. On the new PC: install, sign in with `admin` / `123456`. «لوحة المالك» and the empty room board show **«جهاز
   جديد»** → **فتح من نسخة احتياطية**: the file, the login as on the reception PC, and one choice:
   - **للاطلاع فقط** — the owner's PC (read-only); later backups import from «النسخ والاستيراد» with no login;
   - **للعمل عليه** — this PC replaces a broken reception PC with the backup's data.
3. The service restarts within seconds (`pending-import/` is applied before the database opens); the empty install
   is kept in `backups\pre-import-<stamp>\`. Sign in with the hotel's accounts.

PCs installed as owner PCs before 1.1 keep working: a key pasted in الإعدادات › النسخ الاحتياطي («مفتاح جهاز مالك
قديم») still receives every backup.
### Updates

Run a newer installer over the old one. It stops the service, takes a pre-upgrade backup, installs, and the
service migrates the database on start. Uninstalling never deletes `%ProgramData%\SkyTowers`.

### Where things are

| What | Where |
| --- | --- |
| Database, attachments | `%ProgramData%\SkyTowers\data\` |
| Backups | `%ProgramData%\SkyTowers\backups\` |
| Service log | `%ProgramData%\SkyTowers\logs\server.log` («فتح سجل الأخطاء» on the start page) |
| Owner key (owner PC only) | `%ProgramData%\SkyTowers\keys\` — keep a copy offline; backups cannot be opened without it |

### Restoring a reception PC from a backup (disaster recovery)

If the reception PC is lost, install Sky Towers on the new PC as *reception*, then, from an administrator
command prompt with the service stopped:

```bat
sc stop SkyTowersServer
cd "C:\Program Files\Sky Towers\server"
skytowers-server.exe manage restore_full D:\skytowers-5a7e0000-000117-20260926-2053.age --identity D:\owner.key
sc start SkyTowersServer
```

`owner.key` is the owner PC's `%ProgramData%\SkyTowers\keys\owner.key`, copied for the restore only — delete the
copy afterwards. The previous database and attachments are kept in `%ProgramData%\SkyTowers\backups\pre-restore-<stamp>\`.
The command refuses a file from another hotel, a tampered file, the wrong key, or a database that is still in use.

### Starting over with an empty program

A new install is empty and opens on the login page with the default owner account (dmin / 123456).
Uninstalling keeps `%ProgramData%\SkyTowers`, so a PC that was used for a trial (the demo hotel, test bookings)
keeps that data through a reinstall. To empty it, from an administrator command prompt:

```bat
sc stop SkyTowersServer
cd "C:\Program Files\Sky Towers\server"
skytowers-server.exe manage reset_data --yes
sc start SkyTowersServer
```

Nothing is deleted: the database, attachments and backup files move to
`%ProgramData%\SkyTowers\backups\pre-reset-<stamp>\`. The role, the secret and the owner's key stay (the two PCs
stay paired); an owner PC forgets the hotel and adopts it again with its first import.

## B. From the source (development)

A source checkout keeps its data in `server\.devdata` (or `SKYTOWERS_HOME`), never in the installed program's
`%ProgramData%\SkyTowers`, and `seed_demo` refuses that folder — the demo hotel cannot leak into an installed app.

Needs Python 3.12 and Node.js 20+.

```bat
git clone https://github.com/Stingcompiler/hotel-mg.git
cd hotel-mg\server
py -3.12 -m venv .venv
.venv\Scripts\activate
pip install -r requirements-dev.txt
python manage.py migrate
python manage.py seed_demo
cd ..
python build\build_spa.py
cd server
python -m service.run_waitress
```

Open `http://127.0.0.1:8471/` in Edge or Chrome. For frontend work run `npm run dev` in `web\` instead of
`build_spa.py` and open `http://localhost:5173/` (it proxies `/api` to the Django server, which must be running).

## Troubleshooting

- **«واجهة البرنامج غير مبنية بعد»** in the app window: the server that answered on 127.0.0.1:8471 has no
  built SPA next to it. The page prints which executable answered and the folder it looked in. Two causes:
  a server started from a source checkout (`python -m service.run_waitress` without `build_spa.py`) holding the
  port — close it (`netstat -ano | findstr :8471`, then end that PID) and restart the service; or a broken install —
  `C:\Program Files\Sky Towers\server\_internal\static_spa\index.html` must exist; run the installer again.
  `server.log` says the same at start-up («SPA missing» / «cannot listen»). The installer and the service
  itself end a foreign process holding the port (`skytowers-server.exe free-port`); our own executable is never ended.
- **«تعذّر الاتصال بالخادم المحلي» right after the page opened, service RUNNING, and `system/status` says
  `"role":"owner"` on the reception PC**: the question of an installer before 1.1 was answered «لا» (or an older config.json said
  owner). Switch the role without losing data, from an administrator prompt:
  `sc stop SkyTowersServer` → `"C:\Program Files\Sky Towers\server\skytowers-server.exe" init --role reception --force`
  → `sc start SkyTowersServer`. The hotel id is taken from the database that is already there.
- **«الخادم المحلي غير متاح»**: the service is not running. `services.msc` → Sky Towers Server → Start, or
  `sc start SkyTowersServer` as administrator. The reason is in `server.log`.
- **«ساعة الجهاز غير صحيحة»**: the Windows clock went back. Settings → Time & language → Set time
  automatically, then «إعادة الفحص». A manager can accept the clock with their password.
- **Backups fail with «لم يُضبط مفتاح المالك العام»**: paste the owner's public key in الإعدادات › النسخ الاحتياطي.
