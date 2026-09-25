# Barrier audit

For each task you line up a noise barrier's recorded position with the
real wall on an aerial photo. This takes about 2–3 hours in total, best in sittings of up to an hour. You
can stop at any time: every answer is saved as soon as you give it, and
the app continues where you left off.

## Starting

1. **Unzip the folder first.** Right-click the zip, choose **Extract All**,
   and pick a normal folder such as Documents or the Desktop.
2. Double-click `start_audit.bat`. A black window opens. Leave it open
   while you work.
3. Your browser opens the audit. If it doesn't, copy the address shown in
   the black window (it starts with `http://127.0.0.1:`) into the browser.
4. Maximise the browser window, wait for the three checks, then press
   **Start**.

## Each task

The pink line is where the barrier is recorded. That is always the
**centre of the road or track**, not where the wall stands. The barrier
always runs left to right on screen.

- **Drag the photo** until the pink line lies on the wall, then press
  **Submit** (`Enter`). Only up/down movement counts. Moving along the
  wall is fine for checking it.
- Match the **foot of the wall or its shadow line**, not its top. Walls
  lean a little in the photo.
- Fine-tune with `↑` / `↓` (0.25 m; hold `Shift` for 2 m). Scroll to zoom
  in or out.
- Hold `Space` to hide the line for a moment. Press `R` to reset.
- The dashed white line shows where you started.
- If the wall stands in the middle of the road or between tracks, submit
  it there. The app asks you to confirm.
- If there is a wall on **both sides** of the road or railway along this
  stretch, press **Both sides** (`B`) instead of lining up one of them.
- Orange lines are other barriers in the register, also drawn at their
  road or track centre. They help you see which walls belong together;
  always answer for the pink line.
- **Street View** (`G`, road barriers only) opens Google Street View in a
  second browser tab, standing on the road and looking along the
  barrier. The barrier's left in Street View is up in the app. Use it
  when the photo leaves you unsure, for example when trees hide the wall
  or a glass screen barely shows. Then come back and line up the wall in
  the app: Street View tells you which side, and the photo tells you
  where. If you can see the wall only in Street View, move the line to
  roughly where it stands and submit. Check the date in
  Street View's corner: if the pictures are older than the wall, it may
  not be there yet. Pressing `G` again reuses the same tab.
- If you can't place the line, press **Unsure** (`U`) and pick a reason:
  1. hidden by trees, shadow or an image seam
  2. no wall visible along this stretch
  3. something else (write a short note)
- Tasks come area by area: the top bar shows the area and how many tasks
  are left there.
- `Backspace` goes back to the previous task. Answering it again simply
  replaces your earlier answer.

The first 10 tasks are practice. After each one, a green line shows where
the wall really is.

## When you are done

The page tells you the file to send:
`answers/answers_<name>.jsonl`, inside the unzipped folder. Email it to
Felix, or put it in the shared folder. You can also send it part-way
through.

## If something goes wrong

- **The black window closes at once, or can't find Python.** Open
  **Anaconda Prompt** and type:

  ```
  cd /d "C:\path\to\the\unzipped\folder"
  python -m barrier_audit
  ```

- **"The answer was not saved".** The black window was probably closed.
  Start it again and reload the page. Nothing already saved is lost.
- **The photo stays grey.** Check your internet connection, then reload
  the page.
