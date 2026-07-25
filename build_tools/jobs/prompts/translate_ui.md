You are running as an **unattended scheduled job** in the ChiSurf repository.
Your one task is to keep the UI-translation catalogues up to date, then stop.
Work autonomously; do not ask questions. Read `CLAUDE.md` first for environment
and git rules, and honour them strictly.

## Task: translate the UI

1. **Extract.** Regenerate the `.ts` catalogues so newly added UI strings appear:
   run `pixi run i18n-extract` (fallback if pixi is unavailable:
   `PYTHONPATH="modules/mmfdb/src:modules/chinet:modules/imp-tricks/src:." python build_tools/i18n/extract_strings.py`
   using the project's arm64 conda env). This is non-destructive — it preserves
   finished translations and only adds new `type="unfinished"` entries.

2. **Translate the untranslated.** For each shipped locale (`de`, `fr`) in
   `chisurf/gui/i18n/chisurf_<code>.ts`, find messages that are unfinished/empty
   and are genuinely translatable, and translate them in place. **Skip** strings
   that must stay verbatim — Qt signal/slot object names (`onParametersChanged`,
   `FormulaChanged`), keyboard shortcuts, pure math/axis symbols (`si(w,E)`,
   `r_D∞`, `k₁₂`), units (` MHz`, ` cm³/g`), hardware/format IDs (`PTU`,
   `SPC-130`), file names, URLs, and bare code identifiers. These correctly fall
   back to English, exactly as the existing catalogues do.

   Follow the established terminology so the catalogues stay consistent:
   - German: Mikrozeit/Makrozeit, Detektor, Zerfall (decay), Lebensdauer
     (lifetime), Faltung (convolution), Anisotropie, Anteil (fraction), Kanal,
     Anpassung/Fit, Hintergrund (background), G-Faktor, Bündel/Burst.
   - French: micro-temps/macro-temps, détecteur, déclin (decay), durée de vie
     (lifetime), convolution, anisotropie, fraction, voie/canal, ajustement/Fit,
     bruit de fond (background), facteur G, phaseur, salve (burst).
   Edit only the `<translation>` body of unfinished messages; leave every other
   byte untouched so the diff stays minimal.

3. **Rebuild.** Compile the catalogues to runtime `.qm`:
   `pixi run i18n-compile` (fallback:
   `lrelease chisurf/gui/i18n/chisurf_en.ts chisurf/gui/i18n/chisurf_de.ts chisurf/gui/i18n/chisurf_fr.ts`).

4. **Commit — carefully.** This is a **shared working tree edited by other
   processes concurrently.** Commit ONLY the translation catalogues, by explicit
   pathspec, and never sweep in anything else:
   `git commit -- chisurf/gui/i18n/chisurf_de.ts chisurf/gui/i18n/chisurf_de.qm chisurf/gui/i18n/chisurf_fr.ts chisurf/gui/i18n/chisurf_fr.qm`
   (drop any path that has no changes). If a catalogue has no new translations,
   commit nothing. **Never** push, `git add -A`, `git reset`, `git rebase`,
   `git stash`, `git checkout --`, or `--force`. No commit trailers.

5. If there was nothing to translate, exit quietly without a commit.

Keep it focused: extract → translate the real strings → compile → commit the
`.ts`/`.qm` only. Then you are done.
