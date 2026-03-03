**Inspector Behavior & Metadata Improvements**

1. **Modify “Hide Left Panel” behavior**
   Instead of collapsing the entire inspector when pressing *Hide Left Panel* (or its shortcut), only collapse the currently active large tab. The leftmost slide should remain visible.
2. **Allow direct collapse from active tab buttons**
   Once the above is implemented, enable collapsing the (left side, folder tree or metrics) view panel by clicking the active **Folder** or **Metrics** button while already in that respective view.
3. **Increase maximum width of right-side inspector**
   Allow the right-side inspector panel to be resized significantly wider than its current limit, so metadata can be viewed more comfortably.
4. **Enable reordering of inspector sections**
   Allow users to drag and reorder sections within the inspector (e.g., placing “Metadata” above “Basics” instead of the fixed Basics → Meta → Notes layout).
5. **Metadata comparison for multiple selections**
   When more than two images are selected, allow metadata comparison directly from the inspector via a button (not limited to side-by-side view).
6. **Auto-display comparison when auto-load is enabled**
   If **Auto Load Image Meta** is ON and multiple images are selected, automatically show metadata comparison without requiring an additional button click.
7. **Expand comparison limit and improve UI**
   Remove the current two-item comparison limit.
   Allow comparison of up to six images at once.
   Keep a structured, tabular-style layout, but improve the UI if needed.
   Intended workflow: select images → expand inspector wide → compare metadata clearly.
8. **Adjust GIF mode notice**
   Remove the persistent notice:
   *“GIF mode: 1.5s/frame, max 720px long side; capped to 8MB.”*
   Instead, show this information as a hover tooltip on Export GIF.
9. **Add PNG metadata extraction section**
   When **Auto Load Image Meta** is ON and an image is selected:
   - Add a new inspector section at the top (unless reordered).
   - Attempt to read and display: **Prompt**, **Model**, and **LoRA** fields from PNG metadata.
   - Use Image /local/yada/dev/lenslet/docs/test_meta.png as a reference for default metadata field targeting.
   - Allow adding “Quick View” JSON fields.
   - Make each displayed field clickable to copy its value to the clipboard.
10. **Adjust default inspector order**
    Change the default order so that **Basics** and **Metadata** are rearranged (new preferred order to replace current Basics → Metadata → Notes structure).

