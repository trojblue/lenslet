# Touch Readiness Sprint S1 Smoke Checklist

Run from `/home/ubuntu/dev/lenslet`.

## Command Checks

1. `cd /home/ubuntu/dev/lenslet/frontend && npm run test`
2. `cd /home/ubuntu/dev/lenslet/frontend && npm run build`

## Manual Smoke (Tablet Profile)

1. Start app: `cd /home/ubuntu/dev/lenslet && lenslet ./data --reload --port 7070`
2. Open `http://127.0.0.1:7070` in tablet emulation (e.g. iPad Air 820x1180).
3. In grid:
   - Long-press an item and confirm context actions open without right-click.
   - Tap the explicit `...` action button and confirm actions open.
4. In folder tree:
   - Expand/collapse using the dedicated chevron button.
   - Tap the explicit `...` row action button and confirm folder actions open.
5. Move flow:
   - Select one or more items.
   - Open actions -> `Move to…`.
   - Pick destination and confirm files move via dialog flow.
6. Upload flow:
   - Use toolbar `Upload` button (not drag-and-drop).
   - Select files and confirm upload completes.
   - In read-only/no-write mode, confirm a clear read-only error message is shown.
7. Menu clamping:
   - Open context/dropdown menus near viewport edges at ~390px and ~768px widths.
   - Confirm menus remain on-screen.
