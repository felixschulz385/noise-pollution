# Barrier audit: device check

This checks that the audit app works on your laptop before we send the real
tasks. It takes about 10 minutes and installs nothing.

## Steps

1. **Unzip the folder first.** Right-click the zip, choose **Extract All**,
   and pick a normal folder such as Documents. Don't run it from inside the
   zip.
2. **Start the app.**
   - Windows: double-click `start_audit.bat`. If Windows warns about an
     unknown app, click **More info**, then **Run anyway**. A black window
     opens. Leave it open.
   - Mac: right-click `start_audit.command` and choose **Open**.
3. Your browser opens the check page. If it doesn't, copy the address shown
   in the black window (it starts with `http://127.0.0.1:`) into the
   browser.
4. Wait until the automatic checks show ✓, ! or ✗ (up to a minute). Then do
   the three short steps under the map.
5. **Send the report back.** The page tells you the file name. It is inside
   the unzipped folder, at `answers/device_check_<date and time>.json`.
   Email it to Felix, even if something shows ✗.
6. Close the browser tab and the black window.

## If something goes wrong

- **The black window closes straight away, or says it can't find Python.**
  Open **Anaconda Prompt** from the Start menu and type:

  ```
  cd /d "C:\path\to\the\unzipped\folder"
  python -m barrier_audit
  ```

- **The page can't save the report.** Take a screenshot of the page and
  send that instead.
- **The imagery check fails.** Say which network you were on (university
  network, VPN or home). Then try once from another network if you can.
