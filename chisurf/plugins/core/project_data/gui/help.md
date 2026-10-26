# Project data

A project **links** its large data files (photon streams, images, burst containers) instead of copying
them: it records where each file is, its size and its SHA-256 checksum. The project stays small and never
duplicates a measurement. This window lists those links, finds files that were moved, and stores them all
inside the project when it has to travel alone.

## How it works
1. The table lists every linked dataset of the open project: **found**, **embedded** (stored inside the
   project), **missing**, **size changed** or **content changed**, and where its file is or was. Opening a
   project compares sizes only; **Check checksums** reads every file and compares its checksum too.
2. To find a moved file, select it and press **Search in folder…**: every file below the chosen folder with
   the same name is listed, those with the recorded size first. **Use candidate** checks the chosen one's
   checksum and links the dataset to it. **Replace with…** points at a file directly (a renamed original).
3. A file whose size or checksum differs is refused. **Use anyway** accepts it and records its checksum --
   only for a file you know is the right data although it changed.
4. **Make self-contained** stores every linked file inside the project at its next save; missing files must
   be located first. The project then needs no other file: share it, archive it, deposit it. A Zenodo
   deposit refuses a project that is not self-contained unless you override it explicitly.

Right-click a dataset in the Datasets panel to embed it alone, or to write an embedded file back out and
link it again. **Add as** on the Read data page decides how read or dropped files enter the project.

## Before trusting a result
A file that was replaced with **Use anyway** is not the file earlier results were computed from; recompute
them. Embedding makes the project as large as its data.

## Further reading
- [The photon container: addresses and links](docs/concepts/photon_container.md)
