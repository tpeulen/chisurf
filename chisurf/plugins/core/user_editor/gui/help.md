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

Type in the filter box above the rows to keep the accounts containing the
text in any column, click a header to sort (again to reverse), and use the
column picker to show the **E-mail** column. **Copy** puts the rows the table
shows, with their headers, on the clipboard; **Export CSV** writes them to a
file.

## Editing

Select a row and edit the fields on the right. Changes stay local until
**Save** — **Revert** discards them after asking, and the status line says
*unsaved changes* while there are any. **New** starts a blank account.
A reason the account cannot be saved yet (a missing display name, a malformed
e-mail, a username already taken) appears above the fields as you type, rather
than after a round trip to the server.

**Renaming** an account also moves its stored session token, so you stay signed
in. `user_default` and `guest` are built in and cannot be renamed or deleted.

## Passwords

**Password…** opens the strength-checked prompt: the new password and its
confirmation are shown as stars, and a bar rates length, lower case, upper case,
a digit and a special character. An empty password and two entries that differ
are refused. The new password is *staged*: it is applied when you press **Save**, and the status line tells you
one is waiting. Administrators are held to a stronger password than other
accounts.

Passwords are never stored on this machine — they are sent to the server, which
stores only a hash.

## Deleting

**Delete** asks before it removes the selected account, and only that one. The server refuses to delete an account that owns committed data, so that data
never becomes orphaned. An administrator is then offered a forced deletion,
which removes the account and leaves its data in place. The account ChiSurf is
currently using cannot be deleted at all — switch to another one first.

## Further reading

- [Settings reference](docs/reference/settings.md)
