---
name: use-the-computer
description: >-
  Do work outside ChiSurf by running programs on the machine — unpacking
  archives, converting vendor formats, calling other analysis software,
  moving results into place. Use when the job needs a tool that is not part
  of ChiSurf.
triggers:
  - unzip
  - unpack
  - zip
  - zip file
  - extract
  - tar
  - archive
  - convert
  - install
  - installed
  - terminal
  - shell
  - command
  - run the program
  - copy the files
  - rename
  - folder structure
tools:
  - run_command
  - which_program
  - list_directory
  - read_file
  - write_file
---

# Working outside ChiSurf

`run_command` runs anything installed on the machine, in the user's own
account, with their own permissions. There is no sandbox — that is the point,
because a sandbox would block the vendor converter you were asked to run — so
the discipline is yours.

## Before running anything

1. **Look first.** `list_directory` to see what is actually there, and
   `which_program` before building a command around a tool that may not be
   installed. "ImageMagick is not installed on this machine" is a useful
   answer; a command that dies with *not found* is not.
2. **Say what you are about to do.** The user sees the command and can refuse
   it, but they should not have to reverse-engineer your intent from a shell
   line. One sentence: what it does and why.
3. **Quote paths.** Measurement files are full of spaces and parentheses —
   `215-268 D0 irf.dat` will fall apart unquoted.

## Rules that keep this safe

* **Prefer the ChiSurf tools.** Loading, fitting and exporting go through the
  session, which knows about the objects; a shell command does not, and
  results produced behind ChiSurf's back will not appear in the user's
  windows or project.
* **Never delete or overwrite the user's data.** Write new files; leave the
  originals alone. If a job genuinely requires replacing something, say so and
  let the user decide.
* **Work on copies** when a conversion is destructive, and put outputs in a
  new sub-directory rather than scattering them beside the data.
* **One step at a time** when the outcome is uncertain. Run, read the output,
  then decide — do not chain five commands with `&&` and hope.
* **Read the exit code**, not just the output. A non-zero status means it
  failed even if something was printed.
* **Do not install software** or change system configuration unless asked
  directly. Report what is missing and let the user choose.

## Long jobs

A command is killed at `timeout_s` (120 s by default). For something genuinely
long, raise it deliberately and tell the user it will take a while, rather
than discovering the timeout twice.

## Writing scripts to disk

When the user wants something repeatable, `write_file` a script and tell them
how to run it, instead of executing a long one-liner they cannot inspect or
reuse. See also the `write-analysis-script` skill for code that has to run
*inside* the session.
