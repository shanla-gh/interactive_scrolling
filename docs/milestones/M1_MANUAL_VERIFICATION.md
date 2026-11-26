# M1 manual verification checklist

Automated tests cover everything that can be checked without a person in front of the
camera. The items below need a human. Run the application with `scripts\run.ps1`, then
record each result (pass / fail and notes) in `PROJECT_STATUS.md`.

## Camera

- [ ] *Start camera* shows the live image within about 1 s; status shows LIVE.
- [ ] *Stop camera* clears the image; the camera LED turns off.
- [ ] Start/stop five times in a row; every start works.
- [ ] With another app (e.g. the Windows Camera app) holding the camera, *Start camera*
      shows a readable error instead of crashing; after closing the other app, Start works.
- [ ] *Scan* lists the webcam; selecting it and starting works.
- [ ] Each resolution (640x480, 1280x720, 1920x1080 if supported) starts and the bottom-left
      HUD shows the delivered resolution.

## Hand tracking and skeleton

- [ ] Raise one open hand: 21 landmarks appear on the joints and fingertips, the skeleton
      follows the fingers without visible offset.
- [ ] Spread, bend and close the fingers: bones stay on the fingers.
- [ ] Handedness label says RIGHT for your right hand and LEFT for your left hand, both with
      mirroring on and off.
- [ ] Two hands: both are tracked, in different colours (right = green, left = cyan).
- [ ] Move a hand out of the frame: its skeleton, box, label, trail and arrows disappear
      immediately; the panel shows 0 hands.
- [ ] Resize and maximize the window: the overlay stays aligned with the hand.
- [ ] Toggle each overlay checkbox: exactly that layer appears/disappears.

## Motion

- [ ] Hold a hand still: no arrows; panel direction shows "Stationary".
- [ ] Move the index finger left, right, up and down: arrow and panel direction match the
      movement as seen on screen, with mirroring on and off.
- [ ] Faster movement gives a longer arrow and higher palms/s; the trail follows the fingertip.
- [ ] Move the hand out of view and back in at a different place: no arrow spike on re-entry.
- [ ] Rapid waving: tracking may drop briefly but recovers; no stale skeleton remains.

## Application

- [ ] UI stays responsive (buttons, resizing) while tracking two hands.
- [ ] Closing the window while the camera runs exits within a second and turns the LED off.
