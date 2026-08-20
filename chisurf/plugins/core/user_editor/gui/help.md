# Users

The accounts registered in the MMFDB — who they are, what they may do, and which
one ChiSurf uses for its own database connections.

## You need to be an administrator

Listing users is an administrator operation. If you are not signed in as one,
the table stays empty and the status line says so; it is not an error you caused
and nothing is wrong with your installation.

## The table

One row per account.

| Column | Means |
|---|---|
| **User** | Display name, falling back to the username. |
| **Username** | How the account is addressed. Renaming changes it. |
| **Role** | Free text with a list of common choices. |
| **Admin** | May list, edit and delete users. |
| **Autologin** | May sign in without a password. |
| **★ Active** | The account ChiSurf uses for its own MMFDB connections. |

## Editing

Select a row and edit the fields on the right. Changes stay local until
**Save** — **Revert** discards them, and closing with unsaved edits asks first.
A reason the account cannot be saved yet (a missing display name, a malformed
e-mail, a username already taken) appears above the fields as you type, rather
than after a round trip to the server.

**Renaming** an account also moves its stored session token, so you stay signed
in. `user_default` and `guest` are built in and cannot be renamed or deleted.

## Passwords

**Password…** opens the strength-checked entry dialog. The new password is
*staged*: it is applied when you press **Save**, and the status line tells you
one is waiting. Administrators are held to a stronger password than other
accounts.

Passwords are never stored on this machine — they are sent to the server, which
stores only a hash.

## Deleting

The server refuses to delete an account that owns committed data, so that data
never becomes orphaned. An administrator is then offered a forced deletion,
which removes the account and leaves its data in place. The account ChiSurf is
currently using cannot be deleted at all — switch to another one first.

## Further reading

- [Settings reference](docs/reference/settings.md)
