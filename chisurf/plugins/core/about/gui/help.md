# About ChiSurf

This window identifies the ChiSurf application you are running. It is useful when reporting a problem, checking an installation or finding the project and developer contact. Opening it does not load a measurement, change an analysis, start a calculation or contact an external service.

## Version and identity

The version shown is read from this running installation. Include it when asking for help so the recipient can distinguish releases and development builds. The version is not a statement that an analysis has been validated, and it is not the version of a measurement file. The ChiSurf logo, application name and fluorescence-analysis subtitle identify the program rather than the currently selected dataset.

The developer and email address are displayed as contact information. The repository text names the project location. This window does not send email, open the repository automatically or upload a diagnostic report.

## Licence

ChiSurf is MIT-licensed; its documentation is CC BY-SA 4.0. Two companion libraries keep their own licences: tttrlib is BSD-3-Clause, and IMP.bff is LGPL-2.1-or-later. IMP.bff is installed as a separate package that ChiSurf loads at run time, so you may replace it with your own build. The installer carries both licence texts. See [Licensing](docs/licensing.md).

## Copy details

Press **Copy details** to copy the displayed application name, subtitle, version, developer, email, repository and licence text. The payload contains these application details only: it does not include measurements, filenames, fit results, credentials or user settings. Paste the text into a support request yourself, adding the steps needed to reproduce your issue.

Copy uses the clipboard supplied by the native or browser host. A successful copy shows a confirmation. If the host cannot write the clipboard, the window reports that it is unavailable and leaves the guide waiting so that you can retry. No clipboard permission is requested merely by opening this window.

## Help, guide and closing

**Help** opens this reference. Close that help window, or press Escape, to return to the About window. **Guide** waits for you to press the actual Help, Copy details and Close controls; it never copies or closes automatically. Its last action is terminal: pressing **Close** acknowledges the step and closes the About window. Your main ChiSurf window and analysis remain open.

## Further reading

- [Application identity](docs/concepts/application_identity.md)
- [Support-details workflow](docs/guides/103_application_identity.md)

- [Getting started with ChiSurf](docs/getting_started/index.md)
- [About ChiSurf plugin reference](docs/reference/plugins/about.md)
