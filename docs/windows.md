# Sky Towers on Windows

Two ways to run the system on Windows 10/11.

## A. The installer (normal use)

1. Download **skytowers-installer** from the latest successful *Windows release* run on GitHub
   (Actions → Windows release → Artifacts), unzip it, and run `Sky Towers_1.0.0_x64-setup.exe` as administrator.
2. The installer asks one question: **«هل هذا جهاز الاستقبال؟»** — *نعم* for the reception PC,
   *لا* for the owner PC. It then:
   - writes `%ProgramData%\SkyTowers\config.json` (a new hotel id on reception; empty on the owner PC
     until its first import);
   - lets only Administrators and the service account write `%ProgramData%\SkyTowers`;
   - adds a Microsoft Defender exclusion for the program and data folders;
   - installs and starts the Windows service **Sky Towers Server** (`SkyTowersServer`, automatic
     start, restarts on failure) on `http://127.0.0.1:8471`;
   - installs the desktop app, which starts with Windows in the tray.
3. Open **Sky Towers** from the Start menu. The window shows the app served by the local service. Closing
   the window keeps the app in the tray (فتح · نسخة احتياطية الآن · خروج).

### First run — reception PC

The database starts empty. Create the first manager from an administrator command prompt:

```bat
cd "C:\Program Files\Sky Towers\server"
skytowers-server.exe manage createsuperuser
```

It asks for a username and password and creates a manager named «المدير». On the login page choose
**الدخول بكلمة المرور**, then give yourself a PIN in الإعدادات › المستخدمون and fill the rest of **الإعدادات**: بيانات الفندق, أنواع الغرف والأسعار, الغرف, المستخدمون (each user
gets a 4–6 digit PIN), and **النسخ الاحتياطي** (paste the owner PC's public key, see below).

To try the system with demo data instead (a test PC only):

```bat
skytowers-server.exe manage seed_demo --allow-non-debug
```

Demo users: `manager` / `ahmed.ali` / `salma.h`, password `skytowers-dev`, PIN `123456`.

### Owner PC

1. On the owner PC, create the owner's backup key once (administrator prompt):
   ```bat
   cd "C:\Program Files\Sky Towers\server"
   skytowers-server.exe manage generate_owner_key
   ```
   It prints a public key (`age1…`). Paste it on the reception PC in الإعدادات › النسخ الاحتياطي › مفتاح المالك العام.
2. On the reception PC press **نسخة احتياطية الآن**, copy the `.age` file from
   `%ProgramData%\SkyTowers\backups` to a USB stick (or use Drive).
3. On the owner PC open Sky Towers: with no data yet the login page offers **استيراد أول نسخة**. After the
   import, sign in with the reception PC's manager account.

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

- **«الخادم المحلي غير متاح»**: the service is not running. `services.msc` → Sky Towers Server → Start, or
  `sc start SkyTowersServer` as administrator. The reason is in `server.log`.
- **«ساعة الجهاز غير صحيحة»**: the Windows clock went back. Settings → Time & language → Set time
  automatically, then «إعادة الفحص». A manager can accept the clock with their password.
- **Backups fail with «لم يُضبط مفتاح المالك العام»**: paste the owner's public key in الإعدادات › النسخ الاحتياطي.
