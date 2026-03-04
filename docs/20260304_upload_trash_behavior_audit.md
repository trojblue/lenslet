# Upload and Trash Behavior Audit (2026-03-04)

## Scope

Document current behavior for:

- Uploading images
- Moving images to trash
- Recovering or permanently deleting trashed images

This captures what the frontend expects, what the backend currently exposes, and the user-visible result in `lenslet <dir>` mode.

## Frontend Wiring (Current)

### Upload entry points

- Toolbar upload button is rendered when not in fullscreen viewer:
  - `frontend/src/shared/ui/Toolbar.tsx` (around `onUploadClick`)
- Mobile drawer also exposes upload:
  - `frontend/src/shared/ui/toolbar/ToolbarMobileDrawer.tsx`
- Upload input is a hidden `<input type="file" multiple accept="image/*">` in:
  - `frontend/src/app/AppShell.tsx`

### Upload action flow

- Upload behavior is orchestrated in:
  - `frontend/src/app/hooks/useAppActions.ts`
- Guardrail:
  - Upload is allowed only when current folder has no subdirectories (`currentDirCount === 0`).
- API call per file:
  - `api.uploadFile(current, file)`
- Drag/drop upload also calls the same upload flow.

### Trash / move / delete entry points

- Grid item context menu is built in:
  - `frontend/src/app/menu/AppContextMenuItems.tsx`
- Menu items include:
  - `Move to...`
  - `Move to trash`
  - In trash scope only: `Permanent delete`, `Recover`
- Trash detection is path-based:
  - `frontend/src/app/routing/hash.ts` (`isTrashPath` checks `endsWith('/_trash_')`)

### Trash / move / delete action flow

- Move to trash:
  - `api.moveFile(path, '/_trash_')`
- Move to specific folder:
  - `api.moveFile(path, targetDir)`
- Permanent delete:
  - `api.deleteFiles(selectedPaths)`
- Recover:
  - fetch sidecar (`api.getSidecar(path)`), then move to original parent directory:
    - `api.moveFile(path, targetDir)`

## Frontend API Contract (Expected by UI)

Defined in `frontend/src/api/client.ts`:

- Upload: `POST /file` with `FormData(dest, file)`
- Move: `POST /move` with `FormData(src, dest)`
- Delete: `POST /delete` with JSON `{ paths: [...] }`
- Also present: `POST /export-intent`

## Backend Route Surface (Current)

Backend routes are registered via:

- `src/lenslet/server_factory.py`
- `src/lenslet/server_routes_common.py`

Current route surface includes:

- `GET /file`
- No `POST /file`
- No `/move`
- No `/delete`
- No `/export-intent`

OpenAPI route listing confirms only `GET /file` for file endpoint.

## Runtime Verification

A direct in-process probe against `create_app(...)` in browse mode shows:

- `GET /file` -> `200`
- `POST /file` -> `405 Method Not Allowed`
- `POST /move` -> `405 Method Not Allowed`
- `POST /delete` -> `405 Method Not Allowed`
- `POST /export-intent` -> `405 Method Not Allowed`

This was verified on 2026-03-04.

## User-Visible Outcome in `lenslet <dir>`

- Upload button/menu affordances are visible in UI (depending on mode/viewport).
- Trash/move/delete actions are visible in context menu.
- Mutation requests hit non-existent/unsupported backend methods and fail with `405`.
- Net effect: no actual upload/move/trash/delete mutation occurs.

## Notes on Error UX

- `useAppActions` treats `405` as a read-only-style mutation failure and can surface:
  - `"This workspace is read-only. Upload and move actions are disabled."`
- Context-menu trash/recover/delete handlers mostly log failures to console and continue.

## Conclusion

Upload/trash flows are currently frontend-wired but backend-disabled (or not implemented in this route set). In practical terms they are non-functional placeholders in current browse mode.
