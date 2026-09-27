# Tests

- CSV core: `python -m unittest discover -s tests -v` (Python 3.10+, Tkinter)
- Browser smoke tests: install `playwright` and `jszip` locally, then run `node tests/smoke.js` with Google Chrome installed. Set `CHROME_PATH` if Chrome is elsewhere.

The browser tests check the six ToolsHub entries other than the IEC voltage flow. PDF conversion tests additionally require access to the CDN libraries referenced by the two PDF tools.
