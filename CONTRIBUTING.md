# Contributing

Thanks for your interest. This is a personal open-source project with a milestone-based
plan (see [ROADMAP.md](ROADMAP.md)).

1. Read [docs/ENGINEERING_CONVENTIONS.md](docs/ENGINEERING_CONVENTIONS.md). It defines
   the commit style, quality rules, testing requirements and privacy rules.
2. Set up the environment with `scripts\setup.ps1` (see [README.md](README.md)).
3. Run `scripts\test.ps1` before opening a pull request. If your change touches camera or
   tracking behaviour, also run `scripts\test.ps1 -Hardware` and describe what you verified
   by hand.
4. Keep pull requests focused; add tests for new behaviour and a regression test for every
   fixed bug.

Never include webcam images, recordings or personal data in issues, commits or pull requests.
