# Switch User

Signs in to the MMFDB workspace as another account, and remembers the choice. It is the login
dialog of ChiSurf as a tool window.

## The form

| Control | What it does |
|---|---|
| **Server** / **MMFDB URL** | Host of the MMFDB server; a remote MMFDB is given as an http or https URL. **Recent servers** lists the ones used before. |
| **Port** | Command port, 1 to 65535 (the publish port is the next one). Absent for a remote MMFDB. |
| **User** / **Select user** | The account to sign in as: type any name or pick the configured and desktop accounts. An empty field uses the account last picked. |
| **Password** | Shown as stars, sent to the server, never stored. |
| **Save selected user** | Makes the account the default one for the next start. |
| **Log in automatically when allowed** | Keeps a session token in the operating system's credential store for password-free sign-in. |
| **Login** / **Cancel** | Authenticate, or close without changing anything. |

## What Login does

1. Asks the MMFDB to authenticate. A refusal appears as a **Login Failed** message and nothing is changed.
2. On success the account, the server and port and the two options are saved in your settings
   (`mmfdb` section of `settings_chisurf.yaml`), the server is moved to the front of the history
   (five are kept), and the session token is kept for this run.
3. If the settings or the credential store cannot be written, a message says so ("Settings Not Saved",
   "Autologin Not Saved"); the sign-in itself still counts and the window closes after you press **OK**.
