# Grabber download and copy

Step 1 of the page's Data tab lets people get `garmin_grab.py` without visiting GitHub.

## Embedded source

The script lives inside the page:

```html
<script type="text/plain" id="grabber-src">…garmin_grab.py…</script>
```

`type="text/plain"` means the browser never executes it. The page reads it with `textContent` and shows it in the "View the script" panel. The only forbidden sequence is `</script`, which `tools/build.py` checks for.

`tools/build.py` (`make build`) fills the block with the bundled `garmin_grab.py` when it builds `index.html`. In the unbuilt `src/page/index.html` (`make dev`) the block is empty, so "View the script" and "Copy script" have nothing to show.

## Download link

"Download garmin_grab.py" links to `https://github.com/DavideBisio/garmin-run-progress/releases/latest/download/garmin_grab.py`, the asset of the newest [release](../deploy.md#releasing-a-change). It works on any host, but returns 404 until the first release exists.

## Copy buttons

`copyText` tries `navigator.clipboard.writeText` inside the click handler, then falls back to a hidden `<textarea>` + `document.execCommand("copy")`. If both fail the button says "Select and copy manually". The setup and run command blocks use the same helper.

## Zip download

The "Download grabber (.zip)" button produces `garmin_grabber.zip` containing `garmin_grab.py` and a `README.txt`.

`makeZip` (`src/page/js/zip.js`) is a ~40-line ZIP writer using the **stored** method (no compression; the files are small):

- local file header (`0x04034b50`) + name + data for each file
- central directory entry (`0x02014b50`) for each file, with the local header offset
- end-of-central-directory record (`0x06054b50`)
- CRC-32 from a precomputed 256-entry table (polynomial `0xEDB88320`)
- general-purpose flag `0x0800` marks names as UTF-8; DOS date/time from the current clock

### When the button is shown

The button is hidden by default. It appears only when the page runs inside a claude.ai artifact viewer that grants the `downloads` capability (`await window.claude.use("downloads")`). There, the viewer shows a save confirmation and the page calls `downloads.save({filename, data})`. The platform does not allow `.py` files, which is why the script ships inside a zip.

On GitHub Pages or a local file, `window.claude` doesn't exist, so the button stays hidden. People use "Download garmin_grab.py" or "Copy script" instead.

Errors: `declined` is silent, `rate_limited` shows a short message, anything else hides the button and points to "Copy script".
