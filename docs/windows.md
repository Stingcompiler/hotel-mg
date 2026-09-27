# Sky Towers on Windows

Two ways to run the system on Windows 10/11.

## A. The installer (normal use — no command line)

1. Download **SkyTowers-Setup-<version>.exe** from the Releases page:
   <https://github.com/Stingcompiler/hotel-mg/releases/latest> (no GitHub account needed).
2. Run it. The installer is not signed with a commercial certificate, so Windows may show
   «Windows protected your PC»: click **More info → Run anyway**. Accept the administrator prompt.
3. The installer asks one question: **«هل هذا جهاز الاستقبال؟»** — *نعم* for the reception PC,
   *لا* for the owner PC. It then, without further questions:
   - writes `%ProgramData%\SkyTowers\config.json` (a new hotel id on reception; empty on the owner PC
     until its first import);
   - lets only Administrators and the service account write `%ProgramData%\SkyTowers`;
   - adds a Microsoft Defender exclusion for the program and data folders;
   - installs and starts the Windows service **Sky Towers Server** (`SkyTowersServer`, automatic
     start, restarts on failure) on `http://127.0.0.1:8471`;
   - installs the desktop app, which starts with Windows in the tray.
4. Open **Sky Towers** from the Start menu. Closing the window keeps the app in the tray
   (فتح · نسخة احتياطية الآن · خروج).

### First run — reception PC

The app opens on **«إعداد النظام لأول مرة»**: enter the manager's name, username, password and a 4–6 digit
PIN, and you are signed in. The empty room board then points to الإعدادات, in this order: أنواع الغرف والأسعار →
الغرف → المستخدمون → بيانات الفندق → النسخ الاحتياطي (paste the owner PC's key there, see below). Then open a shift
in «الصندوق» and start checking guests in.

To try the system with demo data instead (a test PC only, before creating the manager), from an administrator
command prompt:

```bat
cd "C:\Program Files\Sky Towers\server"
skytowers-server.exe manage seed_demo --allow-non-debug
```

Demo users: `manager` / `ahmed.ali` / `salma.h`, password `skytowers-dev`, PIN `123456`.

### Owner PC

1. Open Sky Towers on the owner PC: it shows **«إعداد جهاز المالك»** with this PC's key (made on first
   start). Press **نسخ المفتاح** and paste it on the reception PC in الإعدادات › النسخ الاحتياطي › مفتاح المالك العام.
   (The key is also shown later in «النسخ والاستيراد».)
2. On the reception PC press **نسخة احتياطية الآن** and copy the `.age` file from
   `%ProgramData%\SkyTowers\backups` to a USB stick (or link Drive).
3. On the owner PC press **استيراد أول نسخة** and choose the file. Then sign in with the reception PC's
   manager account.

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

## B. From the source (development)

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
  `"role":"owner"` on the reception PC**: the installer's question was answered «لا» (or an older config.json said
  owner). Switch the role without losing data, from an administrator prompt:
  `sc stop SkyTowersServer` → `"C:\Program Files\Sky Towers\server\skytowers-server.exe" init --role reception --force`
  → `sc start SkyTowersServer`. The hotel id is taken from the database that is already there.
- **«الخادم المحلي غير متاح»**: the service is not running. `services.msc` → Sky Towers Server → Start, or
  `sc start SkyTowersServer` as administrator. The reason is in `server.log`.
- **«ساعة الجهاز غير صحيحة»**: the Windows clock went back. Settings → Time & language → Set time
  automatically, then «إعادة الفحص». A manager can accept the clock with their password.
- **Backups fail with «لم يُضبط مفتاح المالك العام»**: paste the owner's public key in الإعدادات › النسخ الاحتياطي.
