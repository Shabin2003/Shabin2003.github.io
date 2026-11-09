# Shabin2003.github.io

Portfolio built from my public GitHub repos. It rebuilds every 6 hours and on every push here.

## Updating it

- **New project:** create a public repo and give it a description. It appears on the next build.
- **Put a project in Selected work:** add the topic `featured` to the repo.
- **Hide a project:** add the topic `hide-from-portfolio` to the repo.
- **Filter tags:** every other repo topic becomes a filter.
- **Live demo link:** set the repo's Website field. Links that don't respond are hidden.
- **Project image:** set a custom social preview in the repo's settings.
- **Bio, skills, experience, contact:** edit `site.yml`.

To update right away, run **Deploy site** from the Actions tab.

## Local build

```bash
pip install -r requirements.txt
python build.py
python -m http.server 8123 --directory _site
```

Logs are written to `logs/build.log`.
