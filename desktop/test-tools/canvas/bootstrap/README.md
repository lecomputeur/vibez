# Historical targeted-fix blank-popup regression

This frozen contract records the targeted `3.0.9+test.1` behavior. It expects a
delayed automatic external navigation to invoke the browser in a Canvas popup.
The structural policy introduced in `3.0.9+test.2` intentionally prevents that
automatic browser launch. Use `../structural/run.py` for the current blank-popup,
iframe-auth and main-auth-redirect release gate; this historical contract is not
a pass criterion for test.2.

```
python3 run.py --binary /absolute/candidate/vibez3 --expect fixed --scenario canvas --output /absolute/empty-results
python3 run.py --binary /absolute/candidate/vibez3 --expect fixed --scenario oauth --output /absolute/empty-results
python3 -m unittest discover -s . -p 'test_*.py'
```

Uses a private Xvfb/Openbox, DBus session and disposable profile with a harmless
opener recorder. Requires the same Linux dependencies as the Canvas routing
runner. Installs nothing. A preload substitutes only the initial Mistral
fixture and observes native signals; application handlers are unchanged.

One trusted click opens about:blank. The child runs its own script, a nested
srcdoc script and a Cloudflare challenge iframe before navigating to the Canvas
or provider origin. The report requires actual srcdoc script messages and native
resource-start evidence for challenge and target.

A later ordinary HTTPS navigation is the purpose oracle: Canvas must use the
external opener and remain limited, while the OAuth model must continue inside
the related webview. Both retain opener semantics. Optional remote get_state may remain pending,
which is reported as unconfirmed rather than denied; the separate native smoke
checks actual privilege rejection. Any returned native state fails the report.
This catches a challenge-subframe callback misclassifying Pending before its
real Canvas/provider destination arrives.

All remote test paths are deliberately nonexistent. This tests routing and
purpose, not a real Canvas, successful Turnstile or provider sign-in. Old 3.0.8
is expected to fail this fixed contract; only the candidate is gated here.
